import json
import re
import time
import uuid
from pathlib import Path
from urllib.parse import unquote, urlparse

from aiogram.methods.base import TelegramMethod
from aiogram.types import Message

EDIT_DEBOUNCE_SEC = 0.7
_last_edit_at: dict[int, float] = {}


class SendMessageDraft(TelegramMethod[bool]):
    __returning__ = bool
    __api_method__ = "sendMessageDraft"

    chat_id: int | str
    draft_id: int
    text: str


def _should_edit(chat_id: int) -> bool:
    now = time.monotonic()
    last = _last_edit_at.get(chat_id, 0.0)
    if now - last < EDIT_DEBOUNCE_SEC:
        return False
    _last_edit_at[chat_id] = now
    return True


def _clean_source_text(value: object) -> str:
    return " ".join(str(value or "").split())


def _fallback_source_title(reference: str) -> str:
    if reference.startswith(("http://", "https://")):
        parsed = urlparse(reference)
        slug = unquote(parsed.path.rstrip("/").rsplit("/", 1)[-1])
        if slug:
            return slug.replace("-", " ").replace("_", " ").capitalize()
        return "Официальный сайт Казанского Кремля"
    stem = Path(reference).stem
    return stem.replace("-", " ").replace("_", " ").capitalize() or "Документ музея"


def format_sources_block(payload: str, cited_ids: set[str] | None = None) -> str:
    """Преобразует служебный JSON источников в читаемый блок Telegram."""
    try:
        sources = json.loads(payload)
    except (json.JSONDecodeError, TypeError):
        return ""
    if not isinstance(sources, list):
        return ""

    lines: list[str] = []
    seen: set[str] = set()
    for position, source in enumerate(sources, start=1):
        if not isinstance(source, dict):
            continue
        reference = _clean_source_text(
            source.get("url") or source.get("file_name") or source.get("source")
        )
        if not reference or reference == "unknown" or reference in seen:
            continue
        seen.add(reference)
        source_id = _clean_source_text(source.get("id")) or str(position)
        if cited_ids and source_id not in cited_ids:
            continue
        title = _clean_source_text(source.get("title")) or _fallback_source_title(reference)
        if reference.startswith(("http://", "https://")):
            lines.append(f"[{source_id}] {title} — {reference}")
        else:
            page = source.get("page")
            page_suffix = f", стр. {page}" if page not in (None, "", 0, "0") else ""
            lines.append(f"[{source_id}] {title}{page_suffix} — {reference}")
        if len(lines) >= 5:
            break
    return "Источники:\n" + "\n".join(lines) if lines else ""


async def stream_to_chat(message: Message, tokens) -> tuple[str, str | None]:
    """Рендерит стрим через sendMessageDraft, с запасным edit_text не чаще 700 мс."""
    draft_id = uuid.uuid4().int & 0xFFFFFFFF
    buffer = ""
    message_id = None
    sources_block = ""
    sent = None
    use_draft = True
    chat_id = message.chat.id
    try:
        await message.bot(SendMessageDraft(chat_id=chat_id, text="…", draft_id=draft_id))
        _last_edit_at[chat_id] = time.monotonic()
    except Exception:
        use_draft = False
        sent = await message.answer("⌛ Думаю...")
        _last_edit_at[chat_id] = time.monotonic()

    async for delta in tokens:
        if delta.startswith("[[message_id:") and delta.endswith("]]"):
            message_id = delta[13:-2]
            continue
        if delta.startswith("[[sources:") and delta.endswith("]]"):
            cited_ids = set(re.findall(r"\[(\d+)\]", buffer))
            sources_block = format_sources_block(delta[len("[[sources:") : -2], cited_ids)
            continue
        buffer += delta
        if not buffer.strip():
            continue
        if not _should_edit(chat_id):
            continue
        try:
            if use_draft:
                await message.bot(
                    SendMessageDraft(chat_id=chat_id, text=buffer, draft_id=draft_id)
                )
            elif sent:
                await sent.edit_text(buffer + " …")
        except Exception:
            continue

    if buffer and sources_block:
        buffer = f"{buffer.rstrip()}\n\n{sources_block}"

    if buffer:
        if sent:
            await sent.edit_text(buffer)
        else:
            await message.bot.send_message(chat_id=chat_id, text=buffer)
        _last_edit_at[chat_id] = time.monotonic()
    elif sent:
        await sent.edit_text("⚠️ Ответ не получен. Попробуйте ещё раз.")
    else:
        await message.answer("⚠️ Ответ не получен. Попробуйте ещё раз.")
    return buffer, message_id
