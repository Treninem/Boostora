import logging

import telebot
from telebot.types import CallbackQuery, Message

from app.config import settings
from app.keyboards.inline import (
    admin_home_keyboard,
    admin_input_keyboard,
    admin_logs_keyboard,
    admin_queue_keyboard,
    admin_submission_keyboard,
    blocked_keyboard,
    campaign_card_keyboard,
    campaign_input_keyboard,
    campaign_preview_keyboard,
    campaign_task_type_keyboard,
    campaigns_keyboard,
    history_keyboard,
    language_keyboard,
    main_menu_keyboard,
    proof_wait_keyboard,
    referrals_keyboard,
    rewards_keyboard,
    role_keyboard,
    section_keyboard,
    stats_keyboard,
    subscription_keyboard,
    task_detail_keyboard,
    tasks_keyboard,
    vip_keyboard,
    wallet_keyboard,
)
from app.services.admin import AdminService
from app.services.admin_logs import AdminLogService
from app.services.campaigns import CampaignService
from app.services.client_campaigns import MODE_CONFIRM, ClientCampaignService
from app.services.performer import PerformerService
from app.services.referrals import ReferralService
from app.services.rewards import RewardService
from app.services.subscriptions import SubscriptionService
from app.services.transactions import TransactionService
from app.services.ui_state import UIStateService
from app.services.users import UserService
from app.services.vip import VIP_PLANS, VipService
from app.services.wallets import WalletService
from app.utils.ui import render_managed_screen


logger = logging.getLogger(__name__)

SCREEN_LANGUAGE = 'language'
SCREEN_ROLE = 'role'
SCREEN_REQUIRED_SUBSCRIPTION = 'required_subscription'
SCREEN_MAIN_MENU = 'main_menu'
SCREEN_PROFILE = 'profile'
SCREEN_TASKS = 'tasks'
SCREEN_TASK_DETAIL_PREFIX = 'task:'
SCREEN_SUBMISSION_PREFIX = 'submission:'
SCREEN_PROOF_WAIT_PREFIX = 'proof_wait:'
SCREEN_WALLET = 'wallet'
SCREEN_HISTORY = 'history'
SCREEN_CAMPAIGNS = 'campaigns'
SCREEN_STATS = 'stats'
SCREEN_CAMPAIGN_CREATE = 'campaign_create'
SCREEN_CAMPAIGN_PREVIEW = 'campaign_preview'
SCREEN_CAMPAIGN_INPUT_PREFIX = 'campaign_input:'
SCREEN_CAMPAIGN_CARD_PREFIX = 'campaign:'
SCREEN_VIP = 'vip'
SCREEN_REWARDS = 'rewards'
SCREEN_REFERRALS = 'referrals'
SCREEN_BLOCKED = 'blocked'
SCREEN_ADMIN = 'admin'
SCREEN_ADMIN_QUEUE = 'admin_queue'
SCREEN_ADMIN_LOGS = 'admin_logs'
SCREEN_ADMIN_SUBMISSION_PREFIX = 'admin_submission:'
SCREEN_ADMIN_REJECT_PREFIX = 'admin_reject:'
SCREEN_ADMIN_RISK_PREFIX = 'admin_risk:'
SCREEN_ADMIN_BALANCE_PREFIX = 'admin_balance:'

SECTION_TO_SCREEN = {
    'profile': SCREEN_PROFILE,
    'tasks': SCREEN_TASKS,
    'wallet': SCREEN_WALLET,
    'history': SCREEN_HISTORY,
    'campaigns': SCREEN_CAMPAIGNS,
    'stats': SCREEN_STATS,
    'vip': SCREEN_VIP,
    'rewards': SCREEN_REWARDS,
    'referrals': SCREEN_REFERRALS,
    'admin': SCREEN_ADMIN,
    'admin_queue': SCREEN_ADMIN_QUEUE,
    'admin_logs': SCREEN_ADMIN_LOGS,
}

TASK_TYPE_LABEL_KEYS = {
    'channel_subscribe': 'campaign_task_type_channel_subscribe',
    'chat_join': 'campaign_task_type_chat_join',
    'post_view': 'campaign_task_type_post_view',
    'bot_start': 'campaign_task_type_bot_start',
    'mini_app_open': 'campaign_task_type_mini_app_open',
}

CAMPAIGN_STATUS_LABEL_KEYS = {
    'draft': 'campaign_status_draft',
    'active': 'campaign_status_active',
    'paused': 'campaign_status_paused',
    'completed': 'campaign_status_completed',
    'archived': 'campaign_status_archived',
}

Target = CallbackQuery | Message




def _format_percent(value: float | int) -> str:
    if int(value) == float(value):
        return str(int(value))
    return f'{value:.2f}'.rstrip('0').rstrip('.')

def task_screen_key(campaign_id: int) -> str:
    return f'{SCREEN_TASK_DETAIL_PREFIX}{campaign_id}'



