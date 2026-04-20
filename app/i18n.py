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

CURRENCY = {
    'ru': 'Искры',
    'en': 'Sparks',
    'de': 'Funken',
    'es': 'Chispas',
    'pt': 'Faíscas',
    'tr': 'Kıvılcım',
}

STRINGS = {
    'ru': {
        'choose_language': '<b>Выберите язык</b>',
        'welcome': '<b>Добро пожаловать в {brand}</b>\n\nПлатформа взаимного продвижения в Telegram.',
        'choose_role': '<b>Выберите роль</b>',
        'role_earner': 'Исполнитель',
        'role_advertiser': 'Заказчик',
        'menu_earner': '<b>Главное меню исполнителя</b>',
        'menu_advertiser': '<b>Главное меню заказчика</b>',
        'menu_hint': 'Текущее сообщение обновляется, старые кнопки не остаются активными.',
        'profile': 'Профиль', 'wallet': 'Кошелёк', 'tasks': 'Задания', 'rewards': 'Награды',
        'campaigns': 'Кампании', 'analytics': 'Аналитика', 'topup': 'Пополнение', 'support': 'Поддержка', 'admin': 'Админка',
        'back': 'Назад', 'refresh': 'Обновить', 'to_menu': 'В меню',
        'subscription_required': '<b>Нужна подписка на обязательный чат</b>\n\nСначала вступите в чат, затем нажмите кнопку проверки.',
        'subscription_check': 'Проверить подписку', 'join_chat': 'Открыть чат',
        'subscription_ok': 'Подписка подтверждена.',
        'subscription_cannot_verify': 'Не удалось проверить подписку. Добавьте бота в обязательный чат и лучше дайте ему админку.',
        'profile_text': '<b>Профиль</b>\n\nID: <code>{user_id}</code>\nЯзык: {language}\nРоль: {role}\nСтатус: {tier}\nВыполнено заданий: {completed}',
        'wallet_text': '<b>Кошелёк</b>\n\nДоступно: <b>{available}</b> {currency}\nВ холде: <b>{hold}</b> {currency}\nВсего заработано: <b>{earned}</b> {currency}',
        'tasks_text': '<b>Доступные задания</b>\n\nВыберите задание ниже.',
        'no_tasks': 'Пока нет доступных заданий.',
        'task_card': '<b>Задание #{id}</b>\n\n{title}\nНаграда: <b>+{reward}</b> {currency}',
        'take_task': 'Взять', 'open_target': 'Открыть цель', 'complete_task': 'Завершить',
        'task_taken': 'Задание взято. После выполнения откройте цель и нажмите «Завершить».',
        'task_completed': 'Задание завершено. Награда зачислена.',
        'already_taken': 'Это задание уже взято вами.',
        'rewards_text': '<b>Награды</b>\n\nЗдесь будут VIP, витрина наград и улучшения аккаунта.',
        'campaigns_text': '<b>Мои кампании</b>',
        'no_campaigns': 'У вас пока нет кампаний.',
        'create_demo_campaign': 'Создать демо-кампанию', 'campaign_created': 'Демо-кампания создана.',
        'campaign_card': '<b>Кампания #{id}</b>\n\n{title}\nНаграда: <b>{reward}</b> {currency}\nВыполнено: <b>{completed}/{total}</b>',
        'analytics_text': '<b>Аналитика</b>\n\nКампаний: <b>{campaigns}</b>\nВсего заданий: <b>{tasks}</b>\nВыполнено: <b>{completed}</b>',
        'topup_text': '<b>Пополнение</b>\n\nВ этой версии доступно демо-пополнение рекламного баланса.',
        'topup_demo': 'Пополнить демо-баланс +500', 'topup_done': 'Баланс пополнен на 500.',
        'support_text': '<b>Поддержка</b>\n\nПо всем вопросам: {support}',
        'admin_text': '<b>Админка</b>\n\nПользователей: <b>{users}</b>\nКампаний: <b>{campaigns}</b>\nВзятых заданий: <b>{claims}</b>',
        'access_denied': 'Доступ запрещён.', 'language_saved': 'Язык сохранён.', 'role_saved': 'Роль сохранена.',
        'unknown': 'Неизвестно', 'tier_new': 'Новый', 'tier_verified': 'Проверенный',
        'earner_label': 'Исполнитель', 'advertiser_label': 'Заказчик',
        'chat_opened': 'Откройте чат, вступите в него и вернитесь к проверке.',
    },
    'en': {
        'choose_language': '<b>Choose language</b>',
        'welcome': '<b>Welcome to {brand}</b>\n\nA Telegram growth platform.',
        'choose_role': '<b>Choose your role</b>',
        'role_earner': 'Earner', 'role_advertiser': 'Advertiser',
        'menu_earner': '<b>Earner main menu</b>', 'menu_advertiser': '<b>Advertiser main menu</b>',
        'menu_hint': 'The current message updates, old buttons do not stay active.',
        'profile': 'Profile', 'wallet': 'Wallet', 'tasks': 'Tasks', 'rewards': 'Rewards',
        'campaigns': 'Campaigns', 'analytics': 'Analytics', 'topup': 'Top up', 'support': 'Support', 'admin': 'Admin',
        'back': 'Back', 'refresh': 'Refresh', 'to_menu': 'Menu',
        'subscription_required': '<b>Subscription required</b>\n\nJoin the required chat first, then tap the check button.',
        'subscription_check': 'Check subscription', 'join_chat': 'Open chat',
        'subscription_ok': 'Subscription confirmed.',
        'subscription_cannot_verify': 'Could not verify the subscription. Add the bot to the required chat and preferably make it an admin.',
        'profile_text': '<b>Profile</b>\n\nID: <code>{user_id}</code>\nLanguage: {language}\nRole: {role}\nTier: {tier}\nCompleted tasks: {completed}',
        'wallet_text': '<b>Wallet</b>\n\nAvailable: <b>{available}</b> {currency}\nOn hold: <b>{hold}</b> {currency}\nTotal earned: <b>{earned}</b> {currency}',
        'tasks_text': '<b>Available tasks</b>\n\nChoose a task below.', 'no_tasks': 'No tasks available right now.',
        'task_card': '<b>Task #{id}</b>\n\n{title}\nReward: <b>+{reward}</b> {currency}',
        'take_task': 'Take', 'open_target': 'Open target', 'complete_task': 'Complete',
        'task_taken': 'Task taken. Open the target and tap Complete after finishing.',
        'task_completed': 'Task completed. Reward credited.', 'already_taken': 'You already took this task.',
        'rewards_text': '<b>Rewards</b>\n\nVIP, rewards showcase and account upgrades will be here.',
        'campaigns_text': '<b>My campaigns</b>', 'no_campaigns': 'You have no campaigns yet.',
        'create_demo_campaign': 'Create demo campaign', 'campaign_created': 'Demo campaign created.',
        'campaign_card': '<b>Campaign #{id}</b>\n\n{title}\nReward: <b>{reward}</b> {currency}\nCompleted: <b>{completed}/{total}</b>',
        'analytics_text': '<b>Analytics</b>\n\nCampaigns: <b>{campaigns}</b>\nTotal tasks: <b>{tasks}</b>\nCompleted: <b>{completed}</b>',
        'topup_text': '<b>Top up</b>\n\nDemo top up is available in this build.',
        'topup_demo': 'Add demo balance +500', 'topup_done': 'Balance topped up by 500.',
        'support_text': '<b>Support</b>\n\nContact: {support}',
        'admin_text': '<b>Admin panel</b>\n\nUsers: <b>{users}</b>\nCampaigns: <b>{campaigns}</b>\nTask claims: <b>{claims}</b>',
        'access_denied': 'Access denied.', 'language_saved': 'Language saved.', 'role_saved': 'Role saved.',
        'unknown': 'Unknown', 'tier_new': 'New', 'tier_verified': 'Verified',
        'earner_label': 'Earner', 'advertiser_label': 'Advertiser',
        'chat_opened': 'Open the chat, join it and then return to verification.',
    },
}

