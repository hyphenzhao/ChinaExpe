"""起运 / 大运 / 流年 / 流月 / 流日 / 流时 (WhatFUHaveDone-style chain)."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from lunar_python import Solar

from .. import calendar as cal
from ..settings import BaziSettings, BirthInput
from .chart import changsheng, compute_bazi, nayin, shishen, xunkong
from .constants import HIDDEN, STEM_WUXING
from . import shensha as SS


def _flow_pillar(ctx: SS.Context, gz: str, pos: str, day_stem: str) -> dict:
    g, z = gz[0], gz[1]
    return {
        "pos": pos, "ganzhi": gz, "stem": g, "branch": z,
        "stem_wuxing": STEM_WUXING[g],
        "stem_shishen": shishen(day_stem, g),
        "hidden": [{"stem": h, "shishen": shishen(day_stem, h)} for h in HIDDEN[z]],
        "branch_shishen": [shishen(day_stem, h) for h in HIDDEN[z]],
        "nayin": nayin(gz), "xunkong": xunkong(gz),
        "dishi": changsheng(day_stem, z), "zizuo": changsheng(g, z),
        "shensha": SS.pillar_shensha(ctx, gz, pos),
    }


def _yun(birth: BirthInput, settings: BaziSettings):
    solar = birth.solar
    dt = cal.true_solar_time(solar, birth.longitude) if birth.use_true_solar_time else solar
    ec = cal.eight_char(dt)
    return ec, ec.getYun(1 if birth.is_male else 0, settings.yun_sect), dt


def dayun_list(birth: BirthInput, settings: Optional[BaziSettings] = None, n: int = 10) -> dict:
    settings = settings or BaziSettings()
    ec, yun, dt = _yun(birth, settings)
    day_stem = ec.getDayGan()
    ctx = SS.Context(ec.getYear(), ec.getMonth(), ec.getDay(), ec.getTime(), birth.is_male)
    start = yun.getStartSolar()
    res = {
        "forward": yun.isForward(),
        "start": {"years": yun.getStartYear(), "months": yun.getStartMonth(), "days": yun.getStartDay(),
                  "hours": yun.getStartHour(),
                  "date": f"{start.getYear():04d}-{start.getMonth():02d}-{start.getDay():02d}",
                  "age_decimal": round(yun.getStartYear() + yun.getStartMonth() / 12 + yun.getStartDay() / 365, 1),
                  "text": f"{yun.getStartYear()}年{yun.getStartMonth()}个月{yun.getStartDay()}天起运"},
        "dayun": [],
    }
    for dy in yun.getDaYun(n + 1):
        if dy.getIndex() < 1:
            res["dayun"].append({"index": 0, "ganzhi": "", "label": "起运前", "start_year": dy.getStartYear(),
                                 "end_year": dy.getEndYear(), "start_age": dy.getStartAge(), "end_age": dy.getEndAge()})
            continue
        p = _flow_pillar(ctx, dy.getGanZhi(), "大运", day_stem)
        p.update({"index": dy.getIndex(), "start_year": dy.getStartYear(), "end_year": dy.getEndYear(),
                  "start_age": dy.getStartAge(), "end_age": dy.getEndAge()})
        res["dayun"].append(p)
    return res


def liunian_list(birth: BirthInput, dayun_index: int, settings: Optional[BaziSettings] = None) -> list[dict]:
    settings = settings or BaziSettings()
    ec, yun, dt = _yun(birth, settings)
    day_stem = ec.getDayGan()
    ctx = SS.Context(ec.getYear(), ec.getMonth(), ec.getDay(), ec.getTime(), birth.is_male)
    dys = yun.getDaYun(max(dayun_index + 1, 2))
    dy = dys[dayun_index]
    out = []
    for ln in dy.getLiuNian():
        p = _flow_pillar(ctx, ln.getGanZhi(), "流年", day_stem)
        p.update({"year": ln.getYear(), "age": ln.getAge(), "index": ln.getIndex()})
        out.append(p)
    return out


def liuyue_list(birth: BirthInput, year: int, settings: Optional[BaziSettings] = None) -> list[dict]:
    """12 节气 months of a 流年 (寅月 first) with their 干支."""
    settings = settings or BaziSettings()
    ec, yun, dt = _yun(birth, settings)
    day_stem = ec.getDayGan()
    ctx = SS.Context(ec.getYear(), ec.getMonth(), ec.getDay(), ec.getTime(), birth.is_male)
    ygz = cal.year_ganzhi_of(year)
    from ..ziwei.constants import TIGER_RULE
    from .constants import STEMS, BRANCHES
    out = []
    jq = Solar.fromYmd(year, 6, 1).getLunar().getJieQiTable()
    names = ["立春", "惊蛰", "清明", "立夏", "芒种", "小暑", "立秋", "白露", "寒露", "立冬", "大雪", "小寒"]
    for i in range(12):
        gz = STEMS[(STEMS.index(TIGER_RULE[ygz[0]]) + i) % 10] + BRANCHES[(2 + i) % 12]
        p = _flow_pillar(ctx, gz, "流月", day_stem)
        jname = names[i]
        # 小寒 of the next calendar year belongs to this 流年's 丑月
        key = jname
        s = jq.get(key)
        if i == 11:
            s = Solar.fromYmd(year + 1, 1, 10).getLunar().getJieQiTable().get("小寒")
        p.update({"index": i, "month_no": i + 1, "jie": jname,
                  "start": f"{s.getYear():04d}-{s.getMonth():02d}-{s.getDay():02d}" if s else None})
        out.append(p)
    return out


def _jieqi_year(dt: datetime) -> int:
    """Calendar year number of the 立春-based year containing ``dt``."""
    jq = Solar.fromYmd(dt.year, 6, 1).getLunar().getJieQiTable()
    lc = jq["立春"]
    lc_dt = datetime(lc.getYear(), lc.getMonth(), lc.getDay(), lc.getHour(), lc.getMinute())
    return dt.year if dt >= lc_dt else dt.year - 1


def timeline_for_date(birth: BirthInput, date: datetime, settings: Optional[BaziSettings] = None) -> dict:
    """大运→流年→流月→流日(→流时) chain for ``date`` plus the sibling lists for the UI strips."""
    settings = settings or BaziSettings()
    ec, yun, dt = _yun(birth, settings)
    day_stem = ec.getDayGan()
    ctx = SS.Context(ec.getYear(), ec.getMonth(), ec.getDay(), ec.getTime(), birth.is_male)
    dys = dayun_list(birth, settings)
    year_num = _jieqi_year(date)
    birth_year = dt.year
    age = year_num - birth_year + 1
    cur_dy = None
    for d in dys["dayun"]:
        if d["start_year"] <= year_num <= d["end_year"]:
            cur_dy = d
            break
    if cur_dy is None:
        cur_dy = dys["dayun"][-1]
    liunian = liunian_list(birth, cur_dy["index"], settings)
    cur_ln = next((x for x in liunian if x["year"] == year_num), None)
    if cur_ln is None:
        gz = cal.year_ganzhi_of(year_num)
        cur_ln = _flow_pillar(ctx, gz, "流年", day_stem)
        cur_ln.update({"year": year_num, "age": age, "index": -1})
    liuyue = liuyue_list(birth, year_num, settings)
    dec = cal.eight_char(date.replace(hour=12, minute=0))
    mgz = dec.getMonth()
    cur_ly = next((m for m in liuyue if m["ganzhi"] == mgz), None)
    if cur_ly is None:
        cur_ly = _flow_pillar(ctx, mgz, "流月", day_stem)
    dgz = dec.getDay()
    cur_lr = _flow_pillar(ctx, dgz, "流日", day_stem)
    li = cal.lunar_info(date.replace(hour=12))
    cur_lr.update({"date": date.strftime("%Y-%m-%d"), "lunar": f"{li.year_gz}年{li.month_name}{cal.LUNAR_DAY_NAMES[li.day - 1]}"})
    hec = cal.eight_char(date)
    cur_ls = _flow_pillar(ctx, hec.getTime(), "流时", day_stem)
    cur_ls.update({"hour_branch": hec.getTime()[1]})
    return {
        "date": date.strftime("%Y-%m-%d %H:%M"), "age": age, "year": year_num,
        "start": dys["start"], "forward": dys["forward"],
        "dayun_all": dys["dayun"], "liunian_all": liunian, "liuyue_all": liuyue,
        "dayun": cur_dy, "liunian": cur_ln, "liuyue": cur_ly, "liuri": cur_lr, "liushi": cur_ls,
    }
