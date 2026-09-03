#!/usr/bin/env python3
"""
抖音视频上传脚本 V2 - 等待 file input 出现后再上传
用法: python upload_video_v2.py <tab_id> <video_path> [cdp_port]
"""
import sys
import json
import time
import asyncio
import websockets

def log(msg):
    # Windows console is GBK, avoid emoji
    msg = msg.replace('✅', '[OK]').replace('❌', '[FAIL]')
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

async def wait_for_file_input(ws, root_node_id, max_wait=30):
    """等待 file input 出现"""
    msg_id = 10
    for i in range(max_wait * 2):  # 每0.5秒检查一次
        msg_id += 1
        await ws.send(json.dumps({
            'id': msg_id,
            'method': 'DOM.querySelectorAll',
            'params': {'selector': 'input[type=file]', 'nodeId': root_node_id}
        }))
        r = json.loads(await ws.recv())
        node_ids = r.get('result', {}).get('nodeIds', [])
        
        if len(node_ids) >= 2:  # 至少有视频和封面两个 file input
            log(f"找到 {len(node_ids)} 个 file input: {node_ids}")
            return node_ids
        
        if i % 4 == 0:  # 每2秒打印一次
            log(f"等待 file input 出现... ({i//2}s)")
        
        await asyncio.sleep(0.5)
    
    return None

async def upload_video(tab_id, video_path, cdp_port=9222):
    ws_url = f'ws://127.0.0.1:{cdp_port}/devtools/page/{tab_id}'
    log(f"连接到: {ws_url}")
    
    async with websockets.connect(ws_url, ping_interval=None, open_timeout=15) as ws:
        # Enable domains
        log("启用 DOM...")
        await ws.send(json.dumps({'id': 1, 'method': 'DOM.enable'}))
        await ws.recv()
        
        # Get document
        log("获取 DOM 树...")
        await ws.send(json.dumps({'id': 2, 'method': 'DOM.getDocument', 'params': {'depth': -1}}))
        r = json.loads(await ws.recv())
        
        if 'result' not in r:
            log(f"ERROR: 获取 DOM 失败: {r}")
            return False
        
        root_node_id = r['result']['root']['nodeId']
        log(f"DOM root: {root_node_id}")
        
        # 等待 file input 出现
        log("等待 file input 出现...")
        node_ids = await wait_for_file_input(ws, root_node_id)
        
        if not node_ids:
            log("ERROR: 未找到 file input (超时)")
            return False
        
        # 第一个 file input 是视频上传
        video_input_id = node_ids[0]
        log(f"使用 video input: {video_input_id}")
        
        # 设置文件
        log(f"设置文件: {video_path}")
        await ws.send(json.dumps({
            'id': 3,
            'method': 'DOM.setFileInputFiles',
            'params': {
                'files': [video_path],
                'nodeId': video_input_id
            }
        }))
        await ws.recv()
        
        log("文件已设置，等待上传...")
        # 等待页面跳转
        await asyncio.sleep(5)
        
        log("上传完成")
        return True

if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("用法: python upload_video_v2.py <tab_id> <video_path> [cdp_port]")
        sys.exit(1)
    
    tab_id = sys.argv[1]
    video_path = sys.argv[2]
    cdp_port = int(sys.argv[3]) if len(sys.argv) > 3 else 9222
    
    log(f"Tab: {tab_id}")
    log(f"Video: {video_path}")
    log(f"CDP Port: {cdp_port}")
    
    success = asyncio.run(upload_video(tab_id, video_path, cdp_port))
    
    if success:
        log("✅ 上传成功")
    else:
        log("❌ 上传失败")
        sys.exit(1)
