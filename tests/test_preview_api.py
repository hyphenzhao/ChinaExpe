"""上下调预览接口：挪时辰、挪日期、原盘不被改动。虚构人物，临时目录。"""
import pytest
from fastapi.testclient import TestClient

from conftest import SAMPLE
from app.main import app
from app.models.person import BirthData, Person
from app.services import export_service as ex_mod
from app.services import person_service as ps_mod


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(ps_mod, "PEOPLE_DIR", tmp_path / "people")
    monkeypatch.setattr(ex_mod, "EXPORT_DIR", tmp_path / "exports")
    ps_mod.person_service._astro_cache.clear()
    ps_mod.person_service._bazi_cache.clear()
    ps_mod.person_service.save(Person(id="demo", display_name="示例", gender=SAMPLE["gender"],
                                      birth=BirthData(solar=SAMPLE["solar"], longitude=SAMPLE["longitude"])))
    with TestClient(app) as c:
        yield c


def test_preview_next_slot(client):
    r = client.get("/api/people/demo/preview?slots=1").json()
    assert r["label"]["slot"] == r["original"]["slot"] + 1
    assert r["ziwei"]["birth"]["hour_index"] == r["label"]["slot"]
    assert r["bazi"]["pillars"][3]["branch"] != client.get("/api/people/demo/bazi").json()["pillars"][3]["branch"]
    assert "patterns" in r["ziwei"] and "analysis" in r["bazi"]


def test_preview_next_day_keeps_minutes(client):
    r = client.get("/api/people/demo/preview?days=1").json()
    assert r["birth"]["solar"] == "2000-01-02 12:00"
    assert r["label"]["slot"] == r["original"]["slot"]


def test_preview_does_not_touch_saved_person(client):
    client.get("/api/people/demo/preview?slots=-3")
    assert client.get("/api/people/demo").json()["birth"]["solar"] == SAMPLE["solar"]
