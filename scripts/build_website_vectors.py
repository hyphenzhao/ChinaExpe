"""Rebuild the project's ziwei_knowledge table from the repaired local articles.

Embeddings are checkpointed outside Git. Publish only after every chunk succeeds;
the shared OpenClaw database is never modified. Run on the NAS with local Ollama.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.repair_ziwei_archive import damaged  # noqa: E402
from app.services.knowledge_service import EMBED_MODEL, LEGACY_TABLE, PROJECT_DB, _ollama_embed_url, knowledge_service  # noqa: E402
from app.services.local_knowledge import local_knowledge  # noqa: E402


def split_body(text, size=1200, overlap=100):
    """Cover the entire article, preferring paragraph boundaries, with overlap."""
    if size <= overlap or overlap < 0:
        raise ValueError("invalid chunk size/overlap")
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            boundary = text.rfind("\n", start + size // 2, end)
            if boundary >= 0:
                end = boundary + 1
        chunk = text[start:end].strip()
        if chunk:
            yield chunk
        if end == len(text):
            break
        start = end - overlap


def article_chunks(files, local=local_knowledge):
    rows, seen, articles = [], set(), set()
    for f in files:
        if f.suffix != ".txt":
            continue
        title, source, body = local._parse_file(f, f.read_text(encoding="utf-8"))
        if damaged(title + body):
            raise ValueError(f"refusing to index damaged text: {f.name}")
        if not body.strip():
            continue
        articles.add(source)
        for content in split_body(body):
            key = hashlib.sha256((source + "\n" + title + "\n" + content).encode()).hexdigest()
            if key in seen:
                continue
            seen.add(key)
            rows.append({"id": key, "title": title, "source": source, "category": f.parent.name,
                         "filename": f.name, "content": content})
    return rows, len(articles)


async def build(service=knowledge_service, *, files=None, db_path=PROJECT_DB,
                cache_path=ROOT / "data/maintenance/ziwei-vector-cache.sqlite3", batch=16, progress=None):
    import lancedb

    rows, articles = article_chunks(local_knowledge._scan_files() if files is None else files)
    if not rows:
        raise ValueError("no readable website articles; previous table retained")
    cache_path = Path(cache_path)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    namespace = f"{EMBED_MODEL}|{_ollama_embed_url()}|article-1200-overlap100-v1|"
    dimension = None
    with sqlite3.connect(str(cache_path)) as cache:
        cache.execute("CREATE TABLE IF NOT EXISTS embeddings (key TEXT PRIMARY KEY, vector TEXT NOT NULL)")
        done = 0
        for start in range(0, len(rows), batch):
            group = rows[start:start + batch]
            missing = []
            for row in group:
                saved = cache.execute("SELECT vector FROM embeddings WHERE key=?", (namespace + row["id"],)).fetchone()
                if saved:
                    row["vector"] = json.loads(saved[0])
                else:
                    missing.append(row)
            if missing:
                vectors = await service.embed_many([r["title"] + "\n" + r["content"] for r in missing])
                if not vectors or len(vectors) != len(missing):
                    raise RuntimeError(f"embedding batch failed at {start}; checkpoint saved, previous table retained")
                for row, vector in zip(missing, vectors):
                    row["vector"] = vector
            for row in group:
                vector = row["vector"]
                if not vector or not all(isinstance(v, (int, float)) and math.isfinite(v) for v in vector):
                    raise ValueError("invalid embedding; previous table retained")
                dimension = dimension or len(vector)
                if len(vector) != dimension:
                    raise ValueError("embedding dimension changed; previous table retained")
            cache.executemany("INSERT OR REPLACE INTO embeddings VALUES (?, ?)",
                              [(namespace + r["id"], json.dumps(r["vector"])) for r in missing])
            cache.commit()
            done += len(group)
            if progress:
                progress(done, len(rows))
    # LanceDB's overwrite publishes a new table version, without a drop/create gap.
    db = lancedb.connect(str(db_path))
    table = db.create_table(LEGACY_TABLE, data=rows, mode="overwrite")
    if table.count_rows() != len(rows):
        raise RuntimeError("published row count mismatch")
    service.refresh()
    return {"success": True, "table": LEGACY_TABLE, "articles": articles, "rows": len(rows),
            "dimension": dimension, "elapsed": round(time.time() - t0, 1)}


def main():
    def progress(done, total):
        if done % 160 == 0 or done == total:
            print(f"website vectors: {done}/{total}", flush=True)
    print(json.dumps(asyncio.run(build(progress=progress)), ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
