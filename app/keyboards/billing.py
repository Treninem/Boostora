
from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.core.i18n import t
from app.core.monetization import TOPUP_PACKS, VIP_PACKS



def topup_keyboard(locale: str, enable_demo: bool = True, enable_xtr: bool = True) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if enable_xtr:
        for pack in TOPUP_PACKS:
            rows.append([
                InlineKeyboardButton(
                    text=t(locale, 'btn_topup_xtr_pack', amount=pack.xtr_amount, credits=pack.credit_amount),
                    callback_data=f'billing:topup:{pack.code}',
                )
            ])
    if enable_demo:
        for amount in (500, 2000, 5000):
            rows.append([
                InlineKeyboardButton(
                    text=t(locale, 'btn_topup_demo_pack', amount=amount),
                    callback_data=f'topup:{amount}',
                )
            ])
    return InlineKeyboardMarkup(inline_keyboard=rows)



def vip_center_keyboard(locale: str, enable_xtr: bool = True) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    rows.append([InlineKeyboardButton(text=t(locale, 'btn_redeem_item', cost=80), callback_data='reward:redeem:vip_7d')])
    rows.append([InlineKeyboardButton(text=t(locale, 'btn_redeem_item', cost=260), callback_data='reward:redeem:vip_30d')])
    if enable_xtr:
        for pack in VIP_PACKS:
            rows.append([
                InlineKeyboardButton(
                    text=t(locale, 'btn_vip_xtr_pack', amount=pack.xtr_amount, days=pack.duration_days),
                    callback_data=f'billing:vip:{pack.code}',
                )
            ])
    rows.append([InlineKeyboardButton(text=t(locale, 'btn_back_rewards'), callback_data='reward:back')])
    return InlineKeyboardMarkup(inline_keyboard=rows)
