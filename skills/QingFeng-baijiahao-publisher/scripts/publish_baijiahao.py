# -*- coding: utf-8 -*-
import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

"""
QingFeng-baijiahao-publisher publish_baijiahao.py — 百家号文章自动发布脚本 v13

v13 核心修复（2026-07-12 教训）：
  批量上传后无需等待图片逐张上传完成，直接 setFileInputFiles 后等 1.5 秒稳定，
  再截图定位确认按钮并点击。上传由前端异步处理，确认后自动插入正文。

v10 核心修复（2026-06-19 诊断结果）：
  标题: 使用 CDP Input.dispatchKeyEvent 带 text: 参数逐字输入
  正文: 使用 UE_V2.instants['ueditorInstant0'].execCommand('insertHTML')
  图片验证: 通过 UEditor body.innerHTML 中的 <img> 标签计数

用法: python publish_baijiahao.py "<HTML文件路径>" [--tags "#标签1"] [--port 9222]
"""
import websocket, json, time, urllib.request, base64, os, re, sys, argparse

CDP_PORT = 9222
SCREENSHOT_DIR = r"C:\Users\chenw\.qclaw\workspace"

# ====== CDP 工具函数 ======
def get_cdp(port):
    resp = urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=5)
    pages = json.loads(resp.read())
    page = None
    for p in pages:
        if p.get('type') == 'page' and 'baijiahao' in (p.get('url','')):
            page = p; break
    if not page:
        for p in pages:
            if p.get('type') == 'page': page = p; break
    ws_url = page['webSocketDebuggerUrl']
    print(f"Page: {page.get('title','')[:50]} | {page.get('url','')[:80]}")
    ws = websocket.create_connection(ws_url, ping_interval=20)
    print("CDP connected")
    return ws

def cdp_call(ws, method, params={}, timeout=30):
    rid = int(time.time()*1000) % 100000
    ws.send(json.dumps({'id': rid, 'method': method, 'params': params}))
    start = time.time()
    while time.time() - start < timeout:
        try:
            msg = json.loads(ws.recv())
            if msg.get('id') == rid:
                return msg
        except:
            time.sleep(0.05)
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
    cdp_call(ws, "Input.dispatchMouseEvent", {
        "type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1
    }, 5)
    time.sleep(0.05)
    cdp_call(ws, "Input.dispatchMouseEvent", {
        "type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1
    }, 5)

def key_event(ws, key, vk_code, key_type='keyDown', text=None):
    params = {
        'type': key_type, 'key': key,
        'windowsVirtualKeyCode': vk_code,
        'code': ''
    }
    if text is not None:
        params['text'] = text
    cdp_call(ws, "Input.dispatchKeyEvent", params, 5)
    time.sleep(0.03)

def press_esc(ws):
    key_event(ws, "Escape", 27, 'keyDown')
    time.sleep(0.03)
    key_event(ws, "Escape", 27, 'keyUp')

def press_enter(ws):
    key_event(ws, "Enter", 13, 'keyDown')
    time.sleep(0.03)
    key_event(ws, "Enter", 13, 'keyUp')
    time.sleep(0.5)

def take_screenshot(ws, name):
    r = cdp_call(ws, 'Page.captureScreenshot', {'format': 'png'})
    if 'result' in r and 'data' in r['result']:
        path = os.path.join(SCREENSHOT_DIR, name)
        with open(path, 'wb') as f:
            f.write(base64.b64decode(r['result']['data']))
        print(f"  Screenshot: {path}")
        return path
    return None


# ====== HTML 解析 ======
def parse_html(html_path):
    html_path = os.path.abspath(html_path)
    base_dir = os.path.dirname(html_path)
    with open(html_path, 'r', encoding='utf-8') as f:
        html = f.read()
    html = html.replace('&nbsp;', ' ')
    html = re.sub(r' {2,}', ' ', html)

    title_m = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.DOTALL)
    title = re.sub(r'<[^>]+>', '', title_m.group(1)).strip() if title_m else ''

    elements = []
    for m in re.finditer(r'<h2[^>]*>(.*?)</h2>', html, re.DOTALL):
        t = re.sub(r'<[^>]+>', '', m.group(1)).strip()
        if t: elements.append(('title', 2, t, m.start()))
    for m in re.finditer(r'<h3[^>]*>(.*?)</h3>', html, re.DOTALL):
        t = re.sub(r'<[^>]+>', '', m.group(1)).strip()
        if t: elements.append(('title', 3, t, m.start()))
    for m in re.finditer(r'<p[^>]*>(.*?)</p>', html, re.DOTALL):
        t = re.sub(r'<[^>]+>', '', m.group(1)).strip()
        if len(t) > 5: elements.append(('text', t, m.start()))
    for m in re.finditer(r'<div[^>]*class=["\']paragraph["\'][^>]*>(.*?)</div>', html, re.DOTALL):
        t = re.sub(r'<[^>]+>', '', m.group(1)).strip()
        if len(t) > 5: elements.append(('text', t, m.start()))
    for m in re.finditer(r'<img[^>]+\bsrc=["\']([^"\']+)["\'][^>]*(?:\balt=["\']([^"\']*)["\'])?', html, re.I):
        src = m.group(1).strip()
        abs_path = os.path.normpath(os.path.join(base_dir, src.replace('/', os.sep)))
        elements.append(('image', abs_path, m.group(2) or '', m.start()))

    elements.sort(key=lambda x: x[-1])
    return title, [e[:-1] for e in elements]


