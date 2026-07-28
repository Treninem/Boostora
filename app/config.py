from dataclasses import dataclass
from pathlib import Path
import os

from dotenv import load_dotenv


load_dotenv()

LEGACY_REQUIRED_CHAT_ID = '-4998535978'
LEGACY_REQUIRED_CHAT_LINK = 'https://t.me/+I8t5mJaHGh80ODJi'
DEFAULT_PUBLIC_REQUIRED_CHAT_REF = '@Boostorachat'
DEFAULT_PUBLIC_REQUIRED_CHAT_LINK = 'https://t.me/Boostorachat'

CONFIG_WARNINGS: list[str] = []


@dataclass(frozen=True)
class Settings:
    bot_token: str
    admin_ids: list[int]
    db_path: str
    data_dir: str
    brand_name: str
    support_username: str
    default_hold_hours: int
    demo_hold_minutes: int
    enable_demo_topup: bool
    enable_xtr_payments: bool
    required_chat_id: str
    required_chat_invite_link: str
    run_command: str
    promo_interval_hours: int
    smart_bottom_menu: str
    mini_app_url: str
    webapp_enabled: bool
    webapp_required: bool
    webapp_host: str
    webapp_port: int
    webapp_auth_max_age_seconds: int
    boostore_enabled: bool
    boostore_api_url: str
    boostore_api_key: str
    boostore_default_markup_percent: int
    boostore_request_timeout_seconds: int
    boostore_auto_sync: bool
    boostore_auto_order_enabled: bool
    provider_order_timeout_minutes: int
    credits_per_star: int
    provider_credits_per_price_unit: int
    max_bonus_payment_percent: int
    network_min_members: int
    network_max_platforms_per_user: int
    network_base_placement_credits: int
    legal_docs_required: bool
    legal_docs_version: str
    community_rules_required: bool
    community_rules_version: str
    engagement_standard_required_actions: int
    engagement_pro_monthly_stars: int
    engagement_obligation_due_hours: int
    engagement_reminders_enabled: bool
    engagement_reminder_before_hours: int
    engagement_overdue_blocks_standard: bool
    engagement_admin_warnings_enabled: bool
    drop_pending_updates: bool
    legacy_db_restore_enabled: bool
    legacy_db_mirror_enabled: bool
    legacy_mirror_interval_seconds: int
    background_worker_interval_seconds: int
    db_backup_interval_hours: int
    db_backup_max_files: int


def _add_config_warning(message: str) -> None:
    if message not in CONFIG_WARNINGS:
        CONFIG_WARNINGS.append(message)


def _parse_admin_ids(raw_value: str) -> list[int]:
    ids: list[int] = []
    seen: set[int] = set()
    for chunk in (raw_value or '').split(','):
        value = chunk.strip()
        if not value:
            continue
        try:
            parsed = int(value)
        except ValueError:
            _add_config_warning(f'ADMIN_IDS contains invalid value: {value}')
            continue
        if parsed <= 0:
            _add_config_warning(f'ADMIN_IDS contains non-positive value: {value}')
            continue
        if parsed in seen:
            continue
        seen.add(parsed)
        ids.append(parsed)
    if raw_value.strip() and not ids:
        _add_config_warning('ADMIN_IDS is set but has no valid numeric ids')
    return ids


def _parse_bool(raw_value: str, default: bool = False) -> bool:
    if raw_value is None:
        return default
    value = raw_value.strip().lower()
    if value in {'1', 'true', 'yes', 'on'}:
        return True
    if value in {'0', 'false', 'no', 'off'}:
        return False
    _add_config_warning(f'boolean value is invalid and default was used: {raw_value}')
    return default


def _parse_int_env(name: str, default: int, *, minimum: int | None = None, maximum: int | None = None) -> int:
    raw_value = os.getenv(name, str(default)).strip()
    try:
        value = int(raw_value)
    except ValueError:
        _add_config_warning(f'{name} must be an integer; default {default} was used')
        return default
    if minimum is not None and value < minimum:
        _add_config_warning(f'{name} is below minimum {minimum}; default {default} was used')
        return default
    if maximum is not None and value > maximum:
        _add_config_warning(f'{name} is above maximum {maximum}; default {default} was used')
        return default
    return value


