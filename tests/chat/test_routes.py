from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.chat.deps import get_chat_service, get_repository
from app.chat.domain import Chat
from app.chat.routes import router
from app.core.config import get_settings


class FakeRepo:
    def __init__(self):
        self.chat = Chat(owner_external_id="u", interface="cli")
        self.messages = []
        self.feedbacks = []

    async def get_or_create_chat(self, owner, interface, system_prompt=None):
        return self.chat

    async def create_chat(self, owner, interface, system_prompt=None):
        return self.chat

    async def get_chat(self, chat_id):
        return self.chat if chat_id == self.chat.id else None

    async def list_messages(self, chat_id, limit=50):
        return self.messages[-limit:]

    async def soft_delete_messages(self, chat_id):
        self.messages.clear()

    async def save_feedback(self, feedback):
        self.feedbacks.append(feedback)
        return feedback


class FakeService:
    def __init__(self, repo):
        self.repo = repo

    async def create_chat(self, owner, interface, system_prompt=None):
        return await self.repo.get_or_create_chat(owner, interface, system_prompt)

    async def get_chat(self, chat_id):
        return await self.repo.get_chat(chat_id)

    async def get_history(self, chat_id, limit=50):
        return await self.repo.list_messages(chat_id, limit)

    async def clear_history(self, chat_id):
        await self.repo.soft_delete_messages(chat_id)

    async def send_message(self, chat_id, content, media=None):
        yield "ok"


@pytest.fixture
def app():
    repo = FakeRepo()
    service = FakeService(repo)
    application = FastAPI()
    application.include_router(router)
    application.dependency_overrides[get_chat_service] = lambda: service
    application.dependency_overrides[get_repository] = lambda: repo
    return application


@pytest.mark.asyncio
async def test_create_and_get_chat(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post("/chats", json={"owner_external_id": "u", "interface": "cli"})
        assert created.status_code == 200
        chat_id = created.json()["chat_id"]
        got = await client.get(f"/chats/{chat_id}")
        assert got.status_code == 200


def test_extract_stream_message_id_keeps_full_uuid():
    from app.chat.routes import extract_stream_message_id

    uid = "0c80aa09-8b2b-4659-bfc4-edcd77512ddf"
    assert extract_stream_message_id(f"\n[[message_id:{uid}]]") == uid
    assert extract_stream_message_id(f"[[message_id:{uid}]]") == uid


def test_extract_stream_sources():
    from app.chat.routes import extract_stream_sources

    payload = '[{"file_name":"hours.md","page":1,"score":0.5,"snippet":"x"}]'
    assert extract_stream_sources(f"[[sources:{payload}]]") == payload
    assert extract_stream_sources("hello") is None


@pytest.mark.asyncio
async def test_feedback_accepts_full_uuid(app):
    from uuid import uuid4

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        mid = str(uuid4())
        resp = await client.post(
            "/chats/feedback",
            json={"message_id": mid, "value": "up", "owner_external_id": "123"},
        )
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}
