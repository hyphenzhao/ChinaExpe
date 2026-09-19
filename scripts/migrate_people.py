"""One-off migration: data/charts/<id>/ziwei.json basic_info -> data/people/<id>.json.

Run from the project root:  python scripts/migrate_people.py
Existing person files are left untouched unless --force is given.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import app  # noqa: E402,F401
from app.engine import calendar as cal  # noqa: E402

CHARTS = ROOT / "data" / "charts"
PEOPLE = ROOT / "data" / "people"

# Known birth data (from 文墨天机 exports), kept out of the repository:
# data/golden/known_people.json = {"<id>": {"display_name", "gender", "solar", "longitude"}}.
# Longitude 120 is 文墨's default input.
KNOWN_FILE = ROOT / "data" / "golden" / "known_people.json"
KNOWN = json.loads(KNOWN_FILE.read_text(encoding="utf-8")) if KNOWN_FILE.exists() else {}


def _infer_longitude(clock: str, true_solar: str) -> float:
    """Back-solve longitude from 文墨's clock/true-solar pair (±0.25°)."""
    c = cal.parse_dt(clock)
    t = cal.parse_dt(true_solar)
    diff_min = (t - c).total_seconds() / 60.0
    eot = cal.equation_of_time_minutes(c)
    return round(120.0 + (diff_min - eot) / 4.0, 2)


def main(force: bool = False):
    PEOPLE.mkdir(parents=True, exist_ok=True)
    for d in sorted(CHARTS.iterdir()):
        if not d.is_dir():
            continue
        pid = d.name
        out = PEOPLE / f"{pid}.json"
        if out.exists() and not force:
            print(f"skip {pid} (exists)")
            continue
        info = KNOWN.get(pid, {})
        zj = d / "ziwei.json"
        basic = {}
        if zj.exists():
            try:
                basic = json.loads(zj.read_text(encoding="utf-8")).get("basic_info", {})
            except Exception:
                pass
        display = info.get("display_name") or basic.get("display_name") or pid
        gender = info.get("gender") or basic.get("gender", "男")[-1]
        solar = info.get("solar") or basic.get("clock_time")
        if not solar:
            print(f"!! {pid}: no birth time, skipped")
            continue
        solar = re.sub(r"(\d{4})-(\d{1,2})-(\d{1,2}) (\d{1,2}):(\d{1,2})",
                       lambda m: f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d} {int(m.group(4)):02d}:{int(m.group(5)):02d}", solar)
        lon = info.get("longitude")
        note = ""
        if lon is None and basic.get("clock_time") and basic.get("true_solar_time"):
            lon = _infer_longitude(basic["clock_time"], basic["true_solar_time"])
            note = f"经度由文墨导出的钟表时间/真太阳时反推（≈{lon}）"
        person = {
            "id": pid, "display_name": display, "gender": gender,
            "birth": {"solar": solar, "longitude": lon or 120.0, "place": "", "use_true_solar_time": True,
                      "hour_override": None, "time_source": "clock"},
            "settings": {"ziwei": {"profile": "wenmo"}, "bazi": {}},
            "notes": ([{"ts": datetime.now().isoformat(timespec="seconds"), "text": note, "author": "system"}] if note else []),
            "tags": [],
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }
        out.write_text(json.dumps(person, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"wrote {out.name}: {display} {gender} {solar} @ {person['birth']['longitude']}")


if __name__ == "__main__":
    main(force="--force" in sys.argv)
