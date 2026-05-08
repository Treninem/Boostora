# Boostora v2.7.0 — changelog

## Фокус

Финальная предрелизная закалка перед **v3.0.0-rc1**.

## Сделано

- `APP_VERSION` поднят до `Boostora v2.7.0`.
- `APP_STAGE` изменён на `release_candidate_hardening`.
- В `ReleaseReadinessService` добавлены:
  - `launch_guardrails()`;
  - `final_launch_checklist()`.
- Экран `owner_release` теперь показывает не только критические flows, но и live-матрицу запуска.
- Добавлены guardrails по:
  - env/schema;
  - Stars;
  - VIP;
  - оплате и ускорению заданий;
  - правам бота;
  - ручной очереди;
  - high-risk пользователям;
  - активному предложению заданий.
- Добавлены RU/EN тексты для launch guardrails и финального чек-листа.
- Добавлен `scripts/release_hardening_smoke_test.py`.
- Обновлены существующие smoke-тесты под v2.7.0.

## Совместимость

- Ломающей миграции нет.
- Новых обязательных таблиц нет.
- `BOT_DATA_DIR=/data` сохранён.
- Старые данные пользователей должны сохраниться.
