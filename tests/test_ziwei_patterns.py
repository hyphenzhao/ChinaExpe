"""紫微格局：手工摆盘逐条验证成格与不成格，事实只陈述不改变吉凶。"""
import json

import pytest
from conftest import sample_birth

from app.engine.ziwei import patterns as P
from app.engine.ziwei.astrolabe import compute_astrolabe
from app.engine.ziwei.view import make_view


def names(view):
    return {p["name"] for p in P.detect(view)["patterns"]}


def test_rule_ids_unique():
    ids = [r.id for r in P.RULES]
    assert len(ids) == len(set(ids))
    assert sum(r.kind == "吉" for r in P.RULES) >= 40 and sum(r.kind == "凶" for r in P.RULES) >= 12


def test_view_offsets_match_engine():
    a = compute_astrolabe(sample_birth())
    from app.engine.ziwei.view import from_astrolabe
    v = from_astrolabe(a)
    for key, name in (("官", "官禄宫"), ("财", "财帛宫"), ("迁", "迁移宫"), ("夫", "夫妻宫"), ("兄", "兄弟宫")):
        assert v.name(v.at(v.soul, key)) == name


@pytest.mark.parametrize("layout,soul,expected,present", [
    ({"寅": ["紫微", "天府"]}, "寅", "紫府同宫", True),
    ({"辰": ["紫微", "天府"]}, "辰", "紫府同宫", False),                    # 地支不对
    ({"卯": ["太阳", "天梁"]}, "卯", "日照雷门", True),
    ({"酉": ["太阳", "天梁"]}, "酉", "日照雷门", False),
    ({"午": ["太阳"]}, "午", "金灿光辉", True),
    ({"亥": ["太阴"]}, "亥", "月朗天门", True),
    ({"子": ["巨门"]}, "子", "石中隐玉", True),
    ({"辰": ["巨门"]}, "辰", "石中隐玉", False),
    ({"丑": ["武曲", "贪狼"]}, "丑", "贪武同行", True),
    ({"子": ["七杀"]}, "子", "七杀朝斗", True),
    ({"辰": ["贪狼", "火星"]}, "辰", "火贪格", True),
    ({"午": ["天梁"]}, "午", "寿星入庙", True),
    ({"寅": ["廉贞"]}, "寅", "雄宿朝元", True),
    ({"寅": ["廉贞", "天府"]}, "寅", "雄宿朝元", False),                    # 须独坐
])
def test_single_palace_rules(layout, soul, expected, present):
    assert (expected in names(make_view(layout, soul))) is present


def test_empty_ming_borrows_opposite_for_sha_po_lang():
    # 命宫在寅无主星，对宫申有七杀 → 借星成杀破狼
    v = make_view({"申": ["七杀"]}, "寅")
    res = P.detect(v)
    assert res["ming"]["borrowed"] and "七杀" in res["ming"]["borrowed_majors"]
    assert "杀破狼" in {p["name"] for p in res["patterns"]}


def test_matou_daijian_needs_tongyin_or_tanlang():
    assert "马头带箭" in names(make_view({"午": ["天同", "太阴", "擎羊"]}, "午"))
    assert "马头带箭" not in names(make_view({"午": ["七杀", "擎羊"]}, "午"))


def test_mingli_fengkong_ignores_tiankong():
    assert "命里逢空" not in names(make_view({"午": ["七杀", "天空"]}, "午"))
    assert "命里逢空" in names(make_view({"午": ["七杀", "地劫"]}, "午"))


def test_mingzhu_chuhai_needs_empty_ming():
    base = {"卯": ["太阳"], "亥": ["太阴"], "丑": ["天同", "巨门"]}
    assert "明珠出海" in names(make_view(base, "未"))
    assert "明珠出海" not in names(make_view({**base, "未": ["天府"]}, "未"))


def test_zifu_chaoyuan_needs_a_helper():
    # 命在子：官禄 = 辰，财帛 = 申
    layout = {"辰": ["紫微"], "申": ["天府"]}
    assert "紫府朝垣" not in names(make_view(layout, "子"))
    assert "紫府朝垣" in names(make_view({**layout, "午": ["左辅"]}, "子"))    # 对宫见左辅


def test_junchen_supersedes_fubi():
    # 命在午：官禄 戌、财帛 寅、迁移 子；左右在三方，天相在财帛
    v = make_view({"午": ["紫微"], "戌": ["左辅"], "子": ["右弼"], "寅": ["天相"]}, "午")
    n = names(v)
    assert "君臣庆会" in n and "辅弼拱主" not in n


def test_jia_patterns():
    # 命在午，夹宫为巳与未
    assert "日月夹命" in names(make_view({"巳": ["太阳"], "未": ["太阴"]}, "午"))
    assert "昌曲夹命" in names(make_view({"巳": ["文曲"], "未": ["文昌"]}, "午"))
    v = make_view({"午": ["廉贞"], "巳": ["擎羊"], "未": ["陀罗"]}, "午", birth_hua={"忌": "廉贞"})
    n = names(v)
    assert "羊陀夹忌" in n and "羊陀夹命" not in n


def test_sihua_patterns():
    # 命在寅：官禄 午、财帛 戌、迁移 申
    hua = {"禄": "武曲", "权": "贪狼", "科": "天梁", "忌": "文曲"}
    v = make_view({"寅": ["天梁"], "午": ["武曲"], "戌": ["贪狼"]}, "寅", birth_hua=hua)
    n = names(v)
    assert "三奇加会" in n and "权禄巡逢" not in n
    assert "甲第登庸" in n


def test_context_is_facts_only():
    v = make_view({"寅": ["紫微", "天府", "擎羊"], "申": ["地劫"]}, "寅")
    res = P.detect(v)
    hit = next(p for p in res["patterns"] if p["name"] == "紫府同宫")
    assert hit["kind"] == "吉"                     # 见煞不改吉凶，不判破格
    assert any("擎羊" in s for s in res["context"]["sha"])
    assert any("地劫" in s for s in res["context"]["sha"])


def test_body_palace_rules():
    v = make_view({"丑": ["武曲", "贪狼"], "寅": ["天机"]}, "寅", body_branch="丑")
    hit = next(p for p in P.detect(v)["patterns"] if p["name"] == "贪武同行")
    assert hit["level"] == "身"


def test_detect_on_real_engine_chart_is_serializable():
    res = P.detect(compute_astrolabe(sample_birth()))
    assert res["version"] == P.VERSION
    json.dumps(res, ensure_ascii=False)
