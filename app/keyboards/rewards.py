from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.core.i18n import t
from app.core.reward_catalog import RewardCatalogItem


def rewards_keyboard(locale: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t(locale, 'btn_process_rewards'), callback_data='reward:process')],
            [InlineKeyboardButton(text=t(locale, 'btn_reward_shop'), callback_data='reward:shop')],
            [
                InlineKeyboardButton(text=t(locale, 'btn_vip_center'), callback_data='reward:vip'),
                InlineKeyboardButton(text=t(locale, 'btn_referral_center'), callback_data='reward:referrals'),
            ],
            [InlineKeyboardButton(text=t(locale, 'btn_open_tasks'), callback_data='task:refresh')],
        ]
    )


def reward_shop_keyboard(locale: str, items: list[RewardCatalogItem]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for item in items:
        rows.append([
            InlineKeyboardButton(
                text=t(locale, 'btn_redeem_item', cost=item.cost),
                callback_data=f'reward:redeem:{item.code}',
            )
        ])
    rows.append([InlineKeyboardButton(text=t(locale, 'btn_back_rewards'), callback_data='reward:back')])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def reward_back_keyboard(locale: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=t(locale, 'btn_back_rewards'), callback_data='reward:back')]]
    )
