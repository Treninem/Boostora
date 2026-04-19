from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from app.core.i18n import get_currency_name, normalize_locale, t
from app.keyboards.admin import (
    admin_claim_keyboard,
    admin_events_keyboard,
    admin_panel_keyboard,
    admin_reviews_keyboard,
    admin_user_keyboard,
    admin_users_keyboard,
)
from app.storage.admin import AdminRepository
from app.storage.campaigns import CampaignRepository
from app.storage.memberships import MembershipRepository
from app.storage.referrals import ReferralRepository
from app.storage.task_claims import TaskClaimRepository
from app.storage.users import UserRepository
from app.storage.wallets import WalletRepository

router = Router(name='admin')


async def _users(message_or_callback: Message | CallbackQuery) -> UserRepository:
    return message_or_callback.bot['users_repo']


async def _wallets(message_or_callback: Message | CallbackQuery) -> WalletRepository:
    return message_or_callback.bot['wallets_repo']


async def _campaigns(message_or_callback: Message | CallbackQuery) -> CampaignRepository:
    return message_or_callback.bot['campaigns_repo']


async def _claims(message_or_callback: Message | CallbackQuery) -> TaskClaimRepository:
    return message_or_callback.bot['task_claims_repo']


async def _referrals(message_or_callback: Message | CallbackQuery) -> ReferralRepository:
    return message_or_callback.bot['referrals_repo']


async def _memberships(message_or_callback: Message | CallbackQuery) -> MembershipRepository:
    return message_or_callback.bot['memberships_repo']


async def _admin_repo(message_or_callback: Message | CallbackQuery) -> AdminRepository:
    return message_or_callback.bot['admin_repo']


async def _is_admin(message_or_callback: Message | CallbackQuery) -> bool:
    user_id = message_or_callback.from_user.id if message_or_callback.from_user else 0
    if user_id in message_or_callback.bot['settings'].admin_ids:
        return True
    user = await (await _users(message_or_callback)).get_user(user_id)
    return bool(int((user or {}).get('is_admin', 0) or 0))


async def _get_admin_context(message_or_callback: Message | CallbackQuery) -> tuple[dict, str]:
    users_repo = await _users(message_or_callback)
    user = await users_repo.get_user(message_or_callback.from_user.id if message_or_callback.from_user else 0)
    locale = normalize_locale((user or {}).get('locale'))
    return user or {}, locale


def _task_type_label(locale: str, task_type: str) -> str:
    return t(locale, f'task_type_{task_type}')


def _format_dt(locale: str, value: str | None) -> str:
    if not value:
        return '—'
    try:
        dt = datetime.strptime(value, '%Y-%m-%d %H:%M:%S')
        return dt.strftime('%d.%m %H:%M') if locale == 'ru' else dt.strftime('%Y-%m-%d %H:%M')
    except ValueError:
        return value


def _load_proof(payload: str | None) -> dict:
    if not payload:
        return {}
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        return {}


async def _notify_user(bot, user_id: int, text: str) -> None:
    try:
        await bot.send_message(user_id, text)
    except Exception:
        return


@router.message(Command('admin'))
async def admin_command(message: Message) -> None:
    if not await _is_admin(message):
        return
    _, locale = await _get_admin_context(message)
    await _send_admin_panel(message, locale)


@router.callback_query(F.data == 'admin:panel')
async def admin_panel(callback: CallbackQuery) -> None:
    if not await _is_admin(callback):
        await callback.answer()
        return
    _, locale = await _get_admin_context(callback)
    if callback.message:
        await _send_admin_panel(callback.message, locale, edit=True)
    await callback.answer()


@router.callback_query(F.data == 'admin:reviews')
async def admin_reviews(callback: CallbackQuery) -> None:
    if not await _is_admin(callback):
        await callback.answer()
        return
    _, locale = await _get_admin_context(callback)
    if callback.message:
        await _send_review_queue(callback.message, locale, edit=True)
    await callback.answer()


