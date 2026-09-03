# -*- coding: utf-8 -*-
"""抖音 5.1 - 最终状态检查"""
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

        # 检查标题
        title = await js("""(function(){
            var inputs = document.querySelectorAll('input[placeholder]');
            for (var el of inputs) {
                if (el.getAttribute('placeholder').includes('标题') && el.offsetWidth > 100) {
                    return el.value;
                }
            }
            return '';
        })()""")
        print(f'Title: {title}')

        # 检查简介
        desc = await js("""(function(){
            var el = document.querySelector('div[contenteditable=true].zone-container') ||
                     document.querySelector('div[contenteditable=true].editor-kit-container');
            return el ? el.textContent.substring(0, 80) : 'NOT_FOUND';
        })()""")
        print(f'Desc: {desc}')

        # 检查封面区域
        cover = await js("""(function(){
            var info = [];
            // 横封面预览图
            var imgs = document.querySelectorAll('img');
            for (var img of imgs) {
                var rect = img.getBoundingClientRect();
                if (rect.width > 50 && rect.height > 50) {
                    info.push({src: img.src.substring(0, 80), w: Math.round(rect.width), h: Math.round(rect.height)});
                }
            }
            return JSON.stringify(info.slice(0, 10));
        })()""")
        print(f'Images: {cover}')

        # 检查是否有封面预览（blob 图片表示自定义封面）
        blobs = await js("""(function(){
            var count = 0;
            var imgs = document.querySelectorAll('img');
            for (var img of imgs) {
                if (img.src.indexOf('blob') >= 0 && img.offsetWidth > 50) count++;
            }
            return count;
        })()""")
        print(f'Blob images (custom covers): {blobs}')

        # 检查是否还有弹窗
        modal = await js("""(function(){
            var modals = document.querySelectorAll('[role=dialog], [class*=modal], [class*=Modal]');
            var t = [];
            for (var m of modals) {
                if (m.offsetWidth > 0 && m.offsetHeight > 0) {
                    t.push({w: m.offsetWidth, h: m.offsetHeight, text: m.textContent.substring(0, 40)});
                }
            }
            return JSON.stringify(t);
        })()""")
        print(f'Modals: {modal}')

        # 检查发布按钮状态
        publish = await js("""(function(){
            var btns = document.querySelectorAll('button');
            for (var b of btns) {
                var text = b.textContent.trim();
                if (text === '发布' || text === '立即发布') {
                    return {text: text, disabled: b.disabled, cls: b.className.toString().substring(0, 50)};
                }
            }
            return 'NOT_FOUND';
        })()""")
        print(f'Publish button: {publish}')


asyncio.run(main())
