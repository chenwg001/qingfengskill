#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
确定性短视频编排：文本 -> 配音 -> 按配音时长反推每段素材时长 -> 转场 -> 同步字幕

流水线：
  1. 配音（默认 edge=edge-tts 在线；可选 local=本机 TTS 克隆），得到 voiceover 与总时长 T
  2. 扫描素材库，按文件名排序
  3. 反推每段时长：
       ideal = T / 素材数
       - ideal >= 5：每段 ideal 秒，全部素材都用上，总长≈T
       - ideal <  5：每段至少 5 秒；前 m 段各 5 秒，最后一段补到 T，
                     其余素材（超出 T 的）不用  -> 镜头不切太快且达 T 即停
  4. 抽取/循环每段素材到目标时长（短素材自身循环补齐）
  5. xfade 多转场交替拼接（默认 0.5s，内置多种效果循环使用），再补帧到刚好 T
  6. 字幕对齐：本地克隆逐句生成配音，取每句真实时长做句级时间轴（逐句精确同步）；
     拿不到句级时长时回退为按字数比例的全局近似对齐
  7. 烧录字幕 + 混流配音音频 -> 成片

用法：
  python make_video.py \\
      --script work/script.txt \\
      --materials "path/to/materials" \\
      --backend edge \\
      --output output/video.mp4
