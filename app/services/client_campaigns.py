import json
from typing import Any
from urllib.parse import urlparse

from app.services.campaigns import CampaignService
from app.services.input_sessions import InputSessionService

MODE_TARGET = 'campaign_target'
MODE_REWARD = 'campaign_reward'
MODE_QUANTITY = 'campaign_quantity'
MODE_CONFIRM = 'campaign_confirm'

TASK_TYPES = (
    'channel_subscribe',
    'chat_join',
    'post_view',
    'bot_start',
    'mini_app_open',
)


class ClientCampaignService:
    @staticmethod
    def clear_draft(user_id: int) -> None:
        session = InputSessionService.get_session(user_id)
        if session and str(session['mode']).startswith('campaign_'):
            InputSessionService.clear_session(user_id)

    @staticmethod
    def start_draft(user_id: int, task_type: str) -> tuple[bool, str]:
        if task_type not in TASK_TYPES:
            return False, 'campaign_invalid_task_type'
        payload = {'task_type': task_type}
        InputSessionService.set_session(user_id, MODE_TARGET, json.dumps(payload, ensure_ascii=False))
        return True, 'campaign_type_saved'

    @staticmethod
    def get_draft(user_id: int) -> dict[str, Any] | None:
        session = InputSessionService.get_session(user_id)
        if not session:
            return None
        mode = str(session['mode'])
        if not mode.startswith('campaign_'):
            return None
        payload_raw = str(session['payload'] or '').strip()
        payload: dict[str, Any] = {}
        if payload_raw:
            try:
                payload = json.loads(payload_raw)
            except json.JSONDecodeError:
                payload = {}
        payload['mode'] = mode
        return payload

    @staticmethod
    def get_mode(user_id: int) -> str | None:
        draft = ClientCampaignService.get_draft(user_id)
        if not draft:
            return None
        return str(draft.get('mode') or '')

    @staticmethod
    def consume_target(user_id: int, raw_target: str) -> tuple[bool, str, str]:
        draft = ClientCampaignService.get_draft(user_id)
        if not draft or ClientCampaignService.get_mode(user_id) != MODE_TARGET:
            return False, 'campaign_draft_missing', MODE_TARGET
        target = raw_target.strip()
        if not target:
            return False, 'campaign_target_invalid', MODE_TARGET
        if len(target) < 4 or len(target) > 255:
            return False, 'campaign_target_invalid', MODE_TARGET
        allowed_prefixes = ('http://', 'https://', 'tg://', '@')
        if not target.startswith(allowed_prefixes) and 't.me/' not in target:
            return False, 'campaign_target_invalid', MODE_TARGET
        draft['target_url'] = target
        InputSessionService.set_session(user_id, MODE_REWARD, json.dumps(draft, ensure_ascii=False))
        return True, 'campaign_target_saved', MODE_REWARD

    @staticmethod
    def consume_reward(user_id: int, raw_reward: str) -> tuple[bool, str, str]:
        draft = ClientCampaignService.get_draft(user_id)
        if not draft or ClientCampaignService.get_mode(user_id) != MODE_REWARD:
            return False, 'campaign_draft_missing', MODE_REWARD
        value = raw_reward.strip()
        if not value.isdigit():
            return False, 'campaign_reward_invalid', MODE_REWARD
        reward_amount = int(value)
        if reward_amount <= 0 or reward_amount > 100000:
            return False, 'campaign_reward_invalid', MODE_REWARD
        draft['reward_amount'] = reward_amount
        InputSessionService.set_session(user_id, MODE_QUANTITY, json.dumps(draft, ensure_ascii=False))
        return True, 'campaign_reward_saved', MODE_QUANTITY

    @staticmethod
    def consume_quantity(user_id: int, raw_quantity: str) -> tuple[bool, str, str]:
        draft = ClientCampaignService.get_draft(user_id)
        if not draft or ClientCampaignService.get_mode(user_id) != MODE_QUANTITY:
            return False, 'campaign_draft_missing', MODE_QUANTITY
        value = raw_quantity.strip()
        if not value.isdigit():
            return False, 'campaign_quantity_invalid', MODE_QUANTITY
        total_quantity = int(value)
        if total_quantity <= 0 or total_quantity > 100000:
            return False, 'campaign_quantity_invalid', MODE_QUANTITY
        draft['total_quantity'] = total_quantity
        draft['budget_total'] = int(draft['reward_amount']) * int(total_quantity)
        InputSessionService.set_session(user_id, MODE_CONFIRM, json.dumps(draft, ensure_ascii=False))
        return True, 'campaign_quantity_saved', MODE_CONFIRM

    @staticmethod
    def finalize_draft(user_id: int, launch_now: bool) -> tuple[bool, str, int | None]:
        draft = ClientCampaignService.get_draft(user_id)
        if not draft or ClientCampaignService.get_mode(user_id) != MODE_CONFIRM:
            return False, 'campaign_draft_missing', None
        required = ('task_type', 'target_url', 'reward_amount', 'total_quantity')
        if any(key not in draft for key in required):
            return False, 'campaign_draft_missing', None
        title = ClientCampaignService.build_default_title(str(draft['task_type']), str(draft['target_url']))
        campaign_id = CampaignService.create_campaign(
            owner_user_id=user_id,
            title=title,
            task_type=str(draft['task_type']),
            target_url=str(draft['target_url']),
            reward_amount=int(draft['reward_amount']),
            total_quantity=int(draft['total_quantity']),
            status='active' if launch_now else 'draft',
        )
        InputSessionService.clear_session(user_id)
        return True, 'campaign_created_active' if launch_now else 'campaign_created_draft', campaign_id

    @staticmethod
    def build_default_title(task_type: str, target_url: str) -> str:
        labels = {
            'channel_subscribe': 'Channel subscribe',
            'chat_join': 'Chat join',
            'post_view': 'Post view',
            'bot_start': 'Bot start',
            'mini_app_open': 'Mini App open',
        }
        host = target_url
        if target_url.startswith('@'):
            host = target_url
        else:
            parsed = urlparse(target_url if '://' in target_url else f'https://{target_url}')
            host = parsed.netloc or parsed.path or target_url
        short_host = host.replace('www.', '')[:40]
        return f"{labels.get(task_type, task_type)} · {short_host}"
