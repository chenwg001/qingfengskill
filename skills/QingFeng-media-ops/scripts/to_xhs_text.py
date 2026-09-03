# -*- coding: utf-8 -*-
"""
小红书排版：markdown 文章 → 小红书纯文本格式（短段落+emoji+话题标签）

用法:
  python to_xhs_text.py articles/xhs.md -o formatted/xhs.txt [--title-max 20] [--body-max 1000] [--tags "#教育 #成长"]
  （不传 --tags 时自动从正文 #话题 或默认集取）

规则:
  - 标题 ≤20 字；正文 ≤1000 字
  - 短段落，每段之间空行；关键小节前加 emoji
  - 文末 5-6 个话题标签
"""
import argparse
import os
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')

DEFAULT_TAGS = ['#教育', '#成长', '#干货分享', '#生活感悟', '#轻风教育']

SECTION_EMOJI = {
    '摘要': '📌', '前言': '📌', '导语': '📌', '结论': '💡', '结语': '💡',
    '思考': '🤔', '建议': '✍️', '方法': '🛠️', '故事': '📖',
}


def clean_md_marks(s):
    s = re.sub(r'^#{1,6}\s*', '', s.strip())          # 去掉标题 #
    s = re.sub(r'[*_`]', '', s)                        # 去掉粗斜体/代码
    s = re.sub(r'!\[[^\]]*\]\([^)]*\)', '', s)         # 去掉图片
    s = re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', s)     # 链接保留文字
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def extract_title(lines):
    for ln in lines:
        m = re.match(r'^#\s+(.+)$', ln.strip())
        if m:
            return clean_md_marks(m.group(1))
    for ln in lines:
        t = clean_md_marks(ln)
        if t:
            return t
    return ''


def split_paragraphs(lines):
    paras = []
    buf = []
    for ln in lines:
        s = ln.rstrip()
        if not s.strip():
            if buf:
                paras.append(' '.join(buf))
                buf = []
            continue
        buf.append(s)
    if buf:
        paras.append(' '.join(buf))
    return paras


def parse_tags(text):
    tags = re.findall(r'#([\u4e00-\u9fa5A-Za-z0-9]+)', text)
    return ['#' + t for t in tags if t not in ('教育',)][:6]


def main():
    ap = argparse.ArgumentParser(description='小红书排版')
    ap.add_argument('input')
    ap.add_argument('-o', '--output', required=True)
    ap.add_argument('--title-max', type=int, default=20)
    ap.add_argument('--body-max', type=int, default=1000)
    ap.add_argument('--tags', default='')
    args = ap.parse_args()

    with open(args.input, 'r', encoding='utf-8') as f:
        raw = f.read()
    lines = raw.splitlines()

    full_title = extract_title(lines)
    title = full_title[:args.title_max] if len(full_title) > args.title_max else full_title
    paras = split_paragraphs(lines)
    # 去掉与标题重复的首段（用未截断的标题比对）
    if paras and clean_md_marks(paras[0]) == full_title:
        paras = paras[1:]

    body_lines = []
    for p in paras:
        # 小标题识别必须在清洗前判断（清洗会去掉 # 号）
        hm = re.match(r'^#{1,6}\s*(.+)$', p)
        if hm:
            label = hm.group(1).strip()
            emoji = ''
            for k, e in SECTION_EMOJI.items():
                if k in label:
                    emoji = e
                    break
            body_lines.append(f'{emoji}{label}')
            body_lines.append('')
            continue
        p = clean_md_marks(p)
        if not p:
            continue
        body_lines.append(p)
        body_lines.append('')

    # 控制字数
    body_text = '\n'.join(body_lines)
    if len(body_text) > args.body_max:
        body_text = body_text[:args.body_max]
        body_text = body_text.rsplit('\n', 1)[0] + '\n…（续见全文）'

    if args.tags:
        tags = ['#' + t.strip('#') for t in args.tags.replace('，', ' ').split() if t.strip('#')]
    else:
        tags = parse_tags(raw) or DEFAULT_TAGS

    out = []
    out.append(title)
    out.append('')
    out.append(body_text.rstrip())
    out.append('')
    out.append(' '.join(tags))
    out.append('')

    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    with open(args.output, 'w', encoding='utf-8') as f:
        f.write('\n'.join(out))
    print(f'[OK] 小红书排版完成: {args.output}')
    print(f'[INFO] 标题 {len(title)}/{args.title_max} 字，正文约 {len(body_text)}/{args.body_max} 字，标签 {len(tags)} 个')


if __name__ == '__main__':
    main()
