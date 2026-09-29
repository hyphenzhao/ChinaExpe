"""Chat session and message models."""
from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime
import uuid


def gen_id() -> str:
    return uuid.uuid4().hex[:12]


class Message(BaseModel):
    """A single chat message."""
    id: str = Field(default_factory=gen_id)
    role: Literal["user", "assistant", "system", "tool"] = "user"
    content: str = ""
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    # Optional context from chart interaction
    context: Optional[dict] = None
    # Tool calling support
    tool_calls: Optional[list[dict]] = None       # assistant messages with tool calls
    tool_call_id: Optional[str] = None            # tool result messages
    name: Optional[str] = None                    # tool name for tool result messages
    reasoning: Optional[str] = None               # 思考过程（截断保存；老会话没有这个字段）


class Session(BaseModel):
    """A chat session."""
    id: str = Field(default_factory=gen_id)
    title: str = "新对话"
    mode: Literal["theory", "chart", "chart_ziwei", "chart_shishen"] = "theory"
    person: Optional[str] = None  # person identifier for chart reading
    model: str = ""
    provider: str = "ollama"
    thinking: str = ""                 # "" = 用模型自己的默认档
    messages: list[Message] = []
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())


class SessionListItem(BaseModel):
    """Summary of a session for the sidebar list."""
    id: str
    title: str
    mode: str
    person: Optional[str] = None
    updated_at: str
    message_count: int


class CreateSessionRequest(BaseModel):
    """Request to create a new session."""
    title: str = "新对话"
    mode: Literal["theory", "chart", "chart_ziwei", "chart_shishen"] = "theory"
    person: Optional[str] = None
    model: str = ""
    provider: str = ""                 # 空 = 回退到全局默认（原来是 "ollama"，会把会话钉死）
    thinking: str = ""


class SendMessageRequest(BaseModel):
    """Request to send a message."""
    content: str
    mode: Optional[str] = None
    person: Optional[str] = None
    selected_context: Optional[dict] = None
    view_context: Optional[dict] = None   # {chart, layer, level, date, selected_palace}
    model: Optional[str] = None           # 本次选择，同时粘到会话上
    provider: Optional[str] = None
    thinking: Optional[str] = None
    # 预置分析动作：服务端把代码计算结果附在消息后交给 AI
    # {"type": "ziwei_geju"} | {"type": "bazi_geju"} | {"type": "life_event", "event": "结婚"} | {"type": "rectify", ...}
    action: Optional[dict] = None
