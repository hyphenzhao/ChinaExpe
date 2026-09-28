"""聊天会话的模型选择：能力决定工具、选择写回会话、跳板只提示不自动启。"""
import json

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.config import ApiConfig, ModelRef
from app.services import config_store, proxy_service
from app.api import chat_api


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config_store, "CONFIG_FILE", tmp_path / "config.json")
    monkeypatch.setattr(chat_api, "SESSIONS_DIR", tmp_path / "sessions")
    monkeypatch.setattr(proxy_service, "port_open", lambda *a, **k: False)
    monkeypatch.setattr(proxy_service, "start", lambda *a, **k: pytest.fail("不该启动隧道"))
    config_store.save(ApiConfig(
        provider="deepseek", default_model="deepseek-flash",
        deepseek_api_key="sk-d", anthropic_api_key="sk-a", proxy_enabled=True, proxy_autostart=False,
        enabled_models=[ModelRef(provider="deepseek", model="deepseek-flash"),
                        ModelRef(provider="deepseek", model="deepseek-reasoner"),
                        ModelRef(provider="anthropic", model="claude-opus-5",
                                 thinking="optional", thinking_levels=["off", "low", "medium", "high"],
                                 default_thinking="medium")]))
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def recorder(monkeypatch):
    """替换掉真正的流式调用，记录参数并吐一句回复。"""
    calls = []

    async def fake_stream(**kwargs):
        calls.append(kwargs)
        yield {"type": "token", "content": "好的"}

    monkeypatch.setattr(chat_api.llm_service, "stream_chat", fake_stream)
    return calls


def _send(client, sid, **extra):
    return client.post(f"/api/chats/{sid}/messages", json={"content": "在吗", **extra})


def test_create_session_without_provider_uses_config(client):
    s = client.post("/api/chats", json={"title": "t"}).json()
    assert (s["provider"], s["model"]) == ("deepseek", "deepseek-flash")


def test_pick_sticks_to_session_and_drives_the_call(client, recorder):
    sid = client.post("/api/chats", json={"title": "t"}).json()["id"]
    r = _send(client, sid, provider="anthropic", model="claude-opus-5", thinking="high")
    assert r.status_code == 200
    kw = recorder[0]
    assert (kw["provider"], kw["model"]) == ("anthropic", "claude-opus-5")
    assert kw["options"].thinking == "high"
    assert kw["tools"], "该模型支持工具"
    saved = client.get(f"/api/chats/{sid}").json()
    assert (saved["provider"], saved["model"], saved["thinking"]) == ("anthropic", "claude-opus-5", "high")


def test_tools_disabled_for_reasoner(client, recorder):
    sid = client.post("/api/chats", json={"title": "t"}).json()["id"]
    _send(client, sid, provider="deepseek", model="deepseek-reasoner")
    assert recorder[0]["tools"] is None


def test_thinking_clamped_for_model_without_it(client, recorder):
    sid = client.post("/api/chats", json={"title": "t"}).json()["id"]
    _send(client, sid, provider="deepseek", model="deepseek-flash", thinking="high")
    assert recorder[0]["options"].thinking == ""     # flash 不支持档位


def test_proxy_warning_event_but_no_autostart(client, recorder):
    sid = client.post("/api/chats", json={"title": "t"}).json()["id"]
    r = _send(client, sid, provider="anthropic", model="claude-opus-5")
    assert "event: warning" in r.text and "隧道未监听" in r.text
    assert "event: token" in r.text


def test_no_warning_for_domestic_provider(client, recorder):
    sid = client.post("/api/chats", json={"title": "t"}).json()["id"]
    r = _send(client, sid, provider="deepseek", model="deepseek-flash")
    assert "event: warning" not in r.text


def test_update_session_validates(client):
    sid = client.post("/api/chats", json={"title": "t"}).json()["id"]
    assert client.put(f"/api/chats/{sid}", json={"thinking": "nope"}).status_code == 400
    assert client.put(f"/api/chats/{sid}", json={"provider": "gemini"}).status_code == 400
    ok = client.put(f"/api/chats/{sid}", json={"provider": "anthropic", "model": "claude-opus-5", "thinking": "low"})
    assert ok.status_code == 200 and ok.json()["thinking"] == "low"


def test_legacy_session_without_thinking_still_works(client, recorder, tmp_path):
    legacy = {"id": "old1", "title": "旧会话", "mode": "theory", "person": None,
              "model": "claude-sonnet-5", "provider": "anthropic", "messages": [],
              "created_at": "2026-01-01T00:00:00", "updated_at": "2026-01-01T00:00:00"}
    d = tmp_path / "sessions"
    d.mkdir(parents=True, exist_ok=True)
    (d / "old1.json").write_text(json.dumps(legacy, ensure_ascii=False), encoding="utf-8")
    r = _send(client, "old1")
    assert r.status_code == 200
    assert recorder[0]["model"] == "claude-sonnet-5"           # 不在库里也照用
    assert recorder[0]["options"].thinking == "medium"         # 推断出可调思考，取默认档


def test_no_model_configured_is_a_clear_error(client, recorder, monkeypatch):
    config_store.save(ApiConfig(provider="deepseek", default_model="", enabled_models=[]))
    sid = client.post("/api/chats", json={"title": "t"}).json()["id"]
    r = _send(client, sid)
    assert r.status_code == 400 and "模型库" in r.json()["detail"]
