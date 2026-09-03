#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
古风意境 BGM 生成器（本地程序化合成，无需联网、无 API 成本）。

相比"固定旋律模板"的做法，本脚本按情感（mood）选择调式、速度、音区与配器，
再用带引力的五声音阶随机游走生成旋律，并以 A-A'-B-A'' 的曲式组织乐句，
因此任意诗、任意句数都能得到一首结构完整、气质匹配的背景音乐。

用法：
    python gen_bgm.py --duration 24 --mood nostalgic --sections 4 \
        --output D:/work/jingyesi/bgm.mp3

mood 取值：
    nostalgic  思乡、羁旅、怀远   —— 羽调式，慢，中低音区，古琴质感
    serene     闲适、田园、禅意   —— 宫调式，中慢速，清亮古筝
    melancholy 哀婉、悲凉、送别   —— 商调式，最慢，低音区，长混响
    heroic     豪迈、边塞、咏史   —— 徵调式，稍快，厚低音 + 鼓点
    joyful     明丽、春景、欢愉   —— 宫调式，轻快，高音区，跳跃琶音
"""

import argparse
import io
import json
import os
import subprocess
import sys
import tempfile

import numpy as np
from scipy import signal
from scipy.io import wavfile

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

SR = 44100

# 十二平均律音名 -> 频率（用于按调式动态构建音阶）
A4 = 440.0
NOTE_INDEX = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def note_freq(name: str, octave: int) -> float:
    """如 note_freq('C', 4) -> 261.63"""
    semis = NOTE_INDEX[name] + (octave - 4) * 12 - 9  # 相对 A4
    return A4 * (2 ** (semis / 12.0))


# 五声调式：以 C 宫系统为基础，五个调式对应不同主音
# 宫(C) 商(D) 角(E) 徵(G) 羽(A)
PENTATONIC = ["C", "D", "E", "G", "A"]

# bright: 泛音强度，越大音色越亮（古筝感）；越小越暗（古琴感）
MOODS = {
    "nostalgic": dict(tonic="A", octaves=(3, 4), beat=0.62, decay=2.0, bright=0.65,
                      drone_gain=0.30, melody_gain=0.50, reverb=0.50, percussion=0.0,
                      leap_bias=0.30, rest_prob=0.22),
    "serene": dict(tonic="C", octaves=(4, 5), beat=0.55, decay=2.4, bright=1.00,
                   drone_gain=0.24, melody_gain=0.52, reverb=0.42, percussion=0.10,
                   leap_bias=0.35, rest_prob=0.18),
    "melancholy": dict(tonic="D", octaves=(3, 4), beat=0.72, decay=1.7, bright=0.45,
                       drone_gain=0.34, melody_gain=0.46, reverb=0.58, percussion=0.0,
                       leap_bias=0.22, rest_prob=0.28),
    "heroic": dict(tonic="G", octaves=(3, 4), beat=0.46, decay=2.6, bright=0.85,
                   drone_gain=0.38, melody_gain=0.58, reverb=0.34, percussion=0.42,
                   leap_bias=0.52, rest_prob=0.10),
    "joyful": dict(tonic="C", octaves=(4, 5), beat=0.42, decay=2.8, bright=1.25,
                   drone_gain=0.20, melody_gain=0.55, reverb=0.30, percussion=0.22,
                   leap_bias=0.48, rest_prob=0.12),
}


def build_scale(tonic: str, octaves) -> list:
    """构建以 tonic 为主音的五声音阶频率表（跨指定八度，升序）。"""
    start = PENTATONIC.index(tonic)
    order = PENTATONIC[start:] + PENTATONIC[:start]
    freqs = []
    lo, hi = octaves
    for octv in range(lo, hi + 1):
        for name in order:
            # 音名顺序绕回时八度 +1
            oct_adj = octv + (1 if PENTATONIC.index(name) < start else 0)
            freqs.append(note_freq(name, oct_adj))
    return sorted(set(round(f, 3) for f in freqs))


def pluck(freq: float, dur: float, decay: float, bright: float = 1.0, sr: int = SR) -> np.ndarray:
    """弹拨音色（古琴/古筝质感）：基音 + 泛音 + 指数衰减包络。bright 控制泛音强度。"""
    n = max(1, int(sr * dur))
    t = np.linspace(0, dur, n, endpoint=False)
    w = np.sin(2 * np.pi * freq * t)
    w += 0.32 * bright * np.sin(2 * np.pi * freq * 2 * t)
    w += 0.16 * bright * bright * np.sin(2 * np.pi * freq * 3 * t)
    w += 0.07 * bright * bright * np.sin(2 * np.pi * freq * 4.02 * t)  # 略失谐，更像真实弦
    env = np.exp(-decay * t)
    atk = max(1, int(0.012 * sr))
    env[:atk] *= np.linspace(0, 1, atk)
    fade = max(1, int(min(0.25, dur * 0.3) * sr))
    env[-fade:] *= np.linspace(1, 0, fade)
    return w * env


def drone(root: float, dur: float, sr: int = SR) -> np.ndarray:
    """根音 + 五度持续音，带缓慢起伏，作为和声底。"""
    n = max(1, int(sr * dur))
    t = np.linspace(0, dur, n, endpoint=False)
    w = 0.55 * np.sin(2 * np.pi * root * t)
    w += 0.30 * np.sin(2 * np.pi * root * 1.5 * t)
    w += 0.12 * np.sin(2 * np.pi * root * 2 * t)
    w *= 0.5 + 0.10 * np.sin(2 * np.pi * 0.16 * t)
    fade = max(1, int(min(1.2, dur * 0.25) * sr))
    w[:fade] *= np.linspace(0, 1, fade)
    w[-fade:] *= np.linspace(1, 0, fade)
    return w


def reverb(x: np.ndarray, amount: float, sr: int = SR) -> np.ndarray:
    """多抽头延迟混响。"""
    if amount <= 0:
        return x
    out = x.copy()
    for i, (ms, g) in enumerate([(63, 0.55), (97, 0.42), (149, 0.30), (211, 0.20)]):
        d = int(sr * ms / 1000.0)
        if d >= len(x):
            continue
        tail = np.zeros_like(x)
        tail[d:] = x[:-d] * g * amount
        out += tail
    return out


def make_phrase(scale, rng, beats: int, cfg, center_idx: int, cadence_idx: int):
    """
    生成一个乐句：返回 [(scale_index, start_beat, dur_beats), ...]
    - 音高在音阶上做带引力的随机游走（偏离中心越远，回归概率越大）
    - 句尾落在稳定音（cadence_idx），形成"收句"感
    """
    notes = []
    pos = 0.0
    idx = center_idx
    durations = [0.5, 0.75, 1.0, 1.5]
    weights = [0.34, 0.28, 0.26, 0.12]
    while pos < beats - 1.2:
        if rng.random() < cfg["rest_prob"]:
            pos += 0.5
            continue
        d = float(rng.choice(durations, p=weights))
        d = min(d, beats - 1.2 - pos) if pos + d > beats - 1.2 else d
        if d < 0.4:
            break
        notes.append((idx, pos, d))
        pos += d
        # 下一个音：小步为主，偶尔跳进；带向中心的引力
        step = rng.choice([-2, -1, 1, 2], p=[0.18, 0.36, 0.32, 0.14])
        if rng.random() < cfg["leap_bias"] * 0.35:
            step *= 2
        pull = np.sign(center_idx - idx) * (1 if abs(center_idx - idx) > 3 else 0)
        idx = int(np.clip(idx + step + pull, 0, len(scale) - 1))
    # 收句：落在稳定音，时值拉长
    notes.append((cadence_idx, min(pos, beats - 1.2), max(1.2, beats - pos)))
    return notes


def vary_phrase(phrase, rng, scale_len, cadence_idx):
    """A' 变奏：保持骨架，微调个别音与收句。"""
    out = []
    for i, (idx, st, d) in enumerate(phrase):
        if i < len(phrase) - 1 and rng.random() < 0.35:
            idx = int(np.clip(idx + rng.choice([-1, 1]), 0, scale_len - 1))
        out.append((idx, st, d))
    last = out[-1]
    out[-1] = (cadence_idx, last[1], last[2])
    return out


