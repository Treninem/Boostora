from __future__ import annotations

import logging
import re
from dataclasses import dataclass

import telebot

from app import db
from app.config import settings


logger = logging.getLogger(__name__)

_ALLOWED_MEMBER_STATUSES = {'creator', 'administrator', 'member'}
_MAX_REQUIRED_CHATS = 10
_TME_RE = re.compile(r'^(?:https?://)?t\.me/([A-Za-z0-9_+]+)$', re.IGNORECASE)


@dataclass(frozen=True)
class SubscriptionCheckResult:
    is_subscribed: bool
    is_unknown: bool = False
    checked_chat_id: str | None = None
    error_text: str = ''


class SubscriptionService:
    @staticmethod
    def bootstrap_defaults() -> None:
        meta = db.fetch_one("SELECT value FROM app_meta WHERE key = ?", ('required_chats_bootstrapped',))
        if meta:
            return
        rows = db.fetch_all('SELECT id FROM required_chats LIMIT 1')
        if not rows:
            SubscriptionService.add_required_chat(settings.required_chat_id, settings.required_chat_invite_link)
        db.execute(
            '''
            INSERT INTO app_meta (key, value, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP
            ''',
            ('required_chats_bootstrapped', '1'),
        )

    @staticmethod
    def normalize_chat_ref(raw_value: str) -> str:
        value = (raw_value or '').strip()
        if not value:
            raise ValueError('empty')
        match = _TME_RE.match(value)
        if match:
            token = match.group(1).strip()
            if token.startswith('+'):
                return value
            return f'@{token.lstrip("@")}'
        if value.startswith('@'):
            username = value[1:].strip()
            if username and all(ch.isalnum() or ch == '_' for ch in username):
                return f'@{username}'
            raise ValueError('invalid')
        if value.lstrip('-').isdigit():
            return value
        raise ValueError('invalid')

    @staticmethod
    def normalize_join_link(raw_value: str) -> str:
        value = (raw_value or '').strip()
        if not value:
            return ''
        if value.startswith('@'):
            return f'https://t.me/{value[1:]}'
        if value.startswith('http://') or value.startswith('https://'):
            return value
        match = _TME_RE.match(value)
        if match:
            token = match.group(1).strip()
            return f'https://t.me/{token}'
        return ''

    @staticmethod
    def display_name(chat_ref: str) -> str:
        return chat_ref[:40]

    @staticmethod
    def effective_join_link(chat_ref: str, join_link: str | None) -> str:
        normalized_link = SubscriptionService.normalize_join_link(join_link or '')
        if normalized_link:
            return normalized_link
        if chat_ref.startswith('@'):
            return f'https://t.me/{chat_ref[1:]}'
        return ''

    @staticmethod
    def list_required_chats():
        SubscriptionService.bootstrap_defaults()
        return db.fetch_all('SELECT * FROM required_chats ORDER BY id ASC LIMIT ?', (_MAX_REQUIRED_CHATS,))

    @staticmethod
    def count_required_chats() -> int:
        row = db.fetch_one('SELECT COUNT(*) AS c FROM required_chats')
        return int(row['c']) if row else 0

    @staticmethod
    def add_required_chat(chat_ref: str, join_link: str = '') -> tuple[bool, str]:
        try:
            normalized_ref = SubscriptionService.normalize_chat_ref(chat_ref)
        except ValueError:
            return False, 'admin_required_chat_invalid'
        normalized_link = SubscriptionService.effective_join_link(normalized_ref, join_link)
        existing = db.fetch_one('SELECT id FROM required_chats WHERE chat_ref = ?', (normalized_ref,))
        if existing:
            return False, 'admin_required_chat_exists'
        if SubscriptionService.count_required_chats() >= _MAX_REQUIRED_CHATS:
            return False, 'admin_required_chat_limit_reached'
        db.execute(
            '''
            INSERT INTO required_chats (chat_ref, join_link, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ''',
            (normalized_ref, normalized_link),
        )
        return True, 'admin_required_chat_added'

    @staticmethod
    def remove_required_chat(required_chat_id: int) -> tuple[bool, str]:
        row = db.fetch_one('SELECT id FROM required_chats WHERE id = ?', (required_chat_id,))
        if not row:
            return False, 'admin_required_chat_not_found'
        db.execute('DELETE FROM required_chats WHERE id = ?', (required_chat_id,))
        return True, 'admin_required_chat_removed'

    @staticmethod
    def parse_admin_add_payload(text: str) -> tuple[str, str]:
        raw = (text or '').strip()
        if not raw:
            raise ValueError('empty')
        parts = raw.split()
        ref = parts[0]
        link = parts[1] if len(parts) > 1 else ''
        normalized_ref = SubscriptionService.normalize_chat_ref(ref)
        normalized_link = SubscriptionService.effective_join_link(normalized_ref, link)
        return normalized_ref, normalized_link

    @staticmethod
    def _candidate_refs(chat_ref: str) -> list[str]:
        candidates: list[str] = [chat_ref]
        if chat_ref.startswith('@'):
            plain = chat_ref[1:]
            tme_link = f'https://t.me/{plain}'
            if tme_link not in candidates:
                candidates.append(tme_link)
        elif chat_ref.lstrip('-').isdigit():
            raw_id = int(chat_ref)
            raw_str = str(raw_id)
            if raw_id < 0 and not raw_str.startswith('-100'):
                normalized = f'-100{abs(raw_id)}'
                if normalized not in candidates:
                    candidates.append(normalized)
        return candidates

    @staticmethod
    def should_enforce_required_chat(chat_id: int | str, chat_username: str | None = None) -> bool:
        required_chats = SubscriptionService.list_required_chats()
        if not required_chats:
            return False
        raw_chat = str(chat_id).strip()
        current_id = raw_chat if raw_chat.lstrip('-').isdigit() else ''
        current_username = ''
        if raw_chat.startswith('@'):
            current_username = raw_chat.lower()
        elif chat_username:
            current_username = f'@{chat_username}'.lower()
        for row in required_chats:
            chat_ref = str(row['chat_ref'])
            for candidate in SubscriptionService._candidate_refs(chat_ref):
                candidate_value = str(candidate)
                if current_id and current_id == candidate_value:
                    return False
                if current_username and candidate_value.lower() == current_username:
                    return False
        return True

    @staticmethod
    def _is_member_status(member) -> bool:
        status = getattr(member, 'status', '') or ''
        if status in _ALLOWED_MEMBER_STATUSES:
            return True
        if status == 'restricted' and bool(getattr(member, 'is_member', False)):
            return True
        return False

    @staticmethod
    def get_subscription_check_result(bot: telebot.TeleBot, user_id: int) -> SubscriptionCheckResult:
        required_chats = SubscriptionService.list_required_chats()
        if not required_chats:
            return SubscriptionCheckResult(is_subscribed=True)

        had_unknown_error = False
        last_error = ''

        for row in required_chats:
            chat_ref = str(row['chat_ref'])
            member_found = False
            satisfied = False
            for candidate in SubscriptionService._candidate_refs(chat_ref):
                candidate_value = str(candidate)
                api_chat_ref: str | int = int(candidate_value) if candidate_value.lstrip('-').isdigit() else candidate_value
                try:
                    member = bot.get_chat_member(api_chat_ref, user_id)
                except Exception as exc:
                    last_error = str(exc)
                    had_unknown_error = True
                    logger.warning(
                        'Required chat membership check failed for user %s in chat %s: %s',
                        user_id,
                        candidate_value,
                        exc,
                    )
                    continue
                member_found = True
                if SubscriptionService._is_member_status(member):
                    satisfied = True
                    break
                logger.info(
                    'User %s is not subscribed in required chat %s: status=%s is_member=%s',
                    user_id,
                    candidate_value,
                    getattr(member, 'status', ''),
                    getattr(member, 'is_member', None),
                )
                return SubscriptionCheckResult(is_subscribed=False, checked_chat_id=candidate_value, error_text=last_error)
            if satisfied:
                continue
            if not member_found:
                return SubscriptionCheckResult(is_subscribed=False, is_unknown=True, checked_chat_id=chat_ref, error_text=last_error)
            return SubscriptionCheckResult(is_subscribed=False, checked_chat_id=chat_ref, error_text=last_error)

        if had_unknown_error:
            return SubscriptionCheckResult(is_subscribed=False, is_unknown=True, error_text=last_error)
        return SubscriptionCheckResult(is_subscribed=True)

    @staticmethod
    def is_user_subscribed(bot: telebot.TeleBot, user_id: int) -> bool:
        return SubscriptionService.get_subscription_check_result(bot, user_id).is_subscribed
