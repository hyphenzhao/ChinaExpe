"""模型库：每个模型会不会用工具、能不能调思考档位。

聊天页要据此决定是否给出「思考模式」下拉，发送路径要据此决定是否下发 tools。
判断按提供商 + 模型 id 子串，所以 `gpt-5.5-2026-04-23` 这种带日期的快照能继承
`gpt-5` 的规则。未知 id 一律保守处理：可以用工具，不发思考参数，免得被接口拒绝。

纯函数，不读文件不联网，便于测试。
"""
from __future__ import annotations

import re

from ..models.config import THINKING_LEVELS, ApiConfig, ModelRef

_OPTIONAL_LEVELS = ["off", "low", "medium", "high"]
_O_SERIES = re.compile(r"^o\d")


def infer_caps(provider: str, model: str) -> ModelRef:
    """按模型 id 猜能力，返回一条可直接进模型库的 ModelRef。"""
    p = (provider or "").strip().lower()
    mid = (model or "").strip()
    low = mid.lower()
    ref = ModelRef(provider=p or "ollama", model=mid, label=mid)

    if p == "deepseek":
        if "reasoner" in low:
            ref.supports_tools = False          # deepseek-reasoner 不支持函数调用
            ref.thinking = "always"
        elif "v4-pro" in low or "reason" in low:
            ref.thinking = "always"             # 思考由模型自己决定，没有档位开关
    elif p == "anthropic":
        if "haiku" in low:
            ref.thinking = "none"
        else:
            ref.thinking = "optional"
    elif p == "openai":
        if low.startswith("gpt-5") or _O_SERIES.match(low):
            ref.thinking = "optional"
    elif p == "ollama":
        if any(t in low for t in ("r1", "qwq", "thinking")):
            ref.thinking = "always"

    if ref.thinking == "optional":
        ref.thinking_levels = list(_OPTIONAL_LEVELS)
        ref.default_thinking = "medium"
    else:
        ref.thinking_levels = []
        ref.default_thinking = "off"
    return ref


def normalize(models: list[ModelRef]) -> list[ModelRef]:
    """去重、补空缺字段，顺序保持用户勾选的顺序。

    界面存进来的条目通常只有 provider + model，这里按 id 推断能力补齐；
    已经写明思考档位的条目（用户自己调过）保持原样，不被覆盖。
    """
    out: list[ModelRef] = []
    seen: set[tuple[str, str]] = set()
    for m in models or []:
        key = ((m.provider or "").strip().lower(), (m.model or "").strip())
        if not key[1] or key in seen:
            continue
        seen.add(key)
        ref = m.model_copy(deep=True)
        ref.provider, ref.model = key
        guess = infer_caps(*key)
        if not ref.label:
            ref.label = ref.model
        if ref.thinking == "none" and not ref.thinking_levels:
            ref.thinking = guess.thinking          # 没写过就按 id 推断
            ref.thinking_levels = guess.thinking_levels
            ref.default_thinking = guess.default_thinking
        if ref.supports_tools and not guess.supports_tools:
            ref.supports_tools = False             # 例如 deepseek-reasoner，安全侧收紧
        if ref.thinking == "optional":
            if not ref.thinking_levels:
                ref.thinking_levels = list(_OPTIONAL_LEVELS)
            if ref.default_thinking not in ref.thinking_levels:
                ref.default_thinking = "medium"
        else:
            ref.thinking_levels = []
            ref.default_thinking = "off"
        out.append(ref)
    return out


def migrate(cfg: ApiConfig) -> ApiConfig:
    """让老配置直接可用：库为空时用现有默认模型补一条。纯内存，幂等。"""
    cfg.enabled_models = normalize(cfg.enabled_models)
    if cfg.default_model:
        key = ((cfg.provider or "").strip().lower(), cfg.default_model.strip())
        if not any((m.provider, m.model) == key for m in cfg.enabled_models):
            cfg.enabled_models.append(infer_caps(*key))
    return cfg


def resolve(cfg: ApiConfig, provider: str, model: str) -> ModelRef:
    """会话里记的模型 → 模型库条目；查不到就现场推断，绝不抛错。"""
    p, mid = (provider or "").strip().lower(), (model or "").strip()
    for m in cfg.enabled_models:
        if (m.provider, m.model) == (p, mid):
            return m
    for m in cfg.enabled_models:          # 只对上模型名（提供商被改过）
        if m.model == mid and mid:
            return m
    return infer_caps(p, mid)


def effective_thinking(ref: ModelRef, requested: str | None) -> str:
    """把请求的档位收敛到这个模型真正接受的值，返回 '' 表示不下发参数。"""
    if ref.thinking != "optional":
        return ""                          # none：不支持；always：模型自己思考，不带参数
    lv = (requested or "").strip().lower()
    if lv not in THINKING_LEVELS or lv not in ref.thinking_levels:
        lv = ref.default_thinking
    return "" if lv == "off" else lv


def is_ready(cfg: ApiConfig, provider: str) -> bool:
    """该提供商的凭据是否齐备。"""
    p = (provider or "").strip().lower()
    if p == "ollama":
        return bool(cfg.ollama_host)
    return bool(getattr(cfg, f"{p}_api_key", ""))
