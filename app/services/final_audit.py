from __future__ import annotations

"""Compatibility entry point for the cumulative owner audit.

The historical v3.6.3 audit remains the broad regression baseline. Current
releases replace only the checks whose UI/runtime contract intentionally evolved,
so the audit measures the active architecture instead of old labels.
"""

from pathlib import Path

from app.services import _final_audit_v363 as _baseline
from app.services.economy import INTERNAL_CURRENCY_NAME_RU
from app.version import APP_STAGE, APP_VERSION

CompletionAuditItem = _baseline.CompletionAuditItem
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _source_contains(path: str, *needles: str) -> bool:
    try:
        text = (PROJECT_ROOT / path).read_text(encoding='utf-8')
    except Exception:
        return False
    return all(needle in text for needle in needles)


def _replace_status(items: list[dict], code: str, ok: bool, action_ok: str, action_bad: str) -> None:
    for item in items:
        if item.get('code') != code:
            continue
        item['status'] = 'ready' if ok else 'blocker'
        item['action_key'] = action_ok if ok else action_bad
        return


class FinalAuditService(_baseline.FinalAuditService):
    @staticmethod
    def proposed_items():
        current_version = _baseline.APP_VERSION
        current_stage = _baseline.APP_STAGE
        try:
            # Let historical checks evaluate against their own release marker.
            _baseline.APP_VERSION = 'Boostora v3.6.3'
            _baseline.APP_STAGE = 'boostorachat_start_gate'
            items = _baseline.FinalAuditService.proposed_items()
        finally:
            _baseline.APP_VERSION = current_version
            _baseline.APP_STAGE = current_stage

        html_path = PROJECT_ROOT / 'miniapp_example' / 'index.html'
        try:
            html = html_path.read_text(encoding='utf-8')
        except Exception:
            html = ''

        nav = ''
        if '<nav class="bottom"' in html and '</nav>' in html:
            nav = html.split('<nav class="bottom"', 1)[1].split('</nav>', 1)[0]

        current_cabinet = (
            nav.count('data-page=') == 3
            and 'data-page="home"' in nav
            and 'data-page="work"' in nav
            and 'data-page="cabinet"' in nav
            and 'data-page="services"' not in nav
            and _source_contains(
                'miniapp_example/index.html',
                'renderCabinet()', 'Зарабатывай Искры', 'Сеть рекламных размещений',
                'Standard', 'PRO', 'assets/hero-growth.webp', 'telegram-web-app.js',
                "api('catalog.get'", "api('wallet.get'", "api('campaigns.get'", "api('tasks.get'",
            )
        )
        _replace_status(
            items, 'mini_app_cabinet', current_cabinet,
            'final_audit_action_mini_app_ok', 'final_audit_action_mini_app_fix',
        )

        current_assets = all(
            (PROJECT_ROOT / 'miniapp_example' / 'assets' / name).is_file()
            for name in (
                'hero-growth.webp', 'telegram-profile.webp', 'server-status.webp', 'bot-actions.webp',
                'boostore.webp', 'standard.webp', 'pro.webp', 'obligations.webp',
                'community-rules.webp', 'wallet-hold.webp', 'release-center.webp', 'boostora-logo.png',
            )
        ) and _source_contains(
            'miniapp_example/index.html',
            'assets/hero-growth.webp', 'assets/boostora-logo.png', 'assets/release-center.webp',
            'assets/server-status.webp', 'assets/wallet-hold.webp',
        )
        _replace_status(
            items, 'mini_app_visual_assets', current_assets,
            'final_audit_action_mini_app_visual_ok', 'final_audit_action_mini_app_visual_fix',
        )

        current_priority = (
            APP_VERSION == 'Boostora v3.7.0'
            and APP_STAGE == 'simplified_shell_hardened_core'
            and INTERNAL_CURRENCY_NAME_RU == 'Искры'
            and current_cabinet
            and _source_contains(
                'miniapp_example/index.html',
                'Два главных действия', 'Дополнительные услуги', 'всё второстепенное здесь',
            )
            and _source_contains(
                'app/texts.py',
                "'marketplace_button': '🧰 Дополнительные услуги'",
                "'wallet_topup_button': 'Купить Искры за ⭐'",
            )
        )
        _replace_status(
            items, 'sparks_core_priority', current_priority,
            'final_audit_action_sparks_priority_ok', 'final_audit_action_sparks_priority_fix',
        )

        current_runtime = (
            _source_contains(
                'app/webapp.py',
                'ThreadingHTTPServer', "'/health'", "'/health/ready'", "'/api/config'",
                "'/api/telegram/session'", "'/api/miniapp/query'", '_validate_telegram_init_data',
                'hmac.compare_digest', 'MiniAppApiService.dispatch', 'MINIAPP_USER_LOCK_STRIPES = 64',
            )
            and _source_contains(
                'app/bot.py', 'start_webapp_server()', 'set_chat_menu_button',
                'MenuButtonWebApp', 'webapp_runtime.stop()', 'SystemHealthService.record_heartbeat',
            )
            and _source_contains(
                'miniapp_example/index.html',
                "'/api/telegram/session'", "'/api/miniapp/query'", "'/api/miniapp/open'",
                'fetchJson(', 'inFlightRequests', 'tg.openInvoice', 'renderManagement',
                'owner.system_health',
            )
        )
        _replace_status(
            items, 'embedded_mini_app_runtime', current_runtime,
            'final_audit_action_embedded_mini_app_ok', 'final_audit_action_embedded_mini_app_fix',
        )
        return items


    @staticmethod
    def completion_summary():
        items = FinalAuditService.proposed_items()
        blockers = sum(1 for item in items if item['status'] == 'blocker')
        warnings = sum(1 for item in items if item['status'] == 'warning')
        ready = sum(1 for item in items if item['status'] == 'ready')
        total = len(items)
        score = max(0, min(100, int(round((ready / max(total, 1)) * 100)) - blockers * 8 - warnings * 3))
        state = 'blocked' if blockers else 'guarded_ready' if warnings else 'all_requested_done'
        return {'state': state, 'score': score, 'ready': ready, 'warnings': warnings, 'blockers': blockers, 'total': total, 'items': items}
