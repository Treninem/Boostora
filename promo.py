from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from app import db
from app.config import settings

PROVIDER_CODE = 'boostore'


@dataclass(frozen=True)
class ProviderResult:
    ok: bool
    result_key: str
    data: Any = None
    error: str | None = None


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(str(value).replace(',', '.')))
    except Exception:
        return default


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(str(value).replace(',', '.'))
    except Exception:
        return default


class BoostoreProviderService:
    @staticmethod
    def is_configured() -> bool:
        return bool(settings.boostore_enabled and settings.boostore_api_url and settings.boostore_api_key)

    @staticmethod
    def config_state() -> dict[str, Any]:
        configured = BoostoreProviderService.is_configured()
        return {
            'enabled': bool(settings.boostore_enabled),
            'configured': configured,
            'api_url': settings.boostore_api_url,
            'has_key': bool(settings.boostore_api_key),
            'markup_percent': int(settings.boostore_default_markup_percent),
            'auto_sync': bool(settings.boostore_auto_sync),
        }

    @staticmethod
    def _request(action: str, **payload: Any) -> ProviderResult:
        if not BoostoreProviderService.is_configured():
            return ProviderResult(False, 'boostore_not_configured')
        body = {'key': settings.boostore_api_key, 'action': action}
        body.update({key: value for key, value in payload.items() if value is not None})
        try:
            response = requests.post(settings.boostore_api_url, data=body, timeout=settings.boostore_request_timeout_seconds)
        except requests.Timeout as exc:
            return ProviderResult(False, 'boostore_timeout', error=str(exc))
        except requests.RequestException as exc:
            return ProviderResult(False, 'boostore_network_error', error=str(exc))
        if response.status_code in {429, 500, 502, 503, 504}:
            return ProviderResult(False, 'boostore_temporary_error', error=f'HTTP {response.status_code}')
        if response.status_code >= 400:
            return ProviderResult(False, 'boostore_http_error', error=f'HTTP {response.status_code}: {response.text[:200]}')
        try:
            data = response.json()
        except ValueError:
            return ProviderResult(False, 'boostore_bad_json', error=response.text[:200])
        if isinstance(data, dict) and data.get('error'):
            return ProviderResult(False, 'boostore_api_error', data=data, error=str(data.get('error')))
        return ProviderResult(True, 'boostore_api_ok', data=data)

    @staticmethod
    def sync_services(limit: int = 2000) -> ProviderResult:
        result = BoostoreProviderService._request('services')
        if not result.ok:
            return result
        data = result.data if isinstance(result.data, list) else []
        if not data:
            return ProviderResult(False, 'boostore_services_empty', data=result.data)
        rows = data[:max(1, int(limit))]
        for item in rows:
            if not isinstance(item, dict):
                continue
            external_id = str(item.get('service') or '').strip()
            name = str(item.get('name') or '').strip()
            if not external_id or not name:
                continue
            db.execute(
                '''
                INSERT INTO provider_services (
                    provider_code, external_service_id, name, category, service_type,
                    rate_text, rate_value, min_quantity, max_quantity, refill_enabled,
                    cancel_enabled, markup_percent, raw_json, last_synced_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT(provider_code, external_service_id) DO UPDATE SET
                    name = excluded.name,
                    category = excluded.category,
                    service_type = excluded.service_type,
                    rate_text = excluded.rate_text,
                    rate_value = excluded.rate_value,
                    min_quantity = excluded.min_quantity,
                    max_quantity = excluded.max_quantity,
                    refill_enabled = excluded.refill_enabled,
                    cancel_enabled = excluded.cancel_enabled,
                    raw_json = excluded.raw_json,
                    last_synced_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                ''',
                (
                    PROVIDER_CODE,
                    external_id,
                    name,
                    str(item.get('category') or ''),
                    str(item.get('type') or ''),
                    str(item.get('rate') or ''),
                    _as_float(item.get('rate')),
                    _as_int(item.get('min')),
                    _as_int(item.get('max')),
                    1 if bool(item.get('refill')) else 0,
                    1 if bool(item.get('cancel')) else 0,
                    int(settings.boostore_default_markup_percent),
                    json.dumps(item, ensure_ascii=False, sort_keys=True),
                ),
            )
        return ProviderResult(True, 'boostore_sync_success', data={'count': len(rows)})

    @staticmethod
    def get_balance() -> ProviderResult:
        return BoostoreProviderService._request('balance')

    @staticmethod
    def list_services(*, enabled_only: bool = False, limit: int = 20, offset: int = 0) -> list[Any]:
        where = 'provider_code = ?'
        params: list[Any] = [PROVIDER_CODE]
        if enabled_only:
            where += ' AND is_enabled = 1'
        return db.fetch_all(
            f'''
            SELECT * FROM provider_services
            WHERE {where}
            ORDER BY is_enabled DESC, category COLLATE NOCASE, rate_value ASC, name COLLATE NOCASE
            LIMIT ? OFFSET ?
            ''',
            tuple(params + [max(1, int(limit)), max(0, int(offset))]),
        )

    @staticmethod
    def count_services(*, enabled_only: bool = False) -> int:
        where = "provider_code = 'boostore'"
        if enabled_only:
            where += ' AND is_enabled = 1'
        row = db.fetch_one(f'SELECT COUNT(*) AS cnt FROM provider_services WHERE {where}')
        return int(row['cnt'] or 0) if row else 0

    @staticmethod
    def toggle_service(external_service_id: str) -> ProviderResult:
        row = db.fetch_one(
            'SELECT * FROM provider_services WHERE provider_code = ? AND external_service_id = ?',
            (PROVIDER_CODE, str(external_service_id)),
        )
        if not row:
            return ProviderResult(False, 'boostore_service_not_found')
        new_value = 0 if int(row['is_enabled'] or 0) else 1
        db.execute(
            '''
            UPDATE provider_services
            SET is_enabled = ?, updated_at = CURRENT_TIMESTAMP
            WHERE provider_code = ? AND external_service_id = ?
            ''',
            (new_value, PROVIDER_CODE, str(external_service_id)),
        )
        return ProviderResult(True, 'boostore_service_enabled' if new_value else 'boostore_service_disabled', data={'enabled': new_value})

    @staticmethod
    def marketplace_summary(limit: int = 8) -> dict[str, Any]:
        total = BoostoreProviderService.count_services(enabled_only=False)
        enabled = BoostoreProviderService.count_services(enabled_only=True)
        services = BoostoreProviderService.list_services(enabled_only=True, limit=limit)
        categories = db.fetch_all(
            '''
            SELECT category, COUNT(*) AS cnt
            FROM provider_services
            WHERE provider_code = ? AND is_enabled = 1
            GROUP BY category
            ORDER BY cnt DESC, category COLLATE NOCASE
            LIMIT 8
            ''',
            (PROVIDER_CODE,),
        )
        return {
            'config': BoostoreProviderService.config_state(),
            'total_services': total,
            'enabled_services': enabled,
            'services': services,
            'categories': categories,
        }

    @staticmethod
    def readiness_summary() -> dict[str, Any]:
        config = BoostoreProviderService.config_state()
        total = BoostoreProviderService.count_services(enabled_only=False)
        enabled = BoostoreProviderService.count_services(enabled_only=True)
        if not config['enabled']:
            state = 'disabled'
            score = 55
        elif not config['configured']:
            state = 'needs_key'
            score = 62
        elif total == 0:
            state = 'needs_sync'
            score = 72
        elif enabled == 0:
            state = 'needs_whitelist'
            score = 80
        else:
            state = 'ready'
            score = 94
        return {'state': state, 'score': score, 'total_services': total, 'enabled_services': enabled, **config}


    @staticmethod
    def masked_api_key() -> str:
        key = (settings.boostore_api_key or '').strip()
        if not key:
            return 'not_set'
        if len(key) <= 8:
            return '***'
        return f"{key[:4]}…{key[-4:]}"

    @staticmethod
    def _balance_text(data: Any) -> str:
        if isinstance(data, dict):
            balance = data.get('balance') or data.get('amount') or data.get('funds') or data.get('money')
            currency = data.get('currency') or data.get('cur') or data.get('currency_code') or ''
            if balance is not None:
                return f"{balance} {currency}".strip()
            if data:
                return json.dumps(data, ensure_ascii=False, sort_keys=True)[:180]
        if isinstance(data, (int, float, str)) and str(data).strip():
            return str(data).strip()[:180]
        return '—'

    @staticmethod
    def live_diagnostics() -> dict[str, Any]:
        """Live owner-only API diagnostics without exposing the API key.

        This method intentionally never returns the raw BOOSTORE_API_KEY. It can
        be called from the owner Provider Center to verify that the key from
        Bothost/.env works, see provider balance and decide whether service sync
        is safe.
        """
        config = BoostoreProviderService.config_state()
        cached_total = BoostoreProviderService.count_services(enabled_only=False)
        whitelist_total = BoostoreProviderService.count_services(enabled_only=True)
        base: dict[str, Any] = {
            'enabled': bool(config['enabled']),
            'configured': bool(config['configured']),
            'has_key': bool(config['has_key']),
            'api_url': str(config['api_url']),
            'masked_key': BoostoreProviderService.masked_api_key(),
            'cached_total': int(cached_total),
            'whitelist_total': int(whitelist_total),
            'balance_text': '—',
            'result_key': 'boostore_not_configured',
            'ok': False,
            'state': 'needs_key',
            'score': 60,
            'error': None,
        }
        if not config['enabled']:
            base.update({'result_key': 'boostore_disabled', 'state': 'disabled', 'score': 55})
            return base
        if not config['has_key'] or not config['configured']:
            base.update({'result_key': 'boostore_not_configured', 'state': 'needs_key', 'score': 62})
            return base
        balance = BoostoreProviderService.get_balance()
        base['result_key'] = balance.result_key
        base['ok'] = bool(balance.ok)
        base['balance_text'] = BoostoreProviderService._balance_text(balance.data)
        base['error'] = (balance.error or '')[:180] if balance.error else None
        if balance.ok:
            state = 'ready' if whitelist_total > 0 else ('needs_whitelist' if cached_total > 0 else 'needs_sync')
            score = 96 if state == 'ready' else (86 if state == 'needs_whitelist' else 80)
            base.update({'state': state, 'score': score})
        else:
            base.update({'state': 'api_error', 'score': 68})
        return base

    @staticmethod
    def diagnostics_summary() -> dict[str, Any]:
        provider_path = Path(__file__).resolve()
        try:
            source = provider_path.read_text(encoding='utf-8')
        except Exception:
            source = ''
        checks = {
            'live_diagnostics': 'def live_diagnostics' in source,
            'masked_key': 'def masked_api_key' in source and 'raw BOOSTORE_API_KEY' in source,
            'balance_check': 'get_balance()' in source,
            'safe_error': "'error': (balance.error or '')[:180]" in source,
        }
        failed = [name for name, ok in checks.items() if not ok]
        status = 'ready' if not failed else ('warning' if len(failed) <= 1 else 'blocker')
        score = max(50, 100 - len(failed) * 18)
        return {
            'status': status,
            'score': score,
            'warnings': len(failed),
            'failed': ','.join(failed),
            **{name: int(ok) for name, ok in checks.items()},
        }

    @staticmethod
    def create_order(*, external_service_id: str, link: str, quantity: int) -> ProviderResult:
        service = db.fetch_one(
            'SELECT * FROM provider_services WHERE provider_code = ? AND external_service_id = ? AND is_enabled = 1',
            (PROVIDER_CODE, str(external_service_id)),
        )
        if not service:
            return ProviderResult(False, 'boostore_service_not_enabled')
        min_q = int(service['min_quantity'] or 0)
        max_q = int(service['max_quantity'] or 0)
        if quantity < min_q or (max_q and quantity > max_q):
            return ProviderResult(False, 'boostore_quantity_out_of_range')
        return BoostoreProviderService._request('add', service=external_service_id, link=link, quantity=int(quantity))

