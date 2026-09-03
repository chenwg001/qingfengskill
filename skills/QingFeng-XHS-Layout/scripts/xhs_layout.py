# -*- coding: utf-8 -*-
"""
QingFeng-XHS-Layout 小红书笔记排版生成器

把 markdown 文章转成小红书编辑器可直接粘贴的带 emoji 排版纯文本。
参照 Reditor红薯编辑器 / 自动薯的排版规范：
- 每段 2-4 行（约 40-70 字），段间空一行
- emoji 作为视觉锚点，全文不超过 5 种，每 2-3 段 1 个，自动轮换
- 小标题用符号前缀代替数字编号
- 末尾自动加话题标签（原文已有则合并去重）

用法:
  python xhs_layout.py --input article.md --output xhs.txt
  python xhs_layout.py --input article.md --output xhs.txt --tags "教育,做中学,新教材"
  python xhs_layout.py --input article.md --output xhs.txt --style story
  风格: story(故事共鸣) / ganhuo(干货要点) / life(生活随笔)
"""
import argparse
import os
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')

# ========== 风格配置 ==========

STYLES = {
    'story': {
        'name': '故事共鸣',
        'title_emoji': '✨',
        'section_emojis': ['🌱', '💭', '💡'],
        'point_emoji': '▪️',
        'highlight_emoji': '✨',
        'ending_emoji': '🌿',
        'para_max_chars': 60,
    },
    'ganhuo': {
        'name': '干货要点',
        'title_emoji': '📚',
        'section_emojis': ['🎯', '💡', '📌'],
        'point_emoji': '✅',
        'highlight_emoji': '⚠️',
        'ending_emoji': '💪',
        'para_max_chars': 50,
    },
    'life': {
        'name': '生活随笔',
        'title_emoji': '☀️',
        'section_emojis': ['🌿', '☕', '📖'],
        'point_emoji': '▪️',
        'highlight_emoji': '💛',
        'ending_emoji': '🌸',
        'para_max_chars': 55,
    },
}

DEFAULT_TAGS = ['教育', '做中学', '新教材', '开学季', '家长必读']

ALL_EMOJI = '📚✨☀️🌱💡🎯📌⚠️✅👍▪️➖🌿☕📖💛🌸💪💭'


def extract_title(md_text):
    for line in md_text.split('\n'):
        line = line.strip()
        if line.startswith('# ') and not line.startswith('## '):
            return line[2:].strip()
    return ''


def is_tag_line(text):
    """判断是否是话题标签行（如 '#教育 #做中学'，不是 '# 标题' 或 '## 小标题'）。"""
    stripped = text.strip()
    if not stripped.startswith('#'):
        return False
    # # 标题 / ## 小标题 等 markdown 标题行（# 后紧跟空格）排除
    if re.match(r'^#+\s', stripped):
        return False
    return bool(re.search(r'#\S+', stripped))


def extract_tags(text):
    """从文本中提取 #话题 标签。"""
    return re.findall(r'#(\S+)', text)


def strip_leading_emoji(text):
    """去掉段首的 emoji（避免重复添加）。"""
    return re.sub(r'^[' + ALL_EMOJI + r']+\s*', '', text).strip()


def split_paragraph(text, max_chars):
    text = text.strip()
    if len(text) <= max_chars:
        return [text]
    sentences = re.split(r'(?<=[。！？!?])', text)
    result = []
    current = ''
    for sent in sentences:
        sent = sent.strip()
        if not sent:
            continue
        if len(current) + len(sent) <= max_chars:
            current += sent
        else:
            if current:
                result.append(current)
            current = sent
    if current:
        result.append(current)
    return result


def process_inline(text):
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'`(.+?)`', r'\1', text)
    return text


