# -*- coding: utf-8 -*-
"""
完整封面上传流程（从浏览器启动开始）
1. 导航到创作者首页
2. 点击「高清发布」
3. 上传视频
4. 等待视频处理
5. 进入封面设置对话框
6. 上传4:3横封面
7. 点完成
8. 上传3:4竖封面
9. 点完成
"""
import sys, json, asyncio, websockets, time
sys.stdout.reconfigure(encoding='utf-8')

TAB_ID = '5D96FE9DE365C70458A343D735A4E55A'
CDP_PORT = 9222
VIDEO_PATH = r"D:\个人\资源\个人文章\AI育见\4.1\4.1.mp4"
COVER_4x3 = r"D:\个人\资源\个人文章\AI育见\4.1\4.1-封面_4x3.jpg"
COVER_3x4 = r"D:\个人\资源\个人文章\AI育见\4.1\4.1-封面_3x4.jpg"


async def cdp_send(ws, mid, method, params=None):
    mid[0] += 1
    await ws.send(json.dumps({'id': mid[0], 'method': method, 'params': params or {}}))
    for _ in range(20):
        r = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
        if r.get('id') == mid[0]:
            return r
    return {}


async def js(ws, mid, expr):
    r = await cdp_send(ws, mid, 'Runtime.evaluate', {'expression': expr, 'returnByValue': True})
    return r.get('result', {}).get('result', {}).get('value', '')


