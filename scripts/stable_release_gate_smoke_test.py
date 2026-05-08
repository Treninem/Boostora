from __future__ import annotations

import os
import sys
import tempfile
import types
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

# Lightweight dependency stubs for local CI environments without installed Bot API packages.
dotenv_mod = types.ModuleType('dotenv')
dotenv_mod.load_dotenv = lambda *args, **kwargs: None
sys.modules.setdefault('dotenv', dotenv_mod)

telebot_mod = types.ModuleType('telebot')
telebot_types_mod = types.ModuleType('telebot.types')

class _DummyMarkup:
    def __init__(self, row_width: int = 1):
        self.row_width = row_width
        self.buttons = []
    def add(self, *buttons):
        self.buttons.extend(buttons)
        return self
    def row(self, *buttons):
        self.buttons.extend(buttons)
        return self

class _DummyButton:
    def __init__(self, text: str = '', callback_data: str | None = None, url: str | None = None, web_app=None):
        self.text = text
        self.callback_data = callback_data
        self.url = url
        self.web_app = web_app

class _DummyUser:
    def __init__(self, id: int = 0, username: str | None = None, first_name: str | None = None, last_name: str | None = None):
        self.id = id
        self.username = username
        self.first_name = first_name
        self.last_name = last_name

class _DummyMessage:
    pass

class _DummyCallbackQuery:
    pass

class _DummyWebAppInfo:
    def __init__(self, url: str):
        self.url = url

class _DummyLabeledPrice:
    def __init__(self, label: str, amount: int):
        self.label = label
        self.amount = amount

telebot_types_mod.InlineKeyboardMarkup = _DummyMarkup
telebot_types_mod.InlineKeyboardButton = _DummyButton
telebot_types_mod.User = _DummyUser
telebot_types_mod.Message = _DummyMessage
telebot_types_mod.CallbackQuery = _DummyCallbackQuery
telebot_types_mod.WebAppInfo = _DummyWebAppInfo
telebot_types_mod.LabeledPrice = _DummyLabeledPrice
telebot_mod.TeleBot = object
telebot_mod.types = telebot_types_mod
sys.modules.setdefault('telebot', telebot_mod)
sys.modules.setdefault('telebot.types', telebot_types_mod)

base = Path(tempfile.mkdtemp(prefix='boostora_v300stable_'))
os.environ['BOT_TOKEN'] = 'TEST:TOKEN'
os.environ['ADMIN_IDS'] = '1'
os.environ['BOT_DATA_DIR'] = str(base)
os.environ['DB_PATH'] = str(base / f'boostora_v300stable_{uuid.uuid4().hex}.db')
os.environ['ENABLE_XTR_PAYMENTS'] = '1'

from app import db
from app.services.release_readiness import ReleaseReadinessService
from app.version import APP_STAGE, APP_VERSION


def seed() -> None:
    db.init_db()
    for user_id, username, role, risk in [
        (1, 'owner', 'client', 0),
        (10, 'client', 'client', 0),
        (100, 'worker', 'performer', 4),
    ]:
        db.execute(
            """
            INSERT INTO users (user_id, username, first_name, language_code, role, status, risk_score)
            VALUES (?, ?, ?, 'ru', ?, 'active', ?)
            """,
            (user_id, username, username, role, risk),
        )
        db.ensure_wallet(user_id)
    campaign_id = db.execute(
        """
        INSERT INTO campaigns (
            owner_user_id, title, task_type, target_url,
            reward_amount, unit_price, reward_budget_total, service_fee_total,
            pricing_json, is_funded, total_quantity, completed_quantity,
            rejected_quantity, budget_total, budget_reserved, budget_spent, status
        ) VALUES (
            10, 'Stable market task', 'chat_join', 'https://t.me/example',
            6, 10, 60, 40,
            '{"speed_index": 90, "recommended_unit_price": 10}', 1, 10, 3,
            0, 100, 6, 30, 'active'
        )
        """
    )
    db.execute(
        """
        INSERT INTO task_submissions (
            campaign_id, performer_user_id, status, target_url, proof_text,
            reward_amount, risk_score, submitted_at, reviewed_at, reviewer_user_id
        ) VALUES (?, 100, 'approved', 'https://t.me/example', 'proof', 6, 2, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 1)
        """,
        (campaign_id,),
    )
    db.execute(
        """
        INSERT INTO holds (user_id, submission_id, amount, status, release_at)
        VALUES (100, 1, 6, 'active', DATETIME(CURRENT_TIMESTAMP, '+24 hours'))
        """
    )
    for entry_type, amount in [
        ('stars_topup', 100),
        ('vip_purchase', -20),
        ('campaign_funding', -100),
        ('campaign_boost', -15),
    ]:
        db.execute(
            """
            INSERT INTO transactions (user_id, wallet_user_id, amount, currency_code, direction, entry_type, status, related_campaign_id, note)
            VALUES (10, 10, ?, 'BST', ?, ?, 'completed', ?, 'stable gate')
            """,
            (amount, 'credit' if amount > 0 else 'debit', entry_type, campaign_id),
        )
    db.execute("INSERT INTO bot_chats (chat_id, chat_ref, title, chat_type, is_active, can_post, last_seen_at) VALUES (-100, '@ready', 'Ready chat', 'group', 1, 1, CURRENT_TIMESTAMP)")
    db.execute("INSERT INTO admin_notes (admin_user_id, target_user_id, related_submission_id, note) VALUES (1, 100, NULL, 'stable note')")
    db.execute("INSERT INTO risk_events (user_id, event_type, severity, score_delta, details) VALUES (100, 'stable_check', 'low', 1, 'stable smoke')")


def main() -> None:
    assert APP_VERSION == 'Boostora v3.0.3'
    assert APP_STAGE == 'stable_patch_db_runtime_guard'
    seed()
    gate = ReleaseReadinessService.stable_release_summary()
    assert gate['score'] >= 80
    assert gate['state'] in {'stable_ready', 'stable_guarded', 'live_control'}
    assert len(gate['rows']) >= 8
    assert ReleaseReadinessService.stable_release_contract()

    import app.router as router
    text = router._build_owner_release_text(1)
    assert 'v3.0.0' in text
    assert 'Stable' in text or 'Стабильный' in text
    assert 'Данные не меняются' in text or 'does not mutate' in text
    print('stable_release_gate_smoke_test: OK', flush=True)
    os._exit(0)


if __name__ == '__main__':
    main()
