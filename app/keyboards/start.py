from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

from app.core.i18n import SUPPORTED_LOCALES, t


def language_keyboard() -> InlineKeyboardMarkup:
    rows = []
    row = []
    for code, title in SUPPORTED_LOCALES.items():
        row.append(InlineKeyboardButton(text=title, callback_data=f'lang:{code}'))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def role_keyboard(locale: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t(locale, 'role_earner'), callback_data='role:earner')],
            [InlineKeyboardButton(text=t(locale, 'role_advertiser'), callback_data='role:advertiser')],
        ]
    )


def earner_menu(locale: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=t(locale, 'menu_tasks')), KeyboardButton(text=t(locale, 'menu_wallet'))],
            [KeyboardButton(text=t(locale, 'menu_rewards')), KeyboardButton(text=t(locale, 'menu_profile'))],
            [KeyboardButton(text=t(locale, 'menu_support')), KeyboardButton(text=t(locale, 'btn_change_language'))],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def advertiser_menu(locale: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=t(locale, 'menu_create_campaign')), KeyboardButton(text=t(locale, 'menu_campaigns'))],
            [KeyboardButton(text=t(locale, 'menu_analytics')), KeyboardButton(text=t(locale, 'menu_topup'))],
            [KeyboardButton(text=t(locale, 'menu_profile')), KeyboardButton(text=t(locale, 'menu_support'))],
            [KeyboardButton(text=t(locale, 'btn_change_language'))],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )
