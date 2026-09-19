"""People + chart API (engine-backed)."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ..engine import calendar as cal
from ..engine.ziwei import horoscope as H
from ..engine.ziwei import hua as HUA
from ..engine.bazi import timeline as TL
from ..engine.wenmo_parser import parse_wenmo_export
from ..models.person import Person, PersonCreate, PersonSummary, PersonUpdate
from ..services.person_service import person_service

router = APIRouter(prefix="/api/people", tags=["people"])


def _person(pid: str) -> Person:
    p = person_service.get(pid)
    if not p:
        raise HTTPException(404, f"人物 {pid} 不存在")
    return p


def _date(s: Optional[str], default_now: bool = True) -> datetime:
    if not s:
        return datetime.now().replace(second=0, microsecond=0)
    try:
        return cal.parse_dt(s)
    except ValueError:
        raise HTTPException(400, f"日期格式错误: {s}")


# ------------------------------------------------------------------ people
@router.get("", response_model=list[PersonSummary])
async def list_people():
    return person_service.list_summaries()


@router.post("", response_model=Person)
async def create_person(req: PersonCreate):
    try:
        return person_service.create(req)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/{pid}", response_model=Person)
async def get_person(pid: str):
    return _person(pid)


@router.put("/{pid}", response_model=Person)
async def update_person(pid: str, req: PersonUpdate):
    _person(pid)
    try:
        return person_service.update(pid, req)
    except Exception as e:
        raise HTTPException(400, str(e))


@router.delete("/{pid}")
async def delete_person(pid: str):
    if not person_service.delete(pid):
        raise HTTPException(404, "人物不存在")
    return {"success": True}


class NoteRequest(BaseModel):
    text: str
    author: str = "user"


@router.post("/{pid}/notes", response_model=Person)
async def add_note(pid: str, req: NoteRequest):
    _person(pid)
    return person_service.add_note(pid, req.text, req.author)


@router.delete("/{pid}/notes/{index}", response_model=Person)
async def delete_note(pid: str, index: int):
    p = _person(pid)
    if 0 <= index < len(p.notes):
        p.notes.pop(index)
        person_service.save(p)
    return p


# ------------------------------------------------------------------- ziwei
@router.get("/{pid}/ziwei")
async def get_ziwei(pid: str):
    _person(pid)
    return person_service.ziwei_json(pid)


@router.get("/{pid}/ziwei/text")
async def get_ziwei_text(pid: str):
    _person(pid)
    return {"text": person_service.ziwei_text(pid)}


@router.get("/{pid}/ziwei/decadals")
async def get_decadals(pid: str):
    _person(pid)
    return H.decadal_list(person_service.astrolabe(pid))


@router.get("/{pid}/ziwei/horoscope")
async def get_horoscope(pid: str, date: Optional[str] = None, hour: Optional[int] = None):
    _person(pid)
    dt = _date(date)
    if hour is not None:
        dt = dt.replace(hour=max(0, min(23, hour)), minute=30 if hour % 2 == 1 else 0)
    return H.by_date(person_service.astrolabe(pid), dt)


@router.get("/{pid}/ziwei/yearly")
async def get_yearly(pid: str, year: int):
    _person(pid)
    return H.yearly(person_service.astrolabe(pid), year)


@router.get("/{pid}/ziwei/yearly-list")
async def get_yearly_list(pid: str, decadal: int = Query(..., ge=0, le=11)):
    """流年 list for the n-th 大限 (0-based, sorted by age)."""
    _person(pid)
    a = person_service.astrolabe(pid)
    d = H.decadal_list(a)[decadal]
    return H.yearly_list(a, d["start_age"], d["end_age"])


@router.get("/{pid}/ziwei/monthly-list")
async def get_monthly_list(pid: str, year: int):
    _person(pid)
    return H.monthly_list(person_service.astrolabe(pid), year)


@router.get("/{pid}/ziwei/daily-list")
async def get_daily_list(pid: str, year: int, month: int, leap: bool = False):
    _person(pid)
    return H.daily_list(person_service.astrolabe(pid), year, month, leap)


@router.get("/{pid}/ziwei/hourly-list")
async def get_hourly_list(pid: str, date: str):
    _person(pid)
    return H.hourly_list(person_service.astrolabe(pid), _date(date))


@router.get("/{pid}/ziwei/fly")
async def get_fly(pid: str, palace: Optional[int] = None):
    _person(pid)
    a = person_service.astrolabe(pid)
    if palace is None:
        return HUA.fly_all(a)
    return HUA.fly(a, palace)


# -------------------------------------------------------------------- bazi
@router.get("/{pid}/bazi")
async def get_bazi(pid: str):
    _person(pid)
    return person_service.bazi(pid)


@router.get("/{pid}/bazi/text")
async def get_bazi_text(pid: str):
    _person(pid)
    return {"text": person_service.bazi_text(pid)}


@router.get("/{pid}/bazi/timeline")
async def get_bazi_timeline(pid: str, date: Optional[str] = None):
    _person(pid)
    return person_service.bazi_timeline(pid, _date(date))


@router.get("/{pid}/bazi/liunian")
async def get_bazi_liunian(pid: str, dayun: int = Query(..., ge=0)):
    p = _person(pid)
    return TL.liunian_list(person_service.birth_input(p), dayun, person_service.bazi_settings(pid))


@router.get("/{pid}/bazi/liuyue")
async def get_bazi_liuyue(pid: str, year: int):
    p = _person(pid)
    return TL.liuyue_list(person_service.birth_input(p), year, person_service.bazi_settings(pid))


# ------------------------------------------------------------ wenmo compare
class CompareRequest(BaseModel):
    text: str


@router.post("/{pid}/wenmo-compare")
async def wenmo_compare(pid: str, req: CompareRequest):
    """Compare a pasted 文墨天机 export with the engine output; returns differences."""
    _person(pid)
    a = person_service.astrolabe(pid)
    try:
        exp = parse_wenmo_export(req.text)
    except Exception as e:
        raise HTTPException(400, f"解析失败: {e}")
    if not exp["palaces"]:
        raise HTTPException(400, "未识别到命盘十二宫，请粘贴完整的文墨天机导出文本")
    diffs = []
    b = exp["basic"]
    for key, got in (("bureau", a.bureau), ("ming_zhu", a.ming_zhu), ("shen_zhu", a.shen_zhu),
                     ("zi_dou", a.zi_dou_branch), ("shen_gong", a.palaces[a.body_index].branch), ("lunar", a.lunar.text)):
        if key in b and b[key] != got:
            diffs.append({"where": "基本信息", "field": key, "engine": got, "wenmo": b[key]})
    for ep in exp["palaces"]:
        p = a.palace_by_branch(ep["ganzhi"][1])
        if p.name != ep["name"] or p.ganzhi != ep["ganzhi"]:
            diffs.append({"where": ep["ganzhi"], "field": "宫名/宫干", "engine": f"{p.name}{p.ganzhi}", "wenmo": f"{ep['name']}{ep['ganzhi']}"})
        for cat in ("major", "minor", "adjective"):
            es = {s["name"]: s for s in ep[cat]}
            gs = {s.name: s for s in p.stars if s.category == cat}
            for n in set(gs) - set(es):
                diffs.append({"where": ep["name"], "field": f"{cat} 多出", "engine": n, "wenmo": ""})
            for n in set(es) - set(gs):
                diffs.append({"where": ep["name"], "field": f"{cat} 缺少", "engine": "", "wenmo": n})
            for n in set(es) & set(gs):
                for fld in ("brightness", "birth_hua", "self_hua_out", "self_hua_in"):
                    if es[n][fld] != getattr(gs[n], fld):
                        diffs.append({"where": ep["name"], "field": f"{n}.{fld}", "engine": getattr(gs[n], fld), "wenmo": es[n][fld]})
        for fld in ("suiqian", "jiangqian", "changsheng", "boshi"):
            if ep[fld] and ep[fld] != getattr(p, fld):
                diffs.append({"where": ep["name"], "field": fld, "engine": getattr(p, fld), "wenmo": ep[fld]})
        if ep["decadal"] and ep["decadal"] != [p.decadal_start, p.decadal_end]:
            diffs.append({"where": ep["name"], "field": "大限", "engine": f"{p.decadal_start}-{p.decadal_end}", "wenmo": ep["decadal"]})
    decs = H.decadal_list(a)
    for ed in exp["decadals"]:
        gd = decs[ed["index"] - 1]
        if gd["ganzhi"] != ed["ganzhi"] or {h["hua"]: h["star"] for h in gd["hua"]} != ed.get("hua"):
            diffs.append({"where": f"第{ed['index']}大限", "field": "干支/四化", "engine": gd["ganzhi"], "wenmo": ed["ganzhi"]})
        for ey in ed["years"]:
            gy = H.yearly(a, ey["year"])
            if a.palaces[gy["index"]].ganzhi != ey.get("soul_ganzhi") or {h["hua"]: h["star"] for h in gy["hua"]} != ey.get("hua"):
                diffs.append({"where": f"{ey['year']}流年", "field": "命宫/四化", "engine": a.palaces[gy["index"]].ganzhi, "wenmo": ey.get("soul_ganzhi")})
    return {"diff_count": len(diffs), "diffs": diffs, "parsed_basic": b,
            "message": "引擎排盘与文墨天机导出完全一致" if not diffs else f"发现 {len(diffs)} 处差异"}


# ---------------------------------------------------------------- schools
@router.get("/meta/schools")
async def schools():
    return {
        "ziwei": {
            "hua_table": {"label": "四化表", "options": {"default": "全书/文墨天机（默认）", "zhongzhou": "中州派（庚干天府科 壬干天府科）", "geng_tianxiang": "庚干天相化忌"}},
            "huoling": {"label": "火铃起法", "options": {"year_hour": "年支+时支（全书，默认）", "year": "仅年支（中州派）"}},
            "tianma": {"label": "天马", "options": {"year": "按年支（默认）", "month": "按月支"}},
            "year_divide": {"label": "年分界", "options": {"lunar": "正月初一（默认）", "lichun": "立春"}},
            "leap_month": {"label": "闰月", "options": {"half": "前半月算本月/后半月算下月（默认）", "current": "算本月", "next": "算下月"}},
            "tianshang_tianshi": {"label": "天伤天使", "options": {"default": "伤在交友、使在疾厄（默认）", "zhongzhou": "中州派（阴男阳女互换）"}},
        },
        "bazi": {
            "yun_sect": {"label": "起运算法", "options": {"2": "按分钟折算（默认）", "1": "三天一年/一天四月/一时辰十天"}},
            "zi_hour_day": {"label": "晚子时日柱", "options": {"current": "算当日（默认）", "next": "算次日"}},
        },
    }