@router.callback_query(F.data.startswith('admin:claim:'))
async def admin_claim_detail(callback: CallbackQuery) -> None:
    if not await _is_admin(callback):
        await callback.answer()
        return
    _, locale = await _get_admin_context(callback)
    claim_id = int(callback.data.rsplit(':', 1)[1])
    if callback.message:
        await _send_claim_detail(callback.message, locale, claim_id, edit=True)
    await callback.answer()


@router.callback_query(F.data.startswith('admin:approve:'))
async def approve_claim(callback: CallbackQuery) -> None:
    if not await _is_admin(callback):
        await callback.answer()
        return
    admin_user, locale = await _get_admin_context(callback)
    claim_id = int(callback.data.rsplit(':', 1)[1])
    claims_repo = await _claims(callback)
    campaigns_repo = await _campaigns(callback)
    wallets_repo = await _wallets(callback)
    users_repo = await _users(callback)
    referrals_repo = await _referrals(callback)
    memberships_repo = await _memberships(callback)
    admin_repo = await _admin_repo(callback)
    claim = await claims_repo.get_claim(claim_id)
    if not claim or claim.get('claim_status') != 'submitted':
        await callback.answer(t(locale, 'admin_claim_not_pending'), show_alert=True)
        return
    campaign = await campaigns_repo.get_campaign(int(claim['campaign_id']))
    user = await users_repo.get_user(int(claim['user_id']))
    if not campaign or not user:
        await callback.answer(t(locale, 'task_not_found'), show_alert=True)
        return

    ok = await campaigns_repo.register_completion(int(claim['campaign_id']))
    if not ok:
        await claims_repo.mark_rejected(claim_id, reason='no_slots', meta={'mode': 'admin'})
        await admin_repo.log_event(int(admin_user['user_id']), 'claim_reject', int(user['user_id']), 'no_slots', {'claim_id': claim_id})
        await callback.answer(t(locale, 'task_no_slots'), show_alert=True)
        return

    hold_minutes = await memberships_repo.get_hold_minutes(int(user['user_id']), callback.bot['settings'].demo_hold_minutes)
    release_at = datetime.now(UTC) + timedelta(minutes=hold_minutes)
    await claims_repo.mark_verified(claim_id, proof={'mode': 'admin_approved', 'approved_by': admin_user['user_id']})
    await wallets_repo.add_hold(
        user_id=int(user['user_id']),
        amount=int(claim['reward_amount']),
        source_type='task_claim',
        source_id=claim_id,
        release_at=release_at.strftime('%Y-%m-%d %H:%M:%S'),
        reason=_task_type_label(normalize_locale(user.get('locale')), str(campaign['task_type'])),
    )
    await users_repo.increment_completed_tasks(int(user['user_id']), 1)

    referral_result = await referrals_repo.add_referral_earnings(int(user['user_id']), int(claim['reward_amount']))
    if referral_result:
        inviter_user_id, referral_amount = referral_result
        inviter_user = await users_repo.get_user(inviter_user_id)
        inviter_locale = normalize_locale((inviter_user or {}).get('locale'))
        await wallets_repo.add_available(
            inviter_user_id,
            referral_amount,
            'referral_bonus',
            description=t(inviter_locale, 'ledger_referral_bonus'),
            meta={'invited_user_id': int(user['user_id']), 'claim_id': claim_id, 'mode': 'admin_approve'},
        )

    await admin_repo.log_event(
        int(admin_user['user_id']),
        'claim_approve',
        int(user['user_id']),
        None,
        {'claim_id': claim_id, 'campaign_id': int(claim['campaign_id']), 'amount': int(claim['reward_amount'])},
    )
    user_locale = normalize_locale(user.get('locale'))
    await _notify_user(
        callback.bot,
        int(user['user_id']),
        t(user_locale, 'admin_notify_claim_approved', amount=int(claim['reward_amount']), currency=get_currency_name(user_locale)),
    )
    if callback.message:
        await _send_claim_detail(callback.message, locale, claim_id, edit=True)
    await callback.answer(t(locale, 'admin_action_done'))


