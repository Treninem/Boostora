import logging
import os
import tempfile
import threading
import time

import telebot
from telebot.apihelper import ApiTelegramException

from app.config import settings
from app.db import init_db
from app.handlers.start import register_start_handlers
from app.handlers.callbacks import register_callback_handlers
from app.services.promo import PromoService


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




def _start_promo_worker(bot: telebot.TeleBot) -> threading.Event:
    stop_event = threading.Event()

    def _worker() -> None:
        while not stop_event.is_set():
            try:
                PromoService.run_due_promotions(bot)
            except Exception:
                LOGGER.exception('Promo worker error')
            stop_event.wait(300)

    thread = threading.Thread(target=_worker, name='promo-worker', daemon=True)
    thread.start()
    return stop_event

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
        promo_stop_event = _start_promo_worker(bot)
        LOGGER.info('Boostora bot started')
        try:
            bot.infinity_polling(
                skip_pending=True,
                timeout=30,
                long_polling_timeout=30,
                allowed_updates=[
                    'message', 'callback_query', 'pre_checkout_query', 'chat_member',
                    'message_reaction', 'message_reaction_count', 'poll_answer',
                    'channel_post', 'my_chat_member', 'edited_channel_post'
                ],
            )
        except ApiTelegramException as exc:
            promo_stop_event.set()
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
            promo_stop_event.set()
            LOGGER.exception('Unexpected polling error. Retrying in 5 seconds.')
            time.sleep(5)
            continue
        promo_stop_event.set()
        break
    _release_single_instance_lock(lock_fd)
