"""Agent service — system prompt + message assembly.

The prompt is deliberately slim.  Chart data comes from the engine (never from
hand-edited JSON), knowledge comes through the search tool.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from ..engine import calendar as cal
from .knowledge_service import knowledge_service
from .local_knowledge import local_knowledge
from .person_service import person_service

CST = timezone(timedelta(hours=8))


def _now_context() -> str:
    now = datetime.now(CST).replace(tzinfo=None)
    li = cal.lunar_info(now)
    ec = cal.eight_char(now)
    return (f"当前时间：{now:%Y年%m月%d日 %H:%M}（北京时间，星期{'一二三四五六日'[now.weekday()]}）\n"
            f"农历：{li.text}；节气干支：{ec.getYear()}年 {ec.getMonth()}月 {ec.getDay()}日")


SKILL_FILE = Path(__file__).resolve().parent.parent / "prompts" / "jiepan.md"


def _skill_text() -> str:
    """解盘技能：讲法、铁律、工具分工、回答结构（app/prompts/jiepan.md，可直接编辑）。"""
    try:
        return SKILL_FILE.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


_ROLE = """你是「玄学助手」，精通紫微斗数（三合派为主，兼通飞星派宫干四化与钦天四化派的生年四化/自化）与子平八字。
你的排盘全部由程序引擎按文墨天机默认口径计算（真太阳时、正月初一分年、全书四化表），你**绝不自行推算安星或起大运**，一切盘面数据以工具返回为准。

工具：
- get_chart：紫微本命盘全文（含生年四化、↓离心自化、↑向心自化、神煞、大限四化）。看盘前先调用一次。
- get_horoscope：指定日期的大限/小限/流年/流月/流日/流时（各级四化落宫 + 流曜）。问运势必用。
- get_fly：某宫宫干飞四化与三方四正（飞星派追事件链时用）。
- get_bazi / get_bazi_timeline：八字命盘与大运流年流月流日链。
- search_knowledge：典籍切片与现代文章的混合检索（全书、续道藏本、梁若瑜飞星问答、渊海子平、紫微麦、解盘方法论）。
- list_classics / search_classics / read_classic：本机典籍**全文**（另含三命通会、滴天髓阐微、子平真诠评注、神峰通考、星平会海）。要给出可核对的出处时用这三个，引用写 路径:行号。
- propose_person_update / add_note：用户要求修改出生信息、设置或记录备注时使用。

解盘流程：
1. 先取盘（get_chart / get_bazi），必要时取运限；2. 明确用哪一派的口径并说明（三合看星曜庙旺与三方四正；飞星看宫干飞化；四化派看生年四化与自化、来因宫）；3. 用 search_knowledge 找典籍/文章依据并引用；4. 落到具体宫位/星曜/时间给结论，吉凶并陈，凶象转译为风险与课题；5. 给出可验证的时间点，欢迎用户反馈以修正。

