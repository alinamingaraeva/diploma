import json
from types import SimpleNamespace

import pytest

from bot.services.streaming import (
    _last_edit_at,
    _should_edit,
    format_sources_block,
    stream_to_chat,
)


def test_edit_debounce_skips_second_call():
    _last_edit_at.clear()
    assert _should_edit(42) is True
    assert _should_edit(42) is False
    _last_edit_at[42] = 0.0
    assert _should_edit(42) is True
    _last_edit_at.clear()


def test_format_sources_block_shows_title_and_official_url():
    payload = json.dumps(
        [
            {
                "id": 1,
                "title": "Правила посещения музея-заповедника",
                "file_name": "https://kazan-kremlin.ru/pravila-poseshheniya/",
            }
        ],
        ensure_ascii=False,
    )

    assert format_sources_block(payload) == (
        "Источники:\n"
        "[1] Правила посещения музея-заповедника — "
        "https://kazan-kremlin.ru/pravila-poseshheniya/"
    )


def test_format_sources_block_falls_back_to_document_name():
    payload = json.dumps([{"id": 2, "file_name": "museum_hours.md", "page": 3}])

    assert format_sources_block(payload) == (
        "Источники:\n[2] Museum hours, стр. 3 — museum_hours.md"
    )


def test_format_sources_block_ignores_invalid_payload():
    assert format_sources_block("not-json") == ""


def test_format_sources_block_keeps_only_cited_sources():
    payload = json.dumps(
        [
            {"id": 1, "title": "Правила", "file_name": "https://kazan-kremlin.ru/rules"},
            {"id": 2, "title": "Афиша", "file_name": "https://kazan-kremlin.ru/afisha"},
        ],
        ensure_ascii=False,
    )

    block = format_sources_block(payload, {"1"})

    assert "[1] Правила" in block
    assert "[2]" not in block


@pytest.mark.asyncio
async def test_stream_to_chat_appends_sources_after_answer():
    class FakeBot:
        def __init__(self):
            self.final_text = ""

        async def __call__(self, method):
            return True

        async def send_message(self, chat_id, text):
            self.final_text = text

    bot = FakeBot()
    message = SimpleNamespace(chat=SimpleNamespace(id=42), bot=bot)

    async def tokens():
        yield "Ответ по правилам [1]."
        yield '[[sources:[{"id":1,"title":"Правила посещения","file_name":"https://kazan-kremlin.ru/pravila-poseshheniya/"}]]]'
        yield "[[message_id:12345678-1234-1234-1234-123456789012]]"

    buffer, message_id = await stream_to_chat(message, tokens())

    assert "Ответ по правилам [1].\n\nИсточники:" in buffer
    assert "[1] Правила посещения — https://kazan-kremlin.ru/pravila-poseshheniya/" in buffer
    assert bot.final_text == buffer
    assert message_id == "12345678-1234-1234-1234-123456789012"
