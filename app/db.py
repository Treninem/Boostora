from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from app.i18n import ROLE_EARNER, ROLE_ADVERTISER


class Database:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    locale TEXT DEFAULT 'en',
                    role TEXT,
                    tier TEXT DEFAULT 'new',
                    is_admin INTEGER DEFAULT 0,
                    completed_tasks INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS wallets (
                    user_id INTEGER PRIMARY KEY,
                    available INTEGER DEFAULT 0,
                    hold INTEGER DEFAULT 0,
                    earned_total INTEGER DEFAULT 0,
                    FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS campaigns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    owner_user_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    reward INTEGER NOT NULL DEFAULT 10,
                    target_url TEXT DEFAULT '',
                    total_slots INTEGER NOT NULL DEFAULT 10,
                    completed_slots INTEGER NOT NULL DEFAULT 0,
                    is_demo INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS task_claims (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    campaign_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'taken',
                    reward INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (campaign_id, user_id)
                );
                """
            )
            conn.commit()
            self._seed_demo(conn)

    def _seed_demo(self, conn: sqlite3.Connection) -> None:
        existing = conn.execute("SELECT COUNT(*) AS c FROM campaigns WHERE is_demo=1").fetchone()["c"]
        if existing:
            return
        conn.execute(
            "INSERT OR IGNORE INTO users (user_id, username, first_name, locale, role, tier, is_admin) VALUES (-1, 'boostora', 'Boostora', 'en', ?, 'verified', 1)",
            (ROLE_ADVERTISER,),
        )
        conn.execute("INSERT OR IGNORE INTO wallets (user_id) VALUES (-1)")
        demo_rows = [
            (-1, "Telegram channel subscription", 25, "https://t.me/BoostoraBot", 30, 0, 1),
            (-1, "Open Telegram bot", 20, "https://t.me/BoostoraBot", 30, 0, 1),
            (-1, "View partner post", 15, "https://t.me/BoostoraBot", 30, 0, 1),
        ]
        conn.executemany(
            "INSERT INTO campaigns (owner_user_id, title, reward, target_url, total_slots, completed_slots, is_demo) VALUES (?, ?, ?, ?, ?, ?, ?)",
            demo_rows,
        )
        conn.commit()

    def upsert_user(self, user_id: int, username: str | None, first_name: str | None, is_admin: bool) -> None:
        with self.connect() as conn:
            conn.execute(
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
            conn.execute("INSERT OR IGNORE INTO wallets (user_id) VALUES (?)", (user_id,))
            conn.commit()

    def get_user(self, user_id: int) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()

    def set_locale(self, user_id: int, locale: str) -> None:
        with self.connect() as conn:
            conn.execute("UPDATE users SET locale=?, updated_at=CURRENT_TIMESTAMP WHERE user_id=?", (locale, user_id))
            conn.commit()

    def set_role(self, user_id: int, role: str) -> None:
        with self.connect() as conn:
            conn.execute("UPDATE users SET role=?, updated_at=CURRENT_TIMESTAMP WHERE user_id=?", (role, user_id))
            conn.commit()

    def get_wallet(self, user_id: int) -> sqlite3.Row:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM wallets WHERE user_id=?", (user_id,)).fetchone()
            if row is None:
                conn.execute("INSERT INTO wallets (user_id) VALUES (?)", (user_id,))
                conn.commit()
                row = conn.execute("SELECT * FROM wallets WHERE user_id=?", (user_id,)).fetchone()
            return row

    def topup_wallet(self, user_id: int, amount: int) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE wallets SET available=available+? WHERE user_id=?",
                (amount, user_id),
            )
            conn.commit()

    def add_reward(self, user_id: int, amount: int) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE wallets SET available=available+?, earned_total=earned_total+? WHERE user_id=?",
                (amount, amount, user_id),
            )
            conn.commit()

    def increment_completed_tasks(self, user_id: int) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE users SET completed_tasks=completed_tasks+1, tier=CASE WHEN completed_tasks+1 >= 10 THEN 'verified' ELSE tier END, updated_at=CURRENT_TIMESTAMP WHERE user_id=?",
                (user_id,),
            )
            conn.commit()

    def list_available_tasks(self) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT c.*
                FROM campaigns c
                WHERE c.completed_slots < c.total_slots
                ORDER BY c.is_demo DESC, c.id DESC
                """
            ).fetchall()

    def get_campaign(self, campaign_id: int) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute("SELECT * FROM campaigns WHERE id=?", (campaign_id,)).fetchone()

    def take_task(self, campaign_id: int, user_id: int) -> bool:
        with self.connect() as conn:
            existing = conn.execute(
                "SELECT id FROM task_claims WHERE campaign_id=? AND user_id=?",
                (campaign_id, user_id),
            ).fetchone()
            if existing:
                return False
            campaign = conn.execute(
                "SELECT * FROM campaigns WHERE id=? AND completed_slots < total_slots",
                (campaign_id,),
            ).fetchone()
            if campaign is None:
                return False
            conn.execute(
                "INSERT INTO task_claims (campaign_id, user_id, reward) VALUES (?, ?, ?)",
                (campaign_id, user_id, int(campaign["reward"])),
            )
            conn.commit()
            return True

    def complete_task(self, campaign_id: int, user_id: int) -> bool:
        with self.connect() as conn:
            claim = conn.execute(
                "SELECT * FROM task_claims WHERE campaign_id=? AND user_id=? AND status='taken'",
                (campaign_id, user_id),
            ).fetchone()
            if claim is None:
                return False
            conn.execute(
                "UPDATE task_claims SET status='completed' WHERE id=?",
                (claim["id"],),
            )
            conn.execute(
                "UPDATE campaigns SET completed_slots=MIN(total_slots, completed_slots+1) WHERE id=?",
                (campaign_id,),
            )
            conn.execute(
                "UPDATE wallets SET available=available+?, earned_total=earned_total+? WHERE user_id=?",
                (claim["reward"], claim["reward"], user_id),
            )
            conn.execute(
                "UPDATE users SET completed_tasks=completed_tasks+1, tier=CASE WHEN completed_tasks+1 >= 10 THEN 'verified' ELSE tier END, updated_at=CURRENT_TIMESTAMP WHERE user_id=?",
                (user_id,),
            )
            conn.commit()
            return True

    def user_claimed_ids(self, user_id: int) -> set[int]:
        with self.connect() as conn:
            rows = conn.execute("SELECT campaign_id FROM task_claims WHERE user_id=?", (user_id,)).fetchall()
            return {int(r["campaign_id"]) for r in rows}

    def list_user_campaigns(self, owner_user_id: int) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                "SELECT * FROM campaigns WHERE owner_user_id=? ORDER BY id DESC",
                (owner_user_id,),
            ).fetchall()

    def create_demo_campaign_for_user(self, owner_user_id: int) -> None:
        with self.connect() as conn:
            index = conn.execute(
                "SELECT COUNT(*) AS c FROM campaigns WHERE owner_user_id=?",
                (owner_user_id,),
            ).fetchone()["c"]
            conn.execute(
                "INSERT INTO campaigns (owner_user_id, title, reward, target_url, total_slots, completed_slots, is_demo) VALUES (?, ?, ?, ?, ?, 0, 0)",
                (owner_user_id, f"Boostora campaign #{index + 1}", 30, "https://t.me/BoostoraBot", 25),
            )
            conn.commit()

    def advertiser_stats(self, owner_user_id: int) -> dict[str, int]:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS campaigns, COALESCE(SUM(total_slots),0) AS tasks, COALESCE(SUM(completed_slots),0) AS completed FROM campaigns WHERE owner_user_id=?",
                (owner_user_id,),
            ).fetchone()
            return {"campaigns": int(row["campaigns"]), "tasks": int(row["tasks"]), "completed": int(row["completed"])}

    def admin_stats(self) -> dict[str, int]:
        with self.connect() as conn:
            users = conn.execute("SELECT COUNT(*) AS c FROM users WHERE user_id != -1").fetchone()["c"]
            campaigns = conn.execute("SELECT COUNT(*) AS c FROM campaigns").fetchone()["c"]
            claims = conn.execute("SELECT COUNT(*) AS c FROM task_claims").fetchone()["c"]
            return {"users": int(users), "campaigns": int(campaigns), "claims": int(claims)}
