---
name: QingFeng-video-publisher-v2
description: 短视频发布技能（抖音 / 快手）。当用户说「将某视频发布到抖音」或「发布到快手」时触发。支持上传视频、设置双封面(横4:3+竖3:4)、填写标题简介、添加话题、暂存离开。最后由用户手动点发布。Keywords: 发布视频, 上传视频, 抖音发布, 快手发布, 视频发布, 发到抖音, 发到快手
---

# Video Publisher V2 - 抖音 / 快手 短视频发布

> 本技能（v2）只负责 **抖音 + 快手** 两个短视频平台。
> 小红书 + B站（横竖屏自动路由）已迁移至 **`QingFeng-video-publisher`**（v1）技能。

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

## ✅ 抖音发布完整流程（2026-09-01 验证成功）

使用 `scripts/publish_douyin.py`（Playwright + CDP，已验证封面设置成功）：

```bash
python scripts/publish_douyin.py \
  --video "<视频路径>" \
  --cover-4x3 "<4:3横版封面>" \
  --cover-3x4 "<3:4竖版封面>" \
  --title "<标题>" \
  --desc "<简介>" \
  --save-draft
```

### 封面设置（委托 set_douyin_cover，已实测跑通）
- 封面设置交给同目录 `set_douyin_cover.set_both_covers`（2026-09-01 自探实测版），**不要再回到旧逻辑**。
- 流程：JS 强制显示槽位 hover 按钮（CDP 下 hover 不触发 `:hover`）→ 点槽位内「选择/编辑封面」→ 弹窗内主上传区 `set_input_files` 注入图片 → 点弹窗内「完成」。
- **关键**：弹窗内「取消/完成」按钮**就在 modal 内**（旧脚本用 `closest('.semi-modal-wrap')` 排除掉是错的，会导致编辑器永远关不上）；方向必须对应（4:3 图进「横封面4:3」、3:4 图进「竖封面3:4」）。
- 选图坑：带文字 / 人物 / 强 AI 痕迹的图会被「封面效果检测」回退成视频帧；用无文字无人物的朴素图（水墨 / 风景）最稳。
- ⚠️ **「设置竖封面获更多流量」引导弹窗**：设完封面后抖音可能弹出此 overlay（**非**封面编辑器），会拦截下一个封面槽位与底部「暂存离开」按钮。脚本已**三处加固**：`dismiss_vertical_cover_prompt` 支持多按钮文案（暂不设置 / 暂不 / 以后再说 / 稍后设置 / X关闭 / ESC兜底）+ `set_both_covers` 末尾兜底调用 + `publish_douyin.py` 暂存离开前兜底调用。
- 📐 **封面槽位顺序随视频方向变化（2026-09-02 发现）**：两个槽位的先后**不是固定的**——发**横屏视频时「横封面4:3」槽在前**，**竖屏视频时「竖封面3:4」槽在前**（白话诗说第6期竖屏 720×1280 实测：slot0=竖3:4、slot1=横4:3）。脚本 `find_slot_index` 已按槽位内比例**文本标签**（4:3 / 3:4）定位、与顺序无关，故不受影响；若日后改定位逻辑，务必以"文本标签"为准，不要依赖固定 index 或宽度启发式。
- 详见下方「封面是否真的生效 / 别被检测失败吓到 / NTFS 冒号」等经验。

### 其他要点
- 草稿按钮叫"暂存离开"（不是"存草稿"）；传 `--save-draft` 才点它暂存，不传则不点、保持页面。
- **⚠️ 封面编辑器弹窗拦截「暂存离开」（2026-09-03 实测）**：设完双封面后，封面编辑器弹窗（`.dy-creator-content-modal`）可能仍打开，会拦截底部「暂存离开」按钮的点击（Playwright 报 `subtree intercepts pointer events` 超时）。**必须先点弹窗内「完成」按钮关闭弹窗，再点「暂存离开」**。脚本应在暂存离开前检查弹窗是否可见，若可见则先点「完成」。
- 视频上传用 `set_input_files` 直接设视频 file input（找 `accept` 含 `video` / `.mp4`）。
- **导航铁律**：抖音是 SPA，**不能直接 `goto` 发布页 URL**（会停在框架、不渲染上传组件 → "未找到视频 input"）。必须从创作者首页点「发布视频 / 高清发布」触发路由跳转（脚本已内置此逻辑 + goto fallback）。
- 标题 `input[placeholder*=标题]`，简介 `div[contenteditable=true][data-placeholder*=简介]`。
- 暂存离开后页面回到发布首页，提示"你还有上次未发布的视频"，点"继续编辑"可恢复。

