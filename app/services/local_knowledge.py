"""Local knowledge base — inverted-index search over text files.

Builds an index (knowledge_base/index.json) for fast, precise lookup.
Index can be rebuilt via API endpoint or Settings UI button.
"""

import json
import re
import time
from pathlib import Path
from typing import Optional

# Project root relative to this file: app/services/local_knowledge.py -> ../../
_KB_PATH = Path(__file__).resolve().parent.parent.parent / "knowledge_base"
_INDEX_PATH = _KB_PATH / "index.json"

# Map English directory names to Chinese terms for cross-language matching
# Directories and files to exclude from search — these are dictionary/overview
# pages or changelogs that match every query and drown out focused articles.
_EXCLUDE_DIRS = {
    "twelve-palaces",       # 12-palace overview — lists every palace's stars
    "progress-schedule",    # website changelog
    "pai-ming-pan",         # software release notes
    "website-privacy-policy",  # privacy policy
    "about-abcziweimy-v3",  # old version changelog
    "about-abcziweimy-v5",  # version changelog
    "yi-jing",              # I-Ching, not ziwei
    "uncategorized",        # miscellaneous
    "online-resources",     # link collections
    "home",                 # homepage
    "cases-study",          # case studies
    "index-case-study",
    "index-zi-wei-dou-shu-articles",
    "index-zwds-stars-in-career-palace",
    "index-zwds-stars-in-life-palace",
    "index-zwds-stars-in-spouse-palace",
    "index-zwds-stars-in-wealth-palace",
}

# Specific catch-all files that match too many queries
_EXCLUDE_FILES = {
    "love-and-marriage_what-man-cannot-marry.txt",           # 什么男人不能嫁 — huge, covers all stars
    "love-and-marriage_what-kind-of-seductive-beauty-are-you.txt",  # 诱人尤物 — covers 14 stars
    "love-and-marriage_tao-hua-star-note-9.txt",             # 桃花开几朵 — covers all stars
    "love-and-marriage_what-is-true-love.txt",               # 性爱分离 — broad
    "zi-wei-dou-shu-portfolio_wu-xing-ju-note-1.txt",       # 五行局 — covers all bureaus
    "zi-wei-dou-shu-portfolio_zwds-guide-zi-wei-dou-shu-basics-11.txt",  # basics overview
    "zi-wei-dou-shu-portfolio_zwds-guide-ming-ju-da-xian-xiao-xian-liu-nian.txt",  # overview
}

_DIR_CN_MAP = {
    "palace-life": "命宫",
    "palace-wealth": "财帛宫",
    "palace-career": "官禄宫 事业宫",
    "palace-spouse": "夫妻宫",
    "palace-travel": "迁移宫",
    "palace-health": "疾厄宫",
    "palace-children": "子女宫",
    "palace-sibling": "兄弟宫",
    "palace-parents": "父母宫",
    "palace-property": "田宅宫",
    "palace-spirit": "福德宫",
    "palace-friends": "交友宫 奴仆宫",
    "twelve-palaces": "十二宫 宫位",
    "wu-qu-star": "武曲",
    "zi-wei-star": "紫微",
    "tian-fu-star": "天府",
    "tian-xiang-star": "天相",
    "tian-ji-star": "天机",
    "tian-liang-star": "天梁",
    "tian-tong-star": "天同",
    "tai-yang-star": "太阳",
    "tai-yin-star": "太阴",
    "tan-lang-star": "贪狼",
    "ju-men-star": "巨门",
    "qi-sha-star": "七杀",
    "po-jun-star": "破军",
    "lian-zhen-star": "廉贞",
    "sha-xing": "煞星 地劫 地空 火星 铃星 擎羊 陀罗",
    "ji-xing": "吉星 文昌 文曲 左辅 右弼 天魁 天钺 禄存",
    "za-xing": "杂星 天马 天姚 天喜",
    "si-hua": "四化 化禄 化权 化科 化忌",
    "love-and-marriage": "桃花 婚姻 感情",
    "money-and-wealth": "财运 财富 理财",
    "work-and-career": "事业 工作 职业",
    "literature": "典籍",
    "紫微斗数全书": "全书 紫微斗数 三合",
    "紫微斗数续道藏本": "续道藏 紫微斗数",
    "梁若瑜飞星问答": "梁若瑜 飞星 飞星派 宫干 四化",
    "渊海子平": "渊海子平 子平 八字 十神",
    "子平读书笔记": "子平 八字 笔记",
    "方法论(skills)": "方法论 技能 解盘",
    "紫微学习笔记": "教程 入门 紫微",
}

