from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_v360_automatic_verification_in_isolated_process() -> None:
    script = r'''
import json, os, sys, tempfile
from pathlib import Path
from types import SimpleNamespace
root=Path(sys.argv[1]); sys.path.insert(0,str(root))
os.environ.update({
    'BOT_TOKEN':'123456:TESTTOKEN','ADMIN_IDS':'999','BOT_DATA_DIR':tempfile.mkdtemp(prefix='boostora-v360-'),
    'DB_PATH':'test.db','WEBAPP_ENABLED':'0','LEGACY_DB_MIRROR_ENABLED':'0','SUPPORT_USERNAME':'@BoostoraTestBot',
})
from app import db
from app.services.activity import ActivityService
from app.services.campaigns import CampaignService
from app.services.performer import PerformerService
from app.services.wallets import WalletService

db.init_db()
for uid in (100,200,300,999):
    db.upsert_user(uid,f'u{uid}',f'U{uid}',None); WalletService.ensure_wallet(uid)

class Bot:
    def get_chat(self, chat_ref):
        return SimpleNamespace(id=-100123, username='testchan', linked_chat_id=None)
    def get_chat_member(self, chat_ref, user_id):
        return SimpleNamespace(status='member', is_member=True)
    def get_me(self):
        return SimpleNamespace(id=999, username='BoostoraTestBot')
bot=Bot()

# Reaction: event verifies the user, reward is held, removal before due revokes it.
reaction_campaign=CampaignService.create_campaign(
    100,'post_reaction','https://t.me/testchan/77',5,2,title='Reaction',status='active',
    unit_price=8,reward_budget_total=10,service_fee_total=6,is_funded=True,
    verification_rules={'required_reactions':['🔥']},auto_verify_enabled=True,retention_hours=3,
)
ok,key,sid=PerformerService.take_task(200,reaction_campaign); assert ok and key=='task_taken_auto'
ActivityService.record_reaction(SimpleNamespace(
    user=SimpleNamespace(id=200,is_bot=False),chat=SimpleNamespace(id=-100123,username='testchan'),
    message_id=77,new_reaction=[SimpleNamespace(emoji='🔥',custom_emoji_id=None)],
))
ok,key,hold_id=PerformerService.submit_for_check(bot,200,sid); assert ok and key=='task_verified_hold'
sub=PerformerService.get_submission(sid); assert sub['status']=='approved' and sub['verification_state']=='holding'
hold=db.fetch_one('SELECT * FROM holds WHERE id=?',(hold_id,)); assert hold['verification_status']=='pending'
assert int(WalletService.get_summary(200)['hold_balance'])==5
ActivityService.record_reaction(SimpleNamespace(
    user=SimpleNamespace(id=200,is_bot=False),chat=SimpleNamespace(id=-100123,username='testchan'),
    message_id=77,new_reaction=[],
))
db.execute("UPDATE holds SET verification_due_at='2000-01-01T00:00:00', release_at='2000-01-01T00:00:00' WHERE id=?",(hold_id,))
review=PerformerService.review_due_verification_holds(bot); assert review['revoked']==1, review
assert PerformerService.get_submission(sid)['status']=='revoked'
assert int(WalletService.get_summary(200)['hold_balance'])==0

# Chat member events must be attributed to the joined member, not the admin actor.
joined=ActivityService.record_chat_member(SimpleNamespace(
    chat=SimpleNamespace(id=-100456,username='groupx'),from_user=SimpleNamespace(id=999),
    new_chat_member=SimpleNamespace(user=SimpleNamespace(id=300,is_bot=False),status='member',is_member=True),
))
assert joined==300
row=db.fetch_one("SELECT * FROM activity_events WHERE activity_type='chat_member' ORDER BY id DESC LIMIT 1")
assert int(row['user_id'])==300 and json.loads(row['payload_json'])['actor_user_id']==999

# Opening a publication is explicitly an open/click task, not a claim of personal view tracking.
open_campaign=CampaignService.create_campaign(
    100,'post_view','https://t.me/testchan/88',3,1,title='Open',status='active',
    unit_price=6,reward_budget_total=3,service_fee_total=3,is_funded=True,
    auto_verify_enabled=True,retention_hours=0,
)
ok,key,open_sid=PerformerService.take_task(300,open_campaign); assert ok
ok,key,url,result_id=PerformerService.open_target(bot,300,open_sid)
assert ok and url.endswith('/88')
assert PerformerService.get_submission(open_sid)['status']=='approved'
summary=WalletService.get_summary(300)
assert int(summary['internal_balance'])==3 and int(summary['hold_balance'])==0, summary

# New migration columns and indexes exist.
columns={r['name'] for r in db.fetch_all('PRAGMA table_info(campaigns)')}
assert {'auto_verify_enabled','verification_json','retention_hours','target_chat_ref','target_message_id'} <= columns
columns={r['name'] for r in db.fetch_all('PRAGMA table_info(task_submissions)')}
assert {'verification_state','verification_attempts','last_verification_at','verification_note','retention_check_at'} <= columns
print('V360_AUTOMATIC_VERIFICATION_OK')
'''
    result = subprocess.run([sys.executable, '-c', script, str(ROOT)], cwd=ROOT, text=True, capture_output=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'V360_AUTOMATIC_VERIFICATION_OK' in result.stdout


def test_v360_static_contract() -> None:
    version=(ROOT/'app/version.py').read_text(encoding='utf-8')
    api=(ROOT/'app/services/miniapp_api.py').read_text(encoding='utf-8')
    bot=(ROOT/'app/bot.py').read_text(encoding='utf-8')
    html=(ROOT/'miniapp_example/index.html').read_text(encoding='utf-8')
    assert "APP_VERSION = 'Boostora v3.6.3'" in version
    assert "'chat_join_request'" in bot
    assert 'task_retention_checks' in bot and 'task_hold_releases' in bot
    assert "op == 'tasks.open'" in api and "op == 'tasks.autocheck'" in api
    assert 'visibilitychange' in html and 'Проверить сейчас' in html
    assert 'Добавить канал' in html and 'Добавить группу' in html
