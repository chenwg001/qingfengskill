# -*- coding: utf-8 -*-
"""
QingFeng-GZH-Layout 公众号排版生成器

两种模式：
  模式1（markdown排版，单独使用）：把 markdown 文章转成公众号编辑器可直接粘贴的内联样式 HTML。
    参照 135编辑器 / 秀米的 section 嵌套 + 全内联样式方案，支持五套风格。
    用法: python gzh_layout.py --mode md --input article.md --output gzh.html --style keji

  模式2（HTML优化，全链条使用）：把 QingFeng-PB 生成的通用 HTML 优化为公众号编辑器能渲染的 HTML。
    核心：把 <style> 中的外部 CSS 转为内联 style=""，移除 class，图片路径转绝对路径。
    用法: python gzh_layout.py --mode html --input pb/index.html --output wechat.html --image-dir pb/

样式: guofeng(国风雅致) / jianyue(简约清新) / keji(科技商务) / zazhi(杂志深度) / zhiyu(治愈温暖)
图片: markdown 中 ![描述](路径) 或 [[ILLU1]] 标记，脚本自动替换为 <img>
"""
import argparse
import os
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')

# ========== 样式模板（全内联，公众号白名单安全） ==========

STYLES = {
    'guofeng': {
        'name': '国风雅致',
        'body_bg': '#faf8f5',
        'text_color': '#3d3d3d',
        'title_color': '#8b4513',
        'subtitle_bg': '#f5ebe0',
        'subtitle_border': '#c9a96e',
        'quote_bg': '#f9f5ef',
        'quote_border': '#b8860b',
        'font_size': '16px',
        'line_height': '1.85',
        'accent': '#8b4513',
    },
    'jianyue': {
        'name': '简约清新',
        'body_bg': '#ffffff',
        'text_color': '#3f3f3f',
        'title_color': '#2c3e50',
        'subtitle_bg': '#e8f4f8',
        'subtitle_border': '#5dade2',
        'quote_bg': '#f4f9f9',
        'quote_border': '#48c9b0',
        'font_size': '15px',
        'line_height': '1.75',
        'accent': '#2c3e50',
    },
    'keji': {
        'name': '科技商务',
        'body_bg': '#f8f9fa',
        'text_color': '#2d3436',
        'title_color': '#1a1a2e',
        'subtitle_bg': '#eef2ff',
        'subtitle_border': '#4f46e5',
        'quote_bg': '#f1f5f9',
        'quote_border': '#6366f1',
        'font_size': '15px',
        'line_height': '1.7',
        'accent': '#4f46e5',
    },
    'zazhi': {
        'name': '杂志深度',
        'body_bg': '#ffffff',
        'text_color': '#2b2b2b',
        'title_color': '#1a1a1a',
        'subtitle_bg': 'transparent',
        'subtitle_border': '#1a1a1a',
        'quote_bg': '#f7f7f7',
        'quote_border': '#999999',
        'font_size': '16px',
        'line_height': '1.9',
        'accent': '#1a1a1a',
        # 杂志风专属
        'subtitle_style': 'underline',
        'title_font_family': '"Noto Serif SC", "Source Han Serif SC", "SimSun", serif',
        'title_letter_spacing': '2px',
        'quote_align': 'center',
        'quote_font_size': '19px',
        'divider_symbol': '———',
        'image_radius': '12px',
        'image_shadow': True,
    },
    'zhiyu': {
        'name': '治愈温暖',
        'body_bg': '#fffbfc',
        'text_color': '#5c544e',
        'title_color': '#ff7a9a',
        'subtitle_bg': '#fff5f7',
        'subtitle_border': '#ffb3c6',
        'quote_bg': '#fff5f7',
        'quote_border': '#ff7a9a',
        'font_size': '15px',
        'line_height': '2.0',
        'accent': '#ff7a9a',
        # 治愈风专属
        'quote_border_style': 'dashed',
        'divider_symbol': '✿',
        'image_radius': '12px',
    },
}

FONT_STACK = '-apple-system, BlinkMacSystemFont, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif'


def esc(s):
    return s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def inline_text(text):
    """处理行内格式：加粗 **text**、斜体、行内代码。"""
    text = esc(text)
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong style="font-weight:700;">\1</strong>', text)
    text = re.sub(r'`(.+?)`', r'<code style="background:#f0f0f0;padding:1px 5px;border-radius:3px;font-size:0.9em;">\1</code>', text)
    return text


