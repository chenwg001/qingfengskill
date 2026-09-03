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

def cursor_to_end(ws):
    P.js_eval(ws, """(() => {
        var editor = document.querySelector('.ProseMirror');
        editor.focus();
        var sel = window.getSelection();
        var range = document.createRange();
        range.selectNodeContents(editor);
        range.collapse(false);
        sel.removeAllRanges();
        sel.addRange(range);
        return true;
    })()""")

tabs = list_tabs()
page_tabs = [t for t in tabs if t.get('type') == 'page' and 'graphic/publish' in t.get('url','')]
if not page_tabs:
    page_tabs = [t for t in tabs if t.get('type') == 'page']
ws = connect(page_tabs[0]['webSocketDebuggerUrl'])
P.cdp_call(ws, 'Page.navigate', {'url': 'https://mp.toutiao.com/profile_v4/graphic/publish'})
time.sleep(6)
for _ in range(20):
    if P.js_eval(ws, "!!document.querySelector('.ProseMirror')"):
        break
    time.sleep(1)
root = get_root(ws)
title = "测试标题：赛教相融的实践探索"

print("=== 试验1: 填标题→清空→点击（不含 focus）===")
fill_title(ws, title); time.sleep(0.5)
clear_editor(ws); time.sleep(0.5)
bc = btn_coords(ws)
P.mouse_click(ws, bc[0], bc[1]); time.sleep(4)
n1 = count_inputs(ws, root)
P.press_esc(ws); time.sleep(1.5)
print(f"  file input = {n1} -> {'✅' if n1>0 else '❌'}\n")

print("=== 试验2: 填标题→清空→FOCUS(光标末尾)→点击 ===")
clear_editor(ws); time.sleep(0.5)
cursor_to_end(ws); time.sleep(0.3)
P.press_esc(ws); time.sleep(0.3)
bc = btn_coords(ws)
print(f"  focus 后按钮坐标: {bc}")
P.mouse_click(ws, bc[0], bc[1]); time.sleep(4)
n2 = count_inputs(ws, root)
P.press_esc(ws); time.sleep(1.5)
print(f"  file input = {n2} -> {'✅' if n2>0 else '❌'}\n")

print(f"试验1(无focus): {'成功' if n1>0 else '失败'} | 试验2(有focus): {'成功' if n2>0 else '失败'}")
