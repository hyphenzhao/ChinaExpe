"""子平量化分析：身强身弱、十神占比、格局候选、喜忌用神排序。纯代码，不接 AI。

输入是 compute_bazi() 的结果，输出 JSON 友好的 dict。所有数值口径见 tables.py；
破格一律不判，只把合冲等事实列在 observations 里交给 AI。
"""
from __future__ import annotations

from .chart import shishen as _shishen
from .constants import BRANCH_WUXING, KE, SHENG, STEM_WUXING
from . import tables as T

ELEMENTS = ["木", "火", "土", "金", "水"]
PRODUCER = {v: k for k, v in SHENG.items()}      # 生我者
CONTROLLER = {v: k for k, v in KE.items()}       # 克我者


def _r(x: float, n: int = 1) -> float:
    return round(x + 0.0, n)


# --------------------------------------------------------------- 基础打分
def month_coef(month_branch: str, status: dict[str, str]) -> dict[str, float]:
    """月令系数：五行 → 乘数。"""
    if month_branch in T.MONTH_COEF_EXPLICIT:
        return dict(T.MONTH_COEF_EXPLICIT[month_branch])
    table = T.STATUS_COEF_PURE if month_branch in "子午卯酉" else T.STATUS_COEF_FALLBACK
    return {e: table[status[e]] for e in ELEMENTS}


def items(chart: dict) -> list[dict]:
    """四柱天干与地支藏干逐项列出，带权重。"""
    out = []
    for p in chart["pillars"]:
        out.append({"pos": p["pos"], "src": "干", "stem": p["stem"], "element": STEM_WUXING[p["stem"]],
                    "shishen": p["stem_shishen"], "w": T.STEM_WEIGHT})
        for h in p["hidden"]:
            w = T.HIDDEN_WEIGHT[p["branch"]].get(h["stem"], 0)
            out.append({"pos": p["pos"], "src": T.hidden_kind(p["branch"], h["stem"]), "stem": h["stem"],
                        "element": STEM_WUXING[h["stem"]], "shishen": h["shishen"], "w": w,
                        "branch": p["branch"]})
    return out


def element_scores(chart: dict) -> dict:
    month = chart["pillars"][1]["branch"]
    coef = month_coef(month, chart["wuxing_status"])
    raw = {e: 0.0 for e in ELEMENTS}
    for it in items(chart):
        raw[it["element"]] += it["w"]
    adj = {e: raw[e] * coef[e] for e in ELEMENTS}
    total = sum(adj.values()) or 1.0
    return {"raw": raw, "coef": coef, "adj": adj,
            "pct": {e: _r(adj[e] / total * 100) for e in ELEMENTS},
            "coef_source": T.COEF_SOURCE.get(month, "")}


# --------------------------------------------------------------- 身强身弱
def strength(chart: dict) -> dict:
    dm = chart["day_master_stem"]
    e = STEM_WUXING[dm]
    prod = PRODUCER[e]
    sc = element_scores(chart)
    total = sum(sc["adj"].values()) or 1.0
    same = sc["adj"][e] + sc["adj"][prod]
    pct = same / total * 100

    label, special = "身弱", None
    for floor, name, sp in T.STRENGTH_BANDS:
        if pct >= floor:
            label, special = name, sp
            break

    its = items(chart)
    roots = [{"pos": it["pos"], "stem": it["stem"], "kind": it["src"]}
             for it in its if it["src"] in ("本气", "中气", "余气") and it["element"] == e]
    strong_root = any(r["kind"] in ("本气", "中气") for r in roots)
    yin_stem = any(it["src"] == "干" and it["pos"] != "日柱" and it["element"] == prod for it in its)
    if special == "从弱候选" and (strong_root or yin_stem):
        special = None                      # 有本中气根或天干见印，不作从弱论

    st = chart["wuxing_status"][e]
    de_ling = st in ("旺", "相")
    de_di = strong_root
    de_shi = any(it["src"] == "干" and it["pos"] != "日柱" and it["element"] in (e, prod) for it in its)
    bounds = [b for b, _, _ in T.STRENGTH_BANDS if b > 0]
    border = any(abs(pct - b) <= T.BORDER_MARGIN for b in bounds)
    return {
        "same_pct": _r(pct), "label": label, "special": special, "border": border,
        "same": {"比劫": _r(sc["adj"][e]), "印": _r(sc["adj"][prod])},
        "element_pct": sc["pct"], "month_status": st,
        "de_ling": de_ling, "de_di": de_di, "de_shi": de_shi,
        "roots": roots, "coef_source": sc["coef_source"],
        "legacy": chart.get("strength"),
    }


