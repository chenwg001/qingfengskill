#!/usr/bin/env python3
"""
创建封面图片的4:3和3:4比例副本

重要：通过缩放调整比例，不改变图片内容！
- 将图片缩放到目标比例（4:3 或 3:4）
- 保持图片内容完整，不裁剪，不加黑边

用法:
    python create_cover_copies.py <图片路径或文件夹路径>

示例:
    python create_cover_copies.py "D:/个人/资源/个人文章/AI育见/2.3/2.3-封面.jpg"
    python create_cover_copies.py "D:/个人/资源/个人文章/AI育见/2.3"
"""

import sys
import os
from pathlib import Path

# 自动安装依赖
import subprocess
try:
    from PIL import Image
except ImportError:
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'Pillow', '-q'])
    from PIL import Image


def create_copies(image_path: Path):
    """为单张图片创建4:3和3:4副本，通过缩放调整比例"""
    if not image_path.exists():
        print(f"Error: File not found {image_path}")
        return False
    
    # 检查是否为图片
    valid_extensions = {'.jpg', '.jpeg', '.png', '.webp', '.bmp'}
    if image_path.suffix.lower() not in valid_extensions:
        print(f"Skip non-image file: {image_path}")
        return False
    
    # 检查是否已有副本
    stem = image_path.stem
    if stem.endswith('_4x3') or stem.endswith('_3x4'):
        print(f"Skip existing copy: {image_path.name}")
        return True
    
    try:
        img = Image.open(image_path)
        # 确保是RGB模式
        if img.mode != 'RGB':
            img = img.convert('RGB')
        
        w, h = img.size
        
        # ===== 创建4:3横版 =====
        # 4:3比例：宽度/高度 = 4/3 ≈ 1.333
        # 保持高度不变，调整宽度
        target_h_4x3 = h
        target_w_4x3 = int(h * 4 / 3)
        
        # 缩放图片
        img_4x3 = img.resize((target_w_4x3, target_h_4x3), Image.Resampling.LANCZOS)
        path_4x3 = image_path.parent / f"{stem}_4x3{image_path.suffix}"
        img_4x3.save(path_4x3, quality=95)
        print(f"[OK] Created 4:3: {path_4x3.name} ({target_w_4x3}x{target_h_4x3}) - scaled from {w}x{h}")
        
        # ===== 创建3:4竖版 =====
        # 固定尺寸 2880×3840（3:4 比例）
        target_w_3x4 = 2880
        target_h_3x4 = 3840
        
        # 缩放图片到固定尺寸
        img_3x4 = img.resize((target_w_3x4, target_h_3x4), Image.Resampling.LANCZOS)
        
        path_3x4 = image_path.parent / f"{stem}_3x4{image_path.suffix}"
        img_3x4.save(path_3x4, quality=95)
        print(f"[OK] Created 3:4: {path_3x4.name} ({target_w_3x4}x{target_h_3x4}) - scaled from {w}x{h}")
        
        img.close()
        return True
        
    except Exception as e:
        print(f"Failed to process image {image_path}: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    
    input_path = Path(sys.argv[1])
    
    if input_path.is_file():
        # 单个文件
        create_copies(input_path)
    elif input_path.is_dir():
        # 文件夹，处理其中的封面图片
        print(f"Processing folder: {input_path}")
        valid_extensions = {'.jpg', '.jpeg', '.png', '.webp', '.bmp'}
        count = 0
        for ext in valid_extensions:
            for f in input_path.glob(f'*{ext}'):
                if '_4x3' not in f.stem and '_3x4' not in f.stem:
                    if '封面' in f.name or 'cover' in f.name.lower():
                        create_copies(f)
                        count += 1
        if count == 0:
            print("No cover image found (filename must contain 'cover' or Chinese 'fengmian')")
    else:
        print(f"Error: Path not found {input_path}")
        sys.exit(1)


if __name__ == '__main__':
    main()
