from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.core.i18n import t


REJECT_REASONS = ('fraud', 'low_quality', 'duplicate')


def admin_panel_keyboard(locale: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t(locale, 'btn_admin_reviews'), callback_data='admin:reviews')],
            [InlineKeyboardButton(text=t(locale, 'btn_admin_users'), callback_data='admin:users')],
            [InlineKeyboardButton(text=t(locale, 'btn_admin_stats'), callback_data='admin:stats')],
            [InlineKeyboardButton(text=t(locale, 'btn_admin_events'), callback_data='admin:events')],
            [InlineKeyboardButton(text=t(locale, 'btn_refresh'), callback_data='admin:panel')],
        ]
    )


def admin_reviews_keyboard(locale: str, claims: list[dict]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for claim in claims:
        label = f"#{claim['id']} • {claim['reward_amount']} • {str(claim.get('username') or claim.get('first_name') or claim['user_id'])[:16]}"
        rows.append([InlineKeyboardButton(text=label, callback_data=f"admin:claim:{claim['id']}")])
    rows.append([InlineKeyboardButton(text=t(locale, 'btn_back_admin'), callback_data='admin:panel')])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_claim_keyboard(locale: str, claim_id: int, user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=t(locale, 'btn_admin_approve'), callback_data=f'admin:approve:{claim_id}'),
                InlineKeyboardButton(text=t(locale, 'btn_admin_user_card'), callback_data=f'admin:user:{user_id}'),
            ],
            [
                InlineKeyboardButton(text=t(locale, 'btn_admin_reject_fraud'), callback_data=f'admin:reject:{claim_id}:fraud'),
                InlineKeyboardButton(text=t(locale, 'btn_admin_reject_low_quality'), callback_data=f'admin:reject:{claim_id}:low_quality'),
            ],
            [InlineKeyboardButton(text=t(locale, 'btn_admin_reject_duplicate'), callback_data=f'admin:reject:{claim_id}:duplicate')],
            [InlineKeyboardButton(text=t(locale, 'btn_back_admin_reviews'), callback_data='admin:reviews')],
        ]
    )


def admin_users_keyboard(locale: str, users: list[dict]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for user in users:
        badge = '⛔ ' if int(user.get('is_blocked', 0) or 0) else ''
        label = f"{badge}#{user['user_id']} • {str(user.get('username') or user.get('first_name') or user['user_id'])[:14]} • R{user.get('risk_score', 0)}"
        rows.append([InlineKeyboardButton(text=label, callback_data=f"admin:user:{user['user_id']}")])
    rows.append([InlineKeyboardButton(text=t(locale, 'btn_back_admin'), callback_data='admin:panel')])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_user_keyboard(locale: str, user_id: int, is_blocked: bool) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t(locale, 'btn_admin_unblock') if is_blocked else t(locale, 'btn_admin_block'),
                    callback_data=f"admin:{'unblock' if is_blocked else 'block'}:{user_id}",
                ),
                InlineKeyboardButton(text=t(locale, 'btn_admin_credit'), callback_data=f'admin:credit:{user_id}:50'),
                InlineKeyboardButton(text=t(locale, 'btn_admin_debit'), callback_data=f'admin:credit:{user_id}:-50'),
            ],
            [
                InlineKeyboardButton(text=t(locale, 'btn_admin_risk_down'), callback_data=f'admin:risk:{user_id}:-10'),
                InlineKeyboardButton(text=t(locale, 'btn_admin_risk_up'), callback_data=f'admin:risk:{user_id}:10'),
            ],
            [InlineKeyboardButton(text=t(locale, 'btn_back_admin_users'), callback_data='admin:users')],
        ]
    )


def admin_events_keyboard(locale: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t(locale, 'btn_back_admin'), callback_data='admin:panel')],
        ]
    )