# ── Smart keyword extraction from user questions ─────────────────

# Comprehensive 紫微斗数 terminology: stars, palaces, concepts.
# Used to extract meaningful keywords from natural-language questions.
_ZWDS_TERMS = [
    # 14 main stars
    "紫微", "天机", "太阳", "武曲", "天同", "廉贞",
    "天府", "太阴", "贪狼", "巨门", "天相", "天梁", "七杀", "破军",
    # Compound star names
    "紫微天府", "紫微天相", "紫微七杀", "紫微破军", "紫微贪狼",
    "武曲天府", "武曲天相", "武曲七杀", "武曲破军", "武曲贪狼",
    "廉贞天府", "廉贞天相", "廉贞七杀", "廉贞破军", "廉贞贪狼",
    "天同太阴", "天同天梁", "天同巨门",
    "太阳太阴", "太阳天梁", "太阳巨门",
    "天机太阴", "天机天梁", "天机巨门",
    # Auxiliary stars (吉星)
    "文昌", "文曲", "左辅", "右弼", "天魁", "天钺", "禄存", "天马",
    # Sha stars (煞星)
    "擎羊", "陀罗", "火星", "铃星", "地劫", "地空",
    # Miscellaneous stars (杂耀)
    "天姚", "天刑", "天哭", "天虚", "红鸾", "天喜", "龙池", "凤阁",
    "三台", "八座", "恩光", "天贵", "台辅", "封诰",
    "天官", "天福", "孤辰", "寡宿", "蜚廉", "破碎",
    "天巫", "阴煞", "天月", "天才", "天寿",
    # 12 palaces
    "命宫", "兄弟宫", "夫妻宫", "子女宫", "财帛宫", "疾厄宫",
    "迁移宫", "交友宫", "奴仆宫", "官禄宫", "事业宫", "田宅宫",
    "福德宫", "父母宫", "身宫",
    # 四化
    "化禄", "化权", "化科", "化忌",
    # 大限流年
    "大限", "流年", "小限", "本命", "大运",
    # 格局 concepts
    "三方四正", "对宫", "三合", "六合", "庙旺", "落陷", "得地",
    "空宫", "双星", "单星", "独坐", "同度", "会照", "拱照",
    # 四化/自化/飞星 (extra)
    "自化", "离心自化", "向心自化", "生年四化", "飞化", "飞星", "宫干", "来因宫", "四化派", "钦天四化", "三合派", "飞星派",
    "大限四化", "流年四化", "小限", "斗君", "流月", "流日", "命主", "身主", "五行局",
    # 神煞 (bazi)
    "天乙贵人", "太极贵人", "文昌贵人", "福星贵人", "天德贵人", "月德贵人", "国印", "华盖", "驿马", "将星", "桃花", "咸池",
    "羊刃", "阳刃", "禄神", "学堂", "词馆", "金舆", "劫煞", "亡神", "灾煞", "孤辰", "寡宿", "元辰", "勾绞", "童子", "六秀",
    "阴差阳错", "魁罡", "十恶大败", "空亡", "纳音", "藏干", "地势", "长生", "沐浴", "冠带", "临官", "帝旺", "墓库", "胎元",
    "大运", "起运", "月令", "格局", "食神制杀", "伤官配印", "官印相生", "财官", "从格", "身强", "身弱",
    # 十神 (bazi terms)
    "正官", "偏官", "七杀", "正印", "偏印", "枭神",
    "正财", "偏财", "食神", "伤官", "比肩", "劫财",
    "日主", "用神", "忌神", "喜神", "格局", "十神",
    # 五行
    "金", "木", "水", "火", "土",
    # 天干地支
    "甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸",
    "子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥",
]

# Sort by length descending for longest-match-first extraction
_ZWDS_TERMS.sort(key=len, reverse=True)

