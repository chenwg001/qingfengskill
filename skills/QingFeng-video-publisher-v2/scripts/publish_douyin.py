#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
抖音视频发布脚本 V2（Playwright + CDP）
修复：不用 with 语句，用 browser.close() 只断开连接不关闭浏览器
封面设置：委托给同目录的 set_douyin_cover.py（2026-09-01 实测跑通版）

用法: python publish_douyin.py --video <视频> --cover-4x3 <4:3封面> --cover-3x4 <3:4封面> --title "<标题>" --desc "<简介>"
"""

import argparse
import time
import os
import sys

# 【坑】必须在 import playwright 前清掉代理环境变量，否则连本地 CDP 会被
# 127.0.0.1:6507 代理转发成 502（详见 SKILL.md「已知坑」）
for _k in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY",
           "all_proxy", "ALL_PROXY"):
    os.environ.pop(_k, None)

from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import set_douyin_cover  # noqa: E402  封面设置专用模块

CDP_URL = "http://127.0.0.1:9222"
DOUYIN_POST_URL = "https://creator.douyin.com/creator-micro/content/post/video"

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

def set_both_covers(page, cover_3x4, cover_4x3, shot_dir=None):
    """
    设置竖封面 3:4 与横封面 4:3。

    实现委托给同目录的 set_douyin_cover.set_both_covers（2026-09-01 实测跑通）：
      JS 强制显示 hover 按钮 → 点槽位内「选择/编辑封面」→ 在弹窗内主上传区
      set_input_files 注入图片路径 → 点弹窗内「完成」。
    不要再回到旧的「找 text=选择封面 + ReactCrop 裁剪 + 排除 modal 内按钮」写法，
    那套方向会错位、编辑器还关不上。
    """
    return set_douyin_cover.set_both_covers(
        page, cover_4x3=cover_4x3, cover_3x4=cover_3x4, shot_dir=shot_dir
    )

def set_ai_declaration(page, trigger="自主声明", option="内容由AI生成"):
    """
    【声明环节】勾选平台「内容由AI生成」AI 声明。
    平台真实入口名（2026-09-02 用户确认）：抖音=「自主声明」、快手=「作者声明」。
    流程：① 点开声明面板(trigger) → ② 在展开面板里选「内容由AI生成」选项(option)。
    best-effort：任一步找不到只告警、不中断发布；下次实跑据真实 DOM 微调。
    """
    log(f"勾选 AI 声明（{trigger} → {option}）...")
    # ① 展开声明面板
    try:
        r1 = page.evaluate("""(txt) => {
            const els = [...document.querySelectorAll('button, div, span, label, li, a, p')];
            const t = els.find(e => { const s = (e.innerText||'').replace(/\\s+/g,''); return s===txt || s.includes(txt); });
            if (t) { t.click(); return 'opened'; }
            return 'no-trigger';
        }""", [trigger])
        log(f"  展开声明面板({trigger}): {r1}")
    except Exception as e:
        log(f"  [WARN] 展开声明面板失败: {e}")
    time.sleep(1.5)
    # ② 选择「内容由AI生成」选项（面板展开后命中；若面板本就展开也能直接命中）
    try:
        r2 = page.evaluate("""(opt) => {
            const els = [...document.querySelectorAll('label, div, li, span, button')];
            const cand = els.filter(e => { const s=(e.innerText||'').replace(/\\s+/g,''); return s.includes(opt) || s.includes('AI生成'); });
            for (const c of cand) {
                const box = c.querySelector('input[type=checkbox], input[type=radio]');
                if (box) { if (!box.checked) box.click(); return 'checkbox:' + (box.checked ? 'checked' : 'was'); }
                c.click(); return 'option-clicked';
            }
            return 'no-option';
        }""", [option])
        log(f"  勾选声明项({option}): {r2}")
    except Exception as e:
        log(f"  [WARN] 勾选声明项失败: {e}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--cover-4x3", required=True)
    ap.add_argument("--cover-3x4", required=True)
    ap.add_argument("--title", default="")
    ap.add_argument("--desc", default="")
    ap.add_argument("--save-draft", action="store_true")
    ap.add_argument("--cover-shots", action="store_true",
                    help="保存封面设置过程截图到视频同目录（排错用）")
    args = ap.parse_args()

    for f in [args.video, args.cover_4x3, args.cover_3x4]:
        if not os.path.exists(f):
            log(f"[FAIL] 文件不存在: {f}")
            sys.exit(1)

    # 手动管理 playwright，不用 with（避免 with 退出时 browser.close() 关掉浏览器）
    p = sync_playwright().start()
    browser = None
    try:
        browser = p.chromium.connect_over_cdp(CDP_URL)
        context = browser.contexts[0] if browser.contexts else browser.new_context()

        page = None
        for pg in context.pages:
            if "creator.douyin.com" in (pg.url or ""):
                page = pg
                break
        if page is None:
            for pg in context.pages:
                if "douyin.com" in (pg.url or ""):
                    page = pg
                    break
        if not page:
            page = context.new_page()

        log(f"标签页: {page.url}")

        # 导航到发布页：抖音是 SPA，**禁止直接 goto 发布页 URL**（会停在框架/首页、
        # 不渲染上传组件，从而"未找到视频 input"）。必须从创作者首页点「发布视频 /
        # 高清发布」按钮触发路由跳转（v1 早期记录 2026-04 已验证：直接 goto 是错的）。
        log("导航到抖音创作者首页...")
        page.goto("https://creator.douyin.com/", wait_until="domcontentloaded", timeout=30000)
        time.sleep(4)

        if "login" in page.url or "passport" in page.url:
            log("[FAIL] 未登录抖音")
            return

        # 点「发布视频 / 高清发布」触发 SPA 跳转
        log("点击发布入口按钮进入发布表单页...")
        triggered = False
        for txt in ["发布视频", "高清发布", "发布"]:
            try:
                btns = page.query_selector_all(f'text={txt}')
                for b in btns:
                    if b.is_visible():
                        b.click()
                        triggered = True
                        break
            except Exception:
                pass
            if triggered:
                break
        # 等 SPA 跳转到发布表单页
        for _ in range(20):
            if "content/post/video" in page.url:
                break
            time.sleep(1)
        # fallback：极少数情况下直接 goto 也能成功
        if "content/post/video" not in page.url:
            log("SPA 跳转未触发，回退直接 goto 发布页...")
            page.goto(DOUYIN_POST_URL, wait_until="domcontentloaded", timeout=30000)
            time.sleep(5)

        # 上传视频
        log("上传视频...")
        inputs = page.query_selector_all('input[type="file"]')
        video_input = None
        for inp in inputs:
            acc = inp.get_attribute("accept") or ""
            if "video" in acc.lower() or ".mp4" in acc.lower():
                video_input = inp
                break
        if not video_input and inputs:
            video_input = inputs[0]
        if not video_input:
            log("[FAIL] 未找到视频 input")
            return

        video_input.set_input_files(args.video)
        log("视频已设置，等待处理...")
        time.sleep(10)

        for i in range(40):
            time.sleep(3)
            try:
                c = page.inner_text("body", timeout=2000)
                if "重新上传" in c:
                    log("[OK] 视频上传完成")
                    break
            except:
                pass
        time.sleep(3)

        # 填写标题
        if args.title:
            ti = page.query_selector('input[placeholder*="标题"]')
            if ti:
                ti.click()
                ti.fill("")
                ti.type(args.title, delay=20)
                log("标题已填写")

        # 填写简介
        if args.desc:
            di = page.query_selector('div[contenteditable="true"][data-placeholder*="简介"]')
            if di:
                di.click()
                di.fill("")
                di.type(args.desc, delay=10)
                log("简介已填写")

        time.sleep(2)

        # 设置封面（走 set_douyin_cover 实测跑通版）
        shot_dir = os.path.dirname(args.video) if args.cover_shots else None
        set_both_covers(page, args.cover_3x4, args.cover_4x3, shot_dir=shot_dir)
        time.sleep(2)

        # AI 声明（内容由AI生成）
        set_ai_declaration(page)
        time.sleep(1)

        # 截图
        ts = time.strftime('%Y%m%d_%H%M%S')
        shot = os.path.join(os.path.dirname(args.video), f'douyin_publish_{ts}.png')
        page.screenshot(path=shot, full_page=True)
        log(f"截图: {shot}")

        # 兜底：关掉「设置竖封面」引导弹窗（它常在所有封面设完、临点暂存时才弹出，
        # 会拦截「暂存离开」按钮），确保暂存不被遮挡
        set_douyin_cover.dismiss_vertical_cover_prompt(page)

        # 暂存离开
        if args.save_draft:
            log("暂存离开...")
            for txt in ["暂存离开", "存草稿", "保存草稿"]:
                btns = page.query_selector_all(f'text={txt}')
                for b in btns:
                    if b.is_visible():
                        b.click()
                        log(f"[OK] 点击: {txt}")
                        time.sleep(3)
                        break
                else:
                    continue
                break

        log("\n=== 完成，浏览器保持打开 ===")

    except Exception as e:
        log(f"[ERROR] {e}")
        import traceback
        traceback.print_exc()
    finally:
        # 关键：只断开连接，不关闭浏览器！
        if browser:
            try:
                browser.close()
            except:
                pass
        p.stop()

if __name__ == "__main__":
    main()
