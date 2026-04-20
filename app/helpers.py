from __future__ import annotations

from aiogram import Bot
from aiogram.enums import ChatMemberStatus
from aiogram.types import CallbackQuery, Message

from app.config import Config
from app.db import Database
from app.i18n import normalize_locale, t
from app.keyboards import menu_keyboard, subscription_keyboard
from app.ui import answer_or_edit


async def ensure_subscription(bot: Bot, config: Config, user_id: int) -> bool:
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
    if not config.required_chat_id:
        return True
    # If user interacts inside the mandatory chat itself, do not block them.
    current_chat = getattr(event, 'chat', None)
    if current_chat and int(current_chat.id) == int(config.required_chat_id):
        return True
    if isinstance(event, CallbackQuery) and event.message and int(event.message.chat.id) == int(config.required_chat_id):
        return True

    user_id = event.from_user.id
    user = db.get_user(user_id)
    locale = normalize_locale((user['locale'] if user else None), config.default_language)
    ok = await ensure_subscription(event.bot, config, user_id)
    if ok:
        return True

    await answer_or_edit(event, t(locale, 'subscription_required'), subscription_keyboard(locale, config.required_chat_invite_link or None))
    return False


def main_menu_text(locale: str, role: str) -> str:
    return t(locale, 'menu_advertiser') if role == 'advertiser' else t(locale, 'menu_earner')


def main_menu_markup(locale: str, role: str, is_admin: bool):
    return menu_keyboard(locale, role, is_admin)
