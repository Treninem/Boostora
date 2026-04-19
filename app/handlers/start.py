from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message

from app.core.branding import send_banner
from app.core.i18n import get_currency_name, get_locale_name, normalize_locale, t
from app.keyboards.start import advertiser_menu, earner_menu, language_keyboard, role_keyboard
from app.keyboards.support import support_keyboard
from app.keyboards.subscription import subscription_required_keyboard
from app.storage.campaigns import CampaignRepository
from app.storage.referrals import ReferralRepository
from app.storage.users import UserRepository

router = Router(name='start')


async def _users(message_or_callback: Message | CallbackQuery) -> UserRepository:
    return message_or_callback.bot['users_repo']


async def _campaigns(message_or_callback: Message | CallbackQuery) -> CampaignRepository:
    return message_or_callback.bot['campaigns_repo']


async def _referrals(message_or_callback: Message | CallbackQuery) -> ReferralRepository:
    return message_or_callback.bot['referrals_repo']


def _support_url(message_or_callback: Message | CallbackQuery) -> str | None:
    support_username = str(message_or_callback.bot['settings'].support_username or '').strip()
    if not support_username:
        return None
    if support_username.startswith('https://') or support_username.startswith('http://'):
        return support_username
    if support_username.startswith('@'):
        return f'https://t.me/{support_username[1:]}'
    return f'https://t.me/{support_username}'


def _welcome_picker_text(brand: str) -> str:
    return (
        f"<b>{brand}</b>\n\n"
        "Telegram growth marketplace with a clean, multilingual UX.\n\n"
        "Русский • English • Deutsch • Español • Português • Türkçe\n\n"
        "Choose your language below."
    )


def _main_menu(locale: str, role: str | None):
    return advertiser_menu(locale) if role == 'advertiser' else earner_menu(locale)


def _support_center_text(locale: str, brand: str) -> str:
    return '\n'.join([
        f"<b>{t(locale, 'support_center_title', brand=brand)}</b>",
        t(locale, 'support_center_intro'),
        '',
        t(locale, 'support_center_points'),
    ])


def _support_page_text(locale: str, key: str, brand: str) -> str:
    return '\n'.join([
        f"<b>{t(locale, f'support_{key}_title', brand=brand)}</b>",
        t(locale, f'support_{key}_body', brand=brand),
    ])


def _role_intro(locale: str, role: str, brand: str) -> str:
    role_key = 'role_saved_advertiser' if role == 'advertiser' else 'role_saved_earner'
    intro_key = 'intro_advertiser_body' if role == 'advertiser' else 'intro_earner_body'
    title = t(locale, 'welcome_title', brand=brand)
    return '\n'.join([
        f"<b>{title}</b>",
        t(locale, role_key),
        '',
        t(locale, intro_key),
        '',
        t(locale, 'currency_label', currency=get_currency_name(locale)),
    ])



async def _resolve_locale(message_or_callback: Message | CallbackQuery) -> str:
    users_repo = await _users(message_or_callback)
    user = await users_repo.get_user(message_or_callback.from_user.id if message_or_callback.from_user else 0)
    locale = normalize_locale((user or {}).get('locale'))
    if (user or {}).get('locale'):
        return locale
    telegram_locale = ((message_or_callback.from_user.language_code or '') if message_or_callback.from_user else '').split('-', 1)[0].split('_', 1)[0].lower()
    return normalize_locale(telegram_locale or locale)


async def _show_post_subscription_entrypoint(callback: CallbackQuery, locale: str) -> None:
    users_repo = await _users(callback)
    user = await users_repo.get_user(callback.from_user.id if callback.from_user else 0)
    role = (user or {}).get('role')
    if callback.message is None:
        return
    if role not in {'advertiser', 'earner'}:
        await send_banner(
            callback.message,
            'welcome.png',
            _welcome_picker_text(callback.bot['settings'].brand_name),
            reply_markup=language_keyboard(),
        )
        return
    await callback.message.answer(
        t(locale, 'main_menu_advertiser') if role == 'advertiser' else t(locale, 'main_menu_earner'),
        reply_markup=_main_menu(locale, role),
    )


