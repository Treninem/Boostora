import math

SIGNUP_BONUS_SPARKS = 300
INTERNAL_CURRENCY_CODE = "BST"
INTERNAL_CURRENCY_NAME_RU = "Искры"

# Экономика:
# - заказчик может ставить цену сам, но не ниже базовой рекомендуемой цены
# - при повышении цены 80% добавки уходит исполнителю, остаток сервису
# - объёмная скидка применяется только к базовой цене, а не к добровольной надбавке
# - v2.0.3 добавляет понятные ориентиры: минимум / рекомендовано / быстро / приоритет
TASK_CATALOG = {
    "channel_subscribe": {"client_floor_price": 26, "performer_reward": 18, "title": "Подписка на канал", "label_key": "campaign_task_type_channel_subscribe"},
    "chat_join": {"client_floor_price": 23, "performer_reward": 16, "title": "Вступление в чат", "label_key": "campaign_task_type_chat_join"},
    "post_view": {"client_floor_price": 6, "performer_reward": 3, "title": "Открыть публикацию", "label_key": "campaign_task_type_post_view"},
    "post_like": {"client_floor_price": 9, "performer_reward": 6, "title": "Реакция 👍", "label_key": "campaign_task_type_post_like"},
    "post_reaction": {"client_floor_price": 8, "performer_reward": 5, "title": "Реакция на пост", "label_key": "campaign_task_type_post_reaction"},
    "story_view": {"client_floor_price": 8, "performer_reward": 5, "title": "Просмотр истории", "label_key": "campaign_task_type_story_view"},
    "link_click": {"client_floor_price": 8, "performer_reward": 5, "title": "Открыть ссылку", "label_key": "campaign_task_type_link_click"},
    "post_share": {"client_floor_price": 16, "performer_reward": 11, "title": "Репост поста", "label_key": "campaign_task_type_post_share"},
    "post_comment": {"client_floor_price": 20, "performer_reward": 14, "title": "Комментарий под постом", "label_key": "campaign_task_type_post_comment"},
    "poll_vote": {"client_floor_price": 10, "performer_reward": 7, "title": "Голос в опросе", "label_key": "campaign_task_type_poll_vote"},
    "chat_message": {"client_floor_price": 16, "performer_reward": 11, "title": "Сообщение в чате", "label_key": "campaign_task_type_chat_message"},
    "join_request": {"client_floor_price": 18, "performer_reward": 12, "title": "Заявка на вступление", "label_key": "campaign_task_type_join_request"},
}

DISCOUNT_TIERS = (
    (1000, 7),
    (500, 5),
    (250, 4),
    (100, 3),
    (50, 2),
    (25, 1),
)

CUSTOM_PRICE_PERFORMER_SHARE = 0.8
MIN_SERVICE_FEE = 2

# Эти задания удалены: без интеграции стороннего сервиса Boostora не может
# честно подтвердить запуск чужого бота или открытие чужой Mini App.
RETIRED_TASK_TYPES = frozenset({'bot_start', 'mini_app_open'})

RECOMMENDED_PRICE_EXTRA_PERCENT = 18
FAST_PRICE_EXTRA_PERCENT = 38
PRIORITY_PRICE_EXTRA_PERCENT = 70


def _round_up_to_step(value: int, step: int = 1) -> int:
    if step <= 1:
        return int(value)
    return int(math.ceil(value / step) * step)


def get_discount_percent(quantity: int) -> int:
    for threshold, percent in DISCOUNT_TIERS:
        if quantity >= threshold:
            return percent
    return 0


def supported_task_types() -> tuple[str, ...]:
    return tuple(TASK_CATALOG.keys())


# New campaigns are restricted to actions that Boostora can tie to a concrete
# Telegram user. Legacy story/share campaigns stay readable for compatibility.
def creatable_task_types() -> tuple[str, ...]:
    return (
        "channel_subscribe", "chat_join", "join_request", "post_reaction",
        "post_like", "post_comment", "chat_message", "poll_vote",
        "post_view", "link_click",
    )


def task_meta(task_type: str) -> dict[str, int | str]:
    if task_type not in TASK_CATALOG:
        raise KeyError(task_type)
    return TASK_CATALOG[task_type]


def _task_platform_fee_percent() -> int:
    # SQLite owner setting keeps the commission adjustable without a deploy.
    # Lazy import avoids a module cycle during configuration bootstrap.
    try:
        from app.services.runtime_settings import RuntimeSettingsService
        return max(5, min(50, int(RuntimeSettingsService.get_int('task_platform_fee_percent'))))
    except Exception:
        return 20


def _discounted_floor(base_floor: int, quantity: int, reward_floor: int) -> tuple[int, int]:
    discount_percent = get_discount_percent(quantity)
    discounted_floor = math.floor(base_floor * (100 - discount_percent) / 100)
    fee_percent = _task_platform_fee_percent()
    # The floor always covers the performer reward and the configured platform
    # commission. This prevents task issuance from creating unbacked credits.
    percent_floor = math.ceil(reward_floor / max(0.01, 1.0 - fee_percent / 100.0))
    discounted_floor = max(reward_floor + MIN_SERVICE_FEE, percent_floor, discounted_floor)
    return discounted_floor, discount_percent


