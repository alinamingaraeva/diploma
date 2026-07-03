from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

def main_menu_kb() -> ReplyKeyboardMarkup:
    buttons = [
        [KeyboardButton(text="🎫 Купить билет")],
        [KeyboardButton(text="📜 Правила посещения")],
        [KeyboardButton(text="🕐 Часы работы")],
        [KeyboardButton(text="📅 Афиша")],
        [KeyboardButton(text="❓ Задать вопрос")],
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)