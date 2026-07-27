from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup
try:
    from telebot.types import WebAppInfo
except Exception:  # pragma: no cover
    WebAppInfo = None

from app.config import settings
from app.services.bot_chats import BotChatService
from app.services.ad_broadcasts import AdBroadcastService
from app.services.client_campaigns import TASK_TYPES
from app.services.client_dashboard import boost_options
from app.services.engagement_growth import EngagementGrowthService
from app.services.engagement_modes import EngagementModeService
from app.services.payments import PACK_STAR_LEVELS, SPARKS_PACKS, VIP_STARS_PLANS
from app.services.redemptions import RedemptionService
from app.services.rewards import RewardService
from app.services.subscriptions import SubscriptionService
from app.services.users import UserService
from app.services.invoice_messages import InvoiceMessageService
from app.services.vip import VIP_PLANS
from app.texts import LANGUAGES, ROLE_CLIENT, ROLE_PERFORMER
from app.utils.callbacks import pack_callback


TASK_TYPE_TEXT_KEYS = {
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


STATUS_TEXT_KEYS = {
    'draft': 'campaign_status_draft',
    'active': 'campaign_status_active',
    'paused': 'campaign_status_paused',
    'completed': 'campaign_status_completed',
    'archived': 'campaign_status_archived',
}


def language_keyboard(version: int) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=2)
    buttons = [
        InlineKeyboardButton(text=label, callback_data=pack_callback(version, 'lang', code))
        for code, label in LANGUAGES.items()
    ]
    markup.add(*buttons)
    return markup



def role_keyboard(user_id: int, version: int) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton(
            text=UserService.role_label(user_id, ROLE_PERFORMER),
            callback_data=pack_callback(version, 'role', ROLE_PERFORMER),
        ),
        InlineKeyboardButton(
            text=UserService.role_label(user_id, ROLE_CLIENT),
            callback_data=pack_callback(version, 'role', ROLE_CLIENT),
        ),
    )
    markup.add(
        InlineKeyboardButton(
            text=UserService.t(user_id, 'back_to_language'),
            callback_data=pack_callback(version, 'go', 'language'),
        )
    )
    return markup



def subscription_keyboard(user_id: int, version: int) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=1)
    required_chats = SubscriptionService.list_required_chats()
    for row in required_chats[:10]:
        join_link = SubscriptionService.effective_join_link(str(row['chat_ref']), str(row['join_link'] or ''))
        if not join_link:
            continue
        markup.add(
            InlineKeyboardButton(
                text=UserService.t(
                    user_id,
                    'open_required_chat_named',
                    name=SubscriptionService.display_name(str(row['chat_ref'])),
                ),
                url=join_link,
            )
        )
    markup.add(
        InlineKeyboardButton(
            text=UserService.t(user_id, 'check_subscription'),
            callback_data=pack_callback(version, 'check_subscription', 'required_chat'),
        ),
        InlineKeyboardButton(
            text=UserService.t(user_id, 'back_to_menu'),
            callback_data=pack_callback(version, 'go', 'main_menu'),
        ),
    )
    return markup



def main_menu_keyboard(user_id: int, role: str | None, version: int) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton(text=UserService.t(user_id, 'smart_hub_button'), callback_data=pack_callback(version, 'go', 'smart_hub')),
        InlineKeyboardButton(text=UserService.t(user_id, 'engagement_growth_button'), callback_data=pack_callback(version, 'go', 'engagement_growth')),
    )
    markup.add(InlineKeyboardButton(text=UserService.t(user_id, 'engagement_obligations_button'), callback_data=pack_callback(version, 'go', 'engagement_obligations')))
    markup.add(
        InlineKeyboardButton(text=UserService.t(user_id, 'marketplace_button'), callback_data=pack_callback(version, 'go', 'marketplace')),
        InlineKeyboardButton(text=UserService.t(user_id, 'community_rules_button'), callback_data=pack_callback(version, 'go', 'community_rules')),
    )
    markup.add(
        InlineKeyboardButton(text=UserService.t(user_id, 'menu_wallet'), callback_data=pack_callback(version, 'go', 'wallet')),
        InlineKeyboardButton(text=UserService.t(user_id, 'menu_vip'), callback_data=pack_callback(version, 'go', 'vip')),
    )
    if role == ROLE_PERFORMER:
        markup.add(
            InlineKeyboardButton(
                text=UserService.t(user_id, 'menu_profile'),
                callback_data=pack_callback(version, 'go', 'profile'),
            ),
            InlineKeyboardButton(
                text=UserService.t(user_id, 'menu_tasks'),
                callback_data=pack_callback(version, 'go', 'tasks'),
            ),
            InlineKeyboardButton(
                text=UserService.t(user_id, 'menu_wallet'),
                callback_data=pack_callback(version, 'go', 'wallet'),
            ),
            InlineKeyboardButton(
                text=UserService.t(user_id, 'menu_history'),
                callback_data=pack_callback(version, 'go', 'history'),
            ),
            InlineKeyboardButton(
                text=UserService.t(user_id, 'menu_referrals'),
                callback_data=pack_callback(version, 'go', 'referrals'),
            ),
        )
    else:
        markup.add(
            InlineKeyboardButton(
                text=UserService.t(user_id, 'menu_campaigns'),
                callback_data=pack_callback(version, 'go', 'campaigns'),
            ),
            InlineKeyboardButton(
                text=UserService.t(user_id, 'menu_stats'),
                callback_data=pack_callback(version, 'go', 'stats'),
            ),
            InlineKeyboardButton(
                text=UserService.t(user_id, 'menu_wallet'),
                callback_data=pack_callback(version, 'go', 'wallet'),
            ),
            InlineKeyboardButton(
                text=UserService.t(user_id, 'menu_history'),
                callback_data=pack_callback(version, 'go', 'history'),
            ),
            InlineKeyboardButton(
                text=UserService.t(user_id, 'menu_referrals'),
                callback_data=pack_callback(version, 'go', 'referrals'),
            ),
        )
    markup.add(
        InlineKeyboardButton(
            text=UserService.t(user_id, 'menu_change_role'),
            callback_data=pack_callback(version, 'go', 'role'),
        ),
        InlineKeyboardButton(
            text=UserService.t(user_id, 'menu_change_language'),
            callback_data=pack_callback(version, 'go', 'language'),
        ),
    )
    if UserService.is_admin(user_id):
        markup.add(
            InlineKeyboardButton(
                text=UserService.t(user_id, 'menu_admin'),
                callback_data=pack_callback(version, 'go', 'admin'),
            )
        )
    return markup


