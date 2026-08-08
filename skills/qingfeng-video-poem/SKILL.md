---
name: qingfeng-video-poem
description: 给「诗名 / 全诗 / 任意叙事文本」即可生成意境短视频。解析输入（古诗按库、自由文本由大模型分析理解后拆解分镜）→ 按镜头生成水墨/工笔/写实/国风分镜图 → 用所选生视频模型首尾帧插值做成连贯动态镜头 → edge-tts 朗诵 → 程序化 BGM → 以朗诵时间轴为主时钟严格音画同步合成成片。生图/生视频模型可插拔（阶段 0.5 由用户选择）。触发词：古诗视频、诗名生成视频、给首诗做视频、把这段话做成视频、文本生成视频、叙事文案视频、游记视频。
---

# 古诗视频导演（qingfeng-video-poem）

把一首诗（只需给诗名，或给全文）自动变成一段画面精致、剧情连贯、音画同步的竖屏短视频。
主打差异化：**专业脚本导演 + 高精度水墨/国风/写实画面**，区别于普通模板化 AI 视频。

## 与原技能的关系
原技能（ancient-poem-video-generator）依赖 `image-generation-super` + `sora-video-generation` + `minimax-tts` + `ffmpeg` 四个外部 API。
本技能将其重写为**本地可跑、零外部 API 成本**的工作流：
- 画面：默认用 WorkBuddy 内置 `ImageGen` 出分镜首帧、`VideoGen(last_image)` 做首尾帧插值（真正的 AI 动态，替代原 sora/ffmpeg 假动画）。但技能在**阶段 0.5** 支持更换为其他已安装的图像/视频技能（如 QClaw、Seedance 等通用技能），做到模型可插拔。
- 朗诵：用 `gen_tts.py`（edge-tts 免费中文神经语音，Windows 有 SAPI 兜底），并输出 `timeline.json` 精确时间轴
- BGM：`gen_bgm.py` 按诗情绪本地程序化生成（五声音阶，无 API）
- 合成：`compose_video.py` 以朗诵时间轴为主时钟，严格音画同步

## 何时使用
- 用户说「给首诗/诗名做视频」「把《XX》做成短视频」「古诗视频」
- 用户已有一首诗想可视化
- 用户给一段叙事文本（散文/小说片段/故事/游记/文案），想做成短视频
- 需要批量把若干古诗变成短视频

## 环境前置（一次性）
- `ffmpeg` / `ffprobe`：本机已具备
- Python 包：`edge_tts`、`numpy`、`scipy`（安装在隔离 venv，见下方命令）
  ```
  C:/Users/chenw/.workbuddy/binaries/python/envs/default/Scripts/python.exe -m pip install edge_tts numpy scipy
  ```
- Windows 中文字体（楷体 `simkai.ttf` 等）已具备

## 全流程（6 阶段）

### 阶段 0：解析输入 + 理解先行（统一产出 script.json）

本技能输入有三种，阶段 0 末尾都产出 `<workdir>/script.json`，阶段 1–5 只认它（结构见 `references/script-schema.md`）：

**A. 只给诗名（没给全文）** —— 检索本地诗库（技能自带库 + 工作目录缓存库合并查询）：
```
python <skill>/scripts/resolve_poem.py --name "<诗名>" --user-db <workdir>/poems_user.json --out <workdir>/script.json
```
- 命中（技能库或缓存库任一）：得到 `title/author/dynasty/lines/mood/style/imagery/scene_desc/n_scenes`。
- 未命中：技能库约 41 首，缓存库按需累积。**由你联网检索全文、确认作者朝代，用 `--append` 写入工作目录缓存库（绝不写技能自带库），再重试**：
```
python <skill>/scripts/resolve_poem.py --append --user-db <workdir>/poems_user.json \
  --entry '{"title":"...","author":"...","dynasty":"...","lines":["..."],"mood":"serene","style":"ink","imagery":["..."],"scene_desc":"..."}'
```
- 或请用户直接粘贴全诗（走路径 B）。

**B. 用户已给全诗**：跳过检索，用诗句作 `--lines`，`mood` 默认 `serene`、`style` 默认 `ink`，据意境调整，直接写 `script.json`。

