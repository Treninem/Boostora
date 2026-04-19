from __future__ import annotations

import os
from dataclasses import dataclass, field


def _parse_admin_ids(raw: str) -> set[int]:
    result: set[int] = set()
    for item in raw.split(','):
        item = item.strip()
        if not item:
            continue
        try:
            result.add(int(item))
        except ValueError:
            continue
    return result


@dataclass(slots=True)
class Settings:
    bot_token: str
    admin_ids: set[int] = field(default_factory=set)
    db_path: str = 'data/boostora.db'
    brand_name: str = 'Boostora'
    support_username: str = '@BoostoraBot'
    default_hold_hours: int = 24
    demo_hold_minutes: int = 3
    enable_demo_topup: bool = True
    enable_xtr_payments: bool = True
    required_chat_id: int = 0
    required_chat_invite_link: str = ''

    @classmethod
    def from_env(cls) -> 'Settings':
        token = os.getenv('BOT_TOKEN', '').strip()
        if not token:
            raise RuntimeError('BOT_TOKEN is not set')
        admin_ids = _parse_admin_ids(os.getenv('ADMIN_IDS', ''))
        db_path = os.getenv('DB_PATH', 'data/boostora.db').strip() or 'data/boostora.db'
        brand_name = os.getenv('BRAND_NAME', 'Boostora').strip() or 'Boostora'
        support_username = os.getenv('SUPPORT_USERNAME', '@BoostoraBot').strip() or '@BoostoraBot'
        default_hold_hours = int((os.getenv('DEFAULT_HOLD_HOURS', '24').strip() or '24'))
        demo_hold_minutes = int((os.getenv('DEMO_HOLD_MINUTES', '3').strip() or '3'))
        enable_demo_topup = (os.getenv('ENABLE_DEMO_TOPUP', '1').strip() or '1') not in {'0', 'false', 'False'}
        enable_xtr_payments = (os.getenv('ENABLE_XTR_PAYMENTS', '1').strip() or '1') not in {'0', 'false', 'False'}
        required_chat_id = int((os.getenv('REQUIRED_CHAT_ID', '0').strip() or '0'))
        required_chat_invite_link = os.getenv('REQUIRED_CHAT_INVITE_LINK', '').strip()
        return cls(
            bot_token=token,
            admin_ids=admin_ids,
            db_path=db_path,
            brand_name=brand_name,
            support_username=support_username,
            default_hold_hours=default_hold_hours,
            demo_hold_minutes=demo_hold_minutes,
            enable_demo_topup=enable_demo_topup,
            enable_xtr_payments=enable_xtr_payments,
            required_chat_id=required_chat_id,
            required_chat_invite_link=required_chat_invite_link,
        )
