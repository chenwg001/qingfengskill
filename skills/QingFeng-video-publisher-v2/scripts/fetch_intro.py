#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_intro.py —— 视频发布「获取简介」环节·源文本提取器（确定性部分）

在【视频所在文件夹】内查找相关文档（.txt / .md / .docx），提取其中的介绍文本，
供后续 LLM（Agent 自身）归纳成「符合平台要求、又能吸引用户」的简介。

设计要点：
- 只搜视频同文件夹，不递归上层目录
- 查找优先级：
    ① 与视频【同名】的文档（第30期.mp4 → 第30期.txt / .md / .docx）
    ② 文件名【含视频名】的文档
    ③ 文件夹内任意文档（多份则全部拼入，由 Agent 判断哪段是介绍）
- **汇总类文稿小节抽取（2026-09-02 增强）**：当命中文档是"多期汇总"型
  （如《白话诗说-30期文稿汇总.md》，内含 `## 第6期《单恋知多少》` 这种分节），
  脚本会自动按视频文件名里的【期号】定位对应小节，只抽取本集文本
  （从 `## 第N期` 标题截到下一个同级或更高级标题为止），避免把整本文稿灌进上下文。
  - 期号识别：文件名 `第6期-单恋知多少.mp4` → 第 6 期
  - 命中优先取「同时含期号与集名」的小节标题（如 `第6期《单恋知多少》`），更精准
- .docx 用 zipfile 直接读 word/document.xml 提取，无需 python-docx
- 找到：打印提取文本（stderr 打印命中说明 + 平台字数提示）
- 未找到：打印 `__NO_INTRO_FOUND__`（Agent 据此把简介留空）

