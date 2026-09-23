from typing import Optional, Protocol
from uuid import UUID

from app.chat.domain import Chat, ChatMessage, MessageFeedback


class ChatRepository(Protocol):
    async def create_chat(
        self,
        owner_external_id: str,
        interface: str,
        system_prompt: Optional[str] = None,
    ) -> Chat: ...

    async def get_chat(self, chat_id: UUID) -> Optional[Chat]: ...

    async def get_or_create_chat(
        self,
        owner_external_id: str,
        interface: str,
        system_prompt: Optional[str] = None,
    ) -> Chat: ...

    async def append_message(self, chat_id: UUID, message: ChatMessage) -> ChatMessage: ...

    async def list_messages(self, chat_id: UUID, limit: int = 50) -> list[ChatMessage]: ...

    async def soft_delete_messages(self, chat_id: UUID) -> None: ...

    async def save_feedback(self, feedback: MessageFeedback) -> MessageFeedback: ...

    async def list_owner_ids(self, interface: str) -> list[str]: ...

    async def admin_stats(self) -> dict: ...

    async def list_recent_users(self, limit: int = 50) -> list[dict]: ...
