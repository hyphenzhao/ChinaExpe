"""思考档位怎么翻译成各家的请求体；不联网，用 MockTransport 抓请求。"""
import asyncio
import json

import httpx
import pytest

from app.models.config import ChatOptions
from app.services import llm_service as ls

MESSAGES = [{"role": "system", "content": "系统"}, {"role": "user", "content": "你好"}]


def _sse(*lines: str) -> bytes:
    return ("".join(f"{ln}\n\n" for ln in lines)).encode("utf-8")


def _patch_client(monkeypatch, handler):
    """让 llm_service 用 MockTransport，并记录每次请求体。"""
    seen: list[dict] = []

    def _fake(provider, timeout=120.0):
        def _h(request: httpx.Request) -> httpx.Response:
            seen.append(json.loads(request.content.decode()))
            return handler(len(seen), request)
        return httpx.AsyncClient(transport=httpx.MockTransport(_h), timeout=timeout)

    monkeypatch.setattr(ls, "_client", _fake)
    return seen


def _collect(gen):
    """Drain an async generator from a plain sync test (no pytest-asyncio needed)."""
    async def _run():
        return [e async for e in gen]
    return asyncio.run(_run())


def test_anthropic_thinking_budget(monkeypatch):
    body = _sse('data: {"type":"message_stop"}')
    seen = _patch_client(monkeypatch, lambda n, r: httpx.Response(200, content=body))
    _collect(ls.llm_service._stream_anthropic(
        MESSAGES, "claude-opus-5", "k", "https://api.anthropic.com", None, ChatOptions(thinking="high")))
    sent = seen[0]
    assert sent["thinking"] == {"type": "enabled", "budget_tokens": ls.ANTHROPIC_BUDGET["high"]}
    assert sent["max_tokens"] > sent["thinking"]["budget_tokens"]
    assert sent["system"] == "系统"


def test_anthropic_without_thinking(monkeypatch):
    body = _sse('data: {"type":"message_stop"}')
    seen = _patch_client(monkeypatch, lambda n, r: httpx.Response(200, content=body))
    _collect(ls.llm_service._stream_anthropic(
        MESSAGES, "claude-haiku-4-5", "k", "https://api.anthropic.com", None, ChatOptions(thinking="")))
    assert "thinking" not in seen[0] and seen[0]["max_tokens"] == 8192


def test_anthropic_retries_without_thinking_on_400(monkeypatch):
    ok = _sse('data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"嗨"}}',
              'data: {"type":"message_stop"}')
    seen = _patch_client(monkeypatch, lambda n, r: httpx.Response(400, json={"error": "thinking unsupported"})
                         if n == 1 else httpx.Response(200, content=ok))
    events = _collect(ls.llm_service._stream_anthropic(
        MESSAGES, "claude-old", "k", "https://api.anthropic.com", None, ChatOptions(thinking="high")))
    assert len(seen) == 2 and "thinking" in seen[0] and "thinking" not in seen[1]
    assert [e["content"] for e in events if e["type"] == "token"] == ["嗨"]
    assert not any("[错误]" in e.get("content", "") for e in events)


def test_anthropic_thinking_blocks_round_trip(monkeypatch):
    body = _sse(
        'data: {"type":"content_block_start","index":0,"content_block":{"type":"thinking"}}',
        'data: {"type":"content_block_delta","index":0,"delta":{"type":"thinking_delta","thinking":"想一下"}}',
        'data: {"type":"content_block_delta","index":0,"delta":{"type":"signature_delta","signature":"sig"}}',
        'data: {"type":"content_block_start","index":1,"content_block":{"type":"tool_use","id":"t1","name":"get_chart"}}',
        'data: {"type":"content_block_delta","index":1,"delta":{"type":"input_json_delta","partial_json":"{\\"person\\":\\"x\\"}"}}',
        'data: {"type":"message_stop"}')
    _patch_client(monkeypatch, lambda n, r: httpx.Response(200, content=body))
    events = _collect(ls.llm_service._stream_anthropic(
        MESSAGES, "claude-opus-5", "k", "https://api.anthropic.com", None, ChatOptions(thinking="low")))
    assert [e["content"] for e in events if e["type"] == "thinking"] == ["想一下"]
    call = next(e for e in events if e["type"] == "tool_calls")
    assert call["calls"][0]["function"]["name"] == "get_chart"
    assert call["thinking_blocks"] == [{"type": "thinking", "thinking": "想一下", "signature": "sig"}]


def test_to_anthropic_prepends_thinking_blocks():
    blocks = [{"type": "thinking", "thinking": "想", "signature": "s"}]
    _, msgs, _ = ls.LLMService._to_anthropic([
        {"role": "assistant", "content": "先查一下", "thinking_blocks": blocks,
         "tool_calls": [{"id": "t1", "function": {"name": "get_chart", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "t1", "content": "盘面"},
    ], None)
    assert msgs[0]["content"][0] == blocks[0]
    assert msgs[0]["content"][1]["type"] == "text"
    assert msgs[1]["content"][0]["type"] == "tool_result"


def test_openai_reasoning_effort_and_retry(monkeypatch):
    ok = _sse('data: {"choices":[{"delta":{"content":"好"}}]}', "data: [DONE]")
    seen = _patch_client(monkeypatch, lambda n, r: httpx.Response(400, json={"error": "unknown parameter reasoning_effort"})
                         if n == 1 else httpx.Response(200, content=ok))
    events = _collect(ls.llm_service._stream_openai_compatible(
        MESSAGES, "gpt-5.5", "k", "https://api.openai.com", None, "openai", ChatOptions(thinking="medium")))
    assert seen[0]["reasoning_effort"] == "medium" and "reasoning_effort" not in seen[1]
    assert [e["content"] for e in events if e["type"] == "token"] == ["好"]


def test_deepseek_never_gets_effort_and_streams_thinking(monkeypatch):
    ok = _sse('data: {"choices":[{"delta":{"reasoning_content":"斟酌"}}]}',
              'data: {"choices":[{"delta":{"content":"结论"}}]}',
              'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"c1","function":{"name":"get_bazi","arguments":"{}"}}]}}]}',
              "data: [DONE]")
    seen = _patch_client(monkeypatch, lambda n, r: httpx.Response(200, content=ok))
    events = _collect(ls.llm_service._stream_openai_compatible(
        MESSAGES, "deepseek-v4-pro", "k", "https://api.deepseek.com", None, "deepseek", ChatOptions(thinking="high")))
    assert "reasoning_effort" not in seen[0]
    assert [e["content"] for e in events if e["type"] == "thinking"] == ["斟酌"]
    call = next(e for e in events if e["type"] == "tool_calls")
    assert call["reasoning_content"] == "斟酌"       # DeepSeek 要求原样回传
