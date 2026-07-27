from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app import db
from app.config import CONFIG_WARNINGS, settings
from app.services.boostore_provider import BoostoreProviderService
from app.services.engagement_growth import EngagementGrowthService
from app.services.engagement_modes import EngagementModeService
from app.services.community_rules import CommunityRulesService
from app.services.legal_docs import LegalDocsService
from app.services.standard_admin import StandardAdminService
from app.services.proof_guides import ProofGuideService
from app.services.final_audit import FinalAuditService


@dataclass(frozen=True)
class FlowCheck:
    code: str
    title_key: str
    status: str
    score: int
    signal_key: str
    action_key: str

    def as_dict(self) -> dict[str, Any]:
        return {
            'code': self.code,
            'title_key': self.title_key,
            'status': self.status,
            'score': self.score,
            'signal_key': self.signal_key,
            'action_key': self.action_key,
        }


def _count(table: str, where: str = '1=1') -> int:
    try:
        row = db.fetch_one(f'SELECT COUNT(*) AS cnt FROM {table} WHERE {where}')
        return int(row['cnt'] or 0) if row else 0
    except Exception:
        return 0


def _columns(table: str) -> set[str]:
    try:
        rows = db.fetch_all(f'PRAGMA table_info({table})')
        return {str(row['name']) for row in rows}
    except Exception:
        return set()


def _has_columns(table: str, *column_names: str) -> bool:
    cols = _columns(table)
    return bool(cols) and all(name in cols for name in column_names)


def _status(score: int, *, blocker: bool = False, warning: bool = False) -> str:
    if blocker:
        return 'blocker'
    if warning or score < 80:
        return 'warning'
    return 'ready'



def _first_int(query: str, params: tuple[Any, ...] = ()) -> int:
    try:
        row = db.fetch_one(query, params)
        if row is None:
            return 0
        return int(row[0] or 0)
    except Exception:
        return 0

