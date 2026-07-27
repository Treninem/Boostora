from __future__ import annotations

from typing import Any

from app import db


def _as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _safe_percent(part: int, total: int) -> int:
    if total <= 0:
        return 0
    return int(round((part / total) * 100))


class OwnerAnalyticsService:
    """Owner-only commercial analytics on top of existing Boostora tables."""

    @staticmethod
    def commerce_summary() -> dict[str, int | str]:
        users = db.fetch_one(
            '''
            SELECT
                COUNT(*) AS total_users,
                SUM(CASE WHEN status = 'active' THEN 1 ELSE 0 END) AS active_users,
                SUM(CASE WHEN status = 'blocked' THEN 1 ELSE 0 END) AS blocked_users,
                SUM(CASE WHEN role = 'client' THEN 1 ELSE 0 END) AS clients,
                SUM(CASE WHEN role = 'performer' THEN 1 ELSE 0 END) AS performers,
                SUM(CASE WHEN risk_score >= 60 AND status != 'blocked' THEN 1 ELSE 0 END) AS risky_unblocked
            FROM users
            '''
        )
        campaigns = db.fetch_one(
            '''
            SELECT
                COUNT(*) AS total_campaigns,
                SUM(CASE WHEN status = 'active' THEN 1 ELSE 0 END) AS active_campaigns,
                SUM(CASE WHEN status = 'paused' THEN 1 ELSE 0 END) AS paused_campaigns,
                SUM(CASE WHEN status = 'draft' THEN 1 ELSE 0 END) AS draft_campaigns,
                SUM(CASE WHEN is_funded = 1 THEN 1 ELSE 0 END) AS funded_campaigns,
                COALESCE(SUM(total_quantity), 0) AS quantity_total,
                COALESCE(SUM(completed_quantity), 0) AS completed_total,
                COALESCE(SUM(rejected_quantity), 0) AS rejected_total,
                COALESCE(SUM(budget_total), 0) AS budget_total,
                COALESCE(SUM(CASE WHEN is_funded = 1 THEN budget_total ELSE 0 END), 0) AS funded_budget_total,
                COALESCE(SUM(budget_spent), 0) AS turnover_spent,
                COALESCE(SUM(budget_reserved), 0) AS reserved_total,
                COALESCE(SUM(service_fee_total), 0) AS planned_fee_total,
                COALESCE(SUM(completed_quantity * CASE WHEN unit_price > reward_amount THEN unit_price - reward_amount ELSE 0 END), 0) AS actual_margin_estimate
            FROM campaigns
            '''
        )
        submissions = db.fetch_one(
            '''
            SELECT
                COUNT(*) AS total_submissions,
                SUM(CASE WHEN status = 'manual_review' THEN 1 ELSE 0 END) AS manual_review,
                SUM(CASE WHEN status = 'approved' THEN 1 ELSE 0 END) AS approved,
                SUM(CASE WHEN status = 'rejected' THEN 1 ELSE 0 END) AS rejected,
                COALESCE(AVG(CASE WHEN status IN ('approved', 'rejected', 'manual_review') THEN risk_score END), 0) AS avg_submission_risk
            FROM task_submissions
            '''
        )
        wallets = db.fetch_one(
            '''
            SELECT
                COALESCE(SUM(available_balance), 0) AS available_liability,
                COALESCE(SUM(hold_balance), 0) AS hold_liability,
                COALESCE(SUM(bonus_balance), 0) AS bonus_liability,
                COALESCE(SUM(internal_balance), 0) AS internal_balance_total,
                COALESCE(SUM(lifetime_earned), 0) AS lifetime_earned,
                COALESCE(SUM(total_withdrawn), 0) AS total_withdrawn
            FROM wallets
            '''
        )
        transactions = db.fetch_one(
            '''
            SELECT
                COALESCE(SUM(CASE WHEN entry_type = 'stars_topup' AND direction = 'credit' THEN amount ELSE 0 END), 0) AS stars_topup_volume,
                COALESCE(SUM(CASE WHEN entry_type = 'vip_purchase' THEN ABS(amount) ELSE 0 END), 0) AS vip_volume,
                COALESCE(SUM(CASE WHEN entry_type = 'reward_purchase' THEN ABS(amount) ELSE 0 END), 0) AS reward_store_volume,
                COALESCE(SUM(CASE WHEN entry_type IN ('campaign_funding', 'campaign_boost') THEN ABS(amount) ELSE 0 END), 0) AS campaign_payment_volume,
                COALESCE(SUM(CASE WHEN status = 'hold' THEN amount ELSE 0 END), 0) AS tx_hold_volume
            FROM transactions
            '''
        )
        total_quantity = _as_int(campaigns['quantity_total'] if campaigns else 0)
        completed_total = _as_int(campaigns['completed_total'] if campaigns else 0)
        rejected_total = _as_int(campaigns['rejected_total'] if campaigns else 0)
        total_submissions = _as_int(submissions['total_submissions'] if submissions else 0)
        approved_submissions = _as_int(submissions['approved'] if submissions else 0)
        rejected_submissions = _as_int(submissions['rejected'] if submissions else 0)
        manual_review = _as_int(submissions['manual_review'] if submissions else 0)
        turnover_spent = _as_int(campaigns['turnover_spent'] if campaigns else 0)
        actual_margin = _as_int(campaigns['actual_margin_estimate'] if campaigns else 0)
        margin_percent = _safe_percent(actual_margin, turnover_spent)
        approval_percent = _safe_percent(approved_submissions, approved_submissions + rejected_submissions)
        manual_percent = _safe_percent(manual_review, total_submissions)
        completion_percent = _safe_percent(completed_total, total_quantity)
        monetization_score = OwnerAnalyticsService._monetization_score(
            active_campaigns=_as_int(campaigns['active_campaigns'] if campaigns else 0),
            turnover_spent=turnover_spent,
            margin_percent=margin_percent,
            manual_percent=manual_percent,
            approval_percent=approval_percent,
        )
        user_total = _as_int(users['total_users'] if users else 0)
        return {
            'total_users': user_total,
            'active_users': _as_int(users['active_users'] if users else 0),
            'blocked_users': _as_int(users['blocked_users'] if users else 0),
            'clients': _as_int(users['clients'] if users else 0),
            'performers': _as_int(users['performers'] if users else 0),
            'risky_unblocked': _as_int(users['risky_unblocked'] if users else 0),
            'total_campaigns': _as_int(campaigns['total_campaigns'] if campaigns else 0),
            'active_campaigns': _as_int(campaigns['active_campaigns'] if campaigns else 0),
            'paused_campaigns': _as_int(campaigns['paused_campaigns'] if campaigns else 0),
            'draft_campaigns': _as_int(campaigns['draft_campaigns'] if campaigns else 0),
            'funded_campaigns': _as_int(campaigns['funded_campaigns'] if campaigns else 0),
            'quantity_total': total_quantity,
            'completed_total': completed_total,
            'rejected_total': rejected_total,
            'completion_percent': completion_percent,
            'budget_total': _as_int(campaigns['budget_total'] if campaigns else 0),
            'funded_budget_total': _as_int(campaigns['funded_budget_total'] if campaigns else 0),
            'turnover_spent': turnover_spent,
            'reserved_total': _as_int(campaigns['reserved_total'] if campaigns else 0),
            'planned_fee_total': _as_int(campaigns['planned_fee_total'] if campaigns else 0),
            'actual_margin_estimate': actual_margin,
            'margin_percent': margin_percent,
            'total_submissions': total_submissions,
            'manual_review': manual_review,
            'approved_submissions': approved_submissions,
            'rejected_submissions': rejected_submissions,
            'approval_percent': approval_percent,
            'manual_percent': manual_percent,
            'avg_submission_risk': int(float(submissions['avg_submission_risk'] or 0)) if submissions else 0,
            'available_liability': _as_int(wallets['available_liability'] if wallets else 0),
            'hold_liability': _as_int(wallets['hold_liability'] if wallets else 0),
            'bonus_liability': _as_int(wallets['bonus_liability'] if wallets else 0),
            'internal_balance_total': _as_int(wallets['internal_balance_total'] if wallets else 0),
            'lifetime_earned': _as_int(wallets['lifetime_earned'] if wallets else 0),
            'total_withdrawn': _as_int(wallets['total_withdrawn'] if wallets else 0),
            'stars_topup_volume': _as_int(transactions['stars_topup_volume'] if transactions else 0),
            'vip_volume': _as_int(transactions['vip_volume'] if transactions else 0),
            'reward_store_volume': _as_int(transactions['reward_store_volume'] if transactions else 0),
            'campaign_payment_volume': _as_int(transactions['campaign_payment_volume'] if transactions else 0),
            'tx_hold_volume': _as_int(transactions['tx_hold_volume'] if transactions else 0),
            'monetization_score': monetization_score,
            'commerce_state': OwnerAnalyticsService._state_code(monetization_score, margin_percent, manual_percent, user_total),
        }

    @staticmethod
    def _monetization_score(*, active_campaigns: int, turnover_spent: int, margin_percent: int, manual_percent: int, approval_percent: int) -> int:
        score = 0
        score += min(active_campaigns * 8, 32)
        score += min(turnover_spent // 100, 28)
        score += min(max(margin_percent, 0), 25)
        score += min(max(approval_percent - 40, 0) // 3, 10)
        score -= min(manual_percent // 4, 18)
        return max(0, min(score, 100))

    @staticmethod
    def _state_code(score: int, margin_percent: int, manual_percent: int, users: int) -> str:
        if users == 0:
            return 'empty'
        if score >= 70 and margin_percent >= 15 and manual_percent <= 25:
            return 'strong'
        if score >= 40:
            return 'growing'
        if manual_percent >= 45:
            return 'risk_heavy'
        return 'early'

    @staticmethod
    def top_clients(limit: int = 5) -> list[dict[str, Any]]:
        return [dict(row) for row in db.fetch_all(
            '''
            SELECT
                c.owner_user_id AS user_id,
                COALESCE(u.username, '') AS username,
                COUNT(*) AS campaigns,
                SUM(CASE WHEN c.status = 'active' THEN 1 ELSE 0 END) AS active_campaigns,
                COALESCE(SUM(c.budget_total), 0) AS budget_total,
                COALESCE(SUM(c.budget_spent), 0) AS spent,
                COALESCE(SUM(c.completed_quantity), 0) AS completed,
                COALESCE(SUM(c.rejected_quantity), 0) AS rejected
            FROM campaigns c
            LEFT JOIN users u ON u.user_id = c.owner_user_id
            GROUP BY c.owner_user_id
            ORDER BY spent DESC, budget_total DESC, campaigns DESC
            LIMIT ?
            ''',
            (limit,),
        )]

    @staticmethod
    def top_performers(limit: int = 5) -> list[dict[str, Any]]:
        return [dict(row) for row in db.fetch_all(
            '''
            SELECT
                s.performer_user_id AS user_id,
                COALESCE(u.username, '') AS username,
                COALESCE(u.risk_score, 0) AS risk_score,
                COUNT(*) AS submissions,
                SUM(CASE WHEN s.status = 'approved' THEN 1 ELSE 0 END) AS approved,
                SUM(CASE WHEN s.status = 'rejected' THEN 1 ELSE 0 END) AS rejected,
                SUM(CASE WHEN s.status = 'manual_review' THEN 1 ELSE 0 END) AS manual_review,
                COALESCE(SUM(CASE WHEN s.status = 'approved' THEN s.reward_amount ELSE 0 END), 0) AS earned
            FROM task_submissions s
            LEFT JOIN users u ON u.user_id = s.performer_user_id
            GROUP BY s.performer_user_id
            ORDER BY approved DESC, earned DESC, risk_score ASC
            LIMIT ?
            ''',
            (limit,),
        )]

    @staticmethod
    def economy_recommendations(summary: dict[str, int | str] | None = None) -> list[str]:
        data = summary or OwnerAnalyticsService.commerce_summary()
        tips: list[str] = []
        if _as_int(data.get('active_campaigns')) == 0:
            tips.append('owner_tip_no_active_campaigns')
        if _as_int(data.get('margin_percent')) < 12 and _as_int(data.get('turnover_spent')) > 0:
            tips.append('owner_tip_low_margin')
        if _as_int(data.get('manual_percent')) >= 35:
            tips.append('owner_tip_manual_overload')
        if _as_int(data.get('risky_unblocked')) > 0:
            tips.append('owner_tip_risky_unblocked')
        if _as_int(data.get('draft_campaigns')) > _as_int(data.get('active_campaigns')):
            tips.append('owner_tip_many_drafts')
        if _as_int(data.get('stars_topup_volume')) == 0 and _as_int(data.get('total_users')) > 10:
            tips.append('owner_tip_topup_conversion')
        if not tips:
            tips.append('owner_tip_stable_growth')
        return tips[:5]