def submission_screen_key(submission_id: int) -> str:
    return f'{SCREEN_SUBMISSION_PREFIX}{submission_id}'



def proof_wait_screen_key(submission_id: int) -> str:
    return f'{SCREEN_PROOF_WAIT_PREFIX}{submission_id}'



def campaign_input_screen_key(step: str) -> str:
    return f'{SCREEN_CAMPAIGN_INPUT_PREFIX}{step}'



def campaign_card_screen_key(campaign_id: int) -> str:
    return f'{SCREEN_CAMPAIGN_CARD_PREFIX}{campaign_id}'


def admin_submission_screen_key(submission_id: int) -> str:
    return f'{SCREEN_ADMIN_SUBMISSION_PREFIX}{submission_id}'


def admin_reject_screen_key(submission_id: int) -> str:
    return f'{SCREEN_ADMIN_REJECT_PREFIX}{submission_id}'


def admin_risk_screen_key(user_id: int) -> str:
    return f'{SCREEN_ADMIN_RISK_PREFIX}{user_id}'


def admin_balance_screen_key(user_id: int) -> str:
    return f'{SCREEN_ADMIN_BALANCE_PREFIX}{user_id}'



def _chat_id(target: Target) -> int:
    if isinstance(target, CallbackQuery):
        return int(target.message.chat.id)
    return int(target.chat.id)



def _user_id(target: Target) -> int:
    return int(target.from_user.id)



def _screen_payload(screen_key: str, prefix: str) -> int | None:
    if not screen_key.startswith(prefix):
        return None
    raw = screen_key.split(':', 1)[1]
    if not raw.isdigit():
        return None
    return int(raw)



def _screen_suffix(screen_key: str, prefix: str) -> str | None:
    if not screen_key.startswith(prefix):
        return None
    return screen_key.split(':', 1)[1].strip() or None



def _prepend_notice(user_id: int, body: str, notice_key: str | None = None, notice_text: str | None = None) -> str:
    notice = notice_text
    if not notice and notice_key:
        notice = UserService.t(user_id, notice_key)
    if not notice:
        return body
    return f'{notice}\n\n{body}'



def _task_type_label(user_id: int, task_type: str) -> str:
    key = TASK_TYPE_LABEL_KEYS.get(task_type)
    return UserService.t(user_id, key) if key else task_type



def _campaign_status_label(user_id: int, status: str) -> str:
    key = CAMPAIGN_STATUS_LABEL_KEYS.get(status)
    return UserService.t(user_id, key) if key else status



def _perk_title(user_id: int, tier_code: str) -> str:
    if tier_code in VIP_PLANS:
        return UserService.t(user_id, str(VIP_PLANS[tier_code]['title_key']))
    reward_items = RewardService.get_items()
    if tier_code in reward_items:
        return UserService.t(user_id, str(reward_items[tier_code]['title_key']))
    return tier_code



def _build_main_menu_text(user_id: int) -> str:
    role = UserService.get_role(user_id)
    if not role:
        return UserService.t(user_id, 'choose_role')
    return UserService.t(
        user_id,
        'main_menu',
        brand=settings.brand_name,
        language=UserService.language_label(UserService.get_language(user_id)),
        role=UserService.role_label(user_id, role),
    )



def _build_profile_text(user_id: int) -> str:
    wallet = WalletService.get_summary(user_id)
    active_tasks = PerformerService.get_active_submission_count(user_id)
    task_limit = PerformerService.get_active_task_limit(user_id)
    role = UserService.get_role(user_id) or 'performer'
    return UserService.t(
        user_id,
        'profile_screen',
        user_id=user_id,
        role=UserService.role_label(user_id, role),
        active_tasks=active_tasks,
        task_limit=task_limit,
        available=wallet['available_balance'],
        hold=wallet['hold_balance'],
        earned=wallet['lifetime_earned'],
    )



def _build_tasks_text(user_id: int, tasks) -> str:
    active_tasks = PerformerService.get_active_submission_count(user_id)
    task_limit = PerformerService.get_active_task_limit(user_id)
    if not tasks:
        return UserService.t(user_id, 'tasks_empty')
    return UserService.t(user_id, 'tasks_screen', active_tasks=active_tasks, task_limit=task_limit)



