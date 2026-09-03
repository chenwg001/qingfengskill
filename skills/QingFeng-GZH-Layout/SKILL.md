---
name: QingFeng-GZH-Layout
description: 公众号排版技能（QingFeng-GZH-Layout）。两种模式：①HTML优化模式（全链条用）：把QingFeng-PB生成的通用HTML的外部CSS转为内联样式，让公众号编辑器能渲染；②markdown排版模式（单独使用）：把markdown文章转成公众号编辑器可直接粘贴的内联样式HTML，支持国风雅致/简约清新/科技商务/杂志深度/治愈温暖五套风格。当用户说"公众号排版""排个公众号版""生成公众号HTML""GZH排版""优化公众号HTML"时使用。
---

# QingFeng-GZH-Layout 公众号排版技能

> 核心原则：生成的 HTML **全内联样式、section 嵌套**，公众号编辑器粘贴后样式不丢失。
> 不使用 class、外部 CSS、Flex 布局、CSS 变量（公众号编辑器会清洗这些）。

## 一、两种模式

### 模式1：HTML 优化模式（`--mode html`，全链条使用）

**适用场景**：在 QingFeng-media-ops 全链条中，QingFeng-PB 已生成通用 HTML（含外部 CSS），需要优化为公众号编辑器能渲染的内联样式 HTML。

**做什么**：
- 把 `<style>` 中的外部 CSS 转为每个元素的内联 `style=""` 属性
- 移除所有 `class` 属性和 `<style>` 标签
- 图片相对路径转为绝对路径
- 用 `<section>` 包裹内容（公众号编辑器偏好 section 嵌套）

**用法**：
```bash
python {skill_dir}/scripts/gzh_layout.py \
  --mode html \
  --input  {date}/pb/index.html \
  --output {date}/formatted/wechat.html \
  --image-dir {date}/pb/
```

**参数说明**：
- `--mode html`：HTML 优化模式
- `--input`：QingFeng-PB 生成的通用 HTML（index.html）
- `--output`：输出的公众号 HTML 路径
- `--image-dir`：图片目录，用于把相对路径转为绝对路径

### 模式2：markdown 排版模式（`--mode md`，单独使用，默认）

**适用场景**：单独使用本技能，把一篇 markdown 文章从零排版成公众号风格的 HTML。

**做什么**：
- 解析 markdown 结构（标题/小标题/段落/图片/引用/列表/分割线）
- 按选定风格生成全内联样式的 section 嵌套 HTML
- 支持五套风格

**用法**：
```bash
python {skill_dir}/scripts/gzh_layout.py \
  --mode md \
  --input  article.md \
  --output gzh_article.html \
  --style keji \
  --author 轻风教育 \
  --image-dir D:/path/to/images
```

**参数说明**：
- `--mode md`：markdown 排版模式（默认，可省略）
- `--input`：markdown 文章路径
- `--output`：输出 HTML 路径
- `--style`：排版风格，默认 `jianyue`
- `--author`：文末署名，默认 `轻风教育`
- `--image-dir`：图片目录，`[[ILLU1]]` 标记自动在此查找 `illu1.jpg/png` 或 `illustration_1.jpg/png`

## 二、五套排版风格（仅 markdown 模式）

| 风格 | 适用场景 | 主色调 | 特点 |
|---|---|---|---|
| `guofeng` 国风雅致 | 教育、文化、人文类 | 暖棕 #8b4513 | 背景色块小标题、左竖线引用 |
| `jianyue` 简约清新 | 通用、科技、生活 | 蓝灰 #2c3e50 | 浅蓝小标题、清爽行距 |
| `keji` 科技商务 | 政策、数据、分析 | 靛蓝 #4f46e5 | 靛蓝强调、紧凑排版 |
| `zazhi` 杂志深度 | 深度长文、评论、人物 | 纯黑 #1a1a1a | 衬线标题、下划线小标题、金句居中、配图阴影卡片 |
| `zhiyu` 治愈温暖 | 情感、生活、亲子 | 粉调 #ff7a9a | 粉色标题、虚线引用框、小花分隔、宽松行距 |

## 三、markdown 支持的语法（仅 markdown 模式）

| 语法 | 渲染效果 |
|---|---|
| `# 标题` | 文章大标题（居中、大字、加粗） |
| `## 小标题` | 带背景色+左边框的小标题 |
| `### 子标题` | 加粗子标题 |
| 普通段落 | 正文（行高1.75-1.85，两端对齐） |
| `![描述](路径)` | 图片（居中、圆角、max-width:100%） |
| `[[ILLU1]]` | 图片占位（配合 --image-dir 自动替换） |
| `> 引用文字` | 引用块（左边框+浅背景） |
| `**加粗**` | 加粗文字 |
| `- 列表项` / `1. 列表项` | 带符号的列表 |
| `---` / `***` | 分割线（· · ·） |

## 四、公众号粘贴操作（markdown 模式单独使用时）

1. 用浏览器打开生成的 `gzh_article.html`；
2. `Ctrl+A` 全选 → `Ctrl+C` 复制；
3. 打开公众号后台图文编辑器 → `Ctrl+V` 粘贴；
4. 图片需在公众号编辑器中重新上传（公众号会自动转存到素材库）；
5. 检查样式后点「保存为草稿」。

> **全链条模式下**：不需要手动粘贴，直接交给 QingFeng-wechat-publisher 发布脚本，脚本会自动上传图片拿 CDN URL，再用 execCommand 注入完整 HTML。

## 五、技术要点

- **HTML 优化模式**：CSS 内联化支持标签选择器、.class选择器、#id选择器、tag.class组合；按 CSS 规则顺序合并，后面的覆盖前面的；已有内联样式优先级最高。
- **markdown 模式**：全部样式写在 `style=""` 属性中，不依赖任何外部 CSS；容器用 `<section>` 嵌套（公众号编辑器原生支持）；字体用系统字体栈（PingFang SC / Microsoft YaHei）。
- 图片用 `<img style="max-width:100%">`，适配手机屏宽。
- 行高、字距、段距按公众号阅读体验优化。

## 六、与 QingFeng-media-ops 流水线的衔接

在流水线中，QingFeng-PB 生成通用 HTML 后，用本技能的 **HTML 优化模式** 处理：
```bash
python QingFeng-GZH-Layout/scripts/gzh_layout.py \
  --mode html \
  --input {date}/pb/index.html \
  --output {date}/formatted/wechat.html \
  --image-dir {date}/pb/
```
排版后的 `wechat.html` 直接交给 QingFeng-wechat-publisher 发布进草稿。

单独使用时，用 **markdown 模式**：
```bash
python QingFeng-GZH-Layout/scripts/gzh_layout.py \
  --input article.md \
  --output gzh.html \
  --style guofeng \
  --image-dir ./images/
```

## 七、文件清单

```
QingFeng-GZH-Layout/
├── SKILL.md                  # 本文件
└── scripts/
    └── gzh_layout.py        # 公众号排版脚本（双模式：HTML优化 + markdown排版）
```
