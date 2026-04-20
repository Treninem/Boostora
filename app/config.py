from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent


@dataclass(slots=True)
class Config:
    bot_token: str
    admin_ids: set[int]
    brand_name: str
    support_username: str
    default_language: str
    required_chat_id: int | None
    required_chat_invite_link: str
    db_path: Path

    @classmethod
    def load(cls) -> 'Config':
        load_dotenv(ROOT_DIR / '.env')
        admin_ids_raw = os.getenv('ADMIN_IDS', '')
        admin_ids = {
            int(x.strip()) for x in admin_ids_raw.split(',') if x.strip().lstrip('-').isdigit()
        }
        required_chat_id_raw = os.getenv('REQUIRED_CHAT_ID', '').strip()
        required_chat_id = int(required_chat_id_raw) if required_chat_id_raw else None
        db_path = Path(os.getenv('DB_PATH', 'data/boostora.sqlite3').strip())
        if not db_path.is_absolute():
            db_path = ROOT_DIR / db_path
        return cls(
            bot_token=os.getenv('BOT_TOKEN', '').strip(),
            admin_ids=admin_ids,
            brand_name=os.getenv('BRAND_NAME', 'Boostora').strip() or 'Boostora',
            support_username=os.getenv('SUPPORT_USERNAME', '@BoostoraBot').strip() or '@BoostoraBot',
            default_language=os.getenv('DEFAULT_LANGUAGE', 'ru').strip() or 'ru',
            required_chat_id=required_chat_id,
            required_chat_invite_link=os.getenv('REQUIRED_CHAT_INVITE_LINK', '').strip(),
            db_path=db_path,
        )
