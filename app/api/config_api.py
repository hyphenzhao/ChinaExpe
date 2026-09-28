"""Configuration API routes."""
from fastapi import APIRouter

from ..models.config import (
    ApiConfig, ApiConfigResponse,
    TestConnectionRequest, TestConnectionResponse,
)
from ..services import config_store, proxy_service
from ..services.llm_service import llm_service

router = APIRouter(prefix="/api/config", tags=["config"])

CONFIG_FILE = config_store.CONFIG_FILE          # kept for backwards compatibility

DEEPSEEK_MODELS = [
    {"name": "deepseek-chat", "size": "—", "provider": "deepseek"},
    {"name": "deepseek-reasoner", "size": "—", "provider": "deepseek"},
]
OPENAI_MODELS = [
    {"name": "gpt-5.5", "size": "—", "provider": "openai"},
    {"name": "gpt-5-mini", "size": "—", "provider": "openai"},
]
ANTHROPIC_MODELS = [
    {"name": "claude-opus-5", "size": "—", "provider": "anthropic"},
    {"name": "claude-sonnet-5", "size": "—", "provider": "anthropic"},
    {"name": "claude-haiku-4-5-20251001", "size": "—", "provider": "anthropic"},
]

_load_config = config_store.load
_save_config = config_store.save


def _keep_masked_keys(new: ApiConfig, old: ApiConfig) -> ApiConfig:
    """The UI echoes masked keys back; never overwrite a real key with stars."""
    for field in ("deepseek_api_key", "openai_api_key", "anthropic_api_key"):
        value = getattr(new, field) or ""
        if "***" in value or (not value and getattr(old, field)):
            setattr(new, field, getattr(old, field))
    return new


@router.get("")
async def get_config() -> ApiConfigResponse:
    """Get current API configuration (keys masked)."""
    return ApiConfigResponse.from_config(_load_config())


@router.put("")
async def update_config(config: ApiConfig):
    """Update API configuration and apply the 跳板 setting."""
    config = _keep_masked_keys(config, _load_config())
    _save_config(config)
    proxy = {}
    try:
        if config.proxy_enabled:
            proxy = proxy_service.ensure(config)
        else:
            proxy = proxy_service.stop(config)
    except Exception as e:
        proxy = {"success": False, "message": f"跳板处理失败: {e}"}
    return {"success": True, "message": "配置已保存", "proxy": proxy}


@router.get("/models")
async def list_models(provider: str = "ollama") -> list[dict]:
    """List available models for the given provider."""
    config = _load_config()
    models: list[dict] = []

    if provider == "ollama" or not provider:
        models.extend(await llm_service.list_ollama_models(config.ollama_host, config.ollama_port))

    async def _live(name: str, key: str, base: str, static: list[dict]):
        if not key:
            models.extend({**m, "needs_key": True} for m in static)
            return
        ok, _msg, names = await llm_service._list_models_http(name, key, base)
        if ok and names:
            models.extend({"name": n, "size": "—", "provider": name} for n in names)
        else:
            models.extend(static)
        if config.default_model and config.provider == name and not any(m["name"] == config.default_model for m in models):
            models.insert(0, {"name": config.default_model, "size": "—", "provider": name})

    if provider == "deepseek" or not provider:
        await _live("deepseek", config.deepseek_api_key, config.deepseek_base_url, DEEPSEEK_MODELS)
    if provider == "openai":
        await _live("openai", config.openai_api_key, config.openai_base_url, OPENAI_MODELS)
    if provider == "anthropic":
        await _live("anthropic", config.anthropic_api_key, config.anthropic_base_url, ANTHROPIC_MODELS)

    return models


@router.post("/test")
async def test_connection(req: TestConnectionRequest) -> TestConnectionResponse:
    """Test connection to the specified provider."""
    cfg = _load_config()
    if req.provider == "ollama":
        ok, msg, names = await llm_service.test_ollama_connection(
            req.host or cfg.ollama_host, req.port or cfg.ollama_port)
        return TestConnectionResponse(success=ok, message=msg, models=names)

    stored = {"deepseek": (cfg.deepseek_api_key, cfg.deepseek_base_url),
              "openai": (cfg.openai_api_key, cfg.openai_base_url),
              "anthropic": (cfg.anthropic_api_key, cfg.anthropic_base_url)}.get(req.provider)
    if not stored:
        return TestConnectionResponse(success=False, message=f"未知的提供商: {req.provider}")
    api_key = req.api_key or ""
    if not api_key or "***" in api_key:     # the UI echoes the masked key back
        api_key = stored[0]
    base_url = req.base_url or stored[1]
    ok, msg, names = await llm_service._list_models_http(req.provider, api_key, base_url)
    return TestConnectionResponse(success=ok, message=msg, models=names)


# ---------------------------------------------------------------- 跳板 (proxy)
@router.get("/proxy")
async def proxy_status():
    """Is the jump-host tunnel up, and which providers go through it?"""
    return proxy_service.status(_load_config())


@router.post("/proxy/start")
async def proxy_start():
    return proxy_service.start(_load_config())


@router.post("/proxy/stop")
async def proxy_stop():
    return proxy_service.stop(_load_config())


@router.post("/proxy/test")
async def proxy_test():
    """Check the overseas endpoints through the tunnel, whatever the toggle says.

    A 401/403 is a success here: it means the request reached the real API and
    was only rejected for lack of a key.
    """
    import httpx

    cfg = _load_config()
    st = proxy_service.status(cfg)
    via_proxy = st["listening"]
    results = {}
    for name, url in (("openai", f"{cfg.openai_base_url.rstrip('/')}/v1/models"),
                      ("anthropic", f"{cfg.anthropic_base_url.rstrip('/')}/v1/models")):
        try:
            kwargs = {"timeout": 25.0}
            if via_proxy:
                kwargs["proxy"] = cfg.proxy_url
            async with httpx.AsyncClient(**kwargs) as client:
                r = await client.get(url)
            results[name] = {"ok": r.status_code in (200, 401, 403), "status": r.status_code}
        except Exception as e:
            results[name] = {"ok": False, "error": str(e)[:160] or type(e).__name__}
    exit_ip = None
    if via_proxy:
        try:
            async with httpx.AsyncClient(timeout=20.0, proxy=cfg.proxy_url) as client:
                exit_ip = (await client.get("https://api.ipify.org")).text.strip()[:40]
        except Exception:
            pass
    reachable = [k for k, v in results.items() if v.get("ok")]
    where = "经跳板" if via_proxy else "直连（隧道未监听）"
    msg = f"{where} 可达: {', '.join(reachable)}" if reachable else f"{where} 两个接口都不可达"
    if exit_ip:
        msg += f"；出口 IP {exit_ip}"
    return {"success": bool(reachable), "reachable": reachable, "results": results,
            "proxy": st, "via_proxy": via_proxy, "exit_ip": exit_ip, "message": msg}
