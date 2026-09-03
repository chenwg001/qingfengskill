#!/usr/bin/env python3
"""
抖音视频上传脚本 V4 - 正确匹配 CDP 请求/响应
用法: python upload_video_v4.py <tab_id> <video_path> [cdp_port]
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

async def send_cdp(ws, msg_id, method, params=None):
    """发送 CDP 消息并等待响应"""
    msg = {'id': msg_id, 'method': method}
    if params:
        msg['params'] = params
    
    log(f"发送: {method} (id={msg_id})")
    await ws.send(json.dumps(msg))
    
    # 等待响应（匹配 id）
    while True:
        response = json.loads(await ws.recv())
        if response.get('id') == msg_id:
            return response
        # 跳过事件通知（如 Runtime.consoleAPICalled）
        log(f"跳过事件: {response.get('method', 'unknown')}")

async def upload_video(tab_id, video_path, cdp_port=9222):
    ws_url = f'ws://127.0.0.1:{cdp_port}/devtools/page/{tab_id}'
    log(f"连接到: {ws_url}")
    
    async with websockets.connect(ws_url, ping_interval=None, open_timeout=15) as ws:
        msg_id = 0
        
        # Enable DOM
        msg_id += 1
        r = await send_cdp(ws, msg_id, 'DOM.enable')
        log(f"DOM enabled: {r}")
        
        # Enable Runtime
        msg_id += 1
        r = await send_cdp(ws, msg_id, 'Runtime.enable')
        log(f"Runtime enabled: {r}")
        
        # 等待一会儿让页面稳定
        log("等待页面稳定...")
        await asyncio.sleep(3)
        
        # 使用 JS 查找 file inputs
        log("查找 file inputs...")
        msg_id += 1
        r = await send_cdp(ws, msg_id, 'Runtime.evaluate', {
            'expression': 'document.querySelectorAll("input[type=file]").length',
            'returnByValue': True
        })
        
        length = r.get('result', {}).get('result', {}).get('value', 0)
        log(f"找到 {length} 个 file input")
        
        if length < 1:
            log("ERROR: 未找到 file input")
            return False
        
        # 获取第一个 file input
        msg_id += 1
        r = await send_cdp(ws, msg_id, 'Runtime.evaluate', {
            'expression': 'document.querySelectorAll("input[type=file]")[0]',
            'returnByValue': False
        })
        
        obj_id = r.get('result', {}).get('result', {}).get('objectId')
        if not obj_id:
            log("ERROR: 无法获取 file input 的 objectId")
            return False
        
        log(f"File input objectId: {obj_id}")
        
        # 获取 nodeId
        msg_id += 1
        r = await send_cdp(ws, msg_id, 'DOM.requestNode', {'objectId': obj_id})
        
        node_id = r.get('result', {}).get('nodeId')
        if not node_id:
            log("ERROR: 无法获取 file input 的 nodeId")
            return False
        
        log(f"File input nodeId: {node_id}")
        
        # 设置文件
        log(f"设置文件: {video_path}")
        msg_id += 1
        r = await send_cdp(ws, msg_id, 'DOM.setFileInputFiles', {
            'files': [video_path],
            'nodeId': node_id
        })
        
        log("文件已设置，等待上传...")
        await asyncio.sleep(5)
        log("上传完成")
        return True

if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("用法: python upload_video_v4.py <tab_id> <video_path> [cdp_port]")
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
