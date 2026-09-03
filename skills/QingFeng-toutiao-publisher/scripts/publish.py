# -*- coding: utf-8 -*-
"""
QingFeng-toutiao-publisher publish.py — 头条号文章自动发布脚本

版本: v34（2026-07-09 验证为稳定版）
核心：封面+正文图片全部走 Step 3 统一交替上传，Step 2b 已移除

用法: python publish.py "<HTML文件路径>" [--tags "#标签1 #标签2 #标签3 #标签4"]
示例: python publish.py "D:/path/to/article/index.html" --tags "#教育 #AI教育 #自适应学习 #教育创新"

注意: 脚本绝不点击发布按钮，最终发布由用户手动操作。
"""
import websocket, json, time, urllib.request, base64, os, re, sys, argparse

# Fix Windows console encoding issue for stdout
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

CDP_PORT = 9222
SCREENSHOT_DIR = r"C:\Users\chenw\.qclaw\workspace"

# ====== CDP 工具函数 ======
def get_cdp():
    resp = urllib.request.urlopen(f"http://127.0.0.1:{CDP_PORT}/json", timeout=3)
    pages = json.loads(resp.read())
    page = None
    for p in pages:
        if p.get('type') == 'page' and 'toutiao' in (p.get('url','')):
            page = p; break
    if not page:
        for p in pages:
            if p.get('type') == 'page': page = p; break
    ws_url = page['webSocketDebuggerUrl']
    print(f"Page: {page.get('title','')} | {page.get('url','')[:60]}")
    ws = websocket.create_connection(ws_url, ping_interval=20)
    print("CDP connected")
    return ws



def navigate_to_editor(ws):
    """自动导航到头条号图文编辑器，等待页面加载完成。"""
    EDITOR_URL = "https://mp.toutiao.com/profile_v4/graphic/publish"
    current_url = js_eval(ws, "window.location.href") or ''
    if 'toutiao.com' in current_url and 'publish' in current_url:
        print("  Already on editor page, skip navigation")
    else:
        print(f"  Navigating to {EDITOR_URL}...")
        cdp_call(ws, 'Page.navigate', {'url': EDITOR_URL})
        for i in range(12):
            time.sleep(2)
            has_editor = js_eval(ws, "!!document.querySelector('.ProseMirror')")
            if has_editor:
                print(f"  Editor ready after {(i+1)*2}s")
                break
        else:
            print("  Warning: ProseMirror not detected, proceeding anyway")
    time.sleep(2)

def cdp_call(ws, method, params={}, timeout=30):
    rid = int(time.time()*1000) % 100000
    ws.send(json.dumps({'id': rid, 'method': method, 'params': params}))
    start = time.time()
    while time.time() - start < timeout:
        try:
            msg = json.loads(ws.recv())
        except:
            time.sleep(0.05)
            continue
        if msg.get('id') == rid:
            return msg
        time.sleep(0.05)
    return {'error': 'timeout'}

def js_eval(ws, expr, timeout=30):
    r = cdp_call(ws, 'Runtime.evaluate', {
        'expression': expr,
        'returnByValue': True,
        'awaitPromise': True
    }, timeout)
    v = r.get('result', {}).get('result', {})
    if isinstance(v, dict) and v.get('type') == 'undefined':
        return None
    return v.get('value') if isinstance(v, dict) else v

def mouse_click(ws, x, y):
    # 关键修复：先发 mouseMoved 模拟真实鼠标移动，触发按钮的 hover/mouseenter 状态，
    # 否则按钮的点击处理器可能尚未挂载（前端懒加载事件绑定），导致点击落空。
    try:
        cdp_call(ws, "Input.dispatchMouseEvent", {
            "type": "mouseMoved", "x": x, "y": y
        }, 5)
    except Exception:
        pass
    time.sleep(0.06)
    cdp_call(ws, "Input.dispatchMouseEvent", {
        "type": "mousePressed", "x": x, "y": y,
        "button": "left", "clickCount": 1
    }, 5)
    time.sleep(0.06)
    cdp_call(ws, "Input.dispatchMouseEvent", {
        "type": "mouseReleased", "x": x, "y": y,
        "button": "left", "clickCount": 1
    }, 5)

