#!/usr/bin/env python3
"""
封面生成脚本 - 通用版本
从源图片生成 4:3 横屏和 3:4 竖屏封面

使用方法：
  python make_cover.py --source 源图片.jpg --output 输出图片.jpg --ratio 4:3
  python make_cover.py --source 源图片.jpg --output-dir 输出目录
"""

import argparse
import os
import sys
from PIL import Image

def parse_args():
    parser = argparse.ArgumentParser(description='封面生成脚本')
    parser.add_argument('--source', type=str, required=True, help='源图片路径')
    parser.add_argument('--output', type=str, help='输出文件路径（使用 --ratio 时）')
    parser.add_argument('--output-dir', type=str, help='输出目录（生成两种比例）')
    parser.add_argument('--ratio', type=str, choices=['4:3', '3:4'], help='封面比例')
    return parser.parse_args()

def make_cover(source_path, output_path, target_ratio):
    """
    从源图片生成指定比例的封面
    保持原图不裁剪，添加填充到目标比例
    """
    if not os.path.exists(source_path):
        print(f"❌ 源图片不存在: {source_path}")
        sys.exit(1)
    
    # 打开源图片
    img = Image.open(source_path)
    orig_width, orig_height = img.size
    print(f"📷 源图片: {orig_width}x{orig_height}")
    
    # 计算目标尺寸
    if target_ratio == '4:3':
        # 横屏 4:3
        if orig_width / orig_height > 4/3:
            # 图片更宽，以高度为基准
            new_height = orig_height
            new_width = int(new_height * 4 / 3)
        else:
            # 图片更高，以宽度为基准
            new_width = orig_width
            new_height = int(new_width * 3 / 4)
    elif target_ratio == '3:4':
        # 竖屏 3:4
        if orig_width / orig_height > 3/4:
            # 图片更宽，以高度为基准
            new_height = orig_height
            new_width = int(new_height * 3 / 4)
        else:
            # 图片更高，以宽度为基准
            new_width = orig_width
            new_height = int(new_width * 4 / 3)
    
    print(f"📐 目标尺寸: {new_width}x{new_height} ({target_ratio})")
    
    # 创建新画布（白色背景）
    canvas = Image.new('RGB', (new_width, new_height), (255, 255, 255))
    
    # 计算粘贴位置（居中）
    paste_x = (new_width - orig_width) // 2
    paste_y = (new_height - orig_height) // 2
    
    # 粘贴原图
    canvas.paste(img, (paste_x, paste_y))
    
    # 保存
    canvas.save(output_path, 'JPEG', quality=95)
    print(f"✅ 封面已生成: {output_path}")
    
    return output_path

def main():
    args = parse_args()
    
    source = args.source
    
    if args.output_dir:
        # 生成两种比例
        os.makedirs(args.output_dir, exist_ok=True)
        base_name = os.path.splitext(os.path.basename(source))[0]
        
        # 4:3 横屏
        output_4x3 = os.path.join(args.output_dir, f"{base_name}_cover_4x3.jpg")
        make_cover(source, output_4x3, '4:3')
        
        # 3:4 竖屏
        output_3x4 = os.path.join(args.output_dir, f"{base_name}_cover_3x4.jpg")
        make_cover(source, output_3x4, '3:4')
        
        print(f"\n✅ 两种封面已生成:")
        print(f"   横屏 (4:3): {output_4x3}")
        print(f"   竖屏 (3:4): {output_3x4}")
    else:
        # 生成单一比例
        if not args.output or not args.ratio:
            print("❌ 使用 --output 时必须同时指定 --ratio")
            sys.exit(1)
        
        make_cover(source, args.output, args.ratio)

if __name__ == "__main__":
    main()
