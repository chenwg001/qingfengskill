---
name: QingFeng-xiaohongshu-publisher
description: 将小红书排版txt文件的图文内容自动发布到小红书创作者平台（creator.xiaohongshu.com），保存为草稿。触发词：发布到小红书、发到小红书、小红书发布、xhs发布。统一使用 Chrome for Testing CDP 连接。
---

# 小红书发布技能

将小红书排版 txt 文件的图文内容**自动填入**小红书创作者平台，**保存为草稿**，用户手动完成最终发布。

**脚本**：`scripts/publish_xiaohongshu.py`（v3）

## 核心规则

- **脚本绝不点击发布按钮** — 最终发布必须由用户手动操作
- **脚本结束后浏览器保持打开** — 停留在草稿箱或发布页面
- **自动切换到"上传图文"模式** — 小红书默认是视频发布，必须先点击"上传图文"tab
- **先传封面图，再传插图** — 第一张图用3:4封面图，后续用插图
- **逐张上传图片** — 小红书文件 input 不支持多文件，必须一张一张传
- **禁止用 `with sync_playwright()`** — 退出时会关闭浏览器，必须用 `p = sync_playwright().start()` 手动管理
- **禁止调用 `p.stop()`** — Python 正常退出时浏览器保持打开
- **禁止用 `os._exit(0)`** — 会导致 playwright driver 被强制终止，反而关闭浏览器；正常 return 即可

## 前置条件

1. Chrome for Testing 已启动（端口 9222）
2. 已安装 Python 包 `playwright`
3. **小红书已登录**（Chrome for Testing 中已登录小红书创作者平台，profile 会保存登录态）
4. **必须使用 Chrome for Testing**（`D:\chenw\chrome-win64\chrome.exe`）

**启动 Chrome for Testing：**
```powershell
Start-Process "D:\chenw\chrome-win64\chrome.exe" -ArgumentList "--user-data-dir=D:\chenw\chrome-test-profile","--no-first-run","--remote-debugging-port=9222","--remote-allow-origins=*"
```

## 使用方法

当用户说「将某某内容发布到小红书」时：

1. 准备小红书排版 txt 文件（第一行标题，剩余正文）
2. 准备 3:4 封面图和插图目录
3. 执行脚本：

```bash
python scripts/publish_xiaohongshu.py "<txt文件路径>" \
  --images-dir "<插图目录>" \
  --cover "<3:4封面图路径>"
```

**参数说明：**
- `file` — 小红书排版 txt 文件路径（必填）
- `--images-dir` — 插图目录（默认：txt 文件同目录的 ../pb）
- `--cover` — 3:4 封面图路径（可选，作为第一张图上传）

## 发布流程（5步）

### Step 0 — 切换到图文模式

导航到发布页面后，自动点击"上传图文"tab 切换到图文发布模式。

- 用 JS 点击 `.creator-tab` 中 textContent 为"上传图文"的元素
- 等待 4 秒让页面切换完成
- 验证：页面出现"上传图片"文字

### Step 1 — 逐张上传图片

先传封面图（如有），再传插图，逐张上传：

- 小红书 `input[type="file"]` 不支持多文件（`Non-multiple file input` 错误）
- 必须循环调用 `file_input.set_input_files(img)`，每次传一张
- 每张图等待 4 秒上传完成
- 全部传完后再等 5 秒

### Step 2 — 填写标题

- 选择器：`input[placeholder*="标题"], textarea[placeholder*="标题"]`
- 从 txt 文件第一行提取标题，去掉开头的 emoji

### Step 3 — 填写正文

- 选择器：`textarea[placeholder*="正文"], [contenteditable="true"]`
- TEXTAREA 用 `fill()`，contenteditable 用 `click()` + `keyboard.type()`

### Step 4 — 保存草稿（暂存离开）

**关键坑点**："暂存离开"按钮用 JS `querySelectorAll` 找不到（可能在 shadow DOM 或有特殊渲染），必须用坐标点击：

1. 先按 ESC 关闭可能打开的下拉菜单（如话题选择器）
2. 滚动内部可滚动容器到底部
3. 尝试 JS 精确匹配"暂存离开"（通常失败）
4. **降级方案**：找到"发布"按钮的坐标，"暂存离开"在其左侧约 100px 处，用 `page.mouse.click(x, y)` 点击
5. 点击后等待 3 秒，页面会显示"保存成功"并弹出草稿箱

### Step 5 — 截图

全页截图保存到当前目录，文件名 `xhs_publish_YYYYMMDD_HHMMSS.png`。

## 关键选择器

| 元素 | 选择器/方法 | 说明 |
|------|------------|------|
| 上传图文 tab | `.creator-tab` 中 textContent="上传图文" | JS click |
| 文件上传 | `input[type="file"]` | 逐张上传，不支持多文件 |
| 标题 | `input[placeholder*="标题"]` | fill |
| 正文 | `textarea[placeholder*="正文"]` | fill |
| 暂存离开 | 坐标点击（发布按钮左侧） | JS 找不到，必须用 mouse.click |
| 发布按钮 | textContent="发布" | 用于计算暂存离开坐标 |

## 技术要点（踩坑记录）

| 问题 | 正确做法 |
|------|---------|
| **默认是视频发布** | 必须先点击"上传图文"tab 切换 |
| **多文件上传报错** | `Non-multiple file input can only accept single file`，必须逐张上传 |
| **暂存离开按钮找不到** | JS querySelectorAll 找不到（shadow DOM？），用发布按钮坐标 + 偏移量 mouse.click |
| **下拉菜单拦截点击** | 点击前先按 ESC 关闭话题选择等下拉菜单 |
| **浏览器被关闭** | 禁止 `with sync_playwright()`、禁止 `p.stop()`、禁止 `os._exit(0)`；手动 `p.start()` + 正常 return |
| **内部滚动容器** | 页面内容在可滚动 div 内，不是 window 滚动；需遍历所有 `scrollHeight > clientHeight` 的元素滚动到底 |
| **标题超20字** | 小红书标题限制20字，超长会显示红色警告，需注意 |

## 常用路径

- 小红书文本：`D:\知识库\媒体运营\{日期}\formatted\xhs.txt`
- 插图目录：`D:\知识库\媒体运营\{日期}\pb\`
- 3:4 封面：`D:\知识库\媒体运营\{日期}\covers\cover_3x4.jpg`

## 依赖

```bash
pip install playwright
```

## 版本历史

- **v1** (2026-08-31)：初始版本，基础图文发布
- **v2** (2026-09-03)：修复多文件上传报错（逐张上传）；添加3:4封面图优先；修复浏览器关闭问题
- **v3** (2026-09-03)：修复"暂存离开"按钮找不到问题（坐标点击降级方案）；去掉 os._exit(0) 改为正常退出；添加 ESC 关闭下拉菜单
