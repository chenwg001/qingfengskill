# -*- coding: utf-8 -*-
"""QingFeng-ppt · 大纲结构校验器

在「第 2 步产出大纲」后、「第 3 步生成 PPT」前运行，确认大纲符合
优化后的生成方法论：

  1) 至少 4 个部分（用 [节标题] 页做部分分隔）
  2) 每个部分至少 2 个要点（即 2 个内容页）
  3) 每个要点（内容页）提炼 2-6 条内容
  4) 每条内容 = 一个关键词(二级标题) + 非空的核心内容(正文)
  5) 关键词与核心内容一一配对（body[i] 对应 keywords[i]）

用法：
    python validate_outline.py 大纲.md
返回码 0 = 通过；非 0 = 存在需修复的问题（同时打印明细）。
"""
import sys, os
# 不在此处重复包裹 sys.stdout：导入 build_ppt 时它已做一次 UTF-8 包裹，
# 二次包裹会导致底层 buffer 被提前关闭（I/O operation on closed file）。

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from build_ppt import parse_outline, norm_layout  # noqa: E402  (导入即完成 stdout UTF-8 包裹)


def lk(page):
    """把页面原始标注归一化成版式 key"""
    return norm_layout(page.get('layout'))

SPECIAL = {'cover', 'toc', 'section', 'blank'}


def main():
    if len(sys.argv) < 2:
        print('用法: python validate_outline.py 大纲.md')
        sys.exit(2)
    md = sys.argv[1]
    if not os.path.exists(md):
        print('[错误] 文件不存在:', md)
        sys.exit(2)

    pages = parse_outline(md)
    errors, warns = [], []

    # 归类页面（用归一化后的版式 key 判断）
    cover = [p for p in pages if lk(p) == 'cover']
    toc = [p for p in pages if lk(p) == 'toc']
    sections = [p for p in pages if lk(p) == 'section']
    contents = [p for p in pages if lk(p) not in SPECIAL]

    print('=' * 60)
    print('大纲结构校验报告  ', os.path.basename(md))
    print('=' * 60)
    print(f'总页数(含封面/目录/节/内容/空白): {len(pages)}')
    print(f'  封面: {len(cover)}  目录: {len(toc)}  节标题(部分): {len(sections)}  '
          f'内容页(要点): {len(contents)}')

    # 1) 部分数
    if len(sections) < 4:
        errors.append(f'部分数={len(sections)}，不足 4 个（要求 ≥4）。请用 [节标题] 页分隔至少 4 个部分。')
    else:
        print(f'  ✅ 部分数 {len(sections)} ≥ 4')

    # 2) 每部分下的要点数 + 3/4/5 校验
    # 把内容页按所属部分分组：内容页归属「其前面的那一个 [节标题]」
    groups = []
    cur = []
    pending = None
    for p in pages:
        k = lk(p)
        if k == 'section':
            if pending is not None:
                groups.append((pending, cur))
            pending = p['title']
            cur = []
        elif k in SPECIAL:
            continue  # 封面/目录/空白 不计入要点分组
        else:
            cur.append(p)
    if pending is not None and cur:
        groups.append((pending, cur))

    for si, (sec_title, grp) in enumerate(groups, 1):
        n_point = len(grp)
        tag = '✅' if n_point >= 2 else '❌'
        if n_point < 2:
            errors.append(f'部分「{sec_title}」仅有 {n_point} 个要点，不足 2 个（要求 ≥2）。')
        print(f'\n  部分 {si}: {sec_title}  →  要点数 {n_point} {tag}')
        for ci, p in enumerate(grp, 1):
            n_kw = len(p['keywords'])
            title = p['title']
            if n_kw == 0:
                # 无关键词页（单栏/图文等）不强制 2-6，但提示
                print(f'    · 要点 {ci}: {title}  （无二级标题，按单栏/图文处理）')
                continue
            if n_kw < 2 or n_kw > 6:
                errors.append(f'要点「{title}」内容条数={n_kw}，应在 2-6 之间。')
                kw_tag = '❌'
            else:
                kw_tag = '✅'
            # 每条内容是否有关键词+核心
            miss = []
            for i, kw in enumerate(p['keywords']):
                core = p['body'][i] if i < len(p['body']) else ''
                if not core or not core.strip():
                    miss.append(kw)
            if miss:
                errors.append(f'要点「{title}」以下关键词缺少核心内容: {", ".join(miss)}')
            print(f'    · 要点 {ci}: {title}  →  内容 {n_kw} 条 {kw_tag}'
                  + (f'  ⚠ 缺核心: {miss}' if miss else ''))
            for i, kw in enumerate(p['keywords']):
                core = (p['body'][i] if i < len(p['body']) else '').replace('\n', ' / ')
                print(f'        - {kw} :: {core[:40]}{"…" if len(core) > 40 else ""}')

    # 封面/目录 提示
    if not cover:
        warns.append('未指定 [封面] 页（可选，建议有）。')
    if not toc:
        warns.append('未指定 [目录] 页（可选，建议有）。')

    # 丰富度提示：内容页关键词数量是否过于单一（只是建议，不算错误）
    counts = [len(p['keywords']) for p in contents if p['keywords']]
    if len(counts) >= 3 and len(set(counts)) == 1:
        warns.append(
            f'所有内容页都提炼了相同数量的关键词（均为 {counts[0]} 个）。'
            f'建议按内容让数量在 2/3/4/6 之间变化（模板栏数：两栏=2、三栏=3、四栏=4、六栏=6），页面更丰富。')

    print('\n' + '=' * 60)
    if errors:
        print(f'❌ 校验未通过，共 {len(errors)} 处需修复：')
        for e in errors:
            print('   -', e)
    else:
        print('✅ 校验通过：符合「4 部分 / 每部分≥2 要点 / 每要点 2-6 条内容 / 关键词+核心齐全」的结构要求。')
    for w in warns:
        print('   ⚠', w)
    print('=' * 60)
    sys.exit(1 if errors else 0)


if __name__ == '__main__':
    main()