@router.callback_query(F.data.startswith('admin:reject:'))
async def reject_claim(callback: CallbackQuery) -> None:
    if not await _is_admin(callback):
        await callback.answer()
        return
    admin_user, locale = await _get_admin_context(callback)
    _, _, claim_id_raw, reason_code = callback.data.split(':', 3)
    claim_id = int(claim_id_raw)
    claims_repo = await _claims(callback)
    users_repo = await _users(callback)
    admin_repo = await _admin_repo(callback)
    claim = await claims_repo.get_claim(claim_id)
    if not claim or claim.get('claim_status') != 'submitted':
        await callback.answer(t(locale, 'admin_claim_not_pending'), show_alert=True)
        return
    await claims_repo.mark_rejected(claim_id, reason=reason_code, meta={'mode': 'admin', 'admin_id': admin_user['user_id']})
    await users_repo.increment_canceled_tasks(int(claim['user_id']), 1)
    await admin_repo.log_event(
        int(admin_user['user_id']),
        'claim_reject',
        int(claim['user_id']),
        reason_code,
        {'claim_id': claim_id},
    )
    target_user = await users_repo.get_user(int(claim['user_id']))
    target_locale = normalize_locale((target_user or {}).get('locale'))
    await _notify_user(
        callback.bot,
        int(claim['user_id']),
        t(target_locale, 'admin_notify_claim_rejected', reason=t(target_locale, f'admin_reject_reason_{reason_code}')),
    )
    if callback.message:
        await _send_claim_detail(callback.message, locale, claim_id, edit=True)
    await callback.answer(t(locale, 'admin_action_done'))


@router.callback_query(F.data == 'admin:users')
async def admin_users(callback: CallbackQuery) -> None:
    if not await _is_admin(callback):
        await callback.answer()
        return
    _, locale = await _get_admin_context(callback)
    if callback.message:
        await _send_users_watchlist(callback.message, locale, edit=True)
    await callback.answer()


@router.callback_query(F.data.startswith('admin:user:'))
async def admin_user_detail(callback: CallbackQuery) -> None:
    if not await _is_admin(callback):
        await callback.answer()
        return
    _, locale = await _get_admin_context(callback)
    user_id = int(callback.data.rsplit(':', 1)[1])
    if callback.message:
        await _send_user_detail(callback.message, locale, user_id, edit=True)
    await callback.answer()


@router.callback_query(F.data.startswith('admin:block:'))
async def admin_block_user(callback: CallbackQuery) -> None:
    if not await _is_admin(callback):
        await callback.answer()
        return
    admin_user, locale = await _get_admin_context(callback)
    target_user_id = int(callback.data.rsplit(':', 1)[1])
    admin_repo = await _admin_repo(callback)
    await admin_repo.set_user_blocked(target_user_id, True)
    await admin_repo.log_event(int(admin_user['user_id']), 'user_block', target_user_id)
    target_user = await (await _users(callback)).get_user(target_user_id)
    user_locale = normalize_locale((target_user or {}).get('locale'))
    await _notify_user(callback.bot, target_user_id, t(user_locale, 'admin_notify_user_blocked'))
    if callback.message:
        await _send_user_detail(callback.message, locale, target_user_id, edit=True)
    await callback.answer(t(locale, 'admin_action_done'))


@router.callback_query(F.data.startswith('admin:unblock:'))
async def admin_unblock_user(callback: CallbackQuery) -> None:
    if not await _is_admin(callback):
        await callback.answer()
        return
    admin_user, locale = await _get_admin_context(callback)
    target_user_id = int(callback.data.rsplit(':', 1)[1])
    admin_repo = await _admin_repo(callback)
    await admin_repo.set_user_blocked(target_user_id, False)
    await admin_repo.log_event(int(admin_user['user_id']), 'user_unblock', target_user_id)
    target_user = await (await _users(callback)).get_user(target_user_id)
    user_locale = normalize_locale((target_user or {}).get('locale'))
    await _notify_user(callback.bot, target_user_id, t(user_locale, 'admin_notify_user_unblocked'))
    if callback.message:
        await _send_user_detail(callback.message, locale, target_user_id, edit=True)
    await callback.answer(t(locale, 'admin_action_done'))


