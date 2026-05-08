import logging
import os
import tempfile
import threading
import time

import requests
import telebot
from telebot.apihelper import ApiTelegramException

from app.config import settings
from app.db import init_db
from app.handlers.start import register_start_handlers
from app.handlers.callbacks import register_callback_handlers
from app.services.promo import PromoService
from app.services.ad_broadcasts import AdBroadcastService
from app.version import APP_VERSION


LOGGER = logging.getLogger(__name__)

ALLOWED_UPDATES = [
    'message', 'callback_query', 'pre_checkout_query', 'chat_member',
    'message_reaction', 'message_reaction_count', 'poll_answer',
    'channel_post', 'my_chat_member', 'edited_channel_post'
]


def _lock_path() -> str:
    safe_token = settings.bot_token.split(':', 1)[0]
    return os.path.join(tempfile.gettempdir(), f'boostora_{safe_token}.lock')


def _read_lock_pid(path: str) -> int | None:
    try:
        with open(path, 'r', encoding='utf-8') as file:
            raw = file.read().strip().split()[0]
        return int(raw)
    except Exception:
        return None


def _pid_is_alive(pid: int | None) -> bool:
    if not pid or pid <= 0:
        return False
    if pid == os.getpid():
        return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except Exception:
        return True
    return True


def _clear_stale_lock(path: str) -> bool:
    pid = _read_lock_pid(path)
    if _pid_is_alive(pid):
        return False
    try:
        os.unlink(path)
        LOGGER.warning('Removed stale Boostora polling lock: %s', path)
        return True
    except FileNotFoundError:
        return True
    except Exception as exc:
        LOGGER.warning('Could not remove stale polling lock %s: %s', path, exc)
        return False


def _write_lock_payload(fd: int) -> None:
    payload = f'{os.getpid()} {int(time.time())}\n'
    os.write(fd, payload.encode())


def _acquire_single_instance_lock() -> int | None:
    path = _lock_path()
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_RDWR)
        _write_lock_payload(fd)
        return fd
    except FileExistsError:
        if not _clear_stale_lock(path):
            return None
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_RDWR)
            _write_lock_payload(fd)
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
    # Keep third-party polling noise low; transient network timeouts are handled by our retry loop.
    logging.getLogger('TeleBot').setLevel(logging.ERROR)
    logging.getLogger('telebot').setLevel(logging.ERROR)
    logging.getLogger('urllib3').setLevel(logging.WARNING)


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
                AdBroadcastService.run_due_orders(bot, support_username=settings.support_username)
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


def _poll_forever(bot: telebot.TeleBot) -> None:
    """Run polling with our own retry loop so transient Telegram/API timeouts do not spam stack traces or kill the bot."""
    backoff_seconds = 5
    while True:
        try:
            bot.polling(
                non_stop=False,
                skip_pending=True,
                timeout=20,
                long_polling_timeout=20,
                allowed_updates=ALLOWED_UPDATES,
            )
            return
        except ApiTelegramException as exc:
            description = str(exc)
            if 'terminated by other getUpdates request' in description:
                LOGGER.warning(
                    'Polling conflict detected: another bot instance is still using getUpdates. Retrying in %s seconds.',
                    backoff_seconds,
                )
                time.sleep(backoff_seconds)
                continue
            LOGGER.exception('Telegram API error during polling. Retrying in %s seconds.', backoff_seconds)
            time.sleep(backoff_seconds)
            continue
        except (requests.exceptions.ReadTimeout, requests.exceptions.ConnectionError) as exc:
            LOGGER.warning('Telegram network timeout during polling: %s. Retrying in %s seconds.', exc, backoff_seconds)
            time.sleep(backoff_seconds)
            continue
        except requests.exceptions.RequestException as exc:
            LOGGER.warning('Telegram request error during polling: %s. Retrying in %s seconds.', exc, backoff_seconds)
            time.sleep(backoff_seconds)
            continue
        except Exception:
            LOGGER.exception('Unexpected polling error. Retrying in %s seconds.', backoff_seconds)
            time.sleep(backoff_seconds)
            continue


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
        LOGGER.info('%s started', APP_VERSION)
        try:
            _poll_forever(bot)
        finally:
            promo_stop_event.set()
        break
    _release_single_instance_lock(lock_fd)
