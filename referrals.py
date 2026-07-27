import sqlite3
from datetime import datetime
from urllib.parse import urlparse

from app import db
from app.config import settings
from app.services.activity import ActivityService, AUTO_VERIFIABLE_TASK_TYPES
from app.services.referrals import ReferralService
from app.services.risk import RiskService
from app.services.trust import TrustService
from app.services.vip import VipService


STATUS_TAKEN = 'taken'
STATUS_APPROVED = 'approved'
STATUS_MANUAL_REVIEW = 'manual_review'
ACTIVE_SUBMISSION_STATUSES = (STATUS_TAKEN, 'submitted', STATUS_MANUAL_REVIEW)
BASE_ACTIVE_TASK_LIMIT = 3
_ALLOWED_MEMBER_STATUSES = {'creator', 'administrator', 'member'}


def normalize_target_url(raw: str) -> str:
    value = (raw or '').strip()
    if not value:
        return 'https://t.me'
    if value.startswith('@'):
        return f"https://t.me/{value[1:]}"
    if value.startswith('t.me/'):
        return f"https://{value}"
    return value



def _extract_chat_ref(target_url: str) -> str | None:
    value = (target_url or '').strip()
    if not value:
        return None
    if value.startswith('@'):
        return value
    if value.lstrip('-').isdigit():
        return value
    if value.startswith('t.me/'):
        value = f'https://{value}'
    if value.startswith('https://t.me/') or value.startswith('http://t.me/'):
        parsed = urlparse(value)
        path = parsed.path.strip('/').split('/')
        if not path:
            return None
        head = path[0].strip()
        if not head or head.startswith('+'):
            return None
        return f'@{head}'
    return None



def _is_member_status(member) -> bool:
    status = getattr(member, 'status', '') or ''
    if status in _ALLOWED_MEMBER_STATUSES:
        return True
    if status == 'restricted' and bool(getattr(member, 'is_member', False)):
        return True
    return False


