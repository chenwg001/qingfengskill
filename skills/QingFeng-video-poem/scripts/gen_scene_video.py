#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
分镜视频生成（ffmpeg 兜底方案）

本技能的主路径是用 WorkBuddy 的 VideoGen 工具做首尾帧插值（真正的 AI 动态视频）。
当 VideoGen 不可用、或只想快速预览时，可用本脚本用 ffmpeg 生成「准动态」分镜：

  - 同时提供首帧(first)与尾帧(last)：两帧各自轻微推拉后用 xfade 交叉淡入，画面有连续运动感
  - 只提供首帧：做 Ken Burns 缓推/缓移，避免呆照

输出 scene_NN.mp4（默认 5s，720x1280，yuv420p，可被 compose_video.py 直接消费）。

用法：
    python gen_scene_video.py --first f1.png --last f2.png \
        --out scene_01.mp4 --duration 5 --size 720x1280 --zoom 1.08

说明：本脚本不调用任何外部 API，纯本地 ffmpeg，零成本，适合离线兜底与草稿预览。
"""

import argparse
import os
import subprocess
import sys

if sys.platform == "win32":
    sys.stdout = __import__("io").TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = __import__("io").TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


def run(cmd, desc=""):
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError(f"{desc or 'ffmpeg'} 失败:\n命令: {' '.join(cmd)}\n{(r.stderr or '')[-2000:]}")
    return r


def parse_args():
    p = argparse.ArgumentParser(description="分镜视频生成（ffmpeg 兜底）")
    p.add_argument("--first", required=True, help="首帧图片")
    p.add_argument("--last", default=None, help="尾帧图片（缺省则做 Ken Burns）")
    p.add_argument("--out", required=True, help="输出视频路径")
    p.add_argument("--duration", type=float, default=5.0, help="时长（秒）")
    p.add_argument("--size", default=None, help="输出分辨率 WxH；缺省由 --orientation 决定")
    p.add_argument("--orientation", default="portrait", choices=["portrait", "landscape"],
                   help="画面方向：portrait=9:16 竖屏（默认），landscape=16:9 横屏；仅当未显式指定 --size 时生效")
    p.add_argument("--fps", type=int, default=30)
    p.add_argument("--zoom", type=float, default=1.08, help="推拉倍率（>1 放大）")
    p.add_argument("--fade", type=float, default=1.2, help="首尾帧交叉淡入时长（秒）")
    return p.parse_args()


def main():
    a = parse_args()
    if not os.path.exists(a.first):
        sys.exit(f"首帧不存在: {a.first}")
    size = a.size or ("720x1280" if a.orientation == "portrait" else "1280x720")
    w, h = size.split("x")
    out_dir = os.path.dirname(os.path.abspath(a.out))
    os.makedirs(out_dir, exist_ok=True)
    z = max(1.01, a.zoom)
    frames = int(a.duration * a.fps)

    if a.last and os.path.exists(a.last):
        # 两帧各自缓慢推拉（贯穿整段时长），再用 xfade 交叉淡入
        fade_d = min(a.fade, a.duration / 2.0)
        zoom_expr = f"min(1.0+(on/{frames})*({z}-1.0),{z})"
        prep = (f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1,"
                f"zoompan=z='{zoom_expr}':d={frames}:s={w}x{h}:fps={a.fps},"
                f"format=yuv420p")
        vf = (f"[0:v]{prep}[f];[1:v]{prep}[l];"
              f"[f][l]xfade=transition=fade:duration={fade_d:.3f}:"
              f"offset={a.duration - fade_d:.3f},"
              f"trim=0:{a.duration:.3f},setpts=PTS-STARTPTS,format=yuv420p[v]")
        run(["ffmpeg", "-y", "-loop", "1", "-i", a.first,
             "-loop", "1", "-i", a.last,
             "-filter_complex", vf, "-map", "[v]", "-an",
             "-c:v", "libx264", "-preset", "medium", "-crf", "20",
             "-pix_fmt", "yuv420p", "-r", str(a.fps),
             "-movflags", "+faststart", a.out],
            desc="首尾帧交叉淡入")
    else:
        # 单图 Ken Burns：缓推 + 轻微横移
        drift = int(int(w) * 0.05)
        vf = (f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1,"
              f"zoompan=z='min(1.0+(on/{frames})*({z}-1.0),{z})':"
              f"x='iw/2-(iw/zoom/2)+({drift})*(on/{frames})':"
              f"y='ih/2-(ih/zoom/2)':"
              f"d={frames}:s={w}x{h}:fps={a.fps},"
              f"trim=0:{a.duration:.3f},setpts=PTS-STARTPTS,format=yuv420p")
        run(["ffmpeg", "-y", "-loop", "1", "-i", a.first,
             "-vf", vf, "-an",
             "-c:v", "libx264", "-preset", "medium", "-crf", "20",
             "-pix_fmt", "yuv420p", "-r", str(a.fps),
             "-movflags", "+faststart", a.out],
            desc="Ken Burns 缓推")

    print(f"已生成分镜: {a.out}  ({size}, {a.duration}s)")


if __name__ == "__main__":
    main()
