# -*- coding: utf-8 -*-
"""
轻风媒体运营 日报生成

用法:
  python report.py --manifest D:/知识库/媒体运营/8.31/manifest.json -o report.md
  python report.py --date 8.31 [-o report.md]

读取批次 manifest.json，输出 markdown 日报：选题、三平台文章/图片/视频清单、
各平台草稿状态与链接、失败项。
"""
import argparse
import json
import os
import sys
import datetime

sys.stdout.reconfigure(encoding='utf-8')

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(SKILL_DIR, 'assets', 'config.yaml')
DEFAULT_ROOT = 'D:/知识库/媒体运营'

PLATFORM_CN = {
    'toutiao': '头条', 'wechat': '公众号', 'xhs': '小红书',
    'douyin': '抖音', 'kuaishou': '快手', 'bilibili': 'B站',
}
STATUS_CN = {'pending': '待处理', 'done': '已完成', 'failed': '失败', 'need_human': '需人工'}


def load_output_root():
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line.startswith('output_root:'):
                    return line.split(':', 1)[1].strip().strip('"').strip("'")
    except Exception:
        pass
    return DEFAULT_ROOT


def today():
    d = datetime.date.today()
    return f"{d.year % 100}.{d.month}.{d.day}"


def main():
    ap = argparse.ArgumentParser(description='轻风媒体运营日报')
    ap.add_argument('--manifest', default='')
    ap.add_argument('--date', default=today())
    ap.add_argument('-o', '--output', default='')
    args = ap.parse_args()

    if args.manifest:
        mpath = args.manifest
    else:
        mpath = os.path.join(load_output_root(), args.date, 'manifest.json')
    if not os.path.exists(mpath):
        print(f'[FAIL] 找不到 manifest: {mpath}', file=sys.stderr)
        sys.exit(1)

    with open(mpath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    out = []
    out.append(f'# 轻风媒体运营日报 · {data.get("date", args.date)}')
    out.append('')
    out.append(f'- **选题**：{data.get("topic") or "（未填写）"}')
    out.append('')

    # 文章
    articles = data.get('articles', {})
    if articles:
        out.append('## 三平台文章')
        for k, v in articles.items():
            out.append(f'- {PLATFORM_CN.get(k, k)}：`{v}`')
        out.append('')

    # 排版
    formatted = data.get('formatted', {})
    if formatted:
        out.append('## 排版成品')
        for k, v in formatted.items():
            out.append(f'- {PLATFORM_CN.get(k, k)}：`{v}`')
        out.append('')

    # 图片
    images = data.get('images', {})
    if images:
        out.append('## 配图')
        for k, v in images.items():
            out.append(f'- `{k}`：`{v}`')
        out.append('')

    # 视频
    videos = data.get('videos', {})
    if videos:
        out.append('## 短视频')
        for k, v in videos.items():
            out.append(f'- {PLATFORM_CN.get(k, k)}：`{v}`')
        out.append('')

    # 发布状态
    status = data.get('publish_status', {})
    if status:
        out.append('## 草稿状态')
        out.append('| 平台 | 状态 | 草稿链接 |')
        out.append('|---|---|---|')
        links = data.get('draft_links', {})
        for k, v in status.items():
            link = links.get(k, '')
            out.append(f'| {PLATFORM_CN.get(k, k)} | {STATUS_CN.get(v, v)} | {link} |')
        out.append('')

    notes = data.get('notes', [])
    if notes:
        out.append('## 备注/失败项')
        for n in notes:
            out.append(f'- {n}')
        out.append('')

    out.append('---')
    out.append('> 以上草稿等待人工最终发布。')

    report = '\n'.join(out)
    if args.output:
        os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(report)
        print(f'[OK] 日报已生成: {args.output}')
    else:
        print(report)


if __name__ == '__main__':
    main()