def _build_task_detail_text(user_id: int, campaign_id: int) -> tuple[str, dict[str, object]]:
    campaign = PerformerService.get_campaign(campaign_id)
    if not campaign:
        return UserService.t(user_id, 'task_not_found'), {
            'target_url': settings.required_chat_invite_link or 'https://t.me',
            'can_take': False,
            'can_submit': False,
            'submission_id': None,
        }

    submission = PerformerService.get_submission_for_campaign(user_id, campaign_id)
    remaining = max(int(campaign['total_quantity']) - int(campaign['completed_quantity']), 0)
    can_take = submission is None and str(campaign['status']) == 'active' and remaining > 0
    can_submit = submission is not None and str(submission['status']) == 'taken'
    if submission is None:
        status_label = UserService.t(user_id, 'task_detail_available')
    elif str(submission['status']) == 'taken':
        status_label = UserService.t(user_id, 'task_detail_taken')
    elif str(submission['status']) == 'manual_review':
        status_label = UserService.t(user_id, 'task_detail_manual_review')
    elif str(submission['status']) == 'rejected':
        status_label = UserService.t(user_id, 'task_detail_rejected')
    else:
        status_label = UserService.t(user_id, 'task_detail_submitted')

    text = UserService.t(
        user_id,
        'task_detail',
        title=str(campaign['title'] or f'#{campaign_id}'),
        task_type=_task_type_label(user_id, str(campaign['task_type'])),
        reward=int(campaign['reward_amount']),
        remaining=remaining,
        status=status_label,
    )
    return text, {
        'target_url': str(campaign['target_url']),
        'can_take': can_take,
        'can_submit': can_submit,
        'submission_id': int(submission['id']) if submission else None,
    }



def _build_wallet_text(user_id: int, released: int) -> str:
    wallet = WalletService.get_summary(user_id)
    return UserService.t(
        user_id,
        'wallet_screen',
        available=wallet['available_balance'],
        hold=wallet['hold_balance'],
        internal=wallet['internal_balance'],
        internal_name=UserService.internal_currency_label(user_id),
        earned=wallet['lifetime_earned'],
        withdrawn=wallet['total_withdrawn'],
        released=released,
    )



def _build_history_text(user_id: int) -> str:
    rows = TransactionService.get_history(user_id, limit=20)
    if not rows:
        return UserService.t(user_id, 'history_screen', items=UserService.t(user_id, 'history_empty'))
    items: list[str] = []
    for row in rows[:10]:
        created_at = str(row['created_at']).replace('T', ' ')[:16]
        currency_code = str(row['currency_code'])
        currency_label = UserService.internal_currency_label(user_id) if currency_code == 'BST' else currency_code
        items.append(
            UserService.t(
                user_id,
                'history_row',
                date=created_at,
                entry_type=str(row['entry_type']),
                amount=int(row['amount']),
                currency=currency_label,
                status=str(row['status']),
            )
        )
    return UserService.t(user_id, 'history_screen', items='\n'.join(items))



def _build_campaigns_text(user_id: int, campaigns) -> str:
    stats = CampaignService.get_owner_stats(user_id)
    if not campaigns:
        return UserService.t(user_id, 'campaigns_empty')
    return UserService.t(
        user_id,
        'campaigns_screen',
        total=stats['total_campaigns'],
        active=stats['active_campaigns'],
        paused=stats['paused_campaigns'],
        drafts=stats['draft_campaigns'],
    )



def _build_campaign_input_text(user_id: int, step: str) -> str:
    draft = ClientCampaignService.get_draft(user_id) or {}
    task_type = _task_type_label(user_id, str(draft.get('task_type') or '—'))
    target_url = str(draft.get('target_url') or '—')
    reward_amount = str(draft.get('reward_amount') or '—')
    total_quantity = str(draft.get('total_quantity') or '—')

    prompt_map = {
        'target': UserService.t(user_id, 'campaign_target_prompt'),
        'reward': UserService.t(user_id, 'campaign_reward_prompt'),
        'quantity': UserService.t(user_id, 'campaign_quantity_prompt'),
    }
    return UserService.t(
        user_id,
        'campaign_input_screen',
        step=prompt_map.get(step, UserService.t(user_id, 'campaign_target_prompt')),
        task_type=task_type,
        target_url=target_url,
        reward=reward_amount,
        quantity=total_quantity,
    )



def _build_campaign_preview_text(user_id: int) -> str:
    draft = ClientCampaignService.get_draft(user_id)
    if not draft or str(draft.get('mode') or '') != MODE_CONFIRM:
        return UserService.t(user_id, 'campaign_draft_missing')
    return UserService.t(
        user_id,
        'campaign_preview_screen',
        task_type=_task_type_label(user_id, str(draft['task_type'])),
        target_url=str(draft['target_url']),
        reward=int(draft['reward_amount']),
        quantity=int(draft['total_quantity']),
        budget=int(draft['budget_total']),
    )



def _build_campaign_card_text(user_id: int, campaign_id: int) -> str:
    campaign = CampaignService.get_owned_campaign(user_id, campaign_id)
    if not campaign:
        return UserService.t(user_id, 'campaign_not_found')
    return UserService.t(
        user_id,
        'campaign_card_screen',
        campaign_id=campaign_id,
        title=str(campaign['title'] or f'#{campaign_id}'),
        task_type=_task_type_label(user_id, str(campaign['task_type'])),
        target_url=str(campaign['target_url']),
        reward=int(campaign['reward_amount']),
        quantity=int(campaign['total_quantity']),
        completed=int(campaign['completed_quantity']),
        rejected=int(campaign['rejected_quantity']),
        budget_total=int(campaign['budget_total']),
        budget_spent=int(campaign['budget_spent']),
        budget_reserved=int(campaign['budget_reserved']),
        budget_remaining=CampaignService.get_remaining_budget(campaign),
        status=_campaign_status_label(user_id, str(campaign['status'])),
    )



