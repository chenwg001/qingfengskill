# -*- coding: utf-8 -*-
import json, asyncio, websockets

TAB = '2DCA79C609751D22F33F368A55889A23'
URL = 'https://creator.douyin.com/creator-micro/content/post/video?enter_from=publish_page'

async def main():
    ws_url = f"ws://127.0.0.1:28800/devtools/page/{TAB}"
    async with websockets.connect(ws_url, ping_interval=None) as ws:
        mid = [0]
        async def cdp(m, p=None):
            mid[0] += 1
            await ws.send(json.dumps({"id": mid[0], "method": m, "params": p or {}}))
            while True:
                r = json.loads(await ws.recv())
                if r.get("id") == mid[0]: return r
        r = await cdp("Page.navigate", {"url": URL})
        print("导航结果:", r.get("result", {}))

asyncio.run(main())
