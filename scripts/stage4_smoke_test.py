import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault('BOT_TOKEN', 'dummy-token-for-local-tests')

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import db
from app.config import settings
from app.db import fetch_all, fetch_one, init_db
from app.services.performer import PerformerService
from app.services.users import UserService
from app.services.wallets import WalletService



def main() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        db_file = Path(temp_dir) / 'stage4.db'
        original_db_path = settings.db_path
        original_hold_hours = settings.default_hold_hours
        object.__setattr__(settings, 'db_path', str(db_file))
        object.__setattr__(settings, 'default_hold_hours', 1)
        try:
            init_db()
            performer = SimpleNamespace(id=4001, username='worker', first_name='Work', last_name='Er')
            UserService.ensure_user(performer)
            UserService.set_language(4001, 'en')
            UserService.set_role(4001, 'performer')

            tasks = PerformerService.list_available_tasks(4001)
            assert len(tasks) >= 3
            first_campaign_id = int(tasks[0]['id'])

            ok, result_key, submission_id = PerformerService.take_task(4001, first_campaign_id)
            assert ok is True and result_key == 'task_taken' and submission_id is not None

            ok_repeat, repeat_key, _ = PerformerService.take_task(4001, first_campaign_id)
            assert ok_repeat is False and repeat_key == 'task_repeat_blocked'

            extra_ids = [int(task['id']) for task in tasks[1:4]]
            for campaign_id in extra_ids[:2]:
                ok_take, _, _ = PerformerService.take_task(4001, campaign_id)
                assert ok_take is True
            ok_limit, limit_key, _ = PerformerService.take_task(4001, extra_ids[2])
            assert ok_limit is False and limit_key == 'task_limit_reached'

            ok_submit, submit_key, hold_id = PerformerService.submit_proof(4001, int(submission_id), '@worker proof')
            assert ok_submit is True and submit_key == 'proof_accepted' and hold_id is not None

            wallet = WalletService.get_summary(4001)
            assert wallet['hold_balance'] == int(tasks[0]['reward_amount'])
            assert wallet['available_balance'] == 0
            assert wallet['lifetime_earned'] == int(tasks[0]['reward_amount'])

            submission = fetch_one('SELECT * FROM task_submissions WHERE id = ?', (submission_id,))
            assert submission is not None and str(submission['status']) == 'approved'

            campaign = fetch_one('SELECT * FROM campaigns WHERE id = ?', (first_campaign_id,))
            assert campaign is not None and int(campaign['completed_quantity']) == 1

            db.execute(
                "UPDATE holds SET release_at = '2000-01-01T00:00:00' WHERE id = ?",
                (hold_id,),
            )
            released = PerformerService.release_due_holds(4001)
            assert released == 1

            wallet_after = WalletService.get_summary(4001)
            assert wallet_after['hold_balance'] == 0
            assert wallet_after['available_balance'] == int(tasks[0]['reward_amount'])

            tx_count = fetch_one('SELECT COUNT(*) AS cnt FROM transactions WHERE user_id = ?', (4001,))
            assert tx_count is not None and int(tx_count['cnt']) >= 2
            assert len(fetch_all('SELECT * FROM holds WHERE user_id = ?', (4001,))) == 1
            print('OK: stage 4 smoke test passed')
        finally:
            object.__setattr__(settings, 'db_path', original_db_path)
            object.__setattr__(settings, 'default_hold_hours', original_hold_hours)


if __name__ == '__main__':
    main()
