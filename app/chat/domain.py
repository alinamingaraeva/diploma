from datetime import datetime, timezone
from typing import Any, Literal, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    chat_id: UUID
    role: Literal["user", "assistant", "system"]
    content: str
    tokens: Optional[int] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    media_refs: Optional[dict[str, Any]] = None


class Chat(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    owner_external_id: str
    interface: Literal["telegram", "web", "cli"]
    system_prompt: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class MessageFeedback(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    message_id: UUID
    owner_external_id: str
    value: Literal["up", "down"]
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
