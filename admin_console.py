from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

from typing import Any

from app import db


AUTO_VERIFIABLE_TASK_TYPES = {
    'channel_subscribe',
    'chat_join',
    'post_comment',
    'post_reaction',
    'poll_vote',
    'bot_start',
    'mini_app_open',
}

SYSTEM_TRACKABLE_TASK_TYPES = {
    'post_view',
    'post_like',
    'story_view',
    'link_click',
    'post_share',
}


@dataclass(frozen=True)
class TargetInfo:
    raw: str
    chat_ref: str | None = None
    message_id: int | None = None
    bot_username: str | None = None
    start_param: str | None = None
    webapp_hint: str | None = None


class ActivityService:
    @staticmethod
    def _json(payload: dict[str, Any]) -> str:
        return json.dumps(payload, ensure_ascii=False)

    @staticmethod
    def _chat_ref_from_message(message) -> str:
        username = getattr(message.chat, 'username', None)
        if username:
            return f'@{username}'
        return str(int(message.chat.id))

    @staticmethod
    def _insert_event(
        *,
        user_id: int | None,
        activity_type: str,
        chat_ref: str | None = None,
        chat_id: int | None = None,
        message_id: int | None = None,
        parent_message_id: int | None = None,
        poll_id: str | None = None,
        target_value: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        db.execute(
            '''
            INSERT INTO activity_events (
                user_id, activity_type, chat_ref, chat_id, message_id, parent_message_id,
                poll_id, target_value, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                user_id,
                activity_type,
                chat_ref,
                chat_id,
                message_id,
                parent_message_id,
                poll_id,
                target_value,
                ActivityService._json(payload or {}),
            ),
        )

    @staticmethod
    def _store_message_snapshot(message) -> None:
        poll_id = None
        message_kind = 'message'
        if getattr(message, 'poll', None):
            poll = getattr(message, 'poll')
            poll_id = getattr(poll, 'id', None)
            message_kind = 'poll'
        elif getattr(message, 'web_app_data', None):
            message_kind = 'web_app_data'
        elif getattr(message, 'text', None):
            message_kind = 'text'
        db.execute(
            '''
            INSERT INTO observed_messages (
                chat_ref, chat_id, message_id, message_kind, poll_id, created_at
            ) VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(chat_id, message_id) DO UPDATE SET
                chat_ref = excluded.chat_ref,
                message_kind = excluded.message_kind,
                poll_id = excluded.poll_id
            ''',
            (
                ActivityService._chat_ref_from_message(message),
                int(message.chat.id),
                int(message.message_id),
                message_kind,
                poll_id,
            ),
        )

    @staticmethod
    def record_group_or_channel_message(message) -> None:
        ActivityService._store_message_snapshot(message)
        if message.chat.type not in {'group', 'supergroup'}:
            return
        user = getattr(message, 'from_user', None)
        if not user:
            return
        text = (getattr(message, 'text', None) or getattr(message, 'caption', None) or '').strip()
        if not text:
            return
        reply_to = getattr(message, 'reply_to_message', None)
        ActivityService._insert_event(
            user_id=int(user.id),
            activity_type='comment',
            chat_ref=ActivityService._chat_ref_from_message(message),
            chat_id=int(message.chat.id),
            message_id=int(message.message_id),
            parent_message_id=int(reply_to.message_id) if reply_to else None,
            payload={'text': text[:500]},
        )

    @staticmethod
    def record_channel_post(message) -> None:
        ActivityService._store_message_snapshot(message)

    @staticmethod
    def record_reaction(update) -> None:
        user = getattr(update, 'user', None)
        chat = getattr(update, 'chat', None)
        if not user or not chat:
            return
        username = getattr(chat, 'username', None)
        chat_ref = f'@{username}' if username else str(int(chat.id))
        new_reaction = getattr(update, 'new_reaction', None) or []
        reaction_keys: list[str] = []
        for item in new_reaction:
            emoji = getattr(item, 'emoji', None)
            custom = getattr(item, 'custom_emoji_id', None)
            if emoji:
                reaction_keys.append(str(emoji))
            elif custom:
                reaction_keys.append(f'custom:{custom}')
        ActivityService._insert_event(
            user_id=int(user.id),
            activity_type='reaction',
            chat_ref=chat_ref,
            chat_id=int(chat.id),
            message_id=int(update.message_id),
            payload={'reactions': reaction_keys},
        )

    @staticmethod
    def record_chat_member(update) -> None:
        user = getattr(update, 'from_user', None)
        chat = getattr(update, 'chat', None)
        new_member = getattr(update, 'new_chat_member', None)
        if not user or not chat or not new_member:
            return
        username = getattr(chat, 'username', None)
        chat_ref = f'@{username}' if username else str(int(chat.id))
        ActivityService._insert_event(
            user_id=int(user.id),
            activity_type='chat_member',
            chat_ref=chat_ref,
            chat_id=int(chat.id),
            payload={
                'status': getattr(new_member, 'status', None),
                'is_member': getattr(new_member, 'is_member', None),
            },
        )

    @staticmethod
    def record_poll_answer(update) -> None:
        user = getattr(update, 'user', None)
        if not user:
            return
        ActivityService._insert_event(
            user_id=int(user.id),
            activity_type='poll_vote',
            poll_id=str(update.poll_id),
            payload={'option_ids': list(getattr(update, 'option_ids', []) or [])},
        )

    @staticmethod
    def record_bot_start(user_id: int, start_arg: str, bot_username: str | None) -> None:
        ActivityService._insert_event(
            user_id=int(user_id),
            activity_type='bot_start',
            target_value=(start_arg or '').strip(),
            payload={'bot_username': (bot_username or '').lower()},
        )

    @staticmethod
    def record_mini_app_open(
        user_id: int,
        *,
        hint: str = '',
        source: str = 'embedded_webapp',
        payload: dict[str, Any] | None = None,
    ) -> None:
        """Record a server-validated Mini App open event.

        Menu-button and inline-button Mini Apps cannot rely on WebApp.sendData;
        their signed initData is validated by app.webapp before this method is
        called. The event remains compatible with the existing auto-verifier.
        """
        clean_hint = (hint or '').strip()[:255]
        event_payload = dict(payload or {})
        event_payload.update({
            'source': (source or 'embedded_webapp').strip()[:64],
            'hint': clean_hint,
            'validated_init_data': True,
        })
        ActivityService._insert_event(
            user_id=int(user_id),
            activity_type='mini_app_open',
            target_value=clean_hint,
            payload=event_payload,
        )

    @staticmethod
    def record_web_app_data(message) -> None:
        payload = getattr(message, 'web_app_data', None)
        if not payload:
            return
        user = getattr(message, 'from_user', None)
        if not user:
            return
        data = getattr(payload, 'data', '') or ''
        ActivityService._insert_event(
            user_id=int(user.id),
            activity_type='mini_app_open',
            chat_ref=ActivityService._chat_ref_from_message(message),
            chat_id=int(message.chat.id),
            message_id=int(message.message_id),
            target_value=data[:255],
            payload={'button_text': getattr(payload, 'button_text', ''), 'data': data[:1000]},
        )

    @staticmethod
    def parse_target(target_url: str) -> TargetInfo:
        raw = (target_url or '').strip()
        if not raw:
            return TargetInfo(raw='')
        if raw.startswith('@'):
            return TargetInfo(raw=raw, chat_ref=raw)
        if raw.lstrip('-').isdigit():
            return TargetInfo(raw=raw, chat_ref=raw)
        if raw.startswith('t.me/'):
            raw = f'https://{raw}'
        if raw.startswith('https://t.me/') or raw.startswith('http://t.me/'):
            parsed = urlparse(raw)
            parts = [part for part in parsed.path.split('/') if part]
            qs = parse_qs(parsed.query or '')
            if len(parts) >= 2 and parts[0] != 'c' and parts[1].isdigit():
                return TargetInfo(
                    raw=target_url,
                    chat_ref=f'@{parts[0]}',
                    message_id=int(parts[1]),
                    start_param=(qs.get('start', ['']) or [''])[0] or None,
                    webapp_hint=(qs.get('startapp', ['']) or [''])[0] or None,
                )
            if len(parts) >= 3 and parts[0] == 'c' and parts[1].isdigit() and parts[2].isdigit():
                return TargetInfo(raw=target_url, chat_ref=f"-100{parts[1]}", message_id=int(parts[2]))
            if parts:
                chat_ref = f"@{parts[0]}" if not parts[0].startswith('+') else None
                return TargetInfo(
                    raw=target_url,
                    chat_ref=chat_ref,
                    bot_username=f"@{parts[0]}" if chat_ref else None,
                    start_param=(qs.get('start', ['']) or [''])[0] or None,
                    webapp_hint=(qs.get('startapp', ['']) or [''])[0] or None,
                )
        if raw.startswith('tg://resolve'):
            parsed = urlparse(raw)
            qs = parse_qs(parsed.query or '')
            domain = (qs.get('domain', ['']) or [''])[0]
            return TargetInfo(
                raw=target_url,
                bot_username=f'@{domain}' if domain else None,
                start_param=(qs.get('start', ['']) or [''])[0] or None,
                webapp_hint=(qs.get('startapp', ['']) or [''])[0] or None,
            )
        return TargetInfo(raw=target_url)

    @staticmethod
    def _query_one(query: str, params: tuple[Any, ...]):
        return db.fetch_one(query, params)

    @staticmethod
    def _comments_match(user_id: int, taken_at: str, candidate_chat_refs: list[str], message_id: int | None) -> bool:
        placeholders = ','.join('?' for _ in candidate_chat_refs)
        params: list[Any] = [user_id, taken_at, *candidate_chat_refs]
        query = f'''
            SELECT id FROM activity_events
            WHERE user_id = ?
              AND activity_type = 'comment'
              AND created_at >= ?
              AND chat_ref IN ({placeholders})
        '''
        if message_id is not None:
            query += ' AND (parent_message_id = ? OR message_id = ?)'
            params.extend([message_id, message_id])
        query += ' ORDER BY id DESC LIMIT 1'
        row = db.fetch_one(query, tuple(params))
        return row is not None

    @staticmethod
    def _reaction_match(user_id: int, taken_at: str, candidate_chat_refs: list[str], message_id: int | None) -> bool:
        if message_id is None:
            return False
        placeholders = ','.join('?' for _ in candidate_chat_refs)
        row = db.fetch_one(
            f'''
            SELECT id FROM activity_events
            WHERE user_id = ?
              AND activity_type = 'reaction'
              AND created_at >= ?
              AND chat_ref IN ({placeholders})
              AND message_id = ?
            ORDER BY id DESC LIMIT 1
            ''',
            (user_id, taken_at, *candidate_chat_refs, message_id),
        )
        return row is not None

    @staticmethod
    def _poll_vote_match(user_id: int, taken_at: str, poll_id: str) -> bool:
        row = db.fetch_one(
            '''
            SELECT id FROM activity_events
            WHERE user_id = ?
              AND activity_type = 'poll_vote'
              AND poll_id = ?
              AND created_at >= ?
            ORDER BY id DESC LIMIT 1
            ''',
            (user_id, poll_id, taken_at),
        )
        return row is not None

    @staticmethod
    def _bot_start_match(user_id: int, taken_at: str, start_param: str | None, bot_username: str | None) -> bool:
        params: list[Any] = [user_id, taken_at]
        query = '''
            SELECT * FROM activity_events
            WHERE user_id = ?
              AND activity_type = 'bot_start'
              AND created_at >= ?
        '''
        if start_param:
            query += ' AND target_value = ?'
            params.append(start_param)
        query += ' ORDER BY id DESC LIMIT 3'
        rows = db.fetch_all(query, tuple(params))
        if not rows:
            return False
        if not bot_username:
            return True
        normalized = bot_username.lower()
        for row in rows:
            payload = str(row['payload_json'] or '')
            if normalized in payload.lower():
                return True
        return False

    @staticmethod
    def _mini_app_match(user_id: int, taken_at: str, hint: str | None) -> bool:
        rows = db.fetch_all(
            '''
            SELECT * FROM activity_events
            WHERE user_id = ?
              AND activity_type = 'mini_app_open'
              AND created_at >= ?
            ORDER BY id DESC LIMIT 5
            ''',
            (user_id, taken_at),
        )
        if not rows:
            return False
        if not hint:
            return True
        hint_l = hint.lower()
        for row in rows:
            data = str(row['target_value'] or '') + ' ' + str(row['payload_json'] or '')
            if hint_l in data.lower():
                return True
        return False

    @staticmethod
    def _observed_poll_id(candidate_chat_refs: list[str], message_id: int) -> str | None:
        placeholders = ','.join('?' for _ in candidate_chat_refs)
        row = db.fetch_one(
            f'''
            SELECT poll_id FROM observed_messages
            WHERE chat_ref IN ({placeholders})
              AND message_id = ?
              AND poll_id IS NOT NULL
            ORDER BY created_at DESC LIMIT 1
            ''',
            (*candidate_chat_refs, message_id),
        )
        return str(row['poll_id']) if row and row['poll_id'] else None

    @staticmethod
    def _candidate_chat_refs(bot, info: TargetInfo) -> list[str]:
        refs: list[str] = []
        if info.chat_ref:
            refs.append(info.chat_ref)
            try:
                api_ref: str | int = int(info.chat_ref) if info.chat_ref.lstrip('-').isdigit() else info.chat_ref
                chat = bot.get_chat(api_ref)
                linked = getattr(chat, 'linked_chat_id', None)
                if linked:
                    refs.append(str(int(linked)))
            except Exception:
                pass
        return list(dict.fromkeys(refs))

    @staticmethod
    def auto_verify_submission(bot, user_id: int, campaign, submission) -> tuple[str, str]:
        task_type = str(campaign['task_type'])
        if task_type not in AUTO_VERIFIABLE_TASK_TYPES:
            if task_type in SYSTEM_TRACKABLE_TASK_TYPES:
                return 'manual', 'task_verify_manual_only'
            return 'manual', 'task_verify_manual_only'

        info = ActivityService.parse_target(str(campaign['target_url']))
        taken_at = str(submission['taken_at'])
        candidate_refs = ActivityService._candidate_chat_refs(bot, info)

        if task_type in {'channel_subscribe', 'chat_join'}:
            from app.services.performer import PerformerService
            state, result_key = PerformerService._verify_membership(bot, user_id, str(campaign['target_url']))
            if state == 'verified':
                return 'verified', 'task_auto_verified'
            if state == 'failed':
                return 'failed', result_key
            return 'manual', 'task_verify_unavailable'

        if task_type == 'post_comment':
            if candidate_refs and ActivityService._comments_match(user_id, taken_at, candidate_refs, info.message_id):
                return 'verified', 'task_auto_verified'
            return 'manual', 'task_comment_not_found'

        if task_type == 'post_reaction':
            if candidate_refs and ActivityService._reaction_match(user_id, taken_at, candidate_refs, info.message_id):
                return 'verified', 'task_auto_verified'
            return 'manual', 'task_reaction_not_found'

        if task_type == 'poll_vote':
            poll_id = ActivityService._observed_poll_id(candidate_refs, info.message_id or 0) if info.message_id and candidate_refs else None
            if poll_id and ActivityService._poll_vote_match(user_id, taken_at, poll_id):
                return 'verified', 'task_auto_verified'
            return 'manual', 'task_poll_vote_not_found'

        if task_type == 'bot_start':
            if ActivityService._bot_start_match(user_id, taken_at, info.start_param, info.bot_username):
                return 'verified', 'task_auto_verified'
            return 'manual', 'task_bot_start_not_found'

        if task_type == 'mini_app_open':
            if ActivityService._mini_app_match(user_id, taken_at, info.webapp_hint):
                return 'verified', 'task_auto_verified'
            return 'manual', 'task_mini_app_not_found'

        return 'manual', 'task_verify_manual_only'