# ====== 获取 UEditor 实例 ======
def get_ueditor(ws):
    """获取 UE_V2.instants['ueditorInstant0'] 实例（带重试）"""
    for attempt in range(5):
        r = js_eval(ws, """
            (function() {
                if (typeof UE_V2 === 'undefined') return 'NO_UE_V2';
                var inst = UE_V2.instants['ueditorInstant0'];
                if (!inst) return 'NO_INSTANCE';
                try {
                    var txt = inst.getContentTxt();
                    return 'OK:' + txt.length;
                } catch(e) { return 'ERR:' + e.message; }
            })()
        """, timeout=10)
        if r and r.startswith('OK:'):
            print(f"  UEditor ready (txt={r[3:]})", flush=True)
            return True
        print(f"  UEditor attempt {attempt+1}: {r}", flush=True)
        time.sleep(2)
    return False


# ====== 标题填写 v10（CDP 键盘事件逐字输入）======
def fill_title_v10(ws, title):
    """
    百家号标题框是 Lexical 编辑器。
    策略：用 CDP Input.dispatchKeyEvent 带 text: 参数逐字输入（已验证有效）。
    """
    # Step 1: 聚焦并清空现有标题（Ctrl+A 全选 + Delete 删除，确保 Lexical 状态同步清除）
    js_eval(ws, """
        (function() {
            var el = document.querySelector('.input-box [contenteditable]');
            if (el) el.focus();
        })()
    """)
    time.sleep(0.3)

    # Ctrl+A 全选
    cdp_call(ws, 'Input.dispatchKeyEvent', {
        'type': 'keyDown', 'key': 'a', 'code': 'KeyA',
        'windowsVirtualKeyCode': 65, 'modifiers': 2
    })
    cdp_call(ws, 'Input.dispatchKeyEvent', {
        'type': 'keyUp', 'key': 'a', 'code': 'KeyA',
        'windowsVirtualKeyCode': 65, 'modifiers': 2
    })
    time.sleep(0.2)

    # Delete 删除选中内容
    cdp_call(ws, 'Input.dispatchKeyEvent', {
        'type': 'keyDown', 'key': 'Backspace', 'code': 'Backspace',
        'windowsVirtualKeyCode': 8
    })
    cdp_call(ws, 'Input.dispatchKeyEvent', {
        'type': 'keyUp', 'key': 'Backspace', 'code': 'Backspace',
        'windowsVirtualKeyCode': 8
    })
    time.sleep(0.5)

    # 双重保险：再清一次 innerHTML
    js_eval(ws, """
        (function() {
            var el = document.querySelector('.input-box [contenteditable]');
            if (!el) return;
            el.innerHTML = '<p dir="auto"><br></p>';
            el.dispatchEvent(new InputEvent('input', {bubbles: true, cancelable: true}));
        })()
    """)
    time.sleep(0.5)

    # Step 3: 逐字输入
    print(f"  Typing title ({len(title)} chars): {title[:20]}...", flush=True)
    for ch in title:
        # 确定 vk_code
        if 'a' <= ch <= 'z':
            vk = ord(ch) - ord('a') + 65; code = 'Key' + ch.upper()
        elif 'A' <= ch <= 'Z':
            vk = ord(ch); code = 'Key' + ch
        elif '0' <= ch <= '9':
            vk = ord(ch); code = 'Digit' + ch
        elif ch == ' ':
            vk = 32; code = 'Space'
        elif ch == '.':
            vk = 190; code = 'Period'
        elif ch == ',':
            vk = 188; code = 'Comma'
        elif ch == '?':
            vk = 191; code = 'Slash'
        elif ch == ':':
            vk = 186; code = 'Semicolon'
        else:
            vk = 0; code = ''

        key_event(ws, ch, vk, 'keyDown', text=ch)
        time.sleep(0.01)
        key_event(ws, ch, vk, 'keyUp', text=ch)
        time.sleep(0.02)

    time.sleep(1)

    # Step 4: 验证
    r = js_eval(ws, """
        (function() {
            var el = document.querySelector('.input-box [contenteditable]');
            if (!el) return 'NO_EL';
            var span = el.querySelector('span[data-lexical-text]');
            return span ? span.textContent : el.textContent.trim();
        })()
    """)
    print(f"  Title verify: [{r}]", flush=True)
    return r


# ====== 清空 UEditor 正文 ======
def clear_ueditor(ws):
    r = js_eval(ws, """
        (function() {
            try {
                var ed = UE_V2.instants['ueditorInstant0'];
                if (!ed) return 'NO_INST';
                ed.focus();
                ed.execCommand('selectAll');
                ed.execCommand('delete');
                return 'cleared:' + ed.getContentTxt().length;
            } catch(e) { return 'error:' + e.message; }
        })()
    """)
    return r


