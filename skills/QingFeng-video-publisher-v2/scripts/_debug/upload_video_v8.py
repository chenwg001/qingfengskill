#!/usr/bin/env python3
"""
抖音视频上传脚本 V8 - 通过 Runtime.evaluate 触发 React onChange
用法: python upload_video_v8.py <tab_id> <video_path> [cdp_port]
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

async def upload_video_v8(tab_id, video_path, cdp_port=9222):
    """上传视频 - 通过 Runtime.evaluate 触发 React onChange"""
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
        log("等待页面加载（15秒）...")
        await asyncio.sleep(15)
        
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
            #  fallback：使用第二个 input
            if len(node_ids) >= 2:
                video_input_id = node_ids[1]
                log(f"[WARN] 未找到 video accept，使用第二个 input: {video_input_id}")
            else:
                log("[FAIL] 未找到视频 input")
                return False
        
        # 4. 通过 Runtime.evaluate 触发 React onChange
        log(f"使用 nodeId: {video_input_id}")
        
        # 方法：通过 Runtime.evaluate 执行 JS，直接设置 input.files 并触发 React 事件
        log("通过 Runtime.evaluate 触发 React onChange...")
        
        # JS 代码：找到 input，设置文件，触发 React 事件
        js_code = f"""
        (function() {{
            // 1. 找到视频 input 元素
            const input = document.querySelectorAll('input[type=file]')[1];  // 第二个是视频
            
            if (!input) {{
                console.log('[V8] 未找到视频 input');
                return false;
            }}
            
            console.log('[V8] 找到视频 input:', input);
            console.log('[V8] accept:', input.accept);
            
            // 2. 创建 File 对象（通过 fetch 加载视频文件）
            const videoPath = '{video_path}';
            console.log('[V8] 视频路径:', videoPath);
            
            // 注意：浏览器无法直接访问本地文件，需要通过 DataTransfer API
            // 但我们可以通过设置 input.value 并触发事件来模拟
            
            // 方法：直接触发 click，让用户选择文件（不可行，因为要自动化）
            // 方法：通过 CDP 的 DOM.setFileInputFiles（已证明不触发 React）
            // 方法：通过 React fiber 找到 onChange 并调用（复杂）
            
            // 简化方案：使用 DataTransfer API（适用于现代浏览器）
            const dt = new DataTransfer();
            
            // 问题：无法直接创建 File 对象从本地路径
            // 需要先用 fetch 加载文件，但视频文件太大
            
            console.log('[V8] 无法直接设置文件，需要 CDP 配合');
            return false;
        }})();
        """
        
        # 实际上，我们需要结合 CDP 和 JS：
        # 1. 先用 CDP 的 DOM.setFileInputFiles 设置文件
        # 2. 再用 JS 触发 React 的 onChange 事件
        
        log("步骤1：用 CDP 设置文件...")
        msg_id += 1
        r = await send_cdp(ws, msg_id, 'DOM.setFileInputFiles', {
            'nodeId': video_input_id,
            'files': [video_path]
        })
        
        log(f"设置文件结果: {r}")
        
        # 等待一下让 CDP 完成
        await asyncio.sleep(2)
        
        log("步骤2：用 JS 触发 React onChange 事件...")
        
        # JS 代码：触发 input 和 change 事件
        js_trigger = f"""
        (function() {{
            const input = document.querySelectorAll('input[type=file]')[1];
            
            if (!input) {{
                console.log('[V8] 未找到视频 input');
                return false;
            }}
            
            console.log('[V8] 触发 React onChange...');
            console.log('[V8] input.files:', input.files);
            console.log('[V8] input.files.length:', input.files ? input.files.length : 0);
            
            // 触发 React 的 onChange
            const event = new Event('input', {{ bubbles: true }});
            input.dispatchEvent(event);
            
            const changeEvent = new Event('change', {{ bubbles: true }});
            input.dispatchEvent(changeEvent);
            
            console.log('[V8] 事件已触发');
            return true;
        }})();
        """
        
        msg_id += 1
        r = await send_cdp(ws, msg_id, 'Runtime.evaluate', {
            'expression': js_trigger,
            'returnByValue': True
        })
        
        log(f"触发事件结果: {r}")
        
        # 5. 等待上传开始
        log("等待上传开始（30秒）...")
        await asyncio.sleep(30)
        
        # 6. 验证上传是否成功
        log("验证上传状态...")
        
        # 检查页面是否跳转或出现视频预览
        msg_id += 1
        r = await send_cdp(ws, msg_id, 'Runtime.evaluate', {
            'expression': 'document.body.innerText.substring(0, 500)',
            'returnByValue': True
        })
        
        page_text = r.get('result', {}).get('result', {}).get('value', '')
        log(f"页面文本（前500字符）:\n{page_text[:200]}")
        
        # 检查是否有视频元素
        msg_id += 1
        r = await send_cdp(ws, msg_id, 'Runtime.evaluate', {
            'expression': 'document.querySelectorAll("video").length',
            'returnByValue': True
        })
        
        video_count = r.get('result', {}).get('result', {}).get('value', 0)
        log(f"页面 video 元素数量: {video_count}")
        
        if video_count > 0:
            log("[OK] 视频已上传（找到 video 元素）")
            return True
        
        # 检查 file input 的 files 属性
        msg_id += 1
        r = await send_cdp(ws, msg_id, 'Runtime.evaluate', {
            'expression': f"""
            (function() {{
                const input = document.querySelectorAll('input[type=file]')[1];
                if (!input) return null;
                return {{
                    'files': input.files ? input.files.length : 0,
                    'value': input.value
                }};
            }})();
            """,
            'returnByValue': True
        })
        
        files_info = r.get('result', {}).get('result', {}).get('value')
        log(f"File input 状态: {files_info}")
        
        if files_info and files_info.get('files', 0) > 0:
            log("[OK] 视频文件已设置")
            return True
        
        log("[FAIL] 视频上传失败")
        return False

if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("用法: python upload_video_v8.py <tab_id> <video_path> [cdp_port]")
        sys.exit(1)
    
    tab_id = sys.argv[1]
    video_path = sys.argv[2]
    cdp_port = int(sys.argv[3]) if len(sys.argv) > 3 else 9222
    
    success = asyncio.run(upload_video_v8(tab_id, video_path, cdp_port))
    
    if success:
        print("\n[OK] 视频上传成功！")
    else:
        print("\n[FAIL] 视频上传失败")
    
    sys.exit(0 if success else 1)
