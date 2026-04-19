from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.core.i18n import t


def campaign_task_type_keyboard(locale: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t(locale, 'task_type_channel_join'), callback_data='camp:new:type:channel_join')],
            [InlineKeyboardButton(text=t(locale, 'task_type_post_view'), callback_data='camp:new:type:post_view')],
            [InlineKeyboardButton(text=t(locale, 'task_type_bot_start'), callback_data='camp:new:type:bot_start')],
            [InlineKeyboardButton(text=t(locale, 'task_type_mini_app_open'), callback_data='camp:new:type:mini_app_open')],
            [InlineKeyboardButton(text=t(locale, 'btn_cancel'), callback_data='camp:new:cancel')],
        ]
    )



def campaigns_keyboard(locale: str, campaigns: list[dict]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for campaign in campaigns:
        campaign_id = int(campaign['id'])
        rows.append([
            InlineKeyboardButton(text=f"{t(locale, 'btn_campaign_view')} #{campaign_id}", callback_data=f'camp:view:{campaign_id}')
        ])
        status = str(campaign.get('status') or 'draft')
        if status == 'draft':
            rows.append([
                InlineKeyboardButton(text=t(locale, 'btn_campaign_launch'), callback_data=f'camp:launch:{campaign_id}')
            ])
        elif status == 'active':
            rows.append([
                InlineKeyboardButton(text=t(locale, 'btn_campaign_pause'), callback_data=f'camp:pause:{campaign_id}')
            ])
        elif status == 'paused':
            rows.append([
                InlineKeyboardButton(text=t(locale, 'btn_campaign_resume'), callback_data=f'camp:resume:{campaign_id}')
            ])
    rows.append([InlineKeyboardButton(text=t(locale, 'btn_refresh'), callback_data='camp:list')])
    return InlineKeyboardMarkup(inline_keyboard=rows)



def campaign_detail_keyboard(locale: str, campaign: dict) -> InlineKeyboardMarkup:
    campaign_id = int(campaign['id'])
    status = str(campaign.get('status') or 'draft')
    rows: list[list[InlineKeyboardButton]] = []
    if status == 'draft':
        rows.append([InlineKeyboardButton(text=t(locale, 'btn_campaign_launch'), callback_data=f'camp:launch:{campaign_id}')])
    elif status == 'active':
        rows.append([InlineKeyboardButton(text=t(locale, 'btn_campaign_pause'), callback_data=f'camp:pause:{campaign_id}')])
    elif status == 'paused':
        rows.append([InlineKeyboardButton(text=t(locale, 'btn_campaign_resume'), callback_data=f'camp:resume:{campaign_id}')])
    rows.append([InlineKeyboardButton(text=t(locale, 'btn_back_to_campaigns'), callback_data='camp:list')])
    return InlineKeyboardMarkup(inline_keyboard=rows)



def topup_keyboard(locale: str) -> InlineKeyboardMarkup:
    packs = [500, 2000, 5000]
    rows = [
        [InlineKeyboardButton(text=t(locale, 'topup_pack', amount=amount), callback_data=f'topup:{amount}')]
        for amount in packs
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)
