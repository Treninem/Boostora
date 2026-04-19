from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.filters.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.core.enums import CampaignStatus
from app.core.i18n import LEXICON, get_currency_name, normalize_locale, t
from app.keyboards.advertiser import (
    campaign_detail_keyboard,
    campaign_task_type_keyboard,
    campaigns_keyboard,
)
from app.keyboards.billing import topup_keyboard
from app.keyboards.start import advertiser_menu
from app.storage.campaigns import CampaignRepository
from app.storage.users import UserRepository
from app.storage.wallets import WalletRepository

router = Router(name='advertiser')

ADVERTISER_MENU_TEXTS = {
    value
    for locale_data in LEXICON.values()
    for key, value in locale_data.items()
    if key in {'menu_create_campaign', 'menu_campaigns', 'menu_analytics', 'menu_topup', 'menu_profile'}
}


class CampaignWizard(StatesGroup):
    title = State()
    target_url = State()
    target_count = State()
    reward = State()


async def _users(message_or_callback: Message | CallbackQuery) -> UserRepository:
    return message_or_callback.bot['users_repo']


async def _wallets(message_or_callback: Message | CallbackQuery) -> WalletRepository:
    return message_or_callback.bot['wallets_repo']


async def _campaigns(message_or_callback: Message | CallbackQuery) -> CampaignRepository:
    return message_or_callback.bot['campaigns_repo']


async def _get_context(message_or_callback: Message | CallbackQuery) -> tuple[dict, str]:
    users_repo = await _users(message_or_callback)
    user = await users_repo.get_user(message_or_callback.from_user.id if message_or_callback.from_user else 0)
    locale = normalize_locale((user or {}).get('locale'))
    return user or {}, locale


def _task_type_label(locale: str, task_type: str) -> str:
    return t(locale, f'task_type_{task_type}')


@router.message(F.text.in_(ADVERTISER_MENU_TEXTS))
async def advertiser_text_routes(message: Message, state: FSMContext) -> None:
    user, locale = await _get_context(message)
    if not user or user.get('role') != 'advertiser':
        return

    if message.text == t(locale, 'menu_create_campaign'):
        await state.clear()
        await state.set_state(CampaignWizard.title)
        await message.answer(
            f"<b>{t(locale, 'campaign_create_intro')}</b>\n\n{t(locale, 'campaign_ask_title')}",
            reply_markup=advertiser_menu(locale),
        )
        return

    if message.text == t(locale, 'menu_campaigns'):
        await _send_campaigns_list(message, user, locale)
        return

    if message.text == t(locale, 'menu_analytics'):
        await _send_analytics(message, user, locale)
        return

    if message.text == t(locale, 'menu_topup'):
        await _send_topup(message, user, locale)
        return

    if message.text == t(locale, 'menu_profile'):
        await _send_profile(message, user, locale)
        return


@router.message(CampaignWizard.title)
async def campaign_title_step(message: Message, state: FSMContext) -> None:
    user, locale = await _get_context(message)
    if not user or user.get('role') != 'advertiser':
        return
    title = (message.text or '').strip()
    if len(title) < 4:
        await message.answer(t(locale, 'campaign_invalid_title'), reply_markup=advertiser_menu(locale))
        return
    await state.update_data(title=title)
    await message.answer(
        t(locale, 'campaign_ask_type'),
        reply_markup=campaign_task_type_keyboard(locale),
    )


@router.callback_query(F.data == 'camp:new:cancel')
async def cancel_campaign_wizard(callback: CallbackQuery, state: FSMContext) -> None:
    user, locale = await _get_context(callback)
    await state.clear()
    if callback.message:
        await callback.message.answer(t(locale, 'campaign_cancelled'), reply_markup=advertiser_menu(locale))
    await callback.answer()


