from aiogram.filters import StateFilter
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from bot.states import AskFlow
from bot.keyboards.inline import topics_kb
from bot.services.backend_client import BackendClient

router = Router()

@router.message(Command("ask"))
async def cmd_ask(message: types.Message, state: FSMContext):
    await state.set_state(AskFlow.waiting_for_topic)
    await message.answer("Выберите тему вопроса:", reply_markup=topics_kb())

@router.callback_query(F.data.startswith("topic:"), StateFilter(AskFlow.waiting_for_topic))
async def topic_callback(callback: types.CallbackQuery, state: FSMContext):
    topic_slug = callback.data.split(":")[1]
    if topic_slug == "cancel":
        await state.clear()
        await callback.message.edit_text("❌ Отменено.")
        await callback.answer()
        return
    await state.update_data(topic=topic_slug)
    await state.set_state(AskFlow.waiting_for_question)
    await callback.message.edit_text(f"Вы выбрали тему: {topic_slug}. Теперь напишите ваш вопрос.")
    await callback.answer()

@router.message(StateFilter(AskFlow.waiting_for_question), F.text)
async def ask_question(message: types.Message, state: FSMContext, backend: BackendClient):
    data = await state.get_data()
    topic = data.get("topic", "общая тема")
    prompt = f"Тема: {topic}. Вопрос: {message.text}"
    owner_id = str(message.from_user.id)
    chat_id = await backend.get_or_create_chat(owner_id, interface="telegram")
    
    sent_msg = await message.answer("⌛ Думаю...")
    buffer = ""
    try:
        async for chunk in backend.send_message(chat_id, prompt):
            buffer += chunk
            await sent_msg.edit_text(buffer + " ...")
        await sent_msg.edit_text(buffer)
        await state.clear()
    except Exception as e:
        await sent_msg.edit_text(f"❌ Ошибка: {str(e)}")
        await state.clear()