def community_rules_keyboard(user_id: int, version: int, *, accepted: bool = False) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=1)
    if not accepted:
        markup.add(InlineKeyboardButton(text=UserService.t(user_id, 'community_rules_accept_button'), callback_data=pack_callback(version, 'rules_accept', 'current')))
    markup.add(
        InlineKeyboardButton(text=UserService.t(user_id, 'community_rules_reopen_button'), callback_data=pack_callback(version, 'go', 'community_rules')),
        InlineKeyboardButton(text=UserService.t(user_id, 'support_button'), url=f'https://t.me/{settings.support_username.lstrip("@")}'),
    )
    markup.add(InlineKeyboardButton(text=UserService.t(user_id, 'back_to_menu'), callback_data=pack_callback(version, 'go', 'main_menu')))
    return markup


def legal_docs_keyboard(user_id: int, version: int, *, accepted: bool = False) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=1)
    if not accepted:
        markup.add(InlineKeyboardButton(text=UserService.t(user_id, 'legal_docs_accept_button'), callback_data=pack_callback(version, 'legal_accept', 'current')))
    markup.add(
        InlineKeyboardButton(text=UserService.t(user_id, 'community_rules_reopen_button'), callback_data=pack_callback(version, 'go', 'community_rules')),
        InlineKeyboardButton(text=UserService.t(user_id, 'support_button'), url=f'https://t.me/{settings.support_username.lstrip("@")}'),
    )
    markup.add(InlineKeyboardButton(text=UserService.t(user_id, 'back_to_menu'), callback_data=pack_callback(version, 'go', 'main_menu')))
    return markup

def section_keyboard(user_id: int, version: int) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton(
            text=UserService.t(user_id, 'back_to_menu'),
            callback_data=pack_callback(version, 'go', 'main_menu'),
        ),
        InlineKeyboardButton(
            text=UserService.t(user_id, 'refresh_screen'),
            callback_data=pack_callback(version, 'refresh', 'current'),
        ),
    )
    return markup



def tasks_keyboard(user_id: int, version: int, tasks) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=1)
    for task in tasks:
        title = str(task['title'] or f"#{int(task['id'])}")
        reward = int(task['reward_amount'])
        markup.add(
            InlineKeyboardButton(
                text=UserService.t(user_id, 'task_row', title=title[:28], reward=reward, internal_name=UserService.internal_currency_label(user_id)),
                callback_data=pack_callback(version, 'task', str(int(task['id']))),
            )
        )
    markup.add(
        InlineKeyboardButton(
            text=UserService.t(user_id, 'admin_queue_groups_button'),
            callback_data=pack_callback(version, 'go', 'admin_groups'),
        )
    )
    markup.add(
        InlineKeyboardButton(
            text=UserService.t(user_id, 'refresh_screen'),
            callback_data=pack_callback(version, 'go', 'tasks'),
        ),
        InlineKeyboardButton(
            text=UserService.t(user_id, 'back_to_menu'),
            callback_data=pack_callback(version, 'go', 'main_menu'),
        ),
    )
    return markup



def task_detail_keyboard(
    user_id: int,
    version: int,
    campaign_id: int,
    *,
    target_url: str,
    can_take: bool,
    can_submit: bool,
    submission_id: int | None,
) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton(
            text=UserService.t(user_id, 'open_task_target'),
            url=target_url,
        )
    )
    if can_take:
        markup.add(
            InlineKeyboardButton(
                text=UserService.t(user_id, 'take_task_button'),
                callback_data=pack_callback(version, 'take', str(campaign_id)),
            )
        )
    if can_submit and submission_id is not None:
        markup.add(
            InlineKeyboardButton(
                text=UserService.t(user_id, 'submit_task_button'),
                callback_data=pack_callback(version, 'submit_start', str(submission_id)),
            ),
            InlineKeyboardButton(
                text=UserService.t(user_id, 'proof_manual_button'),
                callback_data=pack_callback(version, 'proof_input_start', str(submission_id)),
            ),
        )
    markup.add(
        InlineKeyboardButton(
            text=UserService.t(user_id, 'back_to_tasks'),
            callback_data=pack_callback(version, 'go', 'tasks'),
        ),
        InlineKeyboardButton(
            text=UserService.t(user_id, 'back_to_menu'),
            callback_data=pack_callback(version, 'go', 'main_menu'),
        ),
    )
    return markup



def referrals_keyboard(user_id: int, version: int) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton(
            text=UserService.t(user_id, 'refresh_screen'),
            callback_data=pack_callback(version, 'go', 'referrals'),
        ),
        InlineKeyboardButton(
            text=UserService.t(user_id, 'back_to_menu'),
            callback_data=pack_callback(version, 'go', 'main_menu'),
        ),
    )
    return markup



def wallet_keyboard(user_id: int, version: int) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton(
            text=UserService.t(user_id, 'wallet_buy_sparks_button'),
            callback_data=pack_callback(version, 'go', 'topup_packages'),
        ),
        InlineKeyboardButton(
            text=UserService.t(user_id, 'menu_vip'),
            callback_data=pack_callback(version, 'go', 'vip'),
        ),
    )
    markup.add(
        InlineKeyboardButton(
            text=UserService.t(user_id, 'wallet_exchange_button'),
            callback_data=pack_callback(version, 'go', 'exchange'),
        ),
        InlineKeyboardButton(
            text=UserService.t(user_id, 'menu_history'),
            callback_data=pack_callback(version, 'go', 'history'),
        ),
    )
    if InvoiceMessageService.get(user_id):
        markup.add(
            InlineKeyboardButton(
                text=UserService.t(user_id, 'cancel_invoice_button'),
                callback_data=pack_callback(version, 'cancel_invoice', 'wallet'),
            )
        )
    markup.add(
        InlineKeyboardButton(
            text=UserService.t(user_id, 'admin_queue_groups_button'),
            callback_data=pack_callback(version, 'go', 'admin_groups'),
        )
    )
    markup.add(
        InlineKeyboardButton(
            text=UserService.t(user_id, 'refresh_screen'),
            callback_data=pack_callback(version, 'go', 'wallet'),
        ),
        InlineKeyboardButton(
            text=UserService.t(user_id, 'back_to_menu'),
            callback_data=pack_callback(version, 'go', 'main_menu'),
        ),
    )
    return markup

def history_keyboard(user_id: int, version: int) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton(
            text=UserService.t(user_id, 'menu_wallet'),
            callback_data=pack_callback(version, 'go', 'wallet'),
        ),
        InlineKeyboardButton(
            text=UserService.t(user_id, 'wallet_exchange_button'),
            callback_data=pack_callback(version, 'go', 'exchange'),
        ),
    )
    markup.add(
        InlineKeyboardButton(
            text=UserService.t(user_id, 'menu_referrals'),
            callback_data=pack_callback(version, 'go', 'referrals'),
        ),
        InlineKeyboardButton(
            text=UserService.t(user_id, 'refresh_screen'),
            callback_data=pack_callback(version, 'go', 'history'),
        ),
    )
    markup.add(
        InlineKeyboardButton(
            text=UserService.t(user_id, 'back_to_menu'),
            callback_data=pack_callback(version, 'go', 'main_menu'),
        )
    )
    return markup