@router.message(CommandStart())
async def start_command(message: Message) -> None:
    users_repo = await _users(message)
    referrals_repo = await _referrals(message)
    user = message.from_user
    assert user is not None
    await users_repo.upsert_user(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        is_admin=user.id in message.bot['settings'].admin_ids,
    )

    payload = (message.text or '').split(maxsplit=1)
    if len(payload) > 1 and payload[1].isdigit():
        inviter_id = int(payload[1])
        linked = await referrals_repo.link_referral(inviter_id, user.id)
        if linked:
            await users_repo.increment_referrals(inviter_id)

    await send_banner(
        message,
        'welcome.png',
        _welcome_picker_text(message.bot['settings'].brand_name),
        reply_markup=language_keyboard(),
    )


@router.message(Command('help'))
async def help_command(message: Message) -> None:
    users_repo = await _users(message)
    user = await users_repo.get_user(message.from_user.id if message.from_user else 0)
    locale = normalize_locale((user or {}).get('locale'))
    await message.answer(
        _support_center_text(locale, message.bot['settings'].brand_name),
        reply_markup=support_keyboard(locale, _support_url(message)),
    )


@router.callback_query(F.data.startswith('lang:'))
async def select_language(callback: CallbackQuery) -> None:
    repo = await _users(callback)
    assert callback.from_user is not None
    locale = normalize_locale(callback.data.split(':', 1)[1])
    await repo.set_locale(callback.from_user.id, locale)
    text = (
        f"<b>{t(locale, 'welcome_title', brand=callback.bot['settings'].brand_name)}</b>\n\n"
        f"{t(locale, 'language_saved', language=get_locale_name(locale, locale))}\n"
        f"{t(locale, 'currency_label', currency=get_currency_name(locale))}\n\n"
        f"{t(locale, 'choose_role')}"
    )
    if callback.message:
        await callback.message.answer(text, reply_markup=role_keyboard(locale))
        try:
            await callback.message.delete()
        except Exception:
            pass
    await callback.answer()


@router.callback_query(F.data.startswith('role:'))
async def select_role(callback: CallbackQuery) -> None:
    users_repo = await _users(callback)
    campaigns_repo = await _campaigns(callback)
    assert callback.from_user is not None
    user = await users_repo.get_user(callback.from_user.id)
    locale = normalize_locale((user or {}).get('locale'))
    role = callback.data.split(':', 1)[1]
    await users_repo.set_role(callback.from_user.id, role)

    if role == 'advertiser':
        await campaigns_repo.seed_demo_campaigns(callback.from_user.id, locale)
        if callback.message:
            await send_banner(
                callback.message,
                'advertiser.png',
                _role_intro(locale, role, callback.bot['settings'].brand_name),
                reply_markup=advertiser_menu(locale),
            )
    else:
        if callback.message:
            await send_banner(
                callback.message,
                'earner.png',
                _role_intro(locale, role, callback.bot['settings'].brand_name),
                reply_markup=earner_menu(locale),
            )

    if callback.message:
        try:
            await callback.message.delete()
        except Exception:
            pass
    await callback.answer()



@router.callback_query(F.data == 'subscription:check')
async def subscription_check(callback: CallbackQuery) -> None:
    settings = callback.bot['settings']
    required_chat_id = int(settings.required_chat_id or 0)
    locale = await _resolve_locale(callback)
    if not required_chat_id:
        await callback.answer()
        return
    from app.core.subscription import is_user_subscribed
    is_member = await is_user_subscribed(callback.bot, callback.from_user.id if callback.from_user else 0, required_chat_id)
    if not is_member:
        text = '\n'.join([
            f"<b>{t(locale, 'sub_required_title', brand=settings.brand_name)}</b>",
            t(locale, 'sub_required_body'),
        ])
        if callback.message:
            await callback.message.answer(
                text,
                reply_markup=subscription_required_keyboard(locale, settings.required_chat_invite_link),
            )
        await callback.answer(t(locale, 'sub_not_verified'), show_alert=True)
        return

    await callback.answer(t(locale, 'sub_verified'), show_alert=True)
    await _show_post_subscription_entrypoint(callback, locale)