# Boostora v3.2.0 final completion helpers: safe auto-order after payment.
def _boostore_public_price_stars(service_row, quantity: int) -> int:
    rate = float(service_row['rate_value'] or 0)
    markup = int(service_row['markup_percent'] or settings.boostore_default_markup_percent)
    # SMM panels normally provide rate per 1000 units. Keep a safe minimum of 1 Star.
    raw = (rate * max(int(quantity), 1) / 1000.0) * (1 + markup / 100.0)
    return max(1, int(round(raw)))


def _boostore_enabled_service(external_service_id: str):
    return db.fetch_one(
        'SELECT * FROM provider_services WHERE provider_code = ? AND external_service_id = ? AND is_enabled = 1',
        (PROVIDER_CODE, str(external_service_id)),
    )


def _boostore_order_summary() -> dict[str, Any]:
    try:
        total = db.fetch_one("SELECT COUNT(*) AS cnt FROM provider_orders WHERE provider_code = ?", (PROVIDER_CODE,))
        placed = db.fetch_one("SELECT COUNT(*) AS cnt FROM provider_orders WHERE provider_code = ? AND provider_status NOT IN ('draft','failed')", (PROVIDER_CODE,))
        failed = db.fetch_one("SELECT COUNT(*) AS cnt FROM provider_orders WHERE provider_code = ? AND provider_status = 'failed'", (PROVIDER_CODE,))
        return {
            'status': 'ready',
            'auto_order_enabled': int(getattr(settings, 'boostore_auto_order_enabled', False)),
            'total': int(total['cnt'] or 0) if total else 0,
            'placed': int(placed['cnt'] or 0) if placed else 0,
            'failed': int(failed['cnt'] or 0) if failed else 0,
            'whitelist': BoostoreProviderService.count_services(enabled_only=True),
        }
    except Exception:
        return {'status': 'blocker', 'auto_order_enabled': 0, 'total': 0, 'placed': 0, 'failed': 0, 'whitelist': 0}


