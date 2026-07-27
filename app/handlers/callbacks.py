import logging
import telebot
from app.config import settings
from telebot.types import CallbackQuery
from telebot import types

from app.router import (
    SCREEN_ADMIN,
    SCREEN_ADMIN_QUEUE,
    SCREEN_ADMIN_REQUIRED_CHAT_ADD,
    SCREEN_ADMIN_REQUIRED_CHATS,
    SCREEN_CAMPAIGN_CREATE,
    SCREEN_CAMPAIGN_PREVIEW,
    SCREEN_MAIN_MENU,
    SCREEN_REQUIRED_SUBSCRIPTION,
    SCREEN_TOPUP_CUSTOM,
    SECTION_TO_SCREEN,
    admin_balance_screen_key,
    admin_reject_screen_key,
    admin_risk_screen_key,
    admin_submission_screen_key,
    campaign_card_screen_key,
    campaign_input_screen_key,
    proof_wait_screen_key,
    render_current,
    render_entry,
    render_screen,
    submission_screen_key,
    task_screen_key,
)
from app.services.admin import AdminService
from app.services.admin_console import AdminConsoleService
from app.services.ad_broadcasts import AdBroadcastService
from app.services.campaigns import CampaignService
from app.services.client_dashboard import boost_campaign
from app.services.client_campaigns import ClientCampaignService
from app.services.community_rules import CommunityRulesService
from app.services.legal_docs import LegalDocsService
from app.services.standard_admin import StandardAdminService
from app.services.engagement_growth import EngagementGrowthService
from app.services.engagement_modes import EngagementModeService
from app.services.input_sessions import InputSessionService
from app.services.invoice_messages import InvoiceMessageService
from app.services.boostore_provider import BoostoreProviderService
from app.services.payments import SPARKS_PACKS, VIP_STARS_PLANS, calculate_custom_stars_for_sparks, make_payload, make_start_parameter
from app.services.performer import PerformerService
from app.services.redemptions import RedemptionService
from app.services.rewards import RewardService
from app.services.subscriptions import SubscriptionService
from app.services.ui_state import UIStateService
from app.services.users import UserService
from app.services.vip import VipService
from app.texts import ROLE_CLIENT, TEXTS
from app.utils.callbacks import parse_callback

logger = logging.getLogger(__name__)


def _safe_int(raw_value: str) -> int | None:
    raw = (raw_value or '').strip()
    return int(raw) if raw.isdigit() else None


def _answer_stale(bot: telebot.TeleBot, call: CallbackQuery) -> None:
    language = UserService.get_language(call.from_user.id)
    bot.answer_callback_query(call.id, TEXTS[language]['stale_screen'], show_alert=False)


def _ensure_client_role(bot: telebot.TeleBot, call: CallbackQuery) -> bool:
    if UserService.get_role(call.from_user.id) == ROLE_CLIENT:
        return True
    bot.answer_callback_query(call.id, UserService.t(call.from_user.id, 'campaign_client_only'), show_alert=False)
    render_screen(bot, call, SCREEN_MAIN_MENU, notice_key='campaign_client_only')
    return False


def _ensure_admin(bot: telebot.TeleBot, call: CallbackQuery) -> bool:
    if UserService.is_admin(call.from_user.id):
        return True
    bot.answer_callback_query(call.id, UserService.t(call.from_user.id, 'admin_access_denied'), show_alert=False)
    render_screen(bot, call, SCREEN_MAIN_MENU, notice_key='admin_access_denied')
    return False


def _ensure_owner(bot: telebot.TeleBot, call: CallbackQuery) -> bool:
    if UserService.is_owner(call.from_user.id):
        return True
    bot.answer_callback_query(call.id, UserService.t(call.from_user.id, 'admin_access_denied'), show_alert=False)
    render_screen(bot, call, SCREEN_ADMIN, notice_key='admin_access_denied')
    return False



def _safe_delete_message(bot: telebot.TeleBot, chat_id: int | None, message_id: int | None) -> None:
    if chat_id is None or message_id is None:
        return
    try:
        bot.delete_message(chat_id=int(chat_id), message_id=int(message_id))
    except Exception:
        return


def _delete_pending_invoice(bot: telebot.TeleBot, user_id: int) -> None:
    row = InvoiceMessageService.get(user_id)
    if not row:
        return
    _safe_delete_message(bot, row['chat_id'], row['invoice_message_id'])
    _safe_delete_message(bot, row['chat_id'], row['helper_message_id'])
    InvoiceMessageService.clear(user_id)


def _send_stars_invoice(bot: telebot.TeleBot, call: CallbackQuery, *, title: str, description: str, payload: str, amount_stars: int) -> tuple[bool, str | None]:
    prices = [types.LabeledPrice(label=title[:32], amount=int(amount_stars))]
    parsed = payload.split(':', 2)
    start_parameter = make_start_parameter(*(parsed if len(parsed) == 3 else ['pay', 'invoice', str(call.from_user.id)]))
    _delete_pending_invoice(bot, call.from_user.id)
    try:
        sent = bot.send_invoice(
            chat_id=call.from_user.id,
            title=title[:32],
            description=description[:255],
            invoice_payload=payload,
            provider_token='',
            currency='XTR',
            prices=prices,
            start_parameter=start_parameter,
        )
        try:
            InvoiceMessageService.set(call.from_user.id, int(sent.chat.id), int(sent.message_id))
        except Exception:
            logger.exception('Failed to store invoice message for user %s', call.from_user.id)
        return True, None
    except Exception:
        logger.exception('Failed to send Stars invoice to user %s', call.from_user.id)
        return False, 'payment_invoice_failed'


