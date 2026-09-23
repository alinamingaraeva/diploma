import time
import uuid

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


async def stream_to_chat(message: Message, tokens) -> tuple[str, str | None]:
    """Рендерит стрим через sendMessageDraft, с запасным edit_text не чаще 700 мс."""
    draft_id = uuid.uuid4().int & 0xFFFFFFFF
    buffer = ""
    message_id = None
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
        if delta.startswith("[[sources:"):
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