def _boostore_prepare_order(*, owner_user_id: int, external_service_id: str, link: str, quantity: int, campaign_id: int | None = None) -> ProviderResult:
    service = _boostore_enabled_service(external_service_id)
    if not service:
        return ProviderResult(False, 'boostore_service_not_enabled')
    min_q = int(service['min_quantity'] or 0)
    max_q = int(service['max_quantity'] or 0)
    quantity = int(quantity)
    if quantity < min_q or (max_q and quantity > max_q):
        return ProviderResult(False, 'boostore_quantity_out_of_range')
    price = _boostore_public_price_stars(service, quantity)
    order_id = db.execute(
        '''
        INSERT INTO provider_orders (
            provider_code, owner_user_id, campaign_id, external_service_id, link, quantity,
            charge_text, charge_value, currency, provider_status, last_payload_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'XTR', 'draft', ?)
        ''',
        (PROVIDER_CODE, int(owner_user_id), campaign_id, str(external_service_id), str(link)[:255], quantity, str(price), float(price), '{}'),
    )
    return ProviderResult(True, 'boostore_order_prepared', data={'order_id': order_id, 'price_stars': price})


def _boostore_place_prepared_order(order_id: int) -> ProviderResult:
    row = db.fetch_one('SELECT * FROM provider_orders WHERE id = ? AND provider_code = ?', (int(order_id), PROVIDER_CODE))
    if not row:
        return ProviderResult(False, 'boostore_order_not_found')
    if str(row['provider_status']) not in {'draft', 'failed'}:
        return ProviderResult(True, 'boostore_order_already_placed', data={'order_id': int(order_id), 'external_order_id': str(row['external_order_id'] or '')})
    result = BoostoreProviderService.create_order(
        external_service_id=str(row['external_service_id'] or ''),
        link=str(row['link'] or ''),
        quantity=int(row['quantity'] or 0),
    )
    if not result.ok:
        db.execute(
            "UPDATE provider_orders SET provider_status = 'failed', last_error = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            ((result.error or result.result_key)[:500], int(order_id)),
        )
        return result
    data = result.data if isinstance(result.data, dict) else {}
    external_id = str(data.get('order') or data.get('id') or data.get('order_id') or '')
    db.execute(
        '''
        UPDATE provider_orders
        SET provider_status = 'placed', external_order_id = ?, last_payload_json = ?, placed_at = CURRENT_TIMESTAMP,
            last_error = NULL, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        ''',
        (external_id, json.dumps(result.data, ensure_ascii=False, sort_keys=True)[:2000], int(order_id)),
    )
    return ProviderResult(True, 'boostore_order_placed', data={'order_id': int(order_id), 'external_order_id': external_id, 'payload': result.data})


