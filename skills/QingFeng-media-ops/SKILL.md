---
name: QingFeng-media-ops
description: 轻风全自动媒体运营流水线（编排技能）。把「找热点→三平台文章→文章确认→QingFeng-PB排版生图→CDP进各平台草稿→（可选）视频生成→视频进草稿→日报」串成一条可一键/定时运行的流水线，覆盖头条、公众号、小红书图文与抖音、快手、B站短视频。当用户说"跑一期媒体运营""全自动发布""生成并发布到各平台草稿""媒体运营流水线""按流程发到头条公众号小红书和抖音快手B站""全自动媒体运营"时触发。所有发布一律走 CDP 进草稿箱，绝不直接点发布；统一使用 Chrome for Testing。
---

# 轻风全自动媒体运营流水线 QingFeng-media-ops

> 编排技能：本身不重复造轮子，按路径调用本机既有技能 + 本技能补齐的发布器/排版脚本。
> 技能库根目录：`D:\chenw\AgentSpace\.agents\skills`（113 个技能，按绝对路径调用）。

## 一、铁律（不可违反）

1. **只进草稿，绝不发布**：任何平台脚本都禁止点击「发布/发表/投稿」，一律点「存草稿/保存草稿」，最终发布由用户手动。
2. **全部个人账号、无认证、无 API**：发布统一走 **CDP（Chrome DevTools Protocol）**。
3. **统一浏览器**：图文和视频全部用 **Chrome for Testing**（`D:\chenw\chrome-win64\chrome.exe`，profile `D:\chenw\chrome-test-profile`，端口 9222），不用 Edge。该 profile 必须已登录全部六个平台。
4. **技能按路径调用**：不要依赖运行时自动发现。先用「技能发现」找到技能和路径，再按绝对路径 Read 其 SKILL.md / 运行其 scripts。
5. **每步有质检**：上一步产物不合格，禁止进入下一步。
6. **用户第一人称「轻风教育」**：写作用 `QingFeng-writing` 文风约束，禁止用「宿松县教育局」代指，遵守其写作禁忌红线。
7. **停止工作绝不关闭浏览器**：脚本结束后 Chrome for Testing 保持打开，停留在最后操作的页面。禁止用 `with sync_playwright()`（退出时会杀浏览器），必须手动管理 playwright 生命周期。

## 一·五、技能发现（双保险：原生发现 + 索引）

> 技能库 `D:\chenw\AgentSpace\.agents\skills`（113 个技能）。

**原生发现已恢复**：`C:\Users\chenw\Doubao\skills`（应用注册的技能根）已用 junction 指向共享技能库，应用级助手即可自动发现、自动触发全部 113 个技能（新会话生效）。若未来升级再次失效，重建 junction：
```powershell
Remove-Item "C:\Users\chenw\Doubao\skills" -Force -ErrorAction SilentlyContinue
cmd /c mklink /J "C:\Users\chenw\Doubao\skills" "D:\chenw\AgentSpace\.agents\skills"
```

**Plan B 索引仍保留作备份/给其他助手用**：
- 索引文件：`D:\chenw\AgentSpace\.agents\skills_index.md`（人读）、`...skills_index.json`（机器读）
- 重建：`python D:\chenw\AgentSpace\.agents\skills\QingFeng-media-ops\scripts\build_skills_index.py`
- 关键词搜索：`... --search 发布` / `... --search 视频`
- 调用套路：查索引拿 `path` → Read `{path}/SKILL.md` → 按路径运行 scripts。

## 二、运行方式

- **一键跑全链**：按「四、标准流水线」Step 0→Step 7 顺序执行。
- **定时跑**：用定时任务技能设置 cron（建议每日 08:00 生成内容、10:00 进草稿）。
- **单环节跑**：可只执行某一 Step（如只出文章、只发视频），用 `manifest.py` 记录断点。

## 三、输出目录约定

所有内容统一放在 `D:\知识库\媒体运营` 下，每天一个以当天日期命名的文件夹（格式 `YY.M.D`，如 `26.8.31`）。用户明确指定其他路径时除外。

