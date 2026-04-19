from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message

from app.config import Config
from app.db import Database
from app.helpers import role_menu, subscription_gate
from app.i18n import ROLE_ADVERTISER, ROLE_EARNER, SUPPORTED_LANGUAGES, normalize_locale, role_label, t, tier_label
from app.keyboards import campaigns_keyboard, language_keyboard, role_keyboard, task_action_keyboard, tasks_keyboard, topup_keyboard

router = Router()


def current_locale(user, config: Config) -> str:
    if user:
        return normalize_locale(user["locale"], config.default_language)
    return normalize_locale(config.default_language, "en")


@router.message(CommandStart())
async def start(message: Message, db: Database, config: Config) -> None:
    db.upsert_user(
        user_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        is_admin=message.from_user.id in config.admin_ids,
    )
    await message.answer(t(config.default_language, "choose_language"), reply_markup=language_keyboard())


@router.message(Command("help"))
async def help_command(message: Message, db: Database, config: Config) -> None:
    user = db.get_user(message.from_user.id)
    locale = current_locale(user, config)
    await message.answer(t(locale, "support_text", support=config.support_username))


@router.callback_query(F.data.startswith("lang:"))
async def set_language(callback: CallbackQuery, db: Database, config: Config) -> None:
    locale = callback.data.split(":", 1)[1]
    if locale not in SUPPORTED_LANGUAGES:
        locale = config.default_language
    db.upsert_user(
        user_id=callback.from_user.id,
        username=callback.from_user.username,
        first_name=callback.from_user.first_name,
        is_admin=callback.from_user.id in config.admin_ids,
    )
    db.set_locale(callback.from_user.id, locale)
    await callback.answer(t(locale, "language_saved"))
    await callback.message.answer(
        t(locale, "welcome", brand=config.brand_name) + "\n\n" + t(locale, "choose_role"),
        reply_markup=role_keyboard(locale),
    )


@router.callback_query(F.data == "sub:check")
async def check_subscription(callback: CallbackQuery, db: Database, config: Config) -> None:
    if await subscription_gate(callback, db, config):
        user = db.get_user(callback.from_user.id)
        locale = current_locale(user, config)
        await callback.answer(t(locale, "subscription_ok"), show_alert=False)
        if user and user["role"]:
            await callback.message.answer(
                t(locale, "menu_advertiser") if user["role"] == ROLE_ADVERTISER else t(locale, "menu_earner"),
                reply_markup=role_menu(locale, user["role"], bool(user["is_admin"])),
            )
        else:
            await callback.message.answer(t(locale, "choose_role"), reply_markup=role_keyboard(locale))


@router.callback_query(F.data.startswith("role:"))
async def set_role(callback: CallbackQuery, db: Database, config: Config) -> None:
    user = db.get_user(callback.from_user.id)
    locale = current_locale(user, config)
    role = callback.data.split(":", 1)[1]
    if role not in {ROLE_EARNER, ROLE_ADVERTISER}:
        await callback.answer()
        return
    db.set_role(callback.from_user.id, role)
    user = db.get_user(callback.from_user.id)
    if not await subscription_gate(callback, db, config):
        return
    await callback.answer(t(locale, "role_saved"))
    await callback.message.answer(
        t(locale, "menu_advertiser") if role == ROLE_ADVERTISER else t(locale, "menu_earner"),
        reply_markup=role_menu(locale, role, bool(user["is_admin"])),
    )


@router.message(Command("profile"))
async def profile_command(message: Message, db: Database, config: Config) -> None:
    await show_profile(message, db, config)


@router.message(Command("wallet"))
async def wallet_command(message: Message, db: Database, config: Config) -> None:
    await show_wallet(message, db, config)


@router.message(Command("tasks"))
async def tasks_command(message: Message, db: Database, config: Config) -> None:
    await show_tasks(message, db, config)


@router.message(Command("campaigns"))
async def campaigns_command(message: Message, db: Database, config: Config) -> None:
    await show_campaigns(message, db, config)


@router.message(Command("admin"))
async def admin_command(message: Message, db: Database, config: Config) -> None:
    await show_admin(message, db, config)


async def show_profile(message: Message, db: Database, config: Config) -> None:
    if not await subscription_gate(message, db, config):
        return
    user = db.get_user(message.from_user.id)
    locale = current_locale(user, config)
    await message.answer(
        t(
            locale,
            "profile_text",
            user_id=user["user_id"],
            language=SUPPORTED_LANGUAGES.get(locale, locale),
            role=role_label(locale, user["role"]),
            tier=tier_label(locale, user["tier"]),
            completed=int(user["completed_tasks"]),
        ),
        reply_markup=role_menu(locale, user["role"], bool(user["is_admin"])),
    )


async def show_wallet(message: Message, db: Database, config: Config) -> None:
    if not await subscription_gate(message, db, config):
        return
    user = db.get_user(message.from_user.id)
    locale = current_locale(user, config)
    wallet = db.get_wallet(message.from_user.id)
    await message.answer(
        t(locale, "wallet_text", available=wallet["available"], hold=wallet["hold"], earned=wallet["earned_total"]),
        reply_markup=role_menu(locale, user["role"], bool(user["is_admin"])),
    )


async def show_tasks(message: Message, db: Database, config: Config) -> None:
    if not await subscription_gate(message, db, config):
        return
    user = db.get_user(message.from_user.id)
    locale = current_locale(user, config)
    claimed_ids = db.user_claimed_ids(message.from_user.id)
    tasks = [dict(r) for r in db.list_available_tasks() if int(r["id"]) not in claimed_ids]
    if not tasks:
        await message.answer(t(locale, "no_tasks"), reply_markup=role_menu(locale, user["role"], bool(user["is_admin"])))
        return
    await message.answer(t(locale, "tasks_text"), reply_markup=tasks_keyboard(locale, tasks[:10]))