**C. 任意叙事文本（散文/小说片段/故事/游记等）**：不查诗库。由你（大模型）按"理解先行"分析文本、拆解分镜，直接产出 `script.json`：
- 按**语义断点**把文本切成镜头 `segments`（建议 ≤ 8 镜；封面镜 + 每 segment 一镜，`n_scenes = len(segments)+1`）；
- 每个 segment 填 `text`(该镜旁白)/`mood`/`style`/`imagery`/`scene_desc`/`action_start`/`action_end`；
- 顶层填 `consistency_brief`（角色表 `characters` + 风格锁 `style_lock` + 场景锚 `setting`），保证跨镜人设/画风一致——**叙事类重点**；
- `mood` 取整体调性（nostalgic/serene/melancholy/heroic/joyful），`style` 由调性推断（ink/gongbi/realistic/guofeng）；旁白默认用原文句子。

> **⚠️ 铁律一（理解先行）：生成任何图像前，必须先吃透输入的含义、语境与意图。**
> - 古诗：推敲逐句字面含义、创作背景、画面转译、动作设计（见下 4 步）。
> - 自由文本：先判叙事主线/人物/场景/情绪走向，再分镜；禁止不假思索把关键词塞进模板就调用 ImageGen。
> 每镜生图前必完成：①字面/语义含义 ②语境与意图 ③画面转译（人物姿态/动作/景物/光影/构图）④动作设计（首帧→尾帧真实动作差）。
> 1. **字面/语义含义**：这句/这段在描述什么场景、动作或信息？
> 2. **语境与意图**：何时何地？叙述者/诗人心境？要传递什么情绪？
> 3. **画面转译**：应呈现什么具体画面？含哪些元素（人物姿态/动作/景物/光影/构图角度）？
> 4. **动作设计**：该镜首帧→尾帧设计什么真实动作？（人物姿态改变 / 物体位移 / 光影变化）
>
> 禁止不假思索地把文本关键词塞进模板就调用 ImageGen——那会导致「床前明月光」只出一张床、「举头望明月」是张静止图这类错误。

镜头规划：**封面镜 1 个 + 每 segment/每句 1 个**（`n_scenes = 镜头单元数 + 1`）。封面镜用 `scene_desc` 的意象。
对每个镜头，须预先设计**首帧画面**与**尾帧画面**的动作差异（见阶段 1）。

### 阶段 0.5：选择生图 / 生视频模型（模型可插拔）⚠️ 每次新项目先确认

不同用户的技能环境不同，生图/生视频用的可能是别的已安装图像/视频技能，
并不一定是 WorkBuddy 内置的 `ImageGen`/`VideoGen`。因此在真正生图、生视频**之前**，必须先梳理
用户环境里可用的生图/生视频能力，让用户自己选（确认环节）。

#### 0.5.1 梳理可用能力（inventory）
- **生图候选**：
  - `WorkBuddy 内置 ImageGen`（默认·推荐，总是可用，支持文生图+图生图尾帧）
  - 其他已安装的图像生成技能：从当前会话可用技能列表筛选名字/描述含「图像生成 / 文生图 / 图生图」的（如 `qclaw-generate-image`）
- **生视频候选**：
  - `WorkBuddy 内置 VideoGen`（默认·推荐，支持 `last_image` 首尾帧插值，保证人物真动作）
  - 其他已安装的视频生成技能：如 `seedance-director`（先 `Skill` 加载确认其首尾帧接口）
  - `ffmpeg 兜底`（无模型，脚本 `gen_scene_video.py`，首尾帧交叉淡入 / Ken Burns）
- 梳理方式：查看当前可用技能列表，挑出相关的图像/视频技能；内置工具始终列入候选。

#### 0.5.2 让用户选择（AskUserQuestion）
- 用 `AskUserQuestion` 分别问**生图模型**与**生视频模型**两个独立问题，把 0.5.1 梳理出的候选作为选项，
  内置 `ImageGen`/`VideoGen` 标记为「(推荐)」。
- 若某类候选超过 4 个，按相关性截取前 4 个（用户仍可用「其他」自填技能名）。

