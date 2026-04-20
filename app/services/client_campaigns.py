import json
from typing import Any
from urllib.parse import urlparse

from app.services.campaigns import CampaignService
from app.services.economy import calculate_campaign_pricing, supported_task_types, task_meta
from app.services.input_sessions import InputSessionService
from app.services.wallets import WalletService

MODE_TARGET = 'campaign_target'
MODE_QUANTITY = 'campaign_quantity'
MODE_PRICE = 'campaign_price'
MODE_CONFIRM = 'campaign_confirm'
MODE_REWARD = MODE_PRICE

TASK_TYPES = supported_task_types()


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
        if not target or len(target) < 4 or len(target) > 255:
            return False, 'campaign_target_invalid', MODE_TARGET
        allowed_prefixes = ('http://', 'https://', 'tg://', '@')
        if not target.startswith(allowed_prefixes) and 't.me/' not in target:
            return False, 'campaign_target_invalid', MODE_TARGET
        draft['target_url'] = target
        InputSessionService.set_session(user_id, MODE_QUANTITY, json.dumps(draft, ensure_ascii=False))
        return True, 'campaign_target_saved', MODE_QUANTITY

    @staticmethod
    def consume_quantity(user_id: int, raw_quantity: str) -> tuple[bool, str, str]:
        draft = ClientCampaignService.get_draft(user_id)
        current_mode = ClientCampaignService.get_mode(user_id)
        if not draft or current_mode != MODE_QUANTITY:
            return False, 'campaign_draft_missing', MODE_QUANTITY
        value = raw_quantity.strip()
        if not value.isdigit():
            return False, 'campaign_quantity_invalid', MODE_QUANTITY
        total_quantity = int(value)
        if total_quantity <= 0 or total_quantity > 100000:
            return False, 'campaign_quantity_invalid', MODE_QUANTITY
        floor = calculate_campaign_pricing(str(draft['task_type']), total_quantity)
        draft['total_quantity'] = total_quantity
        draft['client_floor_price'] = int(floor['client_floor_price'])
        draft['performer_floor_reward'] = int(floor['performer_floor_reward'])
        draft['discount_percent'] = int(floor['discount_percent'])
        draft['base_client_floor_price'] = int(floor['base_client_floor_price'])
        InputSessionService.set_session(user_id, MODE_PRICE, json.dumps(draft, ensure_ascii=False))
        return True, 'campaign_quantity_saved', MODE_PRICE

    @staticmethod
    def consume_reward(user_id: int, raw_reward: str) -> tuple[bool, str, str]:
        return ClientCampaignService.consume_price(user_id, raw_reward)

    @staticmethod
    def consume_price(user_id: int, raw_price: str) -> tuple[bool, str, str]:
        draft = ClientCampaignService.get_draft(user_id)
        current_mode = ClientCampaignService.get_mode(user_id)
        if not draft or current_mode not in {MODE_PRICE, MODE_REWARD}:
            return False, 'campaign_draft_missing', MODE_PRICE
        value = raw_price.strip().lower()
        if value in {'0', 'auto', 'авто'}:
            selected_unit_price = None
        else:
            if not value.isdigit():
                return False, 'campaign_price_invalid', MODE_PRICE
            selected_unit_price = int(value)
        try:
            pricing = calculate_campaign_pricing(str(draft['task_type']), int(draft['total_quantity']), selected_unit_price)
        except ValueError:
            return False, 'campaign_price_below_floor', MODE_PRICE
        draft['reward_amount'] = int(pricing['performer_reward'])
        draft['unit_price'] = int(pricing['client_unit_price'])
        draft['budget_total'] = int(pricing['budget_total'])
        draft['reward_budget_total'] = int(pricing['reward_budget_total'])
        draft['service_fee_total'] = int(pricing['service_fee_total'])
        draft['service_fee_unit'] = int(pricing['service_fee_unit'])
        draft['discount_percent'] = int(pricing['discount_percent'])
        draft['client_floor_price'] = int(pricing['client_floor_price'])
        draft['performer_floor_reward'] = int(pricing['performer_floor_reward'])
        draft['base_client_floor_price'] = int(pricing['base_client_floor_price'])
        draft['speed_index'] = int(pricing['speed_index'])
        InputSessionService.set_session(user_id, MODE_CONFIRM, json.dumps(draft, ensure_ascii=False))
        return True, 'campaign_price_saved', MODE_CONFIRM

    @staticmethod
    def finalize_draft(user_id: int, launch_now: bool) -> tuple[bool, str, int | None]:
        draft = ClientCampaignService.get_draft(user_id)
        if not draft or ClientCampaignService.get_mode(user_id) != MODE_CONFIRM:
            return False, 'campaign_draft_missing', None
        required = ('task_type', 'target_url', 'reward_amount', 'total_quantity', 'budget_total', 'unit_price')
        if any(key not in draft for key in required):
            return False, 'campaign_draft_missing', None
        budget_total = int(draft['budget_total'])
        if launch_now and int(WalletService.get_summary(user_id)['campaign_balance']) < budget_total:
            return False, 'campaign_balance_low', None
        title = ClientCampaignService.build_default_title(str(draft['task_type']), str(draft['target_url']))
        campaign_id = CampaignService.create_campaign(
            owner_user_id=user_id,
            title=title,
            task_type=str(draft['task_type']),
            target_url=str(draft['target_url']),
            reward_amount=int(draft['reward_amount']),
            unit_price=int(draft['unit_price']),
            reward_budget_total=int(draft['reward_budget_total']),
            service_fee_total=int(draft['service_fee_total']),
            pricing_snapshot={
                'discount_percent': int(draft['discount_percent']),
                'base_client_floor_price': int(draft['base_client_floor_price']),
                'client_floor_price': int(draft['client_floor_price']),
                'client_unit_price': int(draft['unit_price']),
                'performer_reward': int(draft['reward_amount']),
                'performer_floor_reward': int(draft['performer_floor_reward']),
                'service_fee_unit': int(draft['service_fee_unit']),
                'speed_index': int(draft['speed_index']),
            },
            total_quantity=int(draft['total_quantity']),
            status='draft',
            is_funded=False,
        )
        if launch_now:
            ok, result_key = CampaignService.update_status(user_id, campaign_id, 'active')
            if not ok:
                return False, result_key, None
        InputSessionService.clear_session(user_id)
        return True, 'campaign_created_active' if launch_now else 'campaign_created_draft', campaign_id

    @staticmethod
    def build_default_title(task_type: str, target_url: str) -> str:
        try:
            label = str(task_meta(task_type)['title'])
        except Exception:
            label = task_type
        host = target_url
        if target_url.startswith('@'):
            host = target_url
        else:
            parsed = urlparse(target_url if '://' in target_url else f'https://{target_url}')
            if parsed.netloc == 't.me' and parsed.path:
                host = f"t.me{parsed.path}"
            else:
                host = parsed.netloc or parsed.path or target_url
        short_host = host.replace('www.', '')[:40]
        return f"{label} · {short_host}"
