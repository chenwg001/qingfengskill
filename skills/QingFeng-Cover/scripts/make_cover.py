#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
QingFeng-Cover 封面制作脚本
功能：在基础封面图上叠加标题文字，然后按 4:3 / 3:4 / 2.35:1 / 1:1 四种比例输出。
关键规则：先加标题再改尺寸；改尺寸时不裁剪原图，用模糊扩展背景 + 中央缩放原图。
"""

import argparse
import os
import sys
from PIL import Image, ImageDraw, ImageFont, ImageFilter

# 中文字体候选路径（按优先级）
FONT_CANDIDATES = [
    r"C:\Windows\Fonts\msyhbd.ttc",      # 微软雅黑粗体
    r"C:\Windows\Fonts\msyh.ttc",        # 微软雅黑
    r"C:\Windows\Fonts\simhei.ttf",      # 黑体
    r"C:\Windows\Fonts\simsun.ttc",      # 宋体
    "/System/Library/Fonts/PingFang.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
]

# 四种输出比例（宽:高）
RATIOS = {
    "4x3": (4, 3),
    "3x4": (3, 4),
    "235x1": (235, 100),  # 2.35:1
    "1x1": (1, 1),
}

# 输出基准尺寸（短边 1080，长边按比例）
BASE_SIZE = 1080


def find_font():
    """查找可用中文字体"""
    for path in FONT_CANDIDATES:
        if os.path.exists(path):
            return path
    return None


def add_title_to_image(base_img, title, subtitle=None):
    """
    在基础图上叠加标题文字。
    标题居中偏下，带半透明黑色底条 + 白色粗体字 + 阴影。
    返回新的 Image 对象。
    """
    img = base_img.copy()
    draw = ImageDraw.Draw(img, "RGBA")
    w, h = img.size

    font_path = find_font()
    if not font_path:
        print("  [WARN] 未找到中文字体，跳过标题叠加")
        return img

    # 标题字号：图宽的 1/12
    title_size = max(36, int(w / 12))
    try:
        title_font = ImageFont.truetype(font_path, title_size)
    except Exception:
        title_font = ImageFont.load_default()

    # 副标题字号
    sub_size = max(20, int(w / 28))
    try:
        sub_font = ImageFont.truetype(font_path, sub_size)
    except Exception:
        sub_font = ImageFont.load_default()

    # 计算标题尺寸
    title_bbox = draw.textbbox((0, 0), title, font=title_font)
    title_w = title_bbox[2] - title_bbox[0]
    title_h = title_bbox[3] - title_bbox[1]

    # 副标题
    sub_w = sub_h = 0
    if subtitle:
        sub_bbox = draw.textbbox((0, 0), subtitle, font=sub_font)
        sub_w = sub_bbox[2] - sub_bbox[0]
        sub_h = sub_bbox[3] - sub_bbox[1]

    # 底条高度
    padding = int(title_size * 0.6)
    bar_h = title_h + sub_h + padding * 2
    bar_y = h - bar_h - int(h * 0.08)  # 距底部 8%

    # 画半透明底条
    draw.rectangle([0, bar_y, w, bar_y + bar_h], fill=(0, 0, 0, 140))

    # 标题位置（居中）
    title_x = (w - title_w) // 2
    title_y = bar_y + padding

    # 文字阴影
    shadow_offset = max(2, title_size // 20)
    draw.text((title_x + shadow_offset, title_y + shadow_offset), title,
              font=title_font, fill=(0, 0, 0, 200))
    # 主标题
    draw.text((title_x, title_y), title, font=title_font, fill=(255, 255, 255, 255))

    # 副标题
    if subtitle:
        sub_x = (w - sub_w) // 2
        sub_y = title_y + title_h + int(padding * 0.4)
        draw.text((sub_x, sub_y), subtitle, font=sub_font, fill=(220, 220, 220, 230))

    return img


def resize_keep_content(img, target_w, target_h):
    """
    改变比例：直接拉伸改尺寸，不裁剪、不填充。
    图片内容完整保留，仅修改宽高像素（会有变形，但内容不丢失）。
    """
    return img.resize((target_w, target_h), Image.LANCZOS)


def make_covers(base_image_path, title, subtitle=None, output_dir=None):
    """
    主流程：
    1. 读取基础封面图
    2. 叠加标题
    3. 按 4 种比例输出
    """
    if not os.path.exists(base_image_path):
        print(f"[ERROR] 基础图不存在: {base_image_path}")
        sys.exit(1)

    base_img = Image.open(base_image_path).convert("RGB")
    print(f"基础图: {base_img.width}x{base_img.height}")

    # 步骤1：加标题
    print(f"叠加标题: {title}")
    titled_img = add_title_to_image(base_img, title, subtitle)

    # 输出目录
    if output_dir is None:
        output_dir = os.path.dirname(base_image_path)
    os.makedirs(output_dir, exist_ok=True)

    # 保存带标题的中间图（16:9 原版）
    original_path = os.path.join(output_dir, "cover_titled_16x9.jpg")
    titled_img.save(original_path, "JPEG", quality=92)
    print(f"  16:9 (带标题): {original_path}")

    # 步骤2：按4种比例输出
    results = {}
    for name, (rw, rh) in RATIOS.items():
        # 计算目标尺寸（短边 BASE_SIZE）
        if rw >= rh:
            target_h = BASE_SIZE
            target_w = int(BASE_SIZE * rw / rh)
        else:
            target_w = BASE_SIZE
            target_h = int(BASE_SIZE * rh / rw)

        resized = resize_keep_content(titled_img, target_w, target_h)
        out_path = os.path.join(output_dir, f"cover_{name}.jpg")
        resized.save(out_path, "JPEG", quality=92)
        results[name] = out_path
        print(f"  {rw}:{rh} ({target_w}x{target_h}): {out_path}")

    print(f"\n完成！共生成 {len(results) + 1} 张封面（含16:9原版）")
    return results


def main():
    parser = argparse.ArgumentParser(description="QingFeng-Cover 多比例封面制作")
    parser.add_argument("--base", required=True, help="基础封面图路径（QingFeng-PB 生成的 cover.jpg）")
    parser.add_argument("--title", required=True, help="封面标题文字")
    parser.add_argument("--subtitle", default=None, help="副标题（可选）")
    parser.add_argument("--outdir", default=None, help="输出目录（默认与基础图同目录）")
    args = parser.parse_args()

    make_covers(args.base, args.title, args.subtitle, args.outdir)


if __name__ == "__main__":
    main()
