"""人生喜事：按大限与流年给六类事件逐年打分，挑出最强的年份与月份。纯代码。

信号来自通行的紫微论事口径（事件宫、四化引动、流曜、叠宫）；**权重是本系统口径**，
只能用来比较同一个人不同年份的相对强弱，不是断语。所有权重集中在 WEIGHTS / EVENTS，便于调。

层次：流年 1.0、大限 0.6、本命 0.3。流年事件宫与本命或大限的同名宫重叠（叠宫）时，
该层正分 ×1.5。八字流年十神作辅助，加减不超过紫微分的三成。
"""
from __future__ import annotations

from typing import Optional

from . import horoscope as H
from .view import OFFSET, SHA

VERSION = "ev-1"

WEIGHTS = {
    "layer": {"流年": 1.0, "大限": 0.6, "本命": 0.3},
    "diegong": 1.5,            # 叠宫倍数
    "ji_in": -1.0,             # 化忌入事件宫
    "ji_opposite": -0.7,       # 化忌冲事件宫
    "sha": -0.3,               # 煞在事件宫（三方里减半）
    "sanfang": 0.5,            # 信号落在事件宫三方四正时的折扣
    "natal_trigger": 0.6,      # 流年化禄引动本命事件宫
    "ming_on_event": 0.8,      # 流年命宫走到本命事件宫
    "bazi_cap": 0.3,           # 八字加减上限：紫微分绝对值的 30%
}

# 流曜名 → 本名
FLOW_BASE = {"禄": "禄存", "马": "天马", "鸾": "红鸾", "喜": "天喜", "昌": "文昌", "曲": "文曲",
             "魁": "天魁", "钺": "天钺", "羊": "擎羊", "陀": "陀罗"}

EVENTS: dict[str, dict] = {
    "结婚": {"main": "夫", "label": "夫妻宫", "min_age": 18, "max_age": 55,
             "stars": {"红鸾": 1.0, "天喜": 1.0, "天姚": 0.4, "咸池": 0.4, "禄存": 0.3},
             "hua": {"禄": 1.0, "科": 0.5, "权": 0.3},
             "natal_neg": {"孤辰": -0.3, "寡宿": -0.3}},
    "发财": {"main": "财", "label": "财帛宫", "min_age": 18, "max_age": 85,
             "stars": {"禄存": 1.0, "天马": 0.4, "武曲": 0.2, "太阴": 0.1, "天府": 0.1},
             "hua": {"禄": 1.2, "权": 0.5, "科": 0.2}},
    "高升": {"main": "官", "label": "官禄宫", "min_age": 20, "max_age": 65,
             "stars": {"天魁": 0.6, "天钺": 0.6, "左辅": 0.4, "右弼": 0.4, "禄存": 0.3},
             "hua": {"权": 1.2, "科": 0.8, "禄": 0.5}},
    "搬迁": {"main": "迁", "label": "迁移宫", "min_age": 16, "max_age": 85, "also": ["田"],
             "stars": {"天马": 1.2, "禄存": 0.3},
             "hua": {"禄": 0.5, "权": 0.5},
             "ji_moves": 0.5},          # 化忌冲田宅/迁移反主变动
    "添丁": {"main": "子", "label": "子女宫", "min_age": 20, "max_age": 45,
             "stars": {"天喜": 1.0, "红鸾": 0.6, "禄存": 0.3},
             "hua": {"禄": 1.0, "科": 0.5, "权": 0.3}},
    "高中": {"main": "官", "label": "官禄宫", "min_age": 12, "max_age": 45, "also": ["父"],
             "stars": {"文昌": 0.8, "文曲": 0.8, "天魁": 0.6, "天钺": 0.6},
             "hua": {"科": 1.2, "权": 0.5, "禄": 0.3}},
}
ALL_EVENTS = list(EVENTS)
FUTURE_SPAN = 20          # 未来只看 20 年内


def _sf(i: int) -> list[int]:
    return [i % 12, (i + 4) % 12, (i + 8) % 12, (i + 6) % 12]


def _stars_at(astro, i: int) -> list[str]:
    return [s.name for s in astro.palaces[i % 12].stars]


