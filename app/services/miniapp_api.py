from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any
import json
import logging
import threading
import time

import requests

from app import db
from app.config import settings
from app.services.admin import AdminService
from app.services.boostore_provider import BoostoreProviderService
from app.services.campaigns import CampaignService
from app.services.client_campaigns import ClientCampaignService
from app.services.community_rules import CommunityRulesService
from app.services.engagement_modes import EngagementModeService
from app.services.economy import TASK_CATALOG, calculate_campaign_pricing
from app.services.final_audit import FinalAuditService
from app.services.legal_docs import LegalDocsService
from app.services.owner_analytics import OwnerAnalyticsService
from app.services.payments import (
    BASE_SPARKS_PER_STAR,
    SPARKS_PACKS,
    calculate_custom_stars_for_sparks,
    make_payload,
)
from app.services.performer import PerformerService
from app.services.referrals import ReferralService
from app.services.release_readiness import ReleaseReadinessService
from app.services.subscriptions import SubscriptionService
from app.services.transactions import TransactionService
from app.services.users import UserService
from app.services.wallets import WalletService


LOGGER = logging.getLogger(__name__)
TELEGRAM_API_TIMEOUT = 20
SUBSCRIPTION_CACHE_TTL_SECONDS = 300
_SUBSCRIPTION_CACHE: dict[int, tuple[float, bool, bool]] = {}
_SUBSCRIPTION_CACHE_LOCK = threading.Lock()


@dataclass(frozen=True)
class ApiResult:
    status: int
    payload: dict[str, Any]


class TelegramBotApiProxy:
    """Small Telegram Bot API proxy used by Mini App server-side checks.

    It intentionally exposes only the methods required by the existing campaign,
    subscription and task verification services. The bot token never leaves the
    server.
    """

    def _call(self, method: str, **payload: Any) -> Any:
        url = f"https://api.telegram.org/bot{settings.bot_token}/{method}"
        response = requests.post(url, json=payload, timeout=TELEGRAM_API_TIMEOUT)
        response.raise_for_status()
        data = response.json()
        if not data.get('ok'):
            raise RuntimeError(str(data.get('description') or method))
        return data.get('result')

    def get_me(self) -> SimpleNamespace:
        data = self._call('getMe') or {}
        return SimpleNamespace(**data)

    def get_chat_member(self, chat_id: str | int, user_id: int) -> SimpleNamespace:
        data = self._call('getChatMember', chat_id=chat_id, user_id=int(user_id)) or {}
        return SimpleNamespace(**data)

    def get_chat(self, chat_id: str | int) -> SimpleNamespace:
        data = self._call('getChat', chat_id=chat_id) or {}
        return SimpleNamespace(**data)


BOT_PROXY = TelegramBotApiProxy()


def _row(row: Any, fields: tuple[str, ...] | None = None) -> dict[str, Any]:
    if row is None:
        return {}
    keys = list(row.keys()) if hasattr(row, 'keys') else []
    selected = fields or tuple(keys)
    result: dict[str, Any] = {}
    for field in selected:
        if field not in keys:
            continue
        value = row[field]
        if isinstance(value, (str, int, float, bool)) or value is None:
            result[field] = value
        else:
            result[field] = str(value)
    return result


def _rows(rows: list[Any], fields: tuple[str, ...] | None = None) -> list[dict[str, Any]]:
    return [_row(item, fields) for item in rows]


def ensure_web_user(user: dict[str, Any]) -> int:
    user_id = int(user.get('id') or 0)
    if user_id <= 0:
        raise ValueError('invalid_user_id')
    tg_user = SimpleNamespace(
        id=user_id,
        username=user.get('username'),
        first_name=user.get('first_name'),
        last_name=user.get('last_name'),
    )
    UserService.ensure_user(tg_user)
    return user_id


def _accepted_state(user_id: int) -> dict[str, bool]:
    return {
        'rules': CommunityRulesService.is_accepted(user_id),
        'legal': LegalDocsService.is_accepted(user_id),
    }


