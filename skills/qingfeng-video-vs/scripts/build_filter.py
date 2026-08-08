#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_filter.py —— 生成「顺序聚光对比」视频的 ffmpeg 滤镜图脚本。

支持两种布局（由 --orientation 控制，默认 auto 按左视频宽高自动判断）：
  vertical   （竖屏，默认）：左右双小窗 → 左放大聚光播完 → 右放大聚光播完 → 结尾 CTA。
  horizontal（横屏）：上方一个视频、下方一个视频，位置大小都不变，交叉播放
                      （上播完 → 下接着播），中间一条分隔线 + VS 徽标。

用法示例：
  python3 build_filter.py --left 左.mp4 --right 右.mp4 \
      --left-label "<左/上视频标签>" --right-label "<右/下视频标签>" \
      --title "<对比标题>" --out filter_vs.txt

注意：
  --left-label / --right-label / --title 必须由用户根据两个视频的实际含义提供，
  切勿写死任何具体字眼（如 "WorkBuddy" "秒哒" 仅是历史示例）。
  竖屏时 left=左、right=右；横屏时 left=上、right=下。

说明：
  - 自动用 ffprobe 探测两个视频时长与分辨率（也可用 --left-dur/--right-dur 手动指定）。
  - 自动把技能内的 simhei.ttf 拷贝到滤镜图同目录，ffmpeg 才能找到字体。
  - 默认 title-mode=png：需要先用 render_title.cjs 渲染出 title_frames/f_%03d.png。
  - 输出 filter_vs.txt 与可直接运行的 ffmpeg 命令（打印在末尾）。
