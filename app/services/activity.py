from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, urlparse

from app import db


AUTO_VERIFIABLE_TASK_TYPES = {
    'channel_subscribe',
    'chat_join',
    'join_request',
    'post_comment',
    'chat_message',
    'post_reaction',
    'post_like',
    'poll_vote',
    'post_view',
    'link_click',
}

# Kept for backward compatibility with existing campaigns. New campaigns are
# limited to AUTO_VERIFIABLE_TASK_TYPES by ClientCampaignService.
SYSTEM_TRACKABLE_TASK_TYPES = {
    'story_view',
    'post_share',
}

RETENTION_HOURS_BY_TASK = {
    'channel_subscribe': 48,
    'chat_join': 48,
    'join_request': 0,
    'post_reaction': 3,
    'post_like': 3,
    'post_comment': 0,
    'chat_message': 0,
    'poll_vote': 0,
    'post_view': 0,
    'link_click': 0,
}

_URL_RE = re.compile(r'(?:https?://|t\.me/|www\.|@[A-Za-z0-9_]{5,})', re.IGNORECASE)
_MEANINGFUL_RE = re.compile(r'[A-Za-zА-Яа-яЁё0-9]')


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
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)

    @staticmethod
    def is_auto_verifiable(task_type: str) -> bool:
        return str(task_type or '') in AUTO_VERIFIABLE_TASK_TYPES

    @staticmethod
    def default_retention_hours(task_type: str) -> int:
        return int(RETENTION_HOURS_BY_TASK.get(str(task_type or ''), 0))

    @staticmethod
    def default_verification_rules(task_type: str) -> dict[str, Any]:
        task_type = str(task_type or '')
        rules: dict[str, Any] = {
            'task_type': task_type,
            'auto_verify': task_type in AUTO_VERIFIABLE_TASK_TYPES,
            'retention_hours': ActivityService.default_retention_hours(task_type),
        }
        if task_type == 'post_like':
            rules['required_reactions'] = ['👍']
        elif task_type == 'post_reaction':
            rules['required_reactions'] = []
        elif task_type in {'post_comment', 'chat_message'}:
            rules.update({
                'min_length': 20 if task_type == 'post_comment' else 10,
                'allow_links': False,
                'allow_emoji_only': False,
                'block_duplicate_text': True,
                'required_keyword': '',
                'prompt': '',
            })
        elif task_type == 'poll_vote':
            rules['required_option_ids'] = []
        return rules

    @staticmethod
    def campaign_rules(campaign) -> dict[str, Any]:
        rules = ActivityService.default_verification_rules(str(campaign['task_type']))
        raw = ''
        keys = set(campaign.keys()) if hasattr(campaign, 'keys') else set()
        if 'verification_json' in keys:
            raw = str(campaign['verification_json'] or '')
        if raw:
            try:
                saved = json.loads(raw)
                if isinstance(saved, dict):
                    rules.update(saved)
            except json.JSONDecodeError:
                pass
        return rules

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
    ) -> int:
        return db.execute(
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
    def _message_parent_target(message) -> tuple[int | None, int | None]:
        reply_to = getattr(message, 'reply_to_message', None)
        if not reply_to:
            return None, None
        parent_message_id = int(reply_to.message_id)
        source_message_id = None
        origin = getattr(reply_to, 'forward_origin', None)
        if origin is not None:
            candidate = getattr(origin, 'message_id', None)
            if candidate is not None:
                try:
                    source_message_id = int(candidate)
                except (TypeError, ValueError):
                    source_message_id = None
        if source_message_id is None:
            candidate = getattr(reply_to, 'forward_from_message_id', None)
            if candidate is not None:
                try:
                    source_message_id = int(candidate)
                except (TypeError, ValueError):
                    source_message_id = None
        return parent_message_id, source_message_id

    @staticmethod
    def record_group_or_channel_message(message) -> int | None:
        ActivityService._store_message_snapshot(message)
        if message.chat.type not in {'group', 'supergroup'}:
            return None
        user = getattr(message, 'from_user', None)
        if not user or bool(getattr(user, 'is_bot', False)):
            return None
        text = (getattr(message, 'text', None) or getattr(message, 'caption', None) or '').strip()
        if not text:
            return None
        parent_message_id, source_message_id = ActivityService._message_parent_target(message)
        normalized = ' '.join(text.lower().split())[:1000]
        ActivityService._insert_event(
            user_id=int(user.id),
            activity_type='comment',
            chat_ref=ActivityService._chat_ref_from_message(message),
            chat_id=int(message.chat.id),
            message_id=int(message.message_id),
            parent_message_id=parent_message_id,
            payload={
                'text': text[:1000],
                'text_hash': hashlib.sha256(normalized.encode('utf-8')).hexdigest(),
                'source_message_id': source_message_id,
                'thread_id': getattr(message, 'message_thread_id', None),
                'has_link': bool(_URL_RE.search(text)),
            },
        )
        return int(user.id)

    @staticmethod
    def record_channel_post(message) -> None:
        ActivityService._store_message_snapshot(message)

    @staticmethod
    def record_reaction(update) -> int | None:
        user = getattr(update, 'user', None)
        chat = getattr(update, 'chat', None)
        if not user or not chat or bool(getattr(user, 'is_bot', False)):
            return None
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
            payload={'reactions': reaction_keys, 'active': bool(reaction_keys)},
        )
        return int(user.id)

    @staticmethod
    def record_chat_member(update) -> int | None:
        chat = getattr(update, 'chat', None)
        new_member = getattr(update, 'new_chat_member', None)
        member_user = getattr(new_member, 'user', None) if new_member else None
        if not chat or not new_member or not member_user or bool(getattr(member_user, 'is_bot', False)):
            return None
        username = getattr(chat, 'username', None)
        chat_ref = f'@{username}' if username else str(int(chat.id))
        ActivityService._insert_event(
            user_id=int(member_user.id),
            activity_type='chat_member',
            chat_ref=chat_ref,
            chat_id=int(chat.id),
            payload={
                'status': getattr(new_member, 'status', None),
                'is_member': getattr(new_member, 'is_member', None),
                'actor_user_id': int(update.from_user.id) if getattr(update, 'from_user', None) else None,
            },
        )
        return int(member_user.id)

    @staticmethod
    def record_chat_join_request(update) -> int | None:
        chat = getattr(update, 'chat', None)
        user = getattr(update, 'from_user', None)
        if not chat or not user or bool(getattr(user, 'is_bot', False)):
            return None
        username = getattr(chat, 'username', None)
        chat_ref = f'@{username}' if username else str(int(chat.id))
        invite_link = getattr(update, 'invite_link', None)
        ActivityService._insert_event(
            user_id=int(user.id),
            activity_type='join_request',
            chat_ref=chat_ref,
            chat_id=int(chat.id),
            payload={
                'user_chat_id': getattr(update, 'user_chat_id', None),
                'bio': (getattr(update, 'bio', None) or '')[:500],
                'invite_link': getattr(invite_link, 'invite_link', None) if invite_link else None,
            },
        )
        return int(user.id)

    @staticmethod
    def record_poll_answer(update) -> int | None:
        user = getattr(update, 'user', None)
        if not user or bool(getattr(user, 'is_bot', False)):
            return None
        option_ids = list(getattr(update, 'option_ids', []) or [])
        ActivityService._insert_event(
            user_id=int(user.id),
            activity_type='poll_vote',
            poll_id=str(update.poll_id),
            payload={'option_ids': option_ids, 'active': bool(option_ids)},
        )
        return int(user.id)


    @staticmethod
    def record_mini_app_open(
        user_id: int,
        *,
        hint: str = '',
        source: str = 'embedded_webapp',
        payload: dict[str, Any] | None = None,
    ) -> None:
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
    def record_target_open(user_id: int, submission_id: int, campaign_id: int, target_url: str) -> None:
        ActivityService._insert_event(
            user_id=int(user_id),
            activity_type='target_open',
            target_value=str(submission_id),
            payload={
                'submission_id': int(submission_id),
                'campaign_id': int(campaign_id),
                'target_url': (target_url or '')[:500],
                'server_recorded': True,
            },
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
                return TargetInfo(raw=target_url, chat_ref=f'-100{parts[1]}', message_id=int(parts[2]))
            if parts:
                chat_ref = f'@{parts[0]}' if not parts[0].startswith('+') else None
                return TargetInfo(
                    raw=target_url,
                    chat_ref=chat_ref,
                    bot_username=f'@{parts[0]}' if chat_ref else None,
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
    def _load_payload(row) -> dict[str, Any]:
        try:
            data = json.loads(str(row['payload_json'] or '{}'))
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, TypeError):
            return {}

    @staticmethod
    def _latest_event(
        user_id: int,
        taken_at: str,
        activity_type: str,
        *,
        candidate_chat_refs: list[str] | None = None,
        message_id: int | None = None,
        poll_id: str | None = None,
        target_value: str | None = None,
    ):
        params: list[Any] = [user_id, activity_type, taken_at]
        query = '''
            SELECT * FROM activity_events
            WHERE user_id = ? AND activity_type = ? AND created_at >= ?
        '''
        if candidate_chat_refs:
            placeholders = ','.join('?' for _ in candidate_chat_refs)
            query += f' AND chat_ref IN ({placeholders})'
            params.extend(candidate_chat_refs)
        if message_id is not None:
            query += ' AND message_id = ?'
            params.append(int(message_id))
        if poll_id is not None:
            query += ' AND poll_id = ?'
            params.append(str(poll_id))
        if target_value is not None:
            query += ' AND target_value = ?'
            params.append(str(target_value))
        query += ' ORDER BY id DESC LIMIT 1'
        return db.fetch_one(query, tuple(params))

    @staticmethod
    def _comment_event(user_id: int, taken_at: str, refs: list[str], message_id: int | None):
        if not refs:
            return None
        placeholders = ','.join('?' for _ in refs)
        rows = db.fetch_all(
            f'''
            SELECT * FROM activity_events
            WHERE user_id = ? AND activity_type = 'comment' AND created_at >= ?
              AND chat_ref IN ({placeholders})
            ORDER BY id DESC LIMIT 30
            ''',
            (user_id, taken_at, *refs),
        )
        for row in rows:
            if message_id is None:
                return row
            payload = ActivityService._load_payload(row)
            source_message_id = payload.get('source_message_id')
            if int(row['parent_message_id'] or 0) == int(message_id):
                return row
            if int(row['message_id'] or 0) == int(message_id):
                return row
            try:
                if source_message_id is not None and int(source_message_id) == int(message_id):
                    return row
            except (TypeError, ValueError):
                pass
        return None

    @staticmethod
    def _comment_quality(row, rules: dict[str, Any]) -> tuple[bool, str]:
        payload = ActivityService._load_payload(row)
        text = str(payload.get('text') or '').strip()
        min_length = max(1, min(int(rules.get('min_length') or 1), 1000))
        if len(text) < min_length:
            return False, 'task_comment_too_short'
        if not bool(rules.get('allow_emoji_only', False)) and not _MEANINGFUL_RE.search(text):
            return False, 'task_comment_emoji_only'
        if not bool(rules.get('allow_links', False)) and bool(payload.get('has_link') or _URL_RE.search(text)):
            return False, 'task_comment_link_blocked'
        keyword = str(rules.get('required_keyword') or '').strip().lower()
        if keyword and keyword not in text.lower():
            return False, 'task_comment_condition_missing'
        if bool(rules.get('block_duplicate_text', True)):
            text_hash = str(payload.get('text_hash') or '')
            if text_hash:
                duplicate = db.fetch_one(
                    '''
                    SELECT id FROM activity_events
                    WHERE activity_type='comment' AND id != ? AND payload_json LIKE ?
                    ORDER BY id DESC LIMIT 1
                    ''',
                    (int(row['id']), f'%{text_hash}%'),
                )
                if duplicate:
                    return False, 'task_comment_duplicate'
        return True, 'task_auto_verified'

    @staticmethod
    def _observed_poll_id(candidate_chat_refs: list[str], message_id: int) -> str | None:
        if not candidate_chat_refs or not message_id:
            return None
        placeholders = ','.join('?' for _ in candidate_chat_refs)
        row = db.fetch_one(
            f'''
            SELECT poll_id FROM observed_messages
            WHERE chat_ref IN ({placeholders}) AND message_id = ? AND poll_id IS NOT NULL
            ORDER BY created_at DESC LIMIT 1
            ''',
            (*candidate_chat_refs, message_id),
        )
        return str(row['poll_id']) if row and row['poll_id'] else None

    @staticmethod
    def observed_poll_id(bot, target_url: str) -> str | None:
        info = ActivityService.parse_target(target_url)
        refs = ActivityService._candidate_chat_refs(bot, info)
        return ActivityService._observed_poll_id(refs, info.message_id or 0)

    @staticmethod
    def _mini_app_match(user_id: int, taken_at: str, hint: str | None) -> bool:
        rows = db.fetch_all(
            '''
            SELECT * FROM activity_events
            WHERE user_id = ? AND activity_type = 'mini_app_open' AND created_at >= ?
            ORDER BY id DESC LIMIT 5
            ''',
            (user_id, taken_at),
        )
        if not rows:
            return False
        if not hint:
            return True
        hint_l = hint.lower()
        return any(hint_l in (str(row['target_value'] or '') + ' ' + str(row['payload_json'] or '')).lower() for row in rows)

    @staticmethod
    def auto_verify_submission(bot, user_id: int, campaign, submission) -> tuple[str, str]:
        task_type = str(campaign['task_type'])
        keys = set(campaign.keys()) if hasattr(campaign, 'keys') else set()
        if 'auto_verify_enabled' in keys and int(campaign['auto_verify_enabled'] or 0) != 1:
            return 'manual', 'task_verify_manual_only'
        if task_type not in AUTO_VERIFIABLE_TASK_TYPES:
            return 'manual', 'task_verify_manual_only'

        rules = ActivityService.campaign_rules(campaign)
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
            return 'unavailable', 'task_verify_unavailable'

        if task_type == 'join_request':
            row = ActivityService._latest_event(user_id, taken_at, 'join_request', candidate_chat_refs=candidate_refs)
            return ('verified', 'task_auto_verified') if row else ('pending', 'task_join_request_not_found')

        if task_type in {'post_comment', 'chat_message'}:
            row = ActivityService._comment_event(
                user_id,
                taken_at,
                candidate_refs,
                info.message_id if task_type == 'post_comment' else None,
            )
            if not row:
                return 'pending', 'task_comment_not_found' if task_type == 'post_comment' else 'task_message_not_found'
            quality_ok, key = ActivityService._comment_quality(row, rules)
            return ('verified', 'task_auto_verified') if quality_ok else ('failed', key)

        if task_type in {'post_reaction', 'post_like'}:
            if not candidate_refs or info.message_id is None:
                return 'unavailable', 'task_verify_unavailable'
            row = ActivityService._latest_event(
                user_id,
                taken_at,
                'reaction',
                candidate_chat_refs=candidate_refs,
                message_id=info.message_id,
            )
            if not row:
                return 'pending', 'task_reaction_not_found'
            reactions = list(ActivityService._load_payload(row).get('reactions') or [])
            if not reactions:
                return 'failed', 'task_reaction_removed'
            required = [str(item) for item in (rules.get('required_reactions') or []) if str(item)]
            if required and not any(item in reactions for item in required):
                return 'failed', 'task_reaction_wrong'
            return 'verified', 'task_auto_verified'

        if task_type == 'poll_vote':
            poll_id = str(rules.get('poll_id') or '') or ActivityService._observed_poll_id(candidate_refs, info.message_id or 0)
            if not poll_id:
                return 'unavailable', 'task_poll_unavailable'
            row = ActivityService._latest_event(user_id, taken_at, 'poll_vote', poll_id=poll_id)
            if not row:
                return 'pending', 'task_poll_vote_not_found'
            option_ids = [int(value) for value in (ActivityService._load_payload(row).get('option_ids') or [])]
            if not option_ids:
                return 'failed', 'task_poll_vote_removed'
            required = [int(value) for value in (rules.get('required_option_ids') or [])]
            if required and not any(value in option_ids for value in required):
                return 'failed', 'task_poll_vote_wrong'
            return 'verified', 'task_auto_verified'



        if task_type in {'post_view', 'link_click'}:
            row = ActivityService._latest_event(
                user_id,
                taken_at,
                'target_open',
                target_value=str(int(submission['id'])),
            )
            if row:
                return 'verified', 'task_auto_verified'
            return 'pending', 'task_target_not_opened'

        return 'manual', 'task_verify_manual_only'
