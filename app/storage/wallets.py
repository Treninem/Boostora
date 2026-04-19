from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from app.storage.db import Database


class WalletRepository:
    def __init__(self, db: Database):
        self.db = db

    async def get_wallet(self, user_id: int) -> dict[str, Any]:
        async with await self.db.connect() as db:
            async with db.execute('SELECT * FROM wallets WHERE user_id=?', (user_id,)) as cur:
                row = await cur.fetchone()
                return dict(row) if row else {
                    'user_id': user_id,
                    'available_balance': 0,
                    'hold_balance': 0,
                    'spent_balance': 0,
                    'earned_total': 0,
                }

    async def list_recent_entries(self, user_id: int, limit: int = 5) -> list[dict[str, Any]]:
        async with await self.db.connect() as db:
            async with db.execute(
                """
                SELECT * FROM wallet_ledger
                WHERE user_id=?
                ORDER BY id DESC
                LIMIT ?
                """,
                (user_id, limit),
            ) as cur:
                rows = await cur.fetchall()
                return [dict(row) for row in rows]

    async def list_pending_holds(self, user_id: int, limit: int = 10) -> list[dict[str, Any]]:
        async with await self.db.connect() as db:
            async with db.execute(
                """
                SELECT * FROM reward_holds
                WHERE user_id=? AND status='pending'
                ORDER BY release_at ASC, id ASC
                LIMIT ?
                """,
                (user_id, limit),
            ) as cur:
                rows = await cur.fetchall()
                return [dict(row) for row in rows]

    async def add_hold(
        self,
        user_id: int,
        amount: int,
        source_type: str,
        source_id: int | None,
        release_at: str,
        reason: str,
    ) -> int:
        async with await self.db.connect() as db:
            await db.execute(
                """
                UPDATE wallets
                SET hold_balance = hold_balance + ?,
                    updated_at=CURRENT_TIMESTAMP
                WHERE user_id=?
                """,
                (amount, user_id),
            )
            cur = await db.execute(
                """
                INSERT INTO reward_holds (user_id, source_type, source_id, amount, release_at, reason)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (user_id, source_type, source_id, amount, release_at, reason),
            )
            await db.execute(
                """
                INSERT INTO wallet_ledger (user_id, entry_type, amount, balance_after, hold_after, description, meta_json)
                SELECT user_id, 'task_reward_pending', ?, available_balance, hold_balance, ?, ?
                FROM wallets WHERE user_id=?
                """,
                (amount, reason, json.dumps({'source_type': source_type, 'source_id': source_id}, ensure_ascii=False), user_id),
            )
            await db.commit()
            return int(cur.lastrowid)

    async def release_ready_holds(self, user_id: int) -> tuple[int, int]:
        now = datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S')
        async with await self.db.connect() as db:
            async with db.execute(
                """
                SELECT * FROM reward_holds
                WHERE user_id=? AND status='pending' AND release_at <= ?
                ORDER BY id ASC
                """,
                (user_id, now),
            ) as cur:
                holds = [dict(row) for row in await cur.fetchall()]

            released_count = 0
            released_amount = 0
            for hold in holds:
                amount = int(hold['amount'])
                released_count += 1
                released_amount += amount
                await db.execute(
                    """
                    UPDATE wallets
                    SET hold_balance = hold_balance - ?,
                        available_balance = available_balance + ?,
                        earned_total = earned_total + ?,
                        updated_at=CURRENT_TIMESTAMP
                    WHERE user_id=?
                    """,
                    (amount, amount, amount, user_id),
                )
                await db.execute(
                    """
                    UPDATE reward_holds
                    SET status='released', updated_at=CURRENT_TIMESTAMP
                    WHERE id=?
                    """,
                    (hold['id'],),
                )
                await db.execute(
                    """
                    INSERT INTO wallet_ledger (user_id, entry_type, amount, balance_after, hold_after, description, meta_json)
                    SELECT user_id, 'task_reward_release', ?, available_balance, hold_balance, ?, ?
                    FROM wallets WHERE user_id=?
                    """,
                    (
                        amount,
                        hold.get('reason') or 'reward released',
                        json.dumps({'hold_id': hold['id'], 'source_type': hold.get('source_type')}, ensure_ascii=False),
                        user_id,
                    ),
                )
            await db.commit()
            return released_count, released_amount

    async def revoke_hold(self, hold_id: int, reason: str) -> None:
        async with await self.db.connect() as db:
            async with db.execute(
                'SELECT * FROM reward_holds WHERE id=? AND status="pending"',
                (hold_id,),
            ) as cur:
                hold = await cur.fetchone()
                if not hold:
                    return
                amount = int(hold['amount'])
                user_id = int(hold['user_id'])
                await db.execute(
                    """
                    UPDATE wallets
                    SET hold_balance = hold_balance - ?,
                        updated_at=CURRENT_TIMESTAMP
                    WHERE user_id=?
                    """,
                    (amount, user_id),
                )
                await db.execute(
                    """
                    UPDATE reward_holds
                    SET status='revoked', reason=?, updated_at=CURRENT_TIMESTAMP
                    WHERE id=?
                    """,
                    (reason, hold_id),
                )
                await db.execute(
                    """
                    INSERT INTO wallet_ledger (user_id, entry_type, amount, hold_after, description)
                    SELECT user_id, 'task_reward_revoke', ?, hold_balance, ?
                    FROM wallets WHERE user_id=?
                    """,
                    (-amount, reason, user_id),
                )
                await db.commit()

    async def add_available(
        self,
        user_id: int,
        amount: int,
        entry_type: str,
        description: str,
        meta: dict[str, Any] | None = None,
    ) -> None:
        async with await self.db.connect() as db:
            await db.execute(
                """
                UPDATE wallets
                SET available_balance = available_balance + ?,
                    earned_total = earned_total + CASE WHEN ? > 0 THEN ? ELSE 0 END,
                    spent_balance = spent_balance + CASE WHEN ? < 0 THEN ABS(?) ELSE 0 END,
                    updated_at=CURRENT_TIMESTAMP
                WHERE user_id=?
                """,
                (amount, amount, amount, amount, amount, user_id),
            )
            await db.execute(
                """
                INSERT INTO wallet_ledger (user_id, entry_type, amount, balance_after, hold_after, description, meta_json)
                SELECT user_id, ?, ?, available_balance, hold_balance, ?, ?
                FROM wallets WHERE user_id=?
                """,
                (entry_type, amount, description, json.dumps(meta or {}, ensure_ascii=False), user_id),
            )
            await db.commit()
