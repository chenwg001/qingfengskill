# -*- coding: utf-8 -*-
"""
微信公众号自动发布脚本（正式版 v4）
修复：Step 2 仅收集 CDN URL，Step 3 只注入文字，Step 4 单独插入图片（不再重复）。

流程：
  Step 0: 连接 CDP + 解析 HTML
  Step 1: 选择主模板
  Step 2: 上传所有图片，收集 CDN URL（不上传正文，仅占位）
  Step 3: 注入文字内容（跳过图片 element，图片在 Step 4 处理）
  Step 4: 逐张插入图片到正文（利用 Step 2 收集的 CDN URL）
  Step 5: 填写左侧标题 + 正文上方标题 + 作者
  Step 6: 上传封面图
  Step 7: 最终验证 + 截图

用法：
  python scripts/publish_wechat.py "<HTML文件路径>" [--author "作者名"] [--cover "封面图路径"]
"""
import json
import sys
import io
import os
import time
import re
import argparse

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from playwright.sync_api import sync_playwright

# ============================================================
# 配置
# ============================================================
CDP_URL = 'http://127.0.0.1:9222'
DEFAULT_AUTHOR = '无不言'

UPLOAD_WAIT = 4       # 大图上传等待秒数
RETRY_WAIT = 3        # 重试等待秒数


# ============================================================
# HTML 解析
# ============================================================
def parse_html(html_path):
    """解析 HTML 文件，提取标题、正文块和图片路径"""
    with open(html_path, 'r', encoding='utf-8') as f:
        html = f.read()

    base_dir = os.path.dirname(os.path.abspath(html_path))

    # 关键修复：所有「位置匹配」必须基于同一份源串（原始 html）。
    # 旧代码对 h2/h3、<p> 用 html_clean（&nbsp;->空格、连续空格折叠，
    # 使字符串变短），而对 <img> 用原始 html，两套坐标混在一起排序，
    # 导致图片相对文字的顺序错乱（每张图都插不到原网页位置）。
    # 文字清洗只作用于「提取出的文本」，绝不改动用于定位的源串。
    def _clean_text(s):
        s = s.replace('&nbsp;', ' ')
        s = re.sub(r'<[^>]+>', '', s)
        s = re.sub(r'\s+', ' ', s)
        return s.strip()

    # 提取 h1 标题
    title_match = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.DOTALL)
    title = _clean_text(title_match.group(1)) if title_match else ''
    # 兼容 QingFeng-GZH-Layout 排版（无 h1，标题在第一个 section 的 span 中）
    if not title:
        sec_match = re.search(r'<section[^>]*>\s*<span[^>]*font-size:\s*2[0-9]px[^>]*>(.*?)</span>', html, re.DOTALL)
        if sec_match:
            title = _clean_text(sec_match.group(1))
        else:
            # 兜底：取第一个 section 的文本
            first_sec = re.search(r'<section[^>]*>(.*?)</section>', html, re.DOTALL)
            if first_sec:
                title = _clean_text(first_sec.group(1))[:60]

    # 提取 body
    body_match = re.search(r'<body[^>]*>(.*?)</body>', html, re.DOTALL | re.IGNORECASE)
    body_html = body_match.group(1) if body_match else html

    elements = []

    # 标题 h2/h3（跳过 h1，那是文章主标题）—— 统一基于 html 定位
    for m in re.finditer(r'<(h[23])[^>]*>(.*?)</\1>', html, re.DOTALL):
        tag = m.group(1)
        text = _clean_text(m.group(2))
        if text:
            level = int(tag[1])
            elements.append(('title', level, text, m.start()))

    # 段落 p 和 div.paragraph —— 统一基于 html 定位
    for pattern in [r'<p[^>]*>(.*?)</p>', r'<div[^>]*class="[^"]*paragraph[^"]*"[^>]*>(.*?)</div>']:
        for m in re.finditer(pattern, html, re.DOTALL):
            text = _clean_text(m.group(1))
            if len(text) > 5:
                elements.append(('text', text, m.start()))

    # 图片 img（收集路径，但不插入正文——Step 4 才插入）
    for m in re.finditer(r'<img[^>]+src=["\']([^"\']+)["\'][^>]*>', html):
        src = m.group(1)
        alt_m = re.search(r'alt=["\']([^"\']*)["\']', m.group(0))
        alt = alt_m.group(1) if alt_m else ''
        if not os.path.isabs(src):
            abs_src = os.path.join(base_dir, src)
        else:
            abs_src = src
        elements.append(('image', abs_src, alt, m.start()))

    elements.sort(key=lambda x: x[-1])
    return title, body_html, base_dir, elements


def find_image_files(base_dir, body_html):
    """查找配图文件（排除封面图 cover.*，避免封面被插入正文导致重复）"""
    images = []
    srcs = re.findall(r'src=["\']([^"\']+\.(?:jpg|jpeg|png|gif|webp))["\']', body_html, re.IGNORECASE)
    seen = set()
    for src in srcs:
        abs_path = os.path.join(base_dir, src) if not os.path.isabs(src) else src
        fname = os.path.basename(abs_path)
        # 跳过封面图文件（cover.jpg 等），封面由 Step 6 单独处理
        if re.match(r'^cover\.', fname, re.IGNORECASE):
            continue
        if fname not in seen and os.path.exists(abs_path):
            seen.add(fname)
            images.append((fname, abs_path))

    if not images:
        for f in sorted(os.listdir(base_dir)):
            if re.match(r'^illustration_\d+\.(jpg|jpeg|png|gif|webp)$', f, re.IGNORECASE):
                abs_path = os.path.join(base_dir, f)
                if f not in seen:
                    seen.add(fname)
                    images.append((f, abs_path))

    def sort_key(item):
        m = re.match(r'illustration_(\d+)', item[0], re.IGNORECASE)
        return int(m.group(1)) if m else 999
    images.sort(key=sort_key)
    return images


