from __future__ import annotations

from app import db
from app.services.telegram_monetization import TelegramMonetizationService
from app.services.wallets import WalletService

PREMIUM_PLANS = {
    3: {'stars': 1000, 'sparks_cost': 22000, 'label': 'Telegram Premium 3 мес.'},
    6: {'stars': 1500, 'sparks_cost': 31500, 'label': 'Telegram Premium 6 мес.'},
    12: {'stars': 2500, 'sparks_cost': 50000, 'label': 'Telegram Premium 12 мес.'},
}

CASHOUT_PACKS = {}

GIFT_SPARKS_PER_STAR = 18


class RedemptionService:
    @staticmethod
    def access_allowed(user_id: int) -> bool:
        return WalletService.has_paid_stars_topup(user_id)

    @staticmethod
    def list_gifts(limit: int = 3) -> list[dict]:
        gifts = TelegramMonetizationService.get_available_gifts()
        for item in gifts:
            item['sparks_cost'] = int(item['star_count']) * GIFT_SPARKS_PER_STAR
        return gifts[:limit]

    @staticmethod
    def premium_offers() -> dict[int, dict]:
        return PREMIUM_PLANS

    @staticmethod
    def cashout_offers() -> dict[int, dict]:
        return CASHOUT_PACKS

    @staticmethod
    def purchase_premium(user_id: int, months: int) -> tuple[bool, str]:
        plan = PREMIUM_PLANS.get(months)
        if not plan:
            return False, 'redeem_offer_not_found'
        if not RedemptionService.access_allowed(user_id):
            return False, 'redeem_access_denied'
        spent = WalletService.spend_internal_balance(
            user_id,
            int(plan['sparks_cost']),
            entry_type='premium_redeem',
            note=f'Premium redeem {months}m',
        )
        if not spent:
            return False, 'redeem_balance_low'
        ok, result = TelegramMonetizationService.gift_premium(
            user_id=user_id,
            month_count=months,
            text='Обмен Искр на Telegram Premium',
        )
        if not ok:
            WalletService.credit_internal_balance(user_id, int(plan['sparks_cost']), entry_type='premium_refund', note=f'Refund after premium error: {result}')
            return False, 'redeem_telegram_failed'
        db.execute(
            """
            INSERT INTO redemptions (user_id, kind, reference, stars_cost, sparks_cost, status, note)
            VALUES (?, 'premium', ?, ?, ?, 'completed', ?)
            """,
            (user_id, str(months), int(plan['stars']), int(plan['sparks_cost']), f'Premium {months} months'),
        )
        return True, 'premium_redeem_success'

    @staticmethod
    def purchase_gift_by_index(user_id: int, offer_index: int) -> tuple[bool, str]:
        gifts = RedemptionService.list_gifts(limit=10)
        if offer_index < 0 or offer_index >= len(gifts):
            return False, 'redeem_offer_not_found'
        if not RedemptionService.access_allowed(user_id):
            return False, 'redeem_access_denied'
        gift = gifts[offer_index]
        sparks_cost = int(gift['sparks_cost'])
        spent = WalletService.spend_internal_balance(
            user_id,
            sparks_cost,
            entry_type='gift_redeem',
            note=f"Gift redeem {gift['id']}",
        )
        if not spent:
            return False, 'redeem_balance_low'
        ok, result = TelegramMonetizationService.send_gift(
            user_id=user_id,
            gift_id=str(gift['id']),
            text='Подарок за Искры',
        )
        if not ok:
            WalletService.credit_internal_balance(user_id, sparks_cost, entry_type='gift_refund', note=f'Refund after gift error: {result}')
            return False, 'redeem_telegram_failed'
        db.execute(
            """
            INSERT INTO redemptions (user_id, kind, reference, stars_cost, sparks_cost, status, note)
            VALUES (?, 'gift', ?, ?, ?, 'completed', ?)
            """,
            (user_id, str(gift['id']), int(gift['star_count']), sparks_cost, 'Gift sent by bot'),
        )
        return True, 'gift_redeem_success'

    @staticmethod
    def create_cashout_request(user_id: int, stars_amount: int) -> tuple[bool, str, int | None]:
        offer = CASHOUT_PACKS.get(stars_amount)
        if not offer:
            return False, 'redeem_offer_not_found', None
        if not RedemptionService.access_allowed(user_id):
            return False, 'redeem_access_denied', None
        sparks_cost = int(offer['sparks_cost'])
        spent = WalletService.spend_internal_balance(
            user_id,
            sparks_cost,
            entry_type='cashout_request',
            note=f'Cashout request {stars_amount} XTR',
        )
        if not spent:
            return False, 'redeem_balance_low', None
        redemption_id = db.execute(
            """
            INSERT INTO redemptions (user_id, kind, reference, stars_cost, sparks_cost, status, note)
            VALUES (?, 'cashout', ?, ?, ?, 'pending', ?)
            """,
            (user_id, str(stars_amount), int(stars_amount), sparks_cost, 'Manual payout request'),
        )
        return True, 'cashout_request_created', redemption_id
