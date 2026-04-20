import logging
import os
import tempfile
import time

import telebot
from telebot.apihelper import ApiTelegramException

from app.config import settings
from app.db import init_db
from app.handlers.start import register_start_handlers
from app.handlers.callbacks import register_callback_handlers


LOGGER = logging.getLogger(__name__)


def _lock_path() -> str:
    safe_token = settings.bot_token.split(':', 1)[0]
    return os.path.join(tempfile.gettempdir(), f'boostora_{safe_token}.lock')


def _acquire_single_instance_lock() -> int | None:
    path = _lock_path()
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_RDWR)
        os.write(fd, str(os.getpid()).encode())
        return fd
    except FileExistsError:
        return None


def _release_single_instance_lock(fd: int | None) -> None:
    if fd is None:
        return
    try:
        os.close(fd)
    except Exception:
        pass
    try:
        os.unlink(_lock_path())
    except FileNotFoundError:
        pass
    except Exception as exc:
        LOGGER.warning('Could not remove lock file: %s', exc)


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s | %(levelname)s | %(name)s | %(message)s'
    )


def create_bot() -> telebot.TeleBot:
    bot = telebot.TeleBot(settings.bot_token, parse_mode='HTML', threaded=False)
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

    lock_fd = _acquire_single_instance_lock()
    if lock_fd is None:
        LOGGER.warning('Another local bot process is already running. Waiting 5 seconds before retry.')
        time.sleep(5)
    while True:
        lock_fd = lock_fd or _acquire_single_instance_lock()
        if lock_fd is None:
            time.sleep(5)
            continue
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
    _release_single_instance_lock(lock_fd)
