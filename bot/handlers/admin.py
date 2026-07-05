from aiogram import Router, types, F
from aiogram.filters import Command, Filter
from bot.config import get_bot_settings
from bot.services.backend_client import BackendClient

class IsAdmin(Filter):
    async def __call__(self, message: types.Message):
        settings = get_bot_settings()
        return message.from_user.id in settings.bot_admin_ids

router = Router()
router.message.filter(IsAdmin())

@router.message(Command("stats"))
async def stats_command(message: types.Message, backend: BackendClient):
    try:
        stats = await backend.get_stats()
        await message.answer(f"📊 Статистика:\nСообщений: {stats['total_messages']}\nАктивных: {stats['active_users']}\nЗадержка: {stats['avg_latency_ms']} мс")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")