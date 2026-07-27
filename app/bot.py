import logging
import os
import signal
import tempfile
import threading
import time
from typing import Any

import requests
import telebot
from telebot.apihelper import ApiTelegramException

from app.config import settings
from app.db import create_periodic_backup, init_db
from app.handlers.start import register_start_handlers
from app.handlers.callbacks import register_callback_handlers
from app.services.promo import PromoService
from app.services.ad_broadcasts import AdBroadcastService
from app.services.engagement_modes import EngagementModeService
from app.services.boostore_provider import BoostoreProviderService
from app.version import APP_VERSION
from app.webapp import WebAppRuntime, start_webapp_server


LOGGER = logging.getLogger(__name__)

ALLOWED_UPDATES = [
    'message', 'callback_query', 'pre_checkout_query', 'chat_member',
    'message_reaction', 'message_reaction_count', 'poll_answer',
    'channel_post', 'my_chat_member', 'edited_channel_post'
]

POLL_TIMEOUT_SECONDS = 25
LONG_POLLING_TIMEOUT_SECONDS = 25
POLLING_BACKOFF_START_SECONDS = 5
POLLING_BACKOFF_MAX_SECONDS = 60
REMOVE_WEBHOOK_ATTEMPTS = 3
TRANSIENT_TELEGRAM_ERROR_CODES = {429, 500, 502, 503, 504}


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
    # TeleBot logs full tracebacks for temporary Telegram/API outages before
    # the exception reaches our retry loop. Keep that noise out of production logs
    # and write compact warnings ourselves.
    logging.getLogger('TeleBot').setLevel(logging.CRITICAL)
    logging.getLogger('telebot').setLevel(logging.CRITICAL)
    logging.getLogger('urllib3').setLevel(logging.WARNING)




def _install_shutdown_handlers(stop_event: threading.Event) -> None:
    """Translate SIGTERM/SIGINT into a shared graceful-shutdown event."""
    handled = {'requested': False}

    def _handle(signum: int, _frame: Any) -> None:
        if not handled['requested']:
            handled['requested'] = True
            try:
                signal_name = signal.Signals(signum).name
            except Exception:
                signal_name = str(signum)
            LOGGER.info('Shutdown requested by %s', signal_name)
        stop_event.set()

    for signal_name in ('SIGTERM', 'SIGINT'):
        signum = getattr(signal, signal_name, None)
        if signum is None:
            continue
        try:
            signal.signal(signum, _handle)
        except (ValueError, OSError, RuntimeError):
            # Signal handlers can only be installed in the main thread and are
            # unavailable on a few restricted runtimes. The bot still keeps its
            # finally-based cleanup as a fallback.
            continue


def _wait_for_shutdown(stop_event: threading.Event, seconds: float) -> bool:
    """Wait with immediate wake-up when deployment shutdown is requested."""
    return stop_event.wait(max(0.0, float(seconds)))


def create_bot() -> telebot.TeleBot:
    bot = telebot.TeleBot(settings.bot_token, parse_mode='HTML', threaded=False)
    register_start_handlers(bot)
    register_callback_handlers(bot)
    return bot



def _run_background_job(name: str, callback: Any) -> Any:
    """Run one maintenance job without starving the rest of the cycle."""
    try:
        return callback()
    except Exception:
        LOGGER.exception('Background job %s failed; remaining jobs will continue', name)
        return None


def _run_background_cycle(bot: telebot.TeleBot) -> None:
    jobs: list[tuple[str, Any]] = [
        ('promotions', lambda: PromoService.run_due_promotions(bot)),
        ('ad_broadcasts', lambda: AdBroadcastService.run_due_orders(bot, support_username=settings.support_username)),
        ('engagement_reminders', lambda: EngagementModeService.run_due_reminders(
            bot,
            admin_ids=settings.admin_ids,
            support_username=settings.support_username,
        )),
        ('database_backup', create_periodic_backup),
    ]
    if settings.boostore_enabled:
        jobs.append(('boostore_status_sync', lambda: BoostoreProviderService.sync_order_statuses(limit=20)))

    for name, callback in jobs:
        result = _run_background_job(name, callback)
        if name == 'database_backup' and result is not None:
            LOGGER.info('Periodic SQLite backup created: %s', result)


