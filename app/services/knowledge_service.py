"""Vector knowledge service (LanceDB + Ollama bge-m3).

Tables (in ``data/lancedb``; falls back to the legacy ``~/.openclaw/memory/lancedb``):
- ``ziwei_knowledge``  legacy 紫微麦 article chunks (columns: content/source/title/…)
- ``literature``       chunks built from knowledge_base/literature by ``build_vectors``
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Optional

import httpx

ROOT = Path(__file__).resolve().parent.parent.parent
PROJECT_DB = ROOT / "data" / "lancedb"
LEGACY_DB = Path.home() / ".openclaw" / "memory" / "lancedb"
LEGACY_TABLE = "ziwei_knowledge"
LIT_TABLE = "literature"
EMBED_MODEL = "bge-m3"
CONFIG_FILE = ROOT / "data" / "config.json"

_LOW_QUALITY_SOURCES = {"progress-schedule", "pai-ming-pan", "twelve-palaces", "website-privacy-policy",
                        "about-abcziweimy", "wu-xing-ju-note", "zwds-guide"}
_CHANGELOG_CONTENT_PATTERNS = [r"^\d{4}[\.\-/]\d{1,2}[\.\-/]\d{1,2}", r"^紫微[麥麦]网站收录",
                               r"^\d{4}年\d{1,2}月\d{1,2}日(增加|完成|整理|修改|发布|优化)",
                               r"^20\d{2}-\d{1,2}-\d{1,2}\s+\d{2}:\d{2}\s+[AP]M发布", r"^当作是为?\d+\.\d+版", r"^其实还有很多要做"]


def _ollama_embed_url() -> str:
    host, port = "http://127.0.0.1", 11434
    try:
        cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        # embeddings run on the same machine as the app by default (NAS ollama);
        # allow an explicit override via "embed_host"/"embed_port"
        host = cfg.get("embed_host") or host
        port = cfg.get("embed_port") or port
    except Exception:
        pass
    return f"{host.rstrip('/')}:{port}/api/embed"


class KnowledgeService:
    def __init__(self):
        self._db = None
        self._tables: dict[str, object] = {}
        self._checked = False

    # ------------------------------------------------------------- setup
    def db_path(self) -> Path:
        if PROJECT_DB.exists():
            return PROJECT_DB
        if LEGACY_DB.exists():
            return LEGACY_DB
        return PROJECT_DB

    def _connect(self):
        # re-scan every 60s while the literature table is missing (it may be
        # built by scripts/build_vectors.py while the server is running)
        if self._checked and (LIT_TABLE in self._tables or time.time() - getattr(self, "_checked_at", 0) < 60):
            return
        self._checked = True
        self._checked_at = time.time()
        self._tables = {}
        try:
            import lancedb
            path = self.db_path()
            if not path.exists():
                return
            self._db = lancedb.connect(str(path))
            names = set(self._db.table_names())
            for t in (LEGACY_TABLE, LIT_TABLE):
                if t in names:
                    self._tables[t] = self._db.open_table(t)
            # legacy table may live in the legacy folder even when the project folder exists
            if LEGACY_TABLE not in self._tables and path != LEGACY_DB and LEGACY_DB.exists():
                try:
                    ldb = lancedb.connect(str(LEGACY_DB))
                    if LEGACY_TABLE in set(ldb.table_names()):
                        self._tables[LEGACY_TABLE] = ldb.open_table(LEGACY_TABLE)
                except Exception:
                    pass
        except Exception:
            self._db = None

    def refresh(self):
        self._checked = False
        self._tables = {}
        self._connect()

    def is_available(self) -> bool:
        self._connect()
        return bool(self._tables)

    def status(self) -> dict:
        self._connect()
        out = {"path": str(self.db_path()), "tables": {}}
        for n, t in self._tables.items():
            try:
                out["tables"][n] = t.count_rows()
            except Exception:
                out["tables"][n] = "?"
        return out

    # --------------------------------------------------------- embedding
    async def embed(self, text: str) -> Optional[list[float]]:
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(_ollama_embed_url(), json={"model": EMBED_MODEL, "input": text})
                if resp.status_code == 200:
                    emb = resp.json().get("embeddings", [])
                    if emb:
                        return emb[0]
        except Exception:
            pass
        return None

    async def embed_many(self, texts: list[str]) -> Optional[list[list[float]]]:
        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                resp = await client.post(_ollama_embed_url(), json={"model": EMBED_MODEL, "input": texts})
                if resp.status_code == 200:
                    return resp.json().get("embeddings", [])
        except Exception:
            pass
        return None

    # ------------------------------------------------------------- query
    def _is_quality(self, source: str, content: str) -> bool:
        s = source.lower()
        if any(b in s for b in _LOW_QUALITY_SOURCES):
            return False
        head = content[:200].strip()
        if not head:
            return False
        return not any(re.match(p, head) for p in _CHANGELOG_CONTENT_PATTERNS)

    async def query(self, query_text: str, limit: int = 5, chart_context: Optional[str] = None, scope: str = "all") -> list[dict]:
        self._connect()
        if not self._tables:
            return []
        vec = await self.embed(f"{chart_context} {query_text}" if chart_context else query_text)
        if vec is None:
            return []
        rows: list[dict] = []
        for name, table in self._tables.items():
            if name == LEGACY_TABLE and scope == "bazi":
                continue
            try:
                res = table.search(vec).limit(max(limit * 3, 15)).to_list()
            except Exception:
                continue
            for r in res:
                system = r.get("system", "ziwei")
                if scope in ("ziwei", "bazi") and system not in (scope, "general"):
                    continue
                source = r.get("source", r.get("url", ""))
                content = r.get("content", r.get("chunk", r.get("text", "")))
                if name == LEGACY_TABLE and not self._is_quality(source, content):
                    continue
                rows.append({"content": content[:4000], "source": source, "title": r.get("title", ""),
                             "category": r.get("collection", r.get("category", "紫微麦")), "system": system,
                             "_distance": r.get("_distance", 0), "_table": name})
        rows.sort(key=lambda r: r["_distance"])
        out, seen = [], set()
        for r in rows:
            key = (r["title"], r["source"])
            if key in seen:
                continue
            seen.add(key)
            out.append(r)
            if len(out) >= limit:
                break
        return out

    def format_rag_context(self, results: list[dict]) -> str:
        if not results:
            return ""
        parts = ["\n## 向量检索命中（典籍/文章片段）\n"]
        for i, r in enumerate(results[:6], 1):
            cite = f"**[向量{i}]**"
            if r.get("title"):
                cite += f" 《{r['title']}》"
            if r.get("category"):
                cite += f" [{r['category']}]"
            if r.get("source"):
                cite += f" ({r['source']})"
            parts.append(f"{cite}\n{r.get('content', '')[:3000]}\n")
        return "\n".join(parts)

    # ------------------------------------------------------------- build
    async def build_literature_vectors(self, batch: int = 16, progress=None) -> dict:
        """Embed every knowledge_base/literature chunk into the ``literature`` table."""
        from .literature_importer import OUT_DIR
        try:
            import lancedb
        except Exception as e:
            return {"success": False, "message": f"lancedb 不可用: {e}"}
        files = sorted(OUT_DIR.rglob("*.md")) if OUT_DIR.exists() else []
        if not files:
            return {"success": False, "message": "knowledge_base/literature 为空，请先导入典籍"}
        if await self.embed("测试") is None:
            return {"success": False, "message": f"无法连接 Ollama 嵌入模型 ({_ollama_embed_url()}, {EMBED_MODEL})"}
        PROJECT_DB.mkdir(parents=True, exist_ok=True)
        db = lancedb.connect(str(PROJECT_DB))
        rows, t0 = [], time.time()
        pending: list[dict] = []

        async def flush():
            if not pending:
                return
            vecs = await self.embed_many([p["content"][:2000] for p in pending])
            if not vecs or len(vecs) != len(pending):
                for p in pending:   # fall back to one-by-one
                    v = await self.embed(p["content"][:2000])
                    if v:
                        p["vector"] = v
                        rows.append(p)
            else:
                for p, v in zip(pending, vecs):
                    p["vector"] = v
                    rows.append(p)
            pending.clear()
            if progress:
                progress(len(rows), len(files))

        for f in files:
            text = f.read_text(encoding="utf-8", errors="ignore")
            fm = {}
            m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
            body = text
            if m:
                for line in m.group(1).splitlines():
                    if ":" in line:
                        k, v = line.split(":", 1)
                        fm[k.strip()] = v.strip()
                body = text[m.end():]
            body = re.sub(r"^#\s+.+\n", "", body.strip(), count=1).strip()
            pending.append({"content": body, "title": fm.get("title", f.stem), "collection": fm.get("collection", f.parent.name),
                            "system": fm.get("system", "ziwei"), "school": fm.get("school", ""), "source": fm.get("source", str(f)),
                            "file": str(f.relative_to(ROOT))})
            if len(pending) >= batch:
                await flush()
        await flush()
        if not rows:
            return {"success": False, "message": "没有生成任何向量"}
        if LIT_TABLE in set(db.table_names()):
            db.drop_table(LIT_TABLE)
        db.create_table(LIT_TABLE, data=rows)
        self.refresh()
        return {"success": True, "message": f"已向量化 {len(rows)} 个片段，耗时 {time.time() - t0:.0f}s", "rows": len(rows)}


knowledge_service = KnowledgeService()