```
D:\知识库\媒体运营\{YY.M.D}\            # 当天批次根（如 26.8.31）
├── manifest.json                      # 批次清单（断点续跑）
├── articles/                          # Step1 文章（QingFeng-rdxz 产物，纯文本不带图）
│   ├── toutiao/article.md             # 头条版本（短文 800~1500字）→ 头条排版
│   ├── wechat/article.md              # 公众号版本（长文 2000~4000字）→ 通用排版生图 + 公众号排版
│   └── xiaohongshu/article.md         # 小红书版本（精简 500~800字）→ 小红书排版
├── pb/                                # Step2 QingFeng-PB 通用排版生图（用公众号长文生图）
│   ├── preview.html / index.html / cover.jpg / illustration_1~5.jpg / background.jpg
├── pb_toutiao/                        # Step2 头条版排版（复用 pb/ 图片，不重新生图）
│   ├── preview.html / index.html
├── covers/                            # Step2.5 多平台封面（QingFeng-Cover）
│   ├── cover_titled_16x9.jpg / cover_4x3.jpg / cover_3x4.jpg / cover_235x1.jpg / cover_1x1.jpg
├── formatted/                         # Step3 平台专用排版
│   ├── wechat.html（QingFeng-GZH-Layout，图片复用 pb/ 目录）
│   └── xhs.txt（QingFeng-XHS-Layout，图片发布时单独上传 pb/ 目录）
├── videos/                            # Step4 视频产物
│   └── html_video/（hyperframes项目）
├── screenshots/                       # 各平台进草稿截图
└── report.md                          # Step7 日报
```

### 文章—排版—图片对应关系（铁律）

| 平台 | 文章来源 | 排版技能 | 图片来源 |
|---|---|---|---|
| 头条/百家 | `articles/toutiao/article.md`（短文） | QingFeng-PB 头条版排版（pb_toutiao/） | **复用 pb/ 目录的图**（不重新生图） |
| 公众号 | `articles/wechat/article.md`（长文） | QingFeng-PB 通用排版（生图）→ QingFeng-GZH-Layout | **统一用 pb/ 目录的图** |
| 小红书 | `articles/xiaohongshu/article.md`（精简） | QingFeng-XHS-Layout | **统一用 pb/ 目录的图**（发布时单独上传） |

> **排版顺序（重要）**：先用公众号长文跑 QingFeng-PB 通用排版生图（因为长文内容更丰富，生图描述更准确），再用头条短文跑 QingFeng-PB 排版但**复用通用版已生成的图片**（不重新生图），最后用 QingFeng-GZH-Layout 对公众号长文做公众号专属排版。
>
> 所有配图只在 QingFeng-PB 通用版中生成一次（pb/ 目录），各平台排版和发布均复用此目录图片，不再重复生图。

## 四、标准流水线

### Step 0：启动 Chrome for Testing（统一 CDP 入口）

```bash
python {skills_root}/QingFeng-media-ops/scripts/ensure_cft.py
```
- 已运行则跳过；未运行则启动（端口 9222，profile `D:\chenw\chrome-test-profile`）。
- **首次使用**：在该 Chrome 中手动登录 公众号、头条、小红书、抖音、快手、B站 六个平台，登录态会保存到 profile。
- 验证：`python ensure_cft.py --check` 返回 `[OK]`。

### Step 1：找热点 + 生成三平台文章

调用 `QingFeng-rdxz`（其内部写作使用 `QingFeng-writing` 文风）：
- 全网搜索泛教育热点，三维加权遴选主题；
- 按头条/公众号/小红书三平台各写一篇（随笔/论文/小故事三体裁）；
- 产物落到 `{output_root}/{YY.M.D}/articles/`。

调用前 Read `{skills_root}/QingFeng-rdxz/SKILL.md` 按其标准流程执行。
> **选题确认环节归属**：rdxz 标准流程内含「步骤二·五　选题确认（候选表 → 用户确认/给主题 → 1分钟超时自定）」。本流水线**不在此重复选题确认**，直接接收 rdxz 确认后的选题及其三篇文章，再进入 Step 1.5 文章确认。
**质检**：三篇文章均存在、标题合规、无「宿松县教育局」代指、符合 QingFeng-writing 红线。
**字数自检（铁律）**：头条 800~1500 字（短文快节奏）、公众号 2000~4000 字（长文深度）、小红书 500~800 字（精简短句）。不符合则调整后再进入下一步。**绝对不能把头条写成长文、公众号写成短文。**

### Step 1.5：文章确认环节（强制）

三类文章写完后，**必须暂停并向用户展示确认选项**，不得直接进入排版环节：

