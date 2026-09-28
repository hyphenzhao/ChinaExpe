"""LLM service - abstract streaming for Ollama, DeepSeek, OpenAI and Anthropic.

Supports text streaming and tool/function calling.  DeepSeek and OpenAI share
the OpenAI-compatible wire format; Anthropic's Messages API is converted in
_stream_anthropic.  Overseas providers can go through the 跳板 (see
proxy_service): config_store.proxy_for(provider) decides per request.
"""

import json
from typing import AsyncGenerator, Optional

import httpx

from ..models.config import ChatOptions

ANTHROPIC_VERSION = "2023-06-01"
# 思考预算（tokens）：Anthropic 要求 ≥1024 且 max_tokens 必须大于预算
ANTHROPIC_BUDGET = {"low": 2048, "medium": 8192, "high": 24576}
OPENAI_EFFORT = {"low": "low", "medium": "medium", "high": "high"}
RETRY_STATUS = (400, 404, 422)          # 参数不被接受时，去掉思考参数重试一次


def _proxy(provider: str) -> Optional[str]:
    try:
        from . import config_store
        return config_store.proxy_for(provider)
    except Exception:
        return None


def _client(provider: str, timeout: float = 120.0) -> httpx.AsyncClient:
    """httpx client, routed through the 跳板 when the user enabled it."""
    proxy = _proxy(provider)
    try:
        return httpx.AsyncClient(timeout=timeout, proxy=proxy) if proxy else httpx.AsyncClient(timeout=timeout)
    except Exception:
        # socks support missing (needs httpx[socks]) — fall back to a direct connection
        return httpx.AsyncClient(timeout=timeout)


