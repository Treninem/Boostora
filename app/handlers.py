from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message

from app.config import Config
from app.db import Database
from app.i18n import CURRENCY, ROLE_ADVERTISER, ROLE_EARNER, SUPPORTED_LANGUAGES, normalize_locale, role_label, t, tier_label
from app.keyboards import campaign_keyboard, campaigns_keyboard, language_keyboard, menu_keyboard, role_keyboard, simple_back_keyboard, task_keyboard, tasks_keyboard, topup_keyboard
from app.subscriptions import pass_subscription_gate
from app.ui import render_panel

router = Router()


def locale_for(user, config: Config) -> str:
    if user:
        return normalize_locale(user['locale'], config.default_language)
    return normalize_locale(config.default_language, 'en')


def currency(locale: str) -> str:
    return CURRENCY.get(locale, CURRENCY['en'])


async def show_main(event: Message | CallbackQuery, db: Database, config: Config) -> None:
    user = db.get_user(event.from_user.id)
    locale = locale_for(user, config)
    if not user or not user['locale']:
        await render_panel(event, db, t(config.default_language, 'choose_language'), language_keyboard())
        return
    if not user['role']:
        text = t(locale, 'welcome', brand=config.brand_name) + '\n\n' + t(locale, 'choose_role')
        await render_panel(event, db, text, role_keyboard(locale))
        return
    if not await pass_subscription_gate(event, db, config):
        return
    text = (t(locale, 'menu_advertiser') if user['role'] == ROLE_ADVERTISER else t(locale, 'menu_earner')) + '\n\n' + t(locale, 'menu_hint')
    await render_panel(event, db, text, menu_keyboard(locale, user['role'], bool(user['is_admin'])))


async def ensure_user(message_or_callback: Message | CallbackQuery, db: Database, config: Config) -> None:
    u = message_or_callback.from_user
    db.upsert_user(u.id, u.username, u.first_name, u.id in config.admin_ids)


@router.message(CommandStart())
async def start(message: Message, db: Database, config: Config) -> None:
    await ensure_user(message, db, config)
    await show_main(message, db, config)


@router.message(Command('menu'))
async def menu_cmd(message: Message, db: Database, config: Config) -> None:
    await ensure_user(message, db, config)
    await show_main(message, db, config)


@router.message(Command('help'))
async def help_cmd(message: Message, db: Database, config: Config) -> None:
    await ensure_user(message, db, config)
    user = db.get_user(message.from_user.id)
    locale = locale_for(user, config)
    if not await pass_subscription_gate(message, db, config):
        return
    await render_panel(message, db, t(locale, 'support_text', support=config.support_username), simple_back_keyboard(locale))


@router.callback_query(F.data.startswith('lang:'))
async def choose_language(callback: CallbackQuery, db: Database, config: Config) -> None:
    await ensure_user(callback, db, config)
    locale = callback.data.split(':', 1)[1]
    if locale not in SUPPORTED_LANGUAGES:
        locale = config.default_language
    db.set_locale(callback.from_user.id, locale)
    await callback.answer(t(locale, 'language_saved'))
    await show_main(callback, db, config)


@router.callback_query(F.data.startswith('role:'))
async def choose_role(callback: CallbackQuery, db: Database, config: Config) -> None:
    await ensure_user(callback, db, config)
    role = callback.data.split(':', 1)[1]
    if role not in {ROLE_EARNER, ROLE_ADVERTISER}:
        await callback.answer()
        return
    db.set_role(callback.from_user.id, role)
    user = db.get_user(callback.from_user.id)
    locale = locale_for(user, config)
    await callback.answer(t(locale, 'role_saved'))
    await show_main(callback, db, config)


@router.callback_query(F.data == 'sub:check')
async def sub_check(callback: CallbackQuery, db: Database, config: Config) -> None:
    await ensure_user(callback, db, config)
    user = db.get_user(callback.from_user.id)
    locale = locale_for(user, config)
    if await pass_subscription_gate(callback, db, config):
        await callback.answer(t(locale, 'subscription_ok'))
        await show_main(callback, db, config)
    else:
        await callback.answer()


async def show_profile(event: Message | CallbackQuery, db: Database, config: Config) -> None:
    if not await pass_subscription_gate(event, db, config):
        return
    user = db.get_user(event.from_user.id)
    locale = locale_for(user, config)
    text = t(locale, 'profile_text', user_id=user['user_id'], language=SUPPORTED_LANGUAGES.get(locale, locale), role=role_label(locale, user['role']), tier=tier_label(locale, user['tier']), completed=int(user['completed_tasks']))
    await render_panel(event, db, text, simple_back_keyboard(locale))


async def show_wallet(event: Message | CallbackQuery, db: Database, config: Config) -> None:
    if not await pass_subscription_gate(event, db, config):
        return
    user = db.get_user(event.from_user.id)
    locale = locale_for(user, config)
    wallet = db.get_wallet(event.from_user.id)
    text = t(locale, 'wallet_text', available=wallet['available'], hold=wallet['hold'], earned=wallet['earned_total'], currency=currency(locale))
    await render_panel(event, db, text, simple_back_keyboard(locale))


