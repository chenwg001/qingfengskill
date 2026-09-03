#!/usr/bin/env python3
"""
抖音视频上传脚本 V9 - 正确判断上传成功
用法: python upload_video_v9.py <tab_id> <video_path> [cdp_port]

正确判断方法：
1. 检查页面是否跳转到 /content/post/video
2. 检查是否有"重新上传"按钮（表示视频已上传）
3. 检查上传进度是否达到 100%
4. 检查"下一步"按钮是否启用
"""

import sys
import json
import time
import asyncio
import websockets
import os

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

async def wait_for_navigation(ws, msg_id_start, timeout=30):
    """等待页面导航完成"""
    log("等待页面导航...")
    
    # 启用 Page 域
    msg_id = msg_id_start
    await send_cdp(ws, msg_id, 'Page.enable')
    
    # 等待 Page.frameStoppedLoading 事件
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            response = json.loads(await asyncio.wait_for(ws.recv(), timeout=2))
            
            if response.get('method') == 'Page.frameStoppedLoading':
                log("[OK] 页面导航完成")
                return True
        except asyncio.TimeoutError:
            continue
    
    log("[WARN] 页面导航超时")
    return False

async def check_upload_success(ws, msg_id_start, timeout=120):
    """
    正确判断上传是否成功
    
    判断条件（任一满足即认为成功）：
    1. 页面 URL 包含 /content/post/video
    2. 页面包含"重新上传"文本（表示视频已上传）
    3. 页面包含"上传完成"文本
    4. "下一步"按钮已启用
    """
    log("验证上传是否成功...")
    
    msg_id = msg_id_start
    deadline = time.time() + timeout
    
    while time.time() < deadline:
        msg_id += 1
        
        # 检查 URL
        r = await send_cdp(ws, msg_id, 'Runtime.evaluate', {
            'expression': 'window.location.href',
            'returnByValue': True
        })
        
        url = r.get('result', {}).get('result', {}).get('value', '')
        
        if '/content/post/video' in url:
            log(f"[OK] URL 正确: {url}")
            
            # 进一步检查页面内容
            msg_id += 1
            r = await send_cdp(ws, msg_id, 'Runtime.evaluate', {
                'expression': 'document.body.innerText.substring(0, 1000)',
                'returnByValue': True
            })
            
            page_text = r.get('result', {}).get('result', {}).get('value', '')
            
            # 判断条件
            if '重新上传' in page_text:
                log('[OK] 找到"重新上传"按钮（视频已上传）')
                return True
            
            if '上传完成' in page_text:
                log('[OK] 找到"上传完成"文本')
                return True
            
            if '下一步' in page_text:
                log('[OK] 找到"下一步"按钮')
                # 检查按钮是否启用
                msg_id += 1
                r = await send_cdp(ws, msg_id, 'Runtime.evaluate', {
                    'expression': '''
                    (function() {
                        const btn = Array.from(document.querySelectorAll('button')).find(b => b.innerText.includes('下一步'));
                        return btn ? !btn.disabled : false;
                    })()
                    ''',
                    'returnByValue': True
                })
                
                next_enabled = r.get('result', {}).get('result', {}).get('value', False)
                if next_enabled:
                    log('[OK] "下一步"按钮已启用')
                    return True
            
            # 检查 video 元素
            msg_id += 1
            r = await send_cdp(ws, msg_id, 'Runtime.evaluate', {
                'expression': 'document.querySelectorAll("video").length',
                'returnByValue': True
            })
            
            video_count = r.get('result', {}).get('result', {}).get('value', 0)
            if video_count > 0:
                log(f'[OK] 找到 {video_count} 个 video 元素（视频已上传）')
                return True
        
        # 等待 3 秒后重试
        await asyncio.sleep(3)
    
    log("[FAIL] 验证超时（未检测到上传成功）")
    return False

