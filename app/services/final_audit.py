from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app import db
from app.config import settings
from app.services.boostore_provider import BoostoreProviderService
from app.services.community_rules import CommunityRulesService
from app.services.engagement_growth import EngagementGrowthService
from app.services.engagement_modes import EngagementModeService
from app.services.legal_docs import LegalDocsService
from app.services.standard_admin import StandardAdminService


PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class CompletionAuditItem:
    code: str
    title_key: str
    status: str
    value: int
    action_key: str

    def as_dict(self) -> dict[str, Any]:
        return {
            'code': self.code,
            'title_key': self.title_key,
            'status': self.status,
            'value': self.value,
            'action_key': self.action_key,
        }


def _columns(table: str) -> set[str]:
    try:
        return {str(row['name']) for row in db.fetch_all(f'PRAGMA table_info({table})')}
    except Exception:
        return set()


def _has_columns(table: str, *names: str) -> bool:
    cols = _columns(table)
    return bool(cols) and all(name in cols for name in names)


def _source_contains(path: str, *needles: str) -> bool:
    try:
        source_path = Path(path)
        if not source_path.is_absolute():
            source_path = PROJECT_ROOT / source_path
        text = source_path.read_text(encoding='utf-8')
    except Exception:
        return False
    return all(needle in text for needle in needles)


