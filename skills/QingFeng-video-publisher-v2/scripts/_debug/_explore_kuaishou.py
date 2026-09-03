#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
快手创作者平台深度探查（排错用）
dump: URL、所有链接、所有按钮/可点元素文本、iframe、file input、输入框。
用法: python _explore_kuaishou.py [可选URL]
"""
import os, sys, time

for _k in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY",
           "all_proxy", "ALL_PROXY"):
    os.environ.pop(_k, None)

from playwright.sync_api import sync_playwright

CDP_URL = "http://127.0.0.1:9222"
DEFAULT_URL = "https://cp.kuaishou.com/profile"

def log(m): print(m, flush=True)

def dump(page, tag=""):
    log(f"\n===== DUMP {tag} | url={page.url} =====")
    # file input
    try:
        ins = page.query_selector_all('input[type="file"]')
        log(f"[file input] {len(ins)} 个")
        for i, inp in enumerate(ins):
            log(f"  #{i} accept='{inp.get_attribute('accept')}' multiple={inp.get_attribute('multiple')} class='{inp.get_attribute('class')}'")
    except Exception as e:
        log(f"[file input] err {e}")
    # iframe
    try:
        fr = page.query_selector_all('iframe')
        log(f"[iframe] {len(fr)} 个")
        for i, f in enumerate(fr):
            log(f"  #{i} src='{f.get_attribute('src')}'")
    except Exception as e:
        log(f"[iframe] err {e}")
    # 链接
    try:
        as_ = page.query_selector_all('a[href]')
        links = []
        for a in as_:
            href = a.get_attribute('href') or ''
            txt = (a.inner_text() or '').strip().replace('\n', ' ')[:30]
            if href.startswith('javascript') or not href:
                continue
            links.append((href, txt))
        log(f"[links] {len(links)} 个（去空）")
        for href, txt in links[:60]:
            log(f"  '{txt}' -> {href}")
    except Exception as e:
        log(f"[links] err {e}")
    # 按钮 / 可点元素文本
    try:
        btns = page.query_selector_all('button, [class*=btn], [class*=Btn], [role=button]')
        seen = set()
        log(f"[buttons] {len(btns)} 个")
        for b in btns:
            try:
                t = (b.inner_text() or '').strip().replace('\n', ' ')[:24]
            except:
                t = ''
            if not t or t in seen:
                continue
            seen.add(t)
            cls = b.get_attribute('class') or ''
            vis = False
            try: vis = b.is_visible()
            except: pass
            log(f"  '{t}' visible={vis} class='{cls[:60]}'")
    except Exception as e:
        log(f"[buttons] err {e}")
    # 输入框
    try:
        for sel in ['input[placeholder]', 'textarea[placeholder]',
                    'div[contenteditable="true"]']:
            els = page.query_selector_all(sel)
            for e in els:
                ph = e.get_attribute('placeholder') or e.get_attribute('data-placeholder') or ''
                cls = e.get_attribute('class') or ''
                log(f"  [{sel}] ph='{ph}' class='{cls[:50]}'")
    except Exception as e:
        log(f"[inputs] err {e}")
    # 正文首段（判断页面性质）
    try:
        body = page.inner_text("body", timeout=3000)
        log(f"[body 长度] {len(body)}")
        log("[body 前600字]\n" + body[:600].replace('\n\n', '\n'))
    except Exception as e:
        log(f"[body] err {e}")

def main():
    url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_URL
    p = sync_playwright().start()
    browser = None
    try:
        browser = p.chromium.connect_over_cdp(CDP_URL)
        ctx = browser.contexts[0] if browser.contexts else browser.new_context()
        page = ctx.new_page()
        log(f"导航: {url}")
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        time.sleep(7)
        dump(page, "初始")
        time.sleep(4)
        dump(page, "二次加载后")
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