```
✅ 三平台文章已生成完成：
- 头条版：{标题}（{字数}字）
- 公众号版：{标题}（{字数}字）
- 小红书版：{标题}（{字数}字）

请选择：
  [1] 继续下一步（排版生图）
  [2] 修改文章后再继续（请说明修改意见）

⏰ 1分钟后未回复将自动继续下一步。
```

- 用户回复「1」或「继续」→ 进入 Step 2 排版生图。
- 用户回复修改意见 → 按意见修改对应平台文章，修改后再次展示确认选项。
- **1分钟（60秒）后未收到用户回复 → 自动继续下一步**（无需等待）。
- 确认环节只在文章生成后出现一次，后续环节（排版/发布）不再暂停确认。

### Step 2：通用排版生图（QingFeng-PB，双版本）

调用 `QingFeng-PB`，按双版本流程执行：

**第一阶段：通用版（用公众号长文生图）**
- 用公众号长文（`articles/wechat/article.md`）进行文本分析，定插图数量 3~5 张（按内容丰富度，不按字数）；
- 调用当前 Agent 生图工具生成封面+插图+背景图（色调按文章内容选择：技术类蓝绿、教育类暖棕、生活类粉橙、政策类靛蓝，禁止每次都黄色）；
- 生成 CSS，运行 `build_html.py` 拼装通用版 HTML；
- 产物落到 `{YY.M.D}/pb/`（preview.html + index.html + cover.jpg + illustration_1~N.jpg + background.jpg + style.css + analysis.json）。

**第二阶段：头条版（用头条短文，复用图片）**
- 把 pb/ 目录的图片全部复制到 pb_toutiao/（生成几张用几张，不删减）；
- 用头条短文（`articles/toutiao/article.md`）生成独立的 analysis.json（插图数量 = 通用版生成的插图数量）；
- 运行 `build_html.py` 拼装头条版 HTML；
- 产物落到 `{YY.M.D}/pb_toutiao/`。

调用前 Read `{skills_root}/QingFeng-PB/SKILL.md`。
**质检**：两个 preview.html 可正常打开、无 `[[ILLU*]]` 残留、图片非空、标题无 `#` 前缀、全组图片风格色调一致。

### Step 2.5：多平台封面（QingFeng-Cover）

用 pb/cover.jpg 为底，加文章标题，输出 5 种比例封面：
```bash
python {skills_root}/QingFeng-Cover/scripts/make_cover.py \
  --base "{YY.M.D}/pb/cover.jpg" \
  --title "{文章标题}" \
  --subtitle "{副标题}" \
  --outdir "{YY.M.D}/covers/"
```
产物：cover_titled_16x9.jpg、cover_4x3.jpg（头条/B站横版）、cover_3x4.jpg（小红书/抖音竖版）、cover_235x1.jpg、cover_1x1.jpg。
**改尺寸用直接拉伸（Image.resize），不裁剪不填充。**

### Step 3：平台专用排版

| 平台 | 排版技能 | 输入文章 | 图片来源 | 输出 |
|---|---|---|---|---|
| 公众号 | QingFeng-GZH-Layout | articles/wechat/article.md | pb/ 目录（--image-dir） | formatted/wechat.html（全内联样式） |
| 小红书 | QingFeng-XHS-Layout | articles/xiaohongshu/article.md | pb/ 目录（发布时单独上传） | formatted/xhs.txt（emoji 纯文本） |

公众号排版示例：
```bash
python {skills_root}/QingFeng-GZH-Layout/scripts/gzh_layout.py \
  --input {YY.M.D}/articles/wechat/article.md \
  --output {YY.M.D}/formatted/wechat.html \
  --style keji --image-dir {YY.M.D}/pb/
```

小红书排版示例：
```bash
python {skills_root}/QingFeng-XHS-Layout/scripts/xhs_layout.py \
  --input {YY.M.D}/articles/xiaohongshu/article.md \
  --output {YY.M.D}/formatted/xhs.txt \
  --style ganhuo --tags "教育,AI自动化,媒体运营"
```

**质检**：公众号 HTML 全内联样式无 class、图片路径正确；小红书 txt 分段合理、emoji 不超过 5 种、话题标签无重复、无 `##` 前缀残留。

### Step 4：图文发布（CDP 进草稿）

三个平台分别执行，全部连 Chrome for Testing :9222：

