# -*- coding: utf-8 -*-
"""
填写标题、简介、话题
用法: python fill_form.py <tab_id> "<标题>" "<简介>"
"""
import sys, json, asyncio, websockets, time
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


async def fill_form(tab_id: str, title: str, desc: str):
    ws_url = f'ws://127.0.0.1:{CDP_PORT}/devtools/page/{tab_id}'
    async with websockets.connect(ws_url, ping_interval=None, open_timeout=10, max_size=10*1024*1024) as ws:
        mid = [0]

        # === Step 1: 填写标题 ===
        print('[Step1] 填写标题...')
        safe_title = title.replace("'", "\\'").replace("\n", "\\n")
        r = await jsnr(ws, mid, f"""(function(){{
            var inputs = document.querySelectorAll('input[placeholder]');
            for (var el of inputs) {{
                var ph = el.getAttribute('placeholder');
                if (ph && (ph.includes('标题') || ph.includes('title'))) {{
                    var setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                    setter.call(el, '{safe_title}');
                    el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    el.dispatchEvent(new Event('blur', {{ bubbles: true }}));
                    return 'set:' + el.value.substring(0, 40);
                }}
            }}
            return 'TITLE_NOT_FOUND';
        }})()""")
        result = r.get('result', {}).get('result', {}).get('value', '')
        print(f'  标题设置结果: {result}')

        await asyncio.sleep(2)

        # === Step 2: 填写简介 ===
        print('[Step2] 填写简介...')
        safe_desc = desc.replace("'", "\\'").replace("\n", "\\n")
        r = await jsnr(ws, mid, f"""(function(){{
            // 优先找 contenteditable div（zone-container editor-kit-container）
            var el = document.querySelector('div[contenteditable=true].zone-container') ||
                     document.querySelector('div[contenteditable=true].editor-kit-container') ||
                     document.querySelector('div[contenteditable=true]');
            if (el && el.offsetWidth > 0) {{
                el.focus();
                el.textContent = '{safe_desc}';
                el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                return 'set_desc_OK:' + el.textContent.substring(0, 40);
            }}
            // fallback: textarea
            var tas = document.querySelectorAll('textarea');
            for (var ta of tas) {{
                var ph = ta.getAttribute('placeholder') || '';
                if (ph.includes('简介') || ph.includes('描述') || ph.includes('内容')) {{
                    ta.value = '{safe_desc}';
                    ta.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    ta.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    return 'set_ta_OK';
                }}
            }}
            return 'DESC_NOT_FOUND';
        }})()""")
        result = r.get('result', {}).get('result', {}).get('value', '')
        print(f'  简介设置结果: {result}')

        await asyncio.sleep(2)

        # === Step 3: 验证 ===
        title_val = await js(ws, mid, """(function(){
            var inputs = document.querySelectorAll('input[placeholder]');
            for (var el of inputs) {
                if (el.getAttribute('placeholder') && el.getAttribute('placeholder').includes('标题') && el.offsetWidth > 0) {
                    return el.value;
                }
            }
            return '';
        })()""")
        desc_val = await js(ws, mid, """(function(){
            var el = document.querySelector('div[contenteditable=true].zone-container') ||
                     document.querySelector('div[contenteditable=true]');
            return el ? el.textContent.substring(0, 60) : '';
        })()""")
        print(f'\n[验证]')
        print(f'  标题: {title_val}')
        print(f'  简介: {desc_val}')


def main():
    if len(sys.argv) < 4:
        print(f'用法: python {sys.argv[0]} <tab_id> "<标题>" "<简介>"')
        sys.exit(1)
    tab_id = sys.argv[1]
    title = sys.argv[2]
    desc = sys.argv[3]
    asyncio.run(fill_form(tab_id, title, desc))


if __name__ == '__main__':
    main()