### AI 声明（内容由AI生成）
- 平台真实入口名：**抖音叫「自主声明」**（不是"声明""AI生成"等模糊词）。脚本 `set_ai_declaration(page)` 两步逻辑：① 先点开「自主声明」面板 → ② 在展开面板里选「内容由AI生成」选项。
- ⚠️ **已知缺口（2026-09-02 实测）**：本次发布两平台的声明勾选**都没真正生效**（旧逻辑按"AI生成+声明"模糊匹配点不中）。已据真实按钮名改为上述两步逻辑，**下次实跑需据真实 DOM 验证**（面板展开方式 / 选项是否为独立 checkbox 或 radio / 勾选后是否需再点确认）。best-effort：任一步找不到只告警、不中断发布。

---

## ✅ 快手发布完整流程（2026-09-02 验证成功）

使用 `scripts/publish_kuaishou.py`（Playwright + CDP）：

```bash
python scripts/publish_kuaishou.py \
  --video "<视频路径>" \
  --cover "<3:4竖版封面>" \
  --desc "<作品描述>" \
  --ratio 3:4
```

**脚本默认不点发布**（与抖音的「暂存离开」对应机制不同，详见下方），保持页面打开，由你手动点「发布」。

- **⚠️ 快手草稿保存方式（2026-09-03 实测）**：快手无「暂存离开/存草稿」按钮，只有「发布」和「取消」。点「取消」会离开发布页，但**快手会自动保留为草稿**——下次进入发布页会弹出「还有上次未发布的视频，是否继续编辑？」+「继续编辑」/「放弃」。因此保存草稿的方式就是点「取消」。
- **⚠️ 取消按钮可能在视口外**：页面较长时，底部「取消」按钮的 `getBoundingClientRect().y` 可能大于视口高度（如 y=1365，视口高800），直接 `mouse.click` 会点到空白处。**必须先 `el.scrollIntoView({block:'center'})` 滚动到视口内，再点击**。

### AI 声明（内容由AI生成）
- 平台真实入口名：**快手叫「作者声明」**。脚本 `set_ai_declaration(page)` 两步逻辑：① 先点开「作者声明」面板 → ② 在展开面板里选「内容由AI生成」选项。
- ⚠️ **已知缺口（2026-09-02 实测）**：本次发布声明勾选未生效（同抖音）。已改两步逻辑，**下次实跑验证**。best-effort：任一步找不到只告警、不中断发布。

### 平台关键差异（与抖音不同，务必先看！）

1. **没有「存草稿/暂存离开」按钮** —— 发布页底部只有「发布」和「取消」。
   **「取消」会直接丢弃整个作品**（视频都没了），但**快手会自动保留为草稿** ——
   下次进入 `https://cp.kuaishou.com/article/publish/video` 会弹出
   「还有上次未发布的视频，是否继续编辑？」+「继续编辑」/「放弃」。
   点「继续编辑」可恢复视频和封面（描述需要重填）。
2. **没有独立标题框** —— 标题写进「作品描述」(contenteditable) 首行。
3. **没有横屏 4:3 封面** —— 快手封面只有 1 个默认位（正方形自适应，竖屏 3:4 最稳）。
4. **封面注入必须打到弹窗内的 input** —— 选择器是
   `.ant-modal-body input[type="file"][accept*=image]`。
   页面级还有一个同 accept 的 image input，注入它**会被组件忽略，UI 状态错乱、tab 跳回「封面截取」**。