@router.callback_query(F.data.startswith('camp:new:type:'))
async def campaign_type_step(callback: CallbackQuery, state: FSMContext) -> None:
    user, locale = await _get_context(callback)
    if not user or user.get('role') != 'advertiser':
        await callback.answer()
        return
    task_type = callback.data.rsplit(':', 1)[1]
    await state.update_data(task_type=task_type)
    await state.set_state(CampaignWizard.target_url)
    if callback.message:
        await callback.message.answer(
            t(locale, 'campaign_ask_url', task_type=_task_type_label(locale, task_type)),
            reply_markup=advertiser_menu(locale),
        )
    await callback.answer()


@router.message(CampaignWizard.target_url)
async def campaign_url_step(message: Message, state: FSMContext) -> None:
    user, locale = await _get_context(message)
    if not user or user.get('role') != 'advertiser':
        return
    target_url = (message.text or '').strip()
    if not _is_valid_target_url(target_url):
        await message.answer(t(locale, 'campaign_invalid_url'), reply_markup=advertiser_menu(locale))
        return
    await state.update_data(target_url=target_url)
    await state.set_state(CampaignWizard.target_count)
    await message.answer(t(locale, 'campaign_ask_target'), reply_markup=advertiser_menu(locale))


@router.message(CampaignWizard.target_count)
async def campaign_target_step(message: Message, state: FSMContext) -> None:
    user, locale = await _get_context(message)
    if not user or user.get('role') != 'advertiser':
        return
    raw = (message.text or '').strip()
    if not raw.isdigit() or not 10 <= int(raw) <= 10000:
        await message.answer(t(locale, 'campaign_invalid_target'), reply_markup=advertiser_menu(locale))
        return
    await state.update_data(target_count=int(raw))
    await state.set_state(CampaignWizard.reward)
    await message.answer(t(locale, 'campaign_ask_reward'), reply_markup=advertiser_menu(locale))


@router.message(CampaignWizard.reward)
async def campaign_reward_step(message: Message, state: FSMContext) -> None:
    user, locale = await _get_context(message)
    if not user or user.get('role') != 'advertiser':
        return
    raw = (message.text or '').strip()
    if not raw.isdigit() or not 5 <= int(raw) <= 500:
        await message.answer(t(locale, 'campaign_invalid_reward'), reply_markup=advertiser_menu(locale))
        return

    data = await state.get_data()
    reward = int(raw)
    target_count = int(data['target_count'])
    budget_total = target_count * reward

    campaigns_repo = await _campaigns(message)
    campaign_id = await campaigns_repo.create_configured_draft(
        owner_user_id=user['user_id'],
        title=str(data['title']),
        task_type=str(data['task_type']),
        target_url=str(data['target_url']),
        target_count=target_count,
        reward_per_task=reward,
        budget_total=budget_total,
        locale=locale,
    )
    campaign = await campaigns_repo.get_campaign(campaign_id)
    await state.clear()

    text = '\n'.join([
        f"<b>{t(locale, 'campaign_created')}</b>",
        '',
        _campaign_card(locale, campaign or {}, include_url=True),
        '',
        t(locale, 'campaign_launch_ready'),
    ])
    await message.answer(text, reply_markup=campaign_detail_keyboard(locale, campaign or {'id': campaign_id, 'status': 'draft'}))


@router.message(Command('campaigns'))
async def campaigns_command(message: Message) -> None:
    user, locale = await _get_context(message)
    if user and user.get('role') == 'advertiser':
        await _send_campaigns_list(message, user, locale)


@router.message(Command('topup'))
async def topup_command(message: Message) -> None:
    user, locale = await _get_context(message)
    if user and user.get('role') == 'advertiser':
        await _send_topup(message, user, locale)


@router.message(Command('analytics'))
async def analytics_command(message: Message) -> None:
    user, locale = await _get_context(message)
    if user and user.get('role') == 'advertiser':
        await _send_analytics(message, user, locale)


@router.message(Command('profile'))
async def profile_command(message: Message) -> None:
    user, locale = await _get_context(message)
    if user and user.get('role') == 'advertiser':
        await _send_profile(message, user, locale)




