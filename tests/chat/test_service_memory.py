from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.chat.domain import Chat, ChatMessage
from app.chat.service import ChatService


@pytest.mark.asyncio
async def test_last_user_message_is_recalled_without_rag():
    chat = Chat(
        id=uuid4(),
        owner_external_id="42",
        interface="telegram",
        system_prompt="museum system",
    )

    class Repo:
        def __init__(self):
            self.messages = [
                ChatMessage(chat_id=chat.id, role="user", content="как купить билеты в цирк?"),
                ChatMessage(chat_id=chat.id, role="assistant", content="По базе не нашёл."),
            ]

        async def append_message(self, chat_id, message):
            self.messages.append(message)
            return message

        async def get_chat(self, chat_id):
            return chat

        async def list_messages(self, chat_id, limit=50):
            return list(self.messages)

    allowed = SimpleNamespace(allowed=True, categories=[], blocked_by=None)
    rag = MagicMock()
    service = ChatService.__new__(ChatService)
    service.repo = Repo()
    service.rag = rag
    service.llm = SimpleNamespace(openai=MagicMock())
    service.settings = SimpleNamespace(
        chat_context_strategy="sliding",
        chat_context_window=10,
        model_context_window=128000,
        response_tokens=4096,
        safety_margin_tokens=256,
        openai=SimpleNamespace(default_model="openai/gpt-4o-mini"),
    )
    service.canary = ""
    service.moderation = SimpleNamespace(
        check_input=AsyncMock(return_value=allowed),
        check_output=AsyncMock(return_value=allowed),
    )

    chunks = [
        chunk
        async for chunk in service.send_message(chat.id, "о чем я спрашивала в последнем смс?")
    ]

    answer = "".join(part for part in chunks if not part.startswith("\n[[message_id:"))
    assert "как купить билеты в цирк?" in answer
    rag.answer.assert_not_called()
