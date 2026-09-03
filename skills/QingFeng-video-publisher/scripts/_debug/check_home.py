# -*- coding: utf-8 -*-
"""截图 + 查找高清发布按钮"""
import asyncio, websockets, json, sys, time, base64
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
        print('No douyin tab found')
        return
    
    ws_url = f'ws://127.0.0.1:{CDP_PORT}/devtools/page/{tab["id"]}'
    print(f'Tab: {tab["id"]} URL: {tab["url"][:60]}')
    
    async with websockets.connect(ws_url, ping_interval=None, open_timeout=5) as ws:
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
        
        # 截图
        r = await cdp('Page.captureScreenshot', {'format': 'png', 'quality': 70})
        img = r.get('result', {}).get('data', '')
        if img:
            path = 'C:/Users/chenw/.qclaw/media/browser/douyin_home.png'
            with open(path, 'wb') as f:
                f.write(img.encode('latin1'))
            print(f'Screenshot: {path}')
        
        # 查找所有按钮文本
        btns = await js("""(function(){
            var els = document.querySelectorAll('button, a, [role=button]');
            var t = [];
            for (var el of els) {
                var text = el.textContent.trim().substring(0, 30);
                if (text && text.length > 0 && text.length < 30) {
                    t.push(text);
                }
            }
            return JSON.stringify(t.slice(0, 30));
        })()""")
        print(f'Buttons: {btns}')
        
        # 查找含发布/上传的文字
        publish = await js("""(function(){
            var els = document.querySelectorAll('*');
            var t = [];
            for (var el of els) {
                var text = el.textContent.trim();
                if (text.includes('发布') || text.includes('上传') || text.includes('高清')) {
                    t.push(text.substring(0, 40));
                }
                if (t.length > 10) break;
            }
            // 去重
            return JSON.stringify([...new Set(t)]);
        })()""")
        print(f'Publish buttons: {publish}')

asyncio.run(main())
