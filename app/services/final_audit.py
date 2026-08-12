from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app import db
from app.config import settings
from app.services.boostore_provider import BoostoreProviderService
from app.services.community_rules import CommunityRulesService
from app.services.engagement_growth import EngagementGrowthService
from app.services.economy import INTERNAL_CURRENCY_NAME_RU
from app.services.engagement_modes import EngagementModeService
from app.services.legal_docs import LegalDocsService
from app.services.platform_agreement import PlatformAgreementService
from app.services.advertising_network import AdvertisingNetworkService
from app.services.runtime_settings import RuntimeSettingsService
from app.services.star_payments import StarPaymentService
from app.services.wallets import WalletService
from app.services.standard_admin import StandardAdminService
from app.version import APP_STAGE, APP_VERSION


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
    practical owner-side checklist covering the cumulative modernization through
    v3.5.1: smart menu, standalone Mini App, unified Sparks and bonuses,
    mandatory agreement, advertising network, optional provider pricing, owner
    financial controls, Standard/PRO and runtime safety.
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
            and _source_contains('miniapp_example/index.html', 'Основные разделы', 'Заработать Искры', 'Сеть рекламных размещений', 'Standard', 'PRO', 'assets/hero-growth.webp', 'telegram-web-app.js', 'tg.ready()', 'tg.expand()', "api('catalog.get'", "api('wallet.get'", "api('campaigns.get'", "api('tasks.get'"),
            action_ok='final_audit_action_mini_app_ok',
            action_bad='final_audit_action_mini_app_fix',
        )
        add(
            'mini_app_visual_assets',
            'final_audit_mini_app_visual_assets',
            all((PROJECT_ROOT / 'miniapp_example/assets' / name).exists() for name in (
                'hero-growth.webp', 'telegram-profile.webp', 'server-status.webp', 'bot-actions.webp',
                'liker.webp', 'commenter.webp', 'boostore.webp', 'standard.webp', 'pro.webp',
                'obligations.webp', 'community-rules.webp', 'wallet-hold.webp',
                'release-center.webp', 'boostora-logo.png',
            ))
            and _source_contains(
                'miniapp_example/index.html',
                'assets/hero-growth.webp', 'assets/liker.webp', 'assets/commenter.webp',
                'assets/boostora-logo.png', 'assets/release-center.webp',
            ),
            value=(
                len(list((PROJECT_ROOT / 'miniapp_example/assets').glob('*.webp')))
                + len(list((PROJECT_ROOT / 'miniapp_example/assets').glob('*.png')))
            ) if (PROJECT_ROOT / 'miniapp_example/assets').exists() else 0,
            action_ok='final_audit_action_mini_app_visual_ok',
            action_bad='final_audit_action_mini_app_visual_fix',
        )
        add(
            'sparks_core_priority',
            'final_audit_sparks_core_priority',
            APP_VERSION == 'Boostora v3.6.3'
            and APP_STAGE == 'boostorachat_start_gate'
            and INTERNAL_CURRENCY_NAME_RU == 'Искры'
            and _source_contains('miniapp_example/index.html', 'Основные разделы', 'Заработать Искры', 'Сеть рекламных размещений', 'Дополнительные возможности', 'Дополнительные услуги')
            and _source_contains('app/texts.py', "'marketplace_button': '🧰 Дополнительные услуги'", "'wallet_topup_button': 'Купить Искры за ⭐'")
            and _source_contains('app/keyboards/inline.py', 'def smart_hub_keyboard', "'community_rules_button'", "'marketplace_button'"),
            action_ok='final_audit_action_sparks_priority_ok',
            action_bad='final_audit_action_sparks_priority_fix',
        )
        add(
            'embedded_mini_app_runtime',
            'final_audit_embedded_mini_app_runtime',
            settings.webapp_enabled
            and bool(settings.mini_app_url)
            and _source_contains('app/webapp.py', 'ThreadingHTTPServer', "'/health'", "'/api/config'", "'/api/telegram/session'", "'/api/miniapp/query'", '_validate_telegram_init_data', 'hmac.compare_digest', 'MiniAppApiService.dispatch')
            and _source_contains('app/bot.py', 'start_webapp_server()', 'set_chat_menu_button', 'MenuButtonWebApp', 'webapp_runtime.stop()')
            and _source_contains('miniapp_example/index.html', "fetch('/api/telegram/session'", "fetch('/api/miniapp/query'", "fetch('/api/miniapp/open'", 'tg.openInvoice', 'renderManagement', 'owner.catalog_action'),
            action_ok='final_audit_action_embedded_mini_app_ok',
            action_bad='final_audit_action_embedded_mini_app_fix',
        )
        add(
            'standalone_mini_app_operations',
            'final_audit_mini_app_cabinet',
            _source_contains('app/services/miniapp_api.py', 'class MiniAppApiService', "op == 'catalog.get'", "op == 'wallet.get'", "op == 'campaigns.get'", "op == 'tasks.get'", "op == 'network.get'", "op == 'documents.accept'", "op == 'owner.catalog_action'")
            and _source_contains('miniapp_example/index.html', "api('engagement.pro_purchase'", "api('network.quote'", "api('catalog.quote_order'", "api('wallet.invoice'")
            and _source_contains('app/keyboards/reply.py', 'Открыть Boostora', 'WebAppInfo'),
            action_ok='final_audit_action_mini_app_ok',
            action_bad='final_audit_action_mini_app_fix',
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
            and hasattr(EngagementModeService, 'purchase_pro_with_credits')
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
            'unified_economy',
            'final_audit_unified_economy',
            _has_columns('wallets', 'available_balance', 'bonus_balance', 'hold_balance')
            and _has_columns('star_payments', 'user_id', 'telegram_payment_charge_id', 'stars_amount', 'credits_granted', 'status')
            and hasattr(WalletService, 'spend_with_bonus_cap')
            and hasattr(WalletService, 'adjust_balance')
            and hasattr(StarPaymentService, 'apply_credit_purchase')
            and hasattr(StarPaymentService, 'refund_credit_purchase')
            and RuntimeSettingsService.get_int('credits_per_star') > 0
            and 0 <= RuntimeSettingsService.get_int('max_bonus_payment_percent') <= 50,
            action_ok='final_audit_action_v350_ready',
            action_bad='final_audit_action_v350_fix',
        )
        add(
            'mandatory_platform_agreement',
            'final_audit_platform_agreement',
            _has_columns('platform_agreement_events', 'user_id', 'agreement_version', 'action', 'source')
            and bool(PlatformAgreementService.version())
            and _source_contains('app/services/miniapp_api.py', 'PlatformAgreementService.is_accepted', "op == 'documents.accept'", "op == 'documents.decline'")
            and _source_contains('app/handlers/start.py', 'PlatformAgreementService.is_accepted')
            and _source_contains('app/handlers/callbacks.py', 'PlatformAgreementService.is_accepted'),
            action_ok='final_audit_action_v350_ready',
            action_bad='final_audit_action_v350_fix',
        )
        add(
            'advertising_network',
            'final_audit_ad_network',
            _has_columns('network_campaigns', 'owner_user_id', 'budget_credits', 'bonus_used', 'target_chat_id', 'status')
            and _has_columns('network_placements', 'campaign_id', 'host_chat_id', 'tracking_token', 'invite_link', 'reciprocal_placement_id', 'refunded_credits')
            and _has_columns('network_join_events', 'placement_id', 'user_id', 'retained_24h', 'retained_7d')
            and _has_columns('network_contribution_ledger', 'user_id', 'units', 'entry_type')
            and hasattr(AdvertisingNetworkService, 'quote_budget')
            and hasattr(AdvertisingNetworkService, 'create_campaign')
            and hasattr(AdvertisingNetworkService, 'run_due_placements')
            and hasattr(AdvertisingNetworkService, 'handle_platform_deactivated')
            and RuntimeSettingsService.get_int('network_min_members') >= 100,
            action_ok='final_audit_action_v350_ready',
            action_bad='final_audit_action_v350_fix',
        )
        add(
            'owner_financial_controls',
            'final_audit_owner_finance',
            hasattr(WalletService, 'adjust_balance')
            and hasattr(WalletService, 'list_transactions')
            and _source_contains('app/services/miniapp_api.py', "op == 'owner.user_lookup'", "op == 'owner.operations'", "op == 'owner.adjust_balance'", "op == 'owner.star_payments'", "op == 'owner.refund_star_payment'")
            and _source_contains('miniapp_example/index.html', 'showOwnerStarPayments', 'showOwnerRefund', 'owner.adjust_balance'),
            action_ok='final_audit_action_v350_ready',
            action_bad='final_audit_action_v350_fix',
        )
        add(
            'boostore_provider_auto_orders',
            'final_audit_boostore_provider_auto_orders',
            _has_columns('provider_services', 'external_service_id', 'is_enabled', 'markup_percent', 'rate_value', 'raw_json')
            and _has_columns('provider_orders', 'owner_user_id', 'provider_status', 'last_error', 'placed_at', 'paid_at', 'credit_cost', 'bonus_used', 'rate_value_snapshot', 'markup_percent_snapshot', 'expires_at')
            and hasattr(BoostoreProviderService, 'live_diagnostics')
            and hasattr(BoostoreProviderService, 'refresh_service_price')
            and hasattr(BoostoreProviderService, 'quote_credit_order')
            and hasattr(BoostoreProviderService, 'prepare_credit_order')
            and hasattr(BoostoreProviderService, 'expire_stale_orders')
            and hasattr(BoostoreProviderService, 'place_prepared_order'),
            action_ok='final_audit_action_boostore_ok',
            action_bad='final_audit_action_boostore_fix',
        )
        add(
            'provider_exact_price',
            'final_audit_provider_exact_price',
            _source_contains('app/services/boostore_provider.py', 'refresh_service_price', 'quote_credit_order', 'expected_credit_cost', 'boostore_price_changed', 'provider_credits_per_price_unit')
            and _source_contains('app/services/miniapp_api.py', "op in {'catalog.quote_order', 'catalog.prepare_order'}", "op == 'catalog.quote_order'")
            and _source_contains('miniapp_example/index.html', "api('catalog.quote_order'", 'expected_credit_cost')
            and hasattr(BoostoreProviderService, 'set_markup'),
            action_ok='final_audit_action_v350_ready',
            action_bad='final_audit_action_v350_fix',
        )
        add(
            'provider_order_timeout',
            'final_audit_order_timeout',
            RuntimeSettingsService.get_int('provider_order_timeout_minutes') >= 5
            and hasattr(BoostoreProviderService, 'expire_stale_orders')
            and _source_contains('app/bot.py', 'expire_stale_orders')
            and _source_contains('miniapp_example/index.html', "expired:'Время подтверждения истекло'"),
            action_ok='final_audit_action_v350_ready',
            action_bad='final_audit_action_v350_fix',
        )
        add(
            'telegram_service_catalog',
            'final_audit_telegram_service_catalog',
            hasattr(BoostoreProviderService, 'catalog_categories')
            and hasattr(BoostoreProviderService, 'catalog_subcategories')
            and hasattr(BoostoreProviderService, 'set_catalog_enabled')
            and hasattr(BoostoreProviderService, 'normalize_telegram_link')
            and _source_contains('app/services/boostore_provider.py', 'current_only=True', 'last_synced_at IS NOT NULL', 'normalize_telegram_link')
            and _source_contains('app/router.py', 'SCREEN_MARKETPLACE_CATEGORY_PREFIX', 'SCREEN_OWNER_PROVIDER_SUBCATEGORY_PREFIX', 'html.escape')
            and _source_contains('app/handlers/callbacks.py', "parsed.action == 'boostore_bulk'", 'get_public_service')
            and _source_contains('app/keyboards/inline.py', 'marketplace_category_keyboard', 'owner_provider_services_keyboard'),
            action_ok='final_audit_action_telegram_catalog_ok',
            action_bad='final_audit_action_telegram_catalog_fix',
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