def _get_required_env(name: str) -> str:
    value = os.getenv(name, '').strip()
    if not value:
        raise RuntimeError(f'Missing required environment variable: {name}')
    return value


def _normalize_default_required_chat_ref(raw_value: str) -> str:
    value = (raw_value or '').strip()
    if not value or value == LEGACY_REQUIRED_CHAT_ID:
        return DEFAULT_PUBLIC_REQUIRED_CHAT_REF
    if value.startswith('https://t.me/'):
        username = value.rsplit('/', 1)[-1].strip()
        if username:
            return f'@{username.lstrip("@")}'
    return value




def _resolve_data_dir() -> str:
    explicit = os.getenv('BOT_DATA_DIR', '').strip()
    if explicit:
        return explicit
    if Path('/data').exists():
        return '/data'
    return 'storage'


def _resolve_db_path(raw_value: str, data_dir: str) -> str:
    value = (raw_value or '').strip() or 'boostora.db'
    path = Path(value)
    if path.is_absolute():
        return str(path)
    return str(Path(data_dir) / path.name)



def _normalize_public_url(raw_value: str) -> str:
    value = (raw_value or '').strip().rstrip('/')
    if not value:
        return ''
    if '://' not in value:
        value = f'https://{value}'
    return value


def _resolve_mini_app_url() -> str:
    mini_app_url = _normalize_public_url(os.getenv('MINI_APP_URL', ''))
    webapp_url = _normalize_public_url(os.getenv('WEBAPP_URL', ''))
    public_base_url = _normalize_public_url(os.getenv('PUBLIC_BASE_URL', ''))
    domain_url = _normalize_public_url(os.getenv('DOMAIN', ''))

    if mini_app_url and webapp_url and mini_app_url != webapp_url:
        _add_config_warning('MINI_APP_URL and WEBAPP_URL differ; MINI_APP_URL has priority')
    return mini_app_url or webapp_url or public_base_url or domain_url


def _resolve_webapp_port() -> int:
    if os.getenv('WEBAPP_PORT', '').strip():
        return _parse_int_env('WEBAPP_PORT', 3000, minimum=1, maximum=65535)
    return _parse_int_env('PORT', 3000, minimum=1, maximum=65535)


def _normalize_default_required_chat_link(raw_value: str) -> str:
    value = (raw_value or '').strip()
    if not value or value == LEGACY_REQUIRED_CHAT_LINK:
        return DEFAULT_PUBLIC_REQUIRED_CHAT_LINK
    if value.startswith('@'):
        return f'https://t.me/{value[1:]}'
    return value


_data_dir = _resolve_data_dir()

