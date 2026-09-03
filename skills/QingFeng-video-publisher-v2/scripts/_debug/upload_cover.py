# -*- coding: utf-8 -*-
"""
封面上传脚本
工作流程：
1. 打开封面对话框（点击「选择封面」）
2. 等待 dialog 出现
3. 通过 DOM.getFileInputFiles 找到 image 类型的 file input
4. 用 DOM.setFileInputFiles 上传封面文件
5. 点击「完成」关闭对话框

用法: python upload_cover.py <tab_id> <4x3封面路径> <3x4封面路径>
"""
import sys, json, asyncio, websockets, time, os
sys.stdout.reconfigure(encoding='utf-8')

CDP_PORT = 9222


async def cdp(ws, mid, method, params=None):
    mid[0] += 1
    await ws.send(json.dumps({'id': mid[0], 'method': method, 'params': params or {}}))
    for _ in range(30):
        r = json.loads(await asyncio.wait_for(ws.recv(), timeout=15))
        if r.get('id') == mid[0]:
            return r
    return {}


async def js(ws, mid, expr):
    r = await cdp(ws, mid, 'Runtime.evaluate', {'expression': expr, 'returnByValue': True})
    return r.get('result', {}).get('result', {}).get('value', '')


async def jsnr(ws, mid, expr):
    await cdp(ws, mid, 'Runtime.evaluate', {'expression': expr, 'returnByValue': False})