# Noise words to filter from keyword extraction
_STOP_WORDS = {
    "代表什么", "什么意思", "怎么样", "如何", "怎么", "什么", "为什么",
    "看看", "帮我", "请问", "你好", "可以", "这个", "那个", "一下",
    "解读", "分析", "解释", "说明", "描述", "原文", "文章", "内容",
    "来说", "来讲", "来看", "觉得", "认为", "知道", "了解", "听说",
    "在", "的", "了", "是", "有", "和", "与", "或", "吗", "呢", "吧", "啊",
    "：", ":", "，", ",", "。", ".", "？", "?", "！", "!",
}


def extract_keywords(question: str, max_kw: int = 12) -> list[str]:
    """Extract meaningful 紫微斗数 keywords from a natural-language question.

    Uses a known terminology dictionary with longest-match-first extraction.
    Returns keywords in order of appearance, without duplicates.
    """
    text = question.strip()
    keywords = []
    i = 0
    while i < len(text):
        matched = False
        # Try longest match first
        for term in _ZWDS_TERMS:
            if text[i:].startswith(term):
                keywords.append(term)
                i += len(term)
                matched = True
                break
        if not matched:
            i += 1

    # Deduplicate while preserving order
    seen = set()
    result = []
    for kw in keywords:
        if kw not in seen:
            seen.add(kw)
            result.append(kw)

    return result[:max_kw]


