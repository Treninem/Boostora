from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message

from app.config import Config
from app.db import Database
from app.helpers import main_menu_markup, main_menu_text, subscription_gate
from app.i18n import ROLE_ADVERTISER, ROLE_EARNER, SUPPORTED_LANGUAGES, normalize_locale, role_label, t, tier_label
from app.keyboards import (
    campaign_card_keyboard,
    campaigns_keyboard,
    language_keyboard,
    role_keyboard,
    simple_back_keyboard,
    task_card_keyboard,
    tasks_list_keyboard,
    topup_keyboard,
)
from app.ui import answer_or_edit

router = Router()


def current_locale(user, config: Config) -> str:
    if user:
        return normalize_locale(user['locale'], config.default_language)
    return normalize_locale(config.default_language, 'en')


async def render_main(event: Message | CallbackQuery, db: Database, config: Config) -> None:
    user = db.get_user(event.from_user.id)
    locale = current_locale(user, config)
    if not user or not user['locale']:
        await answer_or_edit(event, t(config.default_language, 'choose_language'), language_keyboard())
        return
    if not user['role']:
        await answer_or_edit(event, t(locale, 'welcome', brand=config.brand_name) + '\n\n' + t(locale, 'choose_role'), role_keyboard(locale))
        return
    if not await subscription_gate(event, db, config):
        return
    text = main_menu_text(locale, user['role']) + '\n\n' + t(locale, 'menu_hint')
    await answer_or_edit(event, text, main_menu_markup(locale, user['role'], bool(user['is_admin'])))


@router.message(CommandStart())
async def start(message: Message, db: Database, config: Config) -> None:
    db.upsert_user(message.from_user.id, message.from_user.username, message.from_user.first_name, message.from_user.id in config.admin_ids)
    await render_main(message, db, config)


@router.message(Command('menu'))
async def menu_command(message: Message, db: Database, config: Config) -> None:
    db.upsert_user(message.from_user.id, message.from_user.username, message.from_user.first_name, message.from_user.id in config.admin_ids)
    await render_main(message, db, config)


@router.message(Command('help'))
async def help_command(message: Message, db: Database, config: Config) -> None:
    db.upsert_user(message.from_user.id, message.from_user.username, message.from_user.first_name, message.from_user.id in config.admin_ids)
    user = db.get_user(message.from_user.id)
    locale = current_locale(user, config)
    if not await subscription_gate(message, db, config):
        return
    await answer_or_edit(message, t(locale, 'support_text', support=config.support_username), simple_back_keyboard(locale))


@router.message(Command('profile'))
async def profile_command(message: Message, db: Database, config: Config) -> None:
    db.upsert_user(message.from_user.id, message.from_user.username, message.from_user.first_name, message.from_user.id in config.admin_ids)
    await show_profile(message, db, config)


@router.message(Command('wallet'))
async def wallet_command(message: Message, db: Database, config: Config) -> None:
    db.upsert_user(message.from_user.id, message.from_user.username, message.from_user.first_name, message.from_user.id in config.admin_ids)
    await show_wallet(message, db, config)


@router.message(Command('tasks'))
async def tasks_command(message: Message, db: Database, config: Config) -> None:
    db.upsert_user(message.from_user.id, message.from_user.username, message.from_user.first_name, message.from_user.id in config.admin_ids)
    await show_tasks(message, db, config)


@router.message(Command('campaigns'))
async def campaigns_command(message: Message, db: Database, config: Config) -> None:
    db.upsert_user(message.from_user.id, message.from_user.username, message.from_user.first_name, message.from_user.id in config.admin_ids)
    await show_campaigns(message, db, config)


@router.message(Command('admin'))
async def admin_command(message: Message, db: Database, config: Config) -> None:
    db.upsert_user(message.from_user.id, message.from_user.username, message.from_user.first_name, message.from_user.id in config.admin_ids)
    await show_admin(message, db, config)


