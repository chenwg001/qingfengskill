#!/usr/bin/env python3
"""
抖音视频上传脚本 V5 - 简化版（正确方法）
用法: python upload_video_v5.py <tab_id> <video_path> [cdp_port]
"""
import sys
import json
import time
import asyncio
import websockets

def log(msg):
    msg = msg.replace('✅', '[OK]').replace('❌', '[FAIL]')
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

async def send_cdp(ws, msg_id, method, params=None):
    """发送 CDP 消息并等待响应"""
    msg = {'id': msg_id, 'method': method}
    if params:
        msg['params'] = params
    
    await ws.send(json.dumps(msg))
    
    # 等待响应（匹配 id）
    while True:
        response = json.loads(await ws.recv())
        if response.get('id') == msg_id:
            return response
        # 跳过事件通知
        method = response.get('method', '')
        if method:
            log(f"事件: {method}")

async def upload_video(tab_id, video_path, cdp_port=9222):
    ws_url = f'ws://127.0.0.1:{cdp_port}/devtools/page/{tab_id}'
    log(f"连接: {ws_url}")
    
    async with websockets.connect(ws_url, ping_interval=None, open_timeout=15) as ws:
        msg_id = 0
        
        # 1. 启用 DOM
        msg_id += 1
        r = await send_cdp(ws, msg_id, 'DOM.enable')
        log("DOM 已启用")
        
        # 2. 导航到上传页面（如果还没在）
        log("导航到上传页面...")
        msg_id += 1
        await ws.send(json.dumps({
            'id': msg_id,
            'method': 'Page.navigate',
            'params': {'url': 'https://creator.douyin.com/creator-micro/content/post/video'}
        }))
        
        while True:
            response = json.loads(await ws.recv())
            if response.get('id') == msg_id:
                log(f"导航结果: {response.get('result')}")
                break
            method = response.get('method', '')
            if method:
                log(f"事件: {method}")
        
        # 等待页面加载
        log("等待页面加载...")
        await asyncio.sleep(8)
        
        # 3. 获取 document (depth=1，避免缓冲区溢出)
        msg_id += 1
        r = await send_cdp(ws, msg_id, 'DOM.getDocument', {'depth': 1})
        root_node_id = r.get('result', {}).get('root', {}).get('nodeId')
        if not root_node_id:
            log("ERROR: 无法获取 document root")
            return False
        
        log(f"Document root: {root_node_id}")
        
        # 4. 查找 file inputs
        log("查找 file inputs...")
        for attempt in range(60):  # 等待30秒
            msg_id += 1
            r = await send_cdp(ws, msg_id, 'DOM.querySelectorAll', {
                'selector': 'input[type=file]',
                'nodeId': root_node_id
            })
            
            node_ids = r.get('result', {}).get('nodeIds', [])
            if len(node_ids) >= 1:
                log(f"找到 {len(node_ids)} 个 file input: {node_ids}")
                break
            
            if attempt % 4 == 0:
                log(f"等待 file input 出现... ({attempt // 2}s)")
            await asyncio.sleep(0.5)
        else:
            log("ERROR: 未找到 file input (超时)")
            return False
        
        # 5. 设置视频文件（第一个 file input）
        video_input_id = node_ids[0]
        log(f"设置视频文件: {video_path}")
        log(f"使用 nodeId: {video_input_id}")
        
        msg_id += 1
        r = await send_cdp(ws, msg_id, 'DOM.setFileInputFiles', {
            'files': [video_path],
            'nodeId': video_input_id
        })
        
        log("文件已设置，等待上传...")
        await asyncio.sleep(5)
        
        log("[OK] 视频上传已启动")
        return True

if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("用法: python upload_video_v5.py <tab_id> <video_path> [cdp_port]")
        sys.exit(1)
    
    tab_id = sys.argv[1]
    video_path = sys.argv[2]
    cdp_port = int(sys.argv[3]) if len(sys.argv) > 3 else 9222
    
    log(f"Tab: {tab_id}")
    log(f"Video: {video_path}")
    log(f"CDP Port: {cdp_port}")
    
    success = asyncio.run(upload_video(tab_id, video_path, cdp_port))
    
    if success:
        log("[OK] 上传完成")
    else:
        log("[FAIL] 上传失败")
        sys.exit(1)
