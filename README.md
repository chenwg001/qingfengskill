# 轻风教育工具技能集（light-wind-education）

本人自制的 [WorkBuddy](https://www.workbuddy.cn) 技能开源集合，按技能分目录放在 `skills/` 下。

## 包含的技能

### qingfeng-ppt — 轻风PPT 自动套版

轻风PPT 自动套版「三步工作流」（可选第 4 步自动生图）：

1. **换肤**：按用户上传的模板只读母版背景图 + 主题配色，套到内置轻风 14 版式骨架（版式结构不变），并按背景亮度自动选黑/白字；规范模板则原样使用。
2. **生成大纲**：读用户文本或主题生成标准大纲，用户可改、须确认。
3. **套用**：按大纲把文字纯灌入模板文本占位符，不改任何样式；图片占位符留空。
4. **（可选）生图**：用户回复「生图」时，按页面内容自动生成图片并插入所有图片占位符。

触发词：`qingfeng-ppt` / `轻风PPT` / `套模板做PPT` 等。
详细说明见 [`skills/qingfeng-ppt/技能说明.md`](skills/qingfeng-ppt/技能说明.md)。

### qingfeng-writing — 轻风写作（个人专属文风）

个人专属写作风格生成器，严格遵循教育工作者身份配置，精准输出**公文 / 教学 / 随笔 / 小故事**四类文风。

- 内置通用基础人设 + 四类文体专属写作规范、通用禁忌、句式习惯、标题规范、行文思维模型。
- 当用户标注【公文】【教学】【随笔】【小故事】，或需要生成正式公文、教育论文、生活随笔时触发。
- 纯 Markdown 配置，无脚本、无外部依赖，复制即用。

触发词：`qingfeng-writing` / `轻风写作` / 【公文】【教学】【随笔】【小故事】 等。

### education-hotspot-generator — 教育热点三平台图文

全网搜索泛教育热点，三维加权遴选主题，调用「轻风写作」技能按 **今日头条 / 微信公众号 / 小红书** 三平台各写一篇（随笔 / 论文 / 小故事三体裁），用 `agnes-image` 生成封面 + 插图，输出 docx 纯文本版、docx 图片版、HTML 版。

触发词：`education-hotspot-generator` / `写篇教育热点` / `生成热点文章` / `做三平台教育图文` 等。

依赖：需已安装 `qingfeng-writing`（本仓库已含）与 `agnes-image` 技能。

### toutiao-publisher — 头条 / 公众号文章发布

将本地 HTML 文件的图文内容自动发布到 **头条号（mp.toutiao.com）** 与 **微信公众号（mp.weixin.qq.com）** 编辑器。

- 识别「发布到头条 / 公众号」意图，调用对应脚本把 HTML 标题与正文填入平台编辑器。
- 仅含技能本体（`SKILL.md` + `scripts/*.py`），不含个人发布截图与回执；脚本内不含任何硬编码账号 token。
- 触发词：`toutiao-publisher` / `发布到头条` / `发到头条` / `把文章发到头条` / `发到公众号` 等。

## 安装方式

把对应技能文件夹整体复制到 WorkBuddy 的技能目录即可（重启/刷新后生效）：

- **用户级**（对所有项目生效）：`~/.workbuddy/skills/`
- **项目级**（仅对该项目生效）：`<你的项目>/.workbuddy/skills/`

例如安装 `qingfeng-ppt`：

```bash
# 用户级
cp -r skills/qingfeng-ppt ~/.workbuddy/skills/

# 或项目级
cp -r skills/qingfeng-ppt <你的项目>/.workbuddy/skills/
```

例如安装 `qingfeng-writing`：

```bash
# 用户级
cp -r skills/qingfeng-writing ~/.workbuddy/skills/

# 或项目级
cp -r skills/qingfeng-writing <你的项目>/.workbuddy/skills/
```

例如安装 `toutiao-publisher`：

```bash
# 用户级
cp -r skills/toutiao-publisher ~/.workbuddy/skills/

# 或项目级
cp -r skills/toutiao-publisher <你的项目>/.workbuddy/skills/
```

## 依赖

- `qingfeng-ppt` 第 4 步「自动生图」依赖 `agnes-image` 技能（需已安装）。
- `education-hotspot-generator` 依赖 `qingfeng-writing`（本仓库已含）与 `agnes-image` 技能（需已安装）。
- `toutiao-publisher` 发布到头条 / 公众号需浏览器自动化环境，具体依赖见其 `SKILL.md`。
- `scripts/*.py` 基于 Python 3，运行前请安装 `python-pptx`（`pip install python-pptx`），其余依赖见各脚本头部 `import`。

## 单独下载某个技能（不必克隆整个仓库）

本仓库用集合方式管理多个技能，Gitee 的「下载」按钮会打包整个仓库。如果你只想要其中某一个技能，有两种方式：

### 方式一：git sparse-checkout（推荐，会 git 的人用）

只克隆仓库的元信息，再只检出你需要的那个技能文件夹，本地不会落下其他技能：

```bash
git clone --filter=blob:none --sparse git@gitee.com:chenwg001/qingfengskill.git
cd qingfengskill
# 只检出 qingfeng-ppt（换成你想要的技能目录名即可）
git sparse-checkout set skills/qingfeng-ppt
```

想一次拿多个，就把它们都写进去，例如：

```bash
git sparse-checkout set skills/qingfeng-ppt skills/qingfeng-writing
```

### 方式二：下载发行版附件（不会 git 的人用）

仓库「发行版（Release）」里为每个技能单独打了 zip 包，网页点一下即可下载单个技能，无需安装 git：

- `qingfeng-ppt.zip` — 轻风PPT 自动套版
- `qingfeng-writing.zip` — 轻风写作
- `education-hotspot-generator.zip` — 教育热点三平台图文
- `toutiao-publisher.zip` — 头条 / 公众号发布

## 许可证

MIT，详见 [LICENSE](LICENSE)。