settings = Settings(
    bot_token=_get_required_env('BOT_TOKEN'),
    admin_ids=_parse_admin_ids(os.getenv('ADMIN_IDS', '')),
    db_path=_resolve_db_path(os.getenv('DB_PATH', 'boostora.db'), _data_dir),
    data_dir=_data_dir,
    brand_name=os.getenv('BRAND_NAME', 'Boostora').strip() or 'Boostora',
    support_username=os.getenv('SUPPORT_USERNAME', '@BoostoraBot').strip() or '@BoostoraBot',
    default_hold_hours=_parse_int_env('DEFAULT_HOLD_HOURS', 24, minimum=1, maximum=720),
    demo_hold_minutes=_parse_int_env('DEMO_HOLD_MINUTES', 3, minimum=1, maximum=1440),
    enable_demo_topup=_parse_bool(os.getenv('ENABLE_DEMO_TOPUP', '0'), default=False),
    enable_xtr_payments=_parse_bool(os.getenv('ENABLE_XTR_PAYMENTS', '1'), default=True),
    required_chat_id=_normalize_default_required_chat_ref(os.getenv('REQUIRED_CHAT_ID', DEFAULT_PUBLIC_REQUIRED_CHAT_REF)),
    required_chat_invite_link=_normalize_default_required_chat_link(os.getenv('REQUIRED_CHAT_INVITE_LINK', DEFAULT_PUBLIC_REQUIRED_CHAT_LINK)),
    run_command=os.getenv('RUN_COMMAND', 'python3 main.py').strip() or 'python3 main.py',
    promo_interval_hours=_parse_int_env('PROMO_INTERVAL_HOURS', 18, minimum=1, maximum=720),
    smart_bottom_menu=(os.getenv('SMART_BOTTOM_MENU', 'compact').strip().lower() or 'compact'),
    mini_app_url=_resolve_mini_app_url(),
    webapp_enabled=_parse_bool(os.getenv('WEBAPP_ENABLED', '1'), default=True),
    webapp_required=_parse_bool(os.getenv('WEBAPP_REQUIRED', '1'), default=True),
    webapp_host=os.getenv('WEBAPP_HOST', '0.0.0.0').strip() or '0.0.0.0',
    webapp_port=_resolve_webapp_port(),
    webapp_auth_max_age_seconds=_parse_int_env('WEBAPP_AUTH_MAX_AGE_SECONDS', 86400, minimum=60, maximum=604800),
    boostore_enabled=_parse_bool(os.getenv('BOOSTORE_ENABLED', '0'), default=False),
    boostore_api_url=os.getenv('BOOSTORE_API_URL', 'https://boostore.ru/api/v2').strip() or 'https://boostore.ru/api/v2',
    boostore_api_key=os.getenv('BOOSTORE_API_KEY', '').strip(),
    boostore_default_markup_percent=_parse_int_env('BOOSTORE_DEFAULT_MARKUP_PERCENT', 35, minimum=0, maximum=1000),
    boostore_request_timeout_seconds=_parse_int_env('BOOSTORE_REQUEST_TIMEOUT_SECONDS', 20, minimum=3, maximum=120),
    boostore_auto_sync=_parse_bool(os.getenv('BOOSTORE_AUTO_SYNC', '0'), default=False),
    boostore_auto_order_enabled=_parse_bool(os.getenv('BOOSTORE_AUTO_ORDER_ENABLED', '0'), default=False),
    provider_order_timeout_minutes=_parse_int_env('PROVIDER_ORDER_TIMEOUT_MINUTES', 20, minimum=5, maximum=1440),
    credits_per_star=_parse_int_env('CREDITS_PER_STAR', 10, minimum=1, maximum=10000),
    provider_credits_per_price_unit=_parse_int_env('PROVIDER_CREDITS_PER_PRICE_UNIT', 10, minimum=1, maximum=100000),
    max_bonus_payment_percent=_parse_int_env('MAX_BONUS_PAYMENT_PERCENT', 50, minimum=0, maximum=50),
    network_min_members=_parse_int_env('NETWORK_MIN_MEMBERS', 100, minimum=10, maximum=1000000),
    network_max_platforms_per_user=_parse_int_env('NETWORK_MAX_PLATFORMS_PER_USER', 10, minimum=1, maximum=100),
    network_base_placement_credits=_parse_int_env('NETWORK_BASE_PLACEMENT_CREDITS', 60, minimum=1, maximum=100000),
    legal_docs_required=_parse_bool(os.getenv('LEGAL_DOCS_REQUIRED', '1'), default=True),
    legal_docs_version=os.getenv('LEGAL_DOCS_VERSION', '2026-07-28-v2').strip() or '2026-07-28-v2',
    community_rules_required=_parse_bool(os.getenv('COMMUNITY_RULES_REQUIRED', '1'), default=True),
    community_rules_version=os.getenv('COMMUNITY_RULES_VERSION', '2026-07-28-v2').strip() or '2026-07-28-v2',
    engagement_standard_required_actions=_parse_int_env('ENGAGEMENT_STANDARD_REQUIRED_ACTIONS', 10, minimum=1, maximum=100),
    engagement_pro_monthly_stars=_parse_int_env('ENGAGEMENT_PRO_MONTHLY_STARS', 199, minimum=1, maximum=100000),
    engagement_obligation_due_hours=_parse_int_env('ENGAGEMENT_OBLIGATION_DUE_HOURS', 24, minimum=1, maximum=720),
    engagement_reminders_enabled=_parse_bool(os.getenv('ENGAGEMENT_REMINDERS_ENABLED', '1'), default=True),
    engagement_reminder_before_hours=_parse_int_env('ENGAGEMENT_REMINDER_BEFORE_HOURS', 6, minimum=1, maximum=168),
    engagement_overdue_blocks_standard=_parse_bool(os.getenv('ENGAGEMENT_OVERDUE_BLOCKS_STANDARD', '1'), default=True),
    engagement_admin_warnings_enabled=_parse_bool(os.getenv('ENGAGEMENT_ADMIN_WARNINGS_ENABLED', '1'), default=True),
    drop_pending_updates=_parse_bool(os.getenv('DROP_PENDING_UPDATES', '0'), default=False),
    legacy_db_restore_enabled=_parse_bool(os.getenv('LEGACY_DB_RESTORE_ENABLED', '1'), default=True),
    legacy_db_mirror_enabled=_parse_bool(os.getenv('LEGACY_DB_MIRROR_ENABLED', '0'), default=False),
    legacy_mirror_interval_seconds=_parse_int_env('LEGACY_MIRROR_INTERVAL_SECONDS', 300, minimum=30, maximum=86400),
    background_worker_interval_seconds=_parse_int_env('BACKGROUND_WORKER_INTERVAL_SECONDS', 300, minimum=30, maximum=3600),
    db_backup_interval_hours=_parse_int_env('DB_BACKUP_INTERVAL_HOURS', 12, minimum=1, maximum=168),
    db_backup_max_files=_parse_int_env('DB_BACKUP_MAX_FILES', 10, minimum=2, maximum=100),
)

