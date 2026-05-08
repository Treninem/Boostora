import os
import sys
import tempfile
import types
from pathlib import Path
from types import SimpleNamespace

telebot = types.ModuleType('telebot')
telebot_types = types.ModuleType('telebot.types')
class DummyUser: ...
telebot_types.User = DummyUser
telebot.types = telebot_types
sys.modules.setdefault('telebot', telebot)
sys.modules.setdefault('telebot.types', telebot_types)

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault('BOT_TOKEN', '123:abc')
os.environ.setdefault('ADMIN_IDS', '999')
fd, temp_db = tempfile.mkstemp(prefix='boostora_admin_console_', suffix='.db')
os.close(fd)
os.environ['DB_PATH'] = temp_db

from app import db
from app.db import init_db
from app.services.admin import AdminService
from app.services.admin_console import AdminConsoleService
from app.services.client_campaigns import ClientCampaignService
from app.services.performer import PerformerService
from app.services.users import UserService
from app.version import APP_STAGE, APP_VERSION

try:
    Path(temp_db).unlink(missing_ok=True)
    init_db()
    assert APP_VERSION.startswith('Boostora v2.')
    assert isinstance(APP_STAGE, str) and APP_STAGE

    admin = SimpleNamespace(id=999, username='admin', first_name='Admin', last_name='Root')
    owner = SimpleNamespace(id=710, username='client', first_name='Client', last_name='One')
    clean_user = SimpleNamespace(id=720, username='clean', first_name='Clean', last_name='Two')
    risky_user = SimpleNamespace(id=730, username='risk', first_name='Risk', last_name='Three')
    for user in (admin, owner, clean_user, risky_user):
        UserService.ensure_user(user)

    ok, _ = ClientCampaignService.start_draft(710, 'channel_subscribe')
    assert ok
    assert ClientCampaignService.consume_target(710, 'https://t.me/testchannel')[0]
    assert ClientCampaignService.consume_quantity(710, '4')[0]
    assert ClientCampaignService.consume_price(710, 'auto')[0]
    ok, _, campaign_id = ClientCampaignService.finalize_draft(710, True)
    assert ok and campaign_id

    ok, _, clean_submission_id = PerformerService.take_task(720, int(campaign_id))
    assert ok and clean_submission_id
    assert PerformerService.submit_proof(720, int(clean_submission_id), 'proof clean')[0]
    db.execute("UPDATE task_submissions SET status='manual_review', risk_score=0 WHERE id=?", (int(clean_submission_id),))

    ok, _, risk_submission_id = PerformerService.take_task(730, int(campaign_id))
    assert ok and risk_submission_id
    assert PerformerService.submit_proof(730, int(risk_submission_id), 'proof risk')[0]
    db.execute("UPDATE users SET risk_score=70 WHERE user_id=730")
    db.execute("UPDATE task_submissions SET status='manual_review', risk_score=20 WHERE id=?", (int(risk_submission_id),))

    counts = AdminConsoleService.queue_counts()
    assert counts['all'] >= 2
    assert counts['clean'] >= 1
    assert counts['high'] >= 1
    high_rows = AdminService.list_review_queue(filter_code='high')
    clean_rows = AdminService.list_review_queue(filter_code='clean')
    assert high_rows and clean_rows

    ok, key, count = AdminService.bulk_approve_clean(999, limit=10)
    assert ok and key == 'admin_bulk_approved_clean' and count >= 1

    result = AdminConsoleService.block_high_risk_users(999, limit=10, threshold=60)
    assert result.ok and result.count >= 1
    assert UserService.get_status(730) == 'blocked'

    db.execute("""
        INSERT INTO bot_chats (chat_id, chat_ref, title, chat_type, username, is_active, can_post, last_seen_at)
        VALUES (-1001, '@testchat', 'Test Chat', 'supergroup', 'testchat', 1, 0, CURRENT_TIMESTAMP)
    """)
    rights = AdminConsoleService.bot_rights_summary()
    assert rights['issues'] >= 1
    assert AdminConsoleService.count_bot_right_issues() >= 1
    print('OK: admin console smoke test passed')
finally:
    Path(temp_db).unlink(missing_ok=True)