# --------------------------------------------------------------- 十神占比
def shishen_share(chart: dict) -> dict:
    """日干不计。pct 乘了月令系数（力量占比），raw_pct 只按藏干权重。"""
    month = chart["pillars"][1]["branch"]
    coef = month_coef(month, chart["wuxing_status"])
    raw: dict[str, float] = {}
    adj: dict[str, float] = {}
    for it in items(chart):
        if it["shishen"] == "日主":
            continue
        raw[it["shishen"]] = raw.get(it["shishen"], 0) + it["w"]
        adj[it["shishen"]] = adj.get(it["shishen"], 0) + it["w"] * coef[it["element"]]
    tr, ta = sum(raw.values()) or 1.0, sum(adj.values()) or 1.0
    rows = [{"shishen": k, "pct": _r(adj[k] / ta * 100), "raw_pct": _r(raw[k] / tr * 100)}
            for k in adj]
    rows.sort(key=lambda r: -r["pct"])
    groups = {g: 0.0 for g in T.GROUP_ORDER}
    for r in rows:
        groups[T.SHISHEN_GROUP[r["shishen"]]] += r["pct"]
    visible: dict[str, int] = {}
    for p in chart["pillars"]:
        if p["stem_shishen"] != "日主":
            visible[p["stem_shishen"]] = visible.get(p["stem_shishen"], 0) + 1
    return {"items": rows,
            "groups": [{"group": g, "pct": _r(groups[g])} for g in T.GROUP_ORDER],
            "visible": [{"shishen": k, "count": v} for k, v in visible.items()],
            "method": "天干 100、藏干按本中余 60/30/10 等分配，乘月令系数；日干不计"}


# --------------------------------------------------------------- 格局候选
def _stem_combined(chart: dict, pos: str) -> bool:
    return any(r["type"] == "合" and pos in r["pillars"] for r in chart["relations"]["stems"])


def _geju_name(god: str, dm: str) -> str:
    if god == "劫财":
        return "月刃格" if dm in T.YANG_STEMS else "月劫格"
    return T.GEJU_NAME.get(god, god + "格")


def geju(chart: dict, st: dict | None = None, share: dict | None = None) -> dict:
    st = st or strength(chart)
    share = share or shishen_share(chart)
    dm = chart["day_master_stem"]
    P = chart["pillars"]
    month = P[1]
    shares = {r["shishen"]: r["pct"] for r in share["items"]}
    other_stems = {p["pos"]: p["stem"] for p in P if p["pos"] != "日柱"}

    cands: dict[str, dict] = {}
    for h in month["hidden"]:
        w = T.HIDDEN_WEIGHT[month["branch"]].get(h["stem"], 0)
        kind = T.hidden_kind(month["branch"], h["stem"])
        god = h["shishen"]
        if god in ("比肩", "劫财") and kind != "本气":
            continue                        # 中余气的比劫透出不成格；建禄月刃只看本气
        score, flags = float(w), [kind]
        tou = [pos for pos, s in other_stems.items() if s == h["stem"]]
        same_elem = [pos for pos, s in other_stems.items()
                     if s != h["stem"] and STEM_WUXING[s] == STEM_WUXING[h["stem"]]]
        if tou:
            score *= 1.5
            flags.append("透干(" + "、".join(tou) + ")")
            if "月柱" in tou:
                score *= 1.2
            if any(_stem_combined(chart, pos) for pos in tou):
                score *= 0.5
                flags.append("透干被合")
        elif same_elem:
            score *= 1.2
            flags.append("同五行透出(" + "、".join(same_elem) + ")")
        score *= 1 + shares.get(god, 0) / 100
        name = _geju_name(god, dm)
        c = cands.setdefault(name, {"name": name, "shishen": god, "score": 0.0, "basis": [], "flags": []})
        c["score"] += score
        c["basis"].append(f"月令{month['branch']}{kind}{h['stem']}({god})")
        c["flags"] += flags

    total = sum(c["score"] for c in cands.values()) or 1.0
    rows = sorted(cands.values(), key=lambda c: -c["score"])
    for c in rows:
        c["pct"] = _r(c["score"] / total * 100)
        c["score"] = _r(c["score"])

    # 主格：子平真诠取格次序。月令本气为比劫时直接论建禄 / 月刃，不看透干。
    primary = None
    order = sorted(month["hidden"], key=lambda h: -T.HIDDEN_WEIGHT[month["branch"]].get(h["stem"], 0))
    if order and order[0]["shishen"] in ("比肩", "劫财"):
        h = order[0]
        primary = {"name": _geju_name(h["shishen"], dm), "basis": f"月令本气{h['stem']}为{h['shishen']}"}
    for h in ([] if primary else order):
        if h["shishen"] in ("比肩", "劫财"):
            continue                        # 余气比劫透出不作建禄
        if h["stem"] in other_stems.values():
            primary = {"name": _geju_name(h["shishen"], dm),
                       "basis": f"月令{T.hidden_kind(month['branch'], h['stem'])}{h['stem']}透干"}
            break
    if not primary and order:
        h = order[0]
        primary = {"name": _geju_name(h["shishen"], dm), "basis": f"月令本气{h['stem']}未透，取本气"}
    if primary and primary["name"] in ("建禄格", "月刃格", "月劫格"):
        primary["note"] = "建禄、月刃格另取透出的财官杀食伤为用"

    special = _special_patterns(chart, st, share)
    return {"primary": primary, "candidates": rows[:5], "special": special,
            "observations": _observations(chart),
            "method": "月令藏干按权重打分：透干 ×1.5（月干再 ×1.2）、被合 ×0.5、乘（1+该十神占比）；不判破格"}


