from __future__ import annotations

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, Message

from app.db import Database


async def _edit_message(message: Message, text: str, reply_markup=None) -> bool:
    try:
        await message.edit_text(text, reply_markup=reply_markup)
        return True
    except TelegramBadRequest as e:
        msg = str(e).lower()
        if 'message is not modified' in msg:
            try:
                await message.edit_reply_markup(reply_markup=reply_markup)
            except TelegramBadRequest:
                pass
            return True
        if 'message to edit not found' in msg or 'there is no text in the message to edit' in msg or 'message can\'t be edited' in msg:
            return False
        raise


async def render_panel(event: Message | CallbackQuery, db: Database, text: str, reply_markup=None) -> None:
    if isinstance(event, CallbackQuery) and event.message:
        await _edit_message(event.message, text, reply_markup)
        return

    message: Message = event
    chat_id = message.chat.id
    user_id = message.from_user.id
    panel_id = db.get_panel_message(user_id, chat_id)

    try:
        await message.delete()
    except Exception:
        pass

    if panel_id:
        try:
            panel_message = await message.bot.edit_message_text(
                chat_id=chat_id,
                message_id=panel_id,
                text=text,
                reply_markup=reply_markup,
            )
            db.set_panel_message(user_id, chat_id, panel_message.message_id)
            return
        except TelegramBadRequest:
            db.clear_panel_message(user_id, chat_id)

    sent = await message.answer(text, reply_markup=reply_markup)
    db.set_panel_message(user_id, chat_id, sent.message_id)
