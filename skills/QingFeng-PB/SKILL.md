---
name: QingFeng-PB
description: 文章排版技能（QingFeng-PB）。输入公众号长文和头条短文两篇文章，先用公众号长文排通用版本并生图（1张封面+3-5张插图+背景图），再用头条短文排头条版本并复用通用版生成的图片（不重新生图）。生图工具不写死，按当前Agent环境选择。输出通用版（pb/）和头条版（pb_toutiao/）两套HTML。当用户说「排版这篇文章」「生成排版网页」「把文章做成网页」「PB 一下」或上传文章要求美化排版时使用。
---

# QingFeng-PB 文章排版技能

> 改编自 Coze「自动排版网页内容工作流」（LangGraph 五节点管线）。
> 设计精髓全部保留，**生图工具不写死，按当前 Agent 环境选择**：
> - 文本分析 / CSS 生成 → 本机 LLM（即你，按本技能提示词执行）
> - 图片生成 → **当前 Agent 可用的生图工具**（WorkBuddy 用 agnes-image；豆包用 image_gen/image_edit；其他 Agent 用各自生图能力）
> - HTML 拼装与 ZIP 打包 → 本技能 Python 脚本（确定性、可复现、长文不截断）

---

## 一、能力总览

输入两篇文章：
- **公众号长文**（用于通用排版 + 生图，内容更丰富，生图描述更准确）
- **头条短文**（用于头条排版，复用通用版生成的图片，不重新生图）

输出两个版本：

1. **通用版（`pb/` 目录）** —— 基于公众号长文，含 `preview.html`（base64 内嵌）+ `index.html`（相对路径）+ `cover.jpg` + `illustration_1~N.jpg` + `background.jpg` + `style.css` + `analysis.json`
2. **头条版（`pb_toutiao/` 目录）** —— 基于头条短文，复用通用版图片，含 `preview.html` + `index.html`

全程自动配图、自动识别章节结构、响应式排版。**图片只生成一次（基于公众号长文），头条版直接复用。**

---

## 二、工作流（双版本，6 步）

```
用户输入：公众号长文 + 头条短文
   │
   ▼
① 文本分析（用公众号长文）── 识别标题/章节/段落，定插图数量(3~5张)，出封面+插图描述与插入位置(JSON)
   │
   ▼
② 图片生成（只生成一次）── 封面图 + 插图(3~5) + 背景图，统一 16:9 写实风，落到 pb/ 目录
   │
   ▼
③ CSS 生成（LLM）──── 按【风格】+色调产出纯 CSS，写到 pb/style.css
   │
   ▼
④ 通用版 HTML 拼装 ──── 用公众号长文 + pb/图片 → pb/preview.html + pb/index.html
   │
   ▼
⑤ 头条版 HTML 拼装 ──── 用头条短文 + 复用 pb/图片（复制到 pb_toutiao/）→ pb_toutiao/preview.html + index.html
   │        （不重新生图！通用版生成了几张插图，头条版就插入几张）
   ▼
⑥ 交付：present_files 打开两个 preview.html
```

> **核心原则**：图片只在步骤②生成一次（基于公众号长文），头条版直接复用。通用版生成了 N 张插图，头条版就插入 N 张，不按字数删减。

---

## 三、执行步骤（编排层即你，按此操作）

### 步骤 0：准备输入与产物目录
- **两篇文章输入**：
  - 公众号长文：用于通用排版 + 生图（内容更丰富，生图描述更准确）
  - 头条短文：用于头条排版，复用通用版图片
- 若用户文章开头带 **【风格】** 标记（如 `【国风雅致】`），先记下风格名，再从正文移除该标记再分析。
- 建两个产物目录：
  - 通用版：`<工作目录>/pb/`（生图 + 通用版HTML）
  - 头条版：`<工作目录>/pb_toutiao/`（复用图片 + 头条版HTML）
- 把两篇文章原文分别保存：公众号长文到 `<工作目录>/articles/wechat/article.md`，头条短文到 `<工作目录>/articles/toutiao/article.md`。

### 步骤 1：文本分析（用公众号长文，LLM）
- 读取 `references/prompts.md` 的「一、文本分析」提示词。
- **用公众号长文进行分析**（因为长文内容更丰富，生图描述更准确）。
- `illustration_count` 为 **3~5 张**，根据文章内容丰富度决定：内容丰富、章节多选5张；内容精简选3~4张。不按字数硬定。
- 用提示词产出 **结构化 JSON**（title / theme / mood / content_type / **style** / **color_tone** / illustration_count / cover_image_description / illustration_descriptions[] / image_positions[]）。
- **关键要求**：`style` 和 `color_tone` 是全组图片的统一风格和色调，所有图片必须保持一致；`cover_image_description` 和 `illustration_descriptions` 必须包含具体人物+动作+场景，有故事感，禁止空场景。
- **色调选择规则（重要）**：根据文章内容选择色调，禁止每次都生成黄色/暖色调图片：
  - 技术类、AI类、数据类文章 → 蓝绿色调（深蓝 #1e3a5f + 青绿 #0d9488）
  - 教育类、人文类、文化类文章 → 暖棕色调（#8b4513 + #c9a96e）
  - 生活类、情感类文章 → 柔和粉橙色调
  - 政策类、分析类文章 → 靛蓝商务色调（#4f46e5）
  - 用户明确指定色调时以用户为准
