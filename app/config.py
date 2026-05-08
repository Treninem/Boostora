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
    enable_demo_topup=_parse_bool(os.getenv('ENABLE_DEMO_TOPUP', '1'), default=True),
    enable_xtr_payments=_parse_bool(os.getenv('ENABLE_XTR_PAYMENTS', '1'), default=True),
    required_chat_id=_normalize_default_required_chat_ref(os.getenv('REQUIRED_CHAT_ID', DEFAULT_PUBLIC_REQUIRED_CHAT_REF)),
    required_chat_invite_link=_normalize_default_required_chat_link(os.getenv('REQUIRED_CHAT_INVITE_LINK', DEFAULT_PUBLIC_REQUIRED_CHAT_LINK)),
    run_command=os.getenv('RUN_COMMAND', 'python3 main.py').strip() or 'python3 main.py',
    promo_interval_hours=_parse_int_env('PROMO_INTERVAL_HOURS', 18, minimum=1, maximum=720),
)
