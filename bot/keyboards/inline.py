from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

def topics_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    topics = [
        ("🎫 Билеты", "tickets"),
        ("🕐 Часы работы", "hours"),
        ("📅 Афиша", "poster"),
        ("🚶 Экскурсии", "excursions"),
        ("📍 Как добраться", "location"),
    ]
    for label, slug in topics:
        builder.button(text=label, callback_data=f"topic:{slug}")
    builder.button(text="❌ Отмена", callback_data="topic:cancel")
    builder.adjust(1)
    return builder.as_markup()

def feedback_kb(message_id: str) -> InlineKeyboardMarkup:
    """Клавиатура для оценки ответа."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="👍", callback_data=f"fb:up:{message_id}"),
            InlineKeyboardButton(text="👎", callback_data=f"fb:down:{message_id}")
        ]
    ])