from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.core.i18n import t


def subscription_required_keyboard(locale: str, invite_link: str | None = None) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    invite_link = (invite_link or '').strip()
    if invite_link:
        rows.append([InlineKeyboardButton(text=t(locale, 'btn_join_required_chat'), url=invite_link)])
    rows.append([InlineKeyboardButton(text=t(locale, 'btn_check_subscription'), callback_data='subscription:check')])
    return InlineKeyboardMarkup(inline_keyboard=rows)
