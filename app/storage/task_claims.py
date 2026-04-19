from __future__ import annotations

import json
from typing import Any

from app.core.enums import ClaimStatus
from app.storage.db import Database


class TaskClaimRepository:
    def __init__(self, db: Database):
        self.db = db

    async def get_claim(self, claim_id: int) -> dict[str, Any] | None:
        async with await self.db.connect() as db:
            async with db.execute('SELECT * FROM task_claims WHERE id=?', (claim_id,)) as cur:
                row = await cur.fetchone()
                return dict(row) if row else None

    async def get_user_claim_for_campaign(self, user_id: int, campaign_id: int) -> dict[str, Any] | None:
        async with await self.db.connect() as db:
            async with db.execute(
                """
                SELECT * FROM task_claims
                WHERE user_id=? AND campaign_id=?
                ORDER BY id DESC
                LIMIT 1
                """,
                (user_id, campaign_id),
            ) as cur:
                row = await cur.fetchone()
                return dict(row) if row else None

    async def list_user_open_claims(self, user_id: int, limit: int = 5) -> list[dict[str, Any]]:
        async with await self.db.connect() as db:
            async with db.execute(
                """
                SELECT tc.*, c.task_type, c.target_url, c.title AS campaign_title
                FROM task_claims tc
                JOIN campaigns c ON c.id = tc.campaign_id
                WHERE tc.user_id=? AND tc.claim_status IN ('taken', 'submitted')
                ORDER BY tc.id DESC
                LIMIT ?
                """,
                (user_id, limit),
            ) as cur:
                rows = await cur.fetchall()
                return [dict(row) for row in rows]

    async def count_open_claims(self, user_id: int) -> int:
        async with await self.db.connect() as db:
            async with db.execute(
                "SELECT COUNT(*) AS cnt FROM task_claims WHERE user_id=? AND claim_status IN ('taken', 'submitted')",
                (user_id,),
            ) as cur:
                row = await cur.fetchone()
                return int(row['cnt']) if row else 0

    async def count_recent_verified(self, user_id: int, minutes: int = 10) -> int:
        async with await self.db.connect() as db:
            async with db.execute(
                """
                SELECT COUNT(*) AS cnt
                FROM task_claims
                WHERE user_id=?
                  AND claim_status='verified'
                  AND datetime(updated_at) >= datetime('now', ?)
                """,
                (user_id, f'-{minutes} minutes'),
            ) as cur:
                row = await cur.fetchone()
                return int(row['cnt']) if row else 0

    async def create_claim(self, campaign_id: int, user_id: int, reward_amount: int) -> int:
        async with await self.db.connect() as db:
            cur = await db.execute(
                """
                INSERT INTO task_claims (campaign_id, user_id, claim_status, reward_amount)
                VALUES (?, ?, ?, ?)
                """,
                (campaign_id, user_id, ClaimStatus.TAKEN.value, reward_amount),
            )
            await db.commit()
            return int(cur.lastrowid)

    async def mark_submitted(self, claim_id: int, proof: dict[str, Any] | None = None) -> None:
        async with await self.db.connect() as db:
            await db.execute(
                """
                UPDATE task_claims
                SET claim_status=?, proof_json=?, updated_at=CURRENT_TIMESTAMP
                WHERE id=?
                """,
                (ClaimStatus.SUBMITTED.value, json.dumps(proof or {}, ensure_ascii=False), claim_id),
            )
            await db.commit()

    async def mark_verified(self, claim_id: int, proof: dict[str, Any] | None = None) -> None:
        async with await self.db.connect() as db:
            await db.execute(
                """
                UPDATE task_claims
                SET claim_status=?, proof_json=?, updated_at=CURRENT_TIMESTAMP
                WHERE id=?
                """,
                (ClaimStatus.VERIFIED.value, json.dumps(proof or {}, ensure_ascii=False), claim_id),
            )
            await db.commit()

    async def mark_rejected(self, claim_id: int, reason: str, meta: dict[str, Any] | None = None) -> None:
        payload = meta or {}
        payload['reason'] = reason
        async with await self.db.connect() as db:
            await db.execute(
                """
                UPDATE task_claims
                SET claim_status=?, proof_json=?, updated_at=CURRENT_TIMESTAMP
                WHERE id=?
                """,
                (ClaimStatus.REJECTED.value, json.dumps(payload, ensure_ascii=False), claim_id),
            )
            await db.commit()
