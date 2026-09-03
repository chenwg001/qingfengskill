#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""小红书：细探标题/正文/封面/话题/发布按钮真实 DOM（修正版）"""
import os, sys, time
for _k in ("http_proxy","https_proxy","HTTP_PROXY","HTTPS_PROXY","all_proxy","ALL_PROXY"):
    os.environ.pop(_k, None)
from playwright.sync_api import sync_playwright

CDP = "http://127.0.0.1:9222"
UPLOAD_URL = "https://creator.xiaohongshu.com/publish/publish"

def log(m): print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)

def deep(page, tag=""):
    info = page.evaluate("""() => {
        const out = {bodyLen: document.body.innerText.length, edit:[], ce:[], cover:[], publish:[], files:[]};
        const COVER = ['设置封面','PK封面','更换封面','上传封面','选择封面'];
        const PUB = ['发布','存草稿','保存','立即发布','保存草稿'];
        // 标题 input
        document.querySelectorAll('input').forEach(el=>{
            const ph=el.getAttribute('placeholder')||'';
            if(ph) out.edit.push({ph, cls:(el.className||'').toString().slice(0,50)});
        });
        // contenteditable
        document.querySelectorAll('[contenteditable=\"true\"]').forEach(el=>{
            const r=el.getBoundingClientRect();
            out.ce.push({ph: el.getAttribute('data-placeholder')||el.getAttribute('placeholder')||'',
                cls:(el.className||'').toString().slice(0,50), w:Math.round(r.width), h:Math.round(r.height)});
        });
        // 封面上传 input（accept image）
        document.querySelectorAll('input[type=file]').forEach(f=>{
            const acc=(f.getAttribute('accept')||'');
            if(acc.indexOf('image')>=0){
                const m=f.closest('.semi-modal,[class*=modal],[class*=dialog]');
                out.files.push({accept:acc.slice(0,30), inModal:!!m});
            }
        });
        // 封面对应文本
        document.querySelectorAll('div,span,button,a').forEach(el=>{
            const t=(el.innerText||'').trim();
            if(t && t.length<=12 && COVER.indexOf(t)>=0){
                const cs=getComputedStyle(el);
                out.cover.push({t, cur:cs.cursor, cls:(el.className||'').toString().slice(0,40)});
            }
        });
        // 发布/存草稿按钮
        document.querySelectorAll('button,[class*=btn]').forEach(el=>{
            const t=(el.innerText||'').trim();
            if(t && t.length<=10 && PUB.indexOf(t)>=0){
                const cs=getComputedStyle(el);
                out.publish.push({t, cur:cs.cursor, cls:(el.className||'').toString().slice(0,40)});
            }
        });
        return out;
    }""")
    log(f"\n=== {tag} bodyLen={info['bodyLen']} ===")
    log("标题inputs:")
    for e in info['edit']: log(f"   ph='{e['ph']}' cls={e['cls']}")
    log(f"contenteditable({len(info['ce'])}):")
    for e in info['ce']: log(f"   ph='{e['ph']}' cls={e['cls']} {e['w']}x{e['h']}")
    log(f"封面image input({len(info['files'])}):")
    for f in info['files']: log(f"   accept='{f['accept']}' inModal={f['inModal']}")
    log("封面文本:")
    for c in info['cover']: log(f"   {c['t']} cur={c['cur']} cls={c['cls']}")
    log("发布/草稿按钮:")
    for b in info['publish']: log(f"   {b['t']} cur={b['cur']} cls={b['cls']}")
    return info

def main():
    p = sync_playwright().start()
    browser=None
    try:
        browser = p.chromium.connect_over_cdp(CDP)
        ctx = browser.contexts[0]
        page = ctx.pages[0]
        if "creator.xiaohongshu.com" not in (page.url or ""):
            page.goto(UPLOAD_URL, wait_until="domcontentloaded", timeout=30000)
            time.sleep(6)
        deep(page, "当前表单")
    except Exception as e:
        log(f"[ERROR] {e}"); import traceback; traceback.print_exc()
    finally:
        if browser:
            try: browser.close()
            except Exception: pass
        p.stop()

if __name__ == "__main__":
    main()
