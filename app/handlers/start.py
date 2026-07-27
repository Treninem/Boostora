import time

import telebot
from telebot import types
from telebot.types import Message, PreCheckoutQuery

from app.config import settings
from app.keyboards.reply import main_reply_keyboard
from app.services.activity import ActivityService
from app.services.bot_chats import BotChatService
from app.router import (
    SCREEN_ADMIN,
    SCREEN_ADMIN_QUEUE,
    SCREEN_ADMIN_REQUIRED_CHAT_ADD,
    SCREEN_ADMIN_REQUIRED_CHATS,
    SCREEN_CAMPAIGN_PREVIEW,
    SCREEN_COMMUNITY_RULES,
    SCREEN_TOPUP_CUSTOM,
    admin_balance_screen_key,
    admin_reject_screen_key,
    admin_risk_screen_key,
    admin_submission_screen_key,
    campaign_input_screen_key,
    proof_wait_screen_key,
    render_entry,
    render_screen,
    submission_screen_key,
)
from app.services.admin import AdminService
from app.services.ad_broadcasts import AdBroadcastService, MODE_CONFIRM as BROADCAST_MODE_CONFIRM, MODE_LINK as BROADCAST_MODE_LINK, MODE_TEXT as BROADCAST_MODE_TEXT
from app.services.client_campaigns import ClientCampaignService, MODE_PRICE, MODE_QUANTITY, MODE_REWARD, MODE_TARGET
from app.services.community_rules import CommunityRulesService
from app.services.legal_docs import LegalDocsService
from app.services.boostore_provider import BoostoreProviderService
from app.services.engagement_modes import EngagementModeService
from app.services.input_sessions import InputSessionService
from app.services.invoice_messages import InvoiceMessageService
from app.services.payments import BASE_SPARKS_PER_STAR, SPARKS_PACKS, VIP_STARS_PLANS, calculate_custom_stars_for_sparks, make_payload, parse_payload
from app.services.performer import PerformerService
from app.services.referrals import ReferralService
from app.services.subscriptions import SubscriptionService
from app.services.users import UserService
from app.services.vip import VipService
from app.services.wallets import WalletService
from app.version import APP_VERSION


_BOTTOM_KEYBOARD_SENT_AT: dict[int, float] = {}


def _try_delete_user_message(bot: telebot.TeleBot, message: Message) -> None:
    try:
        bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
    except Exception:
        return


def _ensure_bottom_keyboard(bot: telebot.TeleBot, chat_id: int, user_id: int, *, force: bool = False) -> None:
    # Reply keyboards stay attached to the chat after a message is sent.
    # To avoid chat clutter, refresh the bottom menu at most once per 10 minutes,
    # unless /start explicitly asks for a fresh keyboard.
    now = time.time()
    last_sent = _BOTTOM_KEYBOARD_SENT_AT.get(user_id, 0.0)
    if not force and now - last_sent < 600:
        return
    try:
        if settings.smart_bottom_menu == 'hidden' and not force:
            return
        bot.send_message(chat_id, UserService.t(user_id, 'bottom_nav_ready'), reply_markup=main_reply_keyboard(user_id))
        _BOTTOM_KEYBOARD_SENT_AT[user_id] = now
    except Exception:
        return


def _cancel_destination_for_session(user_id: int, session) -> str | None:
    if not session:
        return None
    mode = str(session['mode'] or '')
    if mode.startswith('broadcast_'):
        draft = AdBroadcastService.get_draft(user_id) or {}
        return 'admin' if draft.get('is_admin') else 'campaigns'
    if mode.startswith('campaign_'):
        return 'campaigns'
    if mode == 'topup_custom_sparks':
        return 'wallet'
    if mode == 'admin_add_required_chat':
        return SCREEN_ADMIN_REQUIRED_CHATS
    if mode in {'admin_reject_submission', 'admin_adjust_risk', 'admin_adjust_balance', 'admin_add_note'}:
        return SCREEN_ADMIN_QUEUE
    if mode == 'submit_proof' and session['payload']:
        return submission_screen_key(int(session['payload']))
    return None