#### 0.5.3 保存选择（model_config.json）
把选择写入两处，避免每次都问：
- `<workdir>/model_config.json`（本次项目）
- `<skill>/model_config.json`（全局默认，下次直接沿用）
```json
{ "image_provider": "builtin_imagen", "video_provider": "builtin_videogen", "updated_at": "YYYY-MM-DD" }
```
- 若全局默认已存在且用户未要求更换，直接沿用并提示「沿用上次选择：生图=… 生视频=…」；
  用户说「换模型」时再重新选。
- **若用户选了某个技能型 provider**：先 `Skill` 加载该技能，按其 SKILL.md 的准确接口调用（见 `references/model-providers.md` 调度表）。

> 各 provider 的具体调用方式与参数差异、能力受限时的退化方案，见 `references/model-providers.md`。

### 阶段 1：生成分镜首帧图 + 尾帧图（用所选生图模型，每镜两张）
读取 `<workdir>/script.json` 的 `segments` / `consistency_brief` / `style` / `imagery`。
使用 `model_config.json` 中的 `image_provider` 生成（默认内置 `ImageGen`；若选了其他技能，按 `references/model-providers.md` 调度表调用）。
对「封面镜 + 每 segment/每句」逐一生成**首帧**与**尾帧**共 `2 × n_scenes` 张图：

> **一致性注入（叙事类重点）**：把 `consistency_brief` 的内容作为**固定前缀**拼进每一张首/尾帧 prompt——具体是 `style_lock`（画风+色调+质感）+ `setting`（时间/地点/光影）+ 每个出场人物的 `characters[].appearance`（固定外貌）。这样跨镜人设与画风保持一致，避免"每镜一个人设、画风漂移"。古诗若无具体人物，`characters` 可空，仅用 `style_lock`/`setting`。

#### 首帧（`img_ii_first.png`）——动作起点
- `size`: 竖屏用 `"1024x1536"`，横屏用 `"1536x1024"`
- `style`: 依 `script.json` 的 `style` 传对应词（见 prompt-templates.md 画风映射）。推荐 `工笔画`（精细写实）优于宽松水墨
- `prompt`: 用 `references/prompt-templates.md` 中对应画风的「分镜提示词」模板，把**理解先行分析结果**（阶段 0 铁律一）填进去。必须包含：
  - 具体场景描述（不是泛泛关键词，而是「唐代旅舍卧房 interior、小格窗、月光照地」这种精确画面）
  - 人物的**起始姿态/动作**
  - 建筑/道具比例准确的约束（如「比例真实的小格窗，非落地大窗」）
  - 时间/光线/氛围

#### 尾帧（`img_ii_last.png`）——动作终点（图生图，保证背景一致）
- `image`: 该镜首帧 `img_ii_first.png`（**必须传数组格式** `["path"]`）
- `input_fidelity`: `"0.82"`（锁死背景机位，仅允许人物姿态变化；过低会导致机位漂移被模型当成旋转假动）
- `prompt`: 描述同一场景的后续瞬间——人物从首帧姿态变为尾帧姿态，景物有相应位移/光影变化
- `size` / `style`: 与首帧保持一致

> **⚠️ 铁律二：每镜必须出首帧+尾帧，用 VideoGen 的 last_image 做真实动作插值。**
> - 尾帧与首帧之间必须有**真实的动作差异**（人物姿态改变 / 物体位移 / 光影流动），不能只是"同一画面的微调"
> - 禁止只出一张首帧就让 VideoGen 单图生视频——那只能产生镜头推移/缩放等假动态，人物不会有真实动作
> - 典型动作设计示例：
>   - 「床前明月光」：首帧=半卧 → 尾帧=坐起
>   - 「疑是地上霜」：首帧=低头看地 → 尾帧=前倾伸手
>   - 「举头望明月」：首帧=低头 → **尾帧=抬头望月**（核心动作！）
>   - 「低头思故乡」：首帧=仰望 → 尾帧=低头沉思

> 画质优先：竖屏单图约 5–10 积分/张。每镜 2 张共约 10–20 积分。若想省积分，封面镜可只出首帧（用 ffmpeg Ken Burns 兜底），但诗句镜必须首尾双帧。

