from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hmac
import json
import logging
import mimetypes
from pathlib import Path
import threading
import time
from typing import Any
from urllib.parse import parse_qsl, unquote, urlsplit

from app.config import settings
from app.version import APP_VERSION
from app.services.activity import ActivityService


LOGGER = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATIC_ROOT = (PROJECT_ROOT / 'miniapp_example').resolve()
MAX_JSON_BODY_BYTES = 64 * 1024


class _ReusableThreadingHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


@dataclass
class WebAppRuntime:
    server: _ReusableThreadingHTTPServer
    thread: threading.Thread

    def stop(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        if self.thread.is_alive():
            self.thread.join(timeout=5)


def _safe_username() -> str:
    return settings.support_username.strip().lstrip('@')


def _telegram_bot_url() -> str:
    username = _safe_username()
    return f'https://t.me/{username}' if username else ''


def _json_bytes(payload: Any) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode('utf-8')


def _validate_telegram_init_data(init_data: str) -> tuple[bool, str, dict[str, Any] | None]:
    if not init_data or len(init_data) > MAX_JSON_BODY_BYTES:
        return False, 'empty_or_oversized', None

    try:
        pairs = dict(parse_qsl(init_data, keep_blank_values=True, strict_parsing=True))
    except (ValueError, TypeError):
        return False, 'malformed', None

    received_hash = pairs.pop('hash', '')
    if not received_hash:
        return False, 'missing_hash', None

    data_check_string = '\n'.join(f'{key}={value}' for key, value in sorted(pairs.items()))
    secret_key = hmac.new(b'WebAppData', settings.bot_token.encode('utf-8'), sha256).digest()
    expected_hash = hmac.new(secret_key, data_check_string.encode('utf-8'), sha256).hexdigest()
    if not hmac.compare_digest(received_hash, expected_hash):
        return False, 'invalid_hash', None

    try:
        auth_date = int(pairs.get('auth_date', '0'))
    except (TypeError, ValueError):
        return False, 'invalid_auth_date', None

    now = int(time.time())
    if auth_date <= 0 or auth_date > now + 60:
        return False, 'invalid_auth_date', None
    if now - auth_date > settings.webapp_auth_max_age_seconds:
        return False, 'expired', None

    raw_user = pairs.get('user', '')
    if not raw_user:
        return True, 'ok', None
    try:
        user = json.loads(raw_user)
    except json.JSONDecodeError:
        return False, 'invalid_user', None
    if not isinstance(user, dict):
        return False, 'invalid_user', None

    safe_user = {
        'id': user.get('id'),
        'first_name': user.get('first_name'),
        'last_name': user.get('last_name'),
        'username': user.get('username'),
        'language_code': user.get('language_code'),
        'is_premium': bool(user.get('is_premium', False)),
    }
    return True, 'ok', safe_user


class BoostoraWebHandler(BaseHTTPRequestHandler):
    server_version = 'BoostoraWeb/3.2.6'

    def log_message(self, fmt: str, *args: Any) -> None:
        if self.path.startswith('/health'):
            return
        LOGGER.info('WebApp %s - %s', self.address_string(), fmt % args)

    def _common_headers(self, *, content_type: str, content_length: int, cache_control: str) -> None:
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(content_length))
        self.send_header('Cache-Control', cache_control)
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Permissions-Policy', 'camera=(), microphone=(), geolocation=()')
        self.send_header(
            'Content-Security-Policy',
            "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
            "script-src 'self' 'unsafe-inline' https://telegram.org; connect-src 'self'; "
            "base-uri 'none'; form-action 'none'; frame-ancestors 'self' https://web.telegram.org https://*.telegram.org",
        )

    def _send_bytes(
        self,
        status: HTTPStatus,
        payload: bytes,
        *,
        content_type: str,
        cache_control: str = 'no-store',
        head_only: bool = False,
    ) -> None:
        self.send_response(status)
        self._common_headers(content_type=content_type, content_length=len(payload), cache_control=cache_control)
        self.end_headers()
        if not head_only:
            self.wfile.write(payload)

    def _send_json(self, status: HTTPStatus, payload: Any, *, head_only: bool = False) -> None:
        self._send_bytes(
            status,
            _json_bytes(payload),
            content_type='application/json; charset=utf-8',
            cache_control='no-store',
            head_only=head_only,
        )

    def _send_error_json(self, status: HTTPStatus, code: str, *, head_only: bool = False) -> None:
        self._send_json(status, {'ok': False, 'error': code}, head_only=head_only)

    def _static_file_for_path(self, request_path: str) -> Path | None:
        clean_path = unquote(urlsplit(request_path).path)
        if clean_path in {'/', '/index.html', '/miniapp', '/miniapp/'}:
            relative = Path('index.html')
        else:
            if clean_path.startswith('/miniapp/'):
                clean_path = clean_path[len('/miniapp'):]
            relative = Path(clean_path.lstrip('/'))

        if any(part in {'', '.', '..'} for part in relative.parts):
            return None
        candidate = (STATIC_ROOT / relative).resolve()
        try:
            candidate.relative_to(STATIC_ROOT)
        except ValueError:
            return None
        if not candidate.is_file():
            return None
        return candidate

    def _serve_static(self, *, head_only: bool = False) -> None:
        path = self._static_file_for_path(self.path)
        if path is None:
            self._send_error_json(HTTPStatus.NOT_FOUND, 'not_found', head_only=head_only)
            return
        try:
            payload = path.read_bytes()
        except OSError:
            LOGGER.exception('Could not read Mini App asset: %s', path)
            self._send_error_json(HTTPStatus.INTERNAL_SERVER_ERROR, 'asset_read_failed', head_only=head_only)
            return
        content_type = mimetypes.guess_type(path.name)[0] or 'application/octet-stream'
        if content_type.startswith('text/') or content_type in {'application/javascript', 'image/svg+xml'}:
            content_type = f'{content_type}; charset=utf-8'
        cache_control = 'no-store' if path.name == 'index.html' else 'public, max-age=86400, immutable'
        self._send_bytes(
            HTTPStatus.OK,
            payload,
            content_type=content_type,
            cache_control=cache_control,
            head_only=head_only,
        )

    def _handle_health(self, *, head_only: bool = False) -> None:
        self._send_json(
            HTTPStatus.OK,
            {
                'ok': True,
                'service': 'boostora',
                'version': APP_VERSION,
                'webapp': True,
                'time': datetime.now(timezone.utc).isoformat(),
            },
            head_only=head_only,
        )

    def _handle_config(self, *, head_only: bool = False) -> None:
        self._send_json(
            HTTPStatus.OK,
            {
                'ok': True,
                'brand_name': settings.brand_name,
                'version': APP_VERSION,
                'support_username': settings.support_username,
                'bot_url': _telegram_bot_url(),
                'webapp_url': settings.mini_app_url,
                'features': {
                    'standard': True,
                    'pro': True,
                    'boostore': settings.boostore_enabled,
                    'telegram_auth': True,
                },
            },
            head_only=head_only,
        )

    def _read_json_body(self) -> dict[str, Any] | None:
        try:
            content_length = int(self.headers.get('Content-Length', '0'))
        except ValueError:
            return None
        if content_length <= 0 or content_length > MAX_JSON_BODY_BYTES:
            return None
        try:
            raw = self.rfile.read(content_length)
            payload = json.loads(raw.decode('utf-8'))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

    def _handle_telegram_session(self) -> None:
        payload = self._read_json_body()
        if payload is None:
            self._send_error_json(HTTPStatus.BAD_REQUEST, 'invalid_json')
            return
        init_data = payload.get('init_data')
        if not isinstance(init_data, str):
            self._send_error_json(HTTPStatus.BAD_REQUEST, 'missing_init_data')
            return
        valid, reason, user = _validate_telegram_init_data(init_data)
        if not valid:
            self._send_json(HTTPStatus.UNAUTHORIZED, {'ok': False, 'authenticated': False, 'reason': reason})
            return
        self._send_json(HTTPStatus.OK, {'ok': True, 'authenticated': True, 'user': user})


    def _handle_miniapp_open(self) -> None:
        payload = self._read_json_body()
        if payload is None:
            self._send_error_json(HTTPStatus.BAD_REQUEST, 'invalid_json')
            return
        init_data = payload.get('init_data')
        if not isinstance(init_data, str):
            self._send_error_json(HTTPStatus.BAD_REQUEST, 'missing_init_data')
            return
        valid, reason, user = _validate_telegram_init_data(init_data)
        if not valid or not user:
            self._send_json(
                HTTPStatus.UNAUTHORIZED,
                {'ok': False, 'authenticated': False, 'reason': reason if not valid else 'missing_user'},
            )
            return
        try:
            user_id = int(user.get('id'))
        except (TypeError, ValueError):
            self._send_error_json(HTTPStatus.BAD_REQUEST, 'invalid_user_id')
            return
        hint = payload.get('hint', '')
        source = payload.get('source', 'embedded_webapp')
        if not isinstance(hint, str) or not isinstance(source, str):
            self._send_error_json(HTTPStatus.BAD_REQUEST, 'invalid_event')
            return
        try:
            ActivityService.record_mini_app_open(
                user_id,
                hint=hint,
                source=source,
                payload={'platform': payload.get('platform'), 'app_version': payload.get('app_version')},
            )
        except Exception:
            LOGGER.exception('Could not record validated Mini App open event for user_id=%s', user_id)
            self._send_error_json(HTTPStatus.INTERNAL_SERVER_ERROR, 'event_store_failed')
            return
        self._send_json(HTTPStatus.OK, {'ok': True, 'recorded': True})

    def do_GET(self) -> None:  # noqa: N802
        path = urlsplit(self.path).path
        if path in {'/health', '/healthz'}:
            self._handle_health()
            return
        if path == '/api/config':
            self._handle_config()
            return
        self._serve_static()

    def do_HEAD(self) -> None:  # noqa: N802
        path = urlsplit(self.path).path
        if path in {'/health', '/healthz'}:
            self._handle_health(head_only=True)
            return
        if path == '/api/config':
            self._handle_config(head_only=True)
            return
        self._serve_static(head_only=True)

    def do_POST(self) -> None:  # noqa: N802
        path = urlsplit(self.path).path
        if path == '/api/telegram/session':
            self._handle_telegram_session()
            return
        if path == '/api/miniapp/open':
            self._handle_miniapp_open()
            return
        self._send_error_json(HTTPStatus.NOT_FOUND, 'not_found')


