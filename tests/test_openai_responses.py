"""OpenAI protocol regression tests: no API keys or real network requests."""
import asyncio
import copy
import json

import httpx
import pytest

from app.models.config import ChatOptions
from app.services import llm_service as ls
from app.services import openai_responses as wire

MESSAGES = [{"role": "system", "content": "读盘"}, {"role": "user", "content": "查典籍"}]
TOOLS = [{"type": "function", "function": {"name": "search_classics", "description": "检索",
          "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": []}}}]
REASONING = {"type": "reasoning", "id": "rs_1", "summary": [], "encrypted_content": "opaque-test-state"}
CALL = {"type": "function_call", "id": "fc_1", "call_id": "call_1", "name": "search_classics",
        "arguments": '{"query":"紫微"}', "status": "completed"}
MESSAGE = {"type": "message", "id": "msg_1", "role": "assistant", "status": "completed",
           "content": [{"type": "output_text", "text": "找到依据", "annotations": []}]}


def sse(*events):
    return "".join("data:" + json.dumps(e, ensure_ascii=False) + "\n\n" for e in events).encode()


def complete(items):
    return {"type": "response.completed", "response": {"status": "completed", "output": items}}


def collect(gen):
    async def run():
        return [e async for e in gen]
    return asyncio.run(run())


def mock_client(monkeypatch, handler):
    seen = []
    def fake(provider, timeout=120):
        assert provider == "openai"
        def send(request):
            seen.append((str(request.url), json.loads(request.content)))
            return handler(len(seen), request)
        return httpx.AsyncClient(transport=httpx.MockTransport(send))
    monkeypatch.setattr(ls, "_client", fake)
    return seen


def stream(messages=None, model="gpt-6.1-sol", base="https://unit.test/v1", tools=TOOLS):
    return ls.llm_service.stream_chat(messages or MESSAGES, model, provider="openai",
                                     openai_api_key="fake", openai_base_url=base, tools=tools,
                                     options=ChatOptions(thinking="high", max_tokens=12000))


@pytest.mark.parametrize("base", ["https://unit.test", "https://unit.test/v1/",
                                  "https://unit.test/v1/chat/completions", "https://unit.test/v1/responses"])
def test_new_model_uses_responses_and_preserves_optional_schema(monkeypatch, base):
    before = copy.deepcopy(TOOLS)
    seen = mock_client(monkeypatch, lambda *_: httpx.Response(200, content=sse(complete([MESSAGE]))))
    events = collect(stream(base=base))
    url, body = seen[0]
    assert url == "https://unit.test/v1/responses"
    assert body["reasoning"] == {"effort": "high"}
    assert body["max_output_tokens"] == 12000 and body["store"] is False
    assert body["input"] == MESSAGES
    assert body["tools"][0]["strict"] is False and "function" not in body["tools"][0]
    assert body["tools"][0]["parameters"]["required"] == [] and TOOLS == before
    assert events == [{"type": "token", "content": "找到依据"}]


def test_full_reasoning_tool_result_round_trip(monkeypatch):
    call2 = {**CALL, "id": "fc_2", "call_id": "call_2", "arguments": '{"query":"天府"}'}
    output = [REASONING, MESSAGE, CALL, call2]
    first = sse(
        {"type": "response.reasoning_summary_text.delta", "delta": "先检索"},
        {"type": "response.output_text.delta", "output_index": 1, "content_index": 0, "delta": "找到"},
        {"type": "response.output_text.delta", "output_index": 1, "content_index": 0, "delta": "依据"},
        {"type": "response.output_item.done", "output_index": 0, "item": REASONING},
        {"type": "response.function_call_arguments.delta", "output_index": 2, "delta": '{"query":'},
        {"type": "response.output_item.done", "output_index": 2, "item": CALL}, complete(output))
    seen = mock_client(monkeypatch, lambda n, _: httpx.Response(200, content=first if n == 1 else sse(complete([MESSAGE]))))
    events = collect(stream())
    tool = next(e for e in events if e["type"] == "tool_calls")
    assert tool["response_items"] == output and len(tool["calls"]) == 2
    assert "".join(e["content"] for e in events if e["type"] == "token") == "找到依据"
    msgs = MESSAGES + [{"role": "assistant", "content": "找到依据", "tool_calls": tool["calls"],
                       "response_items": tool["response_items"]},
                      {"role": "tool", "tool_call_id": "call_1", "content": "条文一"},
                      {"role": "tool", "tool_call_id": "call_2", "content": "条文二"}]
    # Even if no new tools are supplied, follow-up stays on Responses.
    collect(stream(messages=msgs, tools=None))
    assert seen[1][0].endswith("/responses")
    assert seen[1][1]["input"] == MESSAGES + output + [
        {"type": "function_call_output", "call_id": "call_1", "output": "条文一"},
        {"type": "function_call_output", "call_id": "call_2", "output": "条文二"}]


