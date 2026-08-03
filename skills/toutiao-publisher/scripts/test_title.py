import sys, json, time, urllib.request, websocket
sys.path.insert(0, r'C:\Users\chenw\.qclaw\skills\toutiao-publisher\scripts')
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

# 开新标签
tabs = list_tabs()
page_tabs = [t for t in tabs if t.get('type') == 'page']
ws0 = connect(page_tabs[0]['webSocketDebuggerUrl'])
P.cdp_call(ws0, 'Target.createTarget', {'url': 'https://mp.toutiao.com/profile_v4/graphic/publish'})
time.sleep(12)
tabs2 = list_tabs()
new_tabs = [t for t in tabs2 if 'graphic/publish' in t.get('url', '') and t.get('type') == 'page']
ws = connect(new_tabs[-1]['webSocketDebuggerUrl'])
time.sleep(3)
for _ in range(20):
    if P.js_eval(ws, "!!document.querySelector('.ProseMirror')"):
        break
    time.sleep(1)
root = get_root(ws)
bc = btn_coords(ws)
print(f"按钮坐标: {bc}\n")

title = "测试标题：赛教相融的实践探索"

# ===== 场景 A：仅清空（不填标题）=====
print("=== 场景 A：仅清空编辑器后点击 ===")
clear_editor(ws)
time.sleep(1.5)
P.mouse_click(ws, bc[0], bc[1])
time.sleep(4)
na = count_inputs(ws, root)
P.press_esc(ws); time.sleep(1.5)
print(f"  file input 数 = {na}  -> {'✅ 成功' if na>0 else '❌ 失败'}\n")

# ===== 场景 B：填标题后再清空 =====
print("=== 场景 B：填标题 → 清空 → 点击 ===")
fill_title(ws, title)
time.sleep(0.5)
clear_editor(ws)
time.sleep(1.5)
P.mouse_click(ws, bc[0], bc[1])
time.sleep(4)
nb = count_inputs(ws, root)
P.press_esc(ws); time.sleep(1.5)
print(f"  file input 数 = {nb}  -> {'✅ 成功' if nb>0 else '❌ 失败'}\n")

print(f"场景A(仅清空): {'成功' if na>0 else '失败'} | 场景B(填标题后清空): {'成功' if nb>0 else '失败'}")
