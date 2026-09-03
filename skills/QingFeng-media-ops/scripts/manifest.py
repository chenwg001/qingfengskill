# -*- coding: utf-8 -*-
"""
轻风媒体运营 批次清单管理（manifest.json 唯一事实来源）

用法:
  python manifest.py init --date 8.31 --topic "主题"        # 建批次目录+清单
  python manifest.py init --date 8.31                       # 主题留空
  python manifest.py update --date 8.31 --key articles.toutiao --value "路径"
  python manifest.py get --date 8.31 --key publish_status.douyin
  python manifest.py list --date 8.31                       # 查看整批
  （不传 --date 默认今天，格式 M.D 如 8.31）

说明:
  - 批次根目录从 assets/config.yaml 的 output_root 读取（默认 D:/知识库/媒体运营）
  - 每步完成即 update 一次，支持断点续跑
"""
import argparse
import json
import os
import sys
import datetime

sys.stdout.reconfigure(encoding='utf-8')

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(SKILL_DIR, 'assets', 'config.yaml')

DEFAULT_STRUCT = {
    'date': '',
    'topic': '',
    'articles': {},     # {platform: article_path}
    'formatted': {},    # {platform: formatted_path}
    'images': {},       # {platform_type: path}
    'videos': {},       # {platform: video_path}
    'publish_status': {},  # {platform: pending|done|failed|need_human}
    'draft_links': {},  # {platform: url}
    'notes': [],
}


def load_config():
    """极简 yaml 读取（仅取 output_root），避免依赖 pyyaml。"""
    output_root = None
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line.startswith('output_root:'):
                    output_root = line.split(':', 1)[1].strip().strip('"').strip("'")
    except Exception as e:
        print(f'[WARN] 读取 config.yaml 失败: {e}', file=sys.stderr)
    if not output_root:
        output_root = 'D:/知识库/媒体运营'
    return output_root


def batch_dir(output_root, date):
    return os.path.join(output_root, date)


def manifest_path(output_root, date):
    return os.path.join(batch_dir(output_root, date), 'manifest.json')


def today():
    d = datetime.date.today()
    return f"{d.year % 100}.{d.month}.{d.day}"


def load_manifest(output_root, date):
    path = manifest_path(output_root, date)
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None


def save_manifest(output_root, date, data):
    d = batch_dir(output_root, date)
    os.makedirs(d, exist_ok=True)
    path = manifest_path(output_root, date)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return path


def set_key(data, key, value):
    """按 a.b.c 点号路径写值，自动建中间 dict。"""
    parts = key.split('.')
    cur = data
    for p in parts[:-1]:
        if p not in cur or not isinstance(cur[p], dict):
            cur[p] = {}
        cur = cur[p]
    cur[parts[-1]] = value
    return data


def get_key(data, key):
    cur = data
    for p in key.split('.'):
        if isinstance(cur, dict) and p in cur:
            cur = cur[p]
        else:
            return None
    return cur


def main():
    ap = argparse.ArgumentParser(description='轻风媒体运营批次清单')
    sub = ap.add_subparsers(dest='cmd', required=True)

    p_init = sub.add_parser('init')
    p_init.add_argument('--date', default=today())
    p_init.add_argument('--topic', default='')

    p_up = sub.add_parser('update')
    p_up.add_argument('--date', default=today())
    p_up.add_argument('--key', required=True)
    p_up.add_argument('--value', required=True)

    p_get = sub.add_parser('get')
    p_get.add_argument('--date', default=today())
    p_get.add_argument('--key', required=True)

    p_list = sub.add_parser('list')
    p_list.add_argument('--date', default=today())

    args = ap.parse_args()
    output_root = load_config()
    date = getattr(args, 'date', today())

    if args.cmd == 'init':
        data = load_manifest(output_root, date)
        if data is None:
            data = dict(DEFAULT_STRUCT)
            data['date'] = date
        if args.topic:
            data['topic'] = args.topic
        path = save_manifest(output_root, date, data)
        print(f'[OK] 批次已初始化: {path}')
        for d in ('articles', 'formatted', 'images', 'videos', 'drafts'):
            os.makedirs(os.path.join(batch_dir(output_root, date), d), exist_ok=True)
        return

    data = load_manifest(output_root, date)
    if data is None:
        print(f'[FAIL] 批次 {date} 不存在，先执行 init', file=sys.stderr)
        sys.exit(1)

    if args.cmd == 'update':
        set_key(data, args.key, args.value)
        path = save_manifest(output_root, date, data)
        print(f'[OK] {args.key} = {args.value} -> {path}')
    elif args.cmd == 'get':
        print(get_key(data, args.key))
    elif args.cmd == 'list':
        print(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