class LLMService:
    """Unified streaming interface for the supported providers."""

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
        openai_api_key: str = "",
        openai_base_url: str = "https://api.openai.com",
        anthropic_api_key: str = "",
        anthropic_base_url: str = "https://api.anthropic.com",
        options: Optional[ChatOptions] = None,
    ) -> AsyncGenerator[dict, None]:
        """Stream a chat completion from the configured provider.

        Yields dicts with type 'token' ({'content': str}), 'thinking'
        ({'content': str}) or 'tool_calls' ({'calls': [...],
        'reasoning_content': str, 'thinking_blocks': [...]}).
        `options` carries the per-request thinking level.
        """
        if provider == "ollama":
            async for event in self._stream_ollama(
                messages, model, ollama_host, ollama_port, tools
            ):
                yield event
        elif provider in ("deepseek", "openai"):
            key = deepseek_api_key if provider == "deepseek" else openai_api_key
            base = deepseek_base_url if provider == "deepseek" else openai_base_url
            async for event in self._stream_openai_compatible(
                messages, model, key, base, tools, provider, options
            ):
                yield event
        elif provider == "anthropic":
            async for event in self._stream_anthropic(
                messages, model, anthropic_api_key, anthropic_base_url, tools, options
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

    async def _stream_openai_compatible(
        self,
        messages: list[dict],
        model: str,
        api_key: str,
        base_url: str,
        tools: Optional[list[dict]] = None,
        provider: str = "deepseek",
        options: Optional[ChatOptions] = None,
    ) -> AsyncGenerator[dict, None]:
        """Stream from an OpenAI-compatible API (DeepSeek, OpenAI) with tool calls."""
        label = "OpenAI" if provider == "openai" else "DeepSeek"
        base = base_url.rstrip("/")
        url = base + ("/chat/completions" if base.endswith("/v1") else "/v1/chat/completions")
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {"model": model, "messages": messages, "stream": True}
        if tools:
            payload["tools"] = tools
        # DeepSeek 的思考由模型本身决定，不接受档位参数；只有 OpenAI 下发 reasoning_effort
        extra: dict = {}
        if provider == "openai" and options and options.thinking in OPENAI_EFFORT:
            extra["reasoning_effort"] = OPENAI_EFFORT[options.thinking]
        attempts = [{**payload, **extra}] + ([payload] if extra else [])

        try:
            async with _client(provider) as client:
                for attempt, body_json in enumerate(attempts):
                    async with client.stream(
                        "POST", url, json=body_json, headers=headers
                    ) as resp:
                        if resp.status_code != 200:
                            body = await resp.aread()
                            # 参数不被接受时，去掉思考参数再试一次（还没吐过 token，安全）
                            if resp.status_code in RETRY_STATUS and attempt + 1 < len(attempts):
                                continue
                            yield {
                                "type": "token",
                                "content": f"[错误] {label} API 返回 {resp.status_code}: {body.decode()[:200]}",
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
                                yield {"type": "thinking", "content": rc}

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
                        return

        except httpx.ConnectError:
            hint = "；已开启跳板但连不上，检查设置里的跳板状态" if _proxy(provider) else ""
            yield {"type": "token", "content": f"[错误] 无法连接到 {label} API ({base_url}){hint}"}
        except Exception as e:
            yield {"type": "token", "content": f"[错误] {label} 请求失败: {str(e)}"}

    # ------------------------------------------------------------- anthropic
    @staticmethod
    def _to_anthropic(messages: list[dict], tools: Optional[list[dict]]) -> tuple[str, list[dict], list[dict]]:
        """Convert OpenAI-style messages/tools to the Anthropic Messages format."""
        system_parts, out = [], []
        for m in messages:
            role = m.get("role")
            if role == "system":
                system_parts.append(m.get("content") or "")
                continue
            if role == "tool":
                block = {"type": "tool_result", "tool_use_id": m.get("tool_call_id", ""),
                         "content": m.get("content") or ""}
                if out and out[-1]["role"] == "user" and isinstance(out[-1]["content"], list):
                    out[-1]["content"].append(block)
                else:
                    out.append({"role": "user", "content": [block]})
                continue
            if role == "assistant" and m.get("tool_calls"):
                blocks = []
                # extended thinking: the thinking block that preceded a tool_use
                # must be sent back untouched, or the API rejects the follow-up
                for tb in m.get("thinking_blocks") or []:
                    blocks.append(tb)
                if m.get("content"):
                    blocks.append({"type": "text", "text": m["content"]})
                for tc in m["tool_calls"]:
                    fn = tc.get("function", {})
                    try:
                        args = json.loads(fn.get("arguments") or "{}")
                    except json.JSONDecodeError:
                        args = {}
                    blocks.append({"type": "tool_use", "id": tc.get("id", ""),
                                   "name": fn.get("name", ""), "input": args})
                out.append({"role": "assistant", "content": blocks})
                continue
            if m.get("content"):
                out.append({"role": role, "content": m["content"]})
        conv = [{"name": t["function"]["name"],
                 "description": t["function"].get("description", ""),
                 "input_schema": t["function"].get("parameters") or {"type": "object", "properties": {}}}
                for t in (tools or [])]
        return "\n\n".join(p for p in system_parts if p), out, conv

    async def _stream_anthropic(
        self,
        messages: list[dict],
        model: str,
        api_key: str,
        base_url: str,
        tools: Optional[list[dict]] = None,
        options: Optional[ChatOptions] = None,
    ) -> AsyncGenerator[dict, None]:
        """Stream from the Anthropic Messages API, emitting the same events."""
        system, msgs, atools = self._to_anthropic(messages, tools)
        base = base_url.rstrip("/")
        url = base + ("/messages" if base.endswith("/v1") else "/v1/messages")
        headers = {"x-api-key": api_key, "anthropic-version": ANTHROPIC_VERSION,
                   "content-type": "application/json"}
        base_max = (options.max_tokens if options else 0) or 8192
        payload: dict = {"model": model, "messages": msgs, "max_tokens": base_max, "stream": True}
        if system:
            payload["system"] = system
        if atools:
            payload["tools"] = atools
        extra: dict = {}
        level = options.thinking if options else ""
        if level in ANTHROPIC_BUDGET:
            budget = ANTHROPIC_BUDGET[level]
            extra["thinking"] = {"type": "enabled", "budget_tokens": budget}
            extra["max_tokens"] = max(base_max, budget + 1024)   # API 要求 max_tokens > budget
        attempts = [{**payload, **extra}] + ([payload] if extra else [])
        try:
            async with _client("anthropic") as client:
                for attempt, body_json in enumerate(attempts):
                    async with client.stream("POST", url, json=body_json, headers=headers) as resp:
                        if resp.status_code != 200:
                            body = await resp.aread()
                            if resp.status_code in RETRY_STATUS and attempt + 1 < len(attempts):
                                continue        # 模型不支持扩展思考，去掉参数重试
                            yield {"type": "token",
                                   "content": f"[错误] Anthropic API 返回 {resp.status_code}: {body.decode()[:200]}"}
                            return
                        blocks: dict[int, dict] = {}
                        async for line in resp.aiter_lines():
                            if not line.startswith("data:"):
                                continue
                            try:
                                data = json.loads(line[5:].strip())
                            except json.JSONDecodeError:
                                continue
                            etype = data.get("type")
                            idx = data.get("index", 0)
                            if etype == "content_block_start":
                                blk = data.get("content_block", {})
                                blocks[idx] = {"type": blk.get("type"), "id": blk.get("id", ""),
                                               "name": blk.get("name", ""), "json": "",
                                               "text": "", "signature": "", "data": blk.get("data", "")}
                            elif etype == "content_block_delta":
                                d = data.get("delta", {})
                                dtype = d.get("type")
                                if dtype == "text_delta" and d.get("text"):
                                    yield {"type": "token", "content": d["text"]}
                                elif dtype == "input_json_delta":
                                    b = blocks.setdefault(idx, {"type": "tool_use", "id": "", "name": "",
                                                                "json": "", "text": "", "signature": ""})
                                    b["json"] += d.get("partial_json", "")
                                elif dtype == "thinking_delta" and d.get("thinking"):
                                    b = blocks.setdefault(idx, {"type": "thinking", "id": "", "name": "",
                                                                "json": "", "text": "", "signature": ""})
                                    b["text"] += d["thinking"]
                                    yield {"type": "thinking", "content": d["thinking"]}
                                elif dtype == "signature_delta":
                                    b = blocks.setdefault(idx, {"type": "thinking", "id": "", "name": "",
                                                                "json": "", "text": "", "signature": ""})
                                    b["signature"] += d.get("signature", "")
                            elif etype == "message_stop":
                                break
                        ordered = [b for _, b in sorted(blocks.items())]
                        calls = [{"id": b["id"], "type": "function",
                                  "function": {"name": b["name"], "arguments": b["json"] or "{}"}}
                                 for b in ordered if b.get("type") == "tool_use"]
                        if calls:
                            thinking_blocks = []
                            for b in ordered:
                                if b.get("type") == "thinking" and b.get("text"):
                                    thinking_blocks.append({"type": "thinking", "thinking": b["text"],
                                                            "signature": b.get("signature", "")})
                                elif b.get("type") == "redacted_thinking" and b.get("data"):
                                    thinking_blocks.append({"type": "redacted_thinking", "data": b["data"]})
                            event = {"type": "tool_calls", "calls": calls}
                            if thinking_blocks:
                                event["thinking_blocks"] = thinking_blocks
                            yield event
                        return
        except httpx.ConnectError:
            hint = "；已开启跳板但连不上，检查设置里的跳板状态" if _proxy("anthropic") else "；大陆网络通常需要开启跳板"
            yield {"type": "token", "content": f"[错误] 无法连接到 Anthropic API ({base_url}){hint}"}
        except Exception as e:
            yield {"type": "token", "content": f"[错误] Anthropic 请求失败: {str(e)}"}

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
        return await self._list_models_http("deepseek", api_key, base_url)

    async def test_openai_connection(
        self, api_key: str, base_url: str = "https://api.openai.com"
    ) -> tuple[bool, str, list[str]]:
        return await self._list_models_http("openai", api_key, base_url)

    async def test_anthropic_connection(
        self, api_key: str, base_url: str = "https://api.anthropic.com"
    ) -> tuple[bool, str, list[str]]:
        return await self._list_models_http("anthropic", api_key, base_url)

    async def _list_models_http(
        self, provider: str, api_key: str, base_url: str
    ) -> tuple[bool, str, list[str]]:
        """GET /v1/models for the OpenAI-shaped providers (Anthropic included)."""
        if not api_key:
            return False, "还没有填 API Key", []
        base = base_url.rstrip("/")
        url = base + ("/models" if base.endswith("/v1") else "/v1/models")
        if provider == "anthropic":
            headers = {"x-api-key": api_key, "anthropic-version": ANTHROPIC_VERSION}
        else:
            headers = {"Authorization": f"Bearer {api_key}"}
        via = "（经跳板）" if _proxy(provider) else ""
        try:
            async with _client(provider, timeout=20.0) as client:
                resp = await client.get(url, headers=headers)
            if resp.status_code == 200:
                models = [m.get("id", "") for m in resp.json().get("data", [])]
                return True, f"连接成功{via}，找到 {len(models)} 个模型", models
            return False, f"API 返回 {resp.status_code}{via}: {resp.text[:200]}", []
        except Exception as e:
            hint = "" if _proxy(provider) else "；大陆网络访问 OpenAI/Anthropic 通常要先开跳板" if provider in ("openai", "anthropic") else ""
            return False, f"连接失败{via}: {str(e)}{hint}", []


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
