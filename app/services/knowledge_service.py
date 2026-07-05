"""Knowledge service - LanceDB RAG queries."""
import json
import re
from pathlib import Path
from typing import Optional

import httpx

LANCE_DB_PATH = Path.home() / ".openclaw" / "memory" / "lancedb"
TABLE_NAME = "ziwei_knowledge"
OLLAMA_EMBED_URL = "http://127.0.0.1:11434/api/embed"
EMBED_MODEL = "bge-m3"

# Sources that are known to contain only changelogs/updates, not analytical content
_LOW_QUALITY_SOURCES = {
    "progress-schedule",
    "pai-ming-pan",
}

# Content patterns that indicate changelog/update text rather than analytical articles.
# Changelogs are dense with star/palace keywords, so bge-m3 embeddings rank them
# artificially high for almost any query. We filter them post-search.
_CHANGELOG_CONTENT_PATTERNS = [
    # Starts with date (e.g. "2013.04.08: 更新和修正...")
    r"^\d{4}[\.\-/]\d{1,2}[\.\-/]\d{1,2}",
    # Starts with "紫微麥网站收录" (progress report)
    r"^紫微[麥麦]网站收录",
    # "增加XXX的文章" / "完成XXX" / "整理XXX" changelog entries
    r"^\d{4}年\d{1,2}月\d{1,2}日(增加|完成|整理|修改|发布|优化)",
    # Software version release notes
    r"^20\d{2}-\d{1,2}-\d{1,2}\s+\d{2}:\d{2}\s+[AP]M发布",
    r"^当作是为?\d+\.\d+版",
    r"^其实还有很多要做",
]


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

    def _is_quality_content(self, source: str, content: str) -> bool:
        """Return False if content looks like a changelog/update, not analytical.

        Changelogs contain dense keyword clusters (many star/palace names listed
        together), making bge-m3 embeddings score them artificially high for
        most queries. We filter them out so real analytical articles surface.
        """
        # Source-based filter
        source_lower = source.lower()
        for bad in _LOW_QUALITY_SOURCES:
            if bad in source_lower:
                return False

        # Content-based filter: check first 200 chars for changelog patterns
        head = content[:200].strip()
        if not head:
            return False

        for pattern in _CHANGELOG_CONTENT_PATTERNS:
            if re.match(pattern, head):
                return False

        return True

    async def query(
        self, query_text: str, limit: int = 5, chart_context: Optional[str] = None
    ) -> list[dict]:
        """Query LanceDB for relevant knowledge chunks.

        Fetches more results than needed, filters out low-quality content
        (changelogs, update notes), and returns the best remaining chunks.

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
            # Fetch 3x to compensate for changelog pollution
            fetch_limit = max(limit * 3, 20)
            results = self._table.search(vec).limit(fetch_limit).to_list()

            # Filter and clean
            cleaned = []
            seen_sources = set()  # deduplicate by source URL
            for r in results:
                source = r.get("source", r.get("url", ""))
                content = r.get("content", r.get("chunk", r.get("text", "")))

                # Skip low-quality content
                if not self._is_quality_content(source, content):
                    continue

                # Deduplicate: only one chunk per source URL
                if source and source in seen_sources:
                    continue
                if source:
                    seen_sources.add(source)

                cleaned.append({
                    "content": content[:4000],
                    "source": source,
                    "title": r.get("title", ""),
                    "category": r.get("category", ""),
                    "_distance": r.get("_distance", 0),
                })

                if len(cleaned) >= limit:
                    break

            return cleaned
        except Exception:
            return []

    def format_rag_context(self, results: list[dict]) -> str:
        """Format RAG results as context for the system prompt.

        Includes source title and URL so the LLM can cite original articles.
        """
        if not results:
            return ""

        parts = ["\n## 知识库参考内容（紫微麦原文）\n"]
        parts.append("以下是从紫微麦知识库检索到的相关原文片段，回答时请先引用相关原文，再结合命盘解读。\n")
        for i, r in enumerate(results[:5], 1):
            title = r.get("title", "")
            source = r.get("source", "")
            content = r.get("content", "")[:3000]

            # Build citation header
            cite = f"**[原文{i}]**"
            if title:
                cite += f" 《{title}》"
            if source:
                cite += f" ({source})"

            parts.append(f"{cite}\n{content}\n")
        return "\n".join(parts)


# Singleton
knowledge_service = KnowledgeService()