def _extract_referrer_id(message: Message) -> int | None:
    text = (message.text or '').strip()
    parts = text.split(maxsplit=1)
    if len(parts) < 2:
        return None
    arg = parts[1].strip()
    if not arg.startswith('ref_'):
        return None
    raw_id = arg[4:].strip()
    if not raw_id.isdigit():
        return None
    return int(raw_id)


def _parse_signed_int(raw_value: str) -> int | None:
    value = raw_value.strip().replace(' ', '')
    if not value:
        return None
    if value[0] in '+-' and value[1:].isdigit():
        return int(value)
    if value.isdigit():
        return int(value)
    return None


def _is_cancel_text(text: str) -> bool:
    raw = (text or '').strip().lower()
    return raw in {'отмена', 'cancel', '/cancel', 'назад'}


def _delete_pending_invoice(bot: telebot.TeleBot, user_id: int) -> None:
    row = InvoiceMessageService.get(user_id)
    if not row:
        return
    try:
        bot.delete_message(chat_id=int(row['chat_id']), message_id=int(row['invoice_message_id']))
    except Exception:
        pass
    try:
        if row['helper_message_id'] is not None:
            bot.delete_message(chat_id=int(row['chat_id']), message_id=int(row['helper_message_id']))
    except Exception:
        pass
    InvoiceMessageService.clear(user_id)


def _send_direct_stars_invoice(bot: telebot.TeleBot, user_id: int, *, title: str, description: str, payload: str, amount_stars: int) -> tuple[bool, str]:
    prices = [types.LabeledPrice(label=title[:32], amount=int(amount_stars))]
    kind, code, owner_id = parse_payload(payload) or ('pay', 'invoice', user_id)
    from app.services.payments import make_start_parameter
    _delete_pending_invoice(bot, user_id)
    try:
        sent = bot.send_invoice(
            chat_id=user_id,
            title=title[:32],
            description=description[:255],
            invoice_payload=payload,
            provider_token='',
            currency='XTR',
            prices=prices,
            start_parameter=make_start_parameter(kind, code, owner_id),
        )
        try:
            InvoiceMessageService.set(user_id, int(sent.chat.id), int(sent.message_id))
        except Exception:
            pass
        return True, 'payment_invoice_sent'
    except Exception:
        return False, 'payment_invoice_failed'


