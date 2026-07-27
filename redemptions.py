from __future__ import annotations

from dataclasses import dataclass

from app import db
from app.services.admin_logs import AdminLogService
from app.services.users import UserService


QUEUE_FILTERS = {'all', 'high', 'clean', 'old'}
DEFAULT_QUEUE_FILTER = 'all'


@dataclass(frozen=True)
class BulkResult:
    ok: bool
    result_key: str
    count: int = 0


def normalize_queue_filter(filter_code: str | None) -> str:
    value = (filter_code or '').strip().lower()
    return value if value in QUEUE_FILTERS else DEFAULT_QUEUE_FILTER


def queue_filter_label_key(filter_code: str | None) -> str:
    value = normalize_queue_filter(filter_code)
    return f'admin_queue_filter_{value}'


def priority_label_key(priority_score: int) -> str:
    if priority_score >= 80:
        return 'admin_priority_critical'
    if priority_score >= 50:
        return 'admin_priority_high'
    if priority_score >= 20:
        return 'admin_priority_medium'
    return 'admin_priority_clean'


class AdminConsoleService:
    @staticmethod
    def queue_filter_sql(filter_code: str | None) -> tuple[str, tuple[object, ...]]:
        value = normalize_queue_filter(filter_code)
        if value == 'high':
            return "AND (s.risk_score >= 15 OR u.risk_score >= 40)", ()
        if value == 'clean':
            return "AND s.risk_score <= 5 AND u.risk_score < 25 AND u.status != 'blocked'", ()
        if value == 'old':
            return "AND COALESCE(s.submitted_at, s.updated_at, s.created_at) <= datetime('now', '-12 hours')", ()
        return '', ()

    @staticmethod
    def queue_counts() -> dict[str, int]:
        row = db.fetch_one(
            '''
            SELECT
                (SELECT COUNT(*) FROM task_submissions s JOIN users u ON u.user_id = s.performer_user_id WHERE s.status = 'manual_review') AS all_count,
                (SELECT COUNT(*) FROM task_submissions s JOIN users u ON u.user_id = s.performer_user_id WHERE s.status = 'manual_review' AND (s.risk_score >= 15 OR u.risk_score >= 40)) AS high_count,
                (SELECT COUNT(*) FROM task_submissions s JOIN users u ON u.user_id = s.performer_user_id WHERE s.status = 'manual_review' AND s.risk_score <= 5 AND u.risk_score < 25 AND u.status != 'blocked') AS clean_count,
                (SELECT COUNT(*) FROM task_submissions s JOIN users u ON u.user_id = s.performer_user_id WHERE s.status = 'manual_review' AND COALESCE(s.submitted_at, s.updated_at, s.created_at) <= datetime('now', '-12 hours')) AS old_count
            '''
        )
        if not row:
            return {'all': 0, 'high': 0, 'clean': 0, 'old': 0}
        return {
            'all': int(row['all_count'] or 0),
            'high': int(row['high_count'] or 0),
            'clean': int(row['clean_count'] or 0),
            'old': int(row['old_count'] or 0),
        }

    @staticmethod
    def bot_rights_summary() -> dict[str, int]:
        row = db.fetch_one(
            '''
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN is_active = 1 THEN 1 ELSE 0 END) AS active,
                SUM(CASE WHEN is_active = 1 AND can_post = 1 THEN 1 ELSE 0 END) AS ready,
                SUM(CASE WHEN is_active = 1 AND can_post = 0 THEN 1 ELSE 0 END) AS issues
            FROM bot_chats
            '''
        )
        if not row:
            return {'total': 0, 'active': 0, 'ready': 0, 'issues': 0}
        return {
            'total': int(row['total'] or 0),
            'active': int(row['active'] or 0),
            'ready': int(row['ready'] or 0),
            'issues': int(row['issues'] or 0),
        }

    @staticmethod
    def risky_users_count() -> int:
        row = db.fetch_one("SELECT COUNT(*) AS cnt FROM users WHERE risk_score >= 60 AND status != 'blocked'")
        return int(row['cnt'] or 0) if row else 0

    @staticmethod
    def list_bot_right_issues(limit: int = 10, offset: int = 0):
        return db.fetch_all(
            '''
            SELECT * FROM bot_chats
            WHERE is_active = 1 AND can_post = 0
            ORDER BY COALESCE(last_seen_at, updated_at) DESC, chat_id DESC
            LIMIT ? OFFSET ?
            ''',
            (limit, offset),
        )

    @staticmethod
    def count_bot_right_issues() -> int:
        row = db.fetch_one('SELECT COUNT(*) AS cnt FROM bot_chats WHERE is_active = 1 AND can_post = 0')
        return int(row['cnt'] or 0) if row else 0

    @staticmethod
    def select_clean_submission_ids(limit: int = 10) -> list[int]:
        rows = db.fetch_all(
            '''
            SELECT s.id
            FROM task_submissions s
            JOIN users u ON u.user_id = s.performer_user_id
            WHERE s.status = 'manual_review'
              AND s.risk_score <= 5
              AND u.risk_score < 25
              AND u.status != 'blocked'
            ORDER BY COALESCE(s.submitted_at, s.updated_at, s.created_at) ASC, s.id ASC
            LIMIT ?
            ''',
            (limit,),
        )
        return [int(row['id']) for row in rows]

    @staticmethod
    def high_risk_user_ids(limit: int = 10, threshold: int = 60) -> list[int]:
        rows = db.fetch_all(
            '''
            SELECT user_id
            FROM users
            WHERE risk_score >= ?
              AND status != 'blocked'
            ORDER BY risk_score DESC, updated_at ASC, user_id ASC
            LIMIT ?
            ''',
            (threshold, limit),
        )
        return [int(row['user_id']) for row in rows if not UserService.is_admin(int(row['user_id']))]

    @staticmethod
    def block_high_risk_users(admin_user_id: int, limit: int = 10, threshold: int = 60) -> BulkResult:
        target_ids = AdminConsoleService.high_risk_user_ids(limit=limit, threshold=threshold)
        if not target_ids:
            return BulkResult(False, 'admin_bulk_no_targets', 0)
        blocked = 0
        for target_user_id in target_ids:
            db.execute(
                '''
                UPDATE users
                SET status = 'blocked', updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ? AND status != 'blocked'
                ''',
                (target_user_id,),
            )
            AdminLogService.log(
                admin_user_id,
                'bulk_block_high_risk_user',
                target_user_id=target_user_id,
                details=f'risk_threshold={threshold}',
            )
            blocked += 1
        return BulkResult(True, 'admin_bulk_blocked_high_risk', blocked)


