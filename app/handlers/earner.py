from __future__ import annotations

from datetime import UTC, datetime, timedelta

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from app.core.i18n import LEXICON, get_currency_name, normalize_locale, t
from app.core.reward_catalog import RewardCatalogItem, get_catalog_item, list_catalog_items
from app.core.settings import Settings
from app.keyboards.billing import vip_center_keyboard
from app.keyboards.rewards import reward_back_keyboard, reward_shop_keyboard, rewards_keyboard
from app.keyboards.start import advertiser_menu, earner_menu
from app.keyboards.tasks import task_taken_keyboard, tasks_list_keyboard
from app.storage.campaigns import CampaignRepository
from app.storage.memberships import MembershipRepository
from app.storage.redemptions import RedemptionRepository
from app.storage.referrals import ReferralRepository
from app.storage.task_claims import TaskClaimRepository
from app.storage.users import UserRepository
from app.storage.wallets import WalletRepository

router = Router(name='earner')
BASE_MAX_OPEN_CLAIMS = 3

EARNER_MENU_TEXTS = {
    value
    for locale_data in LEXICON.values()
    for key, value in locale_data.items()
    if key in {'menu_tasks', 'menu_wallet', 'menu_rewards', 'menu_profile'}
}


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


async def _redemptions(message_or_callback: Message | CallbackQuery) -> RedemptionRepository:
    return message_or_callback.bot['redemptions_repo']


async def _settings(message_or_callback: Message | CallbackQuery) -> Settings:
    return message_or_callback.bot['settings']


async def _get_context(message_or_callback: Message | CallbackQuery) -> tuple[dict, str, str]:
    users_repo = await _users(message_or_callback)
    memberships_repo = await _memberships(message_or_callback)
    user_id = message_or_callback.from_user.id if message_or_callback.from_user else 0
    await memberships_repo.sync_user(user_id)
    user = await users_repo.get_user(user_id)
    locale = normalize_locale((user or {}).get('locale'))
    role = (user or {}).get('role') or 'earner'
    return user or {}, locale, role


def _reply_menu(locale: str, role: str):
    return advertiser_menu(locale) if role == 'advertiser' else earner_menu(locale)


def _format_release_time(locale: str, release_at: str | None) -> str:
    if not release_at:
        return '—'
    try:
        dt = datetime.strptime(release_at, '%Y-%m-%d %H:%M:%S')
        return dt.strftime('%d.%m %H:%M') if locale == 'ru' else dt.strftime('%Y-%m-%d %H:%M')
    except ValueError:
        return release_at


def _campaign_title(locale: str, task_type: str) -> str:
    mapping = {
        'channel_join': t(locale, 'task_title_channel_join'),
        'post_view': t(locale, 'task_title_post_view'),
        'bot_start': t(locale, 'task_title_bot_start'),
        'mini_app_open': t(locale, 'task_title_mini_app_open'),
    }
    return mapping.get(task_type, t(locale, 'task_title_bot_start'))


def _task_type_label(locale: str, task_type: str) -> str:
    return t(locale, f'task_type_{task_type}')


def _ledger_label(locale: str, entry_type: str, description: str | None) -> str:
    return description or t(locale, f'ledger_{entry_type}')


def _next_tier_line(locale: str, completed_tasks: int, tier: str) -> str:
    if tier == 'vip':
        return t(locale, 'profile_top_tier')
    if completed_tasks >= 10:
        return t(locale, 'profile_top_tier')
    return t(locale, 'profile_next_tier', left=10 - completed_tasks)


def _needs_manual_review(user: dict, claim: dict, recent_verified: int, age_seconds: int) -> tuple[bool, str]:
    risk_score = float(user.get('risk_score', 0) or 0)
    reward_amount = int(claim.get('reward_amount', 0) or 0)
    completed_tasks = int(user.get('completed_tasks', 0) or 0)

    if age_seconds < 8:
        return True, 'too_fast'
    if risk_score >= 35:
        return True, 'high_risk'
    if recent_verified >= 5:
        return True, 'rate_limit'
    if reward_amount >= 40 and completed_tasks < 10:
        return True, 'high_reward_new_user'
    return False, 'auto'


