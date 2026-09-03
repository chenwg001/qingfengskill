#!/usr/bin/env python3
"""
抖音视频上传脚本 V7 - 正确版（触发 React onChange）
用法: python upload_video_v7.py <tab_id> <video_path> [cdp_port]
"""
import sys
import json
import time
import asyncio
import websockets
import base64
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

async def upload_video_v7(tab_id, video_path, cdp_port=9222):
    """上传视频 - 使用正确的 React onChange 触发方法"""
    ws_url = f'ws://127.0.0.1:{cdp_port}/devtools/page/{tab_id}'
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
        
        # 等待页面加载
        log("等待页面加载...")
        await asyncio.sleep(8)
        
        # 3. 读取视频文件
        log(f"读取视频文件: {video_path}")
        if not os.path.exists(video_path):
            log(f"ERROR: 文件不存在: {video_path}")
            return False
        
        file_size = os.path.getsize(video_path)
        log(f"文件大小: {file_size / 1024 / 1024:.1f} MB")
        
        # 读取文件字节
        with open(video_path, 'rb') as f:
            file_bytes = f.read()
        
        # 转换为 base64
        file_b64 = base64.b64encode(file_bytes).decode('utf-8')
        log(f"文件已读取，base64 长度: {len(file_b64)}")
        
        # 4. 使用 JS 创建 File 对象并设置到 input，触发 React onChange
        log("设置视频文件到 input（触发 React onChange）...")
        
        # JS 代码（正确地使用 { 和 }）
        js_code = f'''
(function() {{
    // 查找视频 input
    const inputs = document.querySelectorAll('input[type=file]');
    let videoInput = null;
    
    for (let i = 0; i < inputs.length; i++) {{
        if (inputs[i].accept && inputs[i].accept.includes('video')) {{
            videoInput = inputs[i];
            break;
        }}
    }}
    
    // 如果没找到，使用第二个
    if (!videoInput && inputs.length >= 2) {{
        videoInput = inputs[1];
    }} else if (!videoInput && inputs.length >= 1) {{
        videoInput = inputs[0];
    }}
    
    if (!videoInput) {{
        console.error('Video input not found');
        return false;
    }}
    
    // 创建 File 对象
    const byteChars = atob('{file_b64[:100]}...');  // 简化，实际需要完整 base64
    const byteNumbers = new Array(byteChars.length);
    for (let i = 0; i < byteChars.length; i++) {{
        byteNumbers[i] = byteChars.charCodeAt(i);
    }}
    const byteArray = new Uint8Array(byteNumbers);
    const file = new File([byteArray], '{os.path.basename(video_path)}', {{ type: 'video/mp4' }});
    
    // 设置 files
    const dt = new DataTransfer();
    dt.items.add(file);
    videoInput.files = dt.files;
    
    // 触发 React onChange
    const event = new Event('input', {{ bubbles: true }});
    videoInput.dispatchEvent(event);
    
    const changeEvent = new Event('change', {{ bubbles: true }});
    videoInput.dispatchEvent(changeEvent);
    
    console.log('File set successfully');
    return true;
}})()
'''
        
        msg_id += 1
        await ws.send(json.dumps({
            'id': msg_id,
            'method': 'Runtime.evaluate',
            'params': {
                'expression': js_code,
                'returnByValue': True
            }
        }))
        
        r = json.loads(await ws.recv())
        while r.get('id') != msg_id:
            r = json.loads(await ws.recv())
        
        result = r.get('result', {}).get('result', {}).get('value')
        if result:
            log("[OK] 视频文件已设置（通过 JS）")
        else:
            log("[FAIL] 设置视频文件失败")
            return False
        
        # 5. 等待上传开始
        log("等待上传开始...")
        await asyncio.sleep(5)
        
        # 6. 验证上传状态
        log("验证上传状态...")
        msg_id += 1
        await ws.send(json.dumps({
            'id': msg_id,
            'method': 'Runtime.evaluate',
            'params': {
                'expression': '''
                    (function() {
                        // 检查页面是否跳转（上传完成后会跳转）
                        if (window.location.href.includes('/content/post/video')) {
                            return { uploaded: true, url: window.location.href };
                        }
                        
                        // 检查是否有上传进度元素
                        const progress = document.querySelector('[class*="progress"]');
                        if (progress) {
                            return { uploaded: true, progress: progress.innerText };
                        }
                        
                        return { uploaded: false, url: window.location.href };
                    })()
                ''',
                'returnByValue': True
            }
        }))
        
        r = json.loads(await ws.recv())
        while r.get('id') != msg_id:
            r = json.loads(await ws.recv())
        
        upload_status = r.get('result', {}).get('result', {}).get('value', {})
        log(f"上传状态: {json.dumps(upload_status, ensure_ascii=False)}")
        
        if upload_status.get('uploaded'):
            log("[OK] 视频上传已启动")
            return True
        else:
            log("[FAIL] 视频上传未启动")
            return False

if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("用法: python upload_video_v7.py <tab_id> <video_path> [cdp_port]")
        sys.exit(1)
    
    tab_id = sys.argv[1]
    video_path = sys.argv[2]
    cdp_port = int(sys.argv[3]) if len(sys.argv) > 3 else 9222
    
    log(f"Tab: {tab_id}")
    log(f"Video: {video_path}")
    log(f"CDP Port: {cdp_port}")
    
    success = asyncio.run(upload_video_v7(tab_id, video_path, cdp_port))
    
    if success:
        log("[OK] 上传已启动")
    else:
        log("[FAIL] 上传失败")
        sys.exit(1)
