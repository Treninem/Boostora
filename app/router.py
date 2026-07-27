import json
import logging

import telebot
from telebot.types import CallbackQuery, Message

from app.config import settings
from app.keyboards.inline import (
    admin_home_keyboard,
    admin_groups_keyboard,
    admin_patterns_keyboard,
    admin_input_keyboard,
    admin_logs_keyboard,
    owner_analytics_keyboard,
    owner_release_keyboard,
    owner_provider_keyboard,
    engagement_growth_keyboard,
    engagement_mode_keyboard,
    engagement_obligations_keyboard,
    admin_engagement_obligations_keyboard,
    community_rules_keyboard,
    legal_docs_keyboard,
    marketplace_keyboard,
    smart_hub_keyboard,
    admin_required_chats_keyboard,
    admin_queue_keyboard,
    admin_bot_chats_keyboard,
    admin_users_keyboard,
    admin_submission_keyboard,
    blocked_keyboard,
    broadcast_input_keyboard,
    broadcast_preview_keyboard,
    broadcast_schedule_keyboard,
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
    exchange_keyboard,
    role_keyboard,
    section_keyboard,
    stats_keyboard,
    subscription_keyboard,
    task_detail_keyboard,
    tasks_keyboard,
    topup_custom_keyboard,
    topup_packages_keyboard,
    vip_keyboard,
    wallet_keyboard,
)
from app.services.admin import AdminService
from app.services.admin_console import AdminConsoleService, normalize_queue_filter, priority_label_key, queue_filter_label_key
from app.services.ad_broadcasts import AdBroadcastService, MODE_CONFIRM as BROADCAST_MODE_CONFIRM, MODE_LINK as BROADCAST_MODE_LINK, MODE_TEXT as BROADCAST_MODE_TEXT
from app.services.admin_logs import AdminLogService
from app.services.bot_chats import BotChatService
from app.services.campaigns import CampaignService
from app.services.client_dashboard import action_tip, boost_options_text, campaign_progress, dashboard_summary, health_label
from app.services.economy import completion_speed_explanation, recommend_unit_prices
from app.services.client_campaigns import MODE_CONFIRM, MODE_PRICE, ClientCampaignService
from app.services.community_rules import CommunityRulesService
from app.services.engagement_modes import EngagementModeService
from app.services.engagement_growth import EngagementGrowthService
from app.services.performer import PerformerService, normalize_target_url
from app.services.proof_guides import ProofGuideService
from app.services.owner_analytics import OwnerAnalyticsService
from app.services.boostore_provider import BoostoreProviderService
from app.services.standard_admin import StandardAdminService
from app.services.legal_docs import LegalDocsService
from app.services.smart_hub import SmartHubService
from app.services.release_readiness import ReleaseReadinessService
from app.services.redemptions import RedemptionService
from app.services.quality import speed_label, trust_tip, verification_label
from app.services.referrals import ReferralService
from app.services.rewards import RewardService
from app.services.subscriptions import SubscriptionService
from app.services.transactions import TransactionService
from app.services.ux_flow import broadcast_step_status, campaign_step_status
from app.services.trust import TrustService
from app.services.ui_state import UIStateService
from app.services.users import UserService
from app.services.vip import VIP_PLANS, VipService
from app.services.wallets import WalletService
from app.utils.ui import render_managed_screen


logger = logging.getLogger(__name__)

TRANSACTION_TYPE_KEYS = {
    'signup_bonus': 'tx_signup_bonus',
    'task_reward_hold': 'tx_task_reward_hold',
    'hold_release': 'tx_hold_release',
    'campaign_funding': 'tx_campaign_funding',
    'campaign_funding_bonus': 'tx_campaign_funding_bonus',
    'campaign_boost': 'tx_campaign_boost',
    'campaign_boost_bonus': 'tx_campaign_boost_bonus',
    'stars_topup': 'tx_stars_topup',
    'vip_purchase': 'tx_vip_purchase',
    'reward_purchase': 'tx_reward_purchase',
    'referral_reward': 'tx_referral_reward',
    'gift_redeem': 'tx_gift_redeem',
    'gift_refund': 'tx_gift_refund',
    'premium_redeem': 'tx_premium_redeem',
    'premium_refund': 'tx_premium_refund',
}

TRANSACTION_STATUS_KEYS = {
    'completed': 'status_completed',
    'hold': 'status_hold',
    'pending': 'status_pending',
    'active': 'status_active',
    'rejected': 'status_rejected',
}

SCREEN_LANGUAGE = 'language'
SCREEN_ROLE = 'role'
SCREEN_REQUIRED_SUBSCRIPTION = 'required_subscription'
SCREEN_MAIN_MENU = 'main_menu'
SCREEN_SMART_HUB = 'smart_hub'
SCREEN_MARKETPLACE = 'marketplace'
SCREEN_ENGAGEMENT_GROWTH = 'engagement_growth'
SCREEN_ENGAGEMENT_MODE = 'engagement_mode'
SCREEN_ENGAGEMENT_OBLIGATIONS = 'engagement_obligations'
SCREEN_ADMIN_ENGAGEMENT_OBLIGATIONS = 'admin_engagement_obligations'
SCREEN_COMMUNITY_RULES = 'community_rules'
SCREEN_LEGAL_DOCS = 'legal_docs'
SCREEN_PROFILE = 'profile'
SCREEN_TASKS = 'tasks'
SCREEN_TASK_DETAIL_PREFIX = 'task:'
SCREEN_SUBMISSION_PREFIX = 'submission:'
SCREEN_PROOF_WAIT_PREFIX = 'proof_wait:'
SCREEN_WALLET = 'wallet'
SCREEN_TOPUP_CUSTOM = 'topup_custom'
SCREEN_TOPUP_PACKAGES = 'topup_packages'
SCREEN_HISTORY = 'history'
SCREEN_CAMPAIGNS = 'campaigns'
SCREEN_STATS = 'stats'
SCREEN_CAMPAIGN_CREATE = 'campaign_create'
SCREEN_CAMPAIGN_PREVIEW = 'campaign_preview'
SCREEN_CAMPAIGN_INPUT_PREFIX = 'campaign_input:'
SCREEN_CAMPAIGN_CARD_PREFIX = 'campaign:'
SCREEN_BROADCAST_TEXT = 'broadcast_text'
SCREEN_BROADCAST_LINK = 'broadcast_link'
SCREEN_BROADCAST_SCHEDULE = 'broadcast_schedule'
SCREEN_BROADCAST_PREVIEW = 'broadcast_preview'
SCREEN_VIP = 'vip'
SCREEN_REWARDS = 'rewards'
SCREEN_EXCHANGE = 'exchange'
SCREEN_REFERRALS = 'referrals'
SCREEN_BLOCKED = 'blocked'
SCREEN_ADMIN = 'admin'
SCREEN_ADMIN_GROUPS = 'admin_groups'
SCREEN_ADMIN_PATTERNS = 'admin_patterns'
SCREEN_OWNER_ANALYTICS = 'owner_analytics'
SCREEN_OWNER_RELEASE = 'owner_release'
SCREEN_OWNER_PROVIDER = 'owner_provider'
SCREEN_ADMIN_QUEUE = 'admin_queue'
SCREEN_ADMIN_QUEUE_PREFIX = 'admin_queue:'
SCREEN_ADMIN_BOT_RIGHTS_PREFIX = 'admin_bot_rights:'
SCREEN_ADMIN_LOGS = 'admin_logs'
SCREEN_ADMIN_SUBMISSION_PREFIX = 'admin_submission:'
SCREEN_ADMIN_REJECT_PREFIX = 'admin_reject:'
SCREEN_ADMIN_RISK_PREFIX = 'admin_risk:'
SCREEN_ADMIN_BALANCE_PREFIX = 'admin_balance:'
SCREEN_ADMIN_REQUIRED_CHATS = 'admin_required_chats'
SCREEN_ADMIN_REQUIRED_CHAT_ADD = 'admin_required_chat_add'
SCREEN_ADMIN_BOT_CHATS_PREFIX = 'admin_bot_chats:'
SCREEN_ADMIN_USERS_PREFIX = 'admin_users:'

SECTION_TO_SCREEN = {
    'smart_hub': SCREEN_SMART_HUB,
    'marketplace': SCREEN_MARKETPLACE,
    'engagement_growth': SCREEN_ENGAGEMENT_GROWTH,
    'engagement_mode': SCREEN_ENGAGEMENT_MODE,
    'engagement_obligations': SCREEN_ENGAGEMENT_OBLIGATIONS,
    'admin_engagement_obligations': SCREEN_ADMIN_ENGAGEMENT_OBLIGATIONS,
    'community_rules': SCREEN_COMMUNITY_RULES,
    'legal_docs': SCREEN_LEGAL_DOCS,
    'profile': SCREEN_PROFILE,
    'tasks': SCREEN_TASKS,
    'wallet': SCREEN_WALLET,
    'history': SCREEN_HISTORY,
    'campaigns': SCREEN_CAMPAIGNS,
    'stats': SCREEN_STATS,
    'vip': SCREEN_VIP,
    'rewards': SCREEN_REWARDS,
    'exchange': SCREEN_EXCHANGE,
    'topup_packages': SCREEN_TOPUP_PACKAGES,
    'referrals': SCREEN_REFERRALS,
    'admin': SCREEN_ADMIN,
    'admin_queue': SCREEN_ADMIN_QUEUE,
    'admin_groups': SCREEN_ADMIN_GROUPS,
    'admin_patterns': SCREEN_ADMIN_PATTERNS,
    'owner_analytics': SCREEN_OWNER_ANALYTICS,
    'owner_release': SCREEN_OWNER_RELEASE,
    'owner_provider': SCREEN_OWNER_PROVIDER,
    'admin_logs': SCREEN_ADMIN_LOGS,
    'admin_required_chats': SCREEN_ADMIN_REQUIRED_CHATS,
}

