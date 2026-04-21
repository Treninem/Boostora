from dataclasses import dataclass
from pathlib import Path
import os

from dotenv import load_dotenv


load_dotenv()

LEGACY_REQUIRED_CHAT_ID = '-4998535978'
LEGACY_REQUIRED_CHAT_LINK = 'https://t.me/+I8t5mJaHGh80ODJi'
DEFAULT_PUBLIC_REQUIRED_CHAT_REF = '@Boostorachat'
DEFAULT_PUBLIC_REQUIRED_CHAT_LINK = 'https://t.me/Boostorachat'


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


def _parse_admin_ids(raw_value: str) -> list[int]:
    ids: list[int] = []
    for chunk in raw_value.split(','):
        value = chunk.strip()
        if not value:
            continue
        ids.append(int(value))
    return ids


def _parse_bool(raw_value: str, default: bool = False) -> bool:
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {'1', 'true', 'yes', 'on'}


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


def _is_writable_dir(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / '.boostora_write_test'
        probe.write_text('ok', encoding='utf-8')
        probe.unlink(missing_ok=True)
        return True
    except Exception:
        return False


def _resolve_data_dir() -> str:
    explicit = os.getenv('BOT_DATA_DIR', '').strip()
    if explicit:
        explicit_path = Path(explicit).expanduser()
        explicit_path.mkdir(parents=True, exist_ok=True)
        return str(explicit_path)

    home_data = Path.home() / '.boostora-data'
    candidates = [
        Path('/data'),
        Path('/storage'),
        Path('/var/data/boostora'),
        home_data,
    ]

    for candidate in candidates:
        if candidate.exists() and _is_writable_dir(candidate):
            return str(candidate)

    if _is_writable_dir(home_data):
        return str(home_data)

    fallback = Path('storage')
    fallback.mkdir(parents=True, exist_ok=True)
    return str(fallback)


def _resolve_db_path(raw_value: str, data_dir: str) -> str:
    value = (raw_value or '').strip() or 'boostora.db'
    path = Path(value).expanduser()
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
    default_hold_hours=int(os.getenv('DEFAULT_HOLD_HOURS', '24')),
    demo_hold_minutes=int(os.getenv('DEMO_HOLD_MINUTES', '3')),
    enable_demo_topup=_parse_bool(os.getenv('ENABLE_DEMO_TOPUP', '1'), default=True),
    enable_xtr_payments=_parse_bool(os.getenv('ENABLE_XTR_PAYMENTS', '1'), default=True),
    required_chat_id=_normalize_default_required_chat_ref(os.getenv('REQUIRED_CHAT_ID', DEFAULT_PUBLIC_REQUIRED_CHAT_REF)),
    required_chat_invite_link=_normalize_default_required_chat_link(os.getenv('REQUIRED_CHAT_INVITE_LINK', DEFAULT_PUBLIC_REQUIRED_CHAT_LINK)),
    run_command=os.getenv('RUN_COMMAND', 'python3 main.py').strip() or 'python3 main.py',
    promo_interval_hours=int(os.getenv('PROMO_INTERVAL_HOURS', '18')),
)
