"""Documented native controls and optional provider model metadata.

OpenAI /models has no effort metadata. These fallback profiles are maintained
from official docs; they are not advertised as remotely discovered capabilities.
Unknown models get no slider. Provider metadata, when present, wins.
"""
import re

from ..models.config import THINKING_LEVELS

FIELDS = ("thinking", "thinking_levels", "default_thinking", "thinking_protocol",
          "thinking_source", "thinking_source_url", "thinking_checked_at")
DEPTHS = ["low", "medium", "high", "xhigh", "max"]


def profile(levels=(), default="off", protocol="", source="docs", url="", thinking=None):
    return dict(thinking=thinking or ("optional" if levels else "none"), thinking_levels=list(levels),
                default_thinking=default, thinking_protocol=protocol, thinking_source=source,
                thinking_source_url=url, thinking_checked_at="")


def documented(provider, model):
    mid = re.sub(r"-\d{4}-?\d{2}-?\d{2}$", "", model.lower())
    if provider == "openai":
        url = "https://developers.openai.com/api/docs/models/" + mid
        if mid in ("gpt-6.1-sol", "gpt-6-astra"):
            return profile(DEPTHS, "medium", "openai_effort", url=url)
        if mid in ("gpt-6-sol", "gpt-6-luna") or re.fullmatch(r"gpt-5\.6(?:-(?:sol|terra|luna))?", mid):
            return profile(["none"] + DEPTHS, "medium", "openai_effort", url=url)
        if mid in ("gpt-5.2", "gpt-5.4", "gpt-5.4-mini", "gpt-5.4-nano", "gpt-5.5"):
            return profile(["none"] + DEPTHS[:-1], "medium" if mid == "gpt-5.5" else "none", "openai_effort", url=url)
        if mid == "gpt-5.1":
            return profile(["none", "low", "medium", "high"], "none", "openai_effort", url=url)
        if mid in ("gpt-5", "gpt-5-mini", "gpt-5-nano"):
            return profile(["minimal", "low", "medium", "high"], "medium", "openai_effort", url=url)
        if mid in ("o1", "o3", "o3-mini", "o4-mini"):
            return profile(DEPTHS[:3], "medium", "openai_effort", url=url)
        if mid in ("gpt-4o", "gpt-4o-mini", "gpt-4.1", "gpt-4.1-mini", "gpt-4.1-nano"):
            return profile(url=url)
    elif provider == "deepseek":
        url = "https://api-docs.deepseek.com/guides/thinking_mode/"
        if mid in ("deepseek-flash", "deepseek-pro") or mid.startswith(("deepseek-v4-", "deepseek-v4.1-")):
            return profile(["off", "low", "high", "max"], "high", "deepseek_effort", url=url)
        if "reasoner" in mid:
            return profile(thinking="always", url=url)
    elif provider == "anthropic":
        url = "https://platform.claude.com/docs/en/build-with-claude/effort"
        if mid in ("claude-opus-5-5", "claude-sonnet-5-5", "claude-fable-5", "claude-fable-5-1",
                   "claude-mythos-5", "claude-mythos-5-1", "claude-opus-4-7", "claude-opus-4-8"):
            return profile(DEPTHS, "medium" if mid == "claude-opus-5-5" else "high", "anthropic_adaptive", url=url)
        if mid in ("claude-opus-5", "claude-sonnet-5", "claude-haiku-5-5"):
            return profile(["off"] + DEPTHS, "medium" if "haiku" in mid else "high", "anthropic_adaptive", url=url)
        if mid in ("claude-opus-4-6", "claude-sonnet-4-6"):
            return profile(["off", "low", "medium", "high", "max"], "high", "anthropic_adaptive", url=url)
        if mid == "claude-opus-4-5":
            return profile(["off", "low", "medium", "high"], "high", "anthropic_effort_budget", url=url)
        if mid in ("claude-haiku-4-5", "claude-sonnet-4-5", "claude-sonnet-4", "claude-opus-4",
                   "claude-opus-4-1", "claude-3-7-sonnet"):
            return profile(["off", "on"], "off", "anthropic_budget", url="https://platform.claude.com/docs/en/build-with-claude/extended-thinking")
    elif provider == "ollama" and any(x in mid for x in ("r1", "qwq", "thinking")):
        return profile(source="unknown", thinking="always")
    return profile(source="unknown")


def remote(provider, row):
    """Parse only explicit metadata; a bare model ID is not proof of capability."""
    caps = row.get("capabilities") or {}
    if not isinstance(caps, dict):
        return None
    thinking = caps.get("thinking") or {}
    effort = caps.get("effort") or {}
    if provider == "anthropic" and isinstance(thinking, dict):
        if thinking.get("supported") is False:
            return profile(source="remote")
        if thinking.get("supported") is not True:
            return None
        types = thinking.get("types") or {}
        if not isinstance(types, dict):
            return None
        if not isinstance(effort, dict):
            effort = {}
        def supported(obj):
            return isinstance(obj, dict) and obj.get("supported") is True
        adaptive = supported(types.get("adaptive"))
        enabled = supported(types.get("enabled"))
        disabled = supported(types.get("disabled"))
        levels = [lv for lv in DEPTHS if supported(effort.get(lv))] if effort.get("supported") is True else []
        if adaptive and levels:
            protocol = "anthropic_adaptive"
        elif enabled and levels:
            protocol = "anthropic_effort_budget"
        elif enabled:
            levels, protocol = ["on"], "anthropic_budget"
        else:
            return profile(source="remote", thinking="always")
        if disabled:
            levels.insert(0, "off")
        fallback = documented(provider, row.get("id", ""))["default_thinking"]
        default = effort.get("default") or row.get("default_effort") or fallback
        if default not in levels:
            default = "high" if "high" in levels else levels[-1]
        return profile(levels, default, protocol, "remote")
    # Optional extension used by OpenAI-compatible gateways. Only enumerated
    # native effort values are accepted; arbitrary remote strings never become knobs.
    effort = caps.get("reasoning") or {}
    if provider == "openai" and isinstance(effort, dict):
        if effort.get("supported") is False:
            return profile(source="remote")
        values = effort.get("effort_levels")
        if isinstance(values, list):
            levels = [lv for lv in THINKING_LEVELS if lv in values and lv not in ("off", "on")]
            if levels:
                default = effort.get("default_effort", "medium")
                return profile(levels, default if default in levels else levels[0], "openai_effort", "remote")
    return None