TASK_TYPE_LABEL_KEYS = {
    'channel_subscribe': 'campaign_task_type_channel_subscribe',
    'chat_join': 'campaign_task_type_chat_join',
    'post_view': 'campaign_task_type_post_view',
    'bot_start': 'campaign_task_type_bot_start',
    'mini_app_open': 'campaign_task_type_mini_app_open',
    'post_like': 'campaign_task_type_post_like',
    'post_reaction': 'campaign_task_type_post_reaction',
    'story_view': 'campaign_task_type_story_view',
    'link_click': 'campaign_task_type_link_click',
    'post_share': 'campaign_task_type_post_share',
    'post_comment': 'campaign_task_type_post_comment',
    'poll_vote': 'campaign_task_type_poll_vote',
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


def _build_broadcast_text_screen(user_id: int) -> str:
    chats = AdBroadcastService.promotable_chat_count()
    language = UserService.get_language(user_id)
    return UserService.t(
        user_id,
        'broadcast_text_screen',
        chats=chats,
        step_status=broadcast_step_status('text', language=language),
    )


def _build_broadcast_link_screen(user_id: int) -> str:
    draft = AdBroadcastService.get_draft(user_id) or {}
    language = UserService.get_language(user_id)
    return UserService.t(
        user_id,
        'broadcast_link_screen',
        ad_text=str(draft.get('ad_text') or '—'),
        step_status=broadcast_step_status('link', language=language),
    )


def _build_broadcast_schedule_text(user_id: int) -> str:
    draft = AdBroadcastService.get_draft(user_id) or {}
    chats = AdBroadcastService.promotable_chat_count()
    language = UserService.get_language(user_id)
    repeats = int(draft.get('repeat_count') or 0)
    if repeats in AdBroadcastService.list_repeat_options():
        return UserService.t(
            user_id,
            'broadcast_schedule_frequency_screen',
            chats=chats,
            ad_text=str(draft.get('ad_text') or '—'),
            link=str(draft.get('target_url') or '—'),
            repeats=AdBroadcastService.list_repeat_options().get(repeats, repeats),
            step_status=broadcast_step_status('schedule', language=language),
        )
    return UserService.t(
        user_id,
        'broadcast_schedule_count_screen',
        chats=chats,
        ad_text=str(draft.get('ad_text') or '—'),
        link=str(draft.get('target_url') or '—'),
        step_status=broadcast_step_status('schedule', language=language),
    )


def _build_broadcast_preview_text(user_id: int) -> str:
    draft = AdBroadcastService.get_draft(user_id) or {}
    schedule_code = str(draft.get('schedule_code') or '')
    chats = AdBroadcastService.promotable_chat_count()
    repeats, interval_hours = AdBroadcastService.parse_schedule_code(schedule_code)
    price = AdBroadcastService.price_for(schedule_code, chats) if repeats is not None and interval_hours is not None else 0
    return UserService.t(
        user_id,
        'broadcast_preview_screen',
        chats=chats,
        ad_text=str(draft.get('ad_text') or '—'),
        link=str(draft.get('target_url') or '—'),
        schedule=AdBroadcastService.schedule_label(schedule_code),
        stars=price,
        payment_mode=UserService.t(user_id, 'broadcast_payment_free' if draft.get('is_admin') else 'broadcast_payment_stars'),
    )


def admin_queue_screen_key(filter_code: str = 'all') -> str:
    value = normalize_queue_filter(filter_code)
    return SCREEN_ADMIN_QUEUE if value == 'all' else f'{SCREEN_ADMIN_QUEUE_PREFIX}{value}'


def admin_bot_rights_screen_key(page: int = 1) -> str:
    return f'{SCREEN_ADMIN_BOT_RIGHTS_PREFIX}{page}'


def admin_submission_screen_key(submission_id: int) -> str:
    return f'{SCREEN_ADMIN_SUBMISSION_PREFIX}{submission_id}'


def admin_reject_screen_key(submission_id: int) -> str:
    return f'{SCREEN_ADMIN_REJECT_PREFIX}{submission_id}'


def admin_risk_screen_key(user_id: int) -> str:
    return f'{SCREEN_ADMIN_RISK_PREFIX}{user_id}'


def admin_balance_screen_key(user_id: int) -> str:
    return f'{SCREEN_ADMIN_BALANCE_PREFIX}{user_id}'


def admin_bot_chats_screen_key(page: int = 1) -> str:
    return f'{SCREEN_ADMIN_BOT_CHATS_PREFIX}{max(1, int(page))}'


def admin_users_screen_key(page: int = 1) -> str:
    return f'{SCREEN_ADMIN_USERS_PREFIX}{max(1, int(page))}'



def _chat_id(target: Target) -> int:
    if isinstance(target, CallbackQuery):
        return int(target.message.chat.id)
    return int(target.chat.id)



def _chat_username(target: Target) -> str | None:
    if isinstance(target, CallbackQuery):
        return getattr(target.message.chat, 'username', None)
    return getattr(target.chat, 'username', None)



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


def _safe_page(raw_value: str | None) -> int:
    try:
        page = int(str(raw_value or '1'))
    except Exception:
        page = 1
    return max(page, 1)



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





def _transaction_type_label(user_id: int, entry_type: str) -> str:
    key = TRANSACTION_TYPE_KEYS.get(entry_type)
    return UserService.t(user_id, key) if key else entry_type.replace('_', ' ')


def _transaction_status_label(user_id: int, status: str) -> str:
    key = TRANSACTION_STATUS_KEYS.get(status)
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





def _build_community_rules_text(user_id: int) -> str:
    rows = []
    for section in CommunityRulesService.sections():
        rows.append(UserService.t(user_id, 'community_rules_section_row',
            title=UserService.t(user_id, section.title_key),
            body=UserService.t(user_id, section.body_key)))
    accepted = CommunityRulesService.is_accepted(user_id)
    return UserService.t(user_id, 'community_rules_screen',
        brand=settings.brand_name,
        version=CommunityRulesService.CURRENT_VERSION,
        state=UserService.t(user_id, 'community_rules_state_accepted' if accepted else 'community_rules_state_required'),
        sections='\n\n'.join(rows))


def _build_legal_docs_text(user_id: int) -> str:
    rows = []
    for section in LegalDocsService.sections():
        rows.append(UserService.t(user_id, 'legal_docs_section_row',
            title=UserService.t(user_id, section.title_key),
            body=UserService.t(user_id, section.body_key)))
    accepted = LegalDocsService.is_accepted(user_id)
    return UserService.t(user_id, 'legal_docs_screen',
        brand=settings.brand_name,
        version=LegalDocsService.CURRENT_VERSION,
        state=UserService.t(user_id, 'legal_docs_state_accepted' if accepted else 'legal_docs_state_required'),
        sections='\n\n'.join(rows))

def _build_smart_hub_text(user_id: int) -> str:
    data = SmartHubService.dashboard(user_id)
    wallet = data['wallet']
    tips = '\n'.join('• ' + UserService.t(user_id, key) for key in data['tips'])
    provider = data['provider']
    return UserService.t(
        user_id, 'smart_hub_screen', brand=settings.brand_name,
        role=UserService.role_label(user_id, data['role']),
        available=wallet['available_balance'], internal=wallet['internal_balance'],
        bonus=wallet['bonus_balance'], hold=wallet['hold_balance'],
        active_tasks=data['active_tasks'], task_limit=data['task_limit'],
        available_tasks=data['available_tasks'], manual_review=data['manual_review'],
        client_campaigns=data['client_campaigns'], client_active=data['client_active'],
        client_drafts=data['client_drafts'], provider_enabled=provider['enabled_services'],
        provider_state=UserService.t(user_id, f"boostore_state_{provider['state']}"),
        internal_name=UserService.internal_currency_label(user_id), tips=tips,
    )


def _build_marketplace_text(user_id: int) -> tuple[str, list]:
    summary = BoostoreProviderService.marketplace_summary(limit=10)
    services = summary['services']
    rows = []
    for row in services[:10]:
        rows.append(UserService.t(user_id, 'marketplace_service_row',
            name=str(row['name'])[:64], category=str(row['category'] or '—')[:32],
            service_type=str(row['service_type'] or '—')[:32],
            min_qty=int(row['min_quantity'] or 0), max_qty=int(row['max_quantity'] or 0),
            markup=int(row['markup_percent'] or 0)))
    items = '\n'.join(rows) if rows else UserService.t(user_id, 'marketplace_empty')
    provider_state = BoostoreProviderService.readiness_summary()['state']
    return UserService.t(user_id, 'marketplace_screen', total=summary['total_services'],
        enabled=summary['enabled_services'], provider_state=UserService.t(user_id, f'boostore_state_{provider_state}'), items=items), services


def _build_engagement_mode_text(user_id: int) -> str:
    summary = EngagementModeService.mode_summary(user_id)
    mode_key = f"engagement_mode_state_{summary['mode']}"
    return UserService.t(
        user_id,
        'engagement_mode_screen',
        mode=UserService.t(user_id, mode_key),
        required=int(summary['required_actions']),
        pro_price=int(summary['pro_price_stars']),
        open_obligations=int(summary['open_obligations']),
        open_required=int(summary['open_required_total']),
        outgoing_30d=int(summary['outgoing_30d']),
        pro_until=summary['pro_expires_at'] or UserService.t(user_id, 'engagement_mode_no_pro_until'),
    )



def _format_engagement_due(raw: str) -> str:
    return str(raw or '').replace('T', ' ')[:16] if raw else '—'


def _build_engagement_obligations_text(user_id: int) -> str:
    dashboard = EngagementModeService.obligation_dashboard(user_id)
    if dashboard['items']:
        rows = []
        for item in dashboard['items'][:10]:
            rows.append(UserService.t(
                user_id,
                'engagement_obligation_row',
                task_type=UserService.t(user_id, item['task_label_key']),
                done=int(item['done']),
                required=int(item['required']),
                remaining=int(item['remaining']),
                percent=int(item['percent']),
                state=UserService.t(user_id, f"engagement_obligation_state_{item['state']}"),
                due=_format_engagement_due(str(item['due_at'])),
                campaign=int(item['campaign_id'] or 0),
            ))
        items = '\n\n'.join(rows)
    else:
        items = UserService.t(user_id, 'engagement_obligations_empty')
    restriction_state = EngagementModeService.soft_restriction(user_id)
    restriction = UserService.t(user_id, 'engagement_obligations_restriction_active', remaining=int(restriction_state['remaining'])) if restriction_state['restricted'] else UserService.t(user_id, 'engagement_obligations_restriction_clear')
    return UserService.t(
        user_id,
        'engagement_obligations_screen',
        status=UserService.t(user_id, f"engagement_obligation_dashboard_state_{dashboard['status']}"),
        restriction=restriction,
        open_count=int(dashboard['open_count']),
        overdue_count=int(dashboard['overdue_count']),
        due_soon_count=int(dashboard['due_soon_count']),
        total_done=int(dashboard['total_done']),
        total_required=int(dashboard['total_required']),
        total_remaining=int(dashboard['total_remaining']),
        outgoing_30d=int(dashboard['outgoing_30d']),
        completed_total=int(dashboard['completed_total']),
        items=items,
    )


def _build_admin_engagement_obligations_text(user_id: int) -> str:
    overview = EngagementModeService.admin_obligation_overview(limit=15)
    if overview['items']:
        rows = []
        for item in overview['items'][:15]:
            name = item.get('username') or item.get('first_name') or str(item['user_id'])
            rows.append(UserService.t(
                user_id,
                'admin_engagement_obligation_row',
                user_id=int(item['user_id']),
                name=str(name)[:32],
                task_type=UserService.t(user_id, item['task_label_key']),
                done=int(item['done']),
                required=int(item['required']),
                remaining=int(item['remaining']),
                state=UserService.t(user_id, f"engagement_obligation_state_{item['state']}"),
                due=_format_engagement_due(str(item['due_at'])),
                campaign=int(item['campaign_id'] or 0),
            ))
        items = '\n'.join(rows)
    else:
        items = UserService.t(user_id, 'admin_engagement_obligations_empty')
    return UserService.t(
        user_id,
        'admin_engagement_obligations_screen',
        table_state=UserService.t(user_id, 'status_ready' if overview['table_ready'] else 'status_blocker'),
        open_total=int(overview['open_total']),
        overdue_total=int(overview['overdue_total']),
        due_soon_total=int(overview['due_soon_total']),
        required=int(overview['required_actions']),
        items=items,
    )


def _build_engagement_growth_text(user_id: int) -> str:
    summary = EngagementGrowthService.summary()
    products = []
    for product in summary['products']:
        products.append('• ' + UserService.t(user_id, product.description_key))
    product_rows = '\n'.join(products)
    presets = []
    for preset in summary.get('presets', []):
        presets.append('• ' + UserService.t(user_id, preset.description_key))
    preset_rows = '\n'.join(presets[:9])
    mode = EngagementModeService.mode_summary(user_id)
    restriction_state = EngagementModeService.soft_restriction(user_id)
    restriction_block = UserService.t(user_id, 'engagement_growth_overdue_block', remaining=int(restriction_state['remaining'])) if restriction_state['restricted'] else UserService.t(user_id, 'engagement_growth_overdue_clear')
    mode_block = UserService.t(
        user_id,
        'engagement_growth_mode_block',
        mode=UserService.t(user_id, f"engagement_mode_state_{mode['mode']}"),
        required=int(mode['required_actions']),
        pro_price=int(mode['pro_price_stars']),
        open_obligations=int(mode['open_obligations']),
        open_required=int(mode['open_required_total']),
        outgoing_30d=int(mode['outgoing_30d']),
        open_remaining=int(mode.get('open_remaining_total', mode['open_required_total'])),
    )
    return UserService.t(
        user_id,
        'engagement_growth_screen',
        restriction_block=restriction_block,
        product_count=int(summary['product_count']),
        preset_count=int(summary.get('preset_count') or 0),
        campaign_types=int(summary['campaign_types']),
        product_rows=product_rows,
        preset_rows=preset_rows,
        mode_block=mode_block,
    )


def _build_owner_provider_text(user_id: int) -> tuple[str, list]:
    readiness = BoostoreProviderService.readiness_summary()
    order_summary = BoostoreProviderService.order_summary()
    services = BoostoreProviderService.list_services(enabled_only=False, limit=12)
    rows = []
    for row in services[:12]:
        rows.append(UserService.t(user_id, 'owner_provider_service_row',
            enabled='✅' if int(row['is_enabled'] or 0) else '▫️', sid=str(row['external_service_id']),
            name=str(row['name'])[:56], category=str(row['category'] or '—')[:24],
            rate=str(row['rate_text'] or '—'), min_qty=int(row['min_quantity'] or 0),
            max_qty=int(row['max_quantity'] or 0)))
    items = '\n'.join(rows) if rows else UserService.t(user_id, 'owner_provider_empty')
    return UserService.t(user_id, 'owner_provider_screen',
        state=UserService.t(user_id, f"boostore_state_{readiness['state']}"), score=int(readiness['score']),
        enabled='ON' if readiness['enabled'] else 'OFF', configured='YES' if readiness['configured'] else 'NO',
        has_key='YES' if readiness['has_key'] else 'NO', api_url=readiness['api_url'],
        total=readiness['total_services'], whitelist=readiness['enabled_services'],
        markup=readiness['markup_percent'], auto_sync='ON' if readiness['auto_sync'] else 'OFF',
        auto_order='ON' if order_summary.get('auto_order_enabled') else 'OFF', provider_orders=int(order_summary.get('total') or 0),
        provider_failed=int(order_summary.get('failed') or 0), items=items), services

def _build_profile_text(user_id: int) -> str:
    wallet = WalletService.get_summary(user_id)
    active_tasks = PerformerService.get_active_submission_count(user_id)
    task_limit = PerformerService.get_active_task_limit(user_id)
    role = UserService.get_role(user_id) or 'performer'
    language = UserService.get_language(user_id)
    trust = TrustService.summary(user_id, language=language)
    return UserService.t(
        user_id,
        'profile_screen',
        profile_id=user_id,
        role=UserService.role_label(user_id, role),
        active_tasks=active_tasks,
        task_limit=task_limit,
        available=wallet['available_balance'],
        sparks=wallet['internal_balance'],
        internal=wallet['internal_balance'],
        bonus=wallet['bonus_balance'],
        campaign_balance=wallet['campaign_balance'],
        withdrawn=wallet['total_withdrawn'],
        hold=wallet['hold_balance'],
        earned=wallet['lifetime_earned'],
        redeem_access=UserService.t(user_id, 'redeem_access_yes' if wallet['has_paid_topup'] else 'redeem_access_no'),
        internal_name=UserService.internal_currency_label(user_id),
        trust_level=trust['level_label'],
        trust_score=trust['score'],
        approval_rate=trust['approval_rate'],
        approved_count=trust['approved_count'],
        rejected_count=trust['rejected_count'],
        trust_bonus=trust['task_bonus'],
        trust_hint=trust['trust_hint'],
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

    language = UserService.get_language(user_id)
    trust = TrustService.summary(user_id, language=language)
    text = UserService.t(
        user_id,
        'task_detail',
        title=str(campaign['title'] or f'#{campaign_id}'),
        task_type=_task_type_label(user_id, str(campaign['task_type'])),
        reward=int(campaign['reward_amount']),
        remaining=remaining,
        status=status_label,
        internal_name=UserService.internal_currency_label(user_id),
        verification=verification_label(str(campaign['task_type']), language),
        trust_tip=trust_tip(str(campaign['task_type']), language),
        trust_level=trust['level_label'],
        trust_score=trust['score'],
        trust_bonus=trust['task_bonus'],
        task_guide=ProofGuideService.task_detail_block(str(campaign['task_type']), language),
    )
    return text, {
        'target_url': normalize_target_url(str(campaign['target_url'])),
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
        internal=wallet['internal_balance'],
        bonus=wallet['bonus_balance'],
        campaign_balance=wallet['campaign_balance'],
        withdrawn=wallet['total_withdrawn'],
        hold=wallet['hold_balance'],
        redeem_access=UserService.t(user_id, 'redeem_access_yes' if wallet['has_paid_topup'] else 'redeem_access_no'),
        internal_name=UserService.internal_currency_label(user_id),
        earned=wallet['lifetime_earned'],
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
        if currency_code == 'BST':
            currency_label = UserService.internal_currency_label(user_id)
        elif currency_code == 'XTR':
            currency_label = '⭐'
        else:
            currency_label = currency_code
        items.append(
            UserService.t(
                user_id,
                'history_row',
                date=created_at,
                entry_type=_transaction_type_label(user_id, str(row['entry_type'])),
                amount=int(row['amount']),
                currency=currency_label,
                status=_transaction_status_label(user_id, str(row['status'])),
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




def _campaign_pricing_snapshot_from_row(row) -> dict[str, object]:
    raw = ''
    try:
        raw = str(row['pricing_json'] or '')
    except Exception:
        raw = ''
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _build_campaign_input_text(user_id: int, step: str) -> str:
    draft = ClientCampaignService.get_draft(user_id) or {}
    language = UserService.get_language(user_id)
    task_type_code = str(draft.get('task_type') or '')
    task_type = _task_type_label(user_id, str(draft.get('task_type') or '—'))
    target_url = str(draft.get('target_url') or '—')
    quantity = str(draft.get('total_quantity') or '—')
    reward_amount = str(draft.get('reward_amount') or draft.get('performer_floor_reward') or 'auto')
    unit_price = str(draft.get('unit_price') or draft.get('client_floor_price') or 'auto')
    floor_price = str(draft.get('client_floor_price') or '—')
    recommended_price = str(draft.get('recommended_unit_price') or '—')
    fast_price = str(draft.get('fast_unit_price') or '—')
    priority_price = str(draft.get('priority_unit_price') or '—')
    speed_hint = UserService.t(user_id, 'campaign_price_hint_wait_quantity')
    if task_type_code and str(draft.get('total_quantity') or '').isdigit():
        try:
            advisory = recommend_unit_prices(task_type_code, int(draft.get('total_quantity') or 0))
            recommended_price = str(advisory['recommended_unit_price'])
            fast_price = str(advisory['fast_unit_price'])
            priority_price = str(advisory['priority_unit_price'])
            speed_hint = UserService.t(
                user_id,
                'campaign_price_recommendation_hint',
                recommended=recommended_price,
                fast=fast_price,
                priority=priority_price,
                internal_name=UserService.internal_currency_label(user_id),
            )
        except Exception:
            pass
    target_prompt = UserService.t(user_id, 'campaign_target_prompt')
    if task_type_code in {'channel_subscribe', 'chat_join', 'post_view', 'post_like', 'post_reaction', 'story_view', 'post_share', 'post_comment', 'poll_vote'}:
        target_prompt += '\n\n' + UserService.t(user_id, 'campaign_target_require_bot_in_chat')
    if task_type_code in {'channel_subscribe', 'chat_join', 'post_reaction', 'poll_vote'}:
        target_prompt += '\n' + UserService.t(user_id, 'campaign_target_require_admin_rights')
    if task_type_code in {'post_view', 'post_like', 'post_reaction', 'post_share', 'post_comment', 'poll_vote'}:
        target_prompt += '\n' + UserService.t(user_id, 'campaign_target_require_post_link')
    if task_type_code == 'bot_start':
        target_prompt += '\n\n' + UserService.t(user_id, 'campaign_target_require_bot_start')
    if task_type_code == 'mini_app_open':
        target_prompt += '\n\n' + UserService.t(user_id, 'campaign_target_require_miniapp_senddata')
    if task_type_code:
        target_prompt += '\n\n' + ProofGuideService.client_hint(task_type_code, language)
    prompt_map = {
        'target': target_prompt,
        'quantity': UserService.t(user_id, 'campaign_quantity_prompt'),
        'price': UserService.t(user_id, 'campaign_price_prompt', floor=floor_price, recommended=recommended_price, fast=fast_price, priority=priority_price, currency=UserService.internal_currency_label(user_id)),
    }
    return UserService.t(
        user_id,
        'campaign_input_screen',
        step=prompt_map.get(step, target_prompt),
        step_status=campaign_step_status(step, language=language),
        task_type=task_type,
        target_url=target_url,
        reward=reward_amount,
        quantity=quantity,
        unit_price=unit_price,
        floor=floor_price,
        recommended=recommended_price,
        fast=fast_price,
        priority=priority_price,
        speed_hint=speed_hint,
        internal_name=UserService.internal_currency_label(user_id),
    )



def _build_campaign_preview_text(user_id: int) -> str:
    draft = ClientCampaignService.get_draft(user_id)
    if not draft:
        return UserService.t(user_id, 'campaign_draft_missing')
    language = UserService.get_language(user_id)
    speed = int(draft.get('speed_index') or 100)
    unit_price = int(draft['unit_price'])
    recommended_unit_price = int(draft.get('recommended_unit_price') or unit_price)
    fast_unit_price = int(draft.get('fast_unit_price') or unit_price)
    priority_unit_price = int(draft.get('priority_unit_price') or unit_price)
    price_position = int(draft.get('price_position_percent') or 0)
    task_type_code = str(draft['task_type'])
    speed_explanation = completion_speed_explanation(speed, unit_price, recommended_unit_price, language)
    return UserService.t(
        user_id,
        'campaign_preview_screen',
        task_type=_task_type_label(user_id, task_type_code),
        target_url=str(draft['target_url']),
        reward=int(draft['reward_amount']),
        reward_floor=int(draft['performer_floor_reward']),
        quantity=int(draft['total_quantity']),
        unit_price=unit_price,
        floor=int(draft['client_floor_price']),
        recommended=recommended_unit_price,
        fast=fast_unit_price,
        priority=priority_unit_price,
        price_position=price_position,
        speed_explanation=speed_explanation,
        fee=int(draft['service_fee_total']),
        discount=int(draft['discount_percent']),
        budget=int(draft['budget_total']),
        speed=speed,
        speed_label=speed_label(speed, language),
        verification=verification_label(task_type_code, language),
        trust_tip=trust_tip(task_type_code, language),
        proof_guide=ProofGuideService.preview_block(task_type_code, language),
        internal_name=UserService.internal_currency_label(user_id),
    )


def _build_campaign_card_text(user_id: int, campaign_id: int) -> str:
    campaign = CampaignService.get_owned_campaign(user_id, campaign_id)
    if not campaign:
        return UserService.t(user_id, 'campaign_not_found')
    language = UserService.get_language(user_id)
    task_type_code = str(campaign['task_type'])
    pricing = _campaign_pricing_snapshot_from_row(campaign)
    unit_price = int(campaign['unit_price'] or campaign['reward_amount'])
    speed = int(pricing.get('speed_index') or 100)
    recommended_unit_price = int(pricing.get('recommended_unit_price') or unit_price)
    price_position = int(pricing.get('price_position_percent') or 0)
    speed_explanation = completion_speed_explanation(speed, unit_price, recommended_unit_price, language)
    progress = campaign_progress(campaign)
    health = health_label(campaign, language=language)
    next_action = action_tip(campaign, language=language)
    boost_block = boost_options_text(campaign, language=language, internal_name=UserService.internal_currency_label(user_id))
    return UserService.t(
        user_id,
        'campaign_card_screen',
        campaign_id=campaign_id,
        title=str(campaign['title'] or f'#{campaign_id}'),
        task_type=_task_type_label(user_id, task_type_code),
        target_url=str(campaign['target_url']),
        reward=int(campaign['reward_amount']),
        quantity=int(campaign['total_quantity']),
        completed=int(campaign['completed_quantity']),
        rejected=int(campaign['rejected_quantity']),
        progress=progress['progress_percent'],
        reject_percent=progress['reject_percent'],
        health=health,
        next_action=next_action,
        boost_block=boost_block,
        budget_total=int(campaign['budget_total']),
        budget_spent=int(campaign['budget_spent']),
        budget_reserved=int(campaign['budget_reserved']),
        budget_remaining=CampaignService.get_remaining_budget(campaign),
        unit_price=unit_price,
        fee_total=int(campaign['service_fee_total'] or 0),
        speed=speed,
        recommended=recommended_unit_price,
        price_position=price_position,
        speed_explanation=speed_explanation,
        funded='yes' if int(campaign['is_funded'] or 0) == 1 else 'no',
        internal_name=UserService.internal_currency_label(user_id),
        status=_campaign_status_label(user_id, str(campaign['status'])),
        speed_label=speed_label(speed, language),
        verification=verification_label(task_type_code, language),
        trust_tip=trust_tip(task_type_code, language),
    )



def _build_stats_text(user_id: int) -> str:
    language = UserService.get_language(user_id)
    dashboard = dashboard_summary(user_id, language=language)
    if dashboard['rows']:
        rows = '\n'.join(
            UserService.t(
                user_id,
                'client_dashboard_row',
                campaign_id=item['id'],
                title=item['title'][:36],
                status=_campaign_status_label(user_id, item['status']),
                progress=item['progress_percent'],
                speed=item['speed'],
                health=item['health'],
                tip=item['tip'],
            )
            for item in dashboard['rows']
        )
    else:
        rows = UserService.t(user_id, 'client_dashboard_empty')
    return UserService.t(
        user_id,
        'client_dashboard_screen',
        total=dashboard['total'],
        active=dashboard['active'],
        paused=dashboard['paused'],
        drafts=dashboard['drafts'],
        completed=dashboard['completed_total'],
        rejected=dashboard['rejected_total'],
        progress=dashboard['progress_percent'],
        budget=dashboard['budget_total'],
        spent=dashboard['budget_spent'],
        reserved=dashboard['budget_reserved'],
        remaining=dashboard['budget_remaining'],
        slow=dashboard['slow_count'],
        quality_risk=dashboard['quality_risk_count'],
        rows=rows,
        internal_name=UserService.internal_currency_label(user_id),
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
    plans_block = '\n'.join(
        UserService.t(
            user_id,
            'vip_plan_row',
            title=UserService.t(user_id, str(plan['title_key'])),
            desc=UserService.t(user_id, str(plan['desc_key'])),
            price=int(plan['price']),
            internal_name=UserService.internal_currency_label(user_id),
        )
        for plan in VIP_PLANS.values()
    )
    return UserService.t(
        user_id,
        'vip_screen',
        active_block=active_block,
        hold_speed=summary['hold_speed_percent'],
        task_bonus=summary['active_task_limit_bonus'],
        priority=summary['priority_level'],
        ref_bonus=_format_percent(summary['referral_rate_bonus_bps'] / 100),
        internal_name=UserService.internal_currency_label(user_id),
        plans_block=plans_block,
        stars_7=69,
        stars_30=199,
    )




def _build_rewards_text(user_id: int) -> str:
    wallet = WalletService.get_summary(user_id)
    items = []
    for item_code, item in RewardService.get_items().items():
        items.append(
            UserService.t(
                user_id,
                'reward_item_row',
                title=UserService.t(user_id, str(item['title_key'])),
                price=int(item['price']),
                internal_name=UserService.internal_currency_label(user_id),
            )
        )
    premium_rows = [f"• {offer['label']} · {offer['sparks_cost']} {UserService.internal_currency_label(user_id)}" for _, offer in RedemptionService.premium_offers().items()]
    gift_rows = [
        f"• {gift['emoji']} Telegram Gift · {gift['sparks_cost']} {UserService.internal_currency_label(user_id)} · {gift['star_count']}⭐"
        for gift in RedemptionService.list_gifts(limit=20)
    ]
    return UserService.t(
        user_id,
        'rewards_screen',
        balance=wallet['redeemable_balance'],
        bonus=wallet['bonus_balance'],
        items='\n'.join(items) if items else '—',
        premium_items='\n'.join(premium_rows) if premium_rows else UserService.t(user_id, 'redeem_catalog_unavailable'),
        gift_items='\n'.join(gift_rows) if gift_rows else UserService.t(user_id, 'redeem_catalog_unavailable'),
        cashout_items=UserService.t(user_id, 'redeem_cashout_manual'),
        redeem_access=UserService.t(user_id, 'redeem_access_yes' if wallet['has_paid_topup'] else 'redeem_access_no'),
        internal_name=UserService.internal_currency_label(user_id),
    )


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
        queue_high=stats['queue_high'],
        queue_clean=stats['queue_clean'],
        queue_old=stats['queue_old'],
        bot_chats_ready=stats['bot_chats_ready'],
        bot_chats_issues=stats['bot_chats_issues'],
        high_risk_unblocked=stats['high_risk_unblocked'],
        groups_performer=stats.get('groups_performer', 0),
        groups_campaign=stats.get('groups_campaign', 0),
        groups_risk=stats.get('groups_risk', 0),
    )


def _build_admin_queue_text(user_id: int, submissions, filter_code: str = 'all') -> str:
    counts = AdminConsoleService.queue_counts()
    active_filter = normalize_queue_filter(filter_code)
    header = UserService.t(
        user_id,
        'admin_queue_header',
        active_filter=UserService.t(user_id, queue_filter_label_key(active_filter)),
        all_count=counts['all'],
        high_count=counts['high'],
        clean_count=counts['clean'],
        old_count=counts['old'],
    )
    advice = AdminConsoleService.bulk_action_advice(active_filter)
    advice_text = UserService.t(
        user_id,
        'admin_bulk_advice_line',
        advice=UserService.t(user_id, f"admin_bulk_advice_{advice['advice_code']}"),
        count=int(advice.get('count', 0)),
        risk=UserService.t(user_id, f"admin_bulk_risk_{advice['risk_level']}"),
    )
    if not submissions:
        return header + '\n\n' + advice_text + '\n\n' + UserService.t(user_id, 'admin_queue_empty')
    rows = []
    for item in submissions[:10]:
        performer = str(item['username'] or '').strip()
        performer_label = f'@{performer}' if performer else f"ID {int(item['performer_user_id'])}"
        priority_score = int(item['priority_score'] or 0) if 'priority_score' in item.keys() else int(item['risk_score'] or 0) + int(item['user_risk_score'] or 0)
        rows.append(
            UserService.t(
                user_id,
                'admin_queue_line',
                submission_id=int(item['id']),
                title=str(item['campaign_title'] or f"#{int(item['campaign_id'])}"),
                performer=performer_label,
                risk=int(item['risk_score']),
                user_risk=int(item['user_risk_score']),
                priority=priority_score,
                priority_label=UserService.t(user_id, priority_label_key(priority_score)),
            )
        )
    return UserService.t(user_id, 'admin_queue_screen', header=header + '\n' + advice_text, items='\n'.join(rows))



def _build_admin_patterns_text(user_id: int) -> str:
    cards = AdminConsoleService.fraud_pattern_cards(limit=8)
    if not cards:
        items = UserService.t(user_id, 'admin_patterns_empty')
    else:
        lines = []
        for card in cards:
            username = str(card.get('username') or '').strip()
            display = f"@{username}" if username else f"ID {int(card['user_id'])}"
            lines.append(UserService.t(
                user_id,
                'admin_pattern_card_row',
                performer=display,
                status=str(card.get('status') or 'active'),
                risk=int(card.get('risk_score') or 0),
                approved=int(card.get('approved_count') or 0),
                rejected=int(card.get('rejected_count') or 0),
                review=int(card.get('review_count') or 0),
                avg=int(card.get('avg_submission_risk') or 0),
                notes=int(card.get('note_count') or 0),
                events=int(card.get('event_count') or 0),
                pattern=UserService.t(user_id, f"admin_pattern_{card.get('pattern_code') or 'neutral'}"),
                recommendation=UserService.t(user_id, f"admin_recommendation_{card.get('recommendation_code') or 'watch'}"),
            ))
        items = '\n'.join(lines)
    diagnostics = AdminConsoleService.bot_rights_diagnostics(limit=5)
    diag_lines = []
    for item in diagnostics.get('items', [])[:5]:
        diag_lines.append(UserService.t(
            user_id,
            'admin_audit_diag_row',
            title=str(item['title'])[:48],
            ref=str(item['ref']),
            severity=UserService.t(user_id, f"admin_audit_severity_{item['severity']}"),
            issue=UserService.t(user_id, f"admin_audit_issue_{item['code']}"),
        ))
    diag_text = '\n'.join(diag_lines) or UserService.t(user_id, 'admin_audit_diag_empty')
    return UserService.t(
        user_id,
        'admin_patterns_screen',
        items=items,
        active=int(diagnostics.get('active', 0)),
        ready=int(diagnostics.get('ready', 0)),
        issues=int(diagnostics.get('issues', 0)),
        stale=int(diagnostics.get('stale', 0)),
        inactive=int(diagnostics.get('inactive', 0)),
        diagnostics=diag_text,
    )



def _build_owner_analytics_text(user_id: int) -> str:
    summary = OwnerAnalyticsService.commerce_summary()
    clients = OwnerAnalyticsService.top_clients(limit=5)
    performers = OwnerAnalyticsService.top_performers(limit=5)
    tips = OwnerAnalyticsService.economy_recommendations(summary)

    client_lines = []
    for row in clients:
        username = str(row.get('username') or '').strip()
        display = f"@{username}" if username else f"ID {int(row['user_id'])}"
        client_lines.append(UserService.t(
            user_id,
            'owner_client_row',
            client=display,
            campaigns=int(row.get('campaigns') or 0),
            active=int(row.get('active_campaigns') or 0),
            spent=int(row.get('spent') or 0),
            budget=int(row.get('budget_total') or 0),
            completed=int(row.get('completed') or 0),
            rejected=int(row.get('rejected') or 0),
            internal_name=UserService.internal_currency_label(user_id),
        ))
    performer_lines = []
    for row in performers:
        username = str(row.get('username') or '').strip()
        display = f"@{username}" if username else f"ID {int(row['user_id'])}"
        performer_lines.append(UserService.t(
            user_id,
            'owner_performer_row',
            performer=display,
            approved=int(row.get('approved') or 0),
            rejected=int(row.get('rejected') or 0),
            review=int(row.get('manual_review') or 0),
            earned=int(row.get('earned') or 0),
            risk=int(row.get('risk_score') or 0),
            internal_name=UserService.internal_currency_label(user_id),
        ))
    tip_lines = '\n'.join('• ' + UserService.t(user_id, key) for key in tips)
    return UserService.t(
        user_id,
        'owner_analytics_screen',
        state=UserService.t(user_id, f"owner_state_{summary.get('commerce_state') or 'early'}"),
        score=int(summary['monetization_score']),
        users=int(summary['total_users']),
        active_users=int(summary['active_users']),
        clients_count=int(summary['clients']),
        performers_count=int(summary['performers']),
        blocked=int(summary['blocked_users']),
        campaigns=int(summary['total_campaigns']),
        active_campaigns=int(summary['active_campaigns']),
        funded_campaigns=int(summary['funded_campaigns']),
        drafts=int(summary['draft_campaigns']),
        completed=int(summary['completed_total']),
        rejected=int(summary['rejected_total']),
        completion=int(summary['completion_percent']),
        budget=int(summary['budget_total']),
        funded_budget=int(summary['funded_budget_total']),
        turnover=int(summary['turnover_spent']),
        reserved=int(summary['reserved_total']),
        planned_fee=int(summary['planned_fee_total']),
        margin=int(summary['actual_margin_estimate']),
        margin_percent=int(summary['margin_percent']),
        manual=int(summary['manual_review']),
        manual_percent=int(summary['manual_percent']),
        approval_percent=int(summary['approval_percent']),
        avg_risk=int(summary['avg_submission_risk']),
        available=int(summary['available_liability']),
        hold=int(summary['hold_liability']),
        bonus=int(summary['bonus_liability']),
        stars=int(summary['stars_topup_volume']),
        vip=int(summary['vip_volume']),
        campaign_payments=int(summary['campaign_payment_volume']),
        clients='\n'.join(client_lines) or UserService.t(user_id, 'owner_no_clients'),
        performers='\n'.join(performer_lines) or UserService.t(user_id, 'owner_no_performers'),
        tips=tip_lines,
        internal_name=UserService.internal_currency_label(user_id),
    )



def _build_owner_release_text(user_id: int) -> str:
    summary = ReleaseReadinessService.readiness_summary()
    guardrails = ReleaseReadinessService.launch_guardrails()
    rc1_gate = ReleaseReadinessService.rc1_gate_summary()
    stable_gate = ReleaseReadinessService.stable_release_summary()
    flow_lines = []
    for flow in summary['flows']:
        flow_lines.append(UserService.t(
            user_id,
            'release_flow_row',
            title=UserService.t(user_id, str(flow['title_key'])),
            status=UserService.t(user_id, f"release_status_{flow['status']}"),
            score=int(flow['score']),
            signal=UserService.t(user_id, str(flow['signal_key'])),
            action=UserService.t(user_id, str(flow['action_key'])),
        ))
    guard_lines = []
    for row in guardrails['matrix']:
        guard_lines.append(UserService.t(
            user_id,
            'launch_guard_row',
            title=UserService.t(user_id, str(row['title_key'])),
            status=UserService.t(user_id, f"release_status_{row['status']}"),
            value=int(row['value']),
            action=UserService.t(user_id, str(row['action_key'])),
        ))
    rc1_gate_lines = []
    for row in rc1_gate['rows']:
        rc1_gate_lines.append(UserService.t(
            user_id,
            'rc1_gate_row',
            title=UserService.t(user_id, str(row['title_key'])),
            status=UserService.t(user_id, f"release_status_{row['status']}"),
            value=int(row['value']),
            action=UserService.t(user_id, str(row['action_key'])),
        ))
    stable_gate_lines = []
    for row in stable_gate['rows']:
        stable_gate_lines.append(UserService.t(
            user_id,
            'stable_gate_row',
            title=UserService.t(user_id, str(row['title_key'])),
            status=UserService.t(user_id, f"release_status_{row['status']}"),
            value=int(row['value']),
            action=UserService.t(user_id, str(row['action_key'])),
        ))
    regression_lines = '\n'.join('• ' + UserService.t(user_id, key) for key in ReleaseReadinessService.regression_plan())
    checklist_lines = '\n'.join('• ' + UserService.t(user_id, key) for key in ReleaseReadinessService.final_launch_checklist())
    contract_lines = '\n'.join('• ' + UserService.t(user_id, key) for key in ReleaseReadinessService.rc1_release_contract())
    stable_contract_lines = '\n'.join('• ' + UserService.t(user_id, key) for key in ReleaseReadinessService.stable_release_contract())
    return UserService.t(
        user_id,
        'owner_release_screen',
        state=UserService.t(user_id, f"release_state_{summary['state']}"),
        launch_state=UserService.t(user_id, f"release_state_{guardrails['launch_state']}"),
        score=int(summary['score']),
        live_score=int(guardrails['live_score']),
        ready=int(summary['ready']),
        warnings=int(summary['warnings']),
        blockers=int(summary['blockers']),
        hard_blockers=int(guardrails['hard_blockers']),
        live_warnings=int(guardrails['live_warnings']),
        stable_state=UserService.t(user_id, f"release_state_{stable_gate['state']}"),
        stable_score=int(stable_gate['score']),
        stable_blockers=int(stable_gate['blockers']),
        stable_warnings=int(stable_gate['warnings']),
        rc1_state=UserService.t(user_id, f"release_state_{rc1_gate['state']}"),
        rc1_score=int(rc1_gate['score']),
        rc1_blockers=int(rc1_gate['blockers']),
        rc1_warnings=int(rc1_gate['warnings']),
        total=int(summary['total']),
        flows='\n'.join(flow_lines),
        guardrails='\n'.join(guard_lines),
        stable_gate='\n'.join(stable_gate_lines),
        rc1_gate='\n'.join(rc1_gate_lines),
        regression=regression_lines,
        checklist=checklist_lines,
        rc1_contract=contract_lines,
        stable_contract=stable_contract_lines,
    )



def _build_admin_groups_text(user_id: int) -> str:
    summary = AdminConsoleService.queue_group_summary(limit=7)

    performer_lines = []
    for row in summary['performers']:
        username = str(row['username'] or '').strip()
        display = f'@{username}' if username else f"ID {int(row['performer_user_id'])}"
        performer_lines.append(UserService.t(
            user_id,
            'admin_group_performer_row',
            performer=display,
            count=int(row['cnt'] or 0),
            risky=int(row['risky'] or 0),
            priority=int(row['max_priority'] or 0),
        ))
    campaign_lines = []
    for row in summary['campaigns']:
        campaign_lines.append(UserService.t(
            user_id,
            'admin_group_campaign_row',
            campaign_id=int(row['campaign_id']),
            title=str(row['title'] or f"#{int(row['campaign_id'])}")[:50],
            count=int(row['cnt'] or 0),
            risky=int(row['risky'] or 0),
            avg_risk=int(float(row['avg_risk'] or 0)),
        ))
    bucket_lines = []
    for row in summary['risk_buckets']:
        bucket_lines.append(UserService.t(
            user_id,
            'admin_group_bucket_row',
            bucket=UserService.t(user_id, f"admin_bucket_{str(row['bucket'])}"),
            count=int(row['cnt'] or 0),
        ))

    return UserService.t(
        user_id,
        'admin_groups_screen',
        performers='\n'.join(performer_lines) or UserService.t(user_id, 'admin_groups_empty'),
        campaigns='\n'.join(campaign_lines) or UserService.t(user_id, 'admin_groups_empty'),
        buckets='\n'.join(bucket_lines) or UserService.t(user_id, 'admin_groups_empty'),
    )

def _build_admin_submission_text(user_id: int, submission_id: int) -> tuple[str, dict[str, object] | None]:
    card = AdminService.get_submission_card(submission_id)
    if not card:
        return UserService.t(user_id, 'admin_submission_not_found'), None
    submission = card['submission']
    stats = card['stats']
    proof = str(submission['proof_text'] or '—')
    events = card['events']
    notes = card.get('notes') or []
    if notes:
        note_lines = '\n'.join(
            UserService.t(
                user_id,
                'admin_note_row',
                created=str(note['created_at']).replace('T', ' ')[:16],
                admin_id=int(note['admin_user_id']),
                note=str(note['note'] or '—')[:220],
            )
            for note in notes
        )
    else:
        note_lines = UserService.t(user_id, 'admin_notes_empty')
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
    history_rows = card.get('decision_history') or []
    if history_rows:
        history_lines = '\n'.join(
            UserService.t(
                user_id,
                'admin_decision_history_row',
                submission_id=int(row['id']),
                status=str(row['status']),
                risk=int(row['risk_score'] or 0),
                reviewed=str(row['reviewed_at'] or '—').replace('T', ' ')[:16],
                reason=str(row['reject_reason'] or '—')[:90],
            )
            for row in history_rows
        )
    else:
        history_lines = UserService.t(user_id, 'admin_decision_history_empty')
    pattern_card = card.get('pattern_card') or {}
    pattern_text = UserService.t(
        user_id,
        'admin_submission_pattern_card',
        pattern=UserService.t(user_id, f"admin_pattern_{pattern_card.get('pattern_code') or 'neutral'}"),
        recommendation=UserService.t(user_id, f"admin_recommendation_{pattern_card.get('recommendation_code') or 'watch'}"),
        approved=int(pattern_card.get('approved_count') or 0),
        rejected=int(pattern_card.get('rejected_count') or 0),
        review=int(pattern_card.get('review_count') or 0),
        avg=int(pattern_card.get('avg_submission_risk') or 0),
        notes=int(pattern_card.get('note_count') or 0),
        events=int(pattern_card.get('event_count') or 0),
    )
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
        notes=note_lines,
        decision_history=history_lines,
        pattern_card=pattern_text,
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


def _build_admin_required_chats_text(user_id: int) -> str:
    chats = SubscriptionService.list_required_chats()
    if not chats:
        return UserService.t(user_id, 'admin_required_chats_empty')
    items = []
    for row in chats[:10]:
        chat_ref = str(row['chat_ref'])
        join_link = SubscriptionService.effective_join_link(chat_ref, str(row['join_link'] or '')) or '—'
        items.append(
            UserService.t(
                user_id,
                'admin_required_chat_row',
                chat_id=int(row['id']),
                name=SubscriptionService.display_name(chat_ref),
                link=join_link,
            )
        )
    return UserService.t(
        user_id,
        'admin_required_chats_screen',
        count=len(chats),
        limit=10,
        items='\n'.join(items),
    )


def _build_admin_required_chat_add_text(user_id: int) -> str:
    return UserService.t(user_id, 'admin_required_chat_add_prompt')


def _build_admin_bot_chats_text(user_id: int, page: int) -> tuple[str, list, int]:
    total = BotChatService.count_all_chats()
    per_page = 10
    total_pages = max((total + per_page - 1) // per_page, 1)
    page = min(max(page, 1), total_pages)
    rows = BotChatService.list_all_chats(limit=per_page, offset=(page - 1) * per_page)
    if not rows:
        items = UserService.t(user_id, 'admin_bot_chats_empty')
    else:
        lines = []
        for row in rows:
            title = str(row['title'] or SubscriptionService.display_name(str(row['chat_ref'] or row['chat_id'])))
            ref = str(row['chat_ref'] or row['chat_id'])
            chat_type = str(row['chat_type'] or 'chat')
            lines.append(UserService.t(user_id, 'admin_bot_chat_row', title=title[:60], ref=ref, chat_type=chat_type))
        items = '\n'.join(lines)
    return UserService.t(user_id, 'admin_bot_chats_screen', items=items, page=page, total_pages=total_pages, total=total), rows, total_pages


def _build_admin_bot_rights_text(user_id: int, page: int) -> tuple[str, list, int]:
    total = AdminConsoleService.count_bot_right_issues()
    per_page = 10
    total_pages = max((total + per_page - 1) // per_page, 1)
    page = min(max(page, 1), total_pages)
    rows = AdminConsoleService.list_bot_right_issues(limit=per_page, offset=(page - 1) * per_page)
    summary = AdminConsoleService.bot_rights_summary()
    if not rows:
        items = UserService.t(user_id, 'admin_bot_rights_empty')
    else:
        lines = []
        for row in rows:
            title = str(row['title'] or SubscriptionService.display_name(str(row['chat_ref'] or row['chat_id'])))
            ref = str(row['chat_ref'] or row['chat_id'])
            chat_type = str(row['chat_type'] or 'chat')
            lines.append(UserService.t(user_id, 'admin_bot_right_row', title=title[:60], ref=ref, chat_type=chat_type))
        items = '\n'.join(lines)
    return UserService.t(
        user_id,
        'admin_bot_rights_screen',
        items=items,
        page=page,
        total_pages=total_pages,
        total=total,
        active=summary['active'],
        ready=summary['ready'],
        issues=summary['issues'],
    ), rows, total_pages



def _build_admin_users_text(user_id: int, page: int) -> tuple[str, list, int]:
    total = UserService.count_users()
    per_page = 10
    total_pages = max((total + per_page - 1) // per_page, 1)
    page = min(max(page, 1), total_pages)
    rows = UserService.list_users(limit=per_page, offset=(page - 1) * per_page)
    if not rows:
        items = UserService.t(user_id, 'admin_users_empty')
    else:
        lines = []
        for row in rows:
            username = str(row['username'] or '').strip()
            display = f'@{username}' if username else f"ID {int(row['user_id'])}"
            trust = TrustService.summary(int(row['user_id']), language=UserService.get_language(user_id))
            lines.append(UserService.t(
                user_id,
                'admin_user_row',
                display=display,
                user_id=int(row['user_id']),
                status=str(row['status']),
                sparks=int(row['internal_balance'] or 0),
                bonus=int(row['bonus_balance'] or 0),
                trust_level=trust['level_label'],
                trust_score=trust['score'],
                approval_rate=trust['approval_rate'],
            ))
        items = '\n'.join(lines)
    return UserService.t(user_id, 'admin_users_screen', items=items, page=page, total_pages=total_pages, total=total), rows, total_pages


def _build_admin_input_text(user_id: int, kind: str, target_id: int) -> str:
    if kind == 'reject':
        return UserService.t(user_id, 'admin_reject_prompt', submission_id=target_id)
    target_user = UserService.get_user(target_id)
    display = f"@{str(target_user['username'])}" if target_user and target_user['username'] else f'ID {target_id}'
    if kind == 'risk':
        risk = int(target_user['risk_score']) if target_user else 0
        return UserService.t(user_id, 'admin_adjust_risk_prompt', target=display, target_user_id=target_id, current=risk)
    return UserService.t(user_id, 'admin_adjust_balance_prompt', target=display, target_user_id=target_id)



def resolve_next_screen(bot: telebot.TeleBot, user_id: int, chat_id: int, chat_username: str | None = None) -> str:
    if not UserService.can_access_bot(user_id):
        return SCREEN_BLOCKED
    role = UserService.get_role(user_id)
    if not role:
        return SCREEN_ROLE
    if not CommunityRulesService.is_accepted(user_id) and not UserService.is_admin(user_id):
        return SCREEN_COMMUNITY_RULES
    if SubscriptionService.should_enforce_required_chat(chat_id, chat_username=chat_username):
        check = SubscriptionService.get_subscription_check_result(bot, user_id)
        if not check.is_subscribed and not check.is_unknown:
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
    chat_username = _chat_username(target)
    UserService.ensure_user(target.from_user)
    if not UserService.can_access_bot(user_id) and screen_key != SCREEN_BLOCKED:
        screen_key = SCREEN_BLOCKED
    released = PerformerService.release_due_holds(user_id)

    if screen_key == SCREEN_LANGUAGE:
        text = _prepend_notice(user_id, UserService.t(user_id, 'welcome', brand=settings.brand_name), notice_key, notice_text)
        render_managed_screen(
            bot,
            target=target,
            profile_id=user_id,
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
            profile_id=user_id,
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
            profile_id=user_id,
            chat_id=chat_id,
            screen_key=SCREEN_REQUIRED_SUBSCRIPTION,
            text=text,
            reply_markup_builder=lambda version: subscription_keyboard(user_id, version),
        )
        return

    if screen_key == SCREEN_COMMUNITY_RULES:
        text = _prepend_notice(user_id, _build_community_rules_text(user_id), notice_key, notice_text)
        render_managed_screen(
            bot,
            target=target,
            profile_id=user_id,
            chat_id=chat_id,
            screen_key=SCREEN_COMMUNITY_RULES,
            text=text,
            reply_markup_builder=lambda version: community_rules_keyboard(user_id, version, accepted=CommunityRulesService.is_accepted(user_id)),
        )
        return

    if screen_key == SCREEN_BLOCKED:
        text = _prepend_notice(user_id, _build_blocked_text(user_id), notice_key, notice_text)
        render_managed_screen(
            bot,
            target=target,
            profile_id=user_id,
            chat_id=chat_id,
            screen_key=SCREEN_BLOCKED,
            text=text,
            reply_markup_builder=lambda version: blocked_keyboard(user_id, version),
        )
        return

    protected_open_screens = {SCREEN_LANGUAGE, SCREEN_ROLE, SCREEN_REQUIRED_SUBSCRIPTION, SCREEN_BLOCKED, SCREEN_COMMUNITY_RULES, SCREEN_LEGAL_DOCS}
    if screen_key not in protected_open_screens and not CommunityRulesService.is_accepted(user_id) and not UserService.is_admin(user_id):
        render_screen(bot, target, SCREEN_COMMUNITY_RULES, notice_key='community_rules_required_notice')
        return
    if screen_key not in protected_open_screens and not LegalDocsService.is_accepted(user_id) and not UserService.is_admin(user_id):
        render_screen(bot, target, SCREEN_LEGAL_DOCS, notice_key='legal_docs_required_notice')
        return

    if (
        screen_key in {SCREEN_ADMIN, SCREEN_ADMIN_QUEUE, SCREEN_ADMIN_LOGS, SCREEN_ADMIN_REQUIRED_CHATS, SCREEN_ADMIN_REQUIRED_CHAT_ADD, SCREEN_OWNER_PROVIDER, SCREEN_ADMIN_ENGAGEMENT_OBLIGATIONS}
        or screen_key.startswith(SCREEN_ADMIN_BOT_CHATS_PREFIX)
        or screen_key.startswith(SCREEN_ADMIN_USERS_PREFIX)
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
            profile_id=user_id,
            chat_id=chat_id,
            screen_key=SCREEN_MAIN_MENU,
            text=text,
            reply_markup_builder=lambda version: main_menu_keyboard(user_id, role, version),
        )
        return


    if screen_key == SCREEN_LEGAL_DOCS:
        text = _prepend_notice(user_id, _build_legal_docs_text(user_id), notice_key, notice_text)
        render_managed_screen(bot, target=target, profile_id=user_id, chat_id=chat_id, screen_key=SCREEN_LEGAL_DOCS, text=text, reply_markup_builder=lambda version: legal_docs_keyboard(user_id, version, accepted=LegalDocsService.is_accepted(user_id)))
        return

    if screen_key == SCREEN_SMART_HUB:
        data = SmartHubService.dashboard(user_id)
        text = _prepend_notice(user_id, _build_smart_hub_text(user_id), notice_key, notice_text)
        render_managed_screen(bot, target=target, profile_id=user_id, chat_id=chat_id, screen_key=SCREEN_SMART_HUB, text=text, reply_markup_builder=lambda version: smart_hub_keyboard(user_id, version, data['role']))
        return

    if screen_key == SCREEN_ENGAGEMENT_MODE:
        text = _prepend_notice(user_id, _build_engagement_mode_text(user_id), notice_key, notice_text)
        render_managed_screen(bot, target=target, profile_id=user_id, chat_id=chat_id, screen_key=SCREEN_ENGAGEMENT_MODE, text=text, reply_markup_builder=lambda version: engagement_mode_keyboard(user_id, version))
        return

    if screen_key == SCREEN_ENGAGEMENT_OBLIGATIONS:
        text = _prepend_notice(user_id, _build_engagement_obligations_text(user_id), notice_key, notice_text)
        render_managed_screen(bot, target=target, profile_id=user_id, chat_id=chat_id, screen_key=SCREEN_ENGAGEMENT_OBLIGATIONS, text=text, reply_markup_builder=lambda version: engagement_obligations_keyboard(user_id, version))
        return

    if screen_key == SCREEN_ADMIN_ENGAGEMENT_OBLIGATIONS:
        text = _prepend_notice(user_id, _build_admin_engagement_obligations_text(user_id), notice_key, notice_text)
        render_managed_screen(bot, target=target, profile_id=user_id, chat_id=chat_id, screen_key=SCREEN_ADMIN_ENGAGEMENT_OBLIGATIONS, text=text, reply_markup_builder=lambda version: admin_engagement_obligations_keyboard(user_id, version, EngagementModeService.admin_obligation_overview(limit=5)['items']))
        return

    if screen_key == SCREEN_ENGAGEMENT_GROWTH:
        text_body = _build_engagement_growth_text(user_id)
        text = _prepend_notice(user_id, text_body, notice_key, notice_text)
        render_managed_screen(bot, target=target, profile_id=user_id, chat_id=chat_id, screen_key=SCREEN_ENGAGEMENT_GROWTH, text=text, reply_markup_builder=lambda version: engagement_growth_keyboard(user_id, version))
        return

    if screen_key == SCREEN_MARKETPLACE:
        text_body, services = _build_marketplace_text(user_id)
        text = _prepend_notice(user_id, text_body, notice_key, notice_text)
        render_managed_screen(bot, target=target, profile_id=user_id, chat_id=chat_id, screen_key=SCREEN_MARKETPLACE, text=text, reply_markup_builder=lambda version: marketplace_keyboard(user_id, version, services))
        return

    if screen_key == SCREEN_PROFILE:
        text = _prepend_notice(user_id, _build_profile_text(user_id), notice_key, notice_text)
        render_managed_screen(
            bot,
            target=target,
            profile_id=user_id,
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
            profile_id=user_id,
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
            profile_id=user_id,
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
        submission = PerformerService.get_submission(proof_submission_id)
        task_type_code = ''
        target_url = ''
        if submission and int(submission['performer_user_id']) == user_id:
            campaign = PerformerService.get_campaign(int(submission['campaign_id']))
            if campaign:
                task_type_code = str(campaign['task_type'])
                target_url = str(campaign['target_url'])
        guide_block = ProofGuideService.proof_prompt_block(task_type_code, target_url, UserService.get_language(user_id))
        text = _prepend_notice(user_id, UserService.t(user_id, 'proof_prompt', internal_name=UserService.internal_currency_label(user_id), proof_guide=guide_block), notice_key, notice_text)
        render_managed_screen(
            bot,
            target=target,
            profile_id=user_id,
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
            profile_id=user_id,
            chat_id=chat_id,
            screen_key=SCREEN_WALLET,
            text=text,
            reply_markup_builder=lambda version: wallet_keyboard(user_id, version),
        )
        return

    if screen_key == SCREEN_TOPUP_PACKAGES:
        text = _prepend_notice(user_id, UserService.t(user_id, 'topup_packages_screen', internal_name=UserService.internal_currency_label(user_id)), notice_key, notice_text)
        render_managed_screen(
            bot,
            target=target,
            profile_id=user_id,
            chat_id=chat_id,
            screen_key=SCREEN_TOPUP_PACKAGES,
            text=text,
            reply_markup_builder=lambda version: topup_packages_keyboard(user_id, version),
        )
        return

    if screen_key == SCREEN_TOPUP_CUSTOM:
        text = _prepend_notice(user_id, UserService.t(user_id, 'topup_custom_screen', rate=6, internal_name=UserService.internal_currency_label(user_id)), notice_key, notice_text)
        render_managed_screen(
            bot,
            target=target,
            profile_id=user_id,
            chat_id=chat_id,
            screen_key=SCREEN_TOPUP_CUSTOM,
            text=text,
            reply_markup_builder=lambda version: topup_custom_keyboard(user_id, version),
        )
        return

    if screen_key == SCREEN_HISTORY:
        text = _prepend_notice(user_id, _build_history_text(user_id), notice_key, notice_text)
        render_managed_screen(
            bot,
            target=target,
            profile_id=user_id,
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
            profile_id=user_id,
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
            profile_id=user_id,
            chat_id=chat_id,
            screen_key=SCREEN_REWARDS,
            text=text,
            reply_markup_builder=lambda version: rewards_keyboard(user_id, version),
        )
        return

    if screen_key == SCREEN_EXCHANGE:
        text = _prepend_notice(user_id, _build_rewards_text(user_id), notice_key, notice_text)
        render_managed_screen(
            bot,
            target=target,
            profile_id=user_id,
            chat_id=chat_id,
            screen_key=SCREEN_EXCHANGE,
            text=text,
            reply_markup_builder=lambda version: exchange_keyboard(user_id, version),
        )
        return

    if screen_key == SCREEN_REFERRALS:
        text = _prepend_notice(user_id, _build_referrals_text(user_id), notice_key, notice_text)
        render_managed_screen(
            bot,
            target=target,
            profile_id=user_id,
            chat_id=chat_id,
            screen_key=SCREEN_REFERRALS,
            text=text,
            reply_markup_builder=lambda version: referrals_keyboard(user_id, version),
        )
        return

    if screen_key == SCREEN_BROADCAST_TEXT:
        text = _prepend_notice(user_id, _build_broadcast_text_screen(user_id), notice_key, notice_text)
        render_managed_screen(
            bot, target=target, profile_id=user_id, chat_id=chat_id, screen_key=SCREEN_BROADCAST_TEXT, text=text,
            reply_markup_builder=lambda version: broadcast_input_keyboard(user_id, version, is_admin=bool((AdBroadcastService.get_draft(user_id) or {}).get('is_admin'))),
        )
        return

    if screen_key == SCREEN_BROADCAST_LINK:
        text = _prepend_notice(user_id, _build_broadcast_link_screen(user_id), notice_key, notice_text)
        render_managed_screen(
            bot, target=target, profile_id=user_id, chat_id=chat_id, screen_key=SCREEN_BROADCAST_LINK, text=text,
            reply_markup_builder=lambda version: broadcast_input_keyboard(user_id, version, is_admin=bool((AdBroadcastService.get_draft(user_id) or {}).get('is_admin'))),
        )
        return

    if screen_key == SCREEN_BROADCAST_SCHEDULE:
        text = _prepend_notice(user_id, _build_broadcast_schedule_text(user_id), notice_key, notice_text)
        render_managed_screen(
            bot, target=target, profile_id=user_id, chat_id=chat_id, screen_key=SCREEN_BROADCAST_SCHEDULE, text=text,
            reply_markup_builder=lambda version: broadcast_schedule_keyboard(user_id, version),
        )
        return

    if screen_key == SCREEN_BROADCAST_PREVIEW:
        draft = AdBroadcastService.get_draft(user_id) or {}
        text = _prepend_notice(user_id, _build_broadcast_preview_text(user_id), notice_key, notice_text)
        render_managed_screen(
            bot, target=target, profile_id=user_id, chat_id=chat_id, screen_key=SCREEN_BROADCAST_PREVIEW, text=text,
            reply_markup_builder=lambda version: broadcast_preview_keyboard(user_id, version, is_admin=bool(draft.get('is_admin'))),
        )
        return

    if screen_key == SCREEN_CAMPAIGNS:
        campaigns = CampaignService.get_campaigns_for_owner(user_id)
        text = _prepend_notice(user_id, _build_campaigns_text(user_id, campaigns), notice_key, notice_text)
        render_managed_screen(
            bot,
            target=target,
            profile_id=user_id,
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
            profile_id=user_id,
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
            profile_id=user_id,
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
            profile_id=user_id,
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
            profile_id=user_id,
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
            profile_id=user_id,
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
            profile_id=user_id,
            chat_id=chat_id,
            screen_key=SCREEN_ADMIN,
            text=text,
            reply_markup_builder=lambda version: admin_home_keyboard(user_id, version),
        )
        return



    if screen_key == SCREEN_OWNER_PROVIDER:
        if not UserService.is_owner(user_id):
            render_screen(bot, target, SCREEN_ADMIN, notice_key='admin_access_denied')
            return
        text_body, services = _build_owner_provider_text(user_id)
        text = _prepend_notice(user_id, text_body, notice_key, notice_text)
        render_managed_screen(bot, target=target, profile_id=user_id, chat_id=chat_id, screen_key=SCREEN_OWNER_PROVIDER, text=text, reply_markup_builder=lambda version: owner_provider_keyboard(user_id, version, services))
        return

    if screen_key == SCREEN_OWNER_ANALYTICS:
        if not UserService.is_owner(user_id):
            render_screen(bot, target, SCREEN_ADMIN, notice_key='admin_access_denied')
            return
        text = _prepend_notice(user_id, _build_owner_analytics_text(user_id), notice_key, notice_text)
        render_managed_screen(
            bot,
            target=target,
            profile_id=user_id,
            chat_id=chat_id,
            screen_key=SCREEN_OWNER_ANALYTICS,
            text=text,
            reply_markup_builder=lambda version: owner_analytics_keyboard(user_id, version),
        )
        return

    if screen_key == SCREEN_OWNER_RELEASE:
        if not UserService.is_owner(user_id):
            render_screen(bot, target, SCREEN_ADMIN, notice_key='admin_access_denied')
            return
        text = _prepend_notice(user_id, _build_owner_release_text(user_id), notice_key, notice_text)
        render_managed_screen(
            bot,
            target=target,
            profile_id=user_id,
            chat_id=chat_id,
            screen_key=SCREEN_OWNER_RELEASE,
            text=text,
            reply_markup_builder=lambda version: owner_release_keyboard(user_id, version),
        )
        return

    if screen_key == SCREEN_ADMIN_GROUPS:
        if not UserService.is_admin(user_id):
            render_screen(bot, target, SCREEN_MAIN_MENU, notice_key='admin_access_denied')
            return
        text = _prepend_notice(user_id, _build_admin_groups_text(user_id), notice_key, notice_text)
        render_managed_screen(
            bot,
            target=target,
            profile_id=user_id,
            chat_id=chat_id,
            screen_key=SCREEN_ADMIN_GROUPS,
            text=text,
            reply_markup_builder=lambda version: admin_groups_keyboard(user_id, version),
        )
        return

    if screen_key == SCREEN_ADMIN_PATTERNS:
        if not UserService.is_admin(user_id):
            render_screen(bot, target, SCREEN_MAIN_MENU, notice_key='admin_access_denied')
            return
        text = _prepend_notice(user_id, _build_admin_patterns_text(user_id), notice_key, notice_text)
        render_managed_screen(
            bot,
            target=target,
            profile_id=user_id,
            chat_id=chat_id,
            screen_key=SCREEN_ADMIN_PATTERNS,
            text=text,
            reply_markup_builder=lambda version: admin_patterns_keyboard(user_id, version),
        )
        return

    queue_filter_payload = None
    if screen_key == SCREEN_ADMIN_QUEUE:
        queue_filter_payload = 'all'
    else:
        queue_filter_payload = _screen_suffix(screen_key, SCREEN_ADMIN_QUEUE_PREFIX)
    if queue_filter_payload is not None:
        if not UserService.is_admin(user_id):
            render_screen(bot, target, SCREEN_MAIN_MENU, notice_key='admin_access_denied')
            return
        filter_code = normalize_queue_filter(queue_filter_payload)
        submissions = AdminService.list_review_queue(filter_code=filter_code)
        text = _prepend_notice(user_id, _build_admin_queue_text(user_id, submissions, filter_code), notice_key, notice_text)
        render_managed_screen(
            bot,
            target=target,
            profile_id=user_id,
            chat_id=chat_id,
            screen_key=admin_queue_screen_key(filter_code),
            text=text,
            reply_markup_builder=lambda version: admin_queue_keyboard(user_id, version, submissions, filter_code=filter_code),
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
            profile_id=user_id,
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
            profile_id=user_id,
            chat_id=chat_id,
            screen_key=SCREEN_ADMIN_LOGS,
            text=text,
            reply_markup_builder=lambda version: admin_logs_keyboard(user_id, version),
        )
        return

    admin_bot_chats_page = _screen_suffix(screen_key, SCREEN_ADMIN_BOT_CHATS_PREFIX)
    if admin_bot_chats_page is not None:
        if not UserService.is_admin(user_id):
            render_screen(bot, target, SCREEN_ADMIN, notice_key='admin_access_denied')
            return
        page = _safe_page(admin_bot_chats_page)
        text, rows, total_pages = _build_admin_bot_chats_text(user_id, page)
        text = _prepend_notice(user_id, text, notice_key, notice_text)
        render_managed_screen(
            bot,
            target=target,
            profile_id=user_id,
            chat_id=chat_id,
            screen_key=admin_bot_chats_screen_key(page),
            text=text,
            reply_markup_builder=lambda version: admin_bot_chats_keyboard(user_id, version, rows, page=page, total_pages=total_pages),
        )
        return

    admin_bot_rights_page = _screen_suffix(screen_key, SCREEN_ADMIN_BOT_RIGHTS_PREFIX)
    if admin_bot_rights_page is not None:
        if not UserService.is_admin(user_id):
            render_screen(bot, target, SCREEN_ADMIN, notice_key='admin_access_denied')
            return
        page = _safe_page(admin_bot_rights_page)
        text, rows, total_pages = _build_admin_bot_rights_text(user_id, page)
        text = _prepend_notice(user_id, text, notice_key, notice_text)
        render_managed_screen(
            bot,
            target=target,
            profile_id=user_id,
            chat_id=chat_id,
            screen_key=admin_bot_rights_screen_key(page),
            text=text,
            reply_markup_builder=lambda version: admin_bot_chats_keyboard(user_id, version, rows, page=page, total_pages=total_pages, issues_mode=True),
        )
        return

    admin_users_page = _screen_suffix(screen_key, SCREEN_ADMIN_USERS_PREFIX)
    if admin_users_page is not None:
        if not UserService.is_admin(user_id):
            render_screen(bot, target, SCREEN_ADMIN, notice_key='admin_access_denied')
            return
        page = _safe_page(admin_users_page)
        text, rows, total_pages = _build_admin_users_text(user_id, page)
        text = _prepend_notice(user_id, text, notice_key, notice_text)
        render_managed_screen(
            bot,
            target=target,
            profile_id=user_id,
            chat_id=chat_id,
            screen_key=admin_users_screen_key(page),
            text=text,
            reply_markup_builder=lambda version: admin_users_keyboard(user_id, version, rows, page=page, total_pages=total_pages),
        )
        return

    if screen_key == SCREEN_ADMIN_REQUIRED_CHATS:
        if not UserService.is_owner(user_id):
            render_screen(bot, target, SCREEN_ADMIN, notice_key='admin_access_denied')
            return
        chats = SubscriptionService.list_required_chats()
        text = _prepend_notice(user_id, _build_admin_required_chats_text(user_id), notice_key, notice_text)
        render_managed_screen(
            bot,
            target=target,
            profile_id=user_id,
            chat_id=chat_id,
            screen_key=SCREEN_ADMIN_REQUIRED_CHATS,
            text=text,
            reply_markup_builder=lambda version: admin_required_chats_keyboard(user_id, version, chats),
        )
        return

    if screen_key == SCREEN_ADMIN_REQUIRED_CHAT_ADD:
        if not UserService.is_owner(user_id):
            render_screen(bot, target, SCREEN_ADMIN, notice_key='admin_access_denied')
            return
        text = _prepend_notice(user_id, _build_admin_required_chat_add_text(user_id), notice_key, notice_text)
        render_managed_screen(
            bot,
            target=target,
            profile_id=user_id,
            chat_id=chat_id,
            screen_key=SCREEN_ADMIN_REQUIRED_CHAT_ADD,
            text=text,
            reply_markup_builder=lambda version: admin_input_keyboard(user_id, version, back_target='admin_required_chats'),
        )
        return

    admin_reject_id = _screen_payload(screen_key, SCREEN_ADMIN_REJECT_PREFIX)
    if admin_reject_id is not None:
        text = _prepend_notice(user_id, _build_admin_input_text(user_id, 'reject', admin_reject_id), notice_key, notice_text)
        render_managed_screen(
            bot,
            target=target,
            profile_id=user_id,
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
            profile_id=user_id,
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
            profile_id=user_id,
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
    chat_username = _chat_username(target)
    UserService.ensure_user(target.from_user)
    if force_language:
        render_screen(bot, target, SCREEN_LANGUAGE)
        return
    next_screen = resolve_next_screen(bot, user_id, chat_id, chat_username=chat_username)
    render_screen(bot, target, next_screen)
