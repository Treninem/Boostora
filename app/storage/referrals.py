from __future__ import annotations

import sqlite3
from typing import Any

from app.storage.db import Database


class ReferralRepository:
    def __init__(self, db: Database):
        self.db = db

    async def link_referral(self, inviter_user_id: int, invited_user_id: int) -> bool:
        if inviter_user_id == invited_user_id:
            return False
        async with await self.db.connect() as db:
            try:
                await db.execute(
                    """
                    INSERT INTO referrals (inviter_user_id, invited_user_id)
                    VALUES (?, ?)
                    """,
                    (inviter_user_id, invited_user_id),
                )
                await db.commit()
                return True
            except sqlite3.IntegrityError:
                return False

    async def count_referrals(self, inviter_user_id: int) -> int:
        async with await self.db.connect() as db:
            async with db.execute(
                'SELECT COUNT(*) AS cnt FROM referrals WHERE inviter_user_id=?',
                (inviter_user_id,),
            ) as cur:
                row = await cur.fetchone()
                return int(row['cnt']) if row else 0

    async def get_inviter_for_user(self, invited_user_id: int) -> dict[str, Any] | None:
        async with await self.db.connect() as db:
            async with db.execute(
                'SELECT * FROM referrals WHERE invited_user_id=?',
                (invited_user_id,),
            ) as cur:
                row = await cur.fetchone()
                return dict(row) if row else None

    async def get_referral_rate_for_inviter(self, inviter_user_id: int) -> float:
        async with await self.db.connect() as db:
            async with db.execute(
                """
                SELECT
                    u.tier AS tier,
                    EXISTS(
                        SELECT 1 FROM memberships m
                        WHERE m.user_id = u.user_id
                          AND m.perk_code = 'referral_boost'
                          AND m.status = 'active'
                          AND m.ends_at > CURRENT_TIMESTAMP
                    ) AS has_referral_boost,
                    COALESCE((SELECT MAX(reward_rate) FROM referrals WHERE inviter_user_id = u.user_id), 0.10) AS base_rate
                FROM users u
                WHERE u.user_id=?
                """,
                (inviter_user_id,),
            ) as cur:
                row = await cur.fetchone()
                if not row:
                    return 0.10
                rate = float(row['base_rate'] or 0.10)
                if str(row['tier']) == 'vip':
                    rate = max(rate, 0.12)
                if int(row['has_referral_boost'] or 0):
                    rate += 0.02
                return round(min(rate, 0.14), 4)

    async def get_referral_summary(self, inviter_user_id: int) -> dict[str, Any]:
        rate = await self.get_referral_rate_for_inviter(inviter_user_id)
        async with await self.db.connect() as db:
            async with db.execute(
                """
                SELECT COUNT(*) AS cnt, COALESCE(SUM(earned_total), 0) AS earned_total
                FROM referrals
                WHERE inviter_user_id=?
                """,
                (inviter_user_id,),
            ) as cur:
                row = await cur.fetchone()
                return {
                    'count': int(row['cnt']) if row else 0,
                    'earned_total': int(row['earned_total']) if row else 0,
                    'rate': rate,
                }

    async def add_referral_earnings(self, invited_user_id: int, amount: int) -> tuple[int, int] | None:
        async with await self.db.connect() as db:
            async with db.execute(
                """
                SELECT r.*, u.tier,
                    EXISTS(
                        SELECT 1 FROM memberships m
                        WHERE m.user_id = r.inviter_user_id
                          AND m.perk_code = 'referral_boost'
                          AND m.status = 'active'
                          AND m.ends_at > CURRENT_TIMESTAMP
                    ) AS has_referral_boost
                FROM referrals r
                JOIN users u ON u.user_id = r.inviter_user_id
                WHERE r.invited_user_id=?
                """,
                (invited_user_id,),
            ) as cur:
                row = await cur.fetchone()
                if not row:
                    return None
                inviter_user_id = int(row['inviter_user_id'])
                reward_rate = float(row['reward_rate'])
                if str(row['tier']) == 'vip':
                    reward_rate = max(reward_rate, 0.12)
                if int(row['has_referral_boost'] or 0):
                    reward_rate += 0.02
                reward_rate = min(reward_rate, 0.14)
                reward_amount = int(round(amount * reward_rate))
                if reward_amount <= 0:
                    return None
                await db.execute(
                    'UPDATE referrals SET earned_total = earned_total + ? WHERE invited_user_id=?',
                    (reward_amount, invited_user_id),
                )
                await db.commit()
                return inviter_user_id, reward_amount
