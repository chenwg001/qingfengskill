# 生图 / 生视频模型调度表（model-providers）

本技能**不写死**生图/生视频模型。运行前在「阶段 0.5」梳理用户环境里可用的能力，让用户自己选，
选择写入 `<workdir>/model_config.json` 与 `<skill>/model_config.json`（全局默认）。

`model_config.json` 格式：
```json
{
  "image_provider": "builtin_imagen",
  "video_provider": "builtin_videogen",
  "updated_at": "2026-08-06"
}
```

> ⚠️ 关于外部技能的参数：下表只给出「已知概览」与调用入口。**真正调用前必须先用 `Skill` 加载该技能，
> 以其 SKILL.md 的准确接口为准**，不要凭记忆硬写参数（避免过期/错误）。

---

## 一、生图模型（image_provider）

### builtin_imagen — WorkBuddy 内置 ImageGen（默认·推荐）
- **调用**：直接调用 `ImageGen` 工具（无需先加载技能）
- **首帧**：text-to-image，`size` 竖屏 `1024x1536`（横屏 `1536x1024`），`style` 按画风映射
- **尾帧**（图生图）：`image` 传数组 `["首帧路径"]`，`input_fidelity: "0.82"` 锁机位
- 详见 SKILL.md「阶段 1」与 prompt-templates.md

### qclaw_image — QClaw 图像生成
- **调用**：`Skill: qclaw-generate-image` 加载后按其接口调用
- **首帧**：按其技能接口文生图，竖图保证成片竖屏
- **尾帧**（图生图）：把首帧作参考图，提示词强调「机位、构图与首帧完全一致」以近似锁机位；具体参数以其 SKILL.md 为准

### 其他（用户在 AskUserQuestion「其他」里自填）
- 先 `Skill: <用户填的技能名>` 加载，确认其文生图/图生图接口后再用

---

## 二、生视频模型（video_provider）

### builtin_videogen — WorkBuddy 内置 VideoGen（默认·推荐）
- **调用**：直接调用 `VideoGen` 工具
- **关键**：`image`=首帧，`last_image`=尾帧（首尾帧插值，产生真实人物动作）
- **不要传 `aspect_ratio`**（后端按输入图比例推断）；`resolution` 用 `720P`/`1080P`
- **固定机位、画面内运动**（铁律三）；`watermark: false`
- 详见 SKILL.md「阶段 2」与 prompt-templates.md

### seedance — Seedance / 即梦导演
- **调用**：`Skill: seedance-director` 加载后按其接口调用
- 同样用首帧 + 尾帧（关键帧）做插值

### ffmpeg_fallback — 无模型兜底
- **调用**：`scripts/gen_scene_video.py`（首帧+尾帧交叉淡入，或仅首帧 Ken Burns）
- **用途**：环境无可用视频模型、或想离线快速出片时
- 效果弱于 AI 首尾帧插值，但能保证流水线跑通

---

## 三、退化方案（所选模型能力受限时）

- **视频模型不支持「首帧 + 尾帧/关键帧」**：
  1. 若支持纯文生视频：用首帧图 + 文本动作描述生成镜头（失去精确首尾控制，但仍有动态）；
  2. 否则用 `gen_scene_video.py` 的 ffmpeg 兜底（首尾帧交叉淡入）。
- **生图模型不支持 image-to-image（无法出尾帧）**：
  - 用 `gen_scene_video.py` 仅首帧 + Ken Burns 代替（失去人物真动作，仅相机微推）；
  - 或在「阶段 0.5」改选支持图生图的生图模型。
- **任何情况下**：BGM / 朗诵 / 合成仍由本技能脚本完成，不受影响。

---

## 四、默认候选

> 最终以「阶段 0.5」运行时实查到的可用技能为准；以下为内置默认与已验证可入候选的技能。

- 生图默认：内置 `ImageGen` · 其他可选 `qclaw-generate-image`
- 生视频默认：内置 `VideoGen` · 其他可选 `seedance-director` · `gen_scene_video.py`(ffmpeg 兜底)
