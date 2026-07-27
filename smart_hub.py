from __future__ import annotations

VERIFICATION_BY_TASK = {
    'channel_subscribe': ('auto_strict', 'Авто: проверка подписки Telegram', 'Auto: Telegram membership check'),
    'chat_join': ('auto_strict', 'Авто: проверка вступления Telegram', 'Auto: Telegram membership check'),
    'bot_start': ('semi_auto', 'Полуавто: нужен старт по deep-link', 'Semi-auto: requires deep-link start'),
    'mini_app_open': ('semi_auto', 'Полуавто: нужен подписанный сигнал Mini App', 'Semi-auto: signed Mini App signal required'),
    'post_reaction': ('manual_plus', 'Ручная/событийная: нужны права и события', 'Manual/event-based: requires rights and updates'),
    'poll_vote': ('manual_plus', 'Ручная/событийная: нужны права и события', 'Manual/event-based: requires rights and updates'),
    'post_comment': ('manual_plus', 'Ручная: нужен контроль комментариев', 'Manual: comment moderation needed'),
    'post_view': ('manual', 'Ручная: Telegram не подтверждает просмотры честно', 'Manual: Telegram does not confirm views reliably'),
    'post_like': ('manual', 'Ручная: Telegram не подтверждает лайки честно', 'Manual: Telegram does not confirm likes reliably'),
    'story_view': ('manual', 'Ручная: Telegram не подтверждает просмотры сторис честно', 'Manual: Telegram does not confirm story views reliably'),
    'link_click': ('manual', 'Ручная/внешняя: нужен трекинг ссылки', 'Manual/external: requires tracked link'),
    'post_share': ('manual', 'Ручная: нужен контроль репоста', 'Manual: repost must be moderated'),
}

def verification_label(task_type: str, language: str = 'ru') -> str:
    code, ru, en = VERIFICATION_BY_TASK.get(task_type, ('manual', 'Ручная проверка', 'Manual review'))
    return ru if language == 'ru' else en

def verification_code(task_type: str) -> str:
    return VERIFICATION_BY_TASK.get(task_type, ('manual', '', ''))[0]

def speed_label(speed_index: int, language: str = 'ru') -> str:
    if speed_index < 95:
        return 'Экономно' if language == 'ru' else 'Budget'
    if speed_index < 120:
        return 'Нормально' if language == 'ru' else 'Balanced'
    if speed_index < 150:
        return 'Быстрее рынка' if language == 'ru' else 'Faster than market'
    return 'Приоритетно' if language == 'ru' else 'Priority'

def trust_tip(task_type: str, language: str = 'ru') -> str:
    code = verification_code(task_type)
    if code == 'auto_strict':
        return 'Бот может проверять выполнение почти без ручной модерации.' if language == 'ru' else 'The bot can verify this with minimal manual moderation.'
    if code == 'semi_auto':
        return 'Нужен корректный сигнал от deep-link или Mini App.' if language == 'ru' else 'A valid deep-link or Mini App signal is required.'
    if code == 'manual_plus':
        return 'Автопроверка зависит от прав бота и доступных событий Telegram.' if language == 'ru' else 'Auto-check depends on bot rights and Telegram updates.'
    return 'Для честной проверки лучше готовить ручную модерацию и понятные правила.' if language == 'ru' else 'Plan for manual moderation and clear rules for honest verification.'