def _flow_signals(block: dict, main: int, cfg: dict, layer: str, pname: str) -> list[dict]:
    """某一层（流年 / 大限）的四化与流曜落在事件宫及其三方四正的信号。"""
    out = []
    sf = _sf(main)
    opp = (main + 6) % 12
    for h in block.get("hua", []):
        i = h.get("palace_index")
        if i is None:
            continue
        kind = h["hua"]
        if kind == "忌":
            if i == main:
                if cfg.get("ji_moves"):
                    out.append({"layer": layer, "delta": cfg["ji_moves"], "text": f"{layer}{h['star']}化忌入{pname}（主变动）"})
                else:
                    out.append({"layer": layer, "delta": WEIGHTS["ji_in"], "text": f"{layer}{h['star']}化忌入{pname}"})
            elif i == opp:
                delta = cfg.get("ji_moves") or WEIGHTS["ji_opposite"]
                out.append({"layer": layer, "delta": delta, "text": f"{layer}{h['star']}化忌冲{pname}"})
            continue
        w = cfg["hua"].get(kind, 0)
        if not w:
            continue
        if i == main:
            out.append({"layer": layer, "delta": w, "text": f"{layer}{h['star']}化{kind}入{pname}"})
        elif i in sf:
            out.append({"layer": layer, "delta": w * WEIGHTS["sanfang"], "text": f"{layer}{h['star']}化{kind}会照{pname}"})
    for s in block.get("stars", []):
        base = FLOW_BASE.get(s["name"][-1])
        i = s.get("palace_index")
        if base is None or i is None:
            continue
        if base in ("擎羊", "陀罗"):
            if i == main:
                out.append({"layer": layer, "delta": WEIGHTS["sha"], "text": f"{s['name']}入{pname}"})
            continue
        w = cfg["stars"].get(base, 0)
        if not w:
            continue
        if i == main:
            out.append({"layer": layer, "delta": w, "text": f"{s['name']}入{pname}"})
        elif i in sf:
            out.append({"layer": layer, "delta": w * WEIGHTS["sanfang"], "text": f"{s['name']}会照{pname}"})
    return out


def _natal_star_signals(astro, main: int, cfg: dict, layer: str, pname: str) -> list[dict]:
    """本命星曜坐落在这一层的事件宫里（例如流年夫妻宫恰好有本命红鸾）。"""
    out = []
    for name in _stars_at(astro, main):
        w = cfg["stars"].get(name, 0) * 0.5
        if w:
            out.append({"layer": layer, "delta": w, "text": f"{pname}见本命{name}"})
        if name in SHA:
            out.append({"layer": layer, "delta": WEIGHTS["sha"] * 0.5, "text": f"{pname}见本命{name}"})
    return out


def score_signals(signals: list[dict], diegong: dict[str, bool]) -> float:
    """按层加权求和；叠宫时该层正分放大。纯函数，单调：加正信号分数只升不降。"""
    total = 0.0
    for layer, w in WEIGHTS["layer"].items():
        pos = sum(s["delta"] for s in signals if s["layer"] == layer and s["delta"] > 0)
        neg = sum(s["delta"] for s in signals if s["layer"] == layer and s["delta"] < 0)
        if diegong.get(layer):
            pos *= WEIGHTS["diegong"]
        total += w * (pos + neg)
    return total


def year_signals(astro, year: int, event: str, yb: Optional[dict] = None) -> tuple[list[dict], dict]:
    cfg = EVENTS[event]
    off = OFFSET[cfg["main"]]
    yb = yb or H.yearly(astro, year)
    db = yb.get("decadal") or {}
    natal_main = (astro.soul_index + off) % 12
    ly_main = (yb["index"] + off) % 12
    dx_main = (db["index"] + off) % 12 if db.get("index") is not None else None
    label = cfg["label"]

    sig = []
    sig += _flow_signals(yb, ly_main, cfg, "流年", f"流年{label}")
    sig += _natal_star_signals(astro, ly_main, cfg, "流年", f"流年{label}")
    for extra in cfg.get("also", []):
        e_off = OFFSET[extra]
        e_main = (yb["index"] + e_off) % 12
        name = {"田": "田宅宫", "父": "父母宫"}[extra]
        sig += [dict(s, delta=s["delta"] * 0.6) for s in _flow_signals(yb, e_main, cfg, "流年", f"流年{name}")]
    if dx_main is not None:
        sig += _flow_signals(db, dx_main, cfg, "大限", f"大限{label}")
    # 流年四化引动本命事件宫
    for h in yb.get("hua", []):
        if h.get("palace_index") == natal_main and h["hua"] == "禄":
            sig.append({"layer": "流年", "delta": WEIGHTS["natal_trigger"], "text": f"流年{h['star']}化禄引动本命{label}"})
    if yb["index"] == natal_main:
        sig.append({"layer": "流年", "delta": WEIGHTS["ming_on_event"], "text": f"流年命宫走到本命{label}"})
    # 本命底色
    sig += _natal_star_signals(astro, natal_main, cfg, "本命", f"本命{label}")
    for name, w in cfg.get("natal_neg", {}).items():
        if name in _stars_at(astro, natal_main):
            sig.append({"layer": "本命", "delta": w, "text": f"本命{label}见{name}"})

    diegong = {"流年": ly_main in (natal_main, dx_main), "大限": dx_main == natal_main}
    if diegong["流年"]:
        sig.append({"layer": "流年", "delta": 0.0,
                    "text": f"叠宫：流年{label}落在{'本命' if ly_main == natal_main else '大限'}{label}上"})
    return sig, diegong


