"""Single place that reads/writes data/config.json.

Both the config API and the LLM service need it: the API to edit providers and
keys, the LLM service to know whether a request should go through the 跳板.
"""
from __future__ import annotations

import json
from pathlib import Path

from ..models.config import ApiConfig

CONFIG_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "config.json"


def load() -> ApiConfig:
    if CONFIG_FILE.exists():
        try:
            return ApiConfig(**json.loads(CONFIG_FILE.read_text(encoding="utf-8")))
        except Exception:
            pass
    return ApiConfig()


def save(config: ApiConfig) -> None:
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(config.model_dump_json(indent=2), encoding="utf-8")


def proxy_for(provider: str) -> str | None:
    """The proxy URL to use for this provider, or None for a direct connection."""
    c = load()
    if not c.proxy_enabled or not c.proxy_url:
        return None
    if provider and c.proxy_providers and provider not in c.proxy_providers:
        return None
    return c.proxy_url
