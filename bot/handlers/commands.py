from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from bot.services.backend_client import BackendClient
from bot.keyboards.reply import main_menu_kb
import uuid

router = Router()

@router.message(Command("start"))
async def cmd_start(message: types.Message, backend: BackendClient):
    owner_id = str(message.from_user.id)
    chat_id = await backend.get_or_create_chat(owner_id, interface="telegram")
    await message.answer(
        "👋 Добро пожаловать в музейный бот Казанского Кремля!\n\n"
        "Я помогу вам с информацией о музеях, выставках, билетах и событиях.\n"
        "Выберите действие в меню ниже или задайте вопрос.",
        reply_markup=main_menu_kb()
    )

@router.message(Command("help"))
async def cmd_help(message: types.Message):
    text = (
        "Доступные команды:\n"
        "/start — начать заново\n"
        "/ask — задать вопрос с выбором темы\n"
        "/clear — очистить историю чата\n"
        "/cancel — отменить текущее действие\n"
        "/help — показать эту справку"
    )
    await message.answer(text)

@router.message(Command("clear"))
async def cmd_clear(message: types.Message, backend: BackendClient):
    owner_id = str(message.from_user.id)
    chat_id = await backend.get_or_create_chat(owner_id, interface="telegram")
    await backend.clear_messages(chat_id)
    await message.answer("🧹 История чата очищена.")

@router.message(Command("cancel"))
async def cmd_cancel(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is None:
        await message.answer("Нет активного сценария для отмены.")
        return
    await state.clear()
    await message.answer("✅ Действие отменено.")