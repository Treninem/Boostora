from __future__ import annotations

import html
import logging
import threading
from datetime import datetime, timezone
from urllib.parse import quote

from telebot import types

from app import db
from app.config import settings


LOGGER = logging.getLogger(__name__)

_NOTICE_LOCKS = tuple(threading.Lock() for _ in range(64))
_BOT_USERNAME_CACHE: dict[int, str] = {}
_BOT_USERNAME_CACHE_LOCK = threading.Lock()


class ChatStartGateService:
    """Require one private /start before a user can write in protected Telegram groups."""

    @staticmethod
    def _normalize_chat_ref(value: str | int | None) -> str:
        raw = str(value or '').strip()
        if not raw:
            return ''
        lowered = raw.lower().rstrip('/')
        if lowered.startswith('https://t.me/') or lowered.startswith('http://t.me/'):
            tail = raw.rstrip('/').rsplit('/', 1)[-1].split('?', 1)[0].strip()
            return f'@{tail.lstrip("@").lower()}' if tail else ''
        if raw.startswith('@'):
            return f'@{raw[1:].lower()}'
        return raw

    @staticmethod
    def is_protected_chat(chat) -> bool:  # noqa: ANN001
        if not settings.chat_start_gate_enabled or chat is None:
            return False
        chat_type = str(getattr(chat, 'type', '') or '').strip().lower()
        return chat_type in {'group', 'supergroup'}

    @staticmethod
    def has_started(user_id: int) -> bool:
        row = db.fetch_one('SELECT chat_gate_started_at FROM users WHERE user_id=?', (int(user_id),))
        return bool(row and str(row['chat_gate_started_at'] or '').strip())

    @staticmethod
    def mark_started(user_id: int) -> bool:
        """Mark a real private /start and return True only on the first grant."""
        existing = ChatStartGateService.has_started(int(user_id))
        db.execute(
            '''
            UPDATE users
            SET chat_gate_started_at=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP
            WHERE user_id=?
            ''',
            (int(user_id),),
        )
        return not existing

    @staticmethod
    def should_block_message(message) -> bool:  # noqa: ANN001
        chat = getattr(message, 'chat', None)
        if not ChatStartGateService.is_protected_chat(chat):
            return False
        from_user = getattr(message, 'from_user', None)
        if from_user is None or bool(getattr(from_user, 'is_bot', False)):
            return False
        try:
            return not ChatStartGateService.has_started(int(from_user.id))
        except (TypeError, ValueError):
            return False

    @staticmethod
    def _bot_username(bot) -> str:  # noqa: ANN001
        cache_key = id(bot)
        with _BOT_USERNAME_CACHE_LOCK:
            cached = _BOT_USERNAME_CACHE.get(cache_key)
        if cached:
            return cached
        username = ''
        try:
            username = str(getattr(bot.get_me(), 'username', '') or '').strip().lstrip('@')
        except Exception:
            username = ''
        if not username:
            username = str(settings.support_username or 'BoostoraBot').strip().lstrip('@') or 'BoostoraBot'
        with _BOT_USERNAME_CACHE_LOCK:
            _BOT_USERNAME_CACHE[cache_key] = username
        return username

    @staticmethod
    def start_link(bot) -> str:  # noqa: ANN001
        username = ChatStartGateService._bot_username(bot)
        parameter = quote(settings.chat_start_gate_start_parameter or 'chat_access', safe='_-')
        return f'https://t.me/{username}?start={parameter}'

    @staticmethod
    def chat_link() -> str:
        explicit = str(settings.chat_start_gate_chat_link or '').strip()
        if explicit:
            return explicit
        ref = ChatStartGateService._normalize_chat_ref(settings.chat_start_gate_chat_ref)
        if ref.startswith('@'):
            return f'https://t.me/{ref[1:]}'
        return settings.required_chat_invite_link

    @staticmethod
    def _mention(user) -> str:  # noqa: ANN001
        user_id = int(getattr(user, 'id', 0) or 0)
        first_name = str(getattr(user, 'first_name', '') or '').strip()
        username = str(getattr(user, 'username', '') or '').strip().lstrip('@')
        label = first_name or (f'@{username}' if username else 'Пользователь')
        return f'<a href="tg://user?id={user_id}">{html.escape(label)}</a>'

    @staticmethod
    def _notice_lock(chat_id: int, user_id: int) -> threading.Lock:
        return _NOTICE_LOCKS[hash((int(chat_id), int(user_id))) % len(_NOTICE_LOCKS)]

    @staticmethod
    def _notice_is_recent(chat_id: int, user_id: int) -> bool:
        row = db.fetch_one(
            'SELECT updated_at FROM chat_start_gate_notices WHERE chat_id=? AND user_id=?',
            (int(chat_id), int(user_id)),
        )
        if not row or not row['updated_at']:
            return False
        try:
            updated = datetime.fromisoformat(str(row['updated_at']).replace('Z', '+00:00'))
            if updated.tzinfo is None:
                updated = updated.replace(tzinfo=timezone.utc)
            age = (datetime.now(timezone.utc) - updated).total_seconds()
            return 0 <= age < int(settings.chat_start_gate_notice_cooldown_seconds)
        except (TypeError, ValueError):
            return False

    @staticmethod
    def _delete_blocked_message(bot, chat_id: int, message_id: int, user_id: int) -> bool:  # noqa: ANN001
        try:
            bot.delete_message(chat_id=int(chat_id), message_id=int(message_id))
            return True
        except Exception as exc:
            LOGGER.error(
                'Chat start gate could not delete blocked message %s in chat %s from user %s: %s',
                message_id,
                chat_id,
                user_id,
                exc,
            )
            return False

    @staticmethod
    def _delete_previous_notice(bot, chat_id: int, user_id: int) -> None:  # noqa: ANN001
        row = db.fetch_one(
            'SELECT warning_message_id FROM chat_start_gate_notices WHERE chat_id=? AND user_id=?',
            (int(chat_id), int(user_id)),
        )
        if row and row['warning_message_id'] is not None:
            try:
                bot.delete_message(int(chat_id), int(row['warning_message_id']))
            except Exception:
                pass

    @staticmethod
    def _save_notice(chat_id: int, user_id: int, message_id: int) -> None:
        db.execute(
            '''
            INSERT INTO chat_start_gate_notices (chat_id, user_id, warning_message_id, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(chat_id, user_id) DO UPDATE SET
                warning_message_id=excluded.warning_message_id,
                updated_at=CURRENT_TIMESTAMP
            ''',
            (int(chat_id), int(user_id), int(message_id)),
        )

    @staticmethod
    def block_message(bot, message) -> None:  # noqa: ANN001
        chat_id = int(message.chat.id)
        user_id = int(message.from_user.id)
        deleted = ChatStartGateService._delete_blocked_message(
            bot,
            chat_id,
            int(message.message_id),
            user_id,
        )

        # TeleBot may process updates concurrently. Serialize only the notice
        # section, while every blocked user message is still deleted first.
        with ChatStartGateService._notice_lock(chat_id, user_id):
            if ChatStartGateService._notice_is_recent(chat_id, user_id):
                return
            ChatStartGateService._delete_previous_notice(bot, chat_id, user_id)
            markup = types.InlineKeyboardMarkup(row_width=1)
            markup.add(types.InlineKeyboardButton('🚀 Запустить Boostora', url=ChatStartGateService.start_link(bot)))
            status_line = 'ваше сообщение удалено.' if deleted else 'доступ к сообщениям пока закрыт.'
            text = (
                f'🔒 {ChatStartGateService._mention(message.from_user)}, {status_line}\n\n'
                'Чтобы писать в этой группе, сначала запустите бота Boostora. '
                'После нажатия Start доступ откроется автоматически.'
            )
            try:
                sent = bot.send_message(
                    chat_id,
                    text,
                    parse_mode='HTML',
                    reply_markup=markup,
                    disable_web_page_preview=True,
                )
                ChatStartGateService._save_notice(chat_id, user_id, int(sent.message_id))
            except Exception as exc:
                LOGGER.warning('Could not send chat start gate warning in chat %s: %s', chat_id, exc)

    @staticmethod
    def clear_notices_for_user(bot, user_id: int) -> None:  # noqa: ANN001
        rows = db.fetch_all(
            'SELECT chat_id, warning_message_id FROM chat_start_gate_notices WHERE user_id=?',
            (int(user_id),),
        )
        for row in rows:
            try:
                bot.delete_message(int(row['chat_id']), int(row['warning_message_id']))
            except Exception:
                pass
        db.execute('DELETE FROM chat_start_gate_notices WHERE user_id=?', (int(user_id),))

    @staticmethod
    def send_access_granted(bot, chat_id: int) -> None:  # noqa: ANN001
        markup = types.InlineKeyboardMarkup(row_width=1)
        chat_link = ChatStartGateService.chat_link()
        if chat_link:
            markup.add(types.InlineKeyboardButton('💬 Открыть Boostora Chat', url=chat_link))
        bot.send_message(
            int(chat_id),
            '✅ Доступ открыт. Теперь вы можете писать во всех группах и чатах, где работает Boostora.',
            reply_markup=markup,
        )