def _special_patterns(chart: dict, st: dict, share: dict) -> list[dict]:
    dm = chart["day_master_stem"]
    e = STEM_WUXING[dm]
    groups = {g["group"]: g["pct"] for g in share["groups"]}
    ep = st["element_pct"]
    branches = [p["branch"] for p in chart["pillars"]]
    month_b = branches[1]
    out = []

    if st["special"] == "从强候选":
        name = "从强格" if groups["比劫"] >= groups["印"] else "从旺格"
        out.append({"name": name, "pct": st["same_pct"],
                    "gates": {"同类占比≥80%": True, "比劫对印": f"{groups['比劫']}/{groups['印']}"}})
    if st["special"] == "从弱候选":
        dom = max(("财", "官杀", "食伤"), key=lambda g: groups[g])
        name = {"财": "从财格", "官杀": "从杀格", "食伤": "从儿格"}[dom]
        out.append({"name": name, "pct": groups[dom],
                    "gates": {"同类占比<20%": True, "无本中气根": True, "天干无印": True}})

    zw_name, season, sets = T.ZHUANWANG[e]
    if ep[e] >= T.ZHUANWANG_MIN_PCT and month_b in season:
        has_set = any(len(s & set(branches)) >= 2 for s in sets)
        weak_ctrl = ep[CONTROLLER[e]] < 10
        if has_set and weak_ctrl:
            out.append({"name": zw_name, "pct": ep[e],
                        "gates": {f"日主五行≥{T.ZHUANWANG_MIN_PCT:.0f}%": True, "生于当令": True,
                                  "方局成二": True, "克我<10%": True}})

    stems = [p["stem"] for p in chart["pillars"]]
    for pos in (1, 3):                      # 月干、时干与日干相合
        pair = frozenset((dm, stems[pos]))
        if len(pair) == 2 and pair in T.HUAQI:
            target = T.HUAQI[pair]
            status = chart["wuxing_status"][target]
            if status in ("旺", "相") and ep[CONTROLLER[target]] < 10:
                out.append({"name": f"化{target}格", "pct": ep[target],
                            "gates": {"合化": f"{dm}{stems[pos]}", "化神得令": status,
                                      "克化神<10%": True}})
    seen, uniq = set(), []                  # 月干时干同合时只列一次
    for s in out:
        if s["name"] not in seen:
            seen.add(s["name"])
            uniq.append(s)
    return uniq


def _observations(chart: dict) -> list[str]:
    """与月令、透干有关的合冲刑害，只列事实。"""
    obs = []
    for r in chart["relations"]["branches"]:
        if "月柱" in r["pillars"] and r["type"] in ("冲", "刑", "害", "破", "六合", "三合", "半合", "三会"):
            obs.append(f"月支{r['text']}")
    for r in chart["relations"]["stems"]:
        if r["type"] == "合":
            obs.append(f"天干{r['text']}")
    return obs


# --------------------------------------------------------------- 喜忌用神
def _group_element(dm_e: str) -> dict[str, str]:
    return {"比劫": dm_e, "印": PRODUCER[dm_e], "食伤": SHENG[dm_e],
            "财": KE[dm_e], "官杀": CONTROLLER[dm_e]}


