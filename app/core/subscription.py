from __future__ import annotations

from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError


async def is_user_subscribed(bot, user_id: int, chat_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
    except (TelegramBadRequest, TelegramForbiddenError):
        return False
    except Exception:
        return False

    status = getattr(member, 'status', None)
    if status in {'administrator', 'creator', 'member'}:
        return True
    if status == 'restricted' and bool(getattr(member, 'is_member', False)):
        return True
    return False
