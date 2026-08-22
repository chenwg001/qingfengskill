#!/usr/bin/env python3
"""
本地短视频剪切工厂（确定性版）v0.2
- 按文件名前缀编号升序排程：小号素材先出（支持 001_intro.mp4 或 1.mp4 两种命名）
- 每个素材必出现 >=1 次
- 单段时长 5-10s；素材 <5s 时循环补齐到 >=5s
- 设了 target_total 且自然总时长不足时，按编号顺序复用素材补满
- 默认确定性（可加 --seed 随机）

用法：
  python video_factory.py --input "D:/趣味活动" --output "output/成片.mp4"
  python video_factory.py --input "素材文件夹" --output "out.mp4" --target-total 120
"""
import argparse
import json
import math
import os
import re
import subprocess
import tempfile

VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v", ".ts", ".flv"}
NAME_RE = re.compile(r"^(\d+)")  # 以数字开头即视为有序素材


# ---------- ffprobe 封装 ----------
def probe_duration(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", path],
        capture_output=True, text=True,
    )
    return float(out.stdout.strip())


def probe_has_audio(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a",
         "-show_entries", "stream=index", "-of", "csv=p=0", path],
        capture_output=True, text=True,
    )
    return bool(out.stdout.strip())


# ---------- 编排：生成片段计划 ----------
def build_plan(folder, clip_min, clip_max, clip_len, target_total, seed):
    files = []
    skipped = []
    for name in sorted(os.listdir(folder)):
        p = os.path.join(folder, name)
        if not os.path.isfile(p):
            continue
        if os.path.splitext(name)[1].lower() not in VIDEO_EXTS:
            continue
        m = NAME_RE.match(name)
        if not m:
            skipped.append(name)
            continue
        d = probe_duration(p)
        files.append((int(m.group(1)), name, p, d))

    if not files:
        raise SystemExit("没有可用素材（请确认文件以数字开头且为视频格式，如 001_xxx.mp4 或 1.mp4）")

    files.sort(key=lambda x: (x[0], x[1]))

    rng = None
    if seed is not None:
        import random
        rng = random.Random(seed)

    segs = []          # (src, start, length, label)
    base_total = 0.0

    def len_for(D):
        """单段目标长度，落在 [clip_min, clip_max] 内"""
        if rng:
            return round(rng.uniform(clip_min, clip_max), 3)
        return clip_len

    # 基础片段：每个素材出现 1 次
    for order, name, p, D in files:
        if D >= clip_min:
            L = min(len_for(D), D)
            L = max(clip_min, min(L, clip_max, D))
            start = round(max(0.0, (D - L) / 2.0), 3)  # 居中截取（确定性）
            segs.append((p, start, L, f"{name}[0]"))
            base_total += L
        else:
            # 短素材：循环补齐到 >=clip_min（尽量 <=clip_max）
            loops = max(1, math.ceil(clip_min / D))
            L = loops * D
            while L > clip_max and loops > 1:
                loops -= 1
                L = loops * D
            segs.append((p, 0.0, round(L, 3), f"{name}[loop x{loops}]"))
            base_total += L

    # 补时长：按编号顺序复用素材
    if target_total and base_total < target_total:
        idx = 0
        rounds = 0
        max_rounds = 100
        while base_total < target_total and rounds < max_rounds:
            order, name, p, D = files[idx % len(files)]
            if idx > 0 and idx % len(files) == 0:
                rounds += 1
            idx += 1
            if D >= clip_min:
                L = min(len_for(D), D)
                L = max(clip_min, min(L, clip_max, D))
                # 复用取不同起点（确定性偏移，确保与首段不重合）
                start = round(min(max(0.0, (D - L) / 2.0) + (rounds + 1) * 1.0,
                                  max(0.0, D - L)), 3)
                segs.append((p, start, L, f"{name}[reuse{rounds}]"))
                base_total += L
            else:
                loops = max(1, math.ceil(clip_min / D))
                L = loops * D
                while L > clip_max and loops > 1:
                    loops -= 1
                    L = loops * D
                segs.append((p, 0.0, round(L, 3), f"{name}[loopreuse x{loops}]"))
                base_total += L

    return files, segs, base_total, skipped


