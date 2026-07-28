from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

from app import db
from app.config import settings

PROVIDER_CODE = 'boostore'
PUBLIC_PLATFORM = 'telegram'
CATALOG_PAGE_SIZE = 8

_PLATFORM_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ('telegram', ('telegram', 'телеграм', ' tg ', 't.me')),
    ('youtube', ('youtube', 'ютуб')),
    ('instagram', ('instagram', 'инстаграм')),
    ('tiktok', ('tiktok', 'tik tok', 'тикток')),
    ('vk', ('vkontakte', 'вконтакте', ' vk ', 'vk.com')),
    ('facebook', ('facebook', 'фейсбук')),
    ('avito', ('avito', 'авито')),
    ('2gis', ('2gis', '2гис', '2 gis')),
    ('rutube', ('rutube', 'рутуб')),
    ('discord', ('discord', 'дискорд')),
    ('twitch', ('twitch', 'твич')),
    ('twitter', ('twitter', ' x.com', 'твиттер')),
)

_CATEGORY_ORDER = (
    'subscribers', 'views', 'reactions', 'comments', 'groups', 'stories',
    'polls', 'shares', 'bots', 'boosts', 'other',
)
_CATEGORY_LABELS = {
    'ru': {
        'subscribers': 'Подписчики', 'views': 'Просмотры', 'reactions': 'Реакции и лайки',
        'comments': 'Комментарии', 'groups': 'Группы и чаты', 'stories': 'Истории',
        'polls': 'Опросы и голоса', 'shares': 'Репосты и пересылки', 'bots': 'Боты',
        'boosts': 'Бусты и Premium', 'other': 'Другие услуги',
    },
    'en': {
        'subscribers': 'Subscribers', 'views': 'Views', 'reactions': 'Reactions and likes',
        'comments': 'Comments', 'groups': 'Groups and chats', 'stories': 'Stories',
        'polls': 'Polls and votes', 'shares': 'Shares and forwards', 'bots': 'Bots',
        'boosts': 'Boosts and Premium', 'other': 'Other services',
    },
}
_SUBCATEGORY_ORDER = (
    'channels', 'groups', 'posts', 'videos', 'stories', 'custom', 'positive',
    'premium', 'refill', 'no_refill', 'general',
)
_SUBCATEGORY_LABELS = {
    'ru': {
        'channels': 'Каналы', 'groups': 'Группы и чаты', 'posts': 'Публикации',
        'videos': 'Видео', 'stories': 'Истории', 'custom': 'Свои варианты',
        'positive': 'Положительные', 'premium': 'Premium', 'refill': 'С гарантией',
        'no_refill': 'Без гарантии', 'general': 'Остальные',
    },
    'en': {
        'channels': 'Channels', 'groups': 'Groups and chats', 'posts': 'Posts',
        'videos': 'Video', 'stories': 'Stories', 'custom': 'Custom',
        'positive': 'Positive', 'premium': 'Premium', 'refill': 'With refill',
        'no_refill': 'Without refill', 'general': 'Other',
    },
}


def _row_text(row: Any, key: str) -> str:
    try:
        return str(row[key] or '')
    except Exception:
        if isinstance(row, dict):
            return str(row.get(key) or '')
        return ''


def _catalog_text(row: Any) -> str:
    return ' '.join((_row_text(row, 'category'), _row_text(row, 'name'), _row_text(row, 'service_type'))).lower()


def _detect_platform(row: Any) -> str:
    text = f' {_catalog_text(row)} '
    for platform, needles in _PLATFORM_PATTERNS:
        if any(needle in text for needle in needles):
            return platform
    return 'other'