### 阶段 2：生成动态镜头（用所选生视频模型，首尾帧插值——必选）
使用 `model_config.json` 中的 `video_provider` 生成（默认内置 `VideoGen`；若选了其他技能，按 `references/model-providers.md` 调度表调用）。
**首尾帧插值是本技能「真动作」的核心**——所选视频模型须支持「首帧 + 尾帧/关键帧」（内置 VideoGen 用 `last_image`，Seedance 等用关键帧）；若不支持，见 model-providers.md 退化方案。
对第 i 个镜头调用所选生成器（默认即 `VideoGen`）：
- `image`: 该镜**首帧** `img_ii_first.png`
- **`last_image`: 该镜**尾帧** `img_ii_last.png`（必传！这是实现真实人物动作的核心）**
- `seconds`: 默认 `5`（compose 会按朗诵时长变速/定格，不必严守）
- **不要传 `aspect_ratio`**（当前 VideoGen 后端不支持该参数，会报 400）；画面比例由输入首帧图自动推断（竖图→竖屏），所以首帧务必用竖图 `1024x1536`
- `resolution`: `"720P"`（竖屏成片足够；要更高清用 `"1080P"`）
- `prompt`: 用 prompt-templates.md 的「动态提示词」模板（**固定机位、画面内运动**）。应描述从首帧到尾帧的**完整人物动作过程** + 物体自然运动 + 光影渐变（如「头部从低垂缓缓抬起，仰脸望向明月；帘幕轻拂、烛火摇曳」）。**严禁写任何运镜/旋转/推拉摇移词**——那会诱导相机旋转假动。
- `watermark`: 建议 `false`
- 把生成结果**重命名为 `<workdir>/scene_ii.mp4`**（与镜头顺序一致，`compose_video.py` 按 `scene_*.mp4` 顺序扫描）

> 若所选视频模型不可用 / 不支持首尾帧：用 `gen_scene_video.py` 以首帧+尾帧做 ffmpeg 交叉淡入兜底（见脚本帮助），但效果远不如 AI 首尾帧插值。

### 阶段 3：生成朗诵音频 + 时间轴（gen_tts.py）
```
python <skill>/scripts/gen_tts.py \
  --lines "句1" "句2" "句3" "句4" \
  --outdir <workdir> \
  --voice zh-CN-YunxiNeural \
  --title-line "<题名> <朝代> <作者>"
```
- `--lines` **只放旁白正文**（来自 `script.json` 的 `lines`），不要包含题名；题名用 `--title-line` 单独播报（会作为第 0 句，在封面镜期间显示）
- 固定输出 `<workdir>/voice_full.mp3` 与 `<workdir>/timeline.json`（含每句精确起止，供合成对齐）
- 音色预设见脚注；语速默认 `-22%` 更从容

### 阶段 4：生成 BGM（gen_bgm.py）
```
python <skill>/scripts/gen_bgm.py --duration <成片时长> --mood <script.mood> --sections <镜头单元数> --output <workdir>/bgm.mp3
```
- `--duration` 取略大于 `timeline.json` 的 `total_duration`（如 27，compose 会用 aloop 循环，不严格也可）
- `--sections` 取镜头单元数（= `n_scenes`）；`mood` 取 `script.json` 的 `mood`（nostalgic/serene/melancholy/heroic/joyful）
- 输出到 `--output` 指定路径（如 `<workdir>/bgm.mp3`）

### 阶段 5：合成成片（compose_video.py）
```
python <skill>/scripts/compose_video.py \
  --workdir <workdir> \
  --timeline timeline.json \
  --bgm bgm.mp3 \
  --title-text "<script.json 的 title> · <dynasty> · <author>" \
  --size 720x1280 --output <题名>.mp4
```
- 以 `timeline.json` 为主时钟，自动把每个 `scene_*.mp4` 适配到对应诗句时长（变速/定格），xfade 转场，字幕按绝对时间烧录
- **`scene_01.mp4 …` 必须位于 `<workdir>` 根目录**（VideoGen 可能把视频输出到子目录，需先移到根目录，或改用 `--scenes` 显式列出路径）；`timeline.json` / `voice_full.mp3` / `bgm.mp3` 默认在 `<workdir>` 内自动查找
- 默认竖屏 `720x1280`；横屏改 `--size 1280x720`
- 产出 `<workdir>/<题名>.mp4` 即最终成片；`sync_offset` 应 ≤ 0.6s

