from dataclasses import dataclass
import os

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class Settings:
    bot_token: str
    admin_ids: list[int]
    db_path: str
    brand_name: str
    support_username: str
    default_hold_hours: int
    demo_hold_minutes: int
    enable_demo_topup: bool
    enable_xtr_payments: bool
    required_chat_id: int
    required_chat_invite_link: str
    run_command: str



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


settings = Settings(
    bot_token=_get_required_env('BOT_TOKEN'),
    admin_ids=_parse_admin_ids(os.getenv('ADMIN_IDS', '')),
    db_path=os.getenv('DB_PATH', 'boostora.db').strip() or 'boostora.db',
    brand_name=os.getenv('BRAND_NAME', 'Boostora').strip() or 'Boostora',
    support_username=os.getenv('SUPPORT_USERNAME', '@BoostoraBot').strip() or '@BoostoraBot',
    default_hold_hours=int(os.getenv('DEFAULT_HOLD_HOURS', '24')),
    demo_hold_minutes=int(os.getenv('DEMO_HOLD_MINUTES', '3')),
    enable_demo_topup=_parse_bool(os.getenv('ENABLE_DEMO_TOPUP', '1'), default=True),
    enable_xtr_payments=_parse_bool(os.getenv('ENABLE_XTR_PAYMENTS', '1'), default=True),
    required_chat_id=int(os.getenv('REQUIRED_CHAT_ID', '-4998535978')),
    required_chat_invite_link=os.getenv('REQUIRED_CHAT_INVITE_LINK', '').strip(),
    run_command=os.getenv('RUN_COMMAND', 'python3 main.py').strip() or 'python3 main.py',
)