- **防御性修正**（必须）：强制 `illustration_count` 为 3~5 之间的正确值；不足则补描述与位置到正确数量，超出截断。
- 把该 JSON 存为 `<工作目录>/pb/analysis.json`，后续步骤复用。

### 步骤 2：图片生成（当前 Agent 生图工具，建议并行）
- 读取 `references/prompts.md` 的「三、图片生成」提示词。
- **生图工具不写死，按当前 Agent 环境选择**：
  - WorkBuddy → agnes-image（`--ratio 16:9`）
  - 豆包 → `image_gen` 文生图工具（指定 16:9 比例）
  - 其他 Agent → 各自可用的生图能力
- **风格统一规则（最高优先级）**：
  1. 全组图片（封面+插图+背景）必须风格一致，默认写实摄影，禁止混搭
  2. 色调一致，使用 analysis.json 中的 `color_tone`
  3. 封面和插图必须有人物、有具体动作和场景，有故事感，禁止空场景
  4. 所有图片高质量、有吸引力、与文章内容强相关
- 全部 16:9 比例，输出到产物目录，命名固定：
  - `cover.jpg`（1 张，有故事感的场景图，含人物）
  - `illustration_1.jpg` … `illustration_N.jpg`（N = illustration_count，每张与对应段落强相关）
  - `background.jpg`（1 张，浅色无文字，与主图同色调）
- 封面、插图、背景**可并行发起**以提速。
- 若某张生成失败，可重试一次；仍失败则该处留空（HTML 会跳过缺失图，不报错）。

### 步骤 3：CSS 生成（LLM）
- 读取 `references/prompts.md` 的「二、CSS 生成」提示词。
- 传入 title / 【风格】/ theme，产出**纯 CSS**（不要 markdown 包裹）。
- 写到 `<产物目录>/style.css`。必须覆盖类名：`body .container .title .cover-image .intro-text .section .subtitle .sub-subtitle .paragraph .illustration .quote`。
- 背景图用占位符 `BACKGROUND_IMAGE_URL`（脚本会替换为实际背景图）。

### 步骤 4：通用版 HTML 拼装（用公众号长文）
运行 build_html.py 拼装通用版（路径按实际调整）：

```bash
python scripts/build_html.py \
  --article "<工作目录>/articles/wechat/article.md" \
  --css "<工作目录>/pb/style.css" \
  --cover cover.jpg --illustrations "<工作目录>/pb" \
  --background background.jpg \
  --image-positions "<工作目录>/pb/analysis.json" \
  --outdir "<工作目录>/pb"
```

- 生成 `<工作目录>/pb/preview.html`（base64 内嵌，自包含）与 `<工作目录>/pb/index.html`（相对路径）。
- `--illustrations` 传**目录**时脚本自动发现 `illustration_*.jpg` 并排序。

### 步骤 5：头条版 HTML 拼装（用头条短文，复用通用版图片，不重新生图）
- 把通用版生成的图片复制到头条版目录：`cover.jpg`、`background.jpg`、`illustration_1.jpg` ~ `illustration_N.jpg`（N = 通用版生成的插图数量，**全部复制，不删减**）
- 复制 `style.css` 到头条版目录
- 为头条短文生成独立的 `analysis.json`（插图数量 = 通用版生成的插图数量，图片位置按头条短文的章节结构调整）
- 运行 build_html.py 拼装头条版：

```bash
python scripts/build_html.py \
  --article "<工作目录>/articles/toutiao/article.md" \
  --css "<工作目录>/pb_toutiao/style.css" \
  --cover cover.jpg --illustrations "<工作目录>/pb_toutiao" \
  --background background.jpg \
  --image-positions "<工作目录>/pb_toutiao/analysis.json" \
  --outdir "<工作目录>/pb_toutiao"
```

- 生成 `<工作目录>/pb_toutiao/preview.html` 与 `<工作目录>/pb_toutiao/index.html`。
- **关键**：头条版插图数量 = 通用版生成的插图数量，通用版生成了几张就用几张，不按头条短文字数删减。

### 步骤 6：交付
- `present_files` 打开 `<工作目录>/pb/preview.html`（通用版）和 `<工作目录>/pb_toutiao/preview.html`（头条版）。
- 告知用户两个版本的路径和图片数量。

---

## 四、风格标签【风格】

