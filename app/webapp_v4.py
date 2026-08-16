from __future__ import annotations

from hashlib import sha256
from http import HTTPStatus
import json
import logging
import secrets
from typing import Any
from urllib.parse import urlsplit

from app import db
from app.config import settings
from app.services.api_guard import GLOBAL_API_GUARD
from app.services.miniapp_api import MiniAppApiService
from app.services.runtime_metrics import RUNTIME_METRICS
from app.services.startup_guard import last_startup_report, run_startup_guard
from app.services.system_health import SystemHealthService
from app.version import APP_VERSION
from app.webapp import (
    BoostoraWebHandler,
    MINIAPP_USER_LOCK_STRIPES,
    STATIC_ROOT,
    WebAppRuntime,
    _MINIAPP_USER_LOCKS,
    _READ_ONLY_MINIAPP_OPERATIONS,
    _ReusableThreadingHTTPServer,
    _user_id,
)


LOGGER = logging.getLogger(__name__)


class BoostoraWebHandlerV4(BoostoraWebHandler):
    """v4 gateway layered over the proven v3.7 API contract.

    Existing routes and payloads remain compatible. The layer adds bounded per-user
    rate protection, optional idempotency keys, request tracing and richer readiness.
    """

    server_version = 'BoostoraWeb/4.0.0'

    def _start_request_trace(self) -> None:
        self._request_id = secrets.token_hex(8)

    def _common_headers(self, *, content_type: str, content_length: int, cache_control: str) -> None:
        super()._common_headers(
            content_type=content_type,
            content_length=content_length,
            cache_control=cache_control,
        )
        self.send_header('X-Request-ID', getattr(self, '_request_id', ''))
        self.send_header('X-Boostora-Version', APP_VERSION)
        self.send_header('Cross-Origin-Resource-Policy', 'same-origin')

    def _send_json(self, status: HTTPStatus, payload: Any, *, head_only: bool = False) -> None:
        if isinstance(payload, dict):
            payload = dict(payload)
            payload.setdefault('request_id', getattr(self, '_request_id', ''))
        super()._send_json(status, payload, head_only=head_only)

    def _client_idempotency_key(self, body: dict[str, Any]) -> str:
        return GLOBAL_API_GUARD.normalize_idempotency_key(
            body.get('request_id') or body.get('idempotency_key') or self.headers.get('Idempotency-Key', '')
        )

    @staticmethod
    def _idempotency_scope(operation: str, payload: dict[str, Any]) -> str:
        try:
            raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'), default=str)
        except Exception:
            raw = repr(payload)
        fingerprint = sha256(raw.encode('utf-8', errors='replace')).hexdigest()[:24]
        return f'{operation}|{fingerprint}'

    def _handle_miniapp_query(self) -> None:
        body = self._read_json_body()
        if body is None:
            self._send_error_json(HTTPStatus.BAD_REQUEST, 'invalid_json')
            return
        user, reason = self._validated_user_from_payload(body)
        if user is None:
            self._send_json(HTTPStatus.UNAUTHORIZED, {'ok': False, 'authenticated': False, 'reason': reason})
            return

        operation = str(body.get('operation') or '').strip()
        data = body.get('payload')
        if data is None:
            data = {}
        if not isinstance(data, dict):
            self._send_error_json(HTTPStatus.BAD_REQUEST, 'invalid_payload')
            return

        user_id = _user_id(user)
        if user_id is None:
            self._send_error_json(HTTPStatus.BAD_REQUEST, 'invalid_user_id')
            return

        normalized_operation = operation.lower()
        read_only = normalized_operation in _READ_ONLY_MINIAPP_OPERATIONS
        decision = GLOBAL_API_GUARD.allow(user_id, read_only=read_only)
        if not decision.allowed:
            RUNTIME_METRICS.record_api(operation, rate_limited=True)
            self._send_json(
                HTTPStatus.TOO_MANY_REQUESTS,
                {
                    'ok': False,
                    'error': 'rate_limited',
                    'retry_after': decision.retry_after_seconds,
                },
            )
            return

        idempotency_key = '' if read_only else self._client_idempotency_key(body)
        idempotency_scope = self._idempotency_scope(normalized_operation, data)
        if idempotency_key:
            cached = GLOBAL_API_GUARD.lookup(user_id, idempotency_scope, idempotency_key)
            if cached is not None:
                replay_payload = dict(cached.payload)
                replay_payload['idempotent_replay'] = True
                RUNTIME_METRICS.record_api(operation, replayed=True)
                try:
                    status = HTTPStatus(cached.status)
                except (TypeError, ValueError):
                    status = HTTPStatus.OK
                self._send_json(status, replay_payload)
                return

        lock = None if read_only else _MINIAPP_USER_LOCKS[user_id % MINIAPP_USER_LOCK_STRIPES]
        try:
            if lock is None:
                result = MiniAppApiService.dispatch(user, operation, data)
            else:
                with lock:
                    # Re-check after taking the mutation lock so two concurrent
                    # identical requests with the same key cannot both execute.
                    if idempotency_key:
                        cached = GLOBAL_API_GUARD.lookup(user_id, idempotency_scope, idempotency_key)
                        if cached is not None:
                            replay_payload = dict(cached.payload)
                            replay_payload['idempotent_replay'] = True
                            RUNTIME_METRICS.record_api(operation, replayed=True)
                            try:
                                status = HTTPStatus(cached.status)
                            except (TypeError, ValueError):
                                status = HTTPStatus.OK
                            self._send_json(status, replay_payload)
                            return
                    result = MiniAppApiService.dispatch(user, operation, data)
        except Exception:
            LOGGER.exception('Mini App v4 operation failed: operation=%s user_id=%s', operation, user_id)
            RUNTIME_METRICS.record_api(operation, error=True)
            self._send_error_json(HTTPStatus.INTERNAL_SERVER_ERROR, 'operation_failed')
            return

        try:
            status = HTTPStatus(result.status)
        except (TypeError, ValueError):
            status = HTTPStatus.INTERNAL_SERVER_ERROR

        result_payload = (
            dict(result.payload)
            if isinstance(result.payload, dict)
            else {'ok': False, 'error': 'invalid_service_payload'}
        )
        if idempotency_key and 200 <= int(status) < 300:
            GLOBAL_API_GUARD.store(
                user_id,
                idempotency_scope,
                idempotency_key,
                status=int(status),
                payload=result_payload,
            )
        RUNTIME_METRICS.record_api(operation, error=int(status) >= 500)
        self._send_json(status, result_payload)

    def _handle_health_ready(self, *, head_only: bool = False) -> None:
        try:
            database_ok = bool(db.health_status().get('ok'))
        except Exception:
            LOGGER.exception('Could not query database readiness')
            database_ok = False
        static_ready = STATIC_ROOT.joinpath('index.html').is_file()
        startup = last_startup_report()
        try:
            runtime = SystemHealthService.snapshot()
            disk_ok = bool(runtime.get('disk', {}).get('ok'))
            worker_ok = bool(runtime.get('worker', {}).get('ok'))
        except Exception:
            LOGGER.exception('Could not build extended readiness snapshot')
            disk_ok = False
            worker_ok = False

        # Worker heartbeat is reported but is not a hard readiness dependency:
        # the web server starts before the background worker during deployment.
        ready = database_ok and static_ready and startup.ok and disk_ok
        self._send_json(
            HTTPStatus.OK if ready else HTTPStatus.SERVICE_UNAVAILABLE,
            {
                'ok': ready,
                'service': 'boostora',
                'version': APP_VERSION,
                'database': {'ok': database_ok},
                'miniapp_assets': static_ready,
                'disk': {'ok': disk_ok},
                'worker': {'ok': worker_ok},
                'startup': startup.public_payload(),
                'gateway': {
                    'ok': True,
                    'rate_limit': True,
                    'idempotency': True,
                    'request_trace': True,
                },
            },
            head_only=head_only,
        )

    def do_GET(self) -> None:  # noqa: N802
        self._start_request_trace()
        error = False
        try:
            path = urlsplit(self.path).path
            if path == '/health/live':
                self._send_json(
                    HTTPStatus.OK,
                    {'ok': True, 'service': 'boostora', 'version': APP_VERSION, 'live': True},
                )
                return
            if path == '/api/capabilities':
                self._send_json(
                    HTTPStatus.OK,
                    {
                        'ok': True,
                        'api_version': '4.0',
                        'features': [
                            'per_user_rate_limit',
                            'mutation_idempotency',
                            'request_trace',
                            'deep_readiness',
                        ],
                    },
                )
                return
            super().do_GET()
        except Exception:
            error = True
            raise
        finally:
            RUNTIME_METRICS.record_request(error=error)

    def do_HEAD(self) -> None:  # noqa: N802
        self._start_request_trace()
        error = False
        try:
            path = urlsplit(self.path).path
            if path == '/health/live':
                self._send_json(
                    HTTPStatus.OK,
                    {'ok': True, 'service': 'boostora', 'version': APP_VERSION, 'live': True},
                    head_only=True,
                )
                return
            if path == '/api/capabilities':
                self._send_json(
                    HTTPStatus.OK,
                    {'ok': True, 'api_version': '4.0'},
                    head_only=True,
                )
                return
            super().do_HEAD()
        except Exception:
            error = True
            raise
        finally:
            RUNTIME_METRICS.record_request(error=error)

    def do_POST(self) -> None:  # noqa: N802
        self._start_request_trace()
        error = False
        try:
            super().do_POST()
        except Exception:
            error = True
            raise
        finally:
            RUNTIME_METRICS.record_request(error=error)