"""

import argparse
import os
import shutil
import subprocess
import sys


def probe(path, entries, fmt="default=nw=1:nk=1"):
    ffprobe = os.environ.get("FFPROBE") or "ffprobe"
    try:
        out = subprocess.check_output(
            [ffprobe, "-v", "error", "-show_entries", entries, "-of", fmt, path]
        )
        return out.decode("utf-8").strip()
    except Exception as e:
        sys.exit(f"[错误] 无法用 ffprobe 探测：{path}\n{e}")


def probe_dur(path):
    return float(probe(path, "format=duration"))


def probe_res(path):
    raw = probe(path, "stream=width,height", fmt="csv=p=0")
    for line in raw.splitlines():
        line = line.strip()
        if line and "," in line:
            w, h = line.split(",")
            return int(w), int(h)
    sys.exit(f"[错误] 无法解析分辨率：{path}")


def gen_vertical(args, L, R, font_rel):
    """竖屏：左右双小窗 + 顺序放大聚光。返回 (lines, TOTAL_R, extra_in)。"""
    gin, gout, gap = args.gin, args.gout, args.gap
    L_START = gin
    L_PLAY = L
    R_START = L + gout + gap
    R_PLAY = R_START + gin + R
    CTA = R_PLAY + gout + 0.3
    TOTAL = CTA + 1.2

    LS_stop = round(TOTAL - L, 2)
    RS = round(R_START, 2)
    RS_stop = round(TOTAL - (R_START + R), 2)

    inL = f"min(max((t-{L_START})/{gin},0),1)"
    outL = f"min(max((t-{L_PLAY})/{gout},0),1)"
    inR = f"min(max((t-{R_START})/{gin},0),1)"
    outR = f"min(max((t-{R_PLAY})/{gout},0),1)"
    wL = f"540+540*{inL}-540*{outL}"
    hL = f"960+960*{inL}-960*{outL}"
    wR = f"540+540*{inR}-540*{outR}"
    hR = f"960+960*{inR}-960*{outR}"

    L_PLAY_G = round(L_PLAY + gout, 2)
    R_START_R = round(R_START, 2)
    R_PLAY_G = round(R_PLAY + gout, 2)
    CTA_R = round(CTA, 2)
    TOTAL_R = round(TOTAL, 2)

    lines = []
    # 1) 每个输入 split 成两路：一路做小窗、一路做放大层（防别名污染）
    lines.append("[0:v]split=2[ov0_raw][zm0_raw];")
    lines.append("[1:v]split=2[ov1_raw][zm1_raw];")
    # 2) 小窗：缩到 540x960；右路先冻结 R_START 秒
    lines.append(f"[ov0_raw]scale=540:960,setsar=1,tpad=stop_mode=clone:stop_duration={LS_stop}[wls];")
    lines.append(f"[ov1_raw]scale=540:960,setsar=1,tpad=start_mode=clone:start_duration={RS},tpad=stop_mode=clone:stop_duration={RS_stop}[wrs];")
    # 3) 放大层：同样缩到 540x960 再按帧动态缩放
    lines.append(f"[zm0_raw]scale=540:960,setsar=1,tpad=stop_mode=clone:stop_duration={LS_stop}[zlz];")
    lines.append(f"[zm1_raw]scale=540:960,setsar=1,tpad=start_mode=clone:start_duration={RS},tpad=stop_mode=clone:stop_duration={RS_stop}[zrz];")
    # 4) 放大层动态缩放（eval=frame）
    lines.append(f"[zlz]scale=w='{wL}':h='{hL}':eval=frame[wlA];")
    lines.append(f"[zrz]scale=w='{wR}':h='{hR}':eval=frame[wrA];")
    # 5) 背景画布
    lines.append(f"color=c={args.bg}:s=1080x1920:d={TOTAL_R}[bg];")
    # 6) 双小窗（左 0..540，右 540..1080，居中上下）
    lines.append("[bg][wls]overlay=x=0:y=480[ovLwin];")
    lines.append("[ovLwin][wrs]overlay=x=540:y=480[ovRwin];")
    # 7) 放大层置顶（enable 控制出现窗口，盖住小窗）
    lines.append(f"[ovRwin][wlA]overlay=x=0:y='(main_h-overlay_h)/2':eval=frame:enable='gte(t,{L_START})*lte(t,{L_PLAY_G})'[ovLzoom];")
    lines.append(f"[ovLzoom][wrA]overlay=x='(main_w-overlay_w)':y='(main_h-overlay_h)/2':eval=frame:enable='gte(t,{R_START_R})*lte(t,{R_PLAY_G})'[ovRzoom];")

    if args.title_mode == "png":
        lines.append("[ovRzoom][2:v]overlay=0:0:format=auto[ovTitle];")
        title_chain = "[ovTitle]"
        extra_in = ["-stream_loop", "-1", "-framerate", "30", "-i", "title_frames/f_%03d.png"]
    else:
        title_chain = "[ovRzoom]"
        extra_in = []

    # 8) 标签（左放大时只显左标签，右放大时只显右标签）
    lblL_en = f"between(t,0,{L_START})+between(t,{L_START},{L_PLAY_G})+between(t,{CTA_R},{TOTAL_R})"
    lblR_en = f"between(t,0,{L_START})+between(t,{R_START_R},{R_PLAY_G})+between(t,{CTA_R},{TOTAL_R})"
    vs_en = f"lt(t,{L_START})+gt(t,{CTA_R})"
    cta_a = f"if(lt(t,{CTA_R}),0,min(1,(t-{CTA_R})/0.6))"

    ch = title_chain
    lines.append(f"{ch}drawtext=fontfile={font_rel}:text='{args.left_label}':x=36:y=505:fontsize=46:fontcolor=0x4cc9f0:box=1:boxcolor={args.bg}@0.75:boxborderw=12:enable='{lblL_en}'[d2];")
    ch = "[d2]"
    lines.append(f"{ch}drawtext=fontfile={font_rel}:text='{args.right_label}':x=576:y=505:fontsize=46:fontcolor=0xf72585:box=1:boxcolor={args.bg}@0.75:boxborderw=12:enable='{lblR_en}'[d3];")
    ch = "[d3]"
    lines.append(f"{ch}drawbox=x=538:y=480:w=4:h=960:color=white@0.5:t=fill:enable='{vs_en}'[d4];")
    ch = "[d4]"
    lines.append(f"{ch}drawbox=x=500:y=920:w=80:h=80:color=0xffd166:t=fill:enable='{vs_en}'[d5];")
    ch = "[d5]"
    lines.append(f"{ch}drawtext=fontfile={font_rel}:text='VS':x=(w/2-text_w/2):y=932:fontsize=44:fontcolor={args.bg}:enable='{vs_en}'[d6];")
    ch = "[d6]"
    lines.append(f"{ch}drawtext=fontfile={font_rel}:text='你更看好谁？评论区聊聊':x=(w-text_w)/2:y=1630:fontsize=54:fontcolor=white:shadowcolor=black:shadowx=3:shadowy=3:alpha='{cta_a}'[d7];")
    ch = "[d7]"
    lines.append(f"{ch}drawtext=fontfile={font_rel}:text='左边 {args.left_label} · 右边 {args.right_label}':x=(w-text_w)/2:y=1715:fontsize=34:fontcolor=0xffd166:alpha='{cta_a}'[outv];")

    # 9) 音频：统一 44100 单声道；右路 atrim 后延时 R_START 秒对齐；再混流
    lines.append(f"[0:a]aresample=44100,aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=mono,atrim=0:{round(L,3)}[la];")
    lines.append(f"[1:a]aresample=44100,aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=mono,atrim=0:{round(R,3)},adelay={round(R_START*1000)}[ra];")
    lines.append("[la][ra]amix=inputs=2:duration=longest[outa]")

    return lines, TOTAL_R, extra_in


def gen_horizontal(args, L, R, W, H, font_rel):
    """横屏：上下各一视频，位置大小不变，交叉播放（上播完 → 下播）。"""
    H2 = H // 2
    T1 = L                      # 上片时长
    T2 = R                      # 下片时长
    BOT_START = T1              # 下片在上片播完后开始
    CTA = (T1 + T2) + 0.3
    TOTAL = CTA + 1.0

    top_stop = round(TOTAL - T1, 2)
    bot_start = round(BOT_START, 2)
    bot_stop = round(TOTAL - (BOT_START + T2), 2)

    fs = max(40, round(W * 0.028))        # 标签字号随画布宽度
    cta_main = max(40, round(W * 0.03))
    cta_sub = max(28, round(W * 0.018))
    CTA_R = round(CTA, 2)
    TOTAL_R = round(TOTAL, 2)

    # 标题条：保持 2:1，高度取画布 1/3，宽度按比例并限制不超画布宽
    titleH = H // 3
    titleW = min(titleH * 2, W)

    lines = []
    # 每路只 overlay 一次，不存在别名污染，无需 split
    lines.append(f"[0:v]scale={W}:{H2},setsar=1,tpad=stop_mode=clone:stop_duration={top_stop}[top];")
    lines.append(f"[1:v]scale={W}:{H2},setsar=1,tpad=start_mode=clone:start_duration={bot_start},tpad=stop_mode=clone:stop_duration={bot_stop}[bot];")
    lines.append(f"color=c={args.bg}:s={W}x{H}:d={TOTAL_R}[bg];")
    lines.append("[bg][top]overlay=0:0[ovTop];")
    lines.append(f"[ovTop][bot]overlay=0:{H2}[ovBot];")

    if args.title_mode == "png":
        lines.append(f"[2:v]scale={titleW}:{titleH}[ttl];")
        lines.append(f"[ovBot][ttl]overlay={(W-titleW)//2}:0:format=auto[ovTitle];")
        ch = "[ovTitle]"
        extra_in = ["-stream_loop", "-1", "-framerate", "30", "-i", "title_frames/f_%03d.png"]
    else:
        ch = "[ovBot]"
        extra_in = []

    # 标签始终显示（上区域顶部、下区域顶部）
    lines.append(f"{ch}drawtext=fontfile={font_rel}:text='{args.left_label}':x=36:y=20:fontsize={fs}:fontcolor=0x4cc9f0:box=1:boxcolor={args.bg}@0.75:boxborderw=12[d2];")
    ch = "[d2]"
    lines.append(f"{ch}drawtext=fontfile={font_rel}:text='{args.right_label}':x=36:y={H2+20}:fontsize={fs}:fontcolor=0xf72585:box=1:boxcolor={args.bg}@0.75:boxborderw=12[d3];")
    ch = "[d3]"
    # 中间分隔线
    lines.append(f"{ch}drawbox=x=0:y={H2-2}:w={W}:h=4:color=white@0.5:t=fill[d4];")
    ch = "[d4]"
    # VS 徽标（分隔线中央）
    lines.append(f"{ch}drawbox=x={W//2-40}:y={H2-40}:w=80:h=80:color=0xffd166:t=fill[d5];")
    ch = "[d5]"
    lines.append(f"{ch}drawtext=fontfile={font_rel}:text='VS':x={W//2-22}:y={H2-26}:fontsize=44:fontcolor={args.bg}[d6];")
    ch = "[d6]"
    # 结尾 CTA
    cta_a = f"if(lt(t,{CTA_R}),0,min(1,(t-{CTA_R})/0.6))"
    lines.append(f"{ch}drawtext=fontfile={font_rel}:text='你更看好谁？评论区聊聊':x=(w-text_w)/2:y={H-130}:fontsize={cta_main}:fontcolor=white:shadowcolor=black:shadowx=3:shadowy=3:alpha='{cta_a}'[d7];")
    ch = "[d7]"
    lines.append(f"{ch}drawtext=fontfile={font_rel}:text='上面 {args.left_label} · 下面 {args.right_label}':x=(w-text_w)/2:y={H-60}:fontsize={cta_sub}:fontcolor=0xffd166:alpha='{cta_a}'[outv];")

    # 音频：上片 atrim 0:T1；下片 atrim 0:T2 后延时 T1 秒对齐；再混流
    lines.append(f"[0:a]aresample=44100,aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=mono,atrim=0:{round(L,3)}[la];")
    lines.append(f"[1:a]aresample=44100,aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=mono,atrim=0:{round(R,3)},adelay={round(BOT_START*1000)}[ra];")
    lines.append("[la][ra]amix=inputs=2:duration=longest[outa]")

    return lines, TOTAL_R, extra_in


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    skill_dir = os.path.dirname(here)

    ap = argparse.ArgumentParser(description="生成顺序聚光对比视频滤镜图（自动判断横竖屏）")
    ap.add_argument("--left", help="左（竖屏）/ 上（横屏）视频文件路径")
    ap.add_argument("--right", help="右（竖屏）/ 下（横屏）视频文件路径")
    ap.add_argument("--left-dur", type=float, help="时长（秒），省略则自动探测")
    ap.add_argument("--right-dur", type=float, help="时长（秒），省略则自动探测")
    ap.add_argument("--left-label", default="左边")
    ap.add_argument("--right-label", default="右边")
    ap.add_argument("--title", default="同一主题 · 两种效果，你更看好谁？",
                    help="仅 text 模式使用；png 模式文字改 assets/title_effect.html")
    ap.add_argument("--out", default="filter_vs.txt", help="输出的滤镜图脚本路径")
    ap.add_argument("--font", default=os.path.join(skill_dir, "assets", "simhei.ttf"))
    ap.add_argument("--bg", default="0x16162b", help="背景色（十六进制 0xRRGGBB）")
    ap.add_argument("--orientation", choices=["auto", "vertical", "horizontal"], default="auto",
                    help="auto 按左视频宽高自动判断；也可手动指定")
    ap.add_argument("--gin", type=float, default=0.6)
    ap.add_argument("--gout", type=float, default=0.7)
    ap.add_argument("--gap", type=float, default=0.2)
    ap.add_argument("--title-mode", choices=["png", "text"], default="png")
    ap.add_argument("--ffmpeg", default="ffmpeg")
    args = ap.parse_args()

    if not args.left or not args.right:
        sys.exit("[错误] 必须提供 --left 与 --right 两个视频路径。")
    if args.left_dur is None:
        args.left_dur = probe_dur(args.left)
    if args.right_dur is None:
        args.right_dur = probe_dur(args.right)
    L, R = args.left_dur, args.right_dur

    # 字体拷贝到输出目录（ffmpeg 相对 cwd 找字体）
    out_dir = os.path.dirname(os.path.abspath(args.out)) or "."
    font_rel = "simhei.ttf"
    font_dst = os.path.join(out_dir, font_rel)
    if os.path.abspath(args.font) != os.path.abspath(font_dst) and os.path.exists(args.font):
        shutil.copy(args.font, font_dst)

    # 决定朝向
    if args.orientation == "auto":
        w, h = probe_res(args.left)
        orientation = "horizontal" if w > h else "vertical"
    else:
        orientation = args.orientation

    if orientation == "vertical":
        lines, TOTAL_R, extra_in = gen_vertical(args, L, R, font_rel)
    else:
        w, h = probe_res(args.left)
        lines, TOTAL_R, extra_in = gen_horizontal(args, L, R, w, h, font_rel)

    with open(args.out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    ffmpeg_cmd = [
        args.ffmpeg, "-y",
        "-i", args.left, "-i", args.right,
    ] + extra_in + [
        "-filter_complex_script", args.out,
        "-map", "[outv]", "-map", "[outa]",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30",
        "-c:a", "aac",
        "-t", str(TOTAL_R), "对比视频.mp4",
    ]

    print("ORIENTATION:", orientation)
    print("FILTER_SCRIPT:", os.path.abspath(args.out))
    print("TOTAL_DURATION:", TOTAL_R)
    print("NOTE: png 模式需先渲染 title_frames/f_%03d.png （见 render_title.cjs）")
    print("RUN:")
    print(" ".join(ffmpeg_cmd))


if __name__ == "__main__":
    main()
