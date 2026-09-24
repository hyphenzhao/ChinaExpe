"""Build data/classics: a reading room of whole books for an AI session.

knowledge_base/literature holds the imported texts split into ~2 KB chunks with
YAML front matter, which is right for retrieval and wrong for reading.  This
script stitches each book back together, copies the untouched originals when
they exist, and writes an index that says what is here and what is missing.

    python scripts/build_classics.py [--source <OpenClaw-Space dir>]

Safe to re-run: the output directory is rebuilt from scratch.
"""
from __future__ import annotations

import argparse
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LITERATURE = ROOT / "knowledge_base" / "literature"
KB = ROOT / "knowledge_base"
OUT = ROOT / "data" / "classics"

# literature folder -> (category folder, one-line note)
BOOKS = {
    "紫微斗数全书": ("01-紫微-三合派", "明代传本，紫微斗数的根本典籍，三合派与各派共同源头"),
    "紫微斗数续道藏本": ("01-紫微-三合派", "道藏续本，星曜与格局的古本对照"),
    "梁若瑜飞星问答": ("02-紫微-四化飞星派", "梁若瑜飞星紫微斗数网络问答文集，四化/飞星派实务"),
    "渊海子平": ("03-子平", "子平法的奠基之作"),
    "子平读书笔记": ("05-笔记与方法论", "个人读书笔记"),
    "紫微学习笔记": ("05-笔记与方法论", "个人学习笔记"),
    "方法论(skills)": ("05-笔记与方法论", "此前整理的解盘方法论"),
}

# originals worth copying verbatim from the OpenClaw-Space library (glob patterns,
# so a renamed or differently normalised filename still matches)
ORIGINALS = {
    "紫微典籍/**/*飞星*.md": "02-紫微-四化飞星派",
    "紫微典籍/**/*续道藏*.md": "01-紫微-三合派",
    "紫微典籍/README.md": "02-紫微-四化飞星派",
    "*渊海子平*.epub": "03-子平",
}

FRONT_MATTER = re.compile(r"^---\n.*?\n---\n", re.S)


def _chunk_key(p: Path):
    m = re.match(r"(\d+)", p.name)
    return (int(m.group(1)) if m else 10**9, p.name)


def merge_book(folder: Path, note: str) -> tuple[str, int]:
    """Concatenate a book's chunks in order, dropping the YAML front matter."""
    parts, seen = [], set()
    for f in sorted(folder.glob("*.md"), key=_chunk_key):
        text = FRONT_MATTER.sub("", f.read_text(encoding="utf-8")).strip()
        if not text:
            continue
        # chunks of the same section repeat their heading; keep the first one
        head = text.split("\n", 1)[0]
        if head.startswith("#") and head in seen:
            text = text.split("\n", 1)[1].strip() if "\n" in text else ""
        elif head.startswith("#"):
            seen.add(head)
        parts.append(text)
    body = "\n\n".join(parts)
    header = (f"# {folder.name}\n\n"
              f"> {note}\n> 由 knowledge_base/literature/{folder.name} 的 {len(list(folder.glob('*.md')))} 个切片合并而成。\n"
              f"> 引用时写明书名与本文件内的小标题。\n\n---\n\n")
    return header + body, len(body)


def main(source: Path) -> None:
    # Only this script's own outputs are rewritten; books downloaded by
    # fetch_classics.py live in the same tree and must survive a rebuild.
    OUT.mkdir(parents=True, exist_ok=True)
    rows, missing = [], []

    for name, (cat, note) in BOOKS.items():
        folder = LITERATURE / name
        if not folder.is_dir():
            missing.append(name)
            continue
        text, size = merge_book(folder, note)
        target = OUT / cat
        target.mkdir(parents=True, exist_ok=True)
        (target / f"{name}.md").write_text(text, encoding="utf-8")
        rows.append((cat, f"{name}.md", f"{size // 1024} KB", note))

    for pattern, cat in ORIGINALS.items():
        for src in sorted(source.glob(pattern)):
            target = OUT / cat / "原件"
            target.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, target / src.name)
            rows.append((cat + "/原件", src.name, f"{src.stat().st_size // 1024} KB", "原始文件，未分块"))

    # everything now in the reading room, including books fetched from the web
    known = {(cat, fn) for cat, fn, _, _ in rows}
    for f in sorted(OUT.rglob("*.md")):
        cat = str(f.parent.relative_to(OUT))
        if cat == "." or (cat, f.name) in known:
            continue
        rows.append((cat, f.name, f"{f.stat().st_size // 1024} KB", "下载的公有领域古籍"))

    kb_dirs = sorted((d.name, len(list(d.glob("*.md")))) for d in KB.iterdir()
                     if d.is_dir() and d.name != "literature")
    index = [
        "# 典籍阅读室（data/classics）",
        "",
        "给解盘用的完整原文，按派别分目录。检索用的切片仍在 `knowledge_base/`，两者内容相同。",
        "**引用规则**：写明书名、文件内小标题，必要时给出行号；找不到出处就说找不到，不要转述成古文。",
        "",
        "## 本目录内容",
        "",
        "| 目录 | 文件 | 大小 | 说明 |",
        "|---|---|---|---|",
    ]
    for cat, fn, size, note in sorted(rows):
        index.append(f"| {cat} | {fn} | {size} | {note} |")
    index += [
        "",
        "## 现代解释：紫微麦网站存档",
        "",
        f"站点存档没有复制到这里，原地在 `knowledge_base/`，共 {len(kb_dirs)} 个栏目。常用栏目：",
        "",
        "- `si-hua` 四化专题，`twelve-palaces` 十二宫，`palace-*` 各宫，`*-star` 各星曜与星系组合",
        "- `cases-study` 案例，`love-and-marriage`、`work-and-career`、`money-and-wealth` 专题",
        "- `ji-xing` 吉星，`sha-xing` 煞星，`za-xing` 杂星，`yi-jing` 易经",
        "",
        "## 还缺的典籍（需要你自己找电子版）",
        "",
        "见 `data/classics/书单.md`。",
        "",
    ]
    (OUT / "README.md").write_text("\n".join(index), encoding="utf-8")

    print(f"built {OUT} with {len(rows)} files")
    for cat, fn, size, _ in sorted(rows):
        print(f"  {cat}/{fn}  {size}")
    if missing:
        print("missing from literature:", "、".join(missing))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    default_src = next((p for p in (ROOT.parent / "OpenClaw-Space", ROOT.parent.parent / "OpenClaw-Space")
                        if p.is_dir()), ROOT.parent / "OpenClaw-Space")
    ap.add_argument("--source", default=str(default_src),
                    help="library folder holding the original files")
    a = ap.parse_args()
    main(Path(a.source))
