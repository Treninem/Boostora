from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RewardCatalogItem:
    code: str
    title_key: str
    desc_key: str
    cost: int
    perk_code: str
    duration_days: int


REWARD_CATALOG: tuple[RewardCatalogItem, ...] = (
    RewardCatalogItem(
        code='vip_7d',
        title_key='shop_item_vip_7d_title',
        desc_key='shop_item_vip_7d_desc',
        cost=220,
        perk_code='vip',
        duration_days=7,
    ),
    RewardCatalogItem(
        code='vip_30d',
        title_key='shop_item_vip_30d_title',
        desc_key='shop_item_vip_30d_desc',
        cost=790,
        perk_code='vip',
        duration_days=30,
    ),
    RewardCatalogItem(
        code='fast_hold_3d',
        title_key='shop_item_fast_hold_3d_title',
        desc_key='shop_item_fast_hold_3d_desc',
        cost=160,
        perk_code='fast_hold',
        duration_days=3,
    ),
    RewardCatalogItem(
        code='priority_7d',
        title_key='shop_item_priority_7d_title',
        desc_key='shop_item_priority_7d_desc',
        cost=180,
        perk_code='priority',
        duration_days=7,
    ),
    RewardCatalogItem(
        code='ref_boost_7d',
        title_key='shop_item_ref_boost_7d_title',
        desc_key='shop_item_ref_boost_7d_desc',
        cost=190,
        perk_code='referral_boost',
        duration_days=7,
    ),
)


def list_catalog_items() -> list[RewardCatalogItem]:
    return list(REWARD_CATALOG)


def get_catalog_item(code: str) -> RewardCatalogItem | None:
    for item in REWARD_CATALOG:
        if item.code == code:
            return item
    return None