async def show_tasks(event: Message | CallbackQuery, db: Database, config: Config) -> None:
    if not await pass_subscription_gate(event, db, config):
        return
    user = db.get_user(event.from_user.id)
    locale = locale_for(user, config)
    claimed_ids = db.user_claimed_ids(event.from_user.id)
    tasks = [dict(r) for r in db.list_available_tasks() if int(r['id']) not in claimed_ids]
    if not tasks:
        await render_panel(event, db, t(locale, 'no_tasks'), simple_back_keyboard(locale))
        return
    await render_panel(event, db, t(locale, 'tasks_text'), tasks_keyboard(locale, tasks[:10]))


async def show_rewards(event: Message | CallbackQuery, db: Database, config: Config) -> None:
    if not await pass_subscription_gate(event, db, config):
        return
    user = db.get_user(event.from_user.id)
    locale = locale_for(user, config)
    await render_panel(event, db, t(locale, 'rewards_text'), simple_back_keyboard(locale))


async def show_campaigns(event: Message | CallbackQuery, db: Database, config: Config) -> None:
    if not await pass_subscription_gate(event, db, config):
        return
    user = db.get_user(event.from_user.id)
    locale = locale_for(user, config)
    rows = [dict(r) for r in db.list_user_campaigns(event.from_user.id)]
    text = t(locale, 'campaigns_text')
    if not rows:
        text += '\n\n' + t(locale, 'no_campaigns')
    await render_panel(event, db, text, campaigns_keyboard(locale, rows))


async def show_analytics(event: Message | CallbackQuery, db: Database, config: Config) -> None:
    if not await pass_subscription_gate(event, db, config):
        return
    user = db.get_user(event.from_user.id)
    locale = locale_for(user, config)
    stats = db.advertiser_stats(event.from_user.id)
    await render_panel(event, db, t(locale, 'analytics_text', **stats), simple_back_keyboard(locale))


async def show_topup(event: Message | CallbackQuery, db: Database, config: Config) -> None:
    if not await pass_subscription_gate(event, db, config):
        return
    user = db.get_user(event.from_user.id)
    locale = locale_for(user, config)
    await render_panel(event, db, t(locale, 'topup_text'), topup_keyboard(locale))


async def show_support(event: Message | CallbackQuery, db: Database, config: Config) -> None:
    if not await pass_subscription_gate(event, db, config):
        return
    user = db.get_user(event.from_user.id)
    locale = locale_for(user, config)
    await render_panel(event, db, t(locale, 'support_text', support=config.support_username), simple_back_keyboard(locale))


async def show_admin(event: Message | CallbackQuery, db: Database, config: Config) -> None:
    user = db.get_user(event.from_user.id)
    locale = locale_for(user, config)
    if not user or not user['is_admin']:
        if isinstance(event, CallbackQuery):
            await event.answer(t(locale, 'access_denied'), show_alert=True)
        else:
            await render_panel(event, db, t(locale, 'access_denied'), simple_back_keyboard(locale))
        return
    if not await pass_subscription_gate(event, db, config):
        return
    await render_panel(event, db, t(locale, 'admin_text', **db.admin_stats()), simple_back_keyboard(locale))


@router.callback_query(F.data == 'menu:main')
async def menu_main(callback: CallbackQuery, db: Database, config: Config) -> None:
    await callback.answer()
    await show_main(callback, db, config)


@router.callback_query(F.data == 'menu:profile')
async def menu_profile(callback: CallbackQuery, db: Database, config: Config) -> None:
    await callback.answer()
    await show_profile(callback, db, config)


@router.callback_query(F.data == 'menu:wallet')
async def menu_wallet(callback: CallbackQuery, db: Database, config: Config) -> None:
    await callback.answer()
    await show_wallet(callback, db, config)


@router.callback_query(F.data == 'menu:tasks')
async def menu_tasks(callback: CallbackQuery, db: Database, config: Config) -> None:
    await callback.answer()
    await show_tasks(callback, db, config)


@router.callback_query(F.data == 'menu:rewards')
async def menu_rewards(callback: CallbackQuery, db: Database, config: Config) -> None:
    await callback.answer()
    await show_rewards(callback, db, config)


@router.callback_query(F.data == 'menu:campaigns')
async def menu_campaigns(callback: CallbackQuery, db: Database, config: Config) -> None:
    await callback.answer()
    await show_campaigns(callback, db, config)


@router.callback_query(F.data == 'menu:analytics')
async def menu_analytics(callback: CallbackQuery, db: Database, config: Config) -> None:
    await callback.answer()
    await show_analytics(callback, db, config)


@router.callback_query(F.data == 'menu:topup')
async def menu_topup(callback: CallbackQuery, db: Database, config: Config) -> None:
    await callback.answer()
    await show_topup(callback, db, config)


@router.callback_query(F.data == 'menu:support')
async def menu_support(callback: CallbackQuery, db: Database, config: Config) -> None:
    await callback.answer()
    await show_support(callback, db, config)


@router.callback_query(F.data == 'menu:admin')
async def menu_admin(callback: CallbackQuery, db: Database, config: Config) -> None:
    await callback.answer()
    await show_admin(callback, db, config)