@router.callback_query(F.data.startswith('lang:'))
async def set_language(callback: CallbackQuery, db: Database, config: Config) -> None:
    locale = callback.data.split(':', 1)[1]
    if locale not in SUPPORTED_LANGUAGES:
        locale = config.default_language
    db.upsert_user(callback.from_user.id, callback.from_user.username, callback.from_user.first_name, callback.from_user.id in config.admin_ids)
    db.set_locale(callback.from_user.id, locale)
    await callback.answer(t(locale, 'language_saved'))
    await answer_or_edit(callback, t(locale, 'welcome', brand=config.brand_name) + '\n\n' + t(locale, 'choose_role'), role_keyboard(locale))


@router.callback_query(F.data == 'sub:check')
async def check_subscription(callback: CallbackQuery, db: Database, config: Config) -> None:
    user = db.get_user(callback.from_user.id)
    locale = current_locale(user, config)
    ok = await subscription_gate(callback, db, config)
    if ok:
        await callback.answer(t(locale, 'subscription_ok'))
        await render_main(callback, db, config)
    else:
        await callback.answer()


@router.callback_query(F.data.startswith('role:'))
async def set_role(callback: CallbackQuery, db: Database, config: Config) -> None:
    role = callback.data.split(':', 1)[1]
    if role not in {ROLE_EARNER, ROLE_ADVERTISER}:
        await callback.answer()
        return
    db.set_role(callback.from_user.id, role)
    user = db.get_user(callback.from_user.id)
    locale = current_locale(user, config)
    await callback.answer(t(locale, 'role_saved'))
    if not await subscription_gate(callback, db, config):
        return
    await render_main(callback, db, config)


async def show_profile(event: Message | CallbackQuery, db: Database, config: Config) -> None:
    if not await subscription_gate(event, db, config):
        return
    user = db.get_user(event.from_user.id)
    locale = current_locale(user, config)
    text = t(locale, 'profile_text', user_id=user['user_id'], language=SUPPORTED_LANGUAGES.get(locale, locale), role=role_label(locale, user['role']), tier=tier_label(locale, user['tier']), completed=int(user['completed_tasks']))
    await answer_or_edit(event, text, simple_back_keyboard(locale))


async def show_wallet(event: Message | CallbackQuery, db: Database, config: Config) -> None:
    if not await subscription_gate(event, db, config):
        return
    user = db.get_user(event.from_user.id)
    locale = current_locale(user, config)
    wallet = db.get_wallet(event.from_user.id)
    await answer_or_edit(event, t(locale, 'wallet_text', available=wallet['available'], hold=wallet['hold'], earned=wallet['earned_total']), simple_back_keyboard(locale))


async def show_tasks(event: Message | CallbackQuery, db: Database, config: Config) -> None:
    if not await subscription_gate(event, db, config):
        return
    user = db.get_user(event.from_user.id)
    locale = current_locale(user, config)
    claimed_ids = db.user_claimed_ids(event.from_user.id)
    tasks = [dict(r) for r in db.list_available_tasks() if int(r['id']) not in claimed_ids]
    if not tasks:
        await answer_or_edit(event, t(locale, 'no_tasks'), simple_back_keyboard(locale))
        return
    await answer_or_edit(event, t(locale, 'tasks_text'), tasks_list_keyboard(locale, tasks[:10]))


async def show_campaigns(event: Message | CallbackQuery, db: Database, config: Config) -> None:
    if not await subscription_gate(event, db, config):
        return
    user = db.get_user(event.from_user.id)
    locale = current_locale(user, config)
    rows = [dict(r) for r in db.list_user_campaigns(event.from_user.id)]
    text = t(locale, 'campaigns_text') if rows else t(locale, 'campaigns_text') + '\n\n' + t(locale, 'no_campaigns')
    await answer_or_edit(event, text, campaigns_keyboard(locale, rows))


