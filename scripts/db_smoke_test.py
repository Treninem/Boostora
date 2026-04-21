import os
import sys
from pathlib import Path

os.environ.setdefault('BOT_TOKEN', 'dummy-token-for-local-tests')

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from types import SimpleNamespace
import tempfile

from app.db import fetch_all, get_user, get_wallet, init_db
from app.services.admin_logs import AdminLogService
from app.services.campaigns import CampaignService
from app.services.holds import HoldService
from app.services.referrals import ReferralService
from app.services.risk import RiskService
from app.services.submissions import SubmissionService
from app.services.transactions import TransactionService
from app.services.users import UserService
from app.services.vip import VipService
from app.services.wallets import WalletService
from app.config import settings


def main() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        db_file = Path(temp_dir) / 'smoke.db'
        original_db_path = settings.db_path
        object.__setattr__(settings, 'db_path', str(db_file))
        try:
            init_db()
            fake_user = SimpleNamespace(id=1001, username='tester', first_name='Test', last_name='User')
            UserService.ensure_user(fake_user)
            UserService.set_language(1001, 'en')
            UserService.set_role(1001, 'performer')

            referred_user = SimpleNamespace(id=1002, username='newbie', first_name='New', last_name='User')
            UserService.ensure_user(referred_user)

            assert get_user(1001) is not None
            assert get_wallet(1001) is not None

            campaign_id = CampaignService.create_campaign(
                owner_user_id=1001,
                task_type='bot_start',
                target_url='https://t.me/BoostoraBot',
                reward_amount=10,
                total_quantity=5,
                title='Smoke test campaign',
            )
            submission_id = SubmissionService.create_submission(campaign_id, 1001, 10)
            hold_id = HoldService.create_hold(1001, 10, submission_id=submission_id, hold_minutes=1)
            TransactionService.create_transaction(1001, 10, 'credit', 'hold_reward', related_campaign_id=campaign_id, related_submission_id=submission_id, related_hold_id=hold_id)
            ReferralService.bind_referral(1001, 1002)
            VipService.create_subscription(1001, 'vip_7d', 7, hold_speed_percent=15, active_task_limit_bonus=2, priority_level=1, referral_rate_bonus_bps=100)
            AdminLogService.log(1001, 'smoke_check', target_user_id=1001, details='ok')
            RiskService.add_event(1001, 'fast_action', 'medium', 5, submission_id=submission_id, details='smoke')

            assert WalletService.get_wallet(1001) is not None
            assert len(fetch_all('SELECT * FROM campaigns')) == 1
            assert len(fetch_all('SELECT * FROM task_submissions')) == 1
            assert len(fetch_all('SELECT * FROM holds')) == 1
            assert len(fetch_all('SELECT * FROM referrals')) == 1
            assert len(fetch_all('SELECT * FROM vip_subscriptions')) == 1
            assert len(fetch_all('SELECT * FROM admin_logs')) == 1
            assert len(fetch_all('SELECT * FROM risk_events')) == 1
            print('OK: stage 2 smoke test passed')
        finally:
            object.__setattr__(settings, 'db_path', original_db_path)


if __name__ == '__main__':
    main()
