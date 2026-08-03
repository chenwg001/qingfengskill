# -*- coding: utf-8 -*-
"""导航到头条号发布页面并执行发布脚本"""
import sys, json, time, urllib.request, websocket
sys.stdout.reconfigure(encoding='utf-8')

PORT = 9222
TARGET_URL = 'https://mp.toutiao.com/profile_v4/graphic/publish'

def get_pages():
    try:
        with urllib.request.urlopen('http://127.0.0.1:{}/json'.format(PORT), timeout=3) as r:
            return json.loads(r.read())
    except:
        return None

print('获取 CDP 页面列表...')
pages = get_pages()
if not pages:
    print('ERROR: 无法连接 CDP 端口 {}'.format(PORT))
    sys.exit(1)

print('找到 {} 个页面'.format(len(pages)))

# 找头条号页面
target_page = None
for p in pages:
    url = p.get('url', '').lower()
    if 'toutiao' in url and p.get('type') == 'page':
        target_page = p
        print('找到头条号页面: {}'.format(p['url'][:80]))
        break

if not target_page:
    # 用第一个 page
    for p in pages:
        if p.get('type') == 'page':
            target_page = p
            break

if not target_page:
    print('ERROR: 没有可用的页面')
    sys.exit(1)

print('使用页面: {}'.format(target_page['url'][:80]))
ws_url = target_page['webSocketDebuggerUrl']

# 连接 WebSocket 并导航
print('连接 WebSocket: {}'.format(ws_url[:60]))
ws = websocket.create_connection(ws_url, timeout=10)
ws.settimeout(10)

# 启用 Page 域
print('启用 Page 域...')
ws.send(json.dumps({'id': 1, 'method': 'Page.enable'}))
ws.recv()

# 导航到发布页
print('导航到: {}'.format(TARGET_URL))
nav_params = {'url': TARGET_URL}
nav_msg = {'id': 2, 'method': 'Page.navigate', 'params': nav_params}
ws.send(json.dumps(nav_msg))
resp = json.loads(ws.recv())
print('导航响应: {}'.format(resp))

# 等待页面加载
print('等待页面加载(10秒)...')
time.sleep(10)

# 验证当前 URL
print('验证当前 URL...')
eval_params = {'expression': 'window.location.href'}
eval_msg = {'id': 3, 'method': 'Runtime.evaluate', 'params': eval_params}
ws.send(json.dumps(eval_msg))
resp = json.loads(ws.recv())
current_url = resp.get('result', {}).get('result', {}).get('value', '')
print('当前 URL: {}'.format(current_url[:100]))

ws.close()

if 'graphic/publish' in current_url:
    print('SUCCESS: 已到达发布页面')
    print('现在可以执行发布脚本...')
else:
    print('WARNING: URL 可能不正确')
    print('请手动检查浏览器，或重新运行此脚本')