def _build_stats_text(user_id: int) -> str:
    stats = CampaignService.get_owner_stats(user_id)
    return UserService.t(
        user_id,
        'campaign_stats_screen',
        total=stats['total_campaigns'],
        active=stats['active_campaigns'],
        paused=stats['paused_campaigns'],
        drafts=stats['draft_campaigns'],
        completed=stats['completed_total'],
        rejected=stats['rejected_total'],
        budget=stats['budget_total'],
        spent=stats['budget_spent'],
        reserved=stats['budget_reserved'],
        remaining=stats['budget_remaining'],
    )



def _build_vip_text(user_id: int) -> str:
    summary = VipService.get_vip_summary(user_id)
    subscriptions = summary['subscriptions']
    if subscriptions:
        active_lines = [
            UserService.t(
                user_id,
                'vip_active_row',
                title=_perk_title(user_id, str(item['tier_code'])),
                expires_at=str(item['expires_at']).replace('T', ' ')[:16],
            )
            for item in subscriptions[:5]
        ]
        active_block = '\n'.join(active_lines)
    else:
        active_block = UserService.t(user_id, 'vip_no_active')
    return UserService.t(
        user_id,
        'vip_screen',
        active_block=active_block,
        hold_speed=summary['hold_speed_percent'],
        task_bonus=summary['active_task_limit_bonus'],
        priority=summary['priority_level'],
        ref_bonus=_format_percent(summary['referral_rate_bonus_bps'] / 100),
        internal_name=UserService.internal_currency_label(user_id),
    )



def _build_rewards_text(user_id: int) -> str:
    wallet = WalletService.get_summary(user_id)
    item_lines = []
    for item in RewardService.get_items().values():
        item_lines.append(
            UserService.t(
                user_id,
                'reward_item_row',
                title=UserService.t(user_id, str(item['title_key'])),
                price=int(item['price']),
                internal_name=UserService.internal_currency_label(user_id),
                desc=UserService.t(user_id, str(item['desc_key'])),
            )
        )
    items_text = '\n\n'.join(item_lines)
    return UserService.t(
        user_id,
        'rewards_screen',
        internal_name=UserService.internal_currency_label(user_id),
        balance=wallet['internal_balance'],
        items=items_text,
    )



def _display_name_from_row(row) -> str:
    username = str(row['username'] or '').strip()
    if username:
        return f'@{username}'
    first_name = str(row['first_name'] or '').strip()
    last_name = str(row['last_name'] or '').strip()
    full_name = ' '.join(part for part in [first_name, last_name] if part).strip()
    return full_name or f"ID {int(row['referred_user_id'])}"



def _build_referrals_text(user_id: int) -> str:
    summary = ReferralService.get_summary(user_id)
    rows = summary['rows']
    if rows:
        items = '\n'.join(
            UserService.t(
                user_id,
                'referral_row',
                name=_display_name_from_row(row),
                earned=int(row['total_earned']),
                joined=str(row['joined_at']).replace('T', ' ')[:10],
                internal_name=UserService.internal_currency_label(user_id),
            )
            for row in rows[:8]
        )
    else:
        items = UserService.t(user_id, 'referrals_empty')
    return UserService.t(
        user_id,
        'referrals_screen',
        link=summary['link'],
        count=summary['invited_count'],
        earned=summary['total_earned'],
        rate=_format_percent(summary['current_rate_percent']),
        internal_name=UserService.internal_currency_label(user_id),
        items=items,
    )



def _build_blocked_text(user_id: int) -> str:
    return UserService.t(user_id, 'blocked_screen', support=settings.support_username)


def _build_admin_home_text(user_id: int) -> str:
    stats = AdminService.get_dashboard_stats()
    return UserService.t(
        user_id,
        'admin_home_screen',
        queue=stats['queue_count'],
        blocked=stats['blocked_users'],
        high_risk=stats['high_risk_users'],
        rejected=stats['rejected_total'],
    )


def _build_admin_queue_text(user_id: int, submissions) -> str:
    if not submissions:
        return UserService.t(user_id, 'admin_queue_empty')
    rows = []
    for item in submissions[:10]:
        performer = str(item['username'] or '').strip()
        performer_label = f'@{performer}' if performer else f"ID {int(item['performer_user_id'])}"
        rows.append(
            UserService.t(
                user_id,
                'admin_queue_line',
                submission_id=int(item['id']),
                title=str(item['campaign_title'] or f"#{int(item['campaign_id'])}"),
                performer=performer_label,
                risk=int(item['risk_score']),
                user_risk=int(item['user_risk_score']),
            )
        )
    return UserService.t(user_id, 'admin_queue_screen', items='\n'.join(rows))


