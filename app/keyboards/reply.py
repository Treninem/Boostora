from telebot.types import ReplyKeyboardMarkup, KeyboardButton

from app.services.users import UserService
from app.texts import ROLE_CLIENT, ROLE_PERFORMER


def main_reply_keyboard(user_id: int):
    role = UserService.get_role(user_id)
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    if role == ROLE_CLIENT:
        markup.row(KeyboardButton('Создать задание'), KeyboardButton('Аналитика'))
        markup.row(KeyboardButton('Кошелёк👛'), KeyboardButton('История'))
    else:
        markup.row(KeyboardButton('Профиль'), KeyboardButton('Задания'))
        markup.row(KeyboardButton('Кошелёк👛'), KeyboardButton('История'))
    markup.row(KeyboardButton('VIP'), KeyboardButton('Искры✨ и обмен'))
    markup.row(KeyboardButton('Рефералы'), KeyboardButton('Меню'))
    return markup