def proof_wait_keyboard(user_id: int, version: int, submission_id: int) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton(
            text=UserService.t(user_id, 'open_task_submission'),
            callback_data=pack_callback(version, 'submission', str(submission_id)),
        ),
        InlineKeyboardButton(
            text=UserService.t(user_id, 'cancel_proof_input'),
            callback_data=pack_callback(version, 'cancel_input', str(submission_id)),
        ),
    )
    return markup



def campaigns_keyboard(user_id: int, version: int, campaigns) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton(
            text=UserService.t(user_id, 'broadcast_create_button'),
            callback_data=pack_callback(version, 'ad_new', 'user'),
        ),
        InlineKeyboardButton(
            text=UserService.t(user_id, 'campaign_create_button'),
            callback_data=pack_callback(version, 'camp_new', 'start'),
        )
    )
    markup.add(
        InlineKeyboardButton(
            text=UserService.t(user_id, 'client_dashboard_button'),
            callback_data=pack_callback(version, 'go', 'stats'),
        )
    )
    for campaign in campaigns[:12]:
        status_key = STATUS_TEXT_KEYS.get(str(campaign['status']), 'campaign_status_draft')
        status_text = UserService.t(user_id, status_key)
        title = str(campaign['title'] or f"#{int(campaign['id'])}")[:24]
        markup.add(
            InlineKeyboardButton(
                text=UserService.t(
                    user_id,
                    'campaign_row',
                    campaign_id=int(campaign['id']),
                    title=title,
                    status=status_text,
                ),
                callback_data=pack_callback(version, 'camp', str(int(campaign['id']))),
            )
        )
    markup.add(
        InlineKeyboardButton(
            text=UserService.t(user_id, 'admin_queue_groups_button'),
            callback_data=pack_callback(version, 'go', 'admin_groups'),
        )
    )
    markup.add(
        InlineKeyboardButton(
            text=UserService.t(user_id, 'refresh_screen'),
            callback_data=pack_callback(version, 'go', 'campaigns'),
        ),
        InlineKeyboardButton(
            text=UserService.t(user_id, 'back_to_menu'),
            callback_data=pack_callback(version, 'go', 'main_menu'),
        ),
    )
    return markup



def campaign_task_type_keyboard(user_id: int, version: int) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=1)
    for task_type in TASK_TYPES:
        markup.add(
            InlineKeyboardButton(
                text=UserService.t(user_id, TASK_TYPE_TEXT_KEYS.get(task_type, 'campaign_unknown_type')),
                callback_data=pack_callback(version, 'ctype', task_type),
            )
        )
    markup.add(
        InlineKeyboardButton(
            text=UserService.t(user_id, 'campaign_cancel_button'),
            callback_data=pack_callback(version, 'camp_cancel', 'create'),
        ),
        InlineKeyboardButton(
            text=UserService.t(user_id, 'back_to_campaigns'),
            callback_data=pack_callback(version, 'go', 'campaigns'),
        ),
    )
    return markup



def campaign_input_keyboard(user_id: int, version: int) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton(
            text=UserService.t(user_id, 'campaign_cancel_button'),
            callback_data=pack_callback(version, 'camp_cancel', 'input'),
        ),
        InlineKeyboardButton(
            text=UserService.t(user_id, 'back_to_campaigns'),
            callback_data=pack_callback(version, 'go', 'campaigns'),
        ),
    )
    return markup



def campaign_preview_keyboard(user_id: int, version: int) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton(
            text=UserService.t(user_id, 'campaign_save_draft_button'),
            callback_data=pack_callback(version, 'camp_save', 'draft'),
        ),
        InlineKeyboardButton(
            text=UserService.t(user_id, 'campaign_launch_now_button'),
            callback_data=pack_callback(version, 'camp_save', 'launch'),
        ),
    )
    markup.add(
        InlineKeyboardButton(
            text=UserService.t(user_id, 'campaign_cancel_button'),
            callback_data=pack_callback(version, 'camp_cancel', 'preview'),
        ),
        InlineKeyboardButton(
            text=UserService.t(user_id, 'back_to_campaigns'),
            callback_data=pack_callback(version, 'go', 'campaigns'),
        ),
    )
    return markup



def campaign_card_keyboard(user_id: int, version: int, campaign) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=2)
    status = str(campaign['status'])
    campaign_id = int(campaign['id'])
    if status == 'draft':
        markup.add(
            InlineKeyboardButton(
                text=UserService.t(user_id, 'campaign_launch_button'),
                callback_data=pack_callback(version, 'camp_status', f'{campaign_id},active'),
            )
        )
    elif status == 'active':
        markup.add(
            InlineKeyboardButton(
                text=UserService.t(user_id, 'campaign_pause_button'),
                callback_data=pack_callback(version, 'camp_status', f'{campaign_id},paused'),
            )
        )
    elif status == 'paused':
        markup.add(
            InlineKeyboardButton(
                text=UserService.t(user_id, 'campaign_resume_button'),
                callback_data=pack_callback(version, 'camp_status', f'{campaign_id},active'),
            )
        )
    options = boost_options(campaign)
    if 'recommended' in options:
        markup.add(
            InlineKeyboardButton(
                text=UserService.t(user_id, 'campaign_boost_recommended_button'),
                callback_data=pack_callback(version, 'camp_boost', f'{campaign_id},recommended'),
            )
        )
    boost_pair = []
    if 'fast' in options:
        boost_pair.append(
            InlineKeyboardButton(
                text=UserService.t(user_id, 'campaign_boost_fast_button'),
                callback_data=pack_callback(version, 'camp_boost', f'{campaign_id},fast'),
            )
        )
    if 'priority' in options:
        boost_pair.append(
            InlineKeyboardButton(
                text=UserService.t(user_id, 'campaign_boost_priority_button'),
                callback_data=pack_callback(version, 'camp_boost', f'{campaign_id},priority'),
            )
        )
    if boost_pair:
        markup.add(*boost_pair)
    markup.add(
        InlineKeyboardButton(
            text=UserService.t(user_id, 'back_to_campaigns'),
            callback_data=pack_callback(version, 'go', 'campaigns'),
        ),
        InlineKeyboardButton(
            text=UserService.t(user_id, 'client_dashboard_button'),
            callback_data=pack_callback(version, 'go', 'stats'),
        ),
    )
    return markup