class PerformerService:
    @staticmethod
    def release_due_holds(user_id: int | None = None) -> int:
        def _run(connection: sqlite3.Connection) -> int:
            now = datetime.utcnow().isoformat(timespec='seconds')
            params: list[object] = [now]
            query = 'SELECT * FROM holds WHERE status = ? AND release_at <= ?'
            if user_id is not None:
                query += ' AND user_id = ?'
                params.append(user_id)
            rows = connection.execute(query, ('active', *params)).fetchall()
            released = 0
            for hold in rows:
                amount = int(hold['amount'])
                target_user_id = int(hold['user_id'])
                hold_id = int(hold['id'])
                currency_code = str(hold['currency_code'] or 'XTR')
                connection.execute(
                    '''
                    UPDATE holds
                    SET status = 'released', released_at = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ? AND status = 'active'
                    ''',
                    (now, hold_id),
                )
                if currency_code == 'BST':
                    connection.execute(
                        '''
                        UPDATE wallets
                        SET hold_balance = CASE WHEN hold_balance >= ? THEN hold_balance - ? ELSE 0 END,
                            internal_balance = internal_balance + ?,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE user_id = ?
                        ''',
                        (amount, amount, amount, target_user_id),
                    )
                    note = 'Hold released to sparks balance'
                else:
                    connection.execute(
                        '''
                        UPDATE wallets
                        SET hold_balance = CASE WHEN hold_balance >= ? THEN hold_balance - ? ELSE 0 END,
                            available_balance = available_balance + ?,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE user_id = ?
                        ''',
                        (amount, amount, amount, target_user_id),
                    )
                    note = 'Hold released to available balance'
                connection.execute(
                    '''
                    INSERT INTO transactions (
                        user_id, wallet_user_id, amount, currency_code, direction, entry_type,
                        status, related_submission_id, related_hold_id, note
                    ) VALUES (?, ?, ?, ?, 'credit', 'hold_release', 'completed', ?, ?, ?)
                    ''',
                    (
                        target_user_id,
                        target_user_id,
                        amount,
                        currency_code,
                        hold['submission_id'],
                        hold_id,
                        note,
                    ),
                )
                released += 1
            return released

        return db.run_in_transaction(_run)

    @staticmethod
    def get_active_task_limit(user_id: int) -> int:
        bonuses = VipService.get_active_bonuses(user_id)
        trust = TrustService.summary(user_id, language='ru')
        return BASE_ACTIVE_TASK_LIMIT + bonuses['active_task_limit_bonus'] + int(trust['task_bonus'])

    @staticmethod
    def get_hold_minutes_for_user(user_id: int) -> int:
        bonuses = VipService.get_active_bonuses(user_id)
        base_minutes = settings.default_hold_hours * 60
        reduction = min(max(bonuses['hold_speed_percent'], 0), 95)
        adjusted = round(base_minutes * (100 - reduction) / 100)
        return max(1, adjusted)

    @staticmethod
    def get_active_submission_count(user_id: int) -> int:
        row = db.fetch_one(
            '''
            SELECT COUNT(*) AS cnt
            FROM task_submissions
            WHERE performer_user_id = ? AND status IN (?, ?, ?)
            ''',
            (user_id, *ACTIVE_SUBMISSION_STATUSES),
        )
        return int(row['cnt']) if row else 0

    @staticmethod
    def list_available_tasks(user_id: int, limit: int = 10):
        return db.fetch_all(
            '''
            SELECT c.*
            FROM campaigns c
            WHERE c.status = 'active'
              AND c.is_funded = 1
              AND c.owner_user_id != ?
              AND c.total_quantity > c.completed_quantity
              AND NOT EXISTS (
                    SELECT 1 FROM task_submissions s
                    WHERE s.campaign_id = c.id AND s.performer_user_id = ?
              )
            ORDER BY c.updated_at DESC, c.id DESC
            LIMIT ?
            ''',
            (user_id, user_id, limit),
        )

    @staticmethod
    def get_campaign(campaign_id: int):
        return db.fetch_one('SELECT * FROM campaigns WHERE id = ?', (campaign_id,))

    @staticmethod
    def get_submission(submission_id: int):
        return db.fetch_one('SELECT * FROM task_submissions WHERE id = ?', (submission_id,))

    @staticmethod
    def get_submission_for_campaign(user_id: int, campaign_id: int):
        return db.fetch_one(
            '''
            SELECT * FROM task_submissions
            WHERE performer_user_id = ? AND campaign_id = ?
            ORDER BY id DESC LIMIT 1
            ''',
            (user_id, campaign_id),
        )

    @staticmethod
    def list_user_submissions(user_id: int, limit: int = 20):
        return db.fetch_all(
            '''
            SELECT s.*, c.title AS campaign_title, c.task_type AS campaign_task_type
            FROM task_submissions s
            JOIN campaigns c ON c.id = s.campaign_id
            WHERE s.performer_user_id = ?
            ORDER BY s.updated_at DESC, s.id DESC
            LIMIT ?
            ''',
            (user_id, limit),
        )

    @staticmethod
    def take_task(user_id: int, campaign_id: int) -> tuple[bool, str, int | None]:
        def _run(connection: sqlite3.Connection) -> tuple[bool, str, int | None]:
            campaign = connection.execute(
                'SELECT * FROM campaigns WHERE id = ?',
                (campaign_id,),
            ).fetchone()
            if not campaign:
                return False, 'task_not_found', None
            if str(campaign['status']) != 'active' or int(campaign['is_funded'] or 0) != 1:
                return False, 'task_not_available', None
            if int(campaign['owner_user_id']) == user_id:
                return False, 'task_not_available', None
            active_for_campaign = connection.execute(
                '''
                SELECT COUNT(*) AS cnt
                FROM task_submissions
                WHERE campaign_id = ? AND status IN ('taken', 'manual_review')
                ''',
                (campaign_id,),
            ).fetchone()
            if int(campaign['completed_quantity']) + int(active_for_campaign['cnt']) >= int(campaign['total_quantity']):
                return False, 'task_not_available', None

            existing = connection.execute(
                '''
                SELECT id FROM task_submissions
                WHERE performer_user_id = ? AND campaign_id = ?
                LIMIT 1
                ''',
                (user_id, campaign_id),
            ).fetchone()
            if existing:
                return False, 'task_repeat_blocked', int(existing['id'])

            active_count = connection.execute(
                '''
                SELECT COUNT(*) AS cnt
                FROM task_submissions
                WHERE performer_user_id = ? AND status IN (?, ?, ?)
                ''',
                (user_id, *ACTIVE_SUBMISSION_STATUSES),
            ).fetchone()
            if int(active_count['cnt']) >= PerformerService.get_active_task_limit(user_id):
                return False, 'task_limit_reached', None

            cursor = connection.execute(
                '''
                INSERT INTO task_submissions (
                    campaign_id,
                    performer_user_id,
                    status,
                    target_url,
                    reward_amount
                ) VALUES (?, ?, 'taken', ?, ?)
                ''',
                (
                    campaign_id,
                    user_id,
                    campaign['target_url'],
                    int(campaign['reward_amount']),
                ),
            )
            submission_id = int(cursor.lastrowid)
            connection.execute(
                '''
                UPDATE campaigns
                SET budget_reserved = budget_reserved + ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                ''',
                (int(campaign['unit_price'] or campaign['reward_amount']), campaign_id),
            )
            return True, 'task_taken', submission_id

        return db.run_in_transaction(_run)

    @staticmethod
    def _finalize_approval(user_id: int, submission_id: int, proof_text: str, risk_score_delta: int) -> tuple[bool, str, int | None, int]:
        def _run(connection: sqlite3.Connection) -> tuple[bool, str, int | None, int]:
            submission = connection.execute(
                'SELECT * FROM task_submissions WHERE id = ?',
                (submission_id,),
            ).fetchone()
            if not submission or int(submission['performer_user_id']) != user_id:
                return False, 'task_not_found', None, 0
            if str(submission['status']) != STATUS_TAKEN:
                return False, 'proof_already_sent', None, 0

            campaign = connection.execute(
                'SELECT * FROM campaigns WHERE id = ?',
                (int(submission['campaign_id']),),
            ).fetchone()
            if not campaign:
                return False, 'task_not_found', None, 0

            now = datetime.utcnow().isoformat(timespec='seconds')
            reward_amount = int(submission['reward_amount'])
            owner_unit_price = int(campaign['unit_price'] or campaign['reward_amount'])
            hold_minutes = PerformerService.get_hold_minutes_for_user(user_id)
            release_at = datetime.utcnow().timestamp() + hold_minutes * 60
            release_iso = datetime.utcfromtimestamp(release_at).isoformat(timespec='seconds')

            connection.execute(
                '''
                UPDATE task_submissions
                SET status = 'approved',
                    proof_text = ?,
                    submitted_at = ?,
                    reviewed_at = ?,
                    reviewer_user_id = NULL,
                    risk_score = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                ''',
                (proof_text, now, now, risk_score_delta, submission_id),
            )
            hold_cursor = connection.execute(
                '''
                INSERT INTO holds (user_id, submission_id, amount, currency_code, release_at, status)
                VALUES (?, ?, ?, 'BST', ?, 'active')
                ''',
                (user_id, submission_id, reward_amount, release_iso),
            )
            hold_id = int(hold_cursor.lastrowid)
            connection.execute(
                '''
                UPDATE wallets
                SET hold_balance = hold_balance + ?,
                    lifetime_earned = lifetime_earned + ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ?
                ''',
                (reward_amount, reward_amount, user_id),
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
                (owner_unit_price, owner_unit_price, owner_unit_price, int(campaign['id'])),
            )
            connection.execute(
                '''
                INSERT INTO transactions (
                    user_id, wallet_user_id, amount, currency_code, direction, entry_type,
                    status, related_campaign_id, related_submission_id, related_hold_id, note
                ) VALUES (?, ?, ?, 'BST', 'credit', 'task_reward_hold', 'hold', ?, ?, ?, ?)
                ''',
                (
                    user_id,
                    user_id,
                    reward_amount,
                    int(campaign['id']),
                    submission_id,
                    hold_id,
                    'Task reward placed into sparks hold',
                ),
            )
            return True, 'proof_accepted', hold_id, reward_amount

        return db.run_in_transaction(_run)

    @staticmethod
    def submit_proof(user_id: int, submission_id: int, proof_text: str) -> tuple[bool, str, int | None]:
        clean_proof = (proof_text or '').strip()
        if not clean_proof:
            return False, 'proof_empty', None

        assessment = RiskService.assess_submission(user_id, submission_id, clean_proof)
        manual_review = bool(assessment.get('manual_review'))
        risk_score_delta = int(assessment.get('score_delta') or 0)

        if manual_review:
            ok, result_key, result_id = PerformerService.send_to_manual_review(user_id, submission_id, clean_proof, risk_score_delta)
        else:
            ok, result_key, result_id, reward_amount = PerformerService._finalize_approval(user_id, submission_id, clean_proof, risk_score_delta)
            if ok and reward_amount > 0:
                ReferralService.reward_for_submission(user_id, reward_amount)
        if assessment.get('reasons'):
            RiskService.record_assessment(user_id, submission_id, assessment)
        return ok, result_key, result_id

    @staticmethod
    def send_to_manual_review(user_id: int, submission_id: int, note: str, risk_score_delta: int = 0) -> tuple[bool, str, int | None]:
        def _run(connection: sqlite3.Connection) -> tuple[bool, str, int | None]:
            submission = connection.execute('SELECT * FROM task_submissions WHERE id = ?', (submission_id,)).fetchone()
            if not submission or int(submission['performer_user_id']) != user_id:
                return False, 'task_not_found', None
            if str(submission['status']) != STATUS_TAKEN:
                return False, 'proof_already_sent', None
            now = datetime.utcnow().isoformat(timespec='seconds')
            connection.execute(
                '''
                UPDATE task_submissions
                SET status = 'manual_review',
                    proof_text = ?,
                    submitted_at = ?,
                    risk_score = ?,
                    reviewed_at = NULL,
                    reviewer_user_id = NULL,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                ''',
                (note, now, risk_score_delta, submission_id),
            )
            return True, 'proof_sent_manual_review', submission_id

        return db.run_in_transaction(_run)

    @staticmethod
    def _verify_membership(bot, user_id: int, target_url: str) -> tuple[str, str]:
        chat_ref = _extract_chat_ref(target_url)
        if not chat_ref:
            return 'unavailable', 'task_verify_unavailable'
        api_chat_ref = int(chat_ref) if chat_ref.lstrip('-').isdigit() else chat_ref
        try:
            member = bot.get_chat_member(api_chat_ref, user_id)
        except Exception:
            return 'unavailable', 'task_verify_unavailable'
        if _is_member_status(member):
            return 'verified', 'task_auto_verified'
        return 'failed', 'task_verification_failed'

    @staticmethod
    def submit_for_check(bot, user_id: int, submission_id: int) -> tuple[bool, str, int | None]:
        submission = PerformerService.get_submission(submission_id)
        if not submission or int(submission['performer_user_id']) != user_id:
            return False, 'task_not_found', None
        if str(submission['status']) != STATUS_TAKEN:
            return False, 'proof_already_sent', None
        campaign = PerformerService.get_campaign(int(submission['campaign_id']))
        if not campaign:
            return False, 'task_not_found', None

        task_type = str(campaign['task_type'])
        state, result_key = ActivityService.auto_verify_submission(bot, user_id, campaign, submission)
        if state == 'verified':
            ok, result_key, result_id = PerformerService.submit_proof(user_id, submission_id, f'auto_verified:{task_type}')
            return ok, result_key, result_id
        if state == 'failed':
            return False, result_key, None

        manual_note = f'manual_review_required:{task_type}'
        if task_type in AUTO_VERIFIABLE_TASK_TYPES:
            manual_note = f'auto_check_pending:{task_type}'
        return PerformerService.send_to_manual_review(user_id, submission_id, manual_note)
