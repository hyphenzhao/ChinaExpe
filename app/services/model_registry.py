"""模型库：每个模型会不会用工具、能不能调思考档位。

聊天页按模型的原生档位显示滑块，发送路径据此决定工具与思考参数。
默认能力来自 thinking_profiles 中已核对的官方文档，config_store 再叠加远程能力缓存。
未知 id 不发思考参数，也不伪造档位。

纯函数，不读文件不联网，便于测试。
"""
from __future__ import annotations

from ..models.config import THINKING_LEVELS, ApiConfig, ModelRef
from . import thinking_profiles as profiles

_OPTIONAL_LEVELS = ["off", "low", "medium", "high"]


def infer_caps(provider: str, model: str) -> ModelRef:
    """按模型 id 猜能力，返回一条可直接进模型库的 ModelRef。"""
    p = (provider or "").strip().lower()
    mid = (model or "").strip()
    low = mid.lower()
    ref = ModelRef(provider=p or "ollama", model=mid, label=mid)

    if p == "deepseek" and "reasoner" in low:
        ref.supports_tools = False
    return ref.model_copy(update=profiles.documented(p, mid))


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
        # Refresh generated/legacy capabilities when documented profiles expand.
        # Deliberate custom subsets remain usable, but remote data is applied later.
        legacy = not ref.thinking_source and ref.thinking_levels in ([], _OPTIONAL_LEVELS, ["low", "medium", "high"])
        if legacy or ref.thinking_source in ("docs", "unknown", "remote"):
            preferred = ref.default_thinking
            ref = ref.model_copy(update={f: getattr(guess, f) for f in profiles.FIELDS})
            if preferred in ref.thinking_levels and (m.thinking_levels or m.thinking_source):
                ref.default_thinking = preferred
        else:
            ref.thinking_source = "manual"
            ref.thinking_protocol = ref.thinking_protocol or guess.thinking_protocol
            # Translate the old OpenAI 'off' label to the actual API value.
            if ref.provider == "openai" and "off" in ref.thinking_levels and "none" in guess.thinking_levels:
                ref.thinking_levels = ["none" if lv == "off" else lv for lv in ref.thinking_levels]
                if ref.default_thinking == "off":
                    ref.default_thinking = "none"
        if ref.supports_tools and not guess.supports_tools:
            ref.supports_tools = False             # 例如 deepseek-reasoner，安全侧收紧
        if ref.thinking == "optional":
            ref.thinking_levels = [lv for lv in THINKING_LEVELS if lv in ref.thinking_levels]
            if guess.thinking_source == "docs":
                ref.thinking_levels = [lv for lv in ref.thinking_levels if lv in guess.thinking_levels]
            if ref.default_thinking not in ref.thinking_levels:
                ref.default_thinking = guess.default_thinking if guess.default_thinking in ref.thinking_levels else next(iter(ref.thinking_levels), "off")
            if not ref.thinking_levels:
                ref.thinking = "none"
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
    if lv == "off" and "none" in ref.thinking_levels:
        lv = "none"
    if lv not in THINKING_LEVELS or lv not in ref.thinking_levels:
        lv = ref.default_thinking
    return lv  # Explicit 'none'/'off' must reach the provider, not become its default.


def is_ready(cfg: ApiConfig, provider: str) -> bool:
    """该提供商的凭据是否齐备。"""
    p = (provider or "").strip().lower()
    if p == "ollama":
        return bool(cfg.ollama_host)
    return bool(getattr(cfg, f"{p}_api_key", ""))
