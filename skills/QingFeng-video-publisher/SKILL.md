---
name: QingFeng-video-publisher
description: 视频发布技能（小红书 + B站，横竖屏自动路由）。当用户说「将某视频发布到小红书」或「发布到B站」时触发；横屏自动发B站、竖屏自动发小红书。支持上传视频、设置封面、填写标题简介/正文、添加话题、存草稿。最后由用户手动点发布。Keywords: 发布视频, 上传视频, 小红书发布, B站发布, 视频发布, 发到小红书, 发到B站, 横屏发B站, 竖屏发小红书
---

# Video Publisher - 小红书 + B站 发布（横竖屏自动路由）

> 本技能（v1）负责 **小红书 + B站** 两个平台，并内置**横竖屏自动路由**：
> - **横屏（宽 ≥ 高）→ B站**
> - **竖屏（高 > 宽）→ 小红书**
>
> 抖音 / 快手 由 **`QingFeng-video-publisher-v2`**（v2）负责。

## ⚠️ 铁律：停止工作绝不关闭浏览器

**Playwright 的 `with sync_playwright()` 上下文管理器退出时会自动调用 `browser.close()`，即使是 `connect_over_cdp` 连接的外部浏览器也会被关掉！**

正确写法（所有脚本必须遵守）：
```python
p = sync_playwright().start()
browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
try:
    # ... 操作 ...
finally:
    browser.close()  # CDP 连接下只断开，不会真正关闭用户的浏览器
    p.stop()
```

> ⚠️ **不要调用 `browser.disconnect()`**：Playwright 1.62 的 CDP `Browser` 对象
> **根本没有 `disconnect()` 方法**（实测只有 `close` / `is_connected`），调用会抛
> `AttributeError`。`browser.close()` 对 CDP 连接等价于"仅断连、不杀浏览器"，安全。

**禁止使用 `with sync_playwright() as p:`**（退出时会 `browser.close()` 杀掉外部浏览器）。

---

## 🔀 横竖屏自动路由（推荐入口）

用 `scripts/publish_auto.py` 一个命令搞定：读分辨率自动选平台。

```bash
python scripts/publish_auto.py \
  --video "<视频路径>" \
  --cover-h "<4:3横版封面(发B站用)>" \
  --cover-v "<3:4竖版封面(发小红书用)>" \
  --title "<标题>" --desc "<简介>" --tags "a,b,c"
```

**路由规则**：
- 宽 ≥ 高（横屏）→ **B站**（`publish_bilibili.py`，用 `--cover-h`）
- 高 > 宽（竖屏）→ **小红书**（`publish_xiaohongshu.py`，用 `--cover-v`）

其他：
- 分辨率用 `ffprobe` 读取（WinGet 自带 ffmpeg 含 ffprobe；找不到则回退默认 B站，或 `--platform bilibili|xiaohongshu` 手动覆盖）
- 子脚本用 `subprocess` 调用，沿用同一 venv python
- 同样默认只「存草稿」，传 `--publish` 才真正发布

> ✅ 小红书网页版**支持自定义封面上传**：脚本自动 hover 当前封面帧（`.default.column`）→ 点「编辑封面」→ 打开设置封面弹窗 → 上传本地图 → 应用 → 完成。`--cover-v` 传你的竖版封面即可。

---

## ✅ B站发布完整流程（2026-09-02 验证成功）

使用 `scripts/publish_bilibili.py`（Playwright + CDP）：

```bash
python scripts/publish_bilibili.py \
  --video "<视频路径>" \
  --cover "<4:3横版封面>" \
  --title "<稿件标题>" \
  --desc "<稿件简介（可含#话题）>" \
  --tags "教育,王阳明,传统文化,心学,历史"
```

**脚本默认点「存草稿」暂存离开**（符合"我手动发布"铁律）；传 `--publish` 才点「立即投稿」真正发出。

### 平台关键差异（与抖音/快手都不同，务必先看！）

1. **视频上传 input**：直接 `set_input_files` 到页面【第一个 file input】
   （`input[type=file]`，accept 含 `.mp4`）。B站用的是 `bcc-upload` Web Component，
   可见的那个 input 就是对的（不同于抖音/快手要找特定 input）。
2. **标题**是普通 `input[placeholder="请输入稿件标题"]`（maxlength 80），
   用 `execCommand('insertText')` 填（React 受控）。
