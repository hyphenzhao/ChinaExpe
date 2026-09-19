"""Import 典籍 / 笔记 / skills into knowledge_base/literature/ as chunked markdown.

Each output file has YAML front matter::

    ---
    title: 论食神
    collection: 渊海子平
    system: bazi          # ziwei | bazi | general
    school: 子平
    source: Z:/OpenClaw-Space/子平读书笔记/原文/渊海子平_全文.txt
    part: 3/12
    ---

Sources are resolved from the OpenClaw-Space folder (env ``OPENCLAW_SPACE`` or
well-known locations) plus this repo's ``skills/`` directory.
"""
from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Optional

ROOT = Path(__file__).resolve().parent.parent.parent
OUT_DIR = ROOT / "knowledge_base" / "literature"

_CANDIDATES = [
    os.environ.get("OPENCLAW_SPACE", ""),
    "/Volumes/Storage/OpenClaw-Space",
    "Z:/OpenClaw-Space",
    str(ROOT.parent.parent / "OpenClaw-Space"),
]


def openclaw_space() -> Optional[Path]:
    for c in _CANDIDATES:
        if c and Path(c).is_dir():
            return Path(c)
    return None


_BOILERPLATE = re.compile(r"^(传硕公版书|关于我们|制作说明|本书属于公版书.*|这本电子书可供.*|https?://\S+)\s*$")
MAX_CHUNK = 2600      # chars per chunk (bge-m3 friendly, ~1.3k tokens)
MIN_CHUNK = 300


@dataclass
class Doc:
    title: str
    text: str
    collection: str
    system: str
    school: str
    source: str
    extra: dict = field(default_factory=dict)


def _clean(text: str) -> str:
    lines = []
    for ln in text.splitlines():
        s = ln.rstrip()
        if _BOILERPLATE.match(s.strip()):
            continue
        if s.strip() in ("", "\u3000"):
            lines.append("")
        else:
            lines.append(s)
    out = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    return out


def _split_by_size(text: str, size: int = MAX_CHUNK) -> list[str]:
    if len(text) <= size:
        return [text]
    paras = re.split(r"\n\s*\n", text)
    chunks, cur = [], ""
    for p in paras:
        if len(cur) + len(p) + 2 > size and len(cur) >= MIN_CHUNK:
            chunks.append(cur.strip())
            cur = p
        else:
            cur = (cur + "\n\n" + p) if cur else p
        while len(cur) > size * 1.5:   # very long paragraph
            chunks.append(cur[:size].strip())
            cur = cur[size:]
    if cur.strip():
        chunks.append(cur.strip())
    return chunks


def _split_by_heading(text: str, pattern: str, title_group: int = 1, default_title: str = "前言") -> list[tuple[str, str]]:
    """Split ``text`` at lines matching ``pattern``; returns [(title, body)]."""
    rx = re.compile(pattern, re.M)
    parts = []
    last = 0
    last_title = default_title
    for m in rx.finditer(text):
        body = text[last:m.start()].strip()
        if body:
            parts.append((last_title, body))
        last_title = m.group(title_group).strip()
        last = m.end()
    body = text[last:].strip()
    if body:
        parts.append((last_title, body))
    return parts


# ---------------------------------------------------------------------------
# source readers -> list[Doc]
# ---------------------------------------------------------------------------

def read_dir_md(folder: Path, collection: str, system: str, school: str, glob: str = "*.md",
                skip: Iterable[str] = ()) -> list[Doc]:
    docs = []
    if not folder.is_dir():
        return docs
    for f in sorted(folder.rglob(glob)):
        if f.name in skip or f.name.startswith(".") or f.name == "README.md" and "readme" not in glob:
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        m = re.match(r"^#\s+(.+)", text)
        title = m.group(1).strip() if m else f.stem
        docs.append(Doc(title=title, text=_clean(text), collection=collection, system=system, school=school, source=str(f)))
    return docs


