import json
import sqlite3

from app import db
from app.services.runtime_settings import RuntimeSettingsService
from app.services.wallets import WalletService


CAMPAIGN_STATUSES = {'draft', 'active', 'paused', 'completed', 'archived'}


class CampaignService:
    @staticmethod
    def create_campaign(
        owner_user_id: int,
        task_type: str,
        target_url: str,
        reward_amount: int,
        total_quantity: int,
        *,
        title: str | None = None,
        status: str = 'draft',
        unit_price: int = 0,
        reward_budget_total: int = 0,
        service_fee_total: int = 0,
        pricing_snapshot: dict | None = None,
        is_funded: bool = False,
    ) -> int:
        budget_total = int(reward_budget_total or reward_amount * total_quantity) + int(service_fee_total or 0)
        return db.execute(
            '''
            INSERT INTO campaigns (
                owner_user_id,
                title,
                task_type,
                target_url,
                reward_amount,
                unit_price,
                reward_budget_total,
                service_fee_total,
                pricing_json,
                is_funded,
                total_quantity,
                budget_total,
                status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                owner_user_id,
                title,
                task_type,
                target_url,
                reward_amount,
                int(unit_price or 0),
                int(reward_budget_total or reward_amount * total_quantity),
                int(service_fee_total or 0),
                json.dumps(pricing_snapshot or {}, ensure_ascii=False),
                1 if is_funded else 0,
                total_quantity,
                budget_total,
                status,
            ),
        )

    @staticmethod
    def get_campaign(campaign_id: int):
        return db.fetch_one('SELECT * FROM campaigns WHERE id = ?', (campaign_id,))

    @staticmethod
    def get_owned_campaign(owner_user_id: int, campaign_id: int):
        return db.fetch_one(
            'SELECT * FROM campaigns WHERE id = ? AND owner_user_id = ?',
            (campaign_id, owner_user_id),
        )

    @staticmethod
    def get_campaigns_for_owner(owner_user_id: int, limit: int = 30):
        return db.fetch_all(
            '''
            SELECT * FROM campaigns
            WHERE owner_user_id = ?
            ORDER BY updated_at DESC, id DESC
            LIMIT ?
            ''',
            (owner_user_id, limit),
        )

    @staticmethod
    def _activate_campaign(connection: sqlite3.Connection, campaign) -> tuple[bool, str]:
        campaign_id = int(campaign['id'])
        owner_user_id = int(campaign['owner_user_id'])
        if int(campaign['is_funded'] or 0) == 1:
            connection.execute(
                '''
                UPDATE campaigns
                SET status = 'active', updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                ''',
                (campaign_id,),
            )
            return True, 'campaign_launched'

        amount = int(campaign['budget_total'])
        wallet = connection.execute('SELECT * FROM wallets WHERE user_id = ?', (owner_user_id,)).fetchone()
        internal_balance = int(wallet['internal_balance']) if wallet else 0
        bonus_balance = int(wallet['bonus_balance']) if wallet and 'bonus_balance' in wallet.keys() else 0
        bonus_percent = max(0, min(50, RuntimeSettingsService.get_int('max_bonus_payment_percent')))
        max_bonus = amount * bonus_percent // 100
        from_bonus = min(bonus_balance, max_bonus)
        from_internal = amount - from_bonus
        if internal_balance < from_internal:
            return False, 'campaign_balance_low'
        connection.execute(
            '''
            UPDATE wallets
            SET bonus_balance = bonus_balance - ?,
                internal_balance = internal_balance - ?, updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ?
            ''',
            (from_bonus, from_internal, owner_user_id),
        )
        if from_bonus > 0:
            connection.execute(
                '''
                INSERT INTO transactions (
                    user_id, wallet_user_id, amount, currency_code, direction, entry_type, status, related_campaign_id, note
                ) VALUES (?, ?, ?, 'BST', 'debit', 'campaign_funding_bonus', 'completed', ?, ?)
                ''',
                (owner_user_id, owner_user_id, from_bonus, campaign_id, 'Campaign funded from bonus sparks balance'),
            )
        if from_internal > 0:
            connection.execute(
                '''
                INSERT INTO transactions (
                    user_id, wallet_user_id, amount, currency_code, direction, entry_type, status, related_campaign_id, note
                ) VALUES (?, ?, ?, 'BST', 'debit', 'campaign_funding', 'completed', ?, ?)
                ''',
                (owner_user_id, owner_user_id, from_internal, campaign_id, 'Campaign funded from earned sparks balance'),
            )
        connection.execute(
            '''
            UPDATE campaigns
            SET status = 'active', is_funded = 1, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            ''',
            (campaign_id,),
        )
        return True, 'campaign_launched'

    @staticmethod
    def update_status(owner_user_id: int, campaign_id: int, new_status: str) -> tuple[bool, str]:
        def _run(connection: sqlite3.Connection) -> tuple[bool, str]:
            campaign = connection.execute(
                'SELECT * FROM campaigns WHERE id = ? AND owner_user_id = ?',
                (campaign_id, owner_user_id),
            ).fetchone()
            if not campaign:
                return False, 'campaign_not_found'
            current_status = str(campaign['status'])
            allowed_transitions = {
                'draft': {'active': 'campaign_launched'},
                'active': {'paused': 'campaign_paused'},
                'paused': {'active': 'campaign_resumed'},
            }
            if new_status not in CAMPAIGN_STATUSES:
                return False, 'campaign_status_invalid'
            next_map = allowed_transitions.get(current_status, {})
            if new_status not in next_map:
                return False, 'campaign_status_transition_invalid'

            if current_status == 'draft' and new_status == 'active':
                return CampaignService._activate_campaign(connection, campaign)

            connection.execute(
                '''
                UPDATE campaigns
                SET status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND owner_user_id = ?
                ''',
                (new_status, campaign_id, owner_user_id),
            )
            return True, next_map[new_status]

        return db.run_in_transaction(_run)

    @staticmethod
    def get_remaining_budget(campaign) -> int:
        return max(int(campaign['budget_total']) - int(campaign['budget_spent']) - int(campaign['budget_reserved']), 0)

    @staticmethod
    def get_owner_stats(owner_user_id: int) -> dict[str, int]:
        row = db.fetch_one(
            '''
            SELECT
                COUNT(*) AS total_campaigns,
                COALESCE(SUM(CASE WHEN status = 'active' THEN 1 ELSE 0 END), 0) AS active_campaigns,
                COALESCE(SUM(CASE WHEN status = 'paused' THEN 1 ELSE 0 END), 0) AS paused_campaigns,
                COALESCE(SUM(CASE WHEN status = 'draft' THEN 1 ELSE 0 END), 0) AS draft_campaigns,
                COALESCE(SUM(completed_quantity), 0) AS completed_total,
                COALESCE(SUM(rejected_quantity), 0) AS rejected_total,
                COALESCE(SUM(budget_total), 0) AS budget_total,
                COALESCE(SUM(budget_reserved), 0) AS budget_reserved,
                COALESCE(SUM(budget_spent), 0) AS budget_spent,
                COALESCE(SUM(service_fee_total), 0) AS fees_total,
                COALESCE(SUM(reward_budget_total), 0) AS reward_budget_total
            FROM campaigns
            WHERE owner_user_id = ?
            ''',
            (owner_user_id,),
        )

        def _as_int(value) -> int:
            return int(value or 0)

        if not row:
            return {
                'total_campaigns': 0,
                'active_campaigns': 0,
                'paused_campaigns': 0,
                'draft_campaigns': 0,
                'completed_total': 0,
                'rejected_total': 0,
                'budget_total': 0,
                'budget_reserved': 0,
                'budget_spent': 0,
                'budget_remaining': 0,
                'fees_total': 0,
                'reward_budget_total': 0,
            }
        budget_total = _as_int(row['budget_total'])
        budget_reserved = _as_int(row['budget_reserved'])
        budget_spent = _as_int(row['budget_spent'])
        return {
            'total_campaigns': _as_int(row['total_campaigns']),
            'active_campaigns': _as_int(row['active_campaigns']),
            'paused_campaigns': _as_int(row['paused_campaigns']),
            'draft_campaigns': _as_int(row['draft_campaigns']),
            'completed_total': _as_int(row['completed_total']),
            'rejected_total': _as_int(row['rejected_total']),
            'budget_total': budget_total,
            'budget_reserved': budget_reserved,
            'budget_spent': budget_spent,
            'budget_remaining': max(budget_total - budget_reserved - budget_spent, 0),
            'fees_total': _as_int(row['fees_total']),
            'reward_budget_total': _as_int(row['reward_budget_total']),
        }
