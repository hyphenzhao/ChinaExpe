"""反推时辰：问卷、答案合并、候选数量、自洽性（用某候选自己的强年当经历，它应排第一）。虚构人物。"""
import pytest
from fastapi.testclient import TestClient

from conftest import SAMPLE
from app.main import app
from app.engine import timeshift as TS
from app.engine.ziwei.events import year_table
from app.models.person import BirthData, Person
from app.services import export_service as ex_mod, person_service as ps_mod
from app.services import rectify_service as RS


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(ps_mod, "PEOPLE_DIR", tmp_path / "people")
    monkeypatch.setattr(ex_mod, "EXPORT_DIR", tmp_path / "exports")
    for cache in (ps_mod.person_service._astro_cache, ps_mod.person_service._bazi_cache,
                  ps_mod.person_service._events_cache):
        cache.clear()
    ps_mod.person_service.save(Person(id="demo", display_name="示例", gender=SAMPLE["gender"],
                                      birth=BirthData(solar=SAMPLE["solar"], longitude=SAMPLE["longitude"])))
    with TestClient(app) as c:
        yield c


def test_questions_endpoint(client):
    qs = client.get("/api/people/meta/rectify-questions").json()
    ids = [q["id"] for q in qs]
    assert {"approx_known", "marriage_year", "first_child_sex", "parents_divorced", "leave_home_year"} <= set(ids)
    assert len(ids) == len(set(ids))


def test_facts_merge_and_delete(client):
    client.put("/api/people/demo/facts", json={"married": "是", "marriage_year": 2026})
    got = client.put("/api/people/demo/facts", json={"children": 1, "marriage_year": ""}).json()
    assert got == {"married": "是", "children": 1}
    assert client.get("/api/people/demo").json()["birth"]["solar"] == SAMPLE["solar"]    # 不动出生信息


def test_day_mode_candidates(client):
    r = client.post("/api/people/demo/rectify", json={}).json()
    assert 1 <= len(r["candidates"]) <= 14
    assert sum(c["flags"]["is_current"] for c in r["candidates"]) == 1
    assert all("offset_slots" in c for c in r["candidates"])
    assert r["confidence"] == "低"                      # 没有经历时不可能高置信


def test_approx_mode_has_five(client):
    r = client.post("/api/people/demo/rectify", json={"approx_time": "12:10"}).json()
    assert len(r["candidates"]) <= 5 and r["mode"].startswith("大致时段")
    assert {c["offset_slots"] for c in r["candidates"]} <= {-2, -1, 0, 1, 2}


def test_self_consistency(client):
    """用候选 X 自己最强的几年当作「经历」，X 应排第一。"""
    person = ps_mod.person_service.get("demo")
    target = TS.shift(ps_mod.person_service.birth_input(person), slots=3)
    astro, bazi = ps_mod.person_service.charts_for_birth(person, target)
    facts = {}
    for key, ev in (("marriage_year", "结婚"), ("leave_home_year", "搬迁"), ("promotion_years", "高升"),
                    ("exam_years", "高中")):
        best = max(year_table(astro, bazi, ev), key=lambda r: r["score"])
        facts[key] = best["year"]
    res = RS.score_candidates("demo", facts)
    assert res["candidates"][0]["offset_slots"] == 3
    assert res["candidates"][0]["score"] > 0


def test_rectify_text_has_table(client):
    client.put("/api/people/demo/facts", json={"married": "是", "marriage_year": 2024})
    txt = RS.rectify_text("demo")
    assert "| 排名 | 候选 |" in txt and "slots=" in txt
