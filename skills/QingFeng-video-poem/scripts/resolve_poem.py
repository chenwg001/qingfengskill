#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
按诗名检索古诗，输出流水线可直接消费的标准化 JSON（script.json）。

用法：
    python resolve_poem.py --name "静夜思" --out workdir/script.json
    python resolve_poem.py --name "静夜思" --author "李白"     # 同名消歧
    python resolve_poem.py --name "早发白帝城" --user-db workdir/poems_user.json --out workdir/script.json
    python resolve_poem.py --list                             # 列出技能自带库全部诗名

检索策略：先精确匹配标题；再「互为包含」模糊匹配（去掉空格与常见标点后比较）；
未命中则列出可用诗库已有诗名，提示可联网补全或补录缓存库。

两级诗库（合并查询）：
    - 技能自带库（DEFAULT_DB = scripts/poems.json，只读，运行期绝不修改）
    - 工作目录缓存库（--user-db 指定，如 workdir/poems_user.json；由助手联网检索/用户粘贴后补录）

写入缓存库：
    python resolve_poem.py --append --user-db workdir/poems_user.json \
        --entry '{"title":"...","author":"...","dynasty":"...","lines":["..."],"mood":"serene","style":"ink","imagery":["..."],"scene_desc":"..."}'
    （同名同作者则更新，否则新增；文件不存在自动创建。绝不写技能自带库。）

输出字段（script.json，同时兼容 poem.json 顶层字段）：
    found / title / author / dynasty / title_line（供 TTS 播报）
    lines（分句数组）/ mood（BGM 情绪）/ style（推荐画风）
    imagery（画面意象关键词）/ scene_desc（意境一句话）
    n_scenes（推荐镜头数 = 句数 + 1 封面镜）
