import os
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault('BOT_TOKEN', '123:abc')
os.environ.setdefault('DB_PATH', 'autocheck_promo_test.db')
os.environ.setdefault('BOT_DATA_DIR', str(ROOT / 'tmpdata'))

from app import db
from app.config import settings
from app.services.activity import ActivityService
from app.services.campaigns import CampaignService
from app.services.performer import PerformerService
from app.services.promo import PromoService
from app.services.subscriptions import SubscriptionService


def reset_db():
    db.init_db()
    with db.get_connection() as connection:
        for table in [
            'activity_events', 'observed_messages', 'task_submissions', 'campaigns',
            'wallets', 'users', 'required_chats', 'app_meta'
        ]:
            connection.execute(f'DELETE FROM {table}')


def seed_user(user_id: int, role: str):
    db.upsert_user(user_id, f'user{user_id}', f'User{user_id}', '', language_code='ru')
    db.set_user_role(user_id, role)
    db.ensure_wallet(user_id)


class FakeBot:
    def __init__(self):
        self.sent = []

    def get_chat(self, chat_ref):
        return SimpleNamespace(linked_chat_id=None)

    def get_chat_member(self, chat_ref, user_id):
        return SimpleNamespace(status='member', is_member=True)

    def send_message(self, chat_ref, text):
        self.sent.append((chat_ref, text))
        return True


reset_db()
seed_user(1, 'client')
seed_user(2, 'performer')

campaign_comment = CampaignService.create_campaign(
    owner_user_id=1,
    title='Комментарий',
    task_type='post_comment',
    target_url='https://t.me/testchat/55',
    reward_amount=14,
    unit_price=20,
    reward_budget_total=14,
    service_fee_total=6,
    total_quantity=1,
    status='active',
    is_funded=True,
)
ok, _, submission_id = PerformerService.take_task(2, campaign_comment)
assert ok and submission_id
ActivityService._insert_event(
    user_id=2,
    activity_type='comment',
    chat_ref='@testchat',
    chat_id=-100123,
    message_id=88,
    parent_message_id=55,
    payload={'text': 'готово'},
)
result = PerformerService.submit_for_check(FakeBot(), 2, int(submission_id))
assert result[0] is True, result
submission = PerformerService.get_submission(int(submission_id))
assert str(submission['status']) == 'approved', dict(submission)

campaign_poll = CampaignService.create_campaign(
    owner_user_id=1,
    title='Опрос',
    task_type='poll_vote',
    target_url='https://t.me/pollchat/77',
    reward_amount=7,
    unit_price=10,
    reward_budget_total=7,
    service_fee_total=3,
    total_quantity=1,
    status='active',
    is_funded=True,
)
ok, _, submission_poll_id = PerformerService.take_task(2, campaign_poll)
assert ok and submission_poll_id
with db.get_connection() as connection:
    connection.execute(
        "INSERT INTO observed_messages (chat_ref, chat_id, message_id, message_kind, poll_id) VALUES (?, ?, ?, ?, ?)",
        ('@pollchat', -100222, 77, 'poll', 'poll-1'),
    )
ActivityService._insert_event(user_id=2, activity_type='poll_vote', poll_id='poll-1', payload={'option_ids': [0]})
result_poll = PerformerService.submit_for_check(FakeBot(), 2, int(submission_poll_id))
assert result_poll[0] is True, result_poll

SubscriptionService.add_required_chat('@Boostorachat', 'https://t.me/Boostorachat')
PromoService.run_due_promotions(FakeBot())

assert settings.db_path.endswith('.db')
assert Path(settings.db_path).parent.exists()
print('OK: autocheck/promo/persistence smoke test passed')
