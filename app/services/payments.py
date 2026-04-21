from __future__ import annotations

import math
import re
from dataclasses import dataclass

from app.services.economy import INTERNAL_CURRENCY_NAME_RU

BASE_SPARKS_PER_STAR = 6


@dataclass(frozen=True)
class SparksPack:
    code: str
    stars: int
    sparks: int
    title: str
    description: str


@dataclass(frozen=True)
class VipStarsPlan:
    code: str
    stars: int
    plan_code: str
    title: str
    description: str


PACK_STAR_LEVELS = (1, 5, 10, 25, 50, 100, 250)
PACK_BONUS_BPS = {
    1: 0,
    5: 600,
    10: 1000,
    25: 1300,
    50: 1650,
    100: 2100,
    250: 2650,
}


def calculate_pack_sparks(stars: int) -> int:
    stars_value = max(int(stars), 1)
    bonus_bps = PACK_BONUS_BPS.get(stars_value, 0)
    return int(round(stars_value * BASE_SPARKS_PER_STAR * (10000 + bonus_bps) / 10000))


SPARKS_PACKS = {
    f"spk_{stars}": SparksPack(
        code=f"spk_{stars}",
        stars=stars,
        sparks=calculate_pack_sparks(stars),
        title=f"{calculate_pack_sparks(stars)} {INTERNAL_CURRENCY_NAME_RU}",
        description=f"Пополнение на {calculate_pack_sparks(stars)} {INTERNAL_CURRENCY_NAME_RU} за {stars} ⭐",
    )
    for stars in PACK_STAR_LEVELS
}

VIP_STARS_PLANS = {
    "vipstars7": VipStarsPlan("vipstars7", 69, "vip_7", "VIP 7 дней", "Покупка VIP на 7 дней за Stars"),
    "vipstars30": VipStarsPlan("vipstars30", 199, "vip_30", "VIP 30 дней", "Покупка VIP на 30 дней за Stars"),
}


def calculate_custom_stars_for_sparks(sparks: int) -> int:
    sparks_value = max(int(sparks), 1)
    return max(1, math.ceil(sparks_value / BASE_SPARKS_PER_STAR))



def make_payload(kind: str, code: str, user_id: int) -> str:
    return f"{kind}:{code}:{user_id}"



def parse_payload(payload: str) -> tuple[str, str, int] | None:
    raw = (payload or "").strip()
    parts = raw.split(':', 2)
    if len(parts) != 3 or not parts[2].isdigit():
        return None
    return parts[0].strip(), parts[1].strip(), int(parts[2])



def make_start_parameter(kind: str, code: str, user_id: int) -> str:
    """Telegram sendInvoice start_parameter allows only A-Z a-z 0-9 _ - and 1-64 chars."""
    safe_kind = re.sub(r"[^A-Za-z0-9_-]", "-", (kind or "").strip())
    safe_code = re.sub(r"[^A-Za-z0-9_-]", "-", (code or "").strip())
    safe_user = str(int(user_id))
    raw = f"{safe_kind}-{safe_code}-{safe_user}".strip("-")
    return raw[:64] or f"pay-{safe_user}"