"""
import argparse
import json
import os
import re
import hashlib
import shutil
import subprocess
import sys
import tempfile

# ---------- 工具 ----------
def run(cmd, **kw):
    print("[ffmpeg]", " ".join(cmd) if isinstance(cmd, list) else cmd)
    subprocess.run(cmd, check=True, **kw)

def ffprobe_duration(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", path],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())

def video_duration(path):
    """素材自身时长：优先 format，缺失/为 0 时用首个视频流时长兜底"""
    d = ffprobe_duration(path)
    if d and d > 0:
        return d
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", path],
        capture_output=True, text=True, check=True,
    )
    v = out.stdout.strip()
    return float(v) if v else 0.0

def video_aspect(path):
    """检测视频宽高比，返回 (width, height, ratio_float)"""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height",
         "-of", "json", path],
        capture_output=True, text=True, check=True,
    )
    import json
    data = json.loads(out.stdout)
    w = int(data['streams'][0]['width'])
    h = int(data['streams'][0]['height'])
    return w, h, w / h if h > 0 else 1.0

def list_materials(folder, numbered_only=False):
    exts = (".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v", ".MP4")
    files = [os.path.join(folder, f) for f in os.listdir(folder)
             if f.lower().endswith(exts)]
    if numbered_only:
        # B 模式：只保留「纯数字序号命名」的素材（如 1.mp4 / 10.mp4），哈希命名一律抛弃
        files = [f for f in files
                 if re.fullmatch(r"\d+", os.path.splitext(os.path.basename(f))[0])]
    # 数字前缀优先排序，否则按文件名
    def key(p):
        base = os.path.basename(p)
        m = re.match(r"^(\d+)", base)
        return (int(m.group(1)) if m else 1 << 30, base)
    return sorted(files, key=key)

# ---------- 1. 配音 ----------
def _decode_to_wav(src, dst):
    subprocess.run(["ffmpeg", "-y", "-i", src, dst], check=True, capture_output=True)

def make_voiceover(script_text, backend, ref, out_wav, language="Auto",
                  voice="zh-CN-YunxiNeural"):
    """返回 (总时长, 每句真实时长列表)。每句真实时长用于字幕精确同步。

    backend:
      - "edge"（默认）：微软 edge-tts 在线生成，逐句生成以拿到每句真实时长，
        无需本机模型，所有用户可用；音色由 voice 指定。
      - "local"：本机 Qwen3-TTS 声音克隆，**仅作者本机可选**，需提前配置模型与 --ref。
    """
    sents = [s.strip() for s in re.split(r"(?<=[。！？\n])", script_text.strip()) if s.strip()]
    sents = sents or [script_text.strip()]
    tmp_dir = tempfile.gettempdir()
    tmp_wavs, sentence_durations = [], []

    if backend == "edge":
        import asyncio, time, edge_tts
        def _gen_once(text, path):
            async def _run():
                # 每次都用全新的 Communicate，避免连接状态复用导致的异常
                comm = edge_tts.Communicate(text, voice)
                n = 0
                with open(path, "wb") as f:
                    async for ev in comm.stream():
                        if ev["type"] == "audio":
                            f.write(ev["data"])
                            n += 1
                if n == 0:
                    raise RuntimeError("edge-tts 未返回任何音频数据")
            asyncio.run(_run())
        # 逐句 28 次连发会在 ~第 20 句被微软限流（NoAudioReceived），故改为每 GROUP 句合成一次，
        # 连接数降到 ~7，既绕开限流，又把段时长按字数比例分到各句，保留句级近似同步。
        GROUP = 4
        chunks = [sents[i:i + GROUP] for i in range(0, len(sents), GROUP)]
        for ci, chunk in enumerate(chunks):
            piece = "".join(chunk)
            mp3 = os.path.join(tmp_dir, f"_vox_c{ci}.mp3")
            wav = os.path.join(tmp_dir, f"_vox_c{ci}.wav")
            last = None
            for attempt in range(3):
                try:
                    if os.path.exists(mp3):
                        os.remove(mp3)
                    _gen_once(piece, mp3)
                    if os.path.getsize(mp3) > 0:
                        break
                except Exception as e:
                    last = e
                    time.sleep(2 * (attempt + 1))
            else:
                raise RuntimeError(
                    f"edge-tts 配音失败（第 {ci+1}/{len(chunks)} 段）：{type(last).__name__}: {last}。"
                    f"请检查网络连接（需能访问微软 TTS 服务）或换一个 voice 音色。"
                )
            _decode_to_wav(mp3, wav)
            cd = ffprobe_duration(wav)
            # 把本段时长按各句字数比例分配，得到近似句级时间轴（字幕仍可句级对齐）
            clens = [len(s) for s in chunk]
            csum = sum(clens) or 1
            for c in clens:
                sentence_durations.append(cd * c / csum)
            tmp_wavs.append(wav)
            if os.path.exists(mp3):
                os.remove(mp3)
            time.sleep(1.2)  # 段间间隔，进一步降低限频概率
    else:
        # 本地克隆：需要使用带 TTS 推理环境的 Python
        tts_py = os.environ.get("QWEN_TTS_PYTHON")
        if not tts_py:
            print("[错误] 未配置本地 TTS 环境，请设置环境变量 QWEN_TTS_PYTHON", file=sys.stderr)
            sys.exit(1)
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
        tts_script = os.path.join(os.path.dirname(__file__), "tts.py")
        for i, s in enumerate(sents):
            t = os.path.join(tmp_dir, f"_vox_{i}.wav")
            subprocess.run(
                [tts_py, tts_script, "--backend", "local", "--text", s,
                 "--ref", ref, "--out", t, "--language", language],
                check=True,
            )
            sentence_durations.append(ffprobe_duration(t))
            tmp_wavs.append(t)

    if len(tmp_wavs) == 1:
        # 兼容跨磁盘移动（Windows 限制 os.replace 不能跨盘）
        if os.path.dirname(os.path.abspath(tmp_wavs[0])) != os.path.dirname(os.path.abspath(out_wav)):
            shutil.copy2(tmp_wavs[0], out_wav)
            os.remove(tmp_wavs[0])
        else:
            os.replace(tmp_wavs[0], out_wav)
    else:
        listf = os.path.join(tmp_dir, "_vox_list.txt")
        with open(listf, "w", encoding="utf-8") as f:
            for t in tmp_wavs:
                f.write(f"file '{t}'\n")
        subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0",
                        "-i", listf, "-c", "copy", out_wav],
                       check=True, capture_output=True)
        os.remove(listf)
        for t in tmp_wavs:
            if os.path.exists(t):
                os.remove(t)
    return ffprobe_duration(out_wav), sentence_durations

# ---------- 3. 反推每段时长（新算法：不变速、不循环、按需补齐） ----------
def plan_clips(T, num, min_clip=5.0):
    """返回每段目标时长列表（长度 <= num，超出 T 的素材不用）"""
    if num == 0:
        raise SystemExit("素材库为空")
    ideal = T / num
    if ideal >= min_clip:
        clips = [ideal] * num
    else:
        # 每段至少 min_clip；最后一段补到 T
        m = max(1, int((T - min_clip) // min_clip))   # 满 min_clip 的段数
        last = T - m * min_clip                       # 末段 ∈ [min_clip, 2*min_clip)
        clips = [min_clip] * m + [last]
    return clips

def build_clip_plan(durations, plan_target, min_clip=5.0):
    """按新剪辑算法规划每段时长：
    - 全部 >= avg 时，均分（各截取 avg 秒）
    - 有短于 avg 时：
      - 短素材保持原长（不变速、不循环）
      - 长素材截取 avg + 额外补偿（缺口由长素材均摊）
    - 所有素材总长仍不足时，选1-2个最长素材重复插位补齐
    返回 (clips: 每段截取时长列表, gap_info: 重复插入的详情列表)
    """
    n = len(durations)
    if n == 0:
        raise SystemExit("素材库为空")

    avg = plan_target / n

    # Phase 1: 分类短/长素材
    short_idx = [i for i, d in enumerate(durations) if d < avg - 1e-3]
    long_idx = [i for i, d in enumerate(durations) if d >= avg - 1e-3]

    if not short_idx:
        # 全部 >= avg，直接均分
        clips = [avg] * n
        return clips, []

    # Phase 2: 短素材保持原长，计算缺口
    short_total = sum(durations[i] for i in short_idx)
    deficit = plan_target - short_total  # 需要长素材提供的时长

    clips = list(durations)  # 先复制所有素材原长
    gap_info = []

    if long_idx:
        # 有长素材可以补偿缺口
        per_long = deficit / len(long_idx)
        for i in long_idx:
            clips[i] = per_long
    else:
        # 所有素材都短于 avg，需要在末尾追加重复片段
        # 选最长的素材重复使用
        longest_idx = max(range(n), key=lambda i: durations[i])
        per_repeat = durations[longest_idx]
        needed_count = int(deficit / per_repeat) + 1
        per_final = deficit / needed_count

        for _ in range(needed_count):
            clips.append(per_final)
            gap_info.append({
                "mat_idx": longest_idx,
                "mat_name": f"素材{longest_idx+1}({durations[longest_idx]:.1f}s)",
                "insert_at": len(clips) - 1,
                "extra_dur": per_final
            })

    return clips, gap_info

# ---------- 4. 抽取/循环素材段 ----------
def extract_scene(mat, need, out_path, w=1280, h=720, fps=30):
    """从素材开头截取 need 秒（不变速、不循环）。
    -seek 0 确保从第一帧开始，-t 精确截断。
    """
    vf = (f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
          f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps},format=yuv420p")
    run(["ffmpeg", "-y", "-ss", "0", "-i", mat, "-t", f"{need:.3f}",
         "-vf", vf, "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p",
         "-preset", "medium", out_path])

# ---------- 5. xfade 转场拼接 ----------
# 内置一组稳妥好看的转场（均不依赖外部文件，且对 1280x720 偶尺寸安全）
TRANSITIONS = [
    "fade",        # 经典溶解
    "slideleft",   # 新画面从左滑入
    "slideright",  # 新画面从右滑入
    "slideup",     # 新画面从下滑入
    "slidedown",   # 新画面从上滑入
    "circlecrop",  # 圆形扩散
    "rectcrop",    # 矩形扩散
    "distance",    # 边缘扩散（菱形）
    "wipeleft",    # 左向擦除
    "wiperight",   # 右向擦除
    "circleopen",  # 圆形张开
    "smoothleft",  # 平滑左推
]
KNOWN_TRANSITIONS = set([
    "fade","wipeleft","wiperight","wipeup","wipedown","slideleft","slideright",
    "slideup","slidedown","circlecrop","rectcrop","distance","fadeblack",
    "fadewhite","radial","smoothleft","smoothright","smoothup","smoothdown",
    "circleopen","circleclose","pixelize","diagtl","diagtr","diagbl","diagbr",
    "hlslice","fadegrays","wipetl","wipetr","wipebl","wipebr","squeezeh",
    "squeezev","fadefast","fadeslow","hlwind","coverleft","coverright",
    "coverup","coverdown","revealleft","revealright","revealup","revealdown",
])

def _resolve_transitions(value, count):
    """把 --transition 参数解析成长度=count(=n-1) 的转场列表。
       - "mix" 或 "auto"：用内置 TRANSITIONS 循环交替
       - 逗号分隔多值：在该列表中循环交替
       - 单一名：全程复用（兼容旧行为）
       非法名回退为 fade。
    """
    if isinstance(value, (list, tuple)):
        base = list(value)
    elif str(value).strip().lower() in ("mix", "auto"):
        base = list(TRANSITIONS)
    else:
        parts = [x.strip() for x in str(value).split(",") if x.strip()]
        base = parts if parts else ["fade"]
    base = [b if b in KNOWN_TRANSITIONS else "fade" for b in base]
    if not base:
        base = ["fade"]
    if len(base) == 1:
        return base * count            # 单一转场：全程复用
    return [base[i % len(base)] for i in range(count)]

def concat_xfade(scenes, transitions="fade", t=0.5, out_path=None):
    n = len(scenes)
    if n == 1:
        if out_path:
            run(["ffmpeg", "-y", "-i", scenes[0], "-c", "copy", out_path])
            return out_path
        return scenes[0]
    if isinstance(transitions, str):
        transitions = _resolve_transitions(transitions, n - 1)
    inputs = []
    for s in scenes:
        inputs += ["-i", s]
    # 累计偏移：第 k 次合并的 offset = 当前已合并长度 - t
    durs = [ffprobe_duration(s) for s in scenes]
    offsets = []
    merged = durs[0]                     # 当前已合并片段长度
    for i in range(1, n):
        offsets.append(merged - t)      # 在这之前开始交叉溶解
        merged = merged + durs[i] - t   # 合并后长度
    fc = []
    prev = "[0:v]"
    for i in range(1, n):
        tr = transitions[i - 1]
        out = f"[v{i}]" if i < n - 1 else "[vout]"
        fc.append(f"{prev}[{i}:v]xfade=transition={tr}"
                  f":duration={t}:offset={offsets[i-1]:.3f}{out}")
        prev = out
    filter_complex = ";".join(fc)
    cmd = ["ffmpeg", "-y"] + inputs + ["-filter_complex", filter_complex,
           "-map", "[vout]", "-c:v", "libx264", "-pix_fmt", "yuv420p",
           "-preset", "medium"]
    if out_path:
        cmd.append(out_path)
    run(cmd)
    return out_path

def concat_xfade_av(scenes, transitions="fade", t=0.5, out_path=None):
    """带音频的 xfade 拼接：视频用 xfade、音频用 acrossfade 同步交叉淡入，
    保证各段原声（配音）在总合成中不丢失。供 B 模式最终拼接使用。
    """
    n = len(scenes)
    if n == 1:
        if out_path:
            run(["ffmpeg", "-y", "-i", scenes[0], "-c", "copy", out_path])
            return out_path
        return scenes[0]
    if isinstance(transitions, str):
        transitions = _resolve_transitions(transitions, n - 1)
    inputs = []
    for s in scenes:
        inputs += ["-i", s]
    durs = [ffprobe_duration(s) for s in scenes]
    offsets = []
    merged = durs[0]
    for i in range(1, n):
        offsets.append(merged - t)
        merged = merged + durs[i] - t
    fc = []
    prev = "[0:v]"
    for i in range(1, n):
        tr = transitions[i - 1]
        out = f"[v{i}]" if i < n - 1 else "[vout]"
        fc.append(f"{prev}[{i}:v]xfade=transition={tr}:duration={t}:offset={offsets[i-1]:.3f}{out}")
        prev = out
    preva = "[0:a]"
    for i in range(1, n):
        aout = f"[a{i}]" if i < n - 1 else "[aout]"
        fc.append(f"{preva}[{i}:a]acrossfade=d={t}:c1=tri:c2=tri{aout}")
        preva = aout
    filter_complex = ";".join(fc)
    cmd = ["ffmpeg", "-y"] + inputs + ["-filter_complex", filter_complex,
           "-map", "[vout]", "-map", "[aout]",
           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "medium",
           "-c:a", "aac", "-ar", "44100"]
    if out_path:
        cmd.append(out_path)
    run(cmd)
    return out_path

def join_segments_intact(parts, out_path=None):
    """纯拼接：把各 partN.mp4 按序「原样串接」，不做 xfade/acrossfade，
    绝不重新处理声音、绝不重定时，确保每段内部已烧好的音画同步完整保留。

    B 模式各段 partN.mp4 已是「画面+字幕+配音」三者同步好的自包含片段，
    最终合成只需把它们首尾相连即可——这正是用户「分段就是为了音画同步、
    最后合成要原样接起」的诉求。任何交叉溶解/重定时都会破坏边界同步。

    优先 stream-copy（零重编码，最保真）；若分段编码不兼容则回退 concat 滤镜。
    """
    n = len(parts)
    if n == 1:
        if out_path:
            run(["ffmpeg", "-y", "-i", parts[0], "-c", "copy", out_path])
            return out_path
        return parts[0]
    # 1) 尝试 stream-copy 拼接（原样接起，声音零改动）
    listf = os.path.join(tempfile.gettempdir(), "_join_list.txt")
    with open(listf, "w", encoding="utf-8") as f:
        for p in parts:
            f.write(f"file '{os.path.abspath(p)}'\n")
    try:
        run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", listf,
             "-c", "copy", out_path])
        print(f"[拼接·纯] stream-copy 原样接起 {n} 段 -> {out_path}")
        return out_path
    except Exception as e:
        print(f"[拼接·纯] stream-copy 失败（{type(e).__name__}），回退 concat 滤镜：{e}")
    finally:
        if os.path.exists(listf):
            os.remove(listf)
    # 2) 回退：concat 滤镜（重编码但无重叠、时间轴不压缩，逐段原样衔接，音画同步仍保留）
    inputs = []
    for p in parts:
        inputs += ["-i", p]
    fc = "".join(f"[{i}:v][{i}:a]" for i in range(n)) + f"concat=n={n}:v=1:a=1[v][a]"
    run(["ffmpeg", "-y"] + inputs + ["-filter_complex", fc,
         "-map", "[v]", "-map", "[a]", "-c:v", "libx264",
         "-pix_fmt", "yuv420p", "-preset", "medium",
         "-c:a", "aac", "-ar", "44100", out_path])
    print(f"[拼接·纯] concat 滤镜接起 {n} 段 -> {out_path}")
    return out_path

def mix_bgm(video, bgm_path, out_path, gain=0.3):
    """把 BGM 叠加在原声之下：BGM 降增益 + 循环补足 + 截断到视频时长，与原声 amix，
    绝不替换/消除原声（配音始终保留、可听）。BGM 短于视频时自动循环。

    关键：用输入级 `-stream_loop -1` 让 BGM 无限循环，再用 `atrim=0:视频时长` 兜底截断，
    避免 `aloop` 在部分 ffmpeg 版本下行为异常把音频拉长（曾导致音频比视频长 40s、
    视频播完画面冻结 BGM 还在响）。视频始终 `-c:v copy`，音画同步结构原样保留。
    """
    vdur = ffprobe_duration(video)
    fc = (
        f"[1:a]volume={gain},"
        f"atrim=0:{vdur:.3f},"
        f"asetpts=PTS-STARTPTS[bgm];"
        f"[0:a][bgm]amix=inputs=2:duration=longest:dropout_transition=0[mix]"
    )
    # 输出层再 -t 硬截断到视频时长：atrim 在「无限循环输入」上会被忽略，
    # 仅靠滤镜无法保证 BGM 不长于视频，故输出层兜底，确保音画等长、视频不冻结。
    run(["ffmpeg", "-y", "-i", video, "-stream_loop", "-1", "-i", bgm_path,
         "-filter_complex", fc,
         "-map", "0:v:0", "-map", "[mix]",
         "-c:v", "copy", "-c:a", "aac", "-ar", "44100", "-t", f"{vdur:.3f}",
         out_path])
    return out_path

# ---------- 6. 字幕（强制单行 + 长句拆行 + 按字数比例对齐） ----------
def split_sentences(text):
    # 以句末标点切分，保留标点
    parts = re.split(r"(?<=[。！？\n])", text)
    return [p.strip() for p in parts if p.strip()]

PUNCT = "，。！？、；：,.!?;: "

def _split_lines(sent, max_chars):
    """把一句话切成若干 <= max_chars 的单行片段，尽量在 max_chars 之前的标点处断句"""
    chunks, rest = [], sent
    while rest:
        if len(rest) <= max_chars:
            chunks.append(rest)
            break
        seg = rest[:max_chars]
        # 在 seg 内（不从首字符起，避免首字即标点导致 1 字符行）找最后一个标点作为断点
        cut = -1
        for i in range(len(seg) - 1, 0, -1):
            if seg[i] in PUNCT:
                cut = i + 1            # 标点留在上一行
                break
        if cut <= 0:                   # 该片段内无标点，只能硬切
            cut = max_chars
        chunks.append(rest[:cut])
        rest = rest[cut:]
    return chunks

def _ass_time(sec):
    h = int(sec // 3600)
    m = int(sec % 3600 // 60)
    s = sec % 60
    return f"{h}:{m:02d}:{s:05.2f}"

def _ass_escape(txt):
    return txt.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")

def _place(s0, s1, chunks, entries):
    """把一行(或拆成多行)的字幕放进 [s0, s1] 区间，多行按各段字数比例依次排布"""
    if len(chunks) == 1:
        entries.append((s0, s1, chunks[0]))
    else:
        clens = [len(c) for c in chunks]
        csum = sum(clens) or 1
        ct = s0
        for c in chunks:
            cd = (s1 - s0) * len(c) / csum
            entries.append((ct, ct + cd, c))
            ct += cd

def build_ass(text, sentence_spans, total_dur, ass_path, max_chars=22,
              width=1280, height=720):
    """生成 ASS 字幕：强制单行(WrapStyle=2)，长句拆成多条依次出现。

    sentence_spans: 优先用「每句在配音中的真实时间区间 (start,end) 列表」，
                   此时字幕与配音逐句精确同步；若为 None（拿不到句级时长，
                   如 edge-tts 整段生成），则回退为按字数比例的全局近似对齐。
    """
    fontsize = round(width / 1280 * 72)   # 字号随宽度等比缩放（16:9 基准 72，大字体更易阅读）
    segs = split_sentences(text)
    entries = []
    if sentence_spans is not None and len(sentence_spans) == len(segs):
        for sent, (s0, s1) in zip(segs, sentence_spans):
            _place(s0, s1, _split_lines(sent, max_chars), entries)
    else:
        # 回退：按字数比例把 total_dur 均分到各句
        lens = [len(s) for s in segs]
        tc = sum(lens) or 1
        t = 0.0
        for s in segs:
            dur = total_dur * len(s) / tc
            _place(t, t + dur, _split_lines(s, max_chars), entries)
            t += dur

    header = f"""[Script Info]
