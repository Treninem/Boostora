from __future__ import annotations

import re

from dataclasses import dataclass

from app.services.economy import INTERNAL_CURRENCY_NAME_RU


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


SPARKS_PACKS = {
    "spk_360": SparksPack("spk_360", 50, 360, f"360 {INTERNAL_CURRENCY_NAME_RU}", "Пополнение внутреннего баланса"),
    "spk_760": SparksPack("spk_760", 100, 760, f"760 {INTERNAL_CURRENCY_NAME_RU}", "Пополнение внутреннего баланса"),
    "spk_2000": SparksPack("spk_2000", 250, 2000, f"2000 {INTERNAL_CURRENCY_NAME_RU}", "Пополнение внутреннего баланса"),
    "spk_4200": SparksPack("spk_4200", 500, 4200, f"4200 {INTERNAL_CURRENCY_NAME_RU}", "Пополнение внутреннего баланса"),
}

VIP_STARS_PLANS = {
    "vipstars7": VipStarsPlan("vipstars7", 69, "vip_7", "VIP 7 дней", "Покупка VIP на 7 дней за Stars"),
    "vipstars30": VipStarsPlan("vipstars30", 199, "vip_30", "VIP 30 дней", "Покупка VIP на 30 дней за Stars"),
}


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
