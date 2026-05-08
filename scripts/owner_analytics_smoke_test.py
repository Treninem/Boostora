from __future__ import annotations

import os
import sys
import tempfile
import types
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

dotenv_mod = types.ModuleType('dotenv')
dotenv_mod.load_dotenv = lambda *args, **kwargs: None
sys.modules.setdefault('dotenv', dotenv_mod)

base = Path(tempfile.mkdtemp(prefix='boostora_v250_'))
os.environ['BOT_TOKEN'] = 'TEST:TOKEN'
os.environ['ADMIN_IDS'] = '1'
os.environ['BOT_DATA_DIR'] = str(base)
os.environ['DB_PATH'] = str(base / f'boostora_v250_{uuid.uuid4().hex}.db')

from app import db
from app.services.owner_analytics import OwnerAnalyticsService
from app.version import APP_STAGE, APP_VERSION


def seed() -> None:
    db.init_db()
    for user_id, username, role, risk in [
        (1, 'owner', 'client', 0),
        (10, 'client_a', 'client', 0),
        (20, 'client_b', 'client', 0),
        (100, 'fast_worker', 'performer', 5),
        (200, 'risky_worker', 'performer', 70),
    ]:
        db.execute("INSERT INTO users (user_id, username, first_name, language_code, role, status, risk_score) VALUES (?, ?, ?, 'ru', ?, 'active', ?)", (user_id, username, username, role, risk))
        db.ensure_wallet(user_id)
    c1 = db.execute("INSERT INTO campaigns (owner_user_id, title, task_type, target_url, reward_amount, unit_price, reward_budget_total, service_fee_total, is_funded, total_quantity, completed_quantity, rejected_quantity, budget_total, budget_reserved, budget_spent, status) VALUES (10, 'Growth A', 'chat_join', 'https://t.me/a', 5, 8, 500, 300, 1, 100, 20, 2, 800, 80, 160, 'active')")
    c2 = db.execute("INSERT INTO campaigns (owner_user_id, title, task_type, target_url, reward_amount, unit_price, reward_budget_total, service_fee_total, is_funded, total_quantity, completed_quantity, rejected_quantity, budget_total, budget_reserved, budget_spent, status) VALUES (20, 'Growth B', 'post_like', 'https://t.me/b/1', 3, 6, 150, 150, 0, 50, 4, 1, 300, 0, 24, 'draft')")
    for campaign_id, performer, status, reward, risk in [
        (c1, 100, 'approved', 5, 1),
        (c1, 100, 'approved', 5, 2),
        (c1, 200, 'manual_review', 5, 30),
        (c1, 200, 'rejected', 5, 22),
        (c2, 100, 'approved', 3, 1),
    ]:
        db.execute("INSERT INTO task_submissions (campaign_id, performer_user_id, status, proof_text, reward_amount, risk_score, submitted_at, reviewed_at) VALUES (?, ?, ?, 'proof', ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)", (campaign_id, performer, status, reward, risk))
    db.execute('UPDATE wallets SET available_balance = 100, hold_balance = 20, bonus_balance = 5 WHERE user_id = 100')
    db.execute("INSERT INTO transactions (user_id, wallet_user_id, amount, currency_code, direction, entry_type, status, note) VALUES (10, 10, 500, 'BST', 'credit', 'stars_topup', 'completed', 'test topup')")
    db.execute("INSERT INTO transactions (user_id, wallet_user_id, amount, currency_code, direction, entry_type, status, note) VALUES (10, 10, -80, 'BST', 'debit', 'campaign_funding', 'completed', 'test campaign')")


def main() -> None:
    assert APP_VERSION == 'Boostora v3.0.3'
    assert APP_STAGE == 'stable_patch_db_runtime_guard'
    seed()
    summary = OwnerAnalyticsService.commerce_summary()
    assert summary['total_users'] == 5
    assert summary['active_campaigns'] == 1
    assert summary['turnover_spent'] == 184
    assert summary['actual_margin_estimate'] == (20 * 3) + (4 * 3)
    assert summary['margin_percent'] > 0
    assert summary['risky_unblocked'] == 1
    assert OwnerAnalyticsService.top_clients(limit=2)
    assert OwnerAnalyticsService.top_performers(limit=2)
    tips = OwnerAnalyticsService.economy_recommendations(summary)
    assert tips
    print('owner_analytics_smoke_test: OK', flush=True)
    os._exit(0)


if __name__ == '__main__':
    main()
