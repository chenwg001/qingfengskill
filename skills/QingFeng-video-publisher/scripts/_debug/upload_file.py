# -*- coding: utf-8 -*-
"""
CDP 文件上传脚本 - 用于视频和封面图片上传
使用方法：
  python upload_file.py <tab_id> <file_path>
  
示例：
  python upload_file.py 01ACED4F5BCE0392664EE0F50B2F32A7 "D:\视频\video.mp4"
  python upload_file.py 01ACED4F5BCE0392664EE0F50B2F32A7 "D:\视频\cover_4x3.jpg"
"""
import json, asyncio, websockets, sys, urllib.request

CDP_PORT = 28800

def get_tabs():
    """获取所有标签页"""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{CDP_PORT}/json", timeout=5) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        print(f"获取标签页失败: {e}")
        return []

def find_tab_by_url(url_pattern: str) -> str:
    """根据 URL 模式查找标签页 ID"""
    tabs = get_tabs()
    for tab in tabs:
        if url_pattern in tab.get('url', ''):
            return tab['id']
    return None

async def cdp_send(ws, method: str, params: dict = None, msg_id: int = 1):
    """发送 CDP 命令并等待响应"""
    await ws.send(json.dumps({
        "id": msg_id,
        "method": method,
        "params": params or {}
    }))
    while True:
        resp = json.loads(await ws.recv())
        if resp.get("id") == msg_id:
            if "error" in resp:
                print(f"CDP 错误: {resp['error']}")
            return resp.get("result", {})

async def get_file_inputs(ws):
    """获取所有 file input 的详细信息"""
    doc = await cdp_send(ws, "DOM.getDocument", {"depth": 1})
    root_id = doc["root"]["nodeId"]
    
    # 获取所有 input 元素
    result = await cdp_send(ws, "DOM.querySelectorAll", {
        "selector": "input",
        "nodeId": root_id
    })
    all_inputs = result.get("nodeIds", [])
    
    # 筛选 file input
    file_inputs = []
    for nid in all_inputs:
        desc = await cdp_send(ws, "DOM.describeNode", {"nodeId": nid})
        node = desc.get("node", {})
        attrs = node.get("attributes", [])
        attrs_dict = dict(zip(attrs[::2], attrs[1::2])) if len(attrs) >= 2 else {}
        
        if attrs_dict.get("type") == "file":
            file_inputs.append({
                "nodeId": nid,
                "accept": attrs_dict.get("accept", ""),
                "name": attrs_dict.get("name", ""),
                "className": attrs_dict.get("class", "")
            })
    
    return file_inputs

async def upload_file(ws, node_id: int, file_path: str):
    """上传文件到指定 input"""
    result = await cdp_send(ws, "DOM.setFileInputFiles", {
        "files": [file_path],
        "nodeId": node_id
    })
    return result == {}  # 空对象表示成功