def best_months(astro, year: int, event: str, yb: Optional[dict] = None, top: int = 2) -> list[dict]:
    cfg = EVENTS[event]
    off = OFFSET[cfg["main"]]
    yb = yb or H.yearly(astro, year)
    ly_main = (yb["index"] + off) % 12
    natal_main = (astro.soul_index + off) % 12
    rows = []
    for mb in H.monthly_list(astro, year):
        sig = _flow_signals(mb, ly_main, cfg, "流月", f"流年{cfg['label']}")
        if ly_main in _sf(mb["index"]):
            sig.append({"layer": "流月", "delta": 0.8 if mb["index"] == ly_main else 0.4,
                        "text": "流月命宫" + ("走到" if mb["index"] == ly_main else "会照") + f"流年{cfg['label']}"})
        for h in mb.get("hua", []):
            if h.get("palace_index") == natal_main and h["hua"] in ("禄", "权", "科"):
                sig.append({"layer": "流月", "delta": 0.3, "text": f"流月{h['star']}化{h['hua']}引动本命{cfg['label']}"})
        score = sum(s["delta"] for s in sig)
        rows.append({"lunar_month": mb["lunar_month"], "is_leap": mb["is_leap"], "name": mb["month_name"],
                     "ganzhi": mb["ganzhi"], "score": round(score, 2), "signals": sig})
    rows.sort(key=lambda r: -r["score"])
    return rows[:top]


def year_table(astro, bazi: Optional[dict], event: str, yblocks: Optional[dict] = None,
               max_age: int = 85, ignore_age_window: bool = False) -> list[dict]:
    """某事件在一生各年的分数与百分位（同一人内比较）。反推时辰也用它查任意年份。"""
    from ..bazi.events import bazi_year_adjust

    cfg = EVENTS[event]
    by = astro.birth_year
    rows = []
    for y in range(by + 1, by + max_age):
        age = y - by + 1
        if not ignore_age_window and (age < cfg["min_age"] or age > cfg.get("max_age", max_age)):
            continue
        yb = (yblocks or {}).get(y) or H.yearly(astro, y)
        sig, dg = year_signals(astro, y, event, yb)
        z = score_signals(sig, dg)
        adj, adj_sig = (0.0, [])
        if bazi:
            adj, adj_sig = bazi_year_adjust(bazi, y, event)
            cap = WEIGHTS["bazi_cap"] * max(abs(z), 1.0)
            adj = max(-cap, min(cap, adj))
        rows.append({"year": y, "age": age, "score": round(z + adj, 2), "ziwei": round(z, 2),
                     "bazi_adj": round(adj, 2), "signals": sig + adj_sig, "diegong": dg})
    ranked = sorted(r["score"] for r in rows)
    for r in rows:
        below = sum(1 for s in ranked if s < r["score"])
        r["pct"] = round(below / max(len(ranked) - 1, 1) * 100)
    return rows


def life_events(astro, bazi: Optional[dict] = None, now_year: Optional[int] = None,
                events: Optional[list[str]] = None, max_age: int = 85, future_top: int = 5,
                past_top: int = 8) -> dict:
    """六类事件的年份评分：未来最强 N 年 + 过去命中的强年，并给出最可能的月份。"""
    from datetime import date

    now_year = now_year or date.today().year
    events = events or ALL_EVENTS
    by = astro.birth_year
    yblocks = {y: H.yearly(astro, y) for y in range(by + 1, by + max_age)}
    out = {}
    for ev in events:
        cfg = EVENTS[ev]
        rows = year_table(astro, bazi, ev, yblocks=yblocks, max_age=max_age)
        if not rows:
            continue
        future = sorted([r for r in rows if now_year <= r["year"] <= now_year + FUTURE_SPAN], key=lambda r: -r["score"])[:future_top]
        past = sorted([r for r in rows if r["year"] < now_year and r["pct"] >= 85], key=lambda r: -r["score"])[:past_top]
        for r in future + past:
            r["months"] = best_months(astro, r["year"], ev, yblocks[r["year"]])
        out[ev] = {"palace": cfg["label"], "future_top": future, "past_strong": past}
    return {"version": VERSION, "now_year": now_year, "events": out,
            "note": "权重为本系统口径，只比较同一人不同年份的相对强弱，不是断语；月份为农历月"}
