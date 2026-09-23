import json
import uuid

import httpx
import pytest

from bot.services.backend_client import BackendClient


@pytest.mark.asyncio
async def test_send_message_parses_sse():
    chat_id = uuid.uuid4()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and str(request.url).endswith("/chats"):
            return httpx.Response(200, json={"chat_id": str(chat_id)})
        body = 'data: {"type": "token", "delta": "Hello"}\n\ndata: {"type": "done"}\n\n'.encode()
        return httpx.Response(200, content=body, headers={"content-type": "text/event-stream"})

    transport = httpx.MockTransport(handler)
    http = httpx.AsyncClient(transport=transport)
    client = BackendClient(base_url="http://test", http=http)
    chunks = []
    async for part in client.send_message(chat_id, "hi"):
        chunks.append(part)
    assert "Hello" in chunks
    await http.aclose()


@pytest.mark.asyncio
async def test_send_message_handles_sources_event_with_json_list():
    chat_id = uuid.uuid4()
    sources = [{"id": 1, "file_name": "hermitage_kazan.md"}]

    def handler(request: httpx.Request) -> httpx.Response:
        body = (
            'data: {"type": "token", "delta": "Ответ"}\n\n'
            f"event: sources\ndata: {json.dumps(sources)}\n\n"
            'data: {"type": "done"}\n\n'
        ).encode()
        return httpx.Response(200, content=body, headers={"content-type": "text/event-stream"})

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = BackendClient(base_url="http://test", http=http)
    chunks = [part async for part in client.send_message(chat_id, "hi")]

    assert chunks[0] == "Ответ"
    assert chunks[1].startswith("[[sources:")
    await http.aclose()


@pytest.mark.asyncio
async def test_clear_and_create():
    chat_id = uuid.uuid4()
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, str(request.url)))
        if request.method == "POST":
            return httpx.Response(200, json={"chat_id": str(chat_id)})
        return httpx.Response(200, json={"status": "ok"})

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = BackendClient(base_url="http://test", http=http)
    got = await client.get_or_create_chat("1", "telegram")
    assert got == chat_id
    await client.clear_messages(chat_id)
    assert any(m == "DELETE" for m, _ in calls)
    await http.aclose()


@pytest.mark.asyncio
async def test_send_message_with_media_multipart():
    chat_id = uuid.uuid4()

    def handler(request: httpx.Request) -> httpx.Response:
        assert b"content" in request.content or request.headers.get("content-type", "").startswith("multipart")
        body = b'data: {"type":"token","delta":"ok"}\n\ndata: {"type":"done"}\n\n'
        return httpx.Response(200, content=body)

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = BackendClient(base_url="http://test", http=http)
    parts = [p async for p in client.send_message(chat_id, "cap", media=b"123", mime="image/jpeg")]
    assert "ok" in parts
    await http.aclose()