@router.callback_query(F.data == 'camp:list')
async def campaign_list_callback(callback: CallbackQuery) -> None:
    user, locale = await _get_context(callback)
    if not user or user.get('role') != 'advertiser':
        await callback.answer()
        return
    if callback.message:
        await _send_campaigns_list(callback.message, user, locale, edit=True)
    await callback.answer()


@router.callback_query(F.data.startswith('camp:view:'))
async def view_campaign(callback: CallbackQuery) -> None:
    user, locale = await _get_context(callback)
    if not user or user.get('role') != 'advertiser':
        await callback.answer()
        return
    campaign_id = int(callback.data.rsplit(':', 1)[1])
    campaigns_repo = await _campaigns(callback)
    campaign = await campaigns_repo.get_campaign_for_owner(campaign_id, user['user_id'])
    if not campaign:
        await callback.answer(t(locale, 'campaign_not_found'), show_alert=True)
        return
    if callback.message:
        await callback.message.edit_text(
            _campaign_card(locale, campaign, include_url=True),
            reply_markup=campaign_detail_keyboard(locale, campaign),
        )
    await callback.answer()


@router.callback_query(F.data.startswith('camp:launch:'))
async def launch_campaign(callback: CallbackQuery) -> None:
    user, locale = await _get_context(callback)
    if not user or user.get('role') != 'advertiser':
        await callback.answer()
        return
    campaign_id = int(callback.data.rsplit(':', 1)[1])
    campaigns_repo = await _campaigns(callback)
    wallets_repo = await _wallets(callback)
    campaign = await campaigns_repo.get_campaign_for_owner(campaign_id, user['user_id'])
    if not campaign:
        await callback.answer(t(locale, 'campaign_not_found'), show_alert=True)
        return
    if str(campaign.get('status')) != CampaignStatus.DRAFT.value:
        await callback.answer()
        return
    wallet = await wallets_repo.get_wallet(user['user_id'])
    budget_total = int(campaign.get('budget_total', 0) or 0)
    if int(wallet.get('available_balance', 0) or 0) < budget_total:
        shortfall = budget_total - int(wallet.get('available_balance', 0) or 0)
        await callback.answer(
            t(locale, 'campaign_launch_need_topup', amount=shortfall, currency=get_currency_name(locale)),
            show_alert=True,
        )
        if callback.message:
            await callback.message.answer(
                t(locale, 'topup_hint', currency=get_currency_name(locale)),
                reply_markup=topup_keyboard(locale),
            )
        return
    await wallets_repo.add_available(
        user['user_id'],
        -budget_total,
        'spend_internal',
        description=t(locale, 'campaign_budget_reserved', campaign_id=campaign_id),
        meta={'campaign_id': campaign_id, 'action': 'launch_campaign'},
    )
    await campaigns_repo.set_status(campaign_id, CampaignStatus.ACTIVE.value)
    campaign = await campaigns_repo.get_campaign(campaign_id)
    if callback.message:
        await callback.message.edit_text(
            t(locale, 'campaign_launch_success') + '\n\n' + _campaign_card(locale, campaign or {}, include_url=True),
            reply_markup=campaign_detail_keyboard(locale, campaign or {}),
        )
    await callback.answer()


@router.callback_query(F.data.startswith('camp:pause:'))
async def pause_campaign(callback: CallbackQuery) -> None:
    user, locale = await _get_context(callback)
    if not user or user.get('role') != 'advertiser':
        await callback.answer()
        return
    campaign_id = int(callback.data.rsplit(':', 1)[1])
    campaigns_repo = await _campaigns(callback)
    campaign = await campaigns_repo.get_campaign_for_owner(campaign_id, user['user_id'])
    if not campaign:
        await callback.answer(t(locale, 'campaign_not_found'), show_alert=True)
        return
    await campaigns_repo.set_status(campaign_id, CampaignStatus.PAUSED.value)
    campaign = await campaigns_repo.get_campaign(campaign_id)
    if callback.message:
        await callback.message.edit_text(
            t(locale, 'campaign_paused') + '\n\n' + _campaign_card(locale, campaign or {}, include_url=True),
            reply_markup=campaign_detail_keyboard(locale, campaign or {}),
        )
    await callback.answer()


