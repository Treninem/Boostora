from __future__ import annotations

from typing import Any

from app.core.enums import CampaignStatus, TaskType
from app.storage.db import Database


class CampaignRepository:
    def __init__(self, db: Database):
        self.db = db

    async def create_draft(
        self,
        owner_user_id: int,
        title: str,
        task_type: str = TaskType.CHANNEL_JOIN.value,
        locale: str = 'en',
    ) -> int:
        async with await self.db.connect() as db:
            cur = await db.execute(
                """
                INSERT INTO campaigns (owner_user_id, title, task_type, locale)
                VALUES (?, ?, ?, ?)
                """,
                (owner_user_id, title, task_type, locale),
            )
            await db.commit()
            return int(cur.lastrowid)

    async def create_configured_draft(
        self,
        owner_user_id: int,
        title: str,
        task_type: str,
        target_url: str,
        target_count: int,
        reward_per_task: int,
        budget_total: int,
        locale: str = 'en',
    ) -> int:
        async with await self.db.connect() as db:
            cur = await db.execute(
                """
                INSERT INTO campaigns (
                    owner_user_id, title, task_type, target_url,
                    target_count, reward_per_task, budget_total,
                    budget_reserved, status, locale
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    owner_user_id,
                    title,
                    task_type,
                    target_url,
                    target_count,
                    reward_per_task,
                    budget_total,
                    budget_total,
                    CampaignStatus.DRAFT.value,
                    locale,
                ),
            )
            await db.commit()
            return int(cur.lastrowid)

    async def get_campaign(self, campaign_id: int) -> dict[str, Any] | None:
        async with await self.db.connect() as db:
            async with db.execute('SELECT * FROM campaigns WHERE id=?', (campaign_id,)) as cur:
                row = await cur.fetchone()
                return dict(row) if row else None

    async def get_campaign_for_owner(self, campaign_id: int, owner_user_id: int) -> dict[str, Any] | None:
        async with await self.db.connect() as db:
            async with db.execute(
                'SELECT * FROM campaigns WHERE id=? AND owner_user_id=?',
                (campaign_id, owner_user_id),
            ) as cur:
                row = await cur.fetchone()
                return dict(row) if row else None

    async def list_user_campaigns(self, owner_user_id: int, limit: int = 10) -> list[dict[str, Any]]:
        async with await self.db.connect() as db:
            async with db.execute(
                """
                SELECT * FROM campaigns
                WHERE owner_user_id=?
                ORDER BY id DESC
                LIMIT ?
                """,
                (owner_user_id, limit),
            ) as cur:
                rows = await cur.fetchall()
                return [dict(row) for row in rows]

    async def list_active_campaigns(self, limit: int = 10) -> list[dict[str, Any]]:
        async with await self.db.connect() as db:
            async with db.execute(
                """
                SELECT *, (target_count - completed_count) AS slots_left
                FROM campaigns
                WHERE status=? AND completed_count < target_count
                ORDER BY reward_per_task DESC, id ASC
                LIMIT ?
                """,
                (CampaignStatus.ACTIVE.value, limit),
            ) as cur:
                rows = await cur.fetchall()
                return [dict(row) for row in rows]

    async def list_available_campaigns_for_user(self, user_id: int, limit: int = 10) -> list[dict[str, Any]]:
        async with await self.db.connect() as db:
            async with db.execute(
                """
                SELECT c.*, (c.target_count - c.completed_count) AS slots_left
                FROM campaigns c
                WHERE c.status=?
                  AND c.completed_count < c.target_count
                  AND c.owner_user_id != ?
                  AND NOT EXISTS (
                      SELECT 1
                      FROM task_claims tc
                      WHERE tc.campaign_id = c.id
                        AND tc.user_id = ?
                        AND tc.claim_status IN ('taken', 'submitted', 'verified')
                  )
                ORDER BY c.reward_per_task DESC, c.id ASC
                LIMIT ?
                """,
                (CampaignStatus.ACTIVE.value, user_id, user_id, limit),
            ) as cur:
                rows = await cur.fetchall()
                return [dict(row) for row in rows]

    async def update_campaign_basics(
        self,
        campaign_id: int,
        target_url: str,
        target_count: int,
        reward_per_task: int,
        budget_total: int,
    ) -> None:
        async with await self.db.connect() as db:
            await db.execute(
                """
                UPDATE campaigns
                SET target_url=?,
                    target_count=?,
                    reward_per_task=?,
                    budget_total=?,
                    budget_reserved=?,
                    updated_at=CURRENT_TIMESTAMP
                WHERE id=?
                """,
                (target_url, target_count, reward_per_task, budget_total, budget_total, campaign_id),
            )
            await db.commit()

    async def set_status(self, campaign_id: int, status: str) -> None:
        async with await self.db.connect() as db:
            await db.execute(
                'UPDATE campaigns SET status=?, updated_at=CURRENT_TIMESTAMP WHERE id=?',
                (status, campaign_id),
            )
            await db.commit()

    async def register_completion(self, campaign_id: int) -> bool:
        async with await self.db.connect() as db:
            cur = await db.execute(
                """
                UPDATE campaigns
                SET completed_count = completed_count + 1,
                    updated_at=CURRENT_TIMESTAMP
                WHERE id=? AND status=? AND completed_count < target_count
                """,
                (campaign_id, CampaignStatus.ACTIVE.value),
            )
            if cur.rowcount <= 0:
                await db.rollback()
                return False
            await db.execute(
                """
                UPDATE campaigns
                SET status=?
                WHERE id=? AND completed_count >= target_count AND status=?
                """,
                (CampaignStatus.COMPLETED.value, campaign_id, CampaignStatus.ACTIVE.value),
            )
            await db.commit()
            return True

    async def seed_demo_campaigns(self, owner_user_id: int, locale: str) -> None:
        existing = await self.list_user_campaigns(owner_user_id, limit=1)
        if existing:
            return
        examples = [
            ('launch_channel_boost', TaskType.CHANNEL_JOIN.value, 'https://t.me/your_channel_here', 100, 25, 2500),
            ('bot_start_wave', TaskType.BOT_START.value, 'https://t.me/your_bot_here?start=promo', 80, 18, 1440),
        ]
        async with await self.db.connect() as db:
            for title, task_type, target_url, target_count, reward_per_task, budget_total in examples:
                await db.execute(
                    """
                    INSERT INTO campaigns (
                        owner_user_id, title, task_type, target_url, target_count,
                        reward_per_task, budget_total, budget_reserved, status, locale
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        owner_user_id,
                        title,
                        task_type,
                        target_url,
                        target_count,
                        reward_per_task,
                        budget_total,
                        budget_total,
                        CampaignStatus.DRAFT.value,
                        locale,
                    ),
                )
            await db.commit()
