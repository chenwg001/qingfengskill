# -*- coding: utf-8 -*-
"""
视频上传脚本
方法：DOM.setFileInputFiles 设置文件 → 页面自动跳转 → 等待视频处理完成
用法: python upload_video.py <tab_id> <视频文件路径>
"""
import sys, json, asyncio, websockets, time
sys.stdout.reconfigure(encoding='utf-8')

CDP_PORT = 9222  # 可通过命令行第3个参数覆盖


async def cdp(ws, mid, method, params=None):
    mid[0] += 1
    await ws.send(json.dumps({'id': mid[0], 'method': method, 'params': params or {}}))
    for _ in range(30):
        r = json.loads(await asyncio.wait_for(ws.recv(), timeout=15))
        if r.get('id') == mid[0]:
            return r
    return {}


async def js(ws, mid, expr):
    r = await cdp(ws, mid, 'Runtime.evaluate', {'expression': expr, 'returnByValue': True})
    return r.get('result', {}).get('result', {}).get('value', '')


async def upload_file(ws, mid, tab_id: str, file_path: str, cdp_port: int = 9222) -> bool:
    ws_url = f'ws://127.0.0.1:{cdp_port}/devtools/page/{tab_id}'
    async with websockets.connect(ws_url, ping_interval=None, open_timeout=10, max_size=10*1024*1024) as ws:
        # === Step 1: 找 file input ===
        r = await cdp(ws, mid, 'DOM.getDocument', {'depth': 0})
        root = r['result']['root']
        body_id = root['nodeId']
        for child in root.get('children', []):
            if child.get('localName') == 'body':
                body_id = child['nodeId']
                break

        r = await cdp(ws, mid, 'DOM.querySelectorAll', {
            'selector': 'input[type=file]',
            'nodeId': body_id
        })
        node_ids = r.get('result', {}).get('nodeIds', [])
        if not node_ids or not node_ids[0]:
            print('[ERROR] 未找到 file input')
            return False
        node_id = node_ids[0]
        print(f'[Step1] file input nodeId: {node_id}')

        # === Step 2: DOM.setFileInputFiles 设置文件 ===
        print(f'[Step2] 上传视频: {file_path}')
        r = await cdp(ws, mid, 'DOM.setFileInputFiles', {
            'files': [file_path],
            'nodeId': node_id
        })
        result = r.get('result')
        print(f'[Step2] setFileInputFiles: {result}')

        if result != {}:
            print('[WARN] 返回非空，尝试继续...')
        else:
            print('[OK] setFileInputFiles 成功，页面将自动跳转')

        # === Step 3: 等待跳转到 post 页 ===
        print('[Step3] 等待跳转到发布页...')
        for i in range(20):
            await asyncio.sleep(2)
            url = await js(ws, mid, 'window.location.href')
            if 'content/post' in str(url):
                print(f'  ✅ 跳转到发布页')
                break
            print(f'  [{i+1}/20] URL: {str(url)[:80]}')
        else:
            print('  ⚠️ 未检测到跳转，但继续')

        # === Step 4: 等待视频处理 ===
        print('[Step4] 等待视频处理（约 90 秒）...')
        for i in range(30):
            await asyncio.sleep(3)
            url = await js(ws, mid, 'window.location.href')
            blobs = await js(ws, mid, "(function(){var c=0;document.querySelectorAll('img').forEach(function(el){if(el.src.indexOf('blob')>=0&&el.offsetWidth>30)c++;});return c;})()")
            print(f'  [{i+1}/30] blobs: {blobs}, URL: {str(url)[:60]}')
            if int(blobs or 0) >= 2:
                print('  ✅ 视频处理完成！')
                break

        return True


def main():
    if len(sys.argv) < 3:
        print(f'用法: python {sys.argv[0]} <tab_id> <视频文件路径> [cdp_port]')
        sys.exit(1)
    tab_id = sys.argv[1]
    file_path = sys.argv[2]
    cdp_port = int(sys.argv[3]) if len(sys.argv) > 3 else 9222
    mid = [0]
    success = asyncio.run(upload_file(None, mid, tab_id, file_path, cdp_port))
    print('[OK] 上传成功!' if success else '[ERROR] 上传失败')
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()