# ====== 向 UEditor 注入内容 ======
def inject_to_ueditor(ws, html):
    """向 UEditor 注入 HTML 内容（全选替换），返回注入后的文本长度"""
    html_json = json.dumps(html)
    r = js_eval(ws, f"""
        (function() {{
            try {{
                var ed = UE_V2.instants['ueditorInstant0'];
                if (!ed) return 'NO_INST';
                ed.focus();
                ed.execCommand('selectAll');
                ed.execCommand('insertHTML', {html_json});
                ed.fireEvent('contentchange');
                return 'ok:txtLen=' + ed.getContentTxt().length + ':htmlLen=' + ed.getContent().length;
            }} catch(e) {{ return 'error:' + e.message; }}
        }})()
    """, timeout=15)
    return r


def append_to_ueditor(ws, html):
    """向 UEditor 末尾追加 HTML 内容（不清空已有内容），返回注入后的文本长度"""
    html_json = json.dumps(html)
    r = js_eval(ws, f"""
        (function() {{
            try {{
                var ed = UE_V2.instants['ueditorInstant0'];
                if (!ed) return 'NO_INST';
                ed.focus();
                // 将光标移到文档末尾
                var body = ed.body || (ed.document && ed.document.body) || (ed.iframe && ed.iframe.contentDocument.body);
                var range = (ed.document || (ed.iframe && ed.iframe.contentDocument) || document).createRange();
                range.selectNodeContents(body);
                range.collapse(false);
                var sel = (ed.document || (ed.iframe && ed.iframe.contentDocument) || document).getSelection();
                if (sel) {{ sel.removeAllRanges(); sel.addRange(range); }}
                ed.execCommand('insertHTML', {html_json});
                ed.fireEvent('contentchange');
                return 'ok:txtLen=' + ed.getContentTxt().length + ':htmlLen=' + ed.getContent().length;
            }} catch(e) {{ return 'error:' + e.message; }}
        }})()
    """, timeout=15)
    return r


# ====== 获取正文文本长度（UEditor）=====
def get_body_txtlen(ws):
    r = js_eval(ws, """
        (function() {
            try {
                var ed = UE_V2.instants['ueditorInstant0'];
                if (!ed) return -1;
                return ed.getContentTxt().length;
            } catch(e) { return -2; }
        })()
    """)
    return r if isinstance(r, int) else -1


# ====== 光标定位（图片交替插入核心）=====
def position_cursor(ws, para_idx):
    """
    将 UEditor 光标定位到第 para_idx 个段落后（setStartAfter）。
    段落索引基于 ed.body.querySelectorAll('p, h1, h2, h3')
    para_idx = -1 时定位到文档开头。
    """
    js = f"""
    (function() {{
        try {{
            var ed = UE_V2.instants['ueditorInstant0'];
            if (!ed) return 'NO_EDITOR';
            ed.focus();
            var iframeDoc = ed.document || (ed.iframe && ed.iframe.contentDocument) || document;
            var body = iframeDoc.body || ed.body;
            var paras = body.querySelectorAll('p, h1, h2, h3, h4, h5, h6');
            var range = iframeDoc.createRange ? iframeDoc.createRange() : document.createRange();
            if ({para_idx} < 0) {{
                range.setStart(body, 0);
            }} else if ({para_idx} >= paras.length) {{
                return 'IDX_OOB:' + {para_idx} + '/' + paras.length;
            }} else {{
                range.setStartAfter(paras[{para_idx}]);
            }}
            range.collapse(true);
            var sel = iframeDoc.getSelection ? iframeDoc.getSelection() : (document.getSelection ? document.getSelection() : null);
            if (sel) {{
                sel.removeAllRanges();
                sel.addRange(range);
            }}
            if (ed.selection) {{
                ed.selection.range = range;
                ed.fireEvent('selectionchange');
            }}
            return 'OK:cursor@' + {para_idx};
        }} catch(e) {{
            return 'ERR:' + e.message;
        }}
    }})()
    """
    r = js_eval(ws, js, timeout=10)
    if not (r and r.startswith('OK:')):
        print(f"  Cursor: {r}", flush=True)
        return False
    # 验证光标位置
    verify = js_eval(ws, """
        (function() {
            try {
                var ed = UE_V2.instants['ueditorInstant0'];
                if (!ed) return 'NO_EDITOR';
                var range = ed.selection.getRange();
                if (!range) return 'NO_RANGE';
                var node = range.startContainer;
                while (node && node.nodeType === 3) node = node.parentNode;
                var para = node;
                while (para && para.nodeName !== 'P' && para.nodeName !== 'H1' && para.nodeName !== 'H2' && para.nodeName !== 'H3') {
                    para = para.parentElement;
                }
                return para ? para.nodeName + ':' + (para.textContent || '').slice(0, 30) : 'unknown';
            } catch(e) { return 'ERR:' + e.message; }
        })()
    """, timeout=5)
    print(f"  Cursor: {r} | verify: {verify}", flush=True)
    return True


# ====== 获取正文图片数量（UEditor）=====
def get_body_imgcount(ws):
    r = js_eval(ws, """
        (function() {
            try {
                var ed = UE_V2.instants['ueditorInstant0'];
                if (!ed) return -1;
                var html = ed.getContent();
                return (html.match(/<img /g) || []).length;
            } catch(e) { return -1; }
        })()
    """)
    return r if isinstance(r, int) else -1