def stats_keyboard(user_id: int, version: int) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton(
            text=UserService.t(user_id, 'menu_campaigns'),
            callback_data=pack_callback(version, 'go', 'campaigns'),
        ),
        InlineKeyboardButton(
            text=UserService.t(user_id, 'refresh_screen'),
            callback_data=pack_callback(version, 'go', 'stats'),
        ),
    )
    markup.add(
        InlineKeyboardButton(
            text=UserService.t(user_id, 'menu_vip'),
            callback_data=pack_callback(version, 'go', 'vip'),
        ),
        InlineKeyboardButton(
            text=UserService.t(user_id, 'back_to_menu'),
            callback_data=pack_callback(version, 'go', 'main_menu'),
        ),
    )
    return markup



def vip_keyboard(user_id: int, version: int) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=1)
    for plan_code, plan in VIP_PLANS.items():
        markup.add(
            InlineKeyboardButton(
                text=f"{UserService.t(user_id, str(plan['title_key']))} · {plan['price']} {UserService.internal_currency_label(user_id)}",
                callback_data=pack_callback(version, 'vip_buy', plan_code),
            )
        )
    for _, offer in VIP_STARS_PLANS.items():
        markup.add(
            InlineKeyboardButton(
                text=f"{offer.title} · {offer.stars} ⭐",
                callback_data=pack_callback(version, 'vip_stars', offer.code),
            )
        )
    if InvoiceMessageService.get(user_id):
        markup.add(
            InlineKeyboardButton(
                text=UserService.t(user_id, 'cancel_invoice_button'),
                callback_data=pack_callback(version, 'cancel_invoice', 'vip'),
            )
        )
    markup.add(
        InlineKeyboardButton(
            text=UserService.t(user_id, 'menu_wallet'),
            callback_data=pack_callback(version, 'go', 'wallet'),
        )
    )
    return markup

def rewards_keyboard(user_id: int, version: int) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=1)
    for item_code, item in RewardService.get_items().items():
        markup.add(
            InlineKeyboardButton(
                text=f"{UserService.t(user_id, item['title_key'])} · {item['price']} {UserService.internal_currency_label(user_id)}",
                callback_data=pack_callback(version, 'reward_buy', item_code),
            )
        )
    for months, offer in RedemptionService.premium_offers().items():
        markup.add(
            InlineKeyboardButton(
                text=f"{offer['label']} · {offer['sparks_cost']} {UserService.internal_currency_label(user_id)}",
                callback_data=pack_callback(version, 'redeem_premium', str(months)),
            )
        )
    gifts = RedemptionService.list_gifts(limit=20)
    for idx, gift in enumerate(gifts):
        markup.add(
            InlineKeyboardButton(
                text=f"{gift['emoji']} Telegram подарок · {gift['sparks_cost']} {UserService.internal_currency_label(user_id)} · {gift['star_count']}⭐" if UserService.get_language(user_id) == 'ru' else f"{gift['emoji']} Telegram gift · {gift['sparks_cost']} {UserService.internal_currency_label(user_id)} · {gift['star_count']}⭐",
                callback_data=pack_callback(version, 'redeem_gift', str(idx)),
            )
        )
    markup.add(
        InlineKeyboardButton(
            text=UserService.t(user_id, 'menu_wallet'),
            callback_data=pack_callback(version, 'go', 'wallet'),
        ),
        InlineKeyboardButton(
            text=UserService.t(user_id, 'menu_history'),
            callback_data=pack_callback(version, 'go', 'history'),
        ),
    )
    return markup

def topup_custom_keyboard(user_id: int, version: int) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton(
            text=UserService.t(user_id, 'cancel_input_button'),
            callback_data=pack_callback(version, 'cancel_input', 'topup_custom'),
        ),
        InlineKeyboardButton(
            text=UserService.t(user_id, 'wallet_buy_sparks_button'),
            callback_data=pack_callback(version, 'go', 'topup_packages'),
        ),
        InlineKeyboardButton(
            text=UserService.t(user_id, 'menu_wallet'),
            callback_data=pack_callback(version, 'go', 'wallet'),
        ),
    )
    return markup

def topup_packages_keyboard(user_id: int, version: int) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=1)
    for stars in PACK_STAR_LEVELS:
        pack_code = f'spk_{stars}'
        pack = SPARKS_PACKS[pack_code]
        markup.add(
            InlineKeyboardButton(
                text=f"{pack.stars} ⭐ → {pack.sparks} {UserService.internal_currency_label(user_id)}",
                callback_data=pack_callback(version, 'topup_stars', pack_code),
            )
        )
    markup.add(
        InlineKeyboardButton(
            text=UserService.t(user_id, 'wallet_custom_topup_button'),
            callback_data=pack_callback(version, 'topup_custom', 'start'),
        )
    )
    if InvoiceMessageService.get(user_id):
        markup.add(
            InlineKeyboardButton(
                text=UserService.t(user_id, 'cancel_invoice_button'),
                callback_data=pack_callback(version, 'cancel_invoice', 'topup_packages'),
            )
        )
    markup.add(
        InlineKeyboardButton(
            text=UserService.t(user_id, 'menu_wallet'),
            callback_data=pack_callback(version, 'go', 'wallet'),
        )
    )
    return markup


def exchange_keyboard(user_id: int, version: int) -> InlineKeyboardMarkup:
    return rewards_keyboard(user_id, version)


def admin_bot_chats_keyboard(user_id: int, version: int, chats, *, page: int, total_pages: int, issues_mode: bool = False) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=1)
    for row in chats:
        title = str(row['title'] or SubscriptionService.display_name(str(row['chat_ref'] or row['chat_id'])))[:40]
        link = BotChatService.chat_link(row)
        label = f"{title}"
        if issues_mode:
            label = '⚠️ ' + label
        if link:
            markup.add(InlineKeyboardButton(text=label, url=link))
        else:
            markup.add(InlineKeyboardButton(text=label, callback_data=pack_callback(version, 'boostore_order_start', str(row['external_service_id']))))
    target_prefix = 'admin_bot_rights' if issues_mode else 'admin_bot_chats'
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton(text='◀️', callback_data=pack_callback(version, 'go', f'{target_prefix}:{page-1}')))
    nav.append(InlineKeyboardButton(text=f'{page}/{max(total_pages,1)}', callback_data=pack_callback(version, 'boostore_order_start', str(row['external_service_id']))))
    if page < total_pages:
        nav.append(InlineKeyboardButton(text='▶️', callback_data=pack_callback(version, 'go', f'{target_prefix}:{page+1}')))
    markup.row(*nav)
    if issues_mode:
        markup.add(InlineKeyboardButton(text=UserService.t(user_id, 'admin_bot_chats_button'), callback_data=pack_callback(version, 'go', 'admin_bot_chats:1')))
    else:
        markup.add(InlineKeyboardButton(text=UserService.t(user_id, 'admin_bot_rights_button'), callback_data=pack_callback(version, 'go', 'admin_bot_rights:1')))
    markup.add(InlineKeyboardButton(text=UserService.t(user_id, 'admin_bot_live_audit_button'), callback_data=pack_callback(version, 'admin_live_audit', '25')))
    markup.add(InlineKeyboardButton(text=UserService.t(user_id, 'menu_admin'), callback_data=pack_callback(version, 'go', 'admin')))
    return markup