def generate(duration: float, mood: str, sections: int, seed: int):
    cfg = MOODS[mood]
    rng = np.random.default_rng(seed)
    scale = build_scale(cfg["tonic"], cfg["octaves"])
    tonic_freq = scale[0]
    center_idx = len(scale) // 2
    cadence_candidates = [0, len(scale) // 2]
    cadence_idx = cadence_candidates[0]

    total = int(SR * duration)
    audio = np.zeros(total, dtype=np.float64)

    beat = cfg["beat"]
    intro = min(4.0, duration * 0.18)
    outro = min(4.0, duration * 0.18)
    body = max(duration - intro - outro, duration * 0.4)
    sections = max(1, sections)
    sec_dur = body / sections
    beats_per_sec = max(4, int(round(sec_dur / beat)))

    # --- 曲式：A A' B A'' 循环 ---
    A = make_phrase(scale, rng, beats_per_sec, cfg, center_idx, cadence_idx)
    B = make_phrase(scale, rng, beats_per_sec, cfg, min(center_idx + 2, len(scale) - 1),
                    cadence_candidates[-1])
    plan = []
    for i in range(sections):
        m = i % 4
        if m == 0:
            plan.append(A)
        elif m == 1:
            plan.append(vary_phrase(A, rng, len(scale), cadence_idx))
        elif m == 2:
            plan.append(B)
        else:
            plan.append(vary_phrase(A, rng, len(scale), cadence_idx))

    def add(buf, start_s, seg):
        s = int(start_s * SR)
        if s >= total:
            return
        e = min(s + len(seg), total)
        buf[s:e] += seg[:e - s]

    # --- 前奏：drone + 上行琶音 ---
    add(audio, 0.0, drone(tonic_freq, intro) * cfg["drone_gain"] * 0.9)
    for k, si in enumerate([0, 2, 4, 5 if len(scale) > 5 else 4]):
        t0 = k * beat
        if t0 >= intro:
            break
        add(audio, t0, pluck(scale[min(si, len(scale) - 1)], beat * 1.8, cfg["decay"], cfg["bright"]) * 0.38)

    # --- 主体：每段 drone + 旋律 ---
    for i, phrase in enumerate(plan):
        seg_start = intro + i * sec_dur
        root = scale[0] if i % 2 == 0 else scale[min(2, len(scale) - 1)]
        add(audio, seg_start, drone(root / 2.0, sec_dur) * cfg["drone_gain"])
        for idx, sb, db in phrase:
            t0 = seg_start + sb * beat
            if t0 >= duration:
                break
            add(audio, t0, pluck(scale[idx], db * beat * 1.6, cfg["decay"], cfg["bright"]) * cfg["melody_gain"])

    # --- 尾声：旋律回落到主音 ---
    o_start = intro + sections * sec_dur
    if o_start < duration:
        add(audio, o_start, drone(tonic_freq / 2.0, duration - o_start) * cfg["drone_gain"] * 0.85)
        for k, si in enumerate([center_idx, max(center_idx - 2, 0), 2, 0]):
            t0 = o_start + k * beat * 1.6
            if t0 >= duration:
                break
            add(audio, t0, pluck(scale[si], beat * 2.6, cfg["decay"] * 0.7, cfg["bright"]) * 0.42)

    # --- 打击（仅部分 mood）---
    if cfg["percussion"] > 0:
        b, a = signal.butter(2, 900 / (SR / 2), btype="low")
        for t0 in np.arange(intro, duration - outro * 0.5, beat * 4):
            click = rng.normal(0, 0.05, int(0.06 * SR))
            click = signal.filtfilt(b, a, click)
            add(audio, float(t0), click * cfg["percussion"])

    # --- 空气感噪声垫 ---
    b, a = signal.butter(2, 700 / (SR / 2), btype="low")
    pad = signal.filtfilt(b, a, rng.normal(0, 0.016, total))
    audio += pad

    # --- 混响 + 归一化 + 首尾淡入淡出 ---
    audio = reverb(audio, cfg["reverb"])
    peak = np.max(np.abs(audio))
    if peak > 0:
        audio = audio / peak * 0.92
    f = min(int(1.2 * SR), total // 2)
    audio[:f] *= np.linspace(0, 1, f)
    audio[-f:] *= np.linspace(1, 0, f)
    return audio.astype(np.float32)


def save_mp3(audio, output_path):
    pcm = (np.clip(audio, -1, 1) * 32767).astype(np.int16)
    fd, tmp = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    try:
        wavfile.write(tmp, SR, pcm)
        r = subprocess.run(
            ["ffmpeg", "-y", "-i", tmp, "-c:a", "libmp3lame", "-b:a", "192k",
             "-af", "loudnorm=I=-18:TP=-1.5:LRA=9", output_path],
            capture_output=True, text=True,
        )
        if r.returncode != 0:
            raise RuntimeError(f"ffmpeg 导出 mp3 失败:\n{r.stderr[-1500:]}")
    finally:
        os.remove(tmp)


def main():
    p = argparse.ArgumentParser(description="生成古风意境 BGM")
    p.add_argument("--duration", type=float, required=True, help="时长（秒），建议与成片总时长一致")
    p.add_argument("--mood", default="nostalgic", choices=sorted(MOODS.keys()), help="情感基调")
    p.add_argument("--sections", type=int, default=4, help="主体段落数，建议等于诗句数")
    p.add_argument("--seed", type=int, default=20240301, help="随机种子，同种子结果可复现")
    p.add_argument("--output", required=True, help="输出 mp3 路径")
    args = p.parse_args()

    os.makedirs(os.path.dirname(os.path.abspath(args.output)) or ".", exist_ok=True)
    audio = generate(args.duration, args.mood, args.sections, args.seed)
    save_mp3(audio, args.output)
    print(json.dumps({
        "file": os.path.abspath(args.output),
        "duration": args.duration,
        "mood": args.mood,
        "sections": args.sections,
        "seed": args.seed,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
