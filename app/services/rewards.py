from app.services.vip import VipService
from app.services.wallets import WalletService


REWARD_ITEMS = {
    'boost_hold_3d': {
        'price': 220,
        'days': 3,
        'hold_speed_percent': 15,
        'active_task_limit_bonus': 0,
        'priority_level': 0,
        'referral_rate_bonus_bps': 0,
        'title_key': 'reward_hold_boost_title',
        'desc_key': 'reward_hold_boost_desc',
    },
    'boost_slots_3d': {
        'price': 320,
        'days': 3,
        'hold_speed_percent': 0,
        'active_task_limit_bonus': 1,
        'priority_level': 0,
        'referral_rate_bonus_bps': 0,
        'title_key': 'reward_slots_boost_title',
        'desc_key': 'reward_slots_boost_desc',
    },
    'boost_priority_3d': {
        'price': 420,
        'days': 3,
        'hold_speed_percent': 0,
        'active_task_limit_bonus': 0,
        'priority_level': 1,
        'referral_rate_bonus_bps': 100,
        'title_key': 'reward_priority_boost_title',
        'desc_key': 'reward_priority_boost_desc',
    },
}


class RewardService:
    @staticmethod
    def get_items() -> dict[str, dict[str, int | str]]:
        return REWARD_ITEMS

    @staticmethod
    def claim_demo_topup(user_id: int) -> tuple[bool, str]:
        return False, 'demo_topup_disabled'

    @staticmethod
    def purchase_item(user_id: int, item_code: str) -> tuple[bool, str]:
        item = REWARD_ITEMS.get(item_code)
        if not item:
            return False, 'reward_item_not_found'
        spent = WalletService.spend_internal_balance(
            user_id,
            int(item['price']),
            entry_type='reward_purchase',
            note=f'Reward purchase: {item_code}',
        )
        if not spent:
            return False, 'reward_balance_low'
        VipService.create_subscription(
            user_id,
            tier_code=item_code,
            duration_days=int(item['days']),
            hold_speed_percent=int(item['hold_speed_percent']),
            active_task_limit_bonus=int(item['active_task_limit_bonus']),
            priority_level=int(item['priority_level']),
            referral_rate_bonus_bps=int(item['referral_rate_bonus_bps']),
        )
        return True, 'reward_purchase_success'