def recommend_unit_prices(task_type: str, quantity: int) -> dict[str, int]:
    """Возвращает честные ориентиры цены за 1 выполнение.

    Функция не пишет в БД и не зависит от текущих данных пользователя, поэтому
    безопасна для старых баз на Bothost. Минимум остаётся обязательным полом,
    а рекомендации помогают заказчику понять, сколько поставить для скорости.
    """
    if task_type not in TASK_CATALOG:
        raise ValueError("unknown task type")
    if quantity <= 0:
        raise ValueError("quantity must be positive")
    meta = TASK_CATALOG[task_type]
    base_floor = int(meta["client_floor_price"])
    base_reward = int(meta["performer_reward"])
    floor_price, discount_percent = _discounted_floor(base_floor, quantity, base_reward)
    step = 5 if floor_price >= 50 else 1
    recommended = max(
        floor_price + 1,
        _round_up_to_step(math.ceil(floor_price * (100 + RECOMMENDED_PRICE_EXTRA_PERCENT) / 100), step),
    )
    fast = max(
        recommended + 1,
        _round_up_to_step(math.ceil(floor_price * (100 + FAST_PRICE_EXTRA_PERCENT) / 100), step),
    )
    priority = max(
        fast + 1,
        _round_up_to_step(math.ceil(floor_price * (100 + PRIORITY_PRICE_EXTRA_PERCENT) / 100), step),
    )
    return {
        "client_floor_price": floor_price,
        "base_client_floor_price": base_floor,
        "performer_floor_reward": base_reward,
        "discount_percent": discount_percent,
        "recommended_unit_price": recommended,
        "fast_unit_price": fast,
        "priority_unit_price": priority,
    }


def price_position_percent(unit_price: int, floor_price: int, recommended_unit_price: int, priority_unit_price: int) -> int:
    if unit_price <= floor_price:
        return 0
    scale = max(priority_unit_price - floor_price, 1)
    return max(0, min(100, round((unit_price - floor_price) * 100 / scale)))


def completion_speed_explanation(speed_index: int, unit_price: int, recommended_unit_price: int, language: str = "ru") -> str:
    below_recommended = unit_price < recommended_unit_price
    if speed_index < 105 or below_recommended:
        return (
            "Цена близка к минимуму: задание экономное, но исполнители могут выбирать его медленнее."
            if language == "ru" else
            "The price is close to the minimum: budget-friendly, but performers may choose it slower."
        )
    if speed_index < 135:
        return (
            "Цена выглядит сбалансированной: обычно это лучший вариант без лишней переплаты."
            if language == "ru" else
            "The price looks balanced: usually the best option without overpaying."
        )
    if speed_index < 170:
        return (
            "Повышенная цена делает задание заметнее для исполнителей и должна ускорить выполнение."
            if language == "ru" else
            "The higher price makes the task more attractive and should speed up completion."
        )
    return (
        "Приоритетная цена: подходит, когда важнее скорость, чем экономия бюджета."
        if language == "ru" else
        "Priority price: use it when speed matters more than saving budget."
    )


def calculate_campaign_pricing(task_type: str, quantity: int, selected_unit_price: int | None = None) -> dict[str, int | float]:
    if task_type not in TASK_CATALOG:
        raise ValueError("unknown task type")
    if quantity <= 0:
        raise ValueError("quantity must be positive")
    meta = TASK_CATALOG[task_type]
    base_floor = int(meta["client_floor_price"])
    base_reward = int(meta["performer_reward"])
    floor_price, discount_percent = _discounted_floor(base_floor, quantity, base_reward)
    advisory = recommend_unit_prices(task_type, quantity)

    if selected_unit_price is None:
        unit_price = floor_price
    else:
        if selected_unit_price < floor_price:
            raise ValueError("selected price below floor")
        unit_price = int(selected_unit_price)

    extra_price = max(unit_price - floor_price, 0)
    fee_percent = _task_platform_fee_percent()
    performer_extra_share = min(CUSTOM_PRICE_PERFORMER_SHARE, (100 - fee_percent) / 100.0)
    performer_bonus = math.floor(extra_price * performer_extra_share)
    reward_unit = base_reward + performer_bonus
    minimum_fee = max(MIN_SERVICE_FEE, math.ceil(unit_price * fee_percent / 100.0))
    service_fee_unit = max(unit_price - reward_unit, minimum_fee)
    service_fee_unit = min(unit_price, service_fee_unit)
    reward_unit = max(0, unit_price - service_fee_unit)
    reward_budget_total = reward_unit * quantity
    total_charge = unit_price * quantity
    service_fee_total = total_charge - reward_budget_total
    speed_index = round((reward_unit / max(base_reward, 1)) * 100)
    price_position = price_position_percent(
        unit_price,
        floor_price,
        int(advisory["recommended_unit_price"]),
        int(advisory["priority_unit_price"]),
    )
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
        "platform_fee_percent": fee_percent,
        "budget_total": total_charge,
        "speed_index": speed_index,
        "price_position_percent": price_position,
        "recommended_unit_price": int(advisory["recommended_unit_price"]),
        "fast_unit_price": int(advisory["fast_unit_price"]),
        "priority_unit_price": int(advisory["priority_unit_price"]),
    }
