#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
古诗成片合成器：把分镜视频 + 朗诵时间轴 + BGM 合成为最终成片。

核心是「以朗诵时间轴为主时钟」，而不是给每个镜头拍脑袋定固定秒数：
  1. 从 timeline.json 读出每句朗诵的精确起止，推导每个镜头应占的时长
  2. 把 AI 生成的定长片段（通常 5s）变速/定格适配到该时长
  3. 预留 xfade 交叠量，保证转场后总时长仍与音频严格对齐
  4. 字幕按绝对时间轴换算为片段内相对时间烧录，不会跑偏

用法：
    python compose_video.py --workdir D:/work/jingyesi \
        --timeline timeline.json --bgm bgm.mp3 \
        --title-text "静夜思 · 唐 · 李白" --output final.mp4

镜头文件默认按 <workdir>/scene_01.mp4, scene_02.mp4 ... 顺序扫描，
也可用 --scenes 显式指定。
"""

import argparse
import glob
import io
import json
import os
import shutil
import subprocess
import sys

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Windows 常见中文字体，优先楷体（古诗气质最搭）
FONT_CANDIDATES = [
    r"C:\Windows\Fonts\simkai.ttf",     # 楷体
    r"C:\Windows\Fonts\STKAITI.TTF",    # 华文楷体
    r"C:\Windows\Fonts\STXIHEI.TTF",    # 华文细黑
    r"C:\Windows\Fonts\msyh.ttc",       # 微软雅黑
    r"C:\Windows\Fonts\simhei.ttf",     # 黑体
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
]

MAX_SLOWDOWN = 1.8   # 变速上限，超出部分用尾帧定格补足
MIN_SPEEDUP = 0.55   # 加速下限


def parse_args():
    p = argparse.ArgumentParser(description="合成古诗意境成片")
    p.add_argument("--workdir", required=True, help="工作目录")
    p.add_argument("--scenes", nargs="*", default=None,
                   help="镜头视频文件（相对 workdir 或绝对路径）；缺省自动扫描 scene_*.mp4")
    p.add_argument("--timeline", default="timeline.json", help="朗诵时间轴 JSON")
    p.add_argument("--voice", default="voice_full.mp3", help="整段朗诵音频")
    p.add_argument("--no-voice", action="store_true", help="不混入朗诵")
    p.add_argument("--bgm", default=None, help="背景音乐 mp3")
    p.add_argument("--bgm-volume", type=float, default=0.30, help="BGM 音量，默认 0.30")
    p.add_argument("--voice-volume", type=float, default=1.35, help="朗诵音量，默认 1.35")
    p.add_argument("--transition", type=float, default=0.7, help="镜头间转场时长（秒）")
    p.add_argument("--size", default=None, help="输出分辨率，如 720x1280 / 1280x720 / 1080x1920；缺省由 --orientation 决定")
    p.add_argument("--orientation", default="portrait", choices=["portrait", "landscape"],
                   help="画面方向：portrait=9:16 竖屏（默认），landscape=16:9 横屏；仅当未显式指定 --size 时生效")
    p.add_argument("--fps", type=int, default=30)
    p.add_argument("--font", default=None, help="字幕字体路径")
    p.add_argument("--font-size", type=int, default=0, help="字幕字号，0=按分辨率自动")
    p.add_argument("--title-text", default=None, help="片头标题文字，如「静夜思 · 唐 · 李白」")
    p.add_argument("--no-subtitle", action="store_true", help="不烧录诗句字幕")
    p.add_argument("--output", default="final.mp4", help="输出文件名（相对 workdir）")
    p.add_argument("--clean", action="store_true",
                   help="合成后删除本脚本产生的中间文件（_clip_*.mp4 等），默认保留")
    return p.parse_args()


def run(cmd, cwd=None, desc=""):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError(f"{desc or 'ffmpeg'} 失败:\n命令: {' '.join(cmd)}\n{(r.stderr or '')[-2500:]}")
    return r


def probe_duration(path: str) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", path],
        capture_output=True, text=True)
    if r.returncode != 0 or not r.stdout.strip():
        raise RuntimeError(f"无法读取时长: {path}")
    return float(r.stdout.strip())


def pick_font(user_font):
    if user_font and os.path.exists(user_font):
        return user_font
    for c in FONT_CANDIDATES:
        if os.path.exists(c):
            return c
    raise RuntimeError("未找到可用中文字体，请用 --font 指定 .ttf/.ttc 路径")


# 折行后需要回退到上一行的行首孤立标点（避免「第二行只剩一个句号」）
_PULLBACK_PUNCT = set("，。！？；：、,.!?;:")


def wrap_subtitle(text, font_size, width, max_ratio=0.86):
    """
    按视频宽度对字幕做「按字符实际宽度」折行，避免 drawtext 不自动换行导致溢出画面。
    中文/全角字符按 1.0*font_size 计宽，半角字符按 0.5*font_size 计宽。
    返回含 \\n 的多行文本（drawtext 的 textfile 支持渲染换行为多行）。
    后处理会把行首的连续孤立标点回退到上一行，避免出现「第二行只剩一个句号」的丑陋折行。
    """
    if not text:
        return text
    max_w = width * max_ratio
    lines, cur, cur_w = [], "", 0.0
    for ch in text:
        if ch == "\n":
            lines.append(cur)
            cur, cur_w = "", 0.0
            continue
        ch_w = font_size * (0.5 if ord(ch) < 128 else 1.0)
        if cur and cur_w + ch_w > max_w:
            lines.append(cur)
            cur, cur_w = ch, ch_w
        else:
            cur += ch
            cur_w += ch_w
    if cur:
        lines.append(cur)
    # 后处理：把落在行首的连续标点回退到上一行，避免第二行只剩一个标点
    merged = []
    for line in lines:
        if merged and line and line[0] in _PULLBACK_PUNCT:
            i = 0
            while i < len(line) and line[i] in _PULLBACK_PUNCT:
                i += 1
            merged[-1] += line[:i]
            rest = line[i:]
            if rest:
                merged.append(rest)
        else:
            merged.append(line)
    return "\n".join(merged)


def wrap_title(text, base_font, width, max_lines=2, max_ratio=0.9):
    """
    标题折行：复用 wrap_subtitle 的按字符宽度折行，但允许更宽（max_ratio=0.9）
    且自动缩字号以保证不超过 max_lines 行，避免标题溢出画面或叠行。
    返回 (折行后文本, 选用字号)。
    """
    if not text:
        return text, base_font
    font = base_font
    while font >= 34:
        wrapped = wrap_subtitle(text, font, width, max_ratio=max_ratio)
        if wrapped.count("\n") + 1 <= max_lines:
            return wrapped, font
        font = int(font * 0.9)
    return wrap_subtitle(text, font, width, max_ratio=max_ratio), font


def plan_segments(tl: dict, n_scenes: int):
    """
    依据朗诵时间轴推导每个镜头覆盖的绝对时间区间。

    两种镜头编排：
      A. 镜头数 == 诗句数      —— 首镜顺带承载前奏与题目播报
      B. 镜头数 == 诗句数 + 1  —— 首镜为独立封面镜（推荐，画面不会被拉伸定格）
    每句镜头覆盖「上一句结束 + 半个气口」到「本句结束 + 半个气口」，末镜延伸到音频结束。
    """
    lines = [x for x in tl["lines"] if x.get("role", "line") == "line"]
    if not lines:
        raise RuntimeError("timeline.json 中没有诗句条目")

    n_lines = len(lines)
    if n_scenes == n_lines:
        cover = False
    elif n_scenes == n_lines + 1:
        cover = True
    else:
        raise RuntimeError(
            f"镜头数({n_scenes})应等于诗句数({n_lines})或诗句数+1（含封面镜），请检查素材")

    gap = float(tl.get("gap", 0.8))
    total = float(tl["total_duration"])

    # 每句的结束边界
    bounds = []
    for i, ln in enumerate(lines):
        bounds.append(total if i == n_lines - 1 else round(ln["end"] + gap / 2.0, 3))

    segs = []
    if cover:
        cover_end = round(max(1.5, lines[0]["start"] - gap / 2.0), 3)
        title_items = [x for x in tl["lines"] if x.get("role") == "title"]
        cover_text = title_items[0]["text"] if title_items else ""
        segs.append({
            "index": 0, "text": "", "role": "cover",
            "abs_start": 0.0, "abs_end": cover_end, "target": cover_end,
            "sub_start": 0.0, "sub_end": 0.0, "cover_text": cover_text,
        })
        prev = cover_end
    else:
        prev = 0.0

    for i, ln in enumerate(lines):
        segs.append({
            "index": i + 1, "text": ln["text"], "role": "line",
            "abs_start": prev, "abs_end": bounds[i],
            "target": round(bounds[i] - prev, 3),
            "sub_start": ln["start"],
            "sub_end": min(ln["end"] + 0.45, bounds[i]),
        })
        prev = bounds[i]
    return segs


def build_clip(src, dst, seg, clip_dur, size, fps, font_rel, sub_file_rel,
               font_size, workdir, title_cfg=None, lead=0.0):
    """
    把一个 AI 片段适配到指定时长，并按需烧字幕/标题。
    lead: 该片段前置的转场交叠量（秒）。片段内相对时间 t 对应绝对时间 abs_start - lead + t。
    """
    w, h = size.split("x")
    src_dur = probe_duration(src)
    ratio = clip_dur / src_dur                      # >1 慢放，<1 加速
    ratio = max(MIN_SPEEDUP, min(MAX_SLOWDOWN, ratio))
    after = src_dur * ratio
    pad_need = max(0.0, clip_dur - after)

    vf = [
        f"scale={w}:{h}:force_original_aspect_ratio=increase",
        f"crop={w}:{h}",
        f"setsar=1",
        f"setpts=PTS*{ratio:.6f}",
        f"fps={fps}",
    ]
    if pad_need > 0.02:
        vf.append(f"tpad=stop_mode=clone:stop_duration={pad_need:.3f}")
    vf.append(f"trim=0:{clip_dur:.3f}")
    vf.append("setpts=PTS-STARTPTS")

    origin = seg["abs_start"] - lead      # 片段第 0 秒对应的绝对时间
    if sub_file_rel:
        rs = max(0.0, seg["sub_start"] - origin)
        re = max(rs + 0.4, seg["sub_end"] - origin)
        vf.append(
            f"drawtext=fontfile={font_rel}:textfile={sub_file_rel}:"
            f"fontcolor=white:fontsize={font_size}:line_spacing=8:"
            f"borderw=2:bordercolor=black@0.55:"
            f"shadowcolor=black@0.6:shadowx=2:shadowy=2:"
            f"x=(w-text_w)/2:y=h-text_h-{int(int(h) * 0.11)}:"
            f"enable='between(t,{rs:.3f},{re:.3f})'"
        )

    if title_cfg:
        t0 = max(0.0, title_cfg["start"] - origin)
        t1 = min(clip_dur, title_cfg["end"] - origin)
        fade = min(0.7, max(0.2, (t1 - t0) / 4.0))
        alpha = (f"if(lt(t,{t0:.2f}),0,"
                 f"if(lt(t,{t0 + fade:.2f}),(t-{t0:.2f})/{fade},"
                 f"if(lt(t,{t1 - fade:.2f}),1,"
                 f"if(lt(t,{t1:.2f}),({t1:.2f}-t)/{fade},0))))")
        vf.append(
            f"drawtext=fontfile={font_rel}:textfile={title_cfg['file']}:"
            f"fontcolor=white:fontsize={title_cfg['font']}:"
            f"borderw=2:bordercolor=black@0.5:"
            f"shadowcolor=black@0.55:shadowx=3:shadowy=3:"
            f"line_spacing=8:"
            f"x=(w-text_w)/2:y=(h-text_h)/2-{int(int(h) * 0.06)}:"
            f"alpha='{alpha}'"
        )

    run(["ffmpeg", "-y", "-i", src, "-an",
         "-vf", ",".join(vf),
         "-c:v", "libx264", "-preset", "medium", "-crf", "20",
         "-pix_fmt", "yuv420p", "-r", str(fps),
         "-movflags", "+faststart", dst],
        cwd=workdir, desc=f"镜头{seg['index']}适配")


def concat_clips(clips, out, targets, transition, size, fps, workdir):
    """
    xfade 串接。xfade 输出时长 = offset + 第二输入时长，因此除首片段外，
    每个片段都要多留 transition 秒作为「被交叠掉」的引入部分，
    拼接后总时长才恰好等于 Σtargets（与朗诵时间轴对齐）。
    """
    n = len(clips)
    if n == 1:
        shutil.copy(os.path.join(workdir, clips[0]), os.path.join(workdir, out))
        return
    if transition <= 0:
        lst = os.path.join(workdir, "_concat.txt")
        with open(lst, "w", encoding="utf-8") as f:
            for c in clips:
                f.write(f"file '{c}'\n")
        run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "_concat.txt",
             "-c", "copy", out], cwd=workdir, desc="拼接")
        return

    inputs = []
    for c in clips:
        inputs += ["-i", c]
    filters = []
    prev = "[0:v]"
    acc = 0.0
    for i in range(n - 1):
        acc += targets[i]
        offset = acc - transition
        label = f"[x{i}]"
        filters.append(
            f"{prev}[{i + 1}:v]xfade=transition=fade:duration={transition:.3f}:"
            f"offset={offset:.3f}{label}")
        prev = label
    filters.append(f"{prev}format=yuv420p[v]")
    run(["ffmpeg", "-y"] + inputs + [
        "-filter_complex", ";".join(filters),
        "-map", "[v]", "-an",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-r", str(fps), "-movflags", "+faststart", out],
        cwd=workdir, desc="转场拼接")


def mix_audio(video, out, voice, bgm, voice_vol, bgm_vol, workdir):
    vdur = probe_duration(os.path.join(workdir, video))
    inputs = ["-i", video]
    filters, mix_labels = [], []
    idx = 1
    if voice:
        inputs += ["-i", voice]
        filters.append(f"[{idx}:a]volume={voice_vol},apad,atrim=0:{vdur:.3f},"
                       f"asetpts=PTS-STARTPTS[voc]")
        mix_labels.append("[voc]")
        idx += 1
    if bgm:
        inputs += ["-i", bgm]
        filters.append(f"[{idx}:a]aloop=loop=-1:size=2E+09,volume={bgm_vol},"
                       f"atrim=0:{vdur:.3f},asetpts=PTS-STARTPTS,"
                       f"afade=t=out:st={max(0.0, vdur - 2.0):.3f}:d=2[bg]")
        mix_labels.append("[bg]")
        idx += 1

    if not mix_labels:
        shutil.copy(os.path.join(workdir, video), os.path.join(workdir, out))
        return
    if len(mix_labels) == 1:
        filters.append(f"{mix_labels[0]}acopy[aout]")
    else:
        weights = " ".join(["1"] * len(mix_labels))
        filters.append(f"{''.join(mix_labels)}amix=inputs={len(mix_labels)}:"
                       f"duration=first:weights='{weights}':normalize=0[aout]")

    run(["ffmpeg", "-y"] + inputs + [
        "-filter_complex", ";".join(filters),
        "-map", "0:v", "-map", "[aout]",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        "-t", f"{vdur:.3f}", "-movflags", "+faststart", out],
        cwd=workdir, desc="混音")


def main():
    args = parse_args()
    workdir = os.path.abspath(args.workdir)
    if not os.path.isdir(workdir):
        sys.exit(f"工作目录不存在: {workdir}")

    tl_path = args.timeline if os.path.isabs(args.timeline) else os.path.join(workdir, args.timeline)
    with open(tl_path, encoding="utf-8") as f:
        tl = json.load(f)

    if args.scenes:
        scenes = [s if os.path.isabs(s) else os.path.join(workdir, s) for s in args.scenes]
    else:
        scenes = sorted(glob.glob(os.path.join(workdir, "scene_*.mp4")))
        scenes = [s for s in scenes if "_clip" not in os.path.basename(s)]
    if not scenes:
        sys.exit("未找到镜头视频（scene_*.mp4）")
    for s in scenes:
        if not os.path.exists(s):
            sys.exit(f"镜头文件不存在: {s}")

    segs = plan_segments(tl, len(scenes))
    size = args.size or ("720x1280" if args.orientation == "portrait" else "1280x720")
    w, h = size.split("x")
    font_size = args.font_size or max(34, int(min(int(w), int(h)) * 0.075))
    transition = max(0.0, args.transition)

    # 字体复制到工作目录，用相对路径引用，规避 Windows 盘符冒号在 filter 中的转义问题
    font_src = pick_font(args.font)
    font_rel = "_subfont" + os.path.splitext(font_src)[1].lower()
    shutil.copy(font_src, os.path.join(workdir, font_rel))

    title_cfg = None
    if args.title_text:
        title_items = [x for x in tl["lines"] if x.get("role") == "title"]
        t_start = 0.4
        t_end = (title_items[0]["end"] + 0.9) if title_items else float(tl.get("lead_in", 1.5)) + 2.4
        tfile = "_title.txt"
        title_font = int(font_size * 1.45)
        wrapped_title, title_font = wrap_title(args.title_text, title_font, int(w))
        with open(os.path.join(workdir, tfile), "w", encoding="utf-8", newline="\n") as f:
            f.write(wrapped_title)
        title_cfg = {"file": tfile, "start": t_start, "end": t_end, "font": title_font}

    print(f"镜头数: {len(scenes)}  分辨率: {size}（{args.orientation}）  字号: {font_size}  转场: {transition}s")
    print(f"字体: {font_src}")

    clips, targets = [], []
    for i, (src, seg) in enumerate(zip(scenes, segs)):
        lead = transition if i > 0 else 0.0     # 首片段无前置交叠
        clip_dur = seg["target"] + lead
        sub_rel = None
        if not args.no_subtitle and seg["text"]:
            sub_rel = f"_sub_{seg['index']:02d}.txt"
            wrapped = wrap_subtitle(seg["text"], font_size, int(w))
            with open(os.path.join(workdir, sub_rel), "w", encoding="utf-8", newline="\n") as f:
                f.write(wrapped)
        dst = f"_clip_{i:02d}.mp4"
        tcfg = title_cfg if (title_cfg and title_cfg["end"] > seg["abs_start"] - lead
                             and title_cfg["start"] < seg["abs_end"]) else None
        label = seg["text"] or "（封面镜）"
        print(f"  [{i + 1}/{len(segs)}] {label}  "
              f"目标 {seg['target']:.2f}s（素材 {clip_dur:.2f}s）")
        build_clip(src, dst, seg, clip_dur, size, args.fps,
                   font_rel, sub_rel, font_size, workdir, tcfg, lead)
        clips.append(dst)
        targets.append(seg["target"])

    print("拼接转场...")
    silent = "_silent.mp4"
    concat_clips(clips, silent, targets, transition, size, args.fps, workdir)

    voice = None
    if not args.no_voice:
        v = args.voice if os.path.isabs(args.voice) else os.path.join(workdir, args.voice)
        if os.path.exists(v):
            voice = os.path.basename(v) if os.path.dirname(v) == workdir else v
        else:
            print(f"警告: 朗诵文件不存在 {v}，输出无人声版本", file=sys.stderr)
    bgm = None
    if args.bgm:
        b = args.bgm if os.path.isabs(args.bgm) else os.path.join(workdir, args.bgm)
        if os.path.exists(b):
            bgm = os.path.basename(b) if os.path.dirname(b) == workdir else b
        else:
            print(f"警告: BGM 不存在 {b}，跳过", file=sys.stderr)

    print("混音...")
    mix_audio(silent, args.output, voice, bgm, args.voice_volume, args.bgm_volume, workdir)

    final = os.path.join(workdir, args.output)
    dur = probe_duration(final)
    audio_dur = float(tl["total_duration"])

    if args.clean:
        for pat in ["_clip_*.mp4", "_sub_*.txt", "_title.txt", "_concat.txt", "_subfont.*"]:
            for f in glob.glob(os.path.join(workdir, pat)):
                try:
                    os.remove(f)
                except OSError:
                    pass

    result = {
        "output": final,
        "duration": round(dur, 2),
        "audio_timeline_duration": round(audio_dur, 2),
        "sync_offset": round(dur - audio_dur, 2),
        "resolution": size,
        "scenes": len(scenes),
        "transition": transition,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if abs(dur - audio_dur) > 0.6:
        print(f"提示: 成片时长与朗诵时间轴相差 {dur - audio_dur:+.2f}s，"
              f"如需更严格同步可减小 --transition", file=sys.stderr)


if __name__ == "__main__":
    main()
