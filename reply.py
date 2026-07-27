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
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit

from app import db
from app.config import settings
from app.version import APP_VERSION
from app.services.activity import ActivityService
from app.services.engagement_modes import EngagementModeService
from app.services.smart_hub import SmartHubService
from app.services.users import UserService
from app.services.wallets import WalletService


LOGGER = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATIC_ROOT = (PROJECT_ROOT / 'miniapp_example').resolve()
MAX_JSON_BODY_BYTES = 64 * 1024

# Mini App actions never execute privileged operations directly. They only create a
# signed, role-checked deep link to an existing protected bot screen. The bot then
# applies all community rules, legal documents, subscription and access gates again.
ACTION_START_PARAMS: dict[str, tuple[str, str]] = {
    'main': ('main_menu', 'user'),
    'hub': ('smart_hub', 'user'),
    'tasks': ('tasks', 'performer'),
    'wallet': ('wallet', 'user'),
    'history': ('history', 'user'),
    'campaigns': ('campaigns', 'client'),
    'stats': ('stats', 'client'),
    'marketplace': ('marketplace', 'client'),
    'engagement': ('engagement_mode', 'user'),
    'obligations': ('engagement_obligations', 'user'),
    'rules': ('community_rules', 'user'),
    'legal': ('legal_docs', 'user'),
    'rewards': ('rewards', 'user'),
    'referrals': ('referrals', 'user'),
    'vip': ('vip', 'user'),
    'admin': ('admin', 'admin'),
    'admin_queue': ('admin_queue', 'admin'),
    'admin_obligations': ('admin_engagement_obligations', 'admin'),
    'admin_logs': ('admin_logs', 'admin'),
    'owner_analytics': ('owner_analytics', 'owner'),
    'owner_release': ('owner_release', 'owner'),
    'owner_provider': ('owner_provider', 'owner'),
}


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


def _telegram_bot_url(start_param: str = '') -> str:
    username = _safe_username()
    if not username:
        return ''
    base = f'https://t.me/{username}'
    if start_param:
        return f'{base}?{urlencode({"start": f"wa_{start_param}"})}'
    return base


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


def _user_id(user: dict[str, Any] | None) -> int | None:
    if not user:
        return None
    try:
        value = int(user.get('id'))
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _can_use_action(user_id: int, audience: str) -> bool:
    if not UserService.can_access_bot(user_id):
        return False
    if audience == 'owner':
        return UserService.is_owner(user_id)
    if audience == 'admin':
        return UserService.is_admin(user_id)
    role = UserService.get_role(user_id) or ''
    if audience == 'client':
        return role == 'client'
    if audience == 'performer':
        return role == 'performer'
    return True


def _safe_dashboard(user_id: int) -> dict[str, Any]:
    user_row = UserService.get_user(user_id)
    role = UserService.get_role(user_id) or ''
    status = UserService.get_status(user_id)
    if user_row is None:
        return {
            'registered': False,
            'role': '',
            'status': status,
            'wallet': {},
            'activity': {},
            'engagement': {},
        }

    wallet = WalletService.get_summary(user_id)
    smart = SmartHubService.dashboard(user_id)
    obligations = EngagementModeService.obligation_dashboard(user_id)
    mode = EngagementModeService.current_mode(user_id) or 'not_selected'
    return {
        'registered': True,
        'role': role,
        'status': status,
        'wallet': {
            'available': int(wallet.get('available_balance', 0)),
            'hold': int(wallet.get('hold_balance', 0)),
            'campaign': int(wallet.get('campaign_balance', 0)),
            'bonus': int(wallet.get('bonus_balance', 0)),
            'earned': int(wallet.get('lifetime_earned', 0)),
        },
        'activity': {
            'available_tasks': int(smart.get('available_tasks', 0)),
            'active_tasks': int(smart.get('active_tasks', 0)),
            'task_limit': int(smart.get('task_limit', 0)),
            'client_campaigns': int(smart.get('client_campaigns', 0)),
            'client_active': int(smart.get('client_active', 0)),
            'client_drafts': int(smart.get('client_drafts', 0)),
        },
        'engagement': {
            'mode': mode,
            'open': int(obligations.get('open_count', 0)),
            'done': int(obligations.get('total_done', 0)),
            'remaining': int(obligations.get('total_remaining', 0)),
            'overdue': int(obligations.get('overdue_count', 0)),
            'required': int(EngagementModeService.required_actions()),
            'pro_price_stars': int(EngagementModeService.pro_price_stars()),
        },
    }


def _session_payload(user: dict[str, Any]) -> dict[str, Any]:
    user_id = _user_id(user)
    if user_id is None:
        raise ValueError('invalid_user_id')
    role = UserService.get_role(user_id) or ''
    is_owner = UserService.is_owner(user_id)
    is_admin = UserService.is_admin(user_id)
    allowed_actions = [
        name for name, (_, audience) in ACTION_START_PARAMS.items()
        if _can_use_action(user_id, audience)
    ]
    payload: dict[str, Any] = {
        'ok': True,
        'authenticated': True,
        'user': user,
        'access': {
            'role': role,
            'is_admin': is_admin,
            'is_owner': is_owner,
            'allowed_actions': allowed_actions,
        },
        'dashboard': _safe_dashboard(user_id),
    }
    # Technical release metadata is intentionally owner-only.
    if is_owner:
        payload['owner_meta'] = {'version': APP_VERSION}
    return payload


