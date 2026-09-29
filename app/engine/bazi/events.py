"""人生喜事的八字辅助分：流年十神与流年地支对原局的合冲。

只做加减，由紫微事件分主导（上限见 ziwei/events.py 的 bazi_cap）。
流年干支按农历年取（与紫微流年一致）；八字严格按立春换年，年初一两个月会有出入。
"""
from __future__ import annotations

from .. import calendar as cal
from .chart import shishen as _shishen
from .constants import BRANCH_CHONG, BRANCH_LIUHE, SANHE_JU, STEM_WUXING
from .tables import HIDDEN_WEIGHT

# 桃花（咸池）与驿马：按年支或日支所在三合局
TAOHUA = {"申子辰": "酉", "寅午戌": "卯", "巳酉丑": "午", "亥卯未": "子"}
YIMA = {"申子辰": "寅", "寅午戌": "申", "巳酉丑": "亥", "亥卯未": "巳"}


def _group(branch: str) -> str:
    return next(g for g in SANHE_JU if branch in g)


def _main_qi(branch: str) -> str:
    return max(HIDDEN_WEIGHT[branch].items(), key=lambda kv: kv[1])[0]


def _he(a: str, b: str) -> bool:
    return frozenset((a, b)) in BRANCH_LIUHE or (a != b and _group(a) == _group(b))


def _chong(a: str, b: str) -> bool:
    return frozenset((a, b)) in BRANCH_CHONG


def bazi_year_adjust(chart: dict, year: int, event: str) -> tuple[float, list[dict]]:
    gz = cal.year_ganzhi_of(year)
    stem, branch = gz[0], gz[1]
    dm = chart["day_master_stem"]
    P = chart["pillars"]
    year_b, day_b, hour_b = P[0]["branch"], P[2]["branch"], P[3]["branch"]
    male = chart.get("birth", {}).get("gender", "男") == "男"
    gods = {_shishen(dm, stem), _shishen(dm, _main_qi(branch))}
    ranking = (chart.get("analysis") or {}).get("yongshen", {}).get("ranking", [])
    favorable = {r["element"] for r in ranking[:2]}
    sig: list[dict] = []

    def add(delta: float, text: str):
        sig.append({"layer": "八字", "delta": delta, "text": f"流年{gz}{text}"})

    if event == "结婚":
        if male and gods & {"正财", "偏财"}:
            add(0.6 if "正财" in gods else 0.4, "见财星（男命妻星）")
        if not male and gods & {"正官", "七杀"}:
            add(0.6 if "正官" in gods else 0.4, "见官杀（女命夫星）")
        if _he(branch, day_b):
            add(0.4, f"合日支{day_b}（夫妻宫）")
        if branch in (TAOHUA[_group(year_b)], TAOHUA[_group(day_b)]):
            add(0.3, "逢桃花")
        if _chong(branch, day_b):
            add(-0.2, f"冲日支{day_b}")
    elif event == "发财":
        if gods & {"正财", "偏财"}:
            add(0.5, "见财星")
            if STEM_WUXING[stem] in favorable:
                add(0.3, "财星为喜用")
        if gods & {"食神", "伤官"}:
            add(0.2, "食伤生财")
        if gods & {"比肩", "劫财"} and not gods & {"正财", "偏财"}:
            add(-0.2, "比劫夺财")
    elif event == "高升":
        if gods & {"正官", "七杀"}:
            add(0.4, "见官杀")
        if gods & {"正印", "偏印"}:
            add(0.3, "见印星")
        if gods & {"正官", "七杀"} and gods & {"正印", "偏印"}:
            add(0.3, "官印相生")
        if STEM_WUXING[stem] in favorable:
            add(0.2, "流年天干为喜用")
    elif event == "高中":
        if gods & {"正印", "偏印"}:
            add(0.5, "见印星（文书学业）")
        if "正官" in gods:
            add(0.2, "见正官")
        if "食神" in gods:
            add(0.2, "食神吐秀")
    elif event == "添丁":
        if male and gods & {"正官", "七杀"}:
            add(0.5, "见官杀（男命子女星）")
        if not male and gods & {"食神", "伤官"}:
            add(0.5, "见食伤（女命子女星）")
        if _he(branch, hour_b):
            add(0.3, f"合时支{hour_b}（子女宫）")
    elif event == "搬迁":
        if branch in (YIMA[_group(year_b)], YIMA[_group(day_b)]):
            add(0.4, "逢驿马")
        if _chong(branch, year_b) or _chong(branch, day_b):
            add(0.4, "冲年支或日支（动象）")
    return sum(s["delta"] for s in sig), sig