def _start_promo_worker(bot: telebot.TeleBot, stop_event: threading.Event) -> threading.Thread:
    def _worker() -> None:
        while not stop_event.is_set():
            _run_background_cycle(bot)
            stop_event.wait(settings.background_worker_interval_seconds)

    thread = threading.Thread(target=_worker, name='promo-worker', daemon=True)
    thread.start()
    return thread




def _configure_telegram_menu(bot: telebot.TeleBot, stop_event: threading.Event) -> None:
    """Publish the global Telegram menu button for the embedded Mini App."""
    if not settings.mini_app_url:
        LOGGER.warning('Telegram Mini App menu button was not configured: public URL is empty')
        return

    try:
        from telebot.types import MenuButtonWebApp, WebAppInfo
    except ImportError:
        LOGGER.warning('Current pyTelegramBotAPI build has no MenuButtonWebApp support')
        return

    menu_button = MenuButtonWebApp(
        text=settings.brand_name[:64],
        web_app=WebAppInfo(url=settings.mini_app_url),
    )
    delay = POLLING_BACKOFF_START_SECONDS
    for attempt in range(1, REMOVE_WEBHOOK_ATTEMPTS + 1):
        if stop_event.is_set():
            return
        try:
            bot.set_chat_menu_button(menu_button=menu_button)
            LOGGER.info('Telegram Mini App menu button configured')
            return
        except Exception as exc:
            if attempt >= REMOVE_WEBHOOK_ATTEMPTS:
                LOGGER.warning(
                    'Could not configure Telegram Mini App menu button after %s attempts: %s',
                    REMOVE_WEBHOOK_ATTEMPTS,
                    _short_error(exc),
                )
                return
            LOGGER.warning(
                'Could not configure Telegram Mini App menu button, attempt %s/%s: %s',
                attempt,
                REMOVE_WEBHOOK_ATTEMPTS,
                _short_error(exc),
            )
            if _wait_for_shutdown(stop_event, delay):
                return
            delay = _next_backoff(delay)


def _remove_webhook_once(bot: telebot.TeleBot) -> None:
    """Remove webhook with compatibility for different pyTelegramBotAPI versions."""
    try:
        bot.remove_webhook(drop_pending_updates=False)
    except TypeError:
        bot.remove_webhook()


def _prepare_bot(bot: telebot.TeleBot, stop_event: threading.Event | None = None) -> None:
    """Prepare polling without failing the whole bot on temporary Telegram timeouts."""
    delay = POLLING_BACKOFF_START_SECONDS
    last_error: Exception | None = None
    effective_stop = stop_event or threading.Event()
    for attempt in range(1, REMOVE_WEBHOOK_ATTEMPTS + 1):
        try:
            _remove_webhook_once(bot)
            LOGGER.info('Webhook removed before polling start')
            return
        except Exception as exc:
            last_error = exc
            if attempt >= REMOVE_WEBHOOK_ATTEMPTS:
                break
            LOGGER.warning(
                'Could not remove webhook before polling, attempt %s/%s: %s. Retrying in %s seconds.',
                attempt,
                REMOVE_WEBHOOK_ATTEMPTS,
                _short_error(exc),
                delay,
            )
            if _wait_for_shutdown(effective_stop, delay):
                return
            delay = _next_backoff(delay)
    LOGGER.warning(
        'Could not remove webhook before polling after %s attempts: %s. Polling will continue.',
        REMOVE_WEBHOOK_ATTEMPTS,
        _short_error(last_error),
    )


def _short_error(exc: Exception | None) -> str:
    if exc is None:
        return 'unknown error'
    text = str(exc).strip().replace('\n', ' ')
    return text[:300] if text else exc.__class__.__name__


def _telegram_error_code(exc: ApiTelegramException) -> int | None:
    for attr in ('error_code', 'error_code_'):
        value = getattr(exc, attr, None)
        if isinstance(value, int):
            return value
    result_json = getattr(exc, 'result_json', None)
    if isinstance(result_json, dict):
        value = result_json.get('error_code')
        if isinstance(value, int):
            return value
    return None


