"""The AI-readable export bundle, built for a fictional person in a temp dir."""
import json

import pytest
from conftest import SAMPLE
from app.models.person import BirthData, Person
from app.services import person_service as ps_mod
from app.services import export_service as ex_mod


@pytest.fixture()
def sample_person(tmp_path, monkeypatch):
    monkeypatch.setattr(ps_mod, "PEOPLE_DIR", tmp_path / "people")
    monkeypatch.setattr(ex_mod, "EXPORT_DIR", tmp_path / "exports")
    ps_mod.person_service._astro_cache.clear()
    ps_mod.person_service._bazi_cache.clear()
    p = Person(id="sample", display_name="示例", gender=SAMPLE["gender"],
               birth=BirthData(solar=SAMPLE["solar"], longitude=SAMPLE["longitude"]))
    ps_mod.person_service.save(p)
    return p


def test_bundle_has_both_charts(sample_person):
    b = ex_mod.build_bundle("sample")
    assert len(b["ziwei"]["palaces"]) == 12
    assert len(b["bazi"]["pillars"]) == 4
    assert b["ziwei"]["fly"] and b["ziwei"]["decadals"]
    assert set(b["text"]) == {"ziwei", "ziwei_horoscope", "bazi", "bazi_timeline"}
    assert all(b["text"].values()), "文字版不能为空"
    assert b["person"]["birth"]["solar"] == SAMPLE["solar"]


def test_write_person_and_index(sample_person):
    row = ex_mod.write_person("sample")
    data = json.loads((ex_mod.EXPORT_DIR / "sample.json").read_text(encoding="utf-8"))
    assert data["schema_version"] == ex_mod.SCHEMA_VERSION
    assert (ex_mod.EXPORT_DIR / "sample.md").read_text(encoding="utf-8").startswith("# 示例")
    assert row["bytes"] > 1000
    ex_mod.write_index()
    idx = json.loads((ex_mod.EXPORT_DIR / "index.json").read_text(encoding="utf-8"))
    assert [r["id"] for r in idx["people"]] == ["sample"]


def test_save_triggers_export(sample_person):
    """A person edit must refresh the bundle without an explicit call."""
    target = ex_mod.EXPORT_DIR / "sample.json"
    if target.exists():
        target.unlink()
    ps_mod.person_service.add_note("sample", "测试备注")
    assert target.exists()
    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["person"]["notes"][-1]["text"] == "测试备注"
