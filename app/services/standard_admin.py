from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from app import db
from app.config import settings
from app.services.engagement_modes import EngagementModeService


class StandardAdminService:
    @staticmethod
    def _log(admin_user_id: int, action: str, *, target_user_id: int | None = None, obligation_id: int | None = None, details: str = '') -> None:
        db.execute(
            '''
            INSERT INTO engagement_admin_decisions (admin_user_id, target_user_id, obligation_id, action, details)
            VALUES (?, ?, ?, ?, ?)
            ''',
            (int(admin_user_id), target_user_id, obligation_id, str(action)[:64], str(details or '')[:1000]),
        )

    @staticmethod
    def get_obligation(obligation_id: int):
        return db.fetch_one('SELECT * FROM engagement_obligations WHERE id = ?', (int(obligation_id),))

    @staticmethod
    def extend_obligation(admin_user_id: int, obligation_id: int, *, hours: int = 24) -> tuple[bool, str]:
        row = StandardAdminService.get_obligation(obligation_id)
        if not row or str(row['status']) != 'open':
            return False, 'standard_admin_obligation_not_found'
        base = EngagementModeService._dt(str(row['due_at'] or '')) or datetime.utcnow()
        if base < datetime.utcnow():
            base = datetime.utcnow()
        new_due = base + timedelta(hours=max(1, int(hours)))
        db.execute(
            '''
            UPDATE engagement_obligations
            SET due_at = ?, extended_at = CURRENT_TIMESTAMP, extended_by_user_id = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            ''',
            (new_due.isoformat(timespec='seconds'), int(admin_user_id), int(obligation_id)),
        )
        StandardAdminService._log(admin_user_id, 'extend_obligation', target_user_id=int(row['user_id']), obligation_id=int(obligation_id), details=f'+{hours}h')
        return True, 'standard_admin_extended'

    @staticmethod
    def forgive_obligation(admin_user_id: int, obligation_id: int, *, reason: str = 'manual_forgive') -> tuple[bool, str]:
        row = StandardAdminService.get_obligation(obligation_id)
        if not row or str(row['status']) not in {'open', 'overdue'}:
            return False, 'standard_admin_obligation_not_found'
        db.execute(
            '''
            UPDATE engagement_obligations
            SET status = 'forgiven', forgiven_at = CURRENT_TIMESTAMP, forgiven_by_user_id = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            ''',
            (int(admin_user_id), int(obligation_id)),
        )
        StandardAdminService._log(admin_user_id, 'forgive_obligation', target_user_id=int(row['user_id']), obligation_id=int(obligation_id), details=reason)
        return True, 'standard_admin_forgiven'

    @staticmethod
    def warn_obligation(bot, admin_user_id: int, obligation_id: int, *, support_username: str = '') -> tuple[bool, str]:
        row = StandardAdminService.get_obligation(obligation_id)
        if not row or str(row['status']) != 'open':
            return False, 'standard_admin_obligation_not_found'
        progress = EngagementModeService.obligation_progress(row)
        text = (
            '<b>⚠️ Напоминание Boostora</b>\n\n'
            f'У тебя открыт Standard 0/10. Осталось выполнить: <b>{int(progress["remaining"])}</b>.\n'
            'Пока долг просрочен, новые Standard-запуски могут быть ограничены.\n'
            f'Поддержка: {support_username or settings.support_username}'
        )
        try:
            bot.send_message(int(row['user_id']), text, parse_mode='HTML')
        except Exception:
            return False, 'standard_admin_warning_failed'
        db.execute('UPDATE engagement_obligations SET last_manual_warning_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP WHERE id = ?', (int(obligation_id),))
        StandardAdminService._log(admin_user_id, 'manual_warning', target_user_id=int(row['user_id']), obligation_id=int(obligation_id), details='sent')
        return True, 'standard_admin_warning_sent'

    @staticmethod
    def grant_manual_pro(admin_user_id: int, target_user_id: int, *, days: int = 30) -> tuple[bool, str]:
        EngagementModeService.activate_pro(int(target_user_id), days=max(1, int(days)), source=f'manual_admin:{int(admin_user_id)}')
        StandardAdminService._log(admin_user_id, 'manual_pro', target_user_id=int(target_user_id), details=f'{days}d')
        return True, 'standard_admin_manual_pro_granted'

    @staticmethod
    def recent_decisions(limit: int = 10) -> list[Any]:
        return db.fetch_all(
            '''
            SELECT d.*, u.username, u.first_name
            FROM engagement_admin_decisions d
            LEFT JOIN users u ON u.user_id = d.target_user_id
            ORDER BY d.created_at DESC, d.id DESC
            LIMIT ?
            ''',
            (max(1, int(limit)),),
        )

    @staticmethod
    def summary() -> dict[str, Any]:
        try:
            decisions = db.fetch_one('SELECT COUNT(*) AS cnt FROM engagement_admin_decisions')
            forgiven = db.fetch_one("SELECT COUNT(*) AS cnt FROM engagement_obligations WHERE status = 'forgiven'")
            extended = db.fetch_one('SELECT COUNT(*) AS cnt FROM engagement_obligations WHERE extended_at IS NOT NULL')
            warned = db.fetch_one('SELECT COUNT(*) AS cnt FROM engagement_obligations WHERE last_manual_warning_at IS NOT NULL')
            return {
                'status': 'ready',
                'decisions': int(decisions['cnt'] or 0) if decisions else 0,
                'forgiven': int(forgiven['cnt'] or 0) if forgiven else 0,
                'extended': int(extended['cnt'] or 0) if extended else 0,
                'warned': int(warned['cnt'] or 0) if warned else 0,
            }
        except Exception:
            return {'status': 'blocker', 'decisions': 0, 'forgiven': 0, 'extended': 0, 'warned': 0}