Title: generated
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Microsoft YaHei,{fontsize},&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,3,0,2,20,20,40,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [header]
    for s0, e0, txt in entries:
        lines.append(
            f"Dialogue: 0,{_ass_time(s0)},{_ass_time(e0)},Default,,0,0,0,,{_ass_escape(txt)}"
        )
    with open(ass_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"[字幕] 共 {len(segs)} 句 -> {len(entries)} 条单行 ASS 字幕 (max_chars={max_chars})")
    return ass_path

# ---------- 7. 烧字幕 + 混音 ----------
def burn_and_mux(video, ass, audio, out_path):
    # Windows 下 subtitles 滤镜对盘符冒号 C: / 反斜杠极敏感。
    # 稳妥做法：把 ass 复制到临时目录，切到该目录用相对文件名引用，彻底避开路径解析问题。
    tmp_ass = os.path.join(tempfile.gettempdir(), "subs_burn.ass")
    with open(ass, encoding="utf-8") as f:
        ass_text = f.read()
    with open(tmp_ass, "w", encoding="utf-8") as f:
        f.write(ass_text)
    vf = "subtitles=subs_burn.ass"
    out_abs = os.path.abspath(out_path)
    old_cwd = os.getcwd()
    os.chdir(tempfile.gettempdir())           # 让 subtitles=subs_burn.ass 按相对路径解析
    try:
        # 不限制长度、不用 -shortest：成品长度=视频长度（比配音长），配音结束后画面继续播
        cmd = ["ffmpeg", "-y", "-i", os.path.abspath(video),
               "-i", os.path.abspath(audio),
               "-vf", vf, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "medium",
               "-map", "0:v:0", "-map", "1:a:0", "-c:a", "aac", out_abs]
        run(cmd)
    finally:
        os.chdir(old_cwd)
    return out_path

