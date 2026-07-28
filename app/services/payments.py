from __future__ import annotations

import math
import re
from collections.abc import Iterator, Mapping
from dataclasses import dataclass

from app.services.economy import INTERNAL_CURRENCY_NAME_RU
from app.services.runtime_settings import RuntimeSettingsService


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
PACK_BONUS_BPS = {stars: 0 for stars in PACK_STAR_LEVELS}


def current_credits_per_star() -> int:
    return max(1, RuntimeSettingsService.get_int('credits_per_star'))


def calculate_pack_sparks(stars: int) -> int:
    stars_value = max(int(stars), 1)
    bonus_bps = PACK_BONUS_BPS.get(stars_value, 0)
    return int(round(stars_value * current_credits_per_star() * (10000 + bonus_bps) / 10000))


def get_sparks_pack(code: str) -> SparksPack | None:
    value = str(code or '')
    if not value.startswith('spk_'):
        return None
    parts = value.split('_')
    try:
        stars = int(parts[1])
    except ValueError:
        return None
    if stars not in PACK_STAR_LEVELS:
        return None
    try:
        credits = int(parts[2]) if len(parts) >= 3 else calculate_pack_sparks(stars)
    except ValueError:
        return None
    if credits <= 0 or credits > 10_000_000:
        return None
    return SparksPack(
        code=value,
        stars=stars,
        sparks=credits,
        title=f'{credits} Искр',
        description=f'Пополнение на {credits} Искр за {stars} ⭐',
    )


def make_pack_invoice_code(pack: SparksPack) -> str:
    return f'spk_{int(pack.stars)}_{int(pack.sparks)}'


def make_custom_invoice_code(credits: int, stars: int) -> str:
    return f'c{int(credits)}s{int(stars)}'


def parse_custom_invoice_code(code: str) -> tuple[int, int] | None:
    match = re.fullmatch(r'c(\d+)s(\d+)', str(code or ''))
    if match:
        credits, stars = int(match.group(1)), int(match.group(2))
        if credits > 0 and stars > 0:
            return credits, stars
    if str(code or '').isdigit():
        credits = int(code)
        return credits, calculate_custom_stars_for_sparks(credits)
    return None


def list_sparks_packs() -> list[SparksPack]:
    return [get_sparks_pack(f'spk_{stars}') for stars in PACK_STAR_LEVELS if get_sparks_pack(f'spk_{stars}') is not None]  # type: ignore[misc]


class _DynamicPackMapping(Mapping[str, SparksPack]):
    """Compatibility mapping whose values follow the owner-editable rate."""

    def __getitem__(self, key: str) -> SparksPack:
        pack = get_sparks_pack(key)
        if pack is None:
            raise KeyError(key)
        return pack

    def __iter__(self) -> Iterator[str]:
        return iter(f'spk_{stars}' for stars in PACK_STAR_LEVELS)

    def __len__(self) -> int:
        return len(PACK_STAR_LEVELS)

    def get(self, key: str, default=None):  # noqa: ANN001
        return get_sparks_pack(key) or default

    def values(self):  # noqa: ANN201
        return list_sparks_packs()


SPARKS_PACKS: Mapping[str, SparksPack] = _DynamicPackMapping()
# Kept as a compatibility snapshot for old code; new code must call
# current_credits_per_star() when validating a user-entered amount.
BASE_SPARKS_PER_STAR = current_credits_per_star()

VIP_STARS_PLANS = {
    'vipstars7': VipStarsPlan('vipstars7', 69, 'vip_7', 'VIP 7 дней', 'Покупка VIP на 7 дней за Stars'),
    'vipstars30': VipStarsPlan('vipstars30', 199, 'vip_30', 'VIP 30 дней', 'Покупка VIP на 30 дней за Stars'),
}


def calculate_custom_stars_for_sparks(sparks: int) -> int:
    sparks_value = max(int(sparks), 1)
    return max(1, math.ceil(sparks_value / current_credits_per_star()))


def make_payload(kind: str, code: str, user_id: int) -> str:
    return f'{kind}:{code}:{user_id}'


def parse_payload(payload: str) -> tuple[str, str, int] | None:
    raw = (payload or '').strip()
    parts = raw.split(':', 2)
    if len(parts) != 3 or not parts[2].isdigit():
        return None
    return parts[0].strip(), parts[1].strip(), int(parts[2])


def make_start_parameter(kind: str, code: str, user_id: int) -> str:
    """Telegram sendInvoice start_parameter allows only A-Z a-z 0-9 _ - and 1-64 chars."""
    safe_kind = re.sub(r'[^A-Za-z0-9_-]', '-', (kind or '').strip())
    safe_code = re.sub(r'[^A-Za-z0-9_-]', '-', (code or '').strip())
    safe_user = str(int(user_id))
    raw = f'{safe_kind}-{safe_code}-{safe_user}'.strip('-')
    return raw[:64] or f'pay-{safe_user}'