def generate_note(md_text, style_name='story', tags=None, title_override=''):
    s = STYLES.get(style_name, STYLES['story'])
    lines = md_text.split('\n')
    output = []
    collected_tags = []

    # 标题
    title = title_override or extract_title(md_text)
    if title:
        title = process_inline(title)
        title = strip_leading_emoji(title)
        title = re.sub(r'[' + ALL_EMOJI + r']+$', '', title).strip()
        output.append(f'{s["title_emoji"]} {title}')
        output.append('')

    section_idx = 0
    para_emoji_idx = 0
    para_since_emoji = 0  # 距离上一个段首 emoji 的段数
    skip_title_line = True

    for line in lines:
        raw = line.rstrip()
        stripped = raw.strip()

        if not stripped:
            continue

        # 跳过已提取的一级标题
        if skip_title_line and stripped.startswith('# ') and not stripped.startswith('## '):
            skip_title_line = False
            continue
        skip_title_line = False

        # 话题标签行 → 收集，不输出
        if is_tag_line(stripped):
            collected_tags.extend(extract_tags(stripped))
            continue

        # 二级标题
        if stripped.startswith('## '):
            text = process_inline(stripped[3:].strip())
            emoji = s['section_emojis'][section_idx % len(s['section_emojis'])]
            section_idx += 1
            output.append(f'{emoji} {text}')
            output.append('')
            para_since_emoji = 0
            continue

        # 三级标题
        if stripped.startswith('### '):
            text = process_inline(stripped[4:].strip())
            output.append(f'{s["point_emoji"]} {text}')
            output.append('')
            continue

        # 引用
        if stripped.startswith('> '):
            text = process_inline(stripped[2:].strip())
            output.append(f'{s["highlight_emoji"]} {text}')
            output.append('')
            continue

        # 图片标记 → 跳过
        if re.match(r'^!\[', stripped) or re.match(r'^\[\[ILLU\d+\]\]$', stripped):
            continue

        # 分割线
        if re.match(r'^-{3,}$|^\*{3,}$', stripped):
            output.append('——')
            output.append('')
            continue

        # 列表项
        m = re.match(r'^(\d+)\.\s+(.+)', stripped)
        if m:
            text = process_inline(m.group(2).strip())
            output.append(f'{s["point_emoji"]} {text}')
            output.append('')
            continue
        if stripped.startswith('- ') or stripped.startswith('* '):
            text = process_inline(stripped[2:].strip())
            output.append(f'{s["point_emoji"]} {text}')
            output.append('')
            continue

        # 普通段落 → 自动分段
        text = process_inline(stripped)
        paras = split_paragraph(text, s['para_max_chars'])
        for p in paras:
            p = strip_leading_emoji(p)
            # 每 2-3 段在段首加一个 emoji（轮换）
            if para_since_emoji >= 2:
                emoji = s['section_emojis'][para_emoji_idx % len(s['section_emojis'])]
                para_emoji_idx += 1
                output.append(f'{emoji} {p}')
                para_since_emoji = 0
            else:
                output.append(p)
                para_since_emoji += 1
            output.append('')

    # 末尾：分割线 + 话题标签（合并原文标签与参数标签，去重）
    output.append('——')
    output.append('')
    if tags:
        param_tags = [t.strip() for t in tags.split(',') if t.strip()]
    else:
        param_tags = DEFAULT_TAGS
    # 合并去重，保持顺序
    all_tags = []
    seen = set()
    for t in collected_tags + param_tags:
        if t not in seen:
            seen.add(t)
            all_tags.append(t)
    tag_str = ' '.join(f'#{t}' for t in all_tags[:8])  # 最多8个标签
    output.append(tag_str)

    return '\n'.join(output)


def main():
    ap = argparse.ArgumentParser(description='QingFeng-XHS-Layout 小红书笔记排版生成器')
    ap.add_argument('--input', '-i', required=True, help='输入 markdown 文件')
    ap.add_argument('--output', '-o', required=True, help='输出 txt 文件')
    ap.add_argument('--style', default='story', choices=list(STYLES.keys()),
                    help='排版风格: story(故事共鸣)/ganhuo(干货要点)/life(生活随笔)')
    ap.add_argument('--tags', default='', help='话题标签，逗号分隔，如 "教育,做中学,新教材"')
    ap.add_argument('--title', default='', help='覆盖标题（默认从 markdown 提取）')
    args = ap.parse_args()

    with open(args.input, 'r', encoding='utf-8') as f:
        md_text = f.read()

    note = generate_note(md_text, args.style, args.tags, args.title)

    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    with open(args.output, 'w', encoding='utf-8') as f:
        f.write(note)

    emoji_count = len(re.findall(r'[' + ALL_EMOJI + r']', note))
    para_count = len([l for l in note.split('\n') if l.strip() and not l.startswith('#') and l != '——'])
    tag_count = len(re.findall(r'#\S+', note))

    print(f'[OK] 小红书排版已生成: {args.output}')
    print(f'     风格: {STYLES[args.style]["name"]}')
    print(f'     段落数: {para_count}, emoji 数: {emoji_count}, 话题标签: {tag_count}')
    print(f'     用法: 打开 txt 全选复制，粘贴到小红书笔记编辑器，图片单独上传')


if __name__ == '__main__':
    main()
