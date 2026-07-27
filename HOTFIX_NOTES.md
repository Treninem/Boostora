# Boostora v3.2.9 — Telegram callback/message hotfix

Исправлены две ошибки из живых логов Bothost:

1. `UserService.t() got multiple values for argument key` при `v18|boostore_check|balance`.
   Параметр функции перевода `key` переименован в `text_key`; поле `{key}` отчёта Boostore теперь передаётся безопасно.

2. `Bad Request: MESSAGE_TOO_LONG` при `v14|go|owner_release`.
   Релиз-центр переведён на компактную сводку; общий renderer дополнительно ограничивает случайно длинные экраны.

Дополнительно изменён порядок замены сообщений: новое сообщение отправляется до удаления старого. База данных и `.env` не меняются.