5. **新手引导浮层 `react-joyride` 拦截所有点击** —— 必须先 remove
   `#react-joyride-portal`，否则任何 click 都会被 overlay 吃掉。
6. **裁剪比例在上传后可点：原始比例 / 4:3 / 3:4 / 1:1 / 9:16**（4:3 和 3:4 标「推荐」）。
   3:4 图选 3:4 比例即可。
7. **描述填写必须用 `document.execCommand('insertText')` 触发 React 受控更新**，
   单纯 `keyboard.type` 或 `textContent` 赋值都不会真正写入。

### 草稿恢复 vs. 重新上传

脚本默认行为：
- 导航到上传页
- 若弹出「还有上次未发布的视频」，默认点「继续编辑」恢复
- 检测到页面已有视频（「重新上传」文本）就跳过上传

需要全新发布时加 `--fresh`（点「放弃」重来）和 `--force-upload`（强制重新上传）。

> ⚠️ **草稿视频不符的坑（已实测踩坑 + 已修复）**：快手草稿恢复下点「继续编辑」后，
> `--force-upload` 的 `set_input_files` **无法真正替换视频预览**，页面仍是旧草稿的视频
> （曾导致"还是原来的视频"）。**现已修复**：传入 `--force-upload` 会自动触发「放弃草稿」
> 重来（脚本 `handle_draft(fresh=args.fresh or args.force_upload)`）。
> 因此——**只要目标视频与草稿不同，务必带 `--force-upload`（或不带 `--fresh` 但明确知道草稿即目标）**；
> 若草稿恰是你要发的视频，才用默认的「继续编辑」行为。

### 封面上传正确流程（关键！）

1. 移除 `react-joyride` 浮层
2. 点击 `[class*="_default-cover"]` 打开封面编辑器（ant-modal 弹窗）
3. 在弹窗内点击「上传封面」tab（**叶子节点** `_header-title-item`）
4. **若显示「清空上传」**（草稿恢复时常见），先点
   `._cropper-upload-clear`（**必须是叶子节点，不能点父容器 _cropper-upload**）清掉旧封面
5. 注入到 `.ant-modal-body input[type="file"][accept*=image]`
6. 等待弹窗文本出现「清空上传」（上传成功的标志）
7. 选比例 3:4
8. 点「确认」（modal 内 `_footer-btn`），弹窗关闭后封面即生效

### 文字点击铁律：必须选叶子节点

`click_by_text()` 优先匹配 `children.length === 0` 的元素（真按钮），
**而不是父容器**（内文本相同的祖先元素没 React 事件，点不动）。
「清空上传」同时命中 `_cropper-upload`(836×500) 和 `_cropper-upload-clear`(64×28)，
只有后者带 `cursor:pointer` + `onclick`。

### 已知坑

- 视频 file input 需要等渲染（page.query_selector 异步），脚本内置轮询等待
- 描述框是 contenteditable，**不能**用 `<input>` 选择器；必须 `[class*="_description_"]`
- 描述填完必须派发 InputEvent 才能让 React 知道（execCommand 已自动派发，兜底手动派发）
- 页面级 image file input (i=1) **不是封面上传**，注入它 UI 状态会错乱
- 封面截图文件名不能含冒号（如 `3:4`）—— 内置 `safe_filename()` 清洗

---

## 📌 小红书 + B站（横竖屏自动路由）已迁移至 v1

> 小红书发布、B站发布、`publish_auto.py` 横竖屏路由（横屏→B站 / 竖屏→小红书），
> 现已归属 **`QingFeng-video-publisher`**（v1）技能：
> - v1 脚本在 `QingFeng-video-publisher/scripts/`：`publish_bilibili.py` / `publish_xiaohongshu.py` / `publish_auto.py`
> - 本技能（v2）只负责 **抖音 + 快手** 两个短视频平台。

---

## 核心原则

