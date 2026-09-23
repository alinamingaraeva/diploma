import base64
from io import BytesIO

import pytest
from fastapi import UploadFile
from starlette.datastructures import Headers
from unittest.mock import AsyncMock, MagicMock

from app.chat.media import extract_pdf_text, media_to_part, set_openai_client


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