def _telegram_retry_after(exc: ApiTelegramException) -> int | None:
    result_json = getattr(exc, 'result_json', None)
    if isinstance(result_json, dict):
        params = result_json.get('parameters') or {}
        value = params.get('retry_after') if isinstance(params, dict) else None
        if isinstance(value, int) and value > 0:
            return min(value, POLLING_BACKOFF_MAX_SECONDS)
    return None


def _is_polling_conflict(exc: ApiTelegramException) -> bool:
    return 'terminated by other getUpdates request' in str(exc)


def _next_backoff(current: int) -> int:
    return min(POLLING_BACKOFF_MAX_SECONDS, max(POLLING_BACKOFF_START_SECONDS, int(current * 1.7)))


def _get_updates_compat(
    bot: telebot.TeleBot,
    *,
    offset: int | None,
    timeout: int,
    long_polling_timeout: int,
) -> list[Any]:
    """Call get_updates across pyTelegramBotAPI versions without using TeleBot polling logger."""
    try:
        return bot.get_updates(
            offset=offset,
            timeout=timeout,
            long_polling_timeout=long_polling_timeout,
            allowed_updates=ALLOWED_UPDATES,
        )
    except TypeError:
        return bot.get_updates(
            offset=offset,
            timeout=timeout,
            allowed_updates=ALLOWED_UPDATES,
        )


def _drop_pending_updates(bot: telebot.TeleBot) -> int | None:
    """Best-effort skip_pending replacement for the controlled polling loop."""
    try:
        updates = _get_updates_compat(
            bot,
            offset=-1,
            timeout=1,
            long_polling_timeout=1,
        )
        if updates:
            LOGGER.info('Dropped %s pending Telegram updates before polling', len(updates))
        return None
    except Exception as exc:
        LOGGER.warning('Could not drop pending Telegram updates before polling: %s', _short_error(exc))
        return None


def _next_offset_from_updates(updates: list[Any]) -> int | None:
    max_update_id = None
    for update in updates:
        update_id = getattr(update, 'update_id', None)
        if isinstance(update_id, int):
            max_update_id = update_id if max_update_id is None else max(max_update_id, update_id)
    return None if max_update_id is None else max_update_id + 1


def _process_updates(bot: telebot.TeleBot, updates: list[Any]) -> int | None:
    """Process updates one by one so one poisoned handler cannot drop its batch peers."""
    if not updates:
        return None

    next_offset: int | None = None
    for update in updates:
        update_id = getattr(update, 'update_id', None)
        if isinstance(update_id, int):
            candidate_offset = update_id + 1
            next_offset = candidate_offset if next_offset is None else max(next_offset, candidate_offset)
        try:
            bot.process_new_updates([update])
        except Exception:
            LOGGER.exception(
                'Update handler error for update_id=%s. Only this update is skipped; the rest of the batch continues.',
                update_id if isinstance(update_id, int) else 'unknown',
            )
    return next_offset


def _initial_poll_offset(bot: telebot.TeleBot) -> int | None:
    """Choose whether startup should preserve or intentionally skip queued updates."""
    if settings.drop_pending_updates:
        LOGGER.warning('DROP_PENDING_UPDATES=1: queued Telegram updates will be skipped once at startup')
        return _drop_pending_updates(bot)
    LOGGER.info('Queued Telegram updates are preserved after restart')
    return None


