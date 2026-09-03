#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
快手登录等待 + DOM 探查。
打开快手创作者上传页，轮询最多 WAIT 秒检测是否已登录；
一旦登录成功即 dump 关键 DOM（视频 input / 标题 / 封面 / 按钮）。
不执行任何发布动作。
"""
import os, sys, time

for _k in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY",
           "all_proxy", "ALL_PROXY"):
    os.environ.pop(_k, None)

from playwright.sync_api import sync_playwright

CDP_URL = "http://127.0.0.1:9222"
KS_URL = "https://creator.kuaishou.com/xs-plane/share/upload"
WAIT = int(os.environ.get("KS_WAIT", "180"))

def log(m): print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)

def dump_dom(page, tag=""):
    log(f"===== DUMP {tag} | url={page.url} =====")
    try:
        ins = page.query_selector_all('input[type="file"]')
        log(f"input[type=file] 数量: {len(ins)}")
        for i, inp in enumerate(ins):
            log(f"  file#{i} accept='{inp.get_attribute('accept')}' multiple={inp.get_attribute('multiple')} class='{inp.get_attribute('class')}'")
    except Exception as e:
        log(f"  file err: {e}")
    try:
        for sel in ['input[placeholder*="标题"]', 'input[placeholder*="title"]',
                    'textarea[placeholder*="标题"]', 'input[placeholder*="填写"]']:
            for e in page.query_selector_all(sel):
                log(f"  [{sel}] ph='{e.get_attribute('placeholder')}' class='{e.get_attribute('class')}'")
    except Exception as e:
        log(f"  title err: {e}")
    try:
        ces = page.query_selector_all('div[contenteditable="true"]')
        log(f"contenteditable 数量: {len(ces)}")
        for i, e in enumerate(ces[:10]):
            log(f"  ce#{i} ph='{e.get_attribute('data-placeholder')}' class='{e.get_attribute('class')}'")
    except Exception as e:
        log(f"  ce err: {e}")
    try:
        keys = ["上传", "发布", "草稿", "保存", "下一步", "暂存", "登录", "立即", "封面"]
        txts = page.inner_text("body", timeout=3000)
        for k in keys:
            if k in txts:
                log(f"  body 含关键字: {k}")
    except Exception as e:
        log(f"  body err: {e}")

def is_logged_in(page):
    url = page.url or ""
    if "passport" in url or "login" in url:
        return False
    try:
        if "登录" in page.inner_text("body", timeout=3000):
            return False
    except:
        pass
    return True

def main():
    p = sync_playwright().start()
    browser = None
    try:
        browser = p.chromium.connect_over_cdp(CDP_URL)
        ctx = browser.contexts[0] if browser.contexts else browser.new_context()
        page = ctx.new_page()
        log(f"打开 {KS_URL}")
        page.goto(KS_URL, wait_until="domcontentloaded", timeout=30000)
        log("请在浏览器窗口中用快手 App 扫码登录...")
        t0 = time.time()
        logged = False
        while time.time() - t0 < WAIT:
            time.sleep(5)
            try:
                if is_logged_in(page):
                    logged = True
                    log("✅ 检测到已登录！")
                    break
            except Exception as e:
                log(f"  poll err: {e}")
            remain = int(WAIT - (time.time() - t0))
            if remain % 20 < 5:
                log(f"  等待登录中，剩余约 {remain}s ... (当前 url={page.url})")
        if not logged:
            log("⏰ 超时仍未登录。请在浏览器手动登录后重跑本脚本。")
            return
        time.sleep(4)
        dump_dom(page, "登录后")
        time.sleep(3)
        dump_dom(page, "登录后[二次]")
    except Exception as e:
        log(f"[ERROR] {e}")
        import traceback; traceback.print_exc()
    finally:
        if browser:
            try: browser.close()
            except: pass
        p.stop()

if __name__ == "__main__":
    main()