async def show_rewards(event: Message | CallbackQuery, db: Database, config: Config) -> None:
    if not await subscription_gate(event, db, config):
        return
    user = db.get_user(event.from_user.id)
    locale = current_locale(user, config)
    await answer_or_edit(event, t(locale, 'rewards_text'), simple_back_keyboard(locale))


async def show_analytics(event: Message | CallbackQuery, db: Database, config: Config) -> None:
    if not await subscription_gate(event, db, config):
        return
    user = db.get_user(event.from_user.id)
    locale = current_locale(user, config)
    stats = db.advertiser_stats(event.from_user.id)
    await answer_or_edit(event, t(locale, 'analytics_text', **stats), simple_back_keyboard(locale))


async def show_topup(event: Message | CallbackQuery, db: Database, config: Config) -> None:
    if not await subscription_gate(event, db, config):
        return
    user = db.get_user(event.from_user.id)
    locale = current_locale(user, config)
    await answer_or_edit(event, t(locale, 'topup_text'), topup_keyboard(locale))


async def show_support(event: Message | CallbackQuery, db: Database, config: Config) -> None:
    if not await subscription_gate(event, db, config):
        return
    user = db.get_user(event.from_user.id)
    locale = current_locale(user, config)
    await answer_or_edit(event, t(locale, 'support_text', support=config.support_username), simple_back_keyboard(locale))


async def show_admin(event: Message | CallbackQuery, db: Database, config: Config) -> None:
    user = db.get_user(event.from_user.id)
    locale = current_locale(user, config)
    if event.from_user.id not in config.admin_ids:
        await answer_or_edit(event, t(locale, 'access_denied'), simple_back_keyboard(locale))
        return
    stats = db.admin_stats()
    await answer_or_edit(event, t(locale, 'admin_text', **stats), simple_back_keyboard(locale))


@router.callback_query(F.data == 'menu:main')
async def cb_main(callback: CallbackQuery, db: Database, config: Config) -> None:
    await callback.answer()
    await render_main(callback, db, config)


@router.callback_query(F.data == 'menu:profile')
async def cb_profile(callback: CallbackQuery, db: Database, config: Config) -> None:
    await callback.answer()
    await show_profile(callback, db, config)


@router.callback_query(F.data == 'menu:wallet')
async def cb_wallet(callback: CallbackQuery, db: Database, config: Config) -> None:
    await callback.answer()
    await show_wallet(callback, db, config)


@router.callback_query(F.data == 'menu:tasks')
async def cb_tasks(callback: CallbackQuery, db: Database, config: Config) -> None:
    await callback.answer()
    await show_tasks(callback, db, config)


@router.callback_query(F.data == 'menu:rewards')
async def cb_rewards(callback: CallbackQuery, db: Database, config: Config) -> None:
    await callback.answer()
    await show_rewards(callback, db, config)


@router.callback_query(F.data == 'menu:campaigns')
async def cb_campaigns(callback: CallbackQuery, db: Database, config: Config) -> None:
    await callback.answer()
    await show_campaigns(callback, db, config)


@router.callback_query(F.data == 'menu:analytics')
async def cb_analytics(callback: CallbackQuery, db: Database, config: Config) -> None:
    await callback.answer()
    await show_analytics(callback, db, config)


@router.callback_query(F.data == 'menu:topup')
async def cb_topup(callback: CallbackQuery, db: Database, config: Config) -> None:
    await callback.answer()
    await show_topup(callback, db, config)


@router.callback_query(F.data == 'menu:support')
async def cb_support(callback: CallbackQuery, db: Database, config: Config) -> None:
    await callback.answer()
    await show_support(callback, db, config)


@router.callback_query(F.data == 'menu:admin')
async def cb_admin(callback: CallbackQuery, db: Database, config: Config) -> None:
    await callback.answer()
    await show_admin(callback, db, config)


