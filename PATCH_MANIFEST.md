# PATCH Boostora v3.6.2

Быстрое обновление поверх **Boostora v3.6.1**.

## Что меняется

- защищается чат `@Boostorachat`;
- сообщения пользователей без нового личного `/start` мгновенно удаляются;
- пользователь получает упоминание и кнопку запуска Boostora;
- после `/start` доступ открывается автоматически;
- правило применяется к новым и старым участникам;
- добавляется проверка прав бота при запуске.

## Файлы

- .env.example
- BOTHOST_START.md
- HOTFIX_NOTES.md
- README.md
- RELEASE_REPORT_v3.6.2.md
- app/bot.py
- app/config.py
- app/db.py
- app/handlers/start.py
- app/services/chat_start_gate.py
- app/services/final_audit.py
- app/texts.py
- app/version.py
- PATCH_INSTALL.md
- PATCH_MANIFEST.md
- DELETE_FILES.txt
