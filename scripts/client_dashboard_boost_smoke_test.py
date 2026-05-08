import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
import types

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
fd, temp_db = tempfile.mkstemp(prefix='boostora_dashboard_', suffix='.db')
os.close(fd)
os.environ['DB_PATH'] = temp_db

from app.db import init_db
from app.services.client_campaigns import ClientCampaignService
from app.services.client_dashboard import boost_campaign, boost_options, dashboard_summary
from app.services.campaigns import CampaignService
from app.services.users import UserService
from app.services.wallets import WalletService
from app.version import APP_STAGE, APP_VERSION

try:
    Path(temp_db).unlink(missing_ok=True)
    init_db()
    assert APP_VERSION.startswith('Boostora v2.')
    assert isinstance(APP_STAGE, str) and APP_STAGE

    owner = SimpleNamespace(id=701, username='client', first_name='Client', last_name='One')
    UserService.ensure_user(owner)

    ok, _ = ClientCampaignService.start_draft(701, 'channel_subscribe')
    assert ok
    ok, _, _ = ClientCampaignService.consume_target(701, 'https://t.me/testchannel')
    assert ok
    ok, _, _ = ClientCampaignService.consume_quantity(701, '5')
    assert ok
    ok, _, _ = ClientCampaignService.consume_price(701, 'auto')
    assert ok
    ok, _, campaign_id = ClientCampaignService.finalize_draft(701, True)
    assert ok and campaign_id is not None

    campaign = CampaignService.get_owned_campaign(701, int(campaign_id))
    options = boost_options(campaign)
    assert 'fast' in options or 'recommended' in options

    before = WalletService.get_summary(701)['bonus_balance'] + WalletService.get_summary(701)['internal_balance']
    target_level = 'fast' if 'fast' in options else 'recommended'
    ok, result_key = boost_campaign(701, int(campaign_id), target_level)
    assert ok, result_key

    boosted = CampaignService.get_owned_campaign(701, int(campaign_id))
    assert int(boosted['unit_price']) > int(campaign['unit_price'])
    after = WalletService.get_summary(701)['bonus_balance'] + WalletService.get_summary(701)['internal_balance']
    assert after < before

    dashboard = dashboard_summary(701)
    assert dashboard['total'] == 1
    assert dashboard['active'] == 1
    assert dashboard['budget_total'] >= int(boosted['budget_total'])
    assert dashboard['rows'] and dashboard['rows'][0]['id'] == int(campaign_id)
    print('OK: client dashboard and boost smoke test passed')
finally:
    Path(temp_db).unlink(missing_ok=True)