DECISION_TEMPLATES = {
    'approve_clean': {
        'kind': 'approve',
        'ru': 'Доказательство выглядит чистым: цель совпадает, явных признаков накрутки или мусорного подтверждения нет.',
        'en': 'Proof looks clean: target matches and there are no clear fraud or junk-proof signs.',
    },
    'reject_wrong_target': {
        'kind': 'reject',
        'ru': 'Отклонено: подтверждение не относится к указанной цели задания.',
        'en': 'Rejected: proof does not match the task target.',
    },
    'reject_no_proof': {
        'kind': 'reject',
        'ru': 'Отклонено: подтверждение недостаточное или пустое, проверить выполнение нельзя.',
        'en': 'Rejected: proof is insufficient or empty, so completion cannot be verified.',
    },
    'reject_spam': {
        'kind': 'reject',
        'ru': 'Отклонено: подтверждение похоже на спам, повтор, мусорный текст или массовую автоматическую отправку.',
        'en': 'Rejected: proof looks like spam, duplicate, junk text or automated bulk submission.',
    },
}


def _template_language(language: str | None) -> str:
    return 'en' if language == 'en' else 'ru'


def _decision_template(template_code: str | None) -> dict[str, str] | None:
    return DECISION_TEMPLATES.get((template_code or '').strip())


def _template_kind(template_code: str | None) -> str | None:
    template = _decision_template(template_code)
    return str(template['kind']) if template else None


def _template_reason(template_code: str | None, language: str = 'ru') -> str:
    template = _decision_template(template_code)
    if not template:
        return ''
    lang = _template_language(language)
    return str(template.get(lang) or template.get('ru') or '')


def _decision_template_rows(language: str = 'ru') -> list[dict[str, str]]:
    lang = _template_language(language)
    return [
        {
            'code': code,
            'kind': str(template['kind']),
            'reason': str(template.get(lang) or template.get('ru') or ''),
        }
        for code, template in DECISION_TEMPLATES.items()
    ]