# ====== 关闭质量检测弹窗 ======
def close_quality_popup(ws):
    """关闭质量检测弹窗，但不要误关图片上传弹窗"""
    for _ in range(3):
        r = js_eval(ws, """
            (function() {
                // 不要关闭 cheetah-ui-pro-image-modal（图片上传弹窗）
                var selectors = [
                    '.quality-check-popup .close-btn', '.quality-check-popup .close',
                    '.ai-quality-modal .close', '[class*=quality] [class*=close]'
                ];
                for (var s of selectors) {
                    var el = document.querySelector(s);
                    if (el && el.offsetParent !== null) { el.click(); return 'closed:' + s; }
                }
                return 'none';
            })()
        """)
        if r and r != 'none':
            print(f"  popup: {r}", flush=True)
            time.sleep(0.5)
        else:
            break


# ====== 上传单张图片（v10: UEditor 验证 + 光标定位）=====
def upload_image_v10(ws, img_path, get_root_id, target_para_idx=None):
    """v12: 适配百家号新版 cheetah-modal 图片上传弹窗"""
    abs_path = os.path.abspath(img_path).replace('\\', '/')
    name = os.path.basename(img_path)

    close_quality_popup(ws)
    time.sleep(0.3)

    # 定位光标到目标段落后（在打开图片弹窗之前）
    if target_para_idx is not None:
        print(f'  [cursor]->para[{target_para_idx}]', end='', flush=True)
        ok_cur = position_cursor(ws, target_para_idx)
        if ok_cur:
            print(' OK', end='', flush=True)
        else:
            print(' FAIL', end='', flush=True)
        time.sleep(2)

    # 激活编辑器后把焦点移回主文档（position_cursor 会把焦点留在 iframe 内）
    # 不移回主文档会导致图片按钮点击无法触发弹窗
    defocus_r = js_eval(ws, """
        (function() {
            // 先 blur iframe 内容
            var iframe = document.getElementById('ueditor_0');
            if (iframe && iframe.contentWindow) {
                try { iframe.contentWindow.blur(); } catch(e) {}
            }
            // 让主文档获得焦点
            document.body.focus();
            // 或者点击工具栏区域
            var toolbar = document.querySelector('.edui-toolbar');
            if (toolbar) {
                toolbar.click();
            }
            return 'done';
        })()
    """)
    print(f' defocus({defocus_r})', end='', flush=True)
    time.sleep(0.5)

    # 找图片按钮并点击
    btn_coord = js_eval(ws, """
        (function() {
            var btn = document.querySelector('.edui-for-insertimage');
            if (!btn) return null;
            var r = btn.getBoundingClientRect();
            return [Math.round(r.x + r.width/2), Math.round(r.y + r.height/2)];
        })()
    """)
    if not btn_coord or len(btn_coord) < 2:
        print(" NO_BTN", end='', flush=True)
        return False
    btn_x, btn_y = btn_coord[0], btn_coord[1]

    mouse_click(ws, btn_x, btn_y)
    print(f" click({btn_x},{btn_y})", end='', flush=True)
    time.sleep(2)

    # 关闭可能的质量检测弹窗
    close_quality_popup(ws)
    time.sleep(0.5)

    # 等待 cheetah-modal 图片弹窗出现（新版弹窗，不是 .edui-dialog）
    dialog_found = False
    for w in range(20):
        time.sleep(0.5)
        dlg = js_eval(ws, """
            (function() {
                // 新版弹窗: cheetah-modal
                var cm = document.querySelector('.cheetah-ui-pro-image-modal-local-upload');
                if (cm && cm.offsetHeight > 50) return 'cheetah';
                // 旧版弹窗: edui-dialog
                var ed = document.querySelector('.edui-dialog');
                if (ed && ed.offsetHeight > 50) return 'edui';
                return 'none';
            })()
        """)
        if dlg in ('cheetah', 'edui'):
            dialog_found = True
            print(f' dlg={dlg}', end='', flush=True)
            break
        elif w % 4 == 3:
            # 重试点击
            mouse_click(ws, btn_x, btn_y)
            time.sleep(1)

    if not dialog_found:
        diag = js_eval(ws, """
            (function() {
                var all = document.querySelectorAll('[class*="modal"],[class*="dialog"]');
                var info = [];
                for (var i=0;i<all.length;i++) {
                    if (all[i].offsetHeight > 50) info.push(all[i].className.substring(0,50)+'|h='+all[i].offsetHeight);
                }
                return info.join(' || ') || 'no-visible-modal';
            })()
        """)
        print(f" NO_DIALOG [diag:{diag[:100]}]", end='', flush=True)
        press_esc(ws)
        return False

    time.sleep(1)

    # 找 file input 并设置文件
    root_id = get_root_id()
    pre_count = get_body_imgcount(ws)
    print(f" pre={pre_count}", end='', flush=True)

    # 检测弹窗类型，使用对应选择器
    file_set = False
    # 新版弹窗: cheetah-modal 内的 input[name=media]
    # 旧版弹窗: .edui-dialog input[type=file]
    for sel_str in ['.cheetah-ui-pro-image-modal-local-upload input[type=file][name="media"]',
                    '.cheetah-modal input[type=file]',
                    '.edui-dialog input[type=file]',
                    'input[type=file]']:
        sel = cdp_call(ws, 'DOM.querySelectorAll', {'nodeId': root_id, 'selector': sel_str})
        ids = sel.get('result', {}).get('nodeIds', [])
        if not ids:
            continue
        for nid in ids:
            desc_r = cdp_call(ws, 'DOM.describeNode', {'nodeId': nid})
            node = desc_r.get('result', {}).get('node', {})
            backend_id = node.get('backendNodeId')
            attrs = node.get('attributes', [])
            accept_val = ''
            for i in range(0, len(attrs), 2):
                if attrs[i] == 'accept':
                    accept_val = attrs[i+1] if i+1 < len(attrs) else ''
                    break
            if accept_val and 'image' not in accept_val:
                continue
            if not backend_id:
                continue
            try:
                cdp_call(ws, 'DOM.setFileInputFiles', {'backendNodeId': backend_id, 'files': [abs_path]}, 10)
                file_set = True
                print(f" set({backend_id})", end='', flush=True)
                break
            except Exception as ex:
                print(f" setErr({ex})", end='', flush=True)
                continue
        if file_set:
            break

    if not file_set:
        print(" NO_FILE_INPUT", end='', flush=True)
        press_esc(ws)
        return False

    # 等待上传处理（新版弹窗自动上传，无需点确认按钮）
    print(" uploading", end='', flush=True)
    time.sleep(5)

    # 检查弹窗内是否出现已上传的图片预览
    preview_check = js_eval(ws, """
        (function() {
            var modal = document.querySelector('.cheetah-ui-pro-image-modal-local-upload');
            if (!modal) return 'no_modal';
            var imgs = modal.querySelectorAll('img');
            var uploaded = [];
            for (var i=0;i<imgs.length;i++) {
                var src = imgs[i].src || '';
                if (src.length > 10) uploaded.push(src.substring(0,60));
            }
            // 找确认/插入按钮
            var btns = modal.querySelectorAll('button');
            var confirmBtns = [];
            for (var i=0;i<btns.length;i++) {
                var t = (btns[i].textContent||'').trim();
                if (t) confirmBtns.push(t);
            }
            return JSON.stringify({previewCount: uploaded.length, buttons: confirmBtns});
        })()
    """)
    print(f" preview={preview_check}", end='', flush=True)

    # 查找并点击确认/插入按钮（新版弹窗可能在上传完成后显示）
    confirm_clicked = False
    confirm_btn = js_eval(ws, """
        (function() {
            var btns = document.querySelectorAll('.cheetah-modal button, .cheetah-ui-pro-image-modal-local-upload button');
            for (var i=0;i<btns.length;i++) {
                var t = (btns[i].textContent||'').trim();
                if (t === '插入' || t === '确认' || t === '确定' || t === '完成') {
                    var r = btns[i].getBoundingClientRect();
                    return JSON.stringify({x:Math.round(r.x+r.width/2), y:Math.round(r.y+r.height/2), text:t});
                }
            }
            return null;
        })()
    """)
    if confirm_btn:
        try:
            info = json.loads(confirm_btn) if isinstance(confirm_btn, str) else confirm_btn
            if info and isinstance(info, dict):
                cx, cy = info.get('x',0), info.get('y',0)
                if cx and cy:
                    mouse_click(ws, cx, cy)
                    confirm_clicked = True
                    print(f" confirm({info.get('text','')})", end='', flush=True)
        except:
            pass

    # 等待图片插入正文
    time.sleep(3)

    # 检查正文图片数量是否增加
    uploaded = False
    for w2 in range(20):
        time.sleep(1)
        cur = get_body_imgcount(ws)
        if isinstance(cur, int) and cur > pre_count:
            uploaded = True
            print(f" OK(imgs={cur})", end='', flush=True)
            break
        print(f" wait{w2+1}({cur})", end='', flush=True)

    if not uploaded:
        # 尝试关闭弹窗后再检查（弹窗关闭后图片可能才出现在正文中）
        press_esc(ws)
        time.sleep(2)
        cur = get_body_imgcount(ws)
        if isinstance(cur, int) and cur > pre_count:
            uploaded = True
            print(f" late_OK(imgs={cur})", end='', flush=True)

    if not uploaded:
        print(" IMG_NOT_INSERTED", end='', flush=True)

    press_esc(ws)
    time.sleep(1)  # 等待弹窗完全关闭
    return uploaded


