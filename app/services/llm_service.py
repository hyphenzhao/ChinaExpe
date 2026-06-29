"""LLM service - abstract streaming for Ollama and DeepSeek."""
import json
from typing import AsyncGenerator, Optional

import httpx


class LLMService:
    """Unified streaming interface for Ollama and DeepSeek APIs."""

    async def stream_chat(
        self,
        messages: list[dict],
        model: str,
        provider: str = "ollama",
        ollama_host: str = "http://127.0.0.1",
        ollama_port: int = 11434,
        deepseek_api_key: str = "",
        deepseek_base_url: str = "https://api.deepseek.com",
    ) -> AsyncGenerator[str, None]:
        """Stream chat completion tokens from the configured provider.

        Args:
            messages: List of {'role': 'user'|'assistant'|'system', 'content': '...'}
            model: Model name
            provider: 'ollama' or 'deepseek'
            ollama_host: Ollama server host
            ollama_port: Ollama server port
            deepseek_api_key: DeepSeek API key
            deepseek_base_url: DeepSeek base URL

        Yields:
            String tokens from the model response
        """
        if provider == "ollama":
            async for token in self._stream_ollama(messages, model, ollama_host, ollama_port):
                yield token
        elif provider == "deepseek":
            async for token in self._stream_deepseek(messages, model, deepseek_api_key, deepseek_base_url):
                yield token
        else:
            yield f"[错误] 未知的提供商: {provider}"

    async def _stream_ollama(
        self, messages: list[dict], model: str, host: str, port: int
    ) -> AsyncGenerator[str, None]:
        """Stream from Ollama API."""
        url = f"{host.rstrip('/')}:{port}/api/chat"
        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
        }
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream("POST", url, json=payload) as resp:
                    if resp.status_code != 200:
                        body = await resp.aread()
                        yield f"[错误] Ollama API 返回 {resp.status_code}: {body.decode()[:200]}"
                        return
                    async for line in resp.aiter_lines():
                        if line.strip():
                            try:
                                data = json.loads(line)
                                content = data.get("message", {}).get("content", "")
                                if content:
                                    yield content
                                if data.get("done", False):
                                    return
                            except json.JSONDecodeError:
                                continue
        except httpx.ConnectError:
            yield f"[错误] 无法连接到 Ollama ({host}:{port})，请确认 Ollama 服务已启动"
        except Exception as e:
            yield f"[错误] Ollama 请求失败: {str(e)}"

    async def _stream_deepseek(
        self, messages: list[dict], model: str, api_key: str, base_url: str
    ) -> AsyncGenerator[str, None]:
        """Stream from DeepSeek API (OpenAI-compatible)."""
        url = f"{base_url.rstrip('/')}/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
        }
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream("POST", url, json=payload, headers=headers) as resp:
                    if resp.status_code != 200:
                        body = await resp.aread()
                        yield f"[错误] DeepSeek API 返回 {resp.status_code}: {body.decode()[:200]}"
                        return
                    async for line in resp.aiter_lines():
                        if line.startswith("data: "):
                            data_str = line[6:].strip()
                            if data_str == "[DONE]":
                                return
                            try:
                                data = json.loads(data_str)
                                choices = data.get("choices", [])
                                if choices:
                                    delta = choices[0].get("delta", {})
                                    content = delta.get("content", "")
                                    if content:
                                        yield content
                            except json.JSONDecodeError:
                                continue
        except httpx.ConnectError:
            yield f"[错误] 无法连接到 DeepSeek API ({base_url})"
        except Exception as e:
            yield f"[错误] DeepSeek 请求失败: {str(e)}"

    async def list_ollama_models(self, host: str = "http://127.0.0.1", port: int = 11434) -> list[dict]:
        """List available models from Ollama."""
        url = f"{host.rstrip('/')}:{port}/api/tags"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    models = data.get("models", [])
                    return [
                        {
                            "name": m.get("name", ""),
                            "size": _format_size(m.get("size", 0)),
                            "provider": "ollama",
                        }
                        for m in models
                    ]
        except Exception:
            pass
        return []

    async def test_ollama_connection(self, host: str, port: int) -> tuple[bool, str, list[str]]:
        """Test connection to Ollama."""
        models = await self.list_ollama_models(host, port)
        if models:
            model_names = [m["name"] for m in models]
            return True, f"连接成功，找到 {len(models)} 个模型", model_names
        return False, "无法连接到 Ollama，请检查服务是否运行", []

    async def test_deepseek_connection(self, api_key: str, base_url: str) -> tuple[bool, str, list[str]]:
        """Test connection to DeepSeek API by listing models."""
        url = f"{base_url.rstrip('/')}/v1/models"
        headers = {"Authorization": f"Bearer {api_key}"}
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(url, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    models = [m.get("id", "") for m in data.get("data", [])]
                    return True, f"连接成功，找到 {len(models)} 个模型", models
                else:
                    return False, f"API 返回 {resp.status_code}: {resp.text[:200]}", []
        except Exception as e:
            return False, f"连接失败: {str(e)}", []


def _format_size(size_bytes: int) -> str:
    """Format byte size to human-readable string."""
    if size_bytes >= 1_000_000_000:
        return f"{size_bytes / 1_000_000_000:.1f} GB"
    elif size_bytes >= 1_000_000:
        return f"{size_bytes / 1_000_000:.0f} MB"
    elif size_bytes >= 1_000:
        return f"{size_bytes / 1_000:.0f} KB"
    return f"{size_bytes} B"


# Singleton
llm_service = LLMService()
