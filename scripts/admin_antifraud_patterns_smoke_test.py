from __future__ import annotations

import os
import sys
import tempfile
import types
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

# Lightweight dependency stubs for local CI environments without installed Bot API packages.
dotenv_mod = types.ModuleType('dotenv')
dotenv_mod.load_dotenv = lambda *args, **kwargs: None
sys.modules.setdefault('dotenv', dotenv_mod)
telebot_mod = types.ModuleType('telebot')
telebot_types_mod = types.ModuleType('telebot.types')
class User:
    def __init__(self, id: int = 0, username: str | None = None, first_name: str | None = None, last_name: str | None = None):
        self.id = id
        self.username = username
        self.first_name = first_name
        self.last_name = last_name
telebot_types_mod.User = User
telebot_mod.types = telebot_types_mod
sys.modules.setdefault('telebot', telebot_mod)
sys.modules.setdefault('telebot.types', telebot_types_mod)

base = Path(tempfile.mkdtemp(prefix='boostora_v240_'))
os.environ['BOT_TOKEN'] = 'TEST:TOKEN'
os.environ['ADMIN_IDS'] = '1'
os.environ['BOT_DATA_DIR'] = str(base)
os.environ['DB_PATH'] = str(base / 'boostora_v240_smoke.db')

from app import db
from app.services.admin_console import AdminConsoleService


def seed() -> None:
    db.init_db()
    for user_id, username, risk in [(1, 'admin', 0), (100, 'cleaner', 10), (200, 'risky', 75), (300, 'watchme', 45)]:
        db.execute(
            '''
            INSERT INTO users (user_id, username, first_name, language_code, status, risk_score)
            VALUES (?, ?, ?, 'ru', 'active', ?)
            ON CONFLICT(user_id) DO UPDATE SET username = excluded.username, risk_score = excluded.risk_score
            ''',
            (user_id, username, username, risk),
        )
        db.ensure_wallet(user_id)
    campaign_id = db.execute(
        '''
        INSERT INTO campaigns (owner_user_id, title, task_type, target_url, reward_amount, unit_price, total_quantity, status)
        VALUES (1, 'Smoke task', 'chat_join', 'https://t.me/example', 5, 7, 10, 'active')
        '''
    )
    submissions = [
        (campaign_id, 100, 'approved', 2, None, '2026-04-26T10:00:00'),
        (campaign_id, 100, 'approved', 1, None, '2026-04-26T11:00:00'),
        (campaign_id, 200, 'rejected', 25, 'spam proof', '2026-04-26T12:00:00'),
        (campaign_id, 200, 'manual_review', 30, None, None),
        (campaign_id, 300, 'manual_review', 12, None, None),
    ]
    for campaign_id, performer, status, risk, reason, reviewed_at in submissions:
        db.execute(
            '''
            INSERT INTO task_submissions (campaign_id, performer_user_id, status, proof_text, reward_amount, risk_score, reject_reason, reviewed_at, reviewer_user_id, submitted_at)
            VALUES (?, ?, ?, 'proof', 5, ?, ?, ?, 1, CURRENT_TIMESTAMP)
            ''',
            (campaign_id, performer, status, risk, reason, reviewed_at),
        )
    db.execute(
        """
        INSERT INTO admin_notes (admin_user_id, target_user_id, related_submission_id, note)
        VALUES (1, 200, NULL, 'Repeated junk proofs')
        """
    )
    db.execute(
        """
        INSERT INTO risk_events (user_id, event_type, severity, score_delta, details)
        VALUES (200, 'duplicate_proof', 'high', 15, 'same text')
        """
    )
    db.execute(
        """
        INSERT INTO bot_chats (chat_id, chat_ref, title, chat_type, is_active, can_post, last_seen_at)
        VALUES (-10, '@ready', 'Ready chat', 'group', 1, 1, CURRENT_TIMESTAMP)
        """
    )
    db.execute(
        """
        INSERT INTO bot_chats (chat_id, chat_ref, title, chat_type, is_active, can_post, last_seen_at)
        VALUES (-20, '@issue', 'Issue channel', 'channel', 1, 0, NULL)
        """
    )


def main() -> None:
    seed()
    risky_card = AdminConsoleService.performer_pattern_card(200)
    assert risky_card['pattern_code'] in {'hard_risk', 'unstable'}
    assert risky_card['note_count'] >= 1
    cards = AdminConsoleService.fraud_pattern_cards(limit=5)
    assert any(int(card['user_id']) == 200 for card in cards)
    history = AdminConsoleService.performer_decision_history(200, limit=3)
    assert history and str(history[0]['status']) == 'rejected'
    diagnostics = AdminConsoleService.bot_rights_diagnostics(limit=5)
    assert diagnostics['issues'] >= 1
    assert diagnostics['items']
    clean_advice = AdminConsoleService.bulk_action_advice('clean')
    high_advice = AdminConsoleService.bulk_action_advice('high')
    assert clean_advice['advice_code'] == 'bulk_clean_safe'
    assert high_advice['advice_code'] == 'bulk_high_caution'
    print('admin_antifraud_patterns_smoke_test: OK')


if __name__ == '__main__':
    main()
