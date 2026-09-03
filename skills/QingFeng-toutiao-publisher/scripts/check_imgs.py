import sys, json, time, urllib.request, websocket
sys.path.insert(0, r'C:\Users\chenw\.qclaw\skills\QingFeng-toutiao-publisher\scripts')
import publish as P

tabs = json.loads(urllib.request.urlopen("http://127.0.0.1:9222/json", timeout=3).read())
ws = None
for t in tabs:
    if t.get('type') == 'page' and 'graphic/publish' in t.get('url', ''):
        ws = websocket.create_connection(t['webSocketDebuggerUrl'], timeout=30)
        break
if not ws:
    print("未找到发布页标签")
    sys.exit(1)

# 列出编辑器内所有 img 的 src/fullsrc
imgs = P.js_eval(ws, """(() => {
    var editor = document.querySelector('.ProseMirror');
    var list = Array.from(editor.querySelectorAll('img'));
    return list.map(function(im, i){
        return {
            idx: i,
            src: (im.getAttribute('src')||'').slice(0, 60),
            alt: (im.getAttribute('alt')||'').slice(0, 30),
            w: im.naturalWidth, h: im.naturalHeight
        };
    });
})()""")
print(f"编辑器内 img 总数: {len(imgs)}")
print("---")
for im in imgs:
    print(f"[{im['idx']}] {im['w']}x{im['h']} alt='{im['alt']}' src={im['src']}")

# 检测相邻重复
print("\n--- 检测重复 ---")
dups = []
for i in range(1, len(imgs)):
    if imgs[i]['src'] == imgs[i-1]['src'] and imgs[i]['src']:
        dups.append(i)
if dups:
    print(f"发现 {len(dups)} 处相邻重复（索引: {dups}）")
else:
    print("未发现相邻重复（src 均不同）")

# 统计唯一 src
uniq = set(im['src'] for im in imgs if im['src'])
print(f"唯一 src 数: {len(uniq)}")
