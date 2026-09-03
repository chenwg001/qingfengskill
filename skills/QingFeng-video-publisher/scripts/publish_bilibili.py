#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
B 站视频投稿脚本（Playwright + CDP）  2026-09-02 实测跑通

流程：导航上传页 → 上传视频 → 填标题 → 填简介(Quill) → 填标签 → 上传封面 → 存草稿(暂存离开)

⚠️ 平台差异（与抖音/快手都不同）：
1. 视频上传 input：直接 set_input_files 到页面【第一个 file input】(accept 含 mp4)，
   其他 input（.txt/.zip/封面）accept 不含 video，跳过即可。用 input#0 实测生效。
2. 【没有独立"标题框"以外的特殊结构】——标题是普通 input[placeholder="请输入稿件标题"]。
3. 简介是【Quill 富文本编辑器】(.ql-editor contenteditable)，必须用 execCommand 填，
   普通 input 赋值无效（页面 0 个 textarea）。
4. 标签是 input[placeholder="按回车键Enter创建标签"]，type 文本后按 Enter 创建。
5. 封面：点「添加封面」→ 弹窗内 image input → set_input_files → 点「完成」。
   ⚠️ 封面上传时 B 站会弹【通知授权框】，必须先点「禁止/知道了」关掉，否则挡住按钮。
6. 投稿页底部有【存草稿】和【立即投稿】两个按钮。
   本脚本默认点【存草稿】(暂存离开)，符合"我手动发布"铁律；
   传 --publish 才会点【立即投稿】真正发出。

用法:
  python publish_bilibili.py --video <视频> --cover <4:3封面> \
      --title "<标题>" --desc "<简介>" --tags "教育,王阳明,传统文化" \
      [--shot-dir <截图目录>] [--publish]