def render_title(text, s):
    font_family = s.get('title_font_family', FONT_STACK)
    letter_spacing = s.get('title_letter_spacing', '1px')
    return (
        f'<section style="margin:20px 0 16px;text-align:center;">'
        f'<span style="font-size:22px;font-weight:700;color:{s["title_color"]};'
        f'letter-spacing:{letter_spacing};line-height:1.5;font-family:{font_family};">'
        f'{inline_text(text)}</span></section>'
    )


def render_subtitle(text, s, level=2):
    if level == 2:
        if s.get('subtitle_style') == 'underline':
            # 杂志风：下划线短横线样式
            return (
                f'<section style="margin:28px 0 14px;">'
                f'<span style="font-size:18px;font-weight:700;color:{s["title_color"]};'
                f'line-height:1.6;letter-spacing:1px;border-bottom:2px solid {s["subtitle_border"]};'
                f'padding-bottom:4px;display:inline-block;">'
                f'{inline_text(text)}</span></section>'
            )
        return (
            f'<section style="margin:24px 0 12px;padding:8px 14px;'
            f'background:{s["subtitle_bg"]};border-left:4px solid {s["subtitle_border"]};'
            f'border-radius:0 4px 4px 0;">'
            f'<span style="font-size:17px;font-weight:700;color:{s["title_color"]};line-height:1.6;">'
            f'{inline_text(text)}</span></section>'
        )
    else:
        return (
            f'<section style="margin:18px 0 10px;">'
            f'<span style="font-size:16px;font-weight:700;color:{s["accent"]};line-height:1.6;">'
            f'{inline_text(text)}</span></section>'
        )


def render_paragraph(text, s):
    return (
        f'<section style="margin:0 0 14px;">'
        f'<span style="font-size:{s["font_size"]};color:{s["text_color"]};'
        f'line-height:{s["line_height"]};letter-spacing:0.5px;text-align:justify;">'
        f'{inline_text(text)}</span></section>'
    )


def render_image(src, alt='', s=None):
    if s is None:
        s = STYLES['guofeng']
    radius = s.get('image_radius', '6px')
    shadow = 'box-shadow:0 2px 12px rgba(0,0,0,0.1);' if s.get('image_shadow') else ''
    src_esc = esc(src)
    alt_esc = esc(alt)
    return (
        f'<section style="margin:16px 0;text-align:center;">'
        f'<img src="{src_esc}" alt="{alt_esc}" '
        f'style="max-width:100%;height:auto;border-radius:{radius};display:block;margin:0 auto;{shadow}" />'
        f'</section>'
    )


def render_quote(text, s):
    border_style = s.get('quote_border_style', 'solid')
    align = s.get('quote_align', 'left')
    q_font_size = s.get('quote_font_size', s['font_size'])
    return (
        f'<section style="margin:16px 0;padding:14px 18px;'
        f'background:{s["quote_bg"]};border-left:4px {border_style} {s["quote_border"]};'
        f'border-radius:0 4px 4px 0;text-align:{align};">'
        f'<span style="font-size:{q_font_size};color:#555;line-height:{s["line_height"]};'
        f'font-style:italic;letter-spacing:0.5px;">{inline_text(text)}</span></section>'
    )


def render_divider(s):
    symbol = s.get('divider_symbol', '· · ·')
    letter_spacing = '8px' if symbol == '· · ·' else '4px'
    return (
        f'<section style="margin:20px 0;text-align:center;">'
        f'<span style="color:{s["accent"]};font-size:14px;letter-spacing:{letter_spacing};">{symbol}</span>'
        f'</section>'
    )


def render_list_item(text, s, ordered=False, idx=1):
    marker = f'{idx}.' if ordered else '●'
    return (
        f'<section style="margin:0 0 8px 20px;">'
        f'<span style="font-size:{s["font_size"]};color:{s["text_color"]};'
        f'line-height:{s["line_height"]};">'
        f'<span style="color:{s["accent"]};font-weight:700;margin-right:6px;">{marker}</span>'
        f'{inline_text(text)}</span></section>'
    )


