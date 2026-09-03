#!/usr/bin/env python3
"""
通用视频发布脚本 - 支持多平台
使用方法：
  python publish_video.py --config config.json
  python publish_video.py --video VIDEO_PATH --platform douyin [options]
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description='通用视频发布脚本')
    
    # 配置文件模式
    parser.add_argument('--config', type=str, help='配置文件路径 (JSON)')
    
    # 命令行参数模式
    parser.add_argument('--video', type=str, help='视频文件路径')
    parser.add_argument('--platform', type=str, choices=['douyin', 'kuaishou', 'baijiahao'], 
                        help='发布平台')
    parser.add_argument('--title', type=str, default='', help='视频标题')
    parser.add_argument('--description', type=str, default='', help='视频简介')
    parser.add_argument('--tags', type=str, nargs='+', help='标签列表')
    parser.add_argument('--cover-source', type=str, help='封面源图片路径')
    parser.add_argument('--ai-declaration', type=str, help='AI声明内容')
    parser.add_argument('--output-dir', type=str, help='输出目录（封面生成位置）')
    
    return parser.parse_args()

def load_config(config_path):
    """加载配置文件"""
    if not os.path.exists(config_path):
        print(f"❌ 配置文件不存在: {config_path}")
        sys.exit(1)
    
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    return config

def ensure_covers(video_path, cover_source, output_dir):
    """
    确保封面图片存在，如不存在则生成
    返回: (cover_4x3_path, cover_3x4_path)
    """
    if not output_dir:
        output_dir = os.path.dirname(video_path) or '.'
    
    base_name = os.path.splitext(os.path.basename(video_path))[0]
    cover_4x3 = os.path.join(output_dir, f"{base_name}_cover_4x3.jpg")
    cover_3x4 = os.path.join(output_dir, f"{base_name}_cover_3x4.jpg")
    
    # 如果封面已存在，直接返回
    if os.path.exists(cover_4x3) and os.path.exists(cover_3x4):
        print(f"✅ 封面已存在: {cover_4x3}, {cover_3x4}")
        return cover_4x3, cover_3x4
    
    # 需要生成封面
    if not cover_source:
        print("❌ 封面不存在且未提供封面源图片 (--cover-source)")
        sys.exit(1)
    
    if not os.path.exists(cover_source):
        print(f"❌ 封面源图片不存在: {cover_source}")
        sys.exit(1)
    
    print(f"🎨 生成封面图片...")
    print(f"   源图片: {cover_source}")
    print(f"   输出目录: {output_dir}")
    
    # 调用 make_cover.py 生成封面
    make_cover_script = os.path.join(os.path.dirname(__file__), 'make_cover.py')
    
    if not os.path.exists(make_cover_script):
        print(f"❌ 找不到封面生成脚本: {make_cover_script}")
        sys.exit(1)
    
    import subprocess
    
    # 生成横屏封面 (4:3)
    cmd_4x3 = [
        sys.executable, make_cover_script,
        '--source', cover_source,
        '--output', cover_4x3,
        '--ratio', '4:3'
    ]
    
    # 生成竖屏封面 (3:4)
    cmd_3x4 = [
        sys.executable, make_cover_script,
        '--source', cover_source,
        '--output', cover_3x4,
        '--ratio', '3:4'
    ]
    
    try:
        subprocess.run(cmd_4x3, check=True)
        subprocess.run(cmd_3x4, check=True)
        print(f"✅ 封面生成成功: {cover_4x3}, {cover_3x4}")
    except subprocess.CalledProcessError as e:
        print(f"❌ 封面生成失败: {e}")
        sys.exit(1)
    
    return cover_4x3, cover_3x4

def get_browser_path():
    """获取本机浏览器路径"""
    paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    ]
    
    for path in paths:
        if os.path.exists(path):
            print(f"✅ 找到浏览器: {path}")
            return path
    
    print("❌ 未安装 Chrome 或 Edge 浏览器")
    sys.exit(1)

def get_edge_user_data_dir():
    """获取 Edge 用户数据目录（包含登录状态）"""
    # Edge 用户数据目录通常在这里
    edge_data_dir = os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\User Data")
    if os.path.exists(edge_data_dir):
        return edge_data_dir
    
    # 备用位置
    edge_data_dir = os.path.expandvars(r"%APPDATA%\..\Local\Microsoft\Edge\User Data")
    if os.path.exists(edge_data_dir):
        return edge_data_dir
    
    return None

def publish_to_douyin(video_path, cover_4x3, cover_3x4, config):
    """发布到抖音"""
    from playwright.sync_api import sync_playwright
    
    print("\n" + "="*50)
    print("开始发布到抖音")
    print("="*50)
    
    browser_path = get_browser_path()
    user_data_dir = get_edge_user_data_dir()
    
    with sync_playwright() as p:
        print(f"🚀 启动本地浏览器（复用登录状态）...")
        
        # 使用 launch_persistent_context 来使用用户数据目录
        context = p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            executable_path=browser_path,
            headless=False,
            slow_mo=1000,
            viewport={"width": 1440, "height": 900},
        )
        
        page = context.pages[0] if context.pages else context.new_page()
        
        # 打开抖音创作者中心
        print("\n🌐 正在打开抖音创作者中心...")
        page.goto("https://creator.douyin.com/creator-micro/content/post/video", 
                  wait_until="networkidle", timeout=60000)
        time.sleep(5)  # 等待页面完全稳定
        
        # 截图1：初始页面
        screenshot(page, "01_initial_page.png")
        
        # 检查登录
        if "login" in page.url or "passport" in page.url:
            print("\n⚠️ 需要登录！请在浏览器中手动完成登录")
            print("登录完成后，脚本将继续...")
            try:
                page.wait_for_url("**/creator-micro/**", timeout=180000)
                print("✅ 登录成功！")
                time.sleep(3)
            except:
                print("⚠️ 等待登录超时，继续尝试...")
        
        # 关闭弹窗（多次尝试）
        print("\n🧹 清理弹窗和遮罩...")
        for i in range(3):
            close_popups(page)
            time.sleep(1)
        
        # 截图2：清理后
        screenshot(page, "02_after_cleanup.png")
        
        # 等待页面完全加载
        print("\n⏳ 等待页面加载完成...")
        page.wait_for_load_state("networkidle")
        time.sleep(3)
        
        # 上传视频
        print("\n📤 上传视频...")
        upload_video(page, video_path)
        
        # 上传封面
        print("\n🖼️ 上传封面...")
        upload_covers(page, cover_4x3, cover_3x4)
        
        # 填写标题和简介
        if config.get('title') or config.get('description'):
            print("\n✏️ 填写标题和简介...")
            fill_title_description(page, config.get('title', ''), config.get('description', ''))
        
        # 填写AI声明
        if config.get('ai_declaration'):
            print("\n🤖 填写AI声明...")
            fill_ai_declaration(page, config['ai_declaration'])
        
        # 截图最终状态
        screenshot(page, "99_final.png")
        
        # 保持浏览器打开
        print("\n✅ 所有步骤执行完成！")
        print("请检查浏览器界面，确认所有信息无误后，手动点击「发布」按钮。")
        print("\n浏览器将保持打开状态。")
        print("关闭浏览器窗口后，程序会自动退出。")
        
        try:
            page.wait_for_event("close", timeout=600000)
        except:
            pass
        
        context.close()

def upload_video(page, video_path):
    """上传视频文件 - 改进版本，更可靠"""
    print(f"   视频路径: {video_path}")
    
    # 等待页面稳定
    page.wait_for_load_state("networkidle")
    time.sleep(3)
    screenshot(page, "upload_video_start.png")
    
    # 方法1：直接查找文件上传输入
    print("   方法1：查找文件上传输入...")
    file_inputs = page.locator('input[type="file"]')
    count = file_inputs.count()
    print(f"   找到 {count} 个文件上传输入")
    
    if count > 0:
        print(f"   ✅ 找到文件输入，设置视频文件...")
        try:
            file_inputs.first.set_input_files(video_path)
            print(f"   ✅ 视频文件已设置: {video_path}")
            
            # 等待上传开始
            time.sleep(5)
            screenshot(page, "upload_video_progress.png")
            
            # 等待上传完成
            print("   ⏳ 等待视频上传完成...")
            try:
                page.wait_for_selector('text=/上传成功|上传完成/', timeout=600000)
                print("   ✅ 视频上传成功！")
            except:
                print("   ⚠️ 未检测到「上传成功」提示，但文件已提交")
                print("   请检查浏览器确认上传状态...")
            return
        except Exception as e:
            print(f"   ⚠️ 方法1失败: {e}")
    
    # 方法2：点击上传区域，然后查找文件输入
    print("   方法2：点击上传区域...")
    try:
        # 尝试点击包含"上传"文本的元素
        upload_area = page.locator('text=/上传视频|点击上传|选择文件/').first
        if upload_area.is_visible(timeout=2000):
            upload_area.click()
            print("   ✅ 已点击上传区域")
            time.sleep(2)
            
            # 再次查找文件输入
            file_inputs = page.locator('input[type="file"]')
            count = file_inputs.count()
            print(f"   重新查找：找到 {count} 个文件上传输入")
            
            if count > 0:
                file_inputs.first.set_input_files(video_path)
                print(f"   ✅ 视频文件已设置（方法2）: {video_path}")
                time.sleep(5)
                return
    except Exception as e:
        print(f"   ⚠️ 方法2失败: {e}")
    
    # 方法3：查找并点击"高清发布"按钮
    print("   方法3：点击「高清发布」...")
    try:
        hd_btn = page.locator('text=高清发布').first
        if hd_btn.is_visible(timeout=2000):
            hd_btn.click()
            print("   ✅ 已点击「高清发布」")
            time.sleep(3)
            screenshot(page, "after_hd_publish.png")
            
            # 再次查找文件输入
            file_inputs = page.locator('input[type="file"]')
            count = file_inputs.count()
            
            if count > 0:
                file_inputs.first.set_input_files(video_path)
                print(f"   ✅ 视频文件已设置（方法3）: {video_path}")
                time.sleep(5)
                return
    except Exception as e:
        print(f"   ⚠️ 方法3失败: {e}")
    
    # 所有方法都失败
    print("   ❌ 所有上传方法都失败了！")
    screenshot(page, "upload_video_failed.png")
    print("   请检查浏览器，可能需要手动上传视频")

def upload_covers(page, cover_4x3, cover_3x4):
    """上传封面图片 - 改进版本"""
    print(f"   横屏封面: {cover_4x3}")
    print(f"   竖屏封面: {cover_3x4}")
    
    # 等待页面稳定
    page.wait_for_load_state("networkidle")
    time.sleep(3)
    screenshot(page, "upload_cover_start.png")
    
    # 方法1：直接查找图片上传输入
    print("   方法1：查找图片上传输入...")
    img_inputs = page.locator('input[accept*="image"]')
    count = img_inputs.count()
    print(f"   找到 {count} 个图片上传输入")
    
    if count >= 1:
        try:
            img_inputs.first.set_input_files(cover_4x3)
            print(f"   ✅ 横屏封面已上传（方法1）")
            time.sleep(3)
            screenshot(page, "after_cover1.png")
        except Exception as e:
            print(f"   ⚠️ 上传横屏封面失败: {e}")
    
    if count >= 2:
        try:
            img_inputs.nth(1).set_input_files(cover_3x4)
            print(f"   ✅ 竖屏封面已上传（方法1）")
            time.sleep(3)
            screenshot(page, "after_cover2.png")
            return
        except Exception as e:
            print(f"   ⚠️ 上传竖屏封面失败: {e}")
    elif count == 1:
        # 只有一个输入，可能需要切换标签
        print("   ⚠️ 只有1个图片上传输入，尝试切换竖屏标签...")
        try:
            vertical_tab = page.locator('text=/竖屏|3:4/').first
            if vertical_tab.is_visible(timeout=2000):
                vertical_tab.click()
                time.sleep(1)
                # 重新查找输入
                img_inputs = page.locator('input[accept*="image"]')
                img_inputs.last.set_input_files(cover_3x4)
                print(f"   ✅ 竖屏封面已上传（切换标签后）")
                time.sleep(3)
                return
        except:
            pass
    
    # 方法2：点击封面上传区域，然后查找输入
    print("   方法2：点击封面上传区域...")
    try:
        # 查找包含"封面"关键词的区域
        cover_area = page.locator('text=/封面|上传封面/').first
        if cover_area.is_visible(timeout=2000):
            cover_area.click()
            print("   ✅ 已点击封面上传区域")
            time.sleep(2)
            screenshot(page, "after_cover_click.png")
            
            # 重新查找图片输入
            img_inputs = page.locator('input[accept*="image"]')
            count = img_inputs.count()
            print(f"   重新查找：找到 {count} 个图片上传输入")
            
            if count >= 1:
                img_inputs.first.set_input_files(cover_4x3)
                print(f"   ✅ 横屏封面已上传（方法2）")
                time.sleep(3)
            
            if count >= 2:
                img_inputs.nth(1).set_input_files(cover_3x4)
                print(f"   ✅ 竖屏封面已上传（方法2）")
                time.sleep(3)
                return
    except Exception as e:
        print(f"   ⚠️ 方法2失败: {e}")
    
    # 方法3：滚动到页面底部，查找所有上传区域
    print("   方法3：滚动查找上传区域...")
    try:
        page.keyboard.press("End")
        time.sleep(1)
        screenshot(page, "after_scroll_end.png")
        
        img_inputs = page.locator('input[accept*="image"]')
        count = img_inputs.count()
        
        if count >= 1:
            img_inputs.first.set_input_files(cover_4x3)
            print(f"   ✅ 横屏封面已上传（方法3）")
            time.sleep(3)
        
        if count >= 2:
            img_inputs.nth(1).set_input_files(cover_3x4)
            print(f"   ✅ 竖屏封面已上传（方法3）")
            return
    except Exception as e:
        print(f"   ⚠️ 方法3失败: {e}")
    
    # 所有方法都失败
    print("   ❌ 所有封面上传方法都失败了！")
    screenshot(page, "upload_cover_failed.png")
    print("   请检查浏览器，可能需要手动上传封面")

def fill_title_description(page, title, description):
    """填写标题和简介"""
    if title:
        try:
            title_input = page.locator('input[placeholder*="标题"], textarea[placeholder*="标题"]').first
            title_input.fill(title)
            print(f"✅ 标题已填写: {title}")
        except:
            print("⚠️ 未找到标题输入框")
    
    if description:
        try:
            desc_input = page.locator('textarea[placeholder*="简介"], textarea[placeholder*="描述"]').first
            desc_input.fill(description)
            print(f"✅ 简介已填写")
        except:
            print("⚠️ 未找到简介输入框")

def fill_ai_declaration(page, declaration):
    """填写AI声明"""
    try:
        # 查找AI声明复选框
        ai_checkbox = page.locator('text=/AI生成|AI声明/').first
        if ai_checkbox.is_visible():
            ai_checkbox.click()
            time.sleep(1)
            
            # 填写声明内容
            ai_textarea = page.locator('textarea[placeholder*="AI"], textarea[placeholder*="声明"]').first
            if ai_textarea.is_visible():
                ai_textarea.fill(declaration)
                print(f"✅ AI声明已填写: {declaration}")
            else:
                print("⚠️ 未找到AI声明输入框")
        else:
            print("⚠️ 未找到AI声明选项")
    except Exception as e:
        print(f"⚠️ 填写AI声明异常: {e}")

def close_popups(page):
    """关闭弹窗/引导层"""
    try:
        page.keyboard.press("Escape")
        time.sleep(0.5)
    except:
        pass

def screenshot(page, filename):
    """截图辅助函数"""
    try:
        ss_dir = r"D:\个人\资源\个人文章\AI育见\5.1"
        os.makedirs(ss_dir, exist_ok=True)
        path = os.path.join(ss_dir, filename)
        page.screenshot(path=path)
        print(f"  📸 截图: {filename}")
    except:
        pass

def main():
    args = parse_args()
    
    # 加载配置
    if args.config:
        config = load_config(args.config)
    else:
        # 从命令行参数构建配置
        if not args.video or not args.platform:
            print("❌ 使用命令行模式需要提供 --video 和 --platform")
            sys.exit(1)
        
        config = {
            'video_path': args.video,
            'platform': args.platform,
            'title': args.title or '',
            'description': args.description or '',
            'tags': args.tags or [],
            'ai_declaration': args.ai_declaration or '',
            'cover_source': args.cover_source or '',
            'output_dir': args.output_dir or '',
        }
    
    # 验证视频文件
    video_path = config.get('video_path')
    if not video_path or not os.path.exists(video_path):
        print(f"❌ 视频文件不存在: {video_path}")
        sys.exit(1)
    
    print(f"📹 视频文件: {video_path}")
    print(f"📊 文件大小: {os.path.getsize(video_path) / (1024*1024):.1f} MB")
    
    # 确保封面存在
    cover_4x3, cover_3x4 = ensure_covers(
        video_path,
        config.get('cover_source', ''),
        config.get('output_dir', '')
    )
    
    # 根据平台执行发布
    platform = config.get('platform', 'douyin')
    
    if platform == 'douyin':
        publish_to_douyin(video_path, cover_4x3, cover_3x4, config)
    elif platform == 'kuaishou':
        print("⚠️ 快手平台支持正在开发中...")
        # TODO: implement publish_to_kuaishou
    elif platform == 'baijiahao':
        print("⚠️ 百家号平台支持正在开发中...")
        # TODO: implement publish_to_baijiahao
    else:
        print(f"❌ 不支持的平台: {platform}")
        sys.exit(1)
    
    print("\n✅ 发布任务完成！")

if __name__ == "__main__":
    main()
