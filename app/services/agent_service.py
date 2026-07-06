"""Agent service - assemble system prompts with skills, chart data, and RAG context."""
import json
from datetime import datetime, timezone, timedelta
from typing import Optional

from .knowledge_service import knowledge_service
from .local_knowledge import local_knowledge
from .chart_service import get_ziwei_grid, get_shishen_data

# China timezone
CST = timezone(timedelta(hours=8))


def _now_context() -> str:
    """Build current time context, mimicking OpenClaw's date injection."""
    now = datetime.now(CST)
    lunar_year_stems = ["甲","乙","丙","丁","戊","己","庚","辛","壬","癸"]
    lunar_year_branches = ["子","丑","寅","卯","辰","巳","午","未","申","酉","戌","亥"]
    # Rough lunar year: 2026-02-17 is Chinese New Year 2026 (丙午)
    # For simplicity, use a lookup
    year_gan = (now.year + 6) % 10  # 2024=甲辰(41), 2025=乙巳(42), 2026=丙午(43)
    year_zhi = (now.year + 8) % 12
    lunar_year = lunar_year_stems[year_gan % 10] + lunar_year_branches[year_zhi % 12]
    return (
        f"当前时间：{now.strftime('%Y年%m月%d日 %H:%M')}（北京时间）\n"
        f"农历年份：{lunar_year}年\n"
        f"星期：{'一二三四五六日'[now.weekday()]}"
    )


# Slim role prompt — skills/knowledge loaded on-demand via tools
_SLIM_ROLE_PROMPT = (
    "你是一位精通紫微斗数、子平命理（八字十神）的专业玄学助手。\n"
    "你可以使用以下工具来获取需要的信息：\n"
    "- **search_knowledge**: 搜索本地知识库获取原文资料（紫微麦文章、古籍经典等）\n"
    "- **read_skill**: 读取命理技能文件（星曜表、四化规则、排盘方法等）\n"
    "- **get_chart**: 获取命盘数据\n\n"
    "工作方式：\n"
    "1. 先理解用户的问题，确定需要查什么\n"
    "2. 使用工具搜索相关知识库原文和技能资料\n"
    "3. 引用原文，结合命盘数据给出专业解读\n"
    "4. 如果搜索结果不相关，换关键词再搜\n\n"
    "重要：回答时先引用原文片段（标明出处），再对照命盘解读。不要凭空断言。\n"
)

_TONE_SECTION = (
    "\n## 回答风格与边界\n"
    "- 客观平衡：吉凶如实解读，不刻意只说好话\n"
    "- 引用原文：搜索到原文后先引用再解读\n"
    "- 凶象转译：凶象转译为风险、课题，不恐吓\n"
    "- 解释边界：命盘展示倾向而非绝对命定\n"
    "- 专业清晰：术语首次出现时用现代汉语解释\n"
)

_TOOLS_HINT = (
    "\n## 可用数据源\n"
    "- 本地知识库（紫微麦完整原文）: {local_avail}\n"
    "- 向量知识库（LanceDB）: {lancedb_avail}\n"
)


