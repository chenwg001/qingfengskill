"""
TTS 配音模块（通用技能）
- 默认/在线：edge-tts（需 pip install edge-tts，联网）
- 本地克隆：Qwen3-TTS-12Hz-0.6B-Base（用带 qwen_tts 的 python 环境运行）

用法：
  # 本地克隆（用带 qwen_tts 的 python 环境运行）
  python tts.py --backend local --text "..." --ref "path/to/ref.mp3" --out work/voiceover.wav
  # 在线配音（主环境运行）
  python tts.py --backend edge --text "..." --voice zh-CN-YunxiNeural --out work/voiceover.wav

环境变量配置（修改 config.json 或直接设置）：
  QWEN_TTS_MODEL_DIR: 本地模型目录路径
  QWEN_TTS_PYTHON: 带 qwen_tts 环境的 Python 解释器路径
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile

# 从配置文件或环境变量读取路径
def load_config():
    """加载技能配置文件"""
    config_path = os.path.join(os.path.dirname(__file__), "config.json")
    defaults = {
        "model_dir": None,  # 默认从环境变量读取
        "python_exe": None  # 默认从环境变量读取
    }
    if os.path.exists(config_path):
        with open(config_path, 'r', encoding='utf-8') as f:
            defaults.update(json.load(f))
    return {
        "model_dir": defaults["model_dir"] or os.environ.get("QWEN_TTS_MODEL_DIR"),
        "python_exe": defaults["python_exe"] or os.environ.get("QWEN_TTS_PYTHON")
    }

CONFIG = load_config()

# 离线加载：禁止联网拉 HuggingFace
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")


def _decode_to_wav(path, sr=24000):
    """用系统 ffmpeg 把任意音频解码成单声道 wav，返回 (wav_float32, sr)"""
    import numpy as np

    wav_tmp = tempfile.mktemp(suffix=".wav")
    subprocess.run(
        ["ffmpeg", "-y", "-i", path, "-ar", str(sr), "-ac", "1", wav_tmp],
        check=True, capture_output=True,
    )
    try:
        import soundfile as sf
        wav, _ = sf.read(wav_tmp, dtype="float32", always_2d=False)
    except Exception:
        import wave
        with wave.open(wav_tmp, "rb") as w:
            n = w.getnframes()
            raw = w.readframes(n)
            wav = np.frombuffer(raw, dtype="<i2").astype("float32") / 32768.0
    os.remove(wav_tmp)
    return wav, sr


def generate_local(text, ref_path, out_path, language="Auto", device=None):
    import numpy as np
    import re
    import torch
    from qwen_tts import Qwen3TTSModel
    import soundfile as sf

    if device is None:
        device = "cuda:0" if torch.cuda.is_available() else "cpu"
    dtype = torch.bfloat16 if "cuda" in str(device) else torch.float32

    wav, sr = _decode_to_wav(ref_path, 24000)
    ref_audio = (np.asarray(wav, dtype=np.float32), int(sr))

    tts = Qwen3TTSModel.from_pretrained(
        CONFIG["model_dir"],
        device_map=device,
        dtype=dtype,
        attn_implementation=None,   # flash-attn 未装，用原生实现
    )

    # 按句切分，逐句生成后拼接：规避单次超长文本生成失败
    sents = [s.strip() for s in re.split(r"(?<=[。！？\n])", text.strip()) if s.strip()]
    sents = sents or [text.strip()]

    chunks = []
    sr_out = 24000
    for s in sents:
        w, so = tts.generate_voice_clone(
            text=s,
            language=language,
            ref_audio=ref_audio,
            ref_text=None,
            x_vector_only_mode=True,   # 无参考文本，仅用说话人向量
        )
        chunks.append(np.asarray(w[0], dtype=np.float32))
        sr_out = int(so)
    merged = np.concatenate(chunks) if len(chunks) > 1 else chunks[0]
    sf.write(out_path, merged, sr_out)
    return out_path


def generate_edge(text, out_path, voice="zh-CN-YunxiNeural"):
    import asyncio
    import edge_tts

    async def _run():
        comm = edge_tts.Communicate(text.strip(), voice)
        # 同时输出音频与字幕边界（用于精确字幕）
        sub_path = out_path + ".srt.tmp"
        with open(out_path, "wb") as af, open(sub_path, "w", encoding="utf-8") as sf_sub:
            async for ev in comm.stream():
                if ev["type"] == "audio":
                    af.write(ev["data"])
                elif ev["type"] == "WordBoundary":
                    # 记录时间轴
                    sf_sub.write(f"{ev}\n")
    asyncio.run(_run())
    return out_path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", choices=["local", "edge"], default="edge")
    ap.add_argument("--text", required=True)
    ap.add_argument("--ref", required=True, help="本地克隆参考音频路径（仅 --backend local 时需要）")
    ap.add_argument("--voice", default="zh-CN-YunxiNeural")
    ap.add_argument("--language", default="Auto")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    if args.backend == "local":
        if not CONFIG["model_dir"]:
            print("[错误] 未配置本地模型路径，请设置环境变量 QWEN_TTS_MODEL_DIR 或在 config.json 中配置", file=sys.stderr)
            sys.exit(1)
        if not CONFIG["python_exe"]:
            print("[错误] 未配置 Python 路径，请设置环境变量 QWEN_TTS_PYTHON 或在 config.json 中配置", file=sys.stderr)
            sys.exit(1)
        generate_local(args.text, args.ref, args.out, language=args.language)
    else:
        generate_edge(args.text, args.out, voice=args.voice)
    print(f"[TTS] 完成 -> {args.out}")


if __name__ == "__main__":
    main()