@router.callback_query(F.data.startswith('task:view:'))
async def task_view(callback: CallbackQuery, db: Database, config: Config) -> None:
    if not await pass_subscription_gate(callback, db, config):
        return
    campaign_id = int(callback.data.split(':', 2)[2])
    campaign = db.get_campaign(campaign_id)
    if not campaign:
        await callback.answer()
        return
    user = db.get_user(callback.from_user.id)
    locale = locale_for(user, config)
    taken = campaign_id in db.user_claimed_ids(callback.from_user.id)
    text = t(locale, 'task_card', id=campaign['id'], title=campaign['title'], reward=campaign['reward'], currency=currency(locale))
    await callback.answer()
    await render_panel(callback, db, text, task_keyboard(locale, campaign_id, campaign['target_url'], taken))


@router.callback_query(F.data.startswith('task:take:'))
async def task_take(callback: CallbackQuery, db: Database, config: Config) -> None:
    if not await pass_subscription_gate(callback, db, config):
        return
    campaign_id = int(callback.data.split(':', 2)[2])
    ok = db.take_task(campaign_id, callback.from_user.id)
    campaign = db.get_campaign(campaign_id)
    user = db.get_user(callback.from_user.id)
    locale = locale_for(user, config)
    await callback.answer(t(locale, 'task_taken') if ok else t(locale, 'already_taken'))
    if not campaign:
        await show_tasks(callback, db, config)
        return
    text = t(locale, 'task_card', id=campaign['id'], title=campaign['title'], reward=campaign['reward'], currency=currency(locale))
    text += '\n\n' + (t(locale, 'task_taken') if ok else t(locale, 'already_taken'))
    await render_panel(callback, db, text, task_keyboard(locale, campaign_id, campaign['target_url'], True))


@router.callback_query(F.data.startswith('task:done:'))
async def task_done(callback: CallbackQuery, db: Database, config: Config) -> None:
    if not await pass_subscription_gate(callback, db, config):
        return
    campaign_id = int(callback.data.split(':', 2)[2])
    ok = db.complete_task(campaign_id, callback.from_user.id)
    user = db.get_user(callback.from_user.id)
    locale = locale_for(user, config)
    await callback.answer(t(locale, 'task_completed') if ok else t(locale, 'unknown'))
    await render_panel(callback, db, t(locale, 'task_completed') if ok else t(locale, 'unknown'), simple_back_keyboard(locale, 'menu:tasks'))


@router.callback_query(F.data == 'camp:create')
async def create_campaign(callback: CallbackQuery, db: Database, config: Config) -> None:
    if not await pass_subscription_gate(callback, db, config):
        return
    db.create_demo_campaign_for_user(callback.from_user.id)
    user = db.get_user(callback.from_user.id)
    locale = locale_for(user, config)
    await callback.answer(t(locale, 'campaign_created'))
    await show_campaigns(callback, db, config)


@router.callback_query(F.data.startswith('camp:view:'))
async def camp_view(callback: CallbackQuery, db: Database, config: Config) -> None:
    if not await pass_subscription_gate(callback, db, config):
        return
    campaign_id = int(callback.data.split(':', 2)[2])
    campaign = db.get_campaign(campaign_id)
    if not campaign:
        await callback.answer()
        return
    user = db.get_user(callback.from_user.id)
    locale = locale_for(user, config)
    text = t(locale, 'campaign_card', id=campaign['id'], title=campaign['title'], reward=campaign['reward'], completed=campaign['completed_slots'], total=campaign['total_slots'], currency=currency(locale))
    await callback.answer()
    await render_panel(callback, db, text, campaign_keyboard(locale))


@router.callback_query(F.data == 'wallet:topup')
async def wallet_topup(callback: CallbackQuery, db: Database, config: Config) -> None:
    db.topup_wallet(callback.from_user.id, 500)
    user = db.get_user(callback.from_user.id)
    locale = locale_for(user, config)
    await callback.answer(t(locale, 'topup_done'))
    await show_wallet(callback, db, config)


@router.message(Command('profile'))
async def cmd_profile(message: Message, db: Database, config: Config) -> None:
    await ensure_user(message, db, config)
    await show_profile(message, db, config)


@router.message(Command('wallet'))
async def cmd_wallet(message: Message, db: Database, config: Config) -> None:
    await ensure_user(message, db, config)
    await show_wallet(message, db, config)


@router.message(Command('tasks'))
async def cmd_tasks(message: Message, db: Database, config: Config) -> None:
    await ensure_user(message, db, config)
    await show_tasks(message, db, config)


@router.message(Command('campaigns'))
async def cmd_campaigns(message: Message, db: Database, config: Config) -> None:
    await ensure_user(message, db, config)
    await show_campaigns(message, db, config)


@router.message(Command('admin'))
async def cmd_admin(message: Message, db: Database, config: Config) -> None:
    await ensure_user(message, db, config)
    await show_admin(message, db, config)


@router.message()
async def fallback(message: Message, db: Database, config: Config) -> None:
    await ensure_user(message, db, config)
    await show_main(message, db, config)