@router.callback_query(F.data == 'support:faq')
async def support_faq(callback: CallbackQuery) -> None:
    users_repo = await _users(callback)
    user = await users_repo.get_user(callback.from_user.id if callback.from_user else 0)
    locale = normalize_locale((user or {}).get('locale'))
    if callback.message:
        await callback.message.edit_text(
            _support_page_text(locale, 'faq', callback.bot['settings'].brand_name),
            reply_markup=support_keyboard(locale, _support_url(callback)),
        )
    await callback.answer()


@router.callback_query(F.data == 'support:safety')
async def support_safety(callback: CallbackQuery) -> None:
    users_repo = await _users(callback)
    user = await users_repo.get_user(callback.from_user.id if callback.from_user else 0)
    locale = normalize_locale((user or {}).get('locale'))
    if callback.message:
        await callback.message.edit_text(
            _support_page_text(locale, 'safety', callback.bot['settings'].brand_name),
            reply_markup=support_keyboard(locale, _support_url(callback)),
        )
    await callback.answer()


@router.callback_query(F.data == 'support:earn')
async def support_earn(callback: CallbackQuery) -> None:
    users_repo = await _users(callback)
    user = await users_repo.get_user(callback.from_user.id if callback.from_user else 0)
    locale = normalize_locale((user or {}).get('locale'))
    if callback.message:
        await callback.message.edit_text(
            _support_page_text(locale, 'earn', callback.bot['settings'].brand_name),
            reply_markup=support_keyboard(locale, _support_url(callback)),
        )
    await callback.answer()


@router.callback_query(F.data == 'support:promote')
async def support_promote(callback: CallbackQuery) -> None:
    users_repo = await _users(callback)
    user = await users_repo.get_user(callback.from_user.id if callback.from_user else 0)
    locale = normalize_locale((user or {}).get('locale'))
    if callback.message:
        await callback.message.edit_text(
            _support_page_text(locale, 'promote', callback.bot['settings'].brand_name),
            reply_markup=support_keyboard(locale, _support_url(callback)),
        )
    await callback.answer()


@router.callback_query(F.data == 'support:home')
async def support_home(callback: CallbackQuery) -> None:
    users_repo = await _users(callback)
    user = await users_repo.get_user(callback.from_user.id if callback.from_user else 0)
    locale = normalize_locale((user or {}).get('locale'))
    role = (user or {}).get('role')
    if callback.message:
        await callback.message.answer(
            t(locale, 'main_menu_advertiser') if role == 'advertiser' else t(locale, 'main_menu_earner'),
            reply_markup=_main_menu(locale, role),
        )
        try:
            await callback.message.delete()
        except Exception:
            pass
    await callback.answer()


@router.message(F.text)
async def fallback_menu(message: Message) -> None:
    users_repo = await _users(message)
    user = await users_repo.get_user(message.from_user.id if message.from_user else 0)
    locale = normalize_locale((user or {}).get('locale'))
    role = (user or {}).get('role')

    if message.text == t(locale, 'btn_change_language'):
        await send_banner(
            message,
            'welcome.png',
            _welcome_picker_text(message.bot['settings'].brand_name),
            reply_markup=language_keyboard(),
        )
        return

    if message.text == t(locale, 'menu_support'):
        await message.answer(
            _support_center_text(locale, message.bot['settings'].brand_name),
            reply_markup=support_keyboard(locale, _support_url(message)),
        )
        return

    if role == 'advertiser':
        await message.answer(t(locale, 'main_menu_advertiser'), reply_markup=advertiser_menu(locale))
        return
    if role == 'earner':
        await message.answer(t(locale, 'main_menu_earner'), reply_markup=earner_menu(locale))
        return

    await message.answer(t(locale, 'error_generic'))