@router.callback_query(F.data.startswith('camp:resume:'))
async def resume_campaign(callback: CallbackQuery) -> None:
    user, locale = await _get_context(callback)
    if not user or user.get('role') != 'advertiser':
        await callback.answer()
        return
    campaign_id = int(callback.data.rsplit(':', 1)[1])
    campaigns_repo = await _campaigns(callback)
    campaign = await campaigns_repo.get_campaign_for_owner(campaign_id, user['user_id'])
    if not campaign:
        await callback.answer(t(locale, 'campaign_not_found'), show_alert=True)
        return
    await campaigns_repo.set_status(campaign_id, CampaignStatus.ACTIVE.value)
    campaign = await campaigns_repo.get_campaign(campaign_id)
    if callback.message:
        await callback.message.edit_text(
            t(locale, 'campaign_resumed') + '\n\n' + _campaign_card(locale, campaign or {}, include_url=True),
            reply_markup=campaign_detail_keyboard(locale, campaign or {}),
        )
    await callback.answer()


@router.callback_query(F.data.startswith('topup:'))
async def demo_topup(callback: CallbackQuery) -> None:
    user, locale = await _get_context(callback)
    if not user or user.get('role') != 'advertiser':
        await callback.answer()
        return
    amount = int(callback.data.split(':', 1)[1])
    wallets_repo = await _wallets(callback)
    await wallets_repo.add_available(
        user['user_id'],
        amount,
        'topup_confirmed',
        description=t(locale, 'topup_demo_success', amount=amount, currency=get_currency_name(locale)),
        meta={'mode': 'demo_topup', 'amount': amount},
    )
    if callback.message:
        await callback.message.answer(
            t(locale, 'topup_success', amount=amount, currency=get_currency_name(locale)),
            reply_markup=advertiser_menu(locale),
        )
    await callback.answer()


async def _send_topup(message: Message, user: dict, locale: str) -> None:
    wallets_repo = await _wallets(message)
    wallet = await wallets_repo.get_wallet(user['user_id'])
    billing_repo = message.bot['billing_repo']
    orders = await billing_repo.list_recent_orders(user['user_id'], limit=3)
    text_lines = [
        f"<b>💸 {t(locale, 'topup_title')}</b>",
        t(locale, 'wallet_available', available=wallet.get('available_balance', 0), currency=get_currency_name(locale)),
        '',
        t(locale, 'topup_hint', currency=get_currency_name(locale)),
        t(locale, 'topup_stars_hint'),
    ]
    if orders:
        text_lines.append('')
        text_lines.append(f"<b>{t(locale, 'billing_recent_title')}</b>")
        for order in orders:
            text_lines.append(t(
                locale,
                'billing_order_line',
                purpose=t(locale, f"billing_purpose_{order.get('purpose') or 'topup'}"),
                amount_xtr=order.get('amount_xtr', 0),
                status=t(locale, f"billing_status_{order.get('status') or 'created'}"),
            ))
    await message.answer(
        '\n'.join(text_lines),
        reply_markup=topup_keyboard(locale, enable_demo=message.bot['settings'].enable_demo_topup, enable_xtr=message.bot['settings'].enable_xtr_payments),
    )


async def _send_campaigns_list(message: Message, user: dict, locale: str, edit: bool = False) -> None:
    campaigns_repo = await _campaigns(message)
    campaigns = await campaigns_repo.list_user_campaigns(user['user_id'], limit=12)
    if not campaigns:
        text = f"<b>📣 {t(locale, 'campaigns_title')}</b>\n\n{t(locale, 'campaigns_empty')}"
        if edit:
            await message.edit_text(text)
        else:
            await message.answer(text, reply_markup=advertiser_menu(locale))
        return

    lines = [f"<b>📣 {t(locale, 'campaigns_title')}</b>"]
    for campaign in campaigns[:5]:
        lines.append('')
        lines.append(_campaign_card(locale, campaign, include_url=False))
    markup = campaigns_keyboard(locale, campaigns[:5])
    if edit:
        await message.edit_text('\n'.join(lines), reply_markup=markup)
    else:
        await message.answer('\n'.join(lines), reply_markup=markup)


