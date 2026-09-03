# -*- coding: utf-8 -*-
"""抖音 5.1 - Step 2: 填写简介 + AI声明 + 上传封面"""
import asyncio, websockets, json, sys, os
sys.stdout.reconfigure(encoding='utf-8')

CDP_PORT = 9222
TAB_ID = '7B9C42697B3EBE4D94FA2F9B29D5EF35'

DESC = '在未进入人工智能时代的日常教学中，小组合作学习一直就是我们推崇的教学方式，但长期以来，它也面临着"分组随意"、"过程失控"和"评价模糊"等痛点。如今，将AI技术融入小组合作学习，正是解决这些问题的一剂良方。结合我近年来的教学探索与思考，我想谈谈这种新模式是如何让课堂发生质变的。'
COVER_4x3 = r'D:\个人\资源\个人文章\AI育见\5.1\5.1-封面_4x3.jpg'
COVER_3x4 = r'D:\个人\资源\个人文章\AI育见\5.1\5.1-封面_3x4.jpg'


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

        # ===== Step 1: 填写简介（contenteditable div）=====
        print('[Step 1] Filling description...')
        r = await js_no_ret("""(function(){
            // 找 contenteditable 的 div（简介编辑器）
            var el = document.querySelector('div[contenteditable=true].zone-container') ||
                     document.querySelector('div[contenteditable=true].editor-kit-container') ||
                     document.querySelector('.zone-container[contenteditable]');
            if (!el) {
                // 尝试更宽泛的搜索
                var divs = document.querySelectorAll('div[contenteditable=true]');
                for (var d of divs) {
                    if (d.offsetWidth > 200 && d.offsetHeight > 30 && d.className.includes('zone')) {
                        el = d;
                        break;
                    }
                }
            }
            if (!el) return 'el_NOT_FOUND';
            
            // 聚焦并输入
            el.focus();
            el.textContent = arguments[0];
            el.dispatchEvent(new Event('input', { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
            return 'set_desc_OK_' + el.textContent.substring(0, 20);
        })('""" + DESC.replace("'", "\\'").replace("\n", "\\n") + """')""")
        print(f'  Result: {r}')
        await asyncio.sleep(2)

        # 验证简介
        desc_val = await js("""(function(){
            var el = document.querySelector('div[contenteditable=true].zone-container') ||
                     document.querySelector('div[contenteditable=true].editor-kit-container');
            if (!el) return '';
            return el.textContent.substring(0, 50);
        })()""")
        print(f'  Desc value: {desc_val}')

        # ===== Step 2: 查找 AI 声明 =====
        print('\n[Step 2] AI declaration...')
        # 滚动查找
        r = await js_no_ret("""(function(){
            // 先滚动页面查找
            var allText = document.body.innerText;
            var aiIndex = allText.indexOf('AI');
            if (aiIndex >= 0) {
                // 找附近的 checkbox
                var allLabels = document.querySelectorAll('label, [role=checkbox]');
                for (var lb of allLabels) {
                    var t = lb.textContent.trim();
                    if ((t.includes('AI') || t.includes('生成内容')) && t.length < 50) {
                        lb.click();
                        return 'clicked:' + t.substring(0,30);
                    }
                }
            }
            
            // 尝试找所有 checkbox
            var cbs = document.querySelectorAll('input[type=checkbox], [class*=checkbox], [class*=Checkbox]');
            var info = [];
            for (var cb of cbs) {
                var rect = cb.getBoundingClientRect();
                var parent = cb.closest('label') || cb.parentElement;
                var ptext = parent ? parent.textContent.trim().substring(0, 40) : '';
                info.push({checked: cb.checked, text: ptext, visible: rect.width > 0});
            }
            return JSON.stringify(info);
        })()""")
        print(f'  Result: {r}')
        await asyncio.sleep(1)

        # ===== Step 3: 封面上传 =====
        print('\n[Step 3] Cover upload...')

        # 先检查当前状态 - 是否有封面对话框已打开
        # 找所有 file input 并检查 accept
        r = await js("""(function(){
            var ins = document.querySelectorAll('input[type=file]');
            var t = [];
            for (var i = 0; i < ins.length; i++) {
                var rect = ins[i].getBoundingClientRect();
                t.push({i: i, accept: ins[i].accept.substring(0,40), w: Math.round(rect.width), h: Math.round(rect.height), visible: rect.width > 0});
            }
            return JSON.stringify(t);
        })()""")
        print(f'  File inputs: {r}')

        # 找到封面区域的 file input（accept=image 的）
        # 使用 DOM.getFileInputFiles 获取 nodeId
        r = await cdp('DOM.getDocument', {'depth': -1, 'pierce': True})
        root = r.get('result', {}).get('root', {})
        
        # 用 JS 在封面对话框里找 input 并直接用 FileReader 上传
        print('  Using JS to find and upload cover...')
        
        # 读取封面文件为 base64 并上传
        with open(COVER_4x3, 'rb') as f:
            cover_4x3_b64 = os.path.basename(COVER_4x3) + '|' + __import__('base64').b64encode(f.read()).decode()
        
        # 先点击「选择封面」- 横封面
        r = await js_no_ret("""(function(){
            var els = document.querySelectorAll('.title-wA45Xd, [class*=title-wA45]');
            var text = [];
            for (var el of els) {
                text.push(el.textContent.trim());
            }
            return JSON.stringify(text);
        })()""")
        print(f'  Cover buttons: {r}')
        
        # 用 JS 点击第一个"选择封面"（横封面）
        r = await js_no_ret("""(function(){
            var els = document.querySelectorAll('.title-wA45Xd');
            if (els.length > 0) {
                els[0].click();
                return 'clicked_horizontal_cover';
            }
            return 'NOT_FOUND';
        })()""")
        print(f'  Click cover button: {r}')
        await asyncio.sleep(2)
        
        # 检查 file inputs
        r = await js("""(function(){
            var ins = document.querySelectorAll('input[type=file]');
            var t = [];
            for (var i = 0; i < ins.length; i++) {
                t.push({i: i, accept: ins[i].accept.substring(0,40)});
            }
            return JSON.stringify(t);
        })()""")
        print(f'  File inputs after click: {r}')
        
        # 尝试用 CDP DOM 搜索（pierce shadow DOM）
        r = await cdp('DOM.querySelectorAll', {'selector': 'input', 'nodeId': root['nodeId']})
        all_nids = r.get('result', {}).get('nodeIds', [])
        print(f'  All input nodeIds (pierce): {len(all_nids)}')
        
        # 找 file type 的
        file_nids = []
        for nid in all_nids:
            nr = await cdp('DOM.getAttributes', {'nodeId': nid})
            attrs = nr.get('result', {}).get('attributes', [])
            attr_dict = {}
            for i in range(0, len(attrs), 2):
                attr_dict[attrs[i]] = attrs[i+1]
            if attr_dict.get('type') == 'file':
                file_nids.append({'nodeId': nid, 'accept': attr_dict.get('accept', '')[:30]})
        print(f'  File input details: {file_nids}')
        
        # 找 accept 含 image 的（封面 input）
        cover_nid = None
        for fi in file_nids:
            if 'image' in fi['accept']:
                cover_nid = fi['nodeId']
                break
        
        if cover_nid:
            print(f'  Uploading 4:3 cover to nodeId {cover_nid}...')
            r = await cdp('DOM.setFileInputFiles', {'files': [COVER_4x3], 'nodeId': cover_nid})
            print(f'  Result: {r.get("result")}')
            await asyncio.sleep(3)
            
            # 然后上传 3:4 封面
            # 先关闭当前对话框（如果有完成按钮）
            r = await js_no_ret("""(function(){
                var btns = document.querySelectorAll('button');
                for (var b of btns) {
                    var t = b.textContent.trim();
                    if (t === '完成' || t === '确认' || t === '确定') {
                        b.click();
                        return 'closed_dialog';
                    }
                }
                return 'no_close_btn';
            })()""")
            print(f'  Close dialog: {r}')
            await asyncio.sleep(2)
            
            # 点击第二个"选择封面"（竖封面）
            r = await js_no_ret("""(function(){
                var els = document.querySelectorAll('.title-wA45Xd');
                if (els.length > 1) {
                    els[1].click();
                    return 'clicked_vertical_cover';
                }
                return 'NOT_FOUND';
            })()""")
            print(f'  Click vertical cover: {r}')
            await asyncio.sleep(2)
            
            # 再次查找封面 file input
            r = await cdp('DOM.querySelectorAll', {'selector': 'input', 'nodeId': root['nodeId']})
            all_nids2 = r.get('result', {}).get('nodeIds', [])
            file_nids2 = []
            for nid in all_nids2:
                nr = await cdp('DOM.getAttributes', {'nodeId': nid})
                attrs = nr.get('result', {}).get('attributes', [])
                attr_dict = {}
                for i in range(0, len(attrs), 2):
                    attr_dict[attrs[i]] = attrs[i+1]
                if attr_dict.get('type') == 'file' and 'image' in attr_dict.get('accept', ''):
                    file_nids2.append(nid)
            
            if file_nids2:
                vcover_nid = file_nids2[-1]  # 最后一个
                print(f'  Uploading 3:4 cover to nodeId {vcover_nid}...')
                r = await cdp('DOM.setFileInputFiles', {'files': [COVER_3x4], 'nodeId': vcover_nid})
                print(f'  Result: {r.get("result")}')
                await asyncio.sleep(3)
            
            # 关闭对话框
            r = await js_no_ret("""(function(){
                var btns = document.querySelectorAll('button');
                for (var b of btns) {
                    var t = b.textContent.trim();
                    if (t === '完成' || t === '确认' || t === '确定') {
                        b.click();
                        return 'closed';
                    }
                }
                return 'no_close_btn';
            })()""")
            print(f'  Close: {r}')
        else:
            print('  No cover file input found! Trying direct approach...')
        
        # ===== Final status =====
        print('\n[Done] All steps completed!')
        print('Please review the page and publish manually.')


asyncio.run(main())
