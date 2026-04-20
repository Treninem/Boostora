from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.config import settings
from app.services.client_campaigns import TASK_TYPES
from app.services.payments import SPARKS_PACKS, VIP_STARS_PLANS
from app.services.redemptions import RedemptionService
from app.services.rewards import RewardService
from app.services.subscriptions import SubscriptionService
from app.services.users import UserService
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
        )
    markup.add(
        InlineKeyboardButton(
            text=UserService.t(user_id, 'menu_vip'),
            callback_data=pack_callback(version, 'go', 'vip'),
        ),
        InlineKeyboardButton(
            text=UserService.t(user_id, 'menu_rewards'),
            callback_data=pack_callback(version, 'go', 'rewards'),
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
            )
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



def wallet_keyboard(user_id: int, version: int) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=2)
    role = UserService.get_role(user_id)
    secondary_section = 'tasks' if role == ROLE_PERFORMER else 'campaigns'
    secondary_label = 'menu_tasks' if role == ROLE_PERFORMER else 'menu_campaigns'
    markup.add(
        InlineKeyboardButton(
            text=UserService.t(user_id, 'menu_history'),
            callback_data=pack_callback(version, 'go', 'history'),
        ),
        InlineKeyboardButton(
            text=UserService.t(user_id, secondary_label),
            callback_data=pack_callback(version, 'go', secondary_section),
        ),
    )
    markup.add(
        InlineKeyboardButton(
            text=UserService.t(user_id, 'wallet_topup_button'),
            callback_data=pack_callback(version, 'topup_stars', 'spk_760'),
        ),
        InlineKeyboardButton(
            text=UserService.t(user_id, 'menu_vip'),
            callback_data=pack_callback(version, 'go', 'vip'),
        ),
    )
    markup.add(
        InlineKeyboardButton(
            text=UserService.t(user_id, 'menu_rewards'),
            callback_data=pack_callback(version, 'go', 'rewards'),
        ),
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
    role = UserService.get_role(user_id)
    secondary_section = 'tasks' if role == ROLE_PERFORMER else 'campaigns'
    secondary_label = 'menu_tasks' if role == ROLE_PERFORMER else 'menu_campaigns'
    markup.add(
        InlineKeyboardButton(
            text=UserService.t(user_id, 'menu_wallet'),
            callback_data=pack_callback(version, 'go', 'wallet'),
        ),
        InlineKeyboardButton(
            text=UserService.t(user_id, secondary_label),
            callback_data=pack_callback(version, 'go', secondary_section),
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
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton(
            text=UserService.t(user_id, 'campaign_create_button'),
            callback_data=pack_callback(version, 'camp_new', 'start'),
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
                text=UserService.t(user_id, TASK_TYPE_TEXT_KEYS[task_type]),
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
    markup.add(
        InlineKeyboardButton(
            text=UserService.t(user_id, 'back_to_campaigns'),
            callback_data=pack_callback(version, 'go', 'campaigns'),
        ),
        InlineKeyboardButton(
            text=UserService.t(user_id, 'menu_stats'),
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
                text=f"{UserService.t(user_id, plan['title_key'])} · {plan['price']} {UserService.internal_currency_label(user_id)}",
                callback_data=pack_callback(version, 'vip_buy', plan_code),
            )
        )
    markup.add(
        InlineKeyboardButton(
            text=f"VIP 7 дней · {VIP_STARS_PLANS['vipstars7'].stars} ⭐",
            callback_data=pack_callback(version, 'vip_stars', 'vipstars7'),
        ),
        InlineKeyboardButton(
            text=f"VIP 30 дней · {VIP_STARS_PLANS['vipstars30'].stars} ⭐",
            callback_data=pack_callback(version, 'vip_stars', 'vipstars30'),
        ),
    )
    markup.add(
        InlineKeyboardButton(
            text=UserService.t(user_id, 'menu_rewards'),
            callback_data=pack_callback(version, 'go', 'rewards'),
        ),
        InlineKeyboardButton(
            text=UserService.t(user_id, 'menu_referrals'),
            callback_data=pack_callback(version, 'go', 'referrals'),
        ),
    )
    markup.add(
        InlineKeyboardButton(
            text=UserService.t(user_id, 'back_to_menu'),
            callback_data=pack_callback(version, 'go', 'main_menu'),
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
    for pack_code, pack in SPARKS_PACKS.items():
        markup.add(
            InlineKeyboardButton(
                text=f"{pack.sparks} {UserService.internal_currency_label(user_id)} · {pack.stars} ⭐",
                callback_data=pack_callback(version, 'topup_stars', pack_code),
            )
        )
    for months, offer in RedemptionService.premium_offers().items():
        markup.add(
            InlineKeyboardButton(
                text=f"{offer['label']} · {offer['sparks_cost']} {UserService.internal_currency_label(user_id)}",
                callback_data=pack_callback(version, 'redeem_premium', str(months)),
            )
        )
    gifts = RedemptionService.list_gifts(limit=3)
    for idx, gift in enumerate(gifts):
        markup.add(
            InlineKeyboardButton(
                text=f"{gift['emoji']} Telegram Gift · {gift['sparks_cost']} {UserService.internal_currency_label(user_id)}",
                callback_data=pack_callback(version, 'redeem_gift', str(idx)),
            )
        )
    markup.add(
        InlineKeyboardButton(
            text=UserService.t(user_id, 'menu_vip'),
            callback_data=pack_callback(version, 'go', 'vip'),
        ),
        InlineKeyboardButton(
            text=UserService.t(user_id, 'menu_referrals'),
            callback_data=pack_callback(version, 'go', 'referrals'),
        ),
    )
    markup.add(
        InlineKeyboardButton(
            text=UserService.t(user_id, 'back_to_menu'),
            callback_data=pack_callback(version, 'go', 'main_menu'),
        )
    )
    return markup


def referrals_keyboard(user_id: int, version: int) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton(
            text=UserService.t(user_id, 'menu_rewards'),
            callback_data=pack_callback(version, 'go', 'rewards'),
        ),
        InlineKeyboardButton(
            text=UserService.t(user_id, 'menu_vip'),
            callback_data=pack_callback(version, 'go', 'vip'),
        ),
    )
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
            text=UserService.t(user_id, 'admin_logs_button'),
            callback_data=pack_callback(version, 'go', 'admin_logs'),
        ),
    )
    if UserService.is_owner(user_id):
        markup.add(
            InlineKeyboardButton(
                text=UserService.t(user_id, 'admin_required_chats_button'),
                callback_data=pack_callback(version, 'go', 'admin_required_chats'),
            )
        )
    markup.add(
        InlineKeyboardButton(
            text=UserService.t(user_id, 'back_to_menu'),
            callback_data=pack_callback(version, 'go', 'main_menu'),
        )
    )
    return markup


def admin_queue_keyboard(user_id: int, version: int, submissions) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=1)
    for submission in submissions[:10]:
        title = str(submission['campaign_title'] or f"#{int(submission['campaign_id'])}")
        performer = str(submission['username'] or '').strip()
        display = f"@{performer}" if performer else f"ID {int(submission['performer_user_id'])}"
        text = UserService.t(
            user_id,
            'admin_queue_row',
            submission_id=int(submission['id']),
            title=title[:18],
            performer=display[:18],
            risk=int(submission['risk_score']),
        )
        markup.add(
            InlineKeyboardButton(
                text=text,
                callback_data=pack_callback(version, 'admin_submission', str(int(submission['id']))),
            )
        )
    markup.add(
        InlineKeyboardButton(
            text=UserService.t(user_id, 'refresh_screen'),
            callback_data=pack_callback(version, 'go', 'admin_queue'),
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