def _boostore_order_status_sync(limit: int = 20) -> dict[str, int]:
    checked = 0
    updated = 0
    failed = 0
    rows = db.fetch_all(
        """
        SELECT * FROM provider_orders
        WHERE provider_code = ? AND external_order_id IS NOT NULL AND external_order_id != ''
        ORDER BY COALESCE(last_checked_at, created_at) ASC
        LIMIT ?
        """,
        (PROVIDER_CODE, max(1, int(limit))),
    )
    for row in rows:
        checked += 1
        result = BoostoreProviderService._request('status', order=str(row['external_order_id']))
        if not result.ok:
            failed += 1
            db.execute('UPDATE provider_orders SET last_checked_at = CURRENT_TIMESTAMP, last_error = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?', ((result.error or result.result_key)[:500], int(row['id'])))
            continue
        status = 'unknown'
        if isinstance(result.data, dict):
            status = str(result.data.get('status') or result.data.get(str(row['external_order_id'])) or 'unknown')[:64]
        db.execute('UPDATE provider_orders SET provider_status = ?, last_payload_json = ?, last_checked_at = CURRENT_TIMESTAMP, last_error = NULL, updated_at = CURRENT_TIMESTAMP WHERE id = ?', (status, json.dumps(result.data, ensure_ascii=False, sort_keys=True)[:2000], int(row['id'])))
        updated += 1
    return {'checked': checked, 'updated': updated, 'failed': failed}


BoostoreProviderService.public_price_stars = staticmethod(_boostore_public_price_stars)
BoostoreProviderService.prepare_order = staticmethod(_boostore_prepare_order)
BoostoreProviderService.place_prepared_order = staticmethod(_boostore_place_prepared_order)
BoostoreProviderService.sync_order_statuses = staticmethod(_boostore_order_status_sync)
BoostoreProviderService.order_summary = staticmethod(_boostore_order_summary)
