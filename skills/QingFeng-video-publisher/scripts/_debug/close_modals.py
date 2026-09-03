# -*- coding: utf-8 -*-
"""关闭所有弹窗"""
import asyncio, websockets, json, sys
sys.stdout.reconfigure(encoding='utf-8')

CDP_PORT = 9222
TAB_ID = '7B9C42697B3EBE4D94FA2F9B29D5EF35'


async def main():
    ws_url = f'ws://127.0.0.1:{CDP_PORT}/devtools/page/{TAB_ID}'

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

        async def js_no_ret(expr):
            r = await cdp('Runtime.evaluate', {'expression': expr, 'returnByValue': False})
            return r

        # 关闭竖封面对话框 - 点击"暂不设置"
        r = await js_no_ret("""(function(){
            var all = document.querySelectorAll('div, button, span');
            for (var el of all) {
                var own = '';
                for (var c = el.firstChild; c; c = c.nextSibling) {
                    if (c.nodeType === 3) own += c.textContent;
                }
                own = own.trim();
                if (own === '暂不设置' || own === '取消') {
                    el.click();
                    return 'clicked:' + own;
                }
            }
            return 'NOT_FOUND';
        })()""")
        print(f'Close dialog: {r}')
        await asyncio.sleep(2)

        # 检查是否还有弹窗
        modal = await js("""(function(){
            var modals = document.querySelectorAll('[role=dialog], [class*=modal], [class*=Modal]');
            var t = [];
            for (var m of modals) {
                if (m.offsetWidth > 0 && m.offsetHeight > 0) {
                    t.push({w: m.offsetWidth, text: m.textContent.substring(0, 30)});
                }
            }
            return JSON.stringify(t);
        })()""")
        print(f'Remaining modals: {modal}')

        # 如果还有弹窗，按 Escape
        if modal and len(json.loads(modal)) > 0:
            print('Pressing Escape...')
            await js_no_ret('document.dispatchEvent(new KeyboardEvent("keydown", {key: "Escape", keyCode: 27, bubbles: true}))')
            await asyncio.sleep(2)

        # 最终检查
        modal2 = await js("""(function(){
            var modals = document.querySelectorAll('[role=dialog], [class*=modal-wrap], [class*=modal-mask]');
            var visible = [];
            for (var m of modals) {
                if (m.offsetWidth > 0 && m.offsetHeight > 0) {
                    visible.push(m.offsetWidth);
                }
            }
            return JSON.stringify(visible);
        })()""")
        print(f'Final modals: {modal2}')

        # 检查封面是否已设置
        cover_status = await js("""(function(){
            var text = document.body.innerText;
            return {
                hasMissing: text.includes('封面缺失'),
                hasDoubleCover: text.includes('双封面') || text.includes('横封面') && text.includes('竖封面'),
                hasBlob: document.querySelectorAll('img[src*="blob"]').length > 0
            };
        })()""")
        print(f'Cover status: {cover_status}')

        # 标题和简介最终确认
        title = await js("""(function(){
            var inputs = document.querySelectorAll('input[placeholder]');
            for (var el of inputs) {
                if (el.getAttribute('placeholder').includes('标题') && el.offsetWidth > 100) return el.value;
            }
            return '';
        })()""")
        desc = await js("""(function(){
            var el = document.querySelector('div[contenteditable=true].zone-container') ||
                     document.querySelector('div[contenteditable=true].editor-kit-container');
            return el ? el.textContent.substring(0, 60) : 'NOT_FOUND';
        })()""")
        print(f'Title: {title}')
        print(f'Desc: {desc}')

        print('\n=== ALL DONE ===')
        print('Please review and publish manually!')


asyncio.run(main())
