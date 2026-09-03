#!/usr/bin/env python3
"""头条号 HTML 解析器 - Step 2

只做一件事：从 HTML 文件中提取结构化内容块。
- 标题（h1/h2/h3）→ 区分层级
- 段落（p）→ 保留原文，清理 &nbsp;
- 图片位置 → 记录在序列中

输出：纯文本内容块列表 + 图片插入位置
"""
import re, os, json, sys

def parse_html(html_path):
    """解析 HTML → 结构化内容块
    
    返回:
      title: str (从 h1 提取)
      blocks: list[dict] 每个 dict 格式:
        {'type': 'title', 'level': 1/2/3, 'text': '...'}
        或
        {'type': 'text', 'text': '...'}
        或
        {'type': 'image', 'src': '绝对路径', 'alt': '...'}
    """
    html_path = os.path.abspath(html_path)
    base_dir = os.path.dirname(html_path)

    with open(html_path, 'r', encoding='utf-8') as f:
        html = f.read()

    # ====== 预处理 &nbsp; ======
    html = html.replace('&nbsp;', ' ')
    html = re.sub(r' {2,}', ' ', html)

    # ====== 提取标题 (h1) ======
    title_match = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.DOTALL)
    title = re.sub(r'<[^>]+>', '', title_match.group(1)).strip() if title_match else ''

    # ====== 收集所有内容元素及其位置 ======
    elements = []

    # h2 小标题
    for m in re.finditer(r'<h2[^>]*>(.*?)</h2>', html, re.DOTALL):
        text = re.sub(r'<[^>]+>', '', m.group(1)).strip()
        if text:
            elements.append({'type': 'title', 'level': 2, 'text': text, 'pos': m.start()})

    # h3 小标题
    for m in re.finditer(r'<h3[^>]*>(.*?)</h3>', html, re.DOTALL):
        text = re.sub(r'<[^>]+>', '', m.group(1)).strip()
        if text:
            elements.append({'type': 'title', 'level': 3, 'text': text, 'pos': m.start()})

    # p 段落
    for m in re.finditer(r'<p[^>]*>(.*?)</p>', html, re.DOTALL):
        text = re.sub(r'<[^>]+>', '', m.group(1)).strip()
        if len(text) > 5:  # 过滤太短的空段落
            elements.append({'type': 'text', 'text': text, 'pos': m.start()})

    # img 图片
    for m in re.finditer(r'<img[^>]+\bsrc=["\']([^"\']+)["\'][^>]*(?:\balt=["\']([^"\']*)["\'])?', html, re.I):
        src = m.group(1).strip()
        alt = m.group(2) or ''
        abs_path = os.path.normpath(os.path.join(base_dir, src.replace('/', os.sep)))
        exists = os.path.exists(abs_path)
        elements.append({
            'type': 'image',
            'src': abs_path,
            'alt': alt,
            'pos': m.start(),
            'exists': exists
        })

    # ====== 按原始位置排序 ======
    elements.sort(key=lambda x: x['pos'])

    # 清理 pos 字段（输出不需要）
    for el in elements:
        del el['pos']

    return title, elements


def main():
    if len(sys.argv) < 2:
        print("用法: python parse_html.py <HTML文件路径>")
        sys.exit(1)

    html_file = sys.argv[1]
    
    if not os.path.exists(html_file):
        print(f"❌ 文件不存在: {html_file}")
        sys.exit(1)

    print(f"📄 解析: {html_file}\n")
    title, blocks = parse_html(html_file)

    print(f"{'='*60}")
    print(f"📌 标题: {title}")
    print(f"{'='*60}")
    print(f"📦 内容块总数: {len(blocks)}")
    print()

    text_count = 0
    title_count = 0
    img_count = 0

    for i, block in enumerate(blocks):
        bt = block['type']
        
        if bt == 'title':
            level = block['level']
            prefix = '#' * level
            print(f"[{i:3d}] 📌 {prefix} {block['text'][:50]}")
            title_count += 1
        
        elif bt == 'text':
            preview = block['text'].replace('\n', '\\n')[:60]
            chars = len(block['text'])
            print(f"[{i:3d}] 📝 ({chars}字) {preview}...")
            text_count += 1
        
        elif bt == 'image':
            name = os.path.basename(block['src'])
            status = '✅' if block.get('exists') else '❌'
            print(f"[{i:3d}] 🖼️ [{status}] {name}")
            img_count += 1

    print(f"\n{'='*60}")
    print(f"统计: 标题={title_count}, 段落={text_count}, 图片={img_count}")

    # 输出 JSON 供后续使用
    output = {
        'file': html_file,
        'title': title,
        'blocks': blocks,
        'stats': {
            'titles': title_count,
            'paragraphs': text_count,
            'images': img_count,
            'total_chars': sum(len(b['text']) for b in blocks if b['type'] in ('text','title'))
        }
    }

    json_path = html_file.rsplit('.', 1)[0] + '_parsed.json'
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n💾 JSON 已保存: {json_path}")


if __name__ == '__main__':
    main()
