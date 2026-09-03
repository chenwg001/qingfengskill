#!/usr/bin/env python3
"""
抖音视频上传脚本 V3 - 使用 Runtime.evaluate 避免 DOM 树过大
用法: python upload_video_v3.py <tab_id> <video_path> [cdp_port]
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

async def find_file_inputs(ws):
    """使用 JS 查找所有 file input，返回 nodeId 列表"""
    msg_id = 10
    
    # 执行 JS 获取所有 file input
    msg_id += 1
    await ws.send(json.dumps({
        'id': msg_id,
        'method': 'Runtime.evaluate',
        'params': {
            'expression': 'document.querySelectorAll("input[type=file]")',
            'returnByValue': False
        }
    }))
    r = json.loads(await ws.recv())
    
    if 'result' not in r:
        log(f"ERROR: Runtime.evaluate failed: {r}")
        return None
    
    obj_id = r['result']['result'].get('objectId')
    if not obj_id:
        log("ERROR: No objectId returned")
        return None
    
    # 获取数组长度
    msg_id += 1
    await ws.send(json.dumps({
        'id': msg_id,
        'method': 'Runtime.getProperties',
        'params': {'objectId': obj_id, 'ownProperties': True}
    }))
    r = json.loads(await ws.recv())
    
    props = r.get('result', {}).get('result', [])
    length = 0
    for p in props:
        if p.get('name') == 'length':
            length = p.get('value', {}).get('value', 0)
            break
    
    log(f"找到 {length} 个 file input")
    
    if length < 2:
        log("WARNING: 少于 2 个 file input，页面可能未完全加载")
        return None
    
    # 获取每个 input 的 nodeId
    node_ids = []
    for i in range(length):
        # 获取数组元素
        msg_id += 1
        await ws.send(json.dumps({
            'id': msg_id,
            'method': 'Runtime.callFunctionOn',
            'params': {
                'objectId': obj_id,
                'functionDeclaration': f'function() {{ return this[{i}] }}'
            }
        }))
        r = json.loads(await ws.recv())
        
        elem_obj_id = r.get('result', {}).get('result', {}).get('objectId')
        if not elem_obj_id:
            continue
        
        # 获取 nodeId
        msg_id += 1
        await ws.send(json.dumps({
            'id': msg_id,
            'method': 'DOM.requestNode',
            'params': {'objectId': elem_obj_id}
        }))
        r = json.loads(await ws.recv())
        
        node_id = r.get('result', {}).get('nodeId')
        if node_id:
            node_ids.append(node_id)
    
    return node_ids

async def upload_video(tab_id, video_path, cdp_port=9222):
    ws_url = f'ws://127.0.0.1:{cdp_port}/devtools/page/{tab_id}'
    log(f"连接到: {ws_url}")
    
    async with websockets.connect(ws_url, ping_interval=None, open_timeout=15) as ws:
        # Enable domains
        log("启用 DOM...")
        await ws.send(json.dumps({'id': 1, 'method': 'DOM.enable'}))
        await ws.recv()
        
        log("启用 Runtime...")
        await ws.send(json.dumps({'id': 2, 'method': 'Runtime.enable'}))
        await ws.recv()
        
        # 等待 file input 出现
        log("等待 file input 出现...")
        node_ids = None
        for i in range(60):  # 等待30秒
            node_ids = await find_file_inputs(ws)
            if node_ids and len(node_ids) >= 2:
                break
            if i % 4 == 0:
                log(f"等待中... ({i//2}s)")
            await asyncio.sleep(0.5)
        
        if not node_ids or len(node_ids) < 2:
            log("ERROR: 未找到足够的 file input")
            return False
        
        # 第一个 file input 是视频上传
        video_input_id = node_ids[0]
        log(f"使用 video input: {video_input_id}")
        
        # 设置文件
        log(f"设置文件: {video_path}")
        await ws.send(json.dumps({
            'id': 50,
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
        print("用法: python upload_video_v3.py <tab_id> <video_path> [cdp_port]")
        sys.exit(1)
    
    tab_id = sys.argv[1]
    video_path = sys.argv[2]
    cdp_port = int(sys.argv[3]) if len(sys.argv) > 3 else 9222
    
    log(f"Tab: {tab_id}")
    log(f"Video: {video_path}")
    log(f"CDP Port: {cdp_port}")
    
    success = asyncio.run(upload_video(tab_id, video_path, cdp_port))
    
    if success:
        log("[OK] 上传成功")
    else:
        log("[FAIL] 上传失败")
        sys.exit(1)
