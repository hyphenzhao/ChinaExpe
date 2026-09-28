"""Configuration and API provider models."""
from pydantic import BaseModel, Field
from typing import Optional, Literal

Provider = Literal["ollama", "deepseek", "openai", "anthropic"]
PROVIDERS = ("ollama", "deepseek", "openai", "anthropic")

# Providers that usually need the 跳板 from mainland China.
DEFAULT_PROXY_PROVIDERS = ["openai", "anthropic"]

THINKING_LEVELS = ("off", "low", "medium", "high")
THINKING_LABELS = {"off": "不思考", "low": "少量思考", "medium": "中等思考", "high": "深度思考"}
ThinkingCap = Literal["none", "optional", "always"]   # 不支持 / 可开关 / 模型自己一直思考


class ModelRef(BaseModel):
    """模型库里的一条：哪个提供商的哪个模型，以及它的能力。

    provider 故意用宽松的 str：config_store.load() 吞掉任何校验错误并退回空配置，
    一条坏数据就会把用户的 API Key 清空。校验放在接口层做。
    """
    provider: str = "ollama"
    model: str = ""
    label: str = ""                 # 显示名，空则显示 model
    supports_tools: bool = True
    thinking: ThinkingCap = "none"
    thinking_levels: list[str] = Field(default_factory=list)
    default_thinking: str = "off"
    max_tokens: int = 0             # 0 = 用各家默认
    note: str = ""


class ChatOptions(BaseModel):
    """单次请求的思考设置；chat_api 组装，llm_service 按提供商翻译。"""
    thinking: str = "off"
    max_tokens: int = 8192


class ModelPick(BaseModel):
    provider: str = ""
    model: str = ""


class LibraryUpdate(BaseModel):
    models: list[ModelRef] = Field(default_factory=list)
    default: Optional[ModelPick] = None


class CatalogModel(ModelRef):
    key: str = ""                   # "provider:model"，前端下拉框的取值
    ready: bool = True              # 该提供商的 key / 主机齐了
    needs_key: bool = False
    needs_proxy: bool = False       # 该提供商在 proxy_providers 里
    proxy_ok: bool = True
    warning: str = ""


class CatalogResponse(BaseModel):
    default: ModelPick
    models: list[CatalogModel] = Field(default_factory=list)
    proxy: dict = Field(default_factory=dict)
    thinking_levels: list[dict] = Field(default_factory=list)


class ApiConfig(BaseModel):
    """Persistent API provider configuration."""
    provider: Provider = "ollama"
    ollama_host: str = "http://127.0.0.1"
    ollama_port: int = 11434
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com"
    anthropic_api_key: str = ""
    anthropic_base_url: str = "https://api.anthropic.com"
    default_model: str = ""
    # 跳板：通过 45.77.19.55 的 SSH 动态转发访问海外 API，由用户自行开关
    proxy_enabled: bool = False
    proxy_url: str = "socks5h://127.0.0.1:1080"
    proxy_providers: list[str] = Field(default_factory=lambda: list(DEFAULT_PROXY_PROVIDERS))
    proxy_ssh_host: str = "45.77.19.55"
    proxy_ssh_user: str = "root"
    proxy_ssh_port: int = 22
    proxy_autostart: bool = True          # start the tunnel when the app starts
    enabled_models: list[ModelRef] = Field(default_factory=list)   # 模型库


def _mask(key: str) -> str:
    if key and len(key) > 8:
        return key[:4] + "*" * (len(key) - 8) + key[-4:]
    return key[:2] + "***" if key else ""


class ApiConfigResponse(BaseModel):
    """API config returned to frontend (keys masked)."""
    provider: str
    ollama_host: str
    ollama_port: int
    deepseek_api_key: str = ""     # masked
    deepseek_base_url: str
    openai_api_key: str = ""       # masked
    openai_base_url: str = "https://api.openai.com"
    anthropic_api_key: str = ""    # masked
    anthropic_base_url: str = "https://api.anthropic.com"
    default_model: str
    proxy_enabled: bool = False
    proxy_url: str = ""
    proxy_providers: list[str] = Field(default_factory=list)
    proxy_ssh_host: str = ""
    proxy_ssh_user: str = ""
    proxy_ssh_port: int = 22
    proxy_autostart: bool = True
    enabled_models: list[ModelRef] = Field(default_factory=list)

    @classmethod
    def from_config(cls, config: ApiConfig) -> "ApiConfigResponse":
        return cls(
            provider=config.provider,
            ollama_host=config.ollama_host,
            ollama_port=config.ollama_port,
            deepseek_api_key=_mask(config.deepseek_api_key),
            deepseek_base_url=config.deepseek_base_url,
            openai_api_key=_mask(config.openai_api_key),
            openai_base_url=config.openai_base_url,
            anthropic_api_key=_mask(config.anthropic_api_key),
            anthropic_base_url=config.anthropic_base_url,
            default_model=config.default_model,
            proxy_enabled=config.proxy_enabled,
            proxy_url=config.proxy_url,
            proxy_providers=config.proxy_providers,
            proxy_ssh_host=config.proxy_ssh_host,
            proxy_ssh_user=config.proxy_ssh_user,
            proxy_ssh_port=config.proxy_ssh_port,
            proxy_autostart=config.proxy_autostart,
            enabled_models=config.enabled_models,
        )


class ModelInfo(BaseModel):
    """A single model entry."""
    name: str
    provider: str
    size: Optional[str] = None


class TestConnectionRequest(BaseModel):
    """Request to test an API connection."""
    provider: str
    host: Optional[str] = None
    port: Optional[int] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None


class TestConnectionResponse(BaseModel):
    """Result of a connection test."""
    success: bool
    message: str
    models: list[str] = []
