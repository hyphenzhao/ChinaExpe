"""Configuration API routes."""
import json
from pathlib import Path
from fastapi import APIRouter, HTTPException

from ..models.config import (
    ApiConfig, ApiConfigResponse, ModelInfo,
    TestConnectionRequest, TestConnectionResponse,
)
from ..services.llm_service import llm_service

router = APIRouter(prefix="/api/config", tags=["config"])

CONFIG_FILE = Path("/Volumes/Storage/Workspace/ChinaExpe/data/config.json")

DEEPSEEK_MODELS = [
    {"name": "deepseek-chat", "size": "—", "provider": "deepseek"},
    {"name": "deepseek-reasoner", "size": "—", "provider": "deepseek"},
]


def _load_config() -> ApiConfig:
    """Load config from disk or return defaults."""
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            return ApiConfig(**data)
        except Exception:
            pass
    return ApiConfig()


def _save_config(config: ApiConfig):
    """Persist config to disk."""
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(
        config.model_dump_json(indent=2),
        encoding="utf-8",
    )


@router.get("")
async def get_config() -> ApiConfigResponse:
    """Get current API configuration (key masked)."""
    config = _load_config()
    return ApiConfigResponse.from_config(config)


@router.put("")
async def update_config(config: ApiConfig):
    """Update API configuration."""
    # The frontend may echo back the masked key (contains '***').
    # In that case, preserve the existing real key instead of overwriting it.
    if "***" in config.deepseek_api_key:
        existing = _load_config()
        config.deepseek_api_key = existing.deepseek_api_key
    _save_config(config)
    return {"success": True, "message": "配置已保存"}


@router.get("/models")
async def list_models(provider: str = "ollama") -> list[dict]:
    """List available models for the given provider."""
    config = _load_config()
    models = []

    if provider == "ollama" or not provider:
        models.extend(await llm_service.list_ollama_models(
            config.ollama_host, config.ollama_port
        ))

    if provider == "deepseek" or not provider:
        if config.deepseek_api_key:
            models.extend(DEEPSEEK_MODELS)
        else:
            # Still show them but mark as needing key
            for m in DEEPSEEK_MODELS:
                models.append({**m, "needs_key": True})

    return models


@router.post("/test")
async def test_connection(req: TestConnectionRequest) -> TestConnectionResponse:
    """Test connection to the specified provider."""
    if req.provider == "ollama":
        host = req.host or "http://127.0.0.1"
        port = req.port or 11434
        ok, msg, model_names = await llm_service.test_ollama_connection(host, port)
        return TestConnectionResponse(success=ok, message=msg, models=model_names)
    elif req.provider == "deepseek":
        api_key = req.api_key or ""
        base_url = req.base_url or "https://api.deepseek.com"
        ok, msg, model_names = await llm_service.test_deepseek_connection(api_key, base_url)
        return TestConnectionResponse(success=ok, message=msg, models=model_names)
    else:
        return TestConnectionResponse(success=False, message=f"未知的提供商: {req.provider}")
