"""人生喜事：打分单调、叠宫放大、未来/过去分栏、月份范围、八字加减封顶。虚构出生信息。"""
import json

import pytest
from conftest import sample_birth

from app.engine.bazi.chart import compute_bazi
from app.engine.bazi.events import bazi_year_adjust
from app.engine.ziwei import events as E
from app.engine.ziwei.astrolabe import compute_astrolabe


@pytest.fixture(scope="module")
def astro():
    return compute_astrolabe(sample_birth())


@pytest.fixture(scope="module")
def bazi():
    return compute_bazi(sample_birth())


def test_score_is_monotonic():
    base = [{"layer": "流年", "delta": 1.0, "text": "a"}]
    s0 = E.score_signals(base, {})
    assert E.score_signals(base + [{"layer": "流年", "delta": 1.2, "text": "化禄入"}], {}) > s0
    assert E.score_signals(base + [{"layer": "流年", "delta": -1.0, "text": "化忌入"}], {}) < s0
    assert E.score_signals(base, {"流年": True}) >= s0          # 叠宫只放大正分


def test_layer_weights_order():
    one = lambda layer: E.score_signals([{"layer": layer, "delta": 1.0, "text": ""}], {})
    assert one("流年") > one("大限") > one("本命")


def test_year_signals_have_text(astro):
    sig, dg = E.year_signals(astro, 2026, "结婚")
    assert all({"layer", "delta", "text"} <= set(s) for s in sig)
    assert set(dg) == {"流年", "大限"}


def test_life_events_shape(astro, bazi):
    res = E.life_events(astro, bazi, now_year=2026)
    assert set(res["events"]) == set(E.ALL_EVENTS)
    for ev, block in res["events"].items():
        fut = block["future_top"]
        assert len(fut) == 5 and all(r["year"] >= 2026 for r in fut)
        assert [r["score"] for r in fut] == sorted((r["score"] for r in fut), reverse=True)
        assert all(r["year"] < 2026 and r["pct"] >= 85 for r in block["past_strong"])
        for r in fut + block["past_strong"]:
            assert r["months"] and all(1 <= m["lunar_month"] <= 12 for m in r["months"])
            assert r["age"] >= E.EVENTS[ev]["min_age"]
    json.dumps(res, ensure_ascii=False)


def test_bazi_adjust_is_capped(astro, bazi):
    res = E.life_events(astro, bazi, now_year=2026, events=["结婚"])
    for r in res["events"]["结婚"]["future_top"]:
        assert abs(r["bazi_adj"]) <= E.WEIGHTS["bazi_cap"] * max(abs(r["ziwei"]), 1.0) + 1e-9


def test_bazi_adjust_male_wealth_star_marriage(bazi):
    # 样本日主戊土：壬癸为财星。找一个天干为壬的年份（男命见财星）
    delta, sig = bazi_year_adjust(bazi, 2032, "结婚")      # 2032 壬子年
    assert any("财星" in s["text"] for s in sig) and delta > 0