| 平台 | 技能/脚本 | 输入 | 说明 |
|---|---|---|---|
| 头条 | `{skills_root}/QingFeng-toutiao-publisher/scripts/publish.py` | pb_toutiao/index.html + --tags | 脚本自动导航到编辑器，填标题/正文/图片/话题标签，截图存证 |
| 公众号 | `{skills_root}/QingFeng-wechat-publisher/scripts/publish_wechat.py` | formatted/wechat.html + --author | 先上传图片拿CDN URL，再 execCommand 一次性注入，保存草稿即结束 |
| 小红书 | `{skills_root}/QingFeng-xiaohongshu-publisher/scripts/publish_xiaohongshu.py` | formatted/xhs.txt + pb/ 封面内图 | 上传图片后粘贴文本，暂存不发布 |

头条发布示例：
```bash
python {skills_root}/QingFeng-toutiao-publisher/scripts/publish.py \
  {YY.M.D}/pb_toutiao/index.html \
  --tags "#教育 #AI自动化 #媒体运营 #效率工具"
```
> 话题标签必须含 `#教育`，另根据文章生成 3 个相关话题。publish.py 会自动导航到 `mp.toutiao.com/profile_v4/graphic/publish`，无需手动导航。

公众号发布示例：
```bash
python {skills_root}/QingFeng-wechat-publisher/scripts/publish_wechat.py \
  {YY.M.D}/formatted/wechat.html --author "轻风教育"
```
> 公众号只保存草稿，不设封面/原创/来源（由用户手动设置）。脚本结束后浏览器保持打开。

- 每个脚本执行后截图存 `screenshots/{平台}.png`，并在 manifest 登记状态（成功/需人工/失败）。
- 退出码约定：0=成功进草稿，42=需人工（登录/验证码），1=其他失败。
- **绝不点发布按钮**。
- **脚本结束后浏览器保持打开**，停留在最后操作的页面。

### Step 4.5：视频生成确认环节（强制）

图文发布完成后，**必须暂停并向用户展示视频生成确认选项**，不得直接进入视频生成：

```
✅ 三平台图文已发布完成（均为草稿）：
- 头条：{状态}
- 公众号：{状态}
- 小红书：{状态}

是否生成短视频？
  [1] 继续生成视频（默认 HTML 类，用公众号排版文本和图片）
  [2] 指定视频类型或要求（如：写实类/动漫类/指定时长/指定风格等）
  [3] 跳过视频，直接结束

⏰ 1分钟后未回复将自动继续（默认生成 HTML 类视频）。
```

- 用户回复「1」或「继续」→ 进入 Step 5，默认用 hyperframes 生成 HTML 类视频。
- 用户回复「2」或具体要求 → 按要求选择视频类型（hyperframes HTML 类 / QingFeng-video-poem 写实或动漫类），调整参数后生成。
- 用户回复「3」或「跳过」→ 跳过 Step 5 和 Step 6，直接进入 Step 7 日报。
- **1分钟（60秒）后未收到用户回复 → 自动继续**（默认生成 HTML 类视频，无需等待）。
- 确认环节只在图文发布后出现一次。

### Step 5（可选）：生成短视频

仅当用户要求视频时执行。按内容类型选择：

| 内容类型 | 技能 | 说明 |
|---|---|---|
| HTML 类（信息图/数据/文字动效） | `hyperframes` | 从 HTML composition 渲染视频，Read `{skills_root}/hyperframes/SKILL.md` |
| 动漫/写实类（故事/剧情/人物） | `QingFeng-video-poem` | 动漫或写实风格短视频，Read `{skills_root}/QingFeng-video-poem/SKILL.md` |

