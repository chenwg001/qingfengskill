#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
古诗朗诵配音生成器（edge-tts 主引擎，Windows SAPI 兜底）。

与常规 TTS 的区别：本脚本按「句」生成，再用可控气口拼接为整段朗诵，
同时输出精确的 timeline.json —— 后续字幕与分镜时长可以据此严格对齐音频，
实现真正的音画同步，而不是把朗诵硬铺在固定时长的画面上。

用法：
    python gen_tts.py \
        --lines "床前明月光" "疑是地上霜" "举头望明月" "低头思故乡" \
        --outdir D:/work/jingyesi \
        --voice zh-CN-YunxiNeural \
        --rate-percent -20 \
        --gap 0.9 --lead-in 1.5 --tail 2.0

输出：
    <outdir>/voice_full.mp3     整段朗诵
    <outdir>/voice_01.mp3 ...   分句朗诵（保留，便于单句重做）
    <outdir>/timeline.json      每句在整段音频中的起止时间
    stdout: timeline.json 内容
"""

import argparse
import asyncio
import io
import json
import os
import subprocess
import sys

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# 古诗朗诵推荐音色（edge-tts 中文神经音色）
VOICE_PRESETS = {
    "male_gentle": "zh-CN-YunxiNeural",       # 温润男声，最百搭，思乡/闲适/哀婉
    "male_solemn": "zh-CN-YunjianNeural",     # 浑厚男声，豪迈/边塞/咏史
    "female_clear": "zh-CN-XiaoxiaoNeural",   # 清亮女声，明丽/闺怨/写景
    "female_soft": "zh-CN-XiaoyiNeural",      # 柔和女声，婉约/小令
    "male_narrate": "zh-CN-YunyangNeural",    # 播音男声，叙事长诗
}


def parse_args():
    p = argparse.ArgumentParser(description="生成古诗朗诵配音与时间轴")
    p.add_argument("--lines", nargs="+", required=True, help="诗句列表，按顺序")
    p.add_argument("--outdir", required=True, help="输出目录")
    p.add_argument("--voice", default="zh-CN-YunxiNeural",
                   help="音色 ID 或预设名（male_gentle/male_solemn/female_clear/female_soft/male_narrate）")
    # 注意：用整数百分比而非 "-20%" 字符串，避免 argparse 把负号开头的值误判为选项
    p.add_argument("--rate-percent", type=int, default=-20,
                   help="语速调整百分比，古诗建议 -25 ~ -10（负数为放慢）")
    p.add_argument("--volume-percent", type=int, default=0, help="音量调整百分比")
    p.add_argument("--pitch-hz", type=int, default=0, help="音高调整（Hz）")
    p.add_argument("--gap", type=float, default=0.9, help="句间气口（秒）")
    p.add_argument("--lead-in", type=float, default=1.5, help="开头留白（秒），给 BGM 前奏")
    p.add_argument("--tail", type=float, default=2.0, help="结尾留白（秒）")
    p.add_argument("--title-line", default=None,
                   help="可选：开头朗读的题目（如「静夜思 唐 李白」），会作为第 0 句并单独留更长气口")
    p.add_argument("--title-gap", type=float, default=1.4, help="题目与正文之间的气口（秒）")
    p.add_argument("--engine", default="auto", choices=["auto", "edge", "sapi"],
                   help="TTS 引擎，auto=优先 edge-tts，失败回退 SAPI")
    return p.parse_args()


def ffprobe_duration(path: str) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", path],
        capture_output=True, text=True,
    )
    if r.returncode != 0 or not r.stdout.strip():
        raise RuntimeError(f"ffprobe 读取时长失败: {path}\n{r.stderr}")
    return float(r.stdout.strip())


async def _edge_say(text: str, out_path: str, voice: str, rate: str, volume: str, pitch: str):
    import edge_tts
    comm = edge_tts.Communicate(text, voice, rate=rate, volume=volume, pitch=pitch)
    await comm.save(out_path)


def edge_say(text: str, out_path: str, voice: str, rate: str, volume: str, pitch: str):
    asyncio.run(_edge_say(text, out_path, voice, rate, volume, pitch))
    if not os.path.exists(out_path) or os.path.getsize(out_path) < 512:
        raise RuntimeError(f"edge-tts 输出异常: {out_path}")


def sapi_say(text: str, out_path: str, rate_percent: int):
    """Windows SAPI 兜底（无网络时可用，音质弱于 edge-tts）。"""
    sapi_rate = max(-10, min(10, round(rate_percent / 10)))
    wav_path = out_path.rsplit(".", 1)[0] + ".wav"
    ps = (
        "Add-Type -AssemblyName System.Speech; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        f"$s.Rate = {sapi_rate}; "
        f"$s.SetOutputToWaveFile('{wav_path}'); "
        f"$s.Speak('{text}'); $s.Dispose()"
    )
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                       capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(wav_path):
        raise RuntimeError(f"SAPI 合成失败: {r.stderr}")
    subprocess.run(["ffmpeg", "-y", "-i", wav_path, "-c:a", "libmp3lame", "-b:a", "128k", out_path],
                   capture_output=True, check=True)
    os.remove(wav_path)


def synth_line(text: str, out_path: str, args) -> str:
    """合成单句，返回实际使用的引擎名。"""
    rate = f"{args.rate_percent:+d}%"
    volume = f"{args.volume_percent:+d}%"
    pitch = f"{args.pitch_hz:+d}Hz"
    if args.engine in ("auto", "edge"):
        try:
            edge_say(text, out_path, args.voice, rate, volume, pitch)
            return "edge-tts"
        except Exception as e:
            if args.engine == "edge":
                raise
            print(f"  edge-tts 失败（{e}），回退 SAPI", file=sys.stderr)
    sapi_say(text, out_path, args.rate_percent)
    return "sapi"


def concat_with_gaps(segments, out_path: str, sample_rate: int = 24000):
    """
    segments: [("audio", path) | ("silence", seconds), ...]
    用 ffmpeg concat filter 串接，统一重采样，避免不同源参数不一致导致的时长漂移。
    """
    inputs, filters, labels = [], [], []
    idx = 0
    for kind, val in segments:
        if kind == "audio":
            inputs += ["-i", val]
        else:
            if val <= 0:
                continue
            inputs += ["-f", "lavfi", "-t", f"{val:.3f}", "-i", f"anullsrc=r={sample_rate}:cl=mono"]
        filters.append(f"[{idx}:a]aresample={sample_rate},aformat=sample_fmts=s16:channel_layouts=mono[a{idx}]")
        labels.append(f"[a{idx}]")
        idx += 1

    filter_complex = ";".join(filters) + ";" + "".join(labels) + f"concat=n={idx}:v=0:a=1[out]"
    cmd = ["ffmpeg", "-y"] + inputs + [
        "-filter_complex", filter_complex,
        "-map", "[out]",
        "-c:a", "libmp3lame", "-b:a", "192k",
        out_path,
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"拼接朗诵失败:\n{r.stderr[-2000:]}")


def main():
    args = parse_args()
    args.voice = VOICE_PRESETS.get(args.voice, args.voice)
    outdir = os.path.abspath(args.outdir)
    os.makedirs(outdir, exist_ok=True)

    engine_used = None
    segments = [("silence", args.lead_in)]
    cursor = args.lead_in
    timeline = []

    # 可选：题目播报
    if args.title_line:
        tpath = os.path.join(outdir, "voice_00_title.mp3")
        print(f"[题目] {args.title_line}", file=sys.stderr)
        engine_used = synth_line(args.title_line, tpath, args)
        d = ffprobe_duration(tpath)
        segments.append(("audio", tpath))
        timeline.append({"index": 0, "text": args.title_line, "role": "title",
                         "start": round(cursor, 3), "end": round(cursor + d, 3), "duration": round(d, 3)})
        cursor += d
        segments.append(("silence", args.title_gap))
        cursor += args.title_gap

    n = len(args.lines)
    for i, line in enumerate(args.lines, start=1):
        path = os.path.join(outdir, f"voice_{i:02d}.mp3")
        print(f"[{i}/{n}] {line}", file=sys.stderr)
        engine_used = synth_line(line, path, args)
        d = ffprobe_duration(path)
        segments.append(("audio", path))
        timeline.append({"index": i, "text": line, "role": "line",
                         "start": round(cursor, 3), "end": round(cursor + d, 3), "duration": round(d, 3)})
        cursor += d
        if i < n:
            segments.append(("silence", args.gap))
            cursor += args.gap

    segments.append(("silence", args.tail))
    cursor += args.tail

    full_path = os.path.join(outdir, "voice_full.mp3")
    concat_with_gaps(segments, full_path)
    total = ffprobe_duration(full_path)

    result = {
        "voice_file": full_path,
        "engine": engine_used,
        "voice_id": args.voice,
        "rate": f"{args.rate_percent:+d}%",
        "total_duration": round(total, 3),
        "lead_in": args.lead_in,
        "gap": args.gap,
        "tail": args.tail,
        "lines": timeline,
    }
    tl_path = os.path.join(outdir, "timeline.json")
    with open(tl_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"\n[OK] 朗诵已生成: {full_path} ({total:.2f}s)", file=sys.stderr)
    print(f"[OK] 时间轴已生成: {tl_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
