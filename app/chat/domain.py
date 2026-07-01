from uuid import UUID, uuid4
from datetime import datetime, timezone
from typing import Literal, Optional
from pydantic import BaseModel, Field

class ChatMessage(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    chat_id: UUID
    role: Literal["user", "assistant", "system"]
    content: str
    tokens: Optional[int] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class Chat(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    owner_external_id: str  # Telegram chat_id, email, ID устройства
    interface: Literal["telegram", "web", "cli"]
    system_prompt: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))