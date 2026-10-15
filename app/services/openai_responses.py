"""Stateless Responses adapter for the existing chat/tool loop.

Only completed responses may release tool calls. Preserve output items (including
encrypted reasoning) verbatim between tool rounds; never send them to the browser.
"""
from __future__ import annotations

import json


def api_url(base: str, endpoint: str) -> str:
    base = base.rstrip("/")
    for suffix in ("/chat/completions", "/responses"):
        if base.endswith(suffix):
            base = base[:-len(suffix)]
            break
    return base + ("/" if base.endswith("/v1") else "/v1/") + endpoint


def prefers_responses(model: str, messages: list[dict], tools) -> bool:
    # New GPT families require Responses for function calling. Old/custom models
    # stay on Chat Completions unless their API explicitly asks for Responses.
    return any(m.get("response_items") for m in messages) or bool(
        tools and model.lower().startswith(("gpt-6-", "gpt-6.")))


def requires_responses(status: int, error: str) -> bool:
    text = error.lower()
    return status in (400, 404, 422) and "responses" in text and any(
        term in text for term in ("tool", "chat/completions", "chat completions"))


def rejects_reasoning_parameter(status: int, error: str) -> bool:
    text = error.lower()
    return status in (400, 422) and "reasoning_effort" in text and any(
        term in text for term in ("unsupported", "not supported", "unknown", "unrecognized"))


def to_input(messages: list[dict]) -> list[dict]:
    items = []
    for m in messages:
        role = m.get("role")
        if role == "assistant" and m.get("response_items"):
            items.extend(m["response_items"])
            continue  # These already contain the text and function calls.
        if role == "tool":
            items.append({"type": "function_call_output", "call_id": m["tool_call_id"],
                          "output": m.get("content") or ""})
            continue
        if role in ("system", "developer", "user", "assistant") and m.get("content"):
            items.append({"role": role, "content": m["content"]})
        if role == "assistant":
            for call in m.get("tool_calls") or []:
                fn = call["function"]
                items.append({"type": "function_call", "call_id": call["id"],
                              "name": fn["name"], "arguments": fn.get("arguments") or "{}"})
    return items


def payload(messages, model, tools, options) -> dict:
    body = {"model": model, "input": to_input(messages), "stream": True, "store": False,
            "include": ["reasoning.encrypted_content"]}
    if tools:
        # Chat schemas contain optional fields; don't implicitly make them required.
        body["tools"] = [{"type": "function", **t["function"],
                          "strict": t["function"].get("strict", False)} for t in tools]
    if options:
        if options.thinking in ("none", "minimal", "low", "medium", "high", "xhigh", "max"):
            body["reasoning"] = {"effort": options.thinking}
        if options.max_tokens:
            body["max_output_tokens"] = options.max_tokens
    return body


async def _events(response):
    lines = []
    async for line in response.aiter_lines():
        if line.startswith("data:"):
            lines.append(line[5:].lstrip())
        elif not line and lines:
            raw, lines = "\n".join(lines), []
            if raw != "[DONE]":
                yield json.loads(raw)
    if lines and "\n".join(lines) != "[DONE]":
        yield json.loads("\n".join(lines))


def _error(message):
    return {"type": "error", "message": f"[错误] OpenAI Responses: {message}"}


async def stream_events(response):
    completed_items = {}
    emitted_parts = set()
    async for event in _events(response):
        kind = event.get("type")
        part = (event.get("output_index", 0), event.get("content_index", 0))
        if kind in ("response.output_text.delta", "response.refusal.delta"):
            if event.get("delta"):
                emitted_parts.add(part)
                yield {"type": "token", "content": event["delta"]}
        elif kind == "response.reasoning_summary_text.delta":
            yield {"type": "thinking", "content": event.get("delta", "")}
        elif kind == "response.output_item.done":
            completed_items[event["output_index"]] = event["item"]
        elif kind in ("error", "response.failed", "response.incomplete"):
            detail = (event.get("response") or {}).get("error") or event.get("error")
            if not detail:
                detail = event.get("message") or (event.get("response") or {}).get("incomplete_details") or kind
            yield _error(json.dumps(detail, ensure_ascii=False) if isinstance(detail, dict) else str(detail))
            return
        elif kind == "response.completed":
            result = event.get("response") or {}
            if result.get("status", "completed") != "completed":
                yield _error(f"回复未完成：{result.get('status')}")
                return
            items = result.get("output")
            if items is None:
                items = [completed_items[i] for i in sorted(completed_items)]
            calls = []
            for i, item in enumerate(items):
                # Some compatible gateways omit encrypted state from the terminal
                # snapshot but deliver it on output_item.done (the streaming source).
                done = completed_items.get(i, {})
                if (item.get("type") == "reasoning" and not item.get("encrypted_content")
                        and done.get("id") == item.get("id") and done.get("encrypted_content")):
                    item = items[i] = done
                if item.get("type") == "message":
                    for j, content in enumerate(item.get("content") or []):
                        text = content.get("text") or content.get("refusal")
                        if text and (i, j) not in emitted_parts:
                            yield {"type": "token", "content": text}
                elif item.get("type") == "function_call":
                    if not item.get("call_id") or not item.get("name"):
                        yield _error("工具调用缺少 call_id 或 name")
                        return
                    # Never let a truncated/malformed argument string execute as {}.
                    try:
                        args = json.loads(item.get("arguments") or "")
                        if not isinstance(args, dict):
                            raise ValueError("arguments must be an object")
                    except (ValueError, TypeError):
                        yield _error("工具参数不完整，未执行工具")
                        return
                    calls.append({"id": item["call_id"], "type": "function",
                                  "function": {"name": item["name"], "arguments": item["arguments"]}})
            if calls:
                yield {"type": "tool_calls", "calls": calls, "response_items": items}
            return
    yield _error("连接在回复完成前中断，未执行未完成的工具调用，请重试")
