# -*- coding: utf-8 -*-
"""查找高清发布按钮"""
import asyncio, websockets, json, sys
sys.stdout.reconfigure(encoding='utf-8')
CDP_PORT = 9222

async def main():
    import urllib.request
    resp = urllib.request.urlopen(f'http://127.0.0.1:{CDP_PORT}/json', timeout=5)
    tabs = json.loads(resp.read())
    tab = None
    for t in tabs:
        if 'creator.douyin.com' in t.get('url', ''):
            tab = t
            break
    if not tab:
        print('No douyin tab')
        return
    
    ws_url = f'ws://127.0.0.1:{CDP_PORT}/devtools/page/{tab["id"]}'
    print(f'Tab: {tab["id"]} URL: {tab["url"][:80]}')
    
    async with websockets.connect(ws_url, ping_interval=None, open_timeout=5, max_size=5*1024*1024) as ws:
        mid = [0]
        async def cdp(method, params=None):
            mid[0] += 1
            await ws.send(json.dumps({'id': mid[0], 'method': method, 'params': params or {}}))
            for _ in range(30):
                r = json.loads(await asyncio.wait_for(ws.recv(), timeout=15))
                if r.get('id') == mid[0]:
                    return r
            return {}
        
        async def js(expr):
            r = await cdp('Runtime.evaluate', {'expression': expr, 'returnByValue': True})
            return r.get('result', {}).get('result', {}).get('value', '')
        
        # 等页面加载
        await asyncio.sleep(2)
        
        # 查找含发布/上传的文字
        publish = await js("""(function(){
            var els = document.querySelectorAll('button, a, [role=button], span, div');
            var t = [];
            for (var el of els) {
                var own = '';
                for (var c = el.firstChild; c; c = c.nextSibling) {
                    if (c.nodeType === 3) own += c.textContent;
                }
                own = own.trim();
                if (own.includes('发布') || own.includes('上传') || own.includes('高清') || own.includes('content/post')) {
                    t.push({tag: el.tagName, text: own.substring(0, 30), class: (el.className||'').toString().substring(0, 40)});
                }
                if (t.length > 15) break;
            }
            return JSON.stringify(t);
        })()""")
        print(f'Publish elements: {publish}')
        
        # 也找 SVG 和 icon 相关
        icons = await js("""(function(){
            var els = document.querySelectorAll('[class*=publish], [class*=upload], [class*=post], [data-e2e*=publish]');
            var t = [];
            for (var el of els) {
                t.push({tag: el.tagName, text: el.textContent.trim().substring(0, 20), class: el.className.toString().substring(0, 40)});
            }
            return JSON.stringify(t.slice(0, 10));
        })()""")
        print(f'Icon elements: {icons}')
        
        # 直接导航到发布页试试
        print('\nTry direct navigate to post page...')
        r = await cdp('Page.navigate', {'url': 'https://creator.douyin.com/creator-micro/content/upload'})
        await asyncio.sleep(5)
        url = await js('window.location.href')
        print(f'  URL: {url}')
        
        # 检查 file inputs
        r = await cdp('DOM.getDocument', {'depth': 0})
        root_id = r.get('result', {}).get('root', {}).get('nodeId')
        r = await cdp('DOM.querySelectorAll', {'selector': 'input[type=file]', 'nodeId': root_id})
        nids = r.get('result', {}).get('nodeIds', [])
        print(f'  File inputs: {nids}')
        
        r2 = await js("""(function(){
            var ins = document.querySelectorAll('input[type=file]');
            var t = [];
            for (var i = 0; i < ins.length; i++) {
                t.push({i:i, accept:ins[i].accept.substring(0,30), w:ins[i].offsetWidth, h:ins[i].offsetHeight});
            }
            return JSON.stringify(t);
        })()""")
        print(f'  JS inputs: {r2}')

asyncio.run(main())
