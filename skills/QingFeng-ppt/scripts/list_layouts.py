# -*- coding: utf-8 -*-
"""列出某模板的版式（名称 + 适用场景），供第 2 步用户选择/锁定每页版式。

用法:
    python list_layouts.py <template.pptx>
"""
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from pptx import Presentation

# 版式名 -> 适用场景（按名称关键字匹配）
ROLE_HINTS = [
    ('封面',     '封面页：标题 + 副标题'),
    ('目录',     '目录页：章节列表'),
    ('节',       '章节过渡 / 分隔页'),
    ('单栏',     '单关键词内容 / 引言 / 过渡页'),
    ('两栏',     '2 个要点并排'),
    ('三栏',     '3 个要点并排'),
    ('四栏',     '4 个要点并排'),
    ('六栏',     '6 个要点并排'),
    ('左图右文', '左侧图、右侧文字'),
    ('右图左文', '右侧图、左侧文字'),
    ('大图',     '全屏大图 + 标题'),
    ('四图',     '4 图网格'),
    ('三图',     '3 图网格'),
    ('空白',     '自定义空白页'),
]


def hint(name):
    for k, v in ROLE_HINTS:
        if k in name:
            return v
    return '通用内容页'


def main():
    if len(sys.argv) < 2:
        print('usage: list_layouts.py <template.pptx>')
        sys.exit(1)
    path = sys.argv[1]
    prs = Presentation(path)
    m = prs.slide_masters[0]
    lays = list(m.slide_layouts)
    print('模板版式列表（共 %d 个）：' % len(lays))
    for i, lay in enumerate(lays):
        print('  %2d. %-22s %s' % (i + 1, lay.name, hint(lay.name)))


if __name__ == '__main__':
    main()
