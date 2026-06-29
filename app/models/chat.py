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
    role: Literal["user", "assistant", "system"]
    content: str
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    # Optional context from chart interaction
    context: Optional[dict] = None


class Session(BaseModel):
    """A chat session."""
    id: str = Field(default_factory=gen_id)
    title: str = "新对话"
    mode: Literal["theory", "chart_ziwei", "chart_shishen"] = "theory"
    person: Optional[str] = None  # person identifier for chart reading
    model: str = ""
    provider: str = "ollama"
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
    mode: Literal["theory", "chart_ziwei", "chart_shishen"] = "theory"
    person: Optional[str] = None
    model: str = ""
    provider: str = "ollama"


class SendMessageRequest(BaseModel):
    """Request to send a message."""
    content: str
    mode: Optional[str] = None
    person: Optional[str] = None
    selected_context: Optional[dict] = None
