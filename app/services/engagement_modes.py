from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from app.time_utils import utcnow
from app import db
from app.config import settings
from app.services.runtime_settings import RuntimeSettingsService
from app.services.wallets import WalletService

STANDARD_MODE = 'standard'
PRO_MODE = 'pro'
ENGAGEMENT_TASK_TYPES = {'post_reaction', 'post_like', 'post_comment'}


@dataclass(frozen=True)
class EngagementMode:
    code: str
    title_key: str
    desc_key: str
    required_actions: int
    price_stars: int


class EngagementModeService:
    """Standard/PRO layer for mutual Telegram engagement."""

    @staticmethod
    def required_actions() -> int:
        return max(1, int(settings.engagement_standard_required_actions))

    @staticmethod
    def pro_price_stars() -> int:
        return max(1, int(settings.engagement_pro_monthly_stars))

    @staticmethod
    def pro_price_credits() -> int:
        return max(1, RuntimeSettingsService.get_int('engagement_pro_monthly_credits'))

    @staticmethod
    def purchase_pro_with_credits(user_id: int, *, days: int = 30, source: str = 'credits') -> tuple[bool, str]:
        price = EngagementModeService.pro_price_credits()
        spent = WalletService.spend_internal_balance(
            int(user_id), price, entry_type='engagement_pro_purchase',
            note=f'Boostora PRO {max(1, int(days))} days',
        )
        if not spent:
            return False, 'insufficient_internal_balance'
        try:
            EngagementModeService.activate_pro(int(user_id), days=max(1, int(days)), source=source)
        except Exception:
            WalletService.credit_internal_balance(
                int(user_id), price, entry_type='engagement_pro_purchase_refund',
                note='PRO activation failed',
            )
            raise
        return True, 'engagement_pro_activated_notice'

    @staticmethod
    def due_hours() -> int:
        return max(1, int(getattr(settings, 'engagement_obligation_due_hours', 24)))

    @staticmethod
    def reminder_before_hours() -> int:
        return max(1, int(getattr(settings, 'engagement_reminder_before_hours', 6)))

    @staticmethod
    def reminders_enabled() -> bool:
        return bool(getattr(settings, 'engagement_reminders_enabled', True))

    @staticmethod
    def overdue_blocks_standard() -> bool:
        return bool(getattr(settings, 'engagement_overdue_blocks_standard', True))

    @staticmethod
    def admin_warnings_enabled() -> bool:
        return bool(getattr(settings, 'engagement_admin_warnings_enabled', True))

    @staticmethod
    def is_engagement_task(task_type: str | None) -> bool:
        return str(task_type or '').strip() in ENGAGEMENT_TASK_TYPES

    @staticmethod
    def modes() -> tuple[EngagementMode, EngagementMode]:
        return (
            EngagementMode(STANDARD_MODE, 'engagement_mode_standard_title', 'engagement_mode_standard_desc', EngagementModeService.required_actions(), 0),
            EngagementMode(PRO_MODE, 'engagement_mode_pro_title', 'engagement_mode_pro_desc', 0, EngagementModeService.pro_price_stars()),
        )

    @staticmethod
    def get_membership(user_id: int):
        return db.fetch_one('SELECT * FROM engagement_memberships WHERE user_id = ?', (user_id,))

    @staticmethod
    def _pro_is_active(row) -> bool:
        if not row or str(row['mode']) != PRO_MODE or str(row['status']) != 'active':
            return False
        expires = str(row['pro_expires_at'] or '')
        if not expires:
            return False
        try:
            return datetime.fromisoformat(expires) > utcnow()
        except ValueError:
            return False

    @staticmethod
    def current_mode(user_id: int) -> str:
        row = EngagementModeService.get_membership(user_id)
        if not row:
            return ''
        if str(row['mode']) == PRO_MODE:
            return PRO_MODE if EngagementModeService._pro_is_active(row) else STANDARD_MODE
        return STANDARD_MODE

    @staticmethod
    def set_standard(user_id: int, *, source: str = 'bot') -> None:
        required = EngagementModeService.required_actions()
        db.execute(
            '''
            INSERT INTO engagement_memberships (user_id, mode, status, pro_expires_at, reciprocal_required_actions, selected_at, updated_at, source)
            VALUES (?, 'standard', 'active', NULL, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                mode = 'standard', status = 'active', pro_expires_at = NULL,
                reciprocal_required_actions = excluded.reciprocal_required_actions,
                updated_at = CURRENT_TIMESTAMP, source = excluded.source
            ''',
            (user_id, required, source),
        )

    @staticmethod
    def activate_pro(user_id: int, *, days: int = 30, source: str = 'stars') -> None:
        expires = utcnow() + timedelta(days=max(int(days), 1))
        db.execute(
            '''
            INSERT INTO engagement_memberships (user_id, mode, status, pro_expires_at, reciprocal_required_actions, selected_at, updated_at, source)
            VALUES (?, 'pro', 'active', ?, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                mode = 'pro', status = 'active', pro_expires_at = excluded.pro_expires_at,
                reciprocal_required_actions = 0, updated_at = CURRENT_TIMESTAMP, source = excluded.source
            ''',
            (user_id, expires.isoformat(timespec='seconds'), source),
        )

    @staticmethod
    def approved_outgoing_actions(user_id: int, *, since: str | None = None) -> int:
        params: list[Any] = [user_id, *sorted(ENGAGEMENT_TASK_TYPES)]
        extra = ''
        if since:
            extra = ' AND s.reviewed_at >= ?'
            params.append(since)
        placeholders = ','.join('?' for _ in ENGAGEMENT_TASK_TYPES)
        row = db.fetch_one(
            f'''
            SELECT COUNT(*) AS cnt
            FROM task_submissions s
            JOIN campaigns c ON c.id = s.campaign_id
            WHERE s.performer_user_id = ?
              AND s.status = 'approved'
              AND c.task_type IN ({placeholders})
              {extra}
            ''',
            tuple(params),
        )
        return int(row['cnt'] or 0) if row else 0

    @staticmethod
    def create_obligation_for_campaign(user_id: int, campaign_id: int, task_type: str, quantity: int = 0) -> int | None:
        if not EngagementModeService.is_engagement_task(task_type):
            return None
        if EngagementModeService.current_mode(user_id) == PRO_MODE:
            return None
        row = EngagementModeService.get_membership(user_id)
        if not row:
            EngagementModeService.set_standard(user_id, source='auto_standard_campaign')
        required = EngagementModeService.required_actions()
        due = utcnow() + timedelta(hours=EngagementModeService.due_hours())
        return db.execute(
            '''
            INSERT INTO engagement_obligations (user_id, campaign_id, task_type, required_actions, status, due_at)
            VALUES (?, ?, ?, ?, 'open', ?)
            ''',
            (user_id, campaign_id, task_type, required, due.isoformat(timespec='seconds')),
        )

    @staticmethod
    def refresh_obligations(user_id: int) -> None:
        rows = db.fetch_all(
            '''
            SELECT * FROM engagement_obligations
            WHERE user_id = ? AND status = 'open'
            ORDER BY created_at ASC, id ASC
            ''',
            (user_id,),
        )
        for row in rows:
            done = EngagementModeService.approved_outgoing_actions(user_id, since=str(row['created_at']))
            if done >= int(row['required_actions'] or 0):
                db.execute(
                    "UPDATE engagement_obligations SET status = 'completed', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (int(row['id']),),
                )

    @staticmethod
    def open_obligations(user_id: int) -> list:
        EngagementModeService.refresh_obligations(user_id)
        return db.fetch_all(
            '''
            SELECT * FROM engagement_obligations
            WHERE user_id = ? AND status = 'open'
            ORDER BY due_at ASC, id ASC
            LIMIT 10
            ''',
            (user_id,),
        )


    @staticmethod
    def _dt(value: str | None) -> datetime | None:
        raw = str(value or '').strip()
        if not raw:
            return None
        try:
            return datetime.fromisoformat(raw)
        except ValueError:
            return None

    @staticmethod
    def _task_label_key(task_type: str) -> str:
        mapping = {
            'post_reaction': 'campaign_task_type_post_reaction',
            'post_like': 'campaign_task_type_post_like',
            'post_comment': 'campaign_task_type_post_comment',
        }
        return mapping.get(str(task_type or ''), 'campaign_task_type_post_reaction')

    @staticmethod
    def obligation_progress(row) -> dict[str, Any]:
        created_at = str(row['created_at'] or '')
        required = max(int(row['required_actions'] or 0), 0)
        done = min(required, EngagementModeService.approved_outgoing_actions(int(row['user_id']), since=created_at))
        remaining = max(required - done, 0)
        due_at = str(row['due_at'] or '')
        due_dt = EngagementModeService._dt(due_at)
        now = utcnow()
        overdue = bool(due_dt and due_dt < now and remaining > 0)
        due_soon = bool(due_dt and due_dt <= now + timedelta(hours=6) and remaining > 0 and not overdue)
        if remaining <= 0:
            state = 'completed'
        elif overdue:
            state = 'overdue'
        elif due_soon:
            state = 'due_soon'
        else:
            state = 'open'
        percent = int(round((done / max(required, 1)) * 100)) if required else 100
        return {
            'id': int(row['id']),
            'user_id': int(row['user_id']),
            'campaign_id': int(row['campaign_id'] or 0),
            'task_type': str(row['task_type'] or ''),
            'task_label_key': EngagementModeService._task_label_key(str(row['task_type'] or '')),
            'required': required,
            'done': done,
            'remaining': remaining,
            'percent': max(0, min(100, percent)),
            'state': state,
            'due_at': due_at,
            'created_at': created_at,
        }

    @staticmethod
    def obligation_items(user_id: int, *, limit: int = 10) -> list[dict[str, Any]]:
        EngagementModeService.refresh_obligations(user_id)
        rows = db.fetch_all(
            """
            SELECT * FROM engagement_obligations
            WHERE user_id = ? AND status = 'open'
            ORDER BY due_at ASC, id ASC
            LIMIT ?
            """,
            (user_id, int(limit)),
        )
        return [EngagementModeService.obligation_progress(row) for row in rows]

    @staticmethod
    def obligation_dashboard(user_id: int) -> dict[str, Any]:
        items = EngagementModeService.obligation_items(user_id, limit=12)
        completed_total_row = db.fetch_one(
            "SELECT COUNT(*) AS cnt FROM engagement_obligations WHERE user_id = ? AND status = 'completed'",
            (user_id,),
        )
        overdue = sum(1 for item in items if item['state'] == 'overdue')
        due_soon = sum(1 for item in items if item['state'] == 'due_soon')
        total_required = sum(int(item['required']) for item in items)
        total_done = sum(int(item['done']) for item in items)
        total_remaining = sum(int(item['remaining']) for item in items)
        status = 'clear'
        if overdue:
            status = 'overdue'
        elif due_soon:
            status = 'due_soon'
        elif total_remaining > 0:
            status = 'open'
        return {
            'items': items,
            'status': status,
            'open_count': len(items),
            'overdue_count': overdue,
            'due_soon_count': due_soon,
            'total_required': total_required,
            'total_done': total_done,
            'total_remaining': total_remaining,
            'completed_total': int(completed_total_row['cnt'] or 0) if completed_total_row else 0,
            'outgoing_30d': EngagementModeService.approved_outgoing_actions(
                user_id,
                since=(utcnow() - timedelta(days=30)).isoformat(timespec='seconds'),
            ),
        }

    @staticmethod
    def admin_obligation_overview(*, limit: int = 15) -> dict[str, Any]:
        try:
            rows = db.fetch_all(
                """
                SELECT o.*, u.username, u.first_name, u.language_code
                FROM engagement_obligations o
                LEFT JOIN users u ON u.user_id = o.user_id
                WHERE o.status = 'open'
                ORDER BY o.due_at ASC, o.created_at ASC, o.id ASC
                LIMIT ?
                """,
                (int(limit),),
            )
            items = []
            for row in rows:
                progress = EngagementModeService.obligation_progress(row)
                progress['username'] = str(row['username'] or '')
                progress['first_name'] = str(row['first_name'] or '')
                items.append(progress)
            total = db.fetch_one("SELECT COUNT(*) AS cnt FROM engagement_obligations WHERE status = 'open'")
            overdue = 0
            due_soon = 0
            for row in db.fetch_all("SELECT * FROM engagement_obligations WHERE status = 'open' LIMIT 500"):
                state = EngagementModeService.obligation_progress(row)['state']
                overdue += 1 if state == 'overdue' else 0
                due_soon += 1 if state == 'due_soon' else 0
            return {
                'table_ready': True,
                'items': items,
                'open_total': int(total['cnt'] or 0) if total else 0,
                'overdue_total': overdue,
                'due_soon_total': due_soon,
                'required_actions': EngagementModeService.required_actions(),
            }
        except Exception:
            return {
                'table_ready': False,
                'items': [],
                'open_total': 0,
                'overdue_total': 0,
                'due_soon_total': 0,
                'required_actions': EngagementModeService.required_actions(),
            }


    @staticmethod
    def soft_restriction(user_id: int) -> dict[str, Any]:
        """Return soft Standard restriction state without touching money or old flows."""
        dashboard = EngagementModeService.obligation_dashboard(user_id)
        mode = EngagementModeService.current_mode(user_id)
        overdue = int(dashboard.get('overdue_count') or 0)
        remaining = int(dashboard.get('total_remaining') or 0)
        restricted = bool(
            EngagementModeService.overdue_blocks_standard()
            and mode != PRO_MODE
            and overdue > 0
            and remaining > 0
        )
        return {
            'restricted': restricted,
            'mode': mode or 'not_selected',
            'overdue_count': overdue,
            'remaining': remaining,
            'open_count': int(dashboard.get('open_count') or 0),
            'dashboard': dashboard,
        }

    @staticmethod
    def can_launch_engagement(user_id: int) -> tuple[bool, str, dict[str, Any]]:
        state = EngagementModeService.soft_restriction(user_id)
        if state['restricted']:
            return False, 'engagement_overdue_launch_blocked', state
        return True, 'engagement_launch_allowed', state

    @staticmethod
    def reminder_candidates(*, limit: int = 50) -> list[dict[str, Any]]:
        if not EngagementModeService.reminders_enabled():
            return []
        before = (utcnow() + timedelta(hours=EngagementModeService.reminder_before_hours())).isoformat(timespec='seconds')
        rows = db.fetch_all(
            """
            SELECT o.*, u.username, u.first_name, u.language_code
            FROM engagement_obligations o
            LEFT JOIN users u ON u.user_id = o.user_id
            WHERE o.status = 'open'
              AND o.due_at IS NOT NULL
              AND o.due_at <= ?
              AND (o.reminder_sent_at IS NULL OR o.warning_sent_at IS NULL OR o.admin_warning_sent_at IS NULL)
            ORDER BY o.due_at ASC, o.id ASC
            LIMIT ?
            """,
            (before, int(limit)),
        )
        result: list[dict[str, Any]] = []
        for row in rows:
            progress = EngagementModeService.obligation_progress(row)
            if int(progress['remaining']) <= 0:
                continue
            progress['reminder_sent_at'] = str(row['reminder_sent_at'] or '') if 'reminder_sent_at' in row.keys() else ''
            progress['warning_sent_at'] = str(row['warning_sent_at'] or '') if 'warning_sent_at' in row.keys() else ''
            progress['admin_warning_sent_at'] = str(row['admin_warning_sent_at'] or '') if 'admin_warning_sent_at' in row.keys() else ''
            progress['username'] = str(row['username'] or '')
            progress['first_name'] = str(row['first_name'] or '')
            result.append(progress)
        return result

    @staticmethod
    def _mark_obligation_column(obligation_id: int, column: str) -> None:
        if column not in {'reminder_sent_at', 'warning_sent_at', 'admin_warning_sent_at'}:
            return
        db.execute(
            f"UPDATE engagement_obligations SET {column} = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (int(obligation_id),),
        )

    @staticmethod
    def run_due_reminders(bot, *, admin_ids: list[int] | None = None, support_username: str = '') -> dict[str, int]:
        """Send one-shot soft reminders for Standard 0/10 obligations.

        This is intentionally soft: no money changes, no auto-bans, no campaign deletion.
        It only nudges users and alerts admins once per obligation.
        """
        sent_user = 0
        sent_admin = 0
        skipped = 0
        if not EngagementModeService.reminders_enabled():
            return {'user': 0, 'admin': 0, 'skipped': 0}
        try:
            from app.services.users import UserService
        except Exception:
            UserService = None
        for item in EngagementModeService.reminder_candidates(limit=60):
            user_id = int(item['user_id'])
            state = str(item['state'])
            try:
                if state == 'due_soon' and not item.get('reminder_sent_at'):
                    text = (UserService.t(user_id, 'engagement_reminder_due_soon_message', remaining=int(item['remaining']), required=int(item['required']), due=str(item['due_at']).replace('T', ' ')[:16], support=support_username or '—') if UserService else f"Standard 0/10: осталось {item['remaining']} действий до {item['due_at']}")
                    bot.send_message(user_id, text, parse_mode='HTML')
                    EngagementModeService._mark_obligation_column(int(item['id']), 'reminder_sent_at')
                    sent_user += 1
                elif state == 'overdue' and not item.get('warning_sent_at'):
                    text = (UserService.t(user_id, 'engagement_reminder_overdue_message', remaining=int(item['remaining']), required=int(item['required']), support=support_username or '—') if UserService else f"Standard 0/10: просрочка, осталось {item['remaining']} действий")
                    bot.send_message(user_id, text, parse_mode='HTML')
                    EngagementModeService._mark_obligation_column(int(item['id']), 'warning_sent_at')
                    sent_user += 1
            except Exception:
                skipped += 1
            if state == 'overdue' and EngagementModeService.admin_warnings_enabled() and not item.get('admin_warning_sent_at'):
                for admin_id in list(admin_ids or [])[:10]:
                    try:
                        if not admin_id:
                            continue
                        name = item.get('username') or item.get('first_name') or str(user_id)
                        text = (UserService.t(int(admin_id), 'engagement_admin_overdue_message', user_id=user_id, name=str(name)[:32], remaining=int(item['remaining']), required=int(item['required']), campaign=int(item.get('campaign_id') or 0)) if UserService else f"Standard overdue: {user_id}, remaining {item['remaining']}")
                        bot.send_message(int(admin_id), text, parse_mode='HTML')
                        sent_admin += 1
                    except Exception:
                        skipped += 1
                EngagementModeService._mark_obligation_column(int(item['id']), 'admin_warning_sent_at')
        return {'user': sent_user, 'admin': sent_admin, 'skipped': skipped}

    @staticmethod
    def soft_enforcement_summary() -> dict[str, Any]:
        try:
            overdue = 0
            due_soon = 0
            blocked_users: set[int] = set()
            reminder_pending = 0
            warning_pending = 0
            for row in db.fetch_all("SELECT * FROM engagement_obligations WHERE status = 'open' LIMIT 1000"):
                progress = EngagementModeService.obligation_progress(row)
                if progress['state'] == 'overdue':
                    overdue += 1
                    blocked_users.add(int(progress['user_id']))
                    if not str(row['warning_sent_at'] or ''):
                        warning_pending += 1
                elif progress['state'] == 'due_soon':
                    due_soon += 1
                    if not str(row['reminder_sent_at'] or ''):
                        reminder_pending += 1
            ready = EngagementModeService.overdue_blocks_standard() and EngagementModeService.reminders_enabled()
            status = 'ready' if ready and overdue == 0 else ('warning' if ready else 'blocker')
            return {
                'table_ready': True,
                'status': status,
                'overdue': overdue,
                'due_soon': due_soon,
                'blocked_users': len(blocked_users),
                'reminder_pending': reminder_pending,
                'warning_pending': warning_pending,
                'block_enabled': int(EngagementModeService.overdue_blocks_standard()),
                'reminders_enabled': int(EngagementModeService.reminders_enabled()),
                'admin_warnings_enabled': int(EngagementModeService.admin_warnings_enabled()),
            }
        except Exception:
            return {
                'table_ready': False,
                'status': 'blocker',
                'overdue': 0,
                'due_soon': 0,
                'blocked_users': 0,
                'reminder_pending': 0,
                'warning_pending': 0,
                'block_enabled': int(EngagementModeService.overdue_blocks_standard()),
                'reminders_enabled': int(EngagementModeService.reminders_enabled()),
                'admin_warnings_enabled': int(EngagementModeService.admin_warnings_enabled()),
            }

    @staticmethod
    def mode_summary(user_id: int) -> dict[str, Any]:
        row = EngagementModeService.get_membership(user_id)
        mode = EngagementModeService.current_mode(user_id)
        obligations = EngagementModeService.open_obligations(user_id)
        outgoing_30d = EngagementModeService.approved_outgoing_actions(
            user_id,
            since=(utcnow() - timedelta(days=30)).isoformat(timespec='seconds'),
        )
        restriction = EngagementModeService.soft_restriction(user_id)
        return {
            'mode': mode or 'not_selected',
            'is_selected': bool(row),
            'is_pro': mode == PRO_MODE,
            'pro_expires_at': str(row['pro_expires_at'] or '') if row else '',
            'required_actions': EngagementModeService.required_actions(),
            'pro_price_stars': EngagementModeService.pro_price_stars(),
            'pro_price_credits': EngagementModeService.pro_price_credits(),
            'open_obligations': len(obligations),
            'open_required_total': sum(int(item['required_actions'] or 0) for item in obligations),
            'open_remaining_total': EngagementModeService.obligation_dashboard(user_id)['total_remaining'],
            'is_restricted': bool(restriction['restricted']),
            'overdue_count': int(restriction['overdue_count']),
            'outgoing_30d': outgoing_30d,
        }

    @staticmethod
    def summary() -> dict[str, Any]:
        try:
            members = db.fetch_one('SELECT COUNT(*) AS cnt FROM engagement_memberships')
            standard = db.fetch_one("SELECT COUNT(*) AS cnt FROM engagement_memberships WHERE mode = 'standard'")
            pro = db.fetch_one("SELECT COUNT(*) AS cnt FROM engagement_memberships WHERE mode = 'pro' AND status = 'active'")
            open_obl = db.fetch_one("SELECT COUNT(*) AS cnt FROM engagement_obligations WHERE status = 'open'")
            soft = EngagementModeService.soft_enforcement_summary()
            return {
                'table_ready': True,
                'members': int(members['cnt'] or 0) if members else 0,
                'standard': int(standard['cnt'] or 0) if standard else 0,
                'pro': int(pro['cnt'] or 0) if pro else 0,
                'open_obligations': int(open_obl['cnt'] or 0) if open_obl else 0,
                'overdue_obligations': int(soft.get('overdue') or 0),
                'soft_blocked_users': int(soft.get('blocked_users') or 0),
                'reminders_enabled': int(soft.get('reminders_enabled') or 0),
                'required_actions': EngagementModeService.required_actions(),
                'pro_price_stars': EngagementModeService.pro_price_stars(),
                'pro_price_credits': EngagementModeService.pro_price_credits(),
            }
        except Exception:
            return {
                'table_ready': False,
                'members': 0,
                'standard': 0,
                'pro': 0,
                'open_obligations': 0,
                'required_actions': EngagementModeService.required_actions(),
                'pro_price_stars': EngagementModeService.pro_price_stars(),
                'pro_price_credits': EngagementModeService.pro_price_credits(),
            }
