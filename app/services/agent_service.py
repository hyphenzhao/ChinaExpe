"""Agent service - assemble system prompts with skills, chart data, and RAG context."""
import json
from datetime import datetime, timezone, timedelta
from typing import Optional

from .skill_loader import get_skill_context_for_prompt
from .knowledge_service import knowledge_service
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
        meta = {"skills_loaded": [], "rag_results": 0, "chart_loaded": False}

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

    async def _build_system_prompt(self, mode: str, person: Optional[str], user_message: str, meta: dict) -> str:
        """Build the system prompt based on mode. Populates meta with usage info.

        The user_message is used as the PRIMARY query for RAG retrieval so
        that knowledge base results are actually relevant to the question.
        """
        if mode == "theory":
            system = f"## 当前时间\n{_now_context()}\n\n" + get_skill_context_for_prompt("theory")
            meta["skills_loaded"] = ["通用玄学"]
            # RAG: use user's actual question for search
            if knowledge_service.is_available():
                results = await knowledge_service.query(user_message, limit=8)
                if results:
                    rag_context = knowledge_service.format_rag_context(results)
                    meta["rag_results"] = len(results)
                    system += "\n" + rag_context
            return system

        chart_type = "ziwei" if mode == "chart_ziwei" else "shishen"
        if chart_type == "ziwei":
            meta["skills_loaded"] = ["紫微斗数"]
        else:
            meta["skills_loaded"] = ["八字大师", "子平正解"]

        # Load skill context
        skill_context = get_skill_context_for_prompt(chart_type)

        # Build chart data context
        chart_context = ""
        if person:
            chart_context = self._get_chart_context(chart_type, person)
            if chart_context:
                meta["chart_loaded"] = True

        # Build RAG context — combine user question with chart structure
        rag_context = ""
        if knowledge_service.is_available():
            rag_query = self._build_rag_query(chart_type, person, user_message)
            if rag_query:
                results = await knowledge_service.query(rag_query, limit=8)
                if results:
                    rag_context = knowledge_service.format_rag_context(results)
                    meta["rag_results"] = len(results)

        # Assemble
        parts = [f"## 当前时间\n{_now_context()}\n", skill_context]

        if chart_context:
            parts.append("\n## 当前命盘数据\n")
            parts.append(chart_context)

        if rag_context:
            parts.append(rag_context)

        parts.append(
            "\n\n## 回答风格与边界（最高优先级）\n"
            "- **客观平衡**：吉凶都要如实解读，不要只说好听的话，也不要刻意吓人，要客观中立\n"
            "- **引用原文优先**：如果系统提示中包含知识库参考内容或技能参考文件，请**先引用原文片段**，再结合命盘数据进行解读。用「紫微麦原文」或「根据经典」来标明引用来源\n"
            "- **凶象转译**：凶象、煞忌、冲克要转译为风险、课题、代价、需要注意之处，而非恐吓式、宿命式表述\n"
            "- **解释边界**：命盘展示的是倾向、结构与课题，不是不可改变的命令；不说「注定如此」「无法改变」\n"
            "- **结论依据**：每个判断都要有推演过程支撑，先分析命盘结构再下结论，不凭空断言\n"
            "- **专业清晰**：术语第一次出现时用现代汉语解释，不堆砌古诀，不空泛玄谈\n"
            "\n"
            "## 回答格式要求\n"
            "- 涉及宫位、星曜、四化、十神、五行等结构化信息时，**默认使用 Markdown 表格**呈现\n"
            "- 如用户明确要求不用表格，则尊重用户偏好\n"
            "- 所有时间计算以当前日期为基准，务必使用上面提供的当前时间\n"
            "- 回复结构：如果知识库提供了相关原文，采用「**引用原文 → 命盘对照 → 综合解读**」的三段式结构\n"
            "- 请基于以上技能知识、命盘数据和知识库参考，为用户提供专业、客观、有据的玄学解析。\n"
            "\n"
            "> 温馨提示：命理属于中华传统文化系统，本解读用于提供自我观察、关系理解与人生规划的参考视角。"
            "命盘呈现的是结构与倾向，不是不可改变的命令；后天选择、环境与持续行动同样重要。"
            "重大决策仍需结合现实条件，理性判断。"
        )

        return "\n".join(parts)

    def _get_chart_context(self, chart_type: str, person: str) -> str:
        """Get chart data as formatted context for the system prompt."""
        if not person:
            return ""
        if chart_type == "ziwei":
            grid = get_ziwei_grid(person)
            if not grid:
                return ""
            return json.dumps(grid, ensure_ascii=False, indent=2)
        else:
            data = get_shishen_data(person)
            if not data:
                return ""
            return json.dumps(data, ensure_ascii=False, indent=2)

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
