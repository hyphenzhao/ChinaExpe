"""Configuration and API provider models."""
from pydantic import BaseModel, Field
from typing import Optional, Literal


class ApiConfig(BaseModel):
    """Persistent API provider configuration."""
    provider: Literal["ollama", "deepseek"] = "ollama"
    ollama_host: str = "http://127.0.0.1"
    ollama_port: int = 11434
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    default_model: str = ""


class ApiConfigResponse(BaseModel):
    """API config returned to frontend (key masked)."""
    provider: str
    ollama_host: str
    ollama_port: int
    deepseek_api_key: str = ""  # masked
    deepseek_base_url: str
    default_model: str

    @classmethod
    def from_config(cls, config: ApiConfig) -> "ApiConfigResponse":
        key = config.deepseek_api_key
        masked = ""
        if key and len(key) > 8:
            masked = key[:4] + "*" * (len(key) - 8) + key[-4:]
        elif key:
            masked = key[:2] + "***"
        return cls(
            provider=config.provider,
            ollama_host=config.ollama_host,
            ollama_port=config.ollama_port,
            deepseek_api_key=masked,
            deepseek_base_url=config.deepseek_base_url,
            default_model=config.default_model,
        )


class ModelInfo(BaseModel):
    """A single model entry."""
    name: str
    provider: str  # "ollama" or "deepseek"
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
