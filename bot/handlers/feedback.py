from aiogram import Router, types, F
from bot.services.backend_client import BackendClient
import logging

logger = logging.getLogger(__name__)
router = Router()

@router.callback_query(F.data.startswith("fb:"))
async def feedback_callback(callback: types.CallbackQuery, backend: BackendClient):
    try:
        _, vote, msg_id = callback.data.split(":")
        # Здесь можно отправить запрос в backend для сохранения фидбека
        # Например: await backend.save_feedback(msg_id, vote, callback.from_user.id)
        # Пока просто ответим
        await callback.answer("Спасибо за оценку!", show_alert=False)
        # Убираем кнопки после голосования
        await callback.message.edit_reply_markup(reply_markup=None)
        logger.info(f"Feedback received: {msg_id} -> {vote}")
    except Exception as e:
        logger.error(f"Feedback error: {e}")
        await callback.answer("Ошибка при обработке оценки", show_alert=True)