def find_cover_image(base_dir, first_image_path=None):
    for c in ['cover.jpg', 'cover.png', 'cover.jpeg', 'Cover.jpg', 'Cover.png']:
        p = os.path.join(base_dir, c)
        if os.path.exists(p):
            return p
    return first_image_path


# ============================================================
# 核心流程
# ============================================================
def wechat_publish(html_path, author=DEFAULT_AUTHOR, cover_path=None):
    print(f"Parsing HTML: {html_path}")
    title, body_html, base_dir, elements = parse_html(html_path)
    print(f"  Title: {title}")

    article_images = find_image_files(base_dir, body_html)
    print(f"  Found {len(article_images)} images:")
    for fname, fpath in article_images:
        print(f"    {fname} ({os.path.getsize(fpath)//1024}KB)")

    if not cover_path:
        cover_path = find_cover_image(base_dir, article_images[0][1] if article_images else None)
    print(f"  Cover: {cover_path}")

    # ===== 自动启动 Edge（用户真实 profile，保留登录态）=====
    import subprocess, socket, urllib.request, json
    
    CFT_PATH = r"D:\chenw\chrome-win64\chrome.exe"
    CFT_PROFILE = r"--user-data-dir=D:\chenw\chrome-test-profile"
    
    def _ensure_cft(open_url=None):
        """确保 Edge 在运行（带 remote debugging），返回实际 CDP 端口"""
        # 先检查 9222 端口
        for port in [9222]:
            try:
                resp = urllib.request.urlopen(f'http://127.0.0.1:{port}/json', timeout=2)
                tabs = json.loads(resp.read())
                print(f"  Chrome for Testing already running on port {port} ({len(tabs)} tabs)")
                if open_url:
                    import urllib.parse as _up
                    urllib.request.urlopen(f'http://127.0.0.1:{port}/json/new?{_up.quote(open_url, safe="")}', timeout=5)
                    time.sleep(3)
                    print(f"  Opened URL via CDP: {open_url[:60]}")
                return port
            except Exception:
                pass
        
        # Edge 未运行，启动它（使用用户真实 profile）
        def get_free_port():
            with socket.socket() as s:
                s.bind(('', 0))
                return s.getsockname()[1]
        
        port = get_free_port()
        cmd = [CFT_PATH, CFT_PROFILE,
               f"--remote-debugging-port={port}",
               "--remote-allow-origins=*",
               "--no-first-run",
               "--no-default-browser-check"]
        if open_url:
            cmd.append(open_url)
        print(f"  Starting Chrome for Testing on port {port}...")
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        for _ in range(20):
            try:
                time.sleep(1)
                resp = urllib.request.urlopen(f'http://127.0.0.1:{port}/json', timeout=2)
                tabs = json.loads(resp.read())
                print(f"  Chrome for Testing ready on port {port} ({len(tabs)} tabs)")
                return port
            except Exception:
                continue
        raise Exception("Chrome for Testing failed to start")
    
    MP_HOME_URL = 'https://mp.weixin.qq.com/cgi-bin/home?t=home/index&lang=zh_CN'
    actual_cdp_port = _ensure_cft()
    cdp_url = f'http://127.0.0.1:{actual_cdp_port}'

    print(f"\nConnecting to CDP: {cdp_url}")
    p = sync_playwright().start()
    browser = p.chromium.connect_over_cdp(cdp_url)
    context = browser.contexts[0]

    # ===== 导航到新建图文（通过页面内点击，避免直接 goto 触发登录拦截）=====
    print(f"=== Opening NEW draft ===")
    
    # ===== 导航策略：绝对不用 page.goto()！=====
    # 通过 CDP /json/new 接口打开 URL（模拟用户地址栏输入回车）
    page = None
    home_page = None
    for p in context.pages:
        url = p.url
        if 'appmsg' in url and 'edit' in url:
            page = p
        elif 'home' in url and 'mp.weixin' in url:
            home_page = p
    
    if page:
        print(f"  Reusing existing editor: {page.url[:80]}")
        # 清理旧正文内容（确保 CDN URL 检测准确）
        page.evaluate("""() => {
            const el = document.querySelectorAll('.ProseMirror')[1];
            if (el) {
                el.querySelectorAll('img').forEach(img => img.remove());
                el.textContent = '';
            }
        }""")
    elif home_page:
        print(f"  Home: {home_page.url[:80]}")
        print("  Clicking \u6587\u7ae0 (JS)...")
        try:
            ok = home_page.evaluate("""() => {
    for (const el of document.querySelectorAll('*')) {
    if (el.textContent.trim() === '\u6587\u7ae0' && el.offsetParent !== null && el.children.length === 0) {
                let pp = el.parentElement, d=0;
                while(pp && d<10) { if(getComputedStyle(pp).cursor==='pointer'||pp.onclick) {pp.click();return true;} pp=pp.parentElement;d++; }
                el.click(); return true;
            }
        }
        return false;
    }""")
            if not ok:
                print("  ERROR: \u6587\u7ae0 not found"); # browser.disconnect()  # 保持浏览器运行; return
            print("  Clicked OK")
        except Exception as e:
            print(f"  ERROR: {e}"); # browser.disconnect()  # 保持浏览器运行; return
        
        # 用 Playwright expect_event 等待新标签页（官方方式）
        print("  Waiting for editor tab (via expect_event)...")
        try:
            with context.expect_page(timeout=30000) as new_page_info:
                pass
            page = new_page_info.value
            print(f"  Editor opened: {page.url[:80]}")
        except Exception as e2:
            print(f"  expect_event failed ({e2}), trying CDP /json fallback...")
            import urllib.request as _ur, json as _js
            time.sleep(3)
            try:
                _resp = _ur.urlopen(f'{cdp_url}/json', timeout=3)
                _tabs = _js.loads(_resp.read())
                editor_ws = None
                for _t in _tabs:
                    if 'appmsg' in _t.get('url', '') and 'edit' in _t.get('url', ''):
                        editor_ws = _t.get('webSocketDebuggerUrl'); break
                if editor_ws:
                    # 用 CDP websocket URL 直接连接到编辑器页面
                    from playwright.sync_api import sync_playwright as _sp2
                    page = None
                    # 在已有 context 中找匹配的 page
                    for _p in context.pages:
                        if 'appmsg' in _p.url:
                            page = _p; break
                    if not page:
                        print("  ERROR: Editor tab found via CDP but not in Playwright context")
                        # browser.disconnect()  # 保持浏览器运行; return
                    print(f"  Editor via CDP fallback: {page.url[:80]}")
                else:
                    print("  ERROR: No editor in CDP tabs"); # browser.disconnect()  # 保持浏览器运行; return
            except Exception as e3:
                print(f"  CDP fallback also failed: {e3}"); # browser.disconnect()  # 保持浏览器运行; return
    else:
        # 没有公众号页面 —— 通过 CDP /json/new 打开首页（非 goto）
        print("  No WeChat MP page, opening via CDP /json/new ...")
        import urllib.parse as _up2
        encoded = _up2.quote(MP_HOME_URL, safe='')
        try:
            urllib.request.urlopen(f'{cdp_url}/json/new?{encoded}', timeout=10)
            print("  CDP /json/new OK")
            time.sleep(5)
        except Exception as ex:
            print(f"  CDP /json/new failed ({ex}), using page.goto ...")
            fp = None
            for p in context.pages:
                if not p.url.startswith('chrome-extension://') and not p.url.startswith('edge://'):
                    fp = p; break
            if not fp:
                fp = context.pages[0]
            try:
                fp.goto(MP_HOME_URL, wait_until='domcontentloaded', timeout=30000)
                print(f"  Navigated to MP home: {fp.url[:80]}")
                # 等待页面完全加载（网络空闲）
                try:
                    fp.wait_for_load_state('networkidle', timeout=15000)
                except Exception:
                    pass
                time.sleep(3)
            except Exception as goto_ex:
                print(f"  page.goto failed ({goto_ex}), trying location.href ...")
                fp.evaluate(f'() => {{ window.location.href = "{MP_HOME_URL}"; }}')
                time.sleep(8)
        
        # 重新获取页面引用（导航后 page 对象可能失效）
        home_page = None
        for p in context.pages:
            u = p.url
            if 'appmsg' in u and 'edit' in u:
                page = p
            elif 'home' in u and 'mp.weixin' in u:
                home_page = p
        
        if page:
            print(f"  Editor exists: {page.url[:80]}")
        elif home_page:
            print(f"  Home loaded: {home_page.url[:80]}, clicking \u6587\u7ae0...")
            # 确保页面加载完成后再点击
            try:
                home_page.wait_for_load_state('domcontentloaded', timeout=10000)
            except Exception:
                pass
            time.sleep(2)
            try:
                ok = home_page.evaluate("""() => {
    for (const el of document.querySelectorAll('*')) {
    if (el.textContent.trim() === '\u6587\u7ae0' && el.offsetParent !== null && el.children.length === 0) {
                let pp = el.parentElement, d=0;
                while(pp && d<10) { if(getComputedStyle(pp).cursor==='pointer'||pp.onclick) {pp.click();return true;} pp=pp.parentElement;d++; }
                el.click(); return true;
            }
        }
        return false;
    }""")
                if not ok:
                    print("  ERROR: \u6587\u7ae0 not found"); # browser.disconnect()  # 保持浏览器运行; return
            except Exception as e:
                print(f"  ERROR: {e}"); # browser.disconnect()  # 保持浏览器运行; return
            
            for i in range(15):
                time.sleep(1)
                for p in context.pages:
                    if ('appmsg' in p.url or 'edit' in p.url) and p != home_page:
                        page = p; break
                if page: break
            
            if not page:
                print("  ERROR: Editor not found"); # browser.disconnect()  # 保持浏览器运行; return
            print(f"  Editor opened: {page.url[:80]}")
        else:
            print("  ERROR: No home/editor. Tabs:")
            for p in context.pages:
                print(f"    - {p.url[:100]}")
            # browser.disconnect()  # 保持浏览器运行; return

    print(f"\n=== Step 1: Select Main Template ===")
    select_template(page)
    time.sleep(2)

    # ===== Step 2: 上传图片 → 收集 CDN URL =====
    # 注意：这里只上传，不往正文插入内容（图片先存起来备用）
    print(f"\n=== Step 2: Upload Images & Collect CDN URLs ===")
    cdn_urls = upload_all_images(page, article_images)
    success_count = sum(1 for v in cdn_urls.values() if v)
    print(f"\n  Uploaded: {success_count}/{len(article_images)}")
    for fname, fpath in article_images:
        url = cdn_urls.get(fname)
        status = "OK" if url else "FAIL"
        print(f"    [{status}] {fname}: {(url[:70]+'...') if url else 'N/A'}")

    # ===== Step 3: 注入完整内容（文字+图片，按原序交替）=====
    # selectAll→delete→insertHTML 一次性注入，图片用 CDN URL
    print(f"\n=== Step 3: Inject Content (text + images) ===")
    inject_styled_content(page, body_html, base_dir, cdn_urls, article_images)

    # ===== Step 4: 填写标题和作者 =====
    print(f"\n=== Step 4: Set Titles & Author ===")
    set_titles_and_author(page, title, author)

    # ===== Step 5: 清理 broken 图片 =====
    page.evaluate("""() => {
        const el = document.querySelectorAll('.ProseMirror')[1];
        if (!el) return 0;
        let cnt = 0;
        el.querySelectorAll('img').forEach(img => {
            if (!img.src || img.naturalWidth === 0 || img.naturalHeight === 0) {
                img.remove();
                cnt++;
            }
        });
        return cnt;
    }""")

    # ===== Step 6: 保存草稿 =====
    print(f"\n=== Step 6: Save Draft ===")
    saved = page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            if (el.children.length === 0 && el.textContent.trim() === '保存为草稿' && el.offsetParent !== null) {
                el.click();
                return true;
            }
        }
        return false;
    }""")
    if saved:
        print("  已点击保存为草稿")
        time.sleep(3)
    else:
        print("  WARNING: 未找到保存为草稿按钮")

    # ===== Step 7: 最终验证 =====
    print(f"\n=== Step 7: Final Verification ===")
    result = final_verification(page, title, author)

    ts = time.strftime('%Y%m%d_%H%M%S')
    screenshot_path = os.path.join(os.getcwd(), f'wechat_publish_{ts}.png')
    page.screenshot(path=screenshot_path, full_page=True)
    print(f"\n  Screenshot: {screenshot_path}")

    # 不关闭浏览器 —— 脚本结束后 Chrome 保持打开，停留在当前页面

    print(f"\n{'='*50}")
    print(f"DONE! Please review and publish manually.")
    print(f"{'='*50}")


# ============================================================
# 各步骤实现
# ============================================================

def select_template(page):
    """Step 1: 选择主模板"""
    result = page.evaluate("""() => {
        const templateSelectors = [
            '[class*="template-item"]', '[class*="TemplateItem"]',
            '[class*="main-template"]', '[class*="MainTemplate"]',
        ];
        let found = [];
        templateSelectors.forEach(sel => {
            try {
                document.querySelectorAll(sel).forEach(el => {
                    found.push({
                        selector: sel,
                        text: el.textContent?.trim().substring(0, 50),
                        className: el.className?.toString().substring(0, 80),
                        visible: el.offsetParent !== null
                    });
                });
            } catch(e) {}
        });
        return found;
    }""")

    print(f"  Found {len(result)} template elements")
    for r in result[:8]:
        print(f"    [{'VIS' if r['visible'] else 'hid'}] {r['selector']} | {r['text'][:40]} | {r['className'][:60]}")

    clicked = page.evaluate("""() => {
        const candidates = [
            () => {
                const items = document.querySelectorAll('[class*="template-item"], [class*="TemplateItem"]');
                for (const item of items) { if (item.offsetParent !== null) { item.click(); return 'template-item'; } }
                return null;
            },
            () => {
                for (const el of document.querySelectorAll('*')) {
                    if (el.children.length === 0 && el.textContent?.trim() === '主模板' && el.offsetParent !== null) {
                        el.click(); return 'text-main-template';
                    }
                }
                return null;
            },
            () => {
                for (const el of document.querySelectorAll('*')) {
                    const t = el.textContent?.trim();
                    if ((t === '默认' || t === '基础' || t === '空白') && el.children.length <= 2 && el.offsetParent !== null) {
                        el.click(); return 'text-default';
                    }
                }
                return null;
            }
        ];
        for (const fn of candidates) { const r = fn(); if (r) return r; }
        return 'none-found';
    }""")

    print(f"  Selection result: {clicked}")
    if clicked == 'none-found':
        print("  WARNING: Could not auto-select template.")


def upload_all_images(page, article_images):
    """Step 2: 逐张上传，收集 CDN URL（不上传正文）"""
    cdn_urls = {}

    for idx, (img_name, img_path) in enumerate(article_images):
        if not os.path.exists(img_path):
            print(f"    [{idx+1}/{len(article_images)}] SKIP {img_name} - not found")
            continue

        size_kb = os.path.getsize(img_path) // 1024
        print(f"    [{idx+1}/{len(article_images)}] Uploading {img_name} ({size_kb}KB)...")

        # 上传后临时记录数量（实际图片由 Step 4 插入正文）
        before_count = page.evaluate("""() => {
            const el = document.querySelectorAll('.ProseMirror')[1];
            if (!el) return 0;
            let cnt = 0;
            el.querySelectorAll('img').forEach(img => {
                if (img.src.includes('mmbiz.qpic.cn') && img.naturalWidth > 100) cnt++;
            });
            return cnt;
        }""")

        uploaded = False
        for fi in page.query_selector_all('input[type="file"]'):
            try:
                fi.set_input_files(img_path)
                uploaded = True
                break
            except Exception:
                continue

        if not uploaded:
            print(f"      ERROR: No file input")
            continue

        time.sleep(UPLOAD_WAIT)

        after_info = page.evaluate("""(beforeCnt) => {
            const el = document.querySelectorAll('.ProseMirror')[1];
            if (!el) return {newOnes: []};
            const imgs = el.querySelectorAll('img');
            const mmbizImgs = [];
            imgs.forEach(img => {
                if (img.src.includes('mmbiz.qpic.cn') && img.naturalWidth > 100) mmbizImgs.push({src: img.src, w: img.naturalWidth, h: img.naturalHeight});
            });
            return {newOnes: mmbizImgs.slice(beforeCnt)};
        }""", before_count)

        if after_info['newOnes']:
            cdn_urls[img_name] = after_info['newOnes'][-1]['src']
            print(f"      OK! {after_info['newOnes'][-1]['w']}x{after_info['newOnes'][-1]['h']}")
        else:
            time.sleep(RETRY_WAIT)
            retry_info = page.evaluate("""(beforeCnt) => {
                const el = document.querySelectorAll('.ProseMirror')[1];
                if (!el) return {newOnes: []};
                let imgs = [];
                el.querySelectorAll('img').forEach(img => {
                    if (img.src.includes('mmbiz.qpic.cn') && img.naturalWidth > 100) imgs.push({src: img.src});
                });
                return {newOnes: imgs.slice(beforeCnt)};
            }""", before_count)
            if retry_info['newOnes']:
                cdn_urls[img_name] = retry_info['newOnes'][-1]['src']
                print(f"      OK (retry)!")
            else:
                print(f"      WARNING: Upload may have failed")

        time.sleep(0.5)

    return cdn_urls




def inject_styled_content(page, body_html, base_dir, cdn_urls, article_images):
    """Step 3: 直接注入完整排版 HTML（保留 QingFeng-GZH-Layout 全内联样式），只替换本地图片路径为 CDN URL。

    不再解析 elements 重建简化 HTML，而是使用原始排版 HTML 的 body 内容，
    确保背景色块小标题、左竖线引用、字体颜色、字间距、section 嵌套等样式全部保留。
    """
    # 构建 本地路径/文件名 → CDN URL 映射
    src_to_cdn = {}
    for fname, fpath in article_images:
        url = cdn_urls.get(fname)
        if url:
            src_to_cdn[fname] = url
            src_to_cdn[os.path.basename(fpath)] = url
            abs_norm = fpath.replace('\\', '/')
            src_to_cdn[abs_norm] = url
            # 相对路径（HTML 中可能用的是相对路径）
            rel_path = os.path.relpath(fpath, base_dir).replace('\\', '/')
            src_to_cdn[rel_path] = url

    # 替换 body_html 中的图片路径为 CDN URL
    styled_html = body_html
    replaced = 0
    for local_src, cdn_url in src_to_cdn.items():
        if not local_src or not cdn_url:
            continue
        # 替换 src="local" 或 src='local'
        pattern = r'(src=["\'])' + re.escape(local_src) + r'(["\'])'
        new_html, n = re.subn(pattern, r'\1' + cdn_url + r'\2', styled_html)
        if n > 0:
            styled_html = new_html
            replaced += n

    print(f'  Replaced {replaced} image src with CDN URLs')
    print(f'  Styled HTML: {len(styled_html)} chars')

    # 注入：清理旧内容 → 直接 innerHTML 写入完整排版
    inject_result = page.evaluate("""(html) => {
        const el = document.querySelectorAll('.ProseMirror')[1];
        if (!el) return {error: 'no editor'};
        // 清理所有 broken/本地图片
        const allImgs = el.querySelectorAll('img');
        allImgs.forEach(img => {
            const isLocal = !img.src ||
                img.src.startsWith('file://') ||
                img.src.startsWith('blob:') ||
                img.src.includes('illustration_') ||
                img.src.includes('cover.') ||
                img.naturalWidth === 0;
            if (isLocal) img.remove();
        });
        // 直接 innerHTML 注入完整排版（保留所有内联样式）
        el.innerHTML = html;
        return {
            textLen: el.textContent.length,
            imgCount: el.querySelectorAll('img').length,
            sectionCount: el.querySelectorAll('section').length,
            preview: el.textContent.substring(0, 100)
        };
    }""", styled_html)

    print(f'  Inject (styled): text={inject_result.get("textLen", 0)} chars, '
          f'imgs={inject_result.get("imgCount", 0)}, '
          f'sections={inject_result.get("sectionCount", 0)}')
    if inject_result.get('preview'):
        print(f'  Preview: {inject_result["preview"][:100]}')
    if inject_result.get('error'):
        print(f'  ERROR: {inject_result["error"]}')


def inject_content_by_blocks(page, elements, cdn_urls, article_images):
    """Step 3: 注入正文内容（文字+图片按原序交替）。

    修复（2026-07-04）：放弃 selectAll→delete→insertHTML，
    该方式触发 ProseMirror 自动同步，把注入内容清空（text→0），
    图片因有 CDN URL 部分保留，导致图文位置全错乱。
    新方案：直接 innerHTML 替换 + 注入前清理 broken 图片。
    """
    src_to_cdn = {}
    for fname, fpath in article_images:
        url = cdn_urls.get(fname)
        if url:
            src_to_cdn[fname] = url
            src_to_cdn[os.path.splitext(fname)[0]] = url
            src_to_cdn[os.path.basename(fpath)] = url

    html_parts = []
    for elem in elements:
        etype = elem[0]
        if etype == 'title':
            html_parts.append('<p><strong>{}</strong></p>'.format(elem[2]))
        elif etype == 'text':
            text = elem[1]
            if len(text) > 20 and '{' in text and '}' in text and (';' in text or ':' in text):
                print(f'    Skipping CSS/JS-like text ({len(text)} chars)')
                continue
            for para in text.split('\n'):
                para = para.strip()
                if para:
                    html_parts.append('<p>{}</p>'.format(para))
        elif etype == 'image':
            img_fname = os.path.basename(elem[1])
            cdn_url = (src_to_cdn.get(img_fname) or
                       src_to_cdn.get(elem[1]) or
                       next((v for k, v in src_to_cdn.items()
                            if img_fname in k or k in img_fname), None))
            if cdn_url:
                html_parts.append(
                    '<p style="text-align:center">'
                    '<img src="{}" style="width:100%;height:auto;" />'
                    '</p>'.format(cdn_url)
                )
            else:
                print(f'    Skipping image (no CDN): {img_fname}')

    new_html = '\n'.join(html_parts)
    print(f'  Built HTML: {len(html_parts)} blocks, {len(new_html)} chars')

    inject_result = page.evaluate("""(html) => {
        const el = document.querySelectorAll('.ProseMirror')[1];
        if (!el) return {error: 'no editor'};

        // 1. 清理所有 broken 图片（src 为空/local/naturalWidth=0）
        const allImgs = el.querySelectorAll('img');
        allImgs.forEach(img => {
            const isLocal = !img.src ||
                img.src.startsWith('file://') ||
                img.src.startsWith('blob:') ||
                img.src.includes('illustration_') ||
                img.src.includes('cover.') ||
                img.naturalWidth === 0;
            if (isLocal) img.remove();
        });

        // 2. 直接 innerHTML 替换（不触发 execCommand，无回滚风险）
        el.innerHTML = html;

        return {
            textLen: el.textContent.length,
            imgCount: el.querySelectorAll('img').length,
            preview: el.textContent.substring(0, 100)
        };
    }""", new_html)

    print(f'  Inject: text={inject_result.get("textLen", 0)} chars, imgs={inject_result.get("imgCount", 0)}')
    if inject_result.get('preview'):
        print(f'  Preview: {inject_result["preview"][:100]}')
    if inject_result.get('error'):
        print(f'  ERROR: {inject_result["error"]}')



def set_titles_and_author(page, title, author):
    """Step 5: 填写三处标题/作者"""
    # 4a + 4c: 左侧标题 + 作者（用 dict 单参数）
    page.evaluate("""(args) => {
        const t = args.title;
        const a = args.author;
        const titleInput = document.querySelector('#title');
        if (titleInput) {
            titleInput.value = t;
            titleInput.dispatchEvent(new Event('input', {bubbles: true}));
            titleInput.dispatchEvent(new Event('change', {bubbles: true}));
        }
        const authorInput = document.querySelector('#author');
        if (authorInput) {
            authorInput.value = a;
            authorInput.dispatchEvent(new Event('input', {bubbles: true}));
            authorInput.dispatchEvent(new Event('change', {bubbles: true}));
        }
    }""", {"title": title, "author": author})

    # 4b: 正文上方标题
    page.evaluate("""(t) => {
        const titleEditor = document.querySelectorAll('.ProseMirror')[0];
        if (titleEditor) {
            titleEditor.focus();
            document.execCommand('selectAll', false, null);
            document.execCommand('delete', false, null);
            document.execCommand('insertHTML', false, '<p><strong>' + t + '</strong></p>');
        }
    }""", title)

    print(f"  Left title: '{title}', Author: '{author}'")
    time.sleep(1)


def upload_cover_image(page, cover_path):
    """Step 6: 上传封面图"""
    if not cover_path or not os.path.exists(cover_path):
        print("  Cover not found, skipping")
        return

    print(f"  Uploading cover: {os.path.basename(cover_path)} ({os.path.getsize(cover_path)//1024}KB)...")
    uploaded = False
    for fi in page.query_selector_all('input[type="file"]'):
        try:
            fi.set_input_files(cover_path)
            uploaded = True
            print("  Cover file set")
            break
        except Exception:
            continue

    if uploaded:
        time.sleep(4)
    else:
        print("  WARNING: Could not upload cover")



def _click_by_text(page, text, timeout=5):
    """通过文字找到元素并点击，返回是否成功"""
    result = page.evaluate("""(txt) => {
        const all = document.querySelectorAll('*');
        for (const el of all) {
            if (el.children.length === 0 && el.textContent.trim() === txt && el.offsetParent !== null) {
                const r = el.getBoundingClientRect();
                return {x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2), found: true};
            }
        }
        return {found: false};
    }""", text)
    if result and result.get('found'):
        page.mouse.click(result['x'], result['y'])
        time.sleep(1)
        return True
    return False


def set_cover_from_first_image(page):
    """Step 5: 直接上传封面文件（从图片库上传，不依赖正文图片）"""
    import os as _os
    cover_path = _os.path.join(_os.path.dirname(__file__), '..', '..', '..', '..', '知识库', '媒体运营', '26.8.31', 'pb', 'cover_gzh_big.jpg')
    # 尝试多个可能的封面路径
    possible_paths = [
        r'D:\知识库\媒体运营\26.8.31\pb\cover_gzh_big.jpg',
        r'D:\知识库\媒体运营\26.8.31\pb\illustration_1.jpg',
    ]
    cover_path = None
    for p in possible_paths:
        if _os.path.exists(p):
            cover_path = p
            break
    if not cover_path:
        print("  WARNING: Cover image not found, skipping")
        return

    print(f"  Uploading cover: {_os.path.basename(cover_path)}")

    # 滚动到封面区域
    page.evaluate("""() => {
        const el = document.querySelector('.setting-group__cover_area');
        if (el) el.scrollIntoView({block: 'center'});
    }""")
    time.sleep(1)

    # 点击封面区域
    cover_btn = page.evaluate("""() => {
        const btn = document.querySelector('.js_cover_btn_area');
        if (!btn) return null;
        const r = btn.getBoundingClientRect();
        return {x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)};
    }""")
    if not cover_btn:
        print("  WARNING: Cover button not found")
        return
    page.mouse.click(cover_btn['x'], cover_btn['y'])
    time.sleep(2)

    # 点击"从图片库选择"
    gallery_clicked = page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            if (el.children.length === 0 && el.textContent.trim() === '从图片库选择' && el.offsetParent !== null) {
                el.click();
                return true;
            }
        }
        return false;
    }""")
    if not gallery_clicked:
        print("  WARNING: '从图片库选择' not found")
        return
    time.sleep(3)

    # 点击"上传文件"
    upload_clicked = page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            if (el.children.length === 0 && el.textContent.trim() === '上传文件' && el.offsetParent !== null) {
                el.click();
                return true;
            }
        }
        return false;
    }""")
    if not upload_clicked:
        print("  WARNING: '上传文件' not found")
        return
    time.sleep(2)

    # 用 file input 上传文件
    uploaded = False
    for fi in page.query_selector_all('input[type="file"]'):
        try:
            fi.set_input_files(cover_path)
            uploaded = True
            print("  Cover file set")
            break
        except Exception:
            continue
    if not uploaded:
        print("  WARNING: Could not upload cover file")
        return
    time.sleep(8)  # 等待上传

    # 选择刚上传的图片（第一张）
    first_img = page.evaluate("""() => {
        const dialog = document.querySelector('.weui-desktop-dialog');
        if (!dialog) return null;
        const imgs = dialog.querySelectorAll('img');
        if (imgs.length > 0) {
            const parent = imgs[0].closest('div, li, [class*="item"]') || imgs[0];
            const r = parent.getBoundingClientRect();
            return {x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)};
        }
        return null;
    }""")
    if first_img:
        page.mouse.click(first_img['x'], first_img['y'])
        print("  Selected uploaded image")
        time.sleep(2)

        # 点击下一步
        page.evaluate("""() => {
            for (const el of document.querySelectorAll('*')) {
                if (el.children.length === 0 && el.textContent.trim() === '下一步' && el.offsetParent !== null) {
                    el.click();
                    return true;
                }
            }
            return false;
        }""")
        time.sleep(3)

        # 点击确认
        page.evaluate("""() => {
            for (const el of document.querySelectorAll('*')) {
                if (el.children.length === 0 && el.textContent.trim() === '确认' && el.offsetParent !== null) {
                    el.click();
                    return true;
                }
            }
            return false;
        }""")
        time.sleep(2)
        print("  Cover set successfully")
    else:
        print("  WARNING: No image found after upload")


def set_original_claim(page):
    """Step 6: 声明原创（文字原创），完整流程包括协议确认"""
    print("  Setting original claim (文字原创)...")

    # 滚动到原创区域
    page.evaluate("""() => {
        const el = document.querySelector('.js_original_apply_cell');
        if (el) el.scrollIntoView({block: 'center'});
    }""")
    time.sleep(1)

    # 检查是否已经声明了原创
    already_original = page.evaluate("""() => {
        const open = document.querySelector('#js_original_open');
        return open && getComputedStyle(open).display !== 'none';
    }""")
    if already_original:
        print("  Already claimed original, skipping")
        return

    # 点击原创开关
    switch = page.evaluate("""() => {
        const el = document.querySelector('.setting-group__switch.js_original_apply');
        if (!el) return null;
        const r = el.getBoundingClientRect();
        return {x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)};
    }""")
    if not switch:
        print("  WARNING: Original switch not found")
        return
    page.mouse.click(switch['x'], switch['y'])
    time.sleep(2)

    # 在对话框中选择"文字原创"
    if not _click_by_text(page, '文字原创'):
        print("  WARNING: '文字原创' not found")
    time.sleep(1)

    # 勾选协议
    page.evaluate("""() => {
        const dialog = document.querySelector('.weui-desktop-dialog');
        if (!dialog) return;
        const checkbox = dialog.querySelector('input[type="checkbox"]');
        if (checkbox) {
            checkbox.checked = true;
            checkbox.dispatchEvent(new Event('change', {bubbles: true}));
        }
    }""")
    time.sleep(1)

    # 点击"确定"
    if _click_by_text(page, '确定'):
        time.sleep(2)
        # 处理可能的二次确认弹窗
        confirm_clicked = False
        for attempt in range(3):
            if _click_by_text(page, '确认'):
                confirm_clicked = True
                time.sleep(2)
                break
            time.sleep(1)
        if confirm_clicked:
            print("  Original claim confirmed")
        print("  Original claim set (文字原创)")
    else:
        print("  WARNING: '确定' button not found in original dialog")


def set_claim_source(page):
    """Step 7: 设置创作来源为'个人观点，仅供参考'"""
    print("  Setting claim source (个人观点，仅供参考)...")

    # 滚动到创作来源区域
    page.evaluate("""() => {
        const el = document.querySelector('#js_claim_source_area');
        if (el) el.scrollIntoView({block: 'center'});
    }""")
    time.sleep(1)

    # 点击创作来源区域
    claim_area = page.evaluate("""() => {
        const el = document.querySelector('#js_claim_source_area');
        if (!el) return null;
        const desc = el.querySelector('.js_claim_source_desc, .allow_click_opr');
        if (desc) {
            const r = desc.getBoundingClientRect();
            return {x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)};
        }
        const r = el.getBoundingClientRect();
        return {x: Math.round(r.x + r.width - 50), y: Math.round(r.y + r.height/2)};
    }""")
    if not claim_area:
        print("  WARNING: Claim source area not found")
        return
    page.mouse.click(claim_area['x'], claim_area['y'])
    time.sleep(2)

    # 选择"个人观点，仅供参考"
    if _click_by_text(page, '个人观点，仅供参考'):
        time.sleep(1)
        # 点击"确认"
        if _click_by_text(page, '确认'):
            time.sleep(2)
            print("  Claim source set: 个人观点，仅供参考")
        else:
            print("  WARNING: '确认' not found in claim source dialog")
    else:
        print("  WARNING: '个人观点，仅供参考' not found")


def final_verification(page, expected_title, expected_author):
    """Step 7: 最终验证"""
    result = page.evaluate("""() => {
        const titleEditor = document.querySelectorAll('.ProseMirror')[0];
        const bodyEditor = document.querySelectorAll('.ProseMirror')[1];
        const imgs = bodyEditor ? bodyEditor.querySelectorAll('img') : [];
        let okCount = 0, phCount = 0;
        const details = Array.from(imgs).map((img, i) => {
            const isReal = img.src.includes('mmbiz.qpic.cn') && img.naturalWidth > 100;
            const isPh = img.src.includes('illustration_');
            if (isReal) okCount++;
            else if (isPh) phCount++;
            return {
                idx: i,
                src: img.src.substring(0, 100),
                w: img.naturalWidth,
                h: img.naturalHeight,
                status: isReal ? 'OK' : (isPh ? 'PH' : 'BAD')
            };
        });
        return {
            leftTitle: document.querySelector('#title')?.value || '',
            bodyTitle: titleEditor?.textContent.trim() || '',
            author: document.querySelector('#author')?.value || '',
            textLength: bodyEditor?.textContent.length || 0,
            totalImages: imgs.length,
            okImages: okCount,
            phImages: phCount,
            details
        };
    }""")

    print(f"  Left title:   {result['leftTitle']}")
    print(f"  Body title:   {result['bodyTitle']}")
    print(f"  Author:       {result['author']}")
    print(f"  Text length:  {result['textLength']} chars")
    print(f"  Images:       {result['okImages']}/{result['totalImages']} valid (CDN)")
    print(f"  Placeholders: {result['phImages']}")

    for d in result['details']:
        print(f"    [{d['idx']}] [{d['status']}] {d['w']}x{d['h']} {d['src'][:70]}")

    return result


# ============================================================
# 入口
# ============================================================
def main():
    parser = argparse.ArgumentParser(description='WeChat Article Publisher v4')
    parser.add_argument('html_file', help='Path to the HTML file')
    parser.add_argument('--author', default=DEFAULT_AUTHOR, help=f'Author (default: {DEFAULT_AUTHOR})')
    parser.add_argument('--cover', default=None, help='Cover image path (default: auto-detect)')
    args = parser.parse_args()

    if not os.path.exists(args.html_file):
        print(f"ERROR: File not found: {args.html_file}")
        sys.exit(1)

    wechat_publish(args.html_file, author=args.author, cover_path=args.cover)

if __name__ == '__main__':
    main()