def _required_chats_payload() -> list[dict[str, str]]:
    return [
        {
            'name': SubscriptionService.display_name(str(item['chat_ref'])),
            'url': SubscriptionService.effective_join_link(str(item['chat_ref']), str(item['join_link'] or '')),
        }
        for item in SubscriptionService.list_required_chats()
    ]


def _subscription_state(user_id: int, *, force: bool = False) -> tuple[bool, bool]:
    now = time.monotonic()
    if not force:
        with _SUBSCRIPTION_CACHE_LOCK:
            cached = _SUBSCRIPTION_CACHE.get(int(user_id))
        if cached and now - cached[0] <= SUBSCRIPTION_CACHE_TTL_SECONDS:
            return cached[1], cached[2]
    result = SubscriptionService.get_subscription_check_result(BOT_PROXY, int(user_id))
    state = (bool(result.is_subscribed), bool(result.is_unknown))
    with _SUBSCRIPTION_CACHE_LOCK:
        _SUBSCRIPTION_CACHE[int(user_id)] = (now, state[0], state[1])
    return state


def _gate(user_id: int, *, role: str | None = None, docs: bool = True, subscription: bool = True) -> ApiResult | None:
    if not UserService.can_access_bot(user_id):
        return ApiResult(403, {'ok': False, 'error': 'blocked'})
    if role and UserService.get_role(user_id) != role:
        return ApiResult(403, {'ok': False, 'error': 'role_required', 'role': role})
    if docs:
        accepted = _accepted_state(user_id)
        if not accepted['rules']:
            return ApiResult(409, {'ok': False, 'error': 'rules_required'})
        if not accepted['legal']:
            return ApiResult(409, {'ok': False, 'error': 'legal_required'})
    if subscription and not UserService.is_admin(user_id):
        try:
            subscribed, unknown = _subscription_state(user_id)
            if not subscribed:
                return ApiResult(409, {
                    'ok': False,
                    'error': 'subscription_required',
                    'unknown': unknown,
                    'required_chats': _required_chats_payload(),
                })
        except Exception:
            LOGGER.exception('Mini App subscription check failed for user_id=%s', user_id)
            return ApiResult(503, {'ok': False, 'error': 'subscription_check_unavailable'})
    return None


def _telegram_invoice_link(*, title: str, description: str, payload: str, stars: int) -> str:
    amount = max(1, int(stars))
    body = {
        'title': str(title)[:32],
        'description': str(description)[:255],
        'payload': str(payload)[:128],
        'currency': 'XTR',
        'prices': [{'label': str(title)[:32], 'amount': amount}],
    }
    response = requests.post(
        f"https://api.telegram.org/bot{settings.bot_token}/createInvoiceLink",
        json=body,
        timeout=TELEGRAM_API_TIMEOUT,
    )
    response.raise_for_status()
    data = response.json()
    if not data.get('ok') or not data.get('result'):
        raise RuntimeError(str(data.get('description') or 'invoice_link_failed'))
    return str(data['result'])


def _task_type_items() -> list[dict[str, Any]]:
    return [
        {
            'code': code,
            'title': str(meta.get('title') or code),
            'floor': int(meta.get('client_floor_price') or 0),
            'reward': int(meta.get('performer_reward') or 0),
        }
        for code, meta in TASK_CATALOG.items()
    ]


def _documents(user_id: int) -> dict[str, Any]:
    rules = [
        {
            'code': section.code,
            'title': UserService.t(user_id, section.title_key),
            'body': UserService.t(user_id, section.body_key),
        }
        for section in CommunityRulesService.sections()
    ]
    legal = [
        {
            'title': UserService.t(user_id, section.title_key),
            'body': UserService.t(user_id, section.body_key),
        }
        for section in LegalDocsService.sections()
    ]
    accepted = _accepted_state(user_id)
    return {
        'rules': {'accepted': accepted['rules'], 'version': CommunityRulesService.CURRENT_VERSION, 'sections': rules},
        'legal': {'accepted': accepted['legal'], 'version': LegalDocsService.CURRENT_VERSION, 'sections': legal},
    }


