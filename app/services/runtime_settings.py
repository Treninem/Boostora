from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app import db
from app.config import settings


@dataclass(frozen=True)
class RuntimeSettingSpec:
    key: str
    label: str
    default: int
    minimum: int
    maximum: int
    group: str


class RuntimeSettingsService:
    """Owner-editable numeric settings with safe environment fallbacks.

    Values are read from SQLite, so the owner can tune the economy and the
    advertising network without rebuilding the application. A missing table or
    value is intentionally non-fatal during first bootstrap.
    """

    SPECS: dict[str, RuntimeSettingSpec] = {
        'credits_per_star': RuntimeSettingSpec('credits_per_star', 'Кредитов за 1 Star', int(settings.credits_per_star), 1, 10000, 'economy'),
        'engagement_pro_monthly_credits': RuntimeSettingSpec('engagement_pro_monthly_credits', 'PRO на 30 дней, кредитов', int(settings.engagement_pro_monthly_stars) * int(settings.credits_per_star), 1, 10000000, 'economy'),
        'task_platform_fee_percent': RuntimeSettingSpec('task_platform_fee_percent', 'Минимальная комиссия заданий, %', 20, 5, 50, 'economy'),
        'provider_credits_per_price_unit': RuntimeSettingSpec('provider_credits_per_price_unit', 'Кредитов за единицу цены поставщика', int(settings.provider_credits_per_price_unit), 1, 100000, 'provider'),
        'provider_default_markup_percent': RuntimeSettingSpec('provider_default_markup_percent', 'Наценка новых услуг поставщика, %', int(settings.boostore_default_markup_percent), 0, 1000, 'provider'),
        'provider_order_timeout_minutes': RuntimeSettingSpec('provider_order_timeout_minutes', 'Срок ожидания оплаты, минут', int(settings.provider_order_timeout_minutes), 5, 1440, 'provider'),
        'max_bonus_payment_percent': RuntimeSettingSpec('max_bonus_payment_percent', 'Максимум оплаты бонусами, %', min(50, int(settings.max_bonus_payment_percent)), 0, 50, 'economy'),
        'network_min_members': RuntimeSettingSpec('network_min_members', 'Минимум участников площадки', int(settings.network_min_members), 10, 1000000, 'network'),
        'network_max_platforms_per_user': RuntimeSettingSpec('network_max_platforms_per_user', 'Максимум площадок пользователя', int(settings.network_max_platforms_per_user), 1, 100, 'network'),
        'network_base_placement_credits': RuntimeSettingSpec('network_base_placement_credits', 'Базовая стоимость размещения, кредитов', int(settings.network_base_placement_credits), 1, 100000, 'network'),
        'network_placement_hours': RuntimeSettingSpec('network_placement_hours', 'Минимальный срок публикации, часов', 24, 1, 720, 'network'),
        'network_bonus_percent': RuntimeSettingSpec('network_bonus_percent', 'Бонус владельцу площадки, %', 12, 0, 50, 'network'),
        'network_best_share_percent': RuntimeSettingSpec('network_best_share_percent', 'Доля лучших площадок, %', 65, 0, 100, 'network'),
        'network_rotation_share_percent': RuntimeSettingSpec('network_rotation_share_percent', 'Доля ротации, %', 25, 0, 100, 'network'),
        'network_test_share_percent': RuntimeSettingSpec('network_test_share_percent', 'Доля новых площадок, %', 10, 0, 100, 'network'),
        'network_max_daily_limit': RuntimeSettingSpec('network_max_daily_limit', 'Максимум размещений в сутки', 20, 1, 100, 'network'),
        'network_activity_days': RuntimeSettingSpec('network_activity_days', 'Период наблюдаемой активности, дней', 30, 1, 365, 'network'),
    }

    @classmethod
    def spec(cls, key: str) -> RuntimeSettingSpec | None:
        return cls.SPECS.get(str(key or '').strip())

    @classmethod
    def get_int(cls, key: str) -> int:
        spec = cls.spec(key)
        if spec is None:
            raise KeyError(key)
        try:
            row = db.fetch_one('SELECT setting_value FROM runtime_settings WHERE setting_key = ?', (spec.key,))
            if row:
                value = int(str(row['setting_value']).strip())
                return max(spec.minimum, min(spec.maximum, value))
        except Exception:
            pass
        return int(spec.default)

    @classmethod
    def set_int(cls, key: str, value: Any, *, admin_user_id: int) -> int:
        spec = cls.spec(key)
        if spec is None:
            raise ValueError('runtime_setting_unknown')
        try:
            parsed = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError('runtime_setting_invalid') from exc
        if parsed < spec.minimum or parsed > spec.maximum:
            raise ValueError('runtime_setting_out_of_range')
        db.execute(
            '''
            INSERT INTO runtime_settings (setting_key, setting_value, updated_by_user_id, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(setting_key) DO UPDATE SET
                setting_value = excluded.setting_value,
                updated_by_user_id = excluded.updated_by_user_id,
                updated_at = CURRENT_TIMESTAMP
            ''',
            (spec.key, str(parsed), int(admin_user_id)),
        )
        return parsed

    @classmethod
    def list_public_owner_settings(cls) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for spec in cls.SPECS.values():
            result.append({
                'key': spec.key,
                'label': spec.label,
                'value': cls.get_int(spec.key),
                'default': spec.default,
                'minimum': spec.minimum,
                'maximum': spec.maximum,
                'group': spec.group,
            })
        return result

    @classmethod
    def normalized_network_shares(cls) -> tuple[float, float, float]:
        values = [
            max(0, cls.get_int('network_best_share_percent')),
            max(0, cls.get_int('network_rotation_share_percent')),
            max(0, cls.get_int('network_test_share_percent')),
        ]
        total = sum(values)
        if total <= 0:
            return 0.65, 0.25, 0.10
        return tuple(value / total for value in values)  # type: ignore[return-value]