# Fallback compact translations for remaining supported languages.
STRINGS['de'] = {
    **STRINGS['en'],
    'choose_language': '<b>Sprache wählen</b>', 'choose_role': '<b>Rolle wählen</b>',
    'role_earner': 'Ausführender', 'role_advertiser': 'Werbetreibender',
    'profile': 'Profil', 'wallet': 'Wallet', 'tasks': 'Aufgaben', 'rewards': 'Belohnungen',
    'campaigns': 'Kampagnen', 'analytics': 'Analytik', 'topup': 'Aufladen', 'support': 'Support', 'admin': 'Admin',
    'back': 'Zurück', 'subscription_check': 'Abo prüfen', 'join_chat': 'Chat öffnen',
    'subscription_ok': 'Abo bestätigt.', 'chat_opened': 'Öffne den Chat, tritt bei und kehre dann zur Prüfung zurück.',
}
STRINGS['es'] = {
    **STRINGS['en'],
    'choose_language': '<b>Elige idioma</b>', 'choose_role': '<b>Elige tu rol</b>',
    'role_earner': 'Ejecutor', 'role_advertiser': 'Anunciante',
    'profile': 'Perfil', 'wallet': 'Billetera', 'tasks': 'Tareas', 'rewards': 'Recompensas',
    'campaigns': 'Campañas', 'analytics': 'Analítica', 'topup': 'Recargar', 'support': 'Soporte', 'admin': 'Admin',
    'back': 'Atrás', 'subscription_check': 'Verificar suscripción', 'join_chat': 'Abrir chat',
    'subscription_ok': 'Suscripción confirmada.', 'chat_opened': 'Abre el chat, únete y vuelve a verificar.',
}
STRINGS['pt'] = {
    **STRINGS['en'],
    'choose_language': '<b>Escolha o idioma</b>', 'choose_role': '<b>Escolha seu papel</b>',
    'role_earner': 'Executor', 'role_advertiser': 'Anunciante',
    'profile': 'Perfil', 'wallet': 'Carteira', 'tasks': 'Tarefas', 'rewards': 'Recompensas',
    'campaigns': 'Campanhas', 'analytics': 'Análises', 'topup': 'Recarga', 'support': 'Suporte', 'admin': 'Admin',
    'back': 'Voltar', 'subscription_check': 'Verificar assinatura', 'join_chat': 'Abrir chat',
    'subscription_ok': 'Assinatura confirmada.', 'chat_opened': 'Abra o chat, entre nele e volte para verificar.',
}
STRINGS['tr'] = {
    **STRINGS['en'],
    'choose_language': '<b>Dil seçin</b>', 'choose_role': '<b>Rolünüzü seçin</b>',
    'role_earner': 'Kazanan', 'role_advertiser': 'Reklamveren',
    'profile': 'Profil', 'wallet': 'Cüzdan', 'tasks': 'Görevler', 'rewards': 'Ödüller',
    'campaigns': 'Kampanyalar', 'analytics': 'Analitik', 'topup': 'Bakiye yükle', 'support': 'Destek', 'admin': 'Yönetim',
    'back': 'Geri', 'subscription_check': 'Aboneliği kontrol et', 'join_chat': 'Sohbeti aç',
    'subscription_ok': 'Abonelik doğrulandı.', 'chat_opened': 'Sohbeti açın, katılın ve sonra kontrole dönün.',
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
    return t(locale, 'tier_verified') if tier == 'verified' else t(locale, 'tier_new')
