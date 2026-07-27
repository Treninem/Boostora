from __future__ import annotations

from app import db


TRUST_LEVELS = [
    (0, 'newbie', 'Новичок', 'New'),
    (35, 'starter', 'Осторожный старт', 'Cautious start'),
    (55, 'reliable', 'Надёжный', 'Reliable'),
    (75, 'proven', 'Проверенный', 'Proven'),
    (90, 'elite', 'Эталон', 'Elite'),
]


class TrustService:
    @staticmethod
    def _counts(user_id: int) -> dict[str, int | bool]:
        row = db.fetch_one(
            '''
            SELECT
                COALESCE(SUM(CASE WHEN status = 'approved' THEN 1 ELSE 0 END), 0) AS approved_count,
                COALESCE(SUM(CASE WHEN status = 'rejected' THEN 1 ELSE 0 END), 0) AS rejected_count,
                COALESCE(SUM(CASE WHEN status = 'manual_review' THEN 1 ELSE 0 END), 0) AS manual_review_count,
                COALESCE(SUM(CASE WHEN status IN ('approved', 'rejected') THEN 1 ELSE 0 END), 0) AS reviewed_count
            FROM task_submissions
            WHERE performer_user_id = ?
            ''',
            (user_id,),
        )
        wallet = db.fetch_one('SELECT * FROM wallets WHERE user_id = ?', (user_id,))
        user = db.fetch_one('SELECT * FROM users WHERE user_id = ?', (user_id,))
        return {
            'approved_count': int(row['approved_count'] or 0) if row else 0,
            'rejected_count': int(row['rejected_count'] or 0) if row else 0,
            'manual_review_count': int(row['manual_review_count'] or 0) if row else 0,
            'reviewed_count': int(row['reviewed_count'] or 0) if row else 0,
            'risk_score': int(user['risk_score'] or 0) if user else 0,
            'has_paid_topup': bool(wallet and ('has_paid_topup' in wallet.keys()) and int(wallet['has_paid_topup'] or 0) == 1),
        }

    @staticmethod
    def _score_from_counts(*, approved_count: int, rejected_count: int, manual_review_count: int, reviewed_count: int, risk_score: int, has_paid_topup: bool) -> int:
        approval_rate = 100 if reviewed_count == 0 else round((approved_count / max(reviewed_count, 1)) * 100)
        score = 35
        score += min(28, approved_count * 2)
        score += min(8, manual_review_count)
        score -= min(28, rejected_count * 7)
        score -= min(30, max(risk_score, 0))
        if has_paid_topup:
            score += 7
        if approved_count >= 10 and approval_rate >= 90:
            score += 6
        if approved_count >= 25 and approval_rate >= 95:
            score += 6
        return max(0, min(100, score))

    @staticmethod
    def level_from_score(score: int, language: str = 'ru') -> tuple[str, str]:
        current = TRUST_LEVELS[0]
        for item in TRUST_LEVELS:
            if score >= item[0]:
                current = item
        return current[1], current[2] if language == 'ru' else current[3]

    @staticmethod
    def active_task_bonus(score: int, approved_count: int, risk_score: int) -> int:
        if score >= 90 and approved_count >= 20 and risk_score <= 10:
            return 2
        if score >= 75 and approved_count >= 8 and risk_score <= 20:
            return 1
        return 0

    @staticmethod
    def summary(user_id: int, language: str = 'ru') -> dict[str, int | str | bool]:
        counts = TrustService._counts(user_id)
        score = TrustService._score_from_counts(**counts)
        level_code, level_label = TrustService.level_from_score(score, language=language)
        reviewed_count = int(counts['reviewed_count'])
        approval_rate = 100 if reviewed_count == 0 else round((int(counts['approved_count']) / max(reviewed_count, 1)) * 100)
        task_bonus = TrustService.active_task_bonus(score, int(counts['approved_count']), int(counts['risk_score']))
        if score >= 85:
            trust_hint = 'Автопроверка охотнее пропускает ваши честные выполнения.' if language == 'ru' else 'Auto-check is more permissive for your honest completions.'
        elif score >= 60:
            trust_hint = 'Хорошая база доверия. Поддерживайте высокий процент одобрения.' if language == 'ru' else 'Good trust base. Keep your approval rate high.'
        else:
            trust_hint = 'Сначала наработайте историю честных выполнений, чтобы снижать ручные проверки.' if language == 'ru' else 'Build a history of honest completions to reduce manual reviews.'
        return {
            **counts,
            'score': score,
            'level_code': level_code,
            'level_label': level_label,
            'approval_rate': approval_rate,
            'task_bonus': task_bonus,
            'trust_hint': trust_hint,
        }
