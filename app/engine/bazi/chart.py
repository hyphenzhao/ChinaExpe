"""子平八字 natal chart (测测 App layout).

Rows per pillar: 干神 / 天干 / 地支 / 藏干 / 支神 / 纳音 / 空亡 / 地势 / 自坐 / 神煞.
Plus 干支关系, 五行状态, 十神汇总.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from lunar_python.util import LunarUtil

from .. import calendar as cal
from ..settings import BaziSettings, BirthInput
from .constants import (BRANCHES, BRANCH_WUXING, CHANGSHENG12, CHANGSHENG_START, HIDDEN, KE, SHENG,
                        STEMS, STEM_WUXING, WUXING, STEM_HE_HUA, BRANCH_LIUHE, BRANCH_CHONG, BRANCH_HAI,
                        BRANCH_PO, BRANCH_ANHE, SANHE_JU, SANHUI, XING_GROUPS, XING_PAIRS, ZIXING)
from . import shensha as SS

PILLAR_NAMES = ["年柱", "月柱", "日柱", "时柱"]


def shishen(day_stem: str, other: str) -> str:
    return LunarUtil.SHI_SHEN[day_stem + other]


def changsheng(stem: str, branch: str) -> str:
    """十二长生 of ``stem`` at ``branch`` (阳顺阴逆)."""
    start = BRANCHES.index(CHANGSHENG_START[stem])
    b = BRANCHES.index(branch)
    yang = STEMS.index(stem) % 2 == 0
    off = (b - start) % 12 if yang else (start - b) % 12
    return CHANGSHENG12[off]


def nayin(gz: str) -> str:
    return LunarUtil.NAYIN[gz]


def xunkong(gz: str) -> str:
    return LunarUtil.getXunKong(gz)


def nayin_wuxing(gz: str) -> str:
    n = nayin(gz)
    for w in WUXING:
        if w in n:
            return w
    return ""


def pillar_info(gz: str, day_stem: str, pos: str) -> dict:
    g, z = gz[0], gz[1]
    hidden = [{"stem": h, "wuxing": STEM_WUXING[h], "shishen": shishen(day_stem, h)} for h in HIDDEN[z]]
    return {
        "pos": pos, "ganzhi": gz, "stem": g, "branch": z,
        "stem_wuxing": STEM_WUXING[g], "branch_wuxing": BRANCH_WUXING[z],
        "stem_shishen": "日主" if (pos == "日柱" and g == day_stem) else shishen(day_stem, g),
        "hidden": hidden,
        "branch_shishen": [h["shishen"] for h in hidden],
        "nayin": nayin(gz), "xunkong": xunkong(gz),
        "dishi": changsheng(day_stem, z),   # 日干在此支之长生
        "zizuo": changsheng(g, z),          # 柱干在柱支之长生
        "shensha": [],
    }


def wuxing_status(month_branch: str) -> dict[str, str]:
    e = BRANCH_WUXING[month_branch]
    st = {e: "旺", SHENG[e]: "相", KE[e]: "死"}
    for w in WUXING:
        if SHENG[w] == e:
            st[w] = "休"
        if KE[w] == e:
            st[w] = "囚"
    return {w: st[w] for w in WUXING}


def relations(pillars: list[dict]) -> dict:
    stems = [p["stem"] for p in pillars]
    branches = [p["branch"] for p in pillars]
    names = PILLAR_NAMES
    gan_rel, zhi_rel = [], []
    in_he = set()
    for i in range(4):
        for j in range(i + 1, 4):
            k = frozenset((stems[i], stems[j]))
            if k in STEM_HE_HUA and stems[i] != stems[j]:
                a, b = sorted((stems[i], stems[j]), key=STEMS.index)
                text = f"{a}{b}合化{STEM_HE_HUA[k]}"
                hit = next((r for r in gan_rel if r["text"] == text), None)
                if hit:
                    hit["pillars"] = sorted(set(hit["pillars"]) | {names[i], names[j]}, key=names.index)
                else:
                    gan_rel.append({"type": "合", "text": text, "pillars": [names[i], names[j]]})
                in_he.update((i, j))
    for i in range(3):
        j = i + 1
        a, b = stems[i], stems[j]
        if i in in_he or j in in_he or a == b:
            continue
        if KE[STEM_WUXING[a]] == STEM_WUXING[b]:
            gan_rel.append({"type": "克", "text": f"{a}克{b}", "pillars": [names[i], names[j]]})
        elif KE[STEM_WUXING[b]] == STEM_WUXING[a]:
            gan_rel.append({"type": "克", "text": f"{b}克{a}", "pillars": [names[i], names[j]]})
    # 三合 / 三会 (full)
    bset = set(branches)
    for trio, e in SANHE_JU.items():
        if set(trio) <= bset:
            zhi_rel.append({"type": "三合", "text": f"{trio}三合{e}局", "pillars": [names[i] for i in range(4) if branches[i] in trio]})
    for trio, e in SANHUI.items():
        if set(trio) <= bset:
            zhi_rel.append({"type": "三会", "text": f"{trio}三会{e}方", "pillars": [names[i] for i in range(4) if branches[i] in trio]})
    seen = set()
    for i in range(4):
        for j in range(i + 1, 4):
            a, b = branches[i], branches[j]
            if a == b:
                if a in ZIXING:
                    zhi_rel.append({"type": "刑", "text": f"{a}{b}自刑", "pillars": [names[i], names[j]]})
                continue
            k = frozenset((a, b))
            if (k, "pair") in seen:
                continue
            seen.add((k, "pair"))
            if k in BRANCH_LIUHE:
                zhi_rel.append({"type": "六合", "text": f"{a}{b}六合{BRANCH_LIUHE[k]}", "pillars": [names[i], names[j]]})
            for trio, e in SANHE_JU.items():
                if a in trio and b in trio and not set(trio) <= bset:
                    mid = trio[1]
                    if mid in (a, b):
                        zhi_rel.append({"type": "半合", "text": f"{a}{b}半合{e}", "pillars": [names[i], names[j]]})
                    else:
                        zhi_rel.append({"type": "拱合", "text": f"{a}{b}拱{mid}", "pillars": [names[i], names[j]]})
            if k in BRANCH_CHONG:
                zhi_rel.append({"type": "冲", "text": f"{a}{b}相冲", "pillars": [names[i], names[j]]})
            if k in XING_PAIRS:
                zhi_rel.append({"type": "刑", "text": f"{a}{b}相刑", "pillars": [names[i], names[j]]})
            for grp in XING_GROUPS:
                if a in grp and b in grp and k not in BRANCH_CHONG:
                    zhi_rel.append({"type": "刑", "text": f"{a}刑{b}", "pillars": [names[i], names[j]]})
            if k in BRANCH_HAI:
                zhi_rel.append({"type": "害", "text": f"{a}{b}相害", "pillars": [names[i], names[j]]})
            if k in BRANCH_PO:
                zhi_rel.append({"type": "破", "text": f"{a}{b}相破", "pillars": [names[i], names[j]]})
            if k in BRANCH_ANHE:
                zhi_rel.append({"type": "暗合", "text": f"{a}{b}暗合", "pillars": [names[i], names[j]]})
    return {"stems": gan_rel, "branches": zhi_rel}


def summary(pillars: list[dict]) -> dict:
    visible: dict[str, list[str]] = {}
    hidden: dict[str, int] = {}
    for p in pillars:
        s = p["stem_shishen"]
        if s != "日主":
            visible.setdefault(s, []).append(p["pos"][0] + "干")
        for h in p["hidden"]:
            hidden[h["shishen"]] = hidden.get(h["shishen"], 0) + 1
    return {"visible": [{"shishen": k, "count": len(v), "where": v} for k, v in visible.items()],
            "hidden": [{"shishen": k, "count": v} for k, v in hidden.items()]}


def day_strength(pillars: list[dict], month_branch: str) -> dict:
    """Crude 日主强弱 estimate (得令/得地/得势), for display only."""
    day = pillars[2]["stem"]
    e = STEM_WUXING[day]
    st = wuxing_status(month_branch)
    score = {"旺": 2, "相": 1, "休": 0, "囚": -1, "死": -2}[st[e]]
    support = 0
    for p in pillars:
        for h in p["hidden"]:
            w = h["wuxing"]
            if w == e or SHENG[w] == e:
                support += 1
            elif KE[w] == e or SHENG[e] == w or KE[e] == w:
                support -= 1
    for i, p in enumerate(pillars):
        if i == 2:
            continue
        w = STEM_WUXING[p["stem"]]
        support += 1 if (w == e or SHENG[w] == e) else -1
    total = score * 2 + support
    label = "偏强" if total > 2 else ("偏弱" if total < -2 else "中和")
    return {"score": total, "label": label, "month_status": st[e]}


def compute_bazi(birth: BirthInput, settings: Optional[BaziSettings] = None, dt_override: Optional[datetime] = None) -> dict:
    settings = settings or BaziSettings()
    solar = birth.solar
    true_solar = cal.true_solar_time(solar, birth.longitude) if birth.use_true_solar_time else solar
    dt = dt_override or true_solar
    ec = cal.eight_char(dt)
    ec.setSect(1 if settings.zi_hour_day == "next" else 2)
    gzs = [ec.getYear(), ec.getMonth(), ec.getDay(), ec.getTime()]
    day_stem = gzs[2][0]
    pillars = [pillar_info(gz, day_stem, PILLAR_NAMES[i]) for i, gz in enumerate(gzs)]
    ctx = SS.Context(year_gz=gzs[0], month_gz=gzs[1], day_gz=gzs[2], hour_gz=gzs[3], is_male=birth.is_male)
    for p in pillars:
        p["shensha"] = SS.pillar_shensha(ctx, p["ganzhi"], p["pos"])
    lunar = cal.lunar_info(dt)
    prev_jie = ec.getLunar().getPrevJie()
    pj_solar = prev_jie.getSolar()
    pj_dt = datetime(pj_solar.getYear(), pj_solar.getMonth(), pj_solar.getDay(), pj_solar.getHour(), pj_solar.getMinute())
    delta = dt - pj_dt
    days, rem = delta.days, delta.seconds // 3600
    return {
        "birth": {"solar": solar.strftime("%Y-%m-%d %H:%M"), "true_solar": true_solar.strftime("%Y-%m-%d %H:%M"),
                  "gender": "男" if birth.is_male else "女", "lunar": lunar.text,
                  "jieqi_note": f"出生于{prev_jie.getName()}（{pj_dt.strftime('%Y-%m-%d %H:%M')}）后 {days} 天 {rem} 小时"},
        "pillars": pillars,
        "day_master": day_stem + STEM_WUXING[day_stem],
        "day_master_stem": day_stem,
        "relations": relations(pillars),
        "wuxing_status": wuxing_status(gzs[1][1]),
        "strength": day_strength(pillars, gzs[1][1]),
        "summary": summary(pillars),
        "taiyuan": ec.getTaiYuan(), "minggong": ec.getMingGong(), "shengong": ec.getShenGong(),
        "settings": settings.as_dict(),
    }