# ---------- 单段混剪（A/B 模式共用） ----------
def mix_segment(seg_text, mat_dir, args, OUT_W, OUT_H, tag):
    """对一段文本 + 一个素材目录，产出一段已烧录字幕、已混入配音的成片片段。
    返回 (片段路径, 配音时长 T)。B 模式对每段分别调用，再拼接。
    """
    work = os.path.join(os.path.dirname(os.path.abspath(__file__)), "work")
    os.makedirs(work, exist_ok=True)

    # 该段配音（按「脚本路径+段号+引擎+音色+段首文本」哈希缓存，避免跨段/跨脚本/换引擎/换音色误复用旧音频）
    seg_key = hashlib.sha1(
        (os.path.abspath(args.script) + "|" + str(tag) + "|" + args.backend + "|" + args.voice + "|" + seg_text[:200])
        .encode("utf-8")
    ).hexdigest()[:12]
    vox = os.path.join(work, f"voiceover_seg_{seg_key}.wav")
    vox_json = vox + ".json"
    part_path = os.path.join(work, f"part_{tag}.mp4")
    raw_path = os.path.join(work, f"raw_{tag}.mp4")
    # 如果配音缓存存在但视频片段缺失，或配音参数（引擎/音色）变化导致需要重新生成，则删除旧缓存
    if os.path.exists(vox) and not os.path.exists(part_path):
        # 配音存在但视频缺失，可能是中途中断，删除配音缓存让下次完整重生成
        print(f"[配音·段{tag}] 发现配音缓存但视频缺失，清除缓存后重新生成")
        os.remove(vox)
        if os.path.exists(vox_json):
            os.remove(vox_json)
        if os.path.exists(raw_path):
            os.remove(raw_path)
    if os.path.exists(vox):
        T = ffprobe_duration(vox)
        sent_durs = (json.load(open(vox_json, encoding="utf-8"))
                     if os.path.exists(vox_json) else None)
        print(f"[配音·段{tag}] 复用已有 {os.path.basename(vox)}  时长 T = {T:.2f}s")
    else:
        T, sent_durs = make_voiceover(seg_text, args.backend, args.ref, vox,
                                      args.language, args.voice)
        with open(vox_json, "w", encoding="utf-8") as f:
            json.dump(sent_durs, f)
        print(f"[配音·段{tag}] 生成完毕  时长 T = {T:.2f}s")

    # 素材：B 模式只收纯数字序号命名，且自身 >=5s
    mats_all = list_materials(mat_dir, numbered_only=True)
    mats, dropped_short = [], []
    for m in mats_all:
        d = video_duration(m)
        if d >= 5.0 - 1e-3:
            mats.append(m)
        else:
            dropped_short.append(f"{os.path.basename(m)}({d:.2f}s)")
    print(f"[规划·段{tag}] 素材 = {len(mats_all)}，保留 = {len(mats)}: "
          f"{[os.path.basename(m) for m in mats]}")
    if dropped_short:
        print(f"[规划·段{tag}] 因 <5s 或 非序号 丢弃: {dropped_short}")

    if not mats:
        raise SystemExit(f"段 {tag} 无可用素材（检查 {mat_dir} 下的序号命名视频）。")

    n = len(mats)
    # 视频时长 = 配音时长 + 额外缓冲（不再强制30秒最小值）
    V = T + args.video_extra
    buf = 0.5
    plan_target = V + (n - 1) * args.t_dur + buf

    # 先量取所有素材真实时长
    durations = [video_duration(m) for m in mats]
    # 新剪辑算法：不变速、不循环、按需补齐
    clips, gap_info = build_clip_plan(durations, plan_target)
    print(f"[规划·段{tag}] 配音 T = {T:.2f}s  视频目标 V = {V:.2f}s  素材数={n}  计划段数={len(clips)}")
    if gap_info:
        print(f"[规划·段{tag}] 因长素材总长不足，重复插入了 {len(gap_info)} 段补齐缺口")
    print(f"[规划·段{tag}] 每段截取 = {[round(c,2) for c in clips]}"
          f"  (对应素材时长 = {[round(d,2) for d in durations]})")

    scenes = []
    plan_detail = []
    for i, (mat, need, orig_dur) in enumerate(zip(mats, clips, durations)):
        sc = os.path.join(work, f"scene_{tag}_{i:03d}.mp4")
        extract_scene(mat, need, sc, w=OUT_W, h=OUT_H)
        scenes.append(sc)
        plan_detail.append({
            "material": os.path.basename(mat),
            "orig_dur": round(orig_dur, 2),
            "need": round(need, 2),
            "short": "✓ 原长" if need <= orig_dur + 1e-3 else "✗ 截短"
        })
    raw = os.path.join(work, f"raw_{tag}.mp4")
    transitions = _resolve_transitions(args.transition, len(scenes) - 1)
    concat_xfade(scenes, transitions=transitions, t=args.t_dur, out_path=raw)
    raw_dur = ffprobe_duration(raw)
    print(f"[拼接·段{tag}] raw 时长 = {raw_dur:.2f}s 转场 = {transitions}")
    # 保存规划详情供诊断
    with open(os.path.join(work, f"plan_seg_{tag}.json"), "w", encoding="utf-8") as f:
        json.dump(plan_detail, f, ensure_ascii=False, indent=2)
    if gap_info:
        print(f"[规划·段{tag}] 重复插入详情: {gap_info}")

    # 字幕：优先句级真实时长，否则全局比例回退
    spans = None
    if sent_durs:
        total = sum(sent_durs) or T
        scale = T / total if total else 1.0
        cum = 0.0
        spans = []
        for d in sent_durs:
            spans.append((cum * scale, (cum + d) * scale))
            cum += d
    ass = os.path.join(work, f"subs_{tag}.ass")
    build_ass(seg_text, spans, T, ass, max_chars=args.max_chars,
              width=OUT_W, height=OUT_H)
    print(f"[字幕·段{tag}] 已生成 (对齐={'句级真实时长' if spans else '全局比例回退'})")

    part = os.path.join(work, f"part_{tag}.mp4")
    burn_and_mux(raw, ass, vox, part)
    final = ffprobe_duration(part)
    print(f"[片段·段{tag}] {part}  时长 = {final:.2f}s (配音 {T:.2f}s，画面多 {final-T:.2f}s)")
    return part, final


