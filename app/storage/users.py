from __future__ import annotations

from typing import Any

from app.core.enums import UserRole, UserTier
from app.storage.db import Database


class UserRepository:
    def __init__(self, db: Database):
        self.db = db

    async def upsert_user(
        self,
        user_id: int,
        username: str | None,
        first_name: str | None,
        is_admin: bool = False,
    ) -> None:
        async with await self.db.connect() as db:
            await db.execute(
                """
                INSERT INTO users (user_id, username, first_name, is_admin)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    username=excluded.username,
                    first_name=excluded.first_name,
                    is_admin=excluded.is_admin,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (user_id, username, first_name, int(is_admin)),
            )
            await db.execute(
                """
                INSERT INTO wallets (user_id)
                VALUES (?)
                ON CONFLICT(user_id) DO NOTHING
                """,
                (user_id,),
            )
            await db.commit()

    async def set_locale(self, user_id: int, locale: str) -> None:
        async with await self.db.connect() as db:
            await db.execute(
                'UPDATE users SET locale=?, updated_at=CURRENT_TIMESTAMP WHERE user_id=?',
                (locale, user_id),
            )
            await db.commit()

    async def set_role(self, user_id: int, role: str) -> None:
        async with await self.db.connect() as db:
            await db.execute(
                'UPDATE users SET role=?, updated_at=CURRENT_TIMESTAMP WHERE user_id=?',
                (role, user_id),
            )
            await db.commit()

    async def set_tier(self, user_id: int, tier: str) -> None:
        async with await self.db.connect() as db:
            await db.execute(
                'UPDATE users SET tier=?, updated_at=CURRENT_TIMESTAMP WHERE user_id=?',
                (tier, user_id),
            )
            await db.commit()

    async def promote_tier_if_needed(self, user_id: int) -> None:
        user = await self.get_user(user_id)
        if not user:
            return
        completed = int(user.get('completed_tasks', 0) or 0)
        desired = UserTier.NEW.value
        if completed >= 10:
            desired = UserTier.VERIFIED.value
        if user.get('tier') != desired and user.get('tier') != UserTier.VIP.value:
            await self.set_tier(user_id, desired)

    async def increment_completed_tasks(self, user_id: int, amount: int = 1) -> None:
        async with await self.db.connect() as db:
            await db.execute(
                'UPDATE users SET completed_tasks = completed_tasks + ?, updated_at=CURRENT_TIMESTAMP WHERE user_id=?',
                (amount, user_id),
            )
            await db.commit()
        await self.promote_tier_if_needed(user_id)
        await self.refresh_risk_score(user_id)

    async def increment_canceled_tasks(self, user_id: int, amount: int = 1) -> None:
        async with await self.db.connect() as db:
            await db.execute(
                'UPDATE users SET canceled_tasks = canceled_tasks + ?, updated_at=CURRENT_TIMESTAMP WHERE user_id=?',
                (amount, user_id),
            )
            await db.commit()
        await self.refresh_risk_score(user_id)

    async def increment_referrals(self, user_id: int, amount: int = 1) -> None:
        async with await self.db.connect() as db:
            await db.execute(
                'UPDATE users SET referral_count = referral_count + ?, updated_at=CURRENT_TIMESTAMP WHERE user_id=?',
                (amount, user_id),
            )
            await db.commit()

    async def refresh_risk_score(self, user_id: int) -> None:
        user = await self.get_user(user_id)
        if not user:
            return
        completed = int(user.get('completed_tasks', 0) or 0)
        canceled = int(user.get('canceled_tasks', 0) or 0)
        total = max(completed + canceled, 1)
        cancellation_ratio = canceled / total
        inactivity_penalty = 15.0 if completed == 0 else 0.0
        risk_score = round(min(100.0, cancellation_ratio * 100 + inactivity_penalty), 1)
        async with await self.db.connect() as db:
            await db.execute(
                'UPDATE users SET risk_score=?, updated_at=CURRENT_TIMESTAMP WHERE user_id=?',
                (risk_score, user_id),
            )
            await db.commit()

    async def get_user(self, user_id: int) -> dict[str, Any] | None:
        async with await self.db.connect() as db:
            async with db.execute('SELECT * FROM users WHERE user_id=?', (user_id,)) as cur:
                row = await cur.fetchone()
                return dict(row) if row else None

    async def get_user_role(self, user_id: int) -> str | None:
        user = await self.get_user(user_id)
        return (user or {}).get('role')

    async def ensure_default_role(self, user_id: int) -> str:
        user = await self.get_user(user_id)
        role = (user or {}).get('role')
        if role in {UserRole.EARNER.value, UserRole.ADVERTISER.value}:
            return str(role)
        await self.set_role(user_id, UserRole.EARNER.value)
        return UserRole.EARNER.value