def _poll_forever(bot: telebot.TeleBot, stop_event: threading.Event | None = None) -> None:
    """Run a quiet controlled long-polling loop.

    pyTelegramBotAPI's built-in polling logs full tracebacks for temporary 502/timeout
    issues before re-raising. The custom loop keeps the bot alive and writes compact,
    useful warnings instead. This is important on Bothost where Telegram API 502 and
    read timeouts can appear for a few minutes while the bot itself is healthy.
    """
    effective_stop = stop_event or threading.Event()
    offset = _initial_poll_offset(bot)
    backoff_seconds = POLLING_BACKOFF_START_SECONDS
    network_failures = 0

    while not effective_stop.is_set():
        try:
            updates = _get_updates_compat(
                bot,
                offset=offset,
                timeout=POLL_TIMEOUT_SECONDS,
                long_polling_timeout=LONG_POLLING_TIMEOUT_SECONDS,
            )
            next_offset = _process_updates(bot, updates)
            if next_offset is not None:
                offset = next_offset
            if network_failures:
                LOGGER.info('Telegram polling recovered after %s temporary network/API errors', network_failures)
            network_failures = 0
            backoff_seconds = POLLING_BACKOFF_START_SECONDS
        except ApiTelegramException as exc:
            code = _telegram_error_code(exc)
            retry_after = _telegram_retry_after(exc)
            if _is_polling_conflict(exc):
                network_failures += 1
                LOGGER.warning(
                    'Telegram polling conflict: another getUpdates session is active. Retrying in %s seconds.',
                    backoff_seconds,
                )
            elif code in TRANSIENT_TELEGRAM_ERROR_CODES:
                network_failures += 1
                delay = retry_after or backoff_seconds
                LOGGER.warning(
                    'Temporary Telegram API error%s during polling: %s. Retrying in %s seconds.',
                    f' {code}' if code else '',
                    _short_error(exc),
                    delay,
                )
                if _wait_for_shutdown(effective_stop, delay):
                    break
                backoff_seconds = _next_backoff(delay)
                continue
            else:
                network_failures += 1
                LOGGER.warning(
                    'Telegram API error%s during polling: %s. Retrying in %s seconds.',
                    f' {code}' if code else '',
                    _short_error(exc),
                    backoff_seconds,
                )
            if _wait_for_shutdown(effective_stop, backoff_seconds):
                break
            backoff_seconds = _next_backoff(backoff_seconds)
        except (requests.exceptions.ReadTimeout, requests.exceptions.ConnectTimeout, requests.exceptions.ConnectionError) as exc:
            network_failures += 1
            LOGGER.warning(
                'Telegram network timeout during polling: %s. Retrying in %s seconds.',
                _short_error(exc),
                backoff_seconds,
            )
            if _wait_for_shutdown(effective_stop, backoff_seconds):
                break
            backoff_seconds = _next_backoff(backoff_seconds)
        except requests.exceptions.RequestException as exc:
            network_failures += 1
            LOGGER.warning(
                'Telegram request error during polling: %s. Retrying in %s seconds.',
                _short_error(exc),
                backoff_seconds,
            )
            if _wait_for_shutdown(effective_stop, backoff_seconds):
                break
            backoff_seconds = _next_backoff(backoff_seconds)
        except KeyboardInterrupt:
            LOGGER.info('Polling stopped by KeyboardInterrupt')
            effective_stop.set()
            break
        except Exception:
            LOGGER.exception('Unexpected polling error. Retrying in %s seconds.', backoff_seconds)
            if _wait_for_shutdown(effective_stop, backoff_seconds):
                break
            backoff_seconds = _next_backoff(backoff_seconds)


def run() -> None:
    configure_logging()
    shutdown_event = threading.Event()
    _install_shutdown_handlers(shutdown_event)
    init_db()

    lock_fd: int | None = None
    promo_thread: threading.Thread | None = None
    webapp_runtime: WebAppRuntime | None = None
    try:
        while lock_fd is None and not shutdown_event.is_set():
            lock_fd = _acquire_single_instance_lock()
            if lock_fd is None:
                LOGGER.warning('Another local bot process is already running. Retrying in 5 seconds.')
                _wait_for_shutdown(shutdown_event, 5)

        if shutdown_event.is_set():
            return

        webapp_runtime = start_webapp_server()
        bot = create_bot()
        _prepare_bot(bot, shutdown_event)
        if shutdown_event.is_set():
            return
        _configure_telegram_menu(bot, shutdown_event)
        if shutdown_event.is_set():
            return
        promo_thread = _start_promo_worker(bot, shutdown_event)
        LOGGER.info('%s started with update guard', APP_VERSION)
        _poll_forever(bot, shutdown_event)
    finally:
        shutdown_event.set()
        if promo_thread is not None and promo_thread.is_alive():
            promo_thread.join(timeout=5)
        if webapp_runtime is not None:
            webapp_runtime.stop()
        _release_single_instance_lock(lock_fd)
        LOGGER.info('%s stopped cleanly', APP_VERSION)

