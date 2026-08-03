import sys, json, time, urllib.request, websocket, os
sys.path.insert(0, r'C:\Users\chenw\.qclaw\skills\toutiao-publisher\scripts')
import publish as P

CDP_PORT = P.CDP_PORT
COVER = r"D:\个人\资源\个人文章\轻风专辑\科学教育\12\cover.jpg"
abs_cover = os.path.abspath(COVER).replace('\\', '/')

def list_tabs():
    return json.loads(urllib.request.urlopen(f"http://127.0.0.1:{CDP_PORT}/json", timeout=3).read())

def connect(url):
    return websocket.create_connection(url, timeout=30)

def get_root(ws):
    doc = P.cdp_call(ws, 'DOM.getDocument')
    return doc['result']['root']['nodeId']

def get_input_ids(ws, root):
    sel = P.cdp_call(ws, 'DOM.querySelectorAll', {'nodeId': root, 'selector': 'input[type=file]'})
    return sel['result'].get('nodeIds', [])

def count_inputs(ws, root):
    return len(get_input_ids(ws, root))

def btn_coords(ws):
    return P.js_eval(ws, """(() => {
        var b = document.querySelector('.syl-toolbar-tool.image');
        if (!b) return null;
        var r = b.getBoundingClientRect();
        return [Math.round(r.x + r.width/2), Math.round(r.y + r.height/2)];
    })()""")

def clear_editor(ws):
    P.js_eval(ws, """(() => {
        var editor = document.querySelector('.ProseMirror');
        editor.innerHTML = '<p><br></p>';
        return 'cleared';
    })()""")

tabs = list_tabs()
page_tabs = [t for t in tabs if t.get('type') == 'page' and 'graphic/publish' in t.get('url','')]
if not page_tabs:
    page_tabs = [t for t in tabs if t.get('type') == 'page']
ws = connect(page_tabs[0]['webSocketDebuggerUrl'])
P.cdp_call(ws, 'Page.navigate', {'url': 'https://mp.toutiao.com/profile_v4/graphic/publish'})
print("导航到发布页，等待 6 秒...")
time.sleep(6)
for _ in range(20):
    if P.js_eval(ws, "!!document.querySelector('.ProseMirror')"):
        break
    time.sleep(1)
root = get_root(ws)

print("\n=== 新流程: 先插文本→光标到最前→插封面 ===")
clear_editor(ws); time.sleep(0.5)

# (1) 插入首段文本（稳定块）
P.js_eval(ws, """(() => {
    var editor = document.querySelector('.ProseMirror');
    var el = document.createElement('p');
    el.textContent = '测试段落：这是用于稳定编辑器的首段文本。';
    editor.appendChild(el);
    editor.dispatchEvent(new Event('input', {bubbles: true}));
    return editor.children.length;
})()""")
print("  已插入稳定文本块")
time.sleep(0.3)

# (2) 光标到最前
P.js_eval(ws, """(() => {
    var editor = document.querySelector('.ProseMirror');
    editor.focus();
    var firstChild = editor.firstElementChild;
    var s = window.getSelection();
    var r = document.createRange();
    if (firstChild) { r.selectNodeContents(firstChild); r.collapse(true); }
    else { r.selectNodeContents(editor); r.collapse(true); }
    s.removeAllRanges(); s.addRange(r);
    return 'cursor_at_start';
})()""")
time.sleep(0.3)

# (3) 点击图片按钮
bc = btn_coords(ws)
print(f"  按钮坐标: {bc}")
P.mouse_click(ws, bc[0], bc[1])
time.sleep(4)
input_ids = get_input_ids(ws, root)
print(f"  file input 数 = {len(input_ids)}")
if len(input_ids) == 0:
    print("  ❌ 弹窗未打开")
else:
    # 上传封面
    cdp_call_result = P.cdp_call(ws, 'DOM.setFileInputFiles', {'nodeId': input_ids[0], 'files': [abs_cover]}, 10)
    time.sleep(5)
    cnt = P.js_eval(ws, "document.querySelector('.ProseMirror').querySelectorAll('img').length")
    print(f"  setFile 后图片数 = {cnt}")
    if isinstance(cnt, int) and cnt == 0:
        # 点击确认按钮提交上传
        P.js_eval(ws, """(() => {
            var buttons = document.querySelectorAll('button');
            for (var k = 0; k < buttons.length; k++) {
                var t = (buttons[k].textContent || '').trim();
                if (t === '确定' || t === '确认') { buttons[k].click(); return 'clicked:' + t; }
            }
            return 'not_found';
        })()""")
        time.sleep(5)
    # 检查封面位置（是否在第一位）
    pos = P.js_eval(ws, """(() => {
        var editor = document.querySelector('.ProseMirror');
        var imgs = editor.querySelectorAll('img');
        if (imgs.length === 0) return 'no_img';
        var first = imgs[0];
        // 判断第一张图是否在第一个文本块之前
        var firstChild = editor.firstElementChild;
        return firstChild.contains(first) ? 'cover_at_front' : 'cover_not_front';
    })()""")
    cnt = P.js_eval(ws, "document.querySelector('.ProseMirror').querySelectorAll('img').length")
    print(f"  图片总数 = {cnt}, 封面位置 = {pos}")
    if pos == 'cover_at_front':
        print("  ✅ 成功：封面在正文最前面！")
    else:
        print("  ⚠️ 封面已上传但不在最前")

P.press_esc(ws); time.sleep(1)