def parse_markdown(md_text, image_map=None):
    """
    解析 markdown，返回元素列表。
    image_map: {标记名: 实际路径}，如 {'ILLU1': 'D:/path/illu1.jpg'}
    [[ILLU1]] 标记会被替换为图片。
    """
    lines = md_text.split('\n')
    elements = []
    i = 0
    list_idx = 0
    in_list = False

    while i < len(lines):
        line = lines[i].rstrip()

        # 空行
        if not line.strip():
            if in_list:
                in_list = False
                list_idx = 0
            i += 1
            continue

        # 一级标题
        if line.startswith('# ') and not line.startswith('## '):
            elements.append(('title', line[2:].strip()))
            i += 1
            continue

        # 二级标题
        if line.startswith('## '):
            elements.append(('subtitle2', line[3:].strip()))
            i += 1
            continue

        # 三级标题
        if line.startswith('### '):
            elements.append(('subtitle3', line[4:].strip()))
            i += 1
            continue

        # 分割线
        if re.match(r'^-{3,}$|^\*{3,}$', line.strip()):
            elements.append(('divider',))
            i += 1
            continue

        # 引用
        if line.startswith('> '):
            quote_lines = []
            while i < len(lines) and lines[i].startswith('> '):
                quote_lines.append(lines[i][2:].strip())
                i += 1
            elements.append(('quote', ' '.join(quote_lines)))
            continue

        # 图片 markdown ![alt](path)
        m = re.match(r'^!\[([^\]]*)\]\(([^)]+)\)', line)
        if m:
            elements.append(('image', m.group(2), m.group(1)))
            i += 1
            continue

        # [[ILLU1]] 图片标记
        m = re.match(r'^\[\[(ILLU\d+)\]\]$', line.strip())
        if m:
            tag = m.group(1)
            if image_map and tag in image_map:
                elements.append(('image', image_map[tag], tag))
            else:
                elements.append(('image_placeholder', tag))
            i += 1
            continue

        # 有序列表
        m = re.match(r'^(\d+)\.\s+(.+)', line)
        if m:
            if not in_list:
                in_list = True
                list_idx = 0
            list_idx += 1
            elements.append(('olist', m.group(2), list_idx))
            i += 1
            continue

        # 无序列表
        if line.startswith('- ') or line.startswith('* '):
            in_list = True
            elements.append(('ulist', line[2:].strip()))
            i += 1
            continue

        # 普通段落（合并连续非空行）
        para_lines = [line]
        i += 1
        while i < len(lines) and lines[i].strip() and not re.match(r'^(#|>|-|\*|\d+\.|!\[|\[\[)', lines[i].strip()):
            para_lines.append(lines[i].rstrip())
            i += 1
        elements.append(('para', ' '.join(para_lines)))

    return elements


def generate_html(md_text, style_name='jianyue', image_map=None, author='轻风教育'):
    s = STYLES.get(style_name, STYLES['jianyue'])
    elements = parse_markdown(md_text, image_map)

    parts = []
    # 外层容器
    parts.append(f'<section style="background:{s["body_bg"]};padding:20px 16px;font-family:{FONT_STACK};max-width:100%;">')

    for el in elements:
        typ = el[0]
        if typ == 'title':
            parts.append(render_title(el[1], s))
        elif typ == 'subtitle2':
            parts.append(render_subtitle(el[1], s, 2))
        elif typ == 'subtitle3':
            parts.append(render_subtitle(el[1], s, 3))
        elif typ == 'para':
            parts.append(render_paragraph(el[1], s))
        elif typ == 'image':
            parts.append(render_image(el[1], el[2] if len(el) > 2 else '', s))
        elif typ == 'image_placeholder':
            parts.append(f'<!-- 图片占位: {el[1]}，请替换为实际图片路径 -->')
        elif typ == 'quote':
            parts.append(render_quote(el[1], s))
        elif typ == 'divider':
            parts.append(render_divider(s))
        elif typ == 'olist':
            parts.append(render_list_item(el[1], s, ordered=True, idx=el[2]))
        elif typ == 'ulist':
            parts.append(render_list_item(el[1], s, ordered=False))

    # 文末署名
    parts.append(
        f'<section style="margin:28px 0 8px;text-align:right;">'
        f'<span style="font-size:13px;color:#999;line-height:1.6;">—— {esc(author)}</span>'
        f'</section>'
    )
    parts.append('</section>')

    return '\n'.join(parts)


# ========== 模式2：HTML 优化（全链条用，把通用HTML转为公众号可渲染的内联样式HTML） ==========