def _catalog_service(row: Any, *, include_internal: bool = False) -> dict[str, Any]:
    taxonomy = BoostoreProviderService.service_taxonomy(row, language='ru')
    quantity_for_price = max(int(row['min_quantity'] or 1), 1)
    payload = {
        'id': str(row['external_service_id']),
        'name': str(row['name'] or ''),
        'category': taxonomy['category'],
        'category_label': taxonomy['category_label'],
        'subcategory': taxonomy['subcategory'],
        'subcategory_label': taxonomy['subcategory_label'],
        'min': int(row['min_quantity'] or 0),
        'max': int(row['max_quantity'] or 0),
        'refill': bool(row['refill_enabled']),
        'cancel': bool(row['cancel_enabled']),
        'enabled': bool(row['is_enabled']),
        'example_price_stars': int(BoostoreProviderService.public_price_stars(row, quantity_for_price)),
    }
    if include_internal:
        payload['rate'] = float(row['rate_value'] or 0)
        payload['markup_percent'] = int(row['markup_percent'] or 0)
        payload['platform'] = taxonomy['platform']
    return payload


def _provider_orders(user_id: int, limit: int = 50) -> list[dict[str, Any]]:
    rows = db.fetch_all(
        '''
        SELECT o.*, s.name AS service_name
        FROM provider_orders o
        LEFT JOIN provider_services s
          ON s.provider_code = o.provider_code AND s.external_service_id = o.external_service_id
        WHERE o.owner_user_id = ?
        ORDER BY o.created_at DESC, o.id DESC
        LIMIT ?
        ''',
        (int(user_id), max(1, min(int(limit), 100))),
    )
    return _rows(rows, (
        'id', 'external_order_id', 'external_service_id', 'service_name', 'link', 'quantity',
        'charge_value', 'currency', 'provider_status', 'created_at', 'updated_at', 'placed_at',
        'paid_at', 'last_error',
    ))


def _all_provider_orders(limit: int = 100) -> list[dict[str, Any]]:
    rows = db.fetch_all(
        '''
        SELECT o.*, s.name AS service_name, u.username, u.first_name, u.last_name
        FROM provider_orders o
        LEFT JOIN provider_services s
          ON s.provider_code = o.provider_code AND s.external_service_id = o.external_service_id
        LEFT JOIN users u ON u.user_id = o.owner_user_id
        ORDER BY o.created_at DESC, o.id DESC
        LIMIT ?
        ''',
        (max(1, min(int(limit), 250)),),
    )
    return _rows(rows, (
        'id', 'owner_user_id', 'username', 'first_name', 'last_name', 'external_order_id',
        'external_service_id', 'service_name', 'link', 'quantity', 'charge_value', 'currency',
        'provider_status', 'created_at', 'updated_at', 'placed_at', 'paid_at', 'last_error',
    ))


def _wallet_payload(user_id: int) -> dict[str, Any]:
    summary = WalletService.get_summary(user_id)
    history = TransactionService.get_history(user_id, limit=50)
    packs = [
        {
            'code': pack.code,
            'stars': int(pack.stars),
            'sparks': int(pack.sparks),
            'title': pack.title,
            'description': pack.description,
        }
        for pack in SPARKS_PACKS.values()
    ]
    return {
        'summary': summary,
        'transactions': _rows(history, (
            'id', 'amount', 'currency_code', 'direction', 'entry_type', 'status', 'created_at',
            'related_campaign_id', 'related_submission_id',
        )),
        'packs': packs,
        'base_sparks_per_star': BASE_SPARKS_PER_STAR,
    }


def _campaigns_payload(user_id: int) -> dict[str, Any]:
    campaigns = CampaignService.get_campaigns_for_owner(user_id, limit=50)
    return {
        'stats': CampaignService.get_owner_stats(user_id),
        'campaigns': _rows(campaigns, (
            'id', 'title', 'task_type', 'target_url', 'reward_amount', 'unit_price',
            'total_quantity', 'completed_quantity', 'rejected_quantity', 'budget_total',
            'budget_reserved', 'budget_spent', 'status', 'is_funded', 'created_at', 'updated_at',
        )),
        'task_types': _task_type_items(),
    }