@router.callback_query(F.data.startswith('admin:risk:'))
async def admin_adjust_risk(callback: CallbackQuery) -> None:
    if not await _is_admin(callback):
        await callback.answer()
        return
    admin_user, locale = await _get_admin_context(callback)
    _, _, user_id_raw, delta_raw = callback.data.split(':', 3)
    user_id = int(user_id_raw)
    delta = float(delta_raw)
    admin_repo = await _admin_repo(callback)
    new_value = await admin_repo.adjust_user_risk(user_id, delta)
    await admin_repo.log_event(int(admin_user['user_id']), 'user_risk_adjust', user_id, None, {'delta': delta, 'risk_score': new_value})
    if callback.message:
        await _send_user_detail(callback.message, locale, user_id, edit=True)
    await callback.answer(t(locale, 'admin_action_done'))


@router.callback_query(F.data.startswith('admin:credit:'))
async def admin_credit_user(callback: CallbackQuery) -> None:
    if not await _is_admin(callback):
        await callback.answer()
        return
    admin_user, locale = await _get_admin_context(callback)
    _, _, user_id_raw, amount_raw = callback.data.split(':', 3)
    target_user_id = int(user_id_raw)
    amount = int(amount_raw)
    wallets_repo = await _wallets(callback)
    admin_repo = await _admin_repo(callback)
    await wallets_repo.add_available(
        target_user_id,
        amount,
        'admin_adjustment',
        description=t(locale, 'ledger_admin_adjustment'),
        meta={'admin_user_id': int(admin_user['user_id']), 'amount': amount},
    )
    await admin_repo.log_event(int(admin_user['user_id']), 'wallet_adjust', target_user_id, None, {'amount': amount})
    if callback.message:
        await _send_user_detail(callback.message, locale, target_user_id, edit=True)
    await callback.answer(t(locale, 'admin_action_done'))


@router.callback_query(F.data == 'admin:stats')
async def admin_stats(callback: CallbackQuery) -> None:
    if not await _is_admin(callback):
        await callback.answer()
        return
    _, locale = await _get_admin_context(callback)
    if callback.message:
        await _send_stats(callback.message, locale, edit=True)
    await callback.answer()


@router.callback_query(F.data == 'admin:events')
async def admin_events(callback: CallbackQuery) -> None:
    if not await _is_admin(callback):
        await callback.answer()
        return
    _, locale = await _get_admin_context(callback)
    if callback.message:
        await _send_events(callback.message, locale, edit=True)
    await callback.answer()


async def _send_admin_panel(message: Message, locale: str, edit: bool = False) -> None:
    admin_repo = await _admin_repo(message)
    stats = await admin_repo.get_dashboard_stats()
    text = '\n'.join([
        f"<b>{t(locale, 'admin_panel_title')}</b>",
        t(locale, 'admin_panel_subtitle'),
        '',
        t(locale, 'admin_stat_total_users', count=stats.get('total_users', 0)),
        t(locale, 'admin_stat_earners', count=stats.get('earners', 0)),
        t(locale, 'admin_stat_advertisers', count=stats.get('advertisers', 0)),
        t(locale, 'admin_stat_active_campaigns', count=stats.get('active_campaigns', 0)),
        t(locale, 'admin_stat_review_claims', count=stats.get('review_claims', 0)),
        t(locale, 'admin_stat_high_risk', count=stats.get('high_risk_users', 0)),
        t(locale, 'admin_stat_blocked', count=stats.get('blocked_users', 0)),
    ])
    markup = admin_panel_keyboard(locale)
    if edit:
        await message.edit_text(text, reply_markup=markup)
    else:
        await message.answer(text, reply_markup=markup)