def extract_css_rules(css_text):
    """解析 CSS 文本，返回规则列表 [(selector, {prop: value}), ...]"""
    rules = []
    # 移除注释
    css_text = re.sub(r'/\*.*?\*/', '', css_text, flags=re.DOTALL)
    # 匹配 选择器 { 声明块 }
    pattern = re.compile(r'([^{}]+)\{([^{}]*)\}', re.DOTALL)
    for m in pattern.finditer(css_text):
        selector = m.group(1).strip()
        declarations = m.group(2).strip()
        if not selector or not declarations:
            continue
        decl_dict = {}
        for decl in declarations.split(';'):
            decl = decl.strip()
            if ':' in decl:
                prop, val = decl.split(':', 1)
                decl_dict[prop.strip()] = val.strip()
        if decl_dict:
            # 处理逗号分隔的多选择器
            for sel in selector.split(','):
                sel = sel.strip()
                if sel:
                    rules.append((sel, decl_dict))
    return rules


def match_selector(selector, tag_name, classes, element_id=''):
    """简化版选择器匹配：支持标签选择器、.class选择器、#id选择器、组合（tag.class）"""
    selector = selector.strip()
    # 伪类去掉（:hover, :first-child等）
    selector = re.sub(r':[a-zA-Z-]+(\([^)]*\))?', '', selector).strip()
    if not selector:
        return False

    # 通用选择器
    if selector == '*':
        return True

    # #id 选择器
    if selector.startswith('#'):
        return element_id == selector[1:]

    # .class 选择器
    if selector.startswith('.'):
        return selector[1:] in classes

    # tag.class 组合
    if '.' in selector and not selector.startswith('.'):
        parts = selector.split('.', 1)
        tag = parts[0].lower()
        cls = parts[1]
        return tag_name == tag and cls in classes

    # 纯标签选择器
    return tag_name == selector.lower()


def inline_css_in_html(html_content, image_dir=''):
    """
    把 HTML 中 <style> 的 CSS 转为内联 style=""，移除 <style> 和 class。
    image_dir: 图片目录，用于把相对路径转为绝对路径。
    """
    # 1. 提取 <style> 内容
    style_match = re.search(r'<style[^>]*>(.*?)</style>', html_content, re.DOTALL | re.IGNORECASE)
    css_rules = []
    if style_match:
        css_rules = extract_css_rules(style_match.group(1))

    # 2. 移除 <style> 标签
    html_content = re.sub(r'<style[^>]*>.*?</style>', '', html_content, flags=re.DOTALL | re.IGNORECASE)

    # 3. 图片相对路径转绝对路径
    if image_dir:
        image_dir_abs = os.path.abspath(image_dir).replace('\\', '/')
        def _abs_img(m):
            src = m.group(1)
            if src.startswith(('http://', 'https://', 'data:')):
                return m.group(0)
            # 相对路径转绝对
            abs_path = os.path.join(image_dir_abs, src).replace('\\', '/')
            return f'src="{abs_path}"'
        html_content = re.sub(r'src="([^"]+)"', _abs_img, html_content)

    # 4. 遍历 HTML 元素，应用 CSS 规则
    # 简化处理：用正则匹配开标签，提取 tag、class、id，计算内联样式
    def _apply_style(m):
        tag_full = m.group(0)
        # 提取标签名
        tag_match = re.match(r'<(\w+)', tag_full)
        if not tag_match:
            return tag_full
        tag_name = tag_match.group(1).lower()
        # 跳过自闭合标签的特殊处理（img等仍要处理）
        if tag_name in ('html', 'head', 'meta', 'link', 'title', 'body', 'script'):
            return tag_full

        # 提取 class
        class_match = re.search(r'class="([^"]*)"', tag_full)
        classes = class_match.group(1).split() if class_match else []
        # 提取 id
        id_match = re.search(r'id="([^"]*)"', tag_full)
        elem_id = id_match.group(1) if id_match else ''
        # 提取已有 style
        style_match = re.search(r'style="([^"]*)"', tag_full)
        existing_style = style_match.group(1) if style_match else ''

        # 合并匹配的 CSS 规则（按顺序，后面的覆盖前面的）
        merged = {}
        # 解析已有 style
        if existing_style:
            for decl in existing_style.split(';'):
                decl = decl.strip()
                if ':' in decl:
                    p, v = decl.split(':', 1)
                    merged[p.strip()] = v.strip()
        # 应用 CSS 规则
        for selector, decl_dict in css_rules:
            if match_selector(selector, tag_name, classes, elem_id):
                merged.update(decl_dict)

        # 生成新的 style 字符串
        if merged:
            new_style = '; '.join(f'{k}: {v}' for k, v in merged.items())
            # 替换或添加 style 属性
            if style_match:
                tag_full = re.sub(r'style="[^"]*"', f'style="{new_style}"', tag_full)
            else:
                tag_full = tag_full[:-1] + f' style="{new_style}">'

        # 移除 class 属性（公众号会清洗）
        tag_full = re.sub(r'\s+class="[^"]*"', '', tag_full)
        # 移除 id 属性
        tag_full = re.sub(r'\s+id="[^"]*"', '', tag_full)

        return tag_full

    # 匹配所有开标签（包括自闭合）
    html_content = re.sub(r'<\w+[^>]*>', _apply_style, html_content)

    # 5. 用 section 包裹 body 内容（公众号偏好 section 嵌套）
    # 提取 body 内容
    body_match = re.search(r'<body[^>]*>(.*?)</body>', html_content, re.DOTALL | re.IGNORECASE)
    if body_match:
        body_content = body_match.group(1).strip()
        # 去掉 container div，直接用 section 包裹
        body_content = re.sub(r'<div class="container">', '', body_content)
        body_content = re.sub(r'</div>\s*$', '', body_content)
        html_content = f'<section style="max-width:100%;padding:0;margin:0;">{body_content}</section>'

    return html_content


