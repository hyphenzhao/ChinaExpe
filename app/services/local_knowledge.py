"""Local knowledge base — keyword search over text files.

Scans knowledge_base/ for .txt/.md files and uses Chinese character
bigram matching to find relevant content. No embedding model needed.
"""

import re
from pathlib import Path
from typing import Optional

# Project root relative to this file: app/services/local_knowledge.py -> ../../
_KB_PATH = Path(__file__).resolve().parent.parent.parent / "knowledge_base"


class LocalKnowledgeService:
    """Searches local text files by keyword matching."""

    def __init__(self):
        self._cache: dict[str, str] = {}  # filepath -> content
        self._cache_mtime: float = 0

    def is_available(self) -> bool:
        """Return True if any content files exist in the knowledge base."""
        files = self._scan_files()
        return len(files) > 0

    def _scan_files(self) -> list[Path]:
        """Scan knowledge_base/ and external mirror for readable files."""
        files = []
        if _KB_PATH.exists():
            for ext in ["*.txt", "*.md"]:
                for f in _KB_PATH.rglob(ext):
                    if f.name in ("README.md",):
                        continue
                    files.append(f)
        return sorted(files)

    def _refresh_cache(self):
        """Scan files and load content into memory cache."""
        files = self._scan_files()
        for f in files:
            fname = str(f)
            if fname not in self._cache:
                try:
                    content = f.read_text(encoding="utf-8", errors="ignore")
                    self._cache[fname] = content
                except Exception:
                    pass

    def _tokenize(self, text: str) -> set[str]:
        """Extract Chinese character unigrams and bigrams as search tokens."""
        # Extract Chinese characters only
        chars = re.findall(r"[一-鿿]", text)
        tokens = set(chars)  # unigrams
        for i in range(len(chars) - 1):
            tokens.add(chars[i] + chars[i + 1])  # bigrams
        # Also add the raw query words split by whitespace/punctuation
        words = re.split(r"[\s,，。！？、；：""''（）　]+", text)
        for w in words:
            if len(w) >= 2:
                tokens.add(w)
        return {t for t in tokens if len(t) >= 1}

    def _extract_snippet(self, content: str, query: str, max_len: int = 3000) -> str:
        """Extract the most relevant snippet from content around query terms."""
        if len(content) <= max_len:
            return content

        # Find where query terms appear and extract surrounding context
        tokens = self._tokenize(query)
        best_pos = 0
        best_score = 0

        # Sliding window to find the densest region
        window = min(500, len(content))
        for i in range(0, len(content) - window, 100):
            chunk = content[i : i + window]
            score = sum(1 for t in tokens if t in chunk)
            if score > best_score:
                best_score = score
                best_pos = i

        start = max(0, best_pos - max_len // 4)
        end = min(len(content), start + max_len)
        snippet = content[start:end]

        prefix = "..." if start > 0 else ""
        suffix = "..." if end < len(content) else ""
        return prefix + snippet + suffix

    def search(self, query: str, limit: int = 5) -> list[dict]:
        """Search local knowledge base for files matching the query.

        Uses Chinese character bigram matching — no embedding model needed.
        Returns list of {title, source, content} dicts.
        """
        self._refresh_cache()

        if not self._cache:
            return []

        tokens = self._tokenize(query)
        if not tokens:
            return []

        # Score each file by token match density
        scored = []
        for fname, content in self._cache.items():
            score = 0
            # Higher weight for filename matches
            fname_lower = fname.lower()
            for t in tokens:
                if len(t) >= 2 and t in fname_lower:
                    score += 3
                if t in content:
                    score += 1

            if score > 0:
                # Normalize by content length to favor focused articles
                density = score / max(len(content), 1000)
                scored.append((score * density, fname, content))

        # Sort by score descending, take top N
        scored.sort(key=lambda x: x[0], reverse=True)

        results = []
        for score, fname, content in scored[:limit]:
            # Extract article title from content header (ziwemy format)
            title = Path(fname).stem
            source = ""
            body = content

            # Parse ziwemy .txt header format
            header_match = re.match(
                r"={5,}\s*\n标题:\s*(.+?)\n来源:\s*(.+?)\n",
                content,
            )
            if header_match:
                title = header_match.group(1).strip()
                source = header_match.group(2).strip()
                # Strip the header from the body
                body = content[header_match.end() :]
                body = re.sub(r"^={5,}\s*\n", "", body)  # remove separator

            snippet = self._extract_snippet(body, query, 3000)
            results.append(
                {
                    "title": title,
                    "source": source,
                    "content": snippet,
                    "file": fname,
                    "score": round(score, 2),
                }
            )

        return results

    def format_context(self, results: list[dict]) -> str:
        """Format local knowledge results as system prompt context."""
        if not results:
            return ""

        parts = ["\n## 本地知识库原文（完整文章，优先引用）\n"]
        parts.append("以下是从本地知识库中找到的完整原文，请优先引用这些内容，再结合命盘解读。\n")
        for i, r in enumerate(results[:5], 1):
            title = r.get("title", "")
            source = r.get("source", "")
            content = r.get("content", "")

            cite = f"**[本地原文{i}]**"
            if title:
                cite += f" 《{title}》"
            if source:
                cite += f" ({source})"

            parts.append(f"{cite}\n{content}\n")
        return "\n".join(parts)


# Singleton
local_knowledge = LocalKnowledgeService()