class AgentService:
    """Assembles the system prompt and message context for different modes."""

    async def build_messages(
        self,
        user_message: str,
        mode: str,
        person: Optional[str] = None,
        selected_context: Optional[dict] = None,
        history: Optional[list[dict]] = None,
    ) -> tuple[list[dict], dict]:
        """Build the full message list including system prompt and context.

        Returns:
            (messages, meta) where meta contains info about what was loaded
        """
        messages = []
        meta = {"skills_loaded": [], "rag_results": 0, "local_results": 0, "local_keywords": [], "chart_loaded": False}

        # 1. Build system prompt (pass user_message for RAG query)
        system_content = await self._build_system_prompt(mode, person, user_message, meta)

        messages.append({"role": "system", "content": system_content})

        # 2. Add chat history
        if history:
            for msg in history[-20:]:
                if msg.get("role") in ("user", "assistant"):
                    messages.append({
                        "role": msg["role"],
                        "content": msg.get("content", ""),
                    })

        # 3. Build user message with context
        full_message = self._build_user_message(user_message, mode, selected_context)
        messages.append({"role": "user", "content": full_message})

        return messages, meta

    async def _build_system_prompt(
        self, mode: str, person: Optional[str], user_message: str, meta: dict
    ) -> str:
        """Build a slim system prompt (~3K chars).

        Skills and knowledge are loaded on-demand via tool calls, not eagerly
        stuffed into the prompt. Only essential context (time, role, tone,
        chart data) is included upfront.
        """
        chart_type = None
        if mode == "chart_ziwei":
            chart_type = "ziwei"
        elif mode == "chart_shishen":
            chart_type = "shishen"

        parts = [
            f"## 当前时间\n{_now_context()}\n",
            _SLIM_ROLE_PROMPT,
        ]

        # Chart data — still included eagerly since it's essential context
        if chart_type and person:
            chart_context = self._get_chart_context(chart_type, person)
            if chart_context:
                meta["chart_loaded"] = True
                parts.append("\n## 当前命盘数据\n")
                parts.append(chart_context)

        # Tone and style guidance
        parts.append(_TONE_SECTION)

        # Available tools hint
        parts.append(_TOOLS_HINT.format(
            local_avail="✅" if local_knowledge.is_available() else "❌",
            lancedb_avail="✅" if knowledge_service.is_available() else "❌",
        ))

        return "\n".join(parts)

    def _get_chart_context(self, chart_type: str, person: str) -> str:
        """Get compact chart summary for the system prompt.

        Full detailed chart data can be retrieved via get_chart tool.
        This summary gives the LLM enough context to start analysis.
        """
        if not person:
            return ""
        if chart_type == "ziwei":
            grid = get_ziwei_grid(person)
            if not grid:
                return ""
            basic = grid.get("basic_info", {})
            palaces = grid.get("palaces", [])
            lines = [
                f"命主: {person} ({basic.get('display_name', person)})",
                f"五行局: {basic.get('wuxing_ju', '?')}",
                f"命主星: {basic.get('ming_zhu', '?')}  身主星: {basic.get('shen_zhu', '?')}",
                "",
                "十二宫概要:",
            ]
            for p in palaces:
                stars = []
                for s in p.get("stars", []):
                    parts_list = [s["name"]]
                    if s.get("brightness"):
                        parts_list.append(f"({s['brightness']})")
                    if s.get("transform"):
                        parts_list.append(f"[{s['transform']}]")
                    stars.append("".join(parts_list))
                stars_str = " · ".join(stars[:5])
                if len(p.get("stars", [])) > 5:
                    stars_str += f" 等{len(p['stars'])}星"
                lines.append(
                    f"  {p.get('name','?')}({p.get('stem_branch','')}): {stars_str}"
                )
            return "\n".join(lines)
        else:
            data = get_shishen_data(person)
            if not data:
                return ""
            lines = [
                f"命主: {person}",
                f"日主: {data.get('day_master', '?')}",
                f"四柱天干: {' '.join(data.get('heavenly_stems', []))}",
                f"四柱地支: {' '.join(data.get('earthly_branches', []))}",
            ]
            hs = data.get("hidden_stems", [])
            if hs:
                hs_str = " / ".join(" ".join(h) for h in hs if h)
                lines.append(f"藏干: {hs_str}")
            shishen = data.get("shishen", {})
            if shishen:
                lines.append(f"十神: {json.dumps(shishen, ensure_ascii=False)}")
            return "\n".join(lines)

    def _build_rag_query(self, chart_type: str, person: str, user_message: str = "") -> Optional[str]:
        """Build a RAG query combining the user's question with chart structure.

        The user's actual question is the primary signal for vector search.
        Chart structure (palace stars, day master) is added as supplementary
        context to improve relevance.
        """
        # Build chart context suffix
        chart_suffix = ""
        if person and chart_type == "ziwei":
            grid = get_ziwei_grid(person)
            if grid:
                # Collect star names from all palaces for broader context
                all_stars = set()
                ming_stars = []
                for p in grid.get("palaces", []):
                    for s in p.get("stars", []):
                        all_stars.add(s["name"])
                    if p.get("name") == "命宫":
                        ming_stars = [s["name"] for s in p.get("stars", [])[:5]]
                if ming_stars:
                    chart_suffix = f" 命宫{' '.join(ming_stars)}"
        elif person and chart_type == "shishen":
            data = get_shishen_data(person)
            if data:
                day_master = data.get("day_master", "")
                if day_master:
                    chart_suffix = f" 日主{day_master}"

        # User question is the primary query; chart context supplements it
        if user_message:
            return f"{user_message}{chart_suffix}"
        elif chart_suffix:
            return f"{chart_type} {chart_suffix} 解析"
        return None

    def _build_user_message(
        self,
        content: str,
        mode: str,
        selected_context: Optional[dict] = None,
    ) -> str:
        """Build the full user message with context tags."""
        if not selected_context:
            return content

        parts = [content]

        context_parts = []
        if selected_context.get("palace"):
            sb = selected_context.get("stem_branch", "")
            context_parts.append(f"宫位: {selected_context['palace']}{'·'+sb if sb else ''}")
        if selected_context.get("star"):
            star = selected_context["star"]
            brightness = selected_context.get("brightness", "")
            transform = selected_context.get("transform", "")
            star_str = f"星曜: {star}"
            if brightness:
                star_str += f"（{brightness}）"
            if transform:
                star_str += f" [{transform}]"
            context_parts.append(star_str)
        if selected_context.get("pillar"):
            context_parts.append(f"柱: {selected_context['pillar']}")
        if selected_context.get("stem"):
            shishen = selected_context.get("shishen", "")
            stem_str = f"天干: {selected_context['stem']}"
            if shishen:
                stem_str += f"（{shishen}）"
            context_parts.append(stem_str)

        if context_parts:
            parts.append("\n---\n" + "\n".join(f"- {c}" for c in context_parts))

        return "\n".join(parts)


# Singleton
agent_service = AgentService()