不传 --publish 默认点「存草稿」，页面保持打开等你手动发布。
"""
import argparse
import os
import re
import sys
import time

# 【坑】必须在 import playwright 前清代理，否则连本地 CDP 被 127.0.0.1:6507 转发成 502
for _k in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY",
           "all_proxy", "ALL_PROXY"):
    os.environ.pop(_k, None)

from playwright.sync_api import sync_playwright

CDP_URL = "http://127.0.0.1:9222"
UPLOAD_URL = "https://member.bilibili.com/platform/upload/video/frame"


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def safe_filename(s):
    """NTFS 备用数据流(ADS)陷阱：文件名冒号会生成 0 字节主文件+隐藏流，替换为 '-'"""
    return re.sub(r'[:*?"<>|/\r\n\t]', '-', str(s))


# ---------- 基础工具 ----------

def js_click(page, sel, index=0):
    try:
        return page.evaluate("""([sel, idx]) => {
            const els = document.querySelectorAll(sel);
            const el = els[idx];
            if (!el) return false;
            el.scrollIntoView({block: 'center'});
            el.dispatchEvent(new MouseEvent('click',
                {bubbles: true, cancelable: true, view: window}));
            return true;
        }""", [sel, index])
    except Exception as e:
        log(f"  js_click({sel}) 失败: {e}")
        return False


def click_by_text(page, text, timeout=8):
    """
    按精确文本点击元素，优先叶子节点（children.length===0 才是真按钮）。
    返回 'ok' / ''（未找到）。
    """
    try:
        return page.evaluate("""([txt]) => {
            const cands = [];
            for (const el of document.querySelectorAll('div,span,button,li,a')) {
                const t = (el.innerText || '').trim();
                if (t === txt && el.getBoundingClientRect().width > 5) {
                    cands.push(el);
                }
            }
            if (!cands.length) return '';
            const target = cands.find(e => e.children.length === 0)
                        || cands[cands.length - 1];
            target.scrollIntoView({block: 'center'});
            target.dispatchEvent(new MouseEvent('click',
                {bubbles: true, cancelable: true, view: window}));
            return 'ok';
        }""", [text])
    except Exception as e:
        log(f"  click_by_text({text}) 失败: {e}")
        return ''


def click_by_text_contains(page, *texts):
    """
    按【包含】文本点击（覆盖"添加封面"/"更换封面"两种文案），优先叶子节点。
    """
    try:
        const_arr = list(texts)
        return page.evaluate("""(txts) => {
            const cands = [];
            for (const el of document.querySelectorAll('div,span,button,li,a')) {
                const t = (el.innerText || '').trim();
                if (t && el.getBoundingClientRect().width > 5
                    && txts.some(x => t.includes(x))) {
                    cands.push(el);
                }
            }
            if (!cands.length) return '';
            const target = cands.find(e => e.children.length === 0)
                        || cands[cands.length - 1];
            target.scrollIntoView({block: 'center'});
            target.dispatchEvent(new MouseEvent('click',
                {bubbles: true, cancelable: true, view: window}));
            return 'ok';
        }""", const_arr)
    except Exception as e:
        log(f"  click_by_text_contains({texts}) 失败: {e}")
        return ''


def click_cover_entry(page):
    """点封面入口：先按文案（添加/更换封面），再用 CSS 兜底"""
    r = click_by_text_contains(page, "添加封面", "更换封面")
    if r:
        return r
    # CSS 兜底：封面区常见类
    for sel in [".add-text", '[class*="cover-empty"]', ".cover-module",
                ".cover-slot", '[class*="cover-main"]']:
        try:
            el = page.query_selector(sel)
            if el and el.is_visible():
                el.click(timeout=3000, force=True)
                return f"css:{sel}"
        except Exception:
            pass
    return ''


def robust_click(page, sel, timeout=5000):
    try:
        el = page.query_selector(sel)
        if el and el.is_visible():
            el.click(timeout=timeout)
            return True
    except Exception:
        pass
    try:
        el = page.query_selector(sel)
        if el:
            el.click(timeout=timeout, force=True)
            return True
    except Exception:
        pass
    return js_click(page, sel)


def dismiss_notifications(page):
    """关掉 B 站通知授权弹窗（封面上传时必弹），点「禁止」或「知道了」"""
    try:
        r = page.evaluate("""() => {
            for (const el of document.querySelectorAll('button,div')) {
                const t = (el.innerText||'').trim();
                if (t === '禁止') { el.dispatchEvent(new MouseEvent('click',{bubbles:true,cancelable:true,view:window})); return 'ban'; }
                if (t === '知道了') { el.dispatchEvent(new MouseEvent('click',{bubbles:true,cancelable:true,view:window})); return 'ok'; }
            }
            return '';
        }""")
        if r:
            log(f"  关闭通知弹窗: {r}")
            time.sleep(1)
        return r
    except Exception:
        return ''


# ---------- 各步骤 ----------

def find_page(ctx):
    page = None
    for pg in ctx.pages:
        if "member.bilibili.com" in (pg.url or "") and "upload" in (pg.url or ""):
            page = pg
            break
    if page is None:
        for pg in ctx.pages:
            if "bilibili.com" in (pg.url or ""):
                page = pg
                break
    if page is None:
        page = ctx.new_page()
    try:
        page.bring_to_front()
    except Exception:
        pass
    return page


def has_video(page):
    """页面是否已有已上传的视频（出现「更换视频」说明视频就绪）"""
    try:
        return "更换视频" in page.inner_text("body", timeout=2500)
    except Exception:
        return False


def upload_video(page, video, skip_if_exists=True):
    if skip_if_exists and has_video(page):
        log("检测到页面已有视频，跳过上传")
        return True
    log("上传视频...")
    inp = page.query_selector_all('input[type="file"]')
    if not inp:
        log("[FAIL] 未渲染出 file input")
        return False
    # 取第一个 accept 含 video 的；没有则用 index 0
    vinput = None
    for i in inp:
        acc = (i.get_attribute("accept") or "").lower()
        if "video" in acc or ".mp4" in acc:
            vinput = i
            break
    if vinput is None:
        vinput = inp[0]
    vinput.set_input_files(video)
    log("已注入视频，等待上传+处理...")
    t0 = time.time()
    while time.time() - t0 < 180:
        time.sleep(5)
        try:
            body = page.inner_text("body", timeout=3000)
            if "请输入稿件标题" in body or "更换视频" in body:
                log(f"[OK] 视频上传完成（{int(time.time()-t0)}s）")
                time.sleep(3)
                return True
        except Exception:
            pass
    log("[WARN] 等待视频处理超时")
    return False


def fill_title(page, title):
    if not title:
        return False
    log("填写标题...")
    sel = 'input[placeholder="请输入稿件标题"]'
    el = page.query_selector(sel)
    if not el:
        log("[FAIL] 未找到标题 input")
        return False
    try:
        el.click(timeout=4000)
    except Exception:
        page.evaluate("""(s)=>{const e=document.querySelector(s); if(e) e.focus();}""", sel)
    time.sleep(1)
    ok = page.evaluate("""([sel, text]) => {
        const el = document.querySelector(sel);
        if (!el) return false;
        el.focus();
        document.execCommand('selectAll', false, null);
        document.execCommand('delete', false, null);
        const ins = document.execCommand('insertText', false, text);
        el.dispatchEvent(new InputEvent('input', {bubbles: true, data: text}));
        return ins || (el.value||'').length > 0;
    }""", [sel, title])
    time.sleep(1.5)
    val = page.evaluate("""(s)=>{const e=document.querySelector(s);return e?(e.value||''):''}""", sel)
    if val.strip():
        log(f"✅ 标题已填写: {val[:50]}")
        return True
    log("[FAIL] 标题未写入")
    return False


def fill_desc(page, desc):
    """简介是 Quill 编辑器 .ql-editor (contenteditable)"""
    if not desc:
        return False
    log("填写简介（Quill 编辑器）...")
    sel = '.ql-editor'
    el = page.query_selector(sel)
    if not el:
        log("[FAIL] 未找到 .ql-editor")
        return False
    try:
        el.click(timeout=4000)
    except Exception:
        page.evaluate("""(s)=>{const e=document.querySelector(s); if(e) e.focus();}""", sel)
    time.sleep(1)
    ok = page.evaluate("""([sel, text]) => {
        const el = document.querySelector(sel);
        if (!el) return false;
        el.focus();
        document.execCommand('selectAll', false, null);
        document.execCommand('delete', false, null);
        const ins = document.execCommand('insertText', false, text);
        el.dispatchEvent(new InputEvent('input', {bubbles: true, data: text}));
        return ins || (el.innerText||'').length > 0;
    }""", [sel, desc])
    time.sleep(1.5)
    val = page.evaluate("""(s)=>{const e=document.querySelector(s);return e?(e.innerText||''):''}""", sel)
    if val.strip():
        log(f"✅ 简介已填写（{len(val)} 字）: {val[:60]}...")
        return True
    log("[FAIL] 简介未写入")
    return False


def fill_tags(page, tags):
    """标签：type 文本后按 Enter 创建；多个用逗号分隔"""
    if not tags:
        return False
    log("填写标签...")
    sel = 'input[placeholder="按回车键Enter创建标签"]'
    el = page.query_selector(sel)
    if not el:
        log("[FAIL] 未找到标签 input")
        return False
    items = [t.strip() for t in tags.split(",") if t.strip()]
    ok_count = 0
    for t in items:
        try:
            el.click(timeout=3000)
            el.fill("")
            el.type(t, delay=20)
            el.press("Enter")
            time.sleep(1)
            ok_count += 1
        except Exception as e:
            log(f"  标签「{t}」失败: {e}")
    log(f"✅ 已添加标签 {ok_count}/{len(items)}")
    return ok_count > 0


def cover_modal_open(page):
    """
    判断【封面上传弹窗】是否打开。
    注意：通知授权框也用 .bcc-dialog__wrap，必须排除——只有含图片 input
    或封面相关文案的弹窗才算封面弹窗。
    """
    return page.evaluate("""() => {
        const modals = document.querySelectorAll('.bili-dialog, .bcc-dialog__wrap, .cover-edit-dialog');
        for (const m of modals) {
            // 含图片上传 input
            for (const i of m.querySelectorAll('input[type=file]')) {
                if ((i.getAttribute('accept')||'').includes('image')) return true;
            }
            // 含封面相关文案（排除"禁止/知道了"通知框）
            const tx = (m.innerText || '');
            if (tx.includes('添加封面') || tx.includes('上传封面')
                || tx.includes('裁剪') || tx.includes('封面上传')) return true;
        }
        return false;
    }""")


def set_cover(page, cover, shot_dir=None):
    if not cover or not os.path.exists(cover):
        log("[FAIL] 封面文件不存在")
        return False
    log("设置封面...")
    # 点封面入口（添加封面 / 更换封面，文案随状态变化）
    r = click_cover_entry(page)
    log(f"  点击封面入口: {r}")
    time.sleep(4)
    dismiss_notifications(page)

    # 找弹窗内 image input
    t0 = time.time()
    handle = None
    while time.time() - t0 < 20:
        handle = page.evaluate_handle("""() => {
            const modals = document.querySelectorAll('.bili-dialog, .bcc-dialog__wrap, .cover-edit-dialog');
            for (const modal of modals) {
                for (const i of modal.querySelectorAll('input[type=file]')) {
                    if ((i.getAttribute('accept')||'').includes('image')) return i;
                }
            }
            return null;
        }""")
        if handle and handle.as_element():
            break
        time.sleep(2)
        dismiss_notifications(page)
        # 可能点了封面入口没反应，再点一次
        if not cover_modal_open(page):
            click_cover_entry(page)
            time.sleep(3)

    if not (handle and handle.as_element()):
        log("[FAIL] 封面弹窗内未找到 image input")
        return False

    try:
        handle.as_element().set_input_files(cover)
        log(f"  ✅ 注入封面: {os.path.basename(cover)}")
    except Exception as e:
        log(f"  set_input_files 失败: {e}")
        return False

    # 等待上传完成（弹窗不消失即成功；可截图核查）
    time.sleep(5)
    dismiss_notifications(page)
    if shot_dir:
        try:
            page.screenshot(path=os.path.join(shot_dir, safe_filename("bili_cover_modal.png")))
        except Exception:
            pass

    # 点「完成」确认
    rc = click_by_text(page, "完成")
    log(f"  点「完成」: {rc}")
    time.sleep(3)
    dismiss_notifications(page)
    closed = not cover_modal_open(page)
    log(f"  ✅ 封面对话框已关闭: {closed}")
    return bool(closed)


def save_draft(page, publish=False):
    """点「存草稿」(默认) 或「立即投稿」(publish)"""
    label = "立即投稿" if publish else "存草稿"
    # 先关掉可能挡住的通知框
    dismiss_notifications(page)
    time.sleep(1)
    r = click_by_text(page, label)
    log(f"点击「{label}」: {r}")
    time.sleep(4)
    dismiss_notifications(page)
    # 验证
    if publish:
        log(f"  发布后 URL: {page.url}")
    else:
        # 存草稿后通常会跳到内容管理或弹"已存草稿"提示
        body = ""
        try:
            body = page.inner_text("body", timeout=3000)
        except Exception:
            pass
        if "草稿" in body or "内容管理" in page.url or "upload" not in page.url:
            log("  ✅ 已存草稿（页面已离开投稿页或提示草稿）")
        else:
            log("  ⚠️ 未检测到明确的存草稿反馈，请手动确认")
    return bool(r)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True, help="视频文件路径")
    ap.add_argument("--cover", required=True, help="封面图路径（横屏视频建议 4:3）")
    ap.add_argument("--title", default="", help="稿件标题")
    ap.add_argument("--desc", default="", help="稿件简介")
    ap.add_argument("--tags", default="", help="标签，逗号分隔")
    ap.add_argument("--shot-dir", default=None, help="过程截图目录")
    ap.add_argument("--publish", action="store_true",
                    help="危险：点「立即投稿」真正发布。默认点「存草稿」暂存离开")
    ap.add_argument("--force-upload", action="store_true",
                    help="即使页面已有视频也重新上传")
    args = ap.parse_args()

    for f in [args.video, args.cover]:
        if not os.path.exists(f):
            log(f"[FAIL] 文件不存在: {f}")
            sys.exit(1)

    p = sync_playwright().start()
    browser = None
    try:
        browser = p.chromium.connect_over_cdp(CDP_URL)
        ctx = browser.contexts[0] if browser.contexts else browser.new_context()
        page = find_page(ctx)

        log(f"当前页: {page.url}")
        # 始终导航到视频上传表单页（即使当前停在草稿管理页也要跳回来）
        log(f"导航到上传页: {UPLOAD_URL}")
        page.goto(UPLOAD_URL, wait_until="domcontentloaded", timeout=30000)
        time.sleep(7)

        body_text = ""
        try:
            body_text = page.inner_text("body", timeout=3000)
        except Exception:
            pass
        if ("passport" in (page.url or "") or "login" in (page.url or "")
                or "短信登录" in body_text or "密码登录" in body_text or "扫码登录" in body_text):
            log("[FAIL] B 站未登录，请先在浏览器中登录")
            return

        # 1) 上传视频
        if not upload_video(page, args.video, skip_if_exists=not args.force_upload):
            log("[FAIL] 视频上传失败，中止")
            return

        time.sleep(2)
        dismiss_notifications(page)

        # 2) 标题
        if args.title:
            fill_title(page, args.title)

        # 3) 简介
        if args.desc:
            fill_desc(page, args.desc)

        # 4) 标签
        if args.tags:
            fill_tags(page, args.tags)

        time.sleep(2)
        dismiss_notifications(page)

        # 5) 封面
        set_cover(page, args.cover, args.shot_dir)
        time.sleep(2)

        # 6) 存草稿 / 发布
        save_draft(page, publish=args.publish)

        # 整页截图
        if args.shot_dir:
            try:
                page.screenshot(path=os.path.join(args.shot_dir, "bili_publish_final.png"), full_page=True)
                log(f"整页截图: {os.path.join(args.shot_dir, 'bili_publish_final.png')}")
            except Exception as e:
                log(f"整页截图失败: {e}")

        log("\n=== 完成，浏览器保持打开 ===")

    except Exception as e:
        log(f"[ERROR] {e}")
        import traceback
        traceback.print_exc()
    finally:
        # 关键：只断开连接，绝不真正关掉浏览器
        if browser:
            try:
                browser.close()
            except Exception:
                pass
        p.stop()


if __name__ == "__main__":
    main()
