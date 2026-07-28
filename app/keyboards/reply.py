from telebot.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
try:
    from telebot.types import WebAppInfo
except Exception:  # pragma: no cover
    WebAppInfo = None

from app.config import settings


def main_reply_keyboard(user_id: int):
    mode = (settings.smart_bottom_menu or 'compact').lower()
    if mode == 'hidden':
        return ReplyKeyboardRemove()
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    if settings.mini_app_url and WebAppInfo is not None:
        markup.row(KeyboardButton('🚀 Открыть Boostora', web_app=WebAppInfo(url=settings.mini_app_url)))
    else:
        markup.row(KeyboardButton('☰ Меню'))
    return markup
