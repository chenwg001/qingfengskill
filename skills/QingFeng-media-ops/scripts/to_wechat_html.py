# -*- coding: utf-8 -*-
"""
公众号排版：markdown 文章 → 内联样式 HTML（可直接粘贴公众号编辑器）

用法:
  python to_wechat_html.py articles/wechat.md -o formatted/wechat.html [--author 轻风教育] [--ai-notice]

规则:
  - h1 标题居中大字；h2 小节金色竖条；金句引用块居中高亮
  - 图片 `<img src="相对路径">` 转 base64 内嵌或保留相对路径（默认保留，发布器会处理上传）
  - 文末引导关注 + 可选 AI 生成标注
"""
import argparse
import base64
import os
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')

SECTION_BAR = 'border-left:4px solid #c9a063; padding-left:12px; color:#333; font-size:17px; font-weight:bold; margin:28px 0 12px;'
P_STYLE = 'font-size:15px; line-height:1.9; color:#3f3f3f; margin:0 0 16px; letter-spacing:0.5px;'
QUOTE_STYLE = 'background:#faf6ee; border-radius:6px; padding:16px 20px; font-size:16px; color:#8a6d3b; text-align:center; font-weight:bold; margin:20px 0;'
IMG_STYLE = 'width:100%; border-radius:8px; margin:12px 0;'


def md_to_html(md_path, embed_images=False):
    with open(md_path, 'r', encoding='utf-8') as f:
        lines = f.read().splitlines()
    base = os.path.dirname(os.path.abspath(md_path))

    html = []
    in_quote = False

    def close_quote():
        nonlocal in_quote
        if in_quote:
            html.append('</blockquote>')
            in_quote = False

    for ln in lines:
        s = ln.rstrip()
        if not s.strip():
            close_quote()
            continue
        m = re.match(r'^#\s+(.+)$', s.strip())
        if m:
            close_quote()
            html.append(f'<h1 style="text-align:center; font-size:22px; color:#222; margin:8px 0 24px; line-height:1.5;">{m.group(1).strip()}</h1>')
            continue
        m = re.match(r'^##\s+(.+)$', s.strip())
        if m:
            close_quote()
            html.append(f'<h2 style="{SECTION_BAR}">{m.group(1).strip()}</h2>')
            continue
        m = re.match(r'^>\s?(.*)$', s.strip())
        if m:
            if not in_quote:
                html.append(f'<blockquote style="{QUOTE_STYLE}">')
                in_quote = True
            html.append(m.group(1).strip())
            continue
        m = re.match(r'!\[([^\]]*)\]\(([^)]+)\)', s.strip())
        if m:
            close_quote()
            src = m.group(2)
            abs_src = src if os.path.isabs(src) else os.path.join(base, src)
            if embed_images and os.path.exists(abs_src):
                with open(abs_src, 'rb') as im:
                    b64 = base64.b64encode(im.read()).decode()
                ext = os.path.splitext(abs_src)[1].lstrip('.').lower() or 'png'
                html.append(f'<img src="data:image/{ext};base64,{b64}" style="{IMG_STYLE}" alt="{m.group(1)}"/>')
            else:
                html.append(f'<img src="{src}" style="{IMG_STYLE}" alt="{m.group(1)}"/>')
            continue
        # 普通段落：行内加粗
        txt = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', s.strip())
        close_quote()
        html.append(f'<p style="{P_STYLE}">{txt}</p>')
    close_quote()
    return '\n'.join(html)


def main():
    ap = argparse.ArgumentParser(description='公众号排版')
    ap.add_argument('input')
    ap.add_argument('-o', '--output', required=True)
    ap.add_argument('--author', default='轻风教育')
    ap.add_argument('--ai-notice', action='store_true', help='文末追加 AI 生成标注')
    ap.add_argument('--embed-images', action='store_true', help='图片转 base64 内嵌')
    args = ap.parse_args()

    body = md_to_html(args.input, embed_images=args.embed_images)

    footer = []
    footer.append('<hr style="border:none; border-top:1px solid #eee; margin:28px 0 18px;"/>')
    footer.append(f'<p style="text-align:center; color:#999; font-size:13px;">— 本文由「{args.author}」出品，欢迎关注 · 在看 · 转发 —</p>')
    if args.ai_notice:
        footer.append('<p style="text-align:center; color:#bbb; font-size:12px;">本文由 AI 辅助生成，经人工审核发布</p>')

    html = (
        '<section style="max-width:677px; margin:0 auto; padding:20px; font-family:-apple-system,BlinkMacSystemFont,\'PingFang SC\',\'Microsoft YaHei\',sans-serif;">\n'
        + body + '\n' + '\n'.join(footer) + '\n</section>'
    )

    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    with open(args.output, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f'[OK] 公众号排版完成: {args.output}')


if __name__ == '__main__':
    main()
