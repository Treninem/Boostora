from __future__ import annotations

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
    "spk_425": SparksPack("spk_425", 50, 425, f"425 {INTERNAL_CURRENCY_NAME_RU}", "Пополнение внутреннего баланса"),
    "spk_900": SparksPack("spk_900", 100, 900, f"900 {INTERNAL_CURRENCY_NAME_RU}", "Пополнение внутреннего баланса"),
    "spk_2350": SparksPack("spk_2350", 250, 2350, f"2350 {INTERNAL_CURRENCY_NAME_RU}", "Пополнение внутреннего баланса"),
    "spk_4900": SparksPack("spk_4900", 500, 4900, f"4900 {INTERNAL_CURRENCY_NAME_RU}", "Пополнение внутреннего баланса"),
}

VIP_STARS_PLANS = {
    "vipstars7": VipStarsPlan("vipstars7", 79, "vip_7", "VIP 7 дней", "Покупка VIP на 7 дней за Stars"),
    "vipstars30": VipStarsPlan("vipstars30", 249, "vip_30", "VIP 30 дней", "Покупка VIP на 30 дней за Stars"),
}


def make_payload(kind: str, code: str, user_id: int) -> str:
    return f"{kind}:{code}:{user_id}"


def parse_payload(payload: str) -> tuple[str, str, int] | None:
    raw = (payload or "").strip()
    parts = raw.split(':', 2)
    if len(parts) != 3 or not parts[2].isdigit():
        return None
    return parts[0].strip(), parts[1].strip(), int(parts[2])
