import json
from typing import Any
from urllib.parse import urlparse

from app.services.activity import ActivityService
from app.services.campaigns import CampaignService
from app.services.economy import calculate_campaign_pricing, recommend_unit_prices, supported_task_types, task_meta
from app.services.engagement_modes import EngagementModeService
from app.services.input_sessions import InputSessionService
from app.services.wallets import WalletService

MODE_TARGET = 'campaign_target'
MODE_QUANTITY = 'campaign_quantity'
MODE_PRICE = 'campaign_price'
MODE_CONFIRM = 'campaign_confirm'
MODE_REWARD = MODE_PRICE

TASK_TYPES = supported_task_types()

CHAT_REQUIRED_TASK_TYPES = {
    'channel_subscribe', 'chat_join', 'post_view', 'post_like', 'post_reaction',
    'story_view', 'post_share', 'post_comment', 'poll_vote'
}
ADMIN_REQUIRED_TASK_TYPES = {'channel_subscribe', 'chat_join', 'post_reaction', 'poll_vote'}
MESSAGE_LINK_TASK_TYPES = {'post_view', 'post_like', 'post_reaction', 'post_share', 'post_comment', 'poll_vote'}


class ClientCampaignService:
    @staticmethod
    def clear_draft(user_id: int) -> None:
        session = InputSessionService.get_session(user_id)
        if session and str(session['mode']).startswith('campaign_'):
            InputSessionService.clear_session(user_id)

    @staticmethod
    def start_draft(user_id: int, task_type: str, engagement_mode: str | None = None) -> tuple[bool, str]:
        if task_type not in TASK_TYPES:
            return False, 'campaign_invalid_task_type'
        payload = {'task_type': task_type}
        if engagement_mode:
            payload['engagement_mode'] = str(engagement_mode)
            payload['reciprocal_required_actions'] = EngagementModeService.required_actions() if str(engagement_mode) == 'standard' else 0
        InputSessionService.set_session(user_id, MODE_TARGET, json.dumps(payload, ensure_ascii=False))
        return True, 'campaign_type_saved'

    @staticmethod
    def start_preset(user_id: int, task_type: str, quantity: int, preset_code: str = '', engagement_mode: str | None = None) -> tuple[bool, str]:
        """Start a campaign draft with a preselected quantity.

        The user still has to provide the target link and price, so this does
        not bypass wallet, proof, hold, moderation or antifraud logic. It only
        removes one repetitive input step for common engagement products.
        """
        if task_type not in TASK_TYPES:
            return False, 'campaign_invalid_task_type'
        if int(quantity) <= 0 or int(quantity) > 100000:
            return False, 'campaign_quantity_invalid'
        payload = {
            'task_type': task_type,
            'preset_code': str(preset_code or ''),
            'preset_quantity': int(quantity),
        }
        if engagement_mode:
            payload['engagement_mode'] = str(engagement_mode)
            payload['reciprocal_required_actions'] = EngagementModeService.required_actions() if str(engagement_mode) == 'standard' else 0
        InputSessionService.set_session(user_id, MODE_TARGET, json.dumps(payload, ensure_ascii=False))
        return True, 'engagement_preset_started'

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
    def _normalize_target(target: str) -> str:
        value = (target or '').strip()
        if value.startswith('t.me/'):
            return f'https://{value}'
        return value

    @staticmethod
    def _get_bot_membership(bot, chat_ref: str) -> tuple[bool, str, str]:
        if bot is None:
            return True, '', ''
        try:
            me = bot.get_me()
            me_id = int(me.id)
            api_ref = int(chat_ref) if chat_ref.lstrip('-').isdigit() else chat_ref
            member = bot.get_chat_member(api_ref, me_id)
            status = str(getattr(member, 'status', '') or '')
            if status not in {'member', 'administrator', 'creator'}:
                return False, 'campaign_target_bot_not_in_chat', status
            if status in {'administrator', 'creator'}:
                return True, '', status
            return True, 'campaign_target_admin_recommended', status
        except Exception:
            return False, 'campaign_target_bot_not_in_chat', ''

    @staticmethod
    def consume_target(user_id: int, raw_target: str, bot=None) -> tuple[bool, str, str]:
        draft = ClientCampaignService.get_draft(user_id)
        if not draft or ClientCampaignService.get_mode(user_id) != MODE_TARGET:
            return False, 'campaign_draft_missing', MODE_TARGET
        task_type = str(draft.get('task_type') or '')
        target = ClientCampaignService._normalize_target(raw_target)
        if not target or len(target) < 4 or len(target) > 255:
            return False, 'campaign_target_invalid', MODE_TARGET
        allowed_prefixes = ('http://', 'https://', 'tg://', '@')
        if not target.startswith(allowed_prefixes) and 't.me/' not in target:
            return False, 'campaign_target_invalid', MODE_TARGET

        info = ActivityService.parse_target(target)
        result_key = 'campaign_target_saved'

        if task_type in MESSAGE_LINK_TASK_TYPES and info.message_id is None:
            return False, 'campaign_target_message_link_required', MODE_TARGET

        if task_type in CHAT_REQUIRED_TASK_TYPES:
            if not info.chat_ref:
                return False, 'campaign_target_chat_ref_required', MODE_TARGET
            ok_membership, status_key, _status = ClientCampaignService._get_bot_membership(bot, info.chat_ref)
            if not ok_membership:
                return False, status_key, MODE_TARGET
            if task_type in ADMIN_REQUIRED_TASK_TYPES and status_key == 'campaign_target_admin_recommended':
                return False, 'campaign_target_admin_required', MODE_TARGET
            if status_key:
                result_key = status_key

        if task_type == 'bot_start':
            if not info.bot_username or not info.start_param:
                return False, 'campaign_target_bot_start_invalid', MODE_TARGET

        if task_type == 'mini_app_open':
            if not info.bot_username or not info.webapp_hint:
                return False, 'campaign_target_mini_app_invalid', MODE_TARGET
            result_key = 'campaign_target_saved_miniapp'

        draft['target_url'] = target
        preset_quantity = draft.get('preset_quantity')
        if str(preset_quantity or '').isdigit():
            total_quantity = int(preset_quantity)
            if 0 < total_quantity <= 100000:
                floor = calculate_campaign_pricing(str(draft['task_type']), total_quantity)
                draft['total_quantity'] = total_quantity
                draft['client_floor_price'] = int(floor['client_floor_price'])
                draft['performer_floor_reward'] = int(floor['performer_floor_reward'])
                draft['discount_percent'] = int(floor['discount_percent'])
                draft['base_client_floor_price'] = int(floor['base_client_floor_price'])
                draft['recommended_unit_price'] = int(floor['recommended_unit_price'])
                draft['fast_unit_price'] = int(floor['fast_unit_price'])
                draft['priority_unit_price'] = int(floor['priority_unit_price'])
                InputSessionService.set_session(user_id, MODE_PRICE, json.dumps(draft, ensure_ascii=False))
                return True, 'campaign_target_preset_quantity_saved', MODE_PRICE
        InputSessionService.set_session(user_id, MODE_QUANTITY, json.dumps(draft, ensure_ascii=False))
        return True, result_key, MODE_QUANTITY

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
        draft['recommended_unit_price'] = int(floor['recommended_unit_price'])
        draft['fast_unit_price'] = int(floor['fast_unit_price'])
        draft['priority_unit_price'] = int(floor['priority_unit_price'])
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
        draft['price_position_percent'] = int(pricing['price_position_percent'])
        draft['recommended_unit_price'] = int(pricing['recommended_unit_price'])
        draft['fast_unit_price'] = int(pricing['fast_unit_price'])
        draft['priority_unit_price'] = int(pricing['priority_unit_price'])
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
                'price_position_percent': int(draft.get('price_position_percent') or 0),
                'recommended_unit_price': int(draft.get('recommended_unit_price') or draft['unit_price']),
                'fast_unit_price': int(draft.get('fast_unit_price') or draft['unit_price']),
                'priority_unit_price': int(draft.get('priority_unit_price') or draft['unit_price']),
                'engagement_mode': str(draft.get('engagement_mode') or ''),
                'reciprocal_required_actions': int(draft.get('reciprocal_required_actions') or 0),
            },
            total_quantity=int(draft['total_quantity']),
            status='draft',
            is_funded=False,
        )
        if launch_now:
            ok, result_key = CampaignService.update_status(user_id, campaign_id, 'active')
            if not ok:
                return False, result_key, None
        if launch_now and str(draft.get('engagement_mode') or '') == 'standard':
            EngagementModeService.create_obligation_for_campaign(user_id, campaign_id, str(draft['task_type']), int(draft['total_quantity']))
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
