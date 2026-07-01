import pytest
from uuid import uuid4
from app.chat.domain import Chat, ChatMessage

@pytest.mark.asyncio
async def test_create_and_get_chat(repo):
    chat = await repo.create_chat("test_owner", "cli")
    assert chat.id is not None
    assert chat.owner_external_id == "test_owner"
    fetched = await repo.get_chat(chat.id)
    assert fetched is not None
    assert fetched.id == chat.id

@pytest.mark.asyncio
async def test_append_and_list_messages(repo):
    chat = await repo.create_chat("test_owner", "cli")
    msg1 = ChatMessage(chat_id=chat.id, role="user", content="Hello")
    msg2 = ChatMessage(chat_id=chat.id, role="assistant", content="Hi there!")
    await repo.append_message(chat.id, msg1)
    await repo.append_message(chat.id, msg2)
    messages = await repo.list_messages(chat.id)
    assert len(messages) == 2
    assert messages[0].content == "Hello"
    assert messages[1].content == "Hi there!"