**推荐入口（v2）**：指定平台直接用 `publish_douyin.py`（抖音）/ `publish_kuaishou.py`（快手）。
所有脚本默认只"暂存离开 / 保持页面"，**最后由你手动点发布**。

通用铁律：先读技能 → 按步骤执行 → 完成后报告用户手动发布。

---

## 📝 获取简介（发布前环节）

发布前先尝试从视频所在文件夹里"自动找稿"，减少手动写简介的工作量。

**机制**：在视频同文件夹内查找相关文档（`.txt` / `.md` / `.docx`），提取其中的介绍文本；
由 LLM（Agent 自身）归纳成**符合平台要求、又能吸引用户**的简介；若文件夹里没有相关文档，则简介留空。

**Step 1 — 提取源文本**（确定性，脚本完成）：
```bash
python scripts/fetch_intro.py --video "<视频路径>" [--platform douyin|kuaishou]
```
- 查找优先级：① 与视频**同名**的文档（`第30期.mp4` → `第30期.txt/.md/.docx`）；
  ② 文件名**含视频名**的文档；③ 文件夹内任意文档；④ **汇总类文稿中按"第N期"标题抽取本集小节**
  （如 `白话诗说-30期文稿汇总.md` 里的「## 第6期」整节）。
- `.docx` 用 `zipfile` 直接读 `word/document.xml` 提取，**无需 python-docx**。
- 输出：找到则打印提取文本；**未找到打印 `__NO_INTRO_FOUND__`**。
- 只搜"视频所在文件夹"，不递归上层目录。

**Step 2 — LLM 归纳成平台简介**（Agent 完成）：
- 若 Step 1 非 `__NO_INTRO_FOUND__`，归纳成一段简介：开门见山点价值 / 悬念，避免官样话；
  **抖音 / 快手简介末尾带 `#教育` 等话题标签**（4-5 个）。
- 把结果作为 `--desc` 传入 `publish_douyin.py` / `publish_kuaishou.py`。
- 若 `__NO_INTRO_FOUND__`，**不传 `--desc`**，简介留空，由你后续手动补。

> 目前为"脚本提取 + Agent 归纳"两段式；若日后要完全无人值守，可把 Step 2 接成 LLM API。

---

## Step 1: 生成封面副本

**每发布到一个平台前都要执行**（封面副本可复用多个平台）。

使用 `scripts/create_cover_copies.py`：
```bash
python scripts/create_cover_copies.py "<视频文件路径>"
```
输出两个副本：
- `{原名}-封面_4x3.jpg`（4:3 横版，2880×2160）
- `{原名}-封面_3x4.jpg`（3:4 竖版，2880×3840）

封面色调需清晰、文字醒目，可适当美化但不得裁剪。

---

## Step 2: 启动浏览器

必须用 Chrome for Testing（不会自动更新），用户 profile 含登录态。

**方式 A（最简单）：双击 `scripts/start_chrome_cdp.cmd`**，自动带 profile 启动并开 CDP。

**方式 B（PowerShell）**：
```powershell
Start-Process "D:\chenw\chrome-win64\chrome.exe" -ArgumentList "--user-data-dir=D:\chenw\chrome-test-profile","--no-first-run","--remote-debugging-port=9222","--remote-allow-origins=*"
```

CDP 端口 9222。

> 🔒 **这两个目录是技能运行依赖，禁止删除**：
> - `D:\chenw\chrome-win64\` —— Chrome for Testing 本体
> - `D:\chenw\chrome-test-profile\` —— **抖音登录态**，删了要重新扫码登录
>
> 另注：从 Git Bash 调用 `.cmd` 会被 MSYS 路径转换坑到（`D:\chenw` 里的 `\c` 被当成 C 盘），请双击或用 PowerShell 执行。

---

## Step 3: 上传视频（旧方法，推荐用 publish_douyin.py）

用 `scripts/upload_video_v9.py`（websockets 直连 CDP）：
```bash
python scripts/upload_video_v9.py <tab_id> <视频文件路径> [cdp_port]
```
**核心方法**：`DOM.setFileInputFiles` 设置文件 → 页面自动跳转 → 等待视频处理完成。

**正确判断方法**：
- 检查 URL 是否包含 `/content/post/video`
- 检查页面是否有"重新上传"文本
- 检查"下一步"按钮是否启用
- 检查 video 元素是否存在

---

## Step 4: 设置封面

**推荐用 `scripts/publish_douyin.py` 自动完成**，详见上方「抖音发布完整流程」。

也可单独只设封面（视频已上传、只想换封面时用）：

```bash
python scripts/set_douyin_cover.py \
  --cover-4x3 "D:/x/封面_4x3.png" \
  --cover-3x4 "D:/x/封面_3x4.png"
