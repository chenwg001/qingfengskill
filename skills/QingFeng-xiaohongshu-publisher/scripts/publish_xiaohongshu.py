# -*- coding: utf-8 -*-
"""
小红书发布脚本 v3
- 自动切换到"上传图文"模式
- 先传3:4封面图，再传插图
- 逐张上传（小红书不支持多文件input）
- 脚本结束/异常时保持浏览器打开（铁律：禁止调用 p.stop()）
"""
import argparse
import os
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

from playwright.sync_api import sync_playwright

CDP_PORT = 9222
PUBLISH_URL = "https://creator.xiaohongshu.com/publish/publish"


def parse_xhs_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    if not lines:
        return "", ""
    title = lines[0].strip()
    import re
    title = re.sub(r'^[^\w\u4e00-\u9fa5]+', '', title).strip()
    body = ''.join(lines[1:]).strip()
    return title, body


def find_images(images_dir, cover_path=None):
    """先封面图，后插图"""
    images = []
    if cover_path and os.path.exists(cover_path):
        images.append(cover_path)
        print(f"  Cover: {os.path.basename(cover_path)}")
    for f in sorted(Path(images_dir).glob('illustration_*.jpg')):
        images.append(str(f))
    for f in sorted(Path(images_dir).glob('illustration_*.png')):
        images.append(str(f))
    return images


def safe_exit(code=0):
    """铁律：退出时不关闭浏览器"""
    try:
        os._exit(code)
    except Exception:
        pass


