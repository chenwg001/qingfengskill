# -*- coding: utf-8 -*-
"""彻底清理微信编辑器，然后重新注入内容"""
import sys, time, re, os
sys.stdout.reconfigure(encoding='utf-8')
from playwright.sync_api import sync_playwright

HTML_PATH = r"D:\办公\宿松县教育局\PPT\遇见AI\AIyj\1\index.html"
AUTHOR = "无不言"
CDP_URL = "http://127.0.0.1:9222"

def parse_html(html_path):
    with open(html_path, 'r', encoding='utf-8') as f:
        html = f.read()
    base_dir = os.path.dirname(os.path.abspath(html_path))
    html_clean = html.replace('&nbsp;', ' ')
    html_clean = re.sub(r' {2,}', ' ', html_clean)
    title_match = re.search(r'<h1[^>]*>(.*?)</h1>', html_clean, re.DOTALL)
    title = re.sub(r'<[^>]+>', '', title_match.group(1)).strip() if title_match else ''
    body_match = re.search(r'<body[^>]*>(.*?)</body>', html, re.DOTALL | re.IGNORECASE)
    body_html = body_match.group(1) if body_match else html
    elements = []
    for m in re.finditer(r'<(h[23])[^>]*>(.*?)</\1>', html_clean, re.DOTALL):
        tag = m.group(1)
        text = re.sub(r'<[^>]+>', '', m.group(2)).strip()
        if text:
            elements.append(('title', int(tag[1]), text, m.start()))
    for pattern in [r'<p[^>]*>(.*?)</p>', r'<div[^>]*class="[^"]*paragraph[^"]*"[^>]*>(.*?)</div>']:
        for m in re.finditer(pattern, html_clean, re.DOTALL):
            text = re.sub(r'<[^>]+>', '', m.group(1)).strip()
            if len(text) > 5 and not ('{' in text and '}' in text):
                elements.append(('text', text, m.start()))
    for m in re.finditer(r'<img[^>]+src=["\']([^"\']+)["\'][^>]*>', html):
        src = m.group(1)
        if not os.path.isabs(src):
            abs_src = os.path.join(base_dir, src)
        else:
            abs_src = src
        elements.append(('image', abs_src, '', m.start()))
    elements.sort(key=lambda x: x[-1])
    return title, body_html, base_dir, elements

def find_image_files(base_dir, body_html):
    images = []
    srcs = re.findall(r'src=["\']([^"\']+\.(?:jpg|jpeg|png|gif|webp))["\']', body_html, re.IGNORECASE)
    seen = set()
    for src in srcs:
        abs_path = os.path.join(base_dir, src) if not os.path.isabs(src) else src
        fname = os.path.basename(abs_path)
        if fname not in seen and os.path.exists(abs_path):
            seen.add(fname)
            images.append((fname, abs_path))
    if not images:
        for f in sorted(os.listdir(base_dir)):
            if re.match(r'^illustration_\d+\.(jpg|jpeg|png|gif|webp)$', f, re.IGNORECASE):
                abs_path = os.path.join(base_dir, f)
                if f not in seen:
                    seen.add(f)
                    images.append((f, abs_path))
    def sort_key(item):
        m = re.match(r'illustration_(\d+)', item[0], re.IGNORECASE)
        return int(m.group(1)) if m else 999
    images.sort(key=sort_key)
    return images