def _queue_group_summary(limit: int = 5) -> dict[str, list]:
    performers = db.fetch_all(
        '''
        SELECT
            s.performer_user_id,
            COALESCE(u.username, '') AS username,
            COUNT(*) AS cnt,
            MAX(s.risk_score + u.risk_score) AS max_priority,
            SUM(CASE WHEN s.risk_score >= 15 OR u.risk_score >= 40 THEN 1 ELSE 0 END) AS risky
        FROM task_submissions s
        JOIN users u ON u.user_id = s.performer_user_id
        WHERE s.status = 'manual_review'
        GROUP BY s.performer_user_id
        ORDER BY cnt DESC, max_priority DESC, s.performer_user_id ASC
        LIMIT ?
        ''',
        (limit,),
    )
    campaigns = db.fetch_all(
        '''
        SELECT
            s.campaign_id,
            COALESCE(c.title, '') AS title,
            COUNT(*) AS cnt,
            AVG(s.risk_score) AS avg_risk,
            SUM(CASE WHEN s.risk_score >= 15 THEN 1 ELSE 0 END) AS risky
        FROM task_submissions s
        JOIN campaigns c ON c.id = s.campaign_id
        WHERE s.status = 'manual_review'
        GROUP BY s.campaign_id
        ORDER BY cnt DESC, avg_risk DESC, s.campaign_id ASC
        LIMIT ?
        ''',
        (limit,),
    )
    risk_buckets = db.fetch_all(
        '''
        SELECT
            CASE
                WHEN s.risk_score + u.risk_score >= 80 THEN 'critical'
                WHEN s.risk_score + u.risk_score >= 50 THEN 'high'
                WHEN s.risk_score + u.risk_score >= 20 THEN 'medium'
                ELSE 'clean'
            END AS bucket,
            COUNT(*) AS cnt
        FROM task_submissions s
        JOIN users u ON u.user_id = s.performer_user_id
        WHERE s.status = 'manual_review'
        GROUP BY bucket
        ORDER BY CASE bucket WHEN 'critical' THEN 1 WHEN 'high' THEN 2 WHEN 'medium' THEN 3 ELSE 4 END
        '''
    )
    return {'performers': performers, 'campaigns': campaigns, 'risk_buckets': risk_buckets}


def _audit_bot_rights_live(bot, limit: int = 25) -> dict[str, int]:
    rows = db.fetch_all(
        '''
        SELECT * FROM bot_chats
        WHERE is_active = 1
        ORDER BY COALESCE(last_seen_at, updated_at) DESC, chat_id DESC
        LIMIT ?
        ''',
        (limit,),
    )
    if not rows:
        return {'checked': 0, 'ready': 0, 'issues': 0, 'failed': 0}
    try:
        me = bot.get_me()
        bot_id = int(me.id)
    except Exception:
        return {'checked': 0, 'ready': 0, 'issues': 0, 'failed': len(rows)}
    checked = ready = issues = failed = 0
    for row in rows:
        chat_id = int(row['chat_id'])
        chat_type = str(row['chat_type'] or 'group')
        can_post = False
        is_active = True
        try:
            member = bot.get_chat_member(chat_id, bot_id)
            status = str(getattr(member, 'status', '') or '').lower()
            is_active = status in {'member', 'administrator', 'creator'}
            if not is_active:
                can_post = False
            elif chat_type == 'channel':
                can_post = status == 'creator' or bool(getattr(member, 'can_post_messages', False))
            elif status == 'restricted':
                can_post = bool(getattr(member, 'can_send_messages', False))
            else:
                can_post = True
            try:
                chat = bot.get_chat(chat_id)
                title = getattr(chat, 'title', None) or str(row['title'] or '')
                username = getattr(chat, 'username', None) or str(row['username'] or '')
                chat_ref = f'@{username}' if username else str(chat_id)
            except Exception:
                title = str(row['title'] or '')
                username = str(row['username'] or '')
                chat_ref = str(row['chat_ref'] or chat_id)
            db.execute(
                '''
                UPDATE bot_chats
                SET chat_ref = ?, title = ?, username = ?, is_active = ?, can_post = ?, last_seen_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                WHERE chat_id = ?
                ''',
                (chat_ref, title, username, 1 if is_active else 0, 1 if can_post else 0, chat_id),
            )
            checked += 1
            if can_post:
                ready += 1
            else:
                issues += 1
        except Exception:
            db.execute('UPDATE bot_chats SET can_post = 0, updated_at = CURRENT_TIMESTAMP WHERE chat_id = ?', (chat_id,))
            checked += 1
            failed += 1
            issues += 1
    return {'checked': checked, 'ready': ready, 'issues': issues, 'failed': failed}


AdminConsoleService.decision_templates = staticmethod(_decision_template_rows)
AdminConsoleService.template_kind = staticmethod(_template_kind)
AdminConsoleService.template_reason = staticmethod(_template_reason)
AdminConsoleService.queue_group_summary = staticmethod(_queue_group_summary)
AdminConsoleService.audit_bot_rights_live = staticmethod(_audit_bot_rights_live)


