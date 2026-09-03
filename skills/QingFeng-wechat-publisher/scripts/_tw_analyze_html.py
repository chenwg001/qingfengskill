# -*- coding: utf-8 -*-
"""分析原 HTML 文件结构，输出 elements 列表的顺序"""
import sys, re, os
sys.stdout.reconfigure(encoding='utf-8')

HTML_PATH = r'D:\办公\宿松县教育局\PPT\遇见AI\AIyj\1\index.html'

with open(HTML_PATH, 'r', encoding='utf-8') as f:
    html = f.read()

base_dir = os.path.dirname(os.path.abspath(HTML_PATH))
html_clean = html.replace('&nbsp;', ' ')

# 提取标题
title_match = re.search(r'<h1[^>]*>(.*?)</h1>', html_clean, re.DOTALL)
title = re.sub(r'<[^>]+>', '', title_match.group(1)).strip() if title_match else ''
print(f'标题: {title}\n')

# 提取 body
body_match = re.search(r'<body[^>]*>(.*?)</body>', html, re.DOTALL | re.IGNORECASE)
body_html = body_match.group(1) if body_match else html

# 构建 elements 列表（按原文位置）
elements = []

# h2/h3 标题
for m in re.finditer(r'<(h[23])[^>]*>(.*?)</\1>', html_clean, re.DOTALL):
    tag = m.group(1)
    text = re.sub(r'<[^>]+>', '', m.group(2)).strip()
    if text:
        elements.append(('title', int(tag[1]), text, m.start()))

# 段落 p 和 div.paragraph
for pattern in [r'<p[^>]*>(.*?)</p>', r'<div[^>]*class="[^"]*paragraph[^"]*"[^>]*>(.*?)</div>']:
    for m in re.finditer(pattern, html_clean, re.DOTALL):
        text = re.sub(r'<[^>]+>', '', m.group(1)).strip()
        if len(text) > 5 and not ('{' in text and '}' in text):
            elements.append(('text', text, m.start()))

# 图片
for m in re.finditer(r'<img[^>]+src=["\']([^"\']+)["\'][^>]*>', html):
    src = m.group(1)
    alt_m = re.search(r'alt=["\']([^"\']*)["\']', m.group(0))
    alt = alt_m.group(1) if alt_m else ''
    if not os.path.isabs(src):
        abs_src = os.path.join(base_dir, src)
    else:
        abs_src = src
    elements.append(('image', abs_src, alt, m.start()))

# 按位置排序
elements.sort(key=lambda x: x[-1])

# 输出 elements 列表
print('=' * 60)
print(f'elements 列表 (共 {len(elements)} 个，按原文位置排序):')
print('=' * 60)
for i, elem in enumerate(elements):
    etype = elem[0]
    if etype == 'title':
        print(f'{i:2d}. [H{elem[1]}] {elem[2][:60]}')
    elif etype == 'text':
        print(f'{i:2d}. [P]   {elem[1][:60]}')
    elif etype == 'image':
        fname = os.path.basename(elem[1])
        print(f'{i:2d}. [IMG] {fname}')

print('\n' + '=' * 60)
print('图片位置检查:')
for i, elem in enumerate(elements):
    if elem[0] == 'image':
        fname = os.path.basename(elem[1])
        prev = elements[i-1] if i > 0 else None
        nxt = elements[i+1] if i < len(elements)-1 else None
        prev_desc = 'None'
        if prev:
            if prev[0] == 'title':
                prev_desc = f'[H{prev[1]}] {prev[2][:40]}'
            else:
                prev_desc = f'[P] {prev[1][:40]}'
        nxt_desc = 'None'
        if nxt:
            if nxt[0] == 'title':
                nxt_desc = f'[H{nxt[1]}] {nxt[2][:40]}'
            else:
                nxt_desc = f'[P] {nxt[1][:40]}'
        print(f'{fname}:')
        print(f'  前: {prev_desc}')
        print(f'  后: {nxt_desc}')
