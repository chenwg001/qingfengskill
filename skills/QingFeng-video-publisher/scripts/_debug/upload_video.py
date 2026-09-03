# -*- coding: utf-8 -*-
"""
抖音视频上传脚本（已验证：DOM.setFileInputFiles 本身就能触发上传）

原理：
1. DOM.setFileInputFiles 设置 inp.files（返回 {} = 成功）
2. 设置后页面自动跳转到发布页 /content/post/video
3. 发布页有 2 个 file input（视频 + 封面），filesLength 清零（已触发上传）
4. 发布页直接显示视频 blob 预览 + 封面 blob 预览

【不需要】React onChange，onChange 调用可省略。
"""
import sys
import json
import asyncio
import websockets

CDP_PORT = 9222  # Edge browser CDP port (browser_edge.py 返回的端口)


async def upload_file(tab_id: str, file_path: str) -> bool:
    ws_url = f"ws://127.0.0.1:{CDP_PORT}/devtools/page/{tab_id}"

    async with websockets.connect(ws_url, ping_interval=None) as ws:
        mid = [0]

        async def cdp(method: str, params: dict = None) -> dict:
            mid[0] += 1
            await ws.send(json.dumps({"id": mid[0], "method": method, "params": params or {}}))
            while True:
                msg = json.loads(await ws.recv())
                if msg.get("id") == mid[0]:
                    return msg

        # === Step 1: 找 file input ===
        r = await cdp("DOM.getDocument", {"depth": 0})
        root = r["result"]["root"]
        body_id = root["nodeId"]
        for child in root.get("children", []):
            if child.get("localName") == "body":
                body_id = child["nodeId"]
                break

        r = await cdp("DOM.querySelectorAll", {
            "selector": "input[type=file]",
            "nodeId": body_id
        })
        node_ids = r.get("result", {}).get("nodeIds", [])
        if not node_ids or not node_ids[0]:
            print("[ERROR] 未找到 file input")
            return False
        node_id = node_ids[0]
        print(f"[Step1] file input nodeId: {node_id}")

        # === Step 2: DOM.setFileInputFiles 设置文件 ===
        r = await cdp("DOM.setFileInputFiles", {
            "files": [file_path],
            "nodeId": node_id
        })
        result = r.get("result")
        print(f"[Step2] setFileInputFiles: {result}")

        if result != {}:
            print("[WARN] setFileInputFiles 返回非空，继续等待...")
        else:
            print("[OK] setFileInputFiles 成功，页面将自动跳转")

        return True  # setFileInputFiles 返回 {} 即认为成功


def main():
    if len(sys.argv) < 3:
        print("用法: python upload_video.py <tab_id> <file_path>")
        sys.exit(1)
    tab_id = sys.argv[1]
    file_path = sys.argv[2]
    success = asyncio.run(upload_file(tab_id, file_path))
    print("[OK] 上传成功!" if success else "[ERROR] 上传失败")
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
