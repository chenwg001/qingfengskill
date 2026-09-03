#!/usr/bin/env python3
"""
检查抖音封面对话框的完整 DOM 结构
用法: python check_cover_dialog.py <tab_id> [cdp_port]
"""
import sys
import json
import time
import asyncio
import websockets

def log(msg):
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

async def check_dialog(tab_id, cdp_port=9222):
    """检查封面对话框的 DOM 结构"""
    ws_url = f'ws://127.0.0.1:{cdp_port}/devtools/page/{tab_id}'
    log(f"连接: {ws_url}")
    
    async with websockets.connect(ws_url, ping_interval=None, open_timeout=15) as ws:
        msg_id = 0
        
        # 1. 启用域
        for domain in ['DOM', 'Runtime', 'Page']:
            msg_id += 1
            await send_cdp(ws, msg_id, f'{domain}.enable')
        
        log("所有域已启用")
        
        # 2. 获取完整 DOM 树（不限制 depth）
        log("获取完整 DOM 树...")
        msg_id += 1
        r = await send_cdp(ws, msg_id, 'DOM.getDocument', {'depth': -1})
        root_node_id = r.get('result', {}).get('root', {}).get('nodeId')
        
        if not root_node_id:
            log("[FAIL] 无法获取 DOM root")
            return
        
        log(f"DOM root: {root_node_id}")
        
        # 3. 查找所有包含"封面"、"裁剪"、"完成"的按钮
        log("查找关键按钮...")
        
        msg_id += 1
        r = await send_cdp(ws, msg_id, 'Runtime.evaluate', {
            'expression': '''
            (function() {
                const result = {
                    buttons: [],
                    inputs: [],
                    shadows: []
                };
                
                // 查找所有按钮
                document.querySelectorAll('button').forEach((btn, idx) => {
                    const text = btn.textContent.trim();
                    if (text) {
                        result.buttons.push({
                            index: idx,
                            text: text,
                            disabled: btn.disabled
                        });
                    }
                });
                
                // 查找所有 file input
                document.querySelectorAll('input[type=file]').forEach((inp, idx) => {
                    result.inputs.push({
                        index: idx,
                        accept: inp.accept,
                        multiple: inp.multiple
                    });
                });
                
                // 查找 shadow DOM
                document.querySelectorAll('*').forEach((el, idx) => {
                    if (el.shadowRoot) {
                        result.shadows.push({
                            tag: el.tagName,
                            id: el.id,
                            class: el.className
                        });
                    }
                });
                
                return result;
            })();
            ''',
            'returnByValue': True
        })
        
        result = r.get('result', {}).get('result', {}).get('value', {})
        
        log(f"找到 {len(result.get('buttons', []))} 个按钮:")
        for btn in result.get('buttons', []):
            log(f"  [{btn['index']}] {btn['text']} {'(disabled)' if btn['disabled'] else ''}")
        
        log(f"找到 {len(result.get('inputs', []))} 个 file input:")
        for inp in result.get('inputs', []):
            log(f"  accept={inp['accept']}, multiple={inp['multiple']}")
        
        log(f"找到 {len(result.get('shadows', []))} 个 shadow DOM:")
        for shadow in result.get('shadows', []):
            log(f"  <{shadow['tag']}> id={shadow['id']} class={shadow['class']}")
        
        # 4. 检查是否有"跳过裁剪"或"不使用裁剪"选项
        log("检查是否有跳过裁剪的选项...")
        
        msg_id += 1
        r = await send_cdp(ws, msg_id, 'Runtime.evaluate', {
            'expression': '''
            (function() {
                const skipKeywords = ['跳过', '不裁剪', '直接使用', '原图', '不编辑'];
                const result = [];
                
                document.querySelectorAll('button, span, div, a').forEach((el) => {
                    const text = el.textContent.trim();
                    if (skipKeywords.some(kw => text.includes(kw))) {
                        result.push({
                            tag: el.tagName,
                            text: text,
                            class: el.className
                        });
                    }
                });
                
                return result;
            })();
            ''',
            'returnByValue': True
        })
        
        skip_options = r.get('result', {}).get('result', {}).get('value', [])
        
        if skip_options:
            log("[OK] 找到可能的跳过裁剪选项:")
            for opt in skip_options:
                log(f"  <{opt['tag']}> {opt['text']}")
        else:
            log("[INFO] 未找到明显的跳过裁剪选项")
        
        # 5. 获取封面对话框的完整 HTML（前 2000 字符）
        log("获取页面 HTML（前 2000 字符）...")
        
        msg_id += 1
        r = await send_cdp(ws, msg_id, 'Runtime.evaluate', {
            'expression': 'document.body.innerHTML.substring(0, 2000)',
            'returnByValue': True
        })
        
        html = r.get('result', {}).get('result', {}).get('value', '')
        log(f"HTML (前 1000 字符):\n{html[:1000]}")

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("用法: python check_cover_dialog.py <tab_id> [cdp_port]")
        sys.exit(1)
    
    tab_id = sys.argv[1]
    cdp_port = int(sys.argv[2]) if len(sys.argv) > 2 else 9222
    
    asyncio.run(check_dialog(tab_id, cdp_port))