def _build_admin_submission_text(user_id: int, submission_id: int) -> tuple[str, dict[str, object] | None]:
    card = AdminService.get_submission_card(submission_id)
    if not card:
        return UserService.t(user_id, 'admin_submission_not_found'), None
    submission = card['submission']
    stats = card['stats']
    proof = str(submission['proof_text'] or '—')
    events = card['events']
    if events:
        event_lines = '\n'.join(
            UserService.t(
                user_id,
                'admin_risk_event_row',
                event_type=str(event['event_type']),
                score=int(event['score_delta']),
                created=str(event['created_at']).replace('T', ' ')[:16],
            )
            for event in events
        )
    else:
        event_lines = UserService.t(user_id, 'admin_risk_events_empty')
    performer = str(submission['username'] or '').strip()
    performer_label = f'@{performer}' if performer else f"ID {int(submission['performer_user_id'])}"
    text = UserService.t(
        user_id,
        'admin_submission_screen',
        submission_id=int(submission['id']),
        title=str(submission['campaign_title'] or f"#{int(submission['campaign_id'])}"),
        performer=performer_label,
        performer_id=int(submission['performer_user_id']),
        user_status=str(submission['user_status']),
        submission_status=str(submission['status']),
        reward=int(submission['reward_amount']),
        submission_risk=int(submission['risk_score']),
        user_risk=int(submission['user_risk_score']),
        approved=stats['approved_count'],
        rejected=stats['rejected_count'],
        review_count=stats['review_count'],
        target=str(submission['campaign_target_url']),
        proof=proof[:1200],
        submitted_at=str(submission['submitted_at'] or '—').replace('T', ' ')[:19],
        reject_reason=str(submission['reject_reason'] or '—'),
        events=event_lines,
    )
    return text, card


def _build_admin_logs_text(user_id: int) -> str:
    rows = AdminLogService.get_logs(limit=15)
    if not rows:
        return UserService.t(user_id, 'admin_logs_empty')
    items = []
    for row in rows:
        items.append(
            UserService.t(
                user_id,
                'admin_log_row',
                created=str(row['created_at']).replace('T', ' ')[:16],
                admin_id=int(row['admin_user_id']),
                target_id=str(row['target_user_id'] or '—'),
                action=str(row['action']),
                details=str(row['details'] or '—')[:120],
            )
        )
    return UserService.t(user_id, 'admin_logs_screen', items='\n'.join(items))


def _build_admin_input_text(user_id: int, kind: str, target_id: int) -> str:
    if kind == 'reject':
        return UserService.t(user_id, 'admin_reject_prompt', submission_id=target_id)
    target_user = UserService.get_user(target_id)
    display = f"@{str(target_user['username'])}" if target_user and target_user['username'] else f'ID {target_id}'
    if kind == 'risk':
        risk = int(target_user['risk_score']) if target_user else 0
        return UserService.t(user_id, 'admin_adjust_risk_prompt', target=display, user_id=target_id, current=risk)
    return UserService.t(user_id, 'admin_adjust_balance_prompt', target=display, user_id=target_id)



def resolve_next_screen(bot: telebot.TeleBot, user_id: int, chat_id: int) -> str:
    if not UserService.can_access_bot(user_id):
        return SCREEN_BLOCKED
    role = UserService.get_role(user_id)
    if not role:
        return SCREEN_ROLE
    if SubscriptionService.should_enforce_required_chat(chat_id) and not SubscriptionService.is_user_subscribed(bot, user_id):
        return SCREEN_REQUIRED_SUBSCRIPTION
    return SCREEN_MAIN_MENU



def render_current(bot: telebot.TeleBot, target: Target, notice_key: str | None = None, notice_text: str | None = None) -> None:
    state = UIStateService.get_state(_user_id(target))
    if state and state['current_screen']:
        render_screen(bot, target, str(state['current_screen']), notice_key=notice_key, notice_text=notice_text)
        return
    render_entry(bot, target)