def upload_images(page, article_images):
    cdn_urls = {}
    for fname, fpath in article_images:
        uploaded = False
        for fi in page.query_selector_all('input[type="file"]'):
            try:
                fi.set_input_files(fpath)
                uploaded = True
                break
            except:
                continue
        if uploaded:
            time.sleep(4)
            for attempt in range(10):
                imgs = page.evaluate("""() => {
                    return Array.from(document.querySelectorAll('img')).map(img => img.src);
                }""")
                for src in imgs:
                    if 'mmbiz.qpic.cn' in src and src not in cdn_urls.values():
                        cdn_urls[fname] = src
                        print(f'    OK: {src[:80]}...')
                        break
                if fname in cdn_urls:
                    break
                time.sleep(1)
        else:
            print(f'    FAIL: no file input found for {fname}')
    return cdn_urls

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp(CDP_URL)
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
    title, body_html, base_dir, elements = parse_html(HTML_PATH)
    article_images = find_image_files(base_dir, body_html)
    print(f'Title: {title}')
    print(f'Elements: {len(elements)}, Images: {len(article_images)}')

    # 2. 彻底清理编辑器
    print('\n=== Cleaning editor (thorough) ===')
    result = page.evaluate("""() => {
        const el = document.querySelectorAll('.ProseMirror')[1];
        if (!el) return {error: 'no editor'};
        
        // 方法1: 设置 innerHTML 为单个空段落
        el.innerHTML = '<p><br></p>';
        
        // 方法2: 同时用 execCommand 清空（双重保险）
        el.focus();
        document.execCommand('selectAll', false, null);
        document.execCommand('delete', false, null);
        
        return {
            innerHTML_len: el.innerHTML.length,
            textLen: el.textContent.length,
            imgCount: el.querySelectorAll('img').length
        };
    }""")
    print(f'  After clean: html={result["innerHTML_len"]}, text={result["textLen"]}, imgs={result["imgCount"]}')
    time.sleep(2)

    # 验证清理是否成功
    verify = page.evaluate("""() => {
        const el = document.querySelectorAll('.ProseMirror')[1];
        return {
            imgCount: el.querySelectorAll('img').length,
            textLen: el.textContent.length,
            html: el.innerHTML.substring(0, 200)
        };
    }""")
    print(f'  Verify: imgs={verify["imgCount"]}, text={verify["textLen"]}, html={verify["html"][:100]}')

    if verify['imgCount'] > 0:
        print('  WARNING: Images still present after clean! Forcing innerHTML...')
        page.evaluate("""() => {
            const el = document.querySelectorAll('.ProseMirror')[1];
            el.innerHTML = '<p><br></p>';
        }""")
        time.sleep(1)

    # 3. 上传图片（如果需要）
    print('\n=== Upload Images ===')
    cdn_urls = upload_images(page, article_images)
    print(f'  Uploaded: {sum(1 for v in cdn_urls.values() if v)}/{len(article_images)}')

    # 4. 构建并注入内容
    print('\n=== Inject Content ===')
    src_to_cdn = {}
    for fname, fpath in article_images:
        url = cdn_urls.get(fname)
        if url:
            src_to_cdn[fname] = url
            src_to_cdn[os.path.basename(fpath)] = url

    html_parts = []
    for elem in elements:
        etype = elem[0]
        if etype == 'title':
            level = elem[1]
            text = elem[2]
            html_parts.append('<p><strong>{}</strong></p>'.format(text))
        elif etype == 'text':
            text = elem[1]
            if len(text) > 20 and ('{' in text and '}' in text):
                continue
            html_parts.append('<p>{}</p>'.format(text))
        elif etype == 'image':
            img_fname = os.path.basename(elem[1])
            cdn_url = src_to_cdn.get(img_fname) or src_to_cdn.get(elem[1])
            if cdn_url:
                html_parts.append('<p style="text-align:center"><img src="{}" style="width:100%;height:auto;" /></p>'.format(cdn_url))
            else:
                html_parts.append('<p>[图片缺失: {}]</p>'.format(img_fname))

    new_html = '\n'.join(html_parts)
    print(f'  Built HTML: {len(html_parts)} blocks, {len(new_html)} chars')

    # 注入
    result = page.evaluate("""(html) => {
        const el = document.querySelectorAll('.ProseMirror')[1];
        if (!el) return {error: 'no editor'};
        el.focus();
        document.execCommand('selectAll', false, null);
        document.execCommand('delete', false, null);
        const ok = document.execCommand('insertHTML', false, html);
        return {
            ok: ok,
            textLen: el.textContent.length,
            imgCount: el.querySelectorAll('img').length,
            preview: el.textContent.substring(0, 80)
        };
    }""", new_html)
    print(f'  Inject result: ok={result.get("ok")}, text={result.get("textLen")}, imgs={result.get("imgCount")}')
    print(f'  Preview: {result.get("preview")}')

    time.sleep(3)

    # 最终验证
    final = page.evaluate("""() => {
        const el = document.querySelectorAll('.ProseMirror')[1];
        const imgs = el.querySelectorAll('img');
        return {
            textLen: el.textContent.length,
            imgCount: imgs.length,
            imgs_detail: Array.from(imgs).map((img, i) => ({
                i: i,
                w: img.naturalWidth,
                h: img.naturalHeight,
                src: img.src.substring(0, 60)
            }))
        };
    }""")
    print(f'\n=== Final Verification ===')
    print(f'  Text: {final["textLen"]} chars')
    print(f'  Images: {final["imgCount"]}')
    for d in final['imgs_detail']:
        status = 'OK' if d['w'] > 100 else 'BAD'
        print(f'    [{status}] {d["i"]}: {d["w"]}x{d["h"]} | {d["src"]}...')

    # 截图
    ss_path = r'C:\Users\chenw\.qclaw\skills\QingFeng-wechat-publisher\scripts\wechat_clean_inject.png'
    page.screenshot(path=ss_path)
    print(f'\n  Screenshot: {ss_path}')