表达：术语首次出现用现代汉语解释；不要恐吓、不要绝对化；命盘展示的是倾向而非命定。
"""


class AgentService:
    async def build_messages(self, user_message: str, mode: str, person: Optional[str] = None,
                             selected_context: Optional[dict] = None, history: Optional[list[dict]] = None,
                             view_context: Optional[dict] = None) -> tuple[list[dict], dict]:
        meta = {"chart_loaded": False, "person": person}
        system = self._system_prompt(mode, person, meta)
        messages = [{"role": "system", "content": system}]
        for msg in (history or [])[-24:]:
            if msg.get("role") in ("user", "assistant") and msg.get("content"):
                messages.append({"role": msg["role"], "content": msg["content"]})
        messages.append({"role": "user", "content": self._user_message(user_message, selected_context, view_context)})
        return messages, meta

    def _system_prompt(self, mode: str, person: Optional[str], meta: dict) -> str:
        parts = [f"## 当前时间\n{_now_context()}\n", _ROLE]
        skill = _skill_text()
        if skill:
            parts.append(skill)
        people = person_service.list_summaries()
        if people:
            parts.append("## 人物列表\n" + "\n".join(
                f"- {p.id}：{p.display_name}，{p.yinyang_gender or p.gender}，{p.birth_solar}，{p.lunar}，{p.bureau}" for p in people))
        if person and person_service.get(person):
            p = person_service.get(person)
            a = None
            try:
                a = person_service.astrolabe(person)
            except Exception:
                pass
            if a:
                meta["chart_loaded"] = True
                soul = a.palaces[a.soul_index]
                major = "、".join(s.name + (f"[{s.brightness}]" if s.brightness else "") for s in soul.stars if s.category == "major") or "无主星(借对宫)"
                parts.append(
                    f"## 当前人物：{p.display_name}（{person}）\n"
                    f"{'阳' if a.yang_year else '阴'}{p.gender}，{a.solar:%Y-%m-%d %H:%M}（真太阳时 {a.true_solar:%H:%M}），{a.lunar.text}，"
                    f"四柱 {' '.join(a.pillars.jieqi)}，{a.bureau}，命宫{soul.ganzhi}坐{major}，身宫在{a.palaces[a.body_index].name}，"
                    f"生年四化 {'、'.join(f'{s}化{h}' for h, s in a.birth_hua.items())}。\n"
                    f"完整盘面请用 get_chart / get_bazi 获取；运限用 get_horoscope / get_bazi_timeline。")
                if p.notes:
                    parts.append("### 备注\n" + "\n".join(f"- [{n.ts[:10]}] {n.text}" for n in p.notes[-8:]))
        parts.append(f"\n## 数据源状态\n- 本地知识库: {'✅' if local_knowledge.is_available() else '❌'}"
                     f"\n- 向量知识库: {'✅' if knowledge_service.is_available() else '❌'}")
        return "\n".join(parts)

    def _user_message(self, content: str, selected_context: Optional[dict], view_context: Optional[dict]) -> str:
        ctx = []
        sc = selected_context or {}
        for r in sc.get("refs") or []:
            if not isinstance(r, dict):
                continue
            stars = "、".join(list(r.get("major") or []) + list(r.get("minor") or [])) or "空宫"
            adj = "、".join(r.get("adjective") or [])
            ctx.append(f"引用宫位 {r.get('palace')}[{r.get('ganzhi')}]（{r.get('role')}）：{stars}"
                       + (f"；小星 {adj}" if adj else "") + (f"；长生{r.get('changsheng')}" if r.get("changsheng") else "")
                       + (f"；大限{r.get('decadal')}" if r.get("decadal") else ""))
        if sc.get("palace"):
            ctx.append(f"选中宫位: {sc['palace']}{('·' + sc['stem_branch']) if sc.get('stem_branch') else ''}")
        if sc.get("star"):
            ctx.append(f"选中星曜: {sc['star']}{('（' + sc['brightness'] + '）') if sc.get('brightness') else ''}")
        if sc.get("pillar"):
            ctx.append(f"选中柱: {sc['pillar']}")
        if sc.get("stem"):
            ctx.append(f"选中天干: {sc['stem']}{('（' + sc['shishen'] + '）') if sc.get('shishen') else ''}")
        vc = view_context or {}
        if vc.get("chart"):
            ctx.append(f"当前视图: {vc['chart']}")
        if vc.get("layer"):
            ctx.append(f"图层: {vc['layer']}")
        if vc.get("level"):
            ctx.append(f"当前运限: {vc['level']}")
        if vc.get("date"):
            ctx.append(f"当前日期: {vc['date']}")
        if vc.get("selected_palace"):
            ctx.append(f"当前宫位: {vc['selected_palace']}")
        if not ctx:
            return content
        return content + "\n\n---\n（界面上下文）\n" + "\n".join(f"- {c}" for c in ctx)


agent_service = AgentService()
