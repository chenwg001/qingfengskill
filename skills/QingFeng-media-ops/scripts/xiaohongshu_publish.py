# -*- coding: utf-8 -*-
"""
小红书图文发布（CDP，进草稿，绝不点发布）

用法:
  python xiaohongshu_publish.py --title "标题(≤20字)" --content 小红书正文.txt \
      --images 封面.png 内图1.png [--port 9222] [--screenshot drafts/xhs.png] [--ai-notice]

流程:
  1. playwright connect_over_cdp 连接 Chrome for Testing（端口默认 9222）
  2. 打开/复用创作服务平台发布页（creator.xiaohongshu.com/publish/publish）
  3. 未登录 -> 抛 NEED_HUMAN（退出码 42），提示人工扫码
  4. 上传图片 -> 填标题 -> 填正文（contenteditable）-> 勾选 AI 声明(可选)
  5. 点「存为草稿」；绝不点「发布」
  6. 截图验证草稿保存成功

退出码: 0=成功进草稿  42=需人工(登录/验证码)  1=其他失败
"""
import argparse
import os
import sys
import time

sys.stdout.reconfigure(encoding='utf-8')

from playwright.sync_api import sync_playwright

DEFAULT_URL = 'https://creator.xiaohongshu.com/publish/publish'
DEFAULT_PORT = 9222  # 统一 Chrome for Testing

# 选择器集中在此，平台改版只改这里
SELECTORS = {
    'file_input': 'input[type=file]',
    'title': 'input[placeholder*="标题"], input[data-testid*="title"], [contenteditable="true"][data-placeholder*="标题"]',
    'content': '.ql-editor[contenteditable="true"], [contenteditable="true"][data-placeholder*="正文"], [contenteditable="true"][data-placeholder*="填写"]',
    'save_draft': 'text=存为草稿',
    'publish_btn': 'text=发布',
    'ai_declare': 'text=作品声明',
    'login_hint': 'text=登录',
}


def fill_title(page, text):
    """标题：原生 setter + input/change 事件（React 兼容）"""
    expr = """
    (text) => {
      const sels = arguments[0];
      let target = null;
      for (const sel of sels) {
        const el = document.querySelector(sel);
        if (el && el.offsetParent !== null) { target = el; break; }
      }
      if (!target) return 'TITLE_NOT_FOUND';
      const proto = target.tagName === 'TEXTAREA' ? window.HTMLTextAreaElement.prototype
                  : target.isContentEditable ? window.HTMLElement.prototype
                  : window.HTMLInputElement.prototype;
      const setter = Object.getOwnPropertyDescriptor(proto, 'value').set;
      if (setter) { setter.call(target, text); } else { target.value = text; }
      target.dispatchEvent(new Event('input', {bubbles:true}));
      target.dispatchEvent(new Event('change', {bubbles:true}));
      target.dispatchEvent(new Event('blur', {bubbles:true}));
      return 'SET:' + target.value.slice(0,30);
    }
    """
    return page.evaluate(expr, SELECTORS['title'], text)


def fill_content(page, text):
    """正文：聚焦 contenteditable，execCommand 插入（Quill/React 兼容）"""
    expr = """
    (text) => {
      const sels = arguments[0];
      let target = null;
      for (const sel of sels) {
        const el = document.querySelector(sel);
        if (el) { target = el; break; }
      }
      if (!target) return 'CONTENT_NOT_FOUND';
      target.focus();
      const sel = window.getSelection();
      const range = document.createRange();
      range.selectNodeContents(target);
      sel.removeAllRanges(); sel.addRange(range);
      document.execCommand('insertText', false, text);
      target.dispatchEvent(new Event('input', {bubbles:true}));
      target.dispatchEvent(new Event('change', {bubbles:true}));
      return 'SET:' + String(target.innerText || '').length + 'chars';
    }
    """
    return page.evaluate(expr, SELECTORS['content'], text)


def find_or_open_page(context, url_part):
    for p in context.pages:
        if url_part in p.url:
            return p, False
    p = context.new_page()
    p.goto(DEFAULT_URL, timeout=60000)
    p.wait_for_load_state('domcontentloaded')
    return p, True


def main():
    ap = argparse.ArgumentParser(description='小红书图文发布（进草稿）')
    ap.add_argument('--title', required=True)
    ap.add_argument('--content', required=True, help='正文 txt 文件路径')
    ap.add_argument('--images', nargs='+', required=True, help='图片路径（第一张为封面）')
    ap.add_argument('--port', type=int, default=DEFAULT_PORT)
    ap.add_argument('--screenshot', default='')
    ap.add_argument('--ai-notice', action='store_true', help='文末追加 AI 生成标注')
    args = ap.parse_args()

    if not os.path.exists(args.content):
        print(f'[FAIL] 正文文件不存在: {args.content}', file=sys.stderr)
        sys.exit(1)
    for img in args.images:
        if not os.path.exists(img):
            print(f'[FAIL] 图片不存在: {img}', file=sys.stderr)
            sys.exit(1)
    with open(args.content, 'r', encoding='utf-8') as f:
        content_text = f.read().strip()
    if args.ai_notice:
        content_text += '\n（本文由 AI 辅助生成，经人工审核发布）'

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.connect_over_cdp(f'http://127.0.0.1:{args.port}')
            context = browser.contexts[0] if browser.contexts else browser.new_context()
            page, _ = find_or_open_page(context, 'creator.xiaohongshu.com')

            # 登录检测
            if 'passport' in page.url or page.locator(SELECTORS['login_hint']).count() > 0:
                print('[NEED_HUMAN] 小红书未登录，请在弹出的浏览器中扫码登录后重试', file=sys.stderr)
                sys.exit(42)

            # 1. 上传图片（第一张为封面）
            page.wait_for_selector(SELECTORS['file_input'], timeout=30000)
            page.set_input_files(SELECTORS['file_input'], args.images)
            print(f'[OK] 已选择 {len(args.images)} 张图片，等待上传处理...')
            time.sleep(6)

            # 2. 标题
            r = fill_title(page, args.title[:20])
            print(f'[INFO] 标题: {r}')
            time.sleep(1)

            # 3. 正文
            r = fill_content(page, content_text)
            print(f'[INFO] 正文: {r}')
            time.sleep(1)

            # 4. 存为草稿（绝不发布）
            if page.locator(SELECTORS['save_draft']).count() > 0:
                page.locator(SELECTORS['save_draft']).first.click()
                print('[OK] 已点击「存为草稿」')
                time.sleep(3)
            else:
                print('[WARN] 未找到「存为草稿」按钮，请人工检查页面', file=sys.stderr)
                sys.exit(1)

            # 5. 截图验证
            if args.screenshot:
                os.makedirs(os.path.dirname(os.path.abspath(args.screenshot)), exist_ok=True)
                page.screenshot(path=args.screenshot, full_page=False)
                print(f'[OK] 截图: {args.screenshot}')

            print('[DONE] 小红书草稿已保存（未发布）')
    except Exception as e:
        print(f'[FAIL] 小红书发布异常: {e}', file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
