"""子平量化：权重表、身强弱档位、从格门槛、格局取格次序、喜用调候。手工构造四柱，不含个人数据。"""
import json

import pytest
from conftest import sample_birth

from app.engine.bazi import analysis as A
from app.engine.bazi import tables as T
from app.engine.bazi.chart import compute_bazi, day_strength, pillar_info, relations, wuxing_status
from app.engine.bazi.constants import HIDDEN

POS = ["年柱", "月柱", "日柱", "时柱"]


def make_chart(*gzs: str) -> dict:
    """用四个干支拼一个与 compute_bazi 同形的最小命盘。"""
    day = gzs[2][0]
    pillars = [pillar_info(gz, day, POS[i]) for i, gz in enumerate(gzs)]
    return {"pillars": pillars, "day_master_stem": day, "relations": relations(pillars),
            "wuxing_status": wuxing_status(gzs[1][1]), "strength": day_strength(pillars, gzs[1][1])}


def test_hidden_weights_are_complete():
    for branch, stems in HIDDEN.items():
        w = T.HIDDEN_WEIGHT[branch]
        assert set(w) == set(stems), branch
        assert sum(w.values()) == 100, branch
    assert T.hidden_kind("巳", "戊") == "中气" and T.hidden_kind("巳", "庚") == "余气"


def test_tiaohou_table_shape():
    assert len(T.TIAOHOU) == 10
    assert all(len(row) == 12 for row in T.TIAOHOU.values())
    assert T.TIAOHOU["甲"]["寅"] == "丙癸"


def test_strong_wood_is_cong_qiang_candidate():
    c = make_chart("壬寅", "癸卯", "甲寅", "乙亥")
    st = A.strength(c)
    assert st["same_pct"] >= 80 and st["special"] == "从强候选"
    assert st["de_ling"] and st["de_di"] and st["de_shi"]
    names = {s["name"] for s in A.geju(c, st)["special"]}
    assert names & {"从强格", "从旺格"}


def test_rootless_weak_is_cong_candidate():
    c = make_chart("丙午", "甲午", "乙巳", "丙戌")
    st = A.strength(c)
    assert st["same_pct"] < 20 and st["special"] == "从弱候选"
    assert not st["de_di"]
    names = {s["name"] for s in A.geju(c, st)["special"]}
    assert "从儿格" in names          # 食伤（火）最旺


def test_root_blocks_cong_ruo():
    # 与上例相近，但日支换成卯（乙木本气根），不应再作从弱
    st = A.strength(make_chart("丙午", "甲午", "乙卯", "丙戌"))
    assert st["special"] is None


def test_shishen_share_sums_to_100():
    sh = A.shishen_share(make_chart("丙子", "庚寅", "庚辰", "甲申"))
    assert abs(sum(r["pct"] for r in sh["items"]) - 100) < 0.6
    assert abs(sum(g["pct"] for g in sh["groups"]) - 100) < 0.6
    assert all(r["shishen"] != "日主" for r in sh["items"])


def test_primary_prefers_benqi_tou():
    # 庚日寅月：本气甲（偏财）在时干透，中气丙（七杀）在年干透 → 取偏财格
    gj = A.geju(make_chart("丙子", "庚寅", "庚辰", "甲申"))
    assert gj["primary"]["name"] == "偏财格"
    assert abs(sum(c["pct"] for c in gj["candidates"]) - 100) < 0.6 or len(gj["candidates"]) == 5
    assert gj["candidates"][0]["name"] == "偏财格"


def test_jianlu_named_for_bijian_month():
    gj = A.geju(make_chart("丙子", "庚寅", "甲辰", "丙寅"))    # 甲日寅月，本气甲为比肩
    assert gj["primary"]["name"] == "建禄格" and "note" in gj["primary"]


def test_yuqi_bijie_tou_is_not_jianlu():
    # 戊日寅月，余气戊透出为比肩，不作建禄；本气甲（七杀）未透 → 取本气七杀格
    gj = A.geju(make_chart("丁卯", "戊寅", "戊辰", "庚申"))
    assert gj["primary"]["name"] == "七杀格"
    assert all(c["name"] != "建禄格" for c in gj["candidates"])


def test_huaqi_listed_once():
    specials = A.geju(make_chart("庚午", "己丑", "甲辰", "己巳"))["special"]
    names = [s["name"] for s in specials]
    assert len(names) == len(set(names))


def test_winter_wood_wants_fire():
    ys = A.yongshen(make_chart("壬子", "壬子", "甲子", "甲子"))
    top2 = [r["element"] for r in ys["ranking"][:2]]
    assert "火" in top2
    assert any(x["layer"] == "调候" for x in ys["ranking"][0]["reasons"] + ys["ranking"][1]["reasons"])


def test_summer_fire_wants_water():
    # 身强（约 78%）但未到从强：扶抑取克泄，调候取壬，夏生缺水 → 水为用神
    ys = A.yongshen(make_chart("庚午", "甲午", "丙午", "庚寅"))
    assert ys["ranking"][0]["element"] == "水"
    assert [r["role"] for r in ys["ranking"]] == T.ROLES
    assert len({r["element"] for r in ys["ranking"]}) == 5


def test_cong_qiang_follows_the_strong_element():
    # 满盘火木已成从强：顺势取火，水反为忌
    c = make_chart("丙午", "甲午", "丙午", "甲午")
    assert A.strength(c)["special"] == "从强候选"
    ys = A.yongshen(c)
    assert ys["ranking"][0]["element"] == "火" and ys["method"].startswith("从格")
    assert ys["ranking"][-1]["element"] == "水"


def test_compute_bazi_carries_analysis():
    c = compute_bazi(sample_birth())
    a = c["analysis"]
    assert a["version"] == T.VERSION
    assert set(a) >= {"strength", "shishen", "geju", "yongshen"}
    assert 0 <= a["strength"]["same_pct"] <= 100
    json.dumps(a, ensure_ascii=False)          # JSON 可序列化
