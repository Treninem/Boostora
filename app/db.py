import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator, Sequence, TypeVar

from app.config import settings


SCHEMA = '''
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    last_name TEXT,
    language_code TEXT NOT NULL DEFAULT 'ru',
    role TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    risk_score INTEGER NOT NULL DEFAULT 0,
    referred_by_user_id INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (referred_by_user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS wallets (
    user_id INTEGER PRIMARY KEY,
    available_balance INTEGER NOT NULL DEFAULT 0,
    hold_balance INTEGER NOT NULL DEFAULT 0,
    internal_balance INTEGER NOT NULL DEFAULT 0,
    lifetime_earned INTEGER NOT NULL DEFAULT 0,
    total_withdrawn INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    wallet_user_id INTEGER NOT NULL,
    amount INTEGER NOT NULL,
    currency_code TEXT NOT NULL DEFAULT 'XTR',
    direction TEXT NOT NULL,
    entry_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'completed',
    related_campaign_id INTEGER,
    related_submission_id INTEGER,
    related_hold_id INTEGER,
    note TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (wallet_user_id) REFERENCES wallets(user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS campaigns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_user_id INTEGER NOT NULL,
    title TEXT,
    task_type TEXT NOT NULL,
    target_url TEXT NOT NULL,
    reward_amount INTEGER NOT NULL DEFAULT 0,
    total_quantity INTEGER NOT NULL DEFAULT 0,
    completed_quantity INTEGER NOT NULL DEFAULT 0,
    rejected_quantity INTEGER NOT NULL DEFAULT 0,
    budget_total INTEGER NOT NULL DEFAULT 0,
    budget_reserved INTEGER NOT NULL DEFAULT 0,
    budget_spent INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'draft',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (owner_user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS task_submissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id INTEGER NOT NULL,
    performer_user_id INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'taken',
    target_url TEXT,
    proof_text TEXT,
    proof_payload TEXT,
    reward_amount INTEGER NOT NULL DEFAULT 0,
    risk_score INTEGER NOT NULL DEFAULT 0,
    reject_reason TEXT,
    taken_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    submitted_at TEXT,
    reviewed_at TEXT,
    reviewer_user_id INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (campaign_id) REFERENCES campaigns(id) ON DELETE CASCADE,
    FOREIGN KEY (performer_user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (reviewer_user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS holds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    submission_id INTEGER,
    amount INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    release_at TEXT NOT NULL,
    released_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (submission_id) REFERENCES task_submissions(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS referrals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    referrer_user_id INTEGER NOT NULL,
    referred_user_id INTEGER NOT NULL UNIQUE,
    reward_rate_bps INTEGER NOT NULL DEFAULT 500,
    total_earned INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (referrer_user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (referred_user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS vip_subscriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    tier_code TEXT NOT NULL,
    duration_days INTEGER NOT NULL,
    hold_speed_percent INTEGER NOT NULL DEFAULT 0,
    active_task_limit_bonus INTEGER NOT NULL DEFAULT 0,
    priority_level INTEGER NOT NULL DEFAULT 0,
    referral_rate_bonus_bps INTEGER NOT NULL DEFAULT 0,
    starts_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS admin_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    admin_user_id INTEGER NOT NULL,
    target_user_id INTEGER,
    action TEXT NOT NULL,
    details TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (admin_user_id) REFERENCES users(user_id),
    FOREIGN KEY (target_user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS risk_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    submission_id INTEGER,
    event_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    score_delta INTEGER NOT NULL DEFAULT 0,
    details TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (submission_id) REFERENCES task_submissions(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS ui_sessions (
    user_id INTEGER PRIMARY KEY,
    chat_id INTEGER,
    message_id INTEGER,
    current_screen TEXT,
    screen_version INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS input_sessions (
    user_id INTEGER PRIMARY KEY,
    mode TEXT NOT NULL,
    payload TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS required_chats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_ref TEXT NOT NULL UNIQUE,
    join_link TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS app_meta (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

'''

