"""Chart export: write an AI-readable bundle per person to data/exports/.

Every time a person is created or edited the engine recomputes the chart and
this module drops two files next to each other:

    data/exports/<pid>.json   machine-readable bundle (紫微 + 子平 + 运限)
    data/exports/<pid>.md     the same chart as the compact text the LLM reads
    data/exports/index.json   one row per person, for a reader to discover files

The JSON is the contract for an external reader such as a Claude Code session:
it must never need to recompute a chart, only read these files.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from ..engine.ziwei import horoscope as H
from ..version import VERSION
from .person_service import person_service

ROOT = Path(__file__).resolve().parent.parent.parent
EXPORT_DIR = ROOT / "data" / "exports"

SCHEMA_VERSION = 1


def _safe(fn, default=None):
    try:
        return fn()
    except Exception as e:  # a broken person file must not break the others
        return default if default is not None else {"error": str(e)}


def build_bundle(pid: str, as_of: Optional[datetime] = None) -> dict:
    """Everything a reader needs about one person, computed by the engine."""
    person = person_service.get(pid)
    if not person:
        raise KeyError(pid)
    now = (as_of or datetime.now()).replace(second=0, microsecond=0)
    astro = person_service.astrolabe(pid)

    ziwei = person_service.ziwei_json(pid)
    horoscope = _safe(lambda: H.by_date(astro, now))
    cur_dec = (horoscope or {}).get("decadal") or {}

    bundle = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": now.isoformat(timespec="minutes"),
        "engine": {"app_version": VERSION, "ziwei_profile": "文墨天机默认口径",
                   "bazi_profile": "测测 App 口径", "note": "盘面由引擎计算，读者不要自行推算"},
        "person": {
            "id": person.id,
            "display_name": person.display_name,
            "gender": person.gender,
            "birth": person.birth.model_dump(),
            "settings": person.settings.model_dump(),
            "tags": person.tags,
            "notes": [n.model_dump() for n in person.notes],
            "updated_at": person.updated_at,
        },
        "ziwei": ziwei,
        "ziwei_horoscope_now": horoscope,
        "bazi": _safe(lambda: person_service.bazi(pid)),
        "bazi_timeline_now": _safe(lambda: person_service.bazi_timeline(pid, now)),
        "text": {
            "ziwei": _safe(lambda: person_service.ziwei_text(pid), ""),
            "ziwei_horoscope": _safe(lambda: person_service.horoscope_text(pid, now), ""),
            "bazi": _safe(lambda: person_service.bazi_text(pid), ""),
            "bazi_timeline": _safe(lambda: person_service.bazi_timeline_text(pid, now), ""),
        },
    }
    # 流年 of the current 大限 and 流月 of the current year, so a reader can work
    # through a decade without calling the API again.
    if cur_dec.get("start_age") is not None:
        bundle["ziwei_yearly_list"] = _safe(
            lambda: H.yearly_list(astro, cur_dec["start_age"], cur_dec["end_age"]), [])
    bundle["ziwei_monthly_list"] = _safe(lambda: H.monthly_list(astro, now.year), [])
    return bundle


def markdown_bundle(bundle: dict) -> str:
    t = bundle.get("text", {})
    p = bundle.get("person", {})
    return "\n\n".join(filter(None, [
        f"# {p.get('display_name')}（{p.get('id')}）命盘导出",
        f"生成时间 {bundle.get('generated_at')}；运限基准 {bundle.get('as_of')}；"
        f"引擎版本 {bundle.get('engine', {}).get('app_version')}。盘面由引擎计算，请勿自行推算。",
        t.get("ziwei", ""), t.get("ziwei_horoscope", ""), t.get("bazi", ""), t.get("bazi_timeline", ""),
    ]))


def write_person(pid: str, as_of: Optional[datetime] = None) -> dict:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    bundle = build_bundle(pid, as_of)
    jp = EXPORT_DIR / f"{pid}.json"
    mp = EXPORT_DIR / f"{pid}.md"
    jp.write_text(json.dumps(bundle, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    mp.write_text(markdown_bundle(bundle), encoding="utf-8")
    return {"id": pid, "json": str(jp), "md": str(mp), "bytes": jp.stat().st_size,
            "as_of": bundle["as_of"]}


def write_index() -> Path:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    rows = []
    for s in person_service.list_summaries():
        jp = EXPORT_DIR / f"{s.id}.json"
        rows.append({"id": s.id, "display_name": s.display_name, "gender": s.gender,
                     "birth_solar": s.birth_solar, "lunar": s.lunar, "bureau": s.bureau,
                     "json": f"{s.id}.json", "md": f"{s.id}.md",
                     "exported_at": datetime.fromtimestamp(jp.stat().st_mtime).isoformat(timespec="seconds")
                     if jp.exists() else None})
    path = EXPORT_DIR / "index.json"
    path.write_text(json.dumps({"schema_version": SCHEMA_VERSION,
                                "generated_at": datetime.now().isoformat(timespec="seconds"),
                                "app_version": VERSION, "people": rows},
                               ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def write_all(as_of: Optional[datetime] = None) -> list[dict]:
    out = []
    for pid in person_service.list_ids():
        try:
            out.append(write_person(pid, as_of))
        except Exception as e:
            out.append({"id": pid, "error": str(e)})
    write_index()
    return out


def _on_person_saved(person) -> None:
    write_person(person.id)
    write_index()


# Auto-export whenever a person is created, edited, or annotated.
person_service.on_save(_on_person_saved)
