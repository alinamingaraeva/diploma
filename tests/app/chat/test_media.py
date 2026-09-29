import base64
from io import BytesIO
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import UploadFile
from starlette.datastructures import Headers
from unittest.mock import AsyncMock, MagicMock

from app.chat.media import extract_pdf_text, media_to_part, set_openai_client
from app.chat.domain import Chat
from app.chat.service import ChatService


def test_extract_pdf_text():
    from pypdf import PdfWriter

    buf = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    writer.write(buf)
    text = extract_pdf_text(buf.getvalue())
    assert isinstance(text, str)


@pytest.mark.asyncio
async def test_png_media_to_part():
    png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05"
        b"\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    upload = UploadFile(
        file=BytesIO(png),
        filename="a.png",
        headers=Headers({"content-type": "image/png"}),
    )
    part = await media_to_part(upload)
    assert part["type"] == "image_url"
    assert part["image_url"]["url"].startswith("data:image/png;base64,")
    base64.b64decode(part["image_url"]["url"].split(",", 1)[1])


@pytest.mark.asyncio
async def test_whisper_stub():
    client = MagicMock()
    client.audio.transcriptions.create = AsyncMock(return_value=MagicMock(text="привет музей"))
    set_openai_client(client)
    media = UploadFile(
        file=BytesIO(b"oggbytes"),
        filename="voice.ogg",
        headers=Headers({"content-type": "audio/ogg"}),
    )
    part = await media_to_part(media)
    assert part["type"] == "text"
    assert "[пользователь сказал голосом]:" in part["text"]
    assert "привет музей" in part["text"]


@pytest.mark.asyncio
async def test_voice_transcript_is_sent_to_rag():
    openai_client = MagicMock()
    openai_client.audio.transcriptions.create = AsyncMock(
        return_value=MagicMock(text="Какие выставки будут в Эрмитаже в эти выходные?")
    )
    set_openai_client(openai_client)

    chat = Chat(
        id=uuid4(),
        owner_external_id="42",
        interface="telegram",
        system_prompt="museum system",
    )

    class Repo:
        def __init__(self):
            self.messages = []

        async def append_message(self, chat_id, message):
            self.messages.append(message)
            return message

        async def get_chat(self, chat_id):
            return chat

        async def list_messages(self, chat_id, limit=50):
            return list(self.messages)

    rag = MagicMock()
    rag.answer.return_value = {
        "answer": "В официальной афише отдельная выставка не указана [1].",
        "sources": [{"id": 1, "file_name": "https://kazan-kremlin.ru/afisha"}],
    }
    moderation_result = SimpleNamespace(allowed=True, categories=[], blocked_by=None)

    service = ChatService.__new__(ChatService)
    service.repo = Repo()
    service.rag = rag
    service.llm = SimpleNamespace(openai=openai_client)
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
        check_input=AsyncMock(return_value=moderation_result),
        check_output=AsyncMock(return_value=moderation_result),
    )

    media = UploadFile(
        file=BytesIO(b"oggbytes"),
        filename="voice.ogg",
        headers=Headers({"content-type": "audio/ogg"}),
    )
    chunks = [chunk async for chunk in service.send_message(chat.id, "[голосовое]", media)]

    assert "В официальной афише" in "".join(chunks)
    rag.answer.assert_called_once()
    assert rag.answer.call_args.args[0] == "Какие выставки будут в Эрмитаже в эти выходные?"
    assert service.repo.messages[0].content.startswith("[голосовое сообщение] Какие выставки")


@pytest.mark.asyncio
async def test_photo_with_official_url_uses_that_page():
    chat = Chat(
        id=uuid4(),
        owner_external_id="42",
        interface="telegram",
        system_prompt="museum system",
    )

    class Repo:
        def __init__(self):
            self.messages = []

        async def append_message(self, chat_id, message):
            self.messages.append(message)
            return message

        async def get_chat(self, chat_id):
            return chat

        async def list_messages(self, chat_id, limit=50):
            return list(self.messages)

    url = "https://kazan-kremlin.ru/events/master-klass-vyshivka-tamburnym-shvom"
    rag = MagicMock()
    rag.answer_from_official_url.return_value = {
        "answer": "Мероприятие проходит в Выставочных залах Присутственных мест [1].",
        "sources": [{"id": 1, "file_name": url}],
    }
    allowed = SimpleNamespace(allowed=True, categories=[], blocked_by=None)

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

    media = UploadFile(
        file=BytesIO(b"jpegbytes"),
        filename="photo.jpg",
        headers=Headers({"content-type": "image/jpeg"}),
    )
    caption = f"Это в каком музее? {url}"
    chunks = [chunk async for chunk in service.send_message(chat.id, caption, media)]

    assert "Выставочных залах Присутственных мест" in "".join(chunks)
    rag.answer_from_official_url.assert_called_once_with(caption, url)