3. **简介是 Quill 富文本编辑器** `.ql-editor`（contenteditable），**0 个 textarea**！
   必须用 `execCommand('insertText')` 填，普通赋值无效。
4. **标签**是 `input[placeholder="按回车键Enter创建标签"]`（maxlength 20），
   `type` 文本后按 `Enter` 创建，多个用逗号分隔。
5. **封面**：点「添加封面」→ 弹窗内 image input（`accept*=image`）→
   `set_input_files` → 点「完成」。**注意封面上传时会弹【通知授权框】，必须先点
   「禁止/知道了」关掉**，否则挡住「完成」按钮。封面确认按钮叫「完成」（不是「确认」）。
6. **B站天然有「存草稿」按钮**（`submit-container` 内），正好对应"暂存离开"铁律——
   点「存草稿」后页面跳到草稿管理页，随时可手动发布。不像快手没有草稿按钮。

### 封面上传正确流程（关键！）

1. 点「添加封面」（封面已设过则文案变「更换封面」，脚本用"包含"匹配+CSS 兜底兼容）
2. 弹窗内找 `input[type=file][accept*=image]` 注入封面图
3. （若有通知授权框先关掉）
4. 点「完成」确认，对话框关闭即生效

### 已知坑

- 投稿页是微前端 micro-app，上传后页面 SPA 不刷新，登录态在 profile 里持久
- **导航铁律**：脚本里**必须始终 `page.goto(上传表单页)`**，不能只在 URL 不含
   bilibili 时才跳——否则会停在上次存草稿后的「草稿管理页」导致找不到 file input
- 通知授权框也用 `.bcc-dialog__wrap` 类，判定"封面对话框是否关闭"时必须排除它
  （用 `cover_modal_open()` 按"含图片 input 或封面文案"判定，不被通知框干扰）
- 封面上传成功的硬证据：弹窗注入后「完成」点击生效、对话框关闭

---

## ✅ 小红书发布完整流程（2026-09-02 实测通过）

使用 `scripts/publish_xiaohongshu.py`（Playwright + CDP，竖屏 9:16 走此平台）：

```bash
python scripts/publish_xiaohongshu.py \
  --video "<竖屏视频>" \
  --cover "<3:4竖版封面(网页版支持上传，脚本自动设置)>" \
  --title "<标题>" \
  --desc "<正文>" \
  --tags "教育,王阳明"
```

**小红书网页端没有「暂存离开/存草稿」按钮，唯一按钮是「发布笔记」**。脚本只填表单、绝不点「发布笔记」（符合"我手动发布"铁律）；表单填好后网页会自动存为草稿。传 `--force-upload` 可强制重新上传。

### 平台关键差异（与抖音/快手/B站都不同，务必先看！）

1. **标题、正文是两个独立框**：
   - 标题：`input[placeholder="填写标题会有更多赞哦"]`（普通 input，`fill()` 即可）
   - 正文：`div.tiptap.ProseMirror`（Tiptap/ProseMirror 富文本）——**必须用「复制粘贴方案」填**（2026-09-02 实战定论，此前 `el.click()`+`type()` 反复把整页吸进编辑器）：
     ① 文本写剪贴板（`navigator.clipboard.writeText`，失败退回 `execCommand('copy')`）
     ② JS `el.focus()` + 光标置末尾（**绝不 `el.click()`**：该元素渲染后体积巨大、含整页布局，点几何中心会误触侧边栏、把整页吸进编辑器）
     ③ `Control+a` + `Delete` 清空旧内容（**绝不用 `Backspace`**：会在文档起点合并根节点、把整页 UI 吸进编辑器）
     ④ `Control+v` 粘贴
     ⑤ 校验失败兜底：`document.execCommand('insertText')`（先清空再插入，保证干净）
2. **话题**：在正文里直接打 `#话题词`（# 前留一个空格）即触发话题标签，空格/回车确认后按 `Escape`
   关掉建议浮层，避免遮挡后续点击