async def _send_analytics(message: Message, user: dict, locale: str) -> None:
    campaigns_repo = await _campaigns(message)
    campaigns = await campaigns_repo.list_user_campaigns(user['user_id'], limit=50)
    if not campaigns:
        await message.answer(
            f"<b>📊 {t(locale, 'analytics_title')}</b>\n\n{t(locale, 'analytics_empty')}",
            reply_markup=advertiser_menu(locale),
        )
        return
    total = len(campaigns)
    active = sum(1 for item in campaigns if item.get('status') == CampaignStatus.ACTIVE.value)
    drafts = sum(1 for item in campaigns if item.get('status') == CampaignStatus.DRAFT.value)
    completed = sum(1 for item in campaigns if item.get('status') == CampaignStatus.COMPLETED.value)
    total_budget = sum(int(item.get('budget_total', 0) or 0) for item in campaigns)
    target_total = sum(int(item.get('target_count', 0) or 0) for item in campaigns)
    completed_total = sum(int(item.get('completed_count', 0) or 0) for item in campaigns)
    conversion = round((completed_total / target_total) * 100, 1) if target_total else 0.0
    text = '\n'.join([
        f"<b>📊 {t(locale, 'analytics_title')}</b>",
        t(locale, 'analytics_total_campaigns', count=total),
        t(locale, 'analytics_active_campaigns', count=active),
        t(locale, 'analytics_draft_campaigns', count=drafts),
        t(locale, 'analytics_completed_campaigns', count=completed),
        t(locale, 'analytics_total_budget', amount=total_budget, currency=get_currency_name(locale)),
        t(locale, 'analytics_progress', done=completed_total, total=target_total, percent=conversion),
    ])
    await message.answer(text, reply_markup=advertiser_menu(locale))



async def _send_profile(message: Message, user: dict, locale: str) -> None:
    wallets_repo = await _wallets(message)
    wallet = await wallets_repo.get_wallet(user['user_id'])
    text = '\n'.join([
        f"<b>✨ {t(locale, 'profile_title')}</b>",
        t(locale, 'profile_id', user_id=user['user_id']),
        t(locale, 'profile_role', role=t(locale, 'role_advertiser')),
        t(locale, 'profile_tier', tier=t(locale, f"tier_{user.get('tier') or 'new'}")),
        t(locale, 'profile_tasks', tasks=user.get('completed_tasks', 0)),
        t(locale, 'profile_risk', risk=user.get('risk_score', 0)),
        '',
        t(locale, 'wallet_available', available=wallet.get('available_balance', 0), currency=get_currency_name(locale)),
    ])
    await message.answer(text, reply_markup=advertiser_menu(locale))


def _campaign_card(locale: str, campaign: dict, include_url: bool = False) -> str:
    lines = [
        t(locale, 'campaign_card_header', id=campaign.get('id', '—'), title=campaign.get('title') or '—'),
        t(locale, 'campaign_card_status', status=t(locale, f"campaign_status_{campaign.get('status') or 'draft'}")),
        t(locale, 'campaign_card_type', task_type=_task_type_label(locale, str(campaign.get('task_type') or 'channel_join'))),
        t(locale, 'campaign_card_reward', amount=campaign.get('reward_per_task', 0), currency=get_currency_name(locale)),
        t(locale, 'campaign_card_target', current=campaign.get('completed_count', 0), total=campaign.get('target_count', 0)),
        t(locale, 'campaign_card_budget', amount=campaign.get('budget_total', 0), currency=get_currency_name(locale)),
    ]
    if include_url:
        lines.append(t(locale, 'campaign_card_url', url=campaign.get('target_url') or '—'))
    return '\n'.join(lines)



def _is_valid_target_url(value: str) -> bool:
    value = value.strip().lower()
    if value.startswith('https://') or value.startswith('http://'):
        return True
    if value.startswith('t.me/') or value.startswith('@'):
        return True
    return False
