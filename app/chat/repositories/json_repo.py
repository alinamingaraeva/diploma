import json
import aiofiles
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID
from typing import Optional, List, Dict, Any
from app.chat.domain import Chat, ChatMessage
from app.chat.repository import ChatRepository

class JsonChatRepository:
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir

    def _chat_dir(self, chat_id: UUID) -> Path:
        return self.base_dir / "chats" / str(chat_id)

    def _chat_meta_path(self, chat_id: UUID) -> Path:
        return self._chat_dir(chat_id) / "chat.json"

    def _messages_path(self, chat_id: UUID) -> Path:
        return self._chat_dir(chat_id) / "messages.jsonl"

    async def create_chat(self, owner_external_id: str, interface: str, system_prompt: Optional[str] = None) -> Chat:
        chat = Chat(owner_external_id=owner_external_id, interface=interface, system_prompt=system_prompt)
        chat_dir = self._chat_dir(chat.id)
        os.makedirs(chat_dir, exist_ok=True)
        async with aiofiles.open(self._chat_meta_path(chat.id), "w") as f:
            await f.write(chat.model_dump_json())
        return chat

    async def get_chat(self, chat_id: UUID) -> Optional[Chat]:
        meta_path = self._chat_meta_path(chat_id)
        if not meta_path.exists():
            return None
        async with aiofiles.open(meta_path, "r") as f:
            data = await f.read()
        return Chat.model_validate_json(data)

    async def append_message(self, chat_id: UUID, message: ChatMessage) -> ChatMessage:
        messages_path = self._messages_path(chat_id)
        os.makedirs(messages_path.parent, exist_ok=True)
        async with aiofiles.open(messages_path, "a") as f:
            await f.write(message.model_dump_json() + "\n")
        return message

    async def list_messages(self, chat_id: UUID, limit: int = 50) -> List[ChatMessage]:
        messages_path = self._messages_path(chat_id)
        if not messages_path.exists():
            return []
        # Читаем все строки
        async with aiofiles.open(messages_path, "r") as f:
            lines = await f.readlines()
        # Парсим и фильтруем soft-delete
        messages = []
        soft_deleted = False
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                if data.get("type") == "soft_delete":
                    soft_deleted = True
                    messages = []
                    continue
                if soft_deleted:
                    continue
                msg = ChatMessage.model_validate(data)
                messages.append(msg)
            except Exception:
                continue
        # Возвращаем последние N в хронологическом порядке
        messages = messages[:limit]
        messages.reverse()
        return messages

    async def soft_delete_messages(self, chat_id: UUID) -> None:
        messages_path = self._messages_path(chat_id)
        if not messages_path.exists():
            return
        # Дописываем маркер soft-delete
        async with aiofiles.open(messages_path, "a") as f:
            await f.write(json.dumps({"type": "soft_delete", "at": datetime.now(timezone.utc).isoformat()}) + "\n")