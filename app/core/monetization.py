
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TopupPack:
    code: str
    xtr_amount: int
    credit_amount: int
    bonus_percent: int
    title_key: str
    desc_key: str


@dataclass(frozen=True, slots=True)
class VipPack:
    code: str
    xtr_amount: int
    duration_days: int
    title_key: str
    desc_key: str


TOPUP_PACKS: tuple[TopupPack, ...] = (
    TopupPack('starter', 100, 1200, 20, 'topup_pack_starter_title', 'topup_pack_starter_desc'),
    TopupPack('growth', 250, 3250, 30, 'topup_pack_growth_title', 'topup_pack_growth_desc'),
    TopupPack('scale', 500, 7000, 40, 'topup_pack_scale_title', 'topup_pack_scale_desc'),
)

VIP_PACKS: tuple[VipPack, ...] = (
    VipPack('vip30', 90, 30, 'vip_pack_30_title', 'vip_pack_30_desc'),
    VipPack('vip90', 240, 90, 'vip_pack_90_title', 'vip_pack_90_desc'),
)


def get_topup_pack(code: str) -> TopupPack | None:
    for item in TOPUP_PACKS:
        if item.code == code:
            return item
    return None


def get_vip_pack(code: str) -> VipPack | None:
    for item in VIP_PACKS:
        if item.code == code:
            return item
    return None