class BoostoraWebHandler(BaseHTTPRequestHandler):
    server_version = 'BoostoraWeb/3.2.8'

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

    def _send_bytes(self, status: HTTPStatus, payload: bytes, *, content_type: str, cache_control: str = 'no-store', head_only: bool = False) -> None:
        self.send_response(status)
        self._common_headers(content_type=content_type, content_length=len(payload), cache_control=cache_control)
        self.end_headers()
        if not head_only:
            self.wfile.write(payload)

    def _send_json(self, status: HTTPStatus, payload: Any, *, head_only: bool = False) -> None:
        self._send_bytes(status, _json_bytes(payload), content_type='application/json; charset=utf-8', cache_control='no-store', head_only=head_only)

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
        return candidate if candidate.is_file() else None

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
        self._send_bytes(HTTPStatus.OK, payload, content_type=content_type, cache_control=cache_control, head_only=head_only)

    def _handle_health(self, *, head_only: bool = False) -> None:
        self._send_json(HTTPStatus.OK, {'ok': True, 'service': 'boostora', 'version': APP_VERSION, 'webapp': True, 'time': datetime.now(timezone.utc).isoformat()}, head_only=head_only)

    def _handle_config(self, *, head_only: bool = False) -> None:
        # Public config deliberately contains no owner/admin details or provider state.
        self._send_json(HTTPStatus.OK, {
            'ok': True,
            'brand_name': settings.brand_name,
            'support_username': settings.support_username,
            'bot_url': _telegram_bot_url(),
            'webapp_url': settings.mini_app_url,
        }, head_only=head_only)

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

    def _validated_user_from_payload(self, payload: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        init_data = payload.get('init_data')
        if not isinstance(init_data, str):
            return None, 'missing_init_data'
        valid, reason, user = _validate_telegram_init_data(init_data)
        if not valid:
            return None, reason
        if not user or _user_id(user) is None:
            return None, 'missing_user'
        return user, 'ok'

    def _handle_telegram_session(self) -> None:
        payload = self._read_json_body()
        if payload is None:
            self._send_error_json(HTTPStatus.BAD_REQUEST, 'invalid_json')
            return
        user, reason = self._validated_user_from_payload(payload)
        if user is None:
            self._send_json(HTTPStatus.UNAUTHORIZED, {'ok': False, 'authenticated': False, 'reason': reason})
            return
        try:
            self._send_json(HTTPStatus.OK, _session_payload(user))
        except Exception:
            LOGGER.exception('Could not build Mini App session')
            self._send_error_json(HTTPStatus.INTERNAL_SERVER_ERROR, 'session_failed')

    def _handle_miniapp_action(self) -> None:
        payload = self._read_json_body()
        if payload is None:
            self._send_error_json(HTTPStatus.BAD_REQUEST, 'invalid_json')
            return
        user, reason = self._validated_user_from_payload(payload)
        if user is None:
            self._send_json(HTTPStatus.UNAUTHORIZED, {'ok': False, 'authenticated': False, 'reason': reason})
            return
        action = str(payload.get('action') or '').strip()
        action_meta = ACTION_START_PARAMS.get(action)
        if action_meta is None:
            self._send_error_json(HTTPStatus.BAD_REQUEST, 'unknown_action')
            return
        user_id = _user_id(user)
        if user_id is None:
            self._send_error_json(HTTPStatus.BAD_REQUEST, 'invalid_user_id')
            return
        start_param, audience = action_meta
        if not _can_use_action(user_id, audience):
            self._send_error_json(HTTPStatus.FORBIDDEN, 'access_denied')
            return
        url = _telegram_bot_url(start_param)
        if not url:
            self._send_error_json(HTTPStatus.SERVICE_UNAVAILABLE, 'bot_url_unavailable')
            return
        self._send_json(HTTPStatus.OK, {'ok': True, 'action': action, 'open_url': url})

    def _handle_miniapp_open(self) -> None:
        payload = self._read_json_body()
        if payload is None:
            self._send_error_json(HTTPStatus.BAD_REQUEST, 'invalid_json')
            return
        user, reason = self._validated_user_from_payload(payload)
        if user is None:
            self._send_json(HTTPStatus.UNAUTHORIZED, {'ok': False, 'authenticated': False, 'reason': reason})
            return
        user_id = _user_id(user)
        if user_id is None:
            self._send_error_json(HTTPStatus.BAD_REQUEST, 'invalid_user_id')
            return
        hint = payload.get('hint', '')
        source = payload.get('source', 'embedded_webapp')
        if not isinstance(hint, str) or not isinstance(source, str):
            self._send_error_json(HTTPStatus.BAD_REQUEST, 'invalid_event')
            return
        try:
            ActivityService.record_mini_app_open(user_id, hint=hint, source=source, payload={'platform': payload.get('platform')})
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
        if path == '/api/miniapp/action':
            self._handle_miniapp_action()
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
        server = _ReusableThreadingHTTPServer((settings.webapp_host, settings.webapp_port), BoostoraWebHandler)
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
