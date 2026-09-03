"""
gen_bgm.py - 按 script.json 情绪分段，程序化合成「完整的歌曲配乐」
（自包含：不依赖任何外部模型 / 联网，可作为技能默认 BGM 生成器，所有用户可用）

用法:
  python gen_bgm.py --json <script.json> --out <bgm.wav> --duration <秒> [--gain 0.5]

相对「简单节奏（和弦垫+琶音）」的升级：
  - 有旋律：根据文本情绪与句子结构生成一条主旋律线（非仅和弦/琶音）。
  - 有结构：按情绪能量把文本分成 intro/verse/chorus/bridge/outro 段落，
            各段配不同速度、配器密度、主旋律音区。
  - 有编曲：主旋律 + 和声垫 + 贝斯 + 轻打击乐（底鼓/军鼓/踩镲），密度随段落能量变化。
  - 文本驱动：mood 情绪标签影响调式（大调/小调）、速度、主旋律走向。
"""
import argparse
import json
import math
import re
import wave
import numpy as np

SR = 24000

# ---------- 音高工具 ----------
def midi_of_name(name):
    m = re.match(r"([A-G]#?)(-?\d+)", name)
    letter, octv = m.group(1), int(m.group(2))
    base = {'C': 0, 'C#': 1, 'D': 2, 'D#': 3, 'E': 4, 'F': 5,
            'F#': 6, 'G': 7, 'G#': 8, 'A': 9, 'A#': 10, 'B': 11}
    return base[letter] + (octv + 1) * 12

def midi_to_freq(m):
    return 440.0 * (2.0 ** ((m - 69) / 12.0))

MAJOR = [0, 2, 4, 5, 7, 9, 11]
MINOR = [0, 2, 3, 5, 7, 8, 10]
TRIAD = {'maj': [0, 4, 7], 'min': [0, 3, 7]}

# 情绪 -> 能量(0..1)
MOOD_ENERGY = {
    '轻柔': 0.30, '舒缓': 0.32, '温暖': 0.42, '温情': 0.48, '慈爱': 0.50,
    '感慨': 0.40, '轻快': 0.70, '欢喜': 0.85, '热闹': 0.92, '昂扬': 0.80,
    '留白': 0.30,
}
# 段落配器方案（优化：verse/chorus 更丰富）
SECTION_PLAN = {
    'intro':  {'drums': False, 'bass': True,  'pad': True, 'density': 0.8, 'lift': -3},
    'verse':  {'drums': True,  'bass': True,  'pad': True, 'density': 1.8, 'lift': 0},
    'chorus': {'drums': True,  'bass': True,  'pad': True, 'density': 2.6, 'lift': 6},
    'bridge': {'drums': False, 'bass': True,  'pad': True, 'density': 1.2, 'lift': -5},
    'outro':  {'drums': False, 'bass': True,  'pad': True, 'density': 0.6, 'lift': -3},
}
# 各段和弦进行（调式内级数 + 三和弦性质）
PROG = {
    'MAJOR': {
        'intro':  [(0, 'maj')],
        'verse':  [(0, 'maj'), (5, 'maj'), (3, 'min'), (4, 'maj')],
        'chorus': [(0, 'maj'), (4, 'maj'), (5, 'maj'), (3, 'min')],
        'bridge': [(5, 'min'), (3, 'min'), (4, 'maj'), (0, 'maj')],
        'outro':  [(0, 'maj'), (5, 'maj')],
    },
    'MINOR': {
        'intro':  [(0, 'min')],
        'verse':  [(0, 'min'), (5, 'min'), (3, 'maj'), (4, 'min')],
        'chorus': [(0, 'min'), (4, 'min'), (5, 'maj'), (3, 'maj')],
        'bridge': [(5, 'min'), (3, 'maj'), (4, 'min'), (0, 'min')],
        'outro':  [(0, 'min'), (5, 'min')],
    },
}

# ---------- 合成基元 ----------
def env_adsr(n, sr, a=0.01, d=0.05, s=0.7, r=0.15):
    if n <= 1:
        return np.zeros(max(n, 0))
    out = np.zeros(n)
    a_n = min(int(a * sr), n - 1)
    d_n = min(int(d * sr), max(0, n - a_n - 1))
    r_n = min(int(r * sr), max(0, n - a_n - d_n - 1))
    sus_n = max(0, n - a_n - d_n - r_n)
    if a_n:   out[:a_n] = np.linspace(0, 1, a_n)
    if d_n:   out[a_n:a_n + d_n] = np.linspace(1, s, d_n)
    out[a_n + d_n:a_n + d_n + sus_n] = s
    if r_n:   out[a_n + d_n + sus_n:] = np.linspace(s, 0, r_n)
    return out