- 视频规格：抖音/快手 9:16、30-60s；B站 16:9、1-3min。
- 产物落到 `{YY.M.D}/videos/`，含成片 + 封面。
- **质检**：成片可播放、时长合规、字幕无溢出、配音无跳句漏读。
- hyperframes 需系统 Node v24+，设 `HYPERFRAMES_BROWSER_PATH=D:\chenw\chrome-win64\chrome.exe`。
- **⚠️ hyperframes 中文路径编码问题（2026-09-03 实测）**：hyperframes 的 CLI 在 Windows 上处理含中文的输出路径时，可能把 UTF-8 编码的中文路径错误解析为 GBK，导致在 D 盘根目录创建乱码文件夹（如 `鐭ヨ瘑搴揬濯掍綋杩愯惀` = `知识库\媒体运营`）。**预防措施**：
  1. 调用 hyperframes 前，先在 PowerShell 中设置 `[Console]::OutputEncoding = [System.Text.Encoding]::UTF8` 和 `$env:PYTHONIOENCODING = "utf-8"`；
  2. 或先在英文临时路径（如 `D:\temp\video_gen\`）生成视频，完成后再移动到 `{YY.M.D}/videos/`；
  3. 生成后检查 D 盘根目录是否有乱码文件夹，若有则将其内容合并到正确日期目录后删除。

### Step 6：视频发布（CDP 进草稿）

| 平台 | 技能/脚本 | 输入 | 草稿机制 |
|---|---|---|---|
| 抖音 | `QingFeng-video-publisher-v2/scripts/publish_douyin.py` | 成片 + cover_4x3 + cover_3x4 + 标题简介 | 点「暂存离开」存草稿 |
| 快手 | `QingFeng-video-publisher-v2/scripts/publish_kuaishou.py` | 成片 + cover_3x4 + 描述 | 无草稿按钮，点「取消」自动存草稿 |
| B站 | `QingFeng-video-publisher/scripts/publish_bilibili.py` | 成片 + cover_4x3 + 标题简介标签 | 点「存草稿」 |
| 小红书 | `QingFeng-video-publisher/scripts/publish_xiaohongshu.py` | 成片 + cover_3x4 + 标题正文 | 无草稿按钮，填好自动存草稿 |

**横竖屏路由**：横屏（宽≥高）发 B站，竖屏（高>宽）发小红书。可用 `publish_auto.py` 自动路由。

抖音发布示例：
```bash
python {skills_root}/QingFeng-video-publisher-v2/scripts/publish_douyin.py \
  --video "{YY.M.D}/videos/...mp4" \
  --cover-4x3 "{YY.M.D}/covers/cover_4x3.jpg" \
  --cover-3x4 "{YY.M.D}/covers/cover_3x4.jpg" \
  --title "{标题}" --desc "{简介}" --save-draft
```

**视频发布关键坑点（实测验证）**：
1. **抖音**：设完双封面后，封面编辑器弹窗（dy-creator-content-modal）可能仍打开，会拦截「暂存离开」按钮。必须先点弹窗内「完成」关闭弹窗，再点「暂存离开」。
2. **快手**：无「暂存离开」按钮，只有「发布」和「取消」。点「取消」会自动保存为草稿（下次进入提示"还有上次未发布的视频"）。取消按钮可能在视口外，需 `scrollIntoView` 后再点击。
3. **小红书视频**：网页端无草稿按钮，唯一按钮是「发布笔记」。脚本只填表单绝不点发布，填好后网页自动存草稿。封面设置的「应用」「完成」按钮必须用真实鼠标坐标点击（JS click 会静默失败）。
4. **封面图选择**：带文字/人物/强AI痕迹的图可能被抖音「封面效果检测」回退成视频帧，用无文字无人物的朴素图最稳。

- **统一用 Chrome for Testing :9222**。
- 每个平台截图存 `screenshots/{平台}_video.png`，manifest 登记状态。
- **绝不点发布/投稿按钮**。
- **脚本结束后浏览器保持打开**。

### Step 7：登记 + 日报

```bash
python {skills_root}/QingFeng-media-ops/scripts/manifest.py update --date {YY.M.D} --key articles.toutiao --value "路径"
python {skills_root}/QingFeng-media-ops/scripts/report.py --date {YY.M.D}
```
- 日报 `report.md` 含：选题、三平台文章状态、排版状态、配图、视频、各平台草稿状态表、需人工项。
- 交付：present_files 展示 report.md + 关键产物路径。

## 五、断点续跑

- `manifest.py` 记录每步状态，中断后从失败步继续，不重跑已完成步。
- 常用命令：
  ```bash
  python manifest.py init {批次目录} --topic "选题"
  python manifest.py update {批次目录} step3.toutiao=success
  python manifest.py get {批次目录}
  python manifest.py list {output_root}
  ```

## 六、参考文件

- `references/pipeline.md` — 流水线技能映射表（每步对应哪个技能、哪个脚本、输入输出）
- `references/cdp_guide.md` — CDP 连接规范（Chrome for Testing 启动/各平台进草稿入口/表单注入/风控）
- `references/platform_spec.md` — 平台规格矩阵（图文三平台+视频三平台+封面规范+AI标注）
- `assets/config.yaml` — 配置（账号定位/CDP/平台规格/技能索引路径）