if settings.smart_bottom_menu not in {'compact', 'hidden', 'full'}:
    _add_config_warning(f'SMART_BOTTOM_MENU has invalid value: {settings.smart_bottom_menu}; compact is recommended')



# Cross-setting validation. These warnings do not stop startup; they surface risky
# production combinations in the owner release center.
if settings.engagement_reminder_before_hours >= settings.engagement_obligation_due_hours:
    _add_config_warning(
        'ENGAGEMENT_REMINDER_BEFORE_HOURS should be lower than ENGAGEMENT_OBLIGATION_DUE_HOURS'
    )
if settings.boostore_enabled and not settings.boostore_api_key:
    _add_config_warning('BOOSTORE_ENABLED=1 but BOOSTORE_API_KEY is empty')
if settings.boostore_auto_order_enabled and not settings.boostore_enabled:
    _add_config_warning('BOOSTORE_AUTO_ORDER_ENABLED=1 requires BOOSTORE_ENABLED=1')
if settings.boostore_auto_order_enabled and not settings.boostore_api_key:
    _add_config_warning('BOOSTORE_AUTO_ORDER_ENABLED=1 requires BOOSTORE_API_KEY')
if settings.mini_app_url and not settings.mini_app_url.lower().startswith('https://'):
    _add_config_warning('WEBAPP_URL/MINI_APP_URL should use HTTPS for Telegram Mini App')
if settings.webapp_enabled and not settings.mini_app_url:
    _add_config_warning('WEBAPP_ENABLED=1 but WEBAPP_URL/MINI_APP_URL/PUBLIC_BASE_URL/DOMAIN is empty')
if settings.boostore_api_url and not settings.boostore_api_url.lower().startswith('https://'):
    _add_config_warning('BOOSTORE_API_URL should use HTTPS')
if settings.drop_pending_updates:
    _add_config_warning('DROP_PENDING_UPDATES=1: Telegram updates may be intentionally skipped after restart')
