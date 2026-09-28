"""Configuration API routes."""
import time

from fastapi import APIRouter, HTTPException

from ..models.config import (
    PROVIDERS, THINKING_LABELS, THINKING_LEVELS,
    ApiConfig, ApiConfigResponse, CatalogModel, CatalogResponse, LibraryUpdate, ModelPick,
    TestConnectionRequest, TestConnectionResponse,
)
from ..services import config_store, model_registry, proxy_service
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


def _keep_library(new: ApiConfig, old: ApiConfig) -> ApiConfig:
    """整体 PUT 不带模型库时别把它清空；清空请用 PUT /api/config/library。"""
    if not new.enabled_models and old.enabled_models:
        new.enabled_models = old.enabled_models
    return new


# live model lists are hit often by the pickers; cache them briefly
_models_cache: dict[str, tuple[float, list[dict]]] = {}
MODELS_TTL = 300.0


@router.get("")
async def get_config() -> ApiConfigResponse:
    """Get current API configuration (keys masked)."""
    return ApiConfigResponse.from_config(_load_config())


PROXY_FIELDS = ("proxy_enabled", "proxy_url", "proxy_providers", "proxy_ssh_host",
                "proxy_ssh_user", "proxy_ssh_port", "proxy_autostart")


@router.put("")
async def update_config(config: ApiConfig):
    """保存提供商与模型配置。

    **不碰跳板**：跳板字段一律沿用磁盘上的值，改跳板请用 PUT /api/config/proxy。
    以前两者混在一个保存按钮里，页面上没勾选的复选框会把正在用的隧道悄悄停掉。
    """
    old = _load_config()
    config = _keep_library(_keep_masked_keys(config, old), old)
    for field in PROXY_FIELDS:
        setattr(config, field, getattr(old, field))
    _save_config(config)
    return {"success": True, "message": "配置已保存", "proxy": proxy_service.snapshot(config)}


@router.put("/proxy")
async def update_proxy(settings: dict):
    """只改跳板设置并立即生效（启用则起隧道，停用则停自己起的那条）。"""
    cfg = _load_config()
    unknown = [k for k in settings if k not in PROXY_FIELDS]
    if unknown:
        raise HTTPException(400, f"不是跳板设置项: {', '.join(unknown)}")
    for k, v in settings.items():
        setattr(cfg, k, v)
    _save_config(cfg)
    try:
        result = proxy_service.ensure(cfg) if cfg.proxy_enabled else proxy_service.stop(cfg)
    except Exception as e:
        result = {"success": False, "message": f"跳板处理失败: {e}"}
    return {"success": True, "message": "跳板设置已保存", "proxy": result}


@router.get("/models")
async def list_models(provider: str = "ollama", refresh: int = 0) -> list[dict]:
    """List models for one provider (or all when provider is empty).

    Rows carry the inferred capabilities and `in_library`, so the settings page
    can render a checkbox plus a 思考 badge per row.  A row marked `stale` means
    the live list could not be fetched and this is the hardcoded fallback.
    """
    config = _load_config()
    models: list[dict] = []
    in_library = {(m.provider, m.model) for m in config.enabled_models}

    def _decorate(rows: list[dict]) -> list[dict]:
        out = []
        for r in rows:
            caps = model_registry.infer_caps(r.get("provider", ""), r.get("name", ""))
            out.append({**r, "in_library": (caps.provider, caps.model) in in_library,
                        "supports_tools": caps.supports_tools, "thinking": caps.thinking,
                        "thinking_levels": caps.thinking_levels,
                        "default_thinking": caps.default_thinking})
        return out

    if provider == "ollama" or not provider:
        models.extend(await llm_service.list_ollama_models(config.ollama_host, config.ollama_port))

    async def _live(name: str, key: str, base: str, static: list[dict]):
        if not key:
            models.extend({**m, "needs_key": True, "stale": True} for m in static)
            return
        cache_key = f"{name}|{base}"
        hit = _models_cache.get(cache_key)
        if hit and not refresh and time.time() - hit[0] < MODELS_TTL:
            models.extend(hit[1])
            return
        ok, msg, names = await llm_service._list_models_http(name, key, base)
        if ok and names:
            rows = [{"name": n, "size": "—", "provider": name} for n in names]
            _models_cache[cache_key] = (time.time(), rows)
        else:
            rows = [{**m, "stale": True, "error": msg} for m in static]
        models.extend(rows)
        if config.default_model and config.provider == name and not any(m["name"] == config.default_model for m in models):
            models.insert(0, {"name": config.default_model, "size": "—", "provider": name})

    if provider == "deepseek" or not provider:
        await _live("deepseek", config.deepseek_api_key, config.deepseek_base_url, DEEPSEEK_MODELS)
    if provider == "openai" or not provider:
        await _live("openai", config.openai_api_key, config.openai_base_url, OPENAI_MODELS)
    if provider == "anthropic" or not provider:
        await _live("anthropic", config.anthropic_api_key, config.anthropic_base_url, ANTHROPIC_MODELS)

    return _decorate(models)


