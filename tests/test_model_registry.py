"""模型库：能力推断、迁移、档位收敛。纯函数，不联网。"""
import pytest

from app.models.config import ApiConfig, ModelRef
from app.services import model_registry as mr


@pytest.mark.parametrize("provider,model,tools,thinking", [
    ("deepseek", "deepseek-reasoner", False, "always"),
    ("deepseek", "deepseek-v4-pro", True, "always"),
    ("deepseek", "deepseek-flash", True, "none"),
    ("anthropic", "claude-opus-5", True, "optional"),
    ("anthropic", "claude-haiku-4-5-20251001", True, "none"),
    ("openai", "gpt-5.5-2026-04-23", True, "optional"),
    ("openai", "gpt-4o", True, "none"),
    ("ollama", "qwen3:8b", True, "none"),
    ("ollama", "deepseek-r1:7b", True, "always"),
])
def test_infer_caps(provider, model, tools, thinking):
    ref = mr.infer_caps(provider, model)
    assert (ref.supports_tools, ref.thinking) == (tools, thinking)
    assert bool(ref.thinking_levels) is (thinking == "optional")


def test_unknown_model_is_conservative():
    ref = mr.infer_caps("openai", "some-new-model")
    assert ref.supports_tools and ref.thinking == "none" and ref.default_thinking == "off"


def test_normalize_dedupes_and_infers():
    rows = mr.normalize([
        ModelRef(provider="Anthropic", model=" claude-opus-5 "),          # 只有 id，按规则补能力
        ModelRef(provider="anthropic", model="claude-opus-5"),            # 重复，丢掉
        ModelRef(provider="deepseek", model=""),                          # 空 id，丢掉
        ModelRef(provider="deepseek", model="deepseek-reasoner"),
    ])
    assert [(r.provider, r.model) for r in rows] == [("anthropic", "claude-opus-5"), ("deepseek", "deepseek-reasoner")]
    assert rows[0].label == "claude-opus-5"
    assert rows[0].thinking == "optional" and rows[0].default_thinking == "medium"
    assert rows[1].supports_tools is False      # reasoner 不支持工具，按 id 收紧


def test_normalize_keeps_explicit_thinking_choice():
    row = mr.normalize([ModelRef(provider="anthropic", model="claude-opus-5", thinking="optional",
                                 thinking_levels=["off", "high"], default_thinking="off")])[0]
    assert row.thinking_levels == ["off", "high"] and row.default_thinking == "off"


def test_migrate_seeds_from_legacy_default_and_is_idempotent():
    cfg = ApiConfig(provider="openai", default_model="gpt-5.5")
    mr.migrate(cfg)
    assert [(m.provider, m.model) for m in cfg.enabled_models] == [("openai", "gpt-5.5")]
    before = [m.model_dump() for m in cfg.enabled_models]
    mr.migrate(cfg)
    assert [m.model_dump() for m in cfg.enabled_models] == before


def test_migrate_keeps_user_choices():
    cfg = ApiConfig(provider="anthropic", default_model="claude-opus-5",
                    enabled_models=[ModelRef(provider="anthropic", model="claude-opus-5",
                                             thinking="optional", thinking_levels=["off", "high"],
                                             default_thinking="off")])
    mr.migrate(cfg)
    assert len(cfg.enabled_models) == 1
    assert cfg.enabled_models[0].default_thinking == "off"   # 用户关掉思考，别被改回去


def test_resolve_falls_back_to_inference():
    cfg = ApiConfig(enabled_models=[ModelRef(provider="deepseek", model="deepseek-flash")])
    assert mr.resolve(cfg, "deepseek", "deepseek-flash").model == "deepseek-flash"
    ref = mr.resolve(cfg, "anthropic", "claude-sonnet-5")     # 老会话里的模型不在库里
    assert ref.provider == "anthropic" and ref.thinking == "optional"


@pytest.mark.parametrize("cap,levels,requested,expected", [
    ("optional", ["off", "low", "medium", "high"], "high", "high"),
    ("optional", ["off", "low", "medium", "high"], "", "medium"),
    ("optional", ["off", "low", "medium", "high"], "nonsense", "medium"),
    ("optional", ["off", "low", "medium", "high"], "off", ""),
    ("none", [], "high", ""),
    ("always", [], "high", ""),
])
def test_effective_thinking(cap, levels, requested, expected):
    ref = ModelRef(provider="anthropic", model="x", thinking=cap,
                   thinking_levels=levels, default_thinking="medium" if levels else "off")
    assert mr.effective_thinking(ref, requested) == expected


def test_is_ready():
    cfg = ApiConfig(anthropic_api_key="sk-x")
    assert mr.is_ready(cfg, "anthropic") and mr.is_ready(cfg, "ollama")
    assert not mr.is_ready(cfg, "openai")