# ---------- 渲染单个片段（统一规格，便于 concat） ----------
def render_segment(seg, out_path, W, H, fps):
    src, start, length, label = seg
    D = probe_duration(src)
    loops = math.ceil(length / D) if length > D else 1
    has_audio = probe_has_audio(src)

    vf = (f"scale={W}:{H}:force_original_aspect_ratio=decrease,"
          f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps},format=yuv420p")

    if has_audio:
        cmd = ["ffmpeg", "-y"]
        if loops > 1:
            cmd += ["-stream_loop", str(loops - 1)]
        cmd += ["-ss", f"{start:.3f}", "-i", src,
                "-t", f"{length:.3f}", "-vf", vf,
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                "-c:a", "aac", "-ar", "44100", "-ac", "2",
                "-map", "0:v", "-map", "0:a", out_path]
    else:
        cmd = ["ffmpeg", "-y"]
        if loops > 1:
            cmd += ["-stream_loop", str(loops - 1)]
        cmd += ["-ss", f"{start:.3f}", "-i", src,
                "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
                "-t", f"{length:.3f}", "-vf", vf,
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                "-c:a", "aac", "-map", "0:v", "-map", "1:a", out_path]

    subprocess.run(cmd, check=True, capture_output=True)
    return out_path


def main():
    ap = argparse.ArgumentParser(description="确定性本地短视频剪切工厂")
    ap.add_argument("--input", required=True, help="素材文件夹（非递归，取直接子文件）")
    ap.add_argument("--output", required=True, help="输出 mp4 路径")
    ap.add_argument("--clip-min", type=float, default=5)
    ap.add_argument("--clip-max", type=float, default=10)
    ap.add_argument("--clip-len", type=float, default=8,
                    help="单段默认长度（落在 5-10 内）；--random 时忽略")
    ap.add_argument("--target-total", type=float, default=None,
                    help="目标成片总时长（秒）；不填则用自然总时长")
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=720)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--random", action="store_true", help="单段长度在 5-10 间随机")
    ap.add_argument("--seed", type=int, default=None)
    args = ap.parse_args()

    assert args.clip_min >= 1, "clip-min 应 >=1"
    assert args.clip_max <= 60, "clip-max 过大"
    if not args.random:
        args.clip_len = max(args.clip_min, min(args.clip_len, args.clip_max))

    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)

    files, segs, base_total, skipped = build_plan(
        args.input, args.clip_min, args.clip_max, args.clip_len,
        args.target_total, args.seed if args.random else None,
    )

    print(f"[素材] 共 {len(files)} 个有序素材：")
    for order, name, p, d in files:
        print(f"   {order:>3}  {name}  ({d:.1f}s)")
    if skipped:
        print(f"[跳过] 无编号前缀的视频：{skipped}")

    print(f"[计划] 片段数={len(segs)}  计划总时长={base_total:.1f}s"
          + (f"  目标={args.target_total}s" if args.target_total else ""))

    tmp = tempfile.mkdtemp(prefix="vf_")
    seg_paths = []
    for i, seg in enumerate(segs):
        out = os.path.join(tmp, f"seg_{i:03d}.mp4")
        render_segment(seg, out, args.width, args.height, args.fps)
        seg_paths.append(out)
        print(f"   -> {seg[3]:<28} {seg[1]:.1f}~{seg[1]+seg[2]:.1f}s")

    # concat
    list_txt = os.path.join(tmp, "list.txt")
    with open(list_txt, "w", encoding="utf-8") as f:
        for sp in seg_paths:
            f.write(f"file '{os.path.abspath(sp)}'\n")

    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_txt,
         "-c", "copy", args.output],
        check=True, capture_output=True,
    )

    dur = probe_duration(args.output)
    print(f"[完成] 输出：{args.output}  时长={dur:.1f}s  片段={len(segs)}")

    # 可溯源的片段映射表
    plan_json = os.path.splitext(args.output)[0] + "_plan.json"
    with open(plan_json, "w", encoding="utf-8") as f:
        json.dump([
            {"file": os.path.basename(s[0]), "start": s[1],
             "length": s[2], "label": s[3]} for s in segs
        ], f, ensure_ascii=False, indent=2)
    print(f"[溯源] 片段映射表：{plan_json}")


if __name__ == "__main__":
    main()