def optimize_html_for_gzh(input_path, output_path, image_dir=''):
    """HTML 优化模式主函数"""
    with open(input_path, 'r', encoding='utf-8') as f:
        html_content = f.read()

    result = inline_css_in_html(html_content, image_dir)

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(result)

    # 统计
    img_count = len(re.findall(r'<img ', result))
    section_count = len(re.findall(r'<section', result))
    print(f'[OK] HTML 优化完成: {output_path}')
    print(f'     模式: HTML优化（通用HTML → 公众号内联样式HTML）')
    print(f'     图片: {img_count} 张')
    print(f'     section: {section_count} 个')
    print(f'     用法: 交给 QingFeng-wechat-publisher 发布，或浏览器打开后全选复制粘贴到公众号编辑器')


def main():
    ap = argparse.ArgumentParser(description='QingFeng-GZH-Layout 公众号排版生成器')
    ap.add_argument('--mode', '-m', default='md', choices=['md', 'html'],
                    help='模式: md=markdown排版（单独使用，五套风格）; html=HTML优化（全链条用，通用HTML转公众号内联样式）')
    ap.add_argument('--input', '-i', required=True, help='输入文件（md模式: markdown文件; html模式: 通用HTML文件）')
    ap.add_argument('--output', '-o', required=True, help='输出 HTML 文件')
    ap.add_argument('--style', default='jianyue', choices=list(STYLES.keys()),
                    help='排版风格（仅md模式）: guofeng/jianyue/keji/zazhi/zhiyu')
    ap.add_argument('--author', default='轻风教育', help='文末署名（仅md模式）')
    ap.add_argument('--image-dir', default='', help='图片目录（md模式: [[ILLU1]]标记查找; html模式: 相对路径转绝对路径）')
    args = ap.parse_args()

    if args.mode == 'html':
        # HTML 优化模式
        optimize_html_for_gzh(args.input, args.output, args.image_dir)
        return

    # markdown 排版模式（原有功能）
    with open(args.input, 'r', encoding='utf-8') as f:
        md_text = f.read()

    # 构建图片映射（支持 illu1.jpg 和 illustration_1.jpg 两种命名）
    image_map = {}
    if args.image_dir and os.path.isdir(args.image_dir):
        for fn in os.listdir(args.image_dir):
            low = fn.lower()
            m = re.match(r'(illu\d+|illustration_\d+|cover)\.(jpg|jpeg|png|webp)', low)
            if m:
                key = m.group(1).upper()
                # illustration_1 -> ILLU1
                key = re.sub(r'^ILLUSTRATION_(\d+)$', r'ILLU\1', key)
                image_map[key] = os.path.join(args.image_dir, fn).replace('\\', '/')

    html = generate_html(md_text, args.style, image_map, args.author)

    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    with open(args.output, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f'[OK] 公众号排版已生成: {args.output}')
    print(f'     模式: markdown排版（{STYLES[args.style]["name"]}风格）')
    print(f'     图片映射: {len(image_map)} 张')
    print(f'     用法: 用浏览器打开 HTML，全选复制，粘贴到公众号编辑器即可保留样式')


if __name__ == '__main__':
    main()
