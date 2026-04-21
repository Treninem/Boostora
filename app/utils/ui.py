import logging
from typing import Callable

import telebot
from telebot.types import CallbackQuery, InlineKeyboardMarkup, Message

from app.services.ui_state import UIStateService


logger = logging.getLogger(__name__)


ReplyMarkupBuilder = Callable[[int], InlineKeyboardMarkup | None]



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

    if isinstance(target, CallbackQuery):
        try:
            bot.edit_message_text(
                chat_id=target.message.chat.id,
                message_id=target.message.message_id,
                text=text,
                reply_markup=markup,
            )
            UIStateService.bind_message(effective_user_id, chat_id, target.message.message_id, screen_key, version)
            return None
        except Exception as exc:
            logger.warning('Edit by callback failed, replacing message instead: %s', exc)
            _safe_delete(bot, int(target.message.chat.id), int(target.message.message_id))
            sent = bot.send_message(chat_id=chat_id, text=text, reply_markup=markup)
            UIStateService.bind_message(effective_user_id, chat_id, sent.message_id, screen_key, version)
            return sent

    bound = UIStateService.get_bound_message(effective_user_id)
    if bound and bound[0] == chat_id:
        try:
            bot.edit_message_text(
                chat_id=bound[0],
                message_id=bound[1],
                text=text,
                reply_markup=markup,
            )
            UIStateService.bind_message(effective_user_id, chat_id, bound[1], screen_key, version)
            return None
        except Exception as exc:
            logger.warning('Managed edit failed, replacing message instead: %s', exc)
            _safe_delete(bot, bound[0], bound[1])

    sent = bot.send_message(chat_id=chat_id, text=text, reply_markup=markup)
    UIStateService.bind_message(effective_user_id, chat_id, sent.message_id, screen_key, version)
    return sent
