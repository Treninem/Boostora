from datetime import datetime, timedelta

from app import db
from app.services.wallets import WalletService


VIP_PLANS = {
    'vip_7': {
        'days': 7,
        'price': 900,
        'hold_speed_percent': 25,
        'active_task_limit_bonus': 2,
        'priority_level': 1,
        'referral_rate_bonus_bps': 200,
        'title_key': 'vip_plan_7_title',
        'desc_key': 'vip_plan_7_desc',
    },
    'vip_30': {
        'days': 30,
        'price': 2800,
        'hold_speed_percent': 50,
        'active_task_limit_bonus': 5,
        'priority_level': 2,
        'referral_rate_bonus_bps': 500,
        'title_key': 'vip_plan_30_title',
        'desc_key': 'vip_plan_30_desc',
    },
}


class VipService:
    @staticmethod
    def create_subscription(
        user_id: int,
        tier_code: str,
        duration_days: int,
        *,
        hold_speed_percent: int = 0,
        active_task_limit_bonus: int = 0,
        priority_level: int = 0,
        referral_rate_bonus_bps: int = 0,
    ) -> int:
        starts_at = datetime.utcnow()
        expires_at = starts_at + timedelta(days=duration_days)
        return db.execute(
            '''
            INSERT INTO vip_subscriptions (
                user_id,
                tier_code,
                duration_days,
                hold_speed_percent,
                active_task_limit_bonus,
                priority_level,
                referral_rate_bonus_bps,
                starts_at,
                expires_at,
                is_active
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            ''',
            (
                user_id,
                tier_code,
                duration_days,
                hold_speed_percent,
                active_task_limit_bonus,
                priority_level,
                referral_rate_bonus_bps,
                starts_at.isoformat(timespec='seconds'),
                expires_at.isoformat(timespec='seconds'),
            ),
        )

    @staticmethod
    def list_active_subscriptions(user_id: int):
        VipService.deactivate_expired(user_id)
        return db.fetch_all(
            '''
            SELECT * FROM vip_subscriptions
            WHERE user_id = ? AND is_active = 1
            ORDER BY expires_at DESC, id DESC
            ''',
            (user_id,),
        )

    @staticmethod
    def get_active_subscription(user_id: int):
        rows = VipService.list_active_subscriptions(user_id)
        return rows[0] if rows else None

    @staticmethod
    def deactivate_expired(user_id: int | None = None) -> None:
        if user_id is None:
            db.execute(
                '''
                UPDATE vip_subscriptions
                SET is_active = 0, updated_at = CURRENT_TIMESTAMP
                WHERE is_active = 1 AND expires_at <= CURRENT_TIMESTAMP
                '''
            )
            return
        db.execute(
            '''
            UPDATE vip_subscriptions
            SET is_active = 0, updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ? AND is_active = 1 AND expires_at <= CURRENT_TIMESTAMP
            ''',
            (user_id,),
        )

    @staticmethod
    def get_active_bonuses(user_id: int) -> dict[str, int]:
        subscriptions = VipService.list_active_subscriptions(user_id)
        if not subscriptions:
            return {
                'hold_speed_percent': 0,
                'active_task_limit_bonus': 0,
                'priority_level': 0,
                'referral_rate_bonus_bps': 0,
            }
        return {
            'hold_speed_percent': sum(int(item['hold_speed_percent']) for item in subscriptions),
            'active_task_limit_bonus': sum(int(item['active_task_limit_bonus']) for item in subscriptions),
            'priority_level': max(int(item['priority_level']) for item in subscriptions),
            'referral_rate_bonus_bps': sum(int(item['referral_rate_bonus_bps']) for item in subscriptions),
        }

    @staticmethod
    def get_vip_summary(user_id: int) -> dict[str, object]:
        bonuses = VipService.get_active_bonuses(user_id)
        subscriptions = VipService.list_active_subscriptions(user_id)
        return {
            'subscriptions': subscriptions,
            'hold_speed_percent': bonuses['hold_speed_percent'],
            'active_task_limit_bonus': bonuses['active_task_limit_bonus'],
            'priority_level': bonuses['priority_level'],
            'referral_rate_bonus_bps': bonuses['referral_rate_bonus_bps'],
        }

    @staticmethod
    def purchase_plan(user_id: int, plan_code: str) -> tuple[bool, str]:
        plan = VIP_PLANS.get(plan_code)
        if not plan:
            return False, 'vip_plan_not_found'
        spent = WalletService.spend_internal_balance(
            user_id,
            int(plan['price']),
            entry_type='vip_purchase',
            note=f'VIP purchase: {plan_code}',
        )
        if not spent:
            return False, 'vip_balance_low'
        VipService.create_subscription(
            user_id,
            plan_code,
            int(plan['days']),
            hold_speed_percent=int(plan['hold_speed_percent']),
            active_task_limit_bonus=int(plan['active_task_limit_bonus']),
            priority_level=int(plan['priority_level']),
            referral_rate_bonus_bps=int(plan['referral_rate_bonus_bps']),
        )
        return True, 'vip_purchase_success'

    @staticmethod
    def purchase_plan_with_stars(user_id: int, plan_code: str) -> tuple[bool, str]:
        plan = VIP_PLANS.get(plan_code)
        if not plan:
            return False, 'vip_plan_not_found'
        VipService.create_subscription(
            user_id,
            plan_code,
            int(plan['days']),
            hold_speed_percent=int(plan['hold_speed_percent']),
            active_task_limit_bonus=int(plan['active_task_limit_bonus']),
            priority_level=int(plan['priority_level']),
            referral_rate_bonus_bps=int(plan['referral_rate_bonus_bps']),
        )
        return True, 'vip_purchase_success'