async def _send_review_queue(message: Message, locale: str, edit: bool = False) -> None:
    admin_repo = await _admin_repo(message)
    claims = await admin_repo.list_review_claims(limit=10)
    lines = [f"<b>{t(locale, 'admin_reviews_title')}</b>", t(locale, 'admin_reviews_hint'), '']
    if not claims:
        lines.append(t(locale, 'admin_reviews_empty'))
    else:
        for claim in claims:
            username = claim.get('username') or claim.get('first_name') or f"id {claim['user_id']}"
            lines.append(
                t(
                    locale,
                    'admin_review_line',
                    claim_id=claim['id'],
                    user=username,
                    reward=claim['reward_amount'],
                    currency=get_currency_name(locale),
                    risk=claim.get('risk_score', 0),
                )
            )
    markup = admin_reviews_keyboard(locale, claims)
    if edit:
        await message.edit_text('\n'.join(lines), reply_markup=markup)
    else:
        await message.answer('\n'.join(lines), reply_markup=markup)


async def _send_claim_detail(message: Message, locale: str, claim_id: int, edit: bool = False) -> None:
    admin_repo = await _admin_repo(message)
    claim = await admin_repo.get_claim_admin_view(claim_id)
    if not claim:
        text = t(locale, 'task_not_found')
        if edit:
            await message.edit_text(text)
        else:
            await message.answer(text)
        return
    proof = _load_proof(claim.get('proof_json'))
    reason_code = proof.get('reason_code') or proof.get('reason') or '—'
    username = claim.get('username') or claim.get('first_name') or f"id {claim['user_id']}"
    text = '\n'.join([
        f"<b>{t(locale, 'admin_claim_title', claim_id=claim['id'])}</b>",
        t(locale, 'admin_claim_user', user=username, user_id=claim['user_id']),
        t(locale, 'admin_claim_campaign', campaign=claim.get('campaign_title') or '—', campaign_id=claim.get('campaign_id')),
        t(locale, 'admin_claim_task_type', task_type=_task_type_label(locale, str(claim.get('task_type') or 'channel_join'))),
        t(locale, 'admin_claim_reward', amount=claim.get('reward_amount', 0), currency=get_currency_name(locale)),
        t(locale, 'admin_claim_status', status=str(claim.get('claim_status') or '—')),
        t(locale, 'admin_claim_risk', risk=claim.get('risk_score', 0)),
        t(locale, 'admin_claim_created', dt=_format_dt(locale, str(claim.get('created_at') or ''))),
        t(locale, 'admin_claim_reason', reason=reason_code),
    ])
    markup = admin_claim_keyboard(locale, int(claim['id']), int(claim['user_id'])) if claim.get('claim_status') == 'submitted' else admin_events_keyboard(locale)
    if edit:
        await message.edit_text(text, reply_markup=markup)
    else:
        await message.answer(text, reply_markup=markup)


async def _send_users_watchlist(message: Message, locale: str, edit: bool = False) -> None:
    admin_repo = await _admin_repo(message)
    users = await admin_repo.list_watch_users(limit=15)
    lines = [f"<b>{t(locale, 'admin_users_title')}</b>", t(locale, 'admin_users_hint'), '']
    if not users:
        lines.append(t(locale, 'admin_users_empty'))
    else:
        for user in users[:8]:
            username = user.get('username') or user.get('first_name') or f"id {user['user_id']}"
            lines.append(
                t(
                    locale,
                    'admin_user_list_line',
                    user=username,
                    user_id=user['user_id'],
                    risk=user.get('risk_score', 0),
                    review_count=user.get('review_count', 0),
                )
            )
    markup = admin_users_keyboard(locale, users)
    if edit:
        await message.edit_text('\n'.join(lines), reply_markup=markup)
    else:
        await message.answer('\n'.join(lines), reply_markup=markup)


