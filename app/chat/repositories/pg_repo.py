from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.chat.domain import Chat, ChatMessage, MessageFeedback
from app.chat.repositories.pg_models import ChatMessageRow, ChatRow, MessageFeedbackRow


class PostgresChatRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_chat(
        self,
        owner_external_id: str,
        interface: str,
        system_prompt: Optional[str] = None,
    ) -> Chat:
        chat = Chat(
            owner_external_id=owner_external_id,
            interface=interface,  # type: ignore[arg-type]
            system_prompt=system_prompt,
        )
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
        result = await self.session.execute(select(ChatRow).where(ChatRow.id == chat_id))
        row = result.scalar_one_or_none()
        if not row:
            return None
        return Chat.model_validate(row, from_attributes=True)

    async def get_or_create_chat(
        self,
        owner_external_id: str,
        interface: str,
        system_prompt: Optional[str] = None,
    ) -> Chat:
        result = await self.session.execute(
            select(ChatRow)
            .where(ChatRow.owner_external_id == owner_external_id, ChatRow.interface == interface)
            .order_by(ChatRow.created_at.desc())
            .limit(1)
        )
        row = result.scalar_one_or_none()
        if row:
            return Chat.model_validate(row, from_attributes=True)
        return await self.create_chat(owner_external_id, interface, system_prompt)

    async def append_message(self, chat_id: UUID, message: ChatMessage) -> ChatMessage:
        row = ChatMessageRow(
            id=message.id,
            chat_id=chat_id,
            role=message.role,
            content=message.content,
            tokens=message.tokens,
            media_refs=message.media_refs,
        )
        self.session.add(row)
        await self.session.commit()
        return message

    async def list_messages(self, chat_id: UUID, limit: int = 50) -> list[ChatMessage]:
        result = await self.session.execute(
            select(ChatMessageRow)
            .where(ChatMessageRow.chat_id == chat_id, ChatMessageRow.deleted_at.is_(None))
            .order_by(ChatMessageRow.created_at.desc())
            .limit(limit)
        )
        rows = list(result.scalars().all())
        rows.reverse()
        return [ChatMessage.model_validate(row, from_attributes=True) for row in rows]

    async def soft_delete_messages(self, chat_id: UUID) -> None:
        await self.session.execute(
            update(ChatMessageRow)
            .where(ChatMessageRow.chat_id == chat_id, ChatMessageRow.deleted_at.is_(None))
            .values(deleted_at=func.now())
        )
        await self.session.commit()

    async def save_feedback(self, feedback: MessageFeedback) -> MessageFeedback:
        stmt = (
            insert(MessageFeedbackRow)
            .values(
                id=feedback.id,
                message_id=feedback.message_id,
                owner_external_id=feedback.owner_external_id,
                value=feedback.value,
            )
            .on_conflict_do_update(
                constraint="uq_feedback_owner_message",
                set_={"value": feedback.value, "created_at": func.now()},
            )
        )
        await self.session.execute(stmt)
        await self.session.commit()
        return feedback

    async def list_owner_ids(self, interface: str) -> list[str]:
        result = await self.session.execute(
            select(ChatRow.owner_external_id).where(ChatRow.interface == interface).distinct()
        )
        return [row[0] for row in result.all()]

    async def admin_stats(self) -> dict:
        since = datetime.now(timezone.utc) - timedelta(hours=24)
        total_q = await self.session.execute(
            select(func.count()).select_from(ChatMessageRow).where(ChatMessageRow.created_at >= since)
        )
        users_q = await self.session.execute(
            select(func.count(func.distinct(ChatRow.owner_external_id))).where(ChatRow.created_at >= since)
        )
        fb_q = await self.session.execute(select(MessageFeedbackRow.value))
        values = [row[0] for row in fb_q.all()]
        up = values.count("up")
        total_fb = len(values)
        return {
            "total_messages": int(total_q.scalar() or 0),
            "active_users": int(users_q.scalar() or 0),
            "avg_latency_ms": 0,
            "moderation_block_rate": 0.0,
            "feedback_up_ratio": (up / total_fb) if total_fb else 0.0,
        }

    async def list_recent_users(self, limit: int = 50) -> list[dict]:
        result = await self.session.execute(
            select(
                ChatRow.owner_external_id,
                func.count(ChatRow.id).label("chats"),
                func.max(ChatRow.created_at).label("last_seen_at"),
            )
            .group_by(ChatRow.owner_external_id)
            .order_by(func.max(ChatRow.created_at).desc())
            .limit(limit)
        )
        rows = []
        for owner, chats, last_seen in result.all():
            rows.append(
                {
                    "owner_external_id": owner,
                    "chats": int(chats),
                    "last_seen_at": last_seen.isoformat() if last_seen else None,
                }
            )
        return rows