3. **封面：网页创作中心【支持】上传自定义封面图**（2026-09-02 实测验证：设置封面弹窗内有 `image/*` 上传入口，可传本地图）。
   脚本自动 hover 当前封面帧 `.default.column` → 「编辑封面」按钮浮现 → 真实鼠标点击打开「设置封面」图片编辑器 →
   上传本地图 → 真实鼠标点「应用」→ 真实鼠标点「完成」。
   ⚠️ **「应用」「完成」必须用【真实鼠标点击】（`page.mouse.click(x,y)` 坐标）**：这两个是 Vue 组件按钮，
   对真实 pointer event 敏感——JS 的 `el.click()`、`dispatchEvent` 合成点击、甚至 `get_by_text().click()` 都会
   **静默失败、弹窗不关、脚本误以为成功**。脚本已固化 `real_click_button_by_text()`（真实坐标点击 + 轮询
   "图片上传入口是否消失"校验弹窗真正关闭），彻底解决"日志显示完成、实则卡在弹窗"。
   （注意：编辑封面按钮默认 `display:none`，须 hover `.default.column` 当前封面帧才显；hover `.cover--column` 容器或 `.cover-image.column` 缩略图均无效）
4. **创作中心 web 端**：`https://creator.xiaohongshu.com/publish/publish`
5. **网页端无独立草稿按钮，唯一按钮是「发布笔记」**：按铁律脚本绝不点它，表单填好后网页自动存草稿，由你手动点「发布笔记」发布

### 已知坑

- 视频上传：`set_input_files` 到首个 `input[type=file]`，轮询"标题框出现"判定处理完成
- 正文是 ProseMirror，**正确手段是「复制粘贴」**（剪贴板 + `Control+v`），详见上面正文框说明；`el.click()` 点几何中心会损坏整页、`page.keyboard.type()` 逐字输入在重填时旧内容易残留，均不推荐
- 若页面已有视频（标题框存在）默认跳过上传；加 `--force-upload` 重传
- **封面弹窗「应用」「完成」按钮必须真实鼠标点击**（坐标 `page.mouse.click`）才生效：Vue 组件对合成点击静默失败、弹窗不关闭，脚本必须轮询校验关闭（见 `real_click_button_by_text()`）。此坑曾导致"日志显示完成、实则卡在封面弹窗"。
- 小红书**无「暂存离开」按钮**，脚本终点是"不点「发布笔记」、靠自动存草稿"；若想确认草稿已存，可在左侧「草稿」列表查看
- **⚠️ 最终截图可能超时（2026-09-03 实测）**：小红书视频发布页填完所有内容后，`page.screenshot()` 可能因页面字体/资源加载超时报 `Timeout 30000ms exceeded`。**这不影响发布结果**——视频、标题、正文、封面都已设置完成，网页会自动存草稿。脚本应将截图设为 best-effort（try/except 包裹），不因截图失败而报错。

---

## 平台差异速查

| 平台 | 视频上传 | 封面 | 话题 | 草稿按钮 |
|------|---------|------|------|---------|
| B站 | set_input_files 到首个 file input | 4:3（弹窗内 input，点「完成」） | 标签框回车创建 | 「存草稿」（脚本默认点它暂存离开） |
| 小红书 | set_input_files 到首个 file input | 支持自定义上传（hover 当前封面帧打开编辑器上传本地图） | 正文内 #词 触发 | 无独立按钮，仅「发布笔记」（按铁律不点，自动存草稿） |

> 抖音 / 快手 见 v2 技能（QingFeng-video-publisher-v2）：抖音有「暂存离开」、快手保持页面手动发布。

---

## 📝 获取简介（发布前环节）

发布前先尝试从视频所在文件夹里"自动找稿"，减少手动写简介的工作量。本步骤复用 **v2 技能的 `fetch_intro.py`**（两技能共用同一提取器）：

```bash
python "C:/Users/chenw/.workbuddy/skills/QingFeng-video-publisher-v2/scripts/fetch_intro.py" \
  --video "<视频路径>" --platform bilibili|xiaohongshu
```

- 查找优先级：① 与视频**同名**的文档；② 文件名**含视频名**的文档；③ 文件夹内任意文档；
  ④ **汇总类文稿中按"第N期"标题抽取本集小节**（如 `白话诗说-30期文稿汇总.md` 里的「## 第6期」整节）。
- `.docx` 用 `zipfile` 直接读 `word/document.xml` 提取，**无需 python-docx**。
- 输出：找到则打印提取文本；**未找到打印 `__NO_INTRO_FOUND__`**。只搜"视频所在文件夹"，不递归上层。

