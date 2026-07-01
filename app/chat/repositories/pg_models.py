from sqlalchemy import Column, String, DateTime, ForeignKey, Integer, Index, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import declarative_base, Mapped, mapped_column
from datetime import datetime, timezone
from uuid import UUID as PyUUID, uuid4

Base = declarative_base()

class ChatRow(Base):
    __tablename__ = "chats"
    id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    owner_external_id: Mapped[str] = mapped_column(String, nullable=False)
    interface: Mapped[str] = mapped_column(String, nullable=False)
    system_prompt: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))

class ChatMessageRow(Base):
    __tablename__ = "chat_messages"
    id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    chat_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), ForeignKey("chats.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(String, nullable=False)
    tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_chat_messages_chat_created", "chat_id", "created_at", postgresql_where=text("deleted_at IS NULL")),
    )