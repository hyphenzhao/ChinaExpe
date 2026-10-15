"""Persist sanitized /models capabilities, isolated by provider, endpoint and key.

Reading this cache never starts a tunnel or sends a generation request. Refresh
uses the settings page's model-list request; failed refreshes retain last success.
"""
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone

from . import thinking_profiles as profiles


def scope(provider, base, api_key):
    return hashlib.sha256(f"{provider}|{base.rstrip('/')}|{api_key}".encode()).hexdigest()


def _path():
    from .config_store import CONFIG_FILE
    return CONFIG_FILE.with_name("model_capabilities.json")


def _read():
    try:
        data = json.loads(_path().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def remember(provider, base, api_key, rows):
    cache = _read()
    entries = {}
    for row in rows:
        parsed = profiles.remote(provider, row)
        if parsed and row.get("id"):
            parsed["thinking_checked_at"] = datetime.now(timezone.utc).isoformat()
            entries[row["id"]] = parsed
    cache[scope(provider, base, api_key)] = entries
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".capabilities-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def for_config(cfg):
    cache = _read()
    result = {}
    for p in ("openai", "anthropic", "deepseek"):
        value = cache.get(scope(p, getattr(cfg, f"{p}_base_url", ""), getattr(cfg, f"{p}_api_key", "")), {})
        result[p] = value if isinstance(value, dict) else {}
    return result


def apply(ref, entries):
    item = entries.get(ref.provider, {}).get(ref.model)
    if not isinstance(item, dict):
        return ref
    clean = {f: item[f] for f in profiles.FIELDS if f in item}
    # Revalidate cached data; malformed metadata must not break config/key loading.
    from ..models.config import ModelRef, THINKING_LEVELS
    try:
        result = ModelRef(**{**ref.model_dump(), **clean})
        result.thinking_levels = [lv for lv in THINKING_LEVELS if lv in result.thinking_levels]
        if result.thinking == "optional" and not result.thinking_levels:
            return ref
        if result.thinking_levels and result.default_thinking not in result.thinking_levels:
            result.default_thinking = result.thinking_levels[0]
        return result
    except (ValueError, TypeError):
        return ref