def _detect_category(row: Any) -> str:
    text = _catalog_text(row)
    checks = (
        ('comments', ('коммент', 'comment', 'review', 'отзыв')),
        ('reactions', ('реакц', 'reaction', 'like', 'лайк', 'emoji')),
        ('stories', ('истори', 'story', 'stories')),
        ('polls', ('опрос', 'голос', 'poll', 'vote')),
        ('shares', ('репост', 'пересыл', 'share', 'forward', 'repost')),
        ('bots', ('бот', ' bot ', 'start bot')),
        ('boosts', ('boost', 'буст', 'premium', 'stars', 'звезд')),
        ('views', ('просмотр', 'view', 'impression')),
        ('groups', ('групп', 'чат', 'group', 'chat')),
        ('subscribers', ('подпис', 'subscriber', 'follower', 'member', 'участник')),
    )
    padded = f' {text} '
    for code, needles in checks:
        if any(needle in padded for needle in needles):
            return code
    return 'other'


def _detect_subcategory(row: Any, category: str) -> str:
    text = _catalog_text(row)
    if 'premium' in text or 'премиум' in text:
        return 'premium'
    if any(word in text for word in ('custom', 'свой текст', 'ваш текст', 'заказной', 'кастом')):
        return 'custom'
    if any(word in text for word in ('positive', 'положительн')):
        return 'positive'
    if any(word in text for word in ('story', 'stories', 'истори')):
        return 'stories'
    if any(word in text for word in ('video', 'видео', 'reels', 'shorts')):
        return 'videos'
    if any(word in text for word in ('group', 'chat', 'групп', 'чат')):
        return 'groups'
    if any(word in text for word in ('post', 'publication', 'пост', 'публикац')):
        return 'posts'
    if any(word in text for word in ('channel', 'канал')):
        return 'channels'
    try:
        refill = bool(int(row['refill_enabled'] or 0))
    except Exception:
        refill = False
    if category in {'subscribers', 'views'}:
        return 'refill' if refill else 'no_refill'
    return 'general'


def _category_label(code: str, language: str = 'ru') -> str:
    labels = _CATEGORY_LABELS.get(language, _CATEGORY_LABELS['ru'])
    return labels.get(code, labels['other'])


