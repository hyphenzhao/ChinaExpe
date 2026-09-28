"""Read the classics reading room (data/classics) as whole files with line numbers.

The vector/inverted index returns ~2 KB chunks, which is right for recall and
wrong for quoting: a citation has to be checkable.  These helpers give the LLM
a file list, a regex search that reports 路径:行号, and a line-range reader,
all restricted to the two knowledge folders.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
CLASSICS = ROOT / "data" / "classics"
KNOWLEDGE = ROOT / "knowledge_base"
ALLOWED_ROOTS = (CLASSICS, KNOWLEDGE)
TEXT_SUFFIXES = {".md", ".txt"}

MAX_READ_LINES = 400
MAX_READ_CHARS = 16000
MAX_HITS = 40


def _resolve(rel: str) -> Path:
    """Map a user/LLM supplied path to a real file inside the allowed roots."""
    rel = (rel or "").strip().replace("\\", "/").lstrip("/")
    # citations quote the repo-relative path; map those prefixes back to the roots
    trimmed = {"data/classics/": CLASSICS, "classics/": CLASSICS, "knowledge_base/": KNOWLEDGE}
    candidates = [CLASSICS / rel, KNOWLEDGE / rel, ROOT / rel]
    for prefix, root in trimmed.items():
        if rel.startswith(prefix):
            candidates.insert(0, root / rel[len(prefix):])
    for c in candidates:
        try:
            p = c.resolve()
        except OSError:
            continue
        if any(str(p).startswith(str(r.resolve())) for r in ALLOWED_ROOTS) and p.is_file():
            return p
    raise FileNotFoundError(f"找不到文件或不在典籍目录内: {rel}")


def _rel(p: Path) -> str:
    """Repository-relative path, which is what a citation should quote."""
    rp = p.resolve()
    for root, prefix in ((CLASSICS, "data/classics"), (KNOWLEDGE, "knowledge_base")):
        try:
            return f"{prefix}/{rp.relative_to(root.resolve()).as_posix()}"
        except ValueError:
            continue
    return rp.as_posix()


def _books() -> list[Path]:
    """Readable books, skipping the 原件 copies and folder READMEs (same text twice)."""
    if not CLASSICS.is_dir():
        return []
    return sorted(p for p in CLASSICS.rglob("*")
                  if p.is_file() and p.suffix.lower() in TEXT_SUFFIXES
                  and "原件" not in p.parts and p.name.lower() != "readme.md")


@lru_cache(maxsize=64)
def _lines(path_str: str, mtime: float) -> tuple[str, ...]:
    return tuple(Path(path_str).read_text(encoding="utf-8", errors="ignore").splitlines())


def lines_of(p: Path) -> tuple[str, ...]:
    return _lines(str(p), p.stat().st_mtime)


def list_books() -> list[dict]:
    out = []
    for p in _books():
        try:
            n = len(lines_of(p))
        except OSError:
            continue
        out.append({"path": _rel(p), "name": p.stem, "category": p.parent.name,
                    "lines": n, "kb": p.stat().st_size // 1024})
    return out


def list_books_text() -> str:
    books = list_books()
    if not books:
        return "典籍目录 data/classics 还是空的，先在服务器上跑 scripts/build_classics.py。"
    rows = ["本机典籍（data/classics，用 search_classics 检索、read_classic 按行读）：", ""]
    by_cat: dict[str, list[dict]] = {}
    for b in books:
        by_cat.setdefault(b["category"], []).append(b)
    for cat in sorted(by_cat):
        rows.append(f"## {cat}")
        for b in by_cat[cat]:
            rows.append(f"- {b['path']}（{b['lines']} 行，{b['kb']} KB）")
        rows.append("")
    rows.append("知识库另有紫微麦网站存档（knowledge_base/ 下按栏目分目录），用 search_knowledge 检索现代解释。")
    return "\n".join(rows)


def search(query: str, book: str = "", limit: int = 8, context: int = 1) -> list[dict]:
    """Regex (or plain substring) search over the classics, with line numbers."""
    try:
        rx = re.compile(query)
    except re.error:
        rx = re.compile(re.escape(query))
    limit = max(1, min(int(limit or 8), MAX_HITS))
    targets = _books()
    if book:
        key = book.strip().lower()
        narrowed = [p for p in targets if key in p.name.lower() or key in _rel(p).lower()]
        targets = narrowed or targets
    hits: list[dict] = []
    for p in targets:
        try:
            ls = lines_of(p)
        except OSError:
            continue
        for i, line in enumerate(ls):
            if not rx.search(line):
                continue
            lo, hi = max(0, i - context), min(len(ls), i + context + 1)
            hits.append({"path": _rel(p), "line": i + 1, "text": line.strip(),
                         "context": "\n".join(ls[lo:hi]).strip(),
                         "section": _section_of(ls, i)})
            if len(hits) >= limit:
                return hits
    return hits


def _section_of(ls: tuple[str, ...], i: int) -> str:
    for j in range(i, -1, -1):
        s = ls[j].strip()
        if s.startswith("#"):
            return s.lstrip("# ").strip()
    return ""


def search_text(query: str, book: str = "", limit: int = 8) -> str:
    hits = search(query, book, limit)
    if not hits:
        return (f"典籍全文里没有匹配 '{query}' 的行。换个写法再试，"
                f"例如只用星名或术语；或用 search_knowledge 检索现代文章。")
    out = [f"在本机典籍中找到 {len(hits)} 处匹配 '{query}'（引用请写 路径:行号）：", ""]
    for h in hits:
        head = f"{h['path']}:{h['line']}"
        if h["section"]:
            head += f"（{h['section']}）"
        out.append(head)
        out.append(h["context"])
        out.append("")
    out.append("需要更多上下文用 read_classic(path, start_line, end_line)。")
    return "\n".join(out)


def read_lines(path: str, start: int = 1, end: int | None = None) -> str:
    p = _resolve(path)
    ls = lines_of(p)
    start = max(1, int(start or 1))
    end = int(end) if end else start + 120
    end = min(end, start + MAX_READ_LINES - 1, len(ls))
    if start > len(ls):
        return f"{_rel(p)} 只有 {len(ls)} 行，起始行 {start} 超出范围。"
    body, size = [], 0
    for n in range(start, end + 1):
        line = ls[n - 1]
        size += len(line)
        if size > MAX_READ_CHARS:
            body.append(f"...（已截断，继续读请从第 {n} 行开始）")
            break
        body.append(f"{n:>6}  {line}")
    return f"# {_rel(p)} 第 {start}-{end} 行（共 {len(ls)} 行）\n\n" + "\n".join(body)