# Boostora v2.4.0 — antifraud pattern intelligence, decision history and safer bulk prompts.
def _bot_rights_diagnostics(limit: int = 12) -> dict[str, object]:
    summary = AdminConsoleService.bot_rights_summary()
    stale_row = db.fetch_one(
        """
        SELECT COUNT(*) AS cnt
        FROM bot_chats
        WHERE is_active = 1
          AND (last_seen_at IS NULL OR last_seen_at <= datetime('now', '-24 hours'))
        """
    )
    inactive_row = db.fetch_one("SELECT COUNT(*) AS cnt FROM bot_chats WHERE is_active = 0")
    rows = db.fetch_all(
        """
        SELECT *
        FROM bot_chats
        WHERE is_active = 0
           OR can_post = 0
           OR last_seen_at IS NULL
           OR last_seen_at <= datetime('now', '-24 hours')
        ORDER BY
            CASE WHEN is_active = 0 THEN 0 WHEN can_post = 0 THEN 1 ELSE 2 END,
            COALESCE(last_seen_at, updated_at) ASC,
            chat_id DESC
        LIMIT ?
        """,
        (limit,),
    )
    diagnostics = []
    for row in rows:
        chat_type = str(row['chat_type'] or 'group')
        is_active = int(row['is_active'] or 0) == 1
        can_post = int(row['can_post'] or 0) == 1
        if not is_active:
            code = 'inactive'
            severity = 'critical'
        elif not can_post and chat_type == 'channel':
            code = 'channel_no_post'
            severity = 'high'
        elif not can_post:
            code = 'chat_no_send'
            severity = 'high'
        else:
            code = 'stale'
            severity = 'medium'
        diagnostics.append({
            'chat_id': int(row['chat_id']),
            'title': str(row['title'] or row['chat_ref'] or row['chat_id']),
            'ref': str(row['chat_ref'] or row['chat_id']),
            'chat_type': chat_type,
            'code': code,
            'severity': severity,
            'last_seen_at': str(row['last_seen_at'] or '—'),
        })
    return {
        'active': int(summary.get('active', 0)),
        'ready': int(summary.get('ready', 0)),
        'issues': int(summary.get('issues', 0)),
        'stale': int(stale_row['cnt'] or 0) if stale_row else 0,
        'inactive': int(inactive_row['cnt'] or 0) if inactive_row else 0,
        'items': diagnostics,
    }


def _performer_decision_history(user_id: int, limit: int = 5):
    return db.fetch_all(
        """
        SELECT
            s.id,
            s.status,
            s.risk_score,
            s.reject_reason,
            s.reviewed_at,
            s.reviewer_user_id,
            c.title AS campaign_title
        FROM task_submissions s
        JOIN campaigns c ON c.id = s.campaign_id
        WHERE s.performer_user_id = ?
          AND s.status IN ('approved', 'rejected')
        ORDER BY COALESCE(s.reviewed_at, s.updated_at, s.created_at) DESC, s.id DESC
        LIMIT ?
        """,
        (user_id, limit),
    )


