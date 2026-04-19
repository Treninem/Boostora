from __future__ import annotations

import json
from typing import Any

from app.storage.db import Database


class AdminRepository:
    def __init__(self, db: Database):
        self.db = db

    async def log_event(
        self,
        admin_user_id: int,
        action: str,
        target_user_id: int | None = None,
        reason: str | None = None,
        meta: dict[str, Any] | None = None,
    ) -> None:
        async with await self.db.connect() as db:
            await db.execute(
                """
                INSERT INTO admin_events (admin_user_id, target_user_id, action, reason, meta_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (admin_user_id, target_user_id, action, reason, json.dumps(meta or {}, ensure_ascii=False)),
            )
            await db.commit()

    async def list_recent_events(self, limit: int = 12) -> list[dict[str, Any]]:
        async with await self.db.connect() as db:
            async with db.execute(
                """
                SELECT ae.*, 
                       au.username AS admin_username,
                       tu.username AS target_username
                FROM admin_events ae
                LEFT JOIN users au ON au.user_id = ae.admin_user_id
                LEFT JOIN users tu ON tu.user_id = ae.target_user_id
                ORDER BY ae.id DESC
                LIMIT ?
                """,
                (limit,),
            ) as cur:
                rows = await cur.fetchall()
                return [dict(row) for row in rows]

    async def get_dashboard_stats(self) -> dict[str, Any]:
        async with await self.db.connect() as db:
            async with db.execute(
                """
                SELECT
                    (SELECT COUNT(*) FROM users WHERE user_id > 0) AS total_users,
                    (SELECT COUNT(*) FROM users WHERE role='earner' AND user_id > 0) AS earners,
                    (SELECT COUNT(*) FROM users WHERE role='advertiser' AND user_id > 0) AS advertisers,
                    (SELECT COUNT(*) FROM users WHERE is_blocked=1 AND user_id > 0) AS blocked_users,
                    (SELECT COUNT(*) FROM users WHERE risk_score >= 35 AND user_id > 0) AS high_risk_users,
                    (SELECT COUNT(*) FROM campaigns WHERE status='active') AS active_campaigns,
                    (SELECT COUNT(*) FROM task_claims WHERE claim_status='submitted') AS review_claims,
                    (SELECT COUNT(*) FROM task_claims WHERE claim_status='verified') AS verified_claims,
                    (SELECT COUNT(*) FROM task_claims WHERE claim_status='rejected') AS rejected_claims
                """
            ) as cur:
                row = await cur.fetchone()
                return dict(row) if row else {}

    async def list_review_claims(self, limit: int = 10) -> list[dict[str, Any]]:
        async with await self.db.connect() as db:
            async with db.execute(
                """
                SELECT tc.*, c.title AS campaign_title, c.task_type, c.target_url,
                       u.username, u.first_name, u.locale, u.risk_score, u.completed_tasks, u.is_blocked
                FROM task_claims tc
                JOIN campaigns c ON c.id = tc.campaign_id
                JOIN users u ON u.user_id = tc.user_id
                WHERE tc.claim_status='submitted'
                ORDER BY tc.updated_at ASC, tc.id ASC
                LIMIT ?
                """,
                (limit,),
            ) as cur:
                rows = await cur.fetchall()
                return [dict(row) for row in rows]

    async def get_claim_admin_view(self, claim_id: int) -> dict[str, Any] | None:
        async with await self.db.connect() as db:
            async with db.execute(
                """
                SELECT tc.*, c.title AS campaign_title, c.task_type, c.target_url, c.status AS campaign_status,
                       u.username, u.first_name, u.locale, u.risk_score, u.completed_tasks, u.canceled_tasks, u.is_blocked
                FROM task_claims tc
                JOIN campaigns c ON c.id = tc.campaign_id
                JOIN users u ON u.user_id = tc.user_id
                WHERE tc.id=?
                LIMIT 1
                """,
                (claim_id,),
            ) as cur:
                row = await cur.fetchone()
                return dict(row) if row else None

    async def list_watch_users(self, limit: int = 15) -> list[dict[str, Any]]:
        async with await self.db.connect() as db:
            async with db.execute(
                """
                SELECT u.*, 
                       COALESCE(w.available_balance, 0) AS available_balance,
                       COALESCE(w.hold_balance, 0) AS hold_balance,
                       COALESCE((SELECT COUNT(*) FROM task_claims tc WHERE tc.user_id=u.user_id AND tc.claim_status='submitted'), 0) AS review_count
                FROM users u
                LEFT JOIN wallets w ON w.user_id = u.user_id
                WHERE u.user_id > 0
                ORDER BY u.is_blocked DESC, review_count DESC, u.risk_score DESC, u.completed_tasks DESC, u.user_id DESC
                LIMIT ?
                """,
                (limit,),
            ) as cur:
                rows = await cur.fetchall()
                return [dict(row) for row in rows]

    async def get_user_admin_snapshot(self, user_id: int) -> dict[str, Any] | None:
        async with await self.db.connect() as db:
            async with db.execute(
                """
                SELECT u.*, 
                       COALESCE(w.available_balance, 0) AS available_balance,
                       COALESCE(w.hold_balance, 0) AS hold_balance,
                       COALESCE(w.earned_total, 0) AS earned_total,
                       COALESCE(w.spent_balance, 0) AS spent_balance,
                       COALESCE((SELECT COUNT(*) FROM task_claims tc WHERE tc.user_id=u.user_id AND tc.claim_status='submitted'), 0) AS review_count,
                       COALESCE((SELECT COUNT(*) FROM campaigns c WHERE c.owner_user_id=u.user_id), 0) AS campaign_count
                FROM users u
                LEFT JOIN wallets w ON w.user_id = u.user_id
                WHERE u.user_id=?
                LIMIT 1
                """,
                (user_id,),
            ) as cur:
                row = await cur.fetchone()
                return dict(row) if row else None

    async def set_user_blocked(self, user_id: int, blocked: bool) -> None:
        async with await self.db.connect() as db:
            await db.execute(
                "UPDATE users SET is_blocked=?, updated_at=CURRENT_TIMESTAMP WHERE user_id=?",
                (1 if blocked else 0, user_id),
            )
            await db.commit()

    async def adjust_user_risk(self, user_id: int, delta: float) -> float | None:
        async with await self.db.connect() as db:
            async with db.execute('SELECT risk_score FROM users WHERE user_id=?', (user_id,)) as cur:
                row = await cur.fetchone()
                if not row:
                    return None
                current = float(row['risk_score'] or 0)
                new_value = max(0.0, min(100.0, round(current + delta, 1)))
                await db.execute(
                    'UPDATE users SET risk_score=?, updated_at=CURRENT_TIMESTAMP WHERE user_id=?',
                    (new_value, user_id),
                )
                await db.commit()
                return new_value