async def main():
    ws_url = f'ws://127.0.0.1:{CDP_PORT}/devtools/page/{TAB_ID}'
    async with websockets.connect(ws_url, ping_interval=None, open_timeout=5) as ws:
        mid = [0]

        # === Step 1: 截图确认当前状态 ===
        r = await cdp_send(ws, mid, 'Page.captureScreenshot', {'format': 'png', 'quality': 60})
        img = r.get('result', {}).get('data', '')
        if img:
            with open(r'C:\Users\chenw\.qclaw\media\browser\step0_current.png', 'wb') as f:
                f.write(img.encode('latin1'))

        # === Step 2: 导航到首页 ===
        print('Step 2: 导航到首页...')
        r = await cdp_send(ws, mid, 'Page.navigate', {'url': 'https://creator.douyin.com/creator-micro/home'})
        await asyncio.sleep(3)
        url = await js(ws, mid, 'window.location.href')
        print(f'  URL: {url}')

        # === Step 3: 点击「高清发布」===
        print('Step 3: 点击「高清发布」...')
        r = await js(ws, mid, "(function(){var els=document.querySelectorAll('button');for(var el of els){if(el.textContent.trim()==='高清发布'){el.click();return'OK_clicked';}}return'NOT_FOUND';})()")
        print(f'  结果: {r}')
        await asyncio.sleep(3)
        url = await js(ws, mid, 'window.location.href')
        print(f'  URL: {url}')

        # === Step 4: 截图确认上传页 ===
        r = await cdp_send(ws, mid, 'Page.captureScreenshot', {'format': 'png', 'quality': 60})
        img = r.get('result', {}).get('data', '')
        if img:
            with open(r'C:\Users\chenw\.qclaw\media\browser\step4_upload_page.png', 'wb') as f:
                f.write(img.encode('latin1'))

        # === Step 5: 找 file input 并上传视频 ===
        print('Step 5: 上传视频...')
        r = await js(ws, mid, "(function(){var ins=document.querySelectorAll('input[type=file]');var t=[];for(var i=0;i<ins.length;i++){var inp=ins[i];t.push({i:i,accept:inp.accept.substring(0,40),files:inp.files?inp.files.length:0,w:inp.offsetWidth,h:inp.offsetHeight});}return JSON.stringify(t)})()")
        print(f'  file inputs: {r}')

        # 找视频 input 并上传
        r = await js(ws, mid, f"(function(){{var ins=document.querySelectorAll('input[type=file]');for(var i=0;i<ins.length;i++){{var inp=ins[i];if(inp.accept&&inp.accept.includes('video')&&(inp.offsetWidth>0||inp.offsetParent!==null)){{inp.click();return'OK_clicked_video_input_'+i;}}}}for(var i=0;i<ins.length;i++){{var inp=ins[i];if(inp.accept&&inp.accept.includes('video')){{inp.click();return'OK_clicked_video_input_'+i;}}}}return'NOT_FOUND';}})()")
        print(f'  点击结果: {r}')
        await asyncio.sleep(1)

        # 重新获取 nodeId
        r = await cdp_send(ws, mid, 'DOM.getDocument', {'depth': 0})
        root = r['result']['root']
        body_id = root['nodeId']
        for child in root.get('children', []):
            if child.get('localName') == 'body':
                body_id = child['nodeId']
                break
        r = await cdp_send(ws, mid, 'DOM.querySelectorAll', {'selector': 'input[type=file]', 'nodeId': body_id})
        node_ids = r.get('result', {}).get('nodeIds', [])
        print(f'  nodeIds: {node_ids}')

        # 上传视频
        if node_ids and node_ids[0]:
            nid = node_ids[0]
            # 先获取 nodeId 对应的 input
            r = await cdp_send(ws, mid, 'DOM.describeNode', {'nodeId': nid})
            attrs = r.get('result', {}).get('node', {}).get('attributes', [])
            print(f'  input 属性: {attrs}')
            r = await cdp_send(ws, mid, 'DOM.setFileInputFiles', {'files': [VIDEO_PATH], 'nodeId': nid})
            print(f'  setFileInputFiles: {r.get("result")}')
            await asyncio.sleep(1)

        # === Step 6: 等待跳转到 post 页 ===
        print('Step 6: 等待跳转到发布页...')
        for i in range(15):
            await asyncio.sleep(2)
            url = await js(ws, mid, 'window.location.href')
            if 'content/post/video' in url:
                print(f'  ✅ 跳转到发布页: {url}')
                break
            print(f'  [{i+1}/15] 当前URL: {url}')
        else:
            print('  ⚠️ 未跳转，假设已在发布页')

        await asyncio.sleep(3)

        # === Step 7: 截图确认发布页 ===
        r = await cdp_send(ws, mid, 'Page.captureScreenshot', {'format': 'png', 'quality': 60})
        img = r.get('result', {}).get('data', '')
        if img:
            with open(r'C:\Users\chenw\.qclaw\media\browser\step7_post_page.png', 'wb') as f:
                f.write(img.encode('latin1'))

        # === Step 8: 检查发布页状态 ===
        print('Step 8: 检查发布页...')
        r = await js(ws, mid, "(function(){var t=[];var els=document.querySelectorAll('*');for(var i=0;i<els.length;i++){var el=els[i];var txt=el.textContent.trim();if((txt.includes('4:3')||txt.includes('3:4')||txt.includes('封面')||txt.includes('上传'))&&txt.length<100){var r=el.getBoundingClientRect();if(r.width>0&&r.height>0)t.push({tag:el.tagName,text:txt.substring(0,40),y:Math.round(r.y)});}}return JSON.stringify(t.slice(0,20)))()")
        print(f'  封面相关文本: {r}')

        # === Step 9: 找「选择封面」按钮 ===
        print('Step 9: 找「选择封面」按钮...')
        r = await js(ws, mid, "(function(){var t=[];var els=document.querySelectorAll('button, [role=button], span, div');for(var el of els){var txt=el.textContent.trim();if(txt.includes('选择封面')||txt.includes('封面设置')||txt.includes('上传封面')||txt.includes('4:3')||txt.includes('3:4')){var r=el.getBoundingClientRect();t.push({tag:el.tagName,text:txt.substring(0,30),x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height)});}}return JSON.stringify(t.slice(0,10)))()")
        print(f'  按钮: {r}')

        # 保存状态
        result = {'done': True}
        with open(r'C:\Users\chenw\.qclaw\full_flow.json', 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False)

asyncio.run(main())
