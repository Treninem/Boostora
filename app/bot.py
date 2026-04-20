import logging
import telebot

from app.config import settings
from app.db import init_db
from app.handlers.start import register_start_handlers
from app.handlers.callbacks import register_callback_handlers


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s | %(levelname)s | %(name)s | %(message)s'
    )


def create_bot() -> telebot.TeleBot:
    bot = telebot.TeleBot(settings.bot_token, parse_mode='HTML', threaded=True)
    register_start_handlers(bot)
    register_callback_handlers(bot)
    return bot


def run() -> None:
    configure_logging()
    init_db()
    bot = create_bot()
    logging.getLogger(__name__).info('Boostora bot started')
    bot.infinity_polling(skip_pending=True, timeout=30, long_polling_timeout=30)
