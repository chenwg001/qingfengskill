# -*- coding: utf-8 -*-
"""
头条排版：markdown 文章 → 头条富文本 HTML（导语+小标题+段落，信息流友好）

用法:
  python to_toutiao_html.py articles/toutiao.md -o formatted/toutiao.html [--ai-notice]

规则:
  - h1 标题；首段作导语（加粗或加大）；h2 小节
  - 图片保留相对路径（发布器处理上传）
"""
import argparse
import os
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')

P_STYLE = 'font-size:16px; line-height:1.8; color:#2b2b2b; margin:0 0 18px;'
H1_STYLE = 'font-size:24px; color:#111; margin:8px 0 20px; line-height:1.4; font-weight:bold;'
H2_STYLE = 'font-size:19px; color:#222; margin:26px 0 12px; font-weight:bold; border-left:4px solid #ff4747; padding-left:10px;'
INTRO_STYLE = 'font-size:16px; line-height:1.9; color:#555; margin:0 0 20px; border-left:3px solid #ddd; padding-left:12px;'
IMG_STYLE = 'width:100%; border-radius:6px; margin:12px 0;'


def main():
    ap = argparse.ArgumentParser(description='头条排版')
    ap.add_argument('input')
    ap.add_argument('-o', '--output', required=True)
    ap.add_argument('--ai-notice', action='store_true')
    args = ap.parse_args()

    with open(args.input, 'r', encoding='utf-8') as f:
        lines = f.read().splitlines()
    base = os.path.dirname(os.path.abspath(args.input))

    html = []
    title = ''
    paras = []
    for ln in lines:
        s = ln.rstrip()
        if not s.strip():
            continue
        m = re.match(r'^#\s+(.+)$', s.strip())
        if m:
            title = m.group(1).strip()
            continue
        paras.append(s.strip())

    if title:
        html.append(f'<h1 style="{H1_STYLE}">{title}</h1>')

    first = True
    for p in paras:
        m = re.match(r'^##\s+(.+)$', p)
        if m:
            html.append(f'<h2 style="{H2_STYLE}">{m.group(1).strip()}</h2>')
            first = False
            continue
        m = re.match(r'!\[([^\]]*)\]\(([^)]+)\)', p)
        if m:
            src = m.group(2)
            abs_src = src if os.path.isabs(src) else os.path.join(base, src)
            html.append(f'<img src="{src}" style="{IMG_STYLE}" alt="{m.group(1)}"/>')
            first = False
            continue
        txt = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', p)
        txt = re.sub(r'\*([^*]+)\*', r'<em>\1</em>', txt)
        if first:
            html.append(f'<p style="{INTRO_STYLE}">{txt}</p>')
            first = False
        else:
            html.append(f'<p style="{P_STYLE}">{txt}</p>')

    if args.ai_notice:
        html.append('<p style="color:#999; font-size:13px;">本文由 AI 辅助生成，经人工审核发布</p>')

    out = '\n'.join(html)
    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    with open(args.output, 'w', encoding='utf-8') as f:
        f.write(out)
    print(f'[OK] 头条排版完成: {args.output}')


if __name__ == '__main__':
    main()
