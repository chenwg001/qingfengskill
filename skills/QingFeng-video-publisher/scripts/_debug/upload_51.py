# -*- coding: utf-8 -*-
"""抖音 5.1 视频上传 - 完整流程"""
import asyncio, websockets, json, sys, time, os
sys.stdout.reconfigure(encoding='utf-8')
CDP_PORT = 9222
VIDEO_PATH = r'D:\个人\资源\个人文章\AI育见\5.1\5.1.mp4'
VIDEO_SIZE_MB = round(os.path.getsize(VIDEO_PATH) / 1024 / 1024, 1)

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
    print(f'Tab: {tab["id"]}')
    
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
        
        # 导航到上传页
        url = await js('window.location.href')
        if 'content/upload' not in str(url):
            print('[1] Navigate to upload page...')
            await cdp('Page.navigate', {'url': 'https://creator.douyin.com/creator-micro/content/upload'})
            await asyncio.sleep(5)
        else:
            print('[1] Already on upload page')
        
        url = await js('window.location.href')
        print(f'  URL: {url}')
        
        # 找 file input
        print(f'[2] Finding file input (video: {VIDEO_SIZE_MB}MB)...')
        r = await cdp('DOM.getDocument', {'depth': 0})
        root_id = r.get('result', {}).get('root', {}).get('nodeId')
        r = await cdp('DOM.querySelectorAll', {'selector': 'input[type=file]', 'nodeId': root_id})
        nids = r.get('result', {}).get('nodeIds', [])
        
        if not nids:
            print('  No file input found! Try again.')
            return
        
        nid = nids[0]
        print(f'  nodeId: {nid}')
        
        # 上传视频
        print(f'[3] Uploading video ({VIDEO_SIZE_MB}MB)...')
        r = await cdp('DOM.setFileInputFiles', {'files': [VIDEO_PATH], 'nodeId': nid})
        result = r.get('result', {})
        print(f'  setFileInputFiles: {result}')
        
        # 等待跳转到发布页
        print('[4] Waiting for redirect to post page...')
        for i in range(40):
            await asyncio.sleep(3)
            try:
                url = await js('window.location.href')
            except:
                continue
            if 'content/post' in str(url):
                print(f'  [{i+1}] REDIRECTED! {str(url)[:60]}')
                break
            if i % 5 == 0:
                print(f'  [{i+1}] waiting... {str(url)[:50]}')
        else:
            url = await js('window.location.href')
            print(f'  Timeout. URL: {url}')
        
        # 等待视频处理完成
        print(f'[5] Waiting for video processing (90s)...')
        for i in range(30):
            await asyncio.sleep(3)
            # 检查是否有进度条或处理完成标志
            blobs = await js("""(function(){
                var count = 0;
                document.querySelectorAll('img').forEach(function(el){
                    if ((el.src.indexOf('blob') >= 0 || el.src.indexOf('douyinpic') >= 0) && el.offsetWidth > 50)
                        count++;
                });
                return count;
            })()""")
            if int(blobs or 0) > 0:
                print(f'  [{i+1}] Video processed! blob images: {blobs}')
                break
            if i % 5 == 0:
                print(f'  [{i+1}] processing...')
        
        # 最终状态
        url = await js('window.location.href')
        print(f'\n[Done] Final URL: {url}')
        print(f'  Video: 5.1.mp4 ({VIDEO_SIZE_MB}MB)')
        print(f'  Cover 4:3: 5.1-封面_4x3.jpg (2880x2160)')
        print(f'  Cover 3:4: 5.1-封面_3x4.jpg (2880x3840)')
        print(f'\n  Video uploaded! Check the page and publish when ready.')

asyncio.run(main())
