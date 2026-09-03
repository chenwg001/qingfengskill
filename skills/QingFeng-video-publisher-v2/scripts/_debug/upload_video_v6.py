#!/usr/bin/env python3
"""
抖音视频上传脚本 V6 - 修复版（正确识别视频 file input）
用法: python upload_video_v6.py <tab_id> <video_path> [cdp_port]
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

async def find_video_input_id(ws, msg_id_start, root_node_id):
    """查找接受视频文件的 input（通过 accept 属性）"""
    msg_id = msg_id_start
    
    # 获取所有 file input
    msg_id += 1
    r = await send_cdp(ws, msg_id, 'DOM.querySelectorAll', {
        'selector': 'input[type=file]',
        'nodeId': root_node_id
    })
    
    node_ids = r.get('result', {}).get('nodeIds', [])
    log(f"找到 {len(node_ids)} 个 file input: {node_ids}")
    
    # 检查每个 input 的 accept 属性
    for idx, node_id in enumerate(node_ids):
        msg_id += 1
        r = await send_cdp(ws, msg_id, 'DOM.getAttributes', {'nodeId': node_id})
        attrs = r.get('result', {}).get('attributes', [])
        
        # 转换为字典
        attr_dict = {}
        for i in range(0, len(attrs), 2):
            attr_dict[attrs[i]] = attrs[i+1] if i+1 < len(attrs) else ''
        
        accept = attr_dict.get('accept', '')
        log(f"  [{idx}] nodeId={node_id}, accept={accept}")
        
        # 如果 accept 包含 video，这就是视频输入
        if 'video' in accept.lower():
            log(f"[OK] 找到视频 input: nodeId={node_id}")
            return node_id, msg_id
    
    # 如果没找到，使用第二个（通常是视频）
    if len(node_ids) >= 2:
        log(f"[?] 未找到 accept 包含 video 的 input，使用第二个: {node_ids[1]}")
        return node_ids[1], msg_id
    
    # 如果只有一个，使用第一个
    if len(node_ids) == 1:
        log(f"[?] 只有一个 input，使用: {node_ids[0]}")
        return node_ids[0], msg_id
    
    return None, msg_id

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
                pass
        
        # 等待页面加载
        log("等待页面加载...")
        await asyncio.sleep(8)
        
        # 3. 获取 document (depth=1)
        msg_id += 1
        r = await send_cdp(ws, msg_id, 'DOM.getDocument', {'depth': 1})
        root_node_id = r.get('result', {}).get('root', {}).get('nodeId')
        if not root_node_id:
            log("ERROR: 无法获取 document root")
            return False
        
        log(f"Document root: {root_node_id}")
        
        # 4. 查找视频 file input（通过 accept 属性）
        log("查找视频 file input...")
        video_input_id, msg_id = await find_video_input_id(ws, msg_id, root_node_id)
        
        if not video_input_id:
            log("ERROR: 未找到 file input")
            return False
        
        # 5. 设置视频文件
        log(f"设置视频文件: {video_path}")
        log(f"使用 nodeId: {video_input_id}")
        
        msg_id += 1
        r = await send_cdp(ws, msg_id, 'DOM.setFileInputFiles', {
            'files': [video_path],
            'nodeId': video_input_id
        })
        
        log("文件已设置，等待上传...")
        await asyncio.sleep(5)
        
        # 6. 验证文件是否真的被设置
        log("验证文件是否设置成功...")
        msg_id += 1
        await ws.send(json.dumps({
            'id': msg_id,
            'method': 'Runtime.evaluate',
            'params': {
                'expression': '''
                    (function() {
                        const inputs = document.querySelectorAll('input[type=file]');
                        const result = [];
                        inputs.forEach((inp, idx) => {
                            result.push({
                                index: idx,
                                files: inp.files ? inp.files.length : 0,
                                accept: inp.accept
                            });
                        });
                        return result;
                    })()
                ''',
                'returnByValue': True
            }
        }))
        
        while True:
            r = json.loads(await ws.recv())
            if r.get('id') == msg_id:
                break
        
        file_status = r.get('result', {}).get('result', {}).get('value', [])
        log(f"文件状态: {json.dumps(file_status, ensure_ascii=False)}")
        
        has_video = any(f['files'] > 0 and 'video' in f.get('accept', '').lower() for f in file_status)
        
        if has_video:
            log("[OK] 视频文件已成功设置")
            return True
        else:
            log("[FAIL] 视频文件未设置成功")
            return False

if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("用法: python upload_video_v6.py <tab_id> <video_path> [cdp_port]")
        sys.exit(1)
    
    tab_id = sys.argv[1]
    video_path = sys.argv[2]
    cdp_port = int(sys.argv[3]) if len(sys.argv) > 3 else 9222
    
    log(f"Tab: {tab_id}")
    log(f"Video: {video_path}")
    log(f"CDP Port: {cdp_port}")
    
    success = asyncio.run(upload_video(tab_id, video_path, cdp_port))
    
    if success:
        log("[OK] 上传已启动")
    else:
        log("[FAIL] 上传失败")
        sys.exit(1)