def yongshen(chart: dict, st: dict | None = None, gj: dict | None = None) -> dict:
    st = st or strength(chart)
    gj = gj or geju(chart, st)
    dm = chart["day_master_stem"]
    e = STEM_WUXING[dm]
    ge = _group_element(e)
    ep = st["element_pct"]
    pct = st["same_pct"]
    score = {x: 0.0 for x in ELEMENTS}
    reasons: dict[str, list] = {x: [] for x in ELEMENTS}

    def add(elem: str, delta: float, layer: str, text: str):
        score[elem] += delta
        reasons[elem].append({"layer": layer, "delta": delta, "text": text})

    specials = {s["name"] for s in gj["special"]}
    method = []
    if specials & {"从强格", "从旺格"} or any(n.endswith(("曲直格", "炎上格", "稼穑格", "从革格", "润下格")) for n in specials):
        method.append("从格/专旺")
        add(e, 3, "从格", "顺其旺势")
        add(SHENG[e], 2, "从格", "泄秀")
        add(PRODUCER[e], 1, "从格", "生扶旺神")
        add(CONTROLLER[e], -3, "从格", "逆其旺势")
    elif specials & {"从财格", "从杀格", "从儿格"}:
        method.append("从弱")
        name = next(iter(specials & {"从财格", "从杀格", "从儿格"}))
        dom = ge[{"从财格": "财", "从杀格": "官杀", "从儿格": "食伤"}[name]]
        add(dom, 3, "从格", f"从{dom}")
        add(PRODUCER[dom], 1.5, "从格", f"生{dom}")
        add(e, -3, "从格", "日主无根，不宜再扶")
        add(PRODUCER[e], -2, "从格", "印生日主反破从势")
    else:
        method.append("扶抑")
        if pct < 45:
            add(ge["印"], 2, "扶抑", "身弱喜印生")
            add(ge["比劫"], 1.5, "扶抑", "身弱喜比劫帮")
            add(ge["官杀"], -2, "扶抑", "身弱忌官杀克")
            add(ge["财"], -1.5, "扶抑", "身弱忌财耗")
            add(ge["食伤"], -1, "扶抑", "身弱忌食伤泄")
        elif pct > 55:
            opp = ["官杀", "食伤", "财"]
            for g in opp:
                add(ge[g], 1.5, "扶抑", f"身强喜{g}")
            need = min(opp, key=lambda g: ep[ge[g]])
            add(ge[need], 0.5, "扶抑", f"{need}最弱，优先补足")
            add(ge["印"], -2, "扶抑", "身强忌印")
            add(ge["比劫"], -1.5, "扶抑", "身强忌比劫")
        else:
            lean = 0.5 if pct < 50 else -0.5
            add(ge["印"], lean, "扶抑", "中和，略偏" + ("弱" if lean > 0 else "强"))
            add(ge["比劫"], lean, "扶抑", "中和，略偏" + ("弱" if lean > 0 else "强"))

    # 调候：中和时加倍；专旺/从格时减半
    month_b = chart["pillars"][1]["branch"]
    th = T.TIAOHOU.get(dm, {}).get(month_b, "")
    mult = 2.0 if 45 <= pct <= 55 else (0.5 if method[0] != "扶抑" else 1.0)
    seen = set()
    for i, s in enumerate(th):
        el = STEM_WUXING[s]
        if el in seen:
            continue
        seen.add(el)
        bonus = T.TIAOHOU_BONUS[min(i, len(T.TIAOHOU_BONUS) - 1)] * mult
        add(el, bonus, "调候", f"穷通宝鉴 {dm}生{month_b}月取{s}")
    if month_b in "亥子丑" and ep["火"] < 5:
        add("火", 1.5, "调候", "冬生火弱，急需温暖")
    if month_b in "巳午未" and ep["水"] < 5:
        add("水", 1.5, "调候", "夏生水弱，急需润泽")

    # 通关：相克的两方都 ≥30%
    for a in ELEMENTS:
        b = KE[a]
        if ep[a] >= 30 and ep[b] >= 30:
            bridge = SHENG[a]
            add(bridge, 1.0, "通关", f"{a}{b}相战，取{bridge}通关")

    # 病药：超出均值最多者为病，克它者为药
    sick = max(ELEMENTS, key=lambda x: ep[x] - 20)
    if ep[sick] - 20 > 15:
        add(CONTROLLER[sick], 0.5, "病药", f"{sick}过旺为病，{CONTROLLER[sick]}为药")

    ranked = sorted(ELEMENTS, key=lambda x: -score[x])
    ranking = [{"element": x, "role": T.ROLES[i], "score": _r(score[x], 2),
                "share": ep[x], "reasons": reasons[x]} for i, x in enumerate(ranked)]
    return {"ranking": ranking, "method": "+".join(method + ["调候", "通关", "病药"]),
            "note": "各层加分为本系统口径，排序用于参考，不是断语"}


# --------------------------------------------------------------- 汇总
def analyze(chart: dict) -> dict:
    st = strength(chart)
    share = shishen_share(chart)
    gj = geju(chart, st, share)
    ys = yongshen(chart, st, gj)
    return {"version": T.VERSION, "strength": st, "shishen": share, "geju": gj, "yongshen": ys}
