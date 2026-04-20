from __future__ import annotations

from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import CallbackQuery, Message

from app.config import Config
from app.db import Database
from app.i18n import normalize_locale, t
from app.keyboards import subscription_keyboard
from app.ui import render_panel


async def ensure_subscription(bot, config: Config, user_id: int) -> tuple[bool, str | None]:
    if not config.required_chat_id:
        return True, None
    try:
        member = await bot.get_chat_member(config.required_chat_id, user_id)
        status = member.status
        if status in {ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER, ChatMemberStatus.MEMBER}:
            return True, None
        if status == ChatMemberStatus.RESTRICTED and getattr(member, 'is_member', False):
            return True, None
        return False, None
    except (TelegramBadRequest, TelegramForbiddenError):
        return False, 'cannot_verify'
    except Exception:
        return False, 'cannot_verify'


async def pass_subscription_gate(event: Message | CallbackQuery, db: Database, config: Config) -> bool:
    if not config.required_chat_id:
        return True

    current_chat_id = None
    if isinstance(event, Message):
        current_chat_id = event.chat.id
    elif event.message:
        current_chat_id = event.message.chat.id

    if current_chat_id is not None and int(current_chat_id) == int(config.required_chat_id):
        return True

    user = db.get_user(event.from_user.id)
    locale = normalize_locale(user['locale'] if user else None, config.default_language)
    ok, reason = await ensure_subscription(event.bot, config, event.from_user.id)
    if ok:
        return True

    text = t(locale, 'subscription_cannot_verify') if reason == 'cannot_verify' else t(locale, 'subscription_required')
    await render_panel(event, db, text, subscription_keyboard(locale, config.required_chat_invite_link or None))
    return False