def read_liangruoyu(f: Path) -> list[Doc]:
    text = f.read_text(encoding="utf-8", errors="ignore")
    docs = []
    for m in re.finditer(r"^## \[(\d+)\]\s*(.+?)\n(.*?)(?=^## \[\d+\]|\Z)", text, re.M | re.S):
        n, title, body = m.group(1), m.group(2).strip(), m.group(3)
        src = re.search(r"来源:\s*(\S+)", body)
        body = re.sub(r"^来源:.*$", "", body, flags=re.M)
        body = re.sub(r"^=+\s*$", "", body, flags=re.M)
        # first heading-ish line inside the body is the real topic
        cand = [ln.strip() for ln in body.splitlines() if ln.strip() and 3 < len(ln.strip()) < 40 and "梁若瑜" not in ln]
        first = cand[0] if cand else ""
        docs.append(Doc(title=f"[{n}] {first or title}", text=_clean(body), collection="梁若瑜飞星问答", system="ziwei",
                        school="飞星派", source=src.group(1) if src else str(f)))
    return docs


def read_yuanhai(f: Path) -> list[Doc]:
    text = f.read_text(encoding="utf-8", errors="ignore")
    text = _clean(text)
    docs = []
    section = "总论"
    for title, body in _split_by_heading(text, r"^[ \u3000]*(【[^】]{1,12}】|《[^》]{1,16}》)\s*$"):
        if title.startswith("【"):
            section = title.strip("【】")
            if len(body) < MIN_CHUNK:
                continue
            title = section
        docs.append(Doc(title=title.strip("《》"), text=body, collection="渊海子平", system="bazi", school="子平",
                        source=str(f), extra={"section": section}))
    return docs


def read_daozang(f: Path) -> list[Doc]:
    text = _clean(f.read_text(encoding="utf-8", errors="ignore"))
    parts = _split_by_heading(text, r"^#{1,3}\s+(.+)$")
    if len(parts) <= 2:  # single heading: split by 「X论」/「论X」 lines
        parts = _split_by_heading(text, r"^[ \u3000]*((?:论|安|定|辨|总)[^\n，。]{1,14}|[^\n，。]{1,14}(?:论|诀|赋|法|例))\s*$")
    return [Doc(title=t, text=b, collection="紫微斗数续道藏本", system="ziwei", school="三合派", source=str(f)) for t, b in parts if len(b) >= 80]


def read_skills(skills_dir: Path) -> list[Doc]:
    docs = []
    for skill in sorted(p for p in skills_dir.iterdir() if p.is_dir()):
        if any(k in skill.name for k in ("qimen", "medicine")):
            continue   # not 紫微/子平
        system = "ziwei" if "ziwei" in skill.name else ("bazi" if any(k in skill.name for k in ("bazi", "ziping")) else "general")
        for f in sorted(skill.rglob("*.md")):
            if f.name in ("LICENSE", "README.md") or ".openclaw" in f.parts or "templates" in f.parts:
                continue
            text = f.read_text(encoding="utf-8", errors="ignore")
            text = re.sub(r"^---\n.*?\n---\n", "", text, count=1, flags=re.S)   # strip SKILL.md front matter
            m = re.match(r"^#\s+(.+)", text.strip())
            title = (m.group(1).strip() if m else f.stem)
            docs.append(Doc(title=f"{skill.name}: {title}", text=_clean(text), collection="方法论(skills)", system=system,
                            school="综合", source=str(f)))
    return docs


def read_epub(f: Path, collection: str, system: str, school: str) -> list[Doc]:
    try:
        from ebooklib import epub, ITEM_DOCUMENT
    except Exception:
        return []
    docs = []
    try:
        book = epub.read_epub(str(f))
        for item in book.get_items():
            if item.get_type() != ITEM_DOCUMENT:
                continue
            html = item.get_content().decode("utf-8", errors="ignore")
            title_m = re.search(r"<h[1-3][^>]*>(.*?)</h[1-3]>", html, re.S)
            text = re.sub(r"<[^>]+>", "\n", html)
            text = re.sub(r"&nbsp;|&#160;", " ", text)
            text = _clean(text)
            if len(text) < 200:
                continue
            title = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", title_m.group(1))).strip() if title_m else item.get_name()
            docs.append(Doc(title=title, text=text, collection=collection, system=system, school=school, source=f"{f}#{item.get_name()}"))
    except Exception:
        return []
    return docs


