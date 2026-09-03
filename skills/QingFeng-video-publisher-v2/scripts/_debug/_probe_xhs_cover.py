#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""小红书：细探封面上传入口与弹窗结构"""
import os, sys, time
for _k in ("http_proxy","https_proxy","HTTP_PROXY","HTTPS_PROXY","all_proxy","ALL_PROXY"):
    os.environ.pop(_k, None)
from playwright.sync_api import sync_playwright

CDP = "http://127.0.0.1:9222"

def log(m): print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)

def dump(page, tag):
    info = page.evaluate("""() => {
        const out = {bodyText:(document.body.innerText||'').slice(0,200),
            modals:[], files:[], texts:[], coverImgs:[]};
        // 所有弹窗
        for (const m of document.querySelectorAll('.semi-modal, .semi-modal-wrapper, [class*="modal" i], [class*="dialog" i]')) {
            const r = m.getBoundingClientRect();
            if (r.width>50 && r.height>50) {
                out.modals.push({cls:(m.className||'').toString().slice(0,60), w:Math.round(r.width), h:Math.round(r.height),
                    text:(m.innerText||'').slice(0,80)});
            }
        }
        // 所有 file input
        for (const f of document.querySelectorAll('input[type=file]')) {
            const acc=(f.getAttribute('accept')||'');
            const r=f.getBoundingClientRect();
            out.files.push({accept:acc.slice(0,40), w:Math.round(r.width), h:Math.round(r.height),
                inModal: !!f.closest('.semi-modal, .semi-modal-wrapper, [class*="modal" i], [class*="dialog" i]')});
        }
        // 封面区附近 img
        for (const img of document.querySelectorAll('img')) {
            const r=img.getBoundingClientRect();
            out.coverImgs.push({src:(img.src||'').slice(0,60), w:Math.round(r.width), h:Math.round(r.height)});
        }
        return out;
    }""")
    log(f"\n=== {tag} ===")
    log(f"bodyText: {info['bodyText']}")
    log(f"弹窗({len(info['modals'])}):")
    for m in info['modals']: log(f"   cls={m['cls']} {m['w']}x{m['h']} text={m['text']}")
    log(f"file inputs({len(info['files'])}):")
    for f in info['files']: log(f"   accept={f['accept']} {f['w']}x{f['h']} inModal={f['inModal']}")
    log(f"imgs({len(info['coverImgs'])}):")
    for i in info['coverImgs'][:5]: log(f"   {i['src']} {i['w']}x{i['h']}")


def click_any(page, selector_or_js):
    try:
        return page.evaluate("""(sel) => {
            let el;
            if (sel.startsWith('TEXT:')) {
                const t=sel.slice(5);
                for (const e of document.querySelectorAll('div,span,button,a')) {
                    if ((e.innerText||'').trim()===t) { el=e; break; }
                }
            } else {
                el = document.querySelector(sel);
            }
            if (!el) return 'not found';
            el.scrollIntoView({block:'center'});
            el.dispatchEvent(new MouseEvent('click',{bubbles:true,cancelable:true,view:window}));
            return 'clicked:' + ((el.className||'').toString().slice(0,30));
        }""", selector_or_js)
    except Exception as e:
        return str(e)


def main():
    p = sync_playwright().start()
    browser=None
    try:
        browser = p.chromium.connect_over_cdp(CDP)
        page = browser.contexts[0].pages[0]
        dump(page, "当前状态")
        # 先按 Escape 关掉话题建议浮层
        page.keyboard.press("Escape")
        time.sleep(1)
        dump(page, "按Escape后")

        # 尝试多种封面入口
        attempts = [
            "TEXT:设置封面",
            "TEXT:上传封面",
            "TEXT:更换封面",
            "TEXT:PK封面",
            "TEXT:添加封面",
            # 常见类名
            '[class*="cover"]',
            '[class*="upload"]',
        ]
        for a in attempts:
            log(f"\n尝试点击: {a}")
            r = click_any(page, a)
            log(f"  -> {r}")
            time.sleep(3)
            dump(page, f"点击后")
            page.keyboard.press("Escape")
            time.sleep(0.5)
    except Exception as e:
        log(f"[ERROR] {e}"); import traceback; traceback.print_exc()
    finally:
        if browser:
            try: browser.close()
            except Exception: pass
        p.stop()

if __name__ == "__main__":
    main()