def _tasks_payload(user_id: int) -> dict[str, Any]:
    available = PerformerService.list_available_tasks(user_id, limit=50)
    submissions = PerformerService.list_user_submissions(user_id, limit=50)
    return {
        'available': _rows(available, (
            'id', 'title', 'task_type', 'target_url', 'reward_amount', 'total_quantity',
            'completed_quantity', 'status', 'updated_at',
        )),
        'submissions': _rows(submissions, (
            'id', 'campaign_id', 'campaign_title', 'campaign_task_type', 'status', 'target_url',
            'proof_text', 'reward_amount', 'reject_reason', 'taken_at', 'submitted_at', 'updated_at',
        )),
        'active_limit': PerformerService.get_active_task_limit(user_id),
        'active_count': PerformerService.get_active_submission_count(user_id),
    }


def _profile_payload(user_id: int) -> dict[str, Any]:
    user = UserService.get_user(user_id)
    referral = ReferralService.get_summary(user_id)
    engagement = EngagementModeService.mode_summary(user_id)
    obligations = EngagementModeService.obligation_dashboard(user_id)
    obligation_items = EngagementModeService.obligation_items(user_id, limit=20)
    return {
        'user': _row(user, ('user_id', 'username', 'first_name', 'last_name', 'language_code', 'role', 'status', 'created_at')),
        'documents': _documents(user_id),
        'engagement': engagement,
        'obligations': obligations,
        'obligation_items': obligation_items,
        'referrals': {
            'invited_count': int(referral.get('invited_count') or 0),
            'total_earned': int(referral.get('total_earned') or 0),
            'rate_percent': float(referral.get('current_rate_percent') or 0),
            'link': str(referral.get('link') or ''),
            'rows': _rows(list(referral.get('rows') or []), ('referred_user_id', 'username', 'first_name', 'last_name', 'total_earned', 'joined_at')),
        },
        'languages': [
            {'code': 'ru', 'label': 'Русский'},
            {'code': 'en', 'label': 'English'},
            {'code': 'de', 'label': 'Deutsch'},
            {'code': 'es', 'label': 'Español'},
            {'code': 'pt', 'label': 'Português'},
            {'code': 'tr', 'label': 'Türkçe'},
        ],
    }


def _admin_payload(user_id: int) -> dict[str, Any]:
    gate = _gate(user_id, docs=False, subscription=False)
    if gate:
        return gate.payload
    if not UserService.is_admin(user_id):
        return {'ok': False, 'error': 'access_denied'}
    queue = AdminService.list_review_queue(limit=30)
    return {
        'ok': True,
        'stats': AdminService.get_dashboard_stats(),
        'queue': _rows(queue, (
            'id', 'campaign_id', 'performer_user_id', 'status', 'proof_text', 'reward_amount',
            'risk_score', 'taken_at', 'submitted_at', 'campaign_title', 'task_type', 'target_url',
        )),
    }


def _owner_payload(user_id: int) -> dict[str, Any]:
    if not UserService.is_owner(user_id):
        return {'ok': False, 'error': 'access_denied'}
    return {
        'ok': True,
        'commerce': OwnerAnalyticsService.commerce_summary(),
        'top_clients': OwnerAnalyticsService.top_clients(limit=10),
        'top_performers': OwnerAnalyticsService.top_performers(limit=10),
        'provider': {
            'diagnostics': BoostoreProviderService.live_diagnostics(),
            'order_summary': BoostoreProviderService.order_summary(),
            'categories': BoostoreProviderService.catalog_categories(enabled_only=False, language='ru'),
        },
        'release': {
            'audit': FinalAuditService.completion_summary(),
            'readiness': ReleaseReadinessService.readiness_summary(),
        },
    }


def _result(ok: bool, key: str, **extra: Any) -> ApiResult:
    status = 200 if ok else 400
    return ApiResult(status, {'ok': ok, 'result': key, **extra})


