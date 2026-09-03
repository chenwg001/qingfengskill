#!/usr/bin/env python3
"""
通用视频发布脚本 v3 - CDP 连接模式
先让用户手动登录并导航到发布页面，然后脚本接管
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

CDP_URL = "http://127.0.0.1:9222"

def parse_args():
    parser = argparse.ArgumentParser(description='通用视频发布脚本（CDP模式）')
    parser.add_argument('--config', type=str, help='配置文件路径')
    parser.add_argument('--video', type=str, help='视频文件路径')
    parser.add_argument('--cover-4x3', type=str, help='横屏封面路径')
    parser.add_argument('--cover-3x4', type=str, help='竖屏封面路径')
    parser.add_argument('--title', type=str, default='', help='标题')
    parser.add_argument('--description', type=str, default='', help='简介')
    parser.add_argument('--ai-declaration', type=str, help='AI声明')
    return parser.parse_args()

def main():
    args = parse_args()
    
    # 加载配置（如果提供）
    if args.config:
        with open(args.config, 'r', encoding='utf-8') as f:
            config = json.load(f)
    else:
        config = {
            'video_path': args.video,
            'title': args.title,
            'description': args.description,
            'ai_declaration': args.ai_declaration,
        }
    
    video_path = config.get('video_path') or args.video
    cover_4x3 = config.get('cover_4x3') or args.cover_4x3
    cover_3x4 = config.get('cover_3x4') or args.cover_3x4
    
    if not video_path or not os.path.exists(video_path):
        print(f"❌ 视频文件不存在: {video_path}")
        sys.exit(1)
    
    print("="*60)
    print("通用视频发布脚本 v3 - CDP 连接模式")
    print("="*60)
    print(f"\n📹 视频: {video_path}")
    print(f"📊 大小: {os.path.getsize(video_path) / (1024*1024):.1f} MB")
    
    # 连接 CDP
    print(f"\n🔗 连接到 CDP: {CDP_URL}")
    print("请确保：")
    print("  1. 浏览器已启动并开启远程调试（--remote-debugging-port=9222）")
    print("  2. 已手动登录抖音创作者中心")
    print("  3. 已导航到发布页面")
    print("\n等待 10 秒，让您可以切换到浏览器窗口...")
    time.sleep(10)
    
    from playwright.sync_api import sync_playwright
    
    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp(CDP_URL)
            print("✅ 已连接到浏览器")
        except Exception as e:
            print(f"❌ 连接 CDP 失败: {e}")
            print("\n请确保浏览器已启动并开启远程调试：")
            print('  "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" --remote-debugging-port=9222')
            sys.exit(1)
        
        # 获取现有页面或创建新页面
        contexts = browser.contexts
        if contexts:
            context = contexts[0]
        else:
            context = browser.new_context()
        
        pages = context.pages
        if pages:
            page = pages[0]
        else:
            page = context.new_page()
        
        print(f"\n🌐 当前页面: {page.url}")
        print("请确保此页面是抖音创作者中心发布页面（https://creator.douyin.com/creator-micro/content/post/video）")
        time.sleep(3)
        
        # 执行上传
        print("\n" + "="*50)
        print("开始操作...")
        print("="*50)
        
        # 关闭弹窗
        print("\n🧹 关闭弹窗...")
        for _ in range(5):
            try:
                page.keyboard.press("Escape")
                time.sleep(0.5)
            except:
                pass
        
        time.sleep(2)
        
        # 上传视频
        print("\n📤 步骤1: 上传视频...")
        try:
            # 查找上传区域
            upload_area = page.locator('text=/上传视频|点击上传|选择文件/').first
            if upload_area.is_visible(timeout=3000):
                print("  ✅ 找到上传区域，点击...")
                upload_area.click()
                time.sleep(2)
            
            # 设置视频文件
            file_inputs = page.locator('input[type="file"]')
            if file_inputs.count() > 0:
                print(f"  ✅ 找到文件输入，设置视频...")
                file_inputs.first.set_input_files(video_path)
                print(f"  ✅ 视频文件已设置: {video_path}")
                print("  ⏳ 等待视频上传...")
                time.sleep(10)
            else:
                print("  ❌ 未找到文件上传输入！")
                print("  请手动点击上传区域，然后重新运行脚本")
        except Exception as e:
            print(f"  ⚠️ 上传视频异常: {e}")
        
        # 上传封面
        if cover_4x3 and cover_3x4:
            print("\n🖼️ 步骤2: 上传封面...")
            try:
                img_inputs = page.locator('input[accept*="image"]')
                count = img_inputs.count()
                print(f"  找到 {count} 个图片上传输入")
                
                if count >= 1:
                    img_inputs.first.set_input_files(cover_4x3)
                    print(f"  ✅ 横屏封面已上传")
                    time.sleep(2)
                
                if count >= 2:
                    img_inputs.nth(1).set_input_files(cover_3x4)
                    print(f"  ✅ 竖屏封面已上传")
                    time.sleep(2)
            except Exception as e:
                print(f"  ⚠️ 上传封面异常: {e}")
        
        # 填写标题和简介
        if config.get('title'):
            print("\n✏️ 步骤3: 填写标题...")
            try:
                title_input = page.locator('input[placeholder*="标题"]').first
                title_input.fill(config['title'])
                print(f"  ✅ 标题已填写: {config['title']}")
            except Exception as e:
                print(f"  ⚠️ 填写标题异常: {e}")
        
        # 保持连接
        print("\n✅ 操作完成！")
        print("浏览器保持打开，您可以继续操作或手动点击发布。")
        print("\n按 Ctrl+C 退出脚本...")
        
        try:
            while True:
                time.sleep(10)
        except KeyboardInterrupt:
            print("\n👋 退出")
        # 不关闭浏览器（CDP 连接模式，只是断开连接）
        browser.close()

if __name__ == "__main__":
    main()
