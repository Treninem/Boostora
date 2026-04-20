import logging

import telebot

from app.config import settings


logger = logging.getLogger(__name__)

_ALLOWED_MEMBER_STATUSES = {'creator', 'administrator', 'member'}


class SubscriptionService:
    @staticmethod
    def should_enforce_required_chat(chat_id: int) -> bool:
        return int(chat_id) != int(settings.required_chat_id)

    @staticmethod
    def is_user_subscribed(bot: telebot.TeleBot, user_id: int) -> bool:
        try:
            member = bot.get_chat_member(settings.required_chat_id, user_id)
        except Exception as exc:
            logger.warning('Required chat membership check failed for user %s: %s', user_id, exc)
            return False

        status = getattr(member, 'status', '') or ''
        if status in _ALLOWED_MEMBER_STATUSES:
            return True
        if status == 'restricted' and bool(getattr(member, 'is_member', False)):
            return True
        return False
