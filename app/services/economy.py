import math

SIGNUP_BONUS_SPARKS = 320
INTERNAL_CURRENCY_CODE = "BST"
INTERNAL_CURRENCY_NAME_RU = "Искры"

# Экономика:
# - заказчик может ставить цену сам, но не ниже базовой рекомендуемой цены
# - при повышении цены 75% добавки уходит исполнителю, 25% сервису
# - объёмная скидка применяется только к базовой цене, а не к добровольной надбавке
TASK_CATALOG = {
    "channel_subscribe": {"client_floor_price": 18, "performer_reward": 13, "title": "Подписка на канал", "label_key": "campaign_task_type_channel_subscribe"},
    "chat_join": {"client_floor_price": 16, "performer_reward": 11, "title": "Вступление в чат", "label_key": "campaign_task_type_chat_join"},
    "post_view": {"client_floor_price": 5, "performer_reward": 3, "title": "Просмотр поста", "label_key": "campaign_task_type_post_view"},
    "bot_start": {"client_floor_price": 15, "performer_reward": 10, "title": "Запуск бота", "label_key": "campaign_task_type_bot_start"},
    "mini_app_open": {"client_floor_price": 22, "performer_reward": 16, "title": "Открытие Mini App", "label_key": "campaign_task_type_mini_app_open"},
    "post_like": {"client_floor_price": 6, "performer_reward": 4, "title": "Лайк поста", "label_key": "campaign_task_type_post_like"},
    "post_reaction": {"client_floor_price": 5, "performer_reward": 3, "title": "Реакция на пост", "label_key": "campaign_task_type_post_reaction"},
    "story_view": {"client_floor_price": 5, "performer_reward": 3, "title": "Просмотр истории", "label_key": "campaign_task_type_story_view"},
    "link_click": {"client_floor_price": 8, "performer_reward": 5, "title": "Переход по ссылке", "label_key": "campaign_task_type_link_click"},
    "post_share": {"client_floor_price": 12, "performer_reward": 8, "title": "Репост поста", "label_key": "campaign_task_type_post_share"},
    "post_comment": {"client_floor_price": 14, "performer_reward": 10, "title": "Комментарий под постом", "label_key": "campaign_task_type_post_comment"},
    "poll_vote": {"client_floor_price": 7, "performer_reward": 5, "title": "Голос в опросе", "label_key": "campaign_task_type_poll_vote"},
}

DISCOUNT_TIERS = (
    (1000, 8),
    (500, 6),
    (250, 4),
    (100, 3),
    (50, 2),
    (25, 1),
)

CUSTOM_PRICE_PERFORMER_SHARE = 0.75
MIN_SERVICE_FEE = 1


def get_discount_percent(quantity: int) -> int:
    for threshold, percent in DISCOUNT_TIERS:
        if quantity >= threshold:
            return percent
    return 0


def supported_task_types() -> tuple[str, ...]:
    return tuple(TASK_CATALOG.keys())


def task_meta(task_type: str) -> dict[str, int | str]:
    if task_type not in TASK_CATALOG:
        raise KeyError(task_type)
    return TASK_CATALOG[task_type]


def _discounted_floor(base_floor: int, quantity: int, reward_floor: int) -> tuple[int, int]:
    discount_percent = get_discount_percent(quantity)
    discounted_floor = math.floor(base_floor * (100 - discount_percent) / 100)
    discounted_floor = max(reward_floor + MIN_SERVICE_FEE, discounted_floor)
    return discounted_floor, discount_percent


def calculate_campaign_pricing(task_type: str, quantity: int, selected_unit_price: int | None = None) -> dict[str, int | float]:
    if task_type not in TASK_CATALOG:
        raise ValueError("unknown task type")
    if quantity <= 0:
        raise ValueError("quantity must be positive")
    meta = TASK_CATALOG[task_type]
    base_floor = int(meta["client_floor_price"])
    base_reward = int(meta["performer_reward"])
    floor_price, discount_percent = _discounted_floor(base_floor, quantity, base_reward)

    if selected_unit_price is None:
        unit_price = floor_price
    else:
        if selected_unit_price < floor_price:
            raise ValueError("selected price below floor")
        unit_price = int(selected_unit_price)

    extra_price = max(unit_price - floor_price, 0)
    performer_bonus = math.floor(extra_price * CUSTOM_PRICE_PERFORMER_SHARE)
    reward_unit = base_reward + performer_bonus
    service_fee_unit = max(unit_price - reward_unit, MIN_SERVICE_FEE)
    if reward_unit + service_fee_unit > unit_price:
        service_fee_unit = max(unit_price - reward_unit, 0)
    reward_budget_total = reward_unit * quantity
    total_charge = unit_price * quantity
    service_fee_total = total_charge - reward_budget_total
    speed_index = round((reward_unit / max(base_reward, 1)) * 100)
    return {
        "task_type": task_type,
        "discount_percent": discount_percent,
        "client_unit_price": unit_price,
        "client_floor_price": floor_price,
        "base_client_floor_price": base_floor,
        "performer_reward": reward_unit,
        "performer_floor_reward": base_reward,
        "quantity": quantity,
        "reward_budget_total": reward_budget_total,
        "service_fee_total": service_fee_total,
        "service_fee_unit": service_fee_unit,
        "budget_total": total_charge,
        "speed_index": speed_index,
    }
