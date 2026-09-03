---
name: QingFeng-wechat-publisher
description: 将本地 HTML 文件的图文内容自动发布到微信公众号（mp.weixin.qq.com）。触发词：发布到公众号、发到公众号、发到微信、微信公众号。头条号发布请使用 QingFeng-toutiao-publisher 技能。
---

# 微信公众号发布技能

将本地 HTML 文件的图文内容**自动填入**微信公众号编辑器，**保存为草稿**，用户手动完成最终发布。

**脚本**：`scripts/publish_wechat.py`（v7）

## 核心规则

- **脚本绝不点击发布按钮** — 最终发布必须由用户手动操作
- **脚本结束后浏览器保持打开** — 停留在编辑器页面，用户可继续手动设置封面/原创/创作来源
- **公众号在新标签页打开** — 不覆盖头条等其他平台已打开的页面，各平台后台独立标签页共存
- **禁止用 `with sync_playwright()`** — 退出时会关闭整个浏览器，必须用 `p = sync_playwright().start()` 手动管理，脚本结束不调用 `p.stop()`
- 用户只需提供 HTML 文件路径，脚本一键完成所有准备工作
- **封面图不会插入正文**（cover.jpg 等文件自动排除在正文配图之外）
- **不自动设置封面、原创声明、创作来源** — 这些由用户在保存草稿后手动完成

## 前置条件

1. Chrome for Testing 已启动（见下方启动命令）
2. 已安装 Python 包 `playwright`
3. **微信公众号已登录**（Chrome for Testing 中已登录微信公众号后台，profile 会保存登录态）
4. **必须使用 Chrome for Testing**（`D:\chenw\chrome-win64\chrome.exe`），不要用 Edge（自动更新会导致问题）

**启动 Chrome for Testing：**
```powershell
Start-Process "D:\chenw\chrome-win64\chrome.exe" -ArgumentList "--user-data-dir=D:\chenw\chrome-test-profile","--no-first-run","--remote-debugging-port=9222","--remote-allow-origins=*"
```

> 无需手动打开浏览器！脚本会通过 CDP 连接已有 Chrome 并在新标签页导航到编辑器页面。

## 使用方法

当用户说「将某某HTML发布到公众号/微信」时：

1. **读取 HTML 文件**，分析文章标题和正文内容
2. **执行脚本**：

```bash
python scripts/publish_wechat.py "<HTML文件路径>" --author "作者名"
```

**可选参数**：
- `--author` — 作者名（默认：无不言）

---

## 发布流程（7步）

### Step 0 — 导航到编辑器（新标签页）

通过 CDP 连接 Chrome for Testing 浏览器，检测当前页面状态：

1. **优先找已有编辑器页面**（URL 含 `appmsg_edit`）
2. 否则找**公众号首页**（URL 含 `home`），从中点击「**文章**」按钮
3. ⚠️ 「文章」按钮会在**新标签页**中打开编辑器（不是当前页跳转）
4. 点击后 `sleep(5)` 等待新标签页，遍历 `context.pages` 找含 `appmsg` 的非首页标签页
5. `editor.bring_to_front()` 切换过去
6. 最后手段才用 `page.goto()` 直接跳转（可能触发登录拦截）

> **重要**：公众号在新标签页打开，不会覆盖头条等其他平台的页面。脚本结束后所有标签页保持打开。

### Step 1 — 选择主模板

进入编辑器后，尝试自动选择「主模板」。若未找到可忽略（手动选择亦可）。

### Step 2 — 上传配图，收集 CDN URL

通过 `input[type="file"]` 逐张上传配图，从 DOM 检测新增的 `mmbiz.qpic.cn` 图片提取 CDN URL。

**关键规则**：
- 配图 = HTML 同目录下的 `illustration_*.jpg` 等
- **自动排除 `cover.*` 文件**（封面由用户手动设置，不插入正文）
- 此步骤只上传+收集 URL，不往正文注入任何内容
- 大图(>300KB) 等待 4 秒 + retry 3 秒

### Step 3 — 注入完整排版 HTML（保留样式）

直接注入 QingFeng-GZH-Layout 生成的**完整排版 HTML**（全内联样式），仅将图片路径替换为 Step 2 收集的 CDN URL。

