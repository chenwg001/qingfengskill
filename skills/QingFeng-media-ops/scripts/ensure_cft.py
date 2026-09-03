# -*- coding: utf-8 -*-
"""
Chrome for Testing 启动保障（统一 CDP 入口，端口 9222）。

图文（头条/公众号/小红书）+ 视频（抖音/快手/B站）全部连这个浏览器。
该 profile 必须已登录全部六个平台。

用法:
  python ensure_cft.py            # 已运行则跳过，未运行则启动
  python ensure_cft.py --check    # 只检查不启动
"""
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request

sys.stdout.reconfigure(encoding='utf-8')

CFT_EXE = r'D:\chenw\chrome-win64\chrome.exe'
PROFILE = r'D:\chenw\chrome-test-profile'
PORT = 9222


def is_running():
    try:
        r = urllib.request.urlopen(f'http://127.0.0.1:{PORT}/json/version', timeout=2)
        info = json.loads(r.read())
        return info.get('Browser', '')
    except Exception:
        return ''


def main():
    ap = argparse.ArgumentParser(description='Chrome for Testing 启动保障')
    ap.add_argument('--check', action='store_true')
    args = ap.parse_args()

    b = is_running()
    if b:
        print(f'[OK] Chrome for Testing 已在端口 {PORT} 运行: {b}')
        return
    if args.check:
        print(f'[FAIL] 端口 {PORT} 未运行', file=sys.stderr)
        sys.exit(1)
    if not os.path.exists(CFT_EXE):
        print(f'[FAIL] 找不到 Chrome for Testing: {CFT_EXE}', file=sys.stderr)
        sys.exit(1)
    print(f'[INFO] 启动 Chrome for Testing (port {PORT}, profile {PROFILE})...')
    subprocess.Popen([
        CFT_EXE,
        f'--user-data-dir={PROFILE}',
        '--no-first-run',
        f'--remote-debugging-port={PORT}',
        '--remote-allow-origins=*',
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(20):
        time.sleep(1)
        b = is_running()
        if b:
            print(f'[OK] 已启动: {b}')
            return
    print('[FAIL] 启动超时，请手动检查', file=sys.stderr)
    sys.exit(1)


if __name__ == '__main__':
    main()
