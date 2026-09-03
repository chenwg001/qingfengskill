import sys, json, time, urllib.request, websocket
sys.path.insert(0, r'C:\Users\chenw\.qclaw\skills\QingFeng-toutiao-publisher\scripts')
import publish as P

CDP_PORT = P.CDP_PORT

def list_tabs():
    return json.loads(urllib.request.urlopen(f"http://127.0.0.1:{CDP_PORT}/json", timeout=3).read())

def connect(url):
    return websocket.create_connection(url, timeout=30)

def get_root(ws):
    doc = P.cdp_call(ws, 'DOM.getDocument')
    return doc['result']['root']['nodeId']

def count_inputs(ws, root):
    sel = P.cdp_call(ws, 'DOM.querySelectorAll', {'nodeId': root, 'selector': 'input[type=file]'})
    return len(sel['result'].get('nodeIds', []))

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
        var tas = document.querySelectorAll('textarea');
        for (var i = 0; i < tas.length; i++) { if (i > 0) tas[i].value = ''; }
        return 'cleared';
    })()""")

def fill_title(ws, title):
    P.js_eval(ws, f"""(() => {{
        var ta = document.querySelector('textarea');
        var setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
        setter.call(ta, {json.dumps(title)});
        ta.dispatchEvent(new Event('input', {{bubbles: true}}));
        ta.dispatchEvent(new Event('change', {{bubbles: true}}));
        return ta.value.length;
    }})()""")

# 连到当前 publish 标签（模拟实际运行：已有标签 + Page.navigate）
tabs = list_tabs()
page_tabs = [t for t in tabs if t.get('type') == 'page' and 'graphic/publish' in t.get('url','')]
if not page_tabs:
    page_tabs = [t for t in tabs if t.get('type') == 'page']
ws = connect(page_tabs[0]['webSocketDebuggerUrl'])

# 用 Page.navigate 重新导航（模拟实际运行）
print("用 Page.navigate 重新导航到发布页...")
P.cdp_call(ws, 'Page.navigate', {'url': 'https://mp.toutiao.com/profile_v4/graphic/publish'})
print("等待 6 秒（模拟实际运行的等待）...")
time.sleep(6)

for _ in range(20):
    if P.js_eval(ws, "!!document.querySelector('.ProseMirror')"):
        break
    time.sleep(1)
root = get_root(ws)
bc = btn_coords(ws)
print(f"按钮坐标(导航后): {bc}\n")

title = "测试标题：赛教相融的实践探索"

print("=== 模拟实际运行: 填标题 → 清空 → 点击 ===")
fill_title(ws, title)
time.sleep(0.5)
clear_editor(ws)
time.sleep(0.5)
# 模拟 Step 2b 的按钮就绪检测（含 scrollIntoView）
ready = P.js_eval(ws, """(() => {
    var btn = document.querySelector('.syl-toolbar-tool.image');
    if (!btn) return false;
    var r = btn.getBoundingClientRect();
    if (r.width === 0 || r.height === 0) return false;
    if (btn.disabled) return false;
    var cs = getComputedStyle(btn);
    if (cs.pointerEvents === 'none') return false;
    if (cs.visibility === 'hidden' || cs.display === 'none') return false;
    btn.scrollIntoView({block: 'center', inline: 'nearest'});
    return true;
})()""")
print(f"  按钮就绪: {ready}")
P.js_eval(ws, "window.scrollTo(0, 0)"); time.sleep(0.5)
bc2 = btn_coords(ws)
print(f"  滚动后按钮坐标: {bc2}")
P.mouse_click(ws, bc2[0], bc2[1])
time.sleep(4)
n = count_inputs(ws, root)
P.press_esc(ws); time.sleep(1.5)
print(f"  file input 数 = {n}  -> {'✅ 成功' if n>0 else '❌ 失败'}")
