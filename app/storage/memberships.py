from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from app.core.enums import UserTier
from app.storage.db import Database


class MembershipRepository:
    def __init__(self, db: Database):
        self.db = db

    async def sync_user(self, user_id: int) -> None:
        now = datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S')
        async with await self.db.connect() as db:
            await db.execute(
                """
                UPDATE memberships
                SET status='expired', updated_at=CURRENT_TIMESTAMP
                WHERE user_id=? AND status='active' AND ends_at <= ?
                """,
                (user_id, now),
            )
            async with db.execute(
                """
                SELECT COUNT(*) AS cnt
                FROM memberships
                WHERE user_id=? AND perk_code='vip' AND status='active' AND ends_at > ?
                """,
                (user_id, now),
            ) as cur:
                row = await cur.fetchone()
                has_vip = int(row['cnt']) > 0 if row else False

            if has_vip:
                await db.execute(
                    "UPDATE users SET tier=?, updated_at=CURRENT_TIMESTAMP WHERE user_id=?",
                    (UserTier.VIP.value, user_id),
                )
            else:
                async with db.execute(
                    'SELECT completed_tasks, tier FROM users WHERE user_id=?',
                    (user_id,),
                ) as cur:
                    user = await cur.fetchone()
                if user:
                    completed = int(user['completed_tasks'] or 0)
                    desired = UserTier.VERIFIED.value if completed >= 10 else UserTier.NEW.value
                    if str(user['tier']) == UserTier.VIP.value:
                        await db.execute(
                            "UPDATE users SET tier=?, updated_at=CURRENT_TIMESTAMP WHERE user_id=?",
                            (desired, user_id),
                        )
            await db.commit()

    async def list_active_memberships(self, user_id: int) -> list[dict[str, Any]]:
        await self.sync_user(user_id)
        now = datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S')
        async with await self.db.connect() as db:
            async with db.execute(
                """
                SELECT * FROM memberships
                WHERE user_id=? AND status='active' AND ends_at > ?
                ORDER BY ends_at ASC, id ASC
                """,
                (user_id, now),
            ) as cur:
                rows = await cur.fetchall()
                return [dict(row) for row in rows]

    async def get_active_perk_codes(self, user_id: int) -> set[str]:
        memberships = await self.list_active_memberships(user_id)
        return {str(item['perk_code']) for item in memberships}

    async def get_membership_ends_at(self, user_id: int, perk_code: str) -> str | None:
        await self.sync_user(user_id)
        now = datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S')
        async with await self.db.connect() as db:
            async with db.execute(
                """
                SELECT ends_at FROM memberships
                WHERE user_id=? AND perk_code=? AND status='active' AND ends_at > ?
                ORDER BY ends_at DESC
                LIMIT 1
                """,
                (user_id, perk_code, now),
            ) as cur:
                row = await cur.fetchone()
                return str(row['ends_at']) if row else None

    async def activate_membership(
        self,
        user_id: int,
        perk_code: str,
        duration_days: int,
        source: str = 'reward_shop',
        meta: dict[str, Any] | None = None,
    ) -> int:
        now = datetime.now(UTC)
        async with await self.db.connect() as db:
            async with db.execute(
                """
                SELECT * FROM memberships
                WHERE user_id=? AND perk_code=? AND status='active' AND ends_at > ?
                ORDER BY ends_at DESC
                LIMIT 1
                """,
                (user_id, perk_code, now.strftime('%Y-%m-%d %H:%M:%S')),
            ) as cur:
                existing = await cur.fetchone()

            if existing:
                current_end = datetime.strptime(str(existing['ends_at']), '%Y-%m-%d %H:%M:%S').replace(tzinfo=UTC)
                new_end = current_end + timedelta(days=duration_days)
                await db.execute(
                    """
                    UPDATE memberships
                    SET ends_at=?, meta_json=?, updated_at=CURRENT_TIMESTAMP
                    WHERE id=?
                    """,
                    (
                        new_end.strftime('%Y-%m-%d %H:%M:%S'),
                        json.dumps(meta or {}, ensure_ascii=False),
                        int(existing['id']),
                    ),
                )
                membership_id = int(existing['id'])
            else:
                new_end = now + timedelta(days=duration_days)
                cur = await db.execute(
                    """
                    INSERT INTO memberships (user_id, perk_code, status, starts_at, ends_at, source, meta_json)
                    VALUES (?, ?, 'active', ?, ?, ?, ?)
                    """,
                    (
                        user_id,
                        perk_code,
                        now.strftime('%Y-%m-%d %H:%M:%S'),
                        new_end.strftime('%Y-%m-%d %H:%M:%S'),
                        source,
                        json.dumps(meta or {}, ensure_ascii=False),
                    ),
                )
                membership_id = int(cur.lastrowid)

            if perk_code == 'vip':
                await db.execute(
                    "UPDATE users SET tier=?, updated_at=CURRENT_TIMESTAMP WHERE user_id=?",
                    (UserTier.VIP.value, user_id),
                )
            await db.commit()
        await self.sync_user(user_id)
        return membership_id

    async def get_effective_open_claim_limit(self, user_id: int, base_limit: int) -> int:
        perks = await self.get_active_perk_codes(user_id)
        limit = base_limit
        if 'priority' in perks:
            limit += 1
        if 'vip' in perks:
            limit += 2
        return limit

    async def get_hold_minutes(self, user_id: int, base_minutes: int) -> int:
        perks = await self.get_active_perk_codes(user_id)
        multiplier = 1.0
        if 'vip' in perks:
            multiplier = min(multiplier, 0.6)
        if 'fast_hold' in perks:
            multiplier = min(multiplier, 0.5)
        return max(1, int(round(base_minutes * multiplier)))
