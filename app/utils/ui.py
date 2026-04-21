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



def render_managed_screen(
    bot: telebot.TeleBot,
    *,
    target: CallbackQuery | Message,
    user_id: int,
    chat_id: int,
    screen_key: str,
    text: str,
    reply_markup_builder: ReplyMarkupBuilder,
) -> Message | None:
    version = UIStateService.reserve_next_version(user_id, chat_id, screen_key)
    markup = reply_markup_builder(version)

    if isinstance(target, CallbackQuery):
        try:
            bot.edit_message_text(
                chat_id=target.message.chat.id,
                message_id=target.message.message_id,
                text=text,
                reply_markup=markup,
            )
            UIStateService.bind_message(user_id, chat_id, target.message.message_id, screen_key, version)
            return None
        except Exception as exc:
            logger.warning('Edit by callback failed, sending new message instead: %s', exc)
            sent = bot.send_message(chat_id=chat_id, text=text, reply_markup=markup)
            UIStateService.bind_message(user_id, chat_id, sent.message_id, screen_key, version)
            return sent

    bound = UIStateService.get_bound_message(user_id)
    if bound and bound[0] == chat_id:
        try:
            bot.edit_message_text(
                chat_id=bound[0],
                message_id=bound[1],
                text=text,
                reply_markup=markup,
            )
            UIStateService.bind_message(user_id, chat_id, bound[1], screen_key, version)
            return None
        except Exception as exc:
            logger.warning('Managed edit failed, sending new message instead: %s', exc)

    sent = bot.send_message(chat_id=chat_id, text=text, reply_markup=markup)
    UIStateService.bind_message(user_id, chat_id, sent.message_id, screen_key, version)
    return sent