async def show_campaigns(message: Message, db: Database, config: Config) -> None:
    if not await subscription_gate(message, db, config):
        return
    user = db.get_user(message.from_user.id)
    locale = current_locale(user, config)
    rows = db.list_user_campaigns(message.from_user.id)
    text = [t(locale, "campaigns_text")]
    if not rows:
        text.append("")
        text.append(t(locale, "no_campaigns"))
    else:
        for row in rows[:20]:
            text.append("")
            text.append(f"• <b>#{row['id']}</b> {row['title']}")
            text.append(f"  Reward: {row['reward']} | {row['completed_slots']}/{row['total_slots']}")
    await message.answer("\n".join(text), reply_markup=campaigns_keyboard(locale))


async def show_admin(message: Message, db: Database, config: Config) -> None:
    user = db.get_user(message.from_user.id)
    locale = current_locale(user, config)
    if message.from_user.id not in config.admin_ids:
        await message.answer(t(locale, "access_denied"))
        return
    stats = db.admin_stats()
    await message.answer(t(locale, "admin_text", **stats))


@router.callback_query(F.data.startswith("task_take:"))
async def task_take(callback: CallbackQuery, db: Database, config: Config) -> None:
    if not await subscription_gate(callback, db, config):
        return
    user = db.get_user(callback.from_user.id)
    locale = current_locale(user, config)
    campaign_id = int(callback.data.split(":", 1)[1])
    campaign = db.get_campaign(campaign_id)
    if not campaign:
        await callback.answer()
        return
    ok = db.take_task(campaign_id, callback.from_user.id)
    await callback.answer(t(locale, "task_taken") if ok else t(locale, "already_taken"), show_alert=False)
    if callback.message and ok:
        await callback.message.answer(
            f"<b>#{campaign['id']}</b> {campaign['title']}\n+{campaign['reward']}",
            reply_markup=task_action_keyboard(locale, campaign_id, campaign['target_url']),
        )


@router.callback_query(F.data.startswith("task_done:"))
async def task_done(callback: CallbackQuery, db: Database, config: Config) -> None:
    if not await subscription_gate(callback, db, config):
        return
    user = db.get_user(callback.from_user.id)
    locale = current_locale(user, config)
    campaign_id = int(callback.data.split(":", 1)[1])
    ok = db.complete_task(campaign_id, callback.from_user.id)
    await callback.answer(t(locale, "task_completed") if ok else t(locale, "unknown"), show_alert=False)
    if callback.message:
        await callback.message.answer(t(locale, "task_completed") if ok else t(locale, "unknown"))


@router.callback_query(F.data == "camp:create_demo")
async def create_demo_campaign(callback: CallbackQuery, db: Database, config: Config) -> None:
    if not await subscription_gate(callback, db, config):
        return
    user = db.get_user(callback.from_user.id)
    locale = current_locale(user, config)
    db.create_demo_campaign_for_user(callback.from_user.id)
    await callback.answer(t(locale, "campaign_created"), show_alert=False)
    if callback.message:
        await callback.message.answer(t(locale, "campaign_created"))


@router.callback_query(F.data == "wallet:topup_demo")
async def topup_demo(callback: CallbackQuery, db: Database, config: Config) -> None:
    user = db.get_user(callback.from_user.id)
    locale = current_locale(user, config)
    db.topup_wallet(callback.from_user.id, 500)
    await callback.answer(t(locale, "topup_done"), show_alert=False)
    if callback.message:
        await callback.message.answer(t(locale, "topup_done"))


@router.message()
async def menu_handler(message: Message, db: Database, config: Config) -> None:
    db.upsert_user(
        user_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        is_admin=message.from_user.id in config.admin_ids,
    )
    user = db.get_user(message.from_user.id)
    locale = current_locale(user, config)
    text = (message.text or "").strip()
    mapping = {
        t(locale, "profile"): show_profile,
        t(locale, "wallet"): show_wallet,
        t(locale, "tasks"): show_tasks,
        t(locale, "campaigns"): show_campaigns,
        t(locale, "support"): None,
        t(locale, "admin"): show_admin,
    }
    if text == t(locale, "rewards"):
        if not await subscription_gate(message, db, config):
            return
        await message.answer(t(locale, "rewards_text"))
        return
    if text == t(locale, "analytics"):
        if not await subscription_gate(message, db, config):
            return
        stats = db.advertiser_stats(message.from_user.id)
        await message.answer(t(locale, "analytics_text", **stats))
        return
    if text == t(locale, "topup"):
        if not await subscription_gate(message, db, config):
            return
        await message.answer(t(locale, "topup_text"), reply_markup=topup_keyboard(locale))
        return
    if text == t(locale, "support"):
        await message.answer(t(locale, "support_text", support=config.support_username))
        return
    handler = mapping.get(text)
    if handler:
        await handler(message, db, config)
        return

    if not user or not user["locale"]:
        await message.answer(t(config.default_language, "choose_language"), reply_markup=language_keyboard())
        return
    if not user["role"]:
        await message.answer(t(locale, "choose_role"), reply_markup=role_keyboard(locale))
        return
    await message.answer(
        t(locale, "menu_advertiser") if user["role"] == ROLE_ADVERTISER else t(locale, "menu_earner"),
        reply_markup=role_menu(locale, user["role"], bool(user["is_admin"])),
    )
