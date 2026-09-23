from uuid import uuid4

import pytest

from app.chat.domain import ChatMessage


@pytest.mark.asyncio
async def test_create_and_get_chat(repo):
    chat = await repo.create_chat("test_owner", "cli")
    fetched = await repo.get_chat(chat.id)
    assert fetched is not None
    assert fetched.id == chat.id


@pytest.mark.asyncio
async def test_append_and_list_messages(repo):
    chat = await repo.create_chat("test_owner", "cli")
    await repo.append_message(chat.id, ChatMessage(chat_id=chat.id, role="user", content="Hello"))
    await repo.append_message(chat.id, ChatMessage(chat_id=chat.id, role="assistant", content="Hi there!"))
    messages = await repo.list_messages(chat.id)
    assert [m.content for m in messages] == ["Hello", "Hi there!"]


@pytest.mark.asyncio
async def test_list_messages_returns_last_n(repo):
    chat = await repo.create_chat("owner", "cli")
    for i in range(5):
        await repo.append_message(chat.id, ChatMessage(chat_id=chat.id, role="user", content=str(i)))
    messages = await repo.list_messages(chat.id, limit=2)
    assert [m.content for m in messages] == ["3", "4"]


@pytest.mark.asyncio
async def test_soft_delete_hides_old_keeps_new(repo):
    chat = await repo.create_chat("owner", "cli")
    await repo.append_message(chat.id, ChatMessage(chat_id=chat.id, role="user", content="old"))
    await repo.soft_delete_messages(chat.id)
    assert await repo.list_messages(chat.id) == []
    await repo.append_message(chat.id, ChatMessage(chat_id=chat.id, role="user", content="new"))
    messages = await repo.list_messages(chat.id)
    assert [m.content for m in messages] == ["new"]


@pytest.mark.asyncio
async def test_get_unknown_chat(repo):
    assert await repo.get_chat(uuid4()) is None


@pytest.mark.asyncio
async def test_get_or_create_idempotent(repo):
    a = await repo.get_or_create_chat("same-user", "telegram")
    b = await repo.get_or_create_chat("same-user", "telegram")
    assert a.id == b.id
