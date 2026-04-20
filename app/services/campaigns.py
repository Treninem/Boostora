from app import db


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
    ) -> int:
        budget_total = reward_amount * total_quantity
        return db.execute(
            '''
            INSERT INTO campaigns (
                owner_user_id,
                title,
                task_type,
                target_url,
                reward_amount,
                total_quantity,
                budget_total,
                status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                owner_user_id,
                title,
                task_type,
                target_url,
                reward_amount,
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
    def update_status(owner_user_id: int, campaign_id: int, new_status: str) -> tuple[bool, str]:
        campaign = CampaignService.get_owned_campaign(owner_user_id, campaign_id)
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
        db.execute(
            '''
            UPDATE campaigns
            SET status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND owner_user_id = ?
            ''',
            (new_status, campaign_id, owner_user_id),
        )
        return True, next_map[new_status]

    @staticmethod
    def get_remaining_budget(campaign) -> int:
        return max(int(campaign['budget_total']) - int(campaign['budget_spent']) - int(campaign['budget_reserved']), 0)

    @staticmethod
    def get_owner_stats(owner_user_id: int) -> dict[str, int]:
        row = db.fetch_one(
            '''
            SELECT
                COUNT(*) AS total_campaigns,
                SUM(CASE WHEN status = 'active' THEN 1 ELSE 0 END) AS active_campaigns,
                SUM(CASE WHEN status = 'paused' THEN 1 ELSE 0 END) AS paused_campaigns,
                SUM(CASE WHEN status = 'draft' THEN 1 ELSE 0 END) AS draft_campaigns,
                COALESCE(SUM(completed_quantity), 0) AS completed_total,
                COALESCE(SUM(rejected_quantity), 0) AS rejected_total,
                COALESCE(SUM(budget_total), 0) AS budget_total,
                COALESCE(SUM(budget_reserved), 0) AS budget_reserved,
                COALESCE(SUM(budget_spent), 0) AS budget_spent
            FROM campaigns
            WHERE owner_user_id = ?
            ''',
            (owner_user_id,),
        )
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
            }
        budget_total = int(row['budget_total'])
        budget_reserved = int(row['budget_reserved'])
        budget_spent = int(row['budget_spent'])
        return {
            'total_campaigns': int(row['total_campaigns']),
            'active_campaigns': int(row['active_campaigns']),
            'paused_campaigns': int(row['paused_campaigns']),
            'draft_campaigns': int(row['draft_campaigns']),
            'completed_total': int(row['completed_total']),
            'rejected_total': int(row['rejected_total']),
            'budget_total': budget_total,
            'budget_reserved': budget_reserved,
            'budget_spent': budget_spent,
            'budget_remaining': max(budget_total - budget_reserved - budget_spent, 0),
        }
