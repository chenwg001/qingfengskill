#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
抖音封面设置（横封面 4:3 + 竖封面 3:4）—— 2026-09-01 实测跑通版

来源：不依赖旧逻辑，直接在真实发布页 DOM 上逆向摸出来的结构。
前提：视频已上传完成（页面上必须已出现「横封面4:3 / 竖封面3:4」两个槽位）。

独立用法：
    python set_douyin_cover.py --cover-4x3 "D:/x/封面_4x3.png" --cover-3x4 "D:/x/封面_3x4.png"
    python set_douyin_cover.py --cover-4x3 "D:/x/封面_4x3.png"          # 只设横封面

被 publish_douyin.py 复用：
    from set_douyin_cover import set_both_covers
    set_both_covers(page, cover_4x3=..., cover_3x4=...)
"""

import os

# ---------------------------------------------------------------------------
# 【坑 1】必须在 import playwright 之前清掉代理环境变量。
# 本机沙箱/系统里常设 http_proxy=127.0.0.1:6507，Playwright 连本地 CDP
# (127.0.0.1:9222) 会被该代理转发并返回 502，表现为 "连接被拒绝/502"。
# ---------------------------------------------------------------------------
for _k in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY",
           "all_proxy", "ALL_PROXY"):
    os.environ.pop(_k, None)

import argparse
import re
import sys
import time

from playwright.sync_api import sync_playwright

CDP_PORT = 9222

# ---- DOM 选择器（抖音 2026-09 版，class 名带哈希后缀会变，已做兜底） ----
SLOT_SEL = ".coverControl-CjlzqC"          # 封面槽位容器（横/竖各一个）
SLOT_BTN_SEL = ".title-wA45Xd"             # 槽位内的「选择封面 / 编辑封面」文字按钮
HOVER_MASK_SEL = ".filter-k_CjvJ"          # hover 才显示的遮罩层
MODAL_SEL = ".dy-creator-content-modal"    # 封面编辑器弹窗
# 弹窗内主上传区的隐藏 file input（弹窗里可能还有别的 input，必须限定容器）
UPLOAD_INPUT_SEL = (
    ".dy-creator-content-modal .semi-upload.upload-BvM5FF input[type=file]"
)


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


# Windows 文件名非法字符：: * ? " < > | 以及路径分隔符 / \ 和控制字符。
# 【坑 6】冒号尤其危险：文件名 "cover_横封面4:3.png" 在 NTFS 上会被解析成
#   主文件 "cover_横封面4"（0 字节）+ 备用数据流(ADS) ":3.png"。
#   结果：文件看似生成成功、不报错，但主文件是 0 字节、图片数据全藏在 ADS 里，
#   用户双击打不开，资源管理器里也看不出真实体积。截图功能等于静默失效。
_UNSAFE_CHARS = re.compile(r'[:*?"<>|/\\\r\n\t]')


def safe_filename(name, repl="-"):
    """把任意标签清洗成 Windows 合法文件名（冒号等替换为 -）。"""
    cleaned = _UNSAFE_CHARS.sub(repl, str(name))
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    return cleaned or "untitled"


def _hash_of(url):
    """从抖音 CDN 图片 URL 中提取 32 位 hash，用于判断封面是否真的换了。"""
    if not url:
        return ""
    m = re.search(r"/([0-9a-f]{32})", url)
    return m.group(1) if m else url[:40]


# ---------------------------------------------------------------------------
# 核心步骤
# ---------------------------------------------------------------------------
def list_slots(page):
    """列出当前页面所有封面槽位（文本 / 图片 hash / 位置）。"""
    return page.evaluate(
        """() => {
            const out = [];
            document.querySelectorAll('%s').forEach((el, i) => {
                const img = el.querySelector('img');
                const r = el.getBoundingClientRect();
                out.push({
                    index: i,
                    text: (el.innerText || '').trim().replace(/\\s+/g, ' ').slice(0, 30),
                    src: img ? (img.currentSrc || img.src || '') : '',
                    box: [Math.round(r.x), Math.round(r.y),
                          Math.round(r.width), Math.round(r.height)],
                });
            });
            return out;
        }""" % SLOT_SEL
    )


def reveal_slot(page, index):
    """
    【坑 2】CDP 连接过来的浏览器，Playwright 的 hover() 触发不了 CSS :hover，
    「选择封面 / 编辑封面」按钮会一直是 display:none。
    用 JS 直接改内联样式强制显示（遮罩层 + 标题都要改）。
    """
    page.evaluate(
        """(i) => {
            const slots = document.querySelectorAll('%s');
            const slot = slots[i];
            if (!slot) return false;
            slot.querySelectorAll('%s').forEach(f => {
                f.style.setProperty('display', 'flex', 'important');
                f.style.setProperty('opacity', '1', 'important');
                f.style.setProperty('visibility', 'visible', 'important');
                f.style.setProperty('pointer-events', 'auto', 'important');
            });
            slot.querySelectorAll('%s').forEach(t => {
                t.style.setProperty('display', 'block', 'important');
                t.style.setProperty('opacity', '1', 'important');
                t.style.setProperty('visibility', 'visible', 'important');
            });
            return true;
        }""" % (SLOT_SEL, HOVER_MASK_SEL, SLOT_BTN_SEL),
        index,
    )
    time.sleep(0.5)


def _click_slot_button(page, index):
    """点击第 index 个槽位里的「选择封面 / 编辑封面」。"""
    btn = page.locator(SLOT_SEL).nth(index).locator(SLOT_BTN_SEL).first
    btn.wait_for(state="attached", timeout=10000)
    # 【坑 3】父级有 SVG 遮罩会拦截普通点击，必须 force
    btn.click(force=True, timeout=10000)
    time.sleep(2)


def _wait_modal(page, timeout=15):
    modal = page.locator(MODAL_SEL).first
    modal.wait_for(state="visible", timeout=timeout * 1000)
    time.sleep(1.5)
    return modal


def _upload_into_modal(page, image_path, timeout=25):
    """
    【核心】把图片路径直接注入弹窗内主上传区的隐藏 file input。
    这是「能不能指向要上传的图片路径」的答案：
      - Playwright 的 set_input_files 会同时触发 change 事件，React 能监听到，
        等价于用户在 Windows 文件选择窗口里选中这个文件（原生窗口根本不弹）。
      - 备选方案是 expect_file_chooser() 拦截，但 set_input_files 更稳。
    """
    inp = page.locator(UPLOAD_INPUT_SEL).first
    inp.wait_for(state="attached", timeout=timeout * 1000)

    # 兜底：限定容器找不到时，退回「弹窗内 accept 含 image 的第一个 input」
    if inp.count() == 0:
        inp = page.locator(
            '%s input[type=file][accept*="image"]' % MODAL_SEL
        ).first
        inp.wait_for(state="attached", timeout=timeout * 1000)

    inp.set_input_files(image_path)
    log(f"  已注入文件: {os.path.basename(image_path)}")

    # 等图片上传 + 进画布（中央预览从 img 变成 canvas）
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            has_canvas = page.evaluate(
                """(sel) => {
                    const m = document.querySelector(sel);
                    return !!(m && m.querySelector('canvas'));
                }""", MODAL_SEL
            )
            if has_canvas:
                log("  已进入封面编辑画布")
                return True
        except Exception:
            pass
        time.sleep(0.6)
    log("  [WARN] 未检测到 canvas，继续尝试点完成")
    return False


def _click_done(page, timeout=15):
    """
    【坑 4】「取消 / 完成」按钮就在弹窗内部（dy-creator-content-modal 里）。
    旧脚本用 closest('.semi-modal-wrap') 把它们排除掉了，导致编辑器永远关不上。
    """
    done = page.locator('%s button:has-text("完成")' % MODAL_SEL).first
    done.wait_for(state="visible", timeout=timeout * 1000)
    try:
        done.click(timeout=10000)
    except Exception:
        done.click(force=True, timeout=10000)
    log("  已点击「完成」")
    time.sleep(2.5)

    # 等弹窗真的关掉
    deadline = time.time() + 12
    while time.time() < deadline:
        try:
            if page.locator(MODAL_SEL).count() == 0 or not page.locator(MODAL_SEL).first.is_visible():
                return True
        except Exception:
            return True
        time.sleep(0.5)
    log("  [WARN] 弹窗可能未关闭")
    return False


def dismiss_vertical_cover_prompt(page, timeout=12):
    """
    【新坑 2026-09-02】设置封面后，抖音可能弹出「设置竖封面获更多流量」引导弹窗。
    该弹窗不是封面编辑器，而是平台引导用户设置竖封面的 overlay，会拦截后续点击
    （包括下一个封面的槽位按钮、以及页面底部的「暂存离开」），必须关掉。
    关闭优先级：指定文本按钮 > 右上角 X 关闭 > ESC 兜底。
    """
    close_labels = ["暂不设置", "暂不", "先不设置", "不用了", "以后再说",
                    "稍后再说", "稍后设置", "我知道了", "关闭"]
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            res = page.evaluate("""(labels) => {
                const wraps = document.querySelectorAll('.dy-creator-content-modal-wrap, .dy-creator-content-modal');
                for (const wrap of wraps) {
                    const text = (wrap.innerText || '').replace(/\\s+/g, ' ');
                    if (!(text.includes('设置竖封面') || text.includes('获更多流量'))) continue;
                    // 1) 指定文本按钮（抖音按钮文案多变，穷举常见文案）
                    const btns = [...wrap.querySelectorAll('button, div[role="button"], span[role="button"]')];
                    for (const lab of labels) {
                        const b = btns.find(x => (x.innerText || '').trim() === lab);
                        if (b) { b.click(); return 'btn:' + lab; }
                    }
                    // 2) 右上角 X 关闭按钮（aria-label / 图标文字）
                    const x = [...wrap.querySelectorAll('button, [role="button"], i, svg')]
                        .find(e => {
                            const t = (e.getAttribute('aria-label') || '').trim();
                            const c = (e.innerText || '').trim();
                            return t === '关闭' || t === 'X' || t === 'x'
                                || c === '×' || c === '✕' || c === 'X';
                        });
                    if (x) { x.click(); return 'x'; }
                    // 3) ESC 兜底
                    document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', code: 'Escape', bubbles: true}));
                    return 'escape';
                }
                return false;
            }""", close_labels)
            if res:
                log(f"  已关闭「设置竖封面」引导弹窗 ({res})")
                time.sleep(1.5)
                return True
        except Exception as e:
            log(f"  [WARN] dismiss_vertical_cover_prompt: {e}")
            break
        time.sleep(0.5)
    return False


# 右侧「发文助手」面板里也有检测项，与封面无关，必须排除，否则会误报。
# 实测页面会同时出现：
#   「封面效果检测通过」（封面区，@页面中部）
#   「封面检测通过 / 暂未发现封面低质问题」（发文助手）
#   「作品检测失败 / 抱歉，当前检测人数过多，请稍后再试」（发文助手，服务端排队限流）
# 旧版用 inner_text("body") 匹配裸子串 "检测失败"，会被「作品检测失败」命中 → 误报。
RE_COVER_FAIL = re.compile(r"封面[^。\n]{0,8}(效果检测|检测|诊断)[^。\n]{0,4}(失败|不通过|异常)")
RE_COVER_PASS = re.compile(r"封面[^。\n]{0,8}(效果检测|检测|诊断)[^。\n]{0,4}(通过|正常)")
RE_WORK_FAIL = re.compile(r"作品检测失败|检测人数过多")


def verify_cover_state(page, slot_hashes=None, strict=True):
    """
    判定封面是否真正生效，返回 dict。

    判据优先级（【坑 5】只认硬证据，不靠裸文本子串）：
      1. 硬证据：右侧手机预览区的 CDN 图 hash 是否落在已设置的槽位 hash 里。
         落进去 = 用户看到的确实是上传的图；没落进去 = 被回退成视频帧。
      2. 软证据：页面上「封面…检测通过 / 失败」这类封面专属状态文字。
      3. 明确忽略「作品检测失败」（发文助手的服务端排队限流，与封面无关）。

    strict=False 用于「只设了其中一个封面」的中间态：
    右侧预览同一时刻只展示一个方向的封面（取决于预览区选中的是「横封面」还是
    「竖封面」tab），所以刚设完横封面时预览里显示的仍是旧的竖封面——这是正常的，
    不算失败。此时降级为 INFO，以最终汇总时的核验为准。
    """
    out = {"preview_matched": None, "review": None, "ignored": []}

    # --- 1. 硬证据：右侧预览区 ---
    try:
        preview_srcs = page.evaluate(
            """() => {
                const out = [];
                document.querySelectorAll('img').forEach(img => {
                    const r = img.getBoundingClientRect();
                    const src = img.currentSrc || img.src || '';
                    // 右侧预览区（页面右 1/4）+ 抖音媒体 CDN 域名
                    if (r.x > window.innerWidth * 0.55 && r.width > 60
                            && /tos-cn|creator-media/.test(src)) {
                        out.push({src: src, w: Math.round(r.width), h: Math.round(r.height)});
                    }
                });
                return out;
            }"""
        )
    except Exception:
        preview_srcs = []

    if slot_hashes:
        wanted = {h for h in slot_hashes if h}
        prev_hashes = [(_hash_of(x["src"]), x["w"], x["h"]) for x in preview_srcs]
        hit = [h for h, _, _ in prev_hashes if h in wanted]
        out["preview_matched"] = bool(hit)
        if hit:
            log(f"  [OK] 右侧预览已使用上传的封面 (hash={hit[0][:12]})")
        elif strict:
            log("  [WARN] 右侧预览未匹配到上传封面，可能被回退成视频帧，建议重设或换图")
        else:
            log("  [INFO] 预览区当前展示的是另一方向的封面（预览一次只显示一张），以最终汇总核验为准")
        if prev_hashes:
            log(f"       预览区图片: " + ", ".join(f"{h[:8]}({w}x{hh})" for h, w, hh in prev_hashes[:4]))

    # --- 2/3. 状态文字（精确匹配，只认封面专属） ---
    try:
        txt = page.inner_text("body", timeout=3000)
    except Exception:
        return out

    m_fail = RE_COVER_FAIL.search(txt)
    m_pass = RE_COVER_PASS.search(txt)
    m_work = RE_WORK_FAIL.search(txt)

    if m_work:
        out["ignored"].append(m_work.group(0))
        log(f"  [忽略] 「{m_work.group(0)}」——发文助手的作品检测，服务端排队限流，与封面无关")

    if m_fail:
        out["review"] = "FAIL"
        log(f"  [WARN] 封面检测未通过：「{m_fail.group(0)}」，建议换一张（避免文字/人物/强AI痕迹）")
    elif m_pass:
        out["review"] = "PASS"
        log(f"  [OK] 封面检测通过：「{m_pass.group(0)}」")
    else:
        log("  封面检测: 页面未出现封面检测结论（通常只是尚未跑完）")

    return out


def set_one_cover(page, slot_index, image_path, label, shot_dir=None):
    """给第 slot_index 个槽位设置封面，返回 (是否成功, 新hash)。"""
    log(f"\n===== {label} =====")
    before = list_slots(page)
    old_hash = _hash_of(before[slot_index]["src"]) if slot_index < len(before) else ""

    reveal_slot(page, slot_index)
    _click_slot_button(page, slot_index)
    try:
        _wait_modal(page)
    except Exception as e:
        log(f"  [FAIL] 封面编辑器未打开: {e}")
        return False, ""

    _upload_into_modal(page, image_path)

    if shot_dir:
        # 必须用 safe_filename：label 含 "4:3"/"3:4"，冒号会在 NTFS 上生成
        # 0 字节主文件 + ADS 隐藏数据流，导致截图实际打不开（见 safe_filename 注释）
        page.screenshot(
            path=os.path.join(shot_dir, f"cover_{safe_filename(label)}_uploaded.png")
        )

    _click_done(page)

    # 封面编辑器关闭后，抖音可能紧接着弹出「设置竖封面获更多流量」引导弹窗，
    # 它会挡住下一个封面的槽位和后续的「暂存离开」，必须先关掉。
    dismiss_vertical_cover_prompt(page)

    # 校验：槽位图片 hash 是否变化
    new_hash = ""
    deadline = time.time() + 20
    while time.time() < deadline:
        cur = list_slots(page)
        if slot_index < len(cur):
            h = _hash_of(cur[slot_index]["src"])
            if h and h != old_hash:
                new_hash = h
                break
        time.sleep(1)

    if new_hash:
        log(f"  [OK] {label} 已生效  ({old_hash[:8]} -> {new_hash[:8]})")
    else:
        log(f"  [WARN] {label} 槽位图片 hash 未变化，可能未生效")

    # strict=False：只设了其中一个封面，预览区可能正展示另一方向，不算失败
    verify_cover_state(page, [new_hash] if new_hash else None, strict=False)
    return bool(new_hash), new_hash


def find_slot_index(page, ratio):
    """
    按槽位文本里的比例标记找 index（不要硬编码 0=横 1=竖，抖音可能调整顺序）。
    ratio: '4:3'（横封面）或 '3:4'（竖封面）
    """
    for s in list_slots(page):
        if ratio in (s.get("text") or ""):
            return s["index"]
    # 兜底：按横竖位置判断（横的更宽）
    slots = list_slots(page)
    if len(slots) >= 2:
        w0 = slots[0]["box"][2]
        w1 = slots[1]["box"][2]
        wider = 0 if w0 >= w1 else 1
        return wider if ratio == "4:3" else (1 - wider)
    return 0 if ratio == "4:3" else 1


def set_both_covers(page, cover_4x3=None, cover_3x4=None, shot_dir=None):
    """
    设置抖音两个封面。横封面 4:3 传 4:3 图，竖封面 3:4 传 3:4 图——方向必须对应，
    否则图会被塞进错误槽位（旧脚本翻车点之一）。
    返回 {'4:3': hash, '3:4': hash}
    """
    result = {}
    slots = list_slots(page)
    if not slots:
        log("[FAIL] 页面未找到封面槽位（视频是否已上传完成？）")
        return result

    log(f"检测到 {len(slots)} 个封面槽位: " + " | ".join(
        f"[{s['index']}]{s['text']}" for s in slots))

    plan = []
    if cover_4x3:
        plan.append(("4:3", cover_4x3, "横封面4:3"))
    if cover_3x4:
        plan.append(("3:4", cover_3x4, "竖封面3:4"))

    for ratio, path, label in plan:
        if not os.path.exists(path):
            log(f"[FAIL] 文件不存在: {path}")
            continue
        idx = find_slot_index(page, ratio)
        ok, h = set_one_cover(page, idx, path, label, shot_dir=shot_dir)
        result[ratio] = h if ok else ""

    time.sleep(2)
    # 兜底：全部封面设完后抖音可能才弹「设置竖封面」引导弹窗，先关掉，
    # 否则会挡住后续「暂存离开」（publish_douyin.py 暂存前也会再兜一次）
    dismiss_vertical_cover_prompt(page)
    log("\n--- 封面设置汇总 ---")
    for s in list_slots(page):
        log(f"  [{s['index']}] {s['text']}  ->  {_hash_of(s['src'])[:12]}")

    # 整体核验：两个槽位的 hash 都要能在右侧预览里找到（硬证据）
    hashes = [h for h in result.values() if h]
    if hashes:
        log("")
        verify_cover_state(page, hashes)
    return result


# ---------------------------------------------------------------------------
# 独立运行入口
# ---------------------------------------------------------------------------
def attach_page(cdp_port):
    """连接到已开启 CDP 的 Chrome，返回 (p, browser, page)。"""
    p = sync_playwright().start()
    browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{cdp_port}")
    ctx = browser.contexts[0]
    page = None
    for pg in ctx.pages:
        if "creator.douyin.com" in (pg.url or ""):
            page = pg
            break
    if page is None:
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
    return p, browser, page


def main():
    ap = argparse.ArgumentParser(description="抖音封面设置（横4:3 + 竖3:4）")
    ap.add_argument("--cover-4x3", help="4:3 横版封面图片绝对路径")
    ap.add_argument("--cover-3x4", help="3:4 竖版封面图片绝对路径")
    ap.add_argument("--cdp-port", type=int, default=CDP_PORT)
    ap.add_argument("--shot-dir", default=None, help="过程截图保存目录")
    args = ap.parse_args()

    if not args.cover_4x3 and not args.cover_3x4:
        ap.error("至少提供 --cover-4x3 或 --cover-3x4")

    for f in (args.cover_4x3, args.cover_3x4):
        if f and not os.path.exists(f):
            log(f"[FAIL] 文件不存在: {f}")
            sys.exit(1)

    if args.shot_dir:
        os.makedirs(args.shot_dir, exist_ok=True)

    p, browser, page = None, None, None
    try:
        p, browser, page = attach_page(args.cdp_port)
        page.bring_to_front()
        log(f"已连接页面: {page.url}")
        set_both_covers(page, args.cover_4x3, args.cover_3x4, shot_dir=args.shot_dir)
        log("\n完成，浏览器保持打开")
    except Exception as e:
        log(f"[ERROR] {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        # 【铁律】只断开连接，绝不 close 浏览器
        if browser:
            try:
                browser.close()
            except Exception:
                pass
        if p:
            p.stop()


if __name__ == "__main__":
    main()
