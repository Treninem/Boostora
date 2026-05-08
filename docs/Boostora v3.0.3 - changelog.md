# Boostora v3.0.3 — changelog

## Тип релиза

Стабильный патч поверх **Boostora v3.0.2**.

## Главное

- Версия поднята до **Boostora v3.0.3**.
- `APP_STAGE='stable_patch_db_runtime_guard'`.
- Ломающей миграции нет.
- Новых обязательных таблиц нет.
- Старые данные сохраняются через `BOT_DATA_DIR=/data`.

## Изменения

- Усилено подключение SQLite:
  - timeout 30 секунд;
  - `PRAGMA busy_timeout = 5000`;
  - безопасная попытка включения WAL.
- Добавлена проверка `runtime_safety_summary()` в `ReleaseReadinessService`.
- Stable gate получил строку `runtime_safety`.
- Релиз-центр показывает риски runtime-состояния:
  - подключение к базе;
  - размер базы и WAL;
  - journal leftovers;
  - старые input-сессии;
  - старые invoice-сообщения;
  - просроченные холды;
  - backlog рекламной очереди.
- Обновлены RU/EN тексты релиз-центра, админки, коммерции владельца и `/version`.
- Добавлен `scripts/stable_patch_v303_smoke_test.py`.
- Старые smoke-тесты обновлены под версию v3.0.3.

## Проверки

- `py_compile` по `app/scripts` — OK.
- `stable_patch_v303_smoke_test.py` — OK.
- `stable_patch_v302_smoke_test.py` — OK.
- `stable_patch_v301_smoke_test.py` — OK.
- `stable_release_gate_smoke_test.py` — OK.
- `release_candidate_rc1_gate_smoke_test.py` — OK.
- `release_hardening_smoke_test.py` — OK.
- `release_candidate_regression_test.py` — OK.
- `owner_analytics_smoke_test.py` — OK.
- zip integrity — OK.
