from __future__ import annotations

from pathlib import Path

import aiosqlite

from app.core.enums import CampaignStatus, HoldStatus, TaskType, UserRole, UserTier


class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path

    async def connect(self) -> aiosqlite.Connection:
        conn = await aiosqlite.connect(self.db_path)
        conn.row_factory = aiosqlite.Row
        await conn.execute('PRAGMA foreign_keys = ON')
        return conn

    async def init(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        async with await self.connect() as db:
            await db.executescript(
                f"""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    locale TEXT DEFAULT 'en',
                    role TEXT,
                    tier TEXT NOT NULL DEFAULT '{UserTier.NEW.value}',
                    is_admin INTEGER DEFAULT 0,
                    is_blocked INTEGER DEFAULT 0,
                    risk_score REAL DEFAULT 0,
                    completed_tasks INTEGER DEFAULT 0,
                    canceled_tasks INTEGER DEFAULT 0,
                    referral_count INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS wallets (
                    user_id INTEGER PRIMARY KEY,
                    available_balance INTEGER NOT NULL DEFAULT 0,
                    hold_balance INTEGER NOT NULL DEFAULT 0,
                    spent_balance INTEGER NOT NULL DEFAULT 0,
                    earned_total INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS wallet_ledger (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    entry_type TEXT NOT NULL,
                    amount INTEGER NOT NULL,
                    balance_after INTEGER,
                    hold_after INTEGER,
                    description TEXT,
                    meta_json TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS reward_holds (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    source_type TEXT NOT NULL,
                    source_id INTEGER,
                    amount INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT '{HoldStatus.PENDING.value}',
                    release_at TEXT,
                    reason TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS campaigns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    owner_user_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    task_type TEXT NOT NULL,
                    target_url TEXT,
                    target_count INTEGER NOT NULL DEFAULT 0,
                    completed_count INTEGER NOT NULL DEFAULT 0,
                    reward_per_task INTEGER NOT NULL DEFAULT 0,
                    budget_total INTEGER NOT NULL DEFAULT 0,
                    budget_reserved INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT '{CampaignStatus.DRAFT.value}',
                    locale TEXT DEFAULT 'en',
                    notes TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(owner_user_id) REFERENCES users(user_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS task_claims (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    campaign_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    claim_status TEXT NOT NULL,
                    proof_json TEXT,
                    reward_amount INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(campaign_id) REFERENCES campaigns(id) ON DELETE CASCADE,
                    FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_task_claims_user_status ON task_claims(user_id, claim_status);

                CREATE TABLE IF NOT EXISTS referrals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    inviter_user_id INTEGER NOT NULL,
                    invited_user_id INTEGER NOT NULL UNIQUE,
                    reward_rate REAL NOT NULL DEFAULT 0.10,
                    earned_total INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(inviter_user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                    FOREIGN KEY(invited_user_id) REFERENCES users(user_id) ON DELETE CASCADE
                );


                CREATE TABLE IF NOT EXISTS memberships (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    perk_code TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    starts_at TEXT NOT NULL,
                    ends_at TEXT NOT NULL,
                    source TEXT,
                    meta_json TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_memberships_user_perk_status ON memberships(user_id, perk_code, status, ends_at);

                CREATE TABLE IF NOT EXISTS reward_redemptions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    item_code TEXT NOT NULL,
                    cost INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'completed',
                    details_json TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_reward_redemptions_user_created ON reward_redemptions(user_id, created_at DESC);


                CREATE TABLE IF NOT EXISTS billing_orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    purpose TEXT NOT NULL,
                    payload TEXT NOT NULL UNIQUE,
                    amount_xtr INTEGER NOT NULL,
                    credit_amount INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'created',
                    telegram_charge_id TEXT,
                    provider_charge_id TEXT,
                    details_json TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_billing_orders_user_created ON billing_orders(user_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_billing_orders_status ON billing_orders(status, purpose);

                CREATE TABLE IF NOT EXISTS admin_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    admin_user_id INTEGER NOT NULL,
                    target_user_id INTEGER,
                    action TEXT NOT NULL,
                    reason TEXT,
                    meta_json TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(admin_user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                    FOREIGN KEY(target_user_id) REFERENCES users(user_id) ON DELETE SET NULL
                );

                CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);
                CREATE INDEX IF NOT EXISTS idx_campaigns_owner_status ON campaigns(owner_user_id, status);
                CREATE INDEX IF NOT EXISTS idx_task_claims_campaign_user ON task_claims(campaign_id, user_id);
                CREATE INDEX IF NOT EXISTS idx_reward_holds_user_status ON reward_holds(user_id, status);
                CREATE INDEX IF NOT EXISTS idx_wallet_ledger_user_created ON wallet_ledger(user_id, created_at DESC);
                """
            )
            await self._seed_system(db)
            await self._seed_demo_campaigns(db)
            await db.commit()

    async def _seed_system(self, db: aiosqlite.Connection) -> None:
        await db.execute(
            """
            INSERT INTO users (user_id, username, first_name, locale, role, tier, is_admin)
            VALUES (-1, 'boostora_system', 'Boostora', 'en', ?, ?, 1)
            ON CONFLICT(user_id) DO NOTHING
            """,
            (UserRole.ADVERTISER.value, UserTier.VIP.value),
        )
        await db.execute(
            """
            INSERT INTO wallets (user_id)
            VALUES (-1)
            ON CONFLICT(user_id) DO NOTHING
            """
        )

    async def _seed_demo_campaigns(self, db: aiosqlite.Connection) -> None:
        async with db.execute('SELECT COUNT(*) AS cnt FROM campaigns WHERE owner_user_id=-1') as cur:
            row = await cur.fetchone()
            if row and int(row['cnt']) > 0:
                return

        campaigns = [
            ('system_channel_join', TaskType.CHANNEL_JOIN.value, 'https://t.me/boostora_demo_channel', 800, 14, 11200),
            ('system_post_view', TaskType.POST_VIEW.value, 'https://t.me/boostora_demo_channel/1', 900, 9, 8100),
            ('system_bot_start', TaskType.BOT_START.value, 'https://t.me/boostora_demo_bot?start=boost', 700, 17, 11900),
            ('system_mini_app', TaskType.MINI_APP_OPEN.value, 'https://t.me/boostora_demo_bot/app', 500, 22, 11000),
        ]
        for title, task_type, target_url, target_count, reward, budget_total in campaigns:
            await db.execute(
                """
                INSERT INTO campaigns (
                    owner_user_id, title, task_type, target_url, target_count,
                    reward_per_task, budget_total, budget_reserved, status, locale, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    -1,
                    title,
                    task_type,
                    target_url,
                    target_count,
                    reward,
                    budget_total,
                    budget_total,
                    CampaignStatus.ACTIVE.value,
                    'en',
                    'system_demo',
                ),
            )
