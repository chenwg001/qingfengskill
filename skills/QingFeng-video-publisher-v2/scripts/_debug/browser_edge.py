# -*- coding: utf-8 -*-
"""
启动 Edge 浏览器（用户真实 profile，含登录态）
返回 CDP 端口和创作者标签页 ID
"""
import subprocess, sys, json, time
sys.stdout.reconfigure(encoding='utf-8')

EDGE_PATH = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
PROFILE_DIR = r"--user-data-dir=C:\Users\chenw\AppData\Local\Microsoft\Edge\User Data"
PORT_FILE = r"C:\Users\chenw\.qclaw\edge_cdp_port.txt"


def get_free_port():
    import socket
    with socket.socket() as s:
        s.bind(('', 0))
        return s.getsockname()[1]


def start_edge():
    # 先检查是否已有 Edge 在运行（带 remote debugging）
    try:
        import urllib.request
        resp = urllib.request.urlopen('http://127.0.0.1:9222/json', timeout=2)
        tabs = json.loads(resp.read())
        print(f"[INFO] Edge already running on port 9222")
        for t in tabs:
            if 'douyin.com' in t.get('url', ''):
                print(f"[INFO] Found Douyin tab: {t['id']}")
                return 9222, t['id']
        if tabs:
            return 9222, tabs[0]['id']
    except Exception:
        pass

    # 启动新 Edge 实例
    port = get_free_port()
    cmd = [
        EDGE_PATH,
        PROFILE_DIR,
        f"--remote-debugging-port={port}",
        "--remote-allow-origins=*",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-background-networking",
    ]
    print(f"[INFO] Starting Edge on port {port}...")
    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    # 等待 Edge 启动
    for _ in range(20):
        try:
            import urllib.request
            resp = urllib.request.urlopen(f'http://127.0.0.1:{port}/json', timeout=2)
            tabs = json.loads(resp.read())
            for t in tabs:
                url = t.get('url', '')
                if 'douyin.com/creator' in url or 'creator.douyin.com' in url:
                    print(f"[OK] Tab ID: {t['id']}")
                    return port, t['id']
            if tabs:
                return port, tabs[0]['id']
        except Exception:
            time.sleep(1)
    
    print("[ERROR] Edge failed to start")
    return port, None


if __name__ == '__main__':
    port, tab_id = start_edge()
    print(f"CDP_PORT={port}")
    print(f"TAB_ID={tab_id}")
    with open(PORT_FILE, 'w') as f:
        f.write(f"{port}\n{tab_id}\n")