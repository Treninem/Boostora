# ПЕРЕНОС В НОВЫЙ ЧАТ — Boostora v3.0.2

Текущая версия проекта: **Boostora v3.0.2**.

Это стабильный патч поверх **Boostora v3.0.1** без отката функций и без ломающей миграции.

## Главный фокус v3.0.2

- защита от зависшего polling-lock;
- проверка хранения `/data`;
- контроль backup/invalid-db;
- усиление релиз-центра владельца;
- сохранение старых данных без ломающих изменений.

## Что уже сделано в v3.0.2

- `APP_VERSION='Boostora v3.0.2'`.
- `APP_STAGE='stable_patch_runtime_safety'`.
- В `app/bot.py` добавлены:
  - `_read_lock_pid()`;
  - `_pid_is_alive()`;
  - `_clear_stale_lock()`;
  - `_write_lock_payload()`.
- `_acquire_single_instance_lock()` теперь умеет убирать stale lock, если старый процесс уже не жив.
- В `app/services/release_readiness.py` добавлен `persistence_summary()`.
- В stable gate добавлена строка `persistence_safety`.
- В stable contract добавлена политика `stable_contract_patch_302_policy`.
- Обновлены RU/EN тексты под v3.0.2.
- Добавлен `scripts/stable_patch_v302_smoke_test.py`.

## Важные правила продолжения

- Не ломать старую базу.
- Не менять смысл `BOT_DATA_DIR=/data`.
- Не добавлять крупные функции в стабильную ветку v3.0.x без крайней необходимости.
- Патчи делать как v3.0.3, v3.0.4 и т.д.
- Пользовательский архив не должен содержать `storage`, `.db`, `.pyc`, `__pycache__`.

## Следующий логичный шаг

**Boostora v3.0.3** — только стабильные патчи: UX-полировка, точные подсказки владельцу, дополнительные regression-проверки и исправление найденных критических ошибок.
