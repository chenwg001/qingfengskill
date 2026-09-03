#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""小红书：用 Playwright locator 点击封面试探，截图观察"""
import os, sys, time
for _k in ("http_proxy","https_proxy","HTTP_PROXY","HTTPS_PROXY","all_proxy","ALL_PROXY"):
    os.environ.pop(_k, None)
from playwright.sync_api import sync_playwright

CDP = "http://127.0.0.1:9222"
SHOT_DIR = "D:/chenw/AgentSpace/outputs/web"

def log(m): print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)

def dump_inputs(page):
    return page.evaluate("""() => {
        const out=[];
        for (const f of document.querySelectorAll('input[type=file]')) {
            const acc=(f.getAttribute('accept')||'');
            const r=f.getBoundingClientRect();
            out.push({accept:acc.slice(0,40), w:Math.round(r.width), h:Math.round(r.height),
                inModal:!!f.closest('.semi-modal, .semi-modal-wrapper, [class*="modal" i], [class*="dialog" i]')});
        }
        return out;
    }""")

def main():
    p = sync_playwright().start()
    browser=None
    try:
        browser = p.chromium.connect_over_cdp(CDP)
        page = browser.contexts[0].pages[0]
        log(f"当前页: {page.url}")
        # 按 Esc 关闭话题浮层
        page.keyboard.press("Escape")
        time.sleep(1)
        log(f"初始 file inputs: {dump_inputs(page)}")
        page.screenshot(path=f"{SHOT_DIR}/xhs_cover_probe1.png")
        log("截图 xhs_cover_probe1.png")

        # 方法A: 文本精确点击 设置封面
        log("\nA) locator click TEXT '设置封面'")
        try:
            page.get_by_text("设置封面").click(timeout=5000)
            log("  clicked")
        except Exception as e:
            log(f"  fail: {e}")
        time.sleep(4)
        log(f"file inputs: {dump_inputs(page)}")
        page.screenshot(path=f"{SHOT_DIR}/xhs_cover_probe2.png")
        log("截图 xhs_cover_probe2.png")

        # 方法B: 点击第一个封面缩略图（设置封面区下的 img）
        log("\nB) 点击设置封面区第一个 img")
        try:
            # 找设置封面文字后的第一个可见 img
            page.evaluate("""()=>{
                const spans=[...document.querySelectorAll('span,div')].filter(e=>(e.innerText||'').trim()==='设置封面');
                if(!spans.length) return;
                const box=spans[0].getBoundingClientRect();
                // 找 box 下方 200px 内最大的 img
                let best=null, bestA=0;
                for(const img of document.querySelectorAll('img')){
                    const r=img.getBoundingClientRect();
                    if(r.top>box.bottom && r.top<box.bottom+200 && r.width>30 && r.height>30){
                        const a=r.width*r.height;
                        if(a>bestA){bestA=a; best=img;}
                    }
                }
                if(best){best.scrollIntoView({block:'center'}); best.click();}
            }""")
            log("  js clicked first cover img")
        except Exception as e:
            log(f"  fail: {e}")
        time.sleep(4)
        log(f"file inputs: {dump_inputs(page)}")
        page.screenshot(path=f"{SHOT_DIR}/xhs_cover_probe3.png")
        log("截图 xhs_cover_probe3.png")

        # 方法C: 直接 set_input_files 到页面现有的唯一 file input（可能视频和封面共用？不，accept不同）
        log("\nC) 检查页面上所有 input[type=file]")
        log(f"file inputs: {dump_inputs(page)}")
    except Exception as e:
        log(f"[ERROR] {e}"); import traceback; traceback.print_exc()
    finally:
        if browser:
            try: browser.close()
            except Exception: pass
        p.stop()

if __name__ == "__main__":
    main()