def main():
    parser = argparse.ArgumentParser(description='小红书发布')
    parser.add_argument('file', help='小红书排版txt文件路径')
    parser.add_argument('--images-dir', help='配图目录')
    parser.add_argument('--cover', help='封面图路径（3:4）', default=None)
    args = parser.parse_args()

    filepath = os.path.abspath(args.file)
    if not os.path.exists(filepath):
        print(f"ERROR: File not found: {filepath}")
        safe_exit(1)

    title, body = parse_xhs_file(filepath)
    print(f"Title: {title}")
    print(f"Body length: {len(body)} chars")

    images_dir = args.images_dir or os.path.join(os.path.dirname(filepath), '..', 'pb')
    images = find_images(images_dir, args.cover)
    print(f"Found {len(images)} images (cover + illustrations):")
    for img in images:
        print(f"  {os.path.basename(img)}")

    # 铁律：手动管理playwright，禁止用with，禁止调用p.stop()
    p = None
    try:
        p = sync_playwright().start()
        print(f"\nConnecting to CDP port {CDP_PORT}...")
        browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{CDP_PORT}")
        context = browser.contexts[0]

        # 找已有发布页面或新建
        page = None
        for pg in context.pages:
            if 'xiaohongshu.com' in pg.url and 'publish' in pg.url:
                page = pg
                break

        if page is None:
            print(f"Navigating to {PUBLISH_URL}...")
            page = context.new_page()
            page.goto(PUBLISH_URL, wait_until='domcontentloaded', timeout=30000)
            time.sleep(5)

        page.bring_to_front()
        print(f"Current URL: {page.url}")

        # Step 0: 切换到图文模式
        print("\n=== Step 0: Switch to 上传图文 ===")
        time.sleep(2)
        clicked = page.evaluate("""() => {
            for (const el of document.querySelectorAll('.creator-tab')) {
                if (el.textContent.trim() === '上传图文') { el.click(); return true; }
            }
            return false;
        }""")
        if clicked:
            print("  Clicked 上传图文 tab")
            time.sleep(4)
        else:
            print("  WARNING: 上传图文 tab not found")

        # Step 1: 逐张上传图片（先封面后插图）
        print(f"\n=== Step 1: Upload {len(images)} Images ===")
        if images:
            file_input = page.query_selector('input[type="file"]')
            if file_input:
                for idx, img in enumerate(images):
                    file_input.set_input_files(img)
                    print(f"  [{idx+1}/{len(images)}] {os.path.basename(img)}")
                    time.sleep(4)
                time.sleep(5)
                print(f"  Total {len(images)} images uploaded")
            else:
                print("  WARNING: No file input found")

        # Step 2: 填写标题
        print(f"\n=== Step 2: Set Title ===")
        title_input = page.query_selector('input[placeholder*="标题"], textarea[placeholder*="标题"]')
        if title_input:
            title_input.fill(title)
            print(f"  Title set: {title}")
        else:
            print("  WARNING: Title input not found")

        # Step 3: 填写正文
        print(f"\n=== Step 3: Set Body ===")
        body_input = page.query_selector('textarea[placeholder*="正文"], [contenteditable="true"]')
        if body_input:
            if body_input.evaluate('el => el.tagName') == 'TEXTAREA':
                body_input.fill(body)
            else:
                body_input.click()
                page.keyboard.type(body, delay=10)
            print(f"  Body set: {len(body)} chars")
        else:
            print("  WARNING: Body input not found")

        time.sleep(2)

        # 先截图查看页面状态
        try:
            ts = time.strftime('%Y%m%d_%H%M%S')
            screenshot_path = os.path.join(os.getcwd(), f'xhs_before_save_{ts}.png')
            page.screenshot(path=screenshot_path, full_page=True)
            print(f"\nBefore-save screenshot: {screenshot_path}")
        except Exception as e:
            print(f"  Screenshot failed: {e}")

        # 滚动内部容器到底部（小红书内容在可滚动div内）
        page.evaluate("""() => {
            // 找到主内容滚动容器并滚动到底
            const containers = document.querySelectorAll('*');
            for (const el of containers) {
                if (el.scrollHeight > el.clientHeight + 100 && el.clientHeight > 300) {
                    el.scrollTop = el.scrollHeight;
                }
            }
            // 同时滚动窗口
            window.scrollTo(0, document.body.scrollHeight);
        }""")
        time.sleep(2)

        # Step 4: 保存草稿（暂存离开）
        print(f"\n=== Step 4: Save Draft (暂存离开) ===")
        # 先按ESC关闭可能的下拉菜单
        page.keyboard.press('Escape')
        time.sleep(1)
        # 用多种方式查找"暂存离开"按钮
        saved = page.evaluate("""() => {
            // 方式1：精确匹配
            for (const el of document.querySelectorAll('div, span, a, button')) {
                if (el.textContent.trim() === '暂存离开' && el.offsetParent !== null) {
                    el.click(); return 'exact';
                }
            }
            // 方式2：包含匹配
            for (const el of document.querySelectorAll('div, span, a, button')) {
                const text = el.textContent.trim();
                if (text.includes('暂存') && text.includes('离开') && el.offsetParent !== null) {
                    el.click(); return 'contains';
                }
            }
            return false;
        }""")
        if saved:
            print(f"  Saved draft (method={saved})")
            time.sleep(3)
        else:
            # 方式3：通过"发布"按钮位置计算"暂存离开"坐标（在发布按钮左边）
            print("  JS查找失败，用坐标点击...")
            pub_pos = page.evaluate("""() => {
                for (const el of document.querySelectorAll('div, span, a, button')) {
                    if (el.textContent.trim() === '发布' && el.offsetParent !== null) {
                        const r = el.getBoundingClientRect();
                        return {x: r.x + r.width/2, y: r.y + r.height/2, w: r.width, found: true};
                    }
                }
                return {found: false};
            }""")
            if pub_pos.get('found'):
                # "暂存离开"在"发布"按钮左边，间距约100px
                save_x = pub_pos['x'] - pub_pos['w']/2 - 60
                save_y = pub_pos['y']
                page.mouse.click(save_x, save_y)
                print(f"  Clicked 暂存离开 at ({save_x:.0f}, {save_y:.0f})")
                time.sleep(3)
            else:
                print("  WARNING: 发布按钮也没找到，无法定位暂存离开")

        # Step 5: 截图
        try:
            ts = time.strftime('%Y%m%d_%H%M%S')
            screenshot_path = os.path.join(os.getcwd(), f'xhs_publish_{ts}.png')
            page.screenshot(path=screenshot_path, full_page=True)
            print(f"\nScreenshot: {screenshot_path}")
        except Exception as e:
            print(f"  Screenshot failed: {e}")

        print(f"\n{'='*50}")
        print("DONE! Browser stays open.")
        print(f"{'='*50}")

    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        print("Browser stays open for manual inspection.")

    # 铁律：禁止调用 p.stop()，Python正常退出时浏览器保持打开


if __name__ == '__main__':
    main()
