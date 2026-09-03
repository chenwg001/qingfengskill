---
name: QingFeng-XHS-Layout
description: 小红书笔记排版技能（QingFeng-XHS-Layout）。把 markdown 文章转成小红书编辑器可直接粘贴的带 emoji 排版纯文本，参照 Reditor红薯编辑器/自动薯的排版规范，自动分段（每段2-4行）、智能插入 emoji（全文不超过5种）、小标题符号化、末尾加话题标签。支持故事共鸣/干货要点/生活随笔三套风格。当用户说"小红书排版""排个小红书版""生成小红书笔记""XHS排版"时使用。
---

# QingFeng-XHS-Layout 小红书笔记排版技能

> 核心原则：小红书编辑器是富文本，不支持复杂 HTML。输出**纯文本 + emoji**，
> 直接复制粘贴到小红书笔记编辑器即可。图片单独上传。

## 一、能力总览

输入一篇 markdown 文章，输出：
- `xhs_note.txt` —— 带 emoji 排版的纯文本，可直接复制粘贴到小红书笔记编辑器。

支持三套风格：
| 风格 | 适用场景 | 标题emoji | 段落emoji池 |
|---|---|---|---|
| `story` 故事共鸣 | 教育故事、个人感悟 | ✨ | 🌱💭💡 |
| `ganhuo` 干货要点 | 方法、技巧、政策解读 | 📚 | 🎯💡📌 |
| `life` 生活随笔 | 日常、随想、亲子 | ☀️ | 🌿☕📖 |

## 二、排版规范（参照主流小红书排版工具）

1. **分段**：每段 2-4 行（约 40-70 字），段间空一行，避免"文字墙"；
2. **emoji**：全文不超过 5 种，每 2-3 段在段首插 1 个作为视觉锚点，不堆砌；
3. **小标题**：用 emoji 前缀代替数字编号（如 `🌱 小标题`），不用 1.2.3；
4. **标题**：首行标题带 1 个 emoji，简洁有力；
5. **话题标签**：末尾 `——` 分隔后加 `#话题1 #话题2`；
6. **图片**：排版文本中不含图片，小红书图片单独上传（封面+内图）。

## 三、使用方法

```bash
python {skill_dir}/scripts/xhs_layout.py \
  --input  article.md \
  --output xhs_note.txt \
  --style story \
  --tags "教育,做中学,新教材,开学季"
```

参数说明：
- `--input`：markdown 文章路径（必填）
- `--output`：输出 txt 路径（必填）
- `--style`：排版风格，默认 `story`
- `--tags`：话题标签，逗号分隔；不传则用默认（教育/做中学/新教材/开学季/家长必读）
- `--title`：覆盖标题（默认从 markdown 的 `# 标题` 提取）

## 四、markdown 支持的语法

| 语法 | 渲染效果 |
|---|---|
| `# 标题` | 笔记首行标题（带标题emoji） |
| `## 小标题` | 带 section emoji 的小标题行 |
| `### 子标题` | 带 point emoji 的子标题 |
| 普通段落 | 自动拆成短段，每 2-3 段段首加 emoji |
| `> 引用` | 带高亮 emoji 的引用行 |
| `- 列表` / `1. 列表` | 带 point emoji 的清单项 |
| `![图片]` / `[[ILLU1]]` | 跳过（小红书图片单独上传） |
| `---` | 分割线 `——` |
| `**加粗**` | 去掉标记保留文字（小红书编辑器内手动加粗） |

## 五、小红书粘贴操作

1. 打开生成的 `xhs_note.txt`，全选复制；
2. 打开小红书创作服务平台 → 发布笔记 → 上传封面和内图；
3. 在正文框粘贴文本；
4. 检查 emoji 显示、分段、话题标签；
5. 点「存为草稿」。

## 六、与 QingFeng-media-ops 流水线的衔接

在流水线中，QingFeng-rdxz 生成小红书文章后，用本技能排版：
```bash
python QingFeng-XHS-Layout/scripts/xhs_layout.py \
  --input {date}/articles/xiaohongshu/article.md \
  --output {date}/formatted/xhs.txt \
  --style story \
  --tags "教育,做中学,新教材"
```
排版后的 `xhs.txt` 直接交给 xiaohongshu_publish.py 发布进草稿（图片从 QingFeng-PB 产物中选取）。
