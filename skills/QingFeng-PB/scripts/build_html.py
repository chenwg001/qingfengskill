#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
QingFeng-PB —— 文章排版 HTML 拼装脚本（确定性部分）

移植自 Coze「自动排版网页内容工作流」的 html_generation_node：
- 用正则程序化解析文章结构（标题 / 章节 / 子标题 / 段落），不依赖 LLM，保证长文不截断；
- LLM 只负责产出 CSS（通过 --css 传入），本脚本只做拼装；
- 输出双版本：
    * index.html   —— 下载版，图片用相对路径（cover.jpg / illustration_N.jpg / background.jpg），离线可用；
    * preview.html —— 预览版，图片以 base64 内嵌，单文件自包含，任意环境可直接打开预览。

用法：
    python build_html.py --article 文章.txt --css style.css \
        --cover cover.jpg --illustrations "ill1.jpg,ill2.jpg,ill3.jpg" \
        --background background.jpg --outdir ./output

图片路径说明：
    --cover / --illustrations / --background 都指向已生成的本地图片文件。
    下载版 index.html 中统一改写为 cover.jpg / illustration_1.jpg / background.jpg 等短名，
    因此调用方需保证这些短名文件存在于 --outdir（本脚本不负责复制图片，由编排层处理）。
"""

import os
import re
import sys
import json
import html as html_module
import base64
import argparse
import mimetypes


# ───────────────────────────────────────────────────────────
# 1. 文本结构解析（程序化，不依赖 LLM）
# ───────────────────────────────────────────────────────────
def parse_text_structure(user_content: str) -> dict:
    lines = user_content.strip().split('\n')

    # 过滤末尾的 AI 生成声明
    disclaimer_patterns = ['本内容由', 'AI 生成', 'AI生成', '人工智能生成', '请遵循相关法律法规']
    while lines:
        last_line = lines[-1].strip()
        if any(pat in last_line for pat in disclaimer_patterns):
            lines.pop()
        else:
            break

    # 提取标题（第一行非空文本）
    title = ""
    start_idx = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped:
            title = re.sub(r'^#+\s*', '', stripped)
            start_idx = i + 1
            break

    # 章节标题：一、二、三、… 或 第一章、第二章、… 等
    section_pattern = re.compile(r'^[一二三四五六七八九十百]+[、.．]\s*.+')
    # 纯数字章节标题（如单独的"一"、"二"、"三"）
    bare_number_section_pattern = re.compile(r'^[一二三四五六七八九十]+$')
    # 特殊章节标题（结语 / 前言 / 引言 / 等）
    special_section_pattern = re.compile(r'^(结语|前言|引言|序言|后记|附录|总结)$')
    # 无序号短标题（随笔常见）：长度适中、独立成行、不以句末标点结尾、不含冒号
    short_title_pattern = re.compile(r'^.{2,30}$')
    short_title_tail = ('。', '；', '……', '，', '、')
    # 疑问句/感叹句标题（如"为什么不用API？"）：以问号/感叹号结尾的短行也可作标题
    question_title_tail = ('？', '!', '！')


    def _is_short_title(s: str) -> bool:
        if not short_title_pattern.match(s):
            return False
        if s.endswith(short_title_tail):
            return False
        # 含冒号的短行（如"整体架构：技能串联而非单体"）也可作章节标题
        if ('：' in s or ':' in s) and len(s) <= 30:
            return True
        if s.isdigit():
            return False
        return True

    sections = []
    current_section = {"title": "", "subsections": [], "paragraphs": []}
    current_subsection = {"title": "", "paragraphs": []}
    intro_paragraphs = []
    in_intro = True

    for i in range(start_idx, len(lines)):
        line = lines[i]
        stripped = line.strip()
        if not stripped:
            continue
        # 跳过图片占位符 [[ILLU1]] 等（图片由 image_positions 控制插入位置）
        if re.match(r'^\[\[ILLU\d+\]\]$', stripped):
            continue
        # 跳过 markdown 图片标记 ![描述](路径)（图片由 image_positions 控制插入位置）
        if re.match(r'^!\[.*?\]\(.*?\)$', stripped):
            continue

        # 疑问句/感叹句标题：以问号/感叹号结尾的短行（<30字）也作章节标题
        is_question_title = (
            len(stripped) <= 30
            and stripped.endswith(question_title_tail)
        )

        if (section_pattern.match(stripped) or bare_number_section_pattern.match(stripped)
                or special_section_pattern.match(stripped) or _is_short_title(stripped)
                or is_question_title
                or stripped.startswith('## ')):
            if in_intro:
                if current_subsection["paragraphs"]:
                    intro_paragraphs.extend(current_subsection["paragraphs"])
                elif current_section["paragraphs"]:
                    intro_paragraphs.extend(current_section["paragraphs"])
                in_intro = False
            if current_section["title"]:
                if current_subsection["title"] or current_subsection["paragraphs"]:
                    current_section["subsections"].append(current_subsection)
                sections.append(current_section)
            current_section = {"title": re.sub(r'^#+\s*', '', stripped), "subsections": [], "paragraphs": []}
            current_subsection = {"title": "", "paragraphs": []}
            continue

        # 子标题：短行（<60 字）、不以句号等结尾、含冒号或匹配特型
        is_subsection = False
        if len(stripped) < 60 and not stripped.endswith(('。', '！', '？', '；', '……')):
            if ('：' in stripped or ':' in stripped) and len(stripped) < 50:
                is_subsection = True

        if is_subsection:
            if current_subsection["title"] or current_subsection["paragraphs"]:
                current_section["subsections"].append(current_subsection)
            current_subsection = {"title": re.sub(r'^#+\s*', '', stripped), "paragraphs": []}
        else:
            current_subsection["paragraphs"].append(stripped)

    if in_intro:
        if current_subsection["paragraphs"]:
            intro_paragraphs.extend(current_subsection["paragraphs"])
        elif current_section["paragraphs"]:
            intro_paragraphs.extend(current_section["paragraphs"])
    else:
        if current_section["title"] or current_subsection["paragraphs"]:
            if current_subsection["title"] or current_subsection["paragraphs"]:
                current_section["subsections"].append(current_subsection)
            sections.append(current_section)

    return {
        "title": title,
        "intro_paragraphs": intro_paragraphs,
        "sections": sections,
    }


def escape_html(text: str) -> str:
    return html_module.escape(text, quote=False)


def build_image_position_map(sections, ill_imgs, image_positions):
    """根据 image_positions 决定每张插图插入到哪个章节之后；无法解析则均匀分配。"""
    total_sections = len(sections)
    total_ills = len(ill_imgs)
    ill_per_section = {}

    if total_sections > 0 and total_ills > 0:
        if image_positions:
            for seq_num, pos_entry in enumerate(image_positions):
                if not isinstance(pos_entry, dict):
                    continue
                ill_index = seq_num
                if ill_index >= total_ills:
                    break
                position_str = str(pos_entry.get("position", ""))
                sec_match = re.search(r'(\d+)', position_str)
                if sec_match:
                    sec_num = int(sec_match.group(1)) - 1
                    sec_num = max(0, min(sec_num, total_sections - 1))
                else:
                    sec_num = seq_num % total_sections
                ill_per_section.setdefault(sec_num, [])
                if ill_index not in ill_per_section[sec_num]:
                    ill_per_section[sec_num].append(ill_index)
            assigned = set()
            for indices in ill_per_section.values():
                assigned.update(indices)
            unassigned = [i for i in range(total_ills) if i not in assigned]
            for ua_idx in unassigned:
                min_sec = min(range(total_sections), key=lambda s: len(ill_per_section.get(s, [])))
                ill_per_section.setdefault(min_sec, []).append(ua_idx)
        else:
            step = max(1, total_sections // total_ills)
            for i in range(total_ills):
                sec_idx = min(i * step, total_sections - 1)
                ill_per_section.setdefault(sec_idx, []).append(i)
    return ill_per_section


def assemble_html(title, intro_paragraphs, sections, css_content,
                  cover_img, ill_imgs, bg_img, image_positions, use_urls=True):
    """程序化拼装完整 HTML。use_urls=False 时用短名相对路径。"""
    if not use_urls:
        cover_img = "cover.jpg"
        ill_imgs = [f"illustration_{i+1}.jpg" for i in range(len(ill_imgs))]
        bg_img = "background.jpg"

    # 替换 CSS 背景图占位符 / 兜底外部 URL
    css_content = css_content.replace("BACKGROUND_IMAGE_URL", bg_img)
    css_content = re.sub(r"url\(['\"]?https?://[^'\")\s]+['\"]?\)", lambda m: f"url('{bg_img}')", css_content)

    parts = []
    parts.append('<!DOCTYPE html>')
    parts.append('<html lang="zh-CN">')
    parts.append('<head>')
    parts.append('<meta charset="UTF-8">')
    parts.append('<meta name="viewport" content="width=device-width, initial-scale=1.0">')
    parts.append(f'<title>{escape_html(title)}</title>')
    parts.append('<style>')
    parts.append(css_content)
    parts.append('</style>')
    parts.append('</head>')
    parts.append('<body>')
    parts.append('<div class="container">')

    parts.append(f'<h1 class="title">{escape_html(title)}</h1>')
    if cover_img:
        parts.append(f'<img src="{cover_img}" alt="封面图" class="cover-image">')

    # ── 展平所有段落为带序号的列表，用于图片位置计算 ──
    all_paragraphs = []  # [(para_text, is_section_title, section_idx, is_subsection_title)]
    for para in intro_paragraphs:
        all_paragraphs.append(("para", para, -1, False))
    for sec_idx, section in enumerate(sections):
        sec_title = section.get("title", "")
        if sec_title:
            all_paragraphs.append(("section_title", sec_title, sec_idx, False))
        for para in section.get("paragraphs", []):
            all_paragraphs.append(("para", para, sec_idx, False))
        for subsec in section.get("subsections", []):
            sub_title = subsec.get("title", "")
            if sub_title:
                all_paragraphs.append(("subsection_title", sub_title, sec_idx, True))
            for para in subsec.get("paragraphs", []):
                all_paragraphs.append(("para", para, sec_idx, True))

    total_paras = len(all_paragraphs)
    total_ills = len(ill_imgs)

    # ── 计算每张插图应插入在哪个段落之后 ──
    # 优先用 image_positions 中的 position 字段（after_paragraph_N / after_subtitle_N）
    # 无法解析时均匀分配：第 i 张图插在第 (i+1)*total_paras/(total_ills+1) 个段落后
    ill_insert_after = {}  # {para_index: [ill_idx, ...]}

    if total_ills > 0 and total_paras > 0:
        used_positions = set()
        if image_positions:
            for seq_num, pos_entry in enumerate(image_positions):
                if seq_num >= total_ills:
                    break
                # 支持字符串格式（如 "after_section_整体架构"、"after_paragraph_3"）
                if isinstance(pos_entry, str):
                    position_str = pos_entry
                elif isinstance(pos_entry, dict):
                    position_str = str(pos_entry.get("position", ""))
                else:
                    continue

                p_idx = None

                # 尝试解析 after_paragraph_N
                para_match = re.search(r'after_paragraph[_]?(\d+)', position_str, re.IGNORECASE)
                if para_match:
                    p_idx = int(para_match.group(1)) - 1
                    p_idx = max(0, min(p_idx, total_paras - 1))
                else:
                    # 尝试解析 after_section_XXX（中文section标题）
                    sec_match = re.search(r'after_section[_]?(.+)', position_str, re.IGNORECASE)
                    if sec_match:
                        target_sec = sec_match.group(1).strip()
                        # 在 all_paragraphs 中找到匹配的 section_title
                        for idx, (ptype, text, sidx, is_sub) in enumerate(all_paragraphs):
                            if ptype == "section_title" and target_sec in text:
                                p_idx = idx
                                break
                    # 尝试解析 before_section_XXX
                    if p_idx is None:
                        before_match = re.search(r'before_section[_]?(.+)', position_str, re.IGNORECASE)
                        if before_match:
                            target_sec = before_match.group(1).strip()
                            for idx, (ptype, text, sidx, is_sub) in enumerate(all_paragraphs):
                                if ptype == "section_title" and target_sec in text:
                                    p_idx = max(0, idx - 1)
                                    break

                # 无法解析则均匀分配
                if p_idx is None:
                    p_idx = int((seq_num + 1) * total_paras / (total_ills + 1))
                    p_idx = min(p_idx, total_paras - 1)

                # 避免两张图插在同一段落后
                while p_idx in used_positions and p_idx < total_paras - 1:
                    p_idx += 1
                used_positions.add(p_idx)
                ill_insert_after.setdefault(p_idx, []).append(seq_num)
        else:
            # 无 image_positions 时均匀分配
            for i in range(total_ills):
                p_idx = int((i + 1) * total_paras / (total_ills + 1))
                p_idx = min(p_idx, total_paras - 1)
                while p_idx in used_positions and p_idx < total_paras - 1:
                    p_idx += 1
                used_positions.add(p_idx)
                ill_insert_after.setdefault(p_idx, []).append(i)

    # ── 按顺序输出段落，在指定段落后插入图片 ──
    for p_idx, (ptype, text, sec_idx, is_sub) in enumerate(all_paragraphs):
        if ptype == "section_title":
            parts.append(f'<h2 class="subtitle">{escape_html(text)}</h2>')
        elif ptype == "subsection_title":
            parts.append(f'<h3 class="sub-subtitle">{escape_html(text)}</h3>')
        else:
            parts.append(f'<p class="paragraph">{escape_html(text)}</p>')

        # 在该段落后插入图片
        if p_idx in ill_insert_after:
            for ill_idx in ill_insert_after[p_idx]:
                if ill_idx < len(ill_imgs) and ill_imgs[ill_idx]:
                    parts.append(f'<img src="{ill_imgs[ill_idx]}" alt="插图{ill_idx+1}" class="illustration">')

    parts.append('</div>')
    parts.append('</body>')
    parts.append('</html>')
    return '\n'.join(parts)


def embed_local_images(html: str, base_dir: str) -> str:
    """把 HTML 中的本地图片引用（src / css url）替换为 base64 data URI，生成自包含预览。"""
    def _replace(m):
        ref = m.group(1).strip().strip("'\"")
        if ref.startswith(('http://', 'https://', 'data:')):
            return m.group(0)
        path = os.path.join(base_dir, ref)
        if not os.path.exists(path):
            return m.group(0)
        mime = mimetypes.guess_type(path)[0] or 'image/jpeg'
        with open(path, 'rb') as f:
            b64 = base64.b64encode(f.read()).decode('ascii')
        return f"{m.group(0).split('(')[0]}({m.group(0).split('(')[1].split(')')[0].split(':')[0]}:{mime};base64,{b64})" if '(' in m.group(0) else m.group(0)

    # 处理 src="xxx" 与 url('xxx')
    def _src_repl(m):
        ref = m.group(1).strip().strip("'\"")
        if ref.startswith(('http://', 'https://', 'data:')):
            return m.group(0)
        path = os.path.join(base_dir, ref)
        if not os.path.exists(path):
            return m.group(0)
        mime = mimetypes.guess_type(path)[0] or 'image/jpeg'
        with open(path, 'rb') as f:
            b64 = base64.b64encode(f.read()).decode('ascii')
        return f'src="data:{mime};base64,{b64}"'

    def _url_repl(m):
        inner = m.group(1).strip().strip("'\"")
        if inner.startswith(('http://', 'https://', 'data:')):
            return m.group(0)
        path = os.path.join(base_dir, inner)
        if not os.path.exists(path):
            return m.group(0)
        mime = mimetypes.guess_type(path)[0] or 'image/jpeg'
        with open(path, 'rb') as f:
            b64 = base64.b64encode(f.read()).decode('ascii')
        return f"url('data:{mime};base64,{b64}')"

    html = re.sub(r'src=["\']([^"\']+)["\']', _src_repl, html)
    html = re.sub(r'url\(["\']?([^"\')]+)["\']?\)', _url_repl, html)
    return html


def load_image_positions(path_or_json):
    if not path_or_json:
        return []
    if os.path.exists(path_or_json):
        with open(path_or_json, 'r', encoding='utf-8') as f:
            try:
                return json.load(f)
            except Exception:
                return []
    try:
        return json.loads(path_or_json)
    except Exception:
        return []


def split_images(arg, default_dir):
    """把 --illustrations 参数拆成路径列表：支持逗号分隔，或目录（自动发现 illustration_*.jpg）。"""
    if not arg:
        return []
    if os.path.isdir(arg):
        files = sorted([os.path.join(arg, f) for f in os.listdir(arg)
                        if re.match(r'illustration_\d+\.jpg$', f, re.IGNORECASE)])
        return files
    out = []
    for p in arg.split(','):
        p = p.strip()
        if not p:
            continue
        out.append(p if os.path.isabs(p) else os.path.join(default_dir, p))
    return out


def main():
    ap = argparse.ArgumentParser(description="QingFeng-PB HTML 拼装")
    ap.add_argument('--article', required=True, help='文章文件路径（txt/md）')
    ap.add_argument('--css', required=True, help='LLM 生成的 CSS 文件路径')
    ap.add_argument('--cover', default='', help='封面图路径')
    ap.add_argument('--illustrations', default='', help='插图路径，逗号分隔或目录')
    ap.add_argument('--background', default='', help='背景图路径')
    ap.add_argument('--image-positions', default='', help='插图位置 JSON（文件或字符串）')
    ap.add_argument('--title', default='', help='文章标题（缺省取首行）')
    ap.add_argument('--outdir', default='.', help='输出目录')
    args = ap.parse_args()

    with open(args.article, 'r', encoding='utf-8') as f:
        raw = f.read()

    # 去除风格标记【风格】
    content = raw
    style_match = re.search(r'【(.+?)】', content)
    if style_match:
        content = re.sub(r'【.+?】', '', content, count=1).strip()

    struct = parse_text_structure(content)
    title = args.title or struct["title"]
    intro = struct["intro_paragraphs"]
    sections = struct["sections"]

    with open(args.css, 'r', encoding='utf-8') as f:
        css = f.read()

    cover_path = args.cover
    ill_paths = split_images(args.illustrations, args.outdir)
    bg_path = args.background
    positions = load_image_positions(args.image_positions)
    # 防御性：若传入的是含 image_positions 的整份分析 JSON，自动取该字段
    if isinstance(positions, dict) and "image_positions" in positions:
        positions = positions["image_positions"]

    # 预览版：用真实本地路径组装后再内嵌 base64
    preview = assemble_html(title, intro, sections, css, cover_path, ill_paths, bg_path, positions, use_urls=True)
    preview = embed_local_images(preview, os.path.dirname(os.path.abspath(args.article)) if False else args.outdir)

    # 下载版：相对短名
    download = assemble_html(title, intro, sections, css, cover_path, ill_paths, bg_path, positions, use_urls=False)

    os.makedirs(args.outdir, exist_ok=True)
    with open(os.path.join(args.outdir, 'preview.html'), 'w', encoding='utf-8') as f:
        f.write(preview)
    with open(os.path.join(args.outdir, 'index.html'), 'w', encoding='utf-8') as f:
        f.write(download)

    print(f"OK title={title!r} sections={len(sections)} ill={len(ill_paths)}")
    print(f"  -> {os.path.join(args.outdir, 'preview.html')}")
    print(f"  -> {os.path.join(args.outdir, 'index.html')}")


if __name__ == '__main__':
    main()
