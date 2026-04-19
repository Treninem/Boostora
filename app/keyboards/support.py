from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.core.i18n import t


def support_keyboard(locale: str, support_url: str | None = None) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text=t(locale, 'btn_support_faq'), callback_data='support:faq')],
        [
            InlineKeyboardButton(text=t(locale, 'btn_support_safety'), callback_data='support:safety'),
            InlineKeyboardButton(text=t(locale, 'btn_support_earn'), callback_data='support:earn'),
        ],
        [InlineKeyboardButton(text=t(locale, 'btn_support_promote'), callback_data='support:promote')],
    ]
    if support_url:
        rows.append([InlineKeyboardButton(text=t(locale, 'btn_support_contact'), url=support_url)])
    rows.append([InlineKeyboardButton(text=t(locale, 'btn_home'), callback_data='support:home')])
    return InlineKeyboardMarkup(inline_keyboard=rows)
