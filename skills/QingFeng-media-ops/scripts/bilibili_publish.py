# -*- coding: utf-8 -*-
"""
B站视频发布（CDP，进草稿，绝不点发布）

用法:
  python bilibili_publish.py --title "标题(≤80字)" --desc 简介.txt --video 成片.mp4 \
      --cover 封面.png [--tags 教育,成长] [--port 9222] [--screenshot drafts/bilibili.png] [--ai-notice]

流程:
  1. playwright connect_over_cdp 连接 Chrome for Testing（端口默认 9222）
  2. 打开/复用创作中心投稿页（member.bilibili.com/platform/upload/video/frame）
  3. 未登录 -> 抛 NEED_HUMAN（退出码 42）
  4. 上传视频 -> 填标题 -> 填简介 -> 填标签 -> 传封面
  5. 点「保存草稿」；绝不点「立即投稿」
  6. 截图验证草稿保存成功

退出码: 0=成功进草稿  42=需人工(登录/验证码)  1=其他失败
"""
import argparse
import os
import sys
import time

sys.stdout.reconfigure(encoding='utf-8')

from playwright.sync_api import sync_playwright

DEFAULT_URL = 'https://member.bilibili.com/platform/upload/video/frame'
DEFAULT_PORT = 9222  # 统一 Chrome for Testing

# 选择器集中在此，平台改版只改这里
SELECTORS = {
    'video_input': 'input[type=file][accept*="video"], input[type=file]',
    'cover_input': 'input[type=file][accept*="image"]',
    'title': 'input[placeholder*="标题"], input[data-placeholder*="标题"], input.bili-input',
    'desc': '[contenteditable="true"], .ql-editor, textarea',
    'tags': 'input[placeholder*="标签"]',
    'save_draft': 'text=保存草稿',
    'submit_btn': 'text=立即投稿',
    'login_hint': 'text=登录',
}


def fill_input(page, selector, text):
    expr = """
    (text) => {
      const sels = arguments[0];
      let target = null;
      for (const sel of sels) {
        const el = document.querySelector(sel);
        if (el && el.offsetParent !== null) { target = el; break; }
      }
      if (!target) return 'NOT_FOUND';
      const proto = target.tagName === 'TEXTAREA' ? window.HTMLTextAreaElement.prototype
                  : target.isContentEditable ? window.HTMLElement.prototype
                  : window.HTMLInputElement.prototype;
      const setter = Object.getOwnPropertyDescriptor(proto, 'value').set;
      if (setter) { setter.call(target, text); } else { target.value = text; }
      target.dispatchEvent(new Event('input', {bubbles:true}));
      target.dispatchEvent(new Event('change', {bubbles:true}));
      target.dispatchEvent(new Event('blur', {bubbles:true}));
      return 'SET:' + String(target.value || target.innerText || '').slice(0,30);
    }
    """
    return page.evaluate(expr, selector, text)


def find_or_open_page(context, url_part):
    for p in context.pages:
        if url_part in p.url:
            return p, False
    p = context.new_page()
    p.goto(DEFAULT_URL, timeout=60000)
    p.wait_for_load_state('domcontentloaded')
    return p, True


def main():
    ap = argparse.ArgumentParser(description='B站视频发布（进草稿）')
    ap.add_argument('--title', required=True)
    ap.add_argument('--desc', required=True, help='简介 txt 文件路径')
    ap.add_argument('--video', required=True)
    ap.add_argument('--cover', default='')
    ap.add_argument('--tags', default='')
    ap.add_argument('--port', type=int, default=DEFAULT_PORT)
    ap.add_argument('--screenshot', default='')
    ap.add_argument('--ai-notice', action='store_true')
    args = ap.parse_args()

    for p in [args.desc, args.video]:
        if not os.path.exists(p):
            print(f'[FAIL] 文件不存在: {p}', file=sys.stderr)
            sys.exit(1)
    if args.cover and not os.path.exists(args.cover):
        print(f'[FAIL] 封面不存在: {args.cover}', file=sys.stderr)
        sys.exit(1)
    with open(args.desc, 'r', encoding='utf-8') as f:
        desc_text = f.read().strip()
    if args.ai_notice:
        desc_text += '\n（本文由 AI 辅助生成，经人工审核发布）'

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.connect_over_cdp(f'http://127.0.0.1:{args.port}')
            context = browser.contexts[0] if browser.contexts else browser.new_context()
            page, _ = find_or_open_page(context, 'member.bilibili.com')

            if 'passport' in page.url or page.locator(SELECTORS['login_hint']).count() > 0:
                print('[NEED_HUMAN] B站未登录，请在弹出的浏览器中登录后重试', file=sys.stderr)
                sys.exit(42)

            # 1. 上传视频
            page.wait_for_selector(SELECTORS['video_input'], timeout=30000)
            page.set_input_files(SELECTORS['video_input'], args.video)
            print('[OK] 视频已选择，等待上传处理（大文件较慢）...')
            # 轮询等待上传完成（出现标题输入框即视为进入编辑态）
            deadline = time.time() + 600
            while time.time() < deadline:
                if page.locator(SELECTORS['title']).count() > 0:
                    break
                time.sleep(3)
            time.sleep(3)

            # 2. 标题
            r = fill_input(page, SELECTORS['title'], args.title[:80])
            print(f'[INFO] 标题: {r}')
            time.sleep(1)

            # 3. 简介
            r = fill_input(page, SELECTORS['desc'], desc_text)
            print(f'[INFO] 简介: {r}')
            time.sleep(1)

            # 4. 标签
            if args.tags:
                r = fill_input(page, SELECTORS['tags'], args.tags)
                print(f'[INFO] 标签: {r}')
                time.sleep(1)

            # 5. 封面（可选）
            if args.cover:
                if page.locator(SELECTORS['cover_input']).count() > 0:
                    page.set_input_files(SELECTORS['cover_input'], args.cover)
                    print('[OK] 封面已选择')
                    time.sleep(3)

            # 6. 保存草稿（绝不投稿）
            if page.locator(SELECTORS['save_draft']).count() > 0:
                page.locator(SELECTORS['save_draft']).first.click()
                print('[OK] 已点击「保存草稿」')
                time.sleep(3)
            else:
                print('[WARN] 未找到「保存草稿」按钮，请人工检查页面', file=sys.stderr)
                sys.exit(1)

            if args.screenshot:
                os.makedirs(os.path.dirname(os.path.abspath(args.screenshot)), exist_ok=True)
                page.screenshot(path=args.screenshot, full_page=False)
                print(f'[OK] 截图: {args.screenshot}')

            print('[DONE] B站草稿已保存（未投稿）')
    except Exception as e:
        print(f'[FAIL] B站发布异常: {e}', file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
