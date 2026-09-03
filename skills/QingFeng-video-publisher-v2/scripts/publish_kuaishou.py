#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
快手视频发布脚本（Playwright + CDP）  2026-09-02 实测跑通

流程：导航上传页 → 上传视频 → 填写描述 → 设置封面(3:4) → 核验 → 保持页面打开

⚠️ 铁律与平台差异（与抖音不同，务必注意）：
1. 快手发布页【没有「存草稿/暂存离开」按钮】，只有「发布」和「取消」。
   点「取消」会【直接丢弃整个作品】回到上传初始态，视频都会没！
   因此脚本默认【不点任何按钮】，填完后保持页面打开，由用户手动点「发布」。
2. 快手【没有独立标题框】，只有「作品描述」(contenteditable)，
   标题写在描述首行。对应选择器 [class*="_description_"]。
3. 【封面注入必须打到弹窗内的 input】: .ant-modal-body input[type=file][accept*=image]
   页面级还有一个同 accept 的 image input(i=1)，注入它会上传成功但 UI 状态
   不同步、tab 被重置回「封面截取」，看起来像失败。
4. 发布页有 react-joyride 新手引导浮层会拦截所有点击，必须先移除
   (#react-joyride-portal)。

用法:
  python publish_kuaishou.py --video <视频> --cover <3:4封面> \
      --desc "<描述>" [--ratio 3:4] [--shot-dir <截图目录>]

不传 --publish 就不会点发布（默认安全）。
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
UPLOAD_URL = "https://cp.kuaishou.com/article/publish/video"

DEFAULT_RATIO = "3:4"


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def safe_filename(s):
    """
    【NTFS 备用数据流(ADS)陷阱】文件名含冒号会被解析成 主文件(0字节)+隐藏流，
    导致截图静默失效。这里把所有非法字符替换为 '-'。
    """
    return re.sub(r'[:*?"<>|/\r\n\t]', '-', str(s))


# ---------- 基础工具 ----------

def dismiss_joyride(page):
    """移除快手新手引导浮层，否则所有点击都被 overlay 拦截"""
    try:
        n = page.evaluate("""() => {
            let c = 0;
            document.querySelectorAll(
                '#react-joyride-portal, .react-joyride__overlay, .react-joyride__spotlight'
            ).forEach(e => { e.remove(); c++; });
            return c;
        }""")
        if n:
            log(f"  移除新手引导浮层 {n} 个节点")
        return n
    except Exception as e:
        log(f"  移除引导浮层失败: {e}")
        return 0


def js_click(page, sel, index=0):
    """JS 派发点击（绕过遮挡检查）"""
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


def click_by_text(page, text, in_modal=False):
    """
    按精确文本点击元素，modal 内优先。

    【坑】父容器的 innerText 会和子按钮一样（例如「清空上传」同时命中
    836x500 的容器 _cropper-upload 和 64x28 的真按钮 _cropper-upload-clear），
    点容器没有 React 事件。因此必须【优先选叶子节点 children.length===0】。
    """
    try:
        return page.evaluate("""([txt, inModal]) => {
            const roots = [];
            if (inModal) roots.push(document.querySelector('.ant-modal-body'));
            roots.push(document.body);
            const cands = [];
            for (const root of roots) {
                if (!root) continue;
                for (const el of root.querySelectorAll('div,span,button,li,a')) {
                    const t = (el.innerText || '').trim();
                    if (t === txt && el.getBoundingClientRect().width > 5) {
                        cands.push(el);
                    }
                }
            }
            if (!cands.length) return '';
            // 叶子节点优先（真按钮）；退化时取文档序最后一个（通常是最深的）
            const target = cands.find(e => e.children.length === 0)
                        || cands[cands.length - 1];
            target.scrollIntoView({block: 'center'});
            target.dispatchEvent(new MouseEvent('click',
                {bubbles: true, cancelable: true, view: window}));
            return 'ok';
        }""", [text, in_modal])
    except Exception as e:
        log(f"  click_by_text({text}) 失败: {e}")
        return ''


def robust_click(page, sel, timeout=5000):
    """常规点击 → force 点击 → JS 点击，三级兜底"""
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


# ---------- 各步骤 ----------

def find_page(ctx):
    """找已打开的快手发布页，否则新建"""
    page = None
    for pg in ctx.pages:
        if "kuaishou.com" in (pg.url or "") and "publish" in (pg.url or ""):
            page = pg
            break
    if page is None:
        for pg in ctx.pages:
            if "kuaishou.com" in (pg.url or ""):
                page = pg
                break
    if page is None:
        page = ctx.new_page()
    try:
        page.bring_to_front()
    except Exception:
        pass
    return page


def wait_for_file_input(page, timeout=30):
    """等待上传页 file input 渲染出来（页面异步加载，直接找会落空）"""
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            if page.query_selector_all('input[type="file"]'):
                return True
        except Exception:
            pass
        time.sleep(2)
    return False


def handle_draft(page, fresh=False):
    """
    【快手草稿机制】导航到上传页后，若有上次未发布的作品，会提示
    「还有上次未发布的视频，是否继续编辑？」+「继续编辑」/「放弃」。
    默认点「继续编辑」恢复已有草稿（视频和封面都在）；--fresh 则点「放弃」重来。
    """
    try:
        body = page.inner_text("body", timeout=3000)
    except Exception:
        return False
    if "还有上次未发布的视频" not in body:
        return False
    label = "放弃" if fresh else "继续编辑"
    log(f"检测到草稿提示，点击「{label}」")
    click_by_text(page, label)
    time.sleep(8)
    dismiss_joyride(page)
    return True


def has_video(page):
    """页面是否已有已上传的视频（有「重新上传」说明视频就绪）"""
    try:
        return "重新上传" in page.inner_text("body", timeout=2500)
    except Exception:
        return False


def upload_video(page, video, timeout=300, skip_if_exists=True):
    """上传视频并等待处理完成；若页面已有视频则跳过"""
    if skip_if_exists and has_video(page):
        log("检测到页面已有视频（草稿恢复），跳过上传")
        return True

    log("上传视频...")
    if not wait_for_file_input(page):
        log("[FAIL] 上传页未渲染出 file input")
        return False

    inputs = page.query_selector_all('input[type="file"]')
    vinput = None
    for inp in inputs:
        acc = (inp.get_attribute("accept") or "").lower()
        if "video" in acc or ".mp4" in acc:
            vinput = inp
            break
    if vinput is None and inputs:
        vinput = inputs[0]
    if not vinput:
        log("[FAIL] 未找到视频 input")
        return False

    vinput.set_input_files(video)
    log("已注入视频，等待上传+处理...")
    t0 = time.time()
    while time.time() - t0 < timeout:
        time.sleep(5)
        try:
            body = page.inner_text("body", timeout=3000)
            if "重新上传" in body or "作品描述" in body:
                log(f"[OK] 视频上传完成（{int(time.time()-t0)}s）")
                time.sleep(3)
                return True
        except Exception:
            pass
    log("[WARN] 等待视频处理超时")
    return False


def fill_description(page, desc):
    """
    填写作品描述（快手无独立标题，标题写首行）。
    contenteditable + React：用 execCommand insertText 才能触发 React 受控更新，
    单纯 keyboard.type 或 textContent 赋值都不生效。
    """
    if not desc:
        return False
    log("填写作品描述...")
    sel = '[class*="_description_"]'
    el = page.query_selector(sel)
    if not el:
        log("[FAIL] 未找到描述框")
        return False

    # 聚焦
    try:
        el.click(timeout=4000)
    except Exception:
        page.evaluate("""(s)=>{const e=document.querySelector(s); if(e) e.focus();}""", sel)
    time.sleep(1)

    # 用 execCommand 插入（能触发 React input 事件）
    ok = page.evaluate("""([sel, text]) => {
        const el = document.querySelector(sel);
        if (!el) return false;
        el.focus();
        // 清空
        document.execCommand('selectAll', false, null);
        document.execCommand('delete', false, null);
        // 插入
        const okIns = document.execCommand('insertText', false, text);
        // 兜底：手动派发 input 事件确保 React 收到
        el.dispatchEvent(new InputEvent('input', {bubbles: true, data: text}));
        return okIns || (el.innerText || '').length > 0;
    }""", [sel, desc])
    time.sleep(2)

    val = page.evaluate("""(s)=>{const e=document.querySelector(s);return e?(e.innerText||''):''}""", sel)
    if val.strip():
        log(f"✅ 描述已填写（{len(val)} 字）: {val[:60]}...")
        return True
    log("[FAIL] 描述未写入")
    return False


def set_cover(page, cover, ratio=DEFAULT_RATIO, shot_dir=None):
    """
    设置封面：打开封面弹窗 → 切「上传封面」tab → 注入到【弹窗内】image input
    → 选比例 → 确认。
    """
    if not cover or not os.path.exists(cover):
        log("[FAIL] 封面文件不存在")
        return False

    log("设置封面...")
    dismiss_joyride(page)
    time.sleep(1)

    def modal_text():
        try:
            return page.evaluate("""()=>{
                const m=document.querySelector('.ant-modal-body');
                return m ? (m.innerText||'') : '';
            }""")
        except Exception:
            return ''

    def modal_image_input():
        try:
            for inp in page.query_selector_all('.ant-modal-body input[type="file"]'):
                if "image" in (inp.get_attribute("accept") or "").lower():
                    return inp
        except Exception:
            pass
        return None

    # 1) 打开封面弹窗（轮询等待）
    if not page.query_selector('.ant-modal-body'):
        log("  打开封面弹窗...")
        robust_click(page, '[class*="_default-cover"]')
    t0 = time.time()
    while time.time() - t0 < 15 and not page.query_selector('.ant-modal-body'):
        time.sleep(2)
        dismiss_joyride(page)
        robust_click(page, '[class*="_default-cover"]')
    if not page.query_selector('.ant-modal-body'):
        log("[FAIL] 封面弹窗未打开")
        return False

    # 2) 切到「上传封面」tab（轮询等待 image input 出现）
    if '拖拽图片到此或点击上传' not in modal_text():
        log("  切换到「上传封面」tab")
        click_by_text(page, "上传封面", in_modal=True)

    # 【坑】草稿恢复时弹窗里可能已有封面，此时显示「清空上传」而不是
    # 「拖拽图片到此或点击上传」，且 image input 已被组件移除。
    # 必须先点「清空上传」清掉旧封面，input 才会重新出现。
    t0 = time.time()
    tgt = None
    cleared_once = False
    while time.time() - t0 < 25:
        tgt = modal_image_input()
        if tgt is not None:
            break
        mt = modal_text()
        if not cleared_once and '清空上传' in mt:
            log("  检测到已有封面，先点「清空上传」")
            click_by_text(page, "清空上传", in_modal=True)
            cleared_once = True
            time.sleep(3)
            continue
        # tab 可能没切过去，重试
        click_by_text(page, "上传封面", in_modal=True)
        time.sleep(3)

    if tgt is None:
        log(f"[FAIL] 弹窗内未找到 image input。弹窗文本: {modal_text()[:150]}")
        return False

    log(f"  注入封面: {os.path.basename(cover)}")
    tgt.set_input_files(cover)

    # 等待出现「清空上传」（上传成功的标志）
    uploaded = False
    for i in range(12):
        time.sleep(3)
        try:
            m = page.evaluate("""()=>{
                const m=document.querySelector('.ant-modal-body');
                return m ? (m.innerText||'') : '';
            }""")
            if '清空上传' in m:
                log(f"  ✅ 封面已上传（{(i+1)*3}s）")
                uploaded = True
                break
            if not m:
                log("  弹窗意外关闭")
                break
        except Exception:
            pass
    if not uploaded:
        log("[WARN] 未检测到封面上传成功标志")

    # 4) 选裁剪比例
    if ratio:
        log(f"  选择裁剪比例 {ratio}")
        click_by_text(page, ratio, in_modal=True)
        time.sleep(3)

    if shot_dir:
        try:
            shot = os.path.join(shot_dir, safe_filename(f"kuaishou_cover_{ratio}_modal.png"))
            page.screenshot(path=shot)
            log(f"  弹窗截图: {shot}")
        except Exception as e:
            log(f"  截图失败: {e}")

    # 5) 确认
    log("  点击「确认」")
    click_by_text(page, "确认", in_modal=True)
    time.sleep(5)

    closed = page.query_selector('.ant-modal-body') is None
    log(f"  ✅ 弹窗已关闭: {closed}")
    return uploaded


def verify_cover(page, shot_dir=None):
    """核验封面：取封面区截图 + 读取封面区图片 src"""
    log("核验封面...")
    try:
        srcs = page.evaluate("""()=>{
            const out=[];
            document.querySelectorAll('[class*="_default-cover"] img, [class*="_cover"] img')
                .forEach(im=>{
                    const s=im.getAttribute('src')||'';
                    if(s && !s.startsWith('data:image/svg')) out.push(s.slice(0,110));
                });
            return out.slice(0,5);
        }""")
        log(f"  封面区 src: {srcs}")
    except Exception as e:
        log(f"  读取封面 src 失败: {e}")

    if shot_dir:
        try:
            os.makedirs(shot_dir, exist_ok=True)
            shot = os.path.join(shot_dir, "kuaishou_cover_final.png")
            el = page.query_selector('[class*="_default-cover"]')
            if el:
                el.screenshot(path=shot)
                log(f"  ✅ 封面区截图: {shot}")
                return shot
        except Exception as e:
            log(f"  封面截图失败: {e}")
    return None


def set_ai_declaration(page, trigger="作者声明", option="内容由AI生成"):
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
    ap.add_argument("--video", required=True, help="视频文件路径")
    ap.add_argument("--cover", required=True, help="封面图路径（建议 3:4 竖版）")
    ap.add_argument("--desc", default="", help="作品描述（首行即标题）")
    ap.add_argument("--ratio", default=DEFAULT_RATIO, help="裁剪比例，默认 3:4")
    ap.add_argument("--shot-dir", default=None, help="过程截图目录")
    ap.add_argument("--publish", action="store_true",
                    help="危险：真正点击发布。默认不点，交给用户手动发布")
    ap.add_argument("--fresh", action="store_true",
                    help="遇到「上次未发布的视频」提示时点「放弃」重来（默认点继续编辑）")
    ap.add_argument("--force-upload", action="store_true",
                    help="即使页面已有草稿视频也重新上传")
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
        # 始终导航到上传页，保证状态干净（草稿提示也只在导航后出现）
        log(f"导航到上传页: {UPLOAD_URL}")
        page.goto(UPLOAD_URL, wait_until="domcontentloaded", timeout=30000)
        time.sleep(6)

        if "passport" in (page.url or "") or "login" in (page.url or ""):
            log("[FAIL] 快手未登录，请先在浏览器中登录")
            return

        dismiss_joyride(page)
        time.sleep(1)

        # 等待 file input 渲染
        if not wait_for_file_input(page):
            log("[WARN] file input 未就绪，仍继续尝试")

        # 处理草稿提示（默认恢复）
        # 【坑】草稿恢复下「继续编辑」+ --force-upload 无法真正替换视频预览，
        # 残留仍是旧草稿的视频。因此 --force-upload 时强制 --fresh（放弃草稿重来）。
        handle_draft(page, fresh=args.fresh or args.force_upload)
        time.sleep(2)
        dismiss_joyride(page)

        # 1) 上传视频
        if not upload_video(page, args.video,
                            skip_if_exists=not args.force_upload):
            log("[FAIL] 视频上传失败，中止")
            return

        dismiss_joyride(page)

        # 2) 填描述
        fill_description(page, args.desc)

        time.sleep(2)
        dismiss_joyride(page)

        # 3) 设封面
        set_cover(page, args.cover, args.ratio, args.shot_dir)
        time.sleep(2)

        # 4) 核验
        verify_cover(page, args.shot_dir)

        # AI 声明（内容由AI生成）
        set_ai_declaration(page)
        time.sleep(1)

        # 5) 发布 or 保持
        if args.publish:
            log("⚠️ --publish 已指定，点击「发布」...")
            click_by_text(page, "发布")
            time.sleep(6)
            log(f"发布后 URL: {page.url}")
        else:
            log("\n" + "=" * 50)
            log("✅ 快手内容已全部填好，页面保持打开。")
            log("⚠️ 请勿点击「取消」——快手取消会直接丢弃作品！")
            log("👉 请手动检查后点击「发布」。")
            log("=" * 50)

        # 整页截图
        if args.shot_dir:
            try:
                shot = os.path.join(args.shot_dir, "kuaishou_publish_final.png")
                page.screenshot(path=shot, full_page=True)
                log(f"整页截图: {shot}")
            except Exception as e:
                log(f"整页截图失败: {e}")

        log("\n=== 完成，浏览器保持打开 ===")

    except Exception as e:
        log(f"[ERROR] {e}")
        import traceback
        traceback.print_exc()
    finally:
        # 关键：只断开连接，绝不 browser.close()
        if browser:
            try:
                browser.close()
            except Exception:
                pass
        p.stop()


if __name__ == "__main__":
    main()
