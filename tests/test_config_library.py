"""模型库接口、目录接口，以及「保存配置不会停跳板」这条回归。"""
import json

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.config import ApiConfig
from app.services import config_store, proxy_service


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config_store, "CONFIG_FILE", tmp_path / "config.json")
    # 跳板一律当作「已启用但没监听」，并确保测试里绝不会去起隧道
    monkeypatch.setattr(proxy_service, "port_open", lambda *a, **k: False)
    monkeypatch.setattr(proxy_service, "start", lambda *a, **k: pytest.fail("不该启动隧道"))
    cfg = ApiConfig(provider="deepseek", default_model="deepseek-v4-pro",
                    deepseek_api_key="sk-test", anthropic_api_key="sk-ant",
                    proxy_enabled=True, proxy_autostart=False)
    config_store.save(cfg)
    with TestClient(app) as c:
        yield c


def test_library_round_trip(client):
    body = {"models": [{"provider": "anthropic", "model": "claude-opus-5"},
                       {"provider": "deepseek", "model": "deepseek-v4-pro"},
                       {"provider": "openai", "model": "手工-id"}],
            "default": {"provider": "anthropic", "model": "claude-opus-5"}}
    r = client.put("/api/config/library", json=body)
    assert r.status_code == 200 and r.json()["success"]
    got = client.get("/api/config/library").json()
    assert [(m["provider"], m["model"]) for m in got["models"]] == \
        [("anthropic", "claude-opus-5"), ("deepseek", "deepseek-v4-pro"), ("openai", "手工-id")]
    assert got["default"] == {"provider": "anthropic", "model": "claude-opus-5"}
    # 能力推断已写进库里
    assert got["models"][0]["thinking"] == "optional"


def test_library_rejects_bad_provider(client):
    r = client.put("/api/config/library", json={"models": [{"provider": "gemini", "model": "x"}]})
    assert r.status_code == 400 and "未知的提供商" in r.json()["detail"]


def test_default_moves_when_it_leaves_the_library(client):
    r = client.put("/api/config/library", json={"models": [{"provider": "anthropic", "model": "claude-opus-5"}]})
    assert r.json()["default"] == {"provider": "anthropic", "model": "claude-opus-5"}
    assert "默认模型已改为" in r.json()["message"]


def test_main_save_keeps_library_and_never_touches_proxy(client):
    client.put("/api/config/library", json={"models": [{"provider": "deepseek", "model": "deepseek-flash"}]})
    cfg = client.get("/api/config").json()
    cfg["proxy_enabled"] = False                 # 老前端会这么提交，必须被忽略
    cfg.pop("enabled_models", None)              # 也不带模型库
    r = client.put("/api/config", json=cfg)
    assert r.status_code == 200
    saved = config_store.load()
    assert saved.proxy_enabled is True, "保存配置不能把跳板关掉"
    assert [m.model for m in saved.enabled_models] == ["deepseek-flash"]


def test_proxy_endpoint_is_the_only_way_to_change_it(client):
    r = client.put("/api/config/proxy", json={"proxy_enabled": False})
    assert r.status_code == 200 and config_store.load().proxy_enabled is False
    bad = client.put("/api/config/proxy", json={"default_model": "x"})
    assert bad.status_code == 400 and "不是跳板设置项" in bad.json()["detail"]


def test_catalog_flags_proxy_and_keys(client):
    client.put("/api/config/library", json={"models": [
        {"provider": "anthropic", "model": "claude-opus-5"},
        {"provider": "openai", "model": "gpt-5.5"},
        {"provider": "deepseek", "model": "deepseek-flash"}]})
    cat = client.get("/api/config/catalog").json()
    by_id = {m["model"]: m for m in cat["models"]}
    assert by_id["claude-opus-5"]["needs_proxy"] and not by_id["claude-opus-5"]["proxy_ok"]
    assert "隧道未监听" in by_id["claude-opus-5"]["warning"]
    assert by_id["gpt-5.5"]["needs_key"] and "API Key" in by_id["gpt-5.5"]["warning"]
    assert by_id["deepseek-flash"]["proxy_ok"] and by_id["deepseek-flash"]["warning"] == ""
    assert [lv["value"] for lv in cat["thinking_levels"]] == ["off", "low", "medium", "high"]
    assert cat["proxy"]["listening"] is False
