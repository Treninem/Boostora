
from __future__ import annotations

from uuid import uuid4

from aiogram import F, Router
from aiogram.types import CallbackQuery, LabeledPrice, Message, PreCheckoutQuery

from app.core.i18n import get_currency_name, normalize_locale, t
from app.core.monetization import get_topup_pack, get_vip_pack
from app.keyboards.start import advertiser_menu, earner_menu
from app.storage.billing import BillingRepository
from app.storage.memberships import MembershipRepository
from app.storage.users import UserRepository
from app.storage.wallets import WalletRepository

router = Router(name='payments')


async def _users(message_or_callback: Message | CallbackQuery | PreCheckoutQuery) -> UserRepository:
    return message_or_callback.bot['users_repo']


async def _wallets(message_or_callback: Message | CallbackQuery | PreCheckoutQuery) -> WalletRepository:
    return message_or_callback.bot['wallets_repo']


async def _memberships(message_or_callback: Message | CallbackQuery | PreCheckoutQuery) -> MembershipRepository:
    return message_or_callback.bot['memberships_repo']


async def _billing(message_or_callback: Message | CallbackQuery | PreCheckoutQuery) -> BillingRepository:
    return message_or_callback.bot['billing_repo']


async def _context(message_or_callback: Message | CallbackQuery | PreCheckoutQuery) -> tuple[dict, str]:
    users_repo = await _users(message_or_callback)
    user_id = message_or_callback.from_user.id if message_or_callback.from_user else 0
    user = await users_repo.get_user(user_id)
    locale = normalize_locale((user or {}).get('locale'))
    return user or {}, locale


@router.callback_query(F.data.startswith('billing:topup:'))
async def create_topup_invoice(callback: CallbackQuery) -> None:
    user, locale = await _context(callback)
    if not user:
        await callback.answer()
        return
    pack_code = callback.data.rsplit(':', 1)[1]
    pack = get_topup_pack(pack_code)
    if not pack:
        await callback.answer(t(locale, 'error_generic'), show_alert=True)
        return

    payload = f'topup:{pack.code}:{uuid4().hex[:12]}'
    billing_repo = await _billing(callback)
    await billing_repo.create_order(
        user_id=int(user['user_id']),
        purpose='topup',
        payload=payload,
        amount_xtr=pack.xtr_amount,
        credit_amount=pack.credit_amount,
        details={'pack_code': pack.code},
    )

    await callback.bot.send_invoice(
        chat_id=int(user['user_id']),
        title=t(locale, pack.title_key),
        description=t(locale, pack.desc_key, credits=pack.credit_amount),
        payload=payload,
        currency='XTR',
        provider_token='',
        prices=[LabeledPrice(label=t(locale, 'invoice_label_xtr'), amount=pack.xtr_amount)],
        start_parameter=f'topup_{pack.code}',
    )
    await callback.answer(t(locale, 'billing_invoice_sent'))


@router.callback_query(F.data.startswith('billing:vip:'))
async def create_vip_invoice(callback: CallbackQuery) -> None:
    user, locale = await _context(callback)
    if not user:
        await callback.answer()
        return
    pack_code = callback.data.rsplit(':', 1)[1]
    pack = get_vip_pack(pack_code)
    if not pack:
        await callback.answer(t(locale, 'error_generic'), show_alert=True)
        return

    payload = f'vip:{pack.code}:{uuid4().hex[:12]}'
    billing_repo = await _billing(callback)
    await billing_repo.create_order(
        user_id=int(user['user_id']),
        purpose='vip',
        payload=payload,
        amount_xtr=pack.xtr_amount,
        credit_amount=0,
        details={'pack_code': pack.code, 'duration_days': pack.duration_days},
    )

    await callback.bot.send_invoice(
        chat_id=int(user['user_id']),
        title=t(locale, pack.title_key),
        description=t(locale, pack.desc_key, days=pack.duration_days),
        payload=payload,
        currency='XTR',
        provider_token='',
        prices=[LabeledPrice(label=t(locale, 'invoice_label_xtr'), amount=pack.xtr_amount)],
        start_parameter=f'vip_{pack.code}',
    )
    await callback.answer(t(locale, 'billing_invoice_sent'))


@router.pre_checkout_query()
async def approve_pre_checkout(pre_checkout_query: PreCheckoutQuery) -> None:
    billing_repo = await _billing(pre_checkout_query)
    order = await billing_repo.get_order_by_payload(pre_checkout_query.invoice_payload)
    if not order or str(order.get('status')) != 'created':
        await pre_checkout_query.answer(ok=False, error_message='Order is not available anymore.')
        return
    await pre_checkout_query.answer(ok=True)


@router.message(F.successful_payment)
async def handle_successful_payment(message: Message) -> None:
    if not message.successful_payment:
        return
    user, locale = await _context(message)
    if not user:
        return
    billing_repo = await _billing(message)
    wallets_repo = await _wallets(message)
    memberships_repo = await _memberships(message)
    payload = message.successful_payment.invoice_payload
    order = await billing_repo.get_order_by_payload(payload)
    if not order or str(order.get('status')) == 'paid':
        return

    purpose = str(order.get('purpose') or '')
    if purpose == 'topup':
        credit_amount = int(order.get('credit_amount', 0) or 0)
        await wallets_repo.add_available(
            int(user['user_id']),
            credit_amount,
            'topup_confirmed',
            description=t(locale, 'payment_success_topup_ledger', amount=credit_amount, currency=get_currency_name(locale)),
            meta={'xtr': int(order.get('amount_xtr', 0) or 0), 'payload': payload},
        )
        success_text = t(locale, 'payment_success_topup', amount=credit_amount, currency=get_currency_name(locale))
        reply_markup = advertiser_menu(locale)
    elif purpose == 'vip':
        pack_code = payload.split(':', 2)[1]
        pack = get_vip_pack(pack_code)
        if not pack:
            return
        await memberships_repo.activate_membership(
            int(user['user_id']),
            'vip',
            pack.duration_days,
            source='xtr_payment',
            meta={'payload': payload, 'amount_xtr': int(order.get('amount_xtr', 0) or 0), 'pack_code': pack_code},
        )
        success_text = t(locale, 'payment_success_vip', days=pack.duration_days)
        reply_markup = earner_menu(locale)
    else:
        return

    await billing_repo.mark_paid(
        payload,
        telegram_charge_id=message.successful_payment.telegram_payment_charge_id,
        provider_charge_id=message.successful_payment.provider_payment_charge_id,
        details={'currency': message.successful_payment.currency, 'total_amount': message.successful_payment.total_amount},
    )
    await message.answer(success_text, reply_markup=reply_markup)
