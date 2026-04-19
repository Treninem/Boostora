from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from app.core.i18n import DEFAULT_LOCALE, normalize_locale, t
from app.core.subscription import is_user_subscribed
from app.keyboards.subscription import subscription_required_keyboard


class SubscriptionRequiredMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        bot = getattr(event, 'bot', None)
        if bot is None:
            return await handler(event, data)

        settings = bot['settings']
        required_chat_id = int(getattr(settings, 'required_chat_id', 0) or 0)
        if not required_chat_id:
            return await handler(event, data)

        user = getattr(event, 'from_user', None)
        if user is None:
            return await handler(event, data)

        if user.id in settings.admin_ids:
            return await handler(event, data)

        if isinstance(event, CallbackQuery) and event.data == 'subscription:check':
            return await handler(event, data)

        if await is_user_subscribed(bot, user.id, required_chat_id):
            return await handler(event, data)

        locale = await self._resolve_locale(bot, user.id, getattr(user, 'language_code', None))
        text = '\n'.join([
            f"<b>{t(locale, 'sub_required_title', brand=settings.brand_name)}</b>",
            t(locale, 'sub_required_body'),
        ])
        keyboard = subscription_required_keyboard(locale, getattr(settings, 'required_chat_invite_link', ''))

        if isinstance(event, CallbackQuery):
            try:
                await event.answer(t(locale, 'sub_required_alert'), show_alert=True)
            except Exception:
                pass
            if event.message:
                await event.message.answer(text, reply_markup=keyboard)
            return None

        if isinstance(event, Message):
            await event.answer(text, reply_markup=keyboard)
            return None

        return None

    async def _resolve_locale(self, bot, user_id: int, telegram_language_code: str | None) -> str:
        repo = bot['users_repo']
        user = await repo.get_user(user_id)
        locale = normalize_locale((user or {}).get('locale'))
        if (user or {}).get('locale'):
            return locale
        if telegram_language_code:
            short = telegram_language_code.split('-', 1)[0].split('_', 1)[0].lower()
            return normalize_locale(short if short else DEFAULT_LOCALE)
        return DEFAULT_LOCALE
