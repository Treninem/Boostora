# Boostora v3.2.8 — запуск на Bothost

## Настройки проекта

```text
Использовать собственный Dockerfile: Нет
Главный файл: main.py
Команда запуска: python3 main.py
Порт: 3000
```

## Основные переменные

```env
BOT_TOKEN=ТОКЕН_БОТА
ADMIN_IDS=2097006037
BOT_DATA_DIR=/app/data
DB_PATH=boostora.db
WEBAPP_ENABLED=1
WEBAPP_REQUIRED=1
WEBAPP_HOST=0.0.0.0
PORT=3000
WEBAPP_URL=https://boostorabot.bothost.tech
MINI_APP_URL=
WEBAPP_AUTH_MAX_AGE_SECONDS=86400
SMART_BOTTOM_MENU=compact
DROP_PENDING_UPDATES=0
```

## После деплоя

Проверь:

```text
https://boostorabot.bothost.tech/health
https://boostorabot.bothost.tech/
```

В логах должны появиться:

```text
Embedded Mini App is listening on http://0.0.0.0:3000
Telegram Mini App menu button configured
Boostora v3.2.8 started with update guard
```

Открой Mini App именно из Telegram. Обычный пользователь должен видеть только личные разделы. Администратор получает раздел «Управление», а первый ID из `ADMIN_IDS` дополнительно получает раздел владельца.

Рабочая база должна храниться в `/app/data/boostora.db`. Не загружай `.env`, базу, токены и `BOOSTORE_API_KEY` в GitHub.
