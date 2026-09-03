#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
小红书视频发布脚本（Playwright + CDP）

流程（竖屏 9:16 视频 → 小红书）：
  导航创作中心 → 上传视频 → 填标题 → 填正文(ProseMirror, 复制粘贴)
  → 追加话题(#xxx) → 封面区检查（网页版支持上传自定义封面，hover 当前封面帧打开编辑器）
  注意：小红书网页创作中心**没有「暂存离开/存草稿」按钮**，唯一按钮是「发布笔记」。
  按铁律不点「发布笔记」，表单填好后网页会自动存为草稿，保持页面打开由你手动发布。

与 B站/快手的关键差异：
1. 标题、正文是两个独立框（正文是 Tiptap ProseMirror）
2. 话题：在正文里直接打 "#话题词" 即可触发话题标签（空格/回车确认）
3. 封面：网页创作中心【支持】上传自定义封面图（hover 当前封面帧 .default.column → 点编辑封面 → 上传本地图）
4. 创作中心：https://creator.xiaohongshu.com/publish/publish

用法:
  python publish_xiaohongshu.py --video <竖屏视频> --cover <3:4封面> \
      --title "标题" --desc "正文" --tags "教育,王阳明" \
      [--shot-dir <目录>] [--force-upload]
"""
import argparse
import os
import re
import sys
import time

for _k in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY",
           "all_proxy", "ALL_PROXY"):
    os.environ.pop(_k, None)

from playwright.sync_api import sync_playwright

CDP_URL = "http://127.0.0.1:9222"
UPLOAD_URL = "https://creator.xiaohongshu.com/publish/publish"
SHOT_DIR = "D:/chenw/AgentSpace/outputs/web"


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def safe_filename(s):
    return re.sub(r'[:*?"<>|/\r\n\t]', '-', str(s))


def dismiss_overlays(page):
    page.evaluate("""()=>{
        document.querySelectorAll('#react-joyride-portal, .react-joyride__overlay, .semi-overlay, .semi-modal-mask, [class*=guide]')
            .forEach(e=>{ try{e.remove();}catch(_){} });
    }""")


def dismiss_draft_modal(page):
    """刷新后若弹「有未发布的草稿」框，点「放弃」以干净重发；无则跳过。
    用真实鼠标点击（Vue 组件对合成点击会静默失败）。"""
    try:
        if real_click_button_by_text(page, "放弃", timeout=4):
            log("  已点「放弃」关闭草稿弹窗")
            time.sleep(1.5)
    except Exception as e:
        log(f"  dismiss_draft_modal 跳过: {e}")


def click_by_text(page, text, timeout=8):
    """精确文本点击，优先叶子节点（children.length===0 才是真按钮）"""
    try:
        return page.evaluate("""([txt]) => {
            const cands = [];
            for (const el of document.querySelectorAll('div,span,button,li,a')) {
                const t = (el.innerText || '').trim();
                if (t === txt && el.getBoundingClientRect().width > 5) cands.push(el);
            }
            if (!cands.length) return '';
            const target = cands.find(e => e.children.length === 0) || cands[cands.length-1];
            target.scrollIntoView({block:'center'});
            target.dispatchEvent(new MouseEvent('click',{bubbles:true,cancelable:true,view:window}));
            return 'ok';
        }""", [text])
    except Exception as e:
        log(f"  click_by_text({text}) 失败: {e}")
        return ''


def real_click_button_by_text(page, text, timeout=8):
    """真实鼠标点击文本精确匹配的按钮（Vue 组件要求真实 pointer event）。

    ⚠️ 关键坑（2026-09-02 反复踩）：小红书弹窗里的「应用」「完成」等按钮是 Vue 组件，
    对【真实鼠标 pointer event】敏感——JS 的 `el.click()`、`dispatchEvent` 合成点击，
    甚至 Playwright 的 `get_by_text().click()`，都会【静默失败、弹窗不关】，而脚本
    拿不到任何报错，误以为成功。必须用 `page.mouse.click(x, y)` 发真实鼠标点击才生效。
    本函数：按精确文本 + 可见尺寸在 DOM 里定位按钮 → scrollIntoView 到视口中央 →
    取 boundingBox 中心点坐标 → page.mouse.click 真实点击。"""
    t0 = time.time()
    while time.time() - t0 < timeout:
        rect = page.evaluate("""([txt]) => {
            const els = [...document.querySelectorAll('button,div,span,li,a')];
            const b = els.find(x => {
                const t = (x.textContent||'').trim();
                const r = x.getBoundingClientRect();
                return t === txt && r.width > 5 && r.height > 5;
            });
            if (!b) return null;
            b.scrollIntoView({block:'center', inline:'center'});
            const r = b.getBoundingClientRect();
            return {x: r.x + r.width/2, y: r.y + r.height/2};
        }""", [text])
        if rect:
            page.mouse.click(rect['x'], rect['y'])
            time.sleep(1.0)
            return True
        time.sleep(0.5)
    return False


def upload_video(page, video, timeout=300):
    log("上传视频...")
    inp = page.query_selector('input[type="file"]')
    if not inp:
        log("[FAIL] 未找到 video input")
        return False
    inp.set_input_files(video)
    log("✅ 已注入视频，等待处理（轮询标题框出现）...")
    t0 = time.time()
    while time.time() - t0 < timeout:
        has_title = page.evaluate("""()=>{
            return !!document.querySelector('input[placeholder="填写标题会有更多赞哦"]');
        }""")
        if has_title:
            log("✅ 表单就绪（标题框出现）")
            return True
        time.sleep(6)
    log("[FAIL] 超时未出现表单")
    return False


def fill_title(page, title):
    log("填标题...")
    sel = 'input[placeholder="填写标题会有更多赞哦"]'
    try:
        el = page.wait_for_selector(sel, timeout=15000)
        el.click()
        el.fill("")
        time.sleep(0.5)
        el.fill(title)
        time.sleep(1)
        val = page.evaluate("""()=>document.querySelector('input[placeholder="填写标题会有更多赞哦"]').value""")
        log(f"  标题已填: {val[:30]}{'...' if len(val)>30 else ''}")
        return True
    except Exception as e:
        log(f"  标题填充失败: {e}")
        return False


def fill_body(page, text):
    """小红书正文填充（Tiptap/ProseMirror）：复制粘贴方案。
    核心思路（采纳用户建议「用复制粘贴」）：
      1) 文本写入剪贴板（Clipboard API，失败退回 execCommand('copy')）
      2) JS 聚焦编辑器并把光标放到末尾——**不点几何中心**，彻底规避
         之前 el.click() 点中侧边栏、把整页吸进编辑器的损坏
      3) 清空旧内容：Ctrl+A + Delete（绝不用 Backspace，会合并根节点致整页损坏）
      4) Ctrl+V 粘贴
      5) 校验失败兜底：document.execCommand('insertText')（ProseMirror 原生支持）
    损坏守卫：若编辑器已含“创作服务平台”，说明整页已被吸入，放弃本次交上层重导。"""
    log("填正文（复制粘贴方案）...")
    sel = 'div.tiptap.ProseMirror'
    try:
        el = page.wait_for_selector(sel, timeout=15000)
        guard = page.evaluate("()=>document.querySelector('div.tiptap.ProseMirror').innerText")
        if "创作服务平台" in (guard or ""):
            log("  [FAIL] 编辑器已损坏（含整页侧边栏），放弃填充，需重导")
            return False

        # 1) 写剪贴板
        page.evaluate("""(t)=>{
            try {
                if (navigator.clipboard && navigator.clipboard.writeText) {
                    navigator.clipboard.writeText(t);
                } else {
                    const ta=document.createElement('textarea');
                    ta.value=t; ta.style.position='fixed'; ta.style.opacity='0';
                    document.body.appendChild(ta); ta.focus(); ta.select();
                    document.execCommand('copy'); ta.remove();
                }
            } catch(e){}
        }""", text)
        time.sleep(0.3)

        # 2) 聚焦编辑器 + 光标到末尾（evaluate，不点几何中心）
        page.evaluate("""()=>{
            const el=document.querySelector('div.tiptap.ProseMirror');
            el.focus();
            const s=window.getSelection(); const r=document.createRange();
            r.selectNodeContents(el); r.collapse(false);
            s.removeAllRanges(); s.addRange(r);
        }""")
        time.sleep(0.3)

        # 3) 清空旧内容（Ctrl+A + Delete，不用 Backspace）
        cur = page.evaluate("()=>document.querySelector('div.tiptap.ProseMirror').innerText")
        if cur.strip() not in ("", " ", "\n", None):
            page.keyboard.press("Control+a"); time.sleep(0.2)
            page.keyboard.press("Delete"); time.sleep(0.3)

        # 4) 粘贴
        page.keyboard.press("Control+v"); time.sleep(1.0)
        txt = page.evaluate("()=>document.querySelector('div.tiptap.ProseMirror').innerText")

        # 5) 校验失败兜底：execCommand insertText
        if "创作服务平台" in txt or text[:15] not in txt:
            log("  [WARN] 粘贴校验失败，兜底 execCommand('insertText')")
            page.evaluate("""(t)=>{
                const el=document.querySelector('div.tiptap.ProseMirror'); el.focus();
                const s=window.getSelection(); const r=document.createRange();
                r.selectNodeContents(el); r.collapse(false);
                s.removeAllRanges(); s.addRange(r);
                document.execCommand('insertText', false, t);
            }""", text)
            txt = page.evaluate("()=>document.querySelector('div.tiptap.ProseMirror').innerText")

        log(f"  正文已输入，长度={len(txt)}")
        if "创作服务平台" in txt or text[:15] not in txt:
            log(f"  [FAIL] 正文仍校验失败：{txt[:50]!r}")
            return False
        return len(txt) > 0
    except Exception as e:
        log(f"  正文填充失败: {e}")
        return False


def set_cover(page, cover, shot_dir=None):
    """小红书网页创作中心【支持】上传自定义封面图（2026-09-02 实测验证）。

    流程：hover 当前封面帧 .default.column → 浮现「编辑封面」(.cover-edit-stack)
    → 真实鼠标点击 → 打开「设置封面」图片编辑器弹窗（含 image/* 上传入口）→
    上传本地图 → 真实鼠标点「应用」→ 真实鼠标点「完成」关闭弹窗。

    ⚠️ 关键坑（2026-09-02 收尾时反复踩）：弹窗内的「应用」「完成」是 Vue 组件按钮，
    对【真实 pointer event】敏感——JS 的 `el.click()` / `dispatchEvent` 合成点击、
    甚至 Playwright 的 `get_by_text().click()` 都会【静默失败、弹窗不关】，脚本拿不到
    任何报错，误以为成功（曾出现"日志显示完成、实则卡在弹窗"）。必须用
    `real_click_button_by_text()` 发真实鼠标坐标点击才生效，并轮询"图片上传入口是否
    消失"来校验弹窗真正关闭。

    未提供封面或上传失败时保留视频默认帧，不阻塞发布。"""
    log("设置封面...")
    if not cover or not os.path.exists(cover):
        log("  未指定封面文件，使用视频默认第一帧")
        return True
    if not page.evaluate("()=>!!document.querySelector('.cover-plugin-preview, [class*=cover-plugin]')"):
        log("  [WARN] 未找到封面区，跳过自定义封面")
        return False
    try:
        # 1) hover 当前封面帧，让「编辑封面」按钮浮现
        box = page.locator('.default.column').first.bounding_box()
        if box:
            page.mouse.move(box['x']+box['width']/2, box['y']+box['height']/2)
            time.sleep(0.8)
        stk = page.evaluate("()=>{const e=document.querySelector('.cover-edit-stack'); if(!e) return null; const r=e.getBoundingClientRect(); return {w:Math.round(r.width),h:Math.round(r.height),x:r.x,y:r.y};}")
        if not (stk and stk['w']>0):
            log("  [WARN] 未浮现编辑封面按钮，使用默认第一帧")
            return True
        # 真实鼠标点击「编辑封面」打开弹窗
        page.mouse.click(stk['x']+stk['w']/2, stk['y']+stk['h']/2)
        time.sleep(3)

        # 2) 找弹窗内图片上传入口
        img_input = None
        for fi in page.query_selector_all('input[type=file]'):
            acc = fi.get_attribute('accept') or ''
            if 'image' in acc:
                img_input = fi
                break
        if not img_input:
            log("  [WARN] 弹窗内未找到图片上传入口，使用默认第一帧")
            real_click_button_by_text(page, "完成", timeout=4)  # 兜底关弹窗
            return True
        img_input.set_input_files(cover)
        log("  已注入自定义封面图: " + os.path.basename(cover))
        time.sleep(5)

        # 3) 真实鼠标点「应用」（可选：部分版本无此按钮则跳过）
        if real_click_button_by_text(page, "应用", timeout=4):
            log("  已点「应用」")
            time.sleep(1.5)

        # 4) 真实鼠标点「完成」关闭弹窗（关键：必须真实点击 + 校验关闭）
        closed = False
        for attempt in range(3):
            real_click_button_by_text(page, "完成", timeout=5)
            log("  已点「完成」")
            time.sleep(1.5)
            # 校验弹窗是否关闭：图片上传入口（accept 含 image 的 file input）消失即代表弹窗关闭
            still_open = page.evaluate("""()=>{
                return [...document.querySelectorAll('input[type=file]')]
                    .some(i => (i.getAttribute('accept')||'').includes('image'));
            }""")
            if not still_open:
                closed = True
                break
            log(f"  [WARN] 第{attempt+1}次点完成后弹窗仍在，重试真实点击...")
        if closed:
            log("  ✅ 自定义封面已设置（上传+应用+完成，弹窗已真正关闭）")
        else:
            log("  [WARN] 多次真实点击「完成」仍未关闭弹窗，保留默认第一帧（不阻塞发布）")
        return True
    except Exception as e:
        log("  [WARN] 自定义封面设置失败，使用默认第一帧: " + str(e))
    return True


def press_escape_after_topics(page):
    """输入话题后按 Escape 关闭建议浮层，避免遮挡后续点击"""
    page.keyboard.press("Escape")
    time.sleep(0.5)


def ensure_no_publish_click(page):
    """小红书网页创作中心没有「暂存离开/存草稿」按钮，唯一按钮是「发布笔记」。
    按铁律绝不点「发布笔记」——表单填好后网页会自动存为草稿，交给用户手动发布。"""
    log("小红书网页端无「暂存离开」按钮，唯一按钮是「发布笔记」")
    log("✅ 按铁律不点「发布笔记」；表单已填好，网页会自动存为草稿，请手动发布")
    time.sleep(1)
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--cover", default="",
                    help="自定义封面路径；网页版支持上传（脚本自动 hover 封面帧打开编辑器并上传本地图）")
    ap.add_argument("--title", default="")
    ap.add_argument("--desc", default="")
    ap.add_argument("--tags", default="")
    ap.add_argument("--shot-dir", default=SHOT_DIR)
    ap.add_argument("--force-upload", action="store_true",
                    help="强制重新上传视频（默认若已存在则跳过）")
    args = ap.parse_args()

    if not os.path.exists(args.video):
        log(f"[FAIL] 视频文件不存在: {args.video}")
        sys.exit(1)
    if args.cover and not os.path.exists(args.cover):
        log(f"[WARN] 指定封面不存在，已忽略: {args.cover}")
        args.cover = ""

    # 话题合并进正文（小红书：正文打 #词 触发话题，# 前需空格）
    body_text = args.desc or ""
    if args.tags:
        topic_str = " " + " ".join(f"#{t.strip()}" for t in args.tags.split(",") if t.strip())
        body_text = (body_text.strip() + topic_str).strip()

    os.makedirs(args.shot_dir, exist_ok=True)
    p = sync_playwright().start()
    browser = None
    try:
        browser = p.chromium.connect_over_cdp(CDP_URL)
        ctx = browser.contexts[0] if browser.contexts else browser.new_context()
        # 精确按 URL 定位小红书标签，避免盲信 pages[0]
        page = None
        for t in ctx.pages:
            if "creator.xiaohongshu.com" in (t.url or ""):
                page = t
                break
        if not page:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
        if "creator.xiaohongshu.com/publish/publish" not in (page.url or ""):
            log(f"导航: {UPLOAD_URL}")
            page.goto(UPLOAD_URL, wait_until="domcontentloaded", timeout=30000)
            time.sleep(6)
        else:
            log("已在发布页，跳过导航")
            time.sleep(3)

        # 登录态检测：创作中心 cookie 过期会直接跳到登录页
        # 注意：下面用独立变量 page_body，切勿覆盖上面的 body_text（简介文本）！
        try:
            page_body = page.inner_text("body", timeout=5000)
        except Exception:
            page_body = ""
        if "creator.xiaohongshu.com/login" in (page.url or "") or ("短信登录" in page_body and "验证码" in page_body):
            log("[FAIL] 小红书未登录，请先在浏览器中登录小红书创作中心后再运行脚本")
            return

        dismiss_overlays(page)

        # 刷新后可能弹出「有未发布的草稿」框（放弃/继续编辑），先放弃以干净重发
        dismiss_draft_modal(page)

        # 若已有视频（标题框存在）且非强制，跳过上传
        has_video = page.evaluate("""()=>!!document.querySelector('input[placeholder="填写标题会有更多赞哦"]')""")
        if has_video and not args.force_upload:
            log("检测到已有视频，跳过上传")
        else:
            if not upload_video(page, args.video):
                return
            time.sleep(2)

        if args.title:
            fill_title(page, args.title)
        if body_text:
            # 正文填充带损坏自动重试：一旦校验发现整页被吸入编辑器，
            # 重导航 + 重传视频 + 重填，最多 2 次
            ok = False
            for attempt in range(2):
                if fill_body(page, body_text):
                    ok = True
                    break
                log(f"  ⚠️ 正文第{attempt+1}次填充失败，重导航+重传重试...")
                page.goto(UPLOAD_URL, wait_until="domcontentloaded", timeout=30000)
                time.sleep(6)
                dismiss_overlays(page)
                dismiss_draft_modal(page)
                if not upload_video(page, args.video):
                    break
                time.sleep(2)
                if args.title:
                    fill_title(page, args.title)
            if not ok:
                log("[FAIL] 正文多次填充失败，终止")
                return
            press_escape_after_topics(page)
        set_cover(page, args.cover, args.shot_dir)

        page.screenshot(path=os.path.join(args.shot_dir, safe_filename("xhs_publish_final.png")))
        log(f"  截图: {os.path.join(args.shot_dir, safe_filename('xhs_publish_final.png'))}")

        ensure_no_publish_click(page)
        page.screenshot(path=os.path.join(args.shot_dir, safe_filename("xhs_after_draft.png")))
        log("\n=== 小红书发布流程执行完毕：表单已填好并自动存草稿，请手动点「发布笔记」发布 ===")
    except Exception as e:
        log(f"[ERROR] {e}")
        import traceback
        traceback.print_exc()
    finally:
        if browser:
            try:
                browser.close()
            except Exception:
                pass
        p.stop()


if __name__ == "__main__":
    main()
