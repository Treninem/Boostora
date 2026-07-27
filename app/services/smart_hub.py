from __future__ import annotations

from typing import Any

from app import db
from app.services.boostore_provider import BoostoreProviderService
from app.services.performer import PerformerService
from app.services.users import UserService
from app.services.wallets import WalletService
from app.texts import ROLE_CLIENT, ROLE_PERFORMER


def _first_int(query: str, params: tuple[Any, ...] = ()) -> int:
    try:
        row = db.fetch_one(query, params)
        return int(row[0] or 0) if row else 0
    except Exception:
        return 0


class SmartHubService:
    @staticmethod
    def dashboard(user_id: int) -> dict[str, Any]:
        role = UserService.get_role(user_id) or ROLE_PERFORMER
        wallet = WalletService.get_summary(user_id)
        active_tasks = PerformerService.get_active_submission_count(user_id)
        task_limit = PerformerService.get_active_task_limit(user_id)
        available_tasks = _first_int("SELECT COUNT(*) FROM campaigns WHERE status = 'active' AND total_quantity > completed_quantity")
        manual_review = _first_int("SELECT COUNT(*) FROM task_submissions WHERE performer_user_id = ? AND status = 'manual_review'", (user_id,))
        client_campaigns = _first_int('SELECT COUNT(*) FROM campaigns WHERE owner_user_id = ?', (user_id,))
        client_active = _first_int("SELECT COUNT(*) FROM campaigns WHERE owner_user_id = ? AND status = 'active'", (user_id,))
        client_drafts = _first_int("SELECT COUNT(*) FROM campaigns WHERE owner_user_id = ? AND status = 'draft'", (user_id,))
        provider = BoostoreProviderService.readiness_summary()
        tips: list[str] = []
        if role == ROLE_CLIENT:
            if client_campaigns == 0:
                tips.append('smart_tip_client_first_campaign')
            if provider['enabled_services'] > 0:
                tips.append('smart_tip_provider_marketplace')
            if wallet['internal_balance'] <= 0:
                tips.append('smart_tip_topup')
        else:
            if available_tasks > 0:
                tips.append('smart_tip_performer_take_task')
            if active_tasks >= task_limit:
                tips.append('smart_tip_task_limit')
            if wallet['bonus_balance'] > 0:
                tips.append('smart_tip_bonus_to_work')
        if not tips:
            tips.append('smart_tip_all_good')
        return {
            'role': role,
            'wallet': wallet,
            'active_tasks': active_tasks,
            'task_limit': task_limit,
            'available_tasks': available_tasks,
            'manual_review': manual_review,
            'client_campaigns': client_campaigns,
            'client_active': client_active,
            'client_drafts': client_drafts,
            'provider': provider,
            'tips': tips[:4],
        }