def press_key(ws, key, code, vk_code):
    cdp_call(ws, "Input.dispatchKeyEvent", {
        "type": "keyDown", "key": key, "code": code,
        "windowsVirtualKeyCode": vk_code
    }, 5)
    time.sleep(0.05)
    cdp_call(ws, "Input.dispatchKeyEvent", {
        "type": "keyUp", "key": key, "code": code,
        "windowsVirtualKeyCode": vk_code
    }, 5)

def press_esc(ws):
    press_key(ws, "Escape", "Escape", 27)

def take_screenshot(ws, name):
    r = cdp_call(ws, 'Page.captureScreenshot', {'format': 'png'})
    if 'result' in r and 'data' in r['result']:
        path = os.path.join(SCREENSHOT_DIR, name)
        with open(path, 'wb') as f:
            f.write(base64.b64decode(r['result']['data']))
        print(f"  Screenshot saved: {path}")
        return path
    return None


# ====== HTML 解析 ======
def parse_html(html_path):
    html_path = os.path.abspath(html_path)
    base_dir = os.path.dirname(html_path)
    with open(html_path, 'r', encoding='utf-8') as f:
        html = f.read()

    # 清理 &nbsp; 实体（必须在解析阶段处理！）
    html = html.replace('&nbsp;', ' ')
    html = re.sub(r' {2,}', ' ', html)

    # 提取标题 (h1)
    title_m = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.DOTALL)
    title = re.sub(r'<[^>]+>', '', title_m.group(1)).strip() if title_m else ''

    elements = []
    # h2 标题
    for m in re.finditer(r'<h2[^>]*>(.*?)</h2>', html, re.DOTALL):
        t = re.sub(r'<[^>]+>', '', m.group(1)).strip()
        if t:
            elements.append(('title', 2, t, m.start()))
    # h3 标题
    for m in re.finditer(r'<h3[^>]*>(.*?)</h3>', html, re.DOTALL):
        t = re.sub(r'<[^>]+>', '', m.group(1)).strip()
        if t:
            elements.append(('title', 3, t, m.start()))
    # p 段落
    for m in re.finditer(r'<p[^>]*>(.*?)</p>', html, re.DOTALL):
        t = re.sub(r'<[^>]+>', '', m.group(1)).strip()
        if len(t) > 5:
            elements.append(('text', t, m.start()))
    # div.paragraph 段落（部分文章用 div 而非 p）
    for m in re.finditer(r'<div[^>]*class=["\']paragraph["\'][^>]*>(.*?)</div>', html, re.DOTALL):
        t = re.sub(r'<[^>]+>', '', m.group(1)).strip()
        if len(t) > 5:
            elements.append(('text', t, m.start()))
    # img 图片
    for m in re.finditer(r'<img[^>]+\bsrc=["\']([^"\']+)["\'][^>]*(?:\balt=["\']([^"\']*)["\'])?', html, re.I):
        src = m.group(1).strip()
        alt = m.group(2) or ''
        abs_path = os.path.normpath(os.path.join(base_dir, src.replace('/', os.sep)))
        elements.append(('image', abs_path, alt, m.start()))

    # 按原文位置排序（不合并，每个原始标签对应一个独立块）
    elements.sort(key=lambda x: x[-1])
    blocks = [e[:-1] for e in elements]

    # 封面图不再单独处理：保留在 blocks 中作为第一张图，
    # 由 Step 3 的通用图片插入逻辑正常插入（此前单独 Step 2b 插入空编辑器
    # 会导致图片弹窗打不开而卡死，回归到“原来一直正常”的流程）。
    cover_block = None

    return title, blocks, cover_block


