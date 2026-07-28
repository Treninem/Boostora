# Boostora v3.4.0 — запуск на Bothost

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
ENABLE_XTR_PAYMENTS=1
```

Новых обязательных переменных относительно v3.3.1 нет.

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
Boostora v3.4.0 started with update guard
```

Открой Boostora кнопкой Mini App внутри Telegram. Каталог, заказы, кампании, задания, кошелёк, профиль, Standard/PRO и закрытое управление работают внутри приложения. Бот остаётся точкой входа и принимает подтверждения платежей Telegram Stars.

Обычный пользователь не должен видеть управление, внутренние тарифы поставщика, диагностику или релиз-центр. Администратор получает только админский кабинет, а первый ID из `ADMIN_IDS` — кабинет владельца.

Рабочая база должна храниться в `/app/data/boostora.db`. Не загружай `.env`, базу, токены и `BOOSTORE_API_KEY` в GitHub.
