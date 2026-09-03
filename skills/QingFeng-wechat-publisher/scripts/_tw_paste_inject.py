# -*- coding: utf-8 -*-
"""用 paste 事件向 ProSeMirror 注入 HTML（正确创建 transaction）"""
import sys, time, re, os
sys.stdout.reconfigure(encoding='utf-8')
from playwright.sync_api import sync_playwright

HTML_PATH = r"D:\办公\宿松县教育局\PPT\遇见AI\AIyj\1\index.html"

def parse_html(html_path):
    with open(html_path, 'r', encoding='utf-8') as f:
        html = f.read()
    base_dir = os.path.dirname(os.path.abspath(html_path))
    html_clean = html.replace('&nbsp;', ' ')
    title_match = re.search(r'<h1[^>]*>(.*?)</h1>', html_clean, re.DOTALL)
    title = re.sub(r'<[^>]+>', '', title_match.group(1)).strip() if title_match else ''
    body_match = re.search(r'<body[^>]*>(.*?)</body>', html, re.DOTALL | re.IGNORECASE)
    body_html = body_match.group(1) if body_match else html
    elements = []
    for m in re.finditer(r'<(h[23])[^>]*>(.*?)</\1>', html_clean, re.DOTALL):
        tag, text = m.group(1), re.sub(r'<[^>]+>', '', m.group(2)).strip()
        if text:
            elements.append(('title', int(tag[1]), text, m.start()))
    for pattern in [r'<p[^>]*>(.*?)</p>', r'<div[^>]*class="[^"]*paragraph[^"]*"[^>]*>(.*?)</div>']:
        for m in re.finditer(pattern, html_clean, re.DOTALL):
            text = re.sub(r'<[^>]+>', '', m.group(1)).strip()
            if len(text) > 5 and not ('{' in text and '}' in text):
                elements.append(('text', text, m.start()))
    for m in re.finditer(r'<img[^>]+src=["\']([^"\']+)["\'][^>]*>', html):
        src = m.group(1)
        abs_src = os.path.join(base_dir, src) if not os.path.isabs(src) else src
        elements.append(('image', abs_src, '', m.start()))
    elements.sort(key=lambda x: x[-1])
    return title, base_dir, elements

