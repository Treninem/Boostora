from __future__ import annotations

from aiogram import Bot
from aiogram.enums import ChatMemberStatus
from aiogram.types import CallbackQuery, Message

from app.config import Config
from app.db import Database
from app.i18n import normalize_locale, t
from app.keyboards import advertiser_menu, earner_menu, subscription_keyboard


async def ensure_subscription(bot: Bot, db: Database, config: Config, user_id: int) -> bool:
    if not config.required_chat_id:
        return True
    try:
        member = await bot.get_chat_member(config.required_chat_id, user_id)
        return member.status in {
            ChatMemberStatus.MEMBER,
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.OWNER,
            ChatMemberStatus.RESTRICTED,
        }
    except Exception:
        return False


async def subscription_gate(event: Message | CallbackQuery, db: Database, config: Config) -> bool:
    bot = event.bot
    user_id = event.from_user.id
    user = db.get_user(user_id)
    locale = normalize_locale((user["locale"] if user else None), config.default_language)
    ok = await ensure_subscription(bot, db, config, user_id)
    if ok:
        return True

    text = t(locale, "subscription_required")
    markup = subscription_keyboard(locale, config.required_chat_invite_link or None)
    if isinstance(event, Message):
        await event.answer(text, reply_markup=markup)
    else:
        await event.answer()
        if event.message:
            await event.message.answer(text, reply_markup=markup)
    return False


def role_menu(locale: str, role: str | None, is_admin: bool):
    if role == "advertiser":
        return advertiser_menu(locale, is_admin)
    return earner_menu(locale, is_admin)