"""

import argparse
import json
import os
import sys

if sys.platform == "win32":
    sys.stdout = __import__("io").TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = __import__("io").TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DB = os.path.join(SCRIPT_DIR, "poems.json")

_PUNCT = " ，。、·：:；;，,.!！?？（）()《》<>「」“”\"'"


def normalize(s: str) -> str:
    s = (s or "").strip().lower()
    for ch in _PUNCT:
        s = s.replace(ch, "")
    return s


def load_db(path: str):
    if not path or not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def find(name: str, author: str, db: dict):
    """在单个诗库内查找；返回 poem dict、或 {'__ambiguous__': [...]}、或 None。"""
    if db is None:
        return None
    poems = db.get("poems", [])
    nq = normalize(name)
    aq = normalize(author) if author else ""

    # 1) 精确标题
    for p in poems:
        if normalize(p["title"]) == nq and (not aq or normalize(p.get("author", "")) == aq):
            return p
    # 2) 查询词包含于标题 或 标题包含于查询词
    cands = []
    for p in poems:
        pt = normalize(p["title"])
        if nq and (nq in pt or pt in nq):
            if not aq or normalize(p.get("author", "")) == aq:
                cands.append(p)
    if len(cands) == 1:
        return cands[0]
    if len(cands) > 1:
        return {"__ambiguous__": cands}
    return None


def build_result(p: dict) -> dict:
    lines = p["lines"]
    return {
        "found": True,
        "title": p.get("title", ""),
        "author": p.get("author", ""),
        "dynasty": p.get("dynasty", ""),
        "title_line": f"{p.get('title', '')} {p.get('dynasty', '')} {p.get('author', '')}".strip(),
        "lines": lines,
        "mood": p.get("mood", "serene"),
        "style": p.get("style", "ink"),
        "imagery": p.get("imagery", []),
        "scene_desc": p.get("scene_desc", ""),
        "n_scenes": len(lines) + 1,   # 含 1 个封面镜
    }


def append_entry(user_db: str, entry: dict):
    """把条目写入工作目录缓存库；同名同作者更新，否则新增。返回 ('updated'|'added', path)。"""
    db = load_db(user_db)
    if db is None:
        db = {
            "_meta": {
                "version": "1.0",
                "description": "用户工作目录诗库缓存（由 QingFeng-video-poem 运行期自动累积，不写入技能自带库）",
                "coverage": "运行期由助手联网检索 / 用户粘贴后补录，跨项目不共享",
            },
            "poems": [],
        }
    poems = db.setdefault("poems", [])
    nq = normalize(entry.get("title", ""))
    aq = normalize(entry.get("author", ""))
    for i, p in enumerate(poems):
        if normalize(p.get("title", "")) == nq and (not aq or normalize(p.get("author", "")) == aq):
            poems[i] = entry
            _save(user_db, db)
            return "updated", user_db
    poems.append(entry)
    _save(user_db, db)
    return "added", user_db


def _save(path: str, db: dict):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)


def main():
    ap = argparse.ArgumentParser(description="按诗名检索古诗（技能库 + 工作目录缓存库合并）")
    ap.add_argument("--name", help="诗名（可含作者，如「静夜思 李白」）")
    ap.add_argument("--author", help="作者，用于同名消歧（可选）")
    ap.add_argument("--db", default=DEFAULT_DB, help="技能自带诗库 JSON 路径（默认 scripts/poems.json，只读）")
    ap.add_argument("--user-db", default=None, help="工作目录缓存库 JSON；查询时与技能库合并，写入时存这里（不污染技能库）")
    ap.add_argument("--out", default=None, help="输出 JSON 路径；缺省打印到 stdout")
    ap.add_argument("--list", action="store_true", help="列出技能自带库全部诗名")
    ap.add_argument("--append", action="store_true", help="写入模式：把 --entry 指定的条目写入 --user-db（自动创建/更新）")
    ap.add_argument("--entry", default=None, help="--append 模式下的新条目 JSON 字符串（含 title/author/dynasty/lines/mood/style/imagery/scene_desc）")
    args = ap.parse_args()

    # ---- 写入缓存库模式 ----
    if args.append:
        if not args.user_db:
            sys.exit("--append 需要 --user-db 指定缓存库路径")
        if not args.entry:
            sys.exit("--append 需要 --entry 指定条目 JSON")
        try:
            entry = json.loads(args.entry)
        except Exception as e:
            sys.exit(f"--entry 不是合法 JSON: {e}")
        for k in ("title", "lines"):
            if k not in entry:
                sys.exit(f"--entry 缺少必填字段: {k}")
        if not isinstance(entry["lines"], list) or not entry["lines"]:
            sys.exit("--entry 的 lines 必须是非空数组")
        status, path = append_entry(args.user_db, entry)
        print(f"已写入缓存库（{status}）: {entry.get('title')} -> {path}")
        return

    if not os.path.exists(args.db):
        sys.exit(f"技能诗库不存在: {args.db}")
    skill_db = load_db(args.db)
    user_db = load_db(args.user_db) if args.user_db else None

    if args.list:
        titles = [f"{p['title']}（{p.get('dynasty','')}·{p.get('author','')}）" for p in skill_db.get("poems", [])]
        print("\n".join(titles))
        return

    if not args.name:
        sys.exit("请提供 --name 诗名，或 --list 查看本地库")

    # 允许 name 中带作者，如「静夜思 李白」
    name = args.name
    author = args.author
    if not author and " " in name:
        parts = name.split(None, 1)
        name, author = parts[0], parts[1]

    # 先查技能库，未命中再查缓存库
    hit = find(name, author, skill_db)
    src = "技能库"
    if hit is None and user_db is not None:
        hit = find(name, author, user_db)
        src = "缓存库"

    if isinstance(hit, dict) and "__ambiguous__" in hit:
        cands = hit["__ambiguous__"]
        print(f"诗名「{name}」命中多首，请用 --author 指定作者消歧：", file=sys.stderr)
        for c in cands:
            print(f"  - {c['title']}（{c.get('dynasty','')}·{c.get('author','')}）", file=sys.stderr)
        sys.exit(2)

    if hit is None:
        avail = [p["title"] for p in skill_db.get("poems", [])]
        print(f"未找到「{name}」。技能库共 {len(avail)} 首"
              + (f"，缓存库另有 {len(user_db.get('poems', []))} 首" if user_db else "")
              + "。可尝试：", file=sys.stderr)
        for t in avail:
            print(f"  - {t}", file=sys.stderr)
        print("提示：若确需此诗，可由助手联网检索全文后，用 --append --user-db 写入工作目录缓存库（不写技能库）。", file=sys.stderr)
        sys.exit(3)

    result = build_result(hit)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"已解析（{src}）: {result['title']} · {result['dynasty']} {result['author']} "
              f"（{len(result['lines'])}句，建议 {result['n_scenes']} 镜）")
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