def admin_users_keyboard(user_id: int, version: int, users, *, page: int, total_pages: int) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=1)
    for row in users:
        username = str(row['username'] or '').strip()
        title = f"@{username}" if username else f"ID {int(row['user_id'])}"
        label = f"{title}"
        markup.add(InlineKeyboardButton(text=label, url=f"tg://user?id={int(row['user_id'])}"))
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton(text='◀️', callback_data=pack_callback(version, 'go', f'admin_users:{page-1}')))
    nav.append(InlineKeyboardButton(text=f'{page}/{max(total_pages,1)}', callback_data=pack_callback(version, 'boostore_order_start', str(row['external_service_id']))))
    if page < total_pages:
        nav.append(InlineKeyboardButton(text='▶️', callback_data=pack_callback(version, 'go', f'admin_users:{page+1}')))
    markup.row(*nav)
    markup.add(InlineKeyboardButton(text=UserService.t(user_id, 'menu_admin'), callback_data=pack_callback(version, 'go', 'admin')))
    return markup


def broadcast_input_keyboard(user_id: int, version: int, *, is_admin: bool = False) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton(
            text=UserService.t(user_id, 'back_to_menu'),
            callback_data=pack_callback(version, 'go', 'main_menu'),
        ),
    )
    return markup


def broadcast_schedule_keyboard(user_id: int, version: int) -> InlineKeyboardMarkup:
    draft = AdBroadcastService.get_draft(user_id)
    markup = InlineKeyboardMarkup(row_width=2)
    repeats = int(draft.get('repeat_count') or 0) if draft else 0
    if repeats <= 0:
        for repeat_count, label in AdBroadcastService.list_repeat_options().items():
            markup.add(
                InlineKeyboardButton(
                    text=str(label),
                    callback_data=pack_callback(version, 'ad_sched', f'repeat:{int(repeat_count)}'),
                )
            )
    else:
        for hours in AdBroadcastService.list_interval_options(repeats):
            markup.add(
                InlineKeyboardButton(
                    text=AdBroadcastService.interval_label(int(hours)),
                    callback_data=pack_callback(version, 'ad_sched', f'freq:{int(hours)}'),
                )
            )
    markup.add(
        InlineKeyboardButton(
            text=UserService.t(user_id, 'cancel_proof_input'),
            callback_data=pack_callback(version, 'cancel_input', 'broadcast'),
        ),
        InlineKeyboardButton(
            text=UserService.t(user_id, 'back_to_menu'),
            callback_data=pack_callback(version, 'go', 'main_menu'),
        ),
    )
    return markup


def broadcast_preview_keyboard(user_id: int, version: int, *, is_admin: bool = False) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=1)
    action = 'ad_send' if is_admin else 'ad_pay'
    text_key = 'broadcast_send_now_button' if is_admin else 'broadcast_pay_button'
    markup.add(
        InlineKeyboardButton(
            text=UserService.t(user_id, text_key),
            callback_data=pack_callback(version, action, 'confirm'),
        )
    )
    markup.add(
        InlineKeyboardButton(
            text=UserService.t(user_id, 'refresh_screen'),
            callback_data=pack_callback(version, 'go', 'broadcast_preview'),
        ),
        InlineKeyboardButton(
            text=UserService.t(user_id, 'back_to_menu'),
            callback_data=pack_callback(version, 'go', 'main_menu'),
        ),
    )
    return markup



def blocked_keyboard(user_id: int, version: int) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton(
            text=UserService.t(user_id, 'refresh_screen'),
            callback_data=pack_callback(version, 'refresh', 'current'),
        )
    )
    return markup


def admin_home_keyboard(user_id: int, version: int) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton(
            text=UserService.t(user_id, 'admin_queue_button'),
            callback_data=pack_callback(version, 'go', 'admin_queue'),
        ),
        InlineKeyboardButton(
            text=UserService.t(user_id, 'admin_queue_high_button'),
            callback_data=pack_callback(version, 'go', 'admin_queue:high'),
        ),
        InlineKeyboardButton(
            text=UserService.t(user_id, 'admin_queue_groups_button'),
            callback_data=pack_callback(version, 'go', 'admin_groups'),
        ),
        InlineKeyboardButton(
            text=UserService.t(user_id, 'admin_patterns_button'),
            callback_data=pack_callback(version, 'go', 'admin_patterns'),
        ),
        InlineKeyboardButton(
            text=UserService.t(user_id, 'admin_bot_chats_button'),
            callback_data=pack_callback(version, 'go', 'admin_bot_chats:1'),
        ),
        InlineKeyboardButton(
            text=UserService.t(user_id, 'admin_bot_rights_button'),
            callback_data=pack_callback(version, 'go', 'admin_bot_rights:1'),
        ),
        InlineKeyboardButton(
            text=UserService.t(user_id, 'admin_users_button'),
            callback_data=pack_callback(version, 'go', 'admin_users:1'),
        ),
        InlineKeyboardButton(
            text=UserService.t(user_id, 'admin_logs_button'),
            callback_data=pack_callback(version, 'go', 'admin_logs'),
        ),
    )
    markup.add(
        InlineKeyboardButton(text=UserService.t(user_id, 'admin_engagement_obligations_button'), callback_data=pack_callback(version, 'go', 'admin_engagement_obligations')),
    )
    markup.add(
        InlineKeyboardButton(
            text=UserService.t(user_id, 'admin_broadcast_button'),
            callback_data=pack_callback(version, 'ad_new', 'admin'),
        ),
        InlineKeyboardButton(
            text=UserService.t(user_id, 'admin_rules_button'),
            callback_data=pack_callback(version, 'go', 'community_rules'),
        ),
    )
    if UserService.is_owner(user_id):
        markup.add(
            InlineKeyboardButton(
                text=UserService.t(user_id, 'owner_analytics_button'),
                callback_data=pack_callback(version, 'go', 'owner_analytics'),
            ),
            InlineKeyboardButton(
                text=UserService.t(user_id, 'owner_release_button'),
                callback_data=pack_callback(version, 'go', 'owner_release'),
            ),
        )
        markup.add(
            InlineKeyboardButton(text=UserService.t(user_id, 'owner_provider_button'), callback_data=pack_callback(version, 'go', 'owner_provider')),
            InlineKeyboardButton(text=UserService.t(user_id, 'admin_required_chats_button'), callback_data=pack_callback(version, 'go', 'admin_required_chats')),
        )
    markup.add(
        InlineKeyboardButton(
            text=UserService.t(user_id, 'back_to_menu'),
            callback_data=pack_callback(version, 'go', 'main_menu'),
        )
    )
    return markup



