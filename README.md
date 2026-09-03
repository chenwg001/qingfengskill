# 轻风教育工具技能集（QingFeng Skills）

本人自制的 [WorkBuddy](https://www.workbuddy.cn) 技能开源集合，目前共 **17 个**「QingFeng」系列技能，按技能分目录放在 `skills/` 下。所有技能命名统一为 `QingFeng-` 前缀。

## 包含的技能

### 一、内容创作（写作 / 排版 / 封面）

- **QingFeng-writing** — 轻风写作（个人专属文风）。严格遵循教育工作者身份，输出公文 / 教学 / 随笔三类文风；标注【公文】【教学】【随笔】时触发。纯 Markdown 配置，复制即用。
- **QingFeng-rdxz** — 教育热点三平台图文。全网搜教育热点→三维加权选题→调用轻风写作按头条 / 公众号 / 小红书各写一篇（随笔 / 论文 / 小故事三体裁）。
- **QingFeng-PB** — 文章排版。输入公众号长文 + 头条短文，排通用版（生封面/插图/背景图）并复用图片排头条版，输出两套 HTML。
- **QingFeng-GZH-Layout** — 公众号排版。两种模式：HTML 内联样式优化 / markdown 转公众号可直接粘贴的内联样式 HTML，五套风格。
- **QingFeng-XHS-Layout** — 小红书排版。markdown 转小红书可粘贴的带 emoji 纯文本，自动分段、插 emoji、加话题标签，三套风格。
- **QingFeng-Cover** — 多平台封面。将基础封面叠加标题，按 4:3 / 3:4 / 2.35:1 / 1:1 输出，改尺寸不裁剪原图。

### 二、PPT

- **QingFeng-ppt** — 轻风PPT 自动套版「三步工作流」（可选第 4 步自动生图）：换肤→生成大纲→套用→（可选）生图填入占位符。

### 三、多平台发布

- **QingFeng-media-ops** — 轻风全自动媒体运营流水线（编排技能）：找热点→三平台文章→排版生图→CDP 进各平台草稿→（可选）视频→日报，覆盖头条/公众号/小红书图文与抖音/快手/B站短视频。
- **QingFeng-toutiao-publisher** — 头条号文章发布（mp.toutiao.com）。
- **QingFeng-wechat-publisher** — 微信公众号文章发布（mp.weixin.qq.com）。
- **QingFeng-baijiahao-publisher** — 百家号文章发布（baijiahao.baidu.com）。
- **QingFeng-xiaohongshu-publisher** — 小红书图文发布（creator.xiaohongshu.com），存草稿。
- **QingFeng-video-publisher** — 视频发布（小红书 + B站，横竖屏自动路由：横屏发B站、竖屏发小红书）。
- **QingFeng-video-publisher-v2** — 短视频发布（抖音 / 快手），双封面、存草稿。

### 四、视频生成

- **QingFeng-video-poem** — 古诗 / 叙事短视频导演。诗名/全诗/任意文本→分镜图→首尾帧插值动态镜头→edge-tts 朗诵→程序化 BGM→音画同步合成。
- **QingFeng-video-vs** — 顺序对比视频。把两个视频做成「顺序对比」短片（竖屏左右双窗聚光 / 横屏上下交叉播放），适合同题效果对比。
- **QingFeng-VE** — 轻风视频剪辑（确定性短视频生产线）。识别需求、引导信息、执行完整剪辑流水线；核心是确定性剪辑（可控顺序、素材全覆盖）。

## 安装方式

把对应技能文件夹整体复制到 WorkBuddy 的技能目录即可（重启/刷新后生效）：

- **用户级**（对所有项目生效）：`~/.workbuddy/skills/`
- **项目级**（仅对该项目生效）：`<你的项目>/.workbuddy/skills/`

例如安装 `QingFeng-ppt`：

```bash
# 用户级
cp -r skills/QingFeng-ppt ~/.workbuddy/skills/

# 或项目级
cp -r skills/QingFeng-ppt <你的项目>/.workbuddy/skills/
```

本仓库 `skills/` 下全部技能目录（复制其中任意一个即可）：

```
QingFeng-Cover                QingFeng-GZH-Layout           QingFeng-PB
QingFeng-VE                   QingFeng-XHS-Layout           QingFeng-baijiahao-publisher
QingFeng-media-ops            QingFeng-ppt                  QingFeng-rdxz
QingFeng-toutiao-publisher    QingFeng-video-poem           QingFeng-video-publisher
QingFeng-video-publisher-v2   QingFeng-video-vs             QingFeng-wechat-publisher
QingFeng-writing              QingFeng-xiaohongshu-publisher
```

## 依赖

- `QingFeng-ppt` 第 4 步「自动生图」依赖 `agnes-image` 技能（需已安装）。
- `QingFeng-rdxz` 依赖 `QingFeng-writing`（本仓库已含）与 `agnes-image` 技能。
- 各 `*-publisher` 发布类技能需浏览器自动化环境（统一使用 Chrome for Testing + CDP），具体依赖见其 `SKILL.md`；技能内不含任何硬编码账号 token。
- `QingFeng-video-poem` 依赖 `ffmpeg` 与 Python 包 `edge_tts` / `numpy` / `scipy`（生图/生视频默认用 WorkBuddy 内置 `ImageGen` / `VideoGen`）。
- `QingFeng-video-vs` 依赖 `ffmpeg`；标题光效渲染依赖 `node` + `puppeteer-core` / Playwright Chromium（找不到时自动降级跳过）。
- `QingFeng-VE` 依赖 `ffmpeg` / `edge-tts` / `Pillow` / `numpy`；可选本地 TTS 克隆需 `torch` + `transformers` + `qwen_tts`。
- `scripts/*.py` 基于 Python 3，运行前按需安装依赖（如 `pip install python-pptx`），其余见各脚本头部 `import`。

## 单独下载某个技能（不必克隆整个仓库）

本仓库用集合方式管理多个技能，Gitee 的「下载」按钮会打包整个仓库。如果你只想要其中某一个技能，有两种方式：

### 方式一：git sparse-checkout（推荐，会 git 的人用）

只克隆仓库的元信息，再只检出你需要的那个技能文件夹：

```bash
git clone --filter=blob:none --sparse git@gitee.com:chenwg001/qingfengskill.git
cd qingfengskill
# 只检出 QingFeng-ppt（换成你想要的技能目录名即可）
git sparse-checkout set skills/QingFeng-ppt
```

一次拿多个，就把它们都写进去，例如：

```bash
git sparse-checkout set skills/QingFeng-ppt skills/QingFeng-writing
```

### 方式二：下载发行版附件（不会 git 的人用）

仓库「发行版（Release）」里为每个技能单独打了 zip 包，网页点一下即可下载单个技能，无需安装 git。下载地址格式：

```
https://gitee.com/chenwg001/qingfengskill/releases/download/skills-v1/<技能名>.zip
```

当前发行版含以下 17 个 zip：

- `QingFeng-ppt.zip` — 轻风PPT 自动套版
- `QingFeng-writing.zip` — 轻风写作
- `QingFeng-rdxz.zip` — 教育热点三平台图文
- `QingFeng-PB.zip` — 文章排版
- `QingFeng-GZH-Layout.zip` — 公众号排版
- `QingFeng-XHS-Layout.zip` — 小红书排版
- `QingFeng-Cover.zip` — 多平台封面
- `QingFeng-toutiao-publisher.zip` — 头条号发布
- `QingFeng-wechat-publisher.zip` — 公众号发布
- `QingFeng-baijiahao-publisher.zip` — 百家号发布
- `QingFeng-xiaohongshu-publisher.zip` — 小红书发布
- `QingFeng-video-publisher.zip` — 视频发布（小红书 + B站）
- `QingFeng-video-publisher-v2.zip` — 短视频发布（抖音 / 快手）
- `QingFeng-media-ops.zip` — 全自动媒体运营流水线
- `QingFeng-video-poem.zip` — 古诗 / 叙事短视频导演
- `QingFeng-video-vs.zip` — 顺序对比视频生成
- `QingFeng-VE.zip` — 轻风视频剪辑（确定性短视频生产线）

## 许可证

MIT，详见 [LICENSE](LICENSE)。