class ReleaseReadinessService:
    """Owner-only pre-release checklist for critical Boostora flows.

    The service intentionally uses existing tables and configuration only. It does
    not mutate data and does not require a new migration, so it is safe for
    Bothost updates with BOT_DATA_DIR=/data.
    """

    @staticmethod
    def critical_flows() -> list[dict[str, Any]]:
        flows: list[FlowCheck] = []

        env_blocker = not bool(settings.bot_token.strip()) or not bool(settings.admin_ids)
        flows.append(FlowCheck(
            code='startup',
            title_key='release_flow_startup',
            status=_status(100 if not env_blocker else 40, blocker=env_blocker),
            score=100 if not env_blocker else 40,
            signal_key='release_signal_startup_ok' if not env_blocker else 'release_signal_startup_missing_env',
            action_key='release_action_startup_ok' if not env_blocker else 'release_action_startup_fix_env',
        ))

        users_ok = _has_columns('users', 'user_id', 'language_code', 'role', 'status', 'risk_score') and _has_columns('wallets', 'user_id', 'available_balance', 'bonus_balance')
        users_count = _count('users')
        flows.append(FlowCheck(
            code='profile_wallet',
            title_key='release_flow_profile_wallet',
            status=_status(96 if users_ok else 45, blocker=not users_ok, warning=users_count == 0),
            score=96 if users_ok and users_count > 0 else (82 if users_ok else 45),
            signal_key='release_signal_profile_wallet_has_users' if users_count > 0 else 'release_signal_profile_wallet_empty',
            action_key='release_action_profile_wallet_live_start' if users_count == 0 else 'release_action_profile_wallet_ok',
        ))

        payments_ok = _has_columns('transactions', 'entry_type', 'direction', 'amount', 'status') and _has_columns('vip_subscriptions', 'tier_code', 'expires_at', 'is_active')
        payment_score = 94 if payments_ok and settings.enable_xtr_payments else 76 if payments_ok else 40
        flows.append(FlowCheck(
            code='stars_vip',
            title_key='release_flow_stars_vip',
            status=_status(payment_score, blocker=not payments_ok, warning=not settings.enable_xtr_payments),
            score=payment_score,
            signal_key='release_signal_stars_enabled' if settings.enable_xtr_payments else 'release_signal_stars_disabled',
            action_key='release_action_stars_live_invoice' if settings.enable_xtr_payments else 'release_action_stars_enable_env',
        ))

        campaign_ok = _has_columns('campaigns', 'pricing_json', 'unit_price', 'reward_amount', 'budget_total', 'budget_reserved', 'is_funded')
        campaign_count = _count('campaigns')
        flows.append(FlowCheck(
            code='campaigns',
            title_key='release_flow_campaigns',
            status=_status(95 if campaign_ok else 44, blocker=not campaign_ok, warning=campaign_count == 0),
            score=95 if campaign_ok and campaign_count > 0 else (84 if campaign_ok else 44),
            signal_key='release_signal_campaigns_have_data' if campaign_count > 0 else 'release_signal_campaigns_empty',
            action_key='release_action_campaigns_create_test' if campaign_count == 0 else 'release_action_campaigns_ok',
        ))

        boost_ready = _has_columns('campaigns', 'pricing_json', 'service_fee_total', 'reward_budget_total') and _has_columns('transactions', 'related_campaign_id', 'entry_type')
        boosts = _count('transactions', "entry_type IN ('campaign_boost', 'campaign_boost_bonus')")
        flows.append(FlowCheck(
            code='campaign_boosts',
            title_key='release_flow_campaign_boosts',
            status=_status(93 if boost_ready else 46, blocker=not boost_ready, warning=boosts == 0),
            score=93 if boost_ready and boosts > 0 else (83 if boost_ready else 46),
            signal_key='release_signal_boosts_used' if boosts > 0 else 'release_signal_boosts_not_used',
            action_key='release_action_boosts_live_test' if boosts == 0 else 'release_action_boosts_ok',
        ))

        execution_ok = _has_columns('task_submissions', 'campaign_id', 'performer_user_id', 'proof_text', 'risk_score', 'reviewed_at') and _has_columns('holds', 'release_at', 'status')
        submissions = _count('task_submissions')
        flows.append(FlowCheck(
            code='task_execution',
            title_key='release_flow_task_execution',
            status=_status(94 if execution_ok else 43, blocker=not execution_ok, warning=submissions == 0),
            score=94 if execution_ok and submissions > 0 else (82 if execution_ok else 43),
            signal_key='release_signal_execution_has_submissions' if submissions > 0 else 'release_signal_execution_empty',
            action_key='release_action_execution_live_task' if submissions == 0 else 'release_action_execution_ok',
        ))

        manual_ok = _has_columns('task_submissions', 'status', 'reject_reason', 'reviewer_user_id') and _has_columns('admin_notes', 'note', 'target_user_id') and _has_columns('risk_events', 'event_type', 'severity', 'score_delta')
        manual_queue = _count('task_submissions', "status = 'manual_review'")
        flows.append(FlowCheck(
            code='manual_review',
            title_key='release_flow_manual_review',
            status=_status(94 if manual_ok else 42, blocker=not manual_ok, warning=manual_queue > 25),
            score=88 if manual_ok and manual_queue > 25 else (94 if manual_ok else 42),
            signal_key='release_signal_manual_busy' if manual_queue > 25 else 'release_signal_manual_ok',
            action_key='release_action_manual_clear_queue' if manual_queue > 25 else 'release_action_manual_ok',
        ))

        ads_ok = _has_columns('ad_broadcasts', 'schedule_code', 'next_run_at', 'status', 'is_admin') and _has_columns('bot_chats', 'is_active', 'can_post', 'chat_type')
        ready_chats = _count('bot_chats', 'is_active = 1 AND can_post = 1')
        flows.append(FlowCheck(
            code='ads_all_chats',
            title_key='release_flow_ads_all_chats',
            status=_status(93 if ads_ok else 45, blocker=not ads_ok, warning=ready_chats == 0),
            score=93 if ads_ok and ready_chats > 0 else (80 if ads_ok else 45),
            signal_key='release_signal_ads_ready_chats' if ready_chats > 0 else 'release_signal_ads_no_ready_chats',
            action_key='release_action_ads_add_chat' if ready_chats == 0 else 'release_action_ads_ok',
        ))

        chat_issues = _count('bot_chats', 'is_active = 0 OR can_post = 0')
        bot_rights_score = 92 if chat_issues == 0 else 78
        flows.append(FlowCheck(
            code='bot_rights',
            title_key='release_flow_bot_rights',
            status=_status(bot_rights_score, warning=chat_issues > 0),
            score=bot_rights_score,
            signal_key='release_signal_bot_rights_clean' if chat_issues == 0 else 'release_signal_bot_rights_issues',
            action_key='release_action_bot_rights_live_audit' if chat_issues > 0 else 'release_action_bot_rights_ok',
        ))

        antifraud_ok = _has_columns('users', 'risk_score', 'status') and _has_columns('admin_notes', 'note_type', 'created_at') and _has_columns('risk_events', 'details', 'created_at')
        risky_unblocked = _count('users', "risk_score >= 60 AND status != 'blocked'")
        flows.append(FlowCheck(
            code='antifraud',
            title_key='release_flow_antifraud',
            status=_status(93 if antifraud_ok else 43, blocker=not antifraud_ok, warning=risky_unblocked > 0),
            score=82 if antifraud_ok and risky_unblocked > 0 else (93 if antifraud_ok else 43),
            signal_key='release_signal_antifraud_risky' if risky_unblocked > 0 else 'release_signal_antifraud_ok',
            action_key='release_action_antifraud_review_patterns' if risky_unblocked > 0 else 'release_action_antifraud_ok',
        ))

        commerce_ok = _has_columns('campaigns', 'budget_spent', 'service_fee_total') and _has_columns('wallets', 'available_balance', 'hold_balance', 'bonus_balance')
        flows.append(FlowCheck(
            code='owner_commerce',
            title_key='release_flow_owner_commerce',
            status=_status(95 if commerce_ok else 44, blocker=not commerce_ok),
            score=95 if commerce_ok else 44,
            signal_key='release_signal_commerce_ok' if commerce_ok else 'release_signal_commerce_schema_missing',
            action_key='release_action_commerce_ok' if commerce_ok else 'release_action_commerce_check_db',
        ))

        return [flow.as_dict() for flow in flows]

    @staticmethod
    def readiness_summary() -> dict[str, Any]:
        flows = ReleaseReadinessService.critical_flows()
        total = sum(int(flow['score']) for flow in flows)
        score = int(round(total / max(len(flows), 1)))
        blockers = sum(1 for flow in flows if flow['status'] == 'blocker')
        warnings = sum(1 for flow in flows if flow['status'] == 'warning')
        ready = sum(1 for flow in flows if flow['status'] == 'ready')
        if blockers:
            state = 'blocked'
        elif score >= 88 and warnings <= 3:
            state = 'rc_ready'
        elif score >= 78:
            state = 'needs_live_checks'
        else:
            state = 'needs_work'
        return {
            'score': score,
            'state': state,
            'blockers': blockers,
            'warnings': warnings,
            'ready': ready,
            'total': len(flows),
            'flows': flows,
        }

    @staticmethod
    def regression_plan() -> list[str]:
        return [
            'release_regression_start_role_profile',
            'release_regression_wallet_stars_vip',
            'release_regression_campaign_create_pay_boost',
            'release_regression_performer_take_submit',
            'release_regression_admin_review_antifraud',
            'release_regression_ads_bot_rights',
            'release_regression_owner_commerce',
        ]


    @staticmethod
    def launch_guardrails() -> dict[str, Any]:
        """Final owner-only launch guardrails for release candidate builds.

        This method is intentionally read-only. It turns the release-check signal
        into a practical launch matrix: what is ready, what needs a live check,
        and what blocks a v3.0.0 release candidate.
        """
        summary = ReleaseReadinessService.readiness_summary()
        flows = list(summary['flows'])
        blockers = [flow for flow in flows if flow['status'] == 'blocker']
        warnings = [flow for flow in flows if flow['status'] == 'warning']

        stars_topups = _count('transactions', "entry_type = 'stars_topup' AND status = 'completed'")
        vip_purchases = _count('transactions', "entry_type = 'vip_purchase' AND status = 'completed'")
        campaign_payments = _count('transactions', "entry_type IN ('campaign_funding', 'campaign_boost') AND status = 'completed'")
        ready_chats = _count('bot_chats', 'is_active = 1 AND can_post = 1')
        chat_issues = _count('bot_chats', 'is_active = 0 OR can_post = 0')
        manual_queue = _count('task_submissions', "status = 'manual_review'")
        risky_unblocked = _count('users', "risk_score >= 60 AND status != 'blocked'")
        active_campaigns = _count('campaigns', "status = 'active'")
        funded_campaigns = _count('campaigns', 'is_funded = 1')

        matrix: list[dict[str, Any]] = []

        def add(code: str, title_key: str, status: str, value: int, action_key: str) -> None:
            matrix.append({
                'code': code,
                'title_key': title_key,
                'status': status,
                'value': int(value),
                'action_key': action_key,
            })

        add(
            'env_schema',
            'launch_guard_env_schema',
            'blocker' if blockers else 'ready',
            len(blockers),
            'launch_action_fix_blockers' if blockers else 'launch_action_env_schema_ok',
        )
        add(
            'stars_live',
            'launch_guard_stars_live',
            'ready' if stars_topups > 0 else ('warning' if settings.enable_xtr_payments else 'blocker'),
            stars_topups,
            'launch_action_stars_live_ok' if stars_topups > 0 else ('launch_action_make_stars_payment' if settings.enable_xtr_payments else 'launch_action_enable_stars'),
        )
        add(
            'vip_live',
            'launch_guard_vip_live',
            'ready' if vip_purchases > 0 else 'warning',
            vip_purchases,
            'launch_action_vip_ok' if vip_purchases > 0 else 'launch_action_vip_test',
        )
        add(
            'campaign_money',
            'launch_guard_campaign_money',
            'ready' if campaign_payments > 0 and funded_campaigns > 0 else 'warning',
            campaign_payments,
            'launch_action_campaign_money_ok' if campaign_payments > 0 else 'launch_action_campaign_money_test',
        )
        add(
            'bot_rights',
            'launch_guard_bot_rights',
            'ready' if ready_chats > 0 and chat_issues == 0 else ('warning' if ready_chats > 0 else 'blocker'),
            ready_chats,
            'launch_action_bot_rights_ok' if ready_chats > 0 and chat_issues == 0 else 'launch_action_bot_rights_live',
        )
        add(
            'manual_queue',
            'launch_guard_manual_queue',
            'ready' if manual_queue <= 10 else ('warning' if manual_queue <= 30 else 'blocker'),
            manual_queue,
            'launch_action_manual_queue_ok' if manual_queue <= 10 else 'launch_action_manual_queue_clear',
        )
        add(
            'high_risk',
            'launch_guard_high_risk',
            'ready' if risky_unblocked == 0 else ('warning' if risky_unblocked <= 5 else 'blocker'),
            risky_unblocked,
            'launch_action_high_risk_ok' if risky_unblocked == 0 else 'launch_action_high_risk_review',
        )
        add(
            'active_supply',
            'launch_guard_active_supply',
            'ready' if active_campaigns > 0 else 'warning',
            active_campaigns,
            'launch_action_active_supply_ok' if active_campaigns > 0 else 'launch_action_active_supply_seed',
        )

        hard_blockers = sum(1 for row in matrix if row['status'] == 'blocker')
        live_warnings = sum(1 for row in matrix if row['status'] == 'warning')
        live_score = max(0, min(100, int(summary['score']) - hard_blockers * 12 - live_warnings * 4))
        if hard_blockers:
            launch_state = 'blocked'
        elif live_score >= 88 and live_warnings <= 3:
            launch_state = 'rc_ready'
        elif live_score >= 75:
            launch_state = 'needs_live_checks'
        else:
            launch_state = 'needs_work'

        return {
            'launch_state': launch_state,
            'live_score': live_score,
            'hard_blockers': hard_blockers,
            'live_warnings': live_warnings,
            'matrix': matrix,
            'blockers': blockers,
            'warnings': warnings,
        }

    @staticmethod
    def final_launch_checklist() -> list[str]:
        return [
            'launch_check_env_backup',
            'launch_check_stars_invoice',
            'launch_check_vip_purchase',
            'launch_check_campaign_pay_boost',
            'launch_check_performer_submit_hold',
            'launch_check_admin_templates_notes',
            'launch_check_ads_live_audit',
            'launch_check_owner_margin',
        ]


    @staticmethod
    def rc1_gate_summary() -> dict[str, Any]:
        """Read-only v3.0.0-rc1 gate.

        RC1 is not the final public release. It is a controlled candidate that
        may still require live checks, but it must not have schema/.env blockers
        or dangerous unresolved operational blockers. This keeps the update safe
        for Bothost and old /data databases.
        """
        summary = ReleaseReadinessService.readiness_summary()
        guardrails = ReleaseReadinessService.launch_guardrails()
        flows = list(summary['flows'])
        matrix = list(guardrails['matrix'])

        blockers = int(summary['blockers']) + int(guardrails['hard_blockers'])
        warnings = int(summary['warnings']) + int(guardrails['live_warnings'])
        readiness = int(round((int(summary['score']) + int(guardrails['live_score'])) / 2))

        stars_live = _count('transactions', "entry_type = 'stars_topup' AND status = 'completed'")
        vip_live = _count('transactions', "entry_type = 'vip_purchase' AND status = 'completed'")
        campaign_money = _count('transactions', "entry_type IN ('campaign_funding', 'campaign_boost') AND status = 'completed'")
        ready_chats = _count('bot_chats', 'is_active = 1 AND can_post = 1')
        manual_queue = _count('task_submissions', "status = 'manual_review'")
        risky_unblocked = _count('users', "risk_score >= 60 AND status != 'blocked'")
        active_campaigns = _count('campaigns', "status = 'active'")

        rows: list[dict[str, Any]] = []

        def add(code: str, title_key: str, status: str, value: int, action_key: str) -> None:
            rows.append({
                'code': code,
                'title_key': title_key,
                'status': status,
                'value': int(value),
                'action_key': action_key,
            })

        add(
            'code_integrity',
            'rc1_gate_code_integrity',
            'ready' if int(summary['blockers']) == 0 and int(summary['score']) >= 80 else 'blocker',
            int(summary['score']),
            'rc1_action_code_integrity_ok' if int(summary['blockers']) == 0 else 'rc1_action_fix_code_blockers',
        )
        add(
            'live_money',
            'rc1_gate_live_money',
            'ready' if stars_live > 0 and campaign_money > 0 else ('warning' if settings.enable_xtr_payments else 'blocker'),
            stars_live + campaign_money,
            'rc1_action_money_ok' if stars_live > 0 and campaign_money > 0 else 'rc1_action_money_live_test',
        )
        add(
            'vip_check',
            'rc1_gate_vip_check',
            'ready' if vip_live > 0 else 'warning',
            vip_live,
            'rc1_action_vip_ok' if vip_live > 0 else 'rc1_action_vip_control',
        )
        add(
            'bot_rights',
            'rc1_gate_bot_rights',
            'ready' if ready_chats > 0 else 'warning',
            ready_chats,
            'rc1_action_bot_rights_ok' if ready_chats > 0 else 'rc1_action_bot_rights_control',
        )
        add(
            'moderation_safety',
            'rc1_gate_moderation_safety',
            'ready' if manual_queue <= 10 and risky_unblocked == 0 else ('warning' if manual_queue <= 30 and risky_unblocked <= 5 else 'blocker'),
            manual_queue + risky_unblocked,
            'rc1_action_moderation_ok' if manual_queue <= 10 and risky_unblocked == 0 else 'rc1_action_moderation_clear',
        )
        add(
            'market_supply',
            'rc1_gate_market_supply',
            'ready' if active_campaigns > 0 else 'warning',
            active_campaigns,
            'rc1_action_supply_ok' if active_campaigns > 0 else 'rc1_action_supply_seed',
        )
        add(
            'data_safety',
            'rc1_gate_data_safety',
            'ready',
            1,
            'rc1_action_data_safety_ok',
        )

        row_blockers = sum(1 for row in rows if row['status'] == 'blocker')
        row_warnings = sum(1 for row in rows if row['status'] == 'warning')
        rc1_score = max(0, min(100, readiness - row_blockers * 10 - row_warnings * 3))
        if blockers or row_blockers:
            state = 'blocked'
        elif rc1_score >= 88 and row_warnings <= 4:
            state = 'rc1_ready'
        elif rc1_score >= 75:
            state = 'controlled_rc1'
        else:
            state = 'needs_live_checks'

        return {
            'state': state,
            'score': rc1_score,
            'blockers': blockers + row_blockers,
            'warnings': warnings + row_warnings,
            'rows': rows,
            'flows': flows,
            'guardrails': matrix,
        }

    @staticmethod
    def rc1_release_contract() -> list[str]:
        """Human checklist shown in the owner release center for rc1 discipline."""
        return [
            'rc1_contract_no_feature_creep',
            'rc1_contract_no_schema_break',
            'rc1_contract_data_backup',
            'rc1_contract_live_payments',
            'rc1_contract_rights_audit',
            'rc1_contract_fix_only_blockers',
            'rc1_contract_public_after_24h',
        ]


    @staticmethod
    def data_integrity_summary() -> dict[str, Any]:
        """Read-only sanity checks for money and launch safety.

        It intentionally avoids mutations and uses only existing tables, so it is
        safe to run on old Bothost databases before and after an update.
        """
        negative_wallets = _first_int(
            """
            SELECT COUNT(*)
            FROM wallets
            WHERE available_balance < 0
               OR hold_balance < 0
               OR internal_balance < 0
               OR bonus_balance < 0
            """
        )
        over_reserved_campaigns = _first_int(
            """
            SELECT COUNT(*)
            FROM campaigns
            WHERE budget_reserved < 0
               OR budget_spent < 0
               OR budget_total < 0
               OR budget_reserved + budget_spent > budget_total
            """
        )
        orphan_active_holds = _first_int(
            """
            SELECT COUNT(*)
            FROM holds h
            LEFT JOIN task_submissions s ON s.id = h.submission_id
            WHERE h.status = 'active'
              AND h.submission_id IS NOT NULL
              AND s.id IS NULL
            """
        )
        stuck_invoices = _first_int("SELECT COUNT(*) FROM invoice_messages") if _has_columns('invoice_messages', 'user_id', 'invoice_message_id') else 0
        warnings = int(negative_wallets > 0) + int(over_reserved_campaigns > 0) + int(orphan_active_holds > 0)
        status = 'ready' if warnings == 0 else ('warning' if negative_wallets == 0 else 'blocker')
        return {
            'status': status,
            'warnings': warnings,
            'negative_wallets': negative_wallets,
            'over_reserved_campaigns': over_reserved_campaigns,
            'orphan_active_holds': orphan_active_holds,
            'stuck_invoices': stuck_invoices,
        }

    @staticmethod
    def config_warning_summary() -> dict[str, Any]:
        warnings = list(CONFIG_WARNINGS)
        return {
            'status': 'ready' if not warnings else 'warning',
            'warnings': len(warnings),
            'items': warnings[:8],
        }

    def persistence_summary() -> dict[str, Any]:
        """Read-only check for safe Bothost persistence and backup hygiene.

        The check does not touch files or database rows. It only verifies that
        current paths point to a stable data directory and that backup/invalid-db
        folders are not silently growing.
        """
        data_dir = Path(settings.data_dir)
        db_path = Path(settings.db_path)
        data_dir_exists = data_dir.exists()
        db_parent_exists = db_path.parent.exists()

        try:
            db_inside_data = db_path.resolve().is_relative_to(data_dir.resolve())
        except AttributeError:
            try:
                db_path.resolve().relative_to(data_dir.resolve())
                db_inside_data = True
            except Exception:
                db_inside_data = False
        except Exception:
            db_inside_data = False

        backups_dir = data_dir / 'backups'
        invalid_dir = data_dir / 'invalid-db'
        try:
            backup_count = len(list(backups_dir.glob(f"{db_path.stem}_*{db_path.suffix}.bak"))) if backups_dir.exists() else 0
        except Exception:
            backup_count = 0
        try:
            invalid_count = len(list(invalid_dir.glob('*.bad'))) if invalid_dir.exists() else 0
        except Exception:
            invalid_count = 0

        warning_count = 0
        if not data_dir_exists or not db_parent_exists:
            warning_count += 1
        if not db_inside_data:
            warning_count += 1
        if backup_count > 8:
            warning_count += 1
        if invalid_count > 0:
            warning_count += 1

        blocker = not data_dir_exists or not db_parent_exists
        status = 'blocker' if blocker else ('warning' if warning_count else 'ready')
        score = 100
        if blocker:
            score = 45
        elif warning_count:
            score = max(70, 96 - warning_count * 7)

        return {
            'status': status,
            'score': score,
            'warnings': warning_count,
            'data_dir_exists': int(data_dir_exists),
            'db_parent_exists': int(db_parent_exists),
            'db_inside_data': int(db_inside_data),
            'backup_count': backup_count,
            'invalid_db_count': invalid_count,
        }


    @staticmethod
    def database_snapshot_safety_summary() -> dict[str, Any]:
        """Verify WAL-safe backups and throttled optional legacy mirroring."""
        db_source_path = Path(__file__).resolve().parents[1] / 'db.py'
        try:
            source = db_source_path.read_text(encoding='utf-8')
        except Exception:
            source = ''
        checks = {
            'sqlite_backup_api': 'source_connection.backup(target_connection)' in source,
            'snapshot_integrity': "PRAGMA integrity_check" in source,
            'atomic_replace': 'os.replace(temporary, target)' in source,
            'mirror_opt_in': 'settings.legacy_db_mirror_enabled' in source,
            'mirror_throttle': 'settings.legacy_mirror_interval_seconds' in source and '_LAST_LEGACY_MIRROR_MONOTONIC' in source,
            'periodic_backups': 'create_periodic_backup' in source and 'settings.db_backup_interval_hours' in source,
            'backup_retention': 'settings.db_backup_max_files' in source and '_database_backup_files' in source,
            'backup_race_guard': '_recent_backup_exists()' in source and 'with _SNAPSHOT_LOCK:' in source,
        }
        failed = [name for name, ok in checks.items() if not ok]
        status = 'ready' if not failed else ('warning' if len(failed) <= 2 else 'blocker')
        return {
            'status': status,
            'score': max(40, 100 - len(failed) * 15),
            'warnings': len(failed),
            'failed': ','.join(failed),
            'mirror_enabled': int(settings.legacy_db_mirror_enabled),
            'mirror_interval_seconds': int(settings.legacy_mirror_interval_seconds),
            'backup_interval_hours': int(settings.db_backup_interval_hours),
            'backup_max_files': int(settings.db_backup_max_files),
            **{name: int(ok) for name, ok in checks.items()},
        }


    @staticmethod
    def runtime_safety_summary() -> dict[str, Any]:
        """Read-only runtime guard for DB locks, stale sessions and due queues.

        The check is intentionally conservative: it does not delete sessions,
        invoices or tasks. It only highlights what the owner should inspect
        after a restart or after a Bothost/GitHub update.
        """
        db_path = Path(settings.db_path)
        connect_ok = 0
        try:
            row = db.fetch_one('SELECT 1 AS ok')
            connect_ok = 1 if row else 0
        except Exception:
            connect_ok = 0

        db_size_mb = 0
        wal_size_mb = 0
        journal_leftovers = 0
        try:
            if db_path.exists():
                db_size_mb = int(db_path.stat().st_size / 1024 / 1024)
            wal_path = Path(str(db_path) + '-wal')
            journal_path = Path(str(db_path) + '-journal')
            if wal_path.exists():
                wal_size_mb = int(wal_path.stat().st_size / 1024 / 1024)
            if journal_path.exists():
                journal_leftovers += 1
        except Exception:
            pass

        stale_inputs = _first_int(
            """
            SELECT COUNT(*)
            FROM input_sessions
            WHERE updated_at < datetime('now', '-24 hours')
            """
        ) if _has_columns('input_sessions', 'updated_at') else 0
        stale_invoices = _first_int(
            """
            SELECT COUNT(*)
            FROM invoice_messages
            WHERE updated_at < datetime('now', '-12 hours')
            """
        ) if _has_columns('invoice_messages', 'updated_at') else 0
        overdue_holds = _first_int(
            """
            SELECT COUNT(*)
            FROM holds
            WHERE status = 'active'
              AND release_at < datetime('now', '-2 hours')
            """
        ) if _has_columns('holds', 'status', 'release_at') else 0
        due_ads_backlog = _first_int(
            """
            SELECT COUNT(*)
            FROM ad_broadcasts
            WHERE status = 'active'
              AND next_run_at IS NOT NULL
              AND next_run_at < datetime('now', '-1 hour')
            """
        ) if _has_columns('ad_broadcasts', 'status', 'next_run_at') else 0

        warnings = 0
        if not connect_ok:
            warnings += 3
        if db_size_mb > 512:
            warnings += 1
        if wal_size_mb > 256:
            warnings += 1
        if journal_leftovers > 0:
            warnings += 1
        if stale_inputs > 20:
            warnings += 1
        if stale_invoices > 20:
            warnings += 1
        if overdue_holds > 10:
            warnings += 1
        if due_ads_backlog > 10:
            warnings += 1

        status = 'blocker' if not connect_ok else ('warning' if warnings else 'ready')
        score = 100
        if not connect_ok:
            score = 35
        elif warnings:
            score = max(68, 98 - warnings * 6)

        return {
            'status': status,
            'score': score,
            'warnings': warnings,
            'connect_ok': connect_ok,
            'db_size_mb': db_size_mb,
            'wal_size_mb': wal_size_mb,
            'journal_leftovers': journal_leftovers,
            'stale_inputs': stale_inputs,
            'stale_invoices': stale_invoices,
            'overdue_holds': overdue_holds,
            'due_ads_backlog': due_ads_backlog,
        }

    @staticmethod
    def network_resilience_summary() -> dict[str, Any]:
        """Read-only check for Telegram polling/network resilience.

        This guard verifies that the production bot uses Boostora's controlled
        polling loop instead of pyTelegramBotAPI's noisy built-in polling. It
        is aimed at real-world Telegram 502/timeout outages: the bot should
        keep retrying with backoff and write compact warnings, not die with
        repeated TeleBot tracebacks.
        """
        bot_path = Path(__file__).resolve().parents[1] / 'bot.py'
        try:
            source = bot_path.read_text(encoding='utf-8')
        except Exception:
            source = ''

        checks = {
            'custom_poll_loop': '_poll_forever' in source and 'bot.get_updates' in source,
            'transient_codes': 'TRANSIENT_TELEGRAM_ERROR_CODES' in source and '502' in source and '504' in source,
            'webhook_retries': 'REMOVE_WEBHOOK_ATTEMPTS' in source and '_prepare_bot' in source,
            'backoff': 'POLLING_BACKOFF_MAX_SECONDS' in source and '_next_backoff' in source,
            'telebot_noise_guard': "logging.getLogger('TeleBot').setLevel(logging.CRITICAL)" in source,
            'no_builtin_infinity_polling': '.infinity_polling(' not in source and '.polling(' not in source,
            'preserve_updates_default': '_initial_poll_offset' in source and 'settings.drop_pending_updates' in source,
            'clean_shutdown': '_release_single_instance_lock(lock_fd)' in source and 'finally:' in source,
            'signal_shutdown': '_install_shutdown_handlers' in source and 'SIGTERM' in source and 'SIGINT' in source,
            'interruptible_backoff': '_wait_for_shutdown' in source and 'effective_stop' in source,
            'worker_join': 'promo_thread.join(timeout=5)' in source,
            'background_job_isolation': '_run_background_job' in source and 'remaining jobs will continue' in source,
            'worker_interval_config': 'settings.background_worker_interval_seconds' in source,
        }
        failed = [name for name, ok in checks.items() if not ok]
        status = 'ready' if not failed else ('warning' if len(failed) <= 2 else 'blocker')
        score = max(40, 100 - len(failed) * 12)
        return {
            'status': status,
            'score': score,
            'warnings': len(failed),
            'failed': ','.join(failed),
            **{name: int(ok) for name, ok in checks.items()},
        }

    @staticmethod
    def update_handler_safety_summary() -> dict[str, Any]:
        """Read-only check for poisoned update protection.

        A single broken callback/message handler must not trap long polling on
        the same update forever. Boostora v3.0.5 advances the offset for a
        failed batch and writes a compact exception log, so the bot keeps
        serving other users while the owner fixes the root cause.
        """
        bot_path = Path(__file__).resolve().parents[1] / 'bot.py'
        try:
            source = bot_path.read_text(encoding='utf-8')
        except Exception:
            source = ''

        checks = {
            'next_offset_helper': '_next_offset_from_updates' in source,
            'per_update_processing': 'bot.process_new_updates([update])' in source,
            'per_update_guard': 'for update in updates:' in source and 'except Exception:' in source,
            'poisoned_update_log': 'Only this update is skipped' in source,
            'offset_return_on_failure': 'return next_offset' in source,
            'batch_peers_continue': 'the rest of the batch continues' in source,
        }
        failed = [name for name, ok in checks.items() if not ok]
        status = 'ready' if not failed else ('warning' if len(failed) <= 2 else 'blocker')
        score = max(45, 100 - len(failed) * 14)
        return {
            'status': status,
            'score': score,
            'warnings': len(failed),
            'failed': ','.join(failed),
            **{name: int(ok) for name, ok in checks.items()},
        }

    @staticmethod
    def provider_modernization_summary() -> dict[str, Any]:
        provider = BoostoreProviderService.readiness_summary()
        warning = provider['state'] in {'needs_key', 'needs_sync', 'needs_whitelist'}
        return {
            'code': 'boostore_provider',
            'title_key': 'stable_gate_boostore_provider',
            'status': _status(int(provider['score']), warning=warning),
            'score': int(provider['score']),
            'value': int(provider['enabled_services']),
            'action_key': 'stable_action_boostore_provider_ready' if provider['state'] == 'ready' else f"stable_action_boostore_provider_{provider['state']}",
        }




    @staticmethod
    def boostore_api_diagnostics_summary() -> dict[str, Any]:
        summary = BoostoreProviderService.diagnostics_summary()
        status = str(summary.get('status') or 'warning')
        return {
            'code': 'boostore_api_diagnostics',
            'title_key': 'stable_gate_boostore_api_diagnostics',
            'status': status,
            'score': int(summary.get('score') or 0),
            'value': int(summary.get('warnings') or 0),
            'action_key': 'stable_action_boostore_api_diagnostics_ready' if status == 'ready' else 'stable_action_boostore_api_diagnostics_review',
        }

    @staticmethod
    def engagement_presets_summary() -> dict[str, Any]:
        summary = EngagementGrowthService.summary()
        presets = int(summary.get('preset_count') or 0)
        products = int(summary.get('product_count') or 0)
        ready = presets >= 9 and products >= 3
        return {
            'code': 'engagement_presets',
            'title_key': 'stable_gate_engagement_presets',
            'status': 'ready' if ready else 'warning',
            'score': 100 if ready else 70,
            'value': presets,
            'action_key': 'stable_action_engagement_presets_ready' if ready else 'stable_action_engagement_presets_review',
        }

    @staticmethod
    def community_rules_summary() -> dict[str, Any]:
        summary = CommunityRulesService.summary()
        ready = bool(summary.get('table_ready')) and int(summary.get('sections') or 0) >= 8
        return {
            'code': 'community_rules',
            'title_key': 'stable_gate_community_rules',
            'status': 'ready' if ready else 'warning',
            'score': 100 if ready else 72,
            'value': int(summary.get('accepted_users') or 0),
            'action_key': 'stable_action_community_rules_ready' if ready else 'stable_action_community_rules_review',
        }


    @staticmethod
    def engagement_modes_summary() -> dict[str, Any]:
        summary = EngagementModeService.summary()
        ready = bool(summary.get('table_ready')) and int(summary.get('required_actions') or 0) > 0 and int(summary.get('pro_price_stars') or 0) > 0
        return {
            'code': 'engagement_modes',
            'title_key': 'stable_gate_engagement_modes',
            'status': 'ready' if ready else 'warning',
            'score': 100 if ready else 70,
            'value': int(summary.get('members') or 0),
            'action_key': 'stable_action_engagement_modes_ready' if ready else 'stable_action_engagement_modes_review',
        }


    @staticmethod
    def engagement_obligations_summary() -> dict[str, Any]:
        overview = EngagementModeService.admin_obligation_overview(limit=10)
        ready = bool(overview.get('table_ready'))
        overdue = int(overview.get('overdue_total') or 0)
        open_total = int(overview.get('open_total') or 0)
        status = 'ready' if ready and overdue == 0 else ('warning' if ready else 'blocker')
        score = 100 if status == 'ready' else (78 if status == 'warning' else 45)
        return {
            'code': 'engagement_obligations',
            'title_key': 'stable_gate_engagement_obligations',
            'status': status,
            'score': score,
            'value': open_total,
            'action_key': 'stable_action_engagement_obligations_ready' if status == 'ready' else 'stable_action_engagement_obligations_review',
        }


    @staticmethod
    def engagement_soft_enforcement_summary() -> dict[str, Any]:
        summary = EngagementModeService.soft_enforcement_summary()
        ready = bool(summary.get('table_ready')) and bool(summary.get('block_enabled')) and bool(summary.get('reminders_enabled'))
        overdue = int(summary.get('overdue') or 0)
        status = 'ready' if ready and overdue == 0 else ('warning' if ready else 'blocker')
        score = 100 if status == 'ready' else (78 if status == 'warning' else 48)
        return {
            'code': 'engagement_soft_enforcement',
            'title_key': 'stable_gate_engagement_soft_enforcement',
            'status': status,
            'score': score,
            'value': int(summary.get('blocked_users') or 0),
            'action_key': 'stable_action_engagement_soft_enforcement_ready' if status == 'ready' else 'stable_action_engagement_soft_enforcement_review',
        }

    @staticmethod
    def proof_guides_summary() -> dict[str, Any]:
        summary = ProofGuideService.summary()
        guide_count = int(summary.get('guide_count') or 0)
        required_ready = int(summary.get('required_ready') or 0)
        required_total = int(summary.get('required_total') or 3)
        ready = guide_count >= 9 and required_ready >= required_total and bool(summary.get('has_default'))
        return {
            'code': 'proof_guides',
            'title_key': 'stable_gate_proof_guides',
            'status': 'ready' if ready else 'warning',
            'score': 100 if ready else 74,
            'value': guide_count,
            'action_key': 'stable_action_proof_guides_ready' if ready else 'stable_action_proof_guides_review',
        }


    @staticmethod
    def standard_admin_actions_summary() -> dict[str, Any]:
        summary = StandardAdminService.summary()
        status = str(summary.get('status') or 'warning')
        return {
            'code': 'standard_admin_actions',
            'title_key': 'stable_gate_standard_admin_actions',
            'status': status,
            'score': 100 if status == 'ready' else 55,
            'value': int(summary.get('decisions') or 0),
            'action_key': 'stable_action_standard_admin_actions_ready' if status == 'ready' else 'stable_action_standard_admin_actions_review',
        }

    @staticmethod
    def boostore_auto_orders_summary() -> dict[str, Any]:
        summary = BoostoreProviderService.order_summary()
        status = str(summary.get('status') or 'warning')
        if status == 'ready' and not int(summary.get('auto_order_enabled') or 0):
            status = 'warning'
        return {
            'code': 'boostore_auto_orders',
            'title_key': 'stable_gate_boostore_auto_orders',
            'status': status,
            'score': 100 if status == 'ready' else 78,
            'value': int(summary.get('total') or 0),
            'action_key': 'stable_action_boostore_auto_orders_ready' if status == 'ready' else 'stable_action_boostore_auto_orders_review',
        }

    @staticmethod
    def legal_docs_summary() -> dict[str, Any]:
        summary = LegalDocsService.summary()
        status = str(summary.get('status') or 'warning')
        return {
            'code': 'legal_docs',
            'title_key': 'stable_gate_legal_docs',
            'status': status,
            'score': 100 if status == 'ready' else 55,
            'value': int(summary.get('accepted') or 0),
            'action_key': 'stable_action_legal_docs_ready' if status == 'ready' else 'stable_action_legal_docs_review',
        }


    @staticmethod
    def miniapp_visual_assets_summary() -> dict[str, Any]:
        project_root = Path(__file__).resolve().parents[2]
        index = project_root / 'miniapp_example/index.html'
        assets = project_root / 'miniapp_example/assets'
        required = [
            'hero-growth.svg', 'liker.svg', 'commenter.svg', 'standard.svg',
            'pro.svg', 'obligations.svg', 'boostore.svg', 'rules.svg', 'wallet.svg',
        ]
        existing = sum(1 for name in required if (assets / name).is_file())
        checks = {
            'all_assets': existing == len(required),
            'asset_links': False,
            'telegram_sdk': False,
            'telegram_ready': False,
            'safe_area': False,
            'accessibility': False,
        }
        try:
            html = index.read_text(encoding='utf-8')
            checks['asset_links'] = all(f'assets/{name}' in html for name in required)
            checks['telegram_sdk'] = 'telegram-web-app.js' in html
            checks['telegram_ready'] = 'tg.ready()' in html and 'tg.expand()' in html
            checks['safe_area'] = 'safe-area-inset-bottom' in html and 'viewport-fit=cover' in html
            checks['accessibility'] = 'aria-label=' in html and 'focus-visible' in html and 'prefers-reduced-motion' in html
        except Exception:
            pass
        failed = [name for name, ok in checks.items() if not ok]
        status = 'ready' if not failed else ('warning' if existing else 'blocker')
        score = 100 if not failed else max(45, 100 - len(failed) * 11)
        return {
            'code': 'miniapp_visual_assets',
            'title_key': 'stable_gate_miniapp_visual_assets',
            'status': status,
            'score': score,
            'value': existing,
            'warnings': len(failed),
            'failed': ','.join(failed),
            'action_key': 'stable_action_miniapp_visual_assets_ready' if status == 'ready' else 'stable_action_miniapp_visual_assets_review',
        }


    @staticmethod
    def embedded_miniapp_runtime_summary() -> dict[str, Any]:
        project_root = Path(__file__).resolve().parents[2]
        webapp_path = project_root / 'app/webapp.py'
        bot_path = project_root / 'app/bot.py'
        index_path = project_root / 'miniapp_example/index.html'
        try:
            webapp_source = webapp_path.read_text(encoding='utf-8')
            bot_source = bot_path.read_text(encoding='utf-8')
            index_source = index_path.read_text(encoding='utf-8')
        except Exception:
            webapp_source = bot_source = index_source = ''
        checks = {
            'enabled': bool(settings.webapp_enabled),
            'public_url': bool(settings.mini_app_url),
            'http_server': 'ThreadingHTTPServer' in webapp_source and 'start_webapp_server' in webapp_source,
            'health': "'/health'" in webapp_source and "'/healthz'" in webapp_source,
            'telegram_auth': '_validate_telegram_init_data' in webapp_source and 'hmac.compare_digest' in webapp_source,
            'config_api': "'/api/config'" in webapp_source,
            'session_api': "'/api/telegram/session'" in webapp_source,
            'menu_button': 'set_chat_menu_button' in bot_source and 'MenuButtonWebApp' in bot_source,
            'graceful_stop': 'webapp_runtime.stop()' in bot_source,
            'frontend_connected': "fetch('/api/config'" in index_source and "fetch('/api/telegram/session'" in index_source,
            'open_event_api': "'/api/miniapp/open'" in webapp_source and "fetch('/api/miniapp/open'" in index_source and 'record_mini_app_open' in webapp_source,
        }
        failed = [name for name, ok in checks.items() if not ok]
        status = 'ready' if not failed else ('warning' if len(failed) <= 2 else 'blocker')
        score = max(40, 100 - len(failed) * 10)
        return {
            'code': 'embedded_miniapp_runtime',
            'title_key': 'stable_gate_embedded_miniapp_runtime',
            'status': status,
            'score': score,
            'value': sum(1 for ok in checks.values() if ok),
            'warnings': len(failed),
            'failed': ','.join(failed),
            'action_key': 'stable_action_embedded_miniapp_runtime_ready' if status == 'ready' else 'stable_action_embedded_miniapp_runtime_review',
        }

    @staticmethod
    def final_completion_audit_summary() -> dict[str, Any]:
        summary = FinalAuditService.completion_summary()
        status = 'ready' if int(summary['blockers']) == 0 else 'blocker'
        if int(summary['warnings']) > 0 and status == 'ready':
            status = 'warning'
        return {
            'status': status,
            'score': int(summary['score']),
            'title_key': 'stable_gate_final_completion_audit',
            'value': int(summary['ready']),
            'action_key': 'stable_action_final_completion_audit_ready' if status == 'ready' else 'stable_action_final_completion_audit_review',
        }

    @staticmethod
    def stable_release_summary() -> dict[str, Any]:
        """Read-only stable v3.0.0 release gate.

        Stable release is stricter than rc1: it may still surface warnings for
        missing live data in a fresh database, but it blocks dangerous schema,
        .env, rights and moderation states. It is intentionally read-only and
        keeps old Bothost /data databases safe.
        """
        summary = ReleaseReadinessService.readiness_summary()
        guardrails = ReleaseReadinessService.launch_guardrails()
        rc1_gate = ReleaseReadinessService.rc1_gate_summary()

        stars_live = _count('transactions', "entry_type = 'stars_topup' AND status = 'completed'")
        vip_live = _count('transactions', "entry_type = 'vip_purchase' AND status = 'completed'")
        campaign_money = _count('transactions', "entry_type IN ('campaign_funding', 'campaign_boost') AND status = 'completed'")
        completed_submissions = _count('task_submissions', "status = 'approved'")
        active_holds = _count('holds', "status IN ('active', 'released')")
        ready_chats = _count('bot_chats', 'is_active = 1 AND can_post = 1')
        chat_issues = _count('bot_chats', 'is_active = 0 OR can_post = 0')
        manual_queue = _count('task_submissions', "status = 'manual_review'")
        risky_unblocked = _count('users', "risk_score >= 60 AND status != 'blocked'")
        active_campaigns = _count('campaigns', "status = 'active'")
        funded_campaigns = _count('campaigns', 'is_funded = 1')
        notes = _count('admin_notes')
        owner_has_id = 1 if settings.admin_ids else 0
        data_integrity = ReleaseReadinessService.data_integrity_summary()
        config_warnings = ReleaseReadinessService.config_warning_summary()
        persistence = ReleaseReadinessService.persistence_summary()
        snapshot_safety = ReleaseReadinessService.database_snapshot_safety_summary()
        runtime_safety = ReleaseReadinessService.runtime_safety_summary()
        network_resilience = ReleaseReadinessService.network_resilience_summary()
        update_handler_safety = ReleaseReadinessService.update_handler_safety_summary()

        rows: list[dict[str, Any]] = []

        def add(code: str, title_key: str, status: str, value: int, action_key: str) -> None:
            rows.append({
                'code': code,
                'title_key': title_key,
                'status': status,
                'value': int(value),
                'action_key': action_key,
            })

        schema_ok = int(summary['blockers']) == 0 and int(summary['score']) >= 82
        add(
            'schema_env',
            'stable_gate_schema_env',
            'ready' if schema_ok else 'blocker',
            int(summary['score']),
            'stable_action_schema_env_ok' if schema_ok else 'stable_action_fix_schema_env',
        )
        add(
            'payments_vip',
            'stable_gate_payments_vip',
            'ready' if stars_live > 0 and vip_live > 0 else ('warning' if settings.enable_xtr_payments else 'blocker'),
            stars_live + vip_live,
            'stable_action_payments_vip_ok' if stars_live > 0 and vip_live > 0 else ('stable_action_payments_vip_live' if settings.enable_xtr_payments else 'stable_action_enable_stars'),
        )
        add(
            'campaign_cycle',
            'stable_gate_campaign_cycle',
            'ready' if campaign_money > 0 and active_campaigns > 0 and funded_campaigns > 0 else 'warning',
            campaign_money + active_campaigns + funded_campaigns,
            'stable_action_campaign_cycle_ok' if campaign_money > 0 and active_campaigns > 0 else 'stable_action_campaign_cycle_live',
        )
        add(
            'proof_hold',
            'stable_gate_proof_hold',
            'ready' if completed_submissions > 0 and active_holds > 0 else 'warning',
            completed_submissions + active_holds,
            'stable_action_proof_hold_ok' if completed_submissions > 0 and active_holds > 0 else 'stable_action_proof_hold_live',
        )
        add(
            'bot_rights',
            'stable_gate_bot_rights',
            'ready' if ready_chats > 0 and chat_issues == 0 else ('warning' if ready_chats > 0 else 'blocker'),
            ready_chats,
            'stable_action_bot_rights_ok' if ready_chats > 0 and chat_issues == 0 else 'stable_action_bot_rights_live',
        )
        add(
            'moderation_antifraud',
            'stable_gate_moderation_antifraud',
            'ready' if manual_queue <= 10 and risky_unblocked == 0 else ('warning' if manual_queue <= 30 and risky_unblocked <= 5 else 'blocker'),
            manual_queue + risky_unblocked + notes,
            'stable_action_moderation_ok' if manual_queue <= 10 and risky_unblocked == 0 else 'stable_action_moderation_clear',
        )
        add(
            'owner_commerce',
            'stable_gate_owner_commerce',
            'ready' if owner_has_id and _has_columns('wallets', 'available_balance', 'hold_balance', 'bonus_balance') else 'blocker',
            owner_has_id,
            'stable_action_owner_commerce_ok' if owner_has_id else 'stable_action_owner_missing',
        )
        add(
            'data_compat',
            'stable_gate_data_compat',
            'ready',
            1,
            'stable_action_data_compat_ok',
        )
        add(
            'data_integrity',
            'stable_gate_data_integrity',
            str(data_integrity['status']),
            int(data_integrity['negative_wallets']) + int(data_integrity['over_reserved_campaigns']) + int(data_integrity['orphan_active_holds']),
            'stable_action_data_integrity_ok' if data_integrity['status'] == 'ready' else 'stable_action_data_integrity_fix',
        )
        add(
            'config_parse',
            'stable_gate_config_parse',
            str(config_warnings['status']),
            int(config_warnings['warnings']),
            'stable_action_config_parse_ok' if config_warnings['status'] == 'ready' else 'stable_action_config_parse_review',
        )
        add(
            'persistence_safety',
            'stable_gate_persistence_safety',
            str(persistence['status']),
            int(persistence['score']),
            'stable_action_persistence_safety_ok' if persistence['status'] == 'ready' else 'stable_action_persistence_safety_review',
        )
        add(
            'database_snapshot_safety',
            'stable_gate_database_snapshot_safety',
            str(snapshot_safety['status']),
            int(snapshot_safety['score']),
            'stable_action_database_snapshot_safety_ok' if snapshot_safety['status'] == 'ready' else 'stable_action_database_snapshot_safety_review',
        )
        add(
            'runtime_safety',
            'stable_gate_runtime_safety',
            str(runtime_safety['status']),
            int(runtime_safety['score']),
            'stable_action_runtime_safety_ok' if runtime_safety['status'] == 'ready' else 'stable_action_runtime_safety_review',
        )


        add(
            'network_resilience',
            'stable_gate_network_resilience',
            str(network_resilience['status']),
            int(network_resilience['score']),
            'stable_action_network_resilience_ok' if network_resilience['status'] == 'ready' else 'stable_action_network_resilience_review',
        )
        add(
            'update_handler_safety',
            'stable_gate_update_handler_safety',
            str(update_handler_safety['status']),
            int(update_handler_safety['score']),
            'stable_action_update_handler_safety_ok' if update_handler_safety['status'] == 'ready' else 'stable_action_update_handler_safety_review',
        )
        boostore_api_diagnostics = ReleaseReadinessService.boostore_api_diagnostics_summary()
        add(
            'boostore_api_diagnostics',
            str(boostore_api_diagnostics['title_key']),
            str(boostore_api_diagnostics['status']),
            int(boostore_api_diagnostics['value']),
            str(boostore_api_diagnostics['action_key']),
        )

        engagement_presets = ReleaseReadinessService.engagement_presets_summary()
        add(
            'engagement_presets',
            str(engagement_presets['title_key']),
            str(engagement_presets['status']),
            int(engagement_presets['value']),
            str(engagement_presets['action_key']),
        )

        community_rules = ReleaseReadinessService.community_rules_summary()
        add(
            'community_rules',
            str(community_rules['title_key']),
            str(community_rules['status']),
            int(community_rules['value']),
            str(community_rules['action_key']),
        )

        engagement_modes = ReleaseReadinessService.engagement_modes_summary()
        add(
            'engagement_modes',
            str(engagement_modes['title_key']),
            str(engagement_modes['status']),
            int(engagement_modes['value']),
            str(engagement_modes['action_key']),
        )


        engagement_obligations = ReleaseReadinessService.engagement_obligations_summary()
        add(
            'engagement_obligations',
            str(engagement_obligations['title_key']),
            str(engagement_obligations['status']),
            int(engagement_obligations['value']),
            str(engagement_obligations['action_key']),
        )

        engagement_soft_enforcement = ReleaseReadinessService.engagement_soft_enforcement_summary()
        add(
            'engagement_soft_enforcement',
            str(engagement_soft_enforcement['title_key']),
            str(engagement_soft_enforcement['status']),
            int(engagement_soft_enforcement['value']),
            str(engagement_soft_enforcement['action_key']),
        )

        standard_admin_actions = ReleaseReadinessService.standard_admin_actions_summary()
        add(
            'standard_admin_actions',
            str(standard_admin_actions['title_key']),
            str(standard_admin_actions['status']),
            int(standard_admin_actions['value']),
            str(standard_admin_actions['action_key']),
        )

        boostore_auto_orders = ReleaseReadinessService.boostore_auto_orders_summary()
        add(
            'boostore_auto_orders',
            str(boostore_auto_orders['title_key']),
            str(boostore_auto_orders['status']),
            int(boostore_auto_orders['value']),
            str(boostore_auto_orders['action_key']),
        )

        legal_docs = ReleaseReadinessService.legal_docs_summary()
        add(
            'legal_docs',
            str(legal_docs['title_key']),
            str(legal_docs['status']),
            int(legal_docs['value']),
            str(legal_docs['action_key']),
        )

        proof_guides = ReleaseReadinessService.proof_guides_summary()
        add(
            'proof_guides',
            str(proof_guides['title_key']),
            str(proof_guides['status']),
            int(proof_guides['value']),
            str(proof_guides['action_key']),
        )

        miniapp_visual_assets = ReleaseReadinessService.miniapp_visual_assets_summary()
        add(
            'miniapp_visual_assets',
            str(miniapp_visual_assets['title_key']),
            str(miniapp_visual_assets['status']),
            int(miniapp_visual_assets['value']),
            str(miniapp_visual_assets['action_key']),
        )


        embedded_miniapp_runtime = ReleaseReadinessService.embedded_miniapp_runtime_summary()
        add(
            'embedded_miniapp_runtime',
            str(embedded_miniapp_runtime['title_key']),
            str(embedded_miniapp_runtime['status']),
            int(embedded_miniapp_runtime['value']),
            str(embedded_miniapp_runtime['action_key']),
        )

        final_completion_audit = ReleaseReadinessService.final_completion_audit_summary()
        add(
            'final_completion_audit',
            str(final_completion_audit['title_key']),
            str(final_completion_audit['status']),
            int(final_completion_audit['value']),
            str(final_completion_audit['action_key']),
        )

        row_blockers = sum(1 for row in rows if row['status'] == 'blocker')
        row_warnings = sum(1 for row in rows if row['status'] == 'warning')
        combined_base = int(round((int(summary['score']) + int(guardrails['live_score']) + int(rc1_gate['score'])) / 3))
        stable_score = max(0, min(100, combined_base - row_blockers * 12 - row_warnings * 4))
        if row_blockers:
            state = 'blocked'
        elif stable_score >= 90 and row_warnings <= 2:
            state = 'stable_ready'
        elif stable_score >= 82 and row_warnings <= 4:
            state = 'stable_guarded'
        elif stable_score >= 72:
            state = 'live_control'
        else:
            state = 'needs_work'

        return {
            'state': state,
            'score': stable_score,
            'blockers': row_blockers,
            'warnings': row_warnings,
            'rows': rows,
        }

    @staticmethod
    def stable_release_contract() -> list[str]:
        """Owner-facing stable-release discipline for v3.0.0."""
        return [
            'stable_contract_backup_data',
            'stable_contract_no_breaking_updates',
            'stable_contract_live_money_checked',
            'stable_contract_rights_checked',
            'stable_contract_monitor_first_day',
            'stable_contract_next_updates_patch_only',
            'stable_contract_patch_301_policy',
            'stable_contract_patch_302_policy',
            'stable_contract_patch_303_policy',
            'stable_contract_patch_304_policy',
            'stable_contract_patch_305_policy',
            'stable_contract_major_312_policy',
            'stable_contract_major_313_policy',
            'stable_contract_major_314_policy',
            'stable_contract_major_314_modes_policy',
            'stable_contract_major_315_policy',
            'stable_contract_major_316_policy',
            'stable_contract_major_317_policy',
            'stable_contract_major_320_policy',
            'stable_contract_major_321_policy',
            'stable_contract_major_322_policy',
            'stable_contract_patch_323_policy',
            'stable_contract_patch_324_policy',
            'stable_contract_patch_325_policy',
            'stable_contract_patch_326_policy',
        ]

