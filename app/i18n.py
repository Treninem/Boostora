from __future__ import annotations

SUPPORTED_LANGUAGES = {
    'ru': 'Русский',
    'en': 'English',
    'de': 'Deutsch',
    'es': 'Español',
    'pt': 'Português',
    'tr': 'Türkçe',
}

ROLE_EARNER = 'earner'
ROLE_ADVERTISER = 'advertiser'

BASE_RU = {
    'choose_language': '<b>Выберите язык</b>',
    'welcome': '<b>Добро пожаловать в {brand}</b>\n\nПлатформа взаимного продвижения и заданий в Telegram.',
    'choose_role': '<b>Выберите роль</b>',
    'role_earner': 'Исполнитель',
    'role_advertiser': 'Заказчик',
    'menu_earner': '<b>Главное меню исполнителя</b>\n\nВыберите нужный раздел ниже.',
    'menu_advertiser': '<b>Главное меню заказчика</b>\n\nВыберите нужный раздел ниже.',
    'profile': 'Профиль',
    'tasks': 'Задания',
    'wallet': 'Кошелёк',
    'rewards': 'Награды',
    'campaigns': 'Кампании',
    'analytics': 'Аналитика',
    'topup': 'Пополнение',
    'support': 'Поддержка',
    'admin': 'Админка',
    'back': 'Назад',
    'to_menu': 'В меню',
    'refresh': 'Обновить',
    'check_subscription': 'Проверить подписку',
    'join_chat': 'Открыть чат',
    'subscription_required': '<b>Нужна подписка на обязательный чат</b>\n\nСначала вступите в чат, затем нажмите кнопку проверки.',
    'subscription_ok': 'Подписка подтверждена.',
    'profile_text': '<b>Профиль</b>\n\nID: <code>{user_id}</code>\nЯзык: {language}\nРоль: {role}\nСтатус: {tier}\nВыполнено заданий: {completed}',
    'wallet_text': '<b>Кошелёк</b>\n\nДоступно: <b>{available}</b>\nВ холде: <b>{hold}</b>\nВсего заработано: <b>{earned}</b>',
    'rewards_text': '<b>Награды</b>\n\nВ этой версии доступны внутренняя валюта, VIP и базовая витрина наград.',
    'tasks_text': '<b>Доступные задания</b>\n\nВыберите задание ниже.',
    'no_tasks': 'Пока нет доступных заданий.',
    'take_task': 'Взять',
    'open_target': 'Открыть цель',
    'complete_task': 'Завершить',
    'task_taken': 'Задание взято. После выполнения откройте цель и нажмите «Завершить».',
    'task_completed': 'Задание завершено. Награда зачислена.',
    'already_taken': 'Это задание уже взято вами.',
    'task_card': '<b>Задание #{id}</b>\n\n{title}\nНаграда: <b>+{reward}</b>',
    'campaigns_text': '<b>Мои кампании</b>',
    'no_campaigns': 'У вас пока нет кампаний.',
    'create_demo_campaign': 'Создать демо-кампанию',
    'campaign_created': 'Демо-кампания создана.',
    'campaign_card': '<b>Кампания #{id}</b>\n\n{title}\nНаграда: <b>{reward}</b>\nВыполнено: <b>{completed}/{total}</b>',
    'analytics_text': '<b>Аналитика</b>\n\nКампаний: <b>{campaigns}</b>\nВсего заданий: <b>{tasks}</b>\nВыполнено: <b>{completed}</b>',
    'topup_text': '<b>Пополнение</b>\n\nДля прод-версии подключается Telegram Stars.\nСейчас доступен демо-режим пополнения.',
    'topup_demo': 'Пополнить демо-баланс +500',
    'topup_done': 'Баланс пополнен на 500.',
    'support_text': '<b>Поддержка</b>\n\nПо всем вопросам: {support}',
    'admin_text': '<b>Админка</b>\n\nПользователей: <b>{users}</b>\nКампаний: <b>{campaigns}</b>\nВзятых заданий: <b>{claims}</b>',
    'access_denied': 'Доступ запрещён.',
    'language_saved': 'Язык сохранён.',
    'role_saved': 'Роль сохранена.',
    'unknown': 'Неизвестно',
    'tier_new': 'Новый',
    'tier_verified': 'Проверенный',
    'earner_label': 'Исполнитель',
    'advertiser_label': 'Заказчик',
    'menu_hint': 'Нажимайте кнопки ниже — текущее сообщение будет обновляться без лишнего спама.',
}

