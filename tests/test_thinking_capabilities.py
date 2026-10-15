"""Native model levels, provider discovery and request mapping. No paid API calls."""
import asyncio
import json

import httpx
import pytest

from app.models.config import ApiConfig, ModelRef, ChatOptions
from app.services import config_store, model_capabilities as cache, thinking_profiles as profiles
from app.services import model_registry as registry, llm_service as ls
from app.api import config_api


def run(awaitable):
    return asyncio.run(awaitable)


def collect(generator):
    async def get():
        return [e async for e in generator]
    return run(get())


def support(value=True):
    return {"supported": value}


def remote_row(model="claude-future"):
    return {"id": model, "capabilities": {
        "thinking": {"supported": True, "types": {"adaptive": support(), "enabled": support(False), "disabled": support(False)}},
        "effort": {"supported": True, "low": support(), "medium": support(), "high": support(),
                   "xhigh": support(False), "max": support()}}}


@pytest.fixture()
def config(tmp_path, monkeypatch):
    monkeypatch.setattr(config_store, "CONFIG_FILE", tmp_path / "config.json")
    config_api._models_cache.clear()
    cfg = ApiConfig(provider="anthropic", default_model="claude-future", anthropic_api_key="fake-test-only",
                    anthropic_base_url="https://unit.test", proxy_enabled=False,
                    enabled_models=[ModelRef(provider="anthropic", model="claude-future")])
    config_store.save(cfg)
    return cfg


def transport(monkeypatch, handler):
    seen = []
    def fake(provider, timeout=120):
        def send(request):
            seen.append(request)
            return handler(request)
        return httpx.AsyncClient(transport=httpx.MockTransport(send))
    monkeypatch.setattr(ls, "_client", fake)
    return seen


def test_remote_metadata_survives_reload_and_reaches_catalog(config, monkeypatch):
    seen = transport(monkeypatch, lambda _: httpx.Response(200, json={"data": [remote_row()], "has_more": False}))
    rows = run(config_api.list_models("anthropic", 1))
    assert rows[0]["thinking_levels"] == ["low", "medium", "high", "max"]
    assert rows[0]["thinking_source"] == "remote"
    ref = config_store.load().enabled_models[0]
    assert ref.thinking_protocol == "anthropic_adaptive"
    assert registry.effective_thinking(ref, "max") == "max"
    cat = run(config_api.catalog())
    assert cat.models[0].thinking_levels == rows[0]["thinking_levels"]
    assert all(r.method == "GET" and r.url.path == "/v1/models" for r in seen)
    assert "fake-test-only" not in cache._path().read_text()


def test_remote_override_can_remove_documented_thinking(config, monkeypatch):
    config.enabled_models = [ModelRef(provider="anthropic", model="claude-opus-5")]
    config.default_model = "claude-opus-5"
    config_store.save(config)
    row = {"id": "claude-opus-5", "capabilities": {"thinking": support(False)}}
    transport(monkeypatch, lambda _: httpx.Response(200, json={"data": [row]}))
    run(config_api.list_models("anthropic", 1))
    ref = config_store.load().enabled_models[0]
    assert ref.thinking == "none" and ref.thinking_levels == [] and ref.thinking_source == "remote"
    assert registry.effective_thinking(ref, "max") == ""


def test_endpoint_and_key_isolation(config):
    cache.remember("anthropic", config.anthropic_base_url, config.anthropic_api_key, [remote_row()])
    assert cache.for_config(config)["anthropic"]
    config.anthropic_base_url = "https://another.test"
    assert not cache.for_config(config)["anthropic"]
    config.anthropic_base_url = "https://unit.test"
    config.anthropic_api_key = "different"
    assert not cache.for_config(config)["anthropic"]


def test_failed_refresh_retains_last_success(config, monkeypatch):
    cache.remember("anthropic", config.anthropic_base_url, config.anthropic_api_key, [remote_row()])
    transport(monkeypatch, lambda _: httpx.Response(503))
    run(config_api.list_models("anthropic", 1))
    assert config_store.load().enabled_models[0].thinking_source == "remote"


def test_anthropic_discovery_follows_pagination(config, monkeypatch):
    def handler(req):
        if req.url.params.get("after_id"):
            return httpx.Response(200, json={"data": [remote_row()], "has_more": False})
        return httpx.Response(200, json={"data": [{"id": "other"}], "has_more": True, "last_id": "other"})
    seen = transport(monkeypatch, handler)
    ok, _, names = run(ls.llm_service._list_models_http("anthropic", config.anthropic_api_key, config.anthropic_base_url))
    assert ok and names == ["other", "claude-future"] and len(seen) == 2
    assert seen[1].url.params["after_id"] == "other"


