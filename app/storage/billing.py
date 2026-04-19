
from __future__ import annotations

import json
from typing import Any

from app.storage.db import Database


class BillingRepository:
    def __init__(self, db: Database):
        self.db = db

    async def create_order(
        self,
        user_id: int,
        purpose: str,
        payload: str,
        amount_xtr: int,
        credit_amount: int = 0,
        details: dict[str, Any] | None = None,
    ) -> int:
        async with await self.db.connect() as db:
            cur = await db.execute(
                """
                INSERT INTO billing_orders (user_id, purpose, payload, amount_xtr, credit_amount, details_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (user_id, purpose, payload, amount_xtr, credit_amount, json.dumps(details or {}, ensure_ascii=False)),
            )
            await db.commit()
            return int(cur.lastrowid)

    async def get_order_by_payload(self, payload: str) -> dict[str, Any] | None:
        async with await self.db.connect() as db:
            async with db.execute('SELECT * FROM billing_orders WHERE payload=?', (payload,)) as cur:
                row = await cur.fetchone()
                return dict(row) if row else None

    async def mark_paid(
        self,
        payload: str,
        telegram_charge_id: str | None,
        provider_charge_id: str | None,
        details: dict[str, Any] | None = None,
    ) -> None:
        async with await self.db.connect() as db:
            await db.execute(
                """
                UPDATE billing_orders
                SET status='paid',
                    telegram_charge_id=?,
                    provider_charge_id=?,
                    details_json=?,
                    updated_at=CURRENT_TIMESTAMP
                WHERE payload=?
                """,
                (
                    telegram_charge_id,
                    provider_charge_id,
                    json.dumps(details or {}, ensure_ascii=False),
                    payload,
                ),
            )
            await db.commit()

    async def mark_failed(self, payload: str, details: dict[str, Any] | None = None) -> None:
        async with await self.db.connect() as db:
            await db.execute(
                """
                UPDATE billing_orders
                SET status='failed', details_json=?, updated_at=CURRENT_TIMESTAMP
                WHERE payload=?
                """,
                (json.dumps(details or {}, ensure_ascii=False), payload),
            )
            await db.commit()

    async def list_recent_orders(self, user_id: int, limit: int = 5) -> list[dict[str, Any]]:
        async with await self.db.connect() as db:
            async with db.execute(
                """
                SELECT * FROM billing_orders
                WHERE user_id=?
                ORDER BY id DESC
                LIMIT ?
                """,
                (user_id, limit),
            ) as cur:
                rows = await cur.fetchall()
                return [dict(row) for row in rows]