async def main(tab_id: str = None, file_path: str = None, file_type: str = None):
    """主函数"""
    
    # 如果没有提供 tab_id，尝试自动查找
    if not tab_id:
        # 根据文件类型查找对应平台
        if file_type == "video":
            patterns = ["creator.douyin", "cp.kuaishou", "baijiahao"]
        else:
            patterns = ["creator.douyin", "cp.kuaishou", "baijiahao"]
        
        for pattern in patterns:
            tab_id = find_tab_by_url(pattern)
            if tab_id:
                print(f"找到标签页: {pattern} (ID: {tab_id[:20]}...)")
                break
        
        if not tab_id:
            print("未找到合适的标签页，请手动指定 tab_id")
            return False
    
    # 如果没有提供 file_path，从命令行参数获取
    if not file_path and len(sys.argv) >= 3:
        file_path = sys.argv[2]
    elif not file_path and len(sys.argv) >= 2:
        tab_id = sys.argv[1] if len(sys.argv) >= 2 else None
        file_path = sys.argv[2] if len(sys.argv) >= 3 else None
    
    if not file_path:
        print("用法: python upload_file.py [tab_id] <file_path>")
        print("\n可用标签页:")
        for tab in get_tabs():
            print(f"  {tab['id'][:20]}... | {tab.get('title', '')[:30]} | {tab.get('url', '')[:60]}")
        return False
    
    # 检查文件是否存在
    import os
    if not os.path.exists(file_path):
        print(f"文件不存在: {file_path}")
        return False
    
    file_size = os.path.getsize(file_path) / 1024 / 1024
    print(f"\n上传文件: {file_path}")
    print(f"文件大小: {file_size:.1f} MB")
    
    # 连接 WebSocket
    ws_url = f"ws://127.0.0.1:{CDP_PORT}/devtools/page/{tab_id}"
    print(f"连接 CDP: {ws_url[:50]}...")
    
    try:
        async with websockets.connect(ws_url, ping_interval=None) as ws:
            # 获取所有 file input
            print("\n查找 file input...")
            file_inputs = await get_file_inputs(ws)
            
            if not file_inputs:
                print("未找到 file input!")
                return False
            
            print(f"找到 {len(file_inputs)} 个 file input:")
            for i, inp in enumerate(file_inputs):
                accept_short = inp["accept"][:40] if inp["accept"] else "无限制"
                print(f"  [{i}] nodeId={inp['nodeId']}, accept={accept_short}")
            
            # 根据文件类型选择 input
            is_image = file_path.lower().endswith(('.jpg', '.jpeg', '.png', '.gif'))
            target_input = None
            
            if is_image:
                # 查找接受图片的 input
                for inp in file_inputs:
                    if 'image' in inp["accept"].lower() or 'jpeg' in inp["accept"].lower():
                        target_input = inp
                        print(f"\n选择图片 input: nodeId={inp['nodeId']}")
                        break
            
            if not target_input:
                # 默认使用第一个
                target_input = file_inputs[0]
                print(f"\n使用第一个 input: nodeId={target_input['nodeId']}")
            
            # 上传文件
            print(f"\n开始上传...")
            success = await upload_file(ws, target_input["nodeId"], file_path)
            
            if success:
                print("✅ 上传命令发送成功!")
                
                # 等待并检查上传状态
                print("\n等待上传处理...")
                for i in range(30):
                    await asyncio.sleep(2)
                    try:
                        result = await cdp_send(ws, "Runtime.evaluate", {
                            "expression": """
                            (function() {
                                var hasVideo = !!document.querySelector('video');
                                var imgs = document.querySelectorAll('img');
                                var progress = document.body.innerText.match(/\\d+%/);
                                return JSON.stringify({
                                    hasVideo: hasVideo,
                                    imgCount: imgs.length,
                                    progress: progress ? progress[0] : null
                                });
                            })()
                            """,
                            "returnByValue": True
                        }, msg_id=100+i)
                        
                        val_str = result.get("result", {}).get("value", "{}")
                        try:
                            val = json.loads(val_str)
                        except:
                            val = {}
                        
                        status = f"  {(i+1)*2}s: "
                        if val.get("hasVideo"):
                            status += "✅ 视频已出现"
                        if val.get("progress"):
                            status += f" 进度: {val['progress']}"
                        if val.get("imgCount"):
                            status += f" 图片: {val['imgCount']}"
                        print(status)
                        
                        if val.get("hasVideo") or (is_image and val.get("imgCount", 0) > 0):
                            print("\n✅ 上传完成!")
                            return True
                    except Exception as e:
                        print(f"  检查状态出错: {e}")
                
                print("\n⚠️ 上传可能仍在进行中，请检查浏览器")
                return True
            else:
                print("❌ 上传失败!")
                return False
                
    except Exception as e:
        print(f"连接失败: {e}")
        return False

if __name__ == "__main__":
    if len(sys.argv) == 1:
        # 无参数时，显示帮助和可用标签页
        print(__doc__)
        print("\n当前可用标签页:")
        for tab in get_tabs():
            print(f"  ID: {tab['id']}")
            print(f"    标题: {tab.get('title', '')[:50]}")
            print(f"    URL: {tab.get('url', '')[:80]}")
            print()
    else:
        tab_id = sys.argv[1] if len(sys.argv) >= 2 else None
        file_path = sys.argv[2] if len(sys.argv) >= 3 else None
        asyncio.run(main(tab_id, file_path))
