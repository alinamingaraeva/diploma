from aiogram import F, Router, types
from aiogram.enums import ChatAction
from aiogram.fsm.context import FSMContext

from bot.keyboards.inline import feedback_kb
from bot.services.backend_client import BackendClient, friendly_http_error
from bot.services.streaming import stream_to_chat

router = Router()


@router.message(F.text == "🎫 Купить билет")
async def tickets_info(message: types.Message):
    await message.answer(
        "🎫 Купить билеты в музеи Казанского Кремля:\n"
        "https://tickets.kazan-kremlin.ru/?id=1&sid=244\n\n"
        "Там вы найдёте билеты во все музеи и на выставки!"
    )


@router.message(F.text == "📜 Правила посещения")
async def rules_info(message: types.Message):
    await message.answer(
        "📜 Правила посещения музея-заповедника:\n"
        "https://kazan-kremlin.ru/pravila-poseshheniya/"
    )


@router.message(F.text == "🕐 Часы работы")
async def hours_info(message: types.Message):
    await message.answer(
        "🕐 Графики работы:\n\n"
        "Большинство музеев: пн-чт, сб-вс 10:00-18:00, пятница 11:00-20:00\n"
        "Кассы в музеях закрываются за 30 минут до площадки\n"
        "Манеж: понедельник — выходной\n"
        "Эрмитаж-Казань временно закрыт на монтаж новой выставки\n"
        "Музей исламской культуры: 9:00-19:30\n"
        "Визит-центр: ежедневно 8:30-17:30\n"
        "Экскурсионный отдел: 8:30-18:00\n"
        "Благовещенский собор: ежедневно 8:00-20:00\n"
        "Кул-Шариф мечеть: ежедневно 8:00-20:00\n\n"
        "Купить билеты онлайн: https://tickets.kazan-kremlin.ru/?id=1&sid=244"
    )


@router.message(F.text == "📅 Афиша")
async def poster_info(message: types.Message):
    await message.answer(
        "📅 Афиша мероприятий и событий Казанского Кремля:\n"
        "https://kazan-kremlin.ru/sobytiya/"
    )


@router.message(F.text == "❓ Задать вопрос")
async def ask_question_prompt(message: types.Message, state: FSMContext):
    await state.update_data(free_text_mode=True)
    await message.answer(
        "Напишите ваш вопрос о музеях, выставках, билетах или событиях.\n"
        "Я постараюсь найти ответ на основе информации с сайта."
    )


@router.message(
    F.text
    & ~F.text.startswith("/")
    & F.text.not_in(
        ["🎫 Купить билет", "📜 Правила посещения", "🕐 Часы работы", "📅 Афиша", "❓ Задать вопрос"]
    )
)
async def handle_free_text(message: types.Message, backend: BackendClient, state: FSMContext):
    if await state.get_state():
        return
    owner_id = str(message.from_user.id)
    try:
        chat_id = await backend.get_or_create_chat(owner_id, interface="telegram")
        await message.bot.send_chat_action(message.chat.id, ChatAction.TYPING)
        buffer, message_id = await stream_to_chat(message, backend.send_message(chat_id, message.text))
        if buffer and message_id:
            await message.answer("Оцените ответ:", reply_markup=feedback_kb(message_id))
    except Exception as exc:
        text = friendly_http_error(exc)
        if "moderation_blocked" in text or "403" in text:
            await message.answer("⛔️ Ваше сообщение заблокировано модерацией.")
        else:
            await message.answer(f"❌ {text}")
