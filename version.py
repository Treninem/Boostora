from telebot.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove

from app.config import settings
from app.services.users import UserService
from app.texts import ROLE_CLIENT


def main_reply_keyboard(user_id: int):
    mode = (settings.smart_bottom_menu or 'compact').lower()
    if mode == 'hidden':
        return ReplyKeyboardRemove()
    role = UserService.get_role(user_id)
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    if mode == 'full':
        if role == ROLE_CLIENT:
            markup.row(KeyboardButton('Создать задание'), KeyboardButton('Аналитика'))
        else:
            markup.row(KeyboardButton('Профиль'), KeyboardButton('Задания'))
        markup.row(KeyboardButton('🔥 Продвижение'), KeyboardButton('📊 Мои 0/10'))
        markup.row(KeyboardButton('Витрина'))
        markup.row(KeyboardButton('📜 Правила'))
        markup.row(KeyboardButton('Кошелёк👛'), KeyboardButton('Рефералы'))
        markup.row(KeyboardButton('Меню'))
        return markup
    markup.row(KeyboardButton('🚀 Центр'), KeyboardButton('🔥 Продвижение'))
    markup.row(KeyboardButton('📊 Мои 0/10'))
    markup.row(KeyboardButton('🧩 Витрина'), KeyboardButton('💰 Кошелёк'))
    markup.row(KeyboardButton('📜 Правила'))
    markup.row(KeyboardButton('☰ Меню'))
    if UserService.is_admin(user_id):
        markup.row(KeyboardButton('⚙️ Админ'))
    return markup
