#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
视频发布自动路由（横屏→B站 / 竖屏→小红书）

根据视频分辨率自动选择平台：
  - 宽 >= 高  →  B站（publish_bilibili.py，封面用 4:3）
  - 高 >  宽  → 小红书（publish_xiaohongshu.py，封面用 3:4）

用法:
  python publish_auto.py --video <视频> \
      --cover-h <4:3封面(横屏用)> --cover-v <3:4封面(竖屏用)> \
      --title "标题" --desc "简介" --tags "a,b,c" \
      [--shot-dir <目录>] [--publish] [--force-upload]
      [--platform bilibili|xiaohongshu]   # 手动覆盖自动判断

不传 --publish 默认只「存草稿/填好」，由用户手动发布（铁律）。
"""
import argparse
import os
import shutil
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
VENV_PY = sys.executable  # 本脚本就用 venv 的 python 运行

# ffprobe 候选路径
FFPROBE_CANDIDATES = [
    shutil.which("ffprobe"),
    r"C:\Users\chenw\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1.2-full_build\bin\ffprobe",
]


def log(msg):
    print(f"[router] {msg}", flush=True)


def get_ffprobe():
    for p in FFPROBE_CANDIDATES:
        if p and os.path.exists(p):
            return p
    return None


def get_resolution(video):
    """返回 (width, height) 或 None"""
    fp = get_ffprobe()
    if not fp:
        return None
    try:
        out = subprocess.run(
            [fp, "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height", "-of", "csv=p=0",
             video],
            capture_output=True, text=True, timeout=30)
        line = (out.stdout or "").strip().splitlines()
        if line:
            w, h = line[0].split(",")
            return int(w), int(h)
    except Exception as e:
        log(f"ffprobe 失败: {e}")
    return None


def decide_platform(video, manual=None):
    if manual:
        return manual
    res = get_resolution(video)
    if not res:
        log("[WARN] 无法读取分辨率，默认走 B站（横屏）。可用 --platform 手动指定")
        return "bilibili"
    w, h = res
    log(f"分辨率 {w}x{h} → {'横屏' if w >= h else '竖屏'}")
    return "bilibili" if w >= h else "xiaohongshu"


def run_script(script_name, args):
    cmd = [VENV_PY, os.path.join(SCRIPT_DIR, script_name)] + args
    log(f"执行: {' '.join(cmd)}")
    r = subprocess.run(cmd)
    return r.returncode


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--cover-h", default="", help="横屏封面(4:3)，发B站用")
    ap.add_argument("--cover-v", default="", help="竖屏封面(3:4)，发小红书用")
    ap.add_argument("--title", default="")
    ap.add_argument("--desc", default="")
    ap.add_argument("--tags", default="")
    ap.add_argument("--shot-dir", default=None)
    ap.add_argument("--publish", action="store_true")
    ap.add_argument("--force-upload", action="store_true")
    ap.add_argument("--platform", choices=["bilibili", "xiaohongshu"], default=None,
                    help="手动指定平台，覆盖分辨率自动判断")
    args = ap.parse_args()

    if not os.path.exists(args.video):
        log(f"[FAIL] 视频不存在: {args.video}")
        sys.exit(1)

    platform = decide_platform(args.video, args.platform)
    log(f"→ 目标平台: {platform}")

    base = ["--video", args.video,
            "--title", args.title,
            "--desc", args.desc,
            "--tags", args.tags]
    if args.shot_dir:
        base += ["--shot-dir", args.shot_dir]
    if args.publish:
        base += ["--publish"]
    if args.force_upload:
        base += ["--force-upload"]

    if platform == "bilibili":
        cover = args.cover_h or args.cover_v
        if not cover:
            log("[FAIL] 发B站需要 --cover-h(4:3封面)")
            sys.exit(1)
        base = ["--cover", cover] + base
        rc = run_script("publish_bilibili.py", base)
    else:
        # 小红书网页版【支持】自定义封面上传（2026-09-02 实测验证）：传 --cover-v(3:4) 给脚本自动设置
        cover = args.cover_v or args.cover_h
        if cover:
            base = ["--cover", cover] + base
        else:
            log("[INFO] 未提供 --cover-v；将使用视频首帧/智能推荐帧（网页版支持后续手动改封面）")
        rc = run_script("publish_xiaohongshu.py", base)

    log(f"子脚本退出码: {rc}")
    sys.exit(rc)


if __name__ == "__main__":
    main()
