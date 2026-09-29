"""时辰前后挪动：真太阳时反算、子时跨日、候选盘数量与一致性。虚构出生信息。"""
from dataclasses import replace
from datetime import datetime

import pytest
from conftest import sample_birth

from app.engine import calendar as cal
from app.engine import timeshift as TS
from app.engine.bazi.chart import compute_bazi
from app.engine.ziwei.astrolabe import compute_astrolabe

BRANCH = "子丑寅卯辰巳午未申酉戌亥子"


@pytest.mark.parametrize("lon", [87.6, 116.4, 121.5])
def test_clock_for_true_solar_round_trip(lon):
    b = replace(sample_birth(), longitude=lon)
    target = datetime(2000, 7, 15, 14, 0)
    clock = TS.clock_for_true_solar(target, b)
    assert abs((cal.true_solar_time(clock, lon) - target).total_seconds()) <= 60


def test_hai_to_late_zi_to_next_early_zi():
    b = replace(sample_birth(), solar=datetime(2000, 1, 1, 22, 0), longitude=120.0)
    d0, s0 = TS.current_slot(b)
    assert s0 == 11                                    # 亥
    late = TS.shift(b, slots=1)
    assert TS.current_slot(late) == (d0, 12)           # 当天晚子
    early = TS.shift(b, slots=2)
    d2, s2 = TS.current_slot(early)
    assert s2 == 0 and (d2 - d0).days == 1             # 次日早子


def test_early_zi_back_to_previous_late_zi():
    b = replace(sample_birth(), solar=datetime(2000, 1, 2, 0, 30), longitude=120.0)
    d, s = TS.current_slot(TS.shift(b, slots=-1))
    assert s == 12 and d.isoformat() == "2000-01-01"


def test_days_only_keeps_minutes():
    b = sample_birth()
    moved = TS.shift(b, days=1)
    assert (moved.solar - b.solar).total_seconds() == 86400


def test_candidate_counts():
    b = sample_birth()
    day = TS.candidates(b)
    assert len(day) == 14
    assert TS.current_slot(day[0])[1] == 12                                   # 前一天晚子
    assert TS.current_slot(day[1])[0] != TS.current_slot(day[0])[0]
    around = TS.candidates(b, approx=datetime(2000, 1, 1, 12, 10))
    assert len(around) == 5
    assert [TS.current_slot(c)[1] for c in around] == [4, 5, 6, 7, 8]        # 辰巳午未申


def test_candidates_are_consistent_across_both_engines():
    for c in TS.candidates(sample_birth()):
        _, slot = TS.current_slot(c)
        a = compute_astrolabe(c)
        assert a.hour_index == slot
        hour_pillar = compute_bazi(c)["pillars"][3]["branch"]
        assert hour_pillar == BRANCH[slot]


def test_describe_label():
    d = TS.describe(TS.shift(sample_birth(), slots=1))
    assert d["slot_name"].endswith("时") and "–" in d["range"]
