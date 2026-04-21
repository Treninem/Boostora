from __future__ import annotations

from app import db


ACTIVE_STATUSES = {"member", "administrator", "creator"}
PROMOTABLE_TYPES = {"group", "supergroup", "channel"}


class BotChatService:
    @staticmethod
    def upsert_chat(*, chat_id: int, chat_ref: str, title: str = '', chat_type: str = '', username: str = '', is_active: bool = True, can_post: bool = True) -> None:
        db.execute(
            '''
            INSERT INTO bot_chats (
                chat_id, chat_ref, title, chat_type, username, is_active, can_post, last_seen_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT(chat_id) DO UPDATE SET
                chat_ref = excluded.chat_ref,
                title = excluded.title,
                chat_type = excluded.chat_type,
                username = excluded.username,
                is_active = excluded.is_active,
                can_post = excluded.can_post,
                last_seen_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            ''',
            (chat_id, chat_ref, title, chat_type, username, 1 if is_active else 0, 1 if can_post else 0),
        )

    @staticmethod
    def deactivate_chat(chat_id: int) -> None:
        db.execute(
            '''
            INSERT INTO bot_chats (chat_id, chat_ref, is_active, can_post, last_seen_at, updated_at)
            VALUES (?, ?, 0, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT(chat_id) DO UPDATE SET
                is_active = 0,
                can_post = 0,
                updated_at = CURRENT_TIMESTAMP
            ''',
            (chat_id, str(chat_id)),
        )

    @staticmethod
    def _chat_ref(chat) -> str:
        username = getattr(chat, 'username', None)
        if username:
            return f'@{username}'
        return str(int(chat.id))

    @staticmethod
    def touch_from_message(message) -> None:
        chat = getattr(message, 'chat', None)
        if not chat:
            return
        chat_type = getattr(chat, 'type', '') or ''
        if chat_type not in PROMOTABLE_TYPES:
            return
        BotChatService.upsert_chat(
            chat_id=int(chat.id),
            chat_ref=BotChatService._chat_ref(chat),
            title=(getattr(chat, 'title', None) or getattr(chat, 'full_name', None) or ''),
            chat_type=chat_type,
            username=(getattr(chat, 'username', None) or ''),
            is_active=True,
            can_post=True,
        )

    @staticmethod
    def record_my_chat_member(update) -> None:
        chat = getattr(update, 'chat', None)
        new_member = getattr(update, 'new_chat_member', None)
        if not chat or not new_member:
            return
        chat_type = getattr(chat, 'type', '') or ''
        if chat_type not in PROMOTABLE_TYPES:
            return
        status = getattr(new_member, 'status', '') or ''
        is_active = status in ACTIVE_STATUSES
        can_post = is_active
        perms = getattr(new_member, 'can_post_messages', None)
        if perms is not None:
            can_post = bool(perms) or status in {'administrator', 'creator'}
        if is_active:
            BotChatService.upsert_chat(
                chat_id=int(chat.id),
                chat_ref=BotChatService._chat_ref(chat),
                title=(getattr(chat, 'title', None) or getattr(chat, 'full_name', None) or ''),
                chat_type=chat_type,
                username=(getattr(chat, 'username', None) or ''),
                is_active=True,
                can_post=can_post,
            )
        else:
            BotChatService.deactivate_chat(int(chat.id))

    @staticmethod
    def list_promotable_chats():
        return db.fetch_all(
            '''
            SELECT * FROM bot_chats
            WHERE is_active = 1
              AND can_post = 1
              AND chat_type IN ('group', 'supergroup', 'channel')
            ORDER BY COALESCE(last_seen_at, updated_at) DESC, chat_id DESC
            '''
        )


    @staticmethod
    def count_all_chats() -> int:
        row = db.fetch_one(
            """
            SELECT COUNT(*) AS cnt
            FROM bot_chats
            WHERE is_active = 1
            """
        )
        return int(row['cnt'] or 0) if row else 0

    @staticmethod
    def list_all_chats(limit: int = 10, offset: int = 0):
        return db.fetch_all(
            """
            SELECT * FROM bot_chats
            WHERE is_active = 1
            ORDER BY COALESCE(last_seen_at, updated_at) DESC, chat_id DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        )

    @staticmethod
    def chat_link(row) -> str | None:
        username = str(row['username'] or '').strip()
        if username:
            return f'https://t.me/{username}'
        chat_ref = str(row['chat_ref'] or '').strip()
        if chat_ref.startswith('@'):
            return f'https://t.me/{chat_ref[1:]}'
        return None
