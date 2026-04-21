import sqlite3
from datetime import datetime
from typing import Any

from app import db
from app.services.admin_logs import AdminLogService
from app.services.referrals import ReferralService
from app.services.users import UserService


STATUS_MANUAL_REVIEW = 'manual_review'
STATUS_APPROVED = 'approved'
STATUS_REJECTED = 'rejected'
STATUS_BLOCKED = 'blocked'
STATUS_ACTIVE = 'active'


class AdminService:
    @staticmethod
    def get_dashboard_stats() -> dict[str, int]:
        row = db.fetch_one(
            '''
            SELECT
                (SELECT COUNT(*) FROM task_submissions WHERE status = 'manual_review') AS queue_count,
                (SELECT COUNT(*) FROM users WHERE status = 'blocked') AS blocked_users,
                (SELECT COUNT(*) FROM users WHERE risk_score >= 40) AS high_risk_users,
                (SELECT COUNT(*) FROM task_submissions WHERE status = 'rejected') AS rejected_total
            '''
        )
        if not row:
            return {'queue_count': 0, 'blocked_users': 0, 'high_risk_users': 0, 'rejected_total': 0}
        return {
            'queue_count': int(row['queue_count']),
            'blocked_users': int(row['blocked_users']),
            'high_risk_users': int(row['high_risk_users']),
            'rejected_total': int(row['rejected_total']),
        }

    @staticmethod
    def list_review_queue(limit: int = 20):
        return db.fetch_all(
            '''
            SELECT
                s.*,
                c.title AS campaign_title,
                c.task_type AS campaign_task_type,
                c.target_url AS campaign_target_url,
                u.username,
                u.first_name,
                u.last_name,
                u.status AS user_status,
                u.risk_score AS user_risk_score
            FROM task_submissions s
            JOIN campaigns c ON c.id = s.campaign_id
            JOIN users u ON u.user_id = s.performer_user_id
            WHERE s.status = 'manual_review'
            ORDER BY s.risk_score DESC, s.submitted_at ASC, s.id ASC
            LIMIT ?
            ''',
            (limit,),
        )

    @staticmethod
    def get_submission_card(submission_id: int):
        submission = db.fetch_one(
            '''
            SELECT
                s.*,
                c.owner_user_id,
                c.title AS campaign_title,
                c.task_type AS campaign_task_type,
                c.target_url AS campaign_target_url,
                c.status AS campaign_status,
                u.username,
                u.first_name,
                u.last_name,
                u.status AS user_status,
                u.risk_score AS user_risk_score
            FROM task_submissions s
            JOIN campaigns c ON c.id = s.campaign_id
            JOIN users u ON u.user_id = s.performer_user_id
            WHERE s.id = ?
            ''',
            (submission_id,),
        )
        if not submission:
            return None
        stats = db.fetch_one(
            '''
            SELECT
                SUM(CASE WHEN status = 'approved' THEN 1 ELSE 0 END) AS approved_count,
                SUM(CASE WHEN status = 'rejected' THEN 1 ELSE 0 END) AS rejected_count,
                SUM(CASE WHEN status = 'manual_review' THEN 1 ELSE 0 END) AS review_count
            FROM task_submissions
            WHERE performer_user_id = ?
            ''',
            (int(submission['performer_user_id']),),
        )
        recent_events = db.fetch_all(
            '''
            SELECT * FROM risk_events
            WHERE user_id = ?
            ORDER BY created_at DESC, id DESC
            LIMIT 5
            ''',
            (int(submission['performer_user_id']),),
        )
        return {
            'submission': submission,
            'stats': {
                'approved_count': int(stats['approved_count'] or 0) if stats else 0,
                'rejected_count': int(stats['rejected_count'] or 0) if stats else 0,
                'review_count': int(stats['review_count'] or 0) if stats else 0,
            },
            'events': recent_events,
        }

    @staticmethod
    def review_submission(admin_user_id: int, submission_id: int, *, approve: bool, reject_reason: str | None = None) -> tuple[bool, str, int | None]:
        def _run(connection: sqlite3.Connection) -> tuple[bool, str, int | None, int]:
            submission = connection.execute(
                '''
                SELECT s.*, c.owner_user_id, c.id AS campaign_id, c.reward_amount AS campaign_reward_amount
                FROM task_submissions s
                JOIN campaigns c ON c.id = s.campaign_id
                WHERE s.id = ?
                ''',
                (submission_id,),
            ).fetchone()
            if not submission:
                return False, 'admin_submission_not_found', None, 0
            if str(submission['status']) != STATUS_MANUAL_REVIEW:
                return False, 'admin_submission_already_reviewed', int(submission['performer_user_id']), 0

            now = datetime.utcnow().isoformat(timespec='seconds')
            reward_amount = int(submission['reward_amount'])
            performer_user_id = int(submission['performer_user_id'])
            campaign_id = int(submission['campaign_id'])

            if approve:
                release_at = AdminService._build_release_at_for_user(performer_user_id)
                connection.execute(
                    '''
                    UPDATE task_submissions
                    SET status = 'approved',
                        reviewed_at = ?,
                        reviewer_user_id = ?,
                        reject_reason = NULL,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    ''',
                    (now, admin_user_id, submission_id),
                )
                hold_id = int(
                    connection.execute(
                        '''
                        INSERT INTO holds (user_id, submission_id, amount, release_at, status)
                        VALUES (?, ?, ?, ?, 'active')
                        ''',
                        (performer_user_id, submission_id, reward_amount, release_at),
                    ).lastrowid
                )
                connection.execute(
                    '''
                    UPDATE wallets
                    SET hold_balance = hold_balance + ?,
                        lifetime_earned = lifetime_earned + ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE user_id = ?
                    ''',
                    (reward_amount, reward_amount, performer_user_id),
                )
                connection.execute(
                    '''
                    UPDATE campaigns
                    SET completed_quantity = completed_quantity + 1,
                        budget_reserved = CASE WHEN budget_reserved >= ? THEN budget_reserved - ? ELSE 0 END,
                        budget_spent = budget_spent + ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    ''',
                    (reward_amount, reward_amount, reward_amount, campaign_id),
                )
                connection.execute(
                    '''
                    INSERT INTO transactions (
                        user_id, wallet_user_id, amount, currency_code, direction, entry_type,
                        status, related_campaign_id, related_submission_id, related_hold_id, note
                    ) VALUES (?, ?, ?, 'XTR', 'credit', 'task_reward_hold', 'hold', ?, ?, ?, ?)
                    ''',
                    (
                        performer_user_id,
                        performer_user_id,
                        reward_amount,
                        campaign_id,
                        submission_id,
                        hold_id,
                        'Reward placed into hold after admin approval',
                    ),
                )
                return True, 'admin_submission_approved', performer_user_id, reward_amount

            reason = (reject_reason or '').strip()
            if not reason:
                return False, 'admin_reject_reason_empty', performer_user_id, 0
            connection.execute(
                '''
                UPDATE task_submissions
                SET status = 'rejected',
                    reviewed_at = ?,
                    reviewer_user_id = ?,
                    reject_reason = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                ''',
                (now, admin_user_id, reason[:500], submission_id),
            )
            connection.execute(
                '''
                UPDATE campaigns
                SET rejected_quantity = rejected_quantity + 1,
                    budget_reserved = CASE WHEN budget_reserved >= ? THEN budget_reserved - ? ELSE 0 END,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                ''',
                (reward_amount, reward_amount, campaign_id),
            )
            return True, 'admin_submission_rejected', performer_user_id, 0

        ok, result_key, performer_user_id, reward_amount = db.run_in_transaction(_run)
        if not ok:
            return ok, result_key, performer_user_id

        if approve and performer_user_id is not None and reward_amount > 0:
            ReferralService.reward_for_submission(performer_user_id, reward_amount)
        if performer_user_id is not None:
            action = 'approve_submission' if approve else 'reject_submission'
            details = f'submission_id={submission_id}'
            if reject_reason:
                details += f'; reason={reject_reason[:200]}'
            AdminLogService.log(admin_user_id, action, target_user_id=performer_user_id, details=details)
        return True, result_key, performer_user_id

    @staticmethod
    def set_user_blocked(admin_user_id: int, target_user_id: int, blocked: bool) -> tuple[bool, str]:
        target = UserService.get_user(target_user_id)
        if not target:
            return False, 'admin_user_not_found'
        if UserService.is_admin(target_user_id) and blocked:
            return False, 'admin_cannot_block_admin'
        status = STATUS_BLOCKED if blocked else STATUS_ACTIVE
        db.execute(
            '''
            UPDATE users
            SET status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ?
            ''',
            (status, target_user_id),
        )
        AdminLogService.log(
            admin_user_id,
            'block_user' if blocked else 'unblock_user',
            target_user_id=target_user_id,
            details=f'status={status}',
        )
        return True, 'admin_user_blocked' if blocked else 'admin_user_unblocked'

    @staticmethod
    def adjust_risk_score(admin_user_id: int, target_user_id: int, delta: int, *, reason: str | None = None) -> tuple[bool, str, int | None]:
        target = UserService.get_user(target_user_id)
        if not target:
            return False, 'admin_user_not_found', None
        db.execute(
            '''
            UPDATE users
            SET risk_score = CASE
                    WHEN risk_score + ? < 0 THEN 0
                    ELSE risk_score + ?
                END,
                updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ?
            ''',
            (delta, delta, target_user_id),
        )
        db.execute(
            '''
            INSERT INTO risk_events (user_id, event_type, severity, score_delta, details)
            VALUES (?, 'admin_adjustment', 'manual', ?, ?)
            ''',
            (target_user_id, delta, reason or f'Adjusted by admin {admin_user_id}'),
        )
        AdminLogService.log(
            admin_user_id,
            'adjust_risk_score',
            target_user_id=target_user_id,
            details=f'delta={delta}; reason={(reason or "manual")[:200]}',
        )
        updated = UserService.get_user(target_user_id)
        return True, 'admin_risk_adjusted', int(updated['risk_score']) if updated else None

    @staticmethod
    def adjust_available_balance(admin_user_id: int, target_user_id: int, delta: int, *, reason: str | None = None) -> tuple[bool, str, int | None]:
        def _run(connection: sqlite3.Connection) -> tuple[bool, str, int | None]:
            target = connection.execute('SELECT * FROM users WHERE user_id = ?', (target_user_id,)).fetchone()
            if not target:
                return False, 'admin_user_not_found', None
            connection.execute(
                '''
                INSERT INTO wallets (user_id)
                VALUES (?)
                ON CONFLICT(user_id) DO NOTHING
                ''',
                (target_user_id,),
            )
            wallet = connection.execute('SELECT * FROM wallets WHERE user_id = ?', (target_user_id,)).fetchone()
            available = int(wallet['available_balance']) if wallet else 0
            if available + delta < 0:
                return False, 'admin_balance_adjust_invalid', available
            connection.execute(
                '''
                UPDATE wallets
                SET available_balance = available_balance + ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ?
                ''',
                (delta, target_user_id),
            )
            connection.execute(
                '''
                INSERT INTO transactions (
                    user_id, wallet_user_id, amount, currency_code, direction, entry_type, status, note
                ) VALUES (?, ?, ?, 'XTR', ?, 'admin_balance_adjustment', 'completed', ?)
                ''',
                (
                    target_user_id,
                    target_user_id,
                    abs(delta),
                    'credit' if delta >= 0 else 'debit',
                    reason or f'Adjusted by admin {admin_user_id}',
                ),
            )
            updated = connection.execute('SELECT * FROM wallets WHERE user_id = ?', (target_user_id,)).fetchone()
            return True, 'admin_balance_adjusted', int(updated['available_balance']) if updated else 0

        ok, result_key, balance = db.run_in_transaction(_run)
        if ok:
            AdminLogService.log(
                admin_user_id,
                'adjust_available_balance',
                target_user_id=target_user_id,
                details=f'delta={delta}; reason={(reason or "manual")[:200]}',
            )
        return ok, result_key, balance

    @staticmethod
    def _build_release_at_for_user(user_id: int) -> str:
        from app.services.performer import PerformerService

        hold_minutes = PerformerService.get_hold_minutes_for_user(user_id)
        release_at = datetime.utcnow().timestamp() + hold_minutes * 60
        return datetime.utcfromtimestamp(release_at).isoformat(timespec='seconds')
