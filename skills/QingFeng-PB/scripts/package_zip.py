#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
QingFeng-PB —— 离线 ZIP 打包脚本

把排版产物目录（index.html + cover.jpg + illustration_*.jpg + background.jpg）
打包为 webpage_package_<时间戳>.zip，并在包内写入 README.md。
移植自 Coze 工作流 package_download_node 的文件结构约定。

用法：
    python package_zip.py --indir ./output --outdir ./output
"""

import os
import re
import time
import zipfile
import argparse


def build_readme(indir, illustration_count):
    lines = "\n".join([f"- illustration_{i}.jpg: 插图{i}" for i in range(1, illustration_count + 1)])
    return f"""# 网页排版包（QingFeng-PB）

本包包含一篇文章的精美排版网页及其全部资源，离线可用。

## 文件说明

- index.html: 主网页文件（用浏览器打开即可）
- cover.jpg: 封面图
{lines}
- background.jpg: 背景图

## 使用方法

1. 解压本 ZIP 到任意文件夹
2. 双击打开 index.html 即可在浏览器中查看（完全离线）

注意：请保持所有图片文件与 index.html 在同一目录下。
"""


def main():
    ap = argparse.ArgumentParser(description="QingFeng-PB ZIP 打包")
    ap.add_argument('--indir', required=True, help='含 index.html 与图片的目录')
    ap.add_argument('--outdir', default='', help='ZIP 输出目录（缺省同 indir）')
    args = ap.parse_args()

    indir = os.path.abspath(args.indir)
    outdir = os.path.abspath(args.outdir) if args.outdir else indir
    os.makedirs(outdir, exist_ok=True)

    # 统计插图数量（排除封面）
    ill_files = sorted([f for f in os.listdir(indir)
                        if re.match(r'illustration_\d+\.jpg$', f, re.IGNORECASE)])
    illustration_count = len(ill_files)

    # 写 README
    readme_path = os.path.join(indir, 'README.md')
    with open(readme_path, 'w', encoding='utf-8') as f:
        f.write(build_readme(indir, illustration_count))

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    zip_name = f"webpage_package_{timestamp}.zip"
    zip_path = os.path.join(outdir, zip_name)

    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(indir):
            for file in files:
                fp = os.path.join(root, file)
                # 不把预览版打进离线包，避免体积膨胀；仅 index.html + 图片 + README
                if file == 'preview.html':
                    continue
                # 排除自身及历史 zip，防止把旧包嵌套进新包导致体积爆炸
                if file.lower().endswith('.zip'):
                    continue
                # 仅打包 jpg（index.html 只引用 jpg），排除 png 原档避免无谓膨胀
                if file.lower().endswith('.png'):
                    continue
                arc = os.path.relpath(fp, indir)
                zf.write(fp, arc)

    size_mb = round(os.path.getsize(zip_path) / (1024 * 1024), 2)
    print(f"OK zip={zip_path} size={size_mb}MB illustrations={illustration_count}")
    print(f"📦 网页文件包: {zip_name}")
    print(f"   包含: index.html / cover.jpg / illustration_1..{illustration_count}.jpg / background.jpg / README.md")


if __name__ == '__main__':
    main()
