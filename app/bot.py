import logging
import time

import telebot
from telebot.apihelper import ApiTelegramException

from app.config import settings
from app.db import init_db
from app.handlers.start import register_start_handlers
from app.handlers.callbacks import register_callback_handlers


LOGGER = logging.getLogger(__name__)


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


def _prepare_bot(bot: telebot.TeleBot) -> None:
    try:
        bot.remove_webhook()
        LOGGER.info('Webhook removed before polling start')
    except Exception as exc:
        LOGGER.warning('Could not remove webhook before polling: %s', exc)


def run() -> None:
    configure_logging()
    init_db()

    while True:
        bot = create_bot()
        _prepare_bot(bot)
        LOGGER.info('Boostora bot started')
        try:
            bot.infinity_polling(skip_pending=True, timeout=30, long_polling_timeout=30)
        except ApiTelegramException as exc:
            description = str(exc)
            if 'terminated by other getUpdates request' in description:
                LOGGER.warning(
                    'Polling conflict detected: another bot instance is still using getUpdates. '
                    'Retrying in 5 seconds.'
                )
                time.sleep(5)
                continue
            raise
        except Exception:
            LOGGER.exception('Unexpected polling error. Retrying in 5 seconds.')
            time.sleep(5)
            continue
        break