class LocalKnowledgeService:
    """Searches local text files using a precomputed inverted index."""

    def __init__(self):
        self._index: Optional[dict] = None
        self._content_cache: dict[str, str] = {}  # relpath -> content

    # ── public API ──────────────────────────────────────────────

    def is_available(self) -> bool:
        """Return True if content files exist."""
        return bool(self._scan_files())

    def index_exists(self) -> bool:
        """Return True if an index has been built."""
        return _INDEX_PATH.exists()

    def index_info(self) -> dict:
        """Return metadata about the current index."""
        if not _INDEX_PATH.exists():
            return {"exists": False, "file_count": 0, "term_count": 0}
        try:
            idx = json.loads(_INDEX_PATH.read_text(encoding="utf-8"))
            return {
                "exists": True,
                "file_count": len(idx.get("files", {})),
                "term_count": len(idx.get("index", {})),
                "built_at": idx.get("built_at", ""),
            }
        except Exception:
            return {"exists": False, "error": "索引文件损坏"}

    def build_index(self) -> dict:
        """Scan all files and build the inverted index.

        Returns a status dict suitable for API response.
        """
        files = self._scan_files()
        if not files:
            return {"success": False, "message": "知识库中没有文件", "file_count": 0}

        start = time.time()
        file_entries = {}
        inverted: dict[str, list[str]] = {}

        for f in files:
            rel = f.relative_to(_KB_PATH).as_posix()   # posix so the index is portable between Windows and the NAS
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            # Parse metadata
            title, source, body = self._parse_file(f, content)

            # Extract search terms from multiple sources
            terms = self._extract_file_terms(f, title, content)

            system = "ziwei"
            fm = re.match(r"^---\n(.*?)\n---\n", content, re.S)
            if fm:
                m = re.search(r"^system:\s*(\S+)", fm.group(1), re.M)
                if m:
                    system = m.group(1)
            file_entries[rel] = {
                "title": title,
                "source": source,
                "terms": sorted(terms),
                "size": len(content),
                "system": system,
                "literature": rel.replace("\\", "/").startswith("literature/"),
            }

            # Populate inverted index
            for t in terms:
                if t not in inverted:
                    inverted[t] = []
                inverted[t].append(rel)

        # Deduplicate inverted index entries
        for t in inverted:
            inverted[t] = list(dict.fromkeys(inverted[t]))  # preserve order, dedup

        index_data = {
            "built_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "file_count": len(file_entries),
            "term_count": len(inverted),
            "files": file_entries,
            "index": inverted,
        }

        _KB_PATH.mkdir(parents=True, exist_ok=True)
        _INDEX_PATH.write_text(
            json.dumps(index_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        elapsed = time.time() - start
        self._index = index_data  # keep in memory
        return {
            "success": True,
            "message": f"索引已生成：{len(file_entries)} 个文件，{len(inverted)} 个关键词，耗时 {elapsed:.1f}s",
            "file_count": len(file_entries),
            "term_count": len(inverted),
            "elapsed": round(elapsed, 1),
        }

    def search(self, query: str, limit: int = 5, scope: str = "all") -> tuple[list[dict], list[str]]:
        """Search using the inverted index with smart keyword extraction.

        Returns (results, keywords_used) so the caller can show what was searched.
        """
        # Extract meaningful keywords from the question
        keywords = extract_keywords(query)
        if not keywords:
            # Fallback: use raw tokenization
            keywords = list(self._tokenize(query))[:10]

        # Build search query from extracted keywords
        search_query = " ".join(keywords) if keywords else query

        # Try index first
        if self._load_index():
            results = self._search_index(search_query, limit, scope)
        else:
            self.build_index()
            if self._load_index():
                results = self._search_index(search_query, limit, scope)
            else:
                results = self._search_scan(search_query, limit)

        return results, keywords

    def format_context(self, results: list[dict], keywords: list[str] = None) -> str:
        """Format local knowledge results as system prompt context."""
        if not results:
            return ""

        parts = ["\n## 本地知识库原文（完整文章，优先引用）\n"]
        if keywords:
            parts.append(f"**搜索关键词**: {' '.join(keywords)}\n")
        parts.append(
            "以下是从本地知识库中找到的完整原文，请优先引用这些内容，再结合命盘解读。\n"
        )
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

    # ── file scanning ───────────────────────────────────────────

    def _scan_files(self) -> list[Path]:
        """List all readable files in knowledge_base/, excluding noise dirs."""
        files = []
        if _KB_PATH.exists():
            for ext in ["*.txt", "*.md"]:
                for f in _KB_PATH.rglob(ext):
                    if f.name in ("README.md",) or f.name.startswith("index."):
                        continue
                    # Exclude known noise directories
                    if f.parent.name in _EXCLUDE_DIRS:
                        continue
                    # Exclude known catch-all files
                    if f.name in _EXCLUDE_FILES:
                        continue
                    if f.parent.name.startswith("."):
                        continue
                    files.append(f)
        return sorted(files)

    def _parse_file(self, filepath: Path, content: str) -> tuple[str, str, str]:
        """Parse a knowledge base file, returning (title, source, body)."""
        title = filepath.stem
        source = ""
        body = content

        # YAML front matter (knowledge_base/literature)
        fm = re.match(r"^---\n(.*?)\n---\n", content, re.S)
        if fm:
            meta = {}
            for line in fm.group(1).splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    meta[k.strip()] = v.strip()
            body = content[fm.end():]
            body = re.sub(r"^\s*#\s+.+\n", "", body, count=1)
            title = meta.get("title", title)
            source = meta.get("source", "")
            coll = meta.get("collection", "")
            if coll:
                title = f"{title}（{coll}）"
            return title, source, body.strip()

        # Try ziwemy .txt header format
        header_match = re.match(
            r"={5,}\s*\n标题:\s*(.+?)\n来源:\s*(.+?)\n",
            content,
        )
        if header_match:
            title = header_match.group(1).strip()
            source = header_match.group(2).strip()
            body = content[header_match.end() :]
            body = re.sub(r"^={5,}\s*\n", "", body)
        else:
            # Try markdown heading
            md_match = re.match(r"^#\s+(.+)", content)
            if md_match:
                title = md_match.group(1).strip()

        return title, source, body

    # ── term extraction for indexing ────────────────────────────

    def _extract_file_terms(
        self, filepath: Path, title: str, content: str
    ) -> set[str]:
        """Extract search terms from a file for the inverted index."""
        terms = set()

        # 1. Directory name → terms + Chinese equivalents
        for part in filepath.parent.parts:
            part_lower = part.strip().lower()
            # Add raw directory name parts
            for seg in re.split(r"[-_/]", part_lower):
                if seg and len(seg) >= 2:
                    terms.add(seg)
            # Map English dir names to Chinese terms
            if part_lower in _DIR_CN_MAP:
                for cn_term in _DIR_CN_MAP[part_lower].split():
                    terms.add(cn_term)
                    # Also add bigrams from the Chinese term
                    for i in range(len(cn_term) - 1):
                        terms.add(cn_term[i : i + 2])

        # 2. Filename stems
        for seg in re.split(r"[-_]", filepath.stem.lower()):
            if len(seg) >= 2:
                terms.add(seg)

        # 3. Title words (Chinese characters)
        title_chars = re.findall(r"[一-鿿]+", title)
        for word in title_chars:
            if len(word) >= 2:
                terms.add(word)
            for i in range(len(word) - 1):
                terms.add(word[i : i + 2])  # bigrams

        # 4. Content: extract Chinese keywords
        body = content[:8000]  # Index first 8K chars
        # Extract Chinese word-like sequences (1-4 chars)
        cn_seqs = re.findall(r"[一-鿿]{1,4}", body)
        # Count frequency
        freq: dict[str, int] = {}
        for s in cn_seqs:
            freq[s] = freq.get(s, 0) + 1
        # Keep terms that appear multiple times OR are length 3-4 (compound terms)
        for s, count in freq.items():
            if count >= 3 or (count >= 1 and len(s) >= 3):
                terms.add(s)
        # Always include single-character terms that appear frequently
        for s, count in freq.items():
            if len(s) == 1 and count >= 5:
                terms.add(s)

        # 5. Section headers / important markers in content
        for line in body.split("\n")[:100]:
            line = line.strip()
            if line.startswith("★") or line.startswith("✴") or line.startswith("##"):
                header_chars = re.findall(r"[一-鿿]{2,}", line)
                for w in header_chars:
                    terms.add(w)

        # Filter: keep only terms between 1-20 chars
        return {t for t in terms if 1 <= len(t) <= 20}

    # ── index loading ───────────────────────────────────────────

    def _load_index(self) -> bool:
        """Load index from disk into memory. Returns True on success."""
        if self._index is not None:
            return True
        if not _INDEX_PATH.exists():
            return False
        try:
            self._index = json.loads(_INDEX_PATH.read_text(encoding="utf-8"))
            return True
        except Exception:
            return False

    # ── index-based search ──────────────────────────────────────

    def _search_index(self, query: str, limit: int = 5, scope: str = "all") -> list[dict]:
        """Search using the precomputed inverted index with TF-IDF-like scoring."""
        idx = self._index
        if not idx:
            return []

        files_db = idx.get("files", {})
        if scope in ("ziwei", "bazi"):
            files_db = {k: v for k, v in files_db.items() if v.get("system", "ziwei") in (scope, "general")}
        inverted = idx.get("index", {})
        total_files = max(len(files_db), 1)

        # Tokenize query
        tokens = self._tokenize(query)
        if not tokens:
            return []

        # Score each file using TF-IDF-like weighting
        scores: dict[str, float] = {}
        files_matched_tokens: dict[str, int] = {}  # how many query tokens matched
        for token in tokens:
            matches = inverted.get(token, [])
            if not matches:
                continue

            # IDF: rare terms are more specific → higher weight
            df = max(len(matches), 1)
            idf = 1.0 + (total_files / df)

            for fname in matches:
                if fname not in files_db:
                    continue
                entry = files_db[fname]
                file_nterms = max(len(entry.get("terms", [])), 1)

                # Key insight: a file that matches many query tokens but has
                # proportionally few total terms is highly relevant (focused article).
                # A file with 1000+ terms that matches everything is a dictionary
                # and should be penalized.
                files_matched_tokens[fname] = files_matched_tokens.get(fname, 0) + 1

                # Jaccard-like precision: what fraction of matched tokens is the file?
                # Plus IDF weight and optional name boost
                name_boost = 3.0 if token in fname.lower() else 1.0
                scores[fname] = scores.get(fname, 0) + idf * name_boost

        # Normalize: penalize files with high term counts (general articles)
        # score = raw_score * (matched / sqrt(file_terms))
        # This gives focused articles (low file_terms) a significant boost
        for fname in list(scores.keys()):
            entry = files_db.get(fname, {})
            file_nterms = max(len(entry.get("terms", [])), 1)
            matched = files_matched_tokens.get(fname, 1)
            # Precision × Coverage: matched tokens over file term diversity
            quality = matched / (file_nterms ** 0.5)
            scores[fname] = scores[fname] * quality
            if entry.get("literature"):
                scores[fname] *= 1.6   # 典籍/方法论片段优先于网站文章

        if not scores:
            return []

        # Take top candidates from index and rerank by term proximity
        # (overview articles listing every palace score high on index matches
        #  but have terms scattered; focused articles have terms close together)
        candidates = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:20]
        reranked = []
        for fname, idx_score in candidates:
            content = self._read_file_content(fname)
            if not content:
                continue
            _, _, body = self._parse_file(Path(fname), content)
            prox_score = self._proximity_score(body, tokens)
            # Combine: index score selects candidates, proximity picks winners
            combined = idx_score * (0.1 + prox_score)
            reranked.append((combined, fname, body))

        # Sort by combined score descending
        ranked = sorted(reranked, key=lambda x: x[0], reverse=True)

        results = []
        for score, fname, body in ranked[:limit]:
            entry = files_db.get(fname, {})
            snippet = self._extract_snippet(body, query, 3000)

            results.append(
                {
                    "title": entry.get("title", Path(fname).stem),
                    "source": entry.get("source", ""),
                    "content": snippet,
                    "file": fname,
                    "score": round(score, 4),
                }
            )

        return results

    def _read_file_content(self, relpath: str) -> str:
        """Read file content from knowledge base, with caching."""
        if relpath in self._content_cache:
            return self._content_cache[relpath]
        f = _KB_PATH / relpath.replace("\\", "/")
        if f.exists():
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
                self._content_cache[relpath] = content
                return content
            except Exception:
                pass
        return ""

    # ── fallback: full-text scan search ─────────────────────────

    def _search_scan(self, query: str, limit: int = 5) -> list[dict]:
        """Fallback: brute-force scan all files (used when index unavailable)."""
        files = self._scan_files()
        tokens = self._tokenize(query)
        if not tokens or not files:
            return []

        scored = []
        for f in files:
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            score = 0
            fname_lower = str(f).lower()
            for t in tokens:
                if len(t) >= 2 and t in fname_lower:
                    score += 5
                if t in content:
                    score += 1

            if score > 0:
                density = score / max(len(content), 1000)
                scored.append((score * density, str(f), content))

        scored.sort(key=lambda x: x[0], reverse=True)

        results = []
        for score, fname, content in scored[:limit]:
            title, source, body = self._parse_file(Path(fname), content)
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

    # ── utilities ───────────────────────────────────────────────

    def _tokenize(self, text: str) -> set[str]:
        """Extract search tokens from a query string."""
        tokens = set()

        # Keep original query as-is for exact matching
        tokens.add(text.strip())

        # Chinese character unigrams + bigrams
        chars = re.findall(r"[一-鿿]", text)
        for c in chars:
            tokens.add(c)
        for i in range(len(chars) - 1):
            tokens.add(chars[i] + chars[i + 1])

        # Whole words (split by whitespace/punctuation)
        words = re.split(r"[\s,，。！？、；：""''（）　]+", text)
        for w in words:
            if len(w) >= 2:
                tokens.add(w)

        # Also try splitting common delimiters within Chinese text
        for w in list(tokens):
            if len(w) >= 4 and re.search(r"[一-鿿]{4,}", w):
                # Split into overlapping 2-3 char ngrams
                for i in range(len(w) - 1):
                    tokens.add(w[i : i + 2])

        return {t for t in tokens if 1 <= len(t) <= 20}

    def _proximity_score(self, body: str, tokens: set[str]) -> float:
        """Score by how close query tokens appear together in the text.

        A focused article about '命宫地劫' has these terms in the same paragraph.
        An overview listing all 12 palaces has them scattered pages apart.
        Returns a value in [0, 1] where higher = more proximate.
        """
        if not tokens or not body:
            return 0.0

        # Find positions of each token in the body
        token_positions: dict[str, list[int]] = {}
        for t in tokens:
            positions = [m.start() for m in re.finditer(re.escape(t), body)]
            if positions:
                token_positions[t] = positions

        if not token_positions:
            return 0.0

        # For each 1000-char sliding window, count how many unique tokens appear
        window_size = 1000
        step = 200
        best_density = 0
        for start in range(0, len(body), step):
            end = start + window_size
            window_text = body[start:end]
            hits = sum(1 for t in token_positions if t in window_text)
            density = hits / len(token_positions)  # 0..1
            if density > best_density:
                best_density = density

        return best_density

    def _extract_snippet(
        self, content: str, query: str, max_len: int = 3000
    ) -> str:
        """Extract the most relevant snippet from content around query terms."""
        if len(content) <= max_len:
            return content

        tokens = self._tokenize(query)
        best_pos = 0
        best_score = 0

        window = min(500, len(content))
        step = max(50, window // 4)
        for i in range(0, len(content) - window, step):
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


# Singleton
local_knowledge = LocalKnowledgeService()
