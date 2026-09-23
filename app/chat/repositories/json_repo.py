import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from uuid import UUID

import aiofiles

from app.chat.domain import Chat, ChatMessage, MessageFeedback


class JsonChatRepository:
    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir)

    def _chat_dir(self, chat_id: UUID) -> Path:
        return self.base_dir / "chats" / str(chat_id)

    def _chat_meta_path(self, chat_id: UUID) -> Path:
        return self._chat_dir(chat_id) / "chat.json"

    def _messages_path(self, chat_id: UUID) -> Path:
        return self._chat_dir(chat_id) / "messages.jsonl"

    def _feedback_path(self) -> Path:
        return self.base_dir / "feedbacks.jsonl"

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
        chat_dir = self._chat_dir(chat.id)
        os.makedirs(chat_dir, exist_ok=True)
        async with aiofiles.open(self._chat_meta_path(chat.id), "w", encoding="utf-8") as f:
            await f.write(chat.model_dump_json())
        return chat

    async def get_chat(self, chat_id: UUID) -> Optional[Chat]:
        meta_path = self._chat_meta_path(chat_id)
        if not meta_path.exists():
            return None
        async with aiofiles.open(meta_path, "r", encoding="utf-8") as f:
            data = await f.read()
        return Chat.model_validate_json(data)

    async def _find_by_owner(self, owner_external_id: str, interface: str) -> Optional[Chat]:
        chats_root = self.base_dir / "chats"
        if not chats_root.exists():
            return None
        for chat_dir in chats_root.iterdir():
            meta = chat_dir / "chat.json"
            if not meta.exists():
                continue
            async with aiofiles.open(meta, "r", encoding="utf-8") as f:
                data = await f.read()
            chat = Chat.model_validate_json(data)
            if chat.owner_external_id == owner_external_id and chat.interface == interface:
                return chat
        return None

    async def get_or_create_chat(
        self,
        owner_external_id: str,
        interface: str,
        system_prompt: Optional[str] = None,
    ) -> Chat:
        existing = await self._find_by_owner(owner_external_id, interface)
        if existing:
            return existing
        return await self.create_chat(owner_external_id, interface, system_prompt)

    async def append_message(self, chat_id: UUID, message: ChatMessage) -> ChatMessage:
        messages_path = self._messages_path(chat_id)
        os.makedirs(messages_path.parent, exist_ok=True)
        async with aiofiles.open(messages_path, "a", encoding="utf-8") as f:
            await f.write(message.model_dump_json() + "\n")
        return message

    async def list_messages(self, chat_id: UUID, limit: int = 50) -> list[ChatMessage]:
        messages_path = self._messages_path(chat_id)
        if not messages_path.exists():
            return []
        async with aiofiles.open(messages_path, "r", encoding="utf-8") as f:
            lines = await f.readlines()

        last_delete_idx = -1
        parsed: list[tuple[int, dict]] = []
        for i, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            if data.get("type") == "soft_delete":
                last_delete_idx = i
                continue
            parsed.append((i, data))

        after = [data for i, data in parsed if i > last_delete_idx]
        messages: list[ChatMessage] = []
        for data in after:
            try:
                messages.append(ChatMessage.model_validate(data))
            except Exception:
                continue
        return messages[-limit:]

    async def soft_delete_messages(self, chat_id: UUID) -> None:
        messages_path = self._messages_path(chat_id)
        if not messages_path.exists():
            return
        marker = {"type": "soft_delete", "at": datetime.now(timezone.utc).isoformat()}
        async with aiofiles.open(messages_path, "a", encoding="utf-8") as f:
            await f.write(json.dumps(marker) + "\n")

    async def save_feedback(self, feedback: MessageFeedback) -> MessageFeedback:
        path = self._feedback_path()
        os.makedirs(path.parent, exist_ok=True)
        existing: list[dict] = []
        if path.exists():
            async with aiofiles.open(path, "r", encoding="utf-8") as f:
                raw = await f.read()
            for line in raw.splitlines():
                if line.strip():
                    existing.append(json.loads(line))
        existing = [
            row
            for row in existing
            if not (
                row.get("owner_external_id") == feedback.owner_external_id
                and row.get("message_id") == str(feedback.message_id)
            )
        ]
        existing.append(json.loads(feedback.model_dump_json()))
        async with aiofiles.open(path, "w", encoding="utf-8") as f:
            for row in existing:
                await f.write(json.dumps(row, ensure_ascii=False) + "\n")
        return feedback

    async def list_owner_ids(self, interface: str) -> list[str]:
        chats_root = self.base_dir / "chats"
        if not chats_root.exists():
            return []
        owners: list[str] = []
        for chat_dir in chats_root.iterdir():
            meta = chat_dir / "chat.json"
            if not meta.exists():
                continue
            async with aiofiles.open(meta, "r", encoding="utf-8") as f:
                chat = Chat.model_validate_json(await f.read())
            if chat.interface == interface:
                owners.append(chat.owner_external_id)
        return list(dict.fromkeys(owners))

    async def admin_stats(self) -> dict:
        chats_root = self.base_dir / "chats"
        total_messages = 0
        active_users: set[str] = set()
        if chats_root.exists():
            for chat_dir in chats_root.iterdir():
                meta = chat_dir / "chat.json"
                msgs = chat_dir / "messages.jsonl"
                if meta.exists():
                    async with aiofiles.open(meta, "r", encoding="utf-8") as f:
                        chat = Chat.model_validate_json(await f.read())
                    active_users.add(chat.owner_external_id)
                if msgs.exists():
                    async with aiofiles.open(msgs, "r", encoding="utf-8") as f:
                        lines = await f.readlines()
                    total_messages += sum(1 for line in lines if line.strip() and '"type": "soft_delete"' not in line)
        up = down = 0
        fb_path = self._feedback_path()
        if fb_path.exists():
            async with aiofiles.open(fb_path, "r", encoding="utf-8") as f:
                for line in (await f.read()).splitlines():
                    if not line.strip():
                        continue
                    row = json.loads(line)
                    if row.get("value") == "up":
                        up += 1
                    elif row.get("value") == "down":
                        down += 1
        total_fb = up + down
        return {
            "total_messages": total_messages,
            "active_users": len(active_users),
            "avg_latency_ms": 0,
            "moderation_block_rate": 0.0,
            "feedback_up_ratio": (up / total_fb) if total_fb else 0.0,
        }

    async def list_recent_users(self, limit: int = 50) -> list[dict]:
        chats_root = self.base_dir / "chats"
        if not chats_root.exists():
            return []
        users: dict[str, dict] = {}
        for chat_dir in chats_root.iterdir():
            meta = chat_dir / "chat.json"
            if not meta.exists():
                continue
            async with aiofiles.open(meta, "r", encoding="utf-8") as f:
                chat = Chat.model_validate_json(await f.read())
            item = users.setdefault(
                chat.owner_external_id,
                {"owner_external_id": chat.owner_external_id, "chats": 0, "last_seen_at": chat.created_at.isoformat()},
            )
            item["chats"] += 1
            if chat.created_at.isoformat() > item["last_seen_at"]:
                item["last_seen_at"] = chat.created_at.isoformat()
        rows = sorted(users.values(), key=lambda x: x["last_seen_at"], reverse=True)
        return rows[:limit]
