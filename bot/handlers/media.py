from io import BytesIO

from aiogram import F, Router, types
from aiogram.enums import ChatAction
from aiogram.fsm.context import FSMContext

from bot.keyboards.inline import feedback_kb
from bot.services.backend_client import BackendClient, friendly_http_error
from bot.services.streaming import stream_to_chat

router = Router()
PHOTO_LIMIT = 2 * 1024 * 1024


async def _proxy_media(message: types.Message, backend: BackendClient, content: str, data: bytes, mime: str):
    owner_id = str(message.from_user.id)
    chat_id = await backend.get_or_create_chat(owner_id, interface="telegram")
    await message.bot.send_chat_action(message.chat.id, ChatAction.TYPING)
    buffer, message_id = await stream_to_chat(
        message, backend.send_message(chat_id, content, media=data, mime=mime)
    )
    if buffer and message_id:
        await message.answer("Оцените ответ:", reply_markup=feedback_kb(message_id))


def _download_bytes(file_bytes) -> bytes:
    if hasattr(file_bytes, "getvalue"):
        return file_bytes.getvalue()
    if isinstance(file_bytes, BytesIO):
        return file_bytes.getvalue()
    return file_bytes


@router.message(F.photo)
async def handle_photo(message: types.Message, backend: BackendClient, state: FSMContext):
    if await state.get_state():
        return
    candidates = [p for p in message.photo if (p.file_size or 0) <= PHOTO_LIMIT]
    if not candidates:
        await message.answer("Фото слишком большое (максимум 2 МБ).")
        return
    photo = candidates[-1]
    file = await message.bot.get_file(photo.file_id)
    raw = await message.bot.download_file(file.file_path)
    try:
        await _proxy_media(message, backend, message.caption or "[фото]", _download_bytes(raw), "image/jpeg")
    except Exception as exc:
        await message.answer(f"❌ {friendly_http_error(exc)}")


@router.message(F.voice)
async def handle_voice(message: types.Message, backend: BackendClient, state: FSMContext):
    if await state.get_state():
        return
    file = await message.bot.get_file(message.voice.file_id)
    raw = await message.bot.download_file(file.file_path)
    try:
        await _proxy_media(message, backend, "[голосовое]", _download_bytes(raw), "audio/ogg")
    except Exception as exc:
        await message.answer(f"❌ {friendly_http_error(exc)}")


@router.message(F.audio)
async def handle_audio(message: types.Message, backend: BackendClient, state: FSMContext):
    if await state.get_state():
        return
    audio = message.audio
    mime = audio.mime_type or "audio/mpeg"
    file = await message.bot.get_file(audio.file_id)
    raw = await message.bot.download_file(file.file_path)
    try:
        await _proxy_media(message, backend, "[аудио]", _download_bytes(raw), mime)
    except Exception as exc:
        await message.answer(f"❌ {friendly_http_error(exc)}")


@router.message(F.document)
async def handle_document(message: types.Message, backend: BackendClient, state: FSMContext):
    if await state.get_state():
        return
    doc = message.document
    if not doc.file_name:
        return
    ext = doc.file_name.lower().rsplit(".", 1)[-1]
    if ext not in ("pdf", "docx"):
        await message.answer("📄 Пока я умею обрабатывать только PDF и DOCX файлы.")
        return
    if (doc.file_size or 0) > 10 * 1024 * 1024:
        await message.answer("📄 Файл слишком большой (макс. 10 МБ).")
        return
    file = await message.bot.get_file(doc.file_id)
    raw = await message.bot.download_file(file.file_path)
    mime = (
        "application/pdf"
        if ext == "pdf"
        else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    try:
        await _proxy_media(message, backend, message.caption or "[документ]", _download_bytes(raw), mime)
    except Exception as exc:
        await message.answer(f"❌ {friendly_http_error(exc)}")