async def upload_video_v9(tab_id, video_path, cdp_port=9222):
    """上传视频 - 使用正确的判断方法"""
    ws_url = f'ws://127.0.0.1:{cdp_port}/devtools/page/{tab_id}'
    log(f"Tab: {tab_id}")
    log(f"Video: {video_path}")
    log(f"CDP Port: {cdp_port}")
    log(f"连接: {ws_url}")
    
    async with websockets.connect(ws_url, ping_interval=None, open_timeout=15) as ws:
        msg_id = 0
        
        # 1. 启用域
        for domain in ['DOM', 'Runtime', 'Page']:
            msg_id += 1
            await send_cdp(ws, msg_id, f'{domain}.enable')
        
        log("所有域已启用")
        
        # 2. 导航到上传页面
        log("导航到上传页面...")
        msg_id += 1
        await send_cdp(ws, msg_id, 'Page.navigate', {
            'url': 'https://creator.douyin.com/creator-micro/content/post/video'
        })
        
        # 等待页面加载
        await wait_for_navigation(ws, msg_id, timeout=30)
        
        # 等待页面完全加载
        log("等待页面加载（10秒）...")
        await asyncio.sleep(10)
        
        # 3. 查找视频 input（通过 accept 属性）
        log("查找视频 file input...")
        
        # 获取 root node
        msg_id += 1
        r = await send_cdp(ws, msg_id, 'DOM.getDocument', {'depth': 1})
        root_node_id = r.get('result', {}).get('root', {}).get('nodeId')
        
        if not root_node_id:
            log("[FAIL] 无法获取 DOM root")
            return False
        
        # 查询所有 file input
        msg_id += 1
        r = await send_cdp(ws, msg_id, 'DOM.querySelectorAll', {
            'selector': 'input[type=file]',
            'nodeId': root_node_id
        })
        
        node_ids = r.get('result', {}).get('nodeIds', [])
        log(f"找到 {len(node_ids)} 个 file input: {node_ids}")
        
        if not node_ids:
            log("[FAIL] 没有找到 file input")
            return False
        
        # 找到视频 input（accept 包含 video）
        video_input_id = None
        for node_id in node_ids:
            msg_id += 1
            r = await send_cdp(ws, msg_id, 'DOM.getAttributes', {'nodeId': node_id})
            attrs = r.get('result', {}).get('attributes', [])
            
            # 转换为字典
            attr_dict = {}
            for i in range(0, len(attrs), 2):
                attr_dict[attrs[i]] = attrs[i+1] if i+1 < len(attrs) else ''
            
            accept = attr_dict.get('accept', '')
            
            # 如果 accept 包含 video，这就是视频输入
            if 'video' in accept.lower():
                video_input_id = node_id
                log(f"[OK] 找到视频 input: nodeId={video_input_id}, accept={accept}")
                break
        
        if not video_input_id:
            # fallback：使用第二个 input
            if len(node_ids) >= 2:
                video_input_id = node_ids[1]
                log(f"[WARN] 未找到 video accept，使用第二个 input: {video_input_id}")
            else:
                log("[FAIL] 未找到视频 input")
                return False
        
        # 4. 设置视频文件
        log(f"使用 nodeId: {video_input_id}")
        log(f"设置视频文件: {video_path}")
        
        msg_id += 1
        r = await send_cdp(ws, msg_id, 'DOM.setFileInputFiles', {
            'nodeId': video_input_id,
            'files': [video_path]
        })
        
        log(f"设置文件结果: {r}")
        
        # 等待文件设置完成
        await asyncio.sleep(3)
        
        # 5. 正确判断上传是否成功
        log("等待上传开始...")
        
        success = await check_upload_success(ws, msg_id, timeout=120)
        
        if success:
            log("[OK] 视频上传成功！")
            return True
        else:
            log("[FAIL] 视频上传失败")
            return False

if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("用法: python upload_video_v9.py <tab_id> <video_path> [cdp_port]")
        sys.exit(1)
    
    tab_id = sys.argv[1]
    video_path = sys.argv[2]
    cdp_port = int(sys.argv[3]) if len(sys.argv) > 3 else 9222
    
    success = asyncio.run(upload_video_v9(tab_id, video_path, cdp_port))
    
    if success:
        print("\n[OK] 视频上传成功！")
    else:
        print("\n[FAIL] 视频上传失败")
    
    sys.exit(0 if success else 1)