class MiniAppApiService:
    @staticmethod
    def bootstrap(user: dict[str, Any]) -> dict[str, Any]:
        user_id = ensure_web_user(user)
        return {
            'documents': _accepted_state(user_id),
            'required_chats': [
                {
                    'name': SubscriptionService.display_name(str(row['chat_ref'])),
                    'url': SubscriptionService.effective_join_link(str(row['chat_ref']), str(row['join_link'] or '')),
                }
                for row in SubscriptionService.list_required_chats()
            ],
            'task_types': _task_type_items(),
        }

    @staticmethod
    def dispatch(user: dict[str, Any], operation: str, payload: dict[str, Any]) -> ApiResult:
        user_id = ensure_web_user(user)
        op = str(operation or '').strip().lower()

        if op == 'documents.get':
            return ApiResult(200, {'ok': True, **_documents(user_id)})
        if op == 'documents.accept':
            if not UserService.can_access_bot(user_id):
                return ApiResult(403, {'ok': False, 'error': 'blocked'})
            kind = str(payload.get('kind') or '')
            if kind in {'rules', 'all'}:
                CommunityRulesService.accept(user_id, source='miniapp')
            if kind in {'legal', 'all'}:
                LegalDocsService.accept(user_id, source='miniapp')
            if kind not in {'rules', 'legal', 'all'}:
                return ApiResult(400, {'ok': False, 'error': 'invalid_document_kind'})
            return ApiResult(200, {'ok': True, **_documents(user_id)})

        if op == 'profile.get':
            basic_gate = _gate(user_id, docs=False, subscription=False)
            if basic_gate:
                return basic_gate
            return ApiResult(200, {'ok': True, **_profile_payload(user_id)})
        if op == 'profile.update':
            basic_gate = _gate(user_id, docs=False, subscription=False)
            if basic_gate:
                return basic_gate
            role = payload.get('role')
            language = payload.get('language')
            try:
                if role is not None:
                    UserService.set_role(user_id, str(role))
                if language is not None:
                    UserService.set_language(user_id, str(language))
            except ValueError as exc:
                return ApiResult(400, {'ok': False, 'error': str(exc)})
            return ApiResult(200, {'ok': True, **_profile_payload(user_id)})

        if op == 'subscription.check':
            try:
                subscribed, unknown = _subscription_state(user_id, force=True)
            except Exception:
                LOGGER.exception('Mini App subscription refresh failed for user_id=%s', user_id)
                return ApiResult(503, {'ok': False, 'error': 'subscription_check_unavailable'})
            return ApiResult(200, {'ok': True, 'subscribed': subscribed, 'unknown': unknown})

        gate = _gate(user_id)
        if gate:
            return gate

        if op == 'dashboard.get':
            return ApiResult(200, {'ok': True})

        if op == 'wallet.get':
            return ApiResult(200, {'ok': True, **_wallet_payload(user_id)})
        if op == 'wallet.invoice':
            if not settings.enable_xtr_payments:
                return ApiResult(503, {'ok': False, 'error': 'payments_disabled'})
            kind = str(payload.get('kind') or 'pack')
            try:
                if kind == 'pack':
                    code = str(payload.get('code') or '')
                    pack = SPARKS_PACKS.get(code)
                    if not pack:
                        return ApiResult(400, {'ok': False, 'error': 'pack_not_found'})
                    invoice_payload = make_payload('wasparks', code, user_id)
                    title = pack.title
                    description = pack.description
                    stars = int(pack.stars)
                elif kind == 'custom':
                    sparks = int(payload.get('sparks') or 0)
                    if sparks < BASE_SPARKS_PER_STAR or sparks > 100000:
                        return ApiResult(400, {'ok': False, 'error': 'invalid_amount'})
                    stars = calculate_custom_stars_for_sparks(sparks)
                    invoice_payload = make_payload('wasparks_custom', str(sparks), user_id)
                    title = f'{sparks} Искр'
                    description = f'Пополнение баланса Boostora на {sparks} Искр'
                else:
                    return ApiResult(400, {'ok': False, 'error': 'invalid_invoice_kind'})
                url = _telegram_invoice_link(title=title, description=description, payload=invoice_payload, stars=stars)
            except Exception:
                LOGGER.exception('Could not create Mini App wallet invoice for user_id=%s', user_id)
                return ApiResult(502, {'ok': False, 'error': 'invoice_failed'})
            return ApiResult(200, {'ok': True, 'invoice_url': url, 'stars': stars})

        if op == 'engagement.get':
            return ApiResult(200, {
                'ok': True,
                'summary': EngagementModeService.mode_summary(user_id),
                'dashboard': EngagementModeService.obligation_dashboard(user_id),
                'items': EngagementModeService.obligation_items(user_id, limit=30),
            })
        if op == 'engagement.standard':
            EngagementModeService.set_standard(user_id, source='miniapp')
            return ApiResult(200, {'ok': True, 'summary': EngagementModeService.mode_summary(user_id)})
        if op == 'engagement.pro_invoice':
            if not settings.enable_xtr_payments:
                return ApiResult(503, {'ok': False, 'error': 'payments_disabled'})
            stars = EngagementModeService.pro_price_stars()
            try:
                url = _telegram_invoice_link(
                    title='Boostora PRO',
                    description='PRO на 30 дней без ответных обязательств',
                    payload=make_payload('waengpro', '30d', user_id),
                    stars=stars,
                )
            except Exception:
                LOGGER.exception('Could not create Mini App PRO invoice for user_id=%s', user_id)
                return ApiResult(502, {'ok': False, 'error': 'invoice_failed'})
            return ApiResult(200, {'ok': True, 'invoice_url': url, 'stars': stars})

        if op == 'referrals.get':
            return ApiResult(200, {'ok': True, **_profile_payload(user_id)['referrals']})

        if op == 'catalog.get':
            category = str(payload.get('category') or '') or None
            subcategory = str(payload.get('subcategory') or '') or None
            query = str(payload.get('query') or '').strip().lower()
            page = max(1, int(payload.get('page') or 1))
            page_size = max(5, min(int(payload.get('page_size') or 20), 50))
            all_rows = BoostoreProviderService.list_catalog_services(
                enabled_only=True,
                category=category,
                subcategory=subcategory,
                limit=100000,
                offset=0,
            )
            if query:
                all_rows = [row for row in all_rows if query in str(row['name'] or '').lower()]
            total = len(all_rows)
            start = (page - 1) * page_size
            page_rows = all_rows[start:start + page_size]
            return ApiResult(200, {
                'ok': True,
                'categories': BoostoreProviderService.catalog_categories(enabled_only=True, language='ru'),
                'subcategories': BoostoreProviderService.catalog_subcategories(category, enabled_only=True, language='ru') if category else [],
                'services': [_catalog_service(row) for row in page_rows],
                'page': page,
                'page_size': page_size,
                'total': total,
                'pages': max(1, (total + page_size - 1) // page_size),
            })
        if op == 'catalog.prepare_order':
            if UserService.get_role(user_id) != 'client':
                return ApiResult(403, {'ok': False, 'error': 'client_role_required'})
            provider_state = BoostoreProviderService.config_state()
            if not provider_state.get('enabled') or not provider_state.get('configured'):
                return ApiResult(503, {'ok': False, 'error': 'service_temporarily_unavailable'})
            external_service_id = str(payload.get('service_id') or '')
            link = str(payload.get('link') or '')
            try:
                quantity = int(payload.get('quantity') or 0)
            except Exception:
                quantity = 0
            result = BoostoreProviderService.prepare_order(
                owner_user_id=user_id,
                external_service_id=external_service_id,
                link=link,
                quantity=quantity,
            )
            if not result.ok:
                return ApiResult(400, {'ok': False, 'error': result.result_key})
            data = result.data if isinstance(result.data, dict) else {}
            order_id = int(data.get('order_id') or 0)
            stars = int(data.get('price_stars') or 1)
            try:
                url = _telegram_invoice_link(
                    title='Услуга Telegram',
                    description=f'Заказ на {quantity} единиц',
                    payload=make_payload('waboostore', str(order_id), user_id),
                    stars=stars,
                )
            except Exception:
                LOGGER.exception('Could not create Mini App Boostore invoice order_id=%s', order_id)
                db.execute(
                    "UPDATE provider_orders SET provider_status = 'invoice_failed', last_error = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    ('invoice_link_failed', order_id),
                )
                return ApiResult(502, {'ok': False, 'error': 'invoice_failed'})
            return ApiResult(200, {'ok': True, 'invoice_url': url, 'stars': stars, 'order_id': order_id})

        if op == 'orders.get':
            return ApiResult(200, {'ok': True, 'orders': _provider_orders(user_id)})

        if op == 'campaigns.get':
            role_gate = _gate(user_id, role='client')
            if role_gate:
                return role_gate
            return ApiResult(200, {'ok': True, **_campaigns_payload(user_id)})
        if op == 'campaigns.quote':
            role_gate = _gate(user_id, role='client')
            if role_gate:
                return role_gate
            try:
                task_type = str(payload.get('task_type') or '')
                quantity = int(payload.get('quantity') or 0)
                raw_price = payload.get('unit_price')
                unit_price = None if raw_price in {None, '', 0, '0', 'auto'} else int(raw_price)
                pricing = calculate_campaign_pricing(task_type, quantity, unit_price)
            except Exception:
                return ApiResult(400, {'ok': False, 'error': 'campaign_quote_invalid'})
            return ApiResult(200, {'ok': True, 'pricing': pricing})
        if op == 'campaigns.create':
            role_gate = _gate(user_id, role='client')
            if role_gate:
                return role_gate
            task_type = str(payload.get('task_type') or '')
            target = str(payload.get('target') or '')
            engagement_mode = str(payload.get('engagement_mode') or '') or None
            try:
                quantity = int(payload.get('quantity') or 0)
                raw_price = payload.get('unit_price')
                unit_price_text = 'auto' if raw_price in {None, '', 0, '0', 'auto'} else str(int(raw_price))
                launch_now = bool(payload.get('launch_now', True))
            except Exception:
                return ApiResult(400, {'ok': False, 'error': 'campaign_input_invalid'})
            ClientCampaignService.clear_draft(user_id)
            ok, key = ClientCampaignService.start_draft(user_id, task_type, engagement_mode=engagement_mode)
            if not ok:
                return _result(False, key)
            ok, key, _ = ClientCampaignService.consume_target(user_id, target, bot=BOT_PROXY)
            if not ok:
                ClientCampaignService.clear_draft(user_id)
                return _result(False, key)
            if ClientCampaignService.get_mode(user_id) != 'campaign_price':
                ok, key, _ = ClientCampaignService.consume_quantity(user_id, str(quantity))
                if not ok:
                    ClientCampaignService.clear_draft(user_id)
                    return _result(False, key)
            ok, key, _ = ClientCampaignService.consume_price(user_id, unit_price_text)
            if not ok:
                ClientCampaignService.clear_draft(user_id)
                return _result(False, key)
            ok, key, campaign_id = ClientCampaignService.finalize_draft(user_id, launch_now)
            return ApiResult(200 if ok else 400, {'ok': ok, 'result': key, 'campaign_id': campaign_id})
        if op == 'campaigns.status':
            role_gate = _gate(user_id, role='client')
            if role_gate:
                return role_gate
            try:
                campaign_id = int(payload.get('campaign_id') or 0)
            except Exception:
                campaign_id = 0
            status = str(payload.get('status') or '')
            ok, key = CampaignService.update_status(user_id, campaign_id, status)
            return _result(ok, key)

        if op == 'tasks.get':
            role_gate = _gate(user_id, role='performer')
            if role_gate:
                return role_gate
            return ApiResult(200, {'ok': True, **_tasks_payload(user_id)})
        if op == 'tasks.take':
            role_gate = _gate(user_id, role='performer')
            if role_gate:
                return role_gate
            try:
                campaign_id = int(payload.get('campaign_id') or 0)
            except Exception:
                campaign_id = 0
            ok, key, submission_id = PerformerService.take_task(user_id, campaign_id)
            return ApiResult(200 if ok else 400, {'ok': ok, 'result': key, 'submission_id': submission_id})
        if op == 'tasks.submit':
            role_gate = _gate(user_id, role='performer')
            if role_gate:
                return role_gate
            try:
                submission_id = int(payload.get('submission_id') or 0)
            except Exception:
                submission_id = 0
            proof = str(payload.get('proof') or '')
            ok, key, result_id = PerformerService.submit_proof(user_id, submission_id, proof)
            return ApiResult(200 if ok else 400, {'ok': ok, 'result': key, 'result_id': result_id})
        if op == 'tasks.check':
            role_gate = _gate(user_id, role='performer')
            if role_gate:
                return role_gate
            try:
                submission_id = int(payload.get('submission_id') or 0)
            except Exception:
                submission_id = 0
            ok, key, result_id = PerformerService.submit_for_check(BOT_PROXY, user_id, submission_id)
            return ApiResult(200 if ok else 400, {'ok': ok, 'result': key, 'result_id': result_id})

        if op == 'admin.get':
            if not UserService.is_admin(user_id):
                return ApiResult(403, {'ok': False, 'error': 'access_denied'})
            return ApiResult(200, _admin_payload(user_id))
        if op == 'admin.review':
            if not UserService.is_admin(user_id):
                return ApiResult(403, {'ok': False, 'error': 'access_denied'})
            try:
                submission_id = int(payload.get('submission_id') or 0)
            except Exception:
                submission_id = 0
            approve = bool(payload.get('approve'))
            reason = str(payload.get('reason') or '') or None
            ok, key, performer_user_id = AdminService.review_submission(user_id, submission_id, approve=approve, reject_reason=reason)
            return ApiResult(200 if ok else 400, {'ok': ok, 'result': key, 'performer_user_id': performer_user_id})

        if op == 'owner.get':
            if not UserService.is_owner(user_id):
                return ApiResult(403, {'ok': False, 'error': 'access_denied'})
            return ApiResult(200, _owner_payload(user_id))
        if op == 'owner.catalog':
            if not UserService.is_owner(user_id):
                return ApiResult(403, {'ok': False, 'error': 'access_denied'})
            category = str(payload.get('category') or '') or None
            subcategory = str(payload.get('subcategory') or '') or None
            page = max(1, int(payload.get('page') or 1))
            page_size = max(10, min(int(payload.get('page_size') or 30), 100))
            all_rows = BoostoreProviderService.list_catalog_services(
                enabled_only=False,
                category=category,
                subcategory=subcategory,
                limit=100000,
                offset=0,
            )
            total = len(all_rows)
            start = (page - 1) * page_size
            return ApiResult(200, {
                'ok': True,
                'categories': BoostoreProviderService.catalog_categories(enabled_only=False, language='ru'),
                'subcategories': BoostoreProviderService.catalog_subcategories(category, enabled_only=False, language='ru') if category else [],
                'services': [_catalog_service(row, include_internal=True) for row in all_rows[start:start + page_size]],
                'page': page,
                'pages': max(1, (total + page_size - 1) // page_size),
                'total': total,
            })
        if op == 'owner.catalog_action':
            if not UserService.is_owner(user_id):
                return ApiResult(403, {'ok': False, 'error': 'access_denied'})
            action = str(payload.get('action') or '')
            if action == 'sync':
                result = BoostoreProviderService.sync_services(limit=None)
            elif action == 'toggle':
                result = BoostoreProviderService.toggle_service(str(payload.get('service_id') or ''))
            elif action in {'folder_enable', 'folder_disable'}:
                result = BoostoreProviderService.set_catalog_enabled(
                    enabled=action == 'folder_enable',
                    category=str(payload.get('category') or '') or None,
                    subcategory=str(payload.get('subcategory') or '') or None,
                )
            else:
                return ApiResult(400, {'ok': False, 'error': 'unknown_owner_action'})
            return ApiResult(200 if result.ok else 400, {'ok': result.ok, 'result': result.result_key, 'data': result.data})
        if op == 'owner.orders':
            if not UserService.is_owner(user_id):
                return ApiResult(403, {'ok': False, 'error': 'access_denied'})
            return ApiResult(200, {'ok': True, 'orders': _all_provider_orders(limit=int(payload.get('limit') or 100))})
        if op == 'owner.place_order':
            if not UserService.is_owner(user_id):
                return ApiResult(403, {'ok': False, 'error': 'access_denied'})
            try:
                order_id = int(payload.get('order_id') or 0)
            except Exception:
                order_id = 0
            result = BoostoreProviderService.place_prepared_order(order_id)
            return ApiResult(200 if result.ok else 400, {'ok': result.ok, 'result': result.result_key, 'data': result.data})

        return ApiResult(404, {'ok': False, 'error': 'unknown_operation'})