def render_screen(
    bot: telebot.TeleBot,
    target: Target,
    screen_key: str,
    notice_key: str | None = None,
    notice_text: str | None = None,
) -> None:
    user_id = _user_id(target)
    chat_id = _chat_id(target)
    UserService.ensure_user(target.from_user)
    if not UserService.can_access_bot(user_id) and screen_key != SCREEN_BLOCKED:
        screen_key = SCREEN_BLOCKED
    released = PerformerService.release_due_holds(user_id)

    if screen_key == SCREEN_LANGUAGE:
        text = _prepend_notice(user_id, UserService.t(user_id, 'welcome', brand=settings.brand_name), notice_key, notice_text)
        render_managed_screen(
            bot,
            target=target,
            user_id=user_id,
            chat_id=chat_id,
            screen_key=SCREEN_LANGUAGE,
            text=text,
            reply_markup_builder=lambda version: language_keyboard(version),
        )
        return

    if screen_key == SCREEN_ROLE:
        text = _prepend_notice(user_id, UserService.t(user_id, 'choose_role'), notice_key, notice_text)
        render_managed_screen(
            bot,
            target=target,
            user_id=user_id,
            chat_id=chat_id,
            screen_key=SCREEN_ROLE,
            text=text,
            reply_markup_builder=lambda version: role_keyboard(user_id, version),
        )
        return

    if screen_key == SCREEN_REQUIRED_SUBSCRIPTION:
        text = _prepend_notice(user_id, UserService.t(user_id, 'required_subscription_text'), notice_key, notice_text)
        render_managed_screen(
            bot,
            target=target,
            user_id=user_id,
            chat_id=chat_id,
            screen_key=SCREEN_REQUIRED_SUBSCRIPTION,
            text=text,
            reply_markup_builder=lambda version: subscription_keyboard(user_id, version),
        )
        return

    if screen_key == SCREEN_BLOCKED:
        text = _prepend_notice(user_id, _build_blocked_text(user_id), notice_key, notice_text)
        render_managed_screen(
            bot,
            target=target,
            user_id=user_id,
            chat_id=chat_id,
            screen_key=SCREEN_BLOCKED,
            text=text,
            reply_markup_builder=lambda version: blocked_keyboard(user_id, version),
        )
        return

    if (
        screen_key in {SCREEN_ADMIN, SCREEN_ADMIN_QUEUE, SCREEN_ADMIN_LOGS}
        or screen_key.startswith(SCREEN_ADMIN_SUBMISSION_PREFIX)
        or screen_key.startswith(SCREEN_ADMIN_REJECT_PREFIX)
        or screen_key.startswith(SCREEN_ADMIN_RISK_PREFIX)
        or screen_key.startswith(SCREEN_ADMIN_BALANCE_PREFIX)
    ) and not UserService.is_admin(user_id):
        render_screen(bot, target, SCREEN_MAIN_MENU, notice_key='admin_access_denied')
        return

    if screen_key == SCREEN_MAIN_MENU:
        body = _build_main_menu_text(user_id)
        if released:
            released_text = UserService.t(user_id, 'released_notice', released=released)
            text = _prepend_notice(user_id, body, notice_text=released_text if not notice_key and not notice_text else None)
            text = _prepend_notice(user_id, text, notice_key, notice_text)
        else:
            text = _prepend_notice(user_id, body, notice_key, notice_text)
        role = UserService.get_role(user_id)
        render_managed_screen(
            bot,
            target=target,
            user_id=user_id,
            chat_id=chat_id,
            screen_key=SCREEN_MAIN_MENU,
            text=text,
            reply_markup_builder=lambda version: main_menu_keyboard(user_id, role, version),
        )
        return

    if screen_key == SCREEN_PROFILE:
        text = _prepend_notice(user_id, _build_profile_text(user_id), notice_key, notice_text)
        render_managed_screen(
            bot,
            target=target,
            user_id=user_id,
            chat_id=chat_id,
            screen_key=SCREEN_PROFILE,
            text=text,
            reply_markup_builder=lambda version: section_keyboard(user_id, version),
        )
        return

    if screen_key == SCREEN_TASKS:
        tasks = PerformerService.list_available_tasks(user_id)
        text = _prepend_notice(user_id, _build_tasks_text(user_id, tasks), notice_key, notice_text)
        render_managed_screen(
            bot,
            target=target,
            user_id=user_id,
            chat_id=chat_id,
            screen_key=SCREEN_TASKS,
            text=text,
            reply_markup_builder=lambda version: tasks_keyboard(user_id, version, tasks),
        )
        return

    campaign_id = _screen_payload(screen_key, SCREEN_TASK_DETAIL_PREFIX)
    if campaign_id is not None:
        text, meta = _build_task_detail_text(user_id, campaign_id)
        text = _prepend_notice(user_id, text, notice_key, notice_text)
        render_managed_screen(
            bot,
            target=target,
            user_id=user_id,
            chat_id=chat_id,
            screen_key=screen_key,
            text=text,
            reply_markup_builder=lambda version: task_detail_keyboard(
                user_id,
                version,
                campaign_id,
                target_url=str(meta['target_url']),
                can_take=bool(meta['can_take']),
                can_submit=bool(meta['can_submit']),
                submission_id=meta['submission_id'],
            ),
        )
        return

    submission_id = _screen_payload(screen_key, SCREEN_SUBMISSION_PREFIX)
    if submission_id is not None:
        submission = PerformerService.get_submission(submission_id)
        if not submission or int(submission['performer_user_id']) != user_id:
            render_screen(bot, target, SCREEN_TASKS, notice_key='task_not_found')
            return
        render_screen(bot, target, task_screen_key(int(submission['campaign_id'])), notice_key=notice_key, notice_text=notice_text)
        return

    proof_submission_id = _screen_payload(screen_key, SCREEN_PROOF_WAIT_PREFIX)
    if proof_submission_id is not None:
        text = _prepend_notice(user_id, UserService.t(user_id, 'proof_prompt'), notice_key, notice_text)
        render_managed_screen(
            bot,
            target=target,
            user_id=user_id,
            chat_id=chat_id,
            screen_key=screen_key,
            text=text,
            reply_markup_builder=lambda version: proof_wait_keyboard(user_id, version, proof_submission_id),
        )
        return

    if screen_key == SCREEN_WALLET:
        text = _prepend_notice(user_id, _build_wallet_text(user_id, released), notice_key, notice_text)
        render_managed_screen(
            bot,
            target=target,
            user_id=user_id,
            chat_id=chat_id,
            screen_key=SCREEN_WALLET,
            text=text,
            reply_markup_builder=lambda version: wallet_keyboard(user_id, version),
        )
        return

    if screen_key == SCREEN_HISTORY:
        text = _prepend_notice(user_id, _build_history_text(user_id), notice_key, notice_text)
        render_managed_screen(
            bot,
            target=target,
            user_id=user_id,
            chat_id=chat_id,
            screen_key=SCREEN_HISTORY,
            text=text,
            reply_markup_builder=lambda version: history_keyboard(user_id, version),
        )
        return

    if screen_key == SCREEN_VIP:
        text = _prepend_notice(user_id, _build_vip_text(user_id), notice_key, notice_text)
        render_managed_screen(
            bot,
            target=target,
            user_id=user_id,
            chat_id=chat_id,
            screen_key=SCREEN_VIP,
            text=text,
            reply_markup_builder=lambda version: vip_keyboard(user_id, version),
        )
        return

    if screen_key == SCREEN_REWARDS:
        text = _prepend_notice(user_id, _build_rewards_text(user_id), notice_key, notice_text)
        render_managed_screen(
            bot,
            target=target,
            user_id=user_id,
            chat_id=chat_id,
            screen_key=SCREEN_REWARDS,
            text=text,
            reply_markup_builder=lambda version: rewards_keyboard(user_id, version),
        )
        return

    if screen_key == SCREEN_REFERRALS:
        text = _prepend_notice(user_id, _build_referrals_text(user_id), notice_key, notice_text)
        render_managed_screen(
            bot,
            target=target,
            user_id=user_id,
            chat_id=chat_id,
            screen_key=SCREEN_REFERRALS,
            text=text,
            reply_markup_builder=lambda version: referrals_keyboard(user_id, version),
        )
        return

    if screen_key == SCREEN_CAMPAIGNS:
        campaigns = CampaignService.get_campaigns_for_owner(user_id)
        text = _prepend_notice(user_id, _build_campaigns_text(user_id, campaigns), notice_key, notice_text)
        render_managed_screen(
            bot,
            target=target,
            user_id=user_id,
            chat_id=chat_id,
            screen_key=SCREEN_CAMPAIGNS,
            text=text,
            reply_markup_builder=lambda version: campaigns_keyboard(user_id, version, campaigns),
        )
        return

    if screen_key == SCREEN_CAMPAIGN_CREATE:
        text = _prepend_notice(user_id, UserService.t(user_id, 'campaign_create_intro'), notice_key, notice_text)
        render_managed_screen(
            bot,
            target=target,
            user_id=user_id,
            chat_id=chat_id,
            screen_key=SCREEN_CAMPAIGN_CREATE,
            text=text,
            reply_markup_builder=lambda version: campaign_task_type_keyboard(user_id, version),
        )
        return

    input_step = _screen_suffix(screen_key, SCREEN_CAMPAIGN_INPUT_PREFIX)
    if input_step is not None:
        text = _prepend_notice(user_id, _build_campaign_input_text(user_id, input_step), notice_key, notice_text)
        render_managed_screen(
            bot,
            target=target,
            user_id=user_id,
            chat_id=chat_id,
            screen_key=screen_key,
            text=text,
            reply_markup_builder=lambda version: campaign_input_keyboard(user_id, version),
        )
        return

    if screen_key == SCREEN_CAMPAIGN_PREVIEW:
        text = _prepend_notice(user_id, _build_campaign_preview_text(user_id), notice_key, notice_text)
        render_managed_screen(
            bot,
            target=target,
            user_id=user_id,
            chat_id=chat_id,
            screen_key=SCREEN_CAMPAIGN_PREVIEW,
            text=text,
            reply_markup_builder=lambda version: campaign_preview_keyboard(user_id, version),
        )
        return

    owner_campaign_id = _screen_payload(screen_key, SCREEN_CAMPAIGN_CARD_PREFIX)
    if owner_campaign_id is not None:
        campaign = CampaignService.get_owned_campaign(user_id, owner_campaign_id)
        if not campaign:
            render_screen(bot, target, SCREEN_CAMPAIGNS, notice_key='campaign_not_found')
            return
        text = _prepend_notice(user_id, _build_campaign_card_text(user_id, owner_campaign_id), notice_key, notice_text)
        render_managed_screen(
            bot,
            target=target,
            user_id=user_id,
            chat_id=chat_id,
            screen_key=screen_key,
            text=text,
            reply_markup_builder=lambda version: campaign_card_keyboard(user_id, version, campaign),
        )
        return

    if screen_key == SCREEN_STATS:
        text = _prepend_notice(user_id, _build_stats_text(user_id), notice_key, notice_text)
        render_managed_screen(
            bot,
            target=target,
            user_id=user_id,
            chat_id=chat_id,
            screen_key=SCREEN_STATS,
            text=text,
            reply_markup_builder=lambda version: stats_keyboard(user_id, version),
        )
        return

    if screen_key == SCREEN_ADMIN:
        text = _prepend_notice(user_id, _build_admin_home_text(user_id), notice_key, notice_text)
        render_managed_screen(
            bot,
            target=target,
            user_id=user_id,
            chat_id=chat_id,
            screen_key=SCREEN_ADMIN,
            text=text,
            reply_markup_builder=lambda version: admin_home_keyboard(user_id, version),
        )
        return

    if screen_key == SCREEN_ADMIN_QUEUE:
        submissions = AdminService.list_review_queue()
        text = _prepend_notice(user_id, _build_admin_queue_text(user_id, submissions), notice_key, notice_text)
        render_managed_screen(
            bot,
            target=target,
            user_id=user_id,
            chat_id=chat_id,
            screen_key=SCREEN_ADMIN_QUEUE,
            text=text,
            reply_markup_builder=lambda version: admin_queue_keyboard(user_id, version, submissions),
        )
        return

    admin_submission_id = _screen_payload(screen_key, SCREEN_ADMIN_SUBMISSION_PREFIX)
    if admin_submission_id is not None:
        if not UserService.is_admin(user_id):
            render_screen(bot, target, SCREEN_MAIN_MENU, notice_key='admin_access_denied')
            return
        text, card = _build_admin_submission_text(user_id, admin_submission_id)
        if card is None:
            render_screen(bot, target, SCREEN_ADMIN_QUEUE, notice_key='admin_submission_not_found')
            return
        text = _prepend_notice(user_id, text, notice_key, notice_text)
        render_managed_screen(
            bot,
            target=target,
            user_id=user_id,
            chat_id=chat_id,
            screen_key=screen_key,
            text=text,
            reply_markup_builder=lambda version: admin_submission_keyboard(user_id, version, card),
        )
        return

    if screen_key == SCREEN_ADMIN_LOGS:
        text = _prepend_notice(user_id, _build_admin_logs_text(user_id), notice_key, notice_text)
        render_managed_screen(
            bot,
            target=target,
            user_id=user_id,
            chat_id=chat_id,
            screen_key=SCREEN_ADMIN_LOGS,
            text=text,
            reply_markup_builder=lambda version: admin_logs_keyboard(user_id, version),
        )
        return

    admin_reject_id = _screen_payload(screen_key, SCREEN_ADMIN_REJECT_PREFIX)
    if admin_reject_id is not None:
        text = _prepend_notice(user_id, _build_admin_input_text(user_id, 'reject', admin_reject_id), notice_key, notice_text)
        render_managed_screen(
            bot,
            target=target,
            user_id=user_id,
            chat_id=chat_id,
            screen_key=screen_key,
            text=text,
            reply_markup_builder=lambda version: admin_input_keyboard(user_id, version, back_target=f'admin_submission:{admin_reject_id}'),
        )
        return

    admin_risk_user_id = _screen_payload(screen_key, SCREEN_ADMIN_RISK_PREFIX)
    if admin_risk_user_id is not None:
        text = _prepend_notice(user_id, _build_admin_input_text(user_id, 'risk', admin_risk_user_id), notice_key, notice_text)
        render_managed_screen(
            bot,
            target=target,
            user_id=user_id,
            chat_id=chat_id,
            screen_key=screen_key,
            text=text,
            reply_markup_builder=lambda version: admin_input_keyboard(user_id, version, back_target='admin_queue'),
        )
        return

    admin_balance_user_id = _screen_payload(screen_key, SCREEN_ADMIN_BALANCE_PREFIX)
    if admin_balance_user_id is not None:
        text = _prepend_notice(user_id, _build_admin_input_text(user_id, 'balance', admin_balance_user_id), notice_key, notice_text)
        render_managed_screen(
            bot,
            target=target,
            user_id=user_id,
            chat_id=chat_id,
            screen_key=screen_key,
            text=text,
            reply_markup_builder=lambda version: admin_input_keyboard(user_id, version, back_target='admin_queue'),
        )
        return

    logger.warning('Unknown screen requested: %s', screen_key)
    render_screen(bot, target, SCREEN_MAIN_MENU)



def render_entry(bot: telebot.TeleBot, target: Target, *, force_language: bool = False) -> None:
    user_id = _user_id(target)
    chat_id = _chat_id(target)
    UserService.ensure_user(target.from_user)
    if force_language:
        render_screen(bot, target, SCREEN_LANGUAGE)
        return
    next_screen = resolve_next_screen(bot, user_id, chat_id)
    render_screen(bot, target, next_screen)