@router.callback_query(F.data.startswith('task:view:'))
async def task_view(callback: CallbackQuery, db: Database, config: Config) -> None:
    if not await subscription_gate(callback, db, config):
        return
    user = db.get_user(callback.from_user.id)
    locale = current_locale(user, config)
    campaign_id = int(callback.data.split(':', 2)[2])
    campaign = db.get_campaign(campaign_id)
    taken = campaign_id in db.user_claimed_ids(callback.from_user.id)
    if not campaign:
        await callback.answer()
        return
    await callback.answer()
    await answer_or_edit(callback, t(locale, 'task_card', id=campaign['id'], title=campaign['title'], reward=campaign['reward']), task_card_keyboard(locale, campaign_id, campaign['target_url'], taken))


@router.callback_query(F.data.startswith('task:take:'))
async def task_take(callback: CallbackQuery, db: Database, config: Config) -> None:
    if not await subscription_gate(callback, db, config):
        return
    user = db.get_user(callback.from_user.id)
    locale = current_locale(user, config)
    campaign_id = int(callback.data.split(':', 2)[2])
    ok = db.take_task(campaign_id, callback.from_user.id)
    campaign = db.get_campaign(campaign_id)
    await callback.answer(t(locale, 'task_taken') if ok else t(locale, 'already_taken'))
    if campaign:
        text = t(locale, 'task_card', id=campaign['id'], title=campaign['title'], reward=campaign['reward'])
        if ok:
            text += '\n\n' + t(locale, 'task_taken')
        await answer_or_edit(callback, text, task_card_keyboard(locale, campaign_id, campaign['target_url'], True))


@router.callback_query(F.data.startswith('task:done:'))
async def task_done(callback: CallbackQuery, db: Database, config: Config) -> None:
    if not await subscription_gate(callback, db, config):
        return
    user = db.get_user(callback.from_user.id)
    locale = current_locale(user, config)
    campaign_id = int(callback.data.split(':', 2)[2])
    ok = db.complete_task(campaign_id, callback.from_user.id)
    await callback.answer(t(locale, 'task_completed') if ok else t(locale, 'unknown'))
    await answer_or_edit(callback, t(locale, 'task_completed') if ok else t(locale, 'unknown'), simple_back_keyboard(locale, 'menu:tasks'))


@router.callback_query(F.data == 'camp:create_demo')
async def create_demo_campaign(callback: CallbackQuery, db: Database, config: Config) -> None:
    if not await subscription_gate(callback, db, config):
        return
    user = db.get_user(callback.from_user.id)
    locale = current_locale(user, config)
    db.create_demo_campaign_for_user(callback.from_user.id)
    await callback.answer(t(locale, 'campaign_created'))
    await show_campaigns(callback, db, config)


@router.callback_query(F.data.startswith('camp:view:'))
async def campaign_view(callback: CallbackQuery, db: Database, config: Config) -> None:
    if not await subscription_gate(callback, db, config):
        return
    user = db.get_user(callback.from_user.id)
    locale = current_locale(user, config)
    campaign_id = int(callback.data.split(':', 2)[2])
    campaign = db.get_campaign(campaign_id)
    if not campaign:
        await callback.answer()
        return
    await callback.answer()
    await answer_or_edit(callback, t(locale, 'campaign_card', id=campaign['id'], title=campaign['title'], reward=campaign['reward'], completed=campaign['completed_slots'], total=campaign['total_slots']), campaign_card_keyboard(locale))


@router.callback_query(F.data == 'wallet:topup_demo')
async def topup_demo(callback: CallbackQuery, db: Database, config: Config) -> None:
    user = db.get_user(callback.from_user.id)
    locale = current_locale(user, config)
    db.topup_wallet(callback.from_user.id, 500)
    await callback.answer(t(locale, 'topup_done'))
    await show_wallet(callback, db, config)


@router.message()
async def fallback(message: Message, db: Database, config: Config) -> None:
    db.upsert_user(message.from_user.id, message.from_user.username, message.from_user.first_name, message.from_user.id in config.admin_ids)
    await render_main(message, db, config)
