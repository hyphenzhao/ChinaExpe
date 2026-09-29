"""Tool definitions and executor for LLM function calling.

Tools (all deterministic, engine-backed except search):
  get_chart(person)                     紫微命盘全文（生年四化/自化分开标注）
  get_horoscope(person, date)           大限/流年/流月/流日/流时 + 各级四化 + 流曜
  get_fly(person, palace)               某宫宫干飞四化 + 三方四正
  get_bazi(person)                      八字命盘（测测口径）
  get_bazi_timeline(person, date)       八字大运→流年→流月→流日链
  search_knowledge(query, scope)        知识库（典籍切片/文章）混合检索
  list_classics()                       本机典籍清单（data/classics 全文）
  search_classics(query, book)          典籍全文正则检索，返回 路径:行号
  read_classic(path, start, end)        按行号区间读典籍原文
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
        "name": "get_ziwei_patterns",
        "description": "紫微格局（代码判定的成格方向，未判破格）以及命宫三方四正与夹宫里的煞、忌、空亡、落陷等事实。做格局或破格分析时先调用。",
        "parameters": {"type": "object", "properties": {"person": _PERSON_PARAM}, "required": ["person"]}}},
    {"type": "function", "function": {
        "name": "get_bazi_analysis",
        "description": "子平量化分析（代码计算）：身强身弱与同类占比、得令得地得势、五行力量、十神占比、格局候选与百分比、特殊格门槛、喜忌用神排序及理由。",
        "parameters": {"type": "object", "properties": {"person": _PERSON_PARAM}, "required": ["person"]}}},
    {"type": "function", "function": {
        "name": "get_life_events",
        "description": "人生喜事（代码计算）：结婚、发财、高升、搬迁、添丁、高中六类事件未来最强年份与农历月份、往年强年；指定 event 时附逐条引动证据。",
        "parameters": {"type": "object", "properties": {
            "person": _PERSON_PARAM,
            "event": {"type": "string", "enum": ["结婚", "发财", "高升", "搬迁", "添丁", "高中"], "description": "只看某一类，附证据"}},
            "required": ["person"]}}},
    {"type": "function", "function": {
        "name": "get_chart_variant",
        "description": "相邻日期或时辰的候选盘（紫微 + 八字文字版，不落盘）。slots 为时辰位偏移，一天 13 位：早子、丑…亥、晚子，跨日自动处理；days 为日期偏移。反推时辰时用来比对候选。",
        "parameters": {"type": "object", "properties": {
            "person": _PERSON_PARAM,
            "slots": {"type": "integer", "description": "时辰位偏移，如 -1 前一个时辰，1 后一个时辰"},
            "days": {"type": "integer", "description": "日期偏移"}},
            "required": ["person"]}}},
    {"type": "function", "function": {
        "name": "get_rectify_candidates",
        "description": "反推时辰的候选时辰评分表（代码计算）：按用户已保存的经历（结婚、头胎、离家、父母变故等）给每个候选时辰打分并排序，附证据与置信度。",
        "parameters": {"type": "object", "properties": {
            "person": _PERSON_PARAM,
            "approx_time": {"type": "string", "description": "大致出生时间 HH:MM（钟表时间），有则只比前后各两个时辰"}},
            "required": ["person"]}}},
    {"type": "function", "function": {
        "name": "save_life_facts",
        "description": "把用户在对话里说出的经历记到人物档案（反推时辰用），如 {\"marriage_year\": 2015, \"children\": 1, \"first_child_sex\": \"男\"}。字段名见问卷；不改出生信息。",
        "parameters": {"type": "object", "properties": {
            "person": _PERSON_PARAM,
            "facts": {"type": "object", "description": "要合并保存的经历字段"}},
            "required": ["person", "facts"]}}},
    {"type": "function", "function": {
        "name": "list_classics",
        "description": "列出本机典籍全文清单（紫微斗数全书、续道藏本、梁若瑜飞星问答、渊海子平、三命通会、滴天髓阐微、子平真诠评注、神峰通考、星平会海等），含路径与行数。不确定有哪些书、该引哪本时先调用。",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "search_classics",
        "description": "在典籍全文里检索原文（支持正则），返回 路径:行号 与上下文。需要给出可核对的出处、抄录原句时用；与 search_knowledge 的区别是它读的是整本书而不是切片。",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "关键词或正则，如 '武曲.{0,6}化忌'、'食神制杀'、'自化忌'"},
            "book": {"type": "string", "description": "限定某本书，可填书名片段，如 '三命通会'、'梁若瑜'、'全书'；省略则搜全部"},
            "limit": {"type": "integer", "description": "返回条数，默认 8，最多 40"}},
            "required": ["query"]}}},
    {"type": "function", "function": {
        "name": "read_classic",
        "description": "按行号区间读典籍原文，确认上下文、避免断章。路径用 search_classics 或 list_classics 返回的那个。",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "description": "如 data/classics/03-子平/三命通会.md"},
            "start_line": {"type": "integer", "description": "起始行，从 1 开始"},
            "end_line": {"type": "integer", "description": "结束行，最多一次读 400 行"}},
            "required": ["path"]}}},
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
        if name in ("list_classics", "search_classics", "read_classic"):
            from . import classics_service as cs
            if name == "list_classics":
                return {"content": cs.list_books_text(), "meta": {"books": len(cs.list_books())}}
            if name == "search_classics":
                q = (arguments.get("query") or "").strip()
                if not q:
                    return {"error": "缺少检索词", "content": "缺少检索词"}
                hits = cs.search(q, arguments.get("book") or "", int(arguments.get("limit") or 8))
                return {"content": cs.search_text(q, arguments.get("book") or "", int(arguments.get("limit") or 8)),
                        "meta": {"hits": len(hits), "query": q}}
            path = (arguments.get("path") or "").strip()
            return {"content": cs.read_lines(path, arguments.get("start_line") or 1, arguments.get("end_line")),
                    "meta": {"path": path}}
        pid = (arguments.get("person") or "").strip()
        if name in ("get_chart", "get_horoscope", "get_fly", "get_bazi", "get_bazi_timeline",
                    "propose_person_update", "add_note", "get_ziwei_patterns", "get_bazi_analysis",
                    "get_life_events", "get_chart_variant", "get_rectify_candidates", "save_life_facts"):
            if not pid or not ps.get(pid):
                ids = ps.list_ids()
                return {"error": f"人物 '{pid}' 不存在。可用人物: {', '.join(ids)}", "content": f"人物 '{pid}' 不存在。可用人物: {', '.join(ids)}"}
        if name == "get_chart":
            return {"content": ps.ziwei_text(pid)}
        if name == "get_ziwei_patterns":
            from .person_service import patterns_text, detect_patterns
            return {"content": patterns_text(detect_patterns(ps.astrolabe(pid)))}
        if name == "get_bazi_analysis":
            from .person_service import bazi_analysis_text
            return {"content": bazi_analysis_text(ps.bazi(pid).get("analysis"))}
        if name == "get_life_events":
            return {"content": ps.life_events_text(pid, arguments.get("event") or None)}
        if name == "get_rectify_candidates":
            from .rectify_service import rectify_text
            return {"content": rectify_text(pid, {"approx_time": arguments.get("approx_time")})}
        if name == "save_life_facts":
            facts = arguments.get("facts") or {}
            if isinstance(facts, str):
                facts = json.loads(facts)
            person = ps.get(pid)
            person.life_facts = {**(person.life_facts or {}), **{k: v for k, v in facts.items() if v not in (None, "")}}
            ps.save(person)
            return {"content": f"已记录经历：{json.dumps(facts, ensure_ascii=False)}", "meta": {"facts_saved": facts}}
        if name == "get_chart_variant":
            return {"content": ps.variant_text(pid, int(arguments.get("days") or 0), int(arguments.get("slots") or 0))}
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
