from __future__ import annotations

from datetime import datetime, timedelta

from app.time_utils import utcnow
from app import db
from app.services.trust import TrustService


RISK_THRESHOLD_MANUAL_REVIEW = 40
FAST_SUBMISSION_SECONDS = 45
BURST_SUBMISSIONS_WINDOW_MINUTES = 15
BURST_SUBMISSIONS_COUNT = 4
RECENT_REJECTION_COUNT = 3


class RiskService:
    @staticmethod
    def add_event(
        user_id: int,
        event_type: str,
        severity: str,
        score_delta: int,
        *,
        submission_id: int | None = None,
        details: str | None = None,
    ) -> int:
        event_id = db.execute(
            '''
            INSERT INTO risk_events (user_id, submission_id, event_type, severity, score_delta, details)
            VALUES (?, ?, ?, ?, ?, ?)
            ''',
            (user_id, submission_id, event_type, severity, score_delta, details),
        )
        db.execute(
            '''
            UPDATE users
            SET risk_score = risk_score + ?, updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ?
            ''',
            (score_delta, user_id),
        )
        return event_id

    @staticmethod
    def get_events(user_id: int):
        return db.fetch_all(
            'SELECT * FROM risk_events WHERE user_id = ? ORDER BY created_at DESC, id DESC',
            (user_id,),
        )

    @staticmethod
    def assess_submission(user_id: int, submission_id: int, proof_text: str) -> dict[str, object]:
        submission = db.fetch_one('SELECT * FROM task_submissions WHERE id = ?', (submission_id,))
        user = db.fetch_one('SELECT * FROM users WHERE user_id = ?', (user_id,))
        trust = TrustService.summary(user_id, language='ru')
        reasons: list[dict[str, object]] = []
        manual_threshold = 15

        if int(trust['score']) >= 85:
            manual_threshold += 5
        elif int(trust['score']) < 40:
            manual_threshold -= 3
            reasons.append({
                'event_type': 'low_trust_profile',
                'severity': 'medium',
                'score_delta': 4,
                'details': f"Trust score is {int(trust['score'])}",
            })

        if user and int(user['risk_score']) >= RISK_THRESHOLD_MANUAL_REVIEW:
            reasons.append({
                'event_type': 'high_risk_user',
                'severity': 'high',
                'score_delta': 15,
                'details': f"User risk score is {int(user['risk_score'])}",
            })

        if submission and submission['taken_at']:
            try:
                taken_at = datetime.fromisoformat(str(submission['taken_at']))
                delta_seconds = (utcnow() - taken_at).total_seconds()
                if delta_seconds <= FAST_SUBMISSION_SECONDS:
                    reasons.append({
                        'event_type': 'fast_submission',
                        'severity': 'high',
                        'score_delta': 5,
                        'details': f'Submission sent in {int(delta_seconds)} seconds',
                    })
            except ValueError:
                pass

        if proof_text.strip():
            duplicate = db.fetch_one(
                '''
                SELECT id FROM task_submissions
                WHERE performer_user_id = ?
                  AND id != ?
                  AND proof_text = ?
                  AND status IN ('approved', 'manual_review', 'rejected')
                LIMIT 1
                ''',
                (user_id, submission_id, proof_text.strip()),
            )
            if duplicate:
                reasons.append({
                    'event_type': 'duplicate_proof',
                    'severity': 'high',
                    'score_delta': 20,
                    'details': f'Duplicate proof detected, previous submission #{int(duplicate["id"])}',
                })

        recent_rejections = db.fetch_one(
            '''
            SELECT COUNT(*) AS cnt
            FROM task_submissions
            WHERE performer_user_id = ?
              AND status = 'rejected'
              AND updated_at >= datetime('now', '-30 days')
            ''',
            (user_id,),
        )
        if recent_rejections and int(recent_rejections['cnt']) >= RECENT_REJECTION_COUNT:
            reasons.append({
                'event_type': 'frequent_rejections',
                'severity': 'medium',
                'score_delta': 10,
                'details': f"Rejected submissions in 30 days: {int(recent_rejections['cnt'])}",
            })

        burst_since = (utcnow() - timedelta(minutes=BURST_SUBMISSIONS_WINDOW_MINUTES)).isoformat(timespec='seconds')
        recent_submissions = db.fetch_one(
            '''
            SELECT COUNT(*) AS cnt
            FROM task_submissions
            WHERE performer_user_id = ?
              AND submitted_at IS NOT NULL
              AND submitted_at >= ?
            ''',
            (user_id, burst_since),
        )
        if recent_submissions and int(recent_submissions['cnt']) >= BURST_SUBMISSIONS_COUNT:
            reasons.append({
                'event_type': 'submission_burst',
                'severity': 'medium',
                'score_delta': 10,
                'details': f"Submitted {int(recent_submissions['cnt'])} tasks in {BURST_SUBMISSIONS_WINDOW_MINUTES} minutes",
            })

        total_score = sum(int(item['score_delta']) for item in reasons)
        return {
            'manual_review': total_score >= manual_threshold,
            'score_delta': total_score,
            'reasons': reasons,
            'manual_threshold': manual_threshold,
            'trust_score': int(trust['score']),
        }

    @staticmethod
    def record_assessment(user_id: int, submission_id: int, assessment: dict[str, object]) -> int:
        reasons = assessment.get('reasons') or []
        count = 0
        for item in reasons:
            RiskService.add_event(
                user_id=user_id,
                submission_id=submission_id,
                event_type=str(item['event_type']),
                severity=str(item['severity']),
                score_delta=int(item['score_delta']),
                details=str(item['details']),
            )
            count += 1
        return count
