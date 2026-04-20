import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault('BOT_TOKEN', '123:abc')
os.environ.setdefault('ADMIN_IDS', '7001')

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.bot import create_bot
from app.config import settings
from app.db import fetch_one, init_db
from app.services.admin import AdminService
from app.services.campaigns import CampaignService
from app.services.performer import PerformerService
from app.services.users import UserService
from app.services.wallets import WalletService



def main() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        db_file = Path(temp_dir) / 'stage7.db'
        original_db_path = settings.db_path
        original_admin_ids = list(settings.admin_ids)
        object.__setattr__(settings, 'db_path', str(db_file))
        object.__setattr__(settings, 'admin_ids', [7001])
        try:
            init_db()
            create_bot()

            admin = SimpleNamespace(id=7001, username='boss', first_name='Boss', last_name='Admin')
            performer = SimpleNamespace(id=7002, username='worker', first_name='Work', last_name='Er')
            client = SimpleNamespace(id=7003, username='client', first_name='Cli', last_name='Ent')

            for tg_user in [admin, performer, client]:
                UserService.ensure_user(tg_user)
                UserService.set_language(tg_user.id, 'ru')

            UserService.set_role(7002, 'performer')
            UserService.set_role(7003, 'client')
            assert UserService.is_admin(7001) is True

            campaign_id = CampaignService.create_campaign(
                owner_user_id=7003,
                task_type='chat_join',
                target_url='https://t.me/+stage7demo',
                reward_amount=120,
                total_quantity=10,
                title='Stage 7 campaign',
                status='active',
            )

            ok_risk, risk_key, current_risk = AdminService.adjust_risk_score(7001, 7002, 50, reason='seed risk')
            assert ok_risk is True and risk_key == 'admin_risk_adjusted' and current_risk == 50

            ok_take, take_key, submission_id = PerformerService.take_task(7002, campaign_id)
            assert ok_take is True and take_key == 'task_taken' and submission_id is not None
            ok_submit, submit_key, result_id = PerformerService.submit_proof(7002, int(submission_id), 'joined @stage7demo')
            assert ok_submit is True and submit_key == 'proof_sent_manual_review'
            assert result_id == int(submission_id)

            queue = AdminService.list_review_queue()
            assert len(queue) == 1 and int(queue[0]['id']) == int(submission_id)
            card = AdminService.get_submission_card(int(submission_id))
            assert card is not None and int(card['submission']['performer_user_id']) == 7002
            event = fetch_one('SELECT COUNT(*) AS cnt FROM risk_events WHERE user_id = ?', (7002,))
            assert event is not None and int(event['cnt']) >= 1

            ok_approve, approve_key, performer_id = AdminService.review_submission(7001, int(submission_id), approve=True)
            assert ok_approve is True and approve_key == 'admin_submission_approved' and performer_id == 7002
            wallet = WalletService.get_summary(7002)
            assert wallet['hold_balance'] == 120
            submission_row = PerformerService.get_submission(int(submission_id))
            assert submission_row is not None and str(submission_row['status']) == 'approved'

            campaign2_id = CampaignService.create_campaign(
                owner_user_id=7003,
                task_type='channel_subscribe',
                target_url='https://t.me/stage7second',
                reward_amount=80,
                total_quantity=5,
                title='Stage 7 campaign 2',
                status='active',
            )
            ok_take2, _, submission2_id = PerformerService.take_task(7002, campaign2_id)
            assert ok_take2 is True and submission2_id is not None
            ok_submit2, submit2_key, _ = PerformerService.submit_proof(7002, int(submission2_id), 'joined @stage7demo again')
            assert ok_submit2 is True and submit2_key == 'proof_sent_manual_review'
            ok_reject, reject_key, _ = AdminService.review_submission(
                7001,
                int(submission2_id),
                approve=False,
                reject_reason='Подозрительное выполнение',
            )
            assert ok_reject is True and reject_key == 'admin_submission_rejected'
            submission2_row = PerformerService.get_submission(int(submission2_id))
            assert submission2_row is not None and str(submission2_row['status']) == 'rejected'
            assert str(submission2_row['reject_reason']) == 'Подозрительное выполнение'

            ok_block, block_key = AdminService.set_user_blocked(7001, 7002, True)
            assert ok_block is True and block_key == 'admin_user_blocked'
            assert UserService.can_access_bot(7002) is False
            ok_unblock, unblock_key = AdminService.set_user_blocked(7001, 7002, False)
            assert ok_unblock is True and unblock_key == 'admin_user_unblocked'
            assert UserService.can_access_bot(7002) is True

            ok_bal1, bal_key1, balance1 = AdminService.adjust_available_balance(7001, 7002, 150, reason='top up')
            assert ok_bal1 is True and bal_key1 == 'admin_balance_adjusted' and balance1 == 150
            ok_bal2, bal_key2, balance2 = AdminService.adjust_available_balance(7001, 7002, -50, reason='fine')
            assert ok_bal2 is True and bal_key2 == 'admin_balance_adjusted' and balance2 == 100
            ok_bal3, bal_key3, _ = AdminService.adjust_available_balance(7001, 7002, -9999, reason='too much')
            assert ok_bal3 is False and bal_key3 == 'admin_balance_adjust_invalid'

            logs = fetch_one('SELECT COUNT(*) AS cnt FROM admin_logs')
            assert logs is not None and int(logs['cnt']) >= 6
            dashboard = AdminService.get_dashboard_stats()
            assert dashboard['blocked_users'] == 0
            assert dashboard['queue_count'] == 0
            print('OK: stage 7 smoke test passed')
        finally:
            object.__setattr__(settings, 'db_path', original_db_path)
            object.__setattr__(settings, 'admin_ids', original_admin_ids)


if __name__ == '__main__':
    main()