def read_pdf(f: Path, collection: str, system: str, school: str) -> list[Doc]:
    try:
        from pypdf import PdfReader
    except Exception:
        return []
    try:
        reader = PdfReader(str(f))
        pages = [(p.extract_text() or "") for p in reader.pages]
    except Exception:
        return []
    docs, buf, start = [], "", 1
    for i, t in enumerate(pages, 1):
        buf += "\n" + t
        if len(buf) >= MAX_CHUNK * 2 or i == len(pages):
            docs.append(Doc(title=f"{f.stem} p{start}-{i}", text=_clean(buf), collection=collection, system=system, school=school, source=f"{f}#p{start}-{i}"))
            buf, start = "", i + 1
    return docs


# ---------------------------------------------------------------------------
# plan + write
# ---------------------------------------------------------------------------

def default_sources(space: Path) -> list[Callable[[], list[Doc]]]:
    return [
        lambda: read_dir_md(space / "紫微斗数全书" / "章节", "紫微斗数全书", "ziwei", "三合派"),
        lambda: read_daozang(space / "紫微典籍" / "三合派" / "紫微斗数_续道藏本.md") if (space / "紫微典籍" / "三合派" / "紫微斗数_续道藏本.md").exists() else [],
        lambda: sum((read_liangruoyu(f) for f in sorted((space / "紫微典籍" / "飞星派").rglob("*.md"))), []) if (space / "紫微典籍" / "飞星派").is_dir() else [],
        lambda: read_yuanhai(space / "子平读书笔记" / "原文" / "渊海子平_全文.txt") if (space / "子平读书笔记" / "原文" / "渊海子平_全文.txt").exists() else [],
        lambda: read_dir_md(space / "子平读书笔记" / "笔记", "子平读书笔记", "bazi", "子平"),
        lambda: [d for d in read_dir_md(space / "Notepad", "紫微学习笔记", "ziwei", "综合")
                 if any(k in Path(d.source).name for k in ("入门教程", "学习进度表", "教程"))],
        lambda: read_skills(ROOT / "skills") if (ROOT / "skills").is_dir() else [],
    ]


def _safe_name(s: str) -> str:
    s = re.sub(r"[\\/:*?\"<>|\s]+", "_", s).strip("_")
    return s[:60] or "doc"


def import_literature(space: Optional[Path] = None, clean: bool = True) -> dict:
    space = space or openclaw_space()
    if space is None:
        return {"success": False, "message": "找不到 OpenClaw-Space 目录（可设置环境变量 OPENCLAW_SPACE）", "files": 0}
    if clean and OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    total, per_collection = 0, {}
    for loader in default_sources(space):
        try:
            docs = loader()
        except Exception as e:  # one bad source must not kill the import
            per_collection[f"error:{loader}"] = str(e)
            continue
        for d in docs:
            if not d.text or len(d.text) < 60:
                continue
            chunks = _split_by_size(d.text)
            cdir = OUT_DIR / _safe_name(d.collection)
            cdir.mkdir(parents=True, exist_ok=True)
            n = per_collection.get(d.collection, 0)
            for k, chunk in enumerate(chunks, 1):
                n += 1
                part = f"{k}/{len(chunks)}"
                fname = f"{n:04d}_{_safe_name(d.title)}{'_' + str(k) if len(chunks) > 1 else ''}.md"
                fm = ["---", f"title: {d.title}", f"collection: {d.collection}", f"system: {d.system}", f"school: {d.school}",
                      f"source: {d.source}", f"part: {part}"]
                for kk, vv in d.extra.items():
                    fm.append(f"{kk}: {vv}")
                fm.append("---")
                (cdir / fname).write_text("\n".join(fm) + f"\n\n# {d.title}\n\n{chunk}\n", encoding="utf-8")
                total += 1
            per_collection[d.collection] = n
    return {"success": True, "message": f"已导入 {total} 个片段：" + "，".join(f"{k} {v}" for k, v in per_collection.items()),
            "files": total, "collections": per_collection, "space": str(space)}


def literature_stats() -> dict:
    if not OUT_DIR.exists():
        return {"files": 0, "collections": {}}
    cols = {}
    for d in OUT_DIR.iterdir():
        if d.is_dir():
            cols[d.name] = len(list(d.glob("*.md")))
    return {"files": sum(cols.values()), "collections": cols}
