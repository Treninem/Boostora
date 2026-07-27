# Boostora v3.2.7 hotfix

Причина падения v3.2.6:

```text
TypeError: MenuButtonWebApp.__init__() missing 1 required positional argument: 'type'
```

Исправление:
- для pyTelegramBotAPI 4.28.0 передаётся `type='web_app'`;
- сохранён fallback для старой сигнатуры;
- создание глобальной кнопки Mini App стало неблокирующим: при несовместимости бот и HTTP-сервер продолжают работу;
- миграция базы не требуется.

После обновления ожидаемые строки:

```text
Embedded Mini App is listening on http://0.0.0.0:3000
Telegram Mini App menu button configured
Boostora v3.2.7 started with update guard
```