INDEXES = '''
CREATE INDEX IF NOT EXISTS idx_users_status ON users(status);
CREATE INDEX IF NOT EXISTS idx_users_referred_by ON users(referred_by_user_id);
CREATE INDEX IF NOT EXISTS idx_transactions_user_id ON transactions(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_campaigns_owner_status ON campaigns(owner_user_id, status, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_task_submissions_campaign_status ON task_submissions(campaign_id, status, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_task_submissions_performer_status ON task_submissions(performer_user_id, status, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_holds_user_status_release ON holds(user_id, status, release_at);
CREATE INDEX IF NOT EXISTS idx_referrals_referrer ON referrals(referrer_user_id);
CREATE INDEX IF NOT EXISTS idx_vip_user_active ON vip_subscriptions(user_id, is_active, expires_at DESC);
CREATE INDEX IF NOT EXISTS idx_admin_logs_target ON admin_logs(target_user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_risk_events_user_created ON risk_events(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ui_sessions_chat_message ON ui_sessions(chat_id, message_id);
CREATE INDEX IF NOT EXISTS idx_required_chats_ref ON required_chats(chat_ref);

'''

T = TypeVar('T')


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    db_path = Path(settings.db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA foreign_keys = ON')
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()



def _get_table_columns(connection: sqlite3.Connection, table_name: str) -> set[str]:
    rows = connection.execute(f'PRAGMA table_info({table_name})').fetchall()
    return {str(row['name']) if isinstance(row, sqlite3.Row) else str(row[1]) for row in rows}



def _ensure_column(connection: sqlite3.Connection, table_name: str, column_name: str, definition: str) -> None:
    columns = _get_table_columns(connection, table_name)
    if column_name in columns:
        return
    connection.execute(f'ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}')



def _run_migrations(connection: sqlite3.Connection) -> None:
    _ensure_column(connection, 'users', 'status', "TEXT NOT NULL DEFAULT 'active'")
    _ensure_column(connection, 'users', 'risk_score', 'INTEGER NOT NULL DEFAULT 0')
    _ensure_column(connection, 'users', 'referred_by_user_id', 'INTEGER')



def init_db() -> None:
    with get_connection() as connection:
        connection.executescript(SCHEMA)
        _run_migrations(connection)
        connection.executescript(INDEXES)



def fetch_one(query: str, params: Sequence[Any] = ()) -> sqlite3.Row | None:
    with get_connection() as connection:
        return connection.execute(query, params).fetchone()



def fetch_all(query: str, params: Sequence[Any] = ()) -> list[sqlite3.Row]:
    with get_connection() as connection:
        return connection.execute(query, params).fetchall()



def execute(query: str, params: Sequence[Any] = ()) -> int:
    with get_connection() as connection:
        cursor = connection.execute(query, params)
        return int(cursor.lastrowid or 0)



def execute_many(query: str, params_list: list[Sequence[Any]]) -> None:
    with get_connection() as connection:
        connection.executemany(query, params_list)



def run_in_transaction(callback: Callable[[sqlite3.Connection], T]) -> T:
    with get_connection() as connection:
        return callback(connection)



def get_user(user_id: int) -> sqlite3.Row | None:
    return fetch_one('SELECT * FROM users WHERE user_id = ?', (user_id,))



def upsert_user(
    user_id: int,
    username: str | None,
    first_name: str | None,
    last_name: str | None,
    *,
    referred_by_user_id: int | None = None,
    language_code: str | None = None,
) -> None:
    execute(
        '''
        INSERT INTO users (
            user_id,
            username,
            first_name,
            last_name,
            referred_by_user_id,
            language_code
        )
        VALUES (?, ?, ?, ?, ?, COALESCE(?, 'ru'))
        ON CONFLICT(user_id) DO UPDATE SET
            username = excluded.username,
            first_name = excluded.first_name,
            last_name = excluded.last_name,
            updated_at = CURRENT_TIMESTAMP
        ''',
        (user_id, username, first_name, last_name, referred_by_user_id, language_code),
    )



def set_user_language(user_id: int, language_code: str) -> None:
    execute(
        '''
        UPDATE users
        SET language_code = ?, updated_at = CURRENT_TIMESTAMP
        WHERE user_id = ?
        ''',
        (language_code, user_id),
    )



def set_user_role(user_id: int, role: str) -> None:
    execute(
        '''
        UPDATE users
        SET role = ?, updated_at = CURRENT_TIMESTAMP
        WHERE user_id = ?
        ''',
        (role, user_id),
    )



def ensure_wallet(user_id: int) -> None:
    execute(
        '''
        INSERT INTO wallets (user_id)
        VALUES (?)
        ON CONFLICT(user_id) DO NOTHING
        ''',
        (user_id,),
    )



def get_wallet(user_id: int) -> sqlite3.Row | None:
    return fetch_one('SELECT * FROM wallets WHERE user_id = ?', (user_id,))
