# -*- coding: utf-8 -*-
"""抖音 5.1 - 填写标题简介、设置封面、添加AI声明"""
import asyncio, websockets, json, sys, os
sys.stdout.reconfigure(encoding='utf-8')

CDP_PORT = 9222
TAB_ID = '7B9C42697B3EBE4D94FA2F9B29D5EF35'

TITLE = 'AI+小组合作学习：5.1 让合作不再"凑合"'
DESC = '在未进入人工智能时代的日常教学中，小组合作学习一直就是我们推崇的教学方式，但长期以来，它也面临着"分组随意"、"过程失控"和"评价模糊"等痛点。如今，将AI技术融入小组合作学习，正是解决这些问题的一剂良方。结合我近年来的教学探索与思考，我想谈谈这种新模式是如何让课堂发生质变的。'
COVER_4x3 = r'D:\个人\资源\个人文章\AI育见\5.1\5.1-封面_4x3.jpg'
COVER_3x4 = r'D:\个人\资源\个人文章\AI育见\5.1\5.1-封面_3x4.jpg'


async def main():
    ws_url = f'ws://127.0.0.1:{CDP_PORT}/devtools/page/{TAB_ID}'
    print(f'Connecting to {TAB_ID}...')

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

        # 确认当前页面
        url = await js('window.location.href')
        print(f'Current URL: {url}')
        if 'content/post' not in str(url):
            print('[ERROR] Not on post page!')
            return

        # ===== Step 1: 填写标题 =====
        print('\n[Step 1] 填写标题...')
        # 查找标题输入框
        title_info = await js("""(function(){
            var inputs = document.querySelectorAll('input[type=text], textarea, [contenteditable=true]');
            var t = [];
            for (var el of inputs) {
                var rect = el.getBoundingClientRect();
                var ph = el.getAttribute('placeholder') || '';
                var val = el.value || el.textContent || '';
                t.push({tag: el.tagName, ph: ph.substring(0,30), val: val.substring(0,30), w: Math.round(rect.width), h: Math.round(rect.height), cls: (el.className||'').toString().substring(0,40)});
            }
            return JSON.stringify(t.slice(0, 15));
        })()""")
        print(f'  Inputs found: {title_info}')

        # 尝试用 placeholder 找标题框
        r = await js_no_ret("""(function(){
            var inputs = document.querySelectorAll('input[placeholder]');
            for (var el of inputs) {
                var ph = el.getAttribute('placeholder');
                if (ph && (ph.includes('标题') || ph.includes('title') || ph.includes('填写'))) {
                    // 使用 React 的方式设置值
                    var nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                    nativeInputValueSetter.call(el, arguments[0]);
                    el.dispatchEvent(new Event('input', { bubbles: true }));
                    el.dispatchEvent(new Event('change', { bubbles: true }));
                    return 'set_title:' + el.value;
                }
            }
            return 'NOT_FOUND';
        })('""" + TITLE.replace("'", "\\'") + """')""")
        print(f'  Title set result: {r}')

        await asyncio.sleep(2)

        # 检查标题是否成功
        title_val = await js("""(function(){
            var inputs = document.querySelectorAll('input[placeholder]');
            for (var el of inputs) {
                var ph = el.getAttribute('placeholder');
                if (ph && (ph.includes('标题') || ph.includes('title'))) {
                    return el.value;
                }
            }
            return '';
        })()""")
        print(f'  Title value: {title_val}')

        # ===== Step 2: 填写简介 =====
        print('\n[Step 2] 填写简介...')
        # 查找简介 textarea
        desc_info = await js("""(function(){
            var els = document.querySelectorAll('textarea, div[contenteditable=true]');
            var t = [];
            for (var el of els) {
                var rect = el.getBoundingClientRect();
                var ph = el.getAttribute('placeholder') || '';
                t.push({tag: el.tagName, editable: el.contentEditable, ph: ph.substring(0,40), w: Math.round(rect.width), h: Math.round(rect.height), cls: (el.className||'').toString().substring(0,40)});
            }
            return JSON.stringify(t.slice(0, 10));
        })()""")
        print(f'  Textareas: {desc_info}')

        r = await js_no_ret("""(function(){
            var els = document.querySelectorAll('textarea, div[contenteditable=true]');
            for (var el of els) {
                var ph = el.getAttribute('placeholder') || '';
                if (ph.includes('简介') || ph.includes('描述') || ph.includes('介绍') || ph.includes('content')) {
                    if (el.tagName === 'TEXTAREA') {
                        var nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
                        nativeSetter.call(el, arguments[0]);
                    } else {
                        el.textContent = arguments[0];
                    }
                    el.dispatchEvent(new Event('input', { bubbles: true }));
                    el.dispatchEvent(new Event('change', { bubbles: true }));
                    return 'set_desc:OK';
                }
            }
            return 'NOT_FOUND';
        })('""" + DESC.replace("'", "\\'").replace("\n", "\\n") + """')""")
        print(f'  Desc set result: {r}')

        await asyncio.sleep(2)

        # ===== Step 3: 添加 AI 声明 =====
        print('\n[Step 3] 查找 AI 声明...')
        ai_info = await js("""(function(){
            var els = document.querySelectorAll('label, [role=checkbox], input[type=checkbox], div[class*=check], span[class*=check]');
            var t = [];
            for (var el of els) {
                var text = el.textContent.trim();
                if (text.includes('AI') || text.includes('智能') || text.includes('声明') || text.includes('生成')) {
                    t.push({tag: el.tagName, text: text.substring(0,40), cls: (el.className||'').toString().substring(0,40), checked: el.checked || false});
                }
                if (t.length > 10) break;
            }
            return JSON.stringify(t);
        })()""")
        print(f'  AI elements: {ai_info}')

        # 尝试勾选 AI 声明
        r = await js_no_ret("""(function(){
            var els = document.querySelectorAll('label, div[role=checkbox], span');
            for (var el of els) {
                var text = el.textContent.trim();
                if (text.includes('AI') && (text.includes('生成') || text.includes('声明') || text.includes('智能'))) {
                    el.click();
                    return 'clicked:' + text.substring(0,30);
                }
            }
            // 也尝试 checkbox
            var cbs = document.querySelectorAll('input[type=checkbox]');
            for (var cb of cbs) {
                var parent = cb.closest('label') || cb.parentElement;
                if (parent && parent.textContent.includes('AI')) {
                    cb.click();
                    return 'checkbox_clicked';
                }
            }
            return 'NOT_FOUND';
        })()""")
        print(f'  AI check result: {r}')

        await asyncio.sleep(2)

        # ===== Step 4: 封面设置 =====
        print('\n[Step 4] 封面设置（查找封面对话框入口）...')
        cover_info = await js("""(function(){
            var els = document.querySelectorAll('div, button, span, a');
            var t = [];
            for (var el of els) {
                var own = '';
                for (var c = el.firstChild; c; c = c.nextSibling) {
                    if (c.nodeType === 3) own += c.textContent;
                }
                own = own.trim();
                if (own.includes('封面') || own.includes('cover') || own.includes('选择封面') || own.includes('设置封面')) {
                    var rect = el.getBoundingClientRect();
                    if (rect.width > 0 && rect.height > 0) {
                        t.push({tag: el.tagName, text: own.substring(0,30), w: Math.round(rect.width), h: Math.round(rect.height), cls: (el.className||'').toString().substring(0,40)});
                    }
                }
                if (t.length > 10) break;
            }
            return JSON.stringify(t);
        })()""")
        print(f'  Cover elements: {cover_info}')

        # 尝试点击「选择封面」或封面区域
        r = await js_no_ret("""(function(){
            var els = document.querySelectorAll('div, button, span, a');
            for (var el of els) {
                var own = '';
                for (var c = el.firstChild; c; c = c.nextSibling) {
                    if (c.nodeType === 3) own += c.textContent;
                }
                own = own.trim();
                if ((own.includes('选择封面') || own.includes('设置封面') || own.includes('上传封面')) && own.length < 20) {
                    el.click();
                    return 'clicked:' + own;
                }
            }
            // 尝试含 cover 关键词的 class
            var coverEls = document.querySelectorAll('[class*=cover], [class*=Cover]');
            for (var el of coverEls) {
                var text = el.textContent.trim().substring(0,20);
                if (text.length > 0 && text.length < 20) {
                    var rect = el.getBoundingClientRect();
                    if (rect.width > 10 && rect.height > 10) {
                        el.click();
                        return 'clicked_cover:' + text;
                    }
                }
            }
            return 'NOT_FOUND';
        })()""")
        print(f'  Cover click result: {r}')

        await asyncio.sleep(3)

        # 检查是否弹出了封面对话框
        dialog_info = await js("""(function(){
            // 检查是否有 modal/dialog
            var modals = document.querySelectorAll('[role=dialog], [class*=modal], [class*=Modal], [class*=dialog], [class*=Dialog]');
            var t = [];
            for (var m of modals) {
                if (m.offsetWidth > 0 && m.offsetHeight > 0) {
                    t.push({cls: (m.className||'').toString().substring(0,50), w: m.offsetWidth, h: m.offsetHeight});
                }
            }
            // 检查 file inputs（封面对话框可能有）
            var ins = document.querySelectorAll('input[type=file]');
            for (var i = 0; i < ins.length; i++) {
                t.push({type:'file_input', i:i, accept: ins[i].accept.substring(0,30)});
            }
            return JSON.stringify(t);
        })()""")
        print(f'  Dialogs/Inputs: {dialog_info}')

        # 如果有封面对话框，尝试上传封面
        file_count = str(dialog_info).count('file_input')
        if file_count > 0:
            print(f'\n[Step 5] 上传封面...')
            # 重新获取 DOM 树找 file inputs
            r = await cdp('DOM.getDocument', {'depth': 0})
            root_id = r.get('result', {}).get('root', {}).get('nodeId')
            r = await cdp('DOM.querySelectorAll', {'selector': 'input[type=file]', 'nodeId': root_id})
            nids = r.get('result', {}).get('nodeIds', [])
            print(f'  File input nodeIds: {nids}')

            if len(nids) >= 2:
                # 第二个 input 通常是封面
                print(f'  Uploading 4:3 cover to nodeId {nids[-1]}...')
                r = await cdp('DOM.setFileInputFiles', {'files': [COVER_4x3], 'nodeId': nids[-1]})
                print(f'  Result: {r.get("result")}')
                await asyncio.sleep(3)

        print('\n[Done] All steps completed!')
        print('  Title: ' + TITLE[:30] + '...')
        print('  Desc: ' + DESC[:30] + '...')
        print('  Please review and publish manually.')


asyncio.run(main())
