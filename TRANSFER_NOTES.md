# Boostora v3.6.6 — контрольная точка

Следующая работа должна начинаться от **v3.6.6**. Глобальный gate из v3.6.5 сохранён; anonymous/sender_chat закрыт, automatic discussion forwards не блокируются, pyTelegramBotAPI = 4.36.0. В v3.6.6 устаревший `datetime.utcnow()` удалён из runtime-кода с сохранением legacy naive UTC формата SQLite. Уже выданный доступ пользователей сохраняется.
