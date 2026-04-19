from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

from app.i18n import ROLE_ADVERTISER, ROLE_EARNER, SUPPORTED_LANGUAGES, t


def language_keyboard() -> InlineKeyboardMarkup:
    rows = []
    items = list(SUPPORTED_LANGUAGES.items())
    for i in range(0, len(items), 2):
        pair = items[i:i + 2]
        rows.append([
            InlineKeyboardButton(text=name, callback_data=f"lang:{code}")
            for code, name in pair
        ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def role_keyboard(locale: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t(locale, "role_earner"), callback_data=f"role:{ROLE_EARNER}")],
            [InlineKeyboardButton(text=t(locale, "role_advertiser"), callback_data=f"role:{ROLE_ADVERTISER}")],
        ]
    )


def subscription_keyboard(locale: str, invite_link: str | None) -> InlineKeyboardMarkup:
    rows = []
    if invite_link:
        rows.append([InlineKeyboardButton(text=t(locale, "join_chat"), url=invite_link)])
    rows.append([InlineKeyboardButton(text=t(locale, "check_subscription"), callback_data="sub:check")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def earner_menu(locale: str, is_admin: bool) -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text=t(locale, "profile")), KeyboardButton(text=t(locale, "wallet"))],
        [KeyboardButton(text=t(locale, "tasks")), KeyboardButton(text=t(locale, "rewards"))],
        [KeyboardButton(text=t(locale, "support"))],
    ]
    if is_admin:
        rows.append([KeyboardButton(text=t(locale, "admin"))])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def advertiser_menu(locale: str, is_admin: bool) -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text=t(locale, "profile")), KeyboardButton(text=t(locale, "wallet"))],
        [KeyboardButton(text=t(locale, "campaigns")), KeyboardButton(text=t(locale, "analytics"))],
        [KeyboardButton(text=t(locale, "topup")), KeyboardButton(text=t(locale, "support"))],
    ]
    if is_admin:
        rows.append([KeyboardButton(text=t(locale, "admin"))])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def tasks_keyboard(locale: str, tasks: list[dict]) -> InlineKeyboardMarkup:
    rows = []
    for task in tasks:
        rows.append([
            InlineKeyboardButton(
                text=f"{t(locale, 'take_task')} • #{task['id']} • +{task['reward']}",
                callback_data=f"task_take:{task['id']}",
            )
        ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def task_action_keyboard(locale: str, campaign_id: int, target_url: str) -> InlineKeyboardMarkup:
    rows = []
    if target_url:
        rows.append([InlineKeyboardButton(text="Open", url=target_url)])
    rows.append([
        InlineKeyboardButton(text=t(locale, "complete_task"), callback_data=f"task_done:{campaign_id}")
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def campaigns_keyboard(locale: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=t(locale, "create_demo_campaign"), callback_data="camp:create_demo")]]
    )


def topup_keyboard(locale: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=t(locale, "topup_demo"), callback_data="wallet:topup_demo")]]
    )