def owner_analytics_keyboard(user_id: int, version: int) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton(
            text=UserService.t(user_id, 'refresh_screen'),
            callback_data=pack_callback(version, 'go', 'owner_analytics'),
        ),
        InlineKeyboardButton(
            text=UserService.t(user_id, 'owner_release_button'),
            callback_data=pack_callback(version, 'go', 'owner_release'),
        ),
    )
    markup.add(
        InlineKeyboardButton(
            text=UserService.t(user_id, 'menu_admin'),
            callback_data=pack_callback(version, 'go', 'admin'),
        ),
    )
    return markup



def owner_release_keyboard(user_id: int, version: int) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton(
            text=UserService.t(user_id, 'refresh_screen'),
            callback_data=pack_callback(version, 'go', 'owner_release'),
        ),
        InlineKeyboardButton(
            text=UserService.t(user_id, 'owner_analytics_button'),
            callback_data=pack_callback(version, 'go', 'owner_analytics'),
        ),
    )
    markup.add(
        InlineKeyboardButton(
            text=UserService.t(user_id, 'menu_admin'),
            callback_data=pack_callback(version, 'go', 'admin'),
        ),
    )
    return markup



def admin_groups_keyboard(user_id: int, version: int) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton(text=UserService.t(user_id, 'admin_queue_button'), callback_data=pack_callback(version, 'go', 'admin_queue')),
        InlineKeyboardButton(text=UserService.t(user_id, 'admin_queue_high_button'), callback_data=pack_callback(version, 'go', 'admin_queue:high')),
    )
    markup.add(
        InlineKeyboardButton(text=UserService.t(user_id, 'admin_patterns_button'), callback_data=pack_callback(version, 'go', 'admin_patterns')),
        InlineKeyboardButton(text=UserService.t(user_id, 'refresh_screen'), callback_data=pack_callback(version, 'go', 'admin_groups')),
    )
    markup.add(
        InlineKeyboardButton(text=UserService.t(user_id, 'menu_admin'), callback_data=pack_callback(version, 'go', 'admin')),
    )
    return markup


def admin_patterns_keyboard(user_id: int, version: int) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton(text=UserService.t(user_id, 'admin_queue_groups_button'), callback_data=pack_callback(version, 'go', 'admin_groups')),
        InlineKeyboardButton(text=UserService.t(user_id, 'admin_queue_high_button'), callback_data=pack_callback(version, 'go', 'admin_queue:high')),
    )
    markup.add(
        InlineKeyboardButton(text=UserService.t(user_id, 'admin_bot_rights_button'), callback_data=pack_callback(version, 'go', 'admin_bot_rights:1')),
        InlineKeyboardButton(text=UserService.t(user_id, 'admin_bot_live_audit_button'), callback_data=pack_callback(version, 'admin_live_audit', '25')),
    )
    markup.add(
        InlineKeyboardButton(text=UserService.t(user_id, 'refresh_screen'), callback_data=pack_callback(version, 'go', 'admin_patterns')),
        InlineKeyboardButton(text=UserService.t(user_id, 'menu_admin'), callback_data=pack_callback(version, 'go', 'admin')),
    )
    return markup


def admin_queue_keyboard(user_id: int, version: int, submissions, *, filter_code: str = 'all') -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton(text=UserService.t(user_id, 'admin_queue_filter_all'), callback_data=pack_callback(version, 'go', 'admin_queue')),
        InlineKeyboardButton(text=UserService.t(user_id, 'admin_queue_filter_high'), callback_data=pack_callback(version, 'go', 'admin_queue:high')),
        InlineKeyboardButton(text=UserService.t(user_id, 'admin_queue_filter_clean'), callback_data=pack_callback(version, 'go', 'admin_queue:clean')),
        InlineKeyboardButton(text=UserService.t(user_id, 'admin_queue_filter_old'), callback_data=pack_callback(version, 'go', 'admin_queue:old')),
    )
    for submission in submissions[:10]:
        title = str(submission['campaign_title'] or f"#{int(submission['campaign_id'])}")
        performer = str(submission['username'] or '').strip()
        display = f"@{performer}" if performer else f"ID {int(submission['performer_user_id'])}"
        priority = int(submission['priority_score'] or 0) if 'priority_score' in submission.keys() else int(submission['risk_score'] or 0)
        text = UserService.t(
            user_id,
            'admin_queue_row',
            submission_id=int(submission['id']),
            title=title[:18],
            performer=display[:18],
            risk=int(submission['risk_score']),
            priority=priority,
        )
        markup.add(
            InlineKeyboardButton(
                text=text,
                callback_data=pack_callback(version, 'admin_submission', str(int(submission['id']))),
            )
        )
    if filter_code == 'clean':
        markup.add(
            InlineKeyboardButton(
                text=UserService.t(user_id, 'admin_bulk_approve_clean_button'),
                callback_data=pack_callback(version, 'admin_bulk_clean', '10'),
            )
        )
    if filter_code == 'high':
        markup.add(
            InlineKeyboardButton(
                text=UserService.t(user_id, 'admin_bulk_block_high_button'),
                callback_data=pack_callback(version, 'admin_bulk_block_high', '10'),
            )
        )
    markup.add(
        InlineKeyboardButton(
            text=UserService.t(user_id, 'admin_queue_groups_button'),
            callback_data=pack_callback(version, 'go', 'admin_groups'),
        )
    )
    markup.add(
        InlineKeyboardButton(
            text=UserService.t(user_id, 'refresh_screen'),
            callback_data=pack_callback(version, 'go', 'admin_queue' if filter_code == 'all' else f'admin_queue:{filter_code}'),
        ),
        InlineKeyboardButton(
            text=UserService.t(user_id, 'menu_admin'),
            callback_data=pack_callback(version, 'go', 'admin'),
        ),
    )
    return markup



