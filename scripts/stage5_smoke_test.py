import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault('BOT_TOKEN', 'dummy-token-for-local-tests')

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import settings
from app.db import init_db
from app.services.campaigns import CampaignService
from app.services.client_campaigns import ClientCampaignService
from app.services.users import UserService



def main() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        db_file = Path(temp_dir) / 'stage5.db'
        original_db_path = settings.db_path
        object.__setattr__(settings, 'db_path', str(db_file))
        try:
            init_db()
            client = SimpleNamespace(id=5001, username='client', first_name='Cli', last_name='Ent')
            UserService.ensure_user(client)
            UserService.set_language(5001, 'ru')
            UserService.set_role(5001, 'client')

            ok_type, key_type = ClientCampaignService.start_draft(5001, 'chat_join')
            assert ok_type is True and key_type == 'campaign_type_saved'

            ok_target, key_target, mode_target = ClientCampaignService.consume_target(5001, 'https://t.me/+abcdef')
            assert ok_target is True and key_target == 'campaign_target_saved'

            ok_reward, key_reward, mode_reward = ClientCampaignService.consume_reward(5001, '25')
            assert ok_reward is True and key_reward == 'campaign_reward_saved'

            ok_qty, key_qty, mode_qty = ClientCampaignService.consume_quantity(5001, '12')
            assert ok_qty is True and key_qty == 'campaign_quantity_saved'

            ok_create, create_key, campaign_id = ClientCampaignService.finalize_draft(5001, launch_now=True)
            assert ok_create is True and create_key == 'campaign_created_active' and campaign_id is not None

            created = CampaignService.get_owned_campaign(5001, int(campaign_id))
            assert created is not None
            assert str(created['status']) == 'active'
            assert int(created['budget_total']) == 300

            campaigns = CampaignService.get_campaigns_for_owner(5001)
            assert len(campaigns) == 1

            ok_pause, pause_key = CampaignService.update_status(5001, int(campaign_id), 'paused')
            assert ok_pause is True and pause_key == 'campaign_paused'
            paused = CampaignService.get_owned_campaign(5001, int(campaign_id))
            assert paused is not None and str(paused['status']) == 'paused'

            ok_resume, resume_key = CampaignService.update_status(5001, int(campaign_id), 'active')
            assert ok_resume is True and resume_key == 'campaign_resumed'
            active_again = CampaignService.get_owned_campaign(5001, int(campaign_id))
            assert active_again is not None and str(active_again['status']) == 'active'

            stats = CampaignService.get_owner_stats(5001)
            assert stats['total_campaigns'] == 1
            assert stats['active_campaigns'] == 1
            assert stats['budget_total'] == 300
            assert stats['budget_remaining'] == 300
            print('OK: stage 5 smoke test passed')
        finally:
            object.__setattr__(settings, 'db_path', original_db_path)


if __name__ == '__main__':
    main()