- 标题从 HTML 第一个 section 的大字号 span 提取（GZH排版无h1标签）
- 注入方式：`execCommand('selectAll') → ('delete') → ('insertHTML', newHTML)`
- 注入后验证 sections 数量和图片数量

### Step 4 — 填写标题和作者

| 位置 | 选择器 | 方法 |
|------|--------|------|
| 左侧标题栏 | `#title` | 直接赋值 value + dispatchEvent |
| 作者输入框 | `#author` | 直接赋值 value + dispatchEvent |

### Step 5 — 清理 broken 图片

移除正文中 naturalWidth=0 或 src 为空的图片元素。

### Step 6 — 保存草稿

点击页面底部的「保存为草稿」按钮，等待3秒确认保存。

### Step 7 — 最终验证 + 截图

验证项目：
- 左侧标题、正文标题、作者是否正确
- 正文文字长度
- 图片数量及有效性（CDN URL + naturalWidth > 100）
- 全页截图保存

> **脚本结束后浏览器保持打开**，用户可在编辑器中继续手动设置封面、原创声明、创作来源，然后点击发布。头条等其他平台的标签页也保持打开，供用户分别验证。

---

## 关键选择器

| 元素 | 选择器 | 说明 |
|------|--------|------|
| 左侧标题 | `#title` | TEXTAREA |
| 作者 | `#author` | INPUT |
| 正文编辑器 | `.ProseMirror[1]` | 第二个 ProseMirror（正文） |
| 文件上传 | `input[type="file"]` | hidden 元素，可直接 set_input_files |
| 保存草稿 | 文字匹配「保存为草稿」 | 页面底部按钮 |

---

## 技术要点（踩坑记录）

| 问题 | 正确做法 |
|------|---------|
| **排版样式丢失** | 直接注入 QingFeng-GZH-Layout 的完整HTML（全内联样式），不要解析重建简化HTML |
| **标题提取失败** | GZH排版无h1标签，从第一个section的大字号span提取 |
| **导航到编辑器失败** | 首页「文章」按钮 → 新标签页打开 → 遍历 pages 找 appmsg 标签 |
| **DOM修改被回滚** | 必须用 `execCommand('selectAll+delete+insertHTML')`，禁止直接改 innerHTML/img.src |
| **图片路径错误** | 图片路径 = HTML 文件同目录（不是固定目录） |
| **上传等待不足** | 大图(>300KB) 等 4 秒 + retry 3 秒 |
| **file input 找不到** | `input[type="file"]` 是 hidden 状态，用 `query_selector_all` 不加 visible 过滤 |
| **直接 goto 触发登录** | 优先用页面内点击导航，goto 作为最后手段 |
| **浏览器被关闭（关键）** | 禁止用 `with sync_playwright()`，必须用 `p = sync_playwright().start()` 手动管理，脚本结束不调用 `p.stop()`。`with` 退出时会调用 `playwright.stop()` 关闭整个浏览器 |
| **CDP /json/new 返回405** | Chrome for Testing安全限制，改用 page.goto导航到首页再点「文章」 |

---

## 常用路径

- 微信公众号文章：`D:\知识库\媒体运营\{日期}\formatted\wechat.html`
- 配图：`D:\知识库\媒体运营\{日期}\pb\illustration_1.jpg` ~ `illustration_N.jpg`
- 封面：`D:\知识库\媒体运营\{日期}\pb\cover.jpg`

---

## 依赖

```bash
pip install playwright
```

## 版本历史

- **v1** (2026-05-16)：初始版本
- **v4** (2026-05-17)：分离文字/图片注入步骤
- **v5** (2026-06-09)：修复封面图重复问题（排除 cover.*）；修复导航逻辑（新标签页 + force click）
- **v6** (2026-08-31)：改用 Chrome for Testing；注入完整排版HTML（保留样式）；去掉封面/原创/来源自动设置，改为保存草稿结束；浏览器保持打开
- **v7** (2026-09-02)：修复浏览器被关闭问题（`with sync_playwright()` → 手动管理 `p.start()`）；明确公众号在新标签页打开，不覆盖其他平台页面
