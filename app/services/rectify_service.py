"""反推时辰：代码控制的引导式问卷 + 候选时辰逐一打分。

排名全部来自这里；AI 只读评分表和候选盘做解读、补问。
- 有年份的经历（结婚、头胎、离家、升职、上榜、进财）：查该候选盘里这一年在对应事件中的百分位，权重 3。
- 离异、父母变故：看父母宫与夫妻宫的化忌、煞、日月落陷，权重 2。
- 头胎男女、兄弟姐妹：民间经验，证据弱，权重 1 与 0.5。
- 文字描述（六亲关系、外貌、性格）不打分，原样交给 AI。
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

from ..engine import timeshift as TS
from ..engine.ziwei import horoscope as H
from ..engine.ziwei.events import year_table
from ..engine.ziwei.view import DARK, KONG, SHA, from_astrolabe
from .person_service import person_service as ps

VERSION = "rect-1"

# show_if：{字段: 取值}，取值以 ">0" 表示数量大于 0，"!否" 表示不等于「否」
QUESTIONS: list[dict] = [
    {"id": "approx_known", "type": "choice", "q": "知道大致的出生时段吗？", "options": ["知道", "不知道"]},
    {"id": "approx_time", "type": "time", "q": "大致出生时间（钟表时间）", "show_if": {"approx_known": "知道"}},
    {"id": "siblings", "type": "number", "q": "有几个兄弟姐妹（不含自己）？"},
    {"id": "sibling_detail", "type": "text", "q": "他们是男是女、比你大还是小？", "show_if": {"siblings": ">0"}},
    {"id": "married", "type": "choice", "q": "结婚了吗？", "options": ["是", "否"]},
    {"id": "marriage_year", "type": "year", "q": "哪一年结婚（或开始同居）？", "show_if": {"married": "是"}},
    {"id": "divorced", "type": "choice", "q": "是否离过婚？", "options": ["否", "是"], "show_if": {"married": "是"}},
    {"id": "divorce_year", "type": "year", "q": "哪一年离婚？", "show_if": {"divorced": "是"}},
    {"id": "children", "type": "number", "q": "有几个子女？"},
    {"id": "first_child_sex", "type": "choice", "q": "头胎是男是女？", "options": ["男", "女"], "show_if": {"children": ">0"}},
    {"id": "first_child_year", "type": "year", "q": "头胎哪一年出生？", "show_if": {"children": ">0"}},
    {"id": "parents_divorced", "type": "choice", "q": "父母是否离异或长期分居？", "options": ["否", "是"]},
    {"id": "parents_divorce_year", "type": "year", "q": "是哪一年？", "show_if": {"parents_divorced": "是"}},
    {"id": "parent_loss", "type": "choice", "q": "父母是否有人在你成年前过世？", "options": ["否", "父亲", "母亲"]},
    {"id": "parent_loss_year", "type": "year", "q": "是哪一年？", "show_if": {"parent_loss": "!否"}},
    {"id": "leave_home_year", "type": "year", "q": "哪一年第一次离家外出（求学或工作）？"},
    {"id": "move_years", "type": "years", "q": "其他搬家或换城市的年份（逗号分隔，可空）"},
    {"id": "promotion_years", "type": "years", "q": "升职或事业明显突破的年份（可空）"},
    {"id": "exam_years", "type": "years", "q": "考试上榜的年份，如中考、高考、考研、考证（可空）"},
    {"id": "wealth_years", "type": "years", "q": "明显进财的年份（可空）"},
    {"id": "relations", "type": "text", "q": "与父母、兄弟姐妹、配偶、子女的关系大致如何？（可空）"},
    {"id": "appearance", "type": "text", "q": "身形样貌特点，如高矮胖瘦、面型（可空）"},
    {"id": "temperament", "type": "text", "q": "性格特点（可空）"},
]

DATED_EVENTS = [("marriage_year", "结婚"), ("first_child_year", "添丁"), ("leave_home_year", "搬迁"),
                ("move_years", "搬迁"), ("promotion_years", "高升"), ("exam_years", "高中"),
                ("wealth_years", "发财")]
TEXT_FACTS = ["sibling_detail", "relations", "appearance", "temperament"]
W = {"dated": 3.0, "divorce": 2.0, "parent_event": 2.0, "parent_static": 2.0, "child_sex": 1.0, "siblings": 0.5}


def _years(v) -> list[int]:
    if v in (None, "", []):
        return []
    if isinstance(v, int):
        return [v]
    if isinstance(v, list):
        return [int(x) for x in v if str(x).strip().isdigit()]
    return [int(x) for x in re.findall(r"\d{4}", str(v))]


def _num(v) -> Optional[int]:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _approx(facts: dict, birth) -> Optional[datetime]:
    t = str(facts.get("approx_time") or "").strip()
    m = re.match(r"^(\d{1,2})[:：](\d{2})$", t)
    if facts.get("approx_known") != "知道" or not m:
        return None
    return birth.solar.replace(hour=int(m.group(1)) % 24, minute=int(m.group(2)))


# ------------------------------------------------------------------ 静态指标
def _palace_facts(v, key: str) -> dict:
    i = v.at(v.soul, key)
    stars = v.stars(i)
    return {"index": i, "majors": v.majors(i),
            "ji": any(s.get("birth_hua") == "忌" or s.get("self_out") == "忌" for s in stars.values()),
            "sha": [s for s in stars if s in SHA], "kong": [s for s in stars if s in KONG],
            "all": list(stars)}


def _parents_indicator(v, who: str = "") -> tuple[float, str]:
    f = _palace_facts(v, "父")
    dark = False
    if who in ("父亲", ""):
        dark = dark or (v.brightness("太阳") in DARK)
    if who in ("母亲", ""):
        dark = dark or (v.brightness("太阴") in DARK)
    ind = min(1.0, 0.5 * f["ji"] + 0.25 * len(f["sha"]) + 0.25 * dark)
    why = f"父母宫{'见忌' if f['ji'] else '无忌'}、煞{len(f['sha'])}颗{'、' + ('太阳' if who == '父亲' else '太阴' if who == '母亲' else '日月') + '落陷' if dark else ''}"
    return ind, why


def _parent_year_hit(astro, year: int) -> bool:
    """那一年流年或大限的化忌是否落入流年/本命父母宫。"""
    yb = H.yearly(astro, year)
    targets = {(yb["index"] + 1) % 12, (astro.soul_index + 1) % 12}
    hua = list(yb.get("hua", [])) + list((yb.get("decadal") or {}).get("hua", []))
    return any(h["hua"] == "忌" and h.get("palace_index") in targets for h in hua)


def _child_sex_signal(bazi: dict, sex: str) -> tuple[float, str]:
    """时柱天干十神（民间经验）：男命七杀为子、正官为女；女命伤官为子、食神为女。"""
    male = bazi["birth"]["gender"] == "男"
    god = bazi["pillars"][3]["stem_shishen"]
    table = {"七杀": "男", "正官": "女"} if male else {"伤官": "男", "食神": "女"}
    guess = table.get(god)
    if not guess:
        return 0.0, f"时干{god}，不作判断"
    return (1.0 if guess == sex else -1.0), f"时干{god}主头胎{guess}"


def _siblings_signal(v, n: Optional[int]) -> tuple[float, str]:
    if n is None or n == 1:
        return 0.0, "不作判断"
    f = _palace_facts(v, "兄")
    lonely = not f["majors"] or f["sha"] or f["kong"] or any(s in f["all"] for s in ("孤辰", "寡宿"))
    many = f["majors"] and any(s in f["all"] for s in ("左辅", "右弼", "天同", "天梁", "天机"))
    if n == 0:
        return (1.0 if lonely else -0.5), ("兄弟宫空或见煞空孤" if lonely else "兄弟宫星曜齐整")
    return (1.0 if many else -0.25), ("兄弟宫有主星且见辅佐" if many else "兄弟宫星曜偏少")


# ------------------------------------------------------------------ 打分
def _signature(astro, bazi) -> tuple:
    soul = astro.palaces[astro.soul_index]
    return (soul.branch, tuple(s.name for s in soul.stars if s.category == "major"), astro.bureau,
            bazi["pillars"][2]["ganzhi"], bazi["pillars"][3]["ganzhi"])


def _offset(orig, cand) -> int:
    d0, s0 = TS.current_slot(orig)
    d1, s1 = TS.current_slot(cand)
    return (d1 - d0).days * TS.PER_DAY + (s1 - s0)


def score_candidates(pid: str, facts: Optional[dict] = None, approx_time: Optional[str] = None) -> dict:
    person = ps.get(pid)
    if not person:
        raise KeyError(pid)
    facts = dict(person.life_facts or {}, **(facts or {}))
    if approx_time:
        facts.update({"approx_known": "知道", "approx_time": approx_time})
    orig = ps.birth_input(person)
    approx = _approx(facts, orig)
    cands = TS.candidates(orig, approx=approx)
    orig_astro, orig_bazi = ps.astrolabe(pid), ps.bazi(pid)

    seen: dict[tuple, dict] = {}
    out = []
    for c in cands:
        astro, bazi = ps.charts_for_birth(person, c)
        sig = _signature(astro, bazi)
        label = TS.describe(c)
        if sig in seen:
            seen[sig]["same_as"].append(label["label"])
            continue
        v = from_astrolabe(astro)
        rows = []
        tables: dict[str, dict] = {}
        yblocks: dict = {}

        def pct_of(event: str, year: int) -> Optional[int]:
            if event not in tables:
                if not yblocks:
                    yblocks.update({y: H.yearly(astro, y) for y in range(astro.birth_year + 1, astro.birth_year + 85)})
                tables[event] = {r["year"]: r for r in year_table(astro, bazi, event, yblocks=yblocks,
                                                                   ignore_age_window=True)}
            r = tables[event].get(year)
            return None if r is None else r["pct"]

        for key, ev in DATED_EVENTS:
            for y in _years(facts.get(key)):
                p = pct_of(ev, y)
                if p is None:
                    continue
                contrib = W["dated"] * (2 * p / 100 - 1)
                rows.append({"fact": f"{y}年{ev}", "weight": W["dated"], "contribution": round(contrib, 2),
                             "why": f"该盘{ev}分在一生中处第 {p} 百分位"})
        if facts.get("divorced") == "是":
            for y in _years(facts.get("divorce_year")):
                p = pct_of("结婚", y)
                if p is not None:
                    contrib = W["divorce"] * (1 - 2 * p / 100)
                    rows.append({"fact": f"{y}年离婚", "weight": W["divorce"], "contribution": round(contrib, 2),
                                 "why": f"该盘这一年婚姻分处第 {p} 百分位（越低越吻合）"})
        for key, yes_key, who in (("parents_divorced", "parents_divorce_year", ""),
                                  ("parent_loss", "parent_loss_year", None)):
            val = facts.get(key)
            if not val:
                continue
            who_ = facts.get("parent_loss") if who is None else who
            ind, why = _parents_indicator(v, who_ if who_ in ("父亲", "母亲") else "")
            if val in ("是", "父亲", "母亲"):
                rows.append({"fact": "父母离异" if key == "parents_divorced" else f"{val}早逝",
                             "weight": W["parent_static"], "contribution": round(W["parent_static"] * (2 * ind - 1), 2),
                             "why": why})
                for y in _years(facts.get(yes_key)):
                    hit = _parent_year_hit(astro, y)
                    rows.append({"fact": f"{y}年父母变故", "weight": W["parent_event"],
                                 "contribution": W["parent_event"] if hit else -0.5 * W["parent_event"],
                                 "why": "当年化忌入父母宫" if hit else "当年父母宫未见化忌"})
            elif val == "否":
                rows.append({"fact": "父母无离异" if key == "parents_divorced" else "父母成年前无早逝",
                             "weight": W["parent_static"] / 2,
                             "contribution": round(-W["parent_static"] / 2 * (2 * ind - 1) / 2, 2), "why": why})
        if facts.get("first_child_sex") in ("男", "女"):
            s, why = _child_sex_signal(bazi, facts["first_child_sex"])
            if s:
                rows.append({"fact": f"头胎{facts['first_child_sex']}", "weight": W["child_sex"],
                             "contribution": s * W["child_sex"], "why": why + "（民间经验，证据弱）"})
        s, why = _siblings_signal(v, _num(facts.get("siblings")))
        if s:
            rows.append({"fact": f"兄弟姐妹{facts.get('siblings')}人", "weight": W["siblings"],
                         "contribution": s * W["siblings"], "why": why + "（证据弱）"})

        soul = astro.palaces[astro.soul_index]
        entry = {
            "label": label["label"], "offset_slots": _offset(orig, c), "birth": c.as_dict(),
            "true_solar": label["true_solar"], "clock": label["clock"], "range": label["range"],
            "brief": {"ming": soul.ganzhi, "majors": [s.name for s in soul.stars if s.category == "major"],
                      "bureau": astro.bureau, "day_pillar": bazi["pillars"][2]["ganzhi"],
                      "hour_pillar": bazi["pillars"][3]["ganzhi"]},
            "flags": {"is_current": _signature(astro, bazi) == _signature(orig_astro, orig_bazi),
                      "bureau_changed": astro.bureau != orig_astro.bureau,
                      "day_changed": bazi["pillars"][2]["ganzhi"] != orig_bazi["pillars"][2]["ganzhi"]},
            "score": round(sum(r["contribution"] for r in rows), 2), "rows": rows, "same_as": [],
        }
        seen[sig] = entry
        out.append(entry)

    out.sort(key=lambda e: -e["score"])
    gap = round(out[0]["score"] - out[1]["score"], 2) if len(out) > 1 else None
    n_dated = sum(len(_years(facts.get(k))) for k, _ in DATED_EVENTS)
    confidence = "低"
    if gap is not None and gap >= 3 and n_dated >= 2:
        confidence = "高"
    elif gap is not None and gap >= 1.5:
        confidence = "中"
    return {
        "version": VERSION, "mode": "大致时段前后各两个时辰" if approx else "全天各时辰（含前一日晚子）",
        "candidates": out, "gap": gap, "confidence": confidence, "dated_facts": n_dated,
        "text_facts": {k: facts[k] for k in TEXT_FACTS if facts.get(k)},
        "weights": W,
        "method": "有年份的经历查该盘此年在事件中的百分位（权重 3）；离异与父母变故看夫妻宫、父母宫化忌煞陷（权重 2）；"
                  "头胎男女与兄弟姐妹为弱证据（1 与 0.5）；文字描述不打分，交给 AI",
    }


def rectify_text(pid: str, action: Optional[dict] = None) -> str:
    action = action or {}
    res = score_candidates(pid, action.get("facts"), action.get("approx_time"))
    person = ps.get(pid)
    lines = [f"# {person.display_name}（{pid}）反推时辰评分（代码计算，{res['version']}）",
             f"候选范围：{res['mode']}；有年份的经历 {res['dated_facts']} 条；第一名领先 {res['gap']} 分，置信度 {res['confidence']}",
             f"方法：{res['method']}",
             "", "| 排名 | 候选 | 相对原盘 | 命宫 | 主星 | 五行局 | 日柱 | 时柱 | 总分 |", "|---|---|---|---|---|---|---|---|---|"]
    for i, c in enumerate(res["candidates"], 1):
        b = c["brief"]
        tag = "（现盘）" if c["flags"]["is_current"] else ""
        lines.append(f"| {i} | {c['label']}{tag} | {c['offset_slots']:+} 位 | {b['ming']} | {'、'.join(b['majors']) or '无主星'} "
                     f"| {b['bureau']} | {b['day_pillar']} | {b['hour_pillar']} | {c['score']} |")
    for i, c in enumerate(res["candidates"][:3], 1):
        lines.append(f"\n## 第 {i} 名 {c['label']} 的证据（调用 get_chart_variant 时 slots={c['offset_slots']}）")
        if c["same_as"]:
            lines.append(f"- 与 {'、'.join(c['same_as'])} 排出的盘相同")
        for r in c["rows"]:
            lines.append(f"- {r['fact']}：{r['contribution']:+}（{r['why']}）")
        if not c["rows"]:
            lines.append("- 没有可打分的经历")
    if res["text_facts"]:
        lines.append("\n## 用户的文字描述（未打分，请你比对各候选盘）")
        for k, v in res["text_facts"].items():
            lines.append(f"- {k}：{v}")
    return "\n".join(lines)