用户在文章开头可写 `【风格名】` 指定视觉基调，例如：`【国风雅致】`、`【科技蓝】`、`【清新简约】`、`【暖橘生活】`。
- 步骤 0 提取风格名 → 步骤 3 作为 CSS 生成的 `page_style` 输入。
- 不写则默认「简洁大方」。
- 风格名仅作 CSS 调性引导，不影响结构与配图逻辑。

---

## 五、防御性规则（务必遵守）

1. **插图数量 3~5 张**，根据文章内容丰富度决定，不按字数硬定。内容丰富、章节多选5张；内容精简选3~4张。头条版复用通用版图片，通用版生成了几张就用几张，不删减。
2. LLM 输出的 `illustration_descriptions` / `image_positions` 数量不对时，**代码/编排层强制修正**到正确数量。
3. **长文不截断**：HTML 由脚本程序化拼装全部章节与段落，绝不依赖 LLM 一次输出整页（避免截断）。
4. **16:9 三重保障**：prompt 强调 + 生图工具指定 16:9 比例 + CSS `aspect-ratio:16/9; object-fit:cover` 兜底。
5. **背景图无文字、低对比**，保证正文可读；CSS 中禁止外部图片 URL（占位符 `BACKGROUND_IMAGE_URL` 由脚本替换）。
6. 任一图片生成失败不阻断整体流程，缺失图在 HTML 中跳过。
7. **全组图片风格色调必须一致**：使用 analysis.json 中的 `style` 和 `color_tone`，禁止写实与卡通混搭，禁止色调跳跃。
8. **封面和插图必须有人物、有场景、有故事感**：禁止空教室、空房间、纯物品等无人单调画面；图片必须与文章内容强相关，能吸引人。
9. **默认写实摄影风**：除非用户明确指定其他风格，否则所有图片使用写实摄影风格。
10. **人物必须是中国人**：所有生成图片中的人物必须是中国人（东亚面孔），除非文章内容明确需要其他种族，否则禁止出现外国人面孔。

---

## 五·五、build_html.py 脚本能力说明（重要）

### image_positions 支持的格式

analysis.json 中的 `image_positions` 支持以下两种格式，脚本都能正确解析：

**格式1：对象数组（推荐）**
```json
"image_positions": [
  {"position": "after_paragraph_3"},
  {"position": "after_section_2"}
]
```

**格式2：字符串数组（LLM 直接输出时常用）**
```json
"image_positions": [
  "after_section_整体架构",
  "after_section_关键设计",
  "before_section_一点感悟",
  "after_paragraph_5"
]
```

字符串格式支持：
- `after_section_章节名` — 插在匹配的章节标题之后（章节名包含匹配，如"整体架构"能匹配"整体架构：技能串联而非单体"）
- `before_section_章节名` — 插在匹配的章节标题之前
- `after_paragraph_N` — 插在第 N 个段落之后
- 无法解析时均匀分配

### 章节标题识别规则

脚本自动识别以下格式的章节标题：
- `一、二、三、` 中文数字序号
- `## 标题` markdown 二级标题
- `结语/前言/引言/附录/总结` 特殊词
- **疑问句短标题**（≤30字，以？/！结尾），如"为什么不用API？"
- **含冒号短标题**（≤30字），如"整体架构：技能串联而非单体"
- 无序号短标题（2~30字，不以句号/逗号等结尾，不含冒号）

### 图片标记处理

脚本会自动跳过以下图片标记，不会当作普通段落：
- `[[ILLU1]]` 占位符（图片由 image_positions 控制插入位置）
- `![描述](路径)` markdown 图片标记（同上）

> **注意**：文章中不需要手动写 `[[ILLU1]]` 或 `![图片]` 标记，图片插入位置完全由 analysis.json 的 image_positions 控制。

---

## 六、关键设计原则（源自原工作流）

- 原子化：分析 / 出图 / 样式 / 拼装 / 打包各司其职。
- LLM 只管「智能」部分（结构分析、CSS 审美），确定性拼装交给脚本，稳定可复现。
- 双版本：通用版（公众号长文+生图）+ 头条版（头条短文+复用图），图片只生成一次。
- 动态规则：按文章内容丰富度决定配图密度（3~5张），不按字数硬定。

---

## 七、不适用场景

- 需要复杂交互（表单、动画逻辑、多页跳转）的网页 —— 本技能只做「单篇图文排版」。
- 需要精确像素级设计稿（如海报、Logo） —— 用 imagegen / agnes-image 单独出图。
- 极短纯文本（<50 字）排版价值低，可建议用户直接发布。

---

## 八、文件清单

```
QingFeng-PB/
├── SKILL.md                      # 本文件
├── references/
│   └── prompts.md               # 文本分析 / CSS / 图片生成 提示词
└── scripts/
    ├── build_html.py            # 文本解析 + 双版本 HTML 拼装
    └── package_zip.py           # 离线 ZIP 打包
```
