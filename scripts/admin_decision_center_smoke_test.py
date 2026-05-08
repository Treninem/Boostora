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

dotenv = types.ModuleType('dotenv')
dotenv.load_dotenv = lambda *args, **kwargs: None
sys.modules.setdefault('dotenv', dotenv)

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault('BOT_TOKEN', '123:abc')
os.environ.setdefault('ADMIN_IDS', '999')
fd, temp_db = tempfile.mkstemp(prefix='boostora_admin_decision_', suffix='.db')
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

class DummyBot:
    def get_me(self):
        return SimpleNamespace(id=555000)
    def get_chat_member(self, chat_id, bot_id):
        if int(chat_id) == -1002:
            return SimpleNamespace(status='administrator', can_post_messages=False)
        return SimpleNamespace(status='administrator', can_post_messages=True)
    def get_chat(self, chat_id):
        return SimpleNamespace(title=f'Chat {chat_id}', username=f'chat{abs(int(chat_id))}')

try:
    Path(temp_db).unlink(missing_ok=True)
    init_db()
    assert APP_VERSION.startswith('Boostora v2.')
    assert isinstance(APP_STAGE, str) and APP_STAGE

    users = [
        SimpleNamespace(id=999, username='admin', first_name='Admin', last_name='Root'),
        SimpleNamespace(id=710, username='client', first_name='Client', last_name='One'),
        SimpleNamespace(id=720, username='clean', first_name='Clean', last_name='Two'),
        SimpleNamespace(id=730, username='risk', first_name='Risk', last_name='Three'),
    ]
    for user in users:
        UserService.ensure_user(user)

    ok, _ = ClientCampaignService.start_draft(710, 'channel_subscribe')
    assert ok
    assert ClientCampaignService.consume_target(710, 'https://t.me/testchannel')[0]
    assert ClientCampaignService.consume_quantity(710, '4')[0]
    assert ClientCampaignService.consume_price(710, 'auto')[0]
    ok, _, campaign_id = ClientCampaignService.finalize_draft(710, True)
    assert ok and campaign_id

    ok, _, sub_clean = PerformerService.take_task(720, int(campaign_id))
    assert ok and sub_clean
    assert PerformerService.submit_proof(720, int(sub_clean), 'clean proof')[0]
    db.execute("UPDATE task_submissions SET status='manual_review', risk_score=0 WHERE id=?", (int(sub_clean),))

    ok, _, sub_risk = PerformerService.take_task(730, int(campaign_id))
    assert ok and sub_risk
    assert PerformerService.submit_proof(730, int(sub_risk), 'wrong target proof')[0]
    db.execute("UPDATE users SET risk_score=70 WHERE user_id=730")
    db.execute("UPDATE task_submissions SET status='manual_review', risk_score=25 WHERE id=?", (int(sub_risk),))

    groups = AdminConsoleService.queue_group_summary(limit=5)
    assert groups['performers'] and groups['campaigns'] and groups['risk_buckets']

    ok, key = AdminService.add_admin_note(999, 730, 'same performer repeats weak proof', related_submission_id=int(sub_risk))
    assert ok and key == 'admin_note_saved'
    card = AdminService.get_submission_card(int(sub_risk))
    assert card and card['notes']

    ok, result_key, performer_id = AdminService.review_submission_with_template(999, int(sub_risk), 'reject_wrong_target')
    assert ok and result_key == 'admin_submission_rejected' and performer_id == 730

    db.execute("""
        INSERT INTO bot_chats (chat_id, chat_ref, title, chat_type, username, is_active, can_post, last_seen_at)
        VALUES (-1001, '@ready', 'Ready', 'channel', 'ready', 1, 0, CURRENT_TIMESTAMP)
    """)
    db.execute("""
        INSERT INTO bot_chats (chat_id, chat_ref, title, chat_type, username, is_active, can_post, last_seen_at)
        VALUES (-1002, '@issue', 'Issue', 'channel', 'issue', 1, 1, CURRENT_TIMESTAMP)
    """)
    audit = AdminConsoleService.audit_bot_rights_live(DummyBot(), limit=10)
    assert audit['checked'] >= 2 and audit['ready'] >= 1 and audit['issues'] >= 1
    print('OK: admin decision center smoke test passed')
finally:
    Path(temp_db).unlink(missing_ok=True)
