import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault('BOT_TOKEN', '123:abc')

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import settings
from app.db import init_db
from app.services.campaigns import CampaignService
from app.services.performer import PerformerService
from app.services.referrals import ReferralService
from app.services.rewards import RewardService
from app.services.users import UserService
from app.services.vip import VipService
from app.services.wallets import WalletService



def main() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        db_file = Path(temp_dir) / 'stage6.db'
        original_db_path = settings.db_path
        object.__setattr__(settings, 'db_path', str(db_file))
        try:
            init_db()

            referrer = SimpleNamespace(id=6001, username='refboss', first_name='Ref', last_name='Boss')
            performer = SimpleNamespace(id=6002, username='worker', first_name='Work', last_name='Er')
            client = SimpleNamespace(id=6003, username='client', first_name='Cli', last_name='Ent')

            for tg_user in [referrer, performer, client]:
                UserService.ensure_user(tg_user)
                UserService.set_language(tg_user.id, 'ru')

            UserService.set_role(6002, 'performer')
            UserService.set_role(6003, 'client')

            ok_demo_ref, key_demo_ref = RewardService.claim_demo_topup(6001)
            assert ok_demo_ref is True and key_demo_ref == 'demo_topup_success'

            ok_vip, vip_key = VipService.purchase_plan(6001, 'vip_7')
            assert ok_vip is True and vip_key == 'vip_purchase_success'
            vip_bonuses = VipService.get_active_bonuses(6001)
            assert vip_bonuses['active_task_limit_bonus'] == 2
            assert vip_bonuses['hold_speed_percent'] == 25
            assert vip_bonuses['referral_rate_bonus_bps'] == 200

            bound = ReferralService.try_bind_referral(6001, 6002)
            assert bound is True
            summary_before = ReferralService.get_summary(6001)
            assert summary_before['invited_count'] == 1
            assert summary_before['current_rate_bps'] == 700
            assert summary_before['link'].endswith('start=ref_6001')

            campaign_id = CampaignService.create_campaign(
                owner_user_id=6003,
                task_type='chat_join',
                target_url='https://t.me/+stage6demo',
                reward_amount=100,
                total_quantity=5,
                title='Stage 6 campaign',
                status='active',
            )
            ok_take, take_key, submission_id = PerformerService.take_task(6002, campaign_id)
            assert ok_take is True and take_key == 'task_taken' and submission_id is not None
            ok_submit, submit_key, hold_id = PerformerService.submit_proof(6002, int(submission_id), 'joined @stage6demo')
            assert ok_submit is True and submit_key == 'proof_accepted' and hold_id is not None

            ref_summary_after = ReferralService.get_summary(6001)
            assert ref_summary_after['total_earned'] == 7
            ref_wallet = WalletService.get_summary(6001)
            assert ref_wallet['internal_balance'] == 607

            ok_demo_perf, key_demo_perf = RewardService.claim_demo_topup(6002)
            assert ok_demo_perf is True and key_demo_perf == 'demo_topup_success'
            ok_slots, slots_key = RewardService.purchase_item(6002, 'boost_slots_3d')
            assert ok_slots is True and slots_key == 'reward_purchase_success'
            ok_hold, hold_key = RewardService.purchase_item(6002, 'boost_hold_3d')
            assert ok_hold is True and hold_key == 'reward_purchase_success'
            assert PerformerService.get_active_task_limit(6002) == 4
            assert PerformerService.get_hold_minutes_for_user(6002) < settings.default_hold_hours * 60

            second_demo, second_key = RewardService.claim_demo_topup(6002)
            assert second_demo is False and second_key == 'demo_topup_already_claimed'

            perf_wallet = WalletService.get_summary(6002)
            assert perf_wallet['internal_balance'] == 900
            print('OK: stage 6 smoke test passed')
        finally:
            object.__setattr__(settings, 'db_path', original_db_path)


if __name__ == '__main__':
    main()
