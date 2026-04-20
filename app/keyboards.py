from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.i18n import ROLE_ADVERTISER, ROLE_EARNER, SUPPORTED_LANGUAGES, t


def language_keyboard() -> InlineKeyboardMarkup:
    items = list(SUPPORTED_LANGUAGES.items())
    rows = []
    for i in range(0, len(items), 2):
        pair = items[i:i+2]
        rows.append([InlineKeyboardButton(text=name, callback_data=f'lang:{code}') for code, name in pair])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def role_keyboard(locale: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(locale, 'role_earner'), callback_data=f'role:{ROLE_EARNER}')],
        [InlineKeyboardButton(text=t(locale, 'role_advertiser'), callback_data=f'role:{ROLE_ADVERTISER}')],
    ])


def subscription_keyboard(locale: str, invite_link: str | None) -> InlineKeyboardMarkup:
    rows = []
    if invite_link:
        rows.append([InlineKeyboardButton(text=t(locale, 'join_chat'), url=invite_link)])
    rows.append([InlineKeyboardButton(text=t(locale, 'subscription_check'), callback_data='sub:check')])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def menu_keyboard(locale: str, role: str | None, is_admin: bool) -> InlineKeyboardMarkup:
    if role == ROLE_ADVERTISER:
        rows = [
            [InlineKeyboardButton(text=t(locale, 'profile'), callback_data='menu:profile'), InlineKeyboardButton(text=t(locale, 'wallet'), callback_data='menu:wallet')],
            [InlineKeyboardButton(text=t(locale, 'campaigns'), callback_data='menu:campaigns'), InlineKeyboardButton(text=t(locale, 'analytics'), callback_data='menu:analytics')],
            [InlineKeyboardButton(text=t(locale, 'topup'), callback_data='menu:topup'), InlineKeyboardButton(text=t(locale, 'support'), callback_data='menu:support')],
        ]
    else:
        rows = [
            [InlineKeyboardButton(text=t(locale, 'profile'), callback_data='menu:profile'), InlineKeyboardButton(text=t(locale, 'wallet'), callback_data='menu:wallet')],
            [InlineKeyboardButton(text=t(locale, 'tasks'), callback_data='menu:tasks'), InlineKeyboardButton(text=t(locale, 'rewards'), callback_data='menu:rewards')],
            [InlineKeyboardButton(text=t(locale, 'support'), callback_data='menu:support')],
        ]
    if is_admin:
        rows.append([InlineKeyboardButton(text=t(locale, 'admin'), callback_data='menu:admin')])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def simple_back_keyboard(locale: str, target: str = 'menu:main') -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=t(locale, 'back'), callback_data=target)]])


def tasks_keyboard(locale: str, tasks: list[dict]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=f"#{task['id']} • +{task['reward']} • {task['title'][:20]}", callback_data=f"task:view:{task['id']}")] for task in tasks]
    rows.append([InlineKeyboardButton(text=t(locale, 'back'), callback_data='menu:main')])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def task_keyboard(locale: str, campaign_id: int, target_url: str, taken: bool) -> InlineKeyboardMarkup:
    rows = []
    if target_url:
        rows.append([InlineKeyboardButton(text=t(locale, 'open_target'), url=target_url)])
    rows.append([InlineKeyboardButton(text=t(locale, 'complete_task') if taken else t(locale, 'take_task'), callback_data=f"task:{'done' if taken else 'take'}:{campaign_id}")])
    rows.append([InlineKeyboardButton(text=t(locale, 'back'), callback_data='menu:tasks')])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def campaigns_keyboard(locale: str, campaigns: list[dict]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=t(locale, 'create_demo_campaign'), callback_data='camp:create')]]
    for campaign in campaigns[:10]:
        rows.append([InlineKeyboardButton(text=f"#{campaign['id']} • {campaign['title'][:22]}", callback_data=f"camp:view:{campaign['id']}")])
    rows.append([InlineKeyboardButton(text=t(locale, 'back'), callback_data='menu:main')])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def campaign_keyboard(locale: str) -> InlineKeyboardMarkup:
    return simple_back_keyboard(locale, 'menu:campaigns')


def topup_keyboard(locale: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(locale, 'topup_demo'), callback_data='wallet:topup')],
        [InlineKeyboardButton(text=t(locale, 'back'), callback_data='menu:main')],
    ])
