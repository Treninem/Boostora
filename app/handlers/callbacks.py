import telebot
from telebot.types import CallbackQuery

from app.router import (
    SCREEN_ADMIN,
    SCREEN_ADMIN_QUEUE,
    SCREEN_CAMPAIGN_CREATE,
    SCREEN_CAMPAIGN_PREVIEW,
    SCREEN_MAIN_MENU,
    SCREEN_REQUIRED_SUBSCRIPTION,
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
from app.services.campaigns import CampaignService
from app.services.client_campaigns import ClientCampaignService
from app.services.input_sessions import InputSessionService
from app.services.performer import PerformerService
from app.services.rewards import RewardService
from app.services.subscriptions import SubscriptionService
from app.services.ui_state import UIStateService
from app.services.users import UserService
from app.services.vip import VipService
from app.texts import ROLE_CLIENT, TEXTS
from app.utils.callbacks import parse_callback


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


def register_callback_handlers(bot: telebot.TeleBot) -> None:
    @bot.callback_query_handler(func=lambda call: True)
    def handle_callbacks(call: CallbackQuery) -> None:
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
            if not SubscriptionService.should_enforce_required_chat(call.message.chat.id):
                bot.answer_callback_query(call.id, UserService.t(call.from_user.id, 'subscription_not_required_here'))
                render_entry(bot, call)
                return
            if SubscriptionService.is_user_subscribed(bot, call.from_user.id):
                bot.answer_callback_query(call.id, UserService.t(call.from_user.id, 'subscription_success'))
                render_screen(bot, call, SCREEN_MAIN_MENU)
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
            if destination in {'language', 'role'}:
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
            InputSessionService.set_session(call.from_user.id, 'submit_proof', str(submission_id))
            bot.answer_callback_query(call.id)
            render_screen(bot, call, proof_wait_screen_key(submission_id))
            return

        if parsed.action == 'cancel_input':
            InputSessionService.clear_session(call.from_user.id)
            bot.answer_callback_query(call.id, UserService.t(call.from_user.id, 'proof_input_cancelled'))
            submission_id = _safe_int(parsed.value)
            if submission_id is None:
                render_screen(bot, call, SECTION_TO_SCREEN['tasks'], notice_key='proof_input_cancelled')
                return
            render_screen(bot, call, submission_screen_key(submission_id), notice_key='proof_input_cancelled')
            return

        if parsed.action == 'camp_new':
            if not _ensure_client_role(bot, call):
                return
            ClientCampaignService.clear_draft(call.from_user.id)
            bot.answer_callback_query(call.id)
            render_screen(bot, call, SCREEN_CAMPAIGN_CREATE)
            return

        if parsed.action == 'ctype':
            if not _ensure_client_role(bot, call):
                return
            ok, result_key = ClientCampaignService.start_draft(call.from_user.id, parsed.value)
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

        bot.answer_callback_query(call.id)
