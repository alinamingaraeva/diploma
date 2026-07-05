from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from bot.services.backend_client import BackendClient
from bot.keyboards.inline import feedback_kb
import uuid

router = Router()

# ---- Кнопки главного меню ----

@router.message(F.text == "🎫 Купить билет")
async def tickets_info(message: types.Message):
    text = (
        "🎫 Купить билеты в музеи Казанского Кремля:\n"
        "https://tickets.kazan-kremlin.ru/?id=1&sid=244\n\n"
        "Там вы найдёте билеты во все музеи и на выставки!"
    )
    await message.answer(text)

@router.message(F.text == "📜 Правила посещения")
async def rules_info(message: types.Message):
    text = (
        "📜 Правила посещения музея-заповедника:\n"
        "https://kazan-kremlin.ru/pravila-poseshheniya/"
    )
    await message.answer(text)

@router.message(F.text == "🕐 Часы работы")
async def hours_info(message: types.Message):
    text = (
        "🕐 Графики работы:\n\n"
        "Музеи: вт-чт, сб-вс 10:00-18:00, пятница 11:00-20:00\n"
        "Кассы в музеях: вт-чт, сб-вс 10:00-17:30, пятница 11:00-19:30\n"
        "Музей исламской культуры: 9:00-19:30\n"
        "Визит-центр: ежедневно 8:30-17:30\n"
        "Касса Визит-центра: ежедневно 8:00-19:30\n"
        "Экскурсионный отдел: 8:30-18:00\n"
        "Благовещенский собор: ежедневно 8:00-20:00\n"
        "Кул-Шариф мечеть: ежедневно 8:00-20:00\n\n"
        "Купить билеты онлайн: https://tickets.kazan-kremlin.ru/?id=1&sid=244"
    )
    await message.answer(text)

@router.message(F.text == "📅 Афиша")
async def poster_info(message: types.Message):
    text = (
        "📅 Афиша мероприятий и событий Казанского Кремля:\n"
        "https://kazan-kremlin.ru/sobytiya/"
    )
    await message.answer(text)

@router.message(F.text == "❓ Задать вопрос")
async def ask_question_prompt(message: types.Message, state: FSMContext):
    await state.update_data(free_text_mode=True)
    await message.answer(
        "Напишите ваш вопрос о музеях, выставках, билетах или событиях.\n"
        "Я постараюсь найти ответ на основе информации с сайта."
    )

# ---- Обработка свободного текста (с edit_message_text) ----

@router.message(F.text & ~F.text.startswith("/") & F.text.not_in([
    "🎫 Купить билет", "📜 Правила посещения", "🕐 Часы работы", "📅 Афиша", "❓ Задать вопрос"
]))
async def handle_free_text(message: types.Message, backend: BackendClient, state: FSMContext):
    current_state = await state.get_state()
    if current_state:
        return

    owner_id = str(message.from_user.id)
    chat_id = await backend.get_or_create_chat(owner_id, interface="telegram")

    sent_msg = await message.answer("⌛ Думаю...")
    buffer = ""
    try:
        async for chunk in backend.send_message(chat_id, message.text):
            buffer += chunk
            await sent_msg.edit_text(buffer + " ...")
        if buffer:
            # Убираем "..." и отправляем финальный ответ с фидбеком
            feedback_id = f"{chat_id}_{uuid.uuid4().int & 0xFFFFFFFF}"
            await sent_msg.edit_text(buffer, reply_markup=feedback_kb(feedback_id))
        else:
            await sent_msg.edit_text("⚠️ Ответ не получен.")
    except Exception as e:
    error_text = str(e)
    print(f"ERROR: {error_text}")  # для отладки
    if "403" in error_text or "moderation_blocked" in error_text:
        await sent_msg.edit_text("⛔️ Ваше сообщение заблокировано модерацией.")
    else:
        await sent_msg.edit_text(f"❌ Ошибка: {error_text}")