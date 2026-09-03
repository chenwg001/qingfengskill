# -*- coding: utf-8 -*-
"""抖音 5.1 - Step 3: 封面上传（JS 方式）"""
import asyncio, websockets, json, sys, os, base64
sys.stdout.reconfigure(encoding='utf-8')

CDP_PORT = 9222
TAB_ID = '7B9C42697B3EBE4D94FA2F9B29D5EF35'

COVER_4x3 = r'D:\个人\资源\个人文章\AI育见\5.1\5.1-封面_4x3.jpg'
COVER_3x4 = r'D:\个人\资源\个人文章\AI育见\5.1\5.1-封面_3x4.jpg'


async def main():
    ws_url = f'ws://127.0.0.1:{CDP_PORT}/devtools/page/{TAB_ID}'

    async with websockets.connect(ws_url, ping_interval=None, open_timeout=5, max_size=10*1024*1024) as ws:
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

        # 读取封面文件为 base64
        with open(COVER_4x3, 'rb') as f:
            b64_4x3 = base64.b64encode(f.read()).decode()
        with open(COVER_3x4, 'rb') as f:
            b64_3x4 = base64.b64encode(f.read()).decode()
        
        cover_4x3_bytes = len(b64_4x3) * 3 // 4
        cover_3x4_bytes = len(b64_3x4) * 3 // 4
        print(f'Cover 4:3: {cover_4x3_bytes} bytes')
        print(f'Cover 3:4: {cover_3x4_bytes} bytes')

        # 用 JS 设置文件到 hidden file input + 触发 change
        # 这需要分步：先读 b64 到内存，然后构造 File，设置到 input
        
        # Step 1: 上传 4:3 封面
        print('\n[Step 1] Uploading 4:3 cover via JS...')
        # 注入 base64 数据到 window 对象
        r = await js(f"window._cover4x3_b64 = '{b64_4x3}'; 'injected'")
        
        # 创建 File 对象并设置到 file input
        r = await js_no_ret("""(function(){
            // 找到所有 file input
            var inputs = document.querySelectorAll('input[type=file]');
            var imageInput = null;
            var videoInput = null;
            for (var i = 0; i < inputs.length; i++) {
                if (inputs[i].accept.indexOf('image') >= 0) imageInput = inputs[i];
                if (inputs[i].accept.indexOf('video') >= 0) videoInput = inputs[i];
            }
            
            if (!imageInput) return 'NO_IMAGE_INPUT';
            
            // 从 base64 创建 File
            var b64 = window._cover4x3_b64;
            var byteChars = atob(b64);
            var byteArray = new Uint8Array(byteChars.length);
            for (var i = 0; i < byteChars.length; i++) {
                byteArray[i] = byteChars.charCodeAt(i);
            }
            var blob = new Blob([byteArray], {type: 'image/jpeg'});
            var file = new File([blob], '5.1-cover-4x3.jpg', {type: 'image/jpeg'});
            
            // 用 DataTransfer 设置 files（现代方式）
            var dt = new DataTransfer();
            dt.items.add(file);
            imageInput.files = dt.files;
            
            // 触发 change 事件
            imageInput.dispatchEvent(new Event('change', {bubbles: true}));
            imageInput.dispatchEvent(new Event('input', {bubbles: true}));
            
            return 'SET_4x3_OK_files:' + imageInput.files.length;
        })()""")
        print(f'  Result: {r}')
        await asyncio.sleep(3)

        # 检查封面对话框状态
        dialog = await js("""(function(){
            var modals = document.querySelectorAll('[role=dialog], [class*=modal], [class*=Modal], [class*=dialog], [class*=Dialog], [class*=overlay]');
            var t = [];
            for (var m of modals) {
                if (m.offsetWidth > 0 && m.offsetHeight > 0) {
                    t.push({cls: (m.className||'').toString().substring(0,50), w: m.offsetWidth, h: m.offsetHeight, text: m.textContent.substring(0,60)});
                }
            }
            return JSON.stringify(t);
        })()""")
        print(f'  Dialogs: {dialog}')

        # 检查是否有完成按钮
        btns = await js("""(function(){
            var all = document.querySelectorAll('button, [role=button]');
            var t = [];
            for (var b of all) {
                var text = b.textContent.trim();
                var rect = b.getBoundingClientRect();
                if (rect.width > 0 && rect.height > 0 && (text === '完成' || text === '确认' || text === '确定' || text.includes('裁剪'))) {
                    t.push(text + ' (' + Math.round(rect.x) + ',' + Math.round(rect.y) + ')');
                }
            }
            return JSON.stringify(t);
        })()""")
        print(f'  Buttons: {btns}')

        # 如果有裁剪对话框，可能需要点击确认/完成
        # 先看看是否有预览
        preview = await js("""(function(){
            var imgs = document.querySelectorAll('img');
            var t = [];
            for (var img of imgs) {
                var rect = img.getBoundingClientRect();
                if (rect.width > 30 && rect.height > 30) {
                    t.push({src: img.src.substring(0,60), w: Math.round(rect.width), h: Math.round(rect.height)});
                }
            }
            return JSON.stringify(t.slice(0, 8));
        })()""")
        print(f'  Images: {preview}')

        # Step 2: 尝试关闭当前对话框（如果有的话）
        if '裁剪' in str(btns):
            print('\n  Crop dialog found, clicking confirm...')
            r = await js_no_ret("""(function(){
                var all = document.querySelectorAll('button');
                for (var b of all) {
                    var text = b.textContent.trim();
                    if (text.includes('裁剪') || text === '完成' || text === '确认') {
                        var rect = b.getBoundingClientRect();
                        if (rect.width > 0) {
                            b.click();
                            return 'clicked:' + text;
                        }
                    }
                }
                return 'NOT_FOUND';
            })()""")
            print(f'  Result: {r}')
            await asyncio.sleep(2)

        # 如果有"完成"按钮，点击
        if '完成' in str(btns):
            print('  Clicking complete...')
            r = await js_no_ret("""(function(){
                var all = document.querySelectorAll('button');
                for (var b of all) {
                    if (b.textContent.trim() === '完成') {
                        var rect = b.getBoundingClientRect();
                        if (rect.width > 0) {
                            b.click();
                            return 'OK';
                        }
                    }
                }
                return 'NOT_FOUND';
            })()""")
            print(f'  Result: {r}')
            await asyncio.sleep(2)

        # Step 3: 上传 3:4 封面
        print('\n[Step 2] Uploading 3:4 cover via JS...')
        r = await js(f"window._cover3x4_b64 = '{b64_3x4}'; 'injected'")
        
        # 先点击第二个"选择封面"
        r = await js_no_ret("""(function(){
            var els = document.querySelectorAll('.title-wA45Xd');
            if (els.length > 1) {
                els[1].click();
                return 'clicked_vertical';
            }
            return 'NOT_FOUND';
        })()""")
        print(f'  Click vertical cover: {r}')
        await asyncio.sleep(2)

        r = await js_no_ret("""(function(){
            var inputs = document.querySelectorAll('input[type=file]');
            var imageInput = null;
            for (var i = 0; i < inputs.length; i++) {
                if (inputs[i].accept.indexOf('image') >= 0) imageInput = inputs[i];
            }
            if (!imageInput) return 'NO_IMAGE_INPUT';
            
            var b64 = window._cover3x4_b64;
            var byteChars = atob(b64);
            var byteArray = new Uint8Array(byteChars.length);
            for (var i = 0; i < byteChars.length; i++) {
                byteArray[i] = byteChars.charCodeAt(i);
            }
            var blob = new Blob([byteArray], {type: 'image/jpeg'});
            var file = new File([blob], '5.1-cover-3x4.jpg', {type: 'image/jpeg'});
            
            var dt = new DataTransfer();
            dt.items.add(file);
            imageInput.files = dt.files;
            
            imageInput.dispatchEvent(new Event('change', {bubbles: true}));
            imageInput.dispatchEvent(new Event('input', {bubbles: true}));
            
            return 'SET_3x4_OK_files:' + imageInput.files.length;
        })()""")
        print(f'  Result: {r}')
        await asyncio.sleep(3)

        # 检查按钮状态
        btns2 = await js("""(function(){
            var all = document.querySelectorAll('button, [role=button]');
            var t = [];
            for (var b of all) {
                var text = b.textContent.trim();
                var rect = b.getBoundingClientRect();
                if (rect.width > 0 && rect.height > 0 && (text === '完成' || text === '确认' || text.includes('裁剪'))) {
                    t.push(text);
                }
            }
            return JSON.stringify(t);
        })()""")
        print(f'  Buttons: {btns2}')

        if '完成' in str(btns2) or '裁剪' in str(btns2):
            print('  Clicking confirm...')
            r = await js_no_ret("""(function(){
                var all = document.querySelectorAll('button');
                for (var b of all) {
                    var text = b.textContent.trim();
                    var rect = b.getBoundingClientRect();
                    if (rect.width > 0 && (text === '完成' || text.includes('裁剪') || text === '确认')) {
                        b.click();
                        return 'clicked:' + text;
                    }
                }
                return 'NOT_FOUND';
            })()""")
            print(f'  Result: {r}')
            await asyncio.sleep(2)

        # 最终检查封面状态
        final = await js("""(function(){
            // 检查封面预览
            var coverInfo = [];
            var tipEls = document.querySelectorAll('.cover-tip-YkBvmu, [class*=cover-tip]');
            for (var el of tipEls) {
                coverInfo.push(el.textContent.trim());
            }
            // 检查是否有"缺失"提示
            var allText = document.body.innerText;
            var hasMissing = allText.includes('封面缺失') || allText.includes('双封面缺失');
            return JSON.stringify({tips: coverInfo, missing: hasMissing});
        })()""")
        print(f'\n  Final cover status: {final}')

        print('\n[Done] Cover upload process completed!')


asyncio.run(main())
