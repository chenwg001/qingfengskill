#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""小红书：上传视频后 dump 表单真实 DOM（标题/正文/封面/话题/按钮）"""
import os, sys, time, re
for _k in ("http_proxy","https_proxy","HTTP_PROXY","HTTPS_PROXY","all_proxy","ALL_PROXY"):
    os.environ.pop(_k, None)
from playwright.sync_api import sync_playwright

CDP = "http://127.0.0.1:9222"
UPLOAD_URL = "https://creator.xiaohongshu.com/publish/publish"

def log(m): print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)

def dump_summary(page, tag=""):
    page.evaluate("""()=>{const ps=document.querySelectorAll('#react-joyride-portal, .react-joyride__overlay, .semi-overlay, .semi-modal-mask');}""")
    info = page.evaluate("""() => {
        const out = {url: location.href, bodyLen: document.body.innerText.length,
            files: [], texts: [], editables: []};
        const files = document.querySelectorAll('input[type=file]');
        for (const f of files) {
            out.files.push({accept:(f.getAttribute('accept')||'').slice(0,60),
                inModal: !!f.closest('.semi-modal, .ant-modal, [class*=modal], [class*=dialog]')});
        }
        // 可编辑区
        for (const el of document.querySelectorAll('textarea, [contenteditable="true"], input')) {
            const ph = el.getAttribute('placeholder')||'';
            const cls = (el.className||'').toString().slice(0,40);
            const tag = el.tagName.toLowerCase();
            if (ph || tag==='textarea' || tag==='input') {
                out.editables.push({tag, ph, cls:cls.slice(0,30)});
            }
        }
        // 可点文本（按钮）
        const seen = new Set();
        for (const el of document.querySelectorAll('div,span,button,a,li')) {
            const t = (el.innerText||'').trim();
            const r = el.getBoundingClientRect();
            if (t && r.width>5 && r.height>5 && !seen.has(t) && t.length<=20) {
                seen.add(t);
                const cs = getComputedStyle(el);
                out.texts.push({t, w:Math.round(r.width), h:Math.round(r.height),
                    cur: cs.cursor, click: cs.cursor==='pointer'||el.tagName==='BUTTON'});
            }
        }
        return out;
    }""")
    log(f"\n=== dump {tag} ===")
    log(f"URL: {info['url']}  bodyLen={info['bodyLen']}")
    log(f"file inputs({len(info['files'])}):")
    for i,f in enumerate(info['files']):
        log(f"  #{i} accept='{f['accept']}' inModal={f['inModal']}")
    log(f"editables({len(info['editables'])}):")
    for e in info['editables']:
        log(f"  {e['tag']} ph='{e['ph']}' cls={e['cls']}")
    log(f"texts({len(info['texts'])}):")
    for t in info['texts']:
        mark = '✅' if t['click'] else '  '
        log(f"  {mark} {t['t']}  {t['w']}x{t['h']} cur={t['cur']}")
    return info

def main():
    video = sys.argv[1]
    timeout = int(sys.argv[2]) if len(sys.argv)>2 else 240
    p = sync_playwright().start()
    browser = None
    try:
        browser = p.chromium.connect_over_cdp(CDP)
        ctx = browser.contexts[0] if browser.contexts else browser.new_context()
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        if "creator.xiaohongshu.com" not in (page.url or ""):
            page.goto(UPLOAD_URL, wait_until="domcontentloaded", timeout=30000)
        time.sleep(6)
        dump_summary(page, "初始上传页")

        # 上传视频
        log("上传视频...")
        inp = page.query_selector('input[type="file"]')
        if not inp:
            log("[FAIL] 未找到 video input")
            return
        inp.set_input_files(video)
        log("✅ 已注入视频，等待处理...")
        # 轮询直到出现标题输入框
        t0 = time.time()
        done = False
        while time.time() - t0 < timeout:
            info = dump_summary(page, f"轮询{int(time.time()-t0)}s")
            # 出现 placeholder 含'标题' 即上传完成
            has_title = any('标题' in (e['ph'] or '') or '标题' in e['cls'] for e in info['editables'])
            has_draft = any(t['t'] in ('存草稿','草稿','发布','保存') for t in info['texts'])
            if has_title or has_draft:
                log(f"✅ 表单已就绪 (标题区={has_title}, 按钮区={has_draft})")
                done = True
                break
            time.sleep(8)
        if not done:
            log("⚠️ 超时未检测到表单就绪，dump 最后一次")
            dump_summary(page, "超时")
    except Exception as e:
        log(f"[ERROR] {e}")
        import traceback; traceback.print_exc()
    finally:
        if browser:
            try: browser.close()
            except Exception: pass
        p.stop()

if __name__ == "__main__":
    main()