def admin_submission_keyboard(user_id: int, version: int, card) -> InlineKeyboardMarkup:
    submission = card['submission']
    performer_user_id = int(submission['performer_user_id'])
    markup = InlineKeyboardMarkup(row_width=2)
    if str(submission['status']) == 'manual_review':
        markup.add(
            InlineKeyboardButton(
                text=UserService.t(user_id, 'admin_approve_button'),
                callback_data=pack_callback(version, 'admin_approve', str(int(submission['id']))),
            ),
            InlineKeyboardButton(
                text=UserService.t(user_id, 'admin_reject_button'),
                callback_data=pack_callback(version, 'admin_reject_start', str(int(submission['id']))),
            ),
        )
    if str(submission['status']) == 'manual_review':
        markup.add(
            InlineKeyboardButton(
                text=UserService.t(user_id, 'admin_tpl_approve_clean_button'),
                callback_data=pack_callback(version, 'admin_tpl_approve', f"{int(submission['id'])}:approve_clean"),
            )
        )
        markup.add(
            InlineKeyboardButton(
                text=UserService.t(user_id, 'admin_tpl_reject_target_button'),
                callback_data=pack_callback(version, 'admin_tpl_reject', f"{int(submission['id'])}:reject_wrong_target"),
            ),
            InlineKeyboardButton(
                text=UserService.t(user_id, 'admin_tpl_reject_proof_button'),
                callback_data=pack_callback(version, 'admin_tpl_reject', f"{int(submission['id'])}:reject_no_proof"),
            ),
        )
        markup.add(
            InlineKeyboardButton(
                text=UserService.t(user_id, 'admin_tpl_reject_spam_button'),
                callback_data=pack_callback(version, 'admin_tpl_reject', f"{int(submission['id'])}:reject_spam"),
            )
        )
    markup.add(
        InlineKeyboardButton(
            text=UserService.t(user_id, 'admin_note_button'),
            callback_data=pack_callback(version, 'admin_note_start', f"{int(submission['id'])}:{performer_user_id}"),
        )
    )
    block_action = 'admin_unblock' if str(submission['user_status']) == 'blocked' else 'admin_block'
    block_text = 'admin_unblock_button' if str(submission['user_status']) == 'blocked' else 'admin_block_button'
    markup.add(
        InlineKeyboardButton(
            text=UserService.t(user_id, block_text),
            callback_data=pack_callback(version, block_action, str(performer_user_id)),
        ),
        InlineKeyboardButton(
            text=UserService.t(user_id, 'admin_adjust_risk_button'),
            callback_data=pack_callback(version, 'admin_adjust_risk_start', str(performer_user_id)),
        ),
    )
    markup.add(
        InlineKeyboardButton(
            text=UserService.t(user_id, 'admin_adjust_balance_button'),
            callback_data=pack_callback(version, 'admin_adjust_balance_start', str(performer_user_id)),
        )
    )
    markup.add(
        InlineKeyboardButton(
            text=UserService.t(user_id, 'admin_queue_button'),
            callback_data=pack_callback(version, 'go', 'admin_queue'),
        ),
        InlineKeyboardButton(
            text=UserService.t(user_id, 'menu_admin'),
            callback_data=pack_callback(version, 'go', 'admin'),
        ),
    )
    return markup


def admin_required_chats_keyboard(user_id: int, version: int, chats) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=1)
    for row in chats[:10]:
        chat_ref = str(row['chat_ref'])
        remove_text = UserService.t(user_id, 'admin_required_chat_remove_button', name=SubscriptionService.display_name(chat_ref))
        markup.add(
            InlineKeyboardButton(
                text=remove_text,
                callback_data=pack_callback(version, 'admin_required_chats_remove', str(int(row['id']))),
            )
        )
    markup.add(
        InlineKeyboardButton(
            text=UserService.t(user_id, 'admin_required_chat_add_button'),
            callback_data=pack_callback(version, 'admin_required_chats_add_start', 'new'),
        )
    )
    markup.add(
        InlineKeyboardButton(
            text=UserService.t(user_id, 'admin_queue_groups_button'),
            callback_data=pack_callback(version, 'go', 'admin_groups'),
        )
    )
    markup.add(
        InlineKeyboardButton(
            text=UserService.t(user_id, 'refresh_screen'),
            callback_data=pack_callback(version, 'go', 'admin_required_chats'),
        ),
        InlineKeyboardButton(
            text=UserService.t(user_id, 'menu_admin'),
            callback_data=pack_callback(version, 'go', 'admin'),
        ),
    )
    return markup


def admin_logs_keyboard(user_id: int, version: int) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton(
            text=UserService.t(user_id, 'admin_queue_groups_button'),
            callback_data=pack_callback(version, 'go', 'admin_groups'),
        )
    )
    markup.add(
        InlineKeyboardButton(
            text=UserService.t(user_id, 'refresh_screen'),
            callback_data=pack_callback(version, 'go', 'admin_logs'),
        ),
        InlineKeyboardButton(
            text=UserService.t(user_id, 'menu_admin'),
            callback_data=pack_callback(version, 'go', 'admin'),
        ),
    )
    return markup


def admin_input_keyboard(user_id: int, version: int, *, back_target: str) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=1)
    if back_target.startswith('admin_submission:'):
        target_id = back_target.split(':', 1)[1]
        callback_data = pack_callback(version, 'admin_submission', target_id)
    else:
        callback_data = pack_callback(version, 'go', back_target)
    markup.add(
        InlineKeyboardButton(
            text=UserService.t(user_id, 'cancel_proof_input'),
            callback_data=callback_data,
        )
    )
    return markup



def _mini_app_button(user_id: int):
    if not settings.mini_app_url:
        return None
    if WebAppInfo is not None:
        return InlineKeyboardButton(text=UserService.t(user_id, 'mini_app_button'), web_app=WebAppInfo(url=settings.mini_app_url))
    return InlineKeyboardButton(text=UserService.t(user_id, 'mini_app_button'), url=settings.mini_app_url)


def smart_hub_keyboard(user_id: int, version: int, role: str | None = None) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=2)
    mini = _mini_app_button(user_id)
    if mini:
        markup.add(mini)
    if role == ROLE_CLIENT:
        markup.add(
            InlineKeyboardButton(text=UserService.t(user_id, 'campaign_create_button'), callback_data=pack_callback(version, 'camp_new', 'start')),
            InlineKeyboardButton(text=UserService.t(user_id, 'client_dashboard_button'), callback_data=pack_callback(version, 'go', 'stats')),
        )
    else:
        markup.add(
            InlineKeyboardButton(text=UserService.t(user_id, 'menu_tasks'), callback_data=pack_callback(version, 'go', 'tasks')),
            InlineKeyboardButton(text=UserService.t(user_id, 'menu_profile'), callback_data=pack_callback(version, 'go', 'profile')),
        )
    markup.add(
        InlineKeyboardButton(text=UserService.t(user_id, 'marketplace_button'), callback_data=pack_callback(version, 'go', 'marketplace')),
    )
    markup.add(
        InlineKeyboardButton(text=UserService.t(user_id, 'client_dashboard_button'), callback_data=pack_callback(version, 'go', 'stats')),
        InlineKeyboardButton(text=UserService.t(user_id, 'menu_referrals'), callback_data=pack_callback(version, 'go', 'referrals')),
    )
    if UserService.is_admin(user_id):
        markup.add(InlineKeyboardButton(text=UserService.t(user_id, 'menu_admin'), callback_data=pack_callback(version, 'go', 'admin')))
    markup.add(
        InlineKeyboardButton(text=UserService.t(user_id, 'community_rules_button'), callback_data=pack_callback(version, 'go', 'community_rules')),
        InlineKeyboardButton(text=UserService.t(user_id, 'refresh_screen'), callback_data=pack_callback(version, 'go', 'smart_hub')),
    )
    return markup


