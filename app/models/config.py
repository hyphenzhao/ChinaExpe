"""Configuration and API provider models."""
from pydantic import BaseModel, Field
from typing import Optional, Literal

Provider = Literal["ollama", "deepseek", "openai", "anthropic"]

# Providers that usually need the 跳板 from mainland China.
DEFAULT_PROXY_PROVIDERS = ["openai", "anthropic"]


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