def _perk_label(locale: str, perk_code: str) -> str:
    return t(locale, f'perk_{perk_code}')


def _item_title(locale: str, item: RewardCatalogItem) -> str:
    return t(locale, item.title_key)


def _item_desc(locale: str, item: RewardCatalogItem) -> str:
    return t(locale, item.desc_key)


def _format_rate(rate: float) -> str:
    percent = rate * 100
    return f'{int(percent)}%' if percent.is_integer() else f'{percent:.1f}%'


@router.message(F.text.in_(EARNER_MENU_TEXTS))
async def earner_text_routes(message: Message) -> None:
    user, locale, role = await _get_context(message)
    if not user:
        return

    if message.text == t(locale, 'menu_tasks'):
        await _send_tasks_overview(message, user, locale)
        return

    if message.text == t(locale, 'menu_wallet'):
        await _send_wallet(message, user, locale, role)
        return

    if message.text == t(locale, 'menu_rewards'):
        await _send_rewards(message, user, locale, role)
        return

    if message.text == t(locale, 'menu_profile'):
        await _send_profile(message, user, locale, role)
        return


@router.message(Command('tasks'))
async def tasks_command(message: Message) -> None:
    user, locale, _ = await _get_context(message)
    if user:
        await _send_tasks_overview(message, user, locale)


@router.message(Command('wallet'))
async def wallet_command(message: Message) -> None:
    user, locale, role = await _get_context(message)
    if user:
        await _send_wallet(message, user, locale, role)


@router.message(Command('rewards'))
async def rewards_command(message: Message) -> None:
    user, locale, role = await _get_context(message)
    if user:
        await _send_rewards(message, user, locale, role)


@router.message(Command('profile'))
async def profile_command(message: Message) -> None:
    user, locale, role = await _get_context(message)
    if user:
        await _send_profile(message, user, locale, role)


@router.callback_query(F.data == 'task:refresh')
async def refresh_tasks(callback: CallbackQuery) -> None:
    user, locale, _ = await _get_context(callback)
    if not user:
        await callback.answer()
        return
    if callback.message:
        await _send_tasks_overview(callback.message, user, locale, edit=True)
    await callback.answer()


