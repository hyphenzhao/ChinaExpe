"""Tool definitions and executor for LLM function calling.

Defines tools that the model can invoke: search_knowledge, read_skill, get_chart.
Each tool returns a dict with "content" (text feed to LLM) and optional metadata.
"""

import json
from typing import Optional

# ── Tool schemas (OpenAI/DeepSeek compatible) ───────────────────

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_knowledge",
            "description": (
                "搜索本地命理知识库，获取紫微斗数或八字相关的原文资料。"
                "当你需要查找某颗星曜、某个宫位、某个格局的具体论述时使用此工具。"
                "可以指定搜索来源：local(本地完整文章)、lancedb(向量知识库)、all(全部)。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索关键词，如'武曲化科 迁移宫'、'命宫地劫'、'天府星财帛宫'",
                    },
                    "source": {
                        "type": "string",
                        "enum": ["local", "lancedb", "all"],
                        "description": "搜索来源。local=本地完整文章(推荐), lancedb=向量知识库, all=全部",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_skill",
            "description": (
                "读取命理技能文件，获取紫微斗数或八字的排盘方法、星曜表、四化规则等专业知识。"
                "当需要了解具体技法（如安星诀、四化表、格局判断规则）时使用。"
                "可用技能: ziwei(紫微斗数), bazi_master(八字大师), ziping(子平正解), bazi(八字经典)。"
                "可选指定参考文件来获取更具体的内容。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "skill_name": {
                        "type": "string",
                        "enum": ["ziwei", "bazi_master", "ziping", "bazi"],
                        "description": "技能名称。ziwei=紫微斗数, bazi_master=八字大师, ziping=子平正解, bazi=八字经典",
                    },
                    "reference": {
                        "type": "string",
                        "description": "可选。要读取的参考文件名，如 stars, sihua, patterns, calculation, tiangan-dizhi, wuxing-tables",
                    },
                },
                "required": ["skill_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_chart",
            "description": (
                "获取某人的紫微斗数或八字十神命盘数据。"
                "当需要针对具体人物的命盘进行解读时使用。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "person": {
                        "type": "string",
                        "description": "人物标识，如 sjc, gy, zhf, zx",
                    },
                    "chart_type": {
                        "type": "string",
                        "enum": ["ziwei", "shishen"],
                        "description": "命盘类型。ziwei=紫微斗数, shishen=八字十神",
                    },
                },
                "required": ["person", "chart_type"],
            },
        },
    },
]


# ── Tool executor ────────────────────────────────────────────────

async def execute_tool(name: str, arguments: dict) -> dict:
    """Execute a tool by name and return its result.

    Returns a dict with:
        - content: text to feed back to the LLM
        - error: error message if execution failed
        - meta: optional metadata
    """
    if name == "search_knowledge":
        return await _search_knowledge(arguments)
    elif name == "read_skill":
        return _read_skill(arguments)
    elif name == "get_chart":
        return _get_chart(arguments)
    else:
        return {"error": f"未知工具: {name}", "content": ""}


async def _search_knowledge(args: dict) -> dict:
    """Execute search_knowledge tool."""
    from .local_knowledge import local_knowledge
    from .knowledge_service import knowledge_service

    query = args.get("query", "")
    source = args.get("source", "all")
    if not query:
        return {"error": "缺少搜索关键词", "content": ""}

    results = []
    meta = {"local_count": 0, "lancedb_count": 0}

    # Local knowledge base (complete articles)
    if source in ("local", "all") and local_knowledge.is_available():
        local_results, keywords = local_knowledge.search(query, limit=5)
        if local_results:
            ctx = local_knowledge.format_context(local_results, keywords)
            results.append(ctx)
            meta["local_count"] = len(local_results)

    # LanceDB vector search
    if source in ("lancedb", "all") and knowledge_service.is_available():
        db_results = await knowledge_service.query(query, limit=5)
        if db_results:
            ctx = knowledge_service.format_rag_context(db_results)
            results.append(ctx)
            meta["lancedb_count"] = len(db_results)

    if not results:
        return {
            "content": f"未找到与'{query}'相关的内容。请尝试调整搜索关键词。",
            "meta": meta,
        }

    total = meta["local_count"] + meta["lancedb_count"]
    header = f"搜索'{query}'共找到 {total} 条相关内容：\n\n"
    return {"content": header + "\n".join(results), "meta": meta}


