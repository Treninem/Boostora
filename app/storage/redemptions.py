from __future__ import annotations

import json
from typing import Any

from app.storage.db import Database


class RedemptionRepository:
    def __init__(self, db: Database):
        self.db = db

    async def log_redemption(
        self,
        user_id: int,
        item_code: str,
        cost: int,
        status: str = 'completed',
        details: dict[str, Any] | None = None,
    ) -> int:
        async with await self.db.connect() as db:
            cur = await db.execute(
                """
                INSERT INTO reward_redemptions (user_id, item_code, cost, status, details_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (user_id, item_code, cost, status, json.dumps(details or {}, ensure_ascii=False)),
            )
            await db.commit()
            return int(cur.lastrowid)

    async def list_recent_redemptions(self, user_id: int, limit: int = 5) -> list[dict[str, Any]]:
        async with await self.db.connect() as db:
            async with db.execute(
                """
                SELECT * FROM reward_redemptions
                WHERE user_id=?
                ORDER BY id DESC
                LIMIT ?
                """,
                (user_id, limit),
            ) as cur:
                rows = await cur.fetchall()
                return [dict(row) for row in rows]
