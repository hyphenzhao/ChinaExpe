"""Engine invariants on a fictional chart (no personal data)."""
from datetime import datetime

import pytest
from conftest import sample_birth
from app.engine.ziwei.astrolabe import compute_astrolabe
from app.engine.ziwei import horoscope as H
from app.engine.bazi.chart import compute_bazi
from app.engine.bazi.timeline import timeline_for_date

MAJOR = ["紫微", "天机", "太阳", "武曲", "天同", "廉贞", "天府",
         "太阴", "贪狼", "巨门", "天相", "天梁", "七杀", "破军"]


@pytest.fixture(scope="module")
def astro():
    return compute_astrolabe(sample_birth())


def test_twelve_distinct_palaces(astro):
    assert len(astro.palaces) == 12
    assert len({p.name for p in astro.palaces}) == 12
    assert len({p.branch for p in astro.palaces}) == 12


def test_palace_stems_follow_year_stem(astro):
    # 五虎遁: a 己 year starts the 寅 palace at 丙寅 (index 0 is 寅).
    assert astro.palaces[0].ganzhi == "丙寅"


def test_each_major_star_placed_once(astro):
    placed = [s.name for p in astro.palaces for s in p.stars if s.category == "major"]
    assert sorted(placed) == sorted(MAJOR)


def test_ziwei_tianfu_mirror(astro):
    # 天府 mirrors 紫微 across the 寅-申 axis.
    def where(name):
        return next(p.index for p in astro.palaces for s in p.stars if s.name == name)
    assert where("天府") == (12 - where("紫微")) % 12


def test_birth_hua_for_ji_year(astro):
    # 全书四化表, 己 stem: 武曲禄 贪狼权 天梁科 文曲忌
    assert dict(astro.birth_hua) == {"禄": "武曲", "权": "贪狼", "科": "天梁", "忌": "文曲"}


def test_decadals_are_contiguous(astro):
    decs = H.decadal_list(astro)
    assert len(decs) == 12
    for d in decs:
        assert d["end_age"] - d["start_age"] == 9
    for a, b in zip(decs, decs[1:]):
        assert b["start_age"] == a["end_age"] + 1


def test_flow_ganzhi_by_date(astro):
    d = H.by_date(astro, datetime(2026, 9, 18, 10, 30))
    assert d["yearly"]["ganzhi"] == "丙午"
    assert d["daily"]["ganzhi"] == "乙未"


def test_bazi_sample():
    c = compute_bazi(sample_birth())
    P = c["pillars"]
    assert [p["ganzhi"] for p in P] == ["己卯", "丙子", "戊午", "戊午"]
    assert [p["stem_shishen"] for p in P] == ["劫财", "偏印", "日主", "比肩"]


def test_bazi_timeline_sample():
    tl = timeline_for_date(sample_birth(), datetime(2026, 7, 22, 12, 0))
    assert tl["forward"] is False  # 阴年 (己) male runs backwards
    assert tl["liunian"]["ganzhi"] == "丙午"
    assert tl["liuyue"]["ganzhi"] == "乙未"
    assert tl["liuri"]["ganzhi"] == "丁酉"