# ====== 主流程 ======
def main():
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='Toutiao article publisher')
    parser.add_argument('html_file', help='Path to HTML file')
    parser.add_argument('--tags', default=None, help='Topic tags, e.g. "#教育 #AI教育 #自适应学习 #教育创新"')
    args = parser.parse_args()

    HTML_FILE = args.html_file
    TAGS = args.tags

    if not os.path.exists(HTML_FILE):
        print(f"ERROR: File not found: {HTML_FILE}")
        sys.exit(1)

    ws = get_cdp()

    # 自动导航到头条编辑器（如果当前不在编辑器页面）
    print("[Navigate] Ensuring editor page...")
    navigate_to_editor(ws)

    # 解析 HTML
    print(f"\n[Parsing] {HTML_FILE}")
    result = parse_html(HTML_FILE)
    title = result[0]
    blocks = result[1]
    cover_block = result[2] if len(result) > 2 else None
    print(f"Title: {title}")

    text_cnt = sum(1 for b in blocks if b[0] in ('text', 'title'))
    img_cnt = sum(1 for b in blocks if b[0] == 'image')
    cover_note = ' (cover.jpg will be inserted first)' if cover_block else ''
    print(f"Blocks: {len(blocks)} (text/title={text_cnt}, images={img_cnt}){cover_note}")

    # ---- Step 1: 填入标题 ----
    print("\n[Step 1] Fill title...")
    js_eval(ws, f"""(() => {{
        var ta = document.querySelector('textarea');
        var setter = Object.getOwnPropertyDescriptor(
            window.HTMLTextAreaElement.prototype, 'value'
        ).set;
        setter.call(ta, {json.dumps(title)});
        ta.dispatchEvent(new Event('input', {{bubbles: true}}));
        ta.dispatchEvent(new Event('change', {{bubbles: true}}));
        return ta.value.length;
    }})()""")
    time.sleep(0.5)
    print("  Title filled OK")

    # ---- Step 2: 清空编辑器 ----
    print("\n[Step 2] Clear editor...")
    js_eval(ws, """(() => {
        var editor = document.querySelector('.ProseMirror');
        editor.innerHTML = '<p><br></p>';
        var tas = document.querySelectorAll('textarea');
        for (var i = 0; i < tas.length; i++) {
            if (i > 0) tas[i].value = '';
        }
        return 'cleared';
    })()""")
    time.sleep(0.5)

    # 获取图片按钮坐标
    btn_info = js_eval(ws, """(() => {
        var btn = document.querySelector('.syl-toolbar-tool.image');
        if (!btn) return null;
        var r = btn.getBoundingClientRect();
        return [Math.round(r.x + r.width/2), Math.round(r.y + r.height/2)];
    })()""")
    if not btn_info:
        print("ERROR: Image button not found!")
        ws.close()
        return
    btn_x, btn_y = btn_info[0], btn_info[1]
    print(f"  Image button at ({btn_x}, {btn_y})")

    # 获取 DOM root id
    doc = cdp_call(ws, 'DOM.getDocument')
    root_id = doc['result']['root']['nodeId']

    # 按 ESC 确保没有残留弹窗
    press_esc(ws)
    time.sleep(0.3)

    # 初始化图片计数器（Step 3 共用）
    current_img_count = 0
    success_img = 0
    fail_img = 0

    # ---- Step 3: 按顺序逐块插入（文字+图片交替）----
    print(f"\n[Step 3] Inserting {len(blocks)} blocks in order...")

    for i, block in enumerate(blocks):
        btype = block[0]

        if btype in ('text', 'title'):
            # === 文本块 ===
            if btype == 'title':
                level = block[1]
                text = block[2]
            else:
                level = None
                text = block[1]

            tag_label = f"H{level}" if btype == 'title' else "P"
            preview = text[:45].replace('\n', ' ')
            if len(text) > 45:
                preview += "..."

            # 通过全局变量传递文本到浏览器
            js_eval(ws, "window.__pt = %s; window.__plv = %s" % (
                json.dumps(text), json.dumps(level)))

            result = js_eval(ws, """(() => {
                var editor = document.querySelector('.ProseMirror');
                var el;
                if (window.__plv === 2 || window.__plv === 3) {
                    el = document.createElement('h1');
                    el.className = 'pgc-h-forward-slash';
                    el.textContent = window.__pt;
                } else {
                    el = document.createElement('p');
                    el.textContent = window.__pt;
                }
                editor.appendChild(el);
                editor.dispatchEvent(new Event('input', {bubbles: true}));
                return editor.children.length;
            })()""")

            print(f"  [{i+1:2d}/{len(blocks)}] {tag_label}: {preview}")
            time.sleep(0.05)

        elif btype == 'image':
            # === 图片块 ===
            img_path = block[1]
            img_alt = block[2]
            name = os.path.basename(img_path)
            abs_path = os.path.abspath(img_path).replace('\\', '/')
            size_kb = os.path.getsize(img_path) // 1024

            print(f"  [{i+1:2d}/{len(blocks)}] IMG: {name} ({size_kb}KB)", end='', flush=True)

            # (a) 光标移到编辑器末尾
            js_eval(ws, """(() => {
                var editor = document.querySelector('.ProseMirror');
                editor.focus();
                var lastChild = editor.lastElementChild;
                if (lastChild) {
                    var s = window.getSelection();
                    var r = document.createRange();
                    r.selectNodeContents(lastChild);
                    r.collapse(false);
                    s.removeAllRanges();
                    s.addRange(r);
                }
                return 'cursor_at_end';
            })()""")
            time.sleep(0.15)

            # (b) ESC 确保无残留 dialog/模式（多次）
            press_esc(ws)
            time.sleep(0.3)
            press_esc(ws)
            time.sleep(0.3)

            # (c-1) 滚动页面到顶部，确保工具栏按钮在视口内
            js_eval(ws, "window.scrollTo(0, 0)")
            time.sleep(0.5)

            # (c-2) 重新获取图片按钮坐标（页面内容填充后坐标可能偏移）
            btn_coords = js_eval(ws, """(() => {
                var btn = document.querySelector('.syl-toolbar-tool.image');
                if (!btn) return null;
                var r = btn.getBoundingClientRect();
                // 确保按钮在视口内
                if (r.top < 0 || r.bottom > window.innerHeight) {
                    btn.scrollIntoView(true);
                }
                r = btn.getBoundingClientRect();
                return [Math.round(r.x + r.width/2), Math.round(r.y + r.height/2)];
            })()""")
            if btn_coords:
                btn_x, btn_y = btn_coords[0], btn_coords[1]
            time.sleep(0.5)

            # (c-3) 鼠标点击图片按钮
            mouse_click(ws, btn_x, btn_y)
            time.sleep(4.0)  # 增加等待时间让对话框完全弹出

            # (d) 查找 file input
            sel = cdp_call(ws, 'DOM.querySelectorAll', {
                'nodeId': root_id,
                'selector': 'input[type=file]'
            })
            input_ids = sel['result'].get('nodeIds', [])
            print(f" ({len(input_ids)}inputs)", end='', flush=True)

            uploaded = False

            # 如果对话框没弹出，增加重试逻辑
            retry_count = 0
            while len(input_ids) == 0 and retry_count < 3:
                retry_count += 1
                print(f" NO_DIALOG (retry {retry_count})", end='', flush=True)
                # 多次 ESC 退出所有残留状态
                for _ in range(3):
                    press_esc(ws)
                    time.sleep(0.3)
                # 滚动到顶部并重新获取按钮坐标
                js_eval(ws, "window.scrollTo(0, 0)")
                time.sleep(0.5)
                btn_coords = js_eval(ws, """(() => {
                    var btn = document.querySelector('.syl-toolbar-tool.image');
                    if (!btn) return null;
                    btn.scrollIntoView(true);
                    var r = btn.getBoundingClientRect();
                    return [Math.round(r.x + r.width/2), Math.round(r.y + r.height/2)];
                })()""")
                if btn_coords:
                    btn_x, btn_y = btn_coords[0], btn_coords[1]
                time.sleep(0.5)
                # 鼠标点击图片按钮
                mouse_click(ws, btn_x, btn_y)
                time.sleep(4.0)
                # 再次查找
                sel = cdp_call(ws, 'DOM.querySelectorAll', {
                    'nodeId': root_id,
                    'selector': 'input[type=file]'
                })
                input_ids = sel['result'].get('nodeIds', [])
                print(f" ({len(input_ids)}inputs)", end='', flush=True)

            if len(input_ids) == 0:
                print(" NO_DIALOG", end='', flush=True)
                fail_img += 1
                press_esc(ws)
                time.sleep(0.3)
                continue

            # 头条图片弹窗内含多个 file input，但只需上传到第一个。
            # 遍历所有 input 会把同一张图上传两次 -> 重复图片。
            nid = input_ids[0]
            try:
                cdp_call(ws, 'DOM.setFileInputFiles', {
                    'nodeId': nid,
                    'files': [abs_path]
                }, 10)
                print(' setFile', end='', flush=True)
            except Exception as ex:
                print(f' setFileERR:{ex}', end='', flush=True)
                press_esc(ws); time.sleep(0.3)
                continue

            time.sleep(5)
            # setFile 后图片处于待提交状态，点击「确认」才真正插入
            print(' ->confirm', end='', flush=True)
            confirm_result = js_eval(ws, """(() => {
                var buttons = document.querySelectorAll('button');
                for (var k = 0; k < buttons.length; k++) {
                    var t = (buttons[k].textContent || '').trim();
                    if (t === '\u786E\u5B9A' || t === '\u786E\u8BA4') {
                        buttons[k].click();
                        return 'clicked:' + t;
                    }
                }
                return 'not_found';
            })()""")
            print(f' {confirm_result}', end='', flush=True)
            time.sleep(5)

            cur = js_eval(ws,
                "document.querySelector('.ProseMirror').querySelectorAll('img').length")
            print(f' ->{cur}imgs', end='', flush=True)

            if isinstance(cur, int) and cur > current_img_count:
                current_img_count = cur
                uploaded = True
                success_img += 1
                print(' OK')
            else:
                fail_img += 1
                press_esc(ws)
                print(' FAIL')
                time.sleep(0.3)

            # (e) 上传完成后按 ESC 退出图片描述模式
            time.sleep(1.0)
            press_esc(ws)
            time.sleep(1.0)

    # ---- Step 4: 添加话题标签 ----
    if TAGS:
        print(f"\n[Step 4] Adding topic tags: {TAGS}")
        js_eval(ws, f"window.__tags = {json.dumps(TAGS)}")
        js_eval(ws, """(() => {
            var editor = document.querySelector('.ProseMirror');
            var el = document.createElement('p');
            el.textContent = window.__tags;
            editor.appendChild(el);
            editor.dispatchEvent(new Event('input', {bubbles: true}));
            return editor.children.length;
        })()""")
        time.sleep(0.3)
        print("  Tags added OK")
    else:
        print("\n[Step 4] No tags specified (use --tags to add topic tags)")

    # ---- Step 5: 最终检查 ----
    print("\n" + "=" * 50)
    print("[Step 5 - Final Check]")
    final_title = js_eval(ws, """(() => {
        var t = document.querySelectorAll('textarea')[0];
        return t ? t.value : '?';
    })()""")
    final_text_len = js_eval(ws,
        "document.querySelector('.ProseMirror').textContent.length")
    final_img_count = js_eval(ws,
        "document.querySelector('.ProseMirror').querySelectorAll('img').length")
    final_h1_count = js_eval(ws,
        "document.querySelector('.ProseMirror').querySelectorAll('h1').length")
    final_p_count = js_eval(ws, """(() => {
        var ps = document.querySelectorAll('.ProseMirror > p');
        var cnt = 0;
        for (var i = 0; i < ps.length; i++) {
            if (ps[i].textContent.trim().length > 2) cnt++;
        }
        return cnt;
    })()""")
    final_children = js_eval(ws,
        "document.querySelector('.ProseMirror').children.length")

    print(f"  Title: '{final_title}' ({len(str(final_title))} chars)")
    print(f"  Text content: {final_text_len} chars")
    print(f"  Total children: {final_children}")
    print(f"  H1 titles: {final_h1_count}")
    print(f"  P paragraphs (non-empty): {final_p_count}")
    print(f"  Images: {final_img_count} (success={success_img}, fail={fail_img})")

    # 截图
    ts = time.strftime("%Y%m%d_%H%M%S")
    spath = take_screenshot(ws, f"toutiao_publish_{ts}.png")

    ws.close()
    if TAGS:
        print(f"  Tags: {TAGS}")

    print(f"\n[DONE] All content filled. Screenshot: {spath}")
    print("=" * 50)
    print("[IMPORTANT] Do NOT auto-publish!")
    print("[ACTION REQUIRED] Please manually check the editor and click Publish.")
    print("=" * 50)


if __name__ == '__main__':
    main()
