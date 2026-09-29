"""预置分析动作：代码结果注入到发给模型的消息里，会话只存短问题；新工具可调用。不联网。"""
import json

import pytest
from fastapi.testclient import TestClient

from conftest import SAMPLE
from app.main import app
from app.api import chat_api
from app.models.config import ApiConfig, ModelRef
from app.models.person import BirthData, Person
from app.services import config_store, export_service as ex_mod, person_service as ps_mod
from app.services.tools import execute_tool


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(ps_mod, "PEOPLE_DIR", tmp_path / "people")
    monkeypatch.setattr(ex_mod, "EXPORT_DIR", tmp_path / "exports")
    monkeypatch.setattr(config_store, "CONFIG_FILE", tmp_path / "config.json")
    monkeypatch.setattr(chat_api, "SESSIONS_DIR", tmp_path / "sessions")
    for cache in (ps_mod.person_service._astro_cache, ps_mod.person_service._bazi_cache,
                  ps_mod.person_service._events_cache):
        cache.clear()
    config_store.save(ApiConfig(provider="deepseek", default_model="deepseek-flash", deepseek_api_key="sk-x",
                                enabled_models=[ModelRef(provider="deepseek", model="deepseek-flash")]))
    ps_mod.person_service.save(Person(id="demo", display_name="示例", gender=SAMPLE["gender"],
                                      birth=BirthData(solar=SAMPLE["solar"], longitude=SAMPLE["longitude"])))
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def recorder(monkeypatch):
    calls = []

    async def fake_stream(**kwargs):
        calls.append(kwargs)
        yield {"type": "token", "content": "好"}

    monkeypatch.setattr(chat_api.llm_service, "stream_chat", fake_stream)
    return calls


def _send(client, **body):
    sid = client.post("/api/chats", json={"title": "t", "person": "demo", "mode": "chart"}).json()["id"]
    r = client.post(f"/api/chats/{sid}/messages", json={"person": "demo", **body})
    return sid, r


@pytest.mark.parametrize("action,marker", [
    ({"type": "ziwei_geju"}, "格局（代码判定成格方向"),
    ({"type": "bazi_geju"}, "命局分析（代码计算"),
    ({"type": "life_event", "event": "结婚"}, "## 结婚"),
    ({"type": "life_events"}, "## 高中"),
    ({"type": "rectify"}, "反推时辰评分"),
])
def test_action_injects_code_results(client, recorder, action, marker):
    sid, r = _send(client, content="分析", action=action)
    assert r.status_code == 200
    last_user = [m for m in recorder[0]["messages"] if m["role"] == "user"][-1]["content"]
    assert "程序计算结果" in last_user and marker in last_user and "（任务）" in last_user
    stored = client.get(f"/api/chats/{sid}").json()["messages"][0]
    assert stored["content"] == "分析"                          # 会话只存短问题
    assert stored["context"]["action"]["type"] == action["type"]


def test_plain_message_has_no_injection(client, recorder):
    _send(client, content="你好")
    last_user = [m for m in recorder[0]["messages"] if m["role"] == "user"][-1]["content"]
    assert "程序计算结果" not in last_user


def test_analysis_endpoint(client):
    a = client.get("/api/people/demo/analysis").json()
    assert set(a) == {"patterns", "bazi", "life_events"}
    assert set(a["life_events"]["events"]) == {"结婚", "发财", "高升", "搬迁", "添丁", "高中"}
    ev = client.get("/api/people/demo/events?event=结婚").json()
    assert list(ev["events"]) == ["结婚"]
    assert client.get("/api/people/demo/events?event=中奖").status_code == 400


@pytest.mark.parametrize("tool,args,needle", [
    ("get_ziwei_patterns", {}, "格局"),
    ("get_bazi_analysis", {}, "身强弱"),
    ("get_life_events", {"event": "发财"}, "发财"),
    ("get_chart_variant", {"slots": 1}, "候选盘"),
])
def test_new_tools(client, tool, args, needle):
    import asyncio
    res = asyncio.run(execute_tool(tool, {"person": "demo", **args}))
    assert not res.get("error"), res
    assert needle in res["content"]
