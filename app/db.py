import os
import shutil
import sqlite3
import threading
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterator, Sequence, TypeVar

from app.time_utils import utcnow
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
    chat_gate_started_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (referred_by_user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS wallets (
    user_id INTEGER PRIMARY KEY,
    available_balance INTEGER NOT NULL DEFAULT 0,
    hold_balance INTEGER NOT NULL DEFAULT 0,
    internal_balance INTEGER NOT NULL DEFAULT 0,
    bonus_balance INTEGER NOT NULL DEFAULT 0,
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
    unit_price INTEGER NOT NULL DEFAULT 0,
    reward_budget_total INTEGER NOT NULL DEFAULT 0,
    service_fee_total INTEGER NOT NULL DEFAULT 0,
    pricing_json TEXT,
    auto_verify_enabled INTEGER NOT NULL DEFAULT 0,
    verification_json TEXT,
    retention_hours INTEGER NOT NULL DEFAULT 0,
    target_chat_ref TEXT,
    target_message_id INTEGER,
    is_funded INTEGER NOT NULL DEFAULT 0,
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
    verification_state TEXT NOT NULL DEFAULT 'pending',
    verification_attempts INTEGER NOT NULL DEFAULT 0,
    last_verification_at TEXT,
    verification_note TEXT,
    retention_check_at TEXT,
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
    currency_code TEXT NOT NULL DEFAULT 'XTR',
    status TEXT NOT NULL DEFAULT 'active',
    verification_required INTEGER NOT NULL DEFAULT 0,
    verification_status TEXT NOT NULL DEFAULT 'not_required',
    verification_due_at TEXT,
    verification_checked_at TEXT,
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

CREATE TABLE IF NOT EXISTS chat_start_gate_notices (
    chat_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    warning_message_id INTEGER NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (chat_id, user_id)
);

CREATE TABLE IF NOT EXISTS app_meta (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS redemptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    kind TEXT NOT NULL,
    reference TEXT,
    stars_cost INTEGER NOT NULL DEFAULT 0,
    sparks_cost INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pending',
    note TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS invoice_messages (
    user_id INTEGER PRIMARY KEY,
    chat_id INTEGER NOT NULL,
    invoice_message_id INTEGER NOT NULL,
    helper_message_id INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);


CREATE TABLE IF NOT EXISTS observed_messages (
    chat_ref TEXT NOT NULL,
    chat_id INTEGER NOT NULL,
    message_id INTEGER NOT NULL,
    message_kind TEXT NOT NULL DEFAULT 'message',
    poll_id TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (chat_id, message_id)
);

CREATE TABLE IF NOT EXISTS activity_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    activity_type TEXT NOT NULL,
    chat_ref TEXT,
    chat_id INTEGER,
    message_id INTEGER,
    parent_message_id INTEGER,
    poll_id TEXT,
    target_value TEXT,
    payload_json TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);




CREATE TABLE IF NOT EXISTS ad_broadcasts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    creator_user_id INTEGER NOT NULL,
    ad_text TEXT NOT NULL,
    target_url TEXT NOT NULL,
    schedule_code TEXT NOT NULL,
    interval_hours INTEGER NOT NULL DEFAULT 0,
    repeats_total INTEGER NOT NULL DEFAULT 1,
    sent_runs INTEGER NOT NULL DEFAULT 0,
    next_run_at TEXT,
    last_run_at TEXT,
    stars_price INTEGER NOT NULL DEFAULT 0,
    credit_price INTEGER NOT NULL DEFAULT 0,
    bonus_used INTEGER NOT NULL DEFAULT 0,
    pay_required INTEGER NOT NULL DEFAULT 1,
    expires_at TEXT,
    is_admin INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'draft',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (creator_user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS bot_chats (
    chat_id INTEGER PRIMARY KEY,
    chat_ref TEXT NOT NULL,
    title TEXT,
    chat_type TEXT NOT NULL DEFAULT 'group',
    username TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    can_post INTEGER NOT NULL DEFAULT 1,
    can_invite_users INTEGER NOT NULL DEFAULT 0,
    owner_user_id INTEGER,
    network_enabled INTEGER NOT NULL DEFAULT 1,
    network_status TEXT NOT NULL DEFAULT 'pending',
    member_count INTEGER NOT NULL DEFAULT 0,
    daily_limit INTEGER NOT NULL DEFAULT 1,
    window_start TEXT NOT NULL DEFAULT '09:00',
    window_end TEXT NOT NULL DEFAULT '22:00',
    min_interval_hours INTEGER NOT NULL DEFAULT 6,
    timezone_offset_minutes INTEGER NOT NULL DEFAULT 0,
    topic_code TEXT NOT NULL DEFAULT 'general',
    language_code TEXT NOT NULL DEFAULT 'ru',
    quality_score INTEGER NOT NULL DEFAULT 50,
    observed_active_users INTEGER NOT NULL DEFAULT 0,
    observed_activity_events INTEGER NOT NULL DEFAULT 0,
    last_activity_at TEXT,
    verified_at TEXT,
    disabled_reason TEXT,
    last_seen_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);


CREATE TABLE IF NOT EXISTS admin_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    admin_user_id INTEGER NOT NULL,
    target_user_id INTEGER NOT NULL,
    related_submission_id INTEGER,
    note_type TEXT NOT NULL DEFAULT 'fraud_note',
    note TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (admin_user_id) REFERENCES users(user_id),
    FOREIGN KEY (target_user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (related_submission_id) REFERENCES task_submissions(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS provider_services (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider_code TEXT NOT NULL DEFAULT 'boostore',
    external_service_id TEXT NOT NULL,
    name TEXT NOT NULL,
    category TEXT,
    service_type TEXT,
    rate_text TEXT,
    rate_value REAL NOT NULL DEFAULT 0,
    min_quantity INTEGER NOT NULL DEFAULT 0,
    max_quantity INTEGER NOT NULL DEFAULT 0,
    refill_enabled INTEGER NOT NULL DEFAULT 0,
    cancel_enabled INTEGER NOT NULL DEFAULT 0,
    is_enabled INTEGER NOT NULL DEFAULT 0,
    markup_percent INTEGER NOT NULL DEFAULT 35,
    raw_json TEXT,
    last_synced_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(provider_code, external_service_id)
);

CREATE TABLE IF NOT EXISTS provider_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider_code TEXT NOT NULL DEFAULT 'boostore',
    owner_user_id INTEGER,
    campaign_id INTEGER,
    external_order_id TEXT,
    external_service_id TEXT,
    link TEXT,
    quantity INTEGER NOT NULL DEFAULT 0,
    charge_text TEXT,
    charge_value REAL NOT NULL DEFAULT 0,
    currency TEXT,
    provider_status TEXT NOT NULL DEFAULT 'draft',
    last_payload_json TEXT,
    last_checked_at TEXT,
    paid_at TEXT,
    placed_at TEXT,
    telegram_payment_charge_id TEXT,
    provider_payment_charge_id TEXT,
    last_error TEXT,
    credit_cost INTEGER NOT NULL DEFAULT 0,
    bonus_used INTEGER NOT NULL DEFAULT 0,
    rate_value_snapshot REAL NOT NULL DEFAULT 0,
    markup_percent_snapshot INTEGER NOT NULL DEFAULT 0,
    price_checked_at TEXT,
    expires_at TEXT,
    refunded_credits INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (owner_user_id) REFERENCES users(user_id) ON DELETE SET NULL,
    FOREIGN KEY (campaign_id) REFERENCES campaigns(id) ON DELETE SET NULL
);


CREATE TABLE IF NOT EXISTS community_rule_acceptances (
    user_id INTEGER NOT NULL,
    rules_version TEXT NOT NULL,
    accepted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    source TEXT NOT NULL DEFAULT 'bot',
    PRIMARY KEY (user_id, rules_version),
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);


CREATE TABLE IF NOT EXISTS engagement_memberships (
    user_id INTEGER PRIMARY KEY,
    mode TEXT NOT NULL DEFAULT 'standard',
    status TEXT NOT NULL DEFAULT 'active',
    pro_expires_at TEXT,
    reciprocal_required_actions INTEGER NOT NULL DEFAULT 10,
    selected_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    source TEXT NOT NULL DEFAULT 'bot',
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS engagement_obligations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    campaign_id INTEGER,
    task_type TEXT NOT NULL,
    required_actions INTEGER NOT NULL DEFAULT 10,
    status TEXT NOT NULL DEFAULT 'open',
    due_at TEXT,
    reminder_sent_at TEXT,
    warning_sent_at TEXT,
    admin_warning_sent_at TEXT,
    forgiven_at TEXT,
    forgiven_by_user_id INTEGER,
    extended_at TEXT,
    extended_by_user_id INTEGER,
    last_manual_warning_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (campaign_id) REFERENCES campaigns(id) ON DELETE SET NULL
);


CREATE TABLE IF NOT EXISTS engagement_admin_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    admin_user_id INTEGER NOT NULL,
    target_user_id INTEGER,
    obligation_id INTEGER,
    action TEXT NOT NULL,
    details TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (admin_user_id) REFERENCES users(user_id),
    FOREIGN KEY (target_user_id) REFERENCES users(user_id) ON DELETE SET NULL,
    FOREIGN KEY (obligation_id) REFERENCES engagement_obligations(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS legal_doc_acceptances (
    user_id INTEGER NOT NULL,
    legal_version TEXT NOT NULL,
    accepted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    source TEXT NOT NULL DEFAULT 'bot',
    PRIMARY KEY (user_id, legal_version),
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS platform_agreement_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    agreement_version TEXT NOT NULL,
    action TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'bot',
    details TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS network_campaigns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_user_id INTEGER NOT NULL,
    title TEXT,
    ad_text TEXT NOT NULL,
    target_url TEXT NOT NULL,
    target_chat_id INTEGER,
    topic_code TEXT NOT NULL DEFAULT 'general',
    language_code TEXT NOT NULL DEFAULT 'ru',
    budget_credits INTEGER NOT NULL,
    bonus_used INTEGER NOT NULL DEFAULT 0,
    paid_credits INTEGER NOT NULL DEFAULT 0,
    predicted_reach_min INTEGER NOT NULL DEFAULT 0,
    predicted_reach_max INTEGER NOT NULL DEFAULT 0,
    predicted_subscribers_min INTEGER NOT NULL DEFAULT 0,
    predicted_subscribers_max INTEGER NOT NULL DEFAULT 0,
    contribution_units_required REAL NOT NULL DEFAULT 0,
    contribution_units_completed REAL NOT NULL DEFAULT 0,
    refunded_credits INTEGER NOT NULL DEFAULT 0,
    refunded_bonus INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'awaiting_contribution',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (owner_user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS network_placements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id INTEGER NOT NULL,
    host_chat_id INTEGER NOT NULL,
    host_owner_user_id INTEGER,
    placement_cost_credits INTEGER NOT NULL DEFAULT 0,
    network_units REAL NOT NULL DEFAULT 1,
    score REAL NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'locked',
    scheduled_at TEXT,
    published_at TEXT,
    expires_at TEXT,
    message_id INTEGER,
    tracking_token TEXT,
    invite_link TEXT,
    clicks INTEGER NOT NULL DEFAULT 0,
    joins INTEGER NOT NULL DEFAULT 0,
    retained_24h INTEGER NOT NULL DEFAULT 0,
    retained_7d INTEGER NOT NULL DEFAULT 0,
    reciprocal_placement_id INTEGER,
    contribution_reserved REAL NOT NULL DEFAULT 0,
    completed_at TEXT,
    revoked_at TEXT,
    refunded_credits INTEGER NOT NULL DEFAULT 0,
    refunded_bonus INTEGER NOT NULL DEFAULT 0,
    refunded_at TEXT,
    last_error TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (campaign_id) REFERENCES network_campaigns(id) ON DELETE CASCADE,
    FOREIGN KEY (host_chat_id) REFERENCES bot_chats(chat_id) ON DELETE CASCADE,
    FOREIGN KEY (host_owner_user_id) REFERENCES users(user_id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS network_bonus_ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    placement_id INTEGER,
    amount INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'earned',
    reason TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (placement_id) REFERENCES network_placements(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS network_join_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    placement_id INTEGER NOT NULL,
    campaign_id INTEGER NOT NULL,
    target_chat_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    joined_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    retained_24h INTEGER NOT NULL DEFAULT 0,
    retained_7d INTEGER NOT NULL DEFAULT 0,
    checked_24h_at TEXT,
    checked_7d_at TEXT,
    left_at TEXT,
    UNIQUE(placement_id, user_id),
    FOREIGN KEY (placement_id) REFERENCES network_placements(id) ON DELETE CASCADE,
    FOREIGN KEY (campaign_id) REFERENCES network_campaigns(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS runtime_settings (
    setting_key TEXT PRIMARY KEY,
    setting_value TEXT NOT NULL,
    updated_by_user_id INTEGER,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (updated_by_user_id) REFERENCES users(user_id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS star_payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    invoice_payload TEXT NOT NULL,
    payment_kind TEXT NOT NULL,
    stars_amount INTEGER NOT NULL,
    credits_granted INTEGER NOT NULL DEFAULT 0,
    telegram_payment_charge_id TEXT NOT NULL UNIQUE,
    provider_payment_charge_id TEXT,
    status TEXT NOT NULL DEFAULT 'paid',
    refunded_at TEXT,
    refunded_by_user_id INTEGER,
    refund_reason TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (refunded_by_user_id) REFERENCES users(user_id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS network_contribution_ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    placement_id INTEGER,
    campaign_id INTEGER,
    units REAL NOT NULL,
    entry_type TEXT NOT NULL,
    reason TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (placement_id) REFERENCES network_placements(id) ON DELETE SET NULL,
    FOREIGN KEY (campaign_id) REFERENCES network_campaigns(id) ON DELETE SET NULL
);

'''

INDEXES = '''
CREATE INDEX IF NOT EXISTS idx_users_status ON users(status);
CREATE INDEX IF NOT EXISTS idx_users_referred_by ON users(referred_by_user_id);
CREATE INDEX IF NOT EXISTS idx_transactions_user_id ON transactions(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_campaigns_owner_status ON campaigns(owner_user_id, status, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_task_submissions_campaign_status ON task_submissions(campaign_id, status, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_task_submissions_performer_status ON task_submissions(performer_user_id, status, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_task_submissions_verification ON task_submissions(verification_state, last_verification_at);
CREATE INDEX IF NOT EXISTS idx_holds_user_status_release ON holds(user_id, status, release_at);
CREATE INDEX IF NOT EXISTS idx_holds_verification_due ON holds(status, verification_required, verification_status, verification_due_at);
CREATE INDEX IF NOT EXISTS idx_referrals_referrer ON referrals(referrer_user_id);
CREATE INDEX IF NOT EXISTS idx_vip_user_active ON vip_subscriptions(user_id, is_active, expires_at DESC);
CREATE INDEX IF NOT EXISTS idx_admin_logs_target ON admin_logs(target_user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_risk_events_user_created ON risk_events(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ui_sessions_chat_message ON ui_sessions(chat_id, message_id);
CREATE INDEX IF NOT EXISTS idx_required_chats_ref ON required_chats(chat_ref);
CREATE INDEX IF NOT EXISTS idx_chat_start_gate_notices_user ON chat_start_gate_notices(user_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_redemptions_user_status ON redemptions(user_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_observed_messages_chat_message ON observed_messages(chat_ref, message_id);
CREATE INDEX IF NOT EXISTS idx_activity_events_user_type_created ON activity_events(user_id, activity_type, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_activity_events_chat_message ON activity_events(chat_ref, message_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_activity_events_poll_id ON activity_events(poll_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_bot_chats_active ON bot_chats(is_active, can_post, chat_type, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_ad_broadcasts_status_due ON ad_broadcasts(status, next_run_at, created_at);
CREATE INDEX IF NOT EXISTS idx_admin_notes_target_created ON admin_notes(target_user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_admin_notes_submission_created ON admin_notes(related_submission_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_provider_services_provider_enabled ON provider_services(provider_code, is_enabled, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_provider_services_category ON provider_services(provider_code, category, service_type);
CREATE INDEX IF NOT EXISTS idx_provider_orders_campaign ON provider_orders(campaign_id, provider_code, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_provider_orders_external ON provider_orders(provider_code, external_order_id);
CREATE INDEX IF NOT EXISTS idx_community_rule_acceptances_user ON community_rule_acceptances(user_id, accepted_at DESC);
CREATE INDEX IF NOT EXISTS idx_engagement_memberships_mode ON engagement_memberships(mode, status, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_engagement_obligations_user_status ON engagement_obligations(user_id, status, due_at);
CREATE INDEX IF NOT EXISTS idx_engagement_obligations_campaign ON engagement_obligations(campaign_id);
CREATE INDEX IF NOT EXISTS idx_engagement_obligations_due ON engagement_obligations(status, due_at, reminder_sent_at, warning_sent_at);
CREATE INDEX IF NOT EXISTS idx_engagement_admin_decisions_target ON engagement_admin_decisions(target_user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_legal_doc_acceptances_user ON legal_doc_acceptances(user_id, accepted_at DESC);
CREATE INDEX IF NOT EXISTS idx_platform_agreement_events_user ON platform_agreement_events(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_network_campaigns_owner_status ON network_campaigns(owner_user_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_network_placements_campaign_status ON network_placements(campaign_id, status, scheduled_at);
CREATE INDEX IF NOT EXISTS idx_network_placements_host_status ON network_placements(host_chat_id, status, scheduled_at);
CREATE INDEX IF NOT EXISTS idx_network_bonus_user ON network_bonus_ledger(user_id, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS idx_network_placements_tracking_token ON network_placements(tracking_token) WHERE tracking_token IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_network_join_due ON network_join_events(checked_24h_at, checked_7d_at, joined_at);
CREATE INDEX IF NOT EXISTS idx_network_join_user ON network_join_events(user_id, joined_at DESC);
CREATE INDEX IF NOT EXISTS idx_bot_chats_network ON bot_chats(network_enabled, network_status, member_count, quality_score);
CREATE INDEX IF NOT EXISTS idx_network_contribution_user ON network_contribution_ledger(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_star_payments_user ON star_payments(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_star_payments_status ON star_payments(status, created_at DESC);

'''

T = TypeVar('T')

_SNAPSHOT_LOCK = threading.Lock()
_TX_LOCAL = threading.local()
_LAST_LEGACY_MIRROR_MONOTONIC = 0.0


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    db_path = Path(settings.db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA foreign_keys = ON')
    connection.execute('PRAGMA busy_timeout = 5000')
    try:
        connection.execute('PRAGMA journal_mode = WAL')
    except sqlite3.DatabaseError:
        pass
    # Balanced durability for a WAL database: committed transactions survive
    # normal process/container restarts without forcing a full fsync per page.
    try:
        connection.execute('PRAGMA synchronous = NORMAL')
        connection.execute('PRAGMA wal_autocheckpoint = 1000')
        connection.execute('PRAGMA journal_size_limit = 67108864')
    except sqlite3.DatabaseError:
        pass
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




def _retire_unverifiable_launch_campaigns(connection: sqlite3.Connection) -> None:
    """Archive removed launch/open campaigns and return all unspent Sparks."""
    migration_key = 'migration_v361_retire_launch_tasks'
    if connection.execute('SELECT 1 FROM app_meta WHERE key = ?', (migration_key,)).fetchone():
        return

    rows = connection.execute(
        """
        SELECT * FROM campaigns
        WHERE task_type IN ('bot_start', 'mini_app_open')
          AND status IN ('draft', 'active', 'paused')
        """
    ).fetchall()
    for campaign in rows:
        campaign_id = int(campaign['id'])
        owner_user_id = int(campaign['owner_user_id'])
        spent = max(0, int(campaign['budget_spent'] or 0))
        total = max(0, int(campaign['budget_total'] or 0))
        refund_total = max(total - spent, 0) if int(campaign['is_funded'] or 0) == 1 else 0

        connection.execute(
            """
            UPDATE task_submissions
            SET status = 'rejected', reject_reason = 'task_type_removed',
                verification_state = 'failed', verification_note = 'task_type_removed',
                reviewed_at = COALESCE(reviewed_at, CURRENT_TIMESTAMP), updated_at = CURRENT_TIMESTAMP
            WHERE campaign_id = ? AND status IN ('taken', 'submitted', 'manual_review')
            """,
            (campaign_id,),
        )

        if refund_total > 0:
            source = connection.execute(
                """
                SELECT
                    COALESCE(SUM(CASE WHEN entry_type IN ('campaign_funding_bonus', 'campaign_boost_bonus')
                                      AND direction = 'debit' THEN amount ELSE 0 END), 0) AS bonus_paid,
                    COALESCE(SUM(CASE WHEN entry_type = 'campaign_retired_refund_bonus'
                                      AND direction = 'credit' THEN amount ELSE 0 END), 0) AS bonus_refunded
                FROM transactions WHERE related_campaign_id = ?
                """,
                (campaign_id,),
            ).fetchone()
            bonus_capacity = max(int(source['bonus_paid'] or 0) - int(source['bonus_refunded'] or 0), 0)
            bonus_refund = min(refund_total, bonus_capacity)
            internal_refund = refund_total - bonus_refund
            connection.execute('INSERT INTO wallets (user_id) VALUES (?) ON CONFLICT(user_id) DO NOTHING', (owner_user_id,))
            connection.execute(
                """
                UPDATE wallets
                SET bonus_balance = bonus_balance + ?, internal_balance = internal_balance + ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ?
                """,
                (bonus_refund, internal_refund, owner_user_id),
            )
            if bonus_refund:
                connection.execute(
                    """
                    INSERT INTO transactions (
                        user_id, wallet_user_id, amount, currency_code, direction, entry_type,
                        status, related_campaign_id, note
                    ) VALUES (?, ?, ?, 'BST', 'credit', 'campaign_retired_refund_bonus',
                              'completed', ?, 'Refund after removal of unverifiable task type')
                    """,
                    (owner_user_id, owner_user_id, bonus_refund, campaign_id),
                )
            if internal_refund:
                connection.execute(
                    """
                    INSERT INTO transactions (
                        user_id, wallet_user_id, amount, currency_code, direction, entry_type,
                        status, related_campaign_id, note
                    ) VALUES (?, ?, ?, 'BST', 'credit', 'campaign_retired_refund',
                              'completed', ?, 'Refund after removal of unverifiable task type')
                    """,
                    (owner_user_id, owner_user_id, internal_refund, campaign_id),
                )

        connection.execute(
            """
            UPDATE campaigns
            SET status = 'archived', auto_verify_enabled = 0, budget_reserved = 0,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (campaign_id,),
        )

    connection.execute(
        """
        INSERT INTO app_meta (key, value, updated_at)
        VALUES (?, 'done', CURRENT_TIMESTAMP)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP
        """,
        (migration_key,),
    )

def _run_migrations(connection: sqlite3.Connection) -> None:
    _ensure_column(connection, 'users', 'status', "TEXT NOT NULL DEFAULT 'active'")
    _ensure_column(connection, 'users', 'risk_score', 'INTEGER NOT NULL DEFAULT 0')
    _ensure_column(connection, 'users', 'referred_by_user_id', 'INTEGER')
    _ensure_column(connection, 'users', 'chat_gate_started_at', 'TEXT')
    _ensure_column(connection, 'campaigns', 'unit_price', 'INTEGER NOT NULL DEFAULT 0')
    _ensure_column(connection, 'campaigns', 'reward_budget_total', 'INTEGER NOT NULL DEFAULT 0')
    _ensure_column(connection, 'campaigns', 'service_fee_total', 'INTEGER NOT NULL DEFAULT 0')
    _ensure_column(connection, 'campaigns', 'pricing_json', 'TEXT')
    _ensure_column(connection, 'campaigns', 'auto_verify_enabled', 'INTEGER NOT NULL DEFAULT 0')
    _ensure_column(connection, 'campaigns', 'verification_json', 'TEXT')
    _ensure_column(connection, 'campaigns', 'retention_hours', 'INTEGER NOT NULL DEFAULT 0')
    _ensure_column(connection, 'campaigns', 'target_chat_ref', 'TEXT')
    _ensure_column(connection, 'campaigns', 'target_message_id', 'INTEGER')
    _ensure_column(connection, 'campaigns', 'is_funded', 'INTEGER NOT NULL DEFAULT 0')
    _ensure_column(connection, 'task_submissions', 'verification_state', "TEXT NOT NULL DEFAULT 'pending'")
    _ensure_column(connection, 'task_submissions', 'verification_attempts', 'INTEGER NOT NULL DEFAULT 0')
    _ensure_column(connection, 'task_submissions', 'last_verification_at', 'TEXT')
    _ensure_column(connection, 'task_submissions', 'verification_note', 'TEXT')
    _ensure_column(connection, 'task_submissions', 'retention_check_at', 'TEXT')
    _ensure_column(connection, 'holds', 'verification_required', 'INTEGER NOT NULL DEFAULT 0')
    _ensure_column(connection, 'holds', 'verification_status', "TEXT NOT NULL DEFAULT 'not_required'")
    _ensure_column(connection, 'holds', 'verification_due_at', 'TEXT')
    _ensure_column(connection, 'holds', 'verification_checked_at', 'TEXT')
    _ensure_column(connection, 'wallets', 'bonus_balance', 'INTEGER NOT NULL DEFAULT 0')
    _ensure_column(connection, 'holds', 'currency_code', "TEXT NOT NULL DEFAULT 'XTR'")
    if _get_table_columns(connection, 'provider_services'):
        _ensure_column(connection, 'provider_services', 'is_enabled', 'INTEGER NOT NULL DEFAULT 0')
        _ensure_column(connection, 'provider_services', 'markup_percent', 'INTEGER NOT NULL DEFAULT 35')
        _ensure_column(connection, 'provider_services', 'raw_json', 'TEXT')
    if _get_table_columns(connection, 'provider_orders'):
        _ensure_column(connection, 'provider_orders', 'provider_status', "TEXT NOT NULL DEFAULT 'draft'")
        _ensure_column(connection, 'provider_orders', 'last_payload_json', 'TEXT')
        _ensure_column(connection, 'provider_orders', 'owner_user_id', 'INTEGER')
        _ensure_column(connection, 'provider_orders', 'placed_at', 'TEXT')
        _ensure_column(connection, 'provider_orders', 'last_error', 'TEXT')
        _ensure_column(connection, 'provider_orders', 'paid_at', 'TEXT')
        _ensure_column(connection, 'provider_orders', 'telegram_payment_charge_id', 'TEXT')
        _ensure_column(connection, 'provider_orders', 'provider_payment_charge_id', 'TEXT')
        _ensure_column(connection, 'provider_orders', 'credit_cost', 'INTEGER NOT NULL DEFAULT 0')
        _ensure_column(connection, 'provider_orders', 'bonus_used', 'INTEGER NOT NULL DEFAULT 0')
        _ensure_column(connection, 'provider_orders', 'rate_value_snapshot', 'REAL NOT NULL DEFAULT 0')
        _ensure_column(connection, 'provider_orders', 'markup_percent_snapshot', 'INTEGER NOT NULL DEFAULT 0')
        _ensure_column(connection, 'provider_orders', 'price_checked_at', 'TEXT')
        _ensure_column(connection, 'provider_orders', 'expires_at', 'TEXT')
        _ensure_column(connection, 'provider_orders', 'refunded_credits', 'INTEGER NOT NULL DEFAULT 0')
    if _get_table_columns(connection, 'bot_chats'):
        _ensure_column(connection, 'bot_chats', 'can_invite_users', 'INTEGER NOT NULL DEFAULT 0')
        _ensure_column(connection, 'bot_chats', 'owner_user_id', 'INTEGER')
        _ensure_column(connection, 'bot_chats', 'network_enabled', 'INTEGER NOT NULL DEFAULT 1')
        _ensure_column(connection, 'bot_chats', 'network_status', "TEXT NOT NULL DEFAULT 'pending'")
        _ensure_column(connection, 'bot_chats', 'member_count', 'INTEGER NOT NULL DEFAULT 0')
        _ensure_column(connection, 'bot_chats', 'daily_limit', 'INTEGER NOT NULL DEFAULT 1')
        _ensure_column(connection, 'bot_chats', 'window_start', "TEXT NOT NULL DEFAULT '09:00'")
        _ensure_column(connection, 'bot_chats', 'window_end', "TEXT NOT NULL DEFAULT '22:00'")
        _ensure_column(connection, 'bot_chats', 'min_interval_hours', 'INTEGER NOT NULL DEFAULT 6')
        _ensure_column(connection, 'bot_chats', 'timezone_offset_minutes', 'INTEGER NOT NULL DEFAULT 0')
        _ensure_column(connection, 'bot_chats', 'topic_code', "TEXT NOT NULL DEFAULT 'general'")
        _ensure_column(connection, 'bot_chats', 'language_code', "TEXT NOT NULL DEFAULT 'ru'")
        _ensure_column(connection, 'bot_chats', 'quality_score', 'INTEGER NOT NULL DEFAULT 50')
        _ensure_column(connection, 'bot_chats', 'observed_active_users', 'INTEGER NOT NULL DEFAULT 0')
        _ensure_column(connection, 'bot_chats', 'observed_activity_events', 'INTEGER NOT NULL DEFAULT 0')
        _ensure_column(connection, 'bot_chats', 'last_activity_at', 'TEXT')
        _ensure_column(connection, 'bot_chats', 'verified_at', 'TEXT')
        _ensure_column(connection, 'bot_chats', 'disabled_reason', 'TEXT')
    if _get_table_columns(connection, 'network_placements'):
        _ensure_column(connection, 'network_placements', 'tracking_token', 'TEXT')
        _ensure_column(connection, 'network_placements', 'invite_link', 'TEXT')
        _ensure_column(connection, 'network_placements', 'reciprocal_placement_id', 'INTEGER')
        _ensure_column(connection, 'network_placements', 'contribution_reserved', 'REAL NOT NULL DEFAULT 0')
        _ensure_column(connection, 'network_placements', 'completed_at', 'TEXT')
        _ensure_column(connection, 'network_placements', 'revoked_at', 'TEXT')
        _ensure_column(connection, 'network_placements', 'refunded_credits', 'INTEGER NOT NULL DEFAULT 0')
        _ensure_column(connection, 'network_placements', 'refunded_bonus', 'INTEGER NOT NULL DEFAULT 0')
        _ensure_column(connection, 'network_placements', 'refunded_at', 'TEXT')
    if _get_table_columns(connection, 'network_campaigns'):
        _ensure_column(connection, 'network_campaigns', 'target_chat_id', 'INTEGER')
        _ensure_column(connection, 'network_campaigns', 'refunded_credits', 'INTEGER NOT NULL DEFAULT 0')
        _ensure_column(connection, 'network_campaigns', 'refunded_bonus', 'INTEGER NOT NULL DEFAULT 0')
    if _get_table_columns(connection, 'ad_broadcasts'):
        _ensure_column(connection, 'ad_broadcasts', 'credit_price', 'INTEGER NOT NULL DEFAULT 0')
        _ensure_column(connection, 'ad_broadcasts', 'bonus_used', 'INTEGER NOT NULL DEFAULT 0')
        _ensure_column(connection, 'ad_broadcasts', 'expires_at', 'TEXT')
    if _get_table_columns(connection, 'engagement_obligations'):
        _ensure_column(connection, 'engagement_obligations', 'reminder_sent_at', 'TEXT')
        _ensure_column(connection, 'engagement_obligations', 'warning_sent_at', 'TEXT')
        _ensure_column(connection, 'engagement_obligations', 'admin_warning_sent_at', 'TEXT')
        _ensure_column(connection, 'engagement_obligations', 'forgiven_at', 'TEXT')
        _ensure_column(connection, 'engagement_obligations', 'forgiven_by_user_id', 'INTEGER')
        _ensure_column(connection, 'engagement_obligations', 'extended_at', 'TEXT')
        _ensure_column(connection, 'engagement_obligations', 'extended_by_user_id', 'INTEGER')
        _ensure_column(connection, 'engagement_obligations', 'last_manual_warning_at', 'TEXT')

    _retire_unverifiable_launch_campaigns(connection)




def _looks_like_sqlite_file(path: Path) -> bool:
    try:
        if not path.exists() or not path.is_file():
            return False
        if path.stat().st_size == 0:
            return False
        with path.open('rb') as file:
            header = file.read(16)
        return header == b'SQLite format 3\x00'
    except Exception:
        return False


def _is_valid_sqlite_database(path: Path) -> bool:
    if not _looks_like_sqlite_file(path):
        return False
    try:
        connection = sqlite3.connect(path)
        try:
            row = connection.execute('PRAGMA integrity_check').fetchone()
            return bool(row) and str(row[0]).lower() == 'ok'
        finally:
            connection.close()
    except Exception:
        return False


def _quarantine_invalid_db(path: Path) -> Path | None:
    try:
        if not path.exists():
            return None
        bad_dir = Path(settings.data_dir) / 'invalid-db'
        bad_dir.mkdir(parents=True, exist_ok=True)
        stamp = utcnow().strftime('%Y%m%d_%H%M%S')
        target = bad_dir / f"{path.stem}_{stamp}{path.suffix}.bad"
        shutil.move(str(path), str(target))
        return target
    except Exception:
        return None


def _ensure_valid_target_db() -> None:
    target = Path(settings.db_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        return
    if target.stat().st_size == 0:
        try:
            target.unlink(missing_ok=True)
        except Exception:
            pass
        return
    if _is_valid_sqlite_database(target):
        return
    _quarantine_invalid_db(target)


def _candidate_restore_paths() -> list[Path]:
    db_name = Path(settings.db_path).name
    candidates = [
        Path(settings.db_path),
        Path(settings.data_dir) / db_name,
    ]
    if settings.legacy_db_restore_enabled:
        candidates.extend([
            Path.home() / '.boostora-data' / db_name,
            Path('/data') / db_name,
            Path('/storage') / db_name,
            Path('/var/data/boostora') / db_name,
            Path('/app') / db_name,
            Path('/app/storage') / db_name,
            Path('boostora.db'),
            Path('storage') / db_name,
        ])
    backups_dir = Path(settings.data_dir) / 'backups'
    if backups_dir.exists():
        candidates.extend(sorted(backups_dir.glob(f"{Path(db_name).stem}_*{Path(db_name).suffix}.bak"), reverse=True))
    unique: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        try:
            key = str(candidate.resolve()) if candidate.exists() else str(candidate)
        except Exception:
            key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        unique.append(candidate)
    return unique


def ensure_persistent_db_file() -> None:
    target = Path(settings.db_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    _ensure_valid_target_db()
    if target.exists() and _is_valid_sqlite_database(target):
        return

    best_source: Path | None = None
    best_mtime = -1.0
    for candidate in _candidate_restore_paths():
        if candidate == target:
            continue
        try:
            if _is_valid_sqlite_database(candidate):
                mtime = candidate.stat().st_mtime
                if mtime > best_mtime:
                    best_mtime = mtime
                    best_source = candidate
        except Exception:
            continue

    if best_source is None:
        return

    try:
        shutil.copy2(best_source, target)
    except Exception:
        return


def _copy_sqlite_snapshot(source: Path, target: Path) -> bool:
    """Create a transactionally consistent SQLite snapshot.

    Plain file copies can miss committed pages that still live in a WAL file.
    SQLite's backup API produces a complete snapshot even while the bot is
    serving users. The temporary file is atomically moved into place only after
    an integrity check succeeds.
    """
    try:
        if not _is_valid_sqlite_database(source):
            return False
        source_resolved = source.resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            if target.exists() and target.resolve() == source_resolved:
                return False
        except Exception:
            pass

        temporary = target.with_name(
            f'.{target.name}.{os.getpid()}.{threading.get_ident()}.tmp'
        )
        temporary.unlink(missing_ok=True)
        try:
            source_connection = sqlite3.connect(source_resolved, timeout=30)
            target_connection = sqlite3.connect(temporary, timeout=30)
            try:
                source_connection.backup(target_connection)
                target_connection.commit()
                row = target_connection.execute('PRAGMA integrity_check').fetchone()
                if not row or str(row[0]).lower() != 'ok':
                    raise sqlite3.DatabaseError('snapshot integrity_check failed')
            finally:
                target_connection.close()
                source_connection.close()
            os.replace(temporary, target)
            return True
        finally:
            temporary.unlink(missing_ok=True)
    except Exception:
        return False


def mirror_db_to_legacy_locations(*, force: bool = False) -> int:
    """Optionally maintain throttled legacy snapshots.

    The primary database is BOT_DATA_DIR/DB_PATH. Legacy mirroring is disabled
    by default because copying the whole database after every write caused disk
    amplification and could create stale WAL-incomplete copies. It can be
    explicitly enabled for a temporary migration window.
    """
    global _LAST_LEGACY_MIRROR_MONOTONIC

    if not settings.legacy_db_mirror_enabled:
        return 0

    now = time.monotonic()
    interval = max(30, int(settings.legacy_mirror_interval_seconds))
    if not force and now - _LAST_LEGACY_MIRROR_MONOTONIC < interval:
        return 0
    if not _SNAPSHOT_LOCK.acquire(blocking=False):
        return 0
    try:
        now = time.monotonic()
        if not force and now - _LAST_LEGACY_MIRROR_MONOTONIC < interval:
            return 0

        source = Path(settings.db_path)
        legacy_candidates = [
            Path('/app/storage') / source.name,
            Path('storage') / source.name,
        ]
        copied = 0
        for candidate in legacy_candidates:
            if _copy_sqlite_snapshot(source, candidate):
                copied += 1
        if copied:
            _LAST_LEGACY_MIRROR_MONOTONIC = now
        return copied
    finally:
        _SNAPSHOT_LOCK.release()


def _database_backup_files(db_path: Path, backup_dir: Path) -> list[Path]:
    pattern = f"{db_path.stem}_*{db_path.suffix}.bak"
    candidates = list(backup_dir.glob(pattern)) if backup_dir.exists() else []

    def _mtime(path: Path) -> float:
        try:
            return path.stat().st_mtime
        except OSError:
            return 0.0

    return sorted(candidates, key=_mtime, reverse=True)


def create_database_backup(*, max_files: int, min_interval_seconds: int = 0) -> Path | None:
    """Create and retain a WAL-consistent database backup.

    ``min_interval_seconds`` makes this safe to call from the frequent background
    cycle: the live database is not integrity-scanned or copied when a recent
    backup already exists. The interval is checked again under the snapshot lock
    so startup and worker backups cannot race each other.
    """
    db_path = Path(settings.db_path)
    backup_dir = Path(settings.data_dir) / 'backups'
    backup_dir.mkdir(parents=True, exist_ok=True)
    minimum_age = max(0, int(min_interval_seconds))

    def _recent_backup_exists() -> bool:
        if minimum_age <= 0:
            return False
        backups = _database_backup_files(db_path, backup_dir)
        if not backups:
            return False
        try:
            return time.time() - backups[0].stat().st_mtime < minimum_age
        except OSError:
            return False

    if _recent_backup_exists():
        return None
    if not _is_valid_sqlite_database(db_path):
        return None

    with _SNAPSHOT_LOCK:
        if _recent_backup_exists():
            return None
        stamp = utcnow().strftime('%Y%m%d_%H%M%S_%f')
        backup_path = backup_dir / f"{db_path.stem}_{stamp}{db_path.suffix}.bak"
        if not _copy_sqlite_snapshot(db_path, backup_path):
            return None

        keep = max(2, int(max_files))
        for extra in _database_backup_files(db_path, backup_dir)[keep:]:
            try:
                extra.unlink()
            except OSError:
                pass
        return backup_path


def create_startup_backup(max_files: int | None = None) -> Path | None:
    keep = settings.db_backup_max_files if max_files is None else max_files
    return create_database_backup(max_files=keep, min_interval_seconds=0)


def create_periodic_backup() -> Path | None:
    return create_database_backup(
        max_files=settings.db_backup_max_files,
        min_interval_seconds=settings.db_backup_interval_hours * 3600,
    )


def _apply_schema() -> None:
    with get_connection() as connection:
        connection.executescript(SCHEMA)
        _run_migrations(connection)
        connection.executescript(INDEXES)


def init_db() -> None:
    ensure_persistent_db_file()
    create_startup_backup()
    try:
        _apply_schema()
    except sqlite3.DatabaseError as error:
        message = str(error).lower()
        if 'file is not a database' not in message and 'database disk image is malformed' not in message:
            raise
        target = Path(settings.db_path)
        _quarantine_invalid_db(target)
        ensure_persistent_db_file()
        _apply_schema()
    mirror_db_to_legacy_locations(force=True)



def _active_transaction_connection() -> sqlite3.Connection | None:
    connection = getattr(_TX_LOCAL, 'connection', None)
    return connection if isinstance(connection, sqlite3.Connection) else None


def fetch_one(query: str, params: Sequence[Any] = ()) -> sqlite3.Row | None:
    active = _active_transaction_connection()
    if active is not None:
        return active.execute(query, params).fetchone()
    with get_connection() as connection:
        return connection.execute(query, params).fetchone()


def fetch_all(query: str, params: Sequence[Any] = ()) -> list[sqlite3.Row]:
    active = _active_transaction_connection()
    if active is not None:
        return active.execute(query, params).fetchall()
    with get_connection() as connection:
        return connection.execute(query, params).fetchall()


def execute(query: str, params: Sequence[Any] = ()) -> int:
    active = _active_transaction_connection()
    if active is not None:
        cursor = active.execute(query, params)
        return int(cursor.lastrowid or 0)
    with get_connection() as connection:
        cursor = connection.execute(query, params)
        result = int(cursor.lastrowid or 0)
    mirror_db_to_legacy_locations()
    return result


def execute_many(query: str, params_list: list[Sequence[Any]]) -> None:
    active = _active_transaction_connection()
    if active is not None:
        active.executemany(query, params_list)
        return
    with get_connection() as connection:
        connection.executemany(query, params_list)
    mirror_db_to_legacy_locations()


def run_in_transaction(callback: Callable[[sqlite3.Connection], T]) -> T:
    # Reuse the same connection for nested service calls. This lets the outer
    # transaction reserve SQLite's writer slot without nested db.execute()/fetch
    # opening a competing connection and deadlocking itself.
    active = _active_transaction_connection()
    if active is not None:
        return callback(active)
    with get_connection() as connection:
        connection.execute('BEGIN IMMEDIATE')
        _TX_LOCAL.connection = connection
        try:
            result = callback(connection)
        finally:
            _TX_LOCAL.connection = None
    mirror_db_to_legacy_locations()
    return result


def health_status() -> dict[str, Any]:
    """Cheap readiness probe for the persistent SQLite core."""
    started = time.monotonic()
    try:
        with get_connection() as connection:
            check = connection.execute('PRAGMA quick_check(1)').fetchone()
            journal = connection.execute('PRAGMA journal_mode').fetchone()
            connection.execute('SELECT 1').fetchone()
        ok = bool(check) and str(check[0]).lower() == 'ok'
        return {
            'ok': ok,
            'quick_check': str(check[0]) if check else 'missing',
            'journal_mode': str(journal[0]).lower() if journal else 'unknown',
            'latency_ms': max(0, int((time.monotonic() - started) * 1000)),
            'path_exists': Path(settings.db_path).exists(),
        }
    except Exception as exc:
        return {
            'ok': False,
            'quick_check': 'failed',
            'journal_mode': 'unknown',
            'latency_ms': max(0, int((time.monotonic() - started) * 1000)),
            'path_exists': Path(settings.db_path).exists(),
            'error': exc.__class__.__name__,
        }



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