def build_html(elements, cdn_urls, base_dir):
    src_to_cdn = {}
    for fname, fpath in cdn_urls.items():
        src_to_cdn[fname] = fpath
        src_to_cdn[os.path.basename(fpath)] = fpath
    html_parts = []
    for elem in elements:
        etype = elem[0]
        if etype == 'title':
            html_parts.append('<p><strong>{}</strong></p>'.format(elem[2]))
        elif etype == 'text':
            text = elem[1]
            html_parts.append('<p>{}</p>'.format(text))
        elif etype == 'image':
            img_fname = os.path.basename(elem[1])
            cdn_url = src_to_cdn.get(img_fname) or src_to_cdn.get(elem[1])
            if cdn_url:
                html_parts.append('<p style="text-align:center"><img src="{}" style="width:100%;height:auto;" /></p>'.format(cdn_url))
            else:
                html_parts.append('<p>[图片缺失: {}]</p>'.format(img_fname))
    return '\n'.join(html_parts)

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp('http://127.0.0.1:9222')
    page = None
    for pg in browser.contexts[0].pages:
        if 'appmsg_edit' in pg.url:
            page = pg
            break
    if not page:
        print("No editor page found")
        sys.exit(1)

    print(f"Connected to: {page.url[:80]}")

    # 1. 解析 HTML
    title, base_dir, elements = parse_html(HTML_PATH)
    print(f'Title: {title}')
    print(f'Elements: {len(elements)}')

    # 2. 收集已有 CDN URL（不需要重新上传）
    print('\n=== Collecting existing CDN URLs ===')
    cdn_urls = {}
    existing_imgs = page.evaluate("""() => {
        const el = document.querySelectorAll('.ProseMirror')[1];
        if (!el) return [];
        return Array.from(el.querySelectorAll('img')).map(img => ({src: img.src, w: img.naturalWidth, h: img.naturalHeight}));
    }""")
    print(f'  Found {len(existing_imgs)} existing images in editor')
    for img in existing_imgs:
        if 'mmbiz.qpic.cn' in img['src'] and img['w'] > 100:
            # 提取文件名（从 URL 无法获得，但我们可以存起来）
            print(f'  Valid CDN: {img["src"][:80]} ({img["w"]}x{img["h"]})')

    # 如果图片不够，需要上传（这里省略上传逻辑，假设已有）
    # 为简化，直接重新上传
    article_images = []
    seen = set()
    for elem in elements:
        if elem[0] == 'image':
            fpath = elem[1]
            fname = os.path.basename(fpath)
            if fname not in seen:
                seen.add(fname)
                article_images.append((fname, fpath))

    print(f'\n=== Uploading {len(article_images)} images ===')
    for fname, fpath in article_images:
        if not os.path.exists(fpath):
            print(f'  SKIP (not found): {fname}')
            continue
        uploaded = False
        for fi in page.query_selector_all('input[type="file"]'):
            try:
                fi.set_input_files(fpath)
                uploaded = True
                print(f'  Uploading {fname}...')
                break
            except:
                continue
        if uploaded:
            time.sleep(4)
            for attempt in range(10):
                imgs = page.evaluate("""() => Array.from(document.querySelectorAll('img')).map(img => img.src)""")
                for src in imgs:
                    if 'mmbiz.qpic.cn' in src and src not in cdn_urls.values():
                        cdn_urls[fname] = src
                        print(f'    OK: {src[:80]}...')
                        break
                if fname in cdn_urls:
                    break
                time.sleep(1)
        else:
            print(f'  FAIL: no file input for {fname}')

    print(f'\n  CDN URLs collected: {len(cdn_urls)}')

    # 3. 彻底清理编辑器（用 innerHTML）
    print('\n=== Cleaning editor ===')
    page.evaluate("""() => {
        const el = document.querySelectorAll('.ProseMirror')[1];
        if (el) el.innerHTML = '<p><br></p>';
    }""")
    time.sleep(1)
    verify = page.evaluate("""() => {
        const el = document.querySelectorAll('.ProseMirror')[1];
        return { textLen: el.textContent.length, imgCount: el.querySelectorAll('img').length, html: el.innerHTML.substring(0,100) };
    }""")
    print(f'  After clean: text={verify["textLen"]}, imgs={verify["imgCount"]}, html={verify["html"][:60]}')

    # 4. 用 paste 事件注入内容（ProSeMirror 会正确创建 transaction）
    print('\n=== Injecting via Paste ===')
    new_html = build_html(elements, cdn_urls, base_dir)
    print(f'  HTML: {len(new_html)} chars, {len(new_html.split(chr(10)))} lines')

    # 方法：创建 ClipboardEvent，设置 DataTransfer 的 text/HTML，dispatch 到编辑器
    result = page.evaluate("""(html) => {
        const el = document.querySelectorAll('.ProseMirror')[1];
        if (!el) return {error: 'no editor'};
        el.focus();
        
        // 创建 paste 事件
        const dataTransfer = new DataTransfer();
        dataTransfer.setData('text/html', html);
        dataTransfer.setData('text/plain', html.replace(/<[^>]+>/g, ' '));
        
        const pasteEvent = new ClipboardEvent('paste', {
            bubbles: true,
            cancelable: true,
            dataType: 'text/html',
            data: dataTransfer
        });
        // 有些浏览器用 clipboardData 而不是 DataTransfer
        pasteEvent.clipboardData = dataTransfer;
        
        const dispatchResult = el.dispatchEvent(pasteEvent);
        return {
            dispatchResult: dispatchResult,
            textLen: el.textContent.length,
            imgCount: el.querySelectorAll('img').length,
            preview: el.textContent.substring(0, 80)
        };
    }""", new_html)

    print(f'  Paste dispatch result: {result.get("dispatchResult")}')
    print(f'  After paste: text={result.get("textLen")} chars, imgs={result.get("imgCount")}')
    print(f'  Preview: {result.get("preview")}')

    # 5. 等待 3 秒，检查是否被回滚
    print('\n  Waiting 3s to check rollback...')
    time.sleep(3)
    stable = page.evaluate("""() => {
        const el = document.querySelectorAll('.ProseMirror')[1];
        return { textLen: el.textContent.length, imgCount: el.querySelectorAll('img').length };
    }""")
    print(f'  Stable: text={stable["textLen"]} chars, imgs={stable["imgCount"]}')

    if stable["textLen"] > 0:
        print('\n*** SUCCESS! Content persisted ***')
    else:
        print('\n*** FAILED! Content was rolled back ***')

    # 截图
    ss_path = r'C:\Users\chenw\.qclaw\skills\QingFeng-wechat-publisher\scripts\wechat_paste_inject.png'
    page.screenshot(path=ss_path)
    print(f'\n  Screenshot: {ss_path}')