def register_callback_handlers(bot: telebot.TeleBot) -> None:
    @bot.callback_query_handler(func=lambda call: True)
    def handle_callbacks(call: CallbackQuery) -> None:
        try:
            UserService.ensure_user(call.from_user)
            parsed = parse_callback(call.data)
            if parsed is None:
                bot.answer_callback_query(call.id)
                return
    
            if not UserService.can_access_bot(call.from_user.id) and not UserService.is_admin(call.from_user.id):
                bot.answer_callback_query(call.id, UserService.t(call.from_user.id, 'blocked_alert'), show_alert=False)
                render_entry(bot, call)
                return
    
            if UIStateService.is_stale(call.from_user.id, parsed.version):
                _answer_stale(bot, call)
                return
    
            if parsed.action == 'rules_accept':
                CommunityRulesService.accept(call.from_user.id, source='bot_callback')
                bot.answer_callback_query(call.id, UserService.t(call.from_user.id, 'community_rules_accepted_notice'), show_alert=False)
                render_entry(bot, call)
                return

            if parsed.action == 'legal_accept':
                LegalDocsService.accept(call.from_user.id, source='bot_callback')
                bot.answer_callback_query(call.id, UserService.t(call.from_user.id, 'legal_docs_accepted_notice'), show_alert=False)
                render_entry(bot, call)
                return

            if (not CommunityRulesService.is_accepted(call.from_user.id)
                    and not UserService.is_admin(call.from_user.id)
                    and parsed.action not in {'lang', 'role', 'go', 'refresh'}):
                bot.answer_callback_query(call.id, UserService.t(call.from_user.id, 'community_rules_required_alert'), show_alert=False)
                render_screen(bot, call, 'community_rules', notice_key='community_rules_required_notice')
                return

            if (not LegalDocsService.is_accepted(call.from_user.id)
                    and not UserService.is_admin(call.from_user.id)
                    and parsed.action not in {'lang', 'role', 'go', 'refresh', 'legal_accept'}):
                bot.answer_callback_query(call.id, UserService.t(call.from_user.id, 'legal_docs_required_alert'), show_alert=False)
                render_screen(bot, call, 'legal_docs', notice_key='legal_docs_required_notice')
                return

            if parsed.action == 'eng_mode':
                if not _ensure_client_role(bot, call):
                    return
                if parsed.value == 'standard':
                    EngagementModeService.set_standard(call.from_user.id, source='bot_callback')
                    bot.answer_callback_query(call.id, UserService.t(call.from_user.id, 'engagement_mode_standard_saved'), show_alert=False)
                    render_screen(bot, call, 'engagement_growth', notice_key='engagement_mode_standard_saved')
                    return
                bot.answer_callback_query(call.id, UserService.t(call.from_user.id, 'stale_screen'), show_alert=False)
                render_screen(bot, call, 'engagement_mode')
                return

            if parsed.action == 'eng_pro_pay':
                if not _ensure_client_role(bot, call):
                    return
                amount = EngagementModeService.pro_price_stars()
                ok_send, notice_key = _send_stars_invoice(
                    bot,
                    call,
                    title=UserService.t(call.from_user.id, 'engagement_pro_invoice_title'),
                    description=UserService.t(call.from_user.id, 'engagement_pro_invoice_desc', days=30),
                    payload=make_payload('engpro', '30d', call.from_user.id),
                    amount_stars=amount,
                )
                bot.answer_callback_query(call.id, UserService.t(call.from_user.id, notice_key or 'payment_invoice_sent'), show_alert=not ok_send)
                render_screen(bot, call, 'engagement_mode', notice_key=notice_key or 'payment_invoice_sent')
                return

            if parsed.action == 'lang':
                try:
                    UserService.set_language(call.from_user.id, parsed.value)
                except ValueError:
                    bot.answer_callback_query(call.id, UserService.t(call.from_user.id, 'stale_screen'), show_alert=False)
                    render_entry(bot, call)
                    return
                bot.answer_callback_query(call.id, UserService.t(call.from_user.id, 'language_updated'))
                render_entry(bot, call)
                return
    
            if parsed.action == 'role':
                try:
                    UserService.set_role(call.from_user.id, parsed.value)
                except ValueError:
                    bot.answer_callback_query(call.id, UserService.t(call.from_user.id, 'stale_screen'), show_alert=False)
                    render_entry(bot, call)
                    return
                bot.answer_callback_query(call.id, UserService.t(call.from_user.id, 'role_updated'))
                render_entry(bot, call)
                return
    
            if parsed.action == 'check_subscription':
                if not SubscriptionService.should_enforce_required_chat(call.message.chat.id, chat_username=getattr(call.message.chat, 'username', None)):
                    bot.answer_callback_query(call.id, UserService.t(call.from_user.id, 'subscription_not_required_here'))
                    render_entry(bot, call)
                    return
                check = SubscriptionService.get_subscription_check_result(bot, call.from_user.id)
                if check.is_subscribed:
                    bot.answer_callback_query(call.id, UserService.t(call.from_user.id, 'subscription_success'))
                    render_screen(bot, call, SCREEN_MAIN_MENU)
                    return
                if check.is_unknown:
                    bot.answer_callback_query(call.id, UserService.t(call.from_user.id, 'subscription_check_unavailable'), show_alert=False)
                    render_screen(bot, call, SCREEN_MAIN_MENU, notice_key='subscription_check_unavailable')
                    return
                bot.answer_callback_query(call.id, UserService.t(call.from_user.id, 'subscription_missing'), show_alert=False)
                render_screen(bot, call, SCREEN_REQUIRED_SUBSCRIPTION, notice_key='subscription_missing')
                return
    
            if parsed.action == 'refresh':
                bot.answer_callback_query(call.id, UserService.t(call.from_user.id, 'screen_refreshed'))
                render_current(bot, call)
                return
    
            if parsed.action == 'go':
                destination = parsed.value
                bot.answer_callback_query(call.id)
                if destination == 'main_menu':
                    InputSessionService.clear_session(call.from_user.id)
                    render_entry(bot, call)
                    return
                if destination in SECTION_TO_SCREEN:
                    InputSessionService.clear_session(call.from_user.id)
                    render_screen(bot, call, SECTION_TO_SCREEN[destination])
                    return
                if destination in {'language', 'role', 'topup_packages', 'exchange'}:
                    InputSessionService.clear_session(call.from_user.id)
                    render_screen(bot, call, destination)
                    return
                if (
                    destination.startswith('admin_bot_chats:')
                    or destination.startswith('admin_bot_rights:')
                    or destination.startswith('admin_users:')
                    or destination.startswith('admin_queue:')
                    or destination.startswith('marketplace:')
                    or destination.startswith('owner_provider:')
                ):
                    InputSessionService.clear_session(call.from_user.id)
                    render_screen(bot, call, destination)
                    return
                render_entry(bot, call)
                return
    
            if parsed.action == 'task':
                campaign_id = _safe_int(parsed.value)
                bot.answer_callback_query(call.id)
                if campaign_id is None:
                    render_screen(bot, call, SECTION_TO_SCREEN['tasks'])
                    return
                render_screen(bot, call, task_screen_key(campaign_id))
                return
    
            if parsed.action == 'submission':
                submission_id = _safe_int(parsed.value)
                bot.answer_callback_query(call.id)
                if submission_id is None:
                    render_screen(bot, call, SECTION_TO_SCREEN['tasks'])
                    return
                render_screen(bot, call, submission_screen_key(submission_id))
                return
    
            if parsed.action == 'take':
                campaign_id = _safe_int(parsed.value)
                if campaign_id is None:
                    bot.answer_callback_query(call.id)
                    render_screen(bot, call, SECTION_TO_SCREEN['tasks'])
                    return
                ok, result_key, submission_id = PerformerService.take_task(call.from_user.id, campaign_id)
                if ok:
                    bot.answer_callback_query(call.id, UserService.t(call.from_user.id, result_key))
                    render_screen(bot, call, submission_screen_key(int(submission_id)), notice_key=result_key)
                    return
                bot.answer_callback_query(call.id, UserService.t(call.from_user.id, result_key), show_alert=False)
                render_screen(bot, call, task_screen_key(campaign_id), notice_key=result_key)
                return
    
            if parsed.action == 'proof_input_start':
                submission_id = _safe_int(parsed.value)
                if submission_id is None:
                    bot.answer_callback_query(call.id)
                    render_screen(bot, call, SECTION_TO_SCREEN['tasks'])
                    return
                submission = PerformerService.get_submission(submission_id)
                if not submission or int(submission['performer_user_id']) != call.from_user.id:
                    bot.answer_callback_query(call.id, UserService.t(call.from_user.id, 'task_not_found'), show_alert=False)
                    render_screen(bot, call, SECTION_TO_SCREEN['tasks'])
                    return
                if str(submission['status']) != 'taken':
                    bot.answer_callback_query(call.id, UserService.t(call.from_user.id, 'proof_already_sent'), show_alert=False)
                    render_screen(bot, call, submission_screen_key(submission_id), notice_key='proof_already_sent')
                    return
                InputSessionService.set_session(call.from_user.id, 'submit_proof', str(submission_id))
                bot.answer_callback_query(call.id, UserService.t(call.from_user.id, 'proof_manual_started'), show_alert=False)
                render_screen(bot, call, proof_wait_screen_key(submission_id), notice_key='proof_manual_started')
                return

            if parsed.action == 'submit_start':
                submission_id = _safe_int(parsed.value)
                if submission_id is None:
                    bot.answer_callback_query(call.id)
                    render_screen(bot, call, SECTION_TO_SCREEN['tasks'])
                    return
                submission = PerformerService.get_submission(submission_id)
                if not submission or int(submission['performer_user_id']) != call.from_user.id:
                    bot.answer_callback_query(call.id, UserService.t(call.from_user.id, 'task_not_found'), show_alert=False)
                    render_screen(bot, call, SECTION_TO_SCREEN['tasks'])
                    return
                ok, result_key, _ = PerformerService.submit_for_check(bot, call.from_user.id, submission_id)
                bot.answer_callback_query(call.id, UserService.t(call.from_user.id, result_key), show_alert=not ok)
                render_screen(bot, call, submission_screen_key(submission_id), notice_key=result_key)
                return
    
            if parsed.action == 'cancel_input':
                session = InputSessionService.get_session(call.from_user.id)
                mode = str(session['mode']) if session else ''
                draft = AdBroadcastService.get_draft(call.from_user.id) if mode.startswith('broadcast_') else {}
                InputSessionService.clear_session(call.from_user.id)
                bot.answer_callback_query(call.id, UserService.t(call.from_user.id, 'input_cancelled'))
                submission_id = _safe_int(parsed.value)
                if mode.startswith('broadcast_'):
                    target_screen = 'admin' if draft.get('is_admin') else SECTION_TO_SCREEN['campaigns']
                    render_screen(bot, call, target_screen, notice_key='input_cancelled')
                    return
                if mode.startswith('campaign_'):
                    render_screen(bot, call, SECTION_TO_SCREEN['campaigns'], notice_key='input_cancelled')
                    return
                if mode == 'topup_custom_sparks' or parsed.value == 'topup_custom':
                    render_screen(bot, call, SECTION_TO_SCREEN['wallet'], notice_key='input_cancelled')
                    return
                if submission_id is None:
                    render_screen(bot, call, SECTION_TO_SCREEN['tasks'], notice_key='input_cancelled')
                    return
                render_screen(bot, call, submission_screen_key(submission_id), notice_key='input_cancelled')
                return
    
            if parsed.action == 'ad_new':
                is_admin_mode = parsed.value == 'admin'
                if is_admin_mode and not _ensure_admin(bot, call):
                    return
                if (not is_admin_mode) and not _ensure_client_role(bot, call):
                    return
                AdBroadcastService.clear_draft(call.from_user.id)
                ok, result_key = AdBroadcastService.start_draft(call.from_user.id, is_admin=is_admin_mode)
                bot.answer_callback_query(call.id, UserService.t(call.from_user.id, result_key), show_alert=not ok)
                render_screen(bot, call, 'broadcast_text' if ok else ('admin' if is_admin_mode else 'campaigns'), notice_key=result_key)
                return

            if parsed.action == 'ad_sched':
                value = str(parsed.value or '')
                if value.startswith('repeat:'):
                    ok, result_key = AdBroadcastService.set_repeat_count(call.from_user.id, _safe_int(value.split(':', 1)[1]) or 0)
                    bot.answer_callback_query(call.id, UserService.t(call.from_user.id, result_key), show_alert=not ok)
                    render_screen(bot, call, 'broadcast_schedule', notice_key=result_key)
                    return
                if value.startswith('freq:'):
                    ok, result_key = AdBroadcastService.set_interval_hours(call.from_user.id, _safe_int(value.split(':', 1)[1]) or 0)
                    bot.answer_callback_query(call.id, UserService.t(call.from_user.id, result_key), show_alert=not ok)
                    render_screen(bot, call, 'broadcast_preview' if ok else 'broadcast_schedule', notice_key=result_key)
                    return
                bot.answer_callback_query(call.id, UserService.t(call.from_user.id, 'broadcast_draft_missing'), show_alert=True)
                render_screen(bot, call, 'broadcast_schedule', notice_key='broadcast_draft_missing')
                return

            if parsed.action == 'ad_pay':
                ok, result_key, order_id = AdBroadcastService.create_pending_order(call.from_user.id)
                if not ok or order_id is None:
                    bot.answer_callback_query(call.id, UserService.t(call.from_user.id, result_key), show_alert=True)
                    render_screen(bot, call, 'broadcast_preview', notice_key=result_key)
                    return
                order = AdBroadcastService.get_order(order_id)
                stars = int(order['stars_price']) if order else 0
                ok_send, notice_key = _send_stars_invoice(
                    bot,
                    call,
                    title='Реклама во все чаты',
                    description=UserService.t(call.from_user.id, 'broadcast_invoice_desc', stars=stars),
                    payload=make_payload('broadcast', str(order_id), call.from_user.id),
                    amount_stars=stars,
                )
                bot.answer_callback_query(call.id, UserService.t(call.from_user.id, notice_key or 'payment_invoice_sent'), show_alert=not ok_send)
                render_screen(bot, call, 'broadcast_preview', notice_key=notice_key or 'payment_invoice_sent')
                return

            if parsed.action == 'ad_send':
                if not _ensure_admin(bot, call):
                    return
                ok, result_key, order_id = AdBroadcastService.create_admin_order(call.from_user.id)
                if ok and order_id is not None:
                    sent, _failed = AdBroadcastService.dispatch_order(bot, order_id, support_username=UserService.t(call.from_user.id, 'support_username_fallback'))
                    AdBroadcastService.clear_draft(call.from_user.id)
                    notice = UserService.t(call.from_user.id, 'broadcast_admin_sent_notice', sent=sent)
                    bot.answer_callback_query(call.id, notice, show_alert=False)
                    render_screen(bot, call, 'admin', notice_text=notice)
                    return
                bot.answer_callback_query(call.id, UserService.t(call.from_user.id, result_key), show_alert=True)
                render_screen(bot, call, 'broadcast_preview', notice_key=result_key)
                return

            if parsed.action == 'camp_new':
                if not _ensure_client_role(bot, call):
                    return
                ClientCampaignService.clear_draft(call.from_user.id)
                bot.answer_callback_query(call.id)
                render_screen(bot, call, SCREEN_CAMPAIGN_CREATE)
                return
    
            if parsed.action == 'egp':
                if not _ensure_client_role(bot, call):
                    return
                preset = EngagementGrowthService.preset_by_code(parsed.value)
                if preset is None:
                    bot.answer_callback_query(call.id, UserService.t(call.from_user.id, 'engagement_preset_not_found'), show_alert=True)
                    render_screen(bot, call, 'engagement_growth', notice_key='engagement_preset_not_found')
                    return
                mode = EngagementModeService.current_mode(call.from_user.id)
                if not mode:
                    bot.answer_callback_query(call.id, UserService.t(call.from_user.id, 'engagement_mode_required_alert'), show_alert=True)
                    render_screen(bot, call, 'engagement_mode', notice_key='engagement_mode_required_notice')
                    return
                allowed, guard_key, _guard = EngagementModeService.can_launch_engagement(call.from_user.id)
                if not allowed:
                    bot.answer_callback_query(call.id, UserService.t(call.from_user.id, guard_key), show_alert=True)
                    render_screen(bot, call, 'engagement_obligations', notice_key=guard_key)
                    return
                ok, result_key = ClientCampaignService.start_preset(call.from_user.id, preset.task_type, preset.quantity, preset.code, engagement_mode=mode)
                bot.answer_callback_query(call.id, UserService.t(call.from_user.id, result_key, quantity=preset.quantity), show_alert=not ok)
                if ok:
                    render_screen(bot, call, campaign_input_screen_key('target'), notice_key=result_key)
                    return
                render_screen(bot, call, 'engagement_growth', notice_key=result_key)
                return

            if parsed.action == 'ctype':
                if not _ensure_client_role(bot, call):
                    return
                mode = EngagementModeService.current_mode(call.from_user.id) if EngagementModeService.is_engagement_task(parsed.value) else None
                if EngagementModeService.is_engagement_task(parsed.value) and not mode:
                    bot.answer_callback_query(call.id, UserService.t(call.from_user.id, 'engagement_mode_required_alert'), show_alert=True)
                    render_screen(bot, call, 'engagement_mode', notice_key='engagement_mode_required_notice')
                    return
                if EngagementModeService.is_engagement_task(parsed.value):
                    allowed, guard_key, _guard = EngagementModeService.can_launch_engagement(call.from_user.id)
                    if not allowed:
                        bot.answer_callback_query(call.id, UserService.t(call.from_user.id, guard_key), show_alert=True)
                        render_screen(bot, call, 'engagement_obligations', notice_key=guard_key)
                        return
                ok, result_key = ClientCampaignService.start_draft(call.from_user.id, parsed.value, engagement_mode=mode)
                bot.answer_callback_query(call.id, UserService.t(call.from_user.id, result_key), show_alert=not ok)
                if ok:
                    render_screen(bot, call, campaign_input_screen_key('target'), notice_key=result_key)
                    return
                render_screen(bot, call, SCREEN_CAMPAIGN_CREATE, notice_key=result_key)
                return
    
            if parsed.action == 'camp_save':
                if not _ensure_client_role(bot, call):
                    return
                ok, result_key, campaign_id = ClientCampaignService.finalize_draft(
                    call.from_user.id,
                    launch_now=parsed.value == 'launch',
                )
                bot.answer_callback_query(call.id, UserService.t(call.from_user.id, result_key), show_alert=False)
                if ok and campaign_id is not None:
                    render_screen(bot, call, campaign_card_screen_key(int(campaign_id)), notice_key=result_key)
                    return
                render_screen(bot, call, SCREEN_CAMPAIGN_PREVIEW, notice_key=result_key)
                return
    
            if parsed.action == 'camp_cancel':
                mode = AdBroadcastService.get_mode(call.from_user.id) or ''
                draft = AdBroadcastService.get_draft(call.from_user.id) if mode.startswith('broadcast_') else {}
                if mode.startswith('broadcast_'):
                    AdBroadcastService.clear_draft(call.from_user.id)
                    bot.answer_callback_query(call.id, UserService.t(call.from_user.id, 'campaign_create_cancelled'))
                    render_screen(bot, call, 'admin' if draft.get('is_admin') else SECTION_TO_SCREEN['campaigns'], notice_key='campaign_create_cancelled')
                    return
                if not _ensure_client_role(bot, call):
                    return
                ClientCampaignService.clear_draft(call.from_user.id)
                bot.answer_callback_query(call.id, UserService.t(call.from_user.id, 'campaign_create_cancelled'))
                render_screen(bot, call, SECTION_TO_SCREEN['campaigns'], notice_key='campaign_create_cancelled')
                return
    
            if parsed.action == 'camp':
                if not _ensure_client_role(bot, call):
                    return
                bot.answer_callback_query(call.id)
                campaign_id = _safe_int(parsed.value)
                if campaign_id is None:
                    render_screen(bot, call, SECTION_TO_SCREEN['campaigns'])
                    return
                render_screen(bot, call, campaign_card_screen_key(campaign_id))
                return
    
            if parsed.action == 'camp_status':
                if not _ensure_client_role(bot, call):
                    return
                raw = parsed.value.split(',', 1)
                if len(raw) != 2 or not raw[0].isdigit():
                    bot.answer_callback_query(call.id)
                    render_screen(bot, call, SECTION_TO_SCREEN['campaigns'])
                    return
                campaign_id = int(raw[0])
                new_status = raw[1].strip()
                ok, result_key = CampaignService.update_status(call.from_user.id, campaign_id, new_status)
                bot.answer_callback_query(call.id, UserService.t(call.from_user.id, result_key), show_alert=False)
                render_screen(bot, call, campaign_card_screen_key(campaign_id), notice_key=result_key)
                return

            if parsed.action == 'camp_boost':
                if not _ensure_client_role(bot, call):
                    return
                raw = parsed.value.split(',', 1)
                if len(raw) != 2 or not raw[0].isdigit():
                    bot.answer_callback_query(call.id)
                    render_screen(bot, call, SECTION_TO_SCREEN['campaigns'])
                    return
                campaign_id = int(raw[0])
                level = raw[1].strip()
                ok, result_key = boost_campaign(call.from_user.id, campaign_id, level)
                bot.answer_callback_query(call.id, UserService.t(call.from_user.id, result_key), show_alert=not ok)
                render_screen(bot, call, campaign_card_screen_key(campaign_id), notice_key=result_key)
                return

            if parsed.action == 'topup_custom':
                InputSessionService.set_session(call.from_user.id, 'topup_custom_sparks', '')
                bot.answer_callback_query(call.id)
                render_screen(bot, call, SCREEN_TOPUP_CUSTOM)
                return

            if parsed.action == 'topup_stars':
                pack = SPARKS_PACKS.get(parsed.value)
                if not pack:
                    bot.answer_callback_query(call.id, UserService.t(call.from_user.id, 'payment_pack_not_found'), show_alert=False)
                    render_current(bot, call, notice_key='payment_pack_not_found')
                    return
                ok, notice_key = _send_stars_invoice(
                    bot,
                    call,
                    title=pack.title,
                    description=pack.description,
                    payload=make_payload('sparks', pack.code, call.from_user.id),
                    amount_stars=pack.stars,
                )
                bot.answer_callback_query(
                    call.id,
                    UserService.t(call.from_user.id, notice_key or 'payment_invoice_sent'),
                    show_alert=not ok,
                )
                render_screen(bot, call, 'wallet', notice_key=notice_key or 'payment_invoice_sent')
                return

            if parsed.action == 'vip_stars':
                plan = VIP_STARS_PLANS.get(parsed.value)
                if not plan:
                    bot.answer_callback_query(call.id, UserService.t(call.from_user.id, 'vip_plan_not_found'), show_alert=False)
                    render_screen(bot, call, 'vip', notice_key='vip_plan_not_found')
                    return
                ok, notice_key = _send_stars_invoice(
                    bot,
                    call,
                    title=plan.title,
                    description=plan.description,
                    payload=make_payload('vip', plan.code, call.from_user.id),
                    amount_stars=plan.stars,
                )
                bot.answer_callback_query(
                    call.id,
                    UserService.t(call.from_user.id, notice_key or 'payment_invoice_sent'),
                    show_alert=not ok,
                )
                render_screen(bot, call, 'vip', notice_key=notice_key or 'payment_invoice_sent')
                return

            if parsed.action == 'cancel_invoice':
                _delete_pending_invoice(bot, call.from_user.id)
                InputSessionService.clear_session(call.from_user.id)
                bot.answer_callback_query(call.id, UserService.t(call.from_user.id, 'payment_invoice_cancelled'))
                target_section = parsed.value if parsed.value in {'wallet', 'vip', 'rewards', 'broadcast_preview', 'topup_packages'} else 'wallet'
                render_screen(bot, call, target_section, notice_key='payment_invoice_cancelled')
                return

            if parsed.action == 'vip_buy':
                ok, result_key = VipService.purchase_plan(call.from_user.id, parsed.value)
                bot.answer_callback_query(call.id, UserService.t(call.from_user.id, result_key), show_alert=False)
                render_screen(bot, call, 'vip', notice_key=result_key)
                return
    
            if parsed.action == 'reward_buy':
                ok, result_key = RewardService.purchase_item(call.from_user.id, parsed.value)
                bot.answer_callback_query(call.id, UserService.t(call.from_user.id, result_key), show_alert=False)
                render_screen(bot, call, 'rewards', notice_key=result_key)
                return
    
            if parsed.action == 'demo_topup':
                ok, result_key = RewardService.claim_demo_topup(call.from_user.id)
                bot.answer_callback_query(call.id, UserService.t(call.from_user.id, result_key), show_alert=False)
                render_screen(bot, call, 'rewards', notice_key=result_key)
                return

            if parsed.action == 'redeem_premium':
                months = _safe_int(parsed.value)
                if months is None:
                    bot.answer_callback_query(call.id)
                    render_screen(bot, call, 'rewards')
                    return
                ok, result_key = RedemptionService.purchase_premium(call.from_user.id, months)
                bot.answer_callback_query(call.id, UserService.t(call.from_user.id, result_key), show_alert=False)
                render_screen(bot, call, 'rewards', notice_key=result_key)
                return

            if parsed.action == 'redeem_gift':
                gift_index = _safe_int(parsed.value)
                if gift_index is None:
                    bot.answer_callback_query(call.id)
                    render_screen(bot, call, 'rewards')
                    return
                ok, result_key = RedemptionService.purchase_gift_by_index(call.from_user.id, gift_index)
                bot.answer_callback_query(call.id, UserService.t(call.from_user.id, result_key), show_alert=False)
                render_screen(bot, call, 'rewards', notice_key=result_key)
                return

            if parsed.action == 'cashout_req':
                stars_amount = _safe_int(parsed.value)
                if stars_amount is None:
                    bot.answer_callback_query(call.id)
                    render_screen(bot, call, 'rewards')
                    return
                ok, result_key, redemption_id = RedemptionService.create_cashout_request(call.from_user.id, stars_amount)
                if ok and UserService.owner_id():
                    try:
                        username = getattr(call.from_user, 'username', None) or '-'
                        bot.send_message(
                            UserService.owner_id(),
                            f"Новая заявка на вывод #{redemption_id}\nПользователь: {call.from_user.id} (@{username})\nПакет: {stars_amount} ⭐",
                        )
                    except Exception:
                        pass
                bot.answer_callback_query(call.id, UserService.t(call.from_user.id, result_key), show_alert=False)
                render_screen(bot, call, 'rewards', notice_key=result_key)
                return
            if parsed.action == 'admin_bulk_clean':
                if not _ensure_admin(bot, call):
                    return
                ok, result_key, count = AdminService.bulk_approve_clean(call.from_user.id, limit=10)
                bot.answer_callback_query(call.id, UserService.t(call.from_user.id, result_key, count=count), show_alert=False)
                render_screen(bot, call, 'admin_queue:clean', notice_text=UserService.t(call.from_user.id, result_key, count=count))
                return

            if parsed.action == 'admin_bulk_block_high':
                if not _ensure_admin(bot, call):
                    return
                result = AdminConsoleService.block_high_risk_users(call.from_user.id, limit=10, threshold=60)
                bot.answer_callback_query(call.id, UserService.t(call.from_user.id, result.result_key, count=result.count), show_alert=False)
                render_screen(bot, call, 'admin_queue:high', notice_text=UserService.t(call.from_user.id, result.result_key, count=result.count))
                return

    

            if parsed.action == 'std_extend':
                if not _ensure_admin(bot, call):
                    return
                obligation_id = _safe_int(parsed.value)
                ok, key = StandardAdminService.extend_obligation(call.from_user.id, obligation_id or 0, hours=24)
                bot.answer_callback_query(call.id, UserService.t(call.from_user.id, key), show_alert=not ok)
                render_screen(bot, call, 'admin_engagement_obligations', notice_key=key)
                return

            if parsed.action == 'std_forgive':
                if not _ensure_admin(bot, call):
                    return
                obligation_id = _safe_int(parsed.value)
                ok, key = StandardAdminService.forgive_obligation(call.from_user.id, obligation_id or 0)
                bot.answer_callback_query(call.id, UserService.t(call.from_user.id, key), show_alert=not ok)
                render_screen(bot, call, 'admin_engagement_obligations', notice_key=key)
                return

            if parsed.action == 'std_warn':
                if not _ensure_admin(bot, call):
                    return
                obligation_id = _safe_int(parsed.value)
                ok, key = StandardAdminService.warn_obligation(bot, call.from_user.id, obligation_id or 0, support_username=settings.support_username)
                bot.answer_callback_query(call.id, UserService.t(call.from_user.id, key), show_alert=not ok)
                render_screen(bot, call, 'admin_engagement_obligations', notice_key=key)
                return

            if parsed.action == 'std_pro':
                if not _ensure_admin(bot, call):
                    return
                target_user_id = _safe_int(parsed.value)
                ok, key = StandardAdminService.grant_manual_pro(call.from_user.id, target_user_id or 0, days=30)
                bot.answer_callback_query(call.id, UserService.t(call.from_user.id, key), show_alert=not ok)
                render_screen(bot, call, 'admin_engagement_obligations', notice_key=key)
                return

            if parsed.action == 'boostore_order_start':
                if not _ensure_client_role(bot, call):
                    return
                service_id = str(parsed.value or '').strip()
                service = BoostoreProviderService.get_public_service(service_id)
                if not service:
                    bot.answer_callback_query(call.id, UserService.t(call.from_user.id, 'boostore_temporarily_unavailable'), show_alert=True)
                    render_screen(bot, call, 'marketplace', notice_key='boostore_temporarily_unavailable')
                    return
                InputSessionService.set_session(call.from_user.id, 'boostore_order_link', service_id)
                bot.answer_callback_query(call.id, UserService.t(call.from_user.id, 'boostore_order_link_prompt'), show_alert=False)
                render_screen(bot, call, 'marketplace', notice_key='boostore_order_link_prompt')
                return

            if parsed.action == 'boostore_check':
                if not _ensure_owner(bot, call):
                    return
                diagnostics = BoostoreProviderService.live_diagnostics()
                status_key = 'boostore_check_success' if diagnostics.get('ok') else 'boostore_check_warning'
                notice = UserService.t(
                    call.from_user.id,
                    'boostore_check_report',
                    state=UserService.t(call.from_user.id, f"boostore_state_{diagnostics.get('state')}"),
                    score=int(diagnostics.get('score') or 0),
                    key=diagnostics.get('masked_key') or '—',
                    balance=diagnostics.get('balance_text') or '—',
                    cached=int(diagnostics.get('cached_total') or 0),
                    whitelist=int(diagnostics.get('whitelist_total') or 0),
                    result=UserService.t(call.from_user.id, str(diagnostics.get('result_key') or 'boostore_api_error')),
                    error=diagnostics.get('error') or '—',
                )
                bot.answer_callback_query(call.id, UserService.t(call.from_user.id, status_key), show_alert=False)
                render_screen(bot, call, 'owner_provider', notice_text=notice)
                return

            if parsed.action == 'boostore_sync':
                if not _ensure_owner(bot, call):
                    return
                result = BoostoreProviderService.sync_services()
                if result.ok:
                    count = int((result.data or {}).get('count', 0)) if isinstance(result.data, dict) else 0
                    text = UserService.t(call.from_user.id, 'boostore_sync_success', count=count)
                    bot.answer_callback_query(call.id, text, show_alert=False)
                    render_screen(bot, call, 'owner_provider', notice_text=text)
                else:
                    bot.answer_callback_query(call.id, UserService.t(call.from_user.id, result.result_key), show_alert=True)
                    render_screen(bot, call, 'owner_provider', notice_key=result.result_key)
                return

            if parsed.action == 'boostore_bulk':
                if not _ensure_owner(bot, call):
                    return
                parts = [part for part in str(parsed.value or '').split(':') if part]
                enabled = bool(parts and parts[0] == 'on')
                category = None
                subcategory = None
                if len(parts) >= 3 and parts[1] == 'c':
                    category = parts[2]
                elif len(parts) >= 4 and parts[1] == 's':
                    category = parts[2]
                    subcategory = parts[3]
                elif len(parts) < 2 or parts[1] != 'all':
                    bot.answer_callback_query(call.id, UserService.t(call.from_user.id, 'stale_screen'), show_alert=False)
                    render_current(bot, call)
                    return
                result = BoostoreProviderService.set_catalog_enabled(
                    enabled=enabled,
                    category=category,
                    subcategory=subcategory,
                )
                count = int((result.data or {}).get('count') or 0) if isinstance(result.data, dict) else 0
                text = UserService.t(call.from_user.id, result.result_key, count=count)
                bot.answer_callback_query(call.id, text, show_alert=not result.ok)
                render_current(bot, call, notice_text=text)
                return

            if parsed.action == 'boostore_toggle':
                if not _ensure_owner(bot, call):
                    return
                result = BoostoreProviderService.toggle_service(parsed.value)
                bot.answer_callback_query(call.id, UserService.t(call.from_user.id, result.result_key), show_alert=not result.ok)
                render_current(bot, call, notice_key=result.result_key)
                return

            if parsed.action == 'admin_live_audit':
                if not _ensure_admin(bot, call):
                    return
                limit = _safe_int(parsed.value) or 25
                result = AdminConsoleService.audit_bot_rights_live(bot, limit=limit)
                text = UserService.t(
                    call.from_user.id,
                    'admin_bot_live_audit_done',
                    checked=result['checked'],
                    ready=result['ready'],
                    issues=result['issues'],
                    failed=result['failed'],
                )
                bot.answer_callback_query(call.id, text, show_alert=False)
                render_screen(bot, call, 'admin_bot_rights:1', notice_text=text)
                return

            if parsed.action in {'admin_tpl_approve', 'admin_tpl_reject'}:
                if not _ensure_admin(bot, call):
                    return
                parts = (parsed.value or '').split(':', 1)
                submission_id = _safe_int(parts[0]) if parts else None
                template_code = parts[1] if len(parts) > 1 else ''
                if submission_id is None:
                    bot.answer_callback_query(call.id)
                    render_screen(bot, call, SCREEN_ADMIN_QUEUE)
                    return
                ok, result_key, _ = AdminService.review_submission_with_template(
                    call.from_user.id,
                    submission_id,
                    template_code,
                    language=UserService.get_language(call.from_user.id),
                )
                bot.answer_callback_query(call.id, UserService.t(call.from_user.id, result_key), show_alert=False)
                if ok:
                    render_screen(bot, call, SCREEN_ADMIN_QUEUE, notice_key=result_key)
                else:
                    render_screen(bot, call, admin_submission_screen_key(submission_id), notice_key=result_key)
                return

            if parsed.action == 'admin_note_start':
                if not _ensure_admin(bot, call):
                    return
                parts = (parsed.value or '').split(':', 1)
                submission_id = _safe_int(parts[0]) if parts else None
                target_user_id = _safe_int(parts[1]) if len(parts) > 1 else None
                if submission_id is None or target_user_id is None:
                    bot.answer_callback_query(call.id)
                    render_screen(bot, call, SCREEN_ADMIN_QUEUE)
                    return
                InputSessionService.set_session(call.from_user.id, 'admin_add_note', f'{submission_id}:{target_user_id}')
                bot.answer_callback_query(call.id)
                render_screen(bot, call, admin_submission_screen_key(submission_id), notice_key='admin_note_prompt')
                return

            if parsed.action == 'admin_submission':
                if not _ensure_admin(bot, call):
                    return
                bot.answer_callback_query(call.id)
                submission_id = _safe_int(parsed.value)
                if submission_id is None:
                    render_screen(bot, call, SCREEN_ADMIN_QUEUE)
                    return
                render_screen(bot, call, admin_submission_screen_key(submission_id))
                return
    
            if parsed.action == 'admin_approve':
                if not _ensure_admin(bot, call):
                    return
                submission_id = _safe_int(parsed.value)
                if submission_id is None:
                    bot.answer_callback_query(call.id)
                    render_screen(bot, call, SCREEN_ADMIN_QUEUE)
                    return
                ok, result_key, _ = AdminService.review_submission(call.from_user.id, submission_id, approve=True)
                bot.answer_callback_query(call.id, UserService.t(call.from_user.id, result_key), show_alert=False)
                if ok:
                    render_screen(bot, call, SCREEN_ADMIN_QUEUE, notice_key=result_key)
                else:
                    render_screen(bot, call, admin_submission_screen_key(submission_id), notice_key=result_key)
                return
    
            if parsed.action == 'admin_reject_start':
                if not _ensure_admin(bot, call):
                    return
                submission_id = _safe_int(parsed.value)
                if submission_id is None:
                    bot.answer_callback_query(call.id)
                    render_screen(bot, call, SCREEN_ADMIN_QUEUE)
                    return
                InputSessionService.set_session(call.from_user.id, 'admin_reject_submission', str(submission_id))
                bot.answer_callback_query(call.id)
                render_screen(bot, call, admin_reject_screen_key(submission_id))
                return
    
            if parsed.action == 'admin_block':
                if not _ensure_admin(bot, call):
                    return
                target_user_id = _safe_int(parsed.value)
                if target_user_id is None:
                    bot.answer_callback_query(call.id)
                    render_screen(bot, call, SCREEN_ADMIN_QUEUE)
                    return
                ok, result_key = AdminService.set_user_blocked(call.from_user.id, target_user_id, True)
                bot.answer_callback_query(call.id, UserService.t(call.from_user.id, result_key), show_alert=False)
                render_screen(bot, call, SCREEN_ADMIN_QUEUE, notice_key=result_key)
                return
    
            if parsed.action == 'admin_unblock':
                if not _ensure_admin(bot, call):
                    return
                target_user_id = _safe_int(parsed.value)
                if target_user_id is None:
                    bot.answer_callback_query(call.id)
                    render_screen(bot, call, SCREEN_ADMIN_QUEUE)
                    return
                ok, result_key = AdminService.set_user_blocked(call.from_user.id, target_user_id, False)
                bot.answer_callback_query(call.id, UserService.t(call.from_user.id, result_key), show_alert=False)
                render_screen(bot, call, SCREEN_ADMIN_QUEUE, notice_key=result_key)
                return
    
            if parsed.action == 'admin_adjust_risk_start':
                if not _ensure_admin(bot, call):
                    return
                target_user_id = _safe_int(parsed.value)
                if target_user_id is None:
                    bot.answer_callback_query(call.id)
                    render_screen(bot, call, SCREEN_ADMIN_QUEUE)
                    return
                InputSessionService.set_session(call.from_user.id, 'admin_adjust_risk', str(target_user_id))
                bot.answer_callback_query(call.id)
                render_screen(bot, call, admin_risk_screen_key(target_user_id))
                return
    
            if parsed.action == 'admin_adjust_balance_start':
                if not _ensure_admin(bot, call):
                    return
                target_user_id = _safe_int(parsed.value)
                if target_user_id is None:
                    bot.answer_callback_query(call.id)
                    render_screen(bot, call, SCREEN_ADMIN_QUEUE)
                    return
                InputSessionService.set_session(call.from_user.id, 'admin_adjust_balance', str(target_user_id))
                bot.answer_callback_query(call.id)
                render_screen(bot, call, admin_balance_screen_key(target_user_id))
                return
    
            if parsed.action == 'admin_required_chats_add_start':
                if not _ensure_owner(bot, call):
                    return
                InputSessionService.set_session(call.from_user.id, 'admin_add_required_chat', 'new')
                bot.answer_callback_query(call.id)
                render_screen(bot, call, SCREEN_ADMIN_REQUIRED_CHAT_ADD)
                return

            if parsed.action == 'admin_required_chats_remove':
                if not _ensure_owner(bot, call):
                    return
                required_chat_id = _safe_int(parsed.value)
                if required_chat_id is None:
                    bot.answer_callback_query(call.id)
                    render_screen(bot, call, SCREEN_ADMIN_REQUIRED_CHATS)
                    return
                ok, result_key = SubscriptionService.remove_required_chat(required_chat_id)
                bot.answer_callback_query(call.id, UserService.t(call.from_user.id, result_key), show_alert=False)
                render_screen(bot, call, SCREEN_ADMIN_REQUIRED_CHATS, notice_key=result_key)
                return

            bot.answer_callback_query(call.id)
        except Exception:
            logger.exception('Callback handling failed for user %s data=%s', call.from_user.id, call.data)
            try:
                bot.answer_callback_query(call.id, UserService.t(call.from_user.id, 'generic_ui_error'), show_alert=False)
            except Exception:
                pass
            try:
                render_entry(bot, call)
            except Exception:
                pass