# ====== 主流程 ======
def main():
    parser = argparse.ArgumentParser(description='Baijiahao publisher v10')
    parser.add_argument('html_file', help='Path to HTML file')
    parser.add_argument('--tags', default=None, help='Topic tags')
    parser.add_argument('--port', type=int, default=9222, help='CDP port')
    args = parser.parse_args()

    HTML_FILE = args.html_file
    TAGS = args.tags
    CDP_PORT = args.port

    if not os.path.exists(HTML_FILE):
        print(f"ERROR: File not found: {HTML_FILE}")
        sys.exit(1)

    ws = get_cdp(CDP_PORT)

    print(f"\n[Parsing] {HTML_FILE}")
    title, blocks = parse_html(HTML_FILE)
    print(f"Title: {title}")
    print(f"Total blocks: {len(blocks)}")

    # 分离文本块和图片块
    text_blocks = []
    img_blocks = []
    text_block_count = 0
    for i, block in enumerate(blocks):
        if block[0] in ('text', 'title'):
            text_blocks.append(block)
            text_block_count += 1
        elif block[0] == 'image':
            img_blocks.append((text_block_count, block[1], os.path.basename(block[1])))

    # 如果第一张图片是 cover.jpg，将其 after_idx 改为 1（正文第一段后）
    # 因为百家号正文开头不能放图，cover 需要插在 para[1] 后面
    if img_blocks and img_blocks[0][2].lower().startswith('cover'):
        old_idx = img_blocks[0][0]
        img_blocks[0] = (1, img_blocks[0][1], img_blocks[0][2])
        print(f"  Cover: moved from after_idx={old_idx} to after_idx=1 for {img_blocks[0][2]}")

    print(f"Text blocks: {len(text_blocks)}, Images: {len(img_blocks)}")

    def get_root_id():
        doc = cdp_call(ws, 'DOM.getDocument')
        return doc['result']['root']['nodeId']

    # Step 1: 确认在编辑器页面
    print("\n[Step 1] Editor page check...")
    url = js_eval(ws, "window.location.href") or ''
    if 'baijiahao' not in url or 'edit' not in url:
        cdp_call(ws, 'Page.navigate', {'url': 'https://baijiahao.baidu.com/builder/rc/edit?type=news'})
        time.sleep(5)
    else:
        print(f"  Already on editor")
    take_screenshot(ws, "bjh_v10_01_editor.png")

    # Step 2: 等待 UEditor 初始化
    print("\n[Step 2] Wait for UEditor...")
    if not get_ueditor(ws):
        print("  WARNING: UEditor not ready, continuing anyway...")

    # Step 3: 填标题
    print("\n[Step 3] Fill title (v10 keyboard events)...")
    title_result = fill_title_v10(ws, title)
    if title_result and title in title_result:
        print("  Title OK")
    else:
        print(f"  ! Title may not match. Expected: [{title}]")
    time.sleep(1)

    # Step 4: 清空正文
    print("\n[Step 4] Clear body...")
    r = clear_ueditor(ws)
    print(f"  Clear: {r}")
    time.sleep(0.5)

    # Step 5: 注入正文
    print(f"\n[Step 5] Inject TEXT ({len(text_blocks)} blocks)...")
    text_html_parts = []
    for block in text_blocks:
        btype = block[0]
        if btype == 'title':
            level, txt = block[1], block[2]
            text_html_parts.append(f'<h{level}>{txt.replace(chr(10), "<br>")}</h{level}>')
        elif btype == 'text':
            text = block[1]
            text_html_parts.append(f'<p>{text.replace(chr(10), "<br>")}</p>')

    full_text_html = ''.join(text_html_parts)
    print(f"  HTML length: {len(full_text_html)} chars")

    inject_r = inject_to_ueditor(ws, full_text_html)
    print(f"  Inject: {inject_r}")
    time.sleep(3)

    # 稳定性检查
    stable_len = None
    for attempt in range(3):
        time.sleep(2)
        cur_len = get_body_txtlen(ws)
        print(f"  Stable check {attempt+1}: txtLen={cur_len}", flush=True)
        if isinstance(cur_len, int) and cur_len > 50:
            stable_len = cur_len
            break

    if not stable_len or stable_len < 50:
        print("  ! Text may not have stuck, retrying...")
        time.sleep(2)
        inject_r2 = inject_to_ueditor(ws, full_text_html)
        print(f"  Retry: {inject_r2}")
        time.sleep(3)

    take_screenshot(ws, "bjh_v10_05_text.png")

    # Step 6: 一次性上传所有图片（批量方案）
    success_img = 0
    fail_img = 0
    if img_blocks:
        print(f"\n[Step 6] Upload {len(img_blocks)} images (batch mode)...")
        
        # 收集所有图片路径
        all_img_paths = []
        for img_idx, (after_idx, img_path, img_name) in enumerate(img_blocks):
            abs_path = os.path.abspath(img_path).replace('\\', '/')
            all_img_paths.append(abs_path)
            sz = os.path.getsize(img_path) // 1024
            print(f"  [{img_idx+1}/{len(img_blocks)}] {img_name} ({sz}KB)")
        
        # 点击图片按钮打开弹窗
        btn_coord = js_eval(ws, """
            (function() {
                var btn = document.querySelector('.edui-for-insertimage');
                if (!btn) return null;
                var r = btn.getBoundingClientRect();
                return [Math.round(r.x + r.width/2), Math.round(r.y + r.height/2)];
            })()
        """)
        if btn_coord and len(btn_coord) >= 2:
            mouse_click(ws, btn_coord[0], btn_coord[1])
            print(f"  Clicked button at ({btn_coord[0]},{btn_coord[1]})")
            time.sleep(2)
            
            # 关闭质量检测弹窗
            close_quality_popup(ws)
            time.sleep(0.5)
            
            # 等待弹窗出现
            dialog_found = False
            for w in range(20):
                time.sleep(0.5)
                dlg = js_eval(ws, """
                    (function() {
                        var cm = document.querySelector('.cheetah-ui-pro-image-modal-local-upload');
                        if (cm && cm.offsetHeight > 50) return 'cheetah';
                        var ed = document.querySelector('.edui-dialog');
                        if (ed && ed.offsetHeight > 50) return 'edui';
                        return 'none';
                    })()
                """)
                if dlg in ('cheetah', 'edui'):
                    dialog_found = True
                    print(f"  Dialog found: {dlg}")
                    break
            
            if dialog_found:
                # 找 file input
                doc_r = cdp_call(ws, 'DOM.getDocument', {'depth': -1})
                root_id = doc_r['result']['root']['nodeId']
                pre_count = get_body_imgcount(ws)
                print(f"  Pre img count: {pre_count}")
                
                file_set = False
                for sel_str in ['input[type=file][name="media"]', '.cheetah-modal input[type=file]', 'input[type=file][accept*="image"]', 'input[type=file]']:
                    sel = cdp_call(ws, 'DOM.querySelectorAll', {'nodeId': root_id, 'selector': sel_str})
                    ids = sel.get('result', {}).get('nodeIds', [])
                    if not ids:
                        continue
                    desc_r = cdp_call(ws, 'DOM.describeNode', {'nodeId': ids[0]})
                    node = desc_r.get('result', {}).get('node', {})
                    backend_id = node.get('backendNodeId')
                    if not backend_id:
                        continue
                    try:
                        cdp_call(ws, 'DOM.setFileInputFiles', {'backendNodeId': backend_id, 'files': all_img_paths}, 15)
                        file_set = True
                        print(f"  Set {len(all_img_paths)} files (backend={backend_id})")
                        break
                    except Exception as ex:
                        print(f"  setErr({ex})")
                        continue
                
                if not file_set:
                    print("  NO_FILE_INPUT")
                else:
                    # 批量上传后无需等待——上传异步进行，直接点确认即可
                    # 等 1.5 秒让弹窗状态稳定（文件已入队，上传在后台继续）
                    print(f"  Files set, waiting 1.5s for modal to stabilize...")
                    time.sleep(1.5)
                    
                    # === 截图确认弹窗状态：先截图看确认按钮在哪里，再点击 ===
                    print('  Taking screenshot to locate confirm button...')
                    ts2 = time.strftime("%H%M%S")
                    modal_ss_path = take_screenshot(ws, f"bjh_v13_confirm_{ts2}.png")
                    
                    # === 确认按钮：直接定位（弹窗已稳定，无需轮询等待）===
                    confirm_btn = None
                    # 策略1: 通用查找
                    confirm_json = js_eval(ws, """
                        (function(){
                            var btns = document.querySelectorAll('button, [role=button], .cheetah-btn, span, div');
                            var found = [];
                            for (var i=0; i<btns.length; i++) {
                                var txt = (btns[i].textContent || '').trim();
                                if (txt === '确认' || txt === '确定' || txt === '插入') {
                                    var rect = btns[i].getBoundingClientRect();
                                    if (rect.width > 0 && rect.height > 0 && rect.x > 500 && rect.y > 400) {
                                        found.push({tag: btns[i].tagName, text: txt, x: Math.round(rect.x+rect.width/2), y: Math.round(rect.y+rect.height/2)});
                                    }
                                }
                            }
                            return JSON.stringify(found);
                        })()
                    """)
                    if confirm_json and confirm_json not in ('null', '[]', None):
                        try:
                            btns = json.loads(confirm_json)
                            if btns and len(btns) > 0:
                                confirm_btn = btns[0]
                                print(f'  Confirm button found (strategy 1): {confirm_btn}')
                        except:
                            pass
                    
                    # 策略2: 直接在 cheetah-modal 内找 button
                    if not confirm_btn:
                        fallback = js_eval(ws, """
                            (function(){
                                var modal = document.querySelector('.cheetah-ui-pro-image-modal-local-upload');
                                if (!modal) return null;
                                var btns = modal.querySelectorAll('button');
                                for (var i=0; i<btns.length; i++) {
                                    var txt = (btns[i].textContent || '').trim();
                                    if (txt === '确认' || txt === '确定') {
                                        var rect = btns[i].getBoundingClientRect();
                                        return JSON.stringify({x: Math.round(rect.x+rect.width/2), y: Math.round(rect.y+rect.height/2), text: txt});
                                    }
                                }
                                return null;
                            })()
                        """)
                        if fallback and fallback != 'null':
                            confirm_btn = json.loads(fallback)
                            print(f'  Confirm button found (strategy 2): {confirm_btn}')
                    
                    # 策略3: 坐标备用（弹窗右下角约 1076,718）
                    if not confirm_btn:
                        print('  ⚠️ Confirm button not detected, using coordinate fallback (1076,718)')
                        confirm_btn = {'x': 1076, 'y': 718, 'text': '确认(坐标)'}
                    
                    # 点击确认按钮（最多重试3次）
                    for click_try in range(3):
                        cx, cy = confirm_btn.get('x', 0), confirm_btn.get('y', 0)
                        if cx and cy:
                            mouse_click(ws, cx, cy)
                            print(f'  Clicked confirm ({confirm_btn.get("text","")}) at ({cx},{cy}) try={click_try+1}')
                            time.sleep(1)
                            still_open = js_eval(ws, """
                                (function() {
                                    var m = document.querySelector('.cheetah-ui-pro-image-modal-local-upload');
                                    return m && m.offsetHeight > 50 ? 'yes' : 'no';
                                })()
                            """)
                            if still_open == 'no':
                                print('  Confirm dialog closed')
                                break
                            else:
                                print('  Dialog still open, retrying...')
                    
                    # 等待图片插入正文（动态轮询，上传完成后才出现在正文中）
                    print('  Waiting for images to insert into body...')
                    post_count = pre_count
                    for insert_wait in range(20):  # 最多等待20秒
                        time.sleep(1)
                        post_count = get_body_imgcount(ws)
                        if isinstance(post_count, int) and post_count > pre_count:
                            print(f'  ✅ {post_count - pre_count} images inserted ({insert_wait+1}s)')
                            break
                        else:
                            print(f'  ⏳ Waiting... ({insert_wait+1}/20)')
                    
                    if post_count == pre_count:
                        print('  ⚠️ Timeout: images may not have been inserted')
                    
                    success_img = post_count - pre_count if isinstance(post_count, int) and isinstance(pre_count, int) else 0
                    fail_img = len(all_img_paths) - success_img
                    print(f"  Post img count: {post_count}, new: {success_img}, failed: {fail_img}")
                    
                    # Step 6.5: 将图片移动到正确的段落位置
                    if success_img > 1 and len(img_blocks) > 1:
                        print(f"\n  [Step 6.5] Repositioning {success_img} images...")
                        move_result = js_eval(ws, f'''(function() {{
                            var ed = UE_V2.instants["ueditorInstant0"];
                            if (!ed || !ed.body) return "no_editor";
                            
                            // 获取所有段落（排除含img的空段落）
                            var paras = ed.body.querySelectorAll("p");
                            var paraList = [];
                            for (var i = 0; i < paras.length; i++) {{
                                var t = (paras[i].textContent || "").trim();
                                if (t.length > 2 && !paras[i].querySelector("img")) {{
                                    paraList.push(paras[i]);
                                }}
                            }}
                            
                            // 获取所有图片（按DOM顺序）
                            var imgs = ed.body.querySelectorAll("img");
                            console.log("Paras:", paraList.length, "Images:", imgs.length);
                            
                            // 目标位置映射：每张图片应该跟在哪个文本段落后
                            // img_blocks: [(after_idx, path, name), ...]
                            var targets = {json.dumps([(after_idx, img_name) for after_idx, _, img_name in img_blocks])};
                            
                            var moved = 0;
                            for (var i = 0; i < Math.min(imgs.length, targets.length); i++) {{
                                var targetAfterIdx = targets[i][0];
                                // targetAfterIdx 是文本块索引，对应到 paraList 的索引
                                // 图片应插入到第 targetAfterIdx 个文本段落后
                                var targetParaIdx = Math.min(targetAfterIdx - 1, paraList.length - 1);
                                if (targetParaIdx < 0) targetParaIdx = 0;
                                
                                var img = imgs[i];
                                var targetPara = paraList[targetParaIdx];
                                if (!targetPara || !img) continue;
                                
                                // 创建包裹p标签，把图片移过去
                                var wrapper = document.createElement("p");
                                wrapper.appendChild(img.cloneNode(true));
                                targetPara.parentNode.insertBefore(wrapper, targetPara.nextSibling);
                                
                                // 删除原位置的图片（如果还在原处）
                                if (img.parentNode) img.parentNode.removeChild(img);
                                
                                moved++;
                            }}
                            
                            return "moved:" + moved + "/" + imgs.length + " paras:" + paraList.length;
                        }})()''')
                        print(f"  Reposition: {move_result}")
            else:
                print("  DIALOG_NOT_FOUND")
                fail_img = len(img_blocks)
        else:
            print("  NO_BTN")
            fail_img = len(img_blocks)

    # Step 7: 标签
    if TAGS:
        print(f"\n[Step 7] Add tags...")
        tags_html = '<p>' + TAGS + '</p>'
        r = append_to_ueditor(ws, tags_html)
        print(f"  Tags: {r}")

    # Step 8: 最终检查
    print("\n" + "=" * 50)
    print("[Step 8 - Final Check]")

    final_title = js_eval(ws, """
        (function() {
            var el = document.querySelector('.input-box [contenteditable]');
            if (!el) return '';
            var span = el.querySelector('span[data-lexical-text]');
            return span ? span.textContent.trim() : el.textContent.trim();
        })()
    """)
    final_txtlen = get_body_txtlen(ws)
    final_imgcount = get_body_imgcount(ws)

    print(f"  Title: [{final_title}]")
    print(f"  Body: txtLen={final_txtlen}, imgCount={final_imgcount}")
    print(f"  Images: success={success_img}, fail={fail_img}")

    ts = time.strftime("%Y%m%d_%H%M%S")
    spath = take_screenshot(ws, f"bjh_v10_final_{ts}.png")

    ws.close()

    print(f"\n[DONE] Screenshot: {spath}")
    print("=" * 50)
    print("[IMPORTANT] Do NOT auto-publish!")
    print("[ACTION REQUIRED] Please manually check and click Publish.")
    print("=" * 50)


if __name__ == '__main__':
    main()