```

手动设置要点：
- 抖音 / 快手需要同时设置横屏(4:3)和竖屏(3:4)封面
- **方向必须对应**：4:3 的图进「横封面4:3」槽位，3:4 的图进「竖封面3:4」槽位，传错会被塞进错误槽位
- 图片比例已精确匹配时（1440×1080 / 1080×1440），编辑器裁剪框默认铺满全图，**不需要任何裁剪动作**，直接点「完成」

### 封面是否真的生效？只看两条硬证据

设置完不要凭感觉判断，按以下顺序核验（脚本 `verify_cover_state()` 已自动做）：

1. **看右侧手机预览的图 hash**——取预览区 `<img>` src 里的 32 位 hash，若等于你设置的槽位 hash，说明用户看到的就是上传的图；不等则被回退成视频帧。
2. **看封面专属状态文字**——「封面效果检测通过」「封面检测通过 / 暂未发现封面低质问题」。

### ⚠️ 别被「检测失败」吓到（实测踩过的假警报）

页面右侧「发文助手」面板常出现：

```
作品检测失败
抱歉，当前检测人数过多，请稍后再试
```

这是**作品检测**（整体内容检测，`服务端排队限流`），**与封面毫无关系**。它旁边往往同时写着「封面检测通过」。

**判定时严禁**用 `page.inner_text("body")` 匹配裸子串 `"检测失败"`——会被「作品检测失败」命中而误报。
**必须**用封面专属正则（如 `封面.*?(效果检测|检测|诊断).*?(失败|不通过)`），并显式排除 `作品检测失败|检测人数过多`。

### 选图也会影响检测结论

若封面真的检测未通过（少见），通常是图上**有文字 / 有人物肖像 / AI 生成痕迹重**。换无文字、无人物的朴素图（水墨、风景）最容易通过。

### ⚠️ 过程截图文件名不能带冒号（NTFS 备用数据流陷阱）

`--shot-dir` 的截图文件名取自封面标签，而标签是 `横封面4:3` / `竖封面3:4`——**含冒号**。

在 Windows NTFS 上，冒号是「备用数据流(ADS)」分隔符。文件名 `cover_横封面4:3_uploaded.png` 会被解析成：

- 主文件 `cover_横封面4` —— **0 字节**
- 隐藏数据流 `:3_uploaded.png` —— 真正的图片数据藏在这里

后果极其隐蔽：**不报错、不失败**，`ls` 看是 0 字节，资源管理器看不出真实体积，双击打不开，截图功能等于静默失效。（实测：两个 0 字节文件背后藏了 1.79 MB 数据。）

脚本已内置 `safe_filename()` 统一清洗（`:*?"<>|/\` 全部替换为 `-`），生成 `cover_横封面4-3_uploaded.png` 这类合法名。**任何新增的截图/写文件代码都必须经过它**，不要手拼含标签的文件名。

---

## Step 5: 填写标题简介

用 `scripts/fill_form.py`：
```bash
python scripts/fill_form.py <tab_id> "<标题>" "<简介>"
```

**标题**：`{视频内容主题}：{章节编号} {核心亮点}`

**简介**：写一段引人入胜的介绍，包含视频核心价值，字数 80-150 字。

**自动添加话题**（必须）：在简介末尾添加 4-5 个话题标签，其中必须包含 `#教育`。

---

## Step 6: 勾选 AI 声明

