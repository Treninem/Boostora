from __future__ import annotations

from aiogram import Bot
from aiogram.types import BotCommand

COMMANDS: dict[str, list[tuple[str, str]]] = {
    'ru': [
        ('start', 'Запуск и смена роли'),
        ('help', 'Справка и безопасность'),
        ('tasks', 'Лента заданий'),
        ('wallet', 'Баланс и история'),
        ('rewards', 'Награды и VIP'),
        ('campaigns', 'Мои кампании'),
        ('topup', 'Пополнение рекламного баланса'),
        ('admin', 'Админ-панель'),
    ],
    'en': [
        ('start', 'Start and choose role'),
        ('help', 'Help and safety center'),
        ('tasks', 'Open task feed'),
        ('wallet', 'Open wallet and history'),
        ('rewards', 'Rewards and VIP center'),
        ('campaigns', 'Open my campaigns'),
        ('topup', 'Top up advertiser balance'),
        ('admin', 'Admin panel'),
    ],
    'de': [
        ('start', 'Start und Rolle wählen'),
        ('help', 'Hilfe und Sicherheit'),
        ('tasks', 'Aufgaben-Feed öffnen'),
        ('wallet', 'Wallet und Verlauf öffnen'),
        ('rewards', 'Prämien und VIP'),
        ('campaigns', 'Meine Kampagnen'),
        ('topup', 'Werbebalance aufladen'),
        ('admin', 'Admin-Bereich'),
    ],
    'es': [
        ('start', 'Iniciar y elegir rol'),
        ('help', 'Ayuda y seguridad'),
        ('tasks', 'Abrir tareas'),
        ('wallet', 'Abrir billetera e historial'),
        ('rewards', 'Recompensas y VIP'),
        ('campaigns', 'Mis campañas'),
        ('topup', 'Recargar saldo publicitario'),
        ('admin', 'Panel admin'),
    ],
    'pt': [
        ('start', 'Iniciar e escolher função'),
        ('help', 'Ajuda e segurança'),
        ('tasks', 'Abrir tarefas'),
        ('wallet', 'Abrir carteira e histórico'),
        ('rewards', 'Recompensas e VIP'),
        ('campaigns', 'Minhas campanhas'),
        ('topup', 'Recarregar saldo de anúncios'),
        ('admin', 'Painel admin'),
    ],
    'tr': [
        ('start', 'Başlat ve rol seç'),
        ('help', 'Yardım ve güvenlik'),
        ('tasks', 'Görev akışını aç'),
        ('wallet', 'Cüzdan ve geçmiş'),
        ('rewards', 'Ödüller ve VIP'),
        ('campaigns', 'Kampanyalarım'),
        ('topup', 'Reklam bakiyesi yükle'),
        ('admin', 'Yönetici paneli'),
    ],
}


async def apply_localized_commands(bot: Bot) -> None:
    for language_code, items in COMMANDS.items():
        await bot.set_my_commands(
            commands=[BotCommand(command=command, description=description) for command, description in items],
            language_code=language_code,
        )

    await bot.set_my_commands(
        commands=[BotCommand(command=command, description=description) for command, description in COMMANDS['en']],
    )