def engagement_growth_keyboard(user_id: int, version: int) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton(text=UserService.t(user_id, 'engagement_mode_select_button'), callback_data=pack_callback(version, 'go', 'engagement_mode')),
        InlineKeyboardButton(text=UserService.t(user_id, 'engagement_obligations_button'), callback_data=pack_callback(version, 'go', 'engagement_obligations')),
    )
    for product in EngagementGrowthService.products():
        markup.add(
            InlineKeyboardButton(
                text=UserService.t(user_id, product.title_key),
                callback_data=pack_callback(version, 'ctype', product.task_type),
            )
        )
        preset_buttons = [
            InlineKeyboardButton(
                text=UserService.t(user_id, preset.title_key),
                callback_data=pack_callback(version, 'egp', preset.code),
            )
            for preset in EngagementGrowthService.presets_for(product.code)
        ]
        if preset_buttons:
            markup.row(*preset_buttons)
    markup.add(
        InlineKeyboardButton(text=UserService.t(user_id, 'campaign_create_button'), callback_data=pack_callback(version, 'camp_new', 'start')),
        InlineKeyboardButton(text=UserService.t(user_id, 'marketplace_button'), callback_data=pack_callback(version, 'go', 'marketplace')),
    )
    markup.add(
        InlineKeyboardButton(text=UserService.t(user_id, 'smart_hub_button'), callback_data=pack_callback(version, 'go', 'smart_hub')),
        InlineKeyboardButton(text=UserService.t(user_id, 'community_rules_button'), callback_data=pack_callback(version, 'go', 'community_rules')),
        InlineKeyboardButton(text=UserService.t(user_id, 'back_to_menu'), callback_data=pack_callback(version, 'go', 'main_menu')),
    )
    return markup


def engagement_mode_keyboard(user_id: int, version: int) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton(text=UserService.t(user_id, 'engagement_mode_standard_button'), callback_data=pack_callback(version, 'eng_mode', 'standard')),
        InlineKeyboardButton(text=UserService.t(user_id, 'engagement_mode_pro_button'), callback_data=pack_callback(version, 'eng_pro_pay', '30d')),
    )
    markup.add(
        InlineKeyboardButton(text=UserService.t(user_id, 'engagement_growth_button'), callback_data=pack_callback(version, 'go', 'engagement_growth')),
        InlineKeyboardButton(text=UserService.t(user_id, 'back_to_menu'), callback_data=pack_callback(version, 'go', 'main_menu')),
    )
    return markup


def engagement_obligations_keyboard(user_id: int, version: int) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton(text=UserService.t(user_id, 'engagement_obligations_do_tasks_button'), callback_data=pack_callback(version, 'go', 'tasks')),
        InlineKeyboardButton(text=UserService.t(user_id, 'refresh_screen'), callback_data=pack_callback(version, 'go', 'engagement_obligations')),
    )
    markup.add(
        InlineKeyboardButton(text=UserService.t(user_id, 'engagement_growth_button'), callback_data=pack_callback(version, 'go', 'engagement_growth')),
        InlineKeyboardButton(text=UserService.t(user_id, 'engagement_mode_select_button'), callback_data=pack_callback(version, 'go', 'engagement_mode')),
        InlineKeyboardButton(text=UserService.t(user_id, 'back_to_menu'), callback_data=pack_callback(version, 'go', 'main_menu')),
    )
    return markup


def admin_engagement_obligations_keyboard(user_id: int, version: int, items=None) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=2)
    for item in list(items or [])[:5]:
        oid = int(item.get('id') or 0)
        name = str(item.get('username') or item.get('first_name') or item.get('user_id') or '')[:18]
        if oid:
            markup.add(InlineKeyboardButton(text=f'⏳ +24ч #{oid} {name}', callback_data=pack_callback(version, 'std_extend', str(oid))))
            markup.add(InlineKeyboardButton(text=f'✅ Простить #{oid}', callback_data=pack_callback(version, 'std_forgive', str(oid))), InlineKeyboardButton(text=f'⚠️ Напомнить #{oid}', callback_data=pack_callback(version, 'std_warn', str(oid))))
            markup.add(InlineKeyboardButton(text=f'⭐ PRO 30д · {name}', callback_data=pack_callback(version, 'std_pro', str(item.get('user_id') or 0))))
    markup.add(
        InlineKeyboardButton(text=UserService.t(user_id, 'refresh_screen'), callback_data=pack_callback(version, 'go', 'admin_engagement_obligations')),
        InlineKeyboardButton(text=UserService.t(user_id, 'menu_tasks'), callback_data=pack_callback(version, 'go', 'tasks')),
    )
    markup.add(
        InlineKeyboardButton(text=UserService.t(user_id, 'menu_admin'), callback_data=pack_callback(version, 'go', 'admin')),
        InlineKeyboardButton(text=UserService.t(user_id, 'back_to_menu'), callback_data=pack_callback(version, 'go', 'main_menu')),
    )
    return markup


def marketplace_keyboard(user_id: int, version: int, services=None) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=1)
    for row in list(services or [])[:10]:
        label = f"{str(row['name'])[:42]} · {int(row['min_quantity'] or 0)}-{int(row['max_quantity'] or 0)}"
        markup.add(InlineKeyboardButton(text=label, callback_data=pack_callback(version, 'boostore_order_start', str(row['external_service_id']))))
    markup.add(
        InlineKeyboardButton(text=UserService.t(user_id, 'smart_hub_button'), callback_data=pack_callback(version, 'go', 'smart_hub')),
        InlineKeyboardButton(text=UserService.t(user_id, 'back_to_menu'), callback_data=pack_callback(version, 'go', 'main_menu')),
    )
    return markup


def owner_provider_keyboard(user_id: int, version: int, services=None) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton(text=UserService.t(user_id, 'boostore_check_button'), callback_data=pack_callback(version, 'boostore_check', 'balance')),
        InlineKeyboardButton(text=UserService.t(user_id, 'boostore_sync_button'), callback_data=pack_callback(version, 'boostore_sync', 'services')),
    )
    for row in list(services or [])[:12]:
        enabled = '✅' if int(row['is_enabled'] or 0) else '▫️'
        label = f"{enabled} {str(row['name'])[:44]}"
        markup.add(InlineKeyboardButton(text=label, callback_data=pack_callback(version, 'boostore_toggle', str(row['external_service_id']))))
    markup.add(
        InlineKeyboardButton(text=UserService.t(user_id, 'owner_analytics_button'), callback_data=pack_callback(version, 'go', 'owner_analytics')),
        InlineKeyboardButton(text=UserService.t(user_id, 'menu_admin'), callback_data=pack_callback(version, 'go', 'admin')),
    )
    return markup
