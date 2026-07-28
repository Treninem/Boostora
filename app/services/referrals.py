from app import db
from app.config import settings
from app.services.vip import VipService
from app.services.wallets import WalletService


BASE_REFERRAL_RATE_BPS = 500
REFERRAL_REWARD_CAP = 100000


class ReferralService:
    @staticmethod
    def bind_referral(referrer_user_id: int, referred_user_id: int, reward_rate_bps: int = BASE_REFERRAL_RATE_BPS) -> int:
        return db.execute(
            '''
            INSERT INTO referrals (referrer_user_id, referred_user_id, reward_rate_bps)
            VALUES (?, ?, ?)
            ON CONFLICT(referred_user_id) DO NOTHING
            ''',
            (referrer_user_id, referred_user_id, reward_rate_bps),
        )

    @staticmethod
    def try_bind_referral(referrer_user_id: int, referred_user_id: int) -> bool:
        if referrer_user_id == referred_user_id:
            return False
        referrer = db.get_user(referrer_user_id)
        referred = db.get_user(referred_user_id)
        if not referrer or not referred:
            return False
        existing = db.fetch_one(
            'SELECT id FROM referrals WHERE referred_user_id = ? LIMIT 1',
            (referred_user_id,),
        )
        if existing:
            return False
        bonus_bps = VipService.get_active_bonuses(referrer_user_id)['referral_rate_bonus_bps']
        ReferralService.bind_referral(referrer_user_id, referred_user_id, BASE_REFERRAL_RATE_BPS + bonus_bps)
        db.execute(
            '''
            UPDATE users
            SET referred_by_user_id = ?, updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ? AND referred_by_user_id IS NULL
            ''',
            (referrer_user_id, referred_user_id),
        )
        return True

    @staticmethod
    def get_referrals(referrer_user_id: int):
        return db.fetch_all(
            '''
            SELECT r.*, u.username, u.first_name, u.last_name, u.created_at AS joined_at
            FROM referrals r
            JOIN users u ON u.user_id = r.referred_user_id
            WHERE r.referrer_user_id = ?
            ORDER BY r.created_at DESC, r.id DESC
            ''',
            (referrer_user_id,),
        )

    @staticmethod
    def get_summary(referrer_user_id: int) -> dict[str, object]:
        rows = ReferralService.get_referrals(referrer_user_id)
        total_earned = sum(int(row['total_earned']) for row in rows)
        bonuses = VipService.get_active_bonuses(referrer_user_id)
        current_rate_bps = BASE_REFERRAL_RATE_BPS + bonuses['referral_rate_bonus_bps']
        return {
            'rows': rows,
            'invited_count': len(rows),
            'total_earned': total_earned,
            'current_rate_bps': current_rate_bps,
            'current_rate_percent': current_rate_bps / 100,
            'link': ReferralService.build_referral_link(referrer_user_id),
        }

    @staticmethod
    def build_referral_link(referrer_user_id: int) -> str:
        username = settings.support_username.strip().lstrip('@')
        return f'https://t.me/{username}?start=ref_{referrer_user_id}'

    @staticmethod
    def reward_for_submission(referred_user_id: int, base_reward_amount: int) -> int:
        if base_reward_amount <= 0:
            return 0
        referral = db.fetch_one(
            'SELECT * FROM referrals WHERE referred_user_id = ? LIMIT 1',
            (referred_user_id,),
        )
        if not referral:
            return 0
        reward_amount = min((base_reward_amount * int(referral['reward_rate_bps'])) // 10000, REFERRAL_REWARD_CAP)
        if reward_amount <= 0:
            return 0
        referrer_user_id = int(referral['referrer_user_id'])
        WalletService.credit_bonus_balance(
            referrer_user_id,
            reward_amount,
            entry_type='referral_bonus',
            note=f'Referral bonus from user {referred_user_id}',
        )
        db.execute(
            '''
            UPDATE referrals
            SET total_earned = total_earned + ?, updated_at = CURRENT_TIMESTAMP
            WHERE referred_user_id = ?
            ''',
            (reward_amount, referred_user_id),
        )
        return reward_amount