def register_start_handlers(bot: telebot.TeleBot) -> None:
    @bot.message_handler(commands=['start'])
    def handle_start(message: Message) -> None:
        existing_user = UserService.get_user(message.from_user.id)
        referrer_id = _extract_referrer_id(message)
        referrer_exists = bool(referrer_id and referrer_id != message.from_user.id and UserService.get_user(referrer_id))
        referred_by = referrer_id if existing_user is None and referrer_exists else None
        UserService.ensure_user(message.from_user, referred_by_user_id=referred_by)
        start_arg = ((message.text or '').split(maxsplit=1)[1].strip() if len((message.text or '').split(maxsplit=1)) > 1 else '')
        bot_username = None
        try:
            me = bot.get_me()
            bot_username = f"@{me.username}" if getattr(me, 'username', None) else None
        except Exception:
            if settings.support_username.startswith('@'):
                bot_username = settings.support_username
        ActivityService.record_bot_start(message.from_user.id, start_arg, bot_username)
        if existing_user is None and referrer_exists and referrer_id is not None:
            ReferralService.try_bind_referral(referrer_id, message.from_user.id)
        InputSessionService.clear_session(message.from_user.id)
        _ensure_bottom_keyboard(bot, message.chat.id, message.from_user.id, force=True)
        render_entry(bot, message, force_language=True)


    @bot.message_handler(commands=['version'])
    def handle_version(message: Message) -> None:
        UserService.ensure_user(message.from_user)
        bot.reply_to(
            message,
            UserService.t(message.from_user.id, 'version_text', version=APP_VERSION),
            parse_mode='HTML',
        )

    @bot.message_handler(commands=['menu'])
    def handle_menu(message: Message) -> None:
        UserService.ensure_user(message.from_user)
        InputSessionService.clear_session(message.from_user.id)
        _ensure_bottom_keyboard(bot, message.chat.id, message.from_user.id)
        render_entry(bot, message)

    @bot.message_handler(commands=['cancel'])
    def handle_cancel(message: Message) -> None:
        UserService.ensure_user(message.from_user)
        InputSessionService.clear_session(message.from_user.id)
        _delete_pending_invoice(bot, message.from_user.id)
        _try_delete_user_message(bot, message)
        _ensure_bottom_keyboard(bot, message.chat.id, message.from_user.id)
        render_entry(bot, message)

    @bot.message_handler(commands=['admin'])
    def handle_admin(message: Message) -> None:
        UserService.ensure_user(message.from_user)
        InputSessionService.clear_session(message.from_user.id)
        if not UserService.is_admin(message.from_user.id):
            render_entry(bot, message)
            return
        render_screen(bot, message, SCREEN_ADMIN)

    @bot.pre_checkout_query_handler(func=lambda query: True)
    def handle_pre_checkout(query: PreCheckoutQuery) -> None:
        parsed = parse_payload(query.invoice_payload)
        if parsed is None:
            bot.answer_pre_checkout_query(query.id, ok=False, error_message='Неверный платёжный payload')
            return
        kind, code, user_id = parsed
        if user_id != query.from_user.id:
            bot.answer_pre_checkout_query(query.id, ok=False, error_message='Платёж предназначен другому пользователю')
            return
        bot.answer_pre_checkout_query(query.id, ok=True)


    @bot.message_handler(content_types=['web_app_data'])
    def handle_web_app_data(message: Message) -> None:
        UserService.ensure_user(message.from_user)
        ActivityService.record_web_app_data(message)
        render_screen(bot, message, 'tasks', notice_key='task_auto_verified')

    @bot.message_handler(content_types=['successful_payment'])
    def handle_successful_payment(message: Message) -> None:
        UserService.ensure_user(message.from_user)
        _delete_pending_invoice(bot, message.from_user.id)
        _try_delete_user_message(bot, message)
        payment = message.successful_payment
        parsed = parse_payload(payment.invoice_payload)
        if parsed is None:
            return
        kind, code, user_id = parsed
        if user_id != message.from_user.id:
            return
        if kind == 'sparks' and code in SPARKS_PACKS:
            pack = SPARKS_PACKS[code]
            WalletService.credit_internal_balance(
                message.from_user.id,
                pack.sparks,
                entry_type='stars_topup',
                note=f'Stars top up: {code}',
            )
            render_screen(bot, message, 'wallet', notice_text=UserService.t(message.from_user.id, 'stars_topup_success', amount=pack.sparks, internal_name=UserService.internal_currency_label(message.from_user.id)))
            return
        if kind == 'sparks_custom' and code.isdigit():
            sparks_amount = int(code)
            WalletService.credit_internal_balance(
                message.from_user.id,
                sparks_amount,
                entry_type='stars_topup',
                note=f'Stars custom top up: {sparks_amount}',
            )
            render_screen(bot, message, 'wallet', notice_text=UserService.t(message.from_user.id, 'stars_topup_success', amount=sparks_amount, internal_name=UserService.internal_currency_label(message.from_user.id)))
            return
        if kind == 'broadcast' and code.isdigit():
            order_id = int(code)
            ok, result_key = AdBroadcastService.activate_paid_order(order_id, message.from_user.id)
            if ok:
                sent, _failed = AdBroadcastService.dispatch_order(bot, order_id, support_username=settings.support_username)
                AdBroadcastService.clear_draft(message.from_user.id)
                render_screen(bot, message, 'campaigns', notice_text=UserService.t(message.from_user.id, 'broadcast_paid_sent_notice', sent=sent))
            else:
                render_screen(bot, message, 'broadcast_preview', notice_key=result_key)
            return
        if kind == 'vip' and code in VIP_STARS_PLANS:
            plan = VIP_STARS_PLANS[code]
            VipService.purchase_plan_with_stars(message.from_user.id, plan.plan_code)
            render_screen(bot, message, 'vip', notice_text=UserService.t(message.from_user.id, 'vip_stars_success'))
            return
        if kind == 'engpro' and code == '30d':
            EngagementModeService.activate_pro(message.from_user.id, days=30, source='stars_payment')
            render_screen(bot, message, 'engagement_growth', notice_text=UserService.t(message.from_user.id, 'engagement_pro_activated_notice'))
            return
        if kind == 'boostore' and code.isdigit():
            result = BoostoreProviderService.place_prepared_order(int(code))
            render_screen(bot, message, 'marketplace', notice_key='boostore_order_placed' if result.ok else result.result_key)
            return


    @bot.message_handler(func=lambda message: message.chat.type in {'group', 'supergroup'}, content_types=['text', 'photo', 'video', 'poll'])
    def handle_group_activity(message: Message) -> None:
        BotChatService.touch_from_message(message)
        ActivityService.record_group_or_channel_message(message)

    @bot.channel_post_handler(func=lambda message: True, content_types=['text', 'photo', 'video', 'poll'])
    def handle_channel_post(message: Message) -> None:
        BotChatService.touch_from_message(message)
        ActivityService.record_channel_post(message)

    @bot.chat_member_handler(func=lambda update: True)
    def handle_chat_member(update) -> None:
        ActivityService.record_chat_member(update)

    @bot.my_chat_member_handler(func=lambda update: True)
    def handle_my_chat_member(update) -> None:
        BotChatService.record_my_chat_member(update)

    @bot.message_reaction_handler(func=lambda update: True)
    def handle_message_reaction(update) -> None:
        ActivityService.record_reaction(update)

    @bot.poll_answer_handler(func=lambda update: True)
    def handle_poll_answer(update) -> None:
        ActivityService.record_poll_answer(update)

    @bot.message_handler(func=lambda message: True, content_types=['text'])
    def handle_fallback(message: Message) -> None:
        UserService.ensure_user(message.from_user)
        if message.chat.type in {'group', 'supergroup'}:
            ActivityService.record_group_or_channel_message(message)
            return
        if not UserService.can_access_bot(message.from_user.id) and not UserService.is_admin(message.from_user.id):
            _try_delete_user_message(bot, message)
            render_entry(bot, message)
            return

        if (not CommunityRulesService.is_accepted(message.from_user.id)
                and not UserService.is_admin(message.from_user.id)):
            text_value = (message.text or '').strip().lower()
            if text_value not in {'/start', '/menu', 'правила', '📜 правила'}:
                _try_delete_user_message(bot, message)
            render_screen(bot, message, SCREEN_COMMUNITY_RULES, notice_key='community_rules_required_notice')
            return

        if (not LegalDocsService.is_accepted(message.from_user.id)
                and not UserService.is_admin(message.from_user.id)):
            _try_delete_user_message(bot, message)
            render_screen(bot, message, 'legal_docs', notice_key='legal_docs_required_notice')
            return

        session = InputSessionService.get_session(message.from_user.id)
        if _is_cancel_text(message.text or ''):
            destination = _cancel_destination_for_session(message.from_user.id, session)
            InputSessionService.clear_session(message.from_user.id)
            _delete_pending_invoice(bot, message.from_user.id)
            _try_delete_user_message(bot, message)
            if destination:
                render_screen(bot, message, destination, notice_key='input_cancelled')
            else:
                render_entry(bot, message)
            return
        if session and str(session['mode']) == 'submit_proof' and session['payload']:
            submission_id = int(session['payload'])
            ok, result_key, _ = PerformerService.submit_proof(
                message.from_user.id,
                submission_id,
                message.text or '',
            )
            _try_delete_user_message(bot, message)
            if ok:
                InputSessionService.clear_session(message.from_user.id)
                render_screen(bot, message, submission_screen_key(submission_id), notice_key=result_key)
                return
            if result_key == 'proof_empty':
                render_screen(bot, message, proof_wait_screen_key(submission_id), notice_key=result_key)
                return
            render_screen(bot, message, submission_screen_key(submission_id), notice_key=result_key)
            return

        mode = str(session['mode']) if session else ''
        if mode == 'admin_reject_submission' and session and session['payload']:
            submission_id = int(session['payload'])
            _try_delete_user_message(bot, message)
            ok, result_key, _ = AdminService.review_submission(
                message.from_user.id,
                submission_id,
                approve=False,
                reject_reason=message.text or '',
            )
            if ok:
                InputSessionService.clear_session(message.from_user.id)
                render_screen(bot, message, SCREEN_ADMIN, notice_key=result_key)
            else:
                render_screen(bot, message, admin_reject_screen_key(submission_id), notice_key=result_key)
            return

        if mode == 'admin_adjust_risk' and session and session['payload']:
            target_user_id = int(session['payload'])
            _try_delete_user_message(bot, message)
            delta = _parse_signed_int(message.text or '')
            if delta is None:
                render_screen(bot, message, admin_risk_screen_key(target_user_id), notice_key='admin_numeric_delta_invalid')
                return
            ok, result_key, _ = AdminService.adjust_risk_score(
                message.from_user.id,
                target_user_id,
                delta,
                reason='manual_admin_input',
            )
            if ok:
                InputSessionService.clear_session(message.from_user.id)
                render_screen(bot, message, SCREEN_ADMIN_QUEUE, notice_key=result_key)
            else:
                render_screen(bot, message, admin_risk_screen_key(target_user_id), notice_key=result_key)
            return

        if mode == 'admin_add_note' and session and session['payload']:
            payload = str(session['payload'])
            parts = payload.split(':', 1)
            submission_id = int(parts[0]) if parts and parts[0].isdigit() else None
            target_user_id = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None
            _try_delete_user_message(bot, message)
            if submission_id is None or target_user_id is None:
                InputSessionService.clear_session(message.from_user.id)
                render_screen(bot, message, SCREEN_ADMIN_QUEUE, notice_key='admin_submission_not_found')
                return
            ok, result_key = AdminService.add_admin_note(
                message.from_user.id,
                target_user_id,
                message.text or '',
                related_submission_id=submission_id,
            )
            if ok:
                InputSessionService.clear_session(message.from_user.id)
            render_screen(bot, message, admin_submission_screen_key(submission_id), notice_key=result_key)
            return

        if mode == 'admin_adjust_balance' and session and session['payload']:
            target_user_id = int(session['payload'])
            _try_delete_user_message(bot, message)
            delta = _parse_signed_int(message.text or '')
            if delta is None:
                render_screen(bot, message, admin_balance_screen_key(target_user_id), notice_key='admin_numeric_delta_invalid')
                return
            ok, result_key, _ = AdminService.adjust_available_balance(
                message.from_user.id,
                target_user_id,
                delta,
                reason='manual_admin_input',
            )
            if ok:
                InputSessionService.clear_session(message.from_user.id)
                render_screen(bot, message, SCREEN_ADMIN_QUEUE, notice_key=result_key)
            else:
                render_screen(bot, message, admin_balance_screen_key(target_user_id), notice_key=result_key)
            return

        if mode == 'admin_add_required_chat':
            _try_delete_user_message(bot, message)
            if not UserService.is_owner(message.from_user.id):
                InputSessionService.clear_session(message.from_user.id)
                render_screen(bot, message, SCREEN_ADMIN, notice_key='admin_access_denied')
                return
            try:
                chat_ref, join_link = SubscriptionService.parse_admin_add_payload(message.text or '')
            except ValueError:
                render_screen(bot, message, SCREEN_ADMIN_REQUIRED_CHAT_ADD, notice_key='admin_required_chat_invalid')
                return
            ok, result_key = SubscriptionService.add_required_chat(chat_ref, join_link)
            if ok:
                InputSessionService.clear_session(message.from_user.id)
                render_screen(bot, message, SCREEN_ADMIN_REQUIRED_CHATS, notice_key=result_key)
            else:
                render_screen(bot, message, SCREEN_ADMIN_REQUIRED_CHAT_ADD, notice_key=result_key)
            return

        if mode == BROADCAST_MODE_TEXT:
            _try_delete_user_message(bot, message)
            ok, result_key = AdBroadcastService.consume_text(message.from_user.id, message.text or '')
            render_screen(bot, message, 'broadcast_link' if ok else 'broadcast_text', notice_key=result_key)
            return

        if mode == BROADCAST_MODE_LINK:
            _try_delete_user_message(bot, message)
            ok, result_key = AdBroadcastService.consume_link(message.from_user.id, message.text or '')
            render_screen(bot, message, 'broadcast_schedule' if ok else 'broadcast_link', notice_key=result_key)
            return

        if mode == 'boostore_order_link' and session and session['payload']:
            _try_delete_user_message(bot, message)
            link = (message.text or '').strip()
            if not (link.startswith('http://') or link.startswith('https://') or link.startswith('t.me/') or link.startswith('@')):
                render_screen(bot, message, 'marketplace', notice_key='boostore_order_link_invalid')
                return
            payload = {'external_service_id': str(session['payload']), 'link': link}
            InputSessionService.set_session(message.from_user.id, 'boostore_order_quantity', __import__('json').dumps(payload, ensure_ascii=False))
            render_screen(bot, message, 'marketplace', notice_key='boostore_order_quantity_prompt')
            return

        if mode == 'boostore_order_quantity' and session and session['payload']:
            _try_delete_user_message(bot, message)
            import json
            try:
                payload = json.loads(str(session['payload'] or '{}'))
            except Exception:
                payload = {}
            raw = (message.text or '').strip().replace(' ', '')
            if not raw.isdigit():
                render_screen(bot, message, 'marketplace', notice_key='boostore_order_quantity_invalid')
                return
            result = BoostoreProviderService.prepare_order(
                owner_user_id=message.from_user.id,
                external_service_id=str(payload.get('external_service_id') or ''),
                link=str(payload.get('link') or ''),
                quantity=int(raw),
            )
            if not result.ok:
                render_screen(bot, message, 'marketplace', notice_key=result.result_key)
                return
            order_id = int((result.data or {}).get('order_id') or 0) if isinstance(result.data, dict) else 0
            price = int((result.data or {}).get('price_stars') or 1) if isinstance(result.data, dict) else 1
            ok, notice_key = _send_direct_stars_invoice(
                bot,
                message.from_user.id,
                title=UserService.t(message.from_user.id, 'boostore_invoice_title'),
                description=UserService.t(message.from_user.id, 'boostore_invoice_desc', quantity=int(raw)),
                payload=make_payload('boostore', str(order_id), message.from_user.id),
                amount_stars=price,
            )
            if ok:
                InputSessionService.clear_session(message.from_user.id)
                render_screen(bot, message, 'marketplace', notice_key='payment_invoice_sent')
            else:
                render_screen(bot, message, 'marketplace', notice_key=notice_key or 'payment_invoice_failed')
            return

        if mode == 'topup_custom_sparks':
            _try_delete_user_message(bot, message)
            raw = (message.text or '').strip().replace(' ', '')
            if not raw.isdigit():
                render_screen(bot, message, SCREEN_TOPUP_CUSTOM, notice_key='topup_custom_invalid')
                return
            sparks_amount = int(raw)
            if sparks_amount < BASE_SPARKS_PER_STAR or sparks_amount > 100000:
                render_screen(bot, message, SCREEN_TOPUP_CUSTOM, notice_key='topup_custom_invalid')
                return
            stars_amount = calculate_custom_stars_for_sparks(sparks_amount)
            payload = make_payload('sparks_custom', str(sparks_amount), message.from_user.id)
            ok, notice_key = _send_direct_stars_invoice(
                bot,
                message.from_user.id,
                title=f"{sparks_amount} {UserService.internal_currency_label(message.from_user.id)}",
                description=UserService.t(message.from_user.id, 'topup_custom_invoice_desc', sparks=sparks_amount, stars=stars_amount, internal_name=UserService.internal_currency_label(message.from_user.id)),
                payload=payload,
                amount_stars=stars_amount,
            )
            if ok:
                InputSessionService.clear_session(message.from_user.id)
                render_screen(bot, message, 'wallet', notice_key='payment_invoice_sent')
            else:
                render_screen(bot, message, SCREEN_TOPUP_CUSTOM, notice_key=notice_key or 'payment_invoice_failed')
            return

        if mode.startswith('campaign_'):
            _try_delete_user_message(bot, message)
            if mode == MODE_TARGET:
                ok, result_key, _ = ClientCampaignService.consume_target(message.from_user.id, message.text or '', bot=bot)
                if ok:
                    render_screen(bot, message, campaign_input_screen_key('quantity'), notice_key=result_key)
                else:
                    render_screen(bot, message, campaign_input_screen_key('target'), notice_key=result_key)
                return
            if mode == MODE_QUANTITY:
                ok, result_key, _ = ClientCampaignService.consume_quantity(message.from_user.id, message.text or '')
                if ok:
                    render_screen(bot, message, campaign_input_screen_key('price'), notice_key=result_key)
                else:
                    render_screen(bot, message, campaign_input_screen_key('quantity'), notice_key=result_key)
                return
            if mode in {MODE_REWARD, MODE_PRICE}:
                ok, result_key, _ = ClientCampaignService.consume_price(message.from_user.id, message.text or '')
                if ok:
                    render_screen(bot, message, SCREEN_CAMPAIGN_PREVIEW, notice_key=result_key)
                else:
                    render_screen(bot, message, campaign_input_screen_key('price'), notice_key=result_key)
                return
            render_screen(bot, message, SCREEN_CAMPAIGN_PREVIEW)
            return

        text_value = (message.text or '').strip()
        text_map = {
            'Меню': lambda: render_entry(bot, message),
            '☰ Меню': lambda: render_entry(bot, message),
            '🚀 Центр': lambda: render_screen(bot, message, 'smart_hub'),
            '💰 Кошелёк': lambda: render_screen(bot, message, 'wallet'),
            '🧩 Витрина': lambda: render_screen(bot, message, 'marketplace'),
            '🔥 Продвижение': lambda: render_screen(bot, message, 'engagement_growth'),
            '📊 Мои 0/10': lambda: render_screen(bot, message, 'engagement_obligations'),
            '📜 Правила': lambda: render_screen(bot, message, SCREEN_COMMUNITY_RULES),
            'Правила': lambda: render_screen(bot, message, SCREEN_COMMUNITY_RULES),
            '⚙️ Админ': lambda: render_screen(bot, message, 'admin'),
            'Профиль': lambda: render_screen(bot, message, 'profile'),
            'Задания': lambda: render_screen(bot, message, 'tasks'),
            'Кошелёк👛': lambda: render_screen(bot, message, 'wallet'),
            'История': lambda: render_screen(bot, message, 'history'),
            'Создать задание': lambda: render_screen(bot, message, 'campaigns'),
            'Витрина': lambda: render_screen(bot, message, 'marketplace'),
            'Аналитика': lambda: render_screen(bot, message, 'stats'),
            'VIP': lambda: render_screen(bot, message, 'vip'),
            'Купить Искры✨': lambda: render_screen(bot, message, 'topup_packages'),
            'Обмен Искр': lambda: render_screen(bot, message, 'exchange'),
            'Искры✨ и обмен': lambda: render_screen(bot, message, 'exchange'),
            'Рефералы': lambda: render_screen(bot, message, 'referrals'),
        }
        action = text_map.get(text_value)
        if action is not None:
            _try_delete_user_message(bot, message)
            action()
            return

        render_entry(bot, message)