class FinalAuditService:
    """Read-only audit: checks that the user's requested Boostora upgrades exist.

    This is not a legal guarantee and it does not call external APIs. It is a
    practical owner-side checklist covering the features requested during the
    v3.1/v3.2 modernization: smart menu, Mini App, Boostore provider, Standard
    0/10, PRO, rules, legal docs, admin debt tools and runtime safety.
    """

    @staticmethod
    def proposed_items() -> list[dict[str, Any]]:
        items: list[CompletionAuditItem] = []

        def add(code: str, title_key: str, ok: bool, value: int = 1, *, warning: bool = False, action_ok: str = '', action_bad: str = '') -> None:
            status = 'ready' if ok and not warning else ('warning' if ok else 'blocker')
            items.append(CompletionAuditItem(
                code=code,
                title_key=title_key,
                status=status,
                value=int(value),
                action_key=action_ok if ok else action_bad,
            ))

        add(
            'old_core_preserved',
            'final_audit_old_core_preserved',
            _has_columns('campaigns', 'pricing_json', 'unit_price', 'reward_amount', 'budget_total')
            and _has_columns('task_submissions', 'proof_text', 'risk_score', 'reviewed_at')
            and _has_columns('wallets', 'available_balance', 'hold_balance', 'bonus_balance'),
            action_ok='final_audit_action_old_core_ok',
            action_bad='final_audit_action_old_core_fix',
        )
        add(
            'smart_menu_hub',
            'final_audit_smart_menu_hub',
            settings.smart_bottom_menu in {'compact', 'hidden', 'full'}
            and _source_contains('app/services/smart_hub.py', 'class SmartHubService')
            and _source_contains('app/router.py', 'SCREEN_SMART_HUB'),
            action_ok='final_audit_action_smart_menu_ok',
            action_bad='final_audit_action_smart_menu_fix',
        )
        add(
            'mini_app_cabinet',
            'final_audit_mini_app_cabinet',
            (PROJECT_ROOT / 'miniapp_example/index.html').exists()
            and _source_contains('miniapp_example/index.html', 'Оживи Telegram-канал', 'Standard', 'Boostore', 'assets/hero-growth.svg', 'telegram-web-app.js', 'tg.ready()', 'tg.expand()'),
            action_ok='final_audit_action_mini_app_ok',
            action_bad='final_audit_action_mini_app_fix',
        )
        add(
            'mini_app_visual_assets',
            'final_audit_mini_app_visual_assets',
            (PROJECT_ROOT / 'miniapp_example/assets/hero-growth.svg').exists()
            and (PROJECT_ROOT / 'miniapp_example/assets/liker.svg').exists()
            and (PROJECT_ROOT / 'miniapp_example/assets/commenter.svg').exists()
            and _source_contains('miniapp_example/index.html', 'assets/hero-growth.svg', 'assets/liker.svg', 'assets/commenter.svg'),
            value=len(list((PROJECT_ROOT / 'miniapp_example/assets').glob('*.svg'))) if (PROJECT_ROOT / 'miniapp_example/assets').exists() else 0,
            action_ok='final_audit_action_mini_app_visual_ok',
            action_bad='final_audit_action_mini_app_visual_fix',
        )
        add(
            'embedded_mini_app_runtime',
            'final_audit_embedded_mini_app_runtime',
            settings.webapp_enabled
            and bool(settings.mini_app_url)
            and _source_contains('app/webapp.py', 'ThreadingHTTPServer', "'/health'", "'/api/config'", "'/api/telegram/session'", '_validate_telegram_init_data', 'hmac.compare_digest')
            and _source_contains('app/bot.py', 'start_webapp_server()', 'set_chat_menu_button', 'MenuButtonWebApp', 'webapp_runtime.stop()')
            and _source_contains('miniapp_example/index.html', "fetch('/api/config'", "fetch('/api/telegram/session'", "fetch('/api/miniapp/open'"),
            action_ok='final_audit_action_embedded_mini_app_ok',
            action_bad='final_audit_action_embedded_mini_app_fix',
        )
        add(
            'engagement_landing_presets',
            'final_audit_engagement_landing_presets',
            _source_contains('app/services/engagement_growth.py', 'class EngagementGrowthService', 'preset_by_code')
            and len(EngagementGrowthService.presets()) >= 9,
            value=len(EngagementGrowthService.presets()) if hasattr(EngagementGrowthService, 'presets') else 0,
            action_ok='final_audit_action_engagement_presets_ok',
            action_bad='final_audit_action_engagement_presets_fix',
        )
        add(
            'standard_pro_modes',
            'final_audit_standard_pro_modes',
            _has_columns('engagement_memberships', 'mode', 'pro_expires_at', 'reciprocal_required_actions')
            and hasattr(EngagementModeService, 'activate_pro')
            and hasattr(EngagementModeService, 'create_obligation_for_campaign'),
            action_ok='final_audit_action_standard_pro_ok',
            action_bad='final_audit_action_standard_pro_fix',
        )
        add(
            'obligations_dashboard_soft_enforcement',
            'final_audit_obligations_dashboard_soft_enforcement',
            _has_columns('engagement_obligations', 'required_actions', 'due_at', 'warning_sent_at', 'admin_warning_sent_at')
            and hasattr(EngagementModeService, 'obligation_dashboard')
            and hasattr(EngagementModeService, 'can_launch_engagement'),
            action_ok='final_audit_action_obligations_ok',
            action_bad='final_audit_action_obligations_fix',
        )
        add(
            'standard_admin_tools',
            'final_audit_standard_admin_tools',
            _has_columns('engagement_admin_decisions', 'admin_user_id', 'target_user_id', 'obligation_id', 'action')
            and hasattr(StandardAdminService, 'extend_obligation')
            and hasattr(StandardAdminService, 'forgive_obligation')
            and hasattr(StandardAdminService, 'grant_manual_pro'),
            action_ok='final_audit_action_standard_admin_ok',
            action_bad='final_audit_action_standard_admin_fix',
        )
        add(
            'rules_and_legal_docs',
            'final_audit_rules_and_legal_docs',
            _has_columns('community_rule_acceptances', 'user_id', 'rules_version')
            and _has_columns('legal_doc_acceptances', 'user_id', 'legal_version')
            and CommunityRulesService.is_required() in {True, False}
            and LegalDocsService.is_required() in {True, False},
            action_ok='final_audit_action_rules_legal_ok',
            action_bad='final_audit_action_rules_legal_fix',
        )
        add(
            'boostore_provider_auto_orders',
            'final_audit_boostore_provider_auto_orders',
            _has_columns('provider_services', 'external_service_id', 'is_enabled', 'markup_percent')
            and _has_columns('provider_orders', 'owner_user_id', 'provider_status', 'last_error', 'placed_at')
            and hasattr(BoostoreProviderService, 'live_diagnostics')
            and hasattr(BoostoreProviderService, 'prepare_order')
            and hasattr(BoostoreProviderService, 'place_prepared_order'),
            action_ok='final_audit_action_boostore_ok',
            action_bad='final_audit_action_boostore_fix',
        )
        add(
            'runtime_network_update_guard',
            'final_audit_runtime_network_update_guard',
            (_source_contains('app/bot.py', '_process_updates', 'bot.process_new_updates([update])', 'Only this update is skipped', '_initial_poll_offset', 'settings.drop_pending_updates')
            and _source_contains('app/bot.py', '_run_background_job', '_run_background_cycle', 'remaining jobs will continue', 'settings.background_worker_interval_seconds')
            and _source_contains('app/bot.py', '_release_single_instance_lock(lock_fd)', 'finally:', '_install_shutdown_handlers', '_wait_for_shutdown', 'promo_thread.join(timeout=5)')),
            action_ok='final_audit_action_runtime_ok',
            action_bad='final_audit_action_runtime_fix',
        )
        add(
            'database_snapshot_safety',
            'final_audit_database_snapshot_safety',
            _source_contains('app/db.py', '_copy_sqlite_snapshot', 'source_connection.backup(target_connection)', 'PRAGMA integrity_check', 'os.replace(temporary, target)', 'settings.legacy_db_mirror_enabled', 'create_periodic_backup', 'settings.db_backup_interval_hours', 'settings.db_backup_max_files'),
            action_ok='final_audit_action_database_snapshot_ok',
            action_bad='final_audit_action_database_snapshot_fix',
        )
        add(
            'secret_hygiene',
            'final_audit_secret_hygiene',
            not _source_contains('README.md', settings.boostore_api_key) if settings.boostore_api_key else True,
            action_ok='final_audit_action_secret_ok',
            action_bad='final_audit_action_secret_fix',
        )
        return [item.as_dict() for item in items]

    @staticmethod
    def completion_summary() -> dict[str, Any]:
        items = FinalAuditService.proposed_items()
        blockers = sum(1 for item in items if item['status'] == 'blocker')
        warnings = sum(1 for item in items if item['status'] == 'warning')
        ready = sum(1 for item in items if item['status'] == 'ready')
        total = len(items)
        score = max(0, min(100, int(round((ready / max(total, 1)) * 100)) - blockers * 8 - warnings * 3))
        if blockers:
            state = 'blocked'
        elif warnings:
            state = 'guarded_ready'
        else:
            state = 'all_requested_done'
        return {
            'state': state,
            'score': score,
            'ready': ready,
            'warnings': warnings,
            'blockers': blockers,
            'total': total,
            'items': items,
        }
