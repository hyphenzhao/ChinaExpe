"""Chat API routes with SSE streaming."""
import json
from pathlib import Path
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from ..models.chat import (
    Session, SessionListItem, CreateSessionRequest,
    SendMessageRequest, Message, gen_id,
)
from ..models.config import ApiConfig
from ..services.llm_service import llm_service
from ..services.agent_service import agent_service
from ..services.tools import TOOLS, execute_tool

router = APIRouter(prefix="/api/chats", tags=["chats"])

_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
SESSIONS_DIR = _DATA_DIR / "sessions"
CONFIG_FILE = _DATA_DIR / "config.json"


def _load_config() -> ApiConfig:
    if CONFIG_FILE.exists():
        try:
            return ApiConfig(**json.loads(CONFIG_FILE.read_text(encoding="utf-8")))
        except Exception:
            pass
    return ApiConfig()


def _session_path(session_id: str) -> Path:
    return SESSIONS_DIR / f"{session_id}.json"


def _load_session(session_id: str) -> Optional[Session]:
    path = _session_path(session_id)
    if path.exists():
        try:
            return Session(**json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            pass
    return None


def _save_session(session: Session):
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    session.updated_at = datetime.now().isoformat()
    _session_path(session.id).write_text(
        session.model_dump_json(indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


@router.get("")
async def list_sessions() -> list[SessionListItem]:
    """List all chat sessions."""
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    sessions = []
    for f in sorted(SESSIONS_DIR.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            sessions.append(SessionListItem(
                id=data.get("id", f.stem),
                title=data.get("title", "未命名"),
                mode=data.get("mode", "theory"),
                person=data.get("person"),
                updated_at=data.get("updated_at", ""),
                message_count=len(data.get("messages", [])),
            ))
        except Exception:
            pass
    return sessions


@router.post("")
async def create_session(req: CreateSessionRequest) -> Session:
    """Create a new chat session."""
    config = _load_config()
    session = Session(
        title=req.title,
        mode=req.mode,
        person=req.person,
        model=req.model or config.default_model,
        provider=req.provider or config.provider,
    )
    _save_session(session)
    return session


@router.get("/{session_id}")
async def get_session(session_id: str) -> Session:
    """Get a session by ID."""
    session = _load_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话未找到")
    return session


@router.put("/{session_id}")
async def update_session(session_id: str, updates: dict) -> Session:
    """Update session metadata."""
    session = _load_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话未找到")

    for key in ["title", "mode", "person", "model", "provider"]:
        if key in updates:
            setattr(session, key, updates[key])

    _save_session(session)
    return session


@router.delete("/{session_id}")
async def delete_session(session_id: str):
    """Delete a session."""
    path = _session_path(session_id)
    if path.exists():
        path.unlink()
    return {"success": True}


@router.post("/{session_id}/messages")
async def send_message(session_id: str, req: SendMessageRequest, request: Request):
    """Send a message and stream the AI response via SSE."""
    session = _load_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话未找到")

    config = _load_config()

    # Update mode/person if changed
    if req.mode and req.mode != session.mode:
        session.mode = req.mode
    if req.person and req.person != session.person:
        session.person = req.person

    # Add user message and save immediately (so it's not lost if LLM fails)
    user_msg = Message(
        role="user",
        content=req.content,
        context=req.selected_context,
    )
    session.messages.append(user_msg)
    _save_session(session)

    # Prepare history for the agent
    history = [
        {"role": m.role, "content": m.content}
        for m in session.messages[:-1]  # exclude the just-added user message
    ]

    # Build messages with agent context
    messages, meta = await agent_service.build_messages(
        user_message=req.content,
        mode=req.mode or session.mode,
        person=req.person or session.person,
        selected_context=req.selected_context,
        history=history,
        view_context=req.view_context,
    )

    def _sse_event(event: str, data: dict) -> str:
        return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

    # Determine if model supports tool calling (deepseek-reasoner does not)
    model_name = session.model or config.default_model
    supports_tools = "reasoner" not in model_name.lower()

    async def event_generator():
        full_response = ""
        saved = False
        current_messages = list(messages)  # mutable copy for tool loop
        iteration = 0
        MAX_ITERATIONS = 5

        try:
            while iteration < MAX_ITERATIONS:
                iteration += 1
                turn_text = ""

                # Stream with tools (if supported)
                stream_tools = TOOLS if supports_tools else None
                async for event in llm_service.stream_chat(
                    messages=current_messages,
                    model=model_name,
                    provider=session.provider or config.provider,
                    ollama_host=config.ollama_host,
                    ollama_port=config.ollama_port,
                    deepseek_api_key=config.deepseek_api_key,
                    deepseek_base_url=config.deepseek_base_url,
                    tools=stream_tools,
                ):
                    if event["type"] == "token":
                        token = event["content"]
                        full_response += token
                        turn_text += token
                        # Error detection on first token
                        if (
                            full_response.startswith("[错误]")
                            and len(full_response) == len(token)
                        ):
                            raise Exception(full_response)
                        yield _sse_event(
                            "token", {"type": "token", "content": token}
                        )

                    elif event["type"] == "tool_calls":
                        # Save any text before tool calls
                        if turn_text.strip():
                            assistant_turn = Message(
                                role="assistant", content=turn_text
                            )
                            session.messages.append(assistant_turn)

                        tool_calls_data = event["calls"]
                        # One assistant message carrying the text, the tool calls and
                        # (DeepSeek thinking mode) the reasoning, which the API
                        # requires to be passed back within the same turn.
                        call_msg = {"role": "assistant", "tool_calls": tool_calls_data}
                        if turn_text:
                            call_msg["content"] = turn_text
                        if event.get("reasoning_content"):
                            call_msg["reasoning_content"] = event["reasoning_content"]
                        current_messages.append(call_msg)
                        turn_text = ""

                        # Execute each tool
                        for tc in tool_calls_data:
                            func = tc.get("function", {})
                            name = func.get("name", "?")
                            try:
                                args = json.loads(func.get("arguments", "{}"))
                            except json.JSONDecodeError:
                                args = {}

                            yield _sse_event(
                                "tool_start",
                                {
                                    "type": "tool_start",
                                    "tool": name,
                                    "query": args.get("query", ""),
                                    "args": args,
                                },
                            )

                            result = await execute_tool(name, args)
                            tool_content = result.get(
                                "content", result.get("error", "")
                            )

                            yield _sse_event(
                                "tool_result",
                                {
                                    "type": "tool_result",
                                    "tool": name,
                                    "summary": tool_content[:200] + "..."
                                    if len(tool_content) > 200
                                    else tool_content,
                                    "meta": result.get("meta") or {},
                                    "error": result.get("error"),
                                },
                            )

                            # Append tool result to conversation
                            current_messages.append(
                                {
                                    "role": "tool",
                                    "tool_call_id": tc.get("id", ""),
                                    "content": tool_content,
                                }
                            )

                            # Also save to session
                            tool_msg = Message(
                                role="tool",
                                content=tool_content[:500],
                                tool_call_id=tc.get("id", ""),
                                name=name,
                            )
                            session.messages.append(tool_msg)

                        # Hint to wrap up after 3 rounds
                        if iteration >= 3:
                            current_messages.append(
                                {
                                    "role": "user",
                                    "content": "你已经调用了多轮工具，请基于已有信息直接给出最终回复，不要再调用工具。",
                                }
                            )

                        break  # exit inner loop, continue outer loop

                else:
                    # No tool_calls — this is the final text response
                    # Save assistant message
                    assistant_msg = Message(
                        role="assistant", content=full_response
                    )
                    session.messages.append(assistant_msg)

                    if (
                        len(session.messages) <= 3
                        and session.title == "新对话"
                    ):
                        session.title = req.content[:30] + (
                            "..." if len(req.content) > 30 else ""
                        )

                    _save_session(session)
                    saved = True

                    yield _sse_event(
                        "done",
                        {
                            "type": "done",
                            "message_id": assistant_msg.id,
                            "session_title": session.title,
                            "meta": meta,
                        },
                    )
                    return

            # Max iterations reached
            if full_response:
                assistant_msg = Message(role="assistant", content=full_response)
                session.messages.append(assistant_msg)
                _save_session(session)
                saved = True
                yield _sse_event(
                    "done",
                    {
                        "type": "done",
                        "message_id": assistant_msg.id,
                        "session_title": session.title,
                        "meta": meta,
                    },
                )
            else:
                raise Exception("达到最大推理轮次，请重试")

        except Exception as e:
            if full_response and not saved:
                partial_msg = Message(
                    role="assistant",
                    content=full_response + "\n\n⚠️ 回复中断",
                )
                session.messages.append(partial_msg)
                _save_session(session)
                saved = True
            yield _sse_event("error", {"type": "error", "message": str(e)})

        finally:
            if full_response and not saved:
                try:
                    partial_msg = Message(
                        role="assistant",
                        content=full_response + "\n\n⚠️ 回复中断",
                    )
                    session.messages.append(partial_msg)
                    _save_session(session)
                except Exception:
                    pass

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
