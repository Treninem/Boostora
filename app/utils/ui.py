import html
import logging
import re
from typing import Callable

import telebot
from telebot.types import CallbackQuery, InlineKeyboardMarkup, Message

from app.services.ui_state import UIStateService


logger = logging.getLogger(__name__)


ReplyMarkupBuilder = Callable[[int], InlineKeyboardMarkup | None]
TELEGRAM_TEXT_LIMIT = 4096
TELEGRAM_SAFE_TEXT_LIMIT = 3900
_HTML_TAG_RE = re.compile(r'<[^>]+>')


def _extract_message_target(target: CallbackQuery | Message) -> tuple[int, int | None]:
    if isinstance(target, CallbackQuery):
        return int(target.message.chat.id), int(target.message.message_id)
    return int(target.chat.id), None


def _safe_delete(bot: telebot.TeleBot, chat_id: int, message_id: int | None) -> None:
    if message_id is None:
        return
    try:
        bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception:
        return


def _fit_telegram_text(text: str, *, screen_key: str) -> str:
    """Keep managed screens inside Telegram's 4096-character text limit.

    Normal screens preserve their HTML. Oversized diagnostic screens are converted
    to escaped plain text and shortened at a line boundary, so malformed HTML can
    never cause a second failure while handling MESSAGE_TOO_LONG.
    """
    value = str(text or '')
    if len(value) <= TELEGRAM_TEXT_LIMIT:
        return value

    plain = html.unescape(_HTML_TAG_RE.sub('', value))
    suffix = '\n\n… Экран сокращён до лимита Telegram. Подробности сохранены в релизных проверках.'
    budget = max(1, TELEGRAM_SAFE_TEXT_LIMIT - len(suffix))
    shortened = plain[:budget]
    newline = shortened.rfind('\n')
    if newline >= int(budget * 0.65):
        shortened = shortened[:newline]
    prepared = html.escape(shortened.rstrip()) + html.escape(suffix)
    logger.warning(
        'Managed screen %s exceeded Telegram text limit (%s chars); safely shortened to %s chars',
        screen_key,
        len(value),
        len(prepared),
    )
    return prepared


def render_managed_screen(
    bot: telebot.TeleBot,
    *,
    target: CallbackQuery | Message,
    user_id: int | None = None,
    profile_id: int | None = None,
    chat_id: int,
    screen_key: str,
    text: str,
    reply_markup_builder: ReplyMarkupBuilder,
) -> Message | None:
    effective_user_id = user_id if user_id is not None else profile_id
    if effective_user_id is None:
        raise ValueError('render_managed_screen requires user_id or profile_id')
    version = UIStateService.reserve_next_version(effective_user_id, chat_id, screen_key)
    markup = reply_markup_builder(version)
    safe_text = _fit_telegram_text(text, screen_key=screen_key)

    if isinstance(target, CallbackQuery):
        try:
            bot.edit_message_text(
                chat_id=target.message.chat.id,
                message_id=target.message.message_id,
                text=safe_text,
                reply_markup=markup,
            )
            UIStateService.bind_message(effective_user_id, chat_id, target.message.message_id, screen_key, version)
            return None
        except Exception as exc:
            logger.warning('Edit by callback failed, replacing message instead: %s', exc)
            # Send the replacement first. If Telegram rejects it, the old screen is
            # kept instead of being deleted and leaving the user with no navigation.
            sent = bot.send_message(chat_id=chat_id, text=safe_text, reply_markup=markup)
            _safe_delete(bot, int(target.message.chat.id), int(target.message.message_id))
            UIStateService.bind_message(effective_user_id, chat_id, sent.message_id, screen_key, version)
            return sent

    bound = UIStateService.get_bound_message(effective_user_id)
    if bound and bound[0] == chat_id:
        try:
            bot.edit_message_text(
                chat_id=bound[0],
                message_id=bound[1],
                text=safe_text,
                reply_markup=markup,
            )
            UIStateService.bind_message(effective_user_id, chat_id, bound[1], screen_key, version)
            return None
        except Exception as exc:
            logger.warning('Managed edit failed, replacing message instead: %s', exc)
            sent = bot.send_message(chat_id=chat_id, text=safe_text, reply_markup=markup)
            _safe_delete(bot, bound[0], bound[1])
            UIStateService.bind_message(effective_user_id, chat_id, sent.message_id, screen_key, version)
            return sent

    sent = bot.send_message(chat_id=chat_id, text=safe_text, reply_markup=markup)
    UIStateService.bind_message(effective_user_id, chat_id, sent.message_id, screen_key, version)
    return sent
