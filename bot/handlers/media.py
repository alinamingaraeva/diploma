from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from io import BytesIO
from bot.services.backend_client import BackendClient
from aiogram.enums import ChatAction
import logging

logger = logging.getLogger(__name__)
router = Router()

@router.message(F.photo)
async def handle_photo(message: types.Message, backend: BackendClient, state: FSMContext):
    # Проверяем, не находится ли пользователь в FSM-сценарии
    current_state = await state.get_state()
    if current_state:
        # Если в FSM, обрабатываем как текст (не медиа)
        # Можно пропустить или обработать отдельно, но для простоты игнорируем
        return

    # Выбираем самое большое фото (последнее в массиве)
    photo = message.photo[-1]
    # Скачиваем файл
    file = await message.bot.get_file(photo.file_id)
    file_bytes = await message.bot.download_file(file.file_path)
    # Конвертируем в байты
    data = file_bytes.getvalue() if hasattr(file_bytes, 'getvalue') else file_bytes

    owner_id = str(message.from_user.id)
    chat_id = await backend.get_or_create_chat(owner_id, interface="telegram")

    sent_msg = await message.answer("🖼️ Обрабатываю фото...")
    buffer = ""
    try:
        async for chunk in backend.send_message(
            chat_id,
            content="[фото]",
            media=data,
            mime="image/jpeg"
        ):
            buffer += chunk
            await sent_msg.edit_text(buffer + " ...")
        await sent_msg.edit_text(buffer)
    except Exception as e:
        await sent_msg.edit_text(f"❌ Ошибка: {str(e)}")

@router.message(F.voice)
async def handle_voice(message: types.Message, backend: BackendClient, state: FSMContext):
    current_state = await state.get_state()
    if current_state:
        return

    voice = message.voice
    file = await message.bot.get_file(voice.file_id)
    file_bytes = await message.bot.download_file(file.file_path)
    data = file_bytes.getvalue() if hasattr(file_bytes, 'getvalue') else file_bytes

    owner_id = str(message.from_user.id)
    chat_id = await backend.get_or_create_chat(owner_id, interface="telegram")

    sent_msg = await message.answer("🎤 Расшифровываю голосовое...")
    buffer = ""
    try:
        async for chunk in backend.send_message(
            chat_id,
            content="[голосовое]",
            media=data,
            mime="audio/ogg"
        ):
            buffer += chunk
            await sent_msg.edit_text(buffer + " ...")
        await sent_msg.edit_text(buffer)
    except Exception as e:
        await sent_msg.edit_text(f"❌ Ошибка: {str(e)}")

@router.message(F.document)
async def handle_document(message: types.Message, backend: BackendClient, state: FSMContext):
    current_state = await state.get_state()
    if current_state:
        return

    doc = message.document
    # Проверяем расширение и размер
    if not doc.file_name:
        return
    ext = doc.file_name.lower().split('.')[-1] if '.' in doc.file_name else ''
    if ext not in ('pdf', 'docx'):
        await message.answer("📄 Пока я умею обрабатывать только PDF и DOCX файлы.")
        return
    if doc.file_size > 10 * 1024 * 1024:
        await message.answer("📄 Файл слишком большой (макс. 10 МБ).")
        return

    file = await message.bot.get_file(doc.file_id)
    file_bytes = await message.bot.download_file(file.file_path)
    data = file_bytes.getvalue() if hasattr(file_bytes, 'getvalue') else file_bytes

    owner_id = str(message.from_user.id)
    chat_id = await backend.get_or_create_chat(owner_id, interface="telegram")

    sent_msg = await message.answer("📄 Обрабатываю документ...")
    buffer = ""
    mime = "application/pdf" if ext == "pdf" else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    try:
        async for chunk in backend.send_message(
            chat_id,
            content="[документ]",
            media=data,
            mime=mime
        ):
            buffer += chunk
            await sent_msg.edit_text(buffer + " ...")
        await sent_msg.edit_text(buffer)
    except Exception as e:
        await sent_msg.edit_text(f"❌ Ошибка: {str(e)}")