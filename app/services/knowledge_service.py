"""Knowledge service - LanceDB RAG queries."""
import json
from pathlib import Path
from typing import Optional

import httpx

LANCE_DB_PATH = Path.home() / ".openclaw" / "memory" / "lancedb"
TABLE_NAME = "ziwei_knowledge"
OLLAMA_EMBED_URL = "http://127.0.0.1:11434/api/embed"
EMBED_MODEL = "bge-m3"


class KnowledgeService:
    """Service for querying the LanceDB knowledge base."""

    def __init__(self):
        self._db = None
        self._table = None

    def _ensure_table(self):
        """Lazy-load the LanceDB table."""
        if self._table is not None:
            return
        try:
            import lancedb
            self._db = lancedb.connect(str(LANCE_DB_PATH))
            self._table = self._db.open_table(TABLE_NAME)
        except Exception:
            self._table = False  # Mark as unavailable

    def is_available(self) -> bool:
        """Check if LanceDB is accessible."""
        self._ensure_table()
        return self._table is not False and self._table is not None

    async def embed(self, text: str) -> Optional[list[float]]:
        """Embed text using Ollama bge-m3."""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    OLLAMA_EMBED_URL,
                    json={"model": EMBED_MODEL, "input": text},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    embeddings = data.get("embeddings", [])
                    if embeddings:
                        return embeddings[0]
        except Exception:
            pass
        return None

    async def query(
        self, query_text: str, limit: int = 5, chart_context: Optional[str] = None
    ) -> list[dict]:
        """Query LanceDB for relevant knowledge chunks.

        Args:
            query_text: The user's question
            limit: Max number of chunks to return
            chart_context: Optional additional context (palace name, star, etc.)

        Returns:
            List of knowledge chunks with content and metadata
        """
        self._ensure_table()
        if not self._table:
            return []

        # Build a richer query from context
        full_query = query_text
        if chart_context:
            full_query = f"{chart_context} {query_text}"

        # Get embedding
        vec = await self.embed(full_query)
        if vec is None:
            return []

        try:
            results = self._table.search(vec).limit(limit).to_list()
            # Clean up results for the API
            cleaned = []
            for r in results:
                cleaned.append({
                    "content": r.get("chunk", r.get("content", r.get("text", "")))[:2000],
                    "source": r.get("source", r.get("url", "")),
                    "_distance": r.get("_distance", 0),
                })
            return cleaned
        except Exception:
            return []

    def format_rag_context(self, results: list[dict]) -> str:
        """Format RAG results as context for the system prompt."""
        if not results:
            return ""

        parts = ["\n## 知识库参考内容\n"]
        for i, r in enumerate(results[:5], 1):
            content = r.get("content", "")[:1500]
            parts.append(f"**[参考{i}]** {content}\n")
        return "\n".join(parts)


# Singleton
knowledge_service = KnowledgeService()
