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
fd, temp_db = tempfile.mkstemp(prefix='boostora_smoke_', suffix='.db')
os.close(fd)
os.environ['DB_PATH'] = temp_db

from app.db import init_db, get_connection
from app.services.campaigns import CampaignService
from app.services.client_campaigns import ClientCampaignService
from app.services.performer import PerformerService
from app.services.users import UserService
from app.services.wallets import WalletService

try:
    Path(temp_db).unlink(missing_ok=True)
    init_db()
    owner = SimpleNamespace(id=101, username='owner', first_name='Owner', last_name='One')
    performer = SimpleNamespace(id=202, username='perf', first_name='Perf', last_name='Two')
    UserService.ensure_user(owner)
    UserService.ensure_user(performer)

    assert WalletService.get_summary(101)['bonus_balance'] == 300
    assert WalletService.get_summary(202)['bonus_balance'] == 300

    ok, _ = ClientCampaignService.start_draft(101, 'channel_subscribe')
    assert ok
    ok, _, _ = ClientCampaignService.consume_target(101, 'https://t.me/testchannel')
    assert ok
    ok, _, _ = ClientCampaignService.consume_quantity(101, '10')
    assert ok
    ok, _, _ = ClientCampaignService.consume_price(101, 'auto')
    assert ok
    ok, _, campaign_id = ClientCampaignService.finalize_draft(101, True)
    assert ok and campaign_id is not None

    campaign = CampaignService.get_campaign(campaign_id)
    assert campaign is not None and campaign['status'] == 'active' and int(campaign['is_funded']) == 1
    assert WalletService.get_summary(101)['bonus_balance'] == 40

    tasks = PerformerService.list_available_tasks(202)
    assert len(tasks) == 1 and int(tasks[0]['id']) == int(campaign_id)

    ok, _, submission_id = PerformerService.take_task(202, int(campaign_id))
    assert ok and submission_id is not None
    ok, _, _ = PerformerService.submit_proof(202, int(submission_id), 'proof ok')
    assert ok
    with get_connection() as connection:
        connection.execute("UPDATE holds SET release_at='2000-01-01T00:00:00' WHERE user_id = 202")
    PerformerService.release_due_holds(202)
    assert WalletService.get_summary(202)['internal_balance'] == 18
    print('OK: final smoke test passed')
finally:
    Path(temp_db).unlink(missing_ok=True)
