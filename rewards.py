from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EngagementProduct:
    code: str
    task_type: str
    title_key: str
    description_key: str


@dataclass(frozen=True)
class EngagementPreset:
    code: str
    product_code: str
    task_type: str
    quantity: int
    title_key: str
    description_key: str


class EngagementGrowthService:
    """Marketing/UX layer for Telegram engagement products.

    This service does not create fake activity and does not bypass the old
    campaign flow. It only gives users a clear launch screen and routes them
    into existing safe campaign types: reactions, likes and comments.
    """

    PRODUCTS: tuple[EngagementProduct, ...] = (
        EngagementProduct('liker', 'post_reaction', 'engagement_product_liker_title', 'engagement_product_liker_desc'),
        EngagementProduct('commenter', 'post_comment', 'engagement_product_commenter_title', 'engagement_product_commenter_desc'),
        EngagementProduct('likes', 'post_like', 'engagement_product_likes_title', 'engagement_product_likes_desc'),
    )

    PRESETS: tuple[EngagementPreset, ...] = (
        EngagementPreset('react_10', 'liker', 'post_reaction', 10, 'engagement_preset_react_10', 'engagement_preset_react_10_desc'),
        EngagementPreset('react_50', 'liker', 'post_reaction', 50, 'engagement_preset_react_50', 'engagement_preset_react_50_desc'),
        EngagementPreset('react_100', 'liker', 'post_reaction', 100, 'engagement_preset_react_100', 'engagement_preset_react_100_desc'),
        EngagementPreset('comment_5', 'commenter', 'post_comment', 5, 'engagement_preset_comment_5', 'engagement_preset_comment_5_desc'),
        EngagementPreset('comment_20', 'commenter', 'post_comment', 20, 'engagement_preset_comment_20', 'engagement_preset_comment_20_desc'),
        EngagementPreset('comment_50', 'commenter', 'post_comment', 50, 'engagement_preset_comment_50', 'engagement_preset_comment_50_desc'),
        EngagementPreset('like_10', 'likes', 'post_like', 10, 'engagement_preset_like_10', 'engagement_preset_like_10_desc'),
        EngagementPreset('like_50', 'likes', 'post_like', 50, 'engagement_preset_like_50', 'engagement_preset_like_50_desc'),
        EngagementPreset('like_100', 'likes', 'post_like', 100, 'engagement_preset_like_100', 'engagement_preset_like_100_desc'),
    )

    @staticmethod
    def products() -> tuple[EngagementProduct, ...]:
        return EngagementGrowthService.PRODUCTS

    @staticmethod
    def presets() -> tuple[EngagementPreset, ...]:
        return EngagementGrowthService.PRESETS

    @staticmethod
    def presets_for(product_code: str) -> tuple[EngagementPreset, ...]:
        code = (product_code or '').strip()
        return tuple(item for item in EngagementGrowthService.PRESETS if item.product_code == code)

    @staticmethod
    def preset_by_code(code: str) -> EngagementPreset | None:
        safe_code = (code or '').strip()
        for item in EngagementGrowthService.PRESETS:
            if item.code == safe_code:
                return item
        return None

    @staticmethod
    def summary() -> dict[str, int | tuple[EngagementProduct, ...] | tuple[EngagementPreset, ...]]:
        products = EngagementGrowthService.products()
        presets = EngagementGrowthService.presets()
        return {
            'product_count': len(products),
            'preset_count': len(presets),
            'campaign_types': len({item.task_type for item in products}),
            'products': products,
            'presets': presets,
        }