async def upload_cover(tab_id: str, cover_4x3: str, cover_3x4: str):
    ws_url = f'ws://127.0.0.1:{CDP_PORT}/devtools/page/{tab_id}'
    async with websockets.connect(ws_url, ping_interval=None, open_timeout=10, max_size=10*1024*1024) as ws:
        mid = [0]

        # === Step 1: 打开封面对话框 ===
        print('[Step1] 打开横封面设置...')
        r = await js(ws, mid, """(function(){
            var els = document.querySelectorAll('[class*=title-wA45Xd], .title-wA45Xd');
            if (els.length > 0) {
                els[0].click();
                return 'clicked_horizontal';
            }
            // fallback: 找文本为"选择封面"的元素
            var all = document.querySelectorAll('div, button, span');
            for (var el of all) {
                var own = '';
                for (var c = el.firstChild; c; c = c.nextSibling) {
                    if (c.nodeType === 3) own += c.textContent;
                }
                if (own.trim() === '选择封面' && el.offsetWidth > 0) {
                    el.click();
                    return 'clicked:' + own.trim();
                }
            }
            return 'NOT_FOUND';
        })()""")
        print(f'  结果: {r}')
        await asyncio.sleep(2)

        # === Step 2: 等待 dialog 出现，枚举所有 file input ===
        print('[Step2] 查找封面对话框 file input...')
        for attempt in range(3):
            await asyncio.sleep(1)
            # 通过 DOM.getFileInputFiles 获取浏览器知道的 file inputs
            r = await cdp(ws, mid, 'DOM.getFileInputFiles')
            inputs = r.get('result', {}).get('files', [])
            print(f'  [attempt {attempt+1}] File inputs: {len(inputs)}')
            for i, inp in enumerate(inputs):
                print(f'    [{i}] nodeId={inp.get("nodeId")} index={inp.get("index")} name={inp.get("name")} type={inp.get("fileType")}')

            # 找 image 类型
            for inp in inputs:
                if 'image' in inp.get('fileType', '').lower() or 'png' in inp.get('fileType', '').lower() or 'jpeg' in inp.get('fileType', '').lower():
                    node_id = inp.get('nodeId')
                    file_idx = inp.get('index')
                    print(f'  ✅ 找到封面 input: nodeId={node_id} index={file_idx}')
                    break
            else:
                node_id = None
                file_idx = None

            if node_id:
                break
        else:
            print('[WARN] 未找到 image file input，尝试 JS 方式...')

        # === Step 3: 用 DOM.getAttributes 获取 nodeId ===
        if not node_id and inputs:
            # 找任意 file input，通过 nodeId 找 accept 属性判断
            print('  尝试通过属性判断...')
            for inp in inputs:
                nid = inp.get('nodeId')
                if nid:
                    attrs = await cdp(ws, mid, 'DOM.getAttributes', {'nodeId': nid})
                    attr_list = attrs.get('result', {}).get('attributes', [])
                    d = {}
                    for j in range(0, len(attr_list), 2):
                        d[attr_list[j]] = attr_list[j+1]
                    print(f'    nodeId={nid}: {d.get("type")} {d.get("accept", "")[:30]}')

        # === Step 4: 上传 4:3 封面 ===
        if node_id and cover_4x3:
            print(f'[Step3] 上传 4:3 封面: {cover_4x3}')
            r = await cdp(ws, mid, 'DOM.setFileInputFiles', {
                'files': [cover_4x3],
                'nodeId': node_id,
                'index': file_idx if file_idx is not None else 0
            })
            print(f'  结果: {r.get("result")}')
            await asyncio.sleep(3)

        # === Step 5: 点击「完成」===
        print('[Step4] 点击完成按钮...')
        r = await js(ws, mid, """(function(){
            var all = document.querySelectorAll('button');
            for (var b of all) {
                var rect = b.getBoundingClientRect();
                var text = b.textContent.trim();
                if (rect.width > 0 && (text === '完成' || text === '确认')) {
                    b.click();
                    return 'clicked:' + text;
                }
            }
            return 'NOT_FOUND';
        })()""")
        print(f'  结果: {r}')
        await asyncio.sleep(2)

        # === Step 6: 上传 3:4 封面 ===
        print('[Step5] 打开竖封面设置...')
        r = await js(ws, mid, """(function(){
            var els = document.querySelectorAll('[class*=title-wA45Xd], .title-wA45Xd');
            if (els.length > 1) {
                els[1].click();
                return 'clicked_vertical';
            }
            return 'NOT_FOUND';
        })()""")
        print(f'  结果: {r}')
        await asyncio.sleep(2)

        # 重新获取 file inputs
        r = await cdp(ws, mid, 'DOM.getFileInputFiles')
        inputs = r.get('result', {}).get('files', [])
        print(f'  File inputs: {len(inputs)}')
        for i, inp in enumerate(inputs):
            print(f'    [{i}] nodeId={inp.get("nodeId")} type={inp.get("fileType")}')

        cover_node_id = None
        cover_idx = None
        for inp in inputs:
            ft = inp.get('fileType', '').lower()
            if 'image' in ft or 'png' in ft or 'jpeg' in ft:
                cover_node_id = inp.get('nodeId')
                cover_idx = inp.get('index')
                break

        if cover_node_id and cover_3x4:
            print(f'[Step6] 上传 3:4 封面: {cover_3x4}')
            r = await cdp(ws, mid, 'DOM.setFileInputFiles', {
                'files': [cover_3x4],
                'nodeId': cover_node_id,
                'index': cover_idx if cover_idx is not None else 0
            })
            print(f'  结果: {r.get("result")}')
            await asyncio.sleep(3)

        # === Step 7: 点击完成 ===
        print('[Step7] 点击完成关闭对话框...')
        r = await js(ws, mid, """(function(){
            var all = document.querySelectorAll('button');
            for (var b of all) {
                var rect = b.getBoundingClientRect();
                var text = b.textContent.trim();
                if (rect.width > 0 && (text === '完成' || text === '确认')) {
                    b.click();
                    return 'clicked:' + text;
                }
            }
            return 'NOT_FOUND';
        })()""")
        print(f'  结果: {r}')
        await asyncio.sleep(2)

        # === 最终验证 ===
        blobs = await js(ws, mid, "(function(){var c=0;document.querySelectorAll('img').forEach(function(el){if(el.src.indexOf('blob')>=0&&el.offsetWidth>30)c++;});return c;})()")
        print(f'\n✅ 封面设置完成！自定义封面 blob 数: {blobs}（>0 表示成功）')


def main():
    if len(sys.argv) < 4:
        print(f'用法: python {sys.argv[0]} <tab_id> <4x3封面路径> <3x4封面路径>')
        sys.exit(1)
    tab_id = sys.argv[1]
    cover_4x3 = sys.argv[2]
    cover_3x4 = sys.argv[3]
    asyncio.run(upload_cover(tab_id, cover_4x3, cover_3x4))


if __name__ == '__main__':
    main()