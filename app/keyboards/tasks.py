from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.core.i18n import t


def tasks_list_keyboard(locale: str, campaign_ids: list[int], active_claims: list[dict] | None = None) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []

    for claim in active_claims or []:
        claim_id = int(claim['id'])
        campaign_id = int(claim['campaign_id'])
        target_url = claim.get('target_url')
        if target_url:
            rows.append([
                InlineKeyboardButton(text=f"{t(locale, 'btn_task_open')} #{campaign_id}", url=str(target_url)),
                InlineKeyboardButton(text=f"{t(locale, 'btn_task_submit')} #{claim_id}", callback_data=f'task:submit:{claim_id}'),
            ])
        else:
            rows.append([InlineKeyboardButton(text=f"{t(locale, 'btn_task_submit')} #{claim_id}", callback_data=f'task:submit:{claim_id}')])

    for campaign_id in campaign_ids:
        rows.append([InlineKeyboardButton(text=f"{t(locale, 'btn_task_take')} #{campaign_id}", callback_data=f'task:take:{campaign_id}')])

    rows.append([InlineKeyboardButton(text=t(locale, 'btn_refresh'), callback_data='task:refresh')])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def task_taken_keyboard(locale: str, claim_id: int, target_url: str | None = None) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if target_url:
        rows.append([InlineKeyboardButton(text=t(locale, 'btn_task_open'), url=target_url)])
    rows.append([InlineKeyboardButton(text=t(locale, 'btn_task_submit'), callback_data=f'task:submit:{claim_id}')])
    rows.append([InlineKeyboardButton(text=t(locale, 'btn_open_tasks'), callback_data='task:refresh')])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def rewards_keyboard(locale: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t(locale, 'btn_process_rewards'), callback_data='reward:process')],
            [InlineKeyboardButton(text=t(locale, 'btn_open_tasks'), callback_data='task:refresh')],
        ]
    )