def test_explicit_endpoint_error_switches_unknown_alias(monkeypatch):
    def handler(n, request):
        if n == 1:
            return httpx.Response(400, json={"error": {"message": "Function tools with reasoning_effort are not supported in /v1/chat/completions. Use /v1/responses or set reasoning_effort to 'none'."}})
        return httpx.Response(200, content=sse(complete([REASONING, CALL])))
    seen = mock_client(monkeypatch, handler)
    events = collect(stream(model="gateway-alias"))
    assert [url.rsplit("/v1/", 1)[1] for url, _ in seen] == ["chat/completions", "responses"]
    assert seen[1][1]["reasoning"]["effort"] == "high"
    assert events[-1]["type"] == "tool_calls"
    # Metadata keeps alias tool follow-ups on Responses as well.
    assert wire.prefers_responses("gateway-alias", [{"response_items": [REASONING, CALL]}], TOOLS)


@pytest.mark.parametrize("status,error", [(401, "invalid key"), (429, "quota"), (500, "server error"),
                                        (400, "invalid function schema"), (404, "model missing")])
def test_unrelated_errors_are_not_retried(monkeypatch, status, error):
    seen = mock_client(monkeypatch, lambda *_: httpx.Response(status, json={"error": error}))
    events = collect(stream(model="gpt-5.5"))
    assert len(seen) == 1 and "[错误]" in events[-1]["content"]


def test_old_models_keep_chat_completions(monkeypatch):
    seen = mock_client(monkeypatch, lambda *_: httpx.Response(200, content=b'data: {"choices":[{"delta":{"content":"ok"}}]}\n\ndata: [DONE]\n\n'))
    assert collect(stream(model="gpt-4o"))[-1]["content"] == "ok"
    assert seen[0][0].endswith("/chat/completions") and seen[0][1]["tools"] == TOOLS


@pytest.mark.parametrize("ending", [None, {"type": "error", "message": "upstream failed"},
    {"type": "response.failed", "response": {"error": {"message": "failed"}}},
    {"type": "response.incomplete", "response": {"incomplete_details": {"reason": "max_output_tokens"}}}])
def test_failed_or_truncated_stream_never_executes_tools(monkeypatch, ending):
    events = [{"type": "response.output_text.delta", "delta": "先查一下"},
              {"type": "response.output_item.done", "output_index": 1, "item": CALL}]
    if ending:
        events.append(ending)
    seen = mock_client(monkeypatch, lambda *_: httpx.Response(200, content=sse(*events)))
    result = collect(stream())
    assert result[-1]["type"] == "error" and not any(e["type"] == "tool_calls" for e in result)
    assert len(seen) == 1


def test_responses_missing_endpoint_does_not_disable_tools_or_reasoning(monkeypatch):
    seen = mock_client(monkeypatch, lambda *_: httpx.Response(404, text="Not found"))
    result = collect(stream())
    assert len(seen) == 1 and result[-1]["type"] == "error"
    assert "Endpoint" in result[-1]["message"]


def test_malformed_arguments_not_executed(monkeypatch):
    mock_client(monkeypatch, lambda *_: httpx.Response(200, content=sse(complete([{**CALL, "arguments": '{"query":'}]))))
    result = collect(stream())
    assert result[-1]["type"] == "error" and not any(e["type"] == "tool_calls" for e in result)


def test_convert_legacy_chat_tool_history():
    msgs = MESSAGES + [{"role": "assistant", "content": "查一下", "reasoning_content": "private",
                       "tool_calls": [{"id": "call_1", "function": {"name": "search_classics", "arguments": "{}"}}]},
                      {"role": "tool", "tool_call_id": "call_1", "content": "结果"}]
    assert wire.to_input(msgs)[-3:] == [
        {"role": "assistant", "content": "查一下"},
        {"type": "function_call", "call_id": "call_1", "name": "search_classics", "arguments": "{}"},
        {"type": "function_call_output", "call_id": "call_1", "output": "结果"}]


def test_stream_done_preserves_encrypted_reasoning_when_terminal_snapshot_omits_it(monkeypatch):
    final_reasoning = {k: v for k, v in REASONING.items() if k != "encrypted_content"}
    mock_client(monkeypatch, lambda *_: httpx.Response(200, content=sse(
        {"type": "response.output_item.done", "output_index": 0, "item": REASONING},
        complete([final_reasoning, CALL]))))
    events = collect(stream())
    assert events[-1]["response_items"][0] == REASONING