@router.callback_query(F.data.startswith('task:take:'))
async def take_task(callback: CallbackQuery) -> None:
    user, locale, _ = await _get_context(callback)
    if not user:
        await callback.answer()
        return

    if int(user.get('is_blocked', 0) or 0):
        await callback.answer(t(locale, 'task_blocked'), show_alert=True)
        return

    campaign_id = int(callback.data.rsplit(':', 1)[1])
    campaigns_repo = await _campaigns(callback)
    claims_repo = await _claims(callback)
    settings = await _settings(callback)
    memberships_repo = await _memberships(callback)

    open_claims = await claims_repo.count_open_claims(user['user_id'])
    open_claim_limit = await memberships_repo.get_effective_open_claim_limit(user['user_id'], BASE_MAX_OPEN_CLAIMS)
    if open_claims >= open_claim_limit:
        await callback.answer(t(locale, 'task_claim_limit_reached', limit=open_claim_limit), show_alert=True)
        return

    campaign = await campaigns_repo.get_campaign(campaign_id)
    if not campaign or campaign.get('status') != 'active' or int(campaign.get('completed_count', 0)) >= int(campaign.get('target_count', 0)):
        await callback.answer(t(locale, 'task_not_found'), show_alert=True)
        return

    existing = await claims_repo.get_user_claim_for_campaign(user['user_id'], campaign_id)
    if existing and existing.get('claim_status') in {'taken', 'verified', 'submitted'}:
        claim_id = int(existing['id'])
        await callback.message.answer(
            t(locale, 'task_already_taken'),
            reply_markup=task_taken_keyboard(locale, claim_id, str(campaign.get('target_url') or '') or None),
        )
        await callback.answer()
        return

    claim_id = await claims_repo.create_claim(campaign_id, user['user_id'], int(campaign['reward_per_task']))
    hold_minutes = await memberships_repo.get_hold_minutes(user['user_id'], settings.demo_hold_minutes)
    hold_text = t(locale, 'hold_minutes', minutes=hold_minutes) if hold_minutes < 60 else t(locale, 'hold_hours', hours=max(1, hold_minutes // 60))
    title = _campaign_title(locale, campaign['task_type'])
    text_lines = [
        f"<b>{title}</b>",
        t(locale, 'task_taken'),
        t(
            locale,
            'task_card',
            title=title,
            task_type=_task_type_label(locale, campaign['task_type']),
            reward=campaign['reward_per_task'],
            currency=get_currency_name(locale),
            hold_time=hold_text,
            left=max(0, int(campaign['target_count']) - int(campaign['completed_count'])),
        ),
    ]
    if campaign.get('target_url'):
        text_lines.append(t(locale, 'task_open_hint', url=campaign['target_url']))
    await callback.message.answer(
        '\n'.join(text_lines),
        reply_markup=task_taken_keyboard(locale, claim_id, str(campaign.get('target_url') or '') or None),
    )
    await callback.answer()


@router.callback_query(F.data.startswith('task:submit:'))
async def submit_task(callback: CallbackQuery) -> None:
    user, locale, role = await _get_context(callback)
    if not user:
        await callback.answer()
        return
    claim_id = int(callback.data.rsplit(':', 1)[1])
    claims_repo = await _claims(callback)
    campaigns_repo = await _campaigns(callback)
    wallets_repo = await _wallets(callback)
    users_repo = await _users(callback)
    referrals_repo = await _referrals(callback)
    settings = await _settings(callback)
    memberships_repo = await _memberships(callback)

    claim = await claims_repo.get_claim(claim_id)
    if not claim or int(claim['user_id']) != int(user['user_id']):
        await callback.answer(t(locale, 'task_not_found'), show_alert=True)
        return
    if claim.get('claim_status') == 'verified':
        await callback.answer(t(locale, 'task_completed', amount=claim['reward_amount'], currency=get_currency_name(locale)), show_alert=True)
        return
    if claim.get('claim_status') == 'submitted':
        await callback.answer(t(locale, 'task_in_review'), show_alert=True)
        return

    campaign = await campaigns_repo.get_campaign(int(claim['campaign_id']))
    if not campaign:
        await callback.answer(t(locale, 'task_not_found'), show_alert=True)
        return

    created_at = datetime.strptime(str(claim['created_at']), '%Y-%m-%d %H:%M:%S')
    age_seconds = int((datetime.now() - created_at).total_seconds())
    recent_verified = await claims_repo.count_recent_verified(user['user_id'], minutes=10)
    needs_review, reason_code = _needs_manual_review(user, claim, recent_verified, age_seconds)

    if needs_review:
        await claims_repo.mark_submitted(
            claim_id,
            proof={'mode': 'manual_review', 'reason_code': reason_code, 'age_seconds': age_seconds},
        )
        await callback.message.answer(
            t(locale, 'task_submitted_for_review', amount=claim['reward_amount'], currency=get_currency_name(locale)),
            reply_markup=_reply_menu(locale, role),
        )
        await callback.answer()
        return

    ok = await campaigns_repo.register_completion(int(claim['campaign_id']))
    if not ok:
        await claims_repo.mark_rejected(claim_id, reason='no_slots', meta={'mode': 'auto'})
        await callback.answer(t(locale, 'task_no_slots'), show_alert=True)
        return

    hold_minutes = await memberships_repo.get_hold_minutes(user['user_id'], settings.demo_hold_minutes)
    release_at = datetime.now(UTC) + timedelta(minutes=hold_minutes)
    hold_reason = _task_type_label(locale, campaign['task_type'])
    await claims_repo.mark_verified(claim_id, proof={'mode': 'demo_auto', 'age_seconds': age_seconds})
    await wallets_repo.add_hold(
        user_id=user['user_id'],
        amount=int(claim['reward_amount']),
        source_type='task_claim',
        source_id=claim_id,
        release_at=release_at.strftime('%Y-%m-%d %H:%M:%S'),
        reason=hold_reason,
    )
    await users_repo.increment_completed_tasks(user['user_id'], 1)

    referral_result = await referrals_repo.add_referral_earnings(user['user_id'], int(claim['reward_amount']))
    if referral_result:
        inviter_user_id, referral_amount = referral_result
        inviter_user = await users_repo.get_user(inviter_user_id)
        inviter_locale = normalize_locale((inviter_user or {}).get('locale'))
        await wallets_repo.add_available(
            inviter_user_id,
            referral_amount,
            'referral_bonus',
            description=t(inviter_locale, 'ledger_referral_bonus'),
            meta={'invited_user_id': user['user_id'], 'claim_id': claim_id},
        )

    await callback.message.answer(
        t(locale, 'task_completed', amount=claim['reward_amount'], currency=get_currency_name(locale)),
        reply_markup=_reply_menu(locale, role),
    )
    await callback.answer()


@router.callback_query(F.data == 'reward:process')
async def process_rewards(callback: CallbackQuery) -> None:
    user, locale, role = await _get_context(callback)
    if not user:
        await callback.answer()
        return
    wallets_repo = await _wallets(callback)
    released_count, released_amount = await wallets_repo.release_ready_holds(user['user_id'])
    if callback.message:
        await _send_rewards(
            callback.message,
            user,
            locale,
            role,
            released_count=released_count,
            released_amount=released_amount,
            edit=True,
        )
    await callback.answer()


@router.callback_query(F.data == 'reward:shop')
async def reward_shop(callback: CallbackQuery) -> None:
    user, locale, role = await _get_context(callback)
    if not user or not callback.message:
        await callback.answer()
        return
    await _send_reward_shop(callback.message, user, locale, role, edit=True)
    await callback.answer()


@router.callback_query(F.data == 'reward:referrals')
async def referral_center(callback: CallbackQuery) -> None:
    user, locale, role = await _get_context(callback)
    if not user or not callback.message:
        await callback.answer()
        return
    await _send_referral_center(callback.message, user, locale, role, edit=True)
    await callback.answer()


@router.callback_query(F.data == 'reward:vip')
async def vip_center(callback: CallbackQuery) -> None:
    user, locale, role = await _get_context(callback)
    if not user or not callback.message:
        await callback.answer()
        return
    await _send_vip_center(callback.message, user, locale, role, edit=True)
    await callback.answer()


@router.callback_query(F.data == 'reward:back')
async def rewards_back(callback: CallbackQuery) -> None:
    user, locale, role = await _get_context(callback)
    if not user or not callback.message:
        await callback.answer()
        return
    await _send_rewards(callback.message, user, locale, role, edit=True)
    await callback.answer()


@router.callback_query(F.data.startswith('reward:redeem:'))
async def redeem_reward_item(callback: CallbackQuery) -> None:
    user, locale, role = await _get_context(callback)
    if not user or not callback.message:
        await callback.answer()
        return

    item_code = callback.data.rsplit(':', 1)[1]
    item = get_catalog_item(item_code)
    if not item:
        await callback.answer(t(locale, 'shop_item_not_found'), show_alert=True)
        return

    wallets_repo = await _wallets(callback)
    memberships_repo = await _memberships(callback)
    redemptions_repo = await _redemptions(callback)
    wallet = await wallets_repo.get_wallet(user['user_id'])
    available = int(wallet.get('available_balance', 0) or 0)
    if available < item.cost:
        await callback.answer(
            t(locale, 'shop_not_enough_balance', need=item.cost - available, currency=get_currency_name(locale)),
            show_alert=True,
        )
        return

    await wallets_repo.add_available(
        user['user_id'],
        -item.cost,
        'spend_internal',
        description=t(locale, 'ledger_reward_redeem', item=_item_title(locale, item)),
        meta={'item_code': item.code, 'perk_code': item.perk_code},
    )
    await memberships_repo.activate_membership(
        user['user_id'],
        item.perk_code,
        item.duration_days,
        source='reward_shop',
        meta={'item_code': item.code, 'cost': item.cost},
    )
    await redemptions_repo.log_redemption(
        user['user_id'],
        item.code,
        item.cost,
        status='completed',
        details={'perk_code': item.perk_code, 'days': item.duration_days},
    )
    user, locale, role = await _get_context(callback)
    await callback.message.edit_text(
        t(
            locale,
            'shop_redeem_success',
            item=_item_title(locale, item),
            days=item.duration_days,
            cost=item.cost,
            currency=get_currency_name(locale),
        ),
        reply_markup=reward_back_keyboard(locale),
    )
    await callback.answer()


async def _send_profile(message: Message, user: dict, locale: str, role: str) -> None:
    referrals_repo = await _referrals(message)
    claims_repo = await _claims(message)
    memberships_repo = await _memberships(message)
    referrals = await referrals_repo.count_referrals(user['user_id'])
    open_claims = await claims_repo.count_open_claims(user['user_id'])
    open_limit = await memberships_repo.get_effective_open_claim_limit(user['user_id'], BASE_MAX_OPEN_CLAIMS)
    active_memberships = await memberships_repo.list_active_memberships(user['user_id'])
    perks_line = ', '.join(_perk_label(locale, str(item['perk_code'])) for item in active_memberships) if active_memberships else t(locale, 'perks_none')
    text = '\n'.join([
        f"<b>✨ {t(locale, 'profile_title')}</b>",
        t(locale, 'profile_id', user_id=user['user_id']),
        t(locale, 'profile_role', role=t(locale, f"role_{role or 'earner'}")),
        t(locale, 'profile_tier', tier=t(locale, f"tier_{user.get('tier') or 'new'}")),
        t(locale, 'profile_tasks', tasks=user.get('completed_tasks', 0)),
        t(locale, 'profile_active_claims', count=open_claims),
        t(locale, 'profile_claim_limit', count=open_limit),
        t(locale, 'profile_referrals', count=referrals),
        t(locale, 'profile_risk', risk=user.get('risk_score', 0)),
        t(locale, 'profile_active_perks', perks=perks_line),
        _next_tier_line(locale, int(user.get('completed_tasks', 0) or 0), str(user.get('tier') or 'new')),
    ])
    await message.answer(text, reply_markup=_reply_menu(locale, role))


async def _send_wallet(message: Message, user: dict, locale: str, role: str) -> None:
    wallets_repo = await _wallets(message)
    wallet = await wallets_repo.get_wallet(user['user_id'])
    entries = await wallets_repo.list_recent_entries(user['user_id'])

    lines = [
        f"<b>💳 {t(locale, 'wallet_title')}</b>",
        t(locale, 'wallet_available', available=wallet.get('available_balance', 0), currency=get_currency_name(locale)),
        t(locale, 'wallet_hold', hold=wallet.get('hold_balance', 0), currency=get_currency_name(locale)),
        t(locale, 'wallet_spent', spent=wallet.get('spent_balance', 0), currency=get_currency_name(locale)),
        t(locale, 'wallet_earned_total', earned=wallet.get('earned_total', 0), currency=get_currency_name(locale)),
        '',
        t(locale, 'wallet_hint'),
        '',
        f"<b>{t(locale, 'wallet_history_title')}</b>",
    ]
    if not entries:
        lines.append(t(locale, 'wallet_empty'))
    else:
        for entry in entries:
            amount = int(entry['amount'])
            label = _ledger_label(locale, str(entry['entry_type']), entry.get('description'))
            if amount >= 0:
                lines.append(t(locale, 'wallet_history_line_plus', amount=amount, currency=get_currency_name(locale), label=label))
            else:
                lines.append(t(locale, 'wallet_history_line_minus', amount=abs(amount), currency=get_currency_name(locale), label=label))
    await message.answer('\n'.join(lines), reply_markup=_reply_menu(locale, role))


async def _send_rewards(
    message: Message,
    user: dict,
    locale: str,
    role: str,
    released_count: int = 0,
    released_amount: int = 0,
    edit: bool = False,
) -> None:
    wallets_repo = await _wallets(message)
    claims_repo = await _claims(message)
    redemptions_repo = await _redemptions(message)
    if released_count == 0:
        released_count, released_amount = await wallets_repo.release_ready_holds(user['user_id'])
    pending_holds = await wallets_repo.list_pending_holds(user['user_id'])
    open_claims = await claims_repo.list_user_open_claims(user['user_id'], limit=20)
    recent_redemptions = await redemptions_repo.list_recent_redemptions(user['user_id'], limit=3)
    review_count = sum(1 for item in open_claims if item.get('claim_status') == 'submitted')
    total_hold = sum(int(item['amount']) for item in pending_holds)

    lines = [f"<b>🎁 {t(locale, 'rewards_title')}</b>"]
    if released_amount > 0:
        lines.append(t(locale, 'rewards_released', amount=released_amount, currency=get_currency_name(locale)))
    else:
        lines.append(t(locale, 'rewards_nothing_released'))
    lines.append(t(locale, 'rewards_pending', count=len(pending_holds)))
    lines.append(t(locale, 'rewards_total_hold', amount=total_hold, currency=get_currency_name(locale)))
    lines.append(t(locale, 'rewards_review_count', count=review_count))
    lines.append(t(locale, 'rewards_shop_hint'))
    if pending_holds:
        lines.append('')
        for hold in pending_holds[:5]:
            lines.append(
                t(
                    locale,
                    'hold_line',
                    amount=hold['amount'],
                    currency=get_currency_name(locale),
                    time=_format_release_time(locale, hold.get('release_at')),
                )
            )

    if recent_redemptions:
        lines.append('')
        lines.append(f"<b>{t(locale, 'rewards_recent_redemptions')}</b>")
        for redemption in recent_redemptions:
            item = get_catalog_item(str(redemption['item_code']))
            title = _item_title(locale, item) if item else str(redemption['item_code'])
            lines.append(t(locale, 'rewards_redemption_line', item=title, cost=redemption['cost'], currency=get_currency_name(locale)))

    if edit:
        await message.edit_text('\n'.join(lines), reply_markup=rewards_keyboard(locale))
    else:
        await message.answer('\n'.join(lines), reply_markup=rewards_keyboard(locale))


async def _send_reward_shop(message: Message, user: dict, locale: str, role: str, edit: bool = False) -> None:
    wallets_repo = await _wallets(message)
    wallet = await wallets_repo.get_wallet(user['user_id'])
    items = list_catalog_items()
    lines = [
        f"<b>🛍️ {t(locale, 'reward_shop_title')}</b>",
        t(locale, 'reward_shop_balance', amount=wallet.get('available_balance', 0), currency=get_currency_name(locale)),
        '',
    ]
    for item in items:
        lines.append(f"<b>{_item_title(locale, item)}</b>")
        lines.append(t(locale, 'reward_shop_item_line', cost=item.cost, currency=get_currency_name(locale), days=item.duration_days))
        lines.append(_item_desc(locale, item))
        lines.append('')
    text = '\n'.join(lines).strip()
    markup = reward_shop_keyboard(locale, items)
    if edit:
        await message.edit_text(text, reply_markup=markup)
    else:
        await message.answer(text, reply_markup=markup)


async def _send_referral_center(message: Message, user: dict, locale: str, role: str, edit: bool = False) -> None:
    referrals_repo = await _referrals(message)
    summary = await referrals_repo.get_referral_summary(user['user_id'])
    invite_link = f'https://t.me/your_bot?start={user["user_id"]}'
    try:
        me = await message.bot.get_me()
        if me.username:
            invite_link = f'https://t.me/{me.username}?start={user["user_id"]}'
    except Exception:
        pass

    lines = [
        f"<b>🤝 {t(locale, 'referral_center_title')}</b>",
        t(locale, 'referral_center_count', count=summary['count']),
        t(locale, 'referral_center_earned', amount=summary['earned_total'], currency=get_currency_name(locale)),
        t(locale, 'referral_center_rate', rate=_format_rate(float(summary['rate']))),
        '',
        t(locale, 'referral_center_link', link=invite_link),
        t(locale, 'referral_center_hint'),
    ]
    if edit:
        await message.edit_text('\n'.join(lines), reply_markup=reward_back_keyboard(locale))
    else:
        await message.answer('\n'.join(lines), reply_markup=reward_back_keyboard(locale))


async def _send_vip_center(message: Message, user: dict, locale: str, role: str, edit: bool = False) -> None:
    memberships_repo = await _memberships(message)
    vip_ends_at = await memberships_repo.get_membership_ends_at(user['user_id'], 'vip')
    active_perks = await memberships_repo.list_active_memberships(user['user_id'])
    perk_lines = [t(locale, 'vip_perk_line', perk=_perk_label(locale, str(item['perk_code'])), until=_format_release_time(locale, item.get('ends_at'))) for item in active_perks]
    lines = [
        f"<b>👑 {t(locale, 'vip_center_title')}</b>",
        t(locale, 'vip_status_line', status=t(locale, f"tier_{user.get('tier') or 'new'}")),
        t(locale, 'vip_until_line', until=_format_release_time(locale, vip_ends_at) if vip_ends_at else t(locale, 'vip_not_active')),
        '',
        t(locale, 'vip_benefits'),
    ]
    if perk_lines:
        lines.append('')
        lines.append(f"<b>{t(locale, 'vip_active_perks')}</b>")
        lines.extend(perk_lines[:5])
    lines.append('')
    lines.append(t(locale, 'vip_buy_hint'))
    lines.append(t(locale, 'vip_xtr_hint'))
    markup = vip_center_keyboard(locale, enable_xtr=message.bot['settings'].enable_xtr_payments)
    if edit:
        await message.edit_text('\n'.join(lines), reply_markup=markup)
    else:
        await message.answer('\n'.join(lines), reply_markup=markup)


async def _send_tasks_overview(message: Message, user: dict, locale: str, edit: bool = False) -> None:
    campaigns_repo = await _campaigns(message)
    claims_repo = await _claims(message)
    settings = await _settings(message)
    memberships_repo = await _memberships(message)

    campaigns = await campaigns_repo.list_available_campaigns_for_user(user['user_id'], limit=6)
    open_claims = await claims_repo.list_user_open_claims(user['user_id'], limit=5)
    open_claim_count = await claims_repo.count_open_claims(user['user_id'])
    hold_minutes = await memberships_repo.get_hold_minutes(user['user_id'], settings.demo_hold_minutes)
    hold_text = t(locale, 'hold_minutes', minutes=hold_minutes) if hold_minutes < 60 else t(locale, 'hold_hours', hours=max(1, hold_minutes // 60))
    open_claim_limit = await memberships_repo.get_effective_open_claim_limit(user['user_id'], BASE_MAX_OPEN_CLAIMS)

    lines = [f"<b>⚡ {t(locale, 'tasks_title')}</b>", t(locale, 'tasks_limit_line', current=open_claim_count, limit=open_claim_limit)]
    if open_claims:
        lines.append('')
        lines.append(f"<b>{t(locale, 'tasks_active_claims_title')}</b>")
        for claim in open_claims:
            title = _campaign_title(locale, str(claim['task_type']))
            lines.append(
                t(
                    locale,
                    'task_active_line',
                    claim_id=claim['id'],
                    title=title,
                    reward=claim['reward_amount'],
                    currency=get_currency_name(locale),
                    status=t(locale, 'task_status_in_review') if claim['claim_status'] == 'submitted' else t(locale, 'task_status_taken'),
                )
            )
    else:
        lines.append('')
        lines.append(t(locale, 'tasks_no_active_claims'))

    ids: list[int] = []
    if campaigns:
        lines.append('')
        lines.append(f"<b>{t(locale, 'tasks_available_title')}</b>")
        for campaign in campaigns:
            ids.append(int(campaign['id']))
            title = _campaign_title(locale, str(campaign['task_type']))
            lines.append('')
            lines.append(
                t(
                    locale,
                    'task_card',
                    title=f"#{campaign['id']} • {title}",
                    task_type=_task_type_label(locale, str(campaign['task_type'])),
                    reward=campaign['reward_per_task'],
                    currency=get_currency_name(locale),
                    hold_time=hold_text,
                    left=max(0, int(campaign['target_count']) - int(campaign['completed_count'])),
                )
            )
            if campaign.get('target_url'):
                lines.append(t(locale, 'task_open_hint', url=campaign['target_url']))
    else:
        lines.append('')
        lines.append(t(locale, 'tasks_empty'))

    markup = tasks_list_keyboard(locale, ids, open_claims)
    if edit:
        await message.edit_text('\n'.join(lines), reply_markup=markup)
    else:
        await message.answer('\n'.join(lines), reply_markup=markup)
