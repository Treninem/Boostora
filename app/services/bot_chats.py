from __future__ import annotations

from datetime import datetime, timezone

from app import db
from app.services.runtime_settings import RuntimeSettingsService


ACTIVE_STATUSES = {"member", "administrator", "creator"}
PROMOTABLE_TYPES = {"group", "supergroup", "channel"}


class BotChatService:
    @staticmethod
    def upsert_chat(
        *,
        chat_id: int,
        chat_ref: str,
        title: str = '',
        chat_type: str = '',
        username: str = '',
        is_active: bool = True,
        can_post: bool = True,
        can_invite_users: bool | None = None,
        owner_user_id: int | None = None,
        member_count: int | None = None,
    ) -> None:
        count_value = None if member_count is None else max(0, int(member_count))
        eligible = bool(
            is_active
            and can_post
            and bool(can_invite_users)
            and count_value is not None
            and count_value >= RuntimeSettingsService.get_int('network_min_members')
        )
        network_status = 'eligible' if eligible else ('pending' if is_active and can_post else 'disabled')
        db.execute(
            '''
            INSERT INTO bot_chats (
                chat_id, chat_ref, title, chat_type, username, is_active, can_post, can_invite_users,
                owner_user_id, member_count, network_enabled, network_status,
                last_seen_at, last_activity_at, verified_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, COALESCE(?, 0), ?, COALESCE(?, 0), 1, ?, CURRENT_TIMESTAMP,
                      CURRENT_TIMESTAMP, CASE WHEN ? IS NOT NULL THEN CURRENT_TIMESTAMP ELSE NULL END,
                      CURRENT_TIMESTAMP)
            ON CONFLICT(chat_id) DO UPDATE SET
                chat_ref = excluded.chat_ref,
                title = excluded.title,
                chat_type = excluded.chat_type,
                username = excluded.username,
                is_active = excluded.is_active,
                can_post = excluded.can_post,
                can_invite_users = CASE WHEN ? IS NULL THEN bot_chats.can_invite_users ELSE excluded.can_invite_users END,
                owner_user_id = COALESCE(bot_chats.owner_user_id, excluded.owner_user_id),
                member_count = CASE WHEN ? IS NULL THEN bot_chats.member_count ELSE excluded.member_count END,
                network_enabled = CASE
                    WHEN bot_chats.network_status = 'limit_exceeded' THEN 0
                    WHEN excluded.is_active = 1 AND excluded.can_post = 1 THEN 1
                    ELSE bot_chats.network_enabled
                END,
                network_status = CASE
                    WHEN excluded.is_active = 0 OR excluded.can_post = 0 THEN 'disabled'
                    WHEN (CASE WHEN ? IS NULL THEN bot_chats.can_invite_users ELSE excluded.can_invite_users END) = 0 THEN 'pending'
                    WHEN (CASE WHEN ? IS NULL THEN bot_chats.member_count ELSE excluded.member_count END) >= ? THEN 'eligible'
                    ELSE 'pending'
                END,
                disabled_reason = CASE WHEN excluded.is_active = 1 AND excluded.can_post = 1 THEN NULL ELSE 'bot_access_removed' END,
                last_seen_at = CURRENT_TIMESTAMP,
                last_activity_at = CURRENT_TIMESTAMP,
                verified_at = CASE WHEN ? IS NULL THEN bot_chats.verified_at ELSE CURRENT_TIMESTAMP END,
                updated_at = CURRENT_TIMESTAMP
            ''',
            (
                int(chat_id), str(chat_ref), str(title or ''), str(chat_type or ''), str(username or ''),
                1 if is_active else 0, 1 if can_post else 0,
                None if can_invite_users is None else (1 if can_invite_users else 0),
                int(owner_user_id) if owner_user_id else None,
                count_value,
                network_status,
                count_value,
                None if can_invite_users is None else (1 if can_invite_users else 0),
                count_value,
                None if can_invite_users is None else (1 if can_invite_users else 0),
                count_value,
                RuntimeSettingsService.get_int('network_min_members'),
                count_value,
            ),
        )

    @staticmethod
    def update_member_count(chat_id: int, member_count: int) -> None:
        safe_count = max(0, int(member_count))
        status = 'eligible' if safe_count >= RuntimeSettingsService.get_int('network_min_members') else 'pending'
        db.execute(
            '''
            UPDATE bot_chats
            SET member_count = ?, network_status = CASE
                    WHEN is_active = 1 AND can_post = 1 AND can_invite_users = 1 AND network_enabled = 1 THEN ?
                    ELSE network_status
                END,
                verified_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
            WHERE chat_id = ?
            ''',
            (safe_count, status, int(chat_id)),
        )

    @staticmethod
    def deactivate_chat(chat_id: int) -> None:
        db.execute(
            '''
            INSERT INTO bot_chats (
                chat_id, chat_ref, is_active, can_post, network_status, disabled_reason,
                last_seen_at, updated_at
            ) VALUES (?, ?, 0, 0, 'disabled', 'bot_access_removed', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT(chat_id) DO UPDATE SET
                is_active = 0,
                can_post = 0,
                network_status = 'disabled',
                disabled_reason = 'bot_access_removed',
                updated_at = CURRENT_TIMESTAMP
            ''',
            (int(chat_id), str(chat_id)),
        )

    @staticmethod
    def _chat_ref(chat) -> str:
        username = getattr(chat, 'username', None)
        if username:
            return f'@{username}'
        return str(int(chat.id))

    @staticmethod
    def register_verified_platform(bot, chat_ref: str | int, owner_user_id: int) -> bool:  # noqa: ANN001
        """Register a channel/chat immediately after a successful access check.

        Telegram normally sends a my_chat_member update when the bot is added,
        but this extra verification removes the delay between adding the bot and
        using the platform in the advertising network. It never overwrites an
        already recorded owner.
        """
        try:
            api_ref = int(chat_ref) if str(chat_ref).lstrip('-').isdigit() else str(chat_ref)
            chat = bot.get_chat(api_ref)
            chat_type = str(getattr(chat, 'type', '') or '')
            if chat_type not in PROMOTABLE_TYPES:
                return False
            me = bot.get_me()
            membership = bot.get_chat_member(int(chat.id), int(me.id))
            status = str(getattr(membership, 'status', '') or '')
            if status not in ACTIVE_STATUSES:
                return False
            is_admin = status in {'administrator', 'creator'}
            post_perm = getattr(membership, 'can_post_messages', None)
            send_perm = getattr(membership, 'can_send_messages', None)
            can_post = bool(is_admin and (post_perm is not False) and (send_perm is not False))
            can_invite = bool(getattr(membership, 'can_invite_users', False) or status == 'creator')
            try:
                member_count = max(0, int(bot.get_chat_member_count(int(chat.id))))
            except Exception:
                member_count = None
            BotChatService.upsert_chat(
                chat_id=int(chat.id),
                chat_ref=BotChatService._chat_ref(chat),
                title=(getattr(chat, 'title', None) or getattr(chat, 'full_name', None) or ''),
                chat_type=chat_type,
                username=(getattr(chat, 'username', None) or ''),
                is_active=True,
                can_post=can_post,
                can_invite_users=can_invite,
                owner_user_id=int(owner_user_id),
                member_count=member_count,
            )
            BotChatService.enforce_owner_platform_limit(int(owner_user_id))
            return True
        except Exception:
            return False

    @staticmethod
    def touch_from_message(message) -> None:
        chat = getattr(message, 'chat', None)
        if not chat:
            return
        chat_type = getattr(chat, 'type', '') or ''
        if chat_type not in PROMOTABLE_TYPES:
            return
        from_user = getattr(message, 'from_user', None)
        existing = db.fetch_one('SELECT can_post FROM bot_chats WHERE chat_id=?', (int(chat.id),))
        BotChatService.upsert_chat(
            chat_id=int(chat.id),
            chat_ref=BotChatService._chat_ref(chat),
            title=(getattr(chat, 'title', None) or getattr(chat, 'full_name', None) or ''),
            chat_type=chat_type,
            username=(getattr(chat, 'username', None) or ''),
            is_active=True,
            # A received message proves activity, not administrator rights.
            # Preserve the last verified posting permission instead of
            # accidentally restoring network eligibility after a downgrade.
            can_post=bool(int(existing['can_post'] or 0)) if existing else False,
            can_invite_users=None,
            owner_user_id=None,
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
        is_admin = status in {'administrator', 'creator'}
        post_perm = getattr(new_member, 'can_post_messages', None)
        send_perm = getattr(new_member, 'can_send_messages', None)
        can_post = bool(is_active and is_admin and post_perm is not False and send_perm is not False)
        invite_perm = getattr(new_member, 'can_invite_users', None)
        can_invite = bool(is_active and (bool(invite_perm) or status == 'creator'))
        actor = getattr(update, 'from_user', None)
        if is_active:
            owner_id = int(actor.id) if actor else None
            BotChatService.upsert_chat(
                chat_id=int(chat.id),
                chat_ref=BotChatService._chat_ref(chat),
                title=(getattr(chat, 'title', None) or getattr(chat, 'full_name', None) or ''),
                chat_type=chat_type,
                username=(getattr(chat, 'username', None) or ''),
                is_active=True,
                can_post=can_post,
                can_invite_users=can_invite,
                owner_user_id=owner_id,
            )
            if owner_id:
                BotChatService.enforce_owner_platform_limit(owner_id)
        else:
            BotChatService.deactivate_chat(int(chat.id))

    @staticmethod
    def _valid_clock(value: str, fallback: str) -> str:
        raw = str(value or fallback).strip()[:5]
        try:
            hour_text, minute_text = raw.split(':', 1)
            hour, minute = int(hour_text), int(minute_text)
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                raise ValueError
            return f'{hour:02d}:{minute:02d}'
        except Exception:
            return fallback

    @staticmethod
    def update_network_settings(
        owner_user_id: int,
        chat_id: int,
        *,
        daily_limit: int,
        window_start: str,
        window_end: str,
        min_interval_hours: int = 6,
        timezone_offset_minutes: int = 0,
        topic_code: str = 'general',
        language_code: str = 'ru',
    ) -> bool:
        row = db.fetch_one('SELECT * FROM bot_chats WHERE chat_id = ? AND owner_user_id = ?', (int(chat_id), int(owner_user_id)))
        if not row:
            return False
        safe_limit = max(1, min(RuntimeSettingsService.get_int('network_max_daily_limit'), int(daily_limit)))
        safe_interval = max(1, min(72, int(min_interval_hours)))
        safe_timezone = max(-720, min(840, int(timezone_offset_minutes)))
        start = BotChatService._valid_clock(window_start, '09:00')
        end = BotChatService._valid_clock(window_end, '22:00')
        db.execute(
            '''
            UPDATE bot_chats
            SET daily_limit = ?, window_start = ?, window_end = ?, min_interval_hours = ?,
                timezone_offset_minutes = ?, topic_code = ?, language_code = ?,
                network_enabled = 1,
                network_status = CASE
                    WHEN is_active = 1 AND can_post = 1 AND can_invite_users = 1 AND member_count >= ? THEN 'eligible'
                    ELSE 'pending'
                END,
                updated_at = CURRENT_TIMESTAMP
            WHERE chat_id = ? AND owner_user_id = ?
            ''',
            (
                safe_limit, start, end, safe_interval, safe_timezone,
                str(topic_code or 'general')[:48], str(language_code or 'ru')[:8],
                RuntimeSettingsService.get_int('network_min_members'), int(chat_id), int(owner_user_id),
            ),
        )
        return True

    @staticmethod
    def enforce_owner_platform_limit(owner_user_id: int) -> None:
        maximum = RuntimeSettingsService.get_int('network_max_platforms_per_user')
        rows = db.fetch_all(
            '''SELECT chat_id FROM bot_chats WHERE owner_user_id=? AND is_active=1
               ORDER BY created_at ASC, chat_id ASC''',
            (int(owner_user_id),),
        )
        allowed_ids = {int(row['chat_id']) for row in rows[:maximum]}
        for row in rows:
            chat_id = int(row['chat_id'])
            if chat_id in allowed_ids:
                db.execute(
                    '''UPDATE bot_chats SET network_enabled=1,
                           network_status=CASE
                               WHEN can_post=1 AND can_invite_users=1 AND member_count>=? THEN 'eligible' ELSE 'pending' END,
                           disabled_reason=NULL, updated_at=CURRENT_TIMESTAMP
                       WHERE chat_id=? AND network_status='limit_exceeded' ''',
                    (RuntimeSettingsService.get_int('network_min_members'), chat_id),
                )
            else:
                db.execute(
                    '''UPDATE bot_chats SET network_enabled=0, network_status='limit_exceeded',
                           disabled_reason='owner_platform_limit', updated_at=CURRENT_TIMESTAMP
                       WHERE chat_id=?''',
                    (chat_id,),
                )

    @staticmethod
    def list_user_network_chats(owner_user_id: int):
        return db.fetch_all(
            '''
            SELECT * FROM bot_chats
            WHERE owner_user_id = ?
            ORDER BY is_active DESC, network_status = 'eligible' DESC, member_count DESC, chat_id DESC
            LIMIT 100
            ''',
            (int(owner_user_id),),
        )

    @staticmethod
    def count_user_chats(owner_user_id: int) -> int:
        row = db.fetch_one('SELECT COUNT(*) AS cnt FROM bot_chats WHERE owner_user_id = ?', (int(owner_user_id),))
        return int(row['cnt'] or 0) if row else 0

    @staticmethod
    def list_network_eligible(*, exclude_owner_user_id: int | None = None, limit: int = 500):
        where = '''is_active = 1 AND can_post = 1 AND can_invite_users = 1 AND network_enabled = 1
                   AND network_status = 'eligible' AND member_count >= ?'''
        params: list[object] = [RuntimeSettingsService.get_int('network_min_members')]
        if exclude_owner_user_id:
            where += ' AND COALESCE(owner_user_id, 0) != ?'
            params.append(int(exclude_owner_user_id))
        params.append(max(1, min(int(limit), 2000)))
        return db.fetch_all(
            f'''
            SELECT * FROM bot_chats
            WHERE {where}
            ORDER BY quality_score DESC, member_count DESC, COALESCE(last_seen_at, created_at) ASC
            LIMIT ?
            ''',
            tuple(params),
        )

    @staticmethod
    def refresh_network_metrics(bot, limit: int = 100) -> dict[str, int]:  # noqa: ANN001
        """Refresh observable platform metrics without claiming a full member audit.

        Telegram Bot API does not expose the complete channel member list. The
        score therefore uses observable activity, member count, network history,
        and retention rather than pretending to know every inactive account.
        """
        activity_days = RuntimeSettingsService.get_int('network_activity_days')
        activity_modifier = f'-{activity_days} days'
        rows = db.fetch_all(
            '''SELECT * FROM bot_chats WHERE is_active = 1 AND can_post = 1
               ORDER BY COALESCE(verified_at, created_at) ASC LIMIT ?''',
            (max(1, min(int(limit), 500)),),
        )
        checked = updated = 0
        for row in rows:
            chat_id = int(row['chat_id'])
            checked += 1
            member_count = int(row['member_count'] or 0)
            can_post = bool(int(row['can_post'] or 0))
            can_invite = bool(int(row['can_invite_users'] or 0))
            try:
                member_count = max(0, int(bot.get_chat_member_count(chat_id)))
            except Exception:
                pass
            try:
                me = bot.get_me()
                membership = bot.get_chat_member(chat_id, int(me.id))
                member_status = str(getattr(membership, 'status', '') or '')
                can_post = member_status == 'creator' or bool(getattr(membership, 'can_post_messages', False)) or (str(row['chat_type'] or '') in {'group', 'supergroup'} and member_status == 'administrator')
                can_invite = member_status == 'creator' or bool(getattr(membership, 'can_invite_users', False))
            except Exception:
                pass
            activity = db.fetch_one(
                '''SELECT COUNT(*) AS events, COUNT(DISTINCT user_id) AS active_users,
                          MAX(created_at) AS last_activity
                   FROM activity_events
                   WHERE chat_id = ? AND datetime(created_at) >= datetime('now', ?)''',
                (chat_id, activity_modifier),
            )
            posts = db.fetch_one(
                '''SELECT COUNT(*) AS posts, MAX(created_at) AS last_post
                   FROM observed_messages
                   WHERE chat_id = ? AND datetime(created_at) >= datetime('now', ?)''',
                (chat_id, activity_modifier),
            )
            history = db.fetch_one(
                '''SELECT COUNT(*) AS total,
                          SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) AS completed,
                          SUM(joins) AS joins, SUM(retained_7d) AS retained
                   FROM network_placements WHERE host_chat_id = ?''',
                (chat_id,),
            )
            events = int(activity['events'] or 0) if activity else 0
            active_users = int(activity['active_users'] or 0) if activity else 0
            post_count = int(posts['posts'] or 0) if posts else 0
            total = int(history['total'] or 0) if history else 0
            completed = int(history['completed'] or 0) if history else 0
            joins = int(history['joins'] or 0) if history else 0
            retained = int(history['retained'] or 0) if history else 0
            reliability = completed / total if total else 0.75
            retention = retained / joins if joins else 0.60
            if str(row['chat_type'] or '') in {'group', 'supergroup'}:
                activity_ratio = min(1.0, active_users / max(1.0, member_count * 0.12))
                volume_ratio = min(1.0, events / max(10.0, member_count * 0.20))
                activity_score = activity_ratio * 0.65 + volume_ratio * 0.35
            else:
                activity_score = min(1.0, post_count / 12.0)
            score = round(25 + 35 * activity_score + 25 * reliability + 15 * retention)
            score = max(20, min(100, int(score)))
            last_activity = ''
            for candidate in (
                str(activity['last_activity'] or '') if activity else '',
                str(posts['last_post'] or '') if posts else '',
                str(row['last_activity_at'] or ''),
            ):
                if candidate and candidate > last_activity:
                    last_activity = candidate
            eligible = bool(member_count >= RuntimeSettingsService.get_int('network_min_members') and can_post and can_invite)
            db.execute(
                '''UPDATE bot_chats SET member_count=?, quality_score=?, observed_active_users=?, observed_activity_events=?, can_post=?, can_invite_users=?,
                       last_activity_at=COALESCE(NULLIF(?, ''), last_activity_at),
                       network_status=CASE
                           WHEN is_active=0 OR ?=0 THEN 'disabled'
                           WHEN network_status='limit_exceeded' THEN 'limit_exceeded'
                           WHEN network_enabled=1 AND ? THEN 'eligible'
                           ELSE 'pending'
                       END,
                       verified_at=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP
                   WHERE chat_id=?''',
                (member_count, score, active_users, events, 1 if can_post else 0, 1 if can_invite else 0, last_activity, 1 if can_post else 0, 1 if eligible else 0, chat_id),
            )
            updated += 1
        return {'checked': checked, 'updated': updated}

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
        row = db.fetch_one('SELECT COUNT(*) AS cnt FROM bot_chats WHERE is_active = 1')
        return int(row['cnt'] or 0) if row else 0

    @staticmethod
    def list_all_chats(limit: int = 10, offset: int = 0):
        return db.fetch_all(
            '''
            SELECT * FROM bot_chats
            WHERE is_active = 1
            ORDER BY COALESCE(last_seen_at, updated_at) DESC, chat_id DESC
            LIMIT ? OFFSET ?
            ''',
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
