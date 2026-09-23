from aiogram import Router, types
from aiogram.filters import Command, Filter

from bot.config import get_bot_settings
from bot.services.backend_client import BackendClient, friendly_http_error


class IsAdmin(Filter):
    async def __call__(self, message: types.Message) -> bool:
        settings = get_bot_settings()
        return bool(message.from_user and message.from_user.id in settings.bot_admin_ids)


router = Router()
router.message.filter(IsAdmin())


@router.message(Command("stats"))
async def stats_command(message: types.Message, backend: BackendClient):
    try:
        stats = await backend.get_stats()
        await message.answer(
            "📊 Статистика\n"
            f"Сообщений: {stats.get('total_messages')}\n"
            f"Активных пользователей: {stats.get('active_users')}\n"
            f"Задержка, мс: {stats.get('avg_latency_ms')}\n"
            f"Доля 👍: {stats.get('feedback_up_ratio')}"
        )
    except Exception as exc:
        await message.answer(f"❌ {friendly_http_error(exc)}")


@router.message(Command("users"))
async def users_command(message: types.Message, backend: BackendClient):
    try:
        users = await backend.get_users(limit=10)
        if not users:
            await message.answer("Пользователей пока нет.")
            return
        lines = ["👥 Последние пользователи:"]
        for row in users[:10]:
            lines.append(
                f"{row.get('owner_external_id')} — чатов: {row.get('chats')}, last: {row.get('last_seen_at')}"
            )
        await message.answer("\n".join(lines))
    except Exception as exc:
        await message.answer(f"❌ {friendly_http_error(exc)}")


@router.message(Command("broadcast"))
async def broadcast_command(message: types.Message, backend: BackendClient):
    text = (message.text or "").replace("/broadcast", "", 1).strip()
    if not text:
        await message.answer("Использование: /broadcast текст объявления")
        return
    try:
        result = await backend.broadcast(text)
        await message.answer(f"Рассылка отправлена: {result.get('sent', 0)}")
    except Exception as exc:
        await message.answer(f"❌ {friendly_http_error(exc)}")