# ---------- 主流程 ----------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--script", required=True, help="配音/字幕文本文件")
    ap.add_argument("--materials", required=True, help="素材文件夹")
    ap.add_argument("--ref", default=None,
                    help="本地克隆参考音频（仅 --backend local 时需要，可通过环境变量 QWEN_TTS_REF 设置默认值）")
    ap.add_argument("--backend", choices=["local", "edge"], default="edge",
                    help="配音引擎：edge=微软 edge-tts 在线（默认，无需本机模型，所有用户可用）；"
                         "local=本机 Qwen3-TTS 声音克隆（仅作者本机可选，需提前配置模型与 --ref）")
    ap.add_argument("--voice", default="zh-CN-YunxiNeural",
                    help="edge-tts 音色，如 zh-CN-YunxiNeural(男·温暖) / zh-CN-XiaoxiaoNeural(女·温柔) / "
                         "zh-CN-YunyangNeural(男·大气) / zh-CN-XiaoruiNeural(女·知性)")
    ap.add_argument("--output", required=True)
    ap.add_argument("--transition", default="mix",
                    help="转场效果：mix=内置多种交替；或填单个名(如 fade)；"
                         "或逗号列表(如 fade,slideleft,wipeleft)循环交替")
    ap.add_argument("--t-dur", type=float, default=0.5)
    ap.add_argument("--video-extra", type=float, default=3.0,
                    help="视频比配音多出的秒数（避免配音未完画面先停）")
    ap.add_argument("--video-min", type=float, default=30.0,
                    help="视频总时长下限（配音再短也不低于此值）")
    ap.add_argument("--language", default="Auto")
    ap.add_argument("--max-chars", type=int, default=22,
                    help="单行字幕最多字数，超出则拆成多行依次按配音出现")
    ap.add_argument("--ratio", default="auto",
                    help="视频比例：auto=自动检测素材（默认）；16:9=横屏；9:16=竖屏；或自定义如4:3")
    ap.add_argument("--mode", choices=["auto", "A", "B"], default="auto",
                    help="混剪模式：auto=按脚本是否含【n】标记自动判定；"
                         "A=一步混剪（所有素材放同一目录）；"
                         "B=分步混剪（每段素材放对应数字子目录，如 1/ 2/，按【n】分段逐段混剪后拼接）")
    ap.add_argument("--bgm", default=None,
                    help="背景音乐文件路径；指定后总合成时叠加在配音之下（原声保留）。"
                         "留空则不配 BGM")
    ap.add_argument("--bgm-gain", type=float, default=0.3,
                    help="BGM 相对配音的音量（默认 0.3，避免压过人声）")
    ap.add_argument("--intro-image", default=None,
                    help="片头图片路径；指定后以图片为背景生成片头视频")
    ap.add_argument("--intro-title", default=None,
                    help="片头标题文本（与 --intro-image 配合使用）")
    ap.add_argument("--intro-duration", type=float, default=5.0,
                    help="片头时长（默认5秒）")
    ap.add_argument("--outro-lines", default=None,
                    help="片尾文本，逗号分隔多行（默认：感谢驻足观看,内容仅供交流参考,我们下期再见）")
    ap.add_argument("--outro-duration", type=float, default=5.0,
                    help="片尾时长（默认5秒）")
    ap.add_argument("--intro-video", default=None,
                    help="用户提供的片头视频路径；指定后直接使用该视频作为片头，不再生成")
    ap.add_argument("--outro-video", default=None,
                    help="用户提供的片尾视频路径；指定后直接使用该视频作为片尾，不再生成默认片尾")
    args = ap.parse_args()

    work = os.path.join(os.path.dirname(os.path.abspath(__file__)), "work")
    os.makedirs(work, exist_ok=True)

    # 视频输出分辨率（按用户选择的比例）
    # 支持 auto 模式：自动检测素材比例
    if args.ratio == "auto":
        # 自动检测素材比例
        mats_for_check = list_materials(args.materials)[:5]  # 先检查前5个素材
        ratios = []
        for m in mats_for_check:
            if os.path.exists(m):
                try:
                    w, h, aspect = video_aspect(m)
                    ratios.append((aspect, w, h, m))
                except:
                    pass
        if ratios:
            # 统计横屏和竖屏数量
            horizontal = [r for r in ratios if r[0] > 1.2]  # 宽大于高
            vertical = [r for r in ratios if r[0] < 0.8]   # 高大于宽
            if len(horizontal) >= len(vertical):
                # 默认横屏
                final_ratio = "16:9"
                OUT_W, OUT_H = 1280, 720
            else:
                final_ratio = "9:16"
                OUT_W, OUT_H = 1080, 1920
            print(f"[比例] 自动检测：横屏{len(horizontal)}个，竖屏{len(vertical)}个 → 默认 {final_ratio}")
        else:
            # 检测失败，默认横屏
            final_ratio = "16:9"
            OUT_W, OUT_H = 1280, 720
            print("[比例] 无法检测素材，默认 16:9")
    elif args.ratio == "9:16":
        final_ratio = "9:16"
        OUT_W, OUT_H = 1080, 1920
    elif ":" in args.ratio:
        # 自定义比例，如 4:3
        final_ratio = args.ratio
        parts = args.ratio.split(":")
        if len(parts) == 2:
            try:
                rw, rh = int(parts[0]), int(parts[1])
                if rw > rh:
                    OUT_W, OUT_H = 1280, int(1280 * rh / rw)
                else:
                    OUT_W, OUT_H = int(1920 * rw / rh), 1920
                # 确保是偶数
                OUT_W = OUT_W - (OUT_W % 2)
                OUT_H = OUT_H - (OUT_H % 2)
            except:
                OUT_W, OUT_H = 1280, 720
        else:
            OUT_W, OUT_H = 1280, 720
    else:
        final_ratio = "16:9"
        OUT_W, OUT_H = 1280, 720

    print(f"[比例] 输出分辨率：{OUT_W}x{OUT_H} ({final_ratio})")
    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)

    # work 目录在主流程开始时就创建，B/A 模式共用
    work = os.path.join(os.path.dirname(os.path.abspath(__file__)), "work")
    os.makedirs(work, exist_ok=True)

    with open(args.script, encoding="utf-8") as f:
        text = f.read()

    # ---------- B 模式：分步混剪（按【n】标记逐段，再拼接） ----------
    seg_markers = re.findall(r"【(\d+)】", text)
    is_b = (args.mode == "B") or (args.mode == "auto" and bool(seg_markers))
    if is_b:
        if not seg_markers:
            raise SystemExit("B 模式需要脚本含【1】【2】…分段标记。")
        print(f"[B 模式] 检测到分段标记：{seg_markers}")
        parts = []
        # 逐段：按【n】切分正文（标记不进配音），素材目录取 args.materials/<n>
        chunks = re.split(r"【(\d+)】", text)
        pairs = []
        i = 1
        while i < len(chunks) - 1:
            pairs.append((int(chunks[i]), chunks[i + 1]))
            i += 2
        for num, body in pairs:
            body = body.strip()
            if not body:
                continue
            seg_dir = os.path.join(args.materials, str(num))
            if not os.path.isdir(seg_dir):
                raise SystemExit(f"B 模式缺少素材目录：{seg_dir}")
            part, _ = mix_segment(body, seg_dir, args, OUT_W, OUT_H, num)
            parts.append((num, part))
        parts.sort(key=lambda x: x[0])
        part_paths = [p for _, p in parts]
        print(f"[B 模式] 共 {len(part_paths)} 段，按序拼接：{part_paths}")
        # 总合成：纯拼接（原样接起，绝不重定时/绝不重新处理声音，
        # 确保每段内部已烧好的音画同步完整保留；段间为硬切，不做交叉溶解）
        # BGM 不在这里混入，留到 add_intro_outro 之后再统一混一次（覆盖片头+主视频+片尾）
        joined = os.path.join(work, "b_joined.mp4")
        join_segments_intact(part_paths, out_path=joined)
        final = ffprobe_duration(joined)
        print(f"[成片·主视频] {joined}  时长 = {final:.2f}s（含配音原声）")

        # B 模式完成，设置主视频变量，后续统一处理 BGM + 片头片尾
        main_video = joined
        print(f"[B 模式] 主视频拼接完成，时长 = {final:.2f}s")
    else:
        # ========== A 模式流程 ==========
        # 1. 配音（按脚本路径 + 引擎 + 音色 哈希缓存，避免跨目录同名或换音色/换引擎时误复用旧音频）
        script_key = hashlib.sha1(
            (os.path.abspath(args.script) + "|" + args.backend + "|" + args.voice).encode("utf-8")
        ).hexdigest()[:12]
        vox = os.path.join(work, f"voiceover_{script_key}.wav")
        vox_json = vox + ".json"
        if os.path.exists(vox):
            T = ffprobe_duration(vox)
            sent_durs = (json.load(open(vox_json, encoding="utf-8"))
                         if os.path.exists(vox_json) else None)
            print(f"[配音] 复用已有 {os.path.basename(vox)}  时长 T = {T:.2f}s")
        else:
            T, sent_durs = make_voiceover(text, args.backend, args.ref, vox, args.language, args.voice)
            with open(vox_json, "w", encoding="utf-8") as f:
                json.dump(sent_durs, f)
            print(f"[配音] 生成完毕  时长 T = {T:.2f}s")

        # 2. 素材（自身时长 < 5s 的直接丢弃，不循环）
        mats_all = list_materials(args.materials)
        mats, dropped_short = [], []
        for m in mats_all:
            d = video_duration(m)
            if d >= 5.0 - 1e-3:
                mats.append(m)
            else:
                dropped_short.append(f"{os.path.basename(m)}({d:.2f}s)")
        print(f"[规划] 素材总数 = {len(mats_all)}，保留 = {len(mats)}: "
              f"{[os.path.basename(m) for m in mats]}")
        if dropped_short:
            print(f"[规划] 因 <5s 丢弃: {dropped_short}")

        # 3. 反推每段时长
        # 视频目标时长 V = 配音 T + 额外缓冲（不再强制30秒最小值）
        # 由于 xfade 会把总时长缩短 (n-1)*t，要让成品恰好铺满 V（不冻结），
        # 各段计划时长之和需 = V + (n-1)*t + 缓冲(避免 fps 取整导致略短)。
        n = len(mats)
        V = T + args.video_extra
        buf = 0.5
        plan_target = V + (n - 1) * args.t_dur + buf

        # 先量取所有素材真实时长
        durations = [video_duration(m) for m in mats]
        # 新剪辑算法：不变速、不循环、按需补齐
        clips, gap_info = build_clip_plan(durations, plan_target)
        print(f"[规划] 配音 T = {T:.2f}s  视频目标 V = {V:.2f}s  素材数={n}  计划段数={len(clips)}")
        if gap_info:
            print(f"[规划] 因长素材总长不足，重复插入了 {len(gap_info)} 段补齐缺口")
        print(f"[规划] 每段截取 = {[round(c,2) for c in clips]}"
              f"  (对应素材时长 = {[round(d,2) for d in durations]})")

        # 4. 抽段
        scenes = []
        plan = []
        for i, (mat, need, orig_dur) in enumerate(zip(mats, clips, durations)):
            sc = os.path.join(work, f"scene_{i:03d}.mp4")
            extract_scene(mat, need, sc, w=OUT_W, h=OUT_H)
            dur = ffprobe_duration(sc)
            scenes.append(sc)
            plan.append({
                "material": os.path.basename(mat),
                "orig_dur": round(orig_dur, 2),
                "need": round(need, 2),
                "got": round(dur, 2),
                "short": "✓ 原长" if need <= orig_dur + 1e-3 else "✗ 截短"
            })
        print(f"[抽段] 完成 {len(scenes)} 段")

        # 5. 转场拼接
        raw = os.path.join(work, "raw.mp4")
        transitions = _resolve_transitions(args.transition, len(scenes) - 1)
        concat_xfade(scenes, transitions=transitions, t=args.t_dur, out_path=raw)
        raw_dur = ffprobe_duration(raw)
        print(f"[拼接] raw 时长 = {raw_dur:.2f}s (xfade 缩短约 {(len(scenes)-1)*args.t_dur:.2f}s)")
        print(f"[转场] 序列({len(transitions)}个) = {transitions}")

        # 6. 字幕：优先用每句真实配音时长做时间轴（逐句精确同步）
        spans = None
        if sent_durs:
            total = sum(sent_durs) or T
            scale = T / total if total else 1.0     # 把句级区间缩放到真实总时长 [0, T]
            cum = 0.0
            spans = []
            for d in sent_durs:
                spans.append((cum * scale, (cum + d) * scale))
                cum += d
        ass = os.path.join(work, "subs.ass")
        build_ass(text, spans, T, ass, max_chars=args.max_chars, width=OUT_W, height=OUT_H)
        print(f"[字幕] 已生成 {ass}  (对齐方式={'句级真实时长' if spans else '全局比例回退'})")

        # 7. 烧字幕 + 混音（视频比配音长，配音结束后画面继续播，不冻结）
        burn_and_mux(raw, ass, vox, args.output)
        final = ffprobe_duration(args.output)
        print(f"[成片] {args.output}  时长 = {final:.2f}s  (配音 {T:.2f}s，画面多 {(final-T):.2f}s)")

        with open(os.path.join(work, "plan.json"), "w", encoding="utf-8") as f:
            json.dump({"audio_T": round(T, 2), "video_V": round(final, 2),
                       "total_materials": len(mats_all),
                       "used": len(clips), "dropped_short": dropped_short,
                       "dropped_overflow": len(mats) - len(clips),
                       "transitions": transitions,
                       "clips": plan}, f, ensure_ascii=False, indent=2)
        print("[完成] 片段规划见 work/plan.json")

        # A 模式设置主视频变量
        main_video = args.output

    # ===== 步骤2: 混入BGM（在主视频上叠加背景音乐，配音原声保留） =====
    # 先加BGM，再加片头片尾——确保片头片尾拼接时主视频已有完整音轨（配音+BGM）
    main_video_with_bgm = main_video
    if args.bgm and main_video:
        bgmed = os.path.join(os.path.dirname(args.output),
                             os.path.splitext(os.path.basename(main_video))[0] + "_bgm.mp4")
        mix_bgm(main_video, args.bgm, bgmed, gain=args.bgm_gain)
        final = ffprobe_duration(bgmed)
        print(f"[成片·BGM] {bgmed}  时长 = {final:.2f}s"
              f"（配音原声已保留，BGM={os.path.basename(args.bgm)}）")
        main_video_with_bgm = bgmed

    # ===== 步骤3: 片头片尾包装（此时 main_video_with_bgm 含配音+BGM或仅配音） =====
    has_intro = args.intro_video and os.path.exists(args.intro_video)
    has_outro = args.outro_video and os.path.exists(args.outro_video)

    if has_intro or has_outro:
        intro_path = os.path.join(work, "intro.mp4")
        outro_path = os.path.join(work, "outro.mp4")

        # 根据主视频实际分辨率确定片头片尾比例
        if main_video_with_bgm and os.path.exists(main_video_with_bgm):
            mv_w, mv_h, _ = video_aspect(main_video_with_bgm)
            print(f"[片头片尾] 主视频比例: {mv_w}x{mv_h}")
        else:
            # 回退到参数中的比例设置
            mv_w, mv_h = (1080, 1920) if args.ratio == "9:16" else (1280, 720)
            print(f"[片头片尾] 使用参数比例: {mv_w}x{mv_h}")

        # 生成或使用片头
        if has_intro:
            import shutil
            shutil.copy2(args.intro_video, intro_path)
            print(f"[片头] 使用用户提供视频: {args.intro_video}")
        elif args.intro_image and os.path.exists(args.intro_image):
            # 自定义图片片头（配置文档第8项 B）：图片缩放模式
            # 仅给 --intro-image：纯图片缩放（title 留空）；同时给 --intro-title：图片背景+标题叠加
            generate_intro_video(
                title=args.intro_title or "",
                subtitle=None,
                image_path=args.intro_image,
                duration=args.intro_duration,
                w=mv_w, h=mv_h,
                out_path=intro_path
            )
            print(f"[片头] 已生成自定义图片片头: {mv_w}x{mv_h}")
        else:
            # 生成默认片头（带星空背景）
            generate_intro_video(
                title=args.intro_title or "视频内容",
                subtitle=None,
                image_path=None,
                duration=args.intro_duration,
                w=mv_w, h=mv_h,
                out_path=intro_path
            )
            print(f"[片头] 已生成星空背景片头: {mv_w}x{mv_h}")

        # 生成或使用片尾
        if has_outro:
            import shutil
            shutil.copy2(args.outro_video, outro_path)
            print(f"[片尾] 使用用户提供视频: {args.outro_video}")
        else:
            # 生成默认片尾（带星空背景）
            outro_lines = args.outro_lines.split(",") if args.outro_lines else None
            generate_outro_video(
                lines=outro_lines,
                duration=args.outro_duration,
                w=mv_w, h=mv_h,
                out_path=outro_path
            )
            print(f"[片尾] 已生成星空背景片尾: {mv_w}x{mv_h}")

        # 拼接片头+主视频(含BGM)+片尾
        final_output = os.path.join(os.path.dirname(args.output),
                                    os.path.splitext(os.path.basename(args.output))[0] + "_final.mp4")
        add_intro_outro(main_video_with_bgm, intro_path, outro_path, out_path=final_output,
                        intro_duration=args.intro_duration, outro_duration=args.outro_duration)
        print(f"[包装] 已添加片头片尾 → {final_output}")
    else:
        print("[包装] 未检测到 --intro-video 或 --outro-video 参数，跳过片头片尾")
        final_output = main_video_with_bgm

    final = ffprobe_duration(final_output)
    print(f"[成片] {final_output}  时长 = {final:.2f}s（含配音原声）")
    return final_output


