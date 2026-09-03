---
name: QingFeng-video-vs
description: 把用户提供的两个视频（来源不限定，可任意两个做效果对比的短片；竖屏或横屏均可）做成"顺序对比"短视频。竖屏时左右双小窗+顺序放大聚光；横屏时上下各一视频、位置大小不变、交叉播放（上播完→下播）。结尾均浮现"你更看好谁？评论区聊聊
  / 左X·右Y（或 上X·下Y）"。两侧不同时播放（各按原时间轴音画同步，单声道）。适合做"同题不同工具/版本/参数效果对比"类讨论视频。
argument-hint: "[left_video] [right_video]"
---

# QingFeng-video-vs · 顺序对比视频生成

把用户提供的两个视频做成"顺序对比"的短视频，让观众讨论哪个效果好。脚本**自动判断横竖屏**：竖屏走"左右放大聚光"，横屏走"上下交叉播放"。

> 💡 **关于源视频（不依赖 hyperframes）**：本技能**只负责把"两个已有的视频"合成对比片**，不关心它们由谁生成——可由 hyperframes、剪映、手机拍摄、其他 Agent 等任何方式产出。因此**不要求预先安装 hyperframes**，用户只要提供两个成品视频文件即可开始。若用户手上还没有视频、希望先生成再做对比，再视情况引导其用任意工具（含 hyperframes）产出源视频。

技能目录（含脚本与资源）：`C:\Users\chenw\.workbuddy\skills\QingFeng-video-vs\`
（以下脚本/资源路径均以该目录为准，新环境解压到任意 `.workbuddy/skills/QingFeng-video-vs/` 即可）
- `scripts/build_filter.py` —— 自动探测时长/分辨率、判断横竖屏、生成对应 ffmpeg 滤镜图脚本
- `scripts/render_title.cjs` —— 把 `assets/title_effect.html` 的光效逐帧截成透明 PNG 序列
- `assets/title_effect.html` —— 炫酷标题光效（呼吸/扫光/光带/浮动光点）
- `assets/simhei.ttf` —— 中文字体

## 成品效果（时间轴）

### 竖屏模式（左视频宽 < 高，默认）
1. **开场**：深色背景，左右两个小窗居中（左=输入1，右=输入2），顶部炫酷标题，中间 `VS` 徽标。
2. **左片聚光**：左窗放大到全屏、置顶独占播放（右窗静止在首帧）；只显「左标签」。
3. **缩回**：左片播完缩回小窗；短暂归位。
4. **右片聚光**：右窗放大到全屏置顶播放（左窗静止）；只显「右标签」。
5. **结尾**：浮现「你更看好谁？评论区聊聊」+「左边 X · 右边 Y」，渐显。
6. **输出**：1080×1920 竖屏。

### 横屏模式（左视频宽 > 高）
1. **布局固定**：上方一个视频、下方一个视频，各自占据半屏，**位置与大小都不变**。
2. **交叉播放**：先播上方视频（下方视频冻结在首帧）；上方播完后，下方视频接着播（上方视频冻结在末帧）。
3. **分隔与标识**：上下之间一条分隔线 + 中央 `VS` 徽标；上方左上角显「上标签」、下方左上角显「下标签」，始终显示。
4. **顶部标题**：炫酷标题光效叠加在画面最上方。
5. **结尾**：浮现「你更看好谁？评论区聊聊」+「上面 X · 下面 Y」，渐显。
6. **输出**：与源视频同分辨率（如 1920×1080）的横屏。
7. **音频**：上方时段只上有声、下方时段只下有声，单声道混流（不分左右声道）。

## 何时使用

用户把两个视频上传或放在同一文件夹，要求"把这两个视频做成对比""哪个效果好""顺序对比视频""同题两个版本效果对比"等。竖屏、横屏均可，无需事先转码。

## 重要：先向用户确认视频信息与上下/左右含义（缺失则主动询问）

本技能**不预设任何具体标签或品牌字眼**（"WorkBuddy""秒哒"等仅是历史示例，切勿作为默认值）。两个视频各自代表什么，完全由用户决定——可能因场景不同而指代不同 AI 工具、不同版本、不同提示词、不同参数或不同作者。

在生成之前，**必须先用一句话提示并询问用户**，拿到以下信息后再继续：
- 「第一个（左 / 上）视频」代表什么？（竖屏→左标签与"左边 X"；横屏→上标签与"上面 X"）
- 「第二个（右 / 下）视频」代表什么？（竖屏→右标签与"右边 Y"；横屏→下标签与"下面 Y"）
- 对比主题 / 标题想怎么写？（默认"同一主题 · 两种效果，你更看好谁？"）

将答案填入 `--left-label` / `--right-label` / `--title`（脚本里 left=第一输入、right=第二输入；竖屏对应左右、横屏对应上下）。若用户未提供，用中性占位（如"左边/右边"或"上面/下面"）并在交付时说明。

## 操作步骤（始终遵循）

### 第 1 步：准备源文件
- 把两个视频放进一个**工作目录**（建议新建空目录，例如 `D:\知识库\视频生成\_work\vs\`）。
- 无需手动判断横竖屏：`build_filter.py` 默认 `--orientation auto`，会按**第一个（左/上）输入**的宽高自动选择竖屏或横屏布局。
- 用 ffprobe 看一眼时长（可选，脚本会自动探测）：
  `ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 左.mp4`

### 第 2 步：生成滤镜图脚本
在**工作目录**内运行（脚本会自动拷贝 `simhei.ttf`、自动探测时长与横竖屏）：
```bash
python3 "C:/Users/chenw/.workbuddy/skills/QingFeng-video-vs/scripts/build_filter.py" \
  --left 左.mp4 --right 右.mp4 \
  --left-label "<第一视频标签>" --right-label "<第二视频标签>" \
  --title "<对比标题>" \
  --out filter_vs.txt
