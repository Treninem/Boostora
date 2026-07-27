# Boostora v3.2.7 — запуск бота и Mini App на Bothost

## Что запускается

Один процесс `python3 main.py` одновременно запускает:

- Telegram-бота через polling;
- Mini App на `0.0.0.0:$PORT`;
- `/health` и `/healthz` для проверки контейнера;
- `/api/config` для безопасной конфигурации интерфейса;
- `/api/telegram/session` для проверки подписи Telegram `initData`;
- `/api/miniapp/open` для сохранения подтверждённого действия пользователя.

Отдельный проект или отдельный статический хостинг для Mini App больше не нужен.

## Файлы в корне GitHub

В корне репозитория должны находиться:

```text
main.py
requirements.txt
.env.example
app/
miniapp_example/
```

Загружай содержимое runtime-архива, а не папку, внутри которой лежат эти файлы.

## Главный файл и команда

```text
Главный файл: main.py
Команда запуска: python3 main.py
Порт: 3000
```

## Обязательные переменные

```env
BOT_TOKEN=ТОКЕН_БОТА
ADMIN_IDS=2097006037

BOT_DATA_DIR=/app/data
DB_PATH=boostora.db

WEBAPP_ENABLED=1
WEBAPP_REQUIRED=1
WEBAPP_HOST=0.0.0.0
PORT=3000
WEBAPP_URL=https://boostora.bothost.tech
WEBAPP_AUTH_MAX_AGE_SECONDS=86400

SMART_BOTTOM_MENU=compact
DROP_PENDING_UPDATES=0
```

`WEBAPP_URL` и `MINI_APP_URL` теперь поддерживаются одновременно. Для этого проекта достаточно:

```env
WEBAPP_URL=https://boostora.bothost.tech
MINI_APP_URL=
```

## Домен

В Bothost привяжи к проекту домен:

```text
boostora.bothost.tech
```

После деплоя должны открываться:

```text
https://boostora.bothost.tech/
https://boostora.bothost.tech/health
https://boostora.bothost.tech/api/config
```

Ожидаемый ответ `/health`:

```json
{"ok":true,"service":"boostora","version":"Boostora v3.2.7","webapp":true}
```

## Telegram

При старте бот сам пытается установить глобальную кнопку меню Mini App. В логах должны появиться строки:

```text
Embedded Mini App is listening on http://0.0.0.0:3000
Telegram Mini App public URL: https://boostora.bothost.tech
Telegram Mini App menu button configured
Boostora v3.2.7 started with update guard
```

Если кнопка меню в старом диалоге не обновилась, полностью закрой Telegram, открой снова и отправь боту `/start`. Кнопка Mini App также остаётся внутри раздела «Центр».

## Проверка после деплоя

1. Открой `https://boostora.bothost.tech/health`.
2. Открой `https://boostora.bothost.tech/` в браузере — должен загрузиться веб-предпросмотр.
3. В Telegram открой меню бота и нажми кнопку Boostora.
4. В Mini App должна появиться подтверждённая Telegram-сессия.
5. Нажми «Подтвердить открытие» — Mini App отправит подписанное событие во встроенный API, а бот сохранит его в активности пользователя.
6. Проверь `/version`, кошелёк, Standard/PRO, задания и релиз-центр.

## Важно

Не добавляй в GitHub `.env`, рабочую БД, токен Telegram или `BOOSTORE_API_KEY`. Рабочая база должна находиться в `/app/data/boostora.db`.


## Исправление v3.2.7

В pyTelegramBotAPI 4.28.0 конструктору `MenuButtonWebApp` обязательно передаётся `type=web_app`. В этой версии параметр добавлен, а сбой настройки глобальной кнопки больше не завершает весь процесс.