def _subcategory_label(code: str, language: str = 'ru') -> str:
    labels = _SUBCATEGORY_LABELS.get(language, _SUBCATEGORY_LABELS['ru'])
    return labels.get(code, labels['general'])


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


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return value != 0
    normalized = str(value).strip().lower()
    return normalized in {'1', 'true', 'yes', 'on', 'enabled', 'да'}


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
    def sync_services(limit: int | None = None) -> ProviderResult:
        """Synchronize the provider catalogue without silently truncating it.

        A full synchronization is applied in one SQLite transaction. Services that
        disappeared from the provider response are kept for order history but are
        disabled so users cannot purchase stale positions. A caller may pass a
        limit for diagnostics; partial syncs never disable unseen rows.
        """
        result = BoostoreProviderService._request('services')
        if not result.ok:
            return result
        data = result.data if isinstance(result.data, list) else []
        if not data:
            return ProviderResult(False, 'boostore_services_empty', data=result.data)

        if limit is None:
            rows = data
            full_sync = True
        else:
            safe_limit = max(1, int(limit))
            rows = data[:safe_limit]
            full_sync = safe_limit >= len(data)

        imported = 0
        skipped = 0

        def _sync(connection):
            nonlocal imported, skipped
            if full_sync:
                connection.execute(
                    'UPDATE provider_services SET last_synced_at = NULL WHERE provider_code = ?',
                    (PROVIDER_CODE,),
                )
            for item in rows:
                if not isinstance(item, dict):
                    skipped += 1
                    continue
                external_id = str(item.get('service') or '').strip()
                name = str(item.get('name') or '').strip()
                if not external_id or not name:
                    skipped += 1
                    continue
                connection.execute(
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
                        1 if _as_bool(item.get('refill')) else 0,
                        1 if _as_bool(item.get('cancel')) else 0,
                        int(settings.boostore_default_markup_percent),
                        json.dumps(item, ensure_ascii=False, sort_keys=True),
                    ),
                )
                imported += 1

            stale_disabled = 0
            if full_sync:
                cursor = connection.execute(
                    '''
                    UPDATE provider_services
                    SET is_enabled = 0, updated_at = CURRENT_TIMESTAMP
                    WHERE provider_code = ? AND last_synced_at IS NULL AND is_enabled != 0
                    ''',
                    (PROVIDER_CODE,),
                )
                stale_disabled = max(0, int(cursor.rowcount or 0))
            return stale_disabled

        stale_disabled = db.run_in_transaction(_sync)
        return ProviderResult(
            True,
            'boostore_sync_success',
            data={
                'count': imported,
                'received': len(data),
                'skipped': skipped,
                'stale_disabled': stale_disabled,
                'full_sync': full_sync,
            },
        )

    @staticmethod
    def normalize_telegram_link(raw_value: str) -> str | None:
        """Return a canonical Telegram target link or reject another platform."""
        value = str(raw_value or '').strip()
        if not value:
            return None
        if value.startswith('@'):
            username = value[1:].strip()
            if re.fullmatch(r'[A-Za-z0-9_]{5,32}', username):
                return f'https://t.me/{username}'
            return None
        lowered = value.lower()
        if lowered.startswith('t.me/') or lowered.startswith('telegram.me/'):
            value = f'https://{value}'
        try:
            parsed = urlparse(value)
        except Exception:
            return None
        hostname = (parsed.hostname or '').lower().rstrip('.')
        if parsed.scheme.lower() not in {'http', 'https'}:
            return None
        if hostname not in {'t.me', 'www.t.me', 'telegram.me', 'www.telegram.me'}:
            return None
        if not (parsed.path or '').strip('/'):
            return None
        return parsed._replace(scheme='https').geturl()

    @staticmethod
    def get_balance() -> ProviderResult:
        return BoostoreProviderService._request('balance')

    @staticmethod
    def list_services(
        *,
        enabled_only: bool = False,
        current_only: bool = False,
        limit: int | None = 20,
        offset: int = 0,
    ) -> list[Any]:
        where = 'provider_code = ?'
        params: list[Any] = [PROVIDER_CODE]
        if enabled_only:
            where += ' AND is_enabled = 1'
        if current_only:
            where += ' AND last_synced_at IS NOT NULL'
        query = f'''
            SELECT * FROM provider_services
            WHERE {where}
            ORDER BY is_enabled DESC, category COLLATE NOCASE, rate_value ASC, name COLLATE NOCASE
        '''
        if limit is None:
            return db.fetch_all(query, tuple(params))
        query += ' LIMIT ? OFFSET ?'
        return db.fetch_all(
            query,
            tuple(params + [max(1, int(limit)), max(0, int(offset))]),
        )

    @staticmethod
    def count_services(*, enabled_only: bool = False, current_only: bool = False) -> int:
        where = "provider_code = 'boostore'"
        if enabled_only:
            where += ' AND is_enabled = 1'
        if current_only:
            where += ' AND last_synced_at IS NOT NULL'
        row = db.fetch_one(f'SELECT COUNT(*) AS cnt FROM provider_services WHERE {where}')
        return int(row['cnt'] or 0) if row else 0

    @staticmethod
    def toggle_service(external_service_id: str) -> ProviderResult:
        row = db.fetch_one(
            'SELECT * FROM provider_services WHERE provider_code = ? AND external_service_id = ? AND last_synced_at IS NOT NULL',
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
    def service_taxonomy(row: Any, *, language: str = 'ru') -> dict[str, str]:
        platform = _detect_platform(row)
        category = _detect_category(row)
        subcategory = _detect_subcategory(row, category)
        return {
            'platform': platform,
            'category': category,
            'subcategory': subcategory,
            'category_label': _category_label(category, language),
            'subcategory_label': _subcategory_label(subcategory, language),
        }

    @staticmethod
    def list_catalog_services(
        *,
        enabled_only: bool = True,
        platform: str = PUBLIC_PLATFORM,
        category: str | None = None,
        subcategory: str | None = None,
        limit: int = CATALOG_PAGE_SIZE,
        offset: int = 0,
    ) -> list[Any]:
        rows = BoostoreProviderService.list_services(enabled_only=enabled_only, current_only=True, limit=None, offset=0)
        filtered: list[Any] = []
        for row in rows:
            taxonomy = BoostoreProviderService.service_taxonomy(row)
            if platform and taxonomy['platform'] != platform:
                continue
            if category and taxonomy['category'] != category:
                continue
            if subcategory and taxonomy['subcategory'] != subcategory:
                continue
            filtered.append(row)
        start = max(0, int(offset))
        page_size = max(1, int(limit))
        return filtered[start:start + page_size]

    @staticmethod
    def count_catalog_services(
        *,
        enabled_only: bool = True,
        platform: str = PUBLIC_PLATFORM,
        category: str | None = None,
        subcategory: str | None = None,
    ) -> int:
        rows = BoostoreProviderService.list_services(enabled_only=enabled_only, current_only=True, limit=None, offset=0)
        count = 0
        for row in rows:
            taxonomy = BoostoreProviderService.service_taxonomy(row)
            if platform and taxonomy['platform'] != platform:
                continue
            if category and taxonomy['category'] != category:
                continue
            if subcategory and taxonomy['subcategory'] != subcategory:
                continue
            count += 1
        return count

    @staticmethod
    def catalog_categories(*, enabled_only: bool, platform: str = PUBLIC_PLATFORM, language: str = 'ru') -> list[dict[str, Any]]:
        rows = BoostoreProviderService.list_services(enabled_only=False, current_only=True, limit=None, offset=0)
        counters: dict[str, dict[str, int]] = {}
        for row in rows:
            taxonomy = BoostoreProviderService.service_taxonomy(row, language=language)
            if taxonomy['platform'] != platform:
                continue
            code = taxonomy['category']
            bucket = counters.setdefault(code, {'total': 0, 'enabled': 0})
            bucket['total'] += 1
            if int(row['is_enabled'] or 0):
                bucket['enabled'] += 1
        result = []
        for code in _CATEGORY_ORDER:
            bucket = counters.get(code)
            if not bucket:
                continue
            if enabled_only and bucket['enabled'] <= 0:
                continue
            result.append({
                'code': code,
                'label': _category_label(code, language),
                'total': int(bucket['total']),
                'enabled': int(bucket['enabled']),
            })
        return result

    @staticmethod
    def catalog_subcategories(
        category: str, *, enabled_only: bool, platform: str = PUBLIC_PLATFORM, language: str = 'ru'
    ) -> list[dict[str, Any]]:
        rows = BoostoreProviderService.list_services(enabled_only=False, current_only=True, limit=None, offset=0)
        counters: dict[str, dict[str, int]] = {}
        for row in rows:
            taxonomy = BoostoreProviderService.service_taxonomy(row, language=language)
            if taxonomy['platform'] != platform or taxonomy['category'] != category:
                continue
            code = taxonomy['subcategory']
            bucket = counters.setdefault(code, {'total': 0, 'enabled': 0})
            bucket['total'] += 1
            if int(row['is_enabled'] or 0):
                bucket['enabled'] += 1
        result = []
        for code in _SUBCATEGORY_ORDER:
            bucket = counters.get(code)
            if not bucket:
                continue
            if enabled_only and bucket['enabled'] <= 0:
                continue
            result.append({
                'code': code,
                'label': _subcategory_label(code, language),
                'total': int(bucket['total']),
                'enabled': int(bucket['enabled']),
            })
        return result

    @staticmethod
    def get_public_service(external_service_id: str) -> Any | None:
        row = db.fetch_one(
            'SELECT * FROM provider_services WHERE provider_code = ? AND external_service_id = ? AND is_enabled = 1 AND last_synced_at IS NOT NULL',
            (PROVIDER_CODE, str(external_service_id)),
        )
        if not row:
            return None
        taxonomy = BoostoreProviderService.service_taxonomy(row)
        return row if taxonomy['platform'] == PUBLIC_PLATFORM else None

    @staticmethod
    def set_catalog_enabled(
        *,
        enabled: bool,
        platform: str = PUBLIC_PLATFORM,
        category: str | None = None,
        subcategory: str | None = None,
    ) -> ProviderResult:
        rows = BoostoreProviderService.list_services(enabled_only=False, current_only=True, limit=None, offset=0)
        selected: list[tuple[int, str, str]] = []
        for row in rows:
            taxonomy = BoostoreProviderService.service_taxonomy(row)
            if taxonomy['platform'] != platform:
                continue
            if category and taxonomy['category'] != category:
                continue
            if subcategory and taxonomy['subcategory'] != subcategory:
                continue
            selected.append((1 if enabled else 0, PROVIDER_CODE, str(row['external_service_id'])))
        if not selected:
            return ProviderResult(False, 'boostore_catalog_folder_empty', data={'count': 0})
        db.execute_many(
            '''
            UPDATE provider_services
            SET is_enabled = ?, updated_at = CURRENT_TIMESTAMP
            WHERE provider_code = ? AND external_service_id = ?
            ''',
            selected,
        )
        return ProviderResult(
            True,
            'boostore_catalog_added' if enabled else 'boostore_catalog_removed',
            data={'count': len(selected)},
        )

    @staticmethod
    def marketplace_summary(limit: int = CATALOG_PAGE_SIZE) -> dict[str, Any]:
        total = BoostoreProviderService.count_catalog_services(enabled_only=False)
        enabled = BoostoreProviderService.count_catalog_services(enabled_only=True)
        services = BoostoreProviderService.list_catalog_services(enabled_only=True, limit=limit)
        categories = BoostoreProviderService.catalog_categories(enabled_only=True)
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
        total = BoostoreProviderService.count_services(enabled_only=False, current_only=True)
        enabled = BoostoreProviderService.count_services(enabled_only=True, current_only=True)
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
        cached_total = BoostoreProviderService.count_services(enabled_only=False, current_only=True)
        whitelist_total = BoostoreProviderService.count_services(enabled_only=True, current_only=True)
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
        service = BoostoreProviderService.get_public_service(external_service_id)
        if not service:
            return ProviderResult(False, 'boostore_service_not_enabled')
        normalized_link = BoostoreProviderService.normalize_telegram_link(link)
        if not normalized_link:
            return ProviderResult(False, 'boostore_order_link_invalid')
        min_q = int(service['min_quantity'] or 0)
        max_q = int(service['max_quantity'] or 0)
        if quantity < min_q or (max_q and quantity > max_q):
            return ProviderResult(False, 'boostore_quantity_out_of_range')
        return BoostoreProviderService._request('add', service=external_service_id, link=normalized_link, quantity=int(quantity))

# Boostora v3.2.0 final completion helpers: safe auto-order after payment.
def _boostore_public_price_stars(service_row, quantity: int) -> int:
    rate = float(service_row['rate_value'] or 0)
    markup = int(service_row['markup_percent'] or settings.boostore_default_markup_percent)
    # SMM panels normally provide rate per 1000 units. Keep a safe minimum of 1 Star.
    raw = (rate * max(int(quantity), 1) / 1000.0) * (1 + markup / 100.0)
    return max(1, int(round(raw)))


def _boostore_enabled_service(external_service_id: str):
    return BoostoreProviderService.get_public_service(external_service_id)


def _boostore_order_summary() -> dict[str, Any]:
    try:
        total = db.fetch_one("SELECT COUNT(*) AS cnt FROM provider_orders WHERE provider_code = ?", (PROVIDER_CODE,))
        placed = db.fetch_one("SELECT COUNT(*) AS cnt FROM provider_orders WHERE provider_code = ? AND (placed_at IS NOT NULL OR provider_status IN ('placed','pending','processing','completed','partial','canceled'))", (PROVIDER_CODE,))
        failed = db.fetch_one("SELECT COUNT(*) AS cnt FROM provider_orders WHERE provider_code = ? AND provider_status = 'failed'", (PROVIDER_CODE,))
        return {
            'status': 'ready',
            'auto_order_enabled': int(getattr(settings, 'boostore_auto_order_enabled', False)),
            'total': int(total['cnt'] or 0) if total else 0,
            'placed': int(placed['cnt'] or 0) if placed else 0,
            'failed': int(failed['cnt'] or 0) if failed else 0,
            'whitelist': BoostoreProviderService.count_services(enabled_only=True, current_only=True),
        }
    except Exception:
        return {'status': 'blocker', 'auto_order_enabled': 0, 'total': 0, 'placed': 0, 'failed': 0, 'whitelist': 0}


def _boostore_prepare_order(*, owner_user_id: int, external_service_id: str, link: str, quantity: int, campaign_id: int | None = None) -> ProviderResult:
    service = _boostore_enabled_service(external_service_id)
    if not service:
        return ProviderResult(False, 'boostore_service_not_enabled')
    normalized_link = BoostoreProviderService.normalize_telegram_link(link)
    if not normalized_link:
        return ProviderResult(False, 'boostore_order_link_invalid')
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
        (PROVIDER_CODE, int(owner_user_id), campaign_id, str(external_service_id), normalized_link[:255], quantity, str(price), float(price), '{}'),
    )
    return ProviderResult(True, 'boostore_order_prepared', data={'order_id': order_id, 'price_stars': price})