```
- 手动指定布局：`--orientation vertical` 或 `--orientation horizontal`（默认 `auto`）。
- 时长已知可省探测，直接 `--left-dur 22.73 --right-dur 27.52`。
- 脚本会先打印 `ORIENTATION: vertical/horizontal`，再打印完整 `ffmpeg` 命令。

### 第 3 步：渲染炫酷标题 PNG 序列（推荐，png 模式默认）
```bash
node "C:/Users/chenw/.workbuddy/skills/QingFeng-video-vs/scripts/render_title.cjs"
```
生成 `工作目录/title_frames/f_000.png … f_089.png`（90 帧，3 秒循环）。
- 改标题文字：编辑 `assets/title_effect.html` 里的 `data-text` 与 `<h1>` 文本（两处都要改一致）。
- 横屏时标题条会自动按画布宽度缩放并居中叠在顶部，无需额外操作。
- 依赖：puppeteer-core + Playwright Chromium（脚本已内置回退路径；找不到时设 `PUPPETEER_CORE` 或 `npm i puppeteer-core`）。

### 第 4 步：运行 ffmpeg 出片
直接用第 2 步打印的命令，或在**工作目录**执行（png 模式需 3 个输入）：
```bash
ffmpeg -y -i 左.mp4 -i 右.mp4 \
  -stream_loop -1 -framerate 30 -i title_frames/f_%03d.png \
  -filter_complex_script filter_vs.txt \
  -map "[outv]" -map "[outa]" \
  -c:v libx264 -pix_fmt yuv420p -r 30 -c:a aac -t <总时长> 对比视频.mp4
```
（总时长 = 脚本打印的 TOTAL_DURATION；用 `-t` 截断，避免末尾补帧。）

### 第 5 步：验证
- **竖屏**：抽帧 `t≈1s` 开场双窗+标题；`t≈左片中部` 左满屏只显左标签、右窗静止；`t≈左片结束` 双窗归位；`t≈右片中部` 右满屏只显右标签；`t≈结尾` CTA 浮现。音频左时段只左有声、右时段只右有声。
- **横屏**：抽帧 `t≈1s` 上方在播、下方冻结首帧、顶部标题+分隔线+VS；`t≈上方中部` 上方在播、下方仍冻结；`t≈上方结束` 上冻结末帧、下开始播；`t≈下方中部` 下在播、上冻结；`t≈结尾` CTA 浮现（"上面 X · 下面 Y"）。音频上方时段只上有声、下方时段只下有声。

## 关键坑（务必遵守，否则画面错乱/黑块）

1. **竖屏才需要 split=2 防别名污染**：同一路输入既做小窗又做放大层时，必须 `split=2` 复制成独立两路。否则放大层会串到另一路输入，导致"开场右窗显示的是左片画面"串台。**横屏版每路只 overlay 一次，无需 split。**
2. **冻结时间轴用 tpad，不是 setpts**：`setpts=N*TB/30` 会把整段塌缩成 3 帧。实现"对方播放时本路停住"用 `tpad=start_mode=clone:start_duration=START`（后播的一路在对方播放期间停在首帧），结尾用 `tpad=stop_mode=clone` 冻结末帧补到总时长。
3. **条件显示用 enable，不用嵌套 if()**：滤镜图里 `if(lt(t,0.6),A,if(...))` 会报 `Invalid chars ')'`。缩放动画用 flat 的 `min(max(x,0),1)` 阶梯表达式；放大层出现时机用 `enable='gte(t,a)*lte(t,b)'` 控制置顶。
4. **透明标题用 PNG 序列，别用 webm/VP9**：本机 ffmpeg 编码 `yuva420p` 后 alpha 丢失，叠加变黑块。用 puppeteer 逐帧 `omitBackground` 截透明 PNG 最稳。
5. **滤镜脚本里不要写 `#` 注释**：ffmpeg 的 filter_complex_script 会把 `#` 当语法报错（Trailing garbage）。纯多行滤镜图，一行一条 filterchain，用 `;` 分隔。
6. **竖屏放大层必须放最后叠加才置顶**：overlay 顺序决定层级，放大层要放在滤镜图末尾（盖住小窗），靠 `enable` 窗口控制它"只在自己播放时出现"。
7. **音频统一单声道**：两源采样率/声道可能不同（如 24k/44.1k、单声道），先 `aresample=44100` + `aformat channel_layouts=mono`；后播的一路 `atrim=0:DUR` 后 `adelay=START*1000` 对齐到先播一路播完之后，再 `amix`。

## 输出

成品 `对比视频.mp4`（竖屏 1080×1920 / 横屏按源分辨率，单声道，含字幕/标签/CTA），放在工作目录，按产品标题规则重命名后交付。