def _performer_pattern_card(user_id: int) -> dict[str, object]:
    row = db.fetch_one(
        """
        SELECT
            u.user_id,
            COALESCE(u.username, '') AS username,
            u.status,
            u.risk_score,
            SUM(CASE WHEN s.status = 'approved' THEN 1 ELSE 0 END) AS approved_count,
            SUM(CASE WHEN s.status = 'rejected' THEN 1 ELSE 0 END) AS rejected_count,
            SUM(CASE WHEN s.status = 'manual_review' THEN 1 ELSE 0 END) AS review_count,
            AVG(CASE WHEN s.id IS NOT NULL THEN s.risk_score ELSE NULL END) AS avg_submission_risk,
            (SELECT COUNT(*) FROM admin_notes n WHERE n.target_user_id = u.user_id) AS note_count,
            (SELECT COUNT(*) FROM risk_events e WHERE e.user_id = u.user_id) AS event_count
        FROM users u
        LEFT JOIN task_submissions s ON s.performer_user_id = u.user_id
        WHERE u.user_id = ?
        GROUP BY u.user_id
        """,
        (user_id,),
    )
    if not row:
        return {
            'user_id': user_id,
            'username': '',
            'status': 'unknown',
            'risk_score': 0,
            'approved_count': 0,
            'rejected_count': 0,
            'review_count': 0,
            'avg_submission_risk': 0,
            'note_count': 0,
            'event_count': 0,
            'reject_rate': 0,
            'pattern_code': 'unknown',
            'recommendation_code': 'watch',
        }
    approved = int(row['approved_count'] or 0)
    rejected = int(row['rejected_count'] or 0)
    review = int(row['review_count'] or 0)
    risk = int(row['risk_score'] or 0)
    notes = int(row['note_count'] or 0)
    events = int(row['event_count'] or 0)
    total_decided = approved + rejected
    reject_rate = (rejected / total_decided * 100.0) if total_decided else 0.0
    if risk >= 70 or reject_rate >= 60 or notes >= 3:
        pattern_code = 'hard_risk'
        recommendation_code = 'block_or_manual'
    elif risk >= 40 or reject_rate >= 35 or review >= 3 or events >= 5:
        pattern_code = 'unstable'
        recommendation_code = 'manual_priority'
    elif approved >= 5 and reject_rate <= 15 and risk < 25:
        pattern_code = 'trusted'
        recommendation_code = 'soft_review'
    else:
        pattern_code = 'neutral'
        recommendation_code = 'watch'
    return {
        'user_id': int(row['user_id']),
        'username': str(row['username'] or ''),
        'status': str(row['status'] or 'active'),
        'risk_score': risk,
        'approved_count': approved,
        'rejected_count': rejected,
        'review_count': review,
        'avg_submission_risk': int(float(row['avg_submission_risk'] or 0)),
        'note_count': notes,
        'event_count': events,
        'reject_rate': int(reject_rate),
        'pattern_code': pattern_code,
        'recommendation_code': recommendation_code,
    }


def _fraud_pattern_cards(limit: int = 8) -> list[dict[str, object]]:
    rows = db.fetch_all(
        """
        SELECT
            u.user_id,
            COALESCE(u.username, '') AS username,
            u.status,
            u.risk_score,
            SUM(CASE WHEN s.status = 'approved' THEN 1 ELSE 0 END) AS approved_count,
            SUM(CASE WHEN s.status = 'rejected' THEN 1 ELSE 0 END) AS rejected_count,
            SUM(CASE WHEN s.status = 'manual_review' THEN 1 ELSE 0 END) AS review_count,
            AVG(CASE WHEN s.id IS NOT NULL THEN s.risk_score ELSE NULL END) AS avg_submission_risk,
            (SELECT COUNT(*) FROM admin_notes n WHERE n.target_user_id = u.user_id) AS note_count,
            (SELECT COUNT(*) FROM risk_events e WHERE e.user_id = u.user_id) AS event_count
        FROM users u
        LEFT JOIN task_submissions s ON s.performer_user_id = u.user_id
        GROUP BY u.user_id
        HAVING u.risk_score >= 25
            OR rejected_count >= 2
            OR review_count >= 2
            OR note_count >= 1
            OR event_count >= 3
        ORDER BY
            u.risk_score DESC,
            note_count DESC,
            rejected_count DESC,
            review_count DESC,
            u.updated_at DESC
        LIMIT ?
        """,
        (limit,),
    )
    return [_performer_pattern_card(int(row['user_id'])) for row in rows]


def _bulk_action_advice(filter_code: str | None) -> dict[str, object]:
    value = normalize_queue_filter(filter_code)
    counts = AdminConsoleService.queue_counts()
    if value == 'clean':
        return {
            'action_code': 'approve_clean',
            'count': min(int(counts.get('clean', 0)), 10),
            'risk_level': 'low',
            'advice_code': 'bulk_clean_safe',
        }
    if value == 'high':
        return {
            'action_code': 'block_high',
            'count': min(AdminConsoleService.risky_users_count(), 10),
            'risk_level': 'high',
            'advice_code': 'bulk_high_caution',
        }
    if value == 'old':
        return {
            'action_code': 'review_old',
            'count': int(counts.get('old', 0)),
            'risk_level': 'medium',
            'advice_code': 'bulk_old_caution',
        }
    return {
        'action_code': 'none',
        'count': 0,
        'risk_level': 'none',
        'advice_code': 'bulk_none',
    }


AdminConsoleService.bot_rights_diagnostics = staticmethod(_bot_rights_diagnostics)
AdminConsoleService.performer_decision_history = staticmethod(_performer_decision_history)
AdminConsoleService.performer_pattern_card = staticmethod(_performer_pattern_card)
AdminConsoleService.fraud_pattern_cards = staticmethod(_fraud_pattern_cards)
AdminConsoleService.bulk_action_advice = staticmethod(_bulk_action_advice)