def _boostore_place_prepared_order(order_id: int) -> ProviderResult:
    row = db.fetch_one('SELECT * FROM provider_orders WHERE id = ? AND provider_code = ?', (int(order_id), PROVIDER_CODE))
    if not row:
        return ProviderResult(False, 'boostore_order_not_found')
    status = str(row['provider_status'] or '')
    if status in {'placed', 'pending', 'processing', 'completed', 'partial', 'canceled'} or str(row['external_order_id'] or ''):
        return ProviderResult(True, 'boostore_order_already_placed', data={'order_id': int(order_id), 'external_order_id': str(row['external_order_id'] or '')})
    # Provider money may be spent only after Telegram confirmed the user's payment.
    if status not in {'paid', 'paid_pending', 'failed'} or not str(row['paid_at'] or ''):
        return ProviderResult(False, 'boostore_order_payment_required', data={'order_id': int(order_id), 'status': status})
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



def _boostore_mark_order_paid(
    order_id: int,
    owner_user_id: int,
    *,
    telegram_payment_charge_id: str = '',
    provider_payment_charge_id: str = '',
) -> ProviderResult:
    row = db.fetch_one(
        'SELECT * FROM provider_orders WHERE id = ? AND provider_code = ? AND owner_user_id = ?',
        (int(order_id), PROVIDER_CODE, int(owner_user_id)),
    )
    if not row:
        return ProviderResult(False, 'boostore_order_not_found')
    current = str(row['provider_status'] or '')
    if str(row['paid_at'] or '') or current not in {'draft', 'invoice_failed', 'failed'}:
        return ProviderResult(True, 'boostore_order_already_paid', data={'order_id': int(order_id), 'status': current})
    next_status = 'paid' if bool(getattr(settings, 'boostore_auto_order_enabled', False)) else 'paid_pending'
    db.execute(
        '''
        UPDATE provider_orders
        SET provider_status = ?, paid_at = COALESCE(paid_at, CURRENT_TIMESTAMP),
            telegram_payment_charge_id = ?, provider_payment_charge_id = ?,
            last_error = NULL, updated_at = CURRENT_TIMESTAMP
        WHERE id = ? AND owner_user_id = ?
        ''',
        (
            next_status,
            str(telegram_payment_charge_id or '')[:255],
            str(provider_payment_charge_id or '')[:255],
            int(order_id),
            int(owner_user_id),
        ),
    )
    return ProviderResult(True, 'boostore_order_paid', data={'order_id': int(order_id), 'status': next_status})

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
BoostoreProviderService.mark_order_paid = staticmethod(_boostore_mark_order_paid)
BoostoreProviderService.sync_order_statuses = staticmethod(_boostore_order_status_sync)
BoostoreProviderService.order_summary = staticmethod(_boostore_order_summary)