def start_webapp_server_v4() -> WebAppRuntime | None:
    if not settings.webapp_enabled:
        LOGGER.info('Embedded Mini App web server is disabled by WEBAPP_ENABLED=0')
        return None
    if not STATIC_ROOT.joinpath('index.html').is_file():
        message = f'Mini App index not found: {STATIC_ROOT / "index.html"}'
        if settings.webapp_required:
            raise RuntimeError(message)
        LOGGER.error(message)
        return None

    run_startup_guard(STATIC_ROOT)

    try:
        server = _ReusableThreadingHTTPServer(
            (settings.webapp_host, settings.webapp_port),
            BoostoraWebHandlerV4,
        )
    except OSError as exc:
        message = f'Could not bind Mini App v4 server on {settings.webapp_host}:{settings.webapp_port}: {exc}'
        if settings.webapp_required:
            raise RuntimeError(message) from exc
        LOGGER.error(message)
        return None

    import threading

    thread = threading.Thread(target=server.serve_forever, name='webapp-v4-server', daemon=True)
    thread.start()
    LOGGER.info('Boostora v4 Mini App gateway is listening on http://%s:%s', settings.webapp_host, settings.webapp_port)
    if settings.mini_app_url:
        LOGGER.info('Telegram Mini App public URL: %s', settings.mini_app_url)
    else:
        LOGGER.warning('Mini App server is running, but public WEBAPP_URL/MINI_APP_URL is not configured')
    return WebAppRuntime(server=server, thread=thread)