用 JS 在发布页查找并点击「内容由AI生成」相关声明。

---

## Step 7: 暂存离开（不发布）

点击"暂存离开"按钮保存草稿，不点击"发布"。

---

## 脚本说明

| 脚本 | 用途 |
|------|------|
| `publish_douyin.py` | **抖音**：上传视频+双封面+标题简介+暂存离开（2026-09-01 验证） |
| `set_douyin_cover.py` | **封面专用**：只设横 4:3 / 竖 3:4 封面（可独立用，也被主脚本复用），含生效核验 |
| `publish_kuaishou.py` | **快手**：草稿恢复+上传视频+描述+封面+保持页面，手动发布（2026-09-02 验证） |
| `fetch_intro.py` | **获取简介**：视频同文件夹查文档(.txt/.md/.docx)，提取+按"第N期"抽取本集；未找到打印 `__NO_INTRO_FOUND__` |
| `create_cover_copies.py` | 生成 4:3 和 3:4 封面副本 |
| `browser_edge.py` | 启动浏览器，返回 CDP 端口和 tab_id |
| `upload_video_v9.py` | 视频上传（websockets 直连 CDP，旧方法参考） |
| `fill_form.py` | 填写标题、简介、话题（旧方法参考） |

所有脚本与本 SKILL.md 同目录的 `scripts/` 子目录。

---

## 平台差异速查

| 平台 | 视频上传 | 封面 | 话题 | 草稿按钮 |
|------|---------|------|------|---------|
| 抖音 | set_input_files | 竖3:4 + 横4:3 | 简介末尾#教育 | 「暂存离开」（不发布） |
| 快手 | set_input_files | 竖3:4（弹窗内 input） | 描述末尾#教育 | 无按钮。取消会丢稿，刷新自动恢复（「继续编辑」）。默认保持页面，手动发布 |

> 小红书 / B站 见 v1 技能（QingFeng-video-publisher）：横屏→B站、竖屏→小红书。

**最后更新**：2026-09-02
**更新内容**：
- **纠正技能归属**：小红书发布、B站发布、`publish_auto.py` 横竖屏路由（横屏→B站 / 竖屏→小红书）**迁移至 v1（QingFeng-video-publisher）**；本技能（v2）现在**只负责抖音 + 快手**两个短视频平台。同步把对应三个脚本移到 v1/scripts，并重写两个 SKILL.md 的归属描述。
- **修复抖音导航铁律**：`publish_douyin.py` 不能直接 `goto` 发布页 URL（抖音 SPA 不渲染上传组件 → "未找到视频 input"）；改为「创作者首页 → 点「发布视频/高清发布」触发 SPA 跳转」+ goto fallback。
- 抖音发布完整流程（2026-09-01）：视频上传无问题；封面用 `set_douyin_cover.set_both_covers` 实测跑通（JS 强制显示 hover 按钮 → 弹窗内注入 → 点 modal 内「完成」；方向对应；选朴素图避检测回退）。
- 快手发布完整流程（2026-09-02）：草稿自动恢复 + 描述 execCommand + 弹窗内封面 input + 移除 react-joyride + 叶子节点点击铁律。
- 新增「获取简介」发布前环节（`fetch_intro.py` + 技能章节）：支持汇总类文稿按"第N期"抽取本集。

**历史更新**：
- 2026-09-01
  - 修复浏览器关闭问题：禁用 `with` 语句。⚠️ 当时误记为用 `browser.disconnect()`，实测 Playwright 1.62 的 CDP Browser **无此方法**，已改为 `browser.close()`（CDP 下只断连不关浏览器）
  - 抖音封面设置验证成功：自探 `set_douyin_cover.py`（脱离旧逻辑按真实 DOM）；修正方向对应、CDP 下 hover 不触发改用 JS 强制显示、「完成」按钮在 modal 内
  - 修复封面「检测失败」误报：改为「右侧预览 hash 匹配 + 封面专属正则」双重判据，显式忽略「作品检测失败」（服务端排队限流）