def tone(freq, dur, sr, kind='melody', vel=1.0):
    n = max(1, int(dur * sr))
    if n <= 0:
        return np.zeros(0)
    t = np.arange(n) / sr
    if kind == 'melody':
        vib = 1 + 0.005 * np.sin(2 * np.pi * 5 * t)
        sig = (np.sin(2 * np.pi * freq * vib * t)
               + 0.35 * np.sin(2 * np.pi * 2 * freq * t)
               + 0.12 * np.sin(2 * np.pi * 3 * freq * t)) / 1.47
        env = env_adsr(n, sr, a=0.02, d=0.06, s=0.8, r=0.18)
    elif kind == 'pad':
        sig = (np.sin(2 * np.pi * freq * t) + 0.3 * np.sin(2 * np.pi * 2 * freq * t)) / 1.3
        env = env_adsr(n, sr, a=0.25, d=0.2, s=0.85, r=0.4)
    elif kind == 'bass':
        sig = (np.sin(2 * np.pi * freq * t) + 0.2 * np.sin(2 * np.pi * 2 * freq * t)) / 1.2
        env = env_adsr(n, sr, a=0.01, d=0.05, s=0.9, r=0.1)
    else:
        sig = np.sin(2 * np.pi * freq * t)
        env = np.ones(n)
    return sig * env * vel

def kick(sr, dur=0.25):
    n = int(dur * sr); t = np.arange(n) / sr
    f = 120 * np.exp(-t * 30) + 45
    return np.sin(2 * np.pi * f * t) * np.exp(-t * 12)

def snare(sr, dur=0.18):
    n = int(dur * sr); t = np.arange(n) / sr
    noise = np.random.randn(n)
    body = np.sin(2 * np.pi * 180 * t) * np.exp(-t * 20)
    return (noise * 0.6 + body * 0.6) * np.exp(-t * 18)

def hat(sr, dur=0.05):
    n = int(dur * sr); t = np.arange(n) / sr
    return np.random.randn(n) * np.exp(-t * 60) * 0.5

def addto(arr, st, seg):
    if st >= len(arr) or len(seg) == 0:
        return
    en = min(st + len(seg), len(arr))
    arr[st:en] += seg[:en - st]

def add_reverb(sig, sr, amount=0.2):
    taps = [(0.04, 0.5), (0.08, 0.32), (0.13, 0.2), (0.19, 0.12)]
    L = int(taps[-1][0] * sr) + 1
    imp = np.zeros(L)
    for dt, a in taps:
        imp[int(dt * sr)] = a
    wet = np.convolve(sig, imp, mode='full')[:len(sig)]
    return sig + amount * wet

