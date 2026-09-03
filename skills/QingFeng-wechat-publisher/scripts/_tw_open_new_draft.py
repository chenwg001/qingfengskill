# -*- coding: utf-8 -*-
"""从当前已登录的微信页面提取 token，然后用正确 token 打开新草稿"""
import sys, time, re, os
sys.stdout.reconfigure(encoding='utf-8')
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp('http://127.0.0.1:9222')
    context = browser.contexts[0]
    
    # 找已登录的标签页，提取 token
    token = None
    found_page = None
    for pg in context.pages:
        url = pg.url
        print(f"  TAB: {url[:100]}")
        m = re.search(r'token=(\d+)', url)
        if m:
            token = m.group(1)
            found_page = pg
            print(f"  Found token: {token} from: {url[:80]}")
            break
    
    if not token:
        print("ERROR: No token found in any tab! Please login to mp.weixin.qq.com first.")
        sys.exit(1)
    
    # 用 token 打开新草稿
    new_url = f"https://mp.weixin.qq.com/cgi-bin/appmsg?t=media/appmsg_edit_v2&action=edit&isdefault=1&type=10&lang=zh_CN&token={token}"
    print(f"\nNavigating to NEW draft (with token)...")
    print(f"  URL: {new_url[:120]}...")
    
    # 在新 tab 中打开（避免覆盖现有页面）
    page = context.new_page()
    page.goto(new_url, wait_until='domcontentloaded', timeout=30000)
    page.wait_for_timeout(5000)
    print(f"  Current URL: {page.url[:120]}")
    
    # 检查是否跳到了登录页
    if 'login' in page.url or 'home' in page.url:
        print(f"  WARNING: Redirected to {page.url[:80]} - token may be invalid!")
    else:
        print(f"  SUCCESS: Editor opened!")
    
    # 等待编辑器加载
    print(f"\n  Waiting for .ProseMirror to appear...")
    try:
        page.wait_for_selector('.ProseMirror', timeout=20000)
        print(f"  Editor loaded! ProseMirror found.")
        pm_count = page.evaluate("() => document.querySelectorAll('.ProseMirror').length")
        print(f"  ProseMirror count: {pm_count}")
    except Exception as e:
        print(f"  WARNING: ProseMirror not found: {e}")
    
    # 等待文件上传 input 出现
    print(f"\n  Waiting for input[type='file']...")
    try:
        page.wait_for_selector('input[type="file"]', timeout=10000)
        print(f"  File inputs ready!")
        inputs = page.query_selector_all('input[type="file"]')
        print(f"  Found {len(inputs)} file inputs")
    except Exception as e:
        print(f"  WARNING: file inputs not found: {e}")
    
    page.wait_for_timeout(2000)
    print(f"\n  Final URL: {page.url[:120]}")
    print(f"  Done!")
