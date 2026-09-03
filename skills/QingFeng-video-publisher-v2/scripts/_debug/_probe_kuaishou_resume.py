#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
验证快手草稿恢复：检测「还有上次未发布的视频」提示 → 点继续编辑 → 检查描述/封面是否恢复。
"""
import os, sys, time

for _k in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY",
           "all_proxy", "ALL_PROXY"):
    os.environ.pop(_k, None)

from playwright.sync_api import sync_playwright

CDP_URL = "http://127.0.0.1:9222"
UPLOAD_URL = "https://cp.kuaishou.com/article/publish/video"

def log(m): print(m, flush=True)

def click_by_text(page, txt):
    try:
        return page.evaluate("""(txt)=>{
            for(const el of document.querySelectorAll('div,span,button,li,a')){
                const t=(el.innerText||'').trim();
                if(t===txt && el.getBoundingClientRect().width>5){
                    el.dispatchEvent(new MouseEvent('click',{bubbles:true,cancelable:true,view:window}));
                    return 'ok';
                }}
            return '';
        }""", txt)
    except Exception as e:
        return f'err:{e}'

def state(page):
    return page.evaluate("""()=>{
        const d=document.querySelector('[class*="_description_"]');
        const cov=[];
        document.querySelectorAll('[class*="_default-cover"] img, [class*="_cover"] img').forEach(im=>{
            const s=im.getAttribute('src')||'';
            if(s&&!s.startsWith('data:image/svg')) cov.push(s.slice(0,90));
        });
        return {url:location.href, desc:(d?(d.innerText||'').slice(0,100):'(无描述框)'), covers:cov.slice(0,3),
                hasVideoInput: document.querySelectorAll('input[type=file]').length};
    }""")

def main():
    p = sync_playwright().start(); browser = None
    try:
        browser = p.chromium.connect_over_cdp(CDP_URL)
        ctx = browser.contexts[0] if browser.contexts else browser.new_context()
        page = None
        for pg in ctx.pages:
            if "kuaishou.com" in (pg.url or ""):
                page = pg
                if "publish" in (pg.url or ""): break
        if page is None: log("[FAIL] 无快手页"); return
        try: page.bring_to_front()
        except: pass
        # 先重新导航（草稿提示在加载时才出现）
        log("重新导航到上传页...")
        page.goto(UPLOAD_URL, wait_until="domcontentloaded", timeout=30000)
        time.sleep(7)
        page.evaluate("""()=>{document.querySelectorAll('#react-joyride-portal').forEach(e=>e.remove());}""")
        time.sleep(1)
        log(f"页面: {page.url}")
        log(f"[初始] {state(page)}")

        # 检测草稿提示
        body = page.inner_text("body", timeout=3000)
        if "还有上次未发布的视频" in body:
            log("\n>>> 检测到草稿提示，点击「继续编辑」: " + str(click_by_text(page, "继续编辑")))
            time.sleep(10)
            log(f"[恢复后] {state(page)}")
        else:
            log("无草稿提示")
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
