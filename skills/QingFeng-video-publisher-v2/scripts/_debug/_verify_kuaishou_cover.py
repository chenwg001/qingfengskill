#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
快手封面生效硬核验：截取发布页封面区，分析主色。
用法: python _verify_kuaishou_cover.py <输出png路径>
"""
import os, sys, time

for _k in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY",
           "all_proxy", "ALL_PROXY"):
    os.environ.pop(_k, None)

from playwright.sync_api import sync_playwright

CDP_URL = "http://127.0.0.1:9222"

def log(m): print(m, flush=True)

def main():
    out = sys.argv[1] if len(sys.argv) > 1 else r"D:\chenw\_ks_cover_test\cover_verify.png"
    os.makedirs(os.path.dirname(out) or '.', exist_ok=True)
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
        page.evaluate("""()=>{document.querySelectorAll('#react-joyride-portal').forEach(e=>e.remove());}""")
        time.sleep(1)

        # 截封面区
        el = page.query_selector('[class*="_default-cover"]')
        if el:
            try:
                el.screenshot(path=out)
                log(f"✅ 封面区截图: {out}")
            except Exception as e:
                log(f"  封面区截图失败: {e}")
                page.screenshot(path=out, full_page=False)
        else:
            log("未找到封面区，截全页")
            page.screenshot(path=out, full_page=False)

        # 分析主色
        try:
            from PIL import Image
            im = Image.open(out).convert('RGB')
            w, h = im.size
            log(f"  截图尺寸: {w}x{h}")
            small = im.resize((32, 32))
            # 取中心区域（避开边框）
            px = small.load()
            from collections import Counter
            cnt = Counter()
            for y in range(6, 26):
                for x in range(6, 26):
                    cnt[px[x, y]] += 1
            top = cnt.most_common(5)
            log("  主色 TOP5:")
            for c, n in top:
                log(f"    RGB{c}  {n} px")
            r, g, b = top[0][0]
            if r > g + 40 and r > b + 40:
                log("  🔴 判定：偏红 → 对应 test_A (红)")
            elif g > r + 20 and g > b + 20:
                log("  🟢 判定：偏绿 → 对应 test_B (绿)")
            elif b > r + 20 and b > g + 20:
                log("  🔵 判定：偏蓝 → 对应 test_C (蓝)")
            else:
                log("  ⚪ 判定：非纯色/其他（可能是视频帧）")
        except Exception as e:
            log(f"  颜色分析失败: {e}")
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
