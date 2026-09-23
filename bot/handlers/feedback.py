from aiogram import F, Router, types

from bot.services.backend_client import BackendClient, friendly_http_error

router = Router()


@router.callback_query(F.data.startswith("fb:"))
async def feedback_callback(callback: types.CallbackQuery, backend: BackendClient):
    try:
        _, vote, message_id = callback.data.split(":", 2)
        await backend.save_feedback(
            message_id=message_id,
            vote=vote,
            owner_external_id=str(callback.from_user.id),
        )
        await callback.answer("Спасибо за оценку!", show_alert=False)
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception as exc:
        await callback.answer(friendly_http_error(exc), show_alert=True)
