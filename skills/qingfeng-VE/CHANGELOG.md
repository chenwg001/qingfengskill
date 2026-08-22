# qingfeng-VE 技能优化记录

**日期**: 2026-08-20  
**版本**: v3.0

## 优化内容

### 0. 修复 `--intro-image` 参数失效（图片片头 bug）

**问题**: 主流程包装阶段，`else` 分支永远以 `image_path=None` + 默认标题 `"视频内容"` 调用 `generate_intro_video()`，导致命令行传入的 `--intro-image`（配置文档第8项 B「自定义图片」）被完全忽略，片头只会生成文字标题而非用户指定的图片。

**修复** (`scripts/make_video.py`, 片头包装分支):
- 新增 `elif args.intro_image and os.path.exists(args.intro_image)` 分支，优先使用自定义图片
- 仅给 `--intro-image` → 纯图片缩放片头（`title=""` 触发 `image_zoom` 模式）
- 同时给 `--intro-image` + `--intro-title` → 图片背景 + 标题叠加模式
- 都不给 → 仍回退默认星空标题片头（行为不变）

**影响**: 修复后「配置文档第8项 B」真正生效，与 `workflow.md`「星空背景片头（带图片缩放动画）」一致。

## 历史版本

### v2.0（2026-08-20）

### 1. 去除个人痕迹

**修改前**:
- `tts.py`: 硬编码 `LOCAL_MODEL_DIR = "D:/chenw/AgentSpace/WorkBuddy/..."`
- `tts.py`: 硬编码 `LOCAL_PYTHON = "C:/Users/chenw/.workbuddy/binaries/..."`
- `make_video.py`: 硬编码参考音频路径 `"D:/趣味活动/男声1.MP3"`
- `make_video.py`: 硬编码 Python 路径 `"C:/Users/chenw/.workbuddy/..."`

**修改后**:
- 使用环境变量 `QWEN_TTS_MODEL_DIR` 和 `QWEN_TTS_PYTHON`
- 创建 `config.json` 配置文件（可通过环境变量覆盖）
- 所有硬编码路径改为可选参数或环境变量

### 2. 添加依赖检测

新增 `scripts/check_deps.py` 脚本：
- 检测 FFmpeg、edge-tts、Pillow、numpy 等必需依赖
- 提示本地 TTS 克隆的可选配置
- 提供安装命令和说明

### 3. 重写 SKILL.md

**改进**:
- 删除个人项目路径引用（如 `D:/趣味活动`、`D:/chenw/AgentSpace/...`）
- 添加完整的前置依赖检查表格
- 使用 `${CLAUDE_SKILL_DIR}` 引用技能目录
- 添加通用配置说明和快速开始示例
- 删除过于详细的内部流程描述，保持文档简洁

### 4. 新增 README.md

提供技能概述、核心特性、依赖说明、使用示例等通用信息。

### 5. 创建配置文件

新增 `config.json`：
```json
{
  "model_dir": null,
  "python_exe": null
}
```

用户可通过编辑此文件或设置环境变量来配置本地 TTS 环境。

## 打包内容

```
qingfeng-VE/
├── SKILL.md                  # 技能主文档（355行 → 356行）
├── README.md                 # 使用说明（新增）
├── config_template.md        # 配置模板
├── config_template.docx      # 配置模板（Word版本）
├── config.json               # 本地TTS配置（新增）
├── scripts/
│   ├── make_video.py         # 主剪辑脚本（已修复硬编码）
│   ├── tts.py                # TTS配音脚本（已修复硬编码）
│   ├── gen_bgm.py            # BGM生成脚本
│   ├── video_factory.py      # 视频工厂脚本
│   └── check_deps.py         # 依赖检测脚本（新增）
└── samples/                  # 示例文件
```

## 使用方法

### 安装

1. 解压 `qingfeng-VE_skill_v2.zip` 到工作目录
2. 运行依赖检测：`python scripts/check_deps.py`
3. （可选）配置本地 TTS：编辑 `config.json` 或设置环境变量

### 配置本地 TTS（可选）

**方式一：编辑配置文件**
```json
{
  "model_dir": "/path/to/qwen3-tts-model",
  "python_exe": "/path/to/python-with-qwen_tts"
}
```

**方式二：设置环境变量**
```bash
export QWEN_TTS_MODEL_DIR=/path/to/qwen3-tts-model
export QWEN_TTS_PYTHON=/path/to/python-with-qwen_tts
```

## 向后兼容性

- 默认使用 edge-tts 在线配音，无需额外配置
- 本地 TTS 克隆为可选功能，不影响基本使用
- 配置文件留空时使用环境变量，环境变量未设置时提示用户配置