def test_absent_metadata_does_not_invent_remote_levels(config, monkeypatch):
    transport(monkeypatch, lambda _: httpx.Response(200, json={"data": [{"id": "gpt-6.1-sol"}]}))
    config.openai_api_key = "fake"
    config_store.save(config)
    rows = run(config_api.list_models("openai", 1))
    assert rows[0]["thinking_source"] == "docs"
    assert rows[0]["thinking_levels"] == profiles.DEPTHS
    assert registry.infer_caps("openai", "unknown-model").thinking_levels == []


def test_malformed_metadata_does_not_break_listing_or_key_loading(config, monkeypatch):
    row = remote_row()
    row["capabilities"]["thinking"]["types"] = ["adaptive"]
    transport(monkeypatch, lambda _: httpx.Response(200, json={"data": [row]}))
    rows = run(config_api.list_models("anthropic", 1))
    assert rows[0]["name"] == "claude-future"
    assert rows[0]["thinking_levels"] == []
    assert config_store.load().anthropic_api_key == "fake-test-only"

    # The optional cache must never cause valid credentials to disappear.
    cache._path().write_text(json.dumps({cache.scope("anthropic", config.anthropic_base_url,
        config.anthropic_api_key): {"claude-future": {"thinking_levels": None}}}))
    assert config_store.load().anthropic_api_key == "fake-test-only"


def test_remote_switch_without_effort_has_only_off_on():
    row = {"id": "claude-switch", "capabilities": {
        "thinking": {"supported": True, "types": {"enabled": support(), "disabled": support()}},
        "effort": []}}
    parsed = profiles.remote("anthropic", row)
    assert parsed["thinking_levels"] == ["off", "on"]
    assert parsed["thinking_protocol"] == "anthropic_budget"


@pytest.mark.parametrize("provider,model,levels", [
    ("openai", "gpt-6.1-sol", ["low", "medium", "high", "xhigh", "max"]),
    ("openai", "gpt-6-sol", ["none", "low", "medium", "high", "xhigh", "max"]),
    ("openai", "gpt-5-mini", ["minimal", "low", "medium", "high"]),
    ("openai", "gpt-4o", []),
    ("deepseek", "deepseek-flash", ["off", "low", "high", "max"]),
    ("anthropic", "claude-opus-5-5", ["low", "medium", "high", "xhigh", "max"]),
    ("anthropic", "claude-haiku-4-5", ["off", "on"]),
])
def test_documented_native_levels(provider, model, levels):
    assert registry.infer_caps(provider, model).thinking_levels == levels


@pytest.mark.parametrize("provider,model,level,protocol,expected", [
    ("openai", "gpt-6.1-sol", "max", "openai_effort", {"reasoning": {"effort": "max"}}),
    ("openai", "gpt-6-sol", "none", "openai_effort", {"reasoning": {"effort": "none"}}),
    ("openai", "gpt-5.5", "xhigh", "openai_effort", {"reasoning_effort": "xhigh"}),
    ("deepseek", "deepseek-flash", "max", "deepseek_effort", {"reasoning_effort": "max", "thinking": {"type": "enabled"}}),
    ("deepseek", "deepseek-flash", "off", "deepseek_effort", {"thinking": {"type": "disabled"}}),
    ("anthropic", "claude-opus-5-5", "max", "anthropic_adaptive", {"thinking": {"type": "adaptive"}, "output_config": {"effort": "max"}}),
    ("anthropic", "claude-opus-5", "off", "anthropic_adaptive", {"thinking": {"type": "disabled"}, "output_config": {"effort": "low"}}),
    ("anthropic", "claude-haiku-4-5", "on", "anthropic_budget", {"thinking": {"type": "enabled", "budget_tokens": 8192}}),
])
def test_native_values_reach_provider(monkeypatch, provider, model, level, protocol, expected):
    def handler(req):
        if req.url.path.endswith("/responses"):
            data = 'data: {"type":"response.completed","response":{"status":"completed","output":[]}}\n\n'
        elif provider == "anthropic":
            data = 'data: {"type":"message_stop"}\n\n'
        else:
            data = 'data: [DONE]\n\n'
        return httpx.Response(200, content=data.encode())
    seen = transport(monkeypatch, handler)
    collect(ls.llm_service.stream_chat([{"role": "user", "content": "test"}], model, provider=provider,
        tools=[{"type": "function", "function": {"name": "test", "parameters": {"type": "object"}}}],
        options=ChatOptions(thinking=level, thinking_protocol=protocol)))
    body = json.loads(seen[0].content)
    for key, value in expected.items():
        assert body[key] == value
    assert len(seen) == 1