# ------------------------------------------------------------------ 模型库
@router.get("/library")
async def get_library():
    """模型库与默认模型（不含任何密钥）。"""
    cfg = _load_config()
    return {"models": cfg.enabled_models,
            "default": {"provider": cfg.provider, "model": cfg.default_model}}


@router.put("/library")
async def put_library(req: LibraryUpdate):
    """保存模型库；可同时指定默认模型。"""
    cfg = _load_config()
    for m in req.models:
        if m.provider not in PROVIDERS:
            raise HTTPException(400, f"未知的提供商: {m.provider}")
        if not (m.model or "").strip():
            raise HTTPException(400, "模型 ID 不能为空")
    cfg.enabled_models = model_registry.normalize(req.models)

    message = "已保存模型库"
    pick = req.default
    if pick and pick.model and any((m.provider, m.model) == (pick.provider, pick.model)
                                   for m in cfg.enabled_models):
        cfg.provider, cfg.default_model = pick.provider, pick.model
    elif cfg.enabled_models and not any(
            (m.provider, m.model) == (cfg.provider, cfg.default_model) for m in cfg.enabled_models):
        first = cfg.enabled_models[0]
        cfg.provider, cfg.default_model = first.provider, first.model
        message += f"；默认模型已改为 {first.label or first.model}"
    _save_config(cfg)
    return {"success": True, "message": message, "models": cfg.enabled_models,
            "default": {"provider": cfg.provider, "model": cfg.default_model}}


@router.get("/catalog")
async def catalog() -> CatalogResponse:
    """聊天页选择器要的一切：可选模型、能力、跳板状态。纯读取，不会启动隧道。"""
    cfg = _load_config()
    snap = proxy_service.snapshot(cfg)
    rows: list[CatalogModel] = []
    for m in cfg.enabled_models:
        needs_proxy = m.provider in (cfg.proxy_providers or [])
        ready = model_registry.is_ready(cfg, m.provider)
        warning = ""
        if not ready:
            warning = f"{m.provider} 还没有填 API Key（设置 → AI 提供商）"
        elif needs_proxy:
            warning = proxy_service.warning_for(cfg, m.provider)
        rows.append(CatalogModel(**m.model_dump(), key=f"{m.provider}:{m.model}",
                                 ready=ready, needs_key=not ready, needs_proxy=needs_proxy,
                                 proxy_ok=not needs_proxy or snap["listening"], warning=warning))
    return CatalogResponse(
        default=ModelPick(provider=cfg.provider, model=cfg.default_model),
        models=rows, proxy=snap,
        thinking_levels=[{"value": lv, "label": THINKING_LABELS[lv]} for lv in THINKING_LEVELS],
    )


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