def start_webapp_server() -> WebAppRuntime | None:
    if not settings.webapp_enabled:
        LOGGER.info('Embedded Mini App web server is disabled by WEBAPP_ENABLED=0')
        return None
    if not STATIC_ROOT.joinpath('index.html').is_file():
        message = f'Mini App index not found: {STATIC_ROOT / "index.html"}'
        if settings.webapp_required:
            raise RuntimeError(message)
        LOGGER.error(message)
        return None

    try:
        server = _ReusableThreadingHTTPServer(
            (settings.webapp_host, settings.webapp_port),
            BoostoraWebHandler,
        )
    except OSError as exc:
        message = f'Could not bind Mini App web server on {settings.webapp_host}:{settings.webapp_port}: {exc}'
        if settings.webapp_required:
            raise RuntimeError(message) from exc
        LOGGER.error(message)
        return None

    thread = threading.Thread(target=server.serve_forever, name='webapp-server', daemon=True)
    thread.start()
    LOGGER.info('Embedded Mini App is listening on http://%s:%s', settings.webapp_host, settings.webapp_port)
    if settings.mini_app_url:
        LOGGER.info('Telegram Mini App public URL: %s', settings.mini_app_url)
    else:
        LOGGER.warning('Mini App server is running, but public WEBAPP_URL/MINI_APP_URL is not configured')
    return WebAppRuntime(server=server, thread=thread)
