#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
快手封面编辑器探查（排错用）：点击默认封面 → dump 弹窗结构 → 找上传入口。
用法: python _probe_kuaishou_cover.py ["图片路径"（可选，给则尝试注入）]
"""
import os, sys, time

for _k in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY",
           "all_proxy", "ALL_PROXY"):
    os.environ.pop(_k, None)

from playwright.sync_api import sync_playwright

CDP_URL = "http://127.0.0.1:9222"

def log(m): print(m, flush=True)

def dismiss_joyride(page):
    """
    【关键坑】快手发布页有 react-joyride 新手引导浮层（#react-joyride-portal），
    overlay/spotlight 会拦截所有 pointer events，导致任何 click 超时。
    必须先移除该浮层再操作。
    """
    try:
        n = page.evaluate("""() => {
            let cnt = 0;
            document.querySelectorAll('#react-joyride-portal, .react-joyride__overlay, .react-joyride__spotlight').forEach(e => {
                e.remove(); cnt++;
            });
            return cnt;
        }""")
        if n:
            log(f"🧹 已移除 react-joyride 引导浮层 {n} 个节点")
        return n
    except Exception as e:
        log(f"  移除引导浮层失败: {e}")
        return 0

def js_click(page, sel):
    """兜底：用 JS 直接派发点击，绕过遮挡检查"""
    try:
        ok = page.evaluate("""(sel) => {
            const el = document.querySelector(sel);
            if (!el) return false;
            el.scrollIntoView({block:'center'});
            el.dispatchEvent(new MouseEvent('click', {bubbles:true, cancelable:true, view:window}));
            return true;
        }""", sel)
        return ok
    except Exception as e:
        log(f"  js_click 失败: {e}")
        return False

def dump_state(page, tag=""):
    log(f"\n===== {tag} | url={page.url} =====")
    try:
        # 弹窗 / modal
        rows = page.evaluate("""() => {
            const out = [];
            const sels = ['.ant-modal','[class*=modal]','[class*=Modal]','[class*=dialog]','[class*=Dialog]','[class*=upload]','[class*=Upload]'];
            sels.forEach(s => {
                document.querySelectorAll(s).forEach(e => {
                    const r = e.getBoundingClientRect();
                    if (r.width < 20) return;
                    out.push({sel:s, tag:e.tagName, cls:(e.className||'').toString().slice(0,60),
                              rect:[Math.round(r.x),Math.round(r.y),Math.round(r.width),Math.round(r.height)],
                              txt:(e.innerText||'').trim().slice(0,120).replace(/\\n/g,' | ')});
                });
            });
            return out.slice(0, 25);
        }""")
        log(f"[弹窗/上传容器] {len(rows)} 个")
        for r in rows:
            log(f"  <{r['tag']}> [{r['sel']}] cls='{r['cls']}' rect={r['rect']}")
            log(f"      txt='{r['txt']}'")
    except Exception as e:
        log(f"  err {e}")
    try:
        rows = page.evaluate("""() => {
            const out = [];
            document.querySelectorAll('input[type=file]').forEach(e => {
                out.push({acc:(e.getAttribute('accept')||'').slice(0,60)});
            });
            return out;
        }""")
        log(f"[file input] {len(rows)} 个")
        for r in rows: log(f"  accept='{r['acc']}'")
    except Exception as e: log(f"  err {e}")
    try:
        # 含关键字的可点文字
        keys = ["上传", "本地", "裁剪", "确定", "完成", "保存", "取消", "推荐", "自定义", "更换"]
        body = page.inner_text("body", timeout=2500)
        hit = [k for k in keys if k in body]
        log(f"[body 关键字命中] {hit}")
        log(f"[body 长度] {len(body)}")
        log("[body 前400]\n" + body[:400].replace('\n\n', '\n'))
    except Exception as e: log(f"  err {e}")

def main():
    img = sys.argv[1] if len(sys.argv) > 1 else None
    p = sync_playwright().start()
    browser = None
    try:
        browser = p.chromium.connect_over_cdp(CDP_URL)
        ctx = browser.contexts[0] if browser.contexts else browser.new_context()
        page = None
        for pg in ctx.pages:
            if "kuaishou.com" in (pg.url or "") and "publish" in (pg.url or ""):
                page = pg; break
        if page is None:
            for pg in ctx.pages:
                if "kuaishou.com" in (pg.url or ""):
                    page = pg; break
        if page is None:
            log("[FAIL] 未找到快手发布页"); return
        try: page.bring_to_front()
        except: pass
        log(f"页面: {page.url}")

        # 先清掉新手引导浮层（否则点击被 overlay 拦截）
        dismiss_joyride(page)
        time.sleep(1)

        # 点击默认封面区
        log("\n>>> 点击默认封面区 _default-cover")
        clicked = False
        for sel in ['[class*="_default-cover"]', '[class*="_cover-full-editor"]']:
            # 1) 正常点击
            try:
                el = page.query_selector(sel)
                if el and el.is_visible():
                    el.click(timeout=5000)
                    log(f"✅ 点击 {sel}")
                    clicked = True
                    break
            except Exception as e:
                log(f"  常规点击 {sel} 失败，改用 force/js: {str(e)[:80]}")
            # 2) force 点击
            try:
                el = page.query_selector(sel)
                if el:
                    el.click(timeout=5000, force=True)
                    log(f"✅ force 点击 {sel}")
                    clicked = True
                    break
            except Exception as e:
                log(f"  force 点击失败: {str(e)[:80]}")
            # 3) JS 派发
            if js_click(page, sel):
                log(f"✅ JS 点击 {sel}")
                clicked = True
                break
        if not clicked:
            log("⚠️ 未点到封面区")
        time.sleep(4)
        dump_state(page, "点击封面后")

        if img and os.path.exists(img):
            log(f"\n>>> 尝试向 image file input 注入封面: {img}")
            try:
                ins = page.query_selector_all('input[type="file"]')
                tgt = None
                for inp in ins:
                    acc = (inp.get_attribute('accept') or '').lower()
                    if 'image' in acc:
                        tgt = inp; break
                if tgt:
                    tgt.set_input_files(img)
                    log("✅ 已注入")
                    time.sleep(5)
                    dump_state(page, "注入封面后")
                else:
                    log("⚠️ 未找到 image file input")
            except Exception as e:
                log(f"  注入失败: {e}")
                import traceback; traceback.print_exc()
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
