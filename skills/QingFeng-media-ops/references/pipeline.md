# 流水线技能映射（QingFeng-media-ops）

> 本技能不重复造轮子。每个环节按绝对路径调用既有技能；本技能只补齐缺口
> （技能索引、CFT启动保障、manifest/日报）并负责编排。
> 技能库根：`D:\chenw\AgentSpace\.agents\skills`
> 统一浏览器：Chrome for Testing :9222（图文+视频全部）

## 目录规范（最高优先级）

- **内容根目录**：`D:\知识库\媒体运营\`
- **每日目录**：`D:\知识库\媒体运营\YY.M.D\`（如 `26.8.31`，年后两位.月.日）
- **每日目录只放内容产物**，绝对禁止放调试脚本、测试文件、临时补丁：
  - ✅ 允许：文章(.md/.txt)、图片(.jpg/.png)、排版HTML、视频(.mp4)、封面、manifest.json、截图
  - ❌ 禁止：.py调试脚本、.ps1/.bat临时脚本、patch_*.py、test_*.py、inspect_*.py
- **所有技能脚本放在技能目录**：`D:\chenw\AgentSpace\.agents\skills\<技能名>\scripts\`
- **调试时临时脚本放系统临时目录**（如 `%TEMP%`），调试完成后删除，不得留在内容目录
- 如需保留调试经验，写入对应技能的 SKILL.md「踩坑记录」 section

## 每日目录标准结构

```
D:\知识库\媒体运营\26.8.31\
├── articles/           # 三平台文章原文
│   ├── toutiao/article.md
│   ├── wechat/article.md
│   └── xiaohongshu/article.md
├── pb/                 # 通用排版生图（QingFeng-PB产物）
│   ├── cover.jpg       # 基础封面（16:9）
│   ├── illustration_1.jpg ~ illustration_N.jpg
│   ├── background.jpg
│   ├── preview.html    # 预览版（base64内嵌）
│   └── index.html      # 下载版（相对路径）
├── covers/             # 多平台封面（QingFeng-Cover产物）
│   ├── cover_titled_16x9.jpg
│   ├── cover_4x3.jpg
│   ├── cover_3x4.jpg
│   ├── cover_235x1.jpg
│   └── cover_1x1.jpg
├── formatted/          # 平台适配排版
│   ├── toutiao.html    # 头条版（通用排版HTML）
│   ├── wechat.html     # 公众号版（QingFeng-GZH-Layout）
│   └── xiaohongshu.txt # 小红书版（QingFeng-XHS-Layout）
├── videos/             # 视频产物
│   └── html_video/     # hyperframes项目
├── screenshots/        # 发布后截图
└── manifest.json       # 批次清单
```

## 技能发现（双保险）

- 原生发现：`C:\Users\chenw\Doubao\skills` junction → 技能库根（新会话自动发现）
- Plan B 索引：`D:\chenw\AgentSpace\.agents\skills_index.md`（人读）/ `.json`（机器读）
- 重建/搜索：`python D:\chenw\AgentSpace\.agents\skills\QingFeng-media-ops\scripts\build_skills_index.py [--search 关键词]`
- 调用套路：查索引拿 `path` → Read `{path}/SKILL.md` → 按路径运行 scripts。

## 环节 → 调用对象（真实链路）

| Step | 环节 | 调用技能/脚本（绝对路径） | 输入 | 输出 | CDP |
|---|---|---|---|---|---|
| 0 | 启动浏览器 | 本技能 `scripts/ensure_cft.py` | — | Chrome for Testing :9222 | — |
| 1 | 热点+三平台文章 | `QingFeng-rdxz`（内部用 `QingFeng-writing` 文风） | 热点主题 | articles/ 三平台文章 | — |
| 2 | 通用排版生图（公众号长文） | `QingFeng-PB/scripts/build_html.py` + 当前Agent生图工具 | 公众号版文章 | pb/ preview.html + cover.jpg + illustration_1~5.jpg + background.jpg | — |
| 2.1 | 头条排版（复用通用版图片，不重新生图） | `QingFeng-PB/scripts/build_html.py` | 头条版文章 + pb/图片 | pb_toutiao/ preview.html + index.html | — |
| 2.5 | 多平台封面 | `QingFeng-Cover/scripts/make_cover.py` | pb/cover.jpg + 标题 | covers/ 5种比例封面 | — |
| 2.6 | 公众号排版 | `QingFeng-GZH-Layout/scripts/gzh_layout.py` | 公众号文章 + pb/图片 | formatted/wechat.html | — |
| 2.7 | 小红书排版 | `QingFeng-XHS-Layout/scripts/xhs_layout.py` | 小红书文章 | formatted/xiaohongshu.txt | — |
| 3a | 头条发布 | `QingFeng-toutiao-publisher/scripts/publish.py` | pb_toutiao/index.html + covers/cover_4x3.jpg | 进草稿+截图 | CFT :9222 |
| 3b | 公众号发布 | `QingFeng-wechat-publisher/scripts/publish_wechat.py` | formatted/wechat.html | 进草稿+截图 | CFT :9222 |
| 3c | 小红书发布 | `QingFeng-xiaohongshu-publisher/scripts/publish_xiaohongshu.py` | formatted/xiaohongshu.txt + covers/cover_3x4.jpg + pb/illustration_*.jpg | 进草稿+截图 | CFT :9222 |
| 4 | 视频生成（可选） | HTML类 → `hyperframes`；动漫/写实类 → `QingFeng-video-poem` | 文章/脚本 + pb/图片 | videos/ 成片+封面 | — |
| 5a | 抖音+快手发布 | `QingFeng-video-publisher-v2`：`publish_douyin.py`（双封面4:3+3:4）+ `publish_kuaishou.py`（单封面3:4） | 成片+covers/封面+标题简介 | 进草稿+截图 | CFT :9222 |
| 5b | B站+小红书发布 | `QingFeng-video-publisher`：`publish_auto.py` 横竖屏自动路由（横→B站`publish_bilibili.py`，竖→小红书`publish_xiaohongshu.py`） | 成片+封面+标题简介标签 | 进草稿+截图 | CFT :9222 |
| 6 | 登记+日报 | 本技能 `scripts/manifest.py` + `scripts/report.py` | 批次状态 | manifest.json + report.md | — |

## 排版与发布对应约定

| 平台 | 文章版本 | 排版技能 | 发布技能 | 封面比例 |
|------|---------|---------|---------|---------|
| 头条 | 头条版（短文） | QingFeng-PB（复用通用版图片，不重新生图） | QingFeng-toutiao-publisher | 4:3 |
| 公众号 | 公众号版（长文） | QingFeng-PB（通用排版，先生图）→ QingFeng-GZH-Layout | QingFeng-wechat-publisher | 正文首图作封面 |
| 小红书 | 小红书版（短文） | QingFeng-XHS-Layout | QingFeng-xiaohongshu-publisher | 3:4 |

> **排版顺序（重要）**：先用公众号长文跑 QingFeng-PB 通用排版生图（因为长文内容更丰富，生图描述更准确），再用头条短文跑 QingFeng-PB 排版但**复用通用版已生成的图片**（不重新生图），最后用 QingFeng-GZH-Layout 对公众号长文做公众号专属排版。
>
> 所有配图统一使用 QingFeng-PB 生成的 illustration_*.jpg，各平台排版不单独生图。
>
> **色调规则**：技术类/AI类文章用蓝绿色调，教育类/人文类用暖棕色调，禁止每次都生成黄色图片。详见 QingFeng-PB SKILL.md。

## 视频发布详细约定（Step 5）

### 封面比例对应

| 平台 | 视频方向 | 所需封面 | 封面来源 |
|------|---------|---------|---------|
| 抖音 | 任意 | 横4:3 + 竖3:4（双封面） | covers/cover_4x3.jpg + cover_3x4.jpg |
| 快手 | 任意 | 竖3:4（单封面） | covers/cover_3x4.jpg |
| B站 | 横屏（宽≥高） | 横4:3 | covers/cover_4x3.jpg |
| 小红书 | 竖屏（高>宽） | 竖3:4 | covers/cover_3x4.jpg |

### 草稿策略（所有平台统一）

- **抖音**：脚本点「暂存离开」保存草稿，不发布
- **快手**：无草稿按钮，脚本填完后保持页面打开，由用户手动点「发布」（点「取消」会丢稿，但快手自动保留草稿）
- **B站**：脚本点「存草稿」暂存离开，不发布
- **小红书**：无草稿按钮，脚本只填表单不点「发布笔记」，网页自动存草稿

### 发布前获取简介

两技能共用 `QingFeng-video-publisher-v2/scripts/fetch_intro.py`：
- 在视频同文件夹查找 .txt/.md/.docx，提取介绍文本
- 支持汇总类文稿按"第N期"标题抽取本集小节
- 由 Agent 归纳成平台简介（抖音/快手末尾带 #教育 等话题）

### 浏览器铁律

- 所有脚本用 `p = sync_playwright().start()` 手动管理，**禁止 `with sync_playwright()`**（with 退出会关闭外部浏览器）
- CDP 连接下 `browser.close()` 只断连不杀浏览器（Playwright CDP Browser 无 `disconnect()` 方法）
- 脚本结束后浏览器保持打开，停在最后一步

## 本技能补齐的脚本

| 脚本 | 用途 | 状态 |
|---|---|---|
| `scripts/ensure_cft.py` | Chrome for Testing 启动保障（统一 CDP 入口） | ✅ |
| `scripts/manifest.py` | 批次清单（init/update/get/list，断点续跑） | ✅ |
| `scripts/report.py` | 日报生成 | ✅ |
| `scripts/build_skills_index.py` | 技能索引生成器 | ✅ |

> 视频发布脚本已全部迁移至独立技能：抖音/快手 → `QingFeng-video-publisher-v2`，B站/小红书 → `QingFeng-video-publisher`。

## 首跑建议

1. 先跑 Step 0-2.7（启动→热点文章→排版生图→多平台封面→三平台排版），不发布，人工核一遍质量。
2. 再开发布，先灰度 头条+公众号（已有成熟发布器，已验证成功）。
3. 小红书图文发布器实机联调通过后再纳入全平台。
4. 视频环节（Step 4-5）：抖音/快手/B站发布脚本已验证，小红书视频发布待实机联调；单独验证后再并入定时。
5. 稳定后全平台 + 定时运行。