async def _send_user_detail(message: Message, locale: str, user_id: int, edit: bool = False) -> None:
    admin_repo = await _admin_repo(message)
    user = await admin_repo.get_user_admin_snapshot(user_id)
    if not user:
        text = t(locale, 'task_not_found')
        if edit:
            await message.edit_text(text)
        else:
            await message.answer(text)
        return
    username = user.get('username') or user.get('first_name') or f"id {user['user_id']}"
    user_locale = normalize_locale(user.get('locale'))
    text = '\n'.join([
        f"<b>{t(locale, 'admin_user_title', user=username)}</b>",
        t(locale, 'admin_user_id_line', user_id=user['user_id']),
        t(locale, 'admin_user_role_line', role=t(locale, f"role_{user.get('role') or 'earner'}")),
        t(locale, 'admin_user_lang_line', language=user_locale),
        t(locale, 'admin_user_tier_line', tier=t(locale, f"tier_{user.get('tier') or 'new'}")),
        t(locale, 'admin_user_risk_line', risk=user.get('risk_score', 0)),
        t(locale, 'admin_user_tasks_line', completed=user.get('completed_tasks', 0), canceled=user.get('canceled_tasks', 0)),
        t(locale, 'admin_user_review_line', count=user.get('review_count', 0)),
        t(locale, 'admin_user_wallet_line', available=user.get('available_balance', 0), hold=user.get('hold_balance', 0), currency=get_currency_name(user_locale)),
        t(locale, 'admin_user_status_line', status=t(locale, 'admin_status_blocked') if int(user.get('is_blocked', 0) or 0) else t(locale, 'admin_status_active')),
    ])
    markup = admin_user_keyboard(locale, int(user['user_id']), bool(int(user.get('is_blocked', 0) or 0)))
    if edit:
        await message.edit_text(text, reply_markup=markup)
    else:
        await message.answer(text, reply_markup=markup)


async def _send_stats(message: Message, locale: str, edit: bool = False) -> None:
    admin_repo = await _admin_repo(message)
    stats = await admin_repo.get_dashboard_stats()
    text = '\n'.join([
        f"<b>{t(locale, 'admin_stats_title')}</b>",
        t(locale, 'admin_stat_total_users', count=stats.get('total_users', 0)),
        t(locale, 'admin_stat_earners', count=stats.get('earners', 0)),
        t(locale, 'admin_stat_advertisers', count=stats.get('advertisers', 0)),
        t(locale, 'admin_stat_active_campaigns', count=stats.get('active_campaigns', 0)),
        t(locale, 'admin_stat_review_claims', count=stats.get('review_claims', 0)),
        t(locale, 'admin_stat_verified', count=stats.get('verified_claims', 0)),
        t(locale, 'admin_stat_rejected', count=stats.get('rejected_claims', 0)),
        t(locale, 'admin_stat_high_risk', count=stats.get('high_risk_users', 0)),
        t(locale, 'admin_stat_blocked', count=stats.get('blocked_users', 0)),
    ])
    markup = admin_events_keyboard(locale)
    if edit:
        await message.edit_text(text, reply_markup=markup)
    else:
        await message.answer(text, reply_markup=markup)


async def _send_events(message: Message, locale: str, edit: bool = False) -> None:
    admin_repo = await _admin_repo(message)
    events = await admin_repo.list_recent_events(limit=12)
    lines = [f"<b>{t(locale, 'admin_events_title')}</b>"]
    if not events:
        lines.append(t(locale, 'admin_events_empty'))
    else:
        for event in events:
            lines.append(
                t(
                    locale,
                    'admin_event_line',
                    action=event.get('action') or '—',
                    target=event.get('target_user_id') or '—',
                    reason=event.get('reason') or '—',
                    dt=_format_dt(locale, str(event.get('created_at') or '')),
                )
            )
    markup = admin_events_keyboard(locale)
    if edit:
        await message.edit_text('\n'.join(lines), reply_markup=markup)
    else:
        await message.answer('\n'.join(lines), reply_markup=markup)