# ---------- 段落划分（强制标准歌曲结构）----------
def build_sections(sentences):
    """强制按标准歌曲结构划分段落，确保有旋律变化"""
    n = len(sentences)
    if n < 4:
        # 句子太少，只分 intro + outro
        return [('intro', list(range(0, n // 2))), ('outro', list(range(n // 2, n)))]

    # 标准结构：intro(10%) / verse(25%) / chorus(25%) / bridge(15%) / outro(25%)
    # 按句子数量分配
    target_ratios = {
        'intro': 0.10,
        'verse': 0.25,
        'chorus': 0.25,
        'bridge': 0.15,
        'outro': 0.25,
    }

    sections = []
    pos = 0
    for stype, ratio in target_ratios.items():
        count = max(1, int(n * ratio))
        if stype in ('intro', 'outro') and pos >= n:
            continue
        if stype == 'outro' and pos < n:
            # outro 包含剩余所有句子
            sections.append((stype, list(range(pos, n))))
            pos = n
        else:
            sections.append((stype, list(range(pos, min(pos + count, n)))))
            pos += count

    return sections

# ---------- 主合成 ----------
def compose(json_path, out_path, duration, gain=0.5, seed=20260818):
    rng = np.random.default_rng(seed)
    data = json.load(open(json_path, encoding='utf-8'))
    sents = data['sentences']
    total_est = sum(s['duration_est'] for s in sents) or 1.0
    N = int(duration * SR)
    melody = np.zeros(N); pad = np.zeros(N); bass = np.zeros(N); drums = np.zeros(N)

    # 全局调式/根音/BPM：含感慨/慈爱且整体偏静 -> 小调；否则大调
    avg_e = sum(MOOD_ENERGY.get(s.get('mood', '温情'), 0.45) for s in sents) / len(sents)
    has_minor = any(s.get('mood') in ('感慨', '慈爱') for s in sents)
    if has_minor and avg_e < 0.55:
        mode, root, base_bpm = 'MINOR', 'A2', 72
    else:
        mode, root, base_bpm = 'MAJOR', 'C3', 78
    scale = MAJOR if mode == 'MAJOR' else MINOR
    root_midi = midi_of_name(root)

    sections = build_sections(sents)
    cum = 0.0
    for stype, idxs in sections:
        if not idxs:
            continue
        frac = sum(sents[i]['duration_est'] for i in idxs) / total_est
        t0 = int(cum * N); t1 = int((cum + frac) * N); cum += frac
        if t1 <= t0:
            continue
        plan = SECTION_PLAN[stype]
        bpm = max(60, min(120, base_bpm + plan['lift'] + int(round((avg_e - 0.5) * 8))))
        spb = 60.0 / bpm
        prog = PROG[mode][stype]
        seg_n = t1 - t0
        beats_in_seg = seg_n / spb

        # 和声垫 + 贝斯 + 鼓：按小节(4拍)推进和弦
        pos = 0; ci = 0
        while pos < seg_n:
            d, q = prog[ci % len(prog)]; ci += 1
            chord_n = min(int(4 * spb * SR), seg_n - pos)
            if chord_n <= 0:
                break
            chord_root = root_midi + scale[d % len(scale)] + 12 * (d // len(scale))
            chord_midis = [chord_root + off for off in TRIAD[q]]
            if plan['pad']:
                for cm in chord_midis:
                    addto(pad, t0 + pos, tone(midi_to_freq(cm), chord_n / SR, SR, kind='pad', vel=0.5))
            if plan['bass']:
                bass_midi = max(28, chord_root - 12)
                beat_n = int(spb * SR)
                k = 0
                while k * beat_n < chord_n:
                    st = t0 + pos + k * beat_n
                    en = min(st + beat_n, t0 + pos + chord_n)
                    if st < N and en - st >= int(0.02 * SR):
                        addto(bass, st, tone(midi_to_freq(bass_midi), (en - st) / SR, SR, kind='bass', vel=0.8))
                    k += 1
            if plan['drums']:
                beat_n = int(spb * SR)
                k = 0
                while k * beat_n < chord_n:
                    st = t0 + pos + k * beat_n
                    if st < N:
                        if k % 2 == 0:
                            addto(drums, st, kick(SR) * 0.9)
                        else:
                            addto(drums, st, snare(SR) * 0.7)
                        hn = beat_n // 2
                        if st + hn < N:
                            addto(drums, st + hn, hat(SR) * 0.4)
                    k += 1
            pos += chord_n

        # 主旋律：按句子生成（增强版）
        lift_deg = {'intro': 0, 'verse': 0, 'chorus': 2, 'bridge': -2, 'outro': -1}[stype]
        density = plan['density']
        # 每段用不同的主题动机，增加记忆点
        motif_offset = {'intro': 0, 'verse': 2, 'chorus': 4, 'bridge': 1, 'outro': -1}[stype]
        deg = 2 + motif_offset  # 起始音高随段落变化
        for i in idxs:
            s = sents[i]
            text = s['text']
            chars = len(re.sub(r'[^\u4e00-\u9fff]', '', text)) or 4
            span = max(int((s['duration_est'] / total_est) * N), int(0.4 * SR))
            nn = max(3, int(round(span / SR * density)))  # 至少3个音符
            mood = s.get('mood', '温情')
            # 根据情绪决定旋律走向
            mood_step = {
                '欢喜': 1, '热闹': 1, '轻快': 1, '昂扬': 1,
                '感慨': -1, '慈爱': -1,
                '留白': 0, '温情': 0, '温柔': 0, '舒缓': 0
            }.get(mood, 0)
            for kk in range(nn):
                if kk > 0:
                    # 旋律进行：避免大跳，小步走
                    delta = rng.choice([-2, -1, 0, 1, 2], p=[0.10, 0.30, 0.20, 0.30, 0.10])
                    deg = max(0, min(len(scale) * 2, deg + delta))
                if kk == nn - 1:
                    # 落回根级，收束
                    deg = (deg // len(scale)) * len(scale)
                midi = root_midi + scale[deg % len(scale)] + 12 * (deg // len(scale)) + 12 * lift_deg
                midi = max(36, min(84, midi))
                st = t0 + int(kk * span / nn)
                en = min(t0 + int((kk + 1) * span / nn), N)
                if st < en:
                    addto(melody, st, tone(midi_to_freq(midi), (en - st) / SR, SR, kind='melody', vel=0.9))

    sig = melody * 0.9 + pad * 0.35 + bass * 0.8 + drums * 0.6
    sig = add_reverb(sig, SR, amount=0.18)
    peak = np.max(np.abs(sig)) or 1.0
    sig = sig / peak * gain
    sig = np.tanh(sig * 1.05)
    # 立体声微宽度（Haas）
    R = np.zeros_like(sig); d = int(0.012 * SR)
    R[d:] = sig[:-d] * 0.6
    stereo = np.stack([sig, R], axis=1)

    w = wave.open(out_path, 'w')
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes((stereo * 32767).clip(-32768, 32767).astype('<i2').tobytes())
    w.close()
    print(f"[BGM] 生成 {out_path}  时长={duration:.2f}s  调式={mode} 根音={root} "
          f"段落={[s[0] for s in sections]}")

if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--json', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--duration', type=float, required=True)
    ap.add_argument('--gain', type=float, default=0.5)
    ap.add_argument('--seed', type=int, default=20260818)
    args = ap.parse_args()
    compose(args.json, args.out, args.duration, args.gain, args.seed)
