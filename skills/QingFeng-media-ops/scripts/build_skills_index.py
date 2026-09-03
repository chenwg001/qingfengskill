# -*- coding: utf-8 -*-
r"""
轻风技能索引生成器（Plan B 技能发现修复核心）

背景：技能库根目录 D:\chenw\AgentSpace\.agents\skills 不在运行时自动发现列表里，
所以技能不会自动触发。Plan B = 按路径调用，用本脚本把全部技能扫描成
可检索目录（名称/说明/路径/关键脚本），任何会话先查索引、再按路径调用。

用法:
  python build_skills_index.py               # 生成/更新全量索引
  python build_skills_index.py --search 视频  # 按关键词搜索技能（打印匹配项）
  python build_skills_index.py --json-only   # 只更新 json，不重写 md

输出:
  D:\chenw\AgentSpace\.agents\skills_index.json
  D:\chenw\AgentSpace\.agents\skills_index.md
"""
import argparse
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')

SKILLS_ROOT = r'D:\chenw\AgentSpace\.agents\skills'
INDEX_JSON = r'D:\chenw\AgentSpace\.agents\skills_index.json'
INDEX_MD = r'D:\chenw\AgentSpace\.agents\skills_index.md'


def parse_frontmatter(text):
    """解析 SKILL.md 顶部 YAML frontmatter（支持 name/description 多行折叠）。"""
    m = re.match(r'^---\s*\n(.*?)\n---\s*', text, re.DOTALL)
    if not m:
        return {}
    lines = m.group(1).splitlines()
    data = {}
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip() or line.lstrip().startswith('#'):
            i += 1
            continue
        km = re.match(r'^([A-Za-z0-9_-]+):\s*(.*)$', line)
        if km:
            key, val = km.group(1), km.group(2).strip()
            if val in ('>', '|', '>-', '|-', '>+', '|+'):
                block = []
                i += 1
                while i < len(lines) and (lines[i].startswith(' ') or lines[i].startswith('\t') or lines[i].strip() == ''):
                    if lines[i].strip():
                        block.append(lines[i].strip())
                    i += 1
                data[key] = ' '.join(block).strip()
                continue
            data[key] = val
            i += 1
        else:
            # 缩进续行：并入上一个键（如多行 description）
            if data:
                last_key = list(data.keys())[-1]
                data[last_key] = (str(data[last_key]) + ' ' + line.strip()).strip()
            i += 1
    return data


def scan():
    entries = []
    if not os.path.isdir(SKILLS_ROOT):
        print(f'[FAIL] 技能库不存在: {SKILLS_ROOT}', file=sys.stderr)
        sys.exit(1)
    for d in sorted(os.listdir(SKILLS_ROOT)):
        dpath = os.path.join(SKILLS_ROOT, d)
        if not os.path.isdir(dpath):
            continue
        skill_md = os.path.join(dpath, 'SKILL.md')
        fm = {}
        if os.path.exists(skill_md):
            with open(skill_md, 'r', encoding='utf-8') as f:
                fm = parse_frontmatter(f.read())
        scripts = []
        sp = os.path.join(dpath, 'scripts')
        if os.path.isdir(sp):
            scripts = sorted(
                f for f in os.listdir(sp)
                if f.endswith(('.py', '.js', '.mjs', '.ts', '.sh'))
            )
        entries.append({
            'dir': d,
            'name': fm.get('name', d),
            'description': fm.get('description', ''),
            'path': dpath,
            'scripts': scripts,
            'has_skill': os.path.exists(skill_md),
        })
    return entries


def to_md(entries):
    lines = ['# 轻风技能索引（Plan B 技能发现）', '']
    lines.append(f'- 技能库：`{SKILLS_ROOT}`')
    lines.append(f'- 技能总数：{len(entries)}')
    lines.append(f'- 索引生成命令：`python scripts/build_skills_index.py`（位于 QingFeng-media-ops/scripts）')
    lines.append('- 使用方式：先在此表按关键词找技能，拿到 `path`，再 Read 该技能 SKILL.md / 按路径运行其 scripts。')
    lines.append('')
    lines.append('| 技能名 | 说明 | 关键脚本 |')
    lines.append('|---|---|---|')
    for e in entries:
        desc = e['description'].replace('|', '\\|').replace('\n', ' ')
        if len(desc) > 90:
            desc = desc[:90] + '…'
        scripts = ', '.join(e['scripts'][:6]) if e['scripts'] else '—'
        lines.append(f"| `{e['name']}` | {desc} | {scripts} |")
    return '\n'.join(lines) + '\n'


def main():
    ap = argparse.ArgumentParser(description='轻风技能索引生成器')
    ap.add_argument('--search', default='')
    ap.add_argument('--json-only', action='store_true')
    args = ap.parse_args()

    entries = scan()

    if args.search:
        kw = args.search.lower()
        hits = [e for e in entries if kw in e['name'].lower() or kw in e['description'].lower() or kw in e['dir'].lower()]
        print(f'搜索「{args.search}」命中 {len(hits)} 个技能：')
        for e in hits:
            print(f"  - {e['name']}  ({e['dir']})")
            print(f"      路径: {e['path']}")
            desc = e['description'].replace('\n', ' ')
            print(f"      说明: {desc[:120]}")
        return

    os.makedirs(os.path.dirname(INDEX_JSON), exist_ok=True)
    with open(INDEX_JSON, 'w', encoding='utf-8') as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)
    print(f'[OK] json 索引已生成: {INDEX_JSON}（{len(entries)} 个技能）')

    if not args.json_only:
        with open(INDEX_MD, 'w', encoding='utf-8') as f:
            f.write(to_md(entries))
        print(f'[OK] md 索引已生成: {INDEX_MD}')


if __name__ == '__main__':
    main()