# ---------- 8. 片头片尾生成 ----------
def generate_intro_video(title, subtitle=None, image_path=None, duration=5, w=1280, h=720, out_path=None):
    """生成片头视频：支持三种模式
    - 模式1（纯标题）：自适应字体大小 + 三次缩放效果（默认）
    - 模式2（纯图片）：图片从中心放大到铺满屏幕（title="" 且 image_path 提供）
    - 模式3（标题+图片）：图片为背景 + 标题文字叠加（默认行为）
    """
    if out_path is None:
        out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "work", "intro.mp4")

    # 判断模式
    if title == "" and image_path:
        mode = "image_zoom"  # 纯图片缩放模式
    elif title:
        mode = "title"  # 标题模式
    else:
        mode = "title"  # 默认标题模式

    if mode == "image_zoom":
        return _make_image_zoom_intro(image_path, duration, w, h, out_path)
    else:
        return _make_title_intro(title, subtitle, image_path, duration, w, h, out_path)


def _make_title_intro(title_text, subtitle_text=None, image_path=None, duration=5, w=1280, h=720, out_path=None):
    """标题模式：自适应字体大小 + 三次缩放效果（可选图片背景+星空）"""
    from PIL import Image, ImageDraw, ImageFont
    import shutil
    import random
    import math

    fps = 30
    total_frames = int(duration * fps)

    frame_dir = os.path.join(tempfile.gettempdir(), "intro_frames")
    if os.path.exists(frame_dir):
        shutil.rmtree(frame_dir)
    os.makedirs(frame_dir)

    try:
        # 加载或创建背景图
        if image_path and os.path.exists(image_path):
            bg = Image.open(image_path).convert("RGB")
            bg_w, bg_h = bg.size
            scale = max(w / bg_w, h / bg_h)
            new_size = (int(bg_w * scale), int(bg_h * scale))
            bg = bg.resize(new_size, Image.LANCZOS)
        else:
            bg = Image.new("RGB", (w, h), color=(10, 10, 30))

        # 预先生成星空点
        random.seed(42)
        stars = []
        for _ in range(200):
            x = random.randint(0, w - 1)
            y = random.randint(0, h - 1)
            size = random.randint(1, 3)
            brightness = random.randint(150, 255)
            flicker_period = random.randint(3, 8)
            flicker_offset = random.randint(0, flicker_period - 1)
            stars.append((x, y, size, brightness, flicker_period, flicker_offset))

        # 加载字体
        try:
            font_base = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", round(w / 1280 * 72))
        except Exception:
            font_base = ImageFont.load_default()

        # 自适应计算标题字体大小
        def calc_adaptive_font(text, max_width, base_font):
            if not text:
                return base_font
            max_width = int(max_width)
            temp_canvas = Image.new("RGBA", (max_width, 100), (0, 0, 0, 0))
            temp_draw = ImageDraw.Draw(temp_canvas)
            low, high = 20, base_font.size
            best_font_size = base_font.size
            while low <= high:
                mid = (low + high) // 2
                try:
                    test_font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", mid)
                except Exception:
                    break
                bbox = temp_draw.textbbox((0, 0), text, font=test_font)
                text_w = bbox[2] - bbox[0]
                if text_w <= max_width:
                    best_font_size = mid
                    low = mid + 1
                else:
                    high = mid - 1
            try:
                return ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", best_font_size)
            except Exception:
                return base_font

        margin_w = w * 0.1
        adaptive_font = calc_adaptive_font(title_text, w - 2 * margin_w, font_base)

        for i in range(total_frames):
            current_time = i / fps
            frame = bg.copy()

            # 绘制闪烁星星
            star_draw = ImageDraw.Draw(frame)
            for sx, sy, ssize, sbright, sflicker_period, sflicker_offset in stars:
                flicker_phase = ((i + sflicker_offset) % sflicker_period) / sflicker_period
                flicker_alpha = int(128 + 127 * math.sin(2 * math.pi * flicker_phase))
                star_color = (min(255, sbright + flicker_alpha // 2),
                              min(255, sbright + flicker_alpha // 2),
                              min(255, sbright + flicker_alpha))
                star_draw.ellipse([sx - ssize, sy - ssize, sx + ssize, sy + ssize], fill=star_color)

            # 绘制标题
            draw = ImageDraw.Draw(frame)
            title_dur = max(duration - 1.0, 2.0)
            fade_in_dur = 0.5
            fade_out_dur = 1.0
            zoom_cycles = 3

            if current_time <= title_dur:
                if current_time < fade_in_dur:
                    alpha = int(255 * (current_time / fade_in_dur))
                elif current_time > (title_dur - fade_out_dur):
                    alpha = int(255 * ((title_dur - current_time) / fade_out_dur))
                else:
                    alpha = 255

                cycle_dur = title_dur / zoom_cycles
                cycle_pos = (current_time % cycle_dur) / cycle_dur
                zoom_scale = 1.0 - 0.3 * math.cos(2 * math.pi * cycle_pos)

                bbox = draw.textbbox((0, 0), title_text, font=adaptive_font)
                text_w = bbox[2] - bbox[0]
                text_h = bbox[3] - bbox[1]

                scaled_text_w = int(text_w * zoom_scale)
                scaled_text_h = int(text_h * zoom_scale)
                tx = (w - scaled_text_w) // 2
                ty = (h - scaled_text_h) // 2

                padding = int(text_h * 0.2)
                temp_w = scaled_text_w + 2 * padding
                temp_h = scaled_text_h + 2 * padding
                temp_img = Image.new("RGBA", (temp_w, temp_h), (0, 0, 0, 0))
                temp_draw = ImageDraw.Draw(temp_img)
                scale_font = round(adaptive_font.size * zoom_scale)
                try:
                    scaled_font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", scale_font)
                except Exception:
                    scaled_font = adaptive_font
                stroke_offset = max(2, int(3 * zoom_scale))
                for dx in range(-stroke_offset, stroke_offset + 1):
                    for dy in range(-stroke_offset, stroke_offset + 1):
                        if dx != 0 or dy != 0:
                            temp_draw.text((padding + dx, padding + dy), title_text,
                                           fill=(0, 0, 0, alpha), font=scaled_font)
                temp_draw.text((padding, padding), title_text, fill=(255, 255, 255, alpha), font=scaled_font)
                paste_x = tx - padding
                paste_y = ty - padding
                frame.paste(temp_img, (paste_x, paste_y), temp_img)

            frame_rgba = frame.convert("RGBA")
            frame_rgb = frame_rgba.convert("RGB")
            frame_rgb.save(os.path.join(frame_dir, f"frame_{i:04d}.png"), quality=95)

        cmd = [
            "ffmpeg", "-y", "-framerate", str(fps),
            "-i", os.path.join(frame_dir, "frame_%04d.png"),
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "medium",
            "-movflags", "+faststart", "-an", out_path
        ]
        run(cmd)
        print(f"[片头] 已生成 {out_path}  时长={duration}s  帧数={total_frames}")
    finally:
        if os.path.exists(frame_dir):
            shutil.rmtree(frame_dir)

    return out_path


def _make_image_zoom_intro(image_path, duration=5, w=1280, h=720, out_path=None):
    """纯图片缩放模式：图片从中心放大到铺满屏幕"""
    from PIL import Image, ImageDraw
    import shutil
    import math

    fps = 30
    total_frames = int(duration * fps)

    frame_dir = os.path.join(tempfile.gettempdir(), "intro_frames")
    if os.path.exists(frame_dir):
        shutil.rmtree(frame_dir)
    os.makedirs(frame_dir)

    try:
        # 加载图片
        img = Image.open(image_path).convert("RGB")
        img_w, img_h = img.size

        # 计算覆盖比例
        cover_scale = max(w / img_w, h / img_h)
        bg = img.resize((int(img_w * cover_scale), int(img_h * cover_scale)), Image.LANCZOS)

        for i in range(total_frames):
            current_time = i / fps
            progress = current_time / duration  # 0→1

            # 从 1.0x 放大到铺满（实际需要从较小比例开始）
            # 初始比例：让图片中心可见，四周有边距
            start_scale = 0.6  # 起始缩小比例
            zoom = start_scale + (1.0 - start_scale) * progress  # 0.6 → 1.0

            # 放大图片
            new_w = int(bg.width * zoom)
            new_h = int(bg.height * zoom)
            frame = bg.resize((new_w, new_h), Image.LANCZOS)

            # 裁切到目标尺寸（从中心裁切）
            left = (new_w - w) // 2
            top = (new_h - h) // 2
            frame = frame.crop((left, top, left + w, top + h))

            frame.save(os.path.join(frame_dir, f"frame_{i:04d}.png"), quality=95)

        cmd = [
            "ffmpeg", "-y", "-framerate", str(fps),
            "-i", os.path.join(frame_dir, "frame_%04d.png"),
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "medium",
            "-movflags", "+faststart", "-an", out_path
        ]
        run(cmd)
        print(f"[片头] 已生成 {out_path}  时长={duration}s  模式=图片缩放")
    finally:
        if os.path.exists(frame_dir):
            shutil.rmtree(frame_dir)

def generate_outro_video(lines=None, duration=5, w=1280, h=720, out_path=None):
    """生成片尾视频：动态文本显示，默认内容为感谢语。
    lines: 多行文本列表，每行一个元素
    - 字体放大1倍（fontsize = w/1280*96）
    - 第一行飞出右侧，第二行从左侧飞入（第三行静止居中）
    - 所有文字居中排列
    """
    if out_path is None:
        out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "work", "outro.mp4")

    if lines is None:
        lines = ["感谢驻足观看", "内容仅供交流参考", "我们下期再见"]

    # 生成 ASS 字幕（居中大字体 + 飞入飞出动效）
    ass_path = os.path.join(tempfile.gettempdir(), "outro_sub.ass")
    fontsize = round(w / 1280 * 96)  # 字体放大1倍
    line_height = fontsize + 24
    total_height = len(lines) * line_height
    start_y = (h - total_height) // 2

    with open(ass_path, "w", encoding="utf-8") as f:
        f.write(f"""[Script Info]
Title: outro
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Microsoft YaHei,{fontsize},&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,4,0,2,20,20,40,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
""")
        # 整体时间安排：duration 秒内，每行间隔 per_line
        per_line = duration / len(lines)
        for i, line in enumerate(lines):
            # 去掉文字中的逗号
            clean_line = line.replace("，", "").replace(",", "")
            start_sec = i * per_line
            end_sec = (i + 1) * per_line
            margin_v = start_y + i * line_height

            if i == 0:
                # 第一行：居中显示
                f.write(f"Dialogue: 0,{_ass_time(start_sec)},{_ass_time(end_sec)},Default,,0,0,{margin_v},,{_ass_escape(clean_line)}\n")
            elif i == 1:
                # 第二行：居中显示
                f.write(f"Dialogue: 0,{_ass_time(start_sec)},{_ass_time(end_sec)},Default,,0,0,{margin_v},,{_ass_escape(clean_line)}\n")
            else:
                # 后续行：静止居中显示
                f.write(f"Dialogue: 0,{_ass_time(start_sec)},{_ass_time(end_sec)},Default,,0,0,{margin_v},,{_ass_escape(clean_line)}\n")

    # 生成带星光闪烁的背景视频（使用Pillow逐帧生成）
    from PIL import Image, ImageDraw
    import random
    import math

    # 预先生成星空点
    random.seed(123)  # 固定种子保证一致性
    stars = []
    for _ in range(200):  # 200颗星星
        x = random.randint(0, w - 1)
        y = random.randint(0, h - 1)
        size = random.randint(1, 3)
        brightness = random.randint(150, 255)
        flicker_period = random.randint(3, 8)
        flicker_offset = random.randint(0, flicker_period - 1)
        stars.append((x, y, size, brightness, flicker_period, flicker_offset))

    # 生成帧序列
    frame_dir = os.path.join(tempfile.gettempdir(), "outro_frames")
    if os.path.exists(frame_dir):
        import shutil
        shutil.rmtree(frame_dir)
    os.makedirs(frame_dir)

    fps = 30
    total_frames = int(duration * fps)

    for i in range(total_frames):
        # 创建深蓝色背景
        frame_img = Image.new("RGB", (w, h), color=(10, 10, 30))
        draw = ImageDraw.Draw(frame_img)

        # 绘制闪烁的星星
        for sx, sy, ssize, sbright, sflicker_period, sflicker_offset in stars:
            flicker_phase = ((i + sflicker_offset) % sflicker_period) / sflicker_period
            flicker_alpha = int(128 + 127 * math.sin(2 * math.pi * flicker_phase))
            star_color = (min(255, sbright + flicker_alpha // 2),
                          min(255, sbright + flicker_alpha // 2),
                          min(255, sbright + flicker_alpha))
            draw.ellipse([sx - ssize, sy - ssize, sx + ssize, sy + ssize],
                        fill=star_color)

        # 保存帧
        frame_path = os.path.join(frame_dir, f"frame_{i:04d}.png")
        frame_img.save(frame_path)

    # 使用ffmpeg将帧序列编码为视频
    run(["ffmpeg", "-y", "-framerate", str(fps),
         "-i", os.path.join(frame_dir, "frame_%04d.png"),
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "medium",
         "-t", f"{duration:.3f}", "-an",
         os.path.join(tempfile.gettempdir(), "outro_bg.mp4")])

    # 清理帧目录
    import shutil
    shutil.rmtree(frame_dir)

    # 烧录字幕（相对路径，避免路径转义问题）
    old_cwd = os.getcwd()
    os.chdir(tempfile.gettempdir())
    try:
        run(["ffmpeg", "-y", "-i", "outro_bg.mp4",
             "-vf", "subtitles=outro_sub.ass", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "medium",
             "-an", out_path])
    finally:
        os.chdir(old_cwd)

    print(f"[片尾] 已生成 {out_path}  时长={duration}s")
    return out_path


def add_intro_outro(video, intro_path=None, outro_path=None, out_path=None,
                    intro_duration=5.0, outro_duration=5.0):
    """在成片前后拼接片头片尾。

    关键约束：
    1. 纯 stream-copy 拼接，绝不重编码主视频
    2. 主视频的音频轨原样保留（单声道/立体声、采样率等）
    3. 片头/片尾需补静音轨，且格式必须与主视频匹配
    """
    if out_path is None:
        out_path = video

    tmpdir = tempfile.gettempdir()

    def _get_audio_info(path):
        """获取视频的音频格式信息（采样率、声道数）。"""
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "stream=sample_rate,channels,codec_name",
             "-of", "json", path],
            capture_output=True, text=True, check=True,
        )
        data = json.loads(probe.stdout)
        streams = data.get("streams", [])
        for s in streams:
            # 根据 codec_name 判断类型（ffprobe -show_entries 不输出 codec_type）
            if s.get("codec_name") in ("aac", "mp3", "flac", "opus", "vorbis", "pcm_s16le"):
                return int(s.get("sample_rate", 44100)), int(s.get("channels", 2))
        return 44100, 2  # 默认立体声 44.1kHz

    def _ensure_audio(video_path, duration, target_sr=44100, target_ch=2):
        """为无音频轨的视频补静音；返回（路径，临时文件列表）。"""
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type",
             "-of", "csv=p=0", video_path],
            capture_output=True, text=True, check=True,
        )
        if "audio" in probe.stdout:
            return video_path, []
        # 生成与主视频格式匹配的静音轨
        ch_str = "mono" if target_ch == 1 else "stereo"
        sil_wav = os.path.join(tmpdir, f"_sil_{hash(video_path) % 10000}.wav")
        run(["ffmpeg", "-y", "-f", "lavfi", "-i",
             f"anullsrc=r={target_sr}:cl={ch_str}",
             "-t", f"{duration:.3f}", sil_wav])
        out = os.path.join(tmpdir, os.path.basename(video_path))
        run(["ffmpeg", "-y", "-i", video_path, "-i", sil_wav,
             "-c:v", "copy", "-c:a", "aac", "-map", "0:v:0", "-map", "1:a:0",
             "-shortest", out])
        return out, [sil_wav]

    # 先检测主视频的音频格式
    main_sr, main_ch = _get_audio_info(video)
    print(f"[包装] 主视频音频: 采样率={main_sr}Hz, 声道={main_ch}")

    # 为片头/片尾补静音（格式与主视频匹配）
    clean_up = []
    parts = []
    if intro_path and os.path.exists(intro_path):
        int_pack, sils = _ensure_audio(intro_path, intro_duration, main_sr, main_ch)
        parts.append(int_pack)
        clean_up.extend(sils)
    parts.append(video)
    if outro_path and os.path.exists(outro_path):
        out_pack, sils = _ensure_audio(outro_path, outro_duration, main_sr, main_ch)
        parts.append(out_pack)
        clean_up.extend(sils)

    if len(parts) == 1:
        return video

    join_segments_intact(parts, out_path=out_path)
    final = ffprobe_duration(out_path)
    dur0 = ffprobe_duration(parts[0]) if parts else 0
    dur_m1 = ffprobe_duration(parts[-1]) if parts else 0
    print(f"[包装] 最终成片 {out_path}  总时长={final:.2f}s"
          f"（含片头{dur0:.1f}s、片尾{dur_m1:.1f}s）")

    # 清理临时文件
    for p in clean_up:
        try:
            os.remove(p)
        except OSError:
            pass
    return out_path

if __name__ == "__main__":
    main()
