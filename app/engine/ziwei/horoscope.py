"""运限: 大限 / 小限 / 流年 / 流月 / 流日 / 流时.

Conventions (文墨天机 default):
- 虚岁 = 农历年 − 出生农历年 + 1; 换年在正月初一.
- 大限 from 五行局数 virtual age, 阳男阴女顺行.
- 流年命宫 = the palace whose branch equals the year branch.
- 流月: 流年斗君 = 子年斗君 + 年支; 正月 in that palace, then one palace per month.
- 流日: 流月宫 起初一 顺行; 流时: 流日宫 起子时 顺行.
- 流曜: 流昌流曲(by stem) 流魁流钺(stem) 流禄流羊流陀(stem) 流马(branch) 流鸾流喜(branch).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from .. import calendar as cal
from .astrolabe import (Astrolabe, chang_qu_by_stem, kui_yue, lu_yang_tuo_ma, luan_xi,
                        nianjie_index)
from .constants import BRANCHES, HUA, JIANGQIAN12, STEMS, SUIQIAN12, pbranch, pidx
from .hua import hua_by_stem

LEVEL_NAMES = {"decadal": "大限", "yearly": "流年", "monthly": "流月", "daily": "流日", "hourly": "流时"}
LEVEL_PREFIX = {"decadal": "限", "yearly": "年", "monthly": "月", "daily": "日", "hourly": "时"}
CHILD_PALACES = ["命宫", "财帛宫", "疾厄宫", "夫妻宫", "福德宫", "官禄宫"]  # 童限 一命二财三疾厄四夫五福六官


def _fix(i: int) -> int:
    return i % 12


def horoscope_stars(stem: str, branch: str, level: str) -> list[dict]:
    """流曜 for a stem/branch pair: list of {name, palace_index}."""
    pre = LEVEL_PREFIX[level]
    kui, yue = kui_yue(stem)
    chang, qu = chang_qu_by_stem(stem)
    lu, yang, tuo, ma = lu_yang_tuo_ma(stem, branch)
    hl, tx = luan_xi(branch)
    stars = [(f"{pre}魁", kui), (f"{pre}钺", yue), (f"{pre}昌", chang), (f"{pre}曲", qu), (f"{pre}禄", lu),
             (f"{pre}羊", yang), (f"{pre}陀", tuo), (f"{pre}马", ma), (f"{pre}鸾", hl), (f"{pre}喜", tx)]
    if level == "yearly":
        stars.append(("年解", nianjie_index(branch)))
    return [{"name": n, "palace_index": i} for n, i in stars]


def _level_block(astro: Astrolabe, level: str, stem: str, branch: str, index: int, **extra) -> dict:
    block = {
        "level": level, "name": LEVEL_NAMES[level], "stem": stem, "branch": branch, "ganzhi": stem + branch,
        "index": index, "palace_name": astro.palaces[index].name if index is not None else None,
        "hua": hua_by_stem(astro, stem),
        "stars": horoscope_stars(stem, branch, level) if level != "hourly" else [],
        # palace names as seen from this level's 命宫
        "palace_names": {astro.palaces[(index + k) % 12].index: name
                         for k, name in enumerate(["命宫", "父母宫", "福德宫", "田宅宫", "官禄宫", "交友宫",
                                                   "迁移宫", "疾厄宫", "财帛宫", "子女宫", "夫妻宫", "兄弟宫"])}
        if index is not None else {},
    }
    block.update(extra)
    return block


# ---------------------------------------------------------------------------
# 大限
# ---------------------------------------------------------------------------

def decadal_list(astro: Astrolabe) -> list[dict]:
    """12 大限 sorted by start age."""
    by = astro.birth_year
    res = []
    for p in sorted(astro.palaces, key=lambda x: x.decadal_start):
        blk = _level_block(astro, "decadal", p.stem, p.branch, p.index,
                           start_age=p.decadal_start, end_age=p.decadal_end,
                           start_year=by + p.decadal_start - 1, end_year=by + p.decadal_end - 1)
        res.append(blk)
    return res


def decadal_for_age(astro: Astrolabe, age: int) -> dict:
    for p in astro.palaces:
        if p.decadal_start <= age <= p.decadal_end:
            return _level_block(astro, "decadal", p.stem, p.branch, p.index,
                                start_age=p.decadal_start, end_age=p.decadal_end,
                                start_year=astro.birth_year + p.decadal_start - 1,
                                end_year=astro.birth_year + p.decadal_end - 1, childhood=False)
    # 童限
    name = CHILD_PALACES[min(max(age, 1), 6) - 1]
    p = astro.palace_by_name(name)
    return _level_block(astro, "decadal", p.stem, p.branch, p.index, start_age=age, end_age=age,
                        start_year=astro.birth_year + age - 1, end_year=astro.birth_year + age - 1, childhood=True)


# ---------------------------------------------------------------------------
# 流年 / 小限
# ---------------------------------------------------------------------------

def yearly(astro: Astrolabe, year: int) -> dict:
    """流年 for a lunar/calendar year number (换年按正月初一)."""
    gz = cal.year_ganzhi_of(year)
    stem, branch = gz[0], gz[1]
    idx = pidx(branch)
    age = year - astro.birth_year + 1
    blk = _level_block(astro, "yearly", stem, branch, idx, year=year, age=age)
    # 小限
    age_palace = next((p for p in astro.palaces if age in p.ages or ((age - 1) % 12 + 1) in p.ages), None)
    if age_palace is None:
        for p in astro.palaces:
            if p.ages and (age - p.ages[0]) % 12 == 0:
                age_palace = p
                break
    blk["age_palace"] = {"index": age_palace.index, "name": age_palace.name, "stem": age_palace.stem,
                         "branch": age_palace.branch, "hua": hua_by_stem(astro, age_palace.stem)} if age_palace else None
    # 流年 岁前 / 将前
    sq = {}
    jq = {}
    from .constants import sanhe_group
    jq_start = pidx({"寅": "午", "申": "子", "巳": "酉", "亥": "卯"}[sanhe_group(branch)])
    for i in range(12):
        sq[_fix(idx + i)] = SUIQIAN12[i]
        jq[_fix(jq_start + i)] = JIANGQIAN12[i]
    blk["suiqian"] = sq
    blk["jiangqian"] = jq
    blk["decadal"] = decadal_for_age(astro, age)
    return blk


def yearly_list(astro: Astrolabe, start_age: int, end_age: int) -> list[dict]:
    return [yearly(astro, astro.birth_year + a - 1) for a in range(start_age, end_age + 1)]


# ---------------------------------------------------------------------------
# 流月 / 流日 / 流时
# ---------------------------------------------------------------------------

def _month_palace_index(astro: Astrolabe, year_branch: str, lunar_month: int, is_leap: bool, lunar_day: int) -> int:
    """正月 palace = 子年斗君 + 年支; then +1 per month.  Leap month follows the same half rule."""
    m = lunar_month - 1
    if is_leap and astro.settings.leap_month != "current":
        if astro.settings.leap_month == "next" or lunar_day > 15:
            m += 1
    dou = pidx(astro.zi_dou_branch)
    start = _fix(dou + BRANCHES.index(year_branch))
    return _fix(start + m)


def monthly(astro: Astrolabe, year: int, lunar_month: int, is_leap: bool = False, lunar_day: int = 1) -> dict:
    ygz = cal.year_ganzhi_of(year)
    # 月干支: 五虎遁 by year stem; leap month shares the month 干支 of its host month
    from .constants import TIGER_RULE
    ms = (STEMS.index(TIGER_RULE[ygz[0]]) + lunar_month - 1) % 10
    mb = (2 + lunar_month - 1) % 12
    stem, branch = STEMS[ms], BRANCHES[mb]
    idx = _month_palace_index(astro, ygz[1], lunar_month, is_leap, lunar_day)
    return _level_block(astro, "monthly", stem, branch, idx, year=year, lunar_month=lunar_month, is_leap=is_leap,
                        month_name=("闰" if is_leap else "") + cal.LUNAR_MONTH_NAMES[lunar_month - 1] + "月")


def monthly_list(astro: Astrolabe, year: int) -> list[dict]:
    res = []
    leap = cal.lunar_leap_month(year)
    for m in range(1, 13):
        res.append(monthly(astro, year, m, False))
        if leap == m:
            res.append(monthly(astro, year, m, True))
    return res


def daily(astro: Astrolabe, solar_date: datetime) -> dict:
    li = cal.lunar_info(solar_date.replace(hour=12, minute=0))
    mblk = monthly(astro, li.year, li.month, li.is_leap, li.day)
    idx = _fix(mblk["index"] + li.day - 1)
    dgz = cal.day_ganzhi(solar_date.replace(hour=12))
    return _level_block(astro, "daily", dgz[0], dgz[1], idx, solar_date=solar_date.strftime("%Y-%m-%d"),
                        lunar_year=li.year, lunar_month=li.month, is_leap=li.is_leap, lunar_day=li.day,
                        lunar_text=f"{li.year_gz}年{li.month_name}{cal.LUNAR_DAY_NAMES[li.day - 1]}")


def daily_list(astro: Astrolabe, year: int, lunar_month: int, is_leap: bool = False) -> list[dict]:
    n = cal.lunar_month_days(year, lunar_month, is_leap)
    res = []
    for d in range(1, n + 1):
        sd = cal.solar_from_lunar(year, lunar_month, d, is_leap)
        res.append(daily(astro, sd))
    return res


def hourly(astro: Astrolabe, solar_dt: datetime) -> dict:
    dblk = daily(astro, solar_dt)
    h = cal.hour_index(solar_dt) % 12
    idx = _fix(dblk["index"] + h)
    ec = cal.eight_char(solar_dt)
    tgz = ec.getTime()
    return _level_block(astro, "hourly", tgz[0], tgz[1], idx, hour_index=cal.hour_index(solar_dt),
                        hour_branch=BRANCHES[h])


def hourly_list(astro: Astrolabe, solar_date: datetime) -> list[dict]:
    base = solar_date.replace(hour=0, minute=30)
    res = []
    for i in range(12):
        dt = base + timedelta(hours=2 * i) if i else base
        if i:
            dt = solar_date.replace(hour=(2 * i - 1), minute=30)
        res.append(hourly(astro, dt))
    return res


# ---------------------------------------------------------------------------
# by date (all levels)
# ---------------------------------------------------------------------------

def by_date(astro: Astrolabe, solar_dt: datetime, include_hourly: bool = True) -> dict:
    li = cal.lunar_info(solar_dt)
    y = yearly(astro, li.year)
    m = monthly(astro, li.year, li.month, li.is_leap, li.day)
    d = daily(astro, solar_dt)
    out = {"solar": solar_dt.strftime("%Y-%m-%d %H:%M"), "lunar": li.text, "age": y["age"],
           "decadal": y["decadal"], "yearly": y, "monthly": m, "daily": d}
    if include_hourly:
        out["hourly"] = hourly(astro, solar_dt)
    return out
