r"""
等待 B 站登录 → 登录成功后自动 dump 投稿页真实 DOM

用法：
    env -u http_proxy -u https_proxy -u HTTP_PROXY -u HTTPS_PROXY \
      "C:\Users\chenw\.workbuddy\binaries\python\envs\default\Scripts\python.exe" \
      _wait_login_bilibili.py

环境变量：
    BILI_WAIT=180   最长等待秒数（默认 180）

登录成功后输出：URL / file input 清单 / 可点文本 / contenteditable / input-textarea
"""
import os
import sys
import time

from playwright.sync_api import sync_playwright

CDP = "http://127.0.0.1:9222"
UPLOAD_URL = "https://member.bilibili.com/platform/upload/video/frame"
WAIT = int(os.environ.get("BILI_WAIT", "180"))


def log(m=""):
    print(m, flush=True)


def section(t):
    log("\n" + "=" * 60)
    log(f"  {t}")
    log("=" * 60)


def is_logged_in(page):
    url = page.url or ""
    title = ""
    try:
        title = page.title()
    except Exception:
        pass
    # 登录页特征：URL 含 passport 或 title 为「账号登录」
    if "passport.bilibili.com" in url:
        return False
    if "账号登录" in title:
        return False
    return "member.bilibili.com" in url


def dump(page):
    section("1. 页面状态")
    log(f"  URL   : {page.url}")
    log(f"  Title : {page.title()}")

    section("2. file input")
    fis = page.evaluate(
        """() => [...document.querySelectorAll('input[type=file]')].map((el, i) => {
            let p = el.parentElement, cls = '', k = 0;
            while (p && k < 4) {
                cls += (cls ? ' < ' : '') + (p.className || p.tagName).toString().slice(0, 40);
                p = p.parentElement; k++;
            }
            const r = el.getBoundingClientRect();
            return {i, accept: el.getAttribute('accept') || '',
                    size: Math.round(r.width) + 'x' + Math.round(r.height),
                    visible: r.width > 2 && r.height > 2, parentCls: cls};
        })""")
    if not fis:
        log("  （无 file input）")
    for f in fis:
        log(f"  #{f['i']} accept={f['accept']!r} {f['size']} visible={f['visible']}")
        log(f"      父链: {f['parentCls'][:120]}")

    section("3. 可点文本（叶子节点）")
    items = page.evaluate(
        """() => {
            const out = [], seen = new Set();
            for (const el of document.querySelectorAll(
                    'div,span,button,li,a,p,label')) {
                const t = (el.innerText || '').trim();
                if (!t || t.length > 26 || t.includes('\\n')) continue;
                if (el.children.length > 0) continue;
                const r = el.getBoundingClientRect();
                if (r.width < 8 || r.height < 8) continue;
                const st = getComputedStyle(el);
                if (st.visibility === 'hidden' || st.display === 'none') continue;
                if (seen.has(t)) continue;
                seen.add(t);
                out.push({text: t, tag: el.tagName,
                          cls: (el.className || '').toString().slice(0, 60),
                          size: Math.round(r.width) + 'x' + Math.round(r.height),
                          cursor: st.cursor, onclick: !!el.onclick});
            }
            return out.slice(0, 50);
        }""")
    for it in items:
        flag = "  ✅" if (it["cursor"] == "pointer" or it["onclick"]) else ""
        log(f"  {it['text'][:24]:<26} {it['tag']:<7} {it['size']:<11}"
            f" cursor={it['cursor']:<11}{flag}")
        if it["cls"]:
            log(f"      cls={it['cls']}")

    section("4. contenteditable / 输入框")
    boxes = page.evaluate(
        """() => {
            const out = [];
            document.querySelectorAll('[contenteditable]').forEach(el => {
                const r = el.getBoundingClientRect();
                out.push({kind: 'contenteditable', tag: el.tagName,
                          cls: (el.className || '').toString().slice(0, 60),
                          ph: el.getAttribute('data-placeholder') || '',
                          size: Math.round(r.width) + 'x' + Math.round(r.height)});
            });
            document.querySelectorAll('input:not([type=file]), textarea')
                .forEach(el => {
                const r = el.getBoundingClientRect();
                if (r.width < 4 || r.height < 4) return;
                out.push({kind: el.tagName.toLowerCase(), tag: el.tagName,
                          cls: (el.className || '').toString().slice(0, 60),
                          ph: el.getAttribute('placeholder') || '',
                          maxlength: el.getAttribute('maxlength') || '',
                          size: Math.round(r.width) + 'x' + Math.round(r.height)});
            });
            return out.slice(0, 30);
        }""")
    if not boxes:
        log("  （无可见输入框）")
    for b in boxes:
        log(f"  [{b['kind']}] {b['size']} maxlen={b.get('maxlength','')} ph={b['ph']!r}")
        log(f"      cls={b['cls']}")

    section("5. body 文本预览（前 700 字）")
    log(page.evaluate(
        "() => (document.body.innerText || '').replace(/\\n{2,}/g, '\\n')"
        ".slice(0, 700)"))


def activate_window(page):
    """把浏览器窗口从最小化状态拉到前台（否则用户看不到二维码）"""
    try:
        s = page.context.new_cdp_session(page)
        tid = s.send("Target.getTargetInfo")["targetInfo"]["targetId"]
        info = s.send("Browser.getWindowForTarget", {"targetId": tid})
        s.send("Browser.setWindowBounds",
               {"windowId": info["windowId"], "bounds": {"windowState": "normal"}})
        log("  （已把浏览器窗口切到前台）")
    except Exception as e:
        log(f"  （窗口激活跳过: {e}）")


def main():
    p = sync_playwright().start()
    browser = p.chromium.connect_over_cdp(CDP)
    try:
        page = browser.contexts[0].pages[0]
        activate_window(page)
        if "member.bilibili.com" not in (page.url or ""):
            page.goto(UPLOAD_URL, wait_until="domcontentloaded", timeout=45000)
        time.sleep(2)
        activate_window(page)

        if is_logged_in(page):
            log("已登录，直接 dump")
        else:
            log(f"未登录。请在浏览器里扫码/密码登录 B 站，最长等待 {WAIT} 秒...")
            log(f"登录页: {page.url}")
            t0 = time.time()
            ok = False
            while time.time() - t0 < WAIT:
                time.sleep(3)
                try:
                    if is_logged_in(page):
                        ok = True
                        break
                except Exception:
                    pass
            if not ok:
                log("[TIMEOUT] 仍未检测到登录")
                return 1
            log(f"✅ 检测到登录（{int(time.time() - t0)}s）")
            time.sleep(5)

        # 确保在投稿页
        if "upload/video" not in (page.url or ""):
            log(f"导航到投稿页: {UPLOAD_URL}")
            page.goto(UPLOAD_URL, wait_until="domcontentloaded", timeout=45000)
            time.sleep(8)

        dump(page)
        log("\n完成。照着上面的真实 DOM 写脚本。")
        return 0
    finally:
        browser.close()
        p.stop()


if __name__ == "__main__":
    sys.exit(main())