def _read_skill(args: dict) -> dict:
    """Execute read_skill tool."""
    from .skill_loader import load_skill, SKILL_MAP

    skill_name = args.get("skill_name", "")
    reference = args.get("reference", "")

    if skill_name not in SKILL_MAP:
        return {
            "error": f"未知技能: {skill_name}。可用: {', '.join(SKILL_MAP.keys())}",
            "content": "",
        }

    skill_data = load_skill(skill_name)
    info = SKILL_MAP[skill_name]
    display = info.get("display", skill_name)

    parts = [f"## 技能: {display}\n"]

    # If reference specified, return just that reference
    if reference:
        ref_content = skill_data.get("references", {}).get(reference)
        if ref_content:
            parts.append(f"### {reference}\n{ref_content[:5000]}")
            return {"content": "\n".join(parts)}
        else:
            available = list(skill_data.get("references", {}).keys())
            parts.append(f"参考文件 '{reference}' 不存在。可用参考文件: {available}")
            return {"content": "\n".join(parts)}

    # Otherwise return SKILL.md body + available references list
    skill_md = skill_data.get("skill_md", {})
    desc = skill_md.get("description", "")
    body = skill_md.get("body", "")

    if desc:
        parts.append(f"**说明**: {desc}\n")
    if body:
        parts.append(body[:6000])

    refs = skill_data.get("references", {})
    if refs:
        parts.append(f"\n### 可用参考文件 ({len(refs)} 个)")
        for ref_name in sorted(refs.keys()):
            ref_len = len(refs[ref_name])
            parts.append(f"- {ref_name} ({ref_len} 字符)")

    return {"content": "\n".join(parts)}


def _get_chart(args: dict) -> dict:
    """Execute get_chart tool."""
    from .chart_service import get_ziwei_grid, get_shishen_data

    person = args.get("person", "")
    chart_type = args.get("chart_type", "ziwei")

    if not person:
        return {"error": "缺少人物标识", "content": ""}

    if chart_type == "ziwei":
        data = get_ziwei_grid(person)
        if not data:
            return {
                "content": f"未找到 {person} 的紫微斗数命盘。请先在人物管理中导入命盘。"
            }
        # Compact: just show key info, not the full JSON
        basic = data.get("basic_info", {})
        palaces = data.get("palaces", [])
        summary = [f"## {person} 紫微斗数命盘\n"]
        if basic:
            summary.append(
                f"出生: {basic.get('display_name', person)} "
                f"({basic.get('birth_date', '?')})"
            )
            summary.append(f"五行局: {basic.get('wuxing_ju', '?')}")
            summary.append(f"命主: {basic.get('ming_zhu', '?')} 身主: {basic.get('shen_zhu', '?')}")
        summary.append(f"\n十二宫概览 ({len(palaces)} 宫):")
        for p in palaces:
            stars_str = ", ".join(
                s["name"] + (f"({s.get('brightness','')})" if s.get("brightness") else "")
                + (f"[{s.get('transform','')}]" if s.get("transform") else "")
                for s in p.get("stars", [])[:4]
            )
            ext = f" +{len(p.get('stars',[]))-4}" if len(p.get("stars", [])) > 4 else ""
            summary.append(
                f"  {p.get('name','?')}({p.get('stem_branch','')}): "
                f"{stars_str}{ext}"
            )
        return {"content": "\n".join(summary), "meta": {"full_data_available": True}}
    else:
        data = get_shishen_data(person)
        if not data:
            return {
                "content": f"未找到 {person} 的八字十神命盘。请先在人物管理中导入命盘。"
            }
        summary = [f"## {person} 八字十神命盘\n"]
        summary.append(f"日主: {data.get('day_master', '?')}")
        summary.append(f"四柱: {' '.join(data.get('heavenly_stems', []))} / {' '.join(data.get('earthly_branches', []))}")
        if data.get("shishen"):
            summary.append(f"十神: {json.dumps(data['shishen'], ensure_ascii=False)}")
        return {"content": "\n".join(summary), "meta": {"full_data_available": True}}