**LLM 归纳成平台简介**（Agent 完成）：
- 若非 `__NO_INTRO_FOUND__`，归纳成一段简介：开门见山点价值 / 悬念，避免官样话。
- **B站**：简介可含 `#话题`（压末尾，必带 `#教育` 等）；**小红书**：话题在**正文内**用 `#词` 触发，不在简介堆 #。
- 把结果作为 `--desc` 传入 `publish_auto.py` / `publish_bilibili.py` / `publish_xiaohongshu.py`。
- 若 `__NO_INTRO_FOUND__`，**不传 `--desc`**，简介留空，由你后续手动补。

> 目前为"脚本提取 + Agent 归纳"两段式；若日后要完全无人值守，可把归纳接成 LLM API。

---

## 脚本说明

| 脚本 | 用途 |
|------|------|
| `publish_auto.py` | **推荐入口**：横竖屏自动路由（横→B站 / 竖→小红书），ffprobe 读分辨率 |
| `publish_bilibili.py` | **B站**：上传视频+标题+简介(Quill)+标签+封面(4:3)+存草稿（2026-09-02 验证） |
| `publish_xiaohongshu.py` | **小红书**：上传视频+标题+正文(ProseMirror 复制粘贴)+#话题+自定义封面（hover 当前封面帧 `.default.column` 自动打开编辑器上传，2026-09-02 验证） |
| `fetch_intro.py` | **获取简介**（位于 v2 技能，两技能共用）：`QingFeng-video-publisher-v2/scripts/fetch_intro.py` |

所有脚本与本 SKILL.md 同目录的 `scripts/` 子目录（fetch_intro 除外，在 v2）。

---

## 启动浏览器（两技能通用）

必须用 Chrome for Testing（不会自动更新），用户 profile 含登录态。

**方式 A（最简单）：双击 v2 技能的 `scripts/start_chrome_cdp.cmd`**，自动带 profile 启动并开 CDP（端口 9222）。

**方式 B（PowerShell）**：
```powershell
Start-Process "D:\chenw\chrome-win64\chrome.exe" -ArgumentList "--user-data-dir=D:\chenw\chrome-test-profile","--no-first-run","--remote-debugging-port=9222","--remote-allow-origins=*"
```

> 🔒 **这两个目录是技能运行依赖，禁止删除**：
> - `D:\chenw\chrome-win64\` —— Chrome for Testing 本体
> - `D:\chenw\chrome-test-profile\` —— **登录态**（抖音/B站/小红书），删了要重新扫码登录

---

**最后更新**：2026-09-02
**更新内容**：
- **技能归属纠正**：将小红书 + B站 + 横竖屏自动路由（横屏→B站 / 竖屏→小红书）**从 v2 迁入本技能（v1）**，重写本 SKILL.md 为真实实现文档（此前是"指针到 v2" + 2026-04 失效旧抖音记录 + `.qclaw` 失效路径）。
- **脚本归位**：`publish_bilibili.py` / `publish_xiaohongshu.py` / `publish_auto.py` 已从 v2/scripts 移到本技能 scripts/。
- **抖音 / 快手归属 v2**：`QingFeng-video-publisher-v2` 现在只负责抖音 + 快手两个短视频平台。
- **封面「应用/完成」真实鼠标点击修复（2026-09-02 收尾）**：`set_cover` / `dismiss_draft_modal` 改用 `real_click_button_by_text()`（真实坐标 `page.mouse.click`），并轮询"图片上传入口是否消失"校验弹窗真正关闭，彻底解决此前"日志成功、实则卡在封面弹窗"的静默失败；同时把该铁律写入 SKILL.md 小红书章节与已知坑。

**历史更新**（源自 v2 早期记录，本技能承接）：
- 2026-09-02 B站发布验证：上传到首个 file input、标题 `请输入稿件标题`、简介 Quill `.ql-editor`、标签回车创建、封面弹窗内 input + 点「完成」（先关通知授权框）、「存草稿」暂存离开、导航铁律始终 goto 上传表单页。
- 2026-09-02 小红书发布实测：标题 `填写标题会有更多赞哦`、正文 ProseMirror 真实键盘输入、`#词` 触发话题、网页【支持】自定义封面（hover `.default.column` 自动打开编辑器上传本地图）、无暂存按钮靠自动存草稿。
- 2026-09-02 横竖屏路由 `publish_auto.py`：ffprobe 读分辨率，横→B站 / 竖→小红书。
