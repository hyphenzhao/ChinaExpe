"""LLM service - abstract streaming for Ollama and DeepSeek APIs.

Supports both text streaming and tool/function calling (OpenAI-compatible).
"""

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
        tools: Optional[list[dict]] = None,
    ) -> AsyncGenerator[dict, None]:
        """Stream chat completion from the configured provider.

        Args:
            messages: List of {'role': ..., 'content': ...} dicts
            model: Model name
            provider: 'ollama' or 'deepseek'
            tools: Optional OpenAI-compatible tool definitions

        Yields:
            dicts with type: 'token' ({'content': str}) or
            'tool_calls' ({'calls': [{'id':..., 'function':{...}}]})
        """
        if provider == "ollama":
            async for event in self._stream_ollama(
                messages, model, ollama_host, ollama_port, tools
            ):
                yield event
        elif provider == "deepseek":
            async for event in self._stream_deepseek(
                messages, model, deepseek_api_key, deepseek_base_url, tools
            ):
                yield event
        else:
            yield {"type": "token", "content": f"[错误] 未知的提供商: {provider}"}

    async def _stream_ollama(
        self,
        messages: list[dict],
        model: str,
        host: str,
        port: int,
        tools: Optional[list[dict]] = None,
    ) -> AsyncGenerator[dict, None]:
        """Stream from Ollama API. Tool calls returned when done=true."""
        url = f"{host.rstrip('/')}:{port}/api/chat"
        payload = {"model": model, "messages": messages, "stream": True}
        if tools:
            payload["tools"] = tools

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream("POST", url, json=payload) as resp:
                    if resp.status_code != 200:
                        body = await resp.aread()
                        yield {
                            "type": "token",
                            "content": f"[错误] Ollama API 返回 {resp.status_code}: {body.decode()[:200]}",
                        }
                        return
                    async for line in resp.aiter_lines():
                        if not line.strip():
                            continue
                        try:
                            data = json.loads(line)
                        except json.JSONDecodeError:
                            continue

                        # Text content
                        content = data.get("message", {}).get("content", "")
                        if content:
                            yield {"type": "token", "content": content}

                        if data.get("done", False):
                            # Check for tool calls (Ollama returns full tool_calls on done)
                            tool_calls = data.get("message", {}).get("tool_calls", [])
                            if tool_calls:
                                formatted = []
                                for tc in tool_calls:
                                    formatted.append(
                                        {
                                            "id": tc.get("id", ""),
                                            "type": "function",
                                            "function": {
                                                "name": tc.get("function", {}).get(
                                                    "name", ""
                                                ),
                                                "arguments": json.dumps(
                                                    tc.get("function", {}).get(
                                                        "arguments", {}
                                                    )
                                                )
                                                if isinstance(
                                                    tc.get("function", {}).get(
                                                        "arguments"
                                                    ),
                                                    dict,
                                                )
                                                else tc.get("function", {}).get(
                                                    "arguments", "{}"
                                                ),
                                            },
                                        }
                                    )
                                yield {"type": "tool_calls", "calls": formatted}
                            return
        except httpx.ConnectError:
            yield {
                "type": "token",
                "content": f"[错误] 无法连接到 Ollama ({host}:{port})，请确认 Ollama 服务已启动",
            }
        except Exception as e:
            yield {"type": "token", "content": f"[错误] Ollama 请求失败: {str(e)}"}

    async def _stream_deepseek(
        self,
        messages: list[dict],
        model: str,
        api_key: str,
        base_url: str,
        tools: Optional[list[dict]] = None,
    ) -> AsyncGenerator[dict, None]:
        """Stream from DeepSeek API (OpenAI-compatible) with tool calling support."""
        url = f"{base_url.rstrip('/')}/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {"model": model, "messages": messages, "stream": True}
        if tools:
            payload["tools"] = tools

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream(
                    "POST", url, json=payload, headers=headers
                ) as resp:
                    if resp.status_code != 200:
                        body = await resp.aread()
                        yield {
                            "type": "token",
                            "content": f"[错误] DeepSeek API 返回 {resp.status_code}: {body.decode()[:200]}",
                        }
                        return

                    # Accumulate tool call deltas by index
                    tool_call_buf: dict[int, dict] = {}
                    # Thinking mode: the reasoning must be passed back to the API
                    # together with the tool calls in the follow-up request.
                    reasoning = ""

                    async for line in resp.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        data_str = line[6:].strip()
                        if data_str == "[DONE]":
                            # Emit any accumulated tool calls
                            if tool_call_buf:
                                calls = [
                                    tool_call_buf[i]
                                    for i in sorted(tool_call_buf.keys())
                                ]
                                yield {"type": "tool_calls", "calls": calls,
                                       "reasoning_content": reasoning}
                            return

                        try:
                            data = json.loads(data_str)
                        except json.JSONDecodeError:
                            continue

                        choices = data.get("choices", [])
                        if not choices:
                            continue

                        delta = choices[0].get("delta", {})

                        rc = delta.get("reasoning_content")
                        if rc:
                            reasoning += rc

                        # Text content
                        content = delta.get("content", "")
                        if content:
                            yield {"type": "token", "content": content}

                        # Tool call deltas (accumulate)
                        tc_deltas = delta.get("tool_calls", [])
                        for tc in tc_deltas:
                            idx = tc.get("index", 0)
                            if idx not in tool_call_buf:
                                tool_call_buf[idx] = {
                                    "id": "",
                                    "type": "function",
                                    "function": {"name": "", "arguments": ""},
                                }
                            buf = tool_call_buf[idx]
                            if "id" in tc:
                                buf["id"] = tc["id"]
                            func = tc.get("function", {})
                            if "name" in func:
                                buf["function"]["name"] = func["name"]
                            if "arguments" in func:
                                buf["function"]["arguments"] += func["arguments"]

        except httpx.ConnectError:
            yield {
                "type": "token",
                "content": f"[错误] 无法连接到 DeepSeek API ({base_url})",
            }
        except Exception as e:
            yield {"type": "token", "content": f"[错误] DeepSeek 请求失败: {str(e)}"}

    async def list_ollama_models(
        self, host: str = "http://127.0.0.1", port: int = 11434
    ) -> list[dict]:
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

    async def test_ollama_connection(
        self, host: str, port: int
    ) -> tuple[bool, str, list[str]]:
        """Test connection to Ollama."""
        models = await self.list_ollama_models(host, port)
        if models:
            model_names = [m["name"] for m in models]
            return True, f"连接成功，找到 {len(models)} 个模型", model_names
        return False, "无法连接到 Ollama，请检查服务是否运行", []

    async def test_deepseek_connection(
        self, api_key: str, base_url: str
    ) -> tuple[bool, str, list[str]]:
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