注意：本脚本只做「提取」，不做「归纳/改写」——归纳成平台简介由 Agent 的 LLM 完成。
"""

import os
import sys
import argparse
import zipfile
import re

DOC_EXTS = [".txt", ".md", ".docx"]
MAX_CHARS = 16000  # 提取文本上限，避免一次性灌爆上下文


def extract_docx_text(path):
    """用 zipfile 直接读 docx 内的 word/document.xml，提取段落文本（无需 python-docx）。"""
    try:
        with zipfile.ZipFile(path) as z:
            xml = z.read("word/document.xml").decode("utf-8", "ignore")
        # 按段落 </w:p> 切分，每段内提取所有 <w:t> 文本
        paras = re.split(r"</w:p>", xml)
        out = []
        for p in paras:
            ts = re.findall(r"<w:t[^>]*>(.*?)</w:t>", p, re.S)
            text = "".join(ts)
            # 还原常见转义
            text = (text.replace("&amp;", "&")
                        .replace("&lt;", "<")
                        .replace("&gt;", ">")
                        .replace("&quot;", '"')
                        .replace("&apos;", "'"))
            if text.strip():
                out.append(text.strip())
        return "\n".join(out)
    except Exception as e:
        return f"[docx 提取失败: {e}]"


def extract_text(path):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".docx":
        return extract_docx_text(path)
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    except Exception as e:
        return f"[读取失败: {e}]"


def get_episode_no(video):
    """从视频文件名提取期号，如 '第6期-单恋知多少.mp4' → 6；无则 None。"""
    m = re.search(r"(?:第\s*)?(\d+)\s*期", os.path.basename(video))
    return int(m.group(1)) if m else None


def get_name_hint(video):
    """从视频文件名提取集名提示，如 '第6期-单恋知多少.mp4' → '单恋知多少'；无则 ''。"""
    m = re.search(r"期[\-_\s]*(.+)$", os.path.splitext(os.path.basename(video))[0])
    return m.group(1).strip() if m else ""


def extract_episode_section(text, ep_no, name_hint=""):
    """
    从文稿中按【期号】抽取对应小节。
    定位 `## 第N期` / `# N期` 这类标题行，截取到下一个同级或更高级标题为止。
    优先选同时含 name_hint 的标题（更精准）。找不到返回 None。
    """
    if ep_no is None:
        return None
    lines = text.splitlines()
    # 候选标题行：任意级别标题，含「第N期」或「N期」
    cand = []
    for i, l in enumerate(lines):
        if re.match(r"^#{1,6}\s+", l) and (f"第{ep_no}期" in l or f"{ep_no}期" in l):
            cand.append((i, l))
    if not cand:
        return None
    # 优先选同时含集名的标题
    idx = cand[0][0]
    if name_hint:
        for i, l in cand:
            if name_hint in l:
                idx = i
                break
    start_level = len(re.match(r"^(#+) ", lines[idx]).group(1))
    end = len(lines)
    for j in range(idx + 1, len(lines)):
        m = re.match(r"^(#+) ", lines[j])
        if m and len(m.group(1)) <= start_level:
            end = j
            break
    sec = "\n".join(lines[idx:end]).strip()
    return sec or None


def find_docs(video):
    """返回 (chosen_paths, why) 。chosen_paths 为空表示没找到。"""
    d = os.path.dirname(os.path.abspath(video))
    stem = os.path.splitext(os.path.basename(video))[0]

    all_docs = []
    for fn in os.listdir(d):
        ext = os.path.splitext(fn)[1].lower()
        if ext in DOC_EXTS:
            all_docs.append(os.path.join(d, fn))
    if not all_docs:
        return [], "视频文件夹内无任何 .txt/.md/.docx 文档"

    # ① 同名文档
    same_stem = [p for p in all_docs
                 if os.path.splitext(os.path.basename(p))[0] == stem]
    if same_stem:
        return same_stem, f"与视频同名文档: {[os.path.basename(p) for p in same_stem]}"

    # ② 文件名含视频名（大小写不敏感）
    contains = [p for p in all_docs
                if stem.lower() in os.path.splitext(os.path.basename(p))[0].lower()]
    if contains:
        return contains, f"文件名含视频名的文档: {[os.path.basename(p) for p in contains]}"

    # ③ 兜底：文件夹内任意文档
    return all_docs, f"未找到同名/含名文档，使用文件夹内全部文档: {[os.path.basename(p) for p in all_docs]}"


def platform_hint(platform):
    if platform == "bilibili":
        return "B站简介 ≤ 2000 字，可含 #话题（压末尾，必带 #教育 等）"
    if platform == "xiaohongshu":
        return "小红书正文 ≤ 1000 字，话题在正文内用 #词 触发（不在简介堆 #）"
    if platform == "douyin":
        return "抖音简介 ≤ 500 字，末尾带 #话题（如 #教育 #国风 #诗词）更利于推荐"
    return "B站简介 ≤ 2000 字（可带 #话题）；抖音/小红书正文惯例末尾带 #话题"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True, help="视频文件路径")
    ap.add_argument("--platform", default="", help="bilibili | xiaohongshu | douyin（仅用于字数提示）")
    args = ap.parse_args()

    if not os.path.exists(args.video):
        print("__NO_INTRO_FOUND__")
        print(f"[WARN] 视频文件不存在: {args.video}", file=sys.stderr)
        return

    docs, why = find_docs(args.video)
    if not docs:
        print("__NO_INTRO_FOUND__")
        print(f"[INFO] {why} —— 简介留空", file=sys.stderr)
        return

    ep_no = get_episode_no(args.video)
    name_hint = get_name_hint(args.video)

    # 优先尝试「汇总类文稿小节抽取」
    sections = []
    if ep_no is not None:
        for p in docs:
            sec = extract_episode_section(extract_text(p), ep_no, name_hint)
            if sec:
                sections.append(
                    f"===== {os.path.basename(p)}（第{ep_no}期《{name_hint or '?'}》小节）=====\n" + sec
                )
        if sections:
            why += f"；已按第{ep_no}期从小节抽取（命中集名: {name_hint or '无'}）"
            text = "\n\n".join(sections)
        else:
            # 兜底：整本文档（单集文档或非汇总型）
            parts = [f"===== {os.path.basename(p)} =====\n" + extract_text(p) for p in docs]
            text = "\n\n".join(parts)
    else:
        parts = [f"===== {os.path.basename(p)} =====\n" + extract_text(p) for p in docs]
        text = "\n\n".join(parts)

    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS] + "\n\n[……已截断至 %d 字，更长部分由 Agent 按需续读]" % MAX_CHARS

    print(f"[INFO] 命中: {why}", file=sys.stderr)
    print(f"[INFO] 平台字数提示: {platform_hint(args.platform)}", file=sys.stderr)
    print(text)


if __name__ == "__main__":
    main()