# Simple localized variants for supported languages.
STRINGS = {
    'ru': BASE_RU,
    'en': {
        **BASE_RU,
        'choose_language': '<b>Choose language</b>',
        'welcome': '<b>Welcome to {brand}</b>\n\nA Telegram growth and task platform.',
        'choose_role': '<b>Choose your role</b>',
        'role_earner': 'Earner', 'role_advertiser': 'Advertiser',
        'menu_earner': '<b>Earner main menu</b>\n\nChoose a section below.',
        'menu_advertiser': '<b>Advertiser main menu</b>\n\nChoose a section below.',
        'profile': 'Profile', 'tasks': 'Tasks', 'wallet': 'Wallet', 'rewards': 'Rewards', 'campaigns': 'Campaigns',
        'analytics': 'Analytics', 'topup': 'Top up', 'support': 'Support', 'admin': 'Admin',
        'back': 'Back', 'to_menu': 'Menu', 'refresh': 'Refresh',
        'check_subscription': 'Check subscription', 'join_chat': 'Open chat',
        'subscription_required': '<b>Subscription required</b>\n\nJoin the mandatory chat first, then tap the check button.',
        'subscription_ok': 'Subscription confirmed.',
        'profile_text': '<b>Profile</b>\n\nID: <code>{user_id}</code>\nLanguage: {language}\nRole: {role}\nTier: {tier}\nCompleted tasks: {completed}',
        'wallet_text': '<b>Wallet</b>\n\nAvailable: <b>{available}</b>\nOn hold: <b>{hold}</b>\nTotal earned: <b>{earned}</b>',
        'rewards_text': '<b>Rewards</b>\n\nThis build includes internal currency, VIP and a basic rewards showcase.',
        'tasks_text': '<b>Available tasks</b>\n\nChoose a task below.',
        'no_tasks': 'No tasks available right now.', 'take_task': 'Take', 'open_target': 'Open target', 'complete_task': 'Complete',
        'task_taken': 'Task taken. Open the target and tap Complete after finishing.',
        'task_completed': 'Task completed. Reward credited.', 'already_taken': 'You already took this task.',
        'task_card': '<b>Task #{id}</b>\n\n{title}\nReward: <b>+{reward}</b>',
        'campaigns_text': '<b>My campaigns</b>', 'no_campaigns': 'You have no campaigns yet.',
        'create_demo_campaign': 'Create demo campaign', 'campaign_created': 'Demo campaign created.',
        'campaign_card': '<b>Campaign #{id}</b>\n\n{title}\nReward: <b>{reward}</b>\nCompleted: <b>{completed}/{total}</b>',
        'analytics_text': '<b>Analytics</b>\n\nCampaigns: <b>{campaigns}</b>\nTotal tasks: <b>{tasks}</b>\nCompleted: <b>{completed}</b>',
        'topup_text': '<b>Top up</b>\n\nTelegram Stars can be connected in production.\nDemo balance top up is available now.',
        'topup_demo': 'Add demo balance +500', 'topup_done': 'Balance topped up by 500.',
        'support_text': '<b>Support</b>\n\nContact: {support}',
        'admin_text': '<b>Admin panel</b>\n\nUsers: <b>{users}</b>\nCampaigns: <b>{campaigns}</b>\nTask claims: <b>{claims}</b>',
        'access_denied': 'Access denied.', 'language_saved': 'Language saved.', 'role_saved': 'Role saved.',
        'unknown': 'Unknown', 'tier_new': 'New', 'tier_verified': 'Verified', 'earner_label': 'Earner', 'advertiser_label': 'Advertiser',
        'menu_hint': 'Use the buttons below — the current message will update without extra spam.',
    },
    'de': {**BASE_RU}, 'es': {**BASE_RU}, 'pt': {**BASE_RU}, 'tr': {**BASE_RU},
}


def normalize_locale(locale: str | None, fallback: str = 'en') -> str:
    if locale in SUPPORTED_LANGUAGES:
        return str(locale)
    return fallback if fallback in SUPPORTED_LANGUAGES else 'en'


def t(locale: str, key: str, **kwargs) -> str:
    lang = normalize_locale(locale)
    template = STRINGS.get(lang, STRINGS['en']).get(key, STRINGS['en'].get(key, key))
    return template.format(**kwargs)


def role_label(locale: str, role: str | None) -> str:
    if role == ROLE_EARNER:
        return t(locale, 'earner_label')
    if role == ROLE_ADVERTISER:
        return t(locale, 'advertiser_label')
    return t(locale, 'unknown')


def tier_label(locale: str, tier: str | None) -> str:
    if tier == 'verified':
        return t(locale, 'tier_verified')
    return t(locale, 'tier_new')
