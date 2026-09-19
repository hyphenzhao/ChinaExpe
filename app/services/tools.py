"""Tool definitions and executor for LLM function calling.

Tools (all deterministic, engine-backed except search):
  get_chart(person)                     紫微命盘全文（生年四化/自化分开标注）
  get_horoscope(person, date)           大限/流年/流月/流日/流时 + 各级四化 + 流曜
  get_fly(person, palace)               某宫宫干飞四化 + 三方四正
  get_bazi(person)                      八字命盘（测测口径）
  get_bazi_timeline(person, date)       八字大运→流年→流月→流日链
  search_knowledge(query, scope)        知识库（典籍/文章/技能）检索
  propose_person_update(person, patch)  修改出生信息/设置（返回待确认 diff，前端确认后才生效）
  add_note(person, text)                给人物追加备注
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from ..engine import calendar as cal

_PERSON_PARAM = {"type": "string", "description": "人物标识（见 system prompt 中的人物列表）"}
_DATE_PARAM = {"type": "string", "description": "公历日期时间，格式 YYYY-MM-DD 或 YYYY-MM-DD HH:MM；省略则为当前时间"}

TOOLS = [
    {"type": "function", "function": {
        "name": "get_chart",
        "description": "获取某人的紫微斗数本命盘全文：十二宫星曜（含亮度、生年四化、离心/向心自化）、神煞、长生、大限区间、大限四化、备注。看盘前必须先调用。",
        "parameters": {"type": "object", "properties": {"person": _PERSON_PARAM}, "required": ["person"]}}},
    {"type": "function", "function": {
        "name": "get_horoscope",
        "description": "获取某人在指定日期的紫微运限：大限、小限、流年、流月、流日、流时的命宫落点、各级四化落宫与流曜。问某年/某月/某天运势时用。",
        "parameters": {"type": "object", "properties": {"person": _PERSON_PARAM, "date": _DATE_PARAM}, "required": ["person"]}}},
    {"type": "function", "function": {
        "name": "get_fly",
        "description": "飞星派用：获取某宫宫干飞出的四化（禄权科忌各飞到哪宫）以及该宫三方四正。",
        "parameters": {"type": "object", "properties": {"person": _PERSON_PARAM,
                                                        "palace": {"type": "string", "description": "宫名，如 命宫、夫妻宫、官禄宫"}},
                       "required": ["person", "palace"]}}},
    {"type": "function", "function": {
        "name": "get_bazi",
        "description": "获取某人的八字（子平）命盘：四柱、干神、藏干支神、纳音、空亡、地势、自坐、神煞、干支关系、五行旺衰、胎元命宫。",
        "parameters": {"type": "object", "properties": {"person": _PERSON_PARAM}, "required": ["person"]}}},
    {"type": "function", "function": {
        "name": "get_bazi_timeline",
        "description": "获取某人在指定日期的八字运限链：起运信息、大运序列、当前大运/流年/流月/流日/流时的干支、十神、地势、自坐、神煞。",
        "parameters": {"type": "object", "properties": {"person": _PERSON_PARAM, "date": _DATE_PARAM}, "required": ["person"]}}},
    {"type": "function", "function": {
        "name": "search_knowledge",
        "description": "检索命理知识库（紫微斗数全书、续道藏本、梁若瑜飞星问答、渊海子平、紫微麦文章、解盘方法论）。需要典籍依据、星曜/宫位/格局/四化/十神/神煞论述时使用；可多次换关键词检索。",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "关键词或短句，如 '武曲化忌 命宫'、'自化忌 飞星'、'食神制杀'"},
            "scope": {"type": "string", "enum": ["ziwei", "bazi", "all"], "description": "范围：ziwei=紫微, bazi=八字, all=全部（默认）"},
            "limit": {"type": "integer", "description": "返回条数，默认 5"}},
            "required": ["query"]}}},
    {"type": "function", "function": {
        "name": "propose_person_update",
        "description": "当用户要求修改某人的出生信息（时间/经度/性别/时辰）或排盘设置（流派选项）时调用。不会直接生效，而是生成待确认的修改，由用户在界面点击确认。",
        "parameters": {"type": "object", "properties": {
            "person": _PERSON_PARAM,
            "patch": {"type": "object", "description": "要修改的字段，如 {\"birth\": {\"solar\": \"2000-01-01 12:30\", \"longitude\": 121.5}} 或 {\"settings\": {\"ziwei\": {\"hua_table\": \"zhongzhou\"}}} 或 {\"display_name\": \"...\", \"gender\": \"女\"}"},
            "reason": {"type": "string", "description": "修改原因（一句话）"}},
            "required": ["person", "patch"]}}},
    {"type": "function", "function": {
        "name": "add_note",
        "description": "给某人的命盘追加一条备注（如已验证的事件、用户反馈、解盘结论），备注会随命盘一起提供给后续对话。",
        "parameters": {"type": "object", "properties": {"person": _PERSON_PARAM,
                                                        "text": {"type": "string", "description": "备注内容"}},
                       "required": ["person", "text"]}}},
]


def _parse_date(s: str | None) -> datetime:
    if not s:
        return datetime.now().replace(second=0, microsecond=0)
    try:
        dt = cal.parse_dt(s)
        return dt.replace(hour=12) if len(s.strip()) <= 10 else dt   # date only -> noon
    except ValueError:
        return datetime.now().replace(second=0, microsecond=0)


async def execute_tool(name: str, arguments: dict) -> dict:
    """Execute a tool.  Returns {content, error?, meta?}."""
    from .person_service import person_service as ps
    try:
        if name == "search_knowledge":
            return await _search_knowledge(arguments)
        pid = (arguments.get("person") or "").strip()
        if name in ("get_chart", "get_horoscope", "get_fly", "get_bazi", "get_bazi_timeline",
                    "propose_person_update", "add_note"):
            if not pid or not ps.get(pid):
                ids = ps.list_ids()
                return {"error": f"人物 '{pid}' 不存在。可用人物: {', '.join(ids)}", "content": f"人物 '{pid}' 不存在。可用人物: {', '.join(ids)}"}
        if name == "get_chart":
            return {"content": ps.ziwei_text(pid)}
        if name == "get_horoscope":
            return {"content": ps.horoscope_text(pid, _parse_date(arguments.get("date")))}
        if name == "get_fly":
            palace = arguments.get("palace", "命宫")
            if not palace.endswith("宫"):
                palace += "宫"
            palace = {"事业宫": "官禄宫", "奴仆宫": "交友宫", "仆役宫": "交友宫"}.get(palace, palace)
            return {"content": ps.fly_text(pid, palace)}
        if name == "get_bazi":
            return {"content": ps.bazi_text(pid)}
        if name == "get_bazi_timeline":
            return {"content": ps.bazi_timeline_text(pid, _parse_date(arguments.get("date")))}
        if name == "propose_person_update":
            patch = arguments.get("patch") or {}
            if isinstance(patch, str):
                try:
                    patch = json.loads(patch)
                except json.JSONDecodeError:
                    return {"error": "patch 必须是 JSON 对象", "content": "patch 必须是 JSON 对象"}
            person = ps.get(pid)
            current = {k: getattr(person, k) for k in patch if hasattr(person, k)}
            current = json.loads(json.dumps({k: (v.model_dump() if hasattr(v, "model_dump") else v) for k, v in current.items()}, ensure_ascii=False, default=str))
            text = (f"已生成对 {person.display_name}（{pid}）的修改建议，等待用户在界面确认后生效。\n"
                    f"原因: {arguments.get('reason', '')}\n当前值: {json.dumps(current, ensure_ascii=False)}\n"
                    f"修改为: {json.dumps(patch, ensure_ascii=False)}")
            return {"content": text, "meta": {"pending_update": {"person": pid, "patch": patch, "current": current,
                                                                 "reason": arguments.get("reason", "")}}}
        if name == "add_note":
            text = (arguments.get("text") or "").strip()
            if not text:
                return {"error": "备注为空", "content": "备注为空"}
            ps.add_note(pid, text, author="ai")
            return {"content": f"已为 {pid} 添加备注：{text}", "meta": {"note_added": {"person": pid, "text": text}}}
        return {"error": f"未知工具: {name}", "content": f"未知工具: {name}"}
    except Exception as e:  # never let a tool crash the stream
        return {"error": str(e), "content": f"工具执行失败: {e}"}


async def _search_knowledge(args: dict) -> dict:
    from .local_knowledge import local_knowledge
    from .knowledge_service import knowledge_service

    query = (args.get("query") or "").strip()
    scope = args.get("scope") or "all"
    limit = int(args.get("limit") or 5)
    if not query:
        return {"error": "缺少搜索关键词", "content": "缺少搜索关键词"}

    parts: list[str] = []
    meta: dict[str, Any] = {"local_count": 0, "vector_count": 0}
    seen_titles: set[str] = set()

    if local_knowledge.is_available():
        local_results, keywords = local_knowledge.search(query, limit=limit, scope=scope)
        if local_results:
            for r in local_results:
                seen_titles.add(r.get("title", ""))
            parts.append(local_knowledge.format_context(local_results, keywords))
            meta["local_count"] = len(local_results)
            meta["keywords"] = keywords

    if knowledge_service.is_available():
        db_results = await knowledge_service.query(query, limit=limit, scope=scope)
        db_results = [r for r in db_results if r.get("title", "") not in seen_titles]
        if db_results:
            parts.append(knowledge_service.format_rag_context(db_results))
            meta["vector_count"] = len(db_results)

    if not parts:
        return {"content": f"未找到与'{query}'相关的内容，请换关键词（例如只用星名+宫名，或只用十神/神煞名）。", "meta": meta}
    total = meta["local_count"] + meta["vector_count"]
    return {"content": f"搜索'{query}'找到 {total} 条相关内容：\n\n" + "\n".join(parts), "meta": meta}