### 阶段 6：交付
- 用 `present_files` 把 `<题名>.mp4` 交给用户预览
- 提示可微调项：画风 `--style`、音色 `--voice`、BGM `--mood`、转场 `--transition`、分辨率 `--size`

## 关键设计点
- **⚠️ 铁律一（诗意先行）**：生成任何图像前，必须先推敲每句诗的字面含义、创作背景、画面转译和动作设计。禁止不假思索地把诗句关键词塞进模板就调用 ImageGen——那会导致构图失真、动作缺失。
- **⚠️ 铁律二（首尾帧真动）**：每个镜头必须生成首帧+尾帧两张图，用 VideoGen 的 `last_image` 做首尾帧插值。尾帧与首帧之间必须有真实的人物姿态变化或物体位移。禁止单图生视频（只能产生镜头推移等假动态）。
- **⚠️ 铁律三（动态合理、禁运镜）**：动态镜头必须「固定机位、画面内运动」，禁止任何镜头旋转/推拉/摇移。动态要符合场景物理逻辑并服务于诗意（人物动作 + 物体自然运动 + 光影渐变三层设计），不是为动而动。尾帧 `input_fidelity` 须用 `0.82` 锁死机位，避免机位漂移被模型当成旋转。
- **音画严格同步**：先有朗诵时间轴，再以它为「主时钟」反推每个镜头时长，字幕按绝对时间换算相对时间烧录——这是与原技能「固定镜头秒数」的本质区别。
- **封面镜模式**：`scenes == 句数 + 1` 时，首镜为独立封面，避免首句画面被拉伸定格覆盖。
- **零外部 API**：edge-tts + 本地 BGM + ffmpeg，全链路可离线（仅 ImageGen/VideoGen 为内置工具）。
- **⚠️ 模型可插拔**：生图/生视频模型不写死。运行前在「阶段 0.5」梳理用户环境里的可用能力（内置工具 + 已安装技能），用 `AskUserQuestion` 让用户自选，选择写入 `model_config.json`（本次项目 + 全局默认）。外部技能型 provider 先 `Skill` 加载其文档再调用，参数以该技能为准。
- **统一中间表示（script.json）**：诗与任意叙事文本都先归一成 `<workdir>/script.json`（见 `references/script-schema.md`），阶段 1–5 只认它，故两种来源完全复用同一套视频管线；新增文本类型无需改下游。库外诗写入工作目录缓存库（`poems_user.json`），技能自带 `poems.json` 保持只读、可分发包不受影响。

## 文件清单
- `SKILL.md`：本流程
- `references/prompt-templates.md`：画风前缀 + 分镜/动态提示词模板
- `references/model-providers.md`：生图/生视频模型调度表（各 provider 调用要点 + 退化方案）
- `model_config.json`：用户选择的生图/生视频模型（全局默认存于 `<skill>/`，本次项目另存一份到 `<workdir>/`）
- `references/script-schema.md`：统一中间表示 `script.json` 结构 + 叙事文本分镜规范（agent 直出依据）
- `scripts/resolve_poem.py`：按诗名检索诗库（技能库 + 工作目录缓存库合并查询），输出 `script.json`；`--append` 把库外诗写入工作目录缓存库
- `scripts/poems.json`：技能自带精选诗库（约 41 首，只读，运行期绝不修改）；库外诗存 `<workdir>/poems_user.json`
- `scripts/gen_tts.py`：edge-tts 朗诵 + timeline.json
- `scripts/gen_bgm.py`：程序化 BGM（按 mood）
- `scripts/gen_scene_video.py`：ffmpeg 兜底分镜（首尾帧交叉淡入 / Ken Burns）
- `scripts/compose_video.py`：时间轴驱动的合成器

## 脚注：edge-tts 音色预设
- `zh-CN-YunxiNeural` 男·温润（默认）
- `zh-CN-YunjianNeural` 男·沉稳
- `zh-CN-YunyangNeural` 男·讲述
- `zh-CN-XiaoxiaoNeural` 女·清亮
- `zh-CN-XiaoyiNeural` 女·温柔
