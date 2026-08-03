# -*- coding: utf-8 -*-
"""
微信公众号自动发布脚本（正式版）
基于 v3 验证成功的完整流程

流程：
  Step 0: 连接 CDP + 解析 HTML
  Step 1: 选择主模板
  Step 2: 上传所有图片，收集 CDN URL
  Step 3: 构建完整 HTML → execCommand 一次性注入
  Step 4: 填写左侧标题 + 正文上方标题 + 作者
  Step 5: 上传封面图（用文章第一张配图）
  Step 6: 最终验证 + 截图

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
CDP_URL = 'http://localhost:9222'
DEFAULT_AUTHOR = '轻风偏教'

UPLOAD_WAIT = 4       # 大图上传等待秒数
RETRY_WAIT = 3        # 重试等待秒数


# ============================================================
# HTML 解析（与 publish.py 相同逻辑）
# ============================================================
def parse_html(html_path):
    """解析 HTML 文件，提取标题、正文块和图片路径"""
    with open(html_path, 'r', encoding='utf-8') as f:
        html = f.read()

    base_dir = os.path.dirname(os.path.abspath(html_path))

    # 预处理
    html_clean = html.replace('&nbsp;', ' ')
    html_clean = re.sub(r' {2,}', ' ', html_clean)

    # 提取标题
    title_match = re.search(r'<h1[^>]*>(.*?)</h1>', html_clean, re.DOTALL)
    title = re.sub(r'<[^>]+>', '', title_match.group(1)).strip() if title_match else ''

    # 提取 body 内容用于注入编辑器
    body_match = re.search(r'<body[^>]*>(.*?)</body>', html, re.DOTALL | re.IGNORECASE)
    body_html = body_match.group(1) if body_match else html

    # 按顺序提取所有元素的位置信息
    elements = []

    # 标题 h2/h3
    for m in re.finditer(r'<(h[23])[^>]*>(.*?)</\1>', html_clean, re.DOTALL):
        tag = m.group(1)
        text = re.sub(r'<[^>]+>', '', m.group(2)).strip()
        if text:
            level = int(tag[1])
            elements.append(('title', level, text, m.start()))

    # 段落 p 和 div.paragraph
    for pattern in [r'<p[^>]*>(.*?)</p>', r'<div[^>]*class="[^"]*paragraph[^"]*"[^>]*>(.*?)</div>']:
        for m in re.finditer(pattern, html_clean, re.DOTALL):
            text = re.sub(r'<[^>]+>', '', m.group(1)).strip()
            if len(text) > 5:  # 排除空段落
                elements.append(('text', text, m.start()))

    # 图片 img
    for m in re.finditer(r'<img[^>]+src=["\']([^"\']+)["\'][^>]*>', html):
        src = m.group(1)
        alt_m = re.search(r'alt=["\']([^"\']*)["\']', m.group(0))
        alt = alt_m.group(1) if alt_m else ''
        # 转为绝对路径
        if not os.path.isabs(src):
            abs_src = os.path.join(base_dir, src)
        else:
            abs_src = src
        elements.append(('image', abs_src, alt, m.start()))

    # 按位置排序
    elements.sort(key=lambda x: x[-1])

    return title, body_html, base_dir, elements


def find_image_files(base_dir, body_html):
    """
    从 HTML 所在目录中查找配图文件。
    规则：查找 illustration_N.jpg/png 以及 HTML 中引用的图片。
    返回：[(filename, abs_path), ...] 按 N 排序
    """
    images = []

    # 方式1：从 body_html 的 img src 中提取
    srcs = re.findall(r'src=["\']([^"\']+\.(?:jpg|jpeg|png|gif|webp))["\']', body_html, re.IGNORECASE)
    seen = set()
    for src in srcs:
        if not os.path.isabs(src):
            abs_path = os.path.join(base_dir, src)
        else:
            abs_path = src
        fname = os.path.basename(abs_path)
        if fname not in seen and os.path.exists(abs_path):
            seen.add(fname)
            images.append((fname, abs_path))

    # 方式2：扫描目录中的 illustration_N 文件
    if not images:
        for f in sorted(os.listdir(base_dir)):
            if re.match(r'^illustration_\d+\.(jpg|jpeg|png|gif|webp)$', f, re.IGNORECASE):
                abs_path = os.path.join(base_dir, f)
                if f not in seen:
                    seen.add(f)
                    images.append((f, abs_path))

    # 按 illustration_N 的数字排序
    def sort_key(item):
        m = re.match(r'illustration_(\d+)', item[0], re.IGNORECASE)
        return int(m.group(1)) if m else 999
    images.sort(key=sort_key)

    return images


def find_cover_image(base_dir, first_image_path=None):
    """查找封面图：优先 cover.jpg，否则用第一张配图"""
    cover_candidates = ['cover.jpg', 'cover.png', 'cover.jpeg', 'Cover.jpg', 'Cover.png']
    for c in cover_candidates:
        p = os.path.join(base_dir, c)
        if os.path.exists(p):
            return p
    # 回退到第一张配图
    return first_image_path


# ============================================================
# 核心：微信发布流程
# ============================================================
def wechat_publish(html_path, author=DEFAULT_AUTHOR, cover_path=None):
    """执行微信公众号发布的完整流程"""

    # 解析 HTML
    print(f"Parsing HTML: {html_path}")
    title, body_html, base_dir, elements = parse_html(html_path)
    print(f"  Title: {title}")
    print(f"  Base dir: {base_dir}")

    # 查找配图
    article_images = find_image_files(base_dir, body_html)
    print(f"  Found {len(article_images)} images:")
    for fname, fpath in article_images:
        size = os.path.getsize(fpath) // 1024
        print(f"    {fname} ({size}KB)")

    # 封面图
    if not cover_path:
        cover_path = find_cover_image(base_dir, article_images[0][1] if article_images else None)
    print(f"  Cover: {cover_path}")

    # ================================================================
    # 连接浏览器
    # ================================================================
    print(f"\nConnecting to CDP: {CDP_URL}")

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(CDP_URL)
        context = browser.contexts[0]
        # 遍历所有页面找到编辑器 tab
        page = None
        for p in context.pages:
            if 'appmsg_edit' in p.url:
                page = p
                break
        if not page:
            page = context.pages[0]
        
        print(f"  Current URL: {page.url}")

        # 如果不在编辑器页面，尝试导航
        if 'appmsg_edit' not in page.url:
            # 从当前 URL 提取 token
            import re as _re
            token_match = _re.search(r'(?:token|from)=(\d+)', page.url)
            token = token_match.group(1) if token_match else ''
            editor_url = (
                'https://mp.weixin.qq.com/cgi-bin/appmsg'
                '?t=media/appmsg_edit_v2&action=edit&lang=zh_CN'
                '&token={}&type=10'.format(token)
            )
            print("  Navigating to editor: {}...".format(editor_url[:80]))
            try:
                page.goto(editor_url, wait_until='domcontentloaded', timeout=30000)
                page.wait_for_timeout(3000)
            except Exception as e:
                print("  Navigation error: {}".format(e))
                print("  Trying to use existing editor tab...")
                # 尝试找已打开的编辑器
                for p in context.pages:
                    if 'appmsg_edit' in p.url:
                        page = p
                        break
            print("  URL: {}".format(page.url))

        # ===== Step 1: 选择主模板 =====
        print(f"\n=== Step 1: Select Main Template ===")
        select_template(page)

        # 等待模板加载
        time.sleep(2)

        # ===== Step 2: 上传所有图片，收集 CDN URL =====
        print(f"\n=== Step 2: Upload Images & Collect CDN URLs ===")
        cdn_urls = upload_all_images(page, article_images)

        success_count = sum(1 for v in cdn_urls.values() if v)
        print(f"\n  Uploaded: {success_count}/{len(article_images)}")
        for fname, fpath in article_images:
            url = cdn_urls.get(fname)
            status = "OK" if url else "FAIL"
            print(f"    [{status}] {fname}: {(url[:70]+'...') if url else 'N/A'}")

        # ===== Step 3: 获取当前编辑器HTML → 替换占位符 → 注入 =====
        print(f"\n=== Step 3: Build & Inject Complete HTML ===")
        inject_content_by_blocks(page, elements, cdn_urls, article_images)

        # ===== Step 4: 填写标题（左侧 + 正文上方）+ 作者 =====
        print(f"\n=== Step 4: Set Titles & Author ===")
        set_titles_and_author(page, title, author)

        # ===== Step 5: 上传封面图 =====
        print(f"\n=== Step 5: Upload Cover Image ===")
        upload_cover_image(page, cover_path)

        # ===== Step 6: 最终验证 =====
        print(f"\n=== Step 6: Final Verification ===")
        result = final_verification(page, title, author)

        # 截图
        ts = time.strftime('%Y%m%d_%H%M%S')
        screenshot_path = os.path.join(os.getcwd(), f'wechat_publish_{ts}.png')
        page.screenshot(path=screenshot_path, full_page=True)
        print(f"\n  Screenshot: {screenshot_path}")

        # 保存报告
        report = {
            'title': title,
            'author': author,
            'html_path': html_path,
            'images': {fname: (url or '') for fname, url in cdn_urls.items()},
            'verification': result,
            'screenshot': screenshot_path,
            'timestamp': ts
        }
        report_path = os.path.join(os.getcwd(), f'wechat_report_{ts}.json')
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"  Report: {report_path}")

        browser.close()

    print(f"\n{'='*50}")
    print(f"DONE! Please review and publish manually.")
    print(f"{'='*50}")


# ============================================================
# 各步骤实现
# ============================================================

def select_template(page):
    """Step 1: 选择主模板"""
    result = page.evaluate("""() => {
        // 查找模板选择区域
        // 微信编辑器的模板通常在侧边栏或顶部区域
        const templateSelectors = [
            '[class*="template"]',
            '[class*="Template"]',
            '[data-type="template"]',
            // 主模板选项
            '[class*="main-template"]',
            '[class*="MainTemplate"]',
            '.template-item:first-child',
            '[class*="template-list"] > [class*="item"]:first-child'
        ];

        let found = [];
        templateSelectors.forEach(sel => {
            try {
                const els = document.querySelectorAll(sel);
                els.forEach(el => {
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

    print(f"  Template elements found: {len(result)}")
    for r in result[:10]:
        vis = "VISIBLE" if r['visible'] else "hidden"
        print(f"    [{vis}] {r['selector']} | {r['text']} | class={r['className']}")

    # 尝试点击主模板（通常是第一个可见的模板项）
    clicked = page.evaluate("""() => {
        // 常见的主模板选择方式
        const candidates = [
            // 模板列表中的第一个
            () => {
                const items = document.querySelectorAll('[class*="template-item"], [class*="TemplateItem"]');
                for (const item of items) {
                    if (item.offsetParent !== null) { item.click(); return 'template-item'; }
                }
                return null;
            },
            // "主模板" 文字按钮
            () => {
                const all = document.querySelectorAll('*');
                for (const el of all) {
                    if (el.children.length === 0 && el.textContent?.trim() === '主模板' && el.offsetParent !== null) {
                        el.click(); return 'text-main-template';
                    }
                }
                return null;
            },
            // 默认/基础模板
            () => {
                const all = document.querySelectorAll('*');
                for (const el of all) {
                    const t = el.textContent?.trim();
                    if ((t === '默认' || t === '基础' || t === '空白') && el.children.length <= 2 && el.offsetParent !== null) {
                        el.click(); return 'text-default';
                    }
                }
                return null;
            }
        ];

        for (const fn of candidates) {
            const result = fn();
            if (result) return result;
        }
        return 'none-found';
    }""")

    print(f"  Template selection: {clicked}")
    if clicked != 'none-found':
        print(f"  Template selected successfully.")
    else:
        print(f"  WARNING: Could not auto-select template. Please select manually.")


def upload_all_images(page, article_images):
    """Step 2: 逐张上传图片，收集 CDN URL"""
    cdn_urls = {}

    for idx, (img_name, img_path) in enumerate(article_images):
        if not os.path.exists(img_path):
            print(f"    [{idx+1}/{len(article_images)}] SKIP {img_name} - file not found")
            continue

        size_kb = os.path.getsize(img_path) // 1024
        print(f"    [{idx+1}/{len(article_images)}] Uploading {img_name} ({size_kb}KB)...")

        # 记录上传前的 mmbiz 图片数量
        before_count = page.evaluate("""() => {
            const editorEl = document.querySelectorAll('.ProseMirror')[1];
            if (!editorEl) return 0;
            const imgs = editorEl.querySelectorAll('img');
            let cnt = 0;
            imgs.forEach(img => {
                if (img.src.includes('mmbiz.qpic.cn') && img.naturalWidth > 100) cnt++;
            });
            return cnt;
        }""")

        # 通过 file input 直接设置文件
        uploaded = False
        file_inputs = page.query_selector_all('input[type="file"]')
        for fi in file_inputs:
            try:
                fi.set_input_files(img_path)
                uploaded = True
                break
            except Exception:
                continue

        if not uploaded:
            print(f"      ERROR: No file input available")
            continue

        # 等待上传完成
        time.sleep(UPLOAD_WAIT)

        # 检测新增的 mmbiz 图片
        after_info = page.evaluate("""(beforeCnt) => {
            const editorEl = document.querySelectorAll('.ProseMirror')[1];
            if (!editorEl) return {total: 0, newOnes: []};
            const imgs = editorEl.querySelectorAll('img');
            const mmbizImgs = [];
            imgs.forEach(img => {
                if (img.src.includes('mmbiz.qpic.cn') && img.naturalWidth > 100) {
                    mmbizImgs.push({src: img.src, w: img.naturalWidth, h: img.naturalHeight});
                }
            });
            return {total: mmbizImgs.length, newOnes: mmbizImgs.slice(beforeCnt)};
        }""", before_count)

        if after_info['newOnes']:
            latest_url = after_info['newOnes'][-1]['src']
            cdn_urls[img_name] = latest_url
            print(f"      OK! {after_info['newOnes'][-1]['w']}x{after_info['newOnes'][-1]['h']} {latest_url[:70]}...")
        else:
            # retry
            time.sleep(RETRY_WAIT)
            retry_info = page.evaluate("""(beforeCnt) => {
                const editorEl = document.querySelectorAll('.ProseMirror')[1];
                if (!editorEl) return {newOnes: []};
                const imgs = editorEl.querySelectorAll('img');
                const mmbizImgs = [];
                imgs.forEach(img => {
                    if (img.src.includes('mmbiz.qpic.cn') && img.naturalWidth > 100) {
                        mmbizImgs.push({src: img.src});
                    }
                });
                return {newOnes: mmbizImgs.slice(beforeCnt)};
            }""", before_count)

            if retry_info['newOnes']:
                cdn_urls[img_name] = retry_info['newOnes'][-1]['src']
                print(f"      OK (retry)! {retry_info['newOnes'][-1]['src'][:70]}...")
            else:
                print(f"      WARNING: Upload may have failed")

        time.sleep(0.5)

    return cdn_urls


def inject_content_by_blocks(page, elements, cdn_urls, article_images):
    """Step 3: 基于解析后的 elements 列表，构建 ProseMirror 兼容的简化 HTML 并注入。

    核心思路：不注入原始 body_html（含 div.container / 注释 / class 等复杂结构，
    ProseMirror 会丢弃无法识别的内容），而是从 elements 有序列表中逐块构建
    简洁的 HTML（只有 p/h2/h3/img/section 标签），确保 ProseMirror 能正确解析。
    """

    # 构建 src → CDN URL 的映射
    src_to_cdn = {}
    for img_name, img_path in article_images:
        url = cdn_urls.get(img_name)
        if url:
            src_to_cdn[img_name] = url
            basename = os.path.splitext(img_name)[0]
            src_to_cdn[basename] = url
            src_to_cdn[os.path.basename(img_path)] = url

    # 从 elements 构建简化 HTML
    html_parts = []
    for elem in elements:
        etype = elem[0]

        if etype == 'title':
            level = elem[1]
            text = elem[2]
            tag = 'h{}'.format(level)
            html_parts.append('<{}><strong>{}</strong></{}>'.format(tag, text, tag))

        elif etype == 'text':
            text = elem[1]
            # 将文本中的换行转为分段
            paragraphs = text.split('\n')
            for para in paragraphs:
                para = para.strip()
                if para:
                    html_parts.append('<p>{}</p>'.format(para))

        elif etype == 'image':
            img_path_e = elem[1]
            alt = elem[2] if len(elem) > 2 else ''
            img_fname = os.path.basename(img_path_e)

            # 查找 CDN URL
            cdn_url = None
            for key in [img_fname, img_path_e]:
                if key in src_to_cdn:
                    cdn_url = src_to_cdn[key]
                    break
            if not cdn_url:
                basename_no_ext = os.path.splitext(img_fname)[0]
                for k, v in src_to_cdn.items():
                    if k.endswith(basename_no_ext) or basename_no_ext in k:
                        cdn_url = v
                        break

            if cdn_url:
                html_parts.append(
                    '<section style="text-align:center">'
                    '<img src="{}" style="width:100%;height:auto;display:block;" '
                    'contenteditable="false" />'
                    '</section>'.format(cdn_url)
                )
                print('  Image block: {} -> CDN OK'.format(img_fname))
            else:
                html_parts.append(
                    '<section style="text-align:center">'
                    '<p>[图片缺失: {}]</p>'
                    '</section>'.format(alt or img_fname)
                )
                print('  Image block: {} -> NO CDN URL'.format(img_fname))

    new_html = '\n'.join(html_parts)
    print('  Built simplified HTML: {} blocks, {} chars'.format(len(html_parts), len(new_html)))

    # execCommand 三步注入
    inject_result = page.evaluate("""(newHTML) => {
        const editorEl = document.querySelectorAll('.ProseMirror')[1];
        if (!editorEl) return {error: 'no editor found'};

        editorEl.focus();
        document.execCommand('selectAll', false, null);
        document.execCommand('delete', false, null);
        const success = document.execCommand('insertHTML', false, newHTML);

        return {
            success: success,
            newTextLen: editorEl.textContent.length,
            newImgCount: editorEl.querySelectorAll('img').length,
            newPCount: editorEl.querySelectorAll('p').length
        };
    }""", new_html)

    print('  Inject: success={}, text={} chars, images={}, paragraphs={}'.format(
        inject_result.get('success'),
        inject_result.get('newTextLen'),
        inject_result.get('newImgCount'),
        inject_result.get('newPCount')
    ))

    time.sleep(2)




def set_titles_and_author(page, title, author):
    """Step 4: 填写左侧标题(#title) + 正文上方标题(.ProseMirror[0]) + 作者(#author)"""

    # 4a + 4c: 直接赋值 value（用 dict 传两个参数）
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

    # 4b: 正文上方标题用 execCommand
    page.evaluate("""(t) => {
        const titleEditor = document.querySelectorAll('.ProseMirror')[0];
        if (titleEditor) {
            titleEditor.focus();
            document.execCommand('selectAll', false, null);
            document.execCommand('delete', false, null);
            document.execCommand('insertHTML', false, '<p><strong>' + t + '</strong></p>');
        }
    }""", title)

    print("  Left title (#title): {}  Author (#author): {}".format(title, author))
    time.sleep(1)


def upload_cover_image(page, cover_path):
    """Step 5: 上传封面图"""

    if not cover_path or not os.path.exists(cover_path):
        print("  Cover: skip (file not found)")
        return

    # 微信公众号封面上传：通过 file input
    file_inputs = page.query_selector_all('input[type="file"]')
    cover_input = None
    for inp in file_inputs:
        accept = inp.get_attribute('accept') or ''
        if 'image' in accept:
            cover_input = inp
            break

    if not cover_input:
        # fallback: 取第一个 file input
        cover_input = file_inputs[0] if file_inputs else None

    if cover_input:
        cover_input.set_input_files(cover_path)
        print(f"  Cover: uploaded {os.path.basename(cover_path)}")
        time.sleep(3)
    else:
        print("  WARNING: No file input found for cover")


def final_verification(page, expected_title, expected_author):
    """Step 6: 最终验证"""
    result = page.evaluate("""() => {
        const titleEditor = document.querySelectorAll('.ProseMirror')[0];
        const bodyEditor = document.querySelectorAll('.ProseMirror')[1];

        const imgs = bodyEditor ? bodyEditor.querySelectorAll('img') : [];
        let okCount = 0;
        let badCount = 0;
        const details = Array.from(imgs).map((img, i) => {
            const isReal = img.src.includes('mmbiz.qpic.cn') && img.naturalWidth > 100;
            const isPh = img.src.includes('illustration_');
            if (isReal) okCount++;
            else if (img.naturalWidth > 0) badCount++;
            return {
                idx: i,
                src: img.src.substring(0, 100),
                naturalWidth: img.naturalWidth,
                naturalHeight: img.naturalHeight,
                status: isReal ? 'OK' : (isPh ? 'PH' : 'BAD')
            };
        });

        return {
            leftTitle: document.querySelector('#title')?.value || '',
            bodyTitle: titleEditor ? titleEditor.textContent.trim() : '',
            author: document.querySelector('#author')?.value || '',
            textLength: bodyEditor ? bodyEditor.textContent.length : 0,
            totalImages: imgs.length,
            okImages: okCount,
            badImages: badCount,
            details: details
        };
    }""")

    print(f"  Left title:   {result['leftTitle']}")
    print(f"  Body title:   {result['bodyTitle']}")
    print(f"  Author:       {result['author']}")
    print(f"  Text length:  {result['textLength']} chars")
    print(f"  Images:       {result['okImages']}/{result['totalImages']} valid")

    for d in result['details']:
        mark = "OK" if d['status'] == 'OK' else ("PH" if d['status'] == 'PH' else "BAD")
        print(f"    [{d['idx']}] [{mark}] {d['naturalWidth']}x{d['naturalHeight']} {d['src'][:70]}")

    return result


# ============================================================
# 入口
# ============================================================
def main():
    parser = argparse.ArgumentParser(description='WeChat Article Publisher')
    parser.add_argument('html_file', help='Path to the HTML file to publish')
    parser.add_argument('--author', default=DEFAULT_AUTHOR, help=f'Author name (default: {DEFAULT_AUTHOR})')
    parser.add_argument('--cover', default=None, help='Path to cover image (default: auto-detect)')
    args = parser.parse_args()

    if not os.path.exists(args.html_file):
        print(f"ERROR: File not found: {args.html_file}")
        sys.exit(1)

    wechat_publish(args.html_file, author=args.author, cover_path=args.cover)


if __name__ == '__main__':
    main()
