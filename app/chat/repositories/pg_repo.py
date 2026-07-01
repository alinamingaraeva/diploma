from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from typing import Optional, List
from app.chat.domain import Chat, ChatMessage
from app.chat.repository import ChatRepository
from app.chat.repositories.pg_models import ChatRow, ChatMessageRow

class PostgresChatRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_chat(self, owner_external_id: str, interface: str, system_prompt: Optional[str] = None) -> Chat:
        chat = Chat(owner_external_id=owner_external_id, interface=interface, system_prompt=system_prompt)
        row = ChatRow(
            id=chat.id,
            owner_external_id=chat.owner_external_id,
            interface=chat.interface,
            system_prompt=chat.system_prompt,
        )
        self.session.add(row)
        await self.session.commit()
        return chat

    async def get_chat(self, chat_id: UUID) -> Optional[Chat]:
        result = await self.session.execute(
            select(ChatRow).where(ChatRow.id == chat_id)
        )
        row = result.scalar_one_or_none()
        if not row:
            return None
        return Chat.model_validate(row, from_attributes=True)

    async def append_message(self, chat_id: UUID, message: ChatMessage) -> ChatMessage:
        row = ChatMessageRow(
            id=message.id,
            chat_id=chat_id,
            role=message.role,
            content=message.content,
            tokens=message.tokens,
        )
        self.session.add(row)
        await self.session.commit()
        return message

    async def list_messages(self, chat_id: UUID, limit: int = 50) -> List[ChatMessage]:
        result = await self.session.execute(
            select(ChatMessageRow)
            .where(ChatMessageRow.chat_id == chat_id, ChatMessageRow.deleted_at.is_(None))
            .order_by(ChatMessageRow.created_at.desc())
            .limit(limit)
        )
        rows = result.scalars().all()
        # Возвращаем в хронологическом порядке (от старых к новым)
        rows.reverse()
        return [ChatMessage.model_validate(row, from_attributes=True) for row in rows]

    async def soft_delete_messages(self, chat_id: UUID) -> None:
        await self.session.execute(
            update(ChatMessageRow)
            .where(ChatMessageRow.chat_id == chat_id, ChatMessageRow.deleted_at.is_(None))
            .values(deleted_at=func.now())
        )
        await self.session.commit()