# Boostora v3.0.0-rc1 — changelog

## Фокус

Стабильный коммерческий релиз-кандидат перед финальной **Boostora v3.0.0**.

## Сделано

- `APP_VERSION` поднят до `Boostora v3.0.0-rc1`.
- `APP_STAGE` изменён на `stable_release_candidate`.
- В `ReleaseReadinessService` добавлены:
  - `rc1_gate_summary()`;
  - `rc1_release_contract()`.
- Релиз-центр теперь показывает:
  - RC1-gate;
  - live guardrails;
  - критические flows;
  - финальный чек-лист;
  - regression pack;
  - RC1-договор.
- Добавлены RU/EN тексты для RC1-gate и owner-only релизного договора.
- Обновлены owner-commerce, admin-home и `/version` тексты под v3.0.0-rc1.
- Добавлен `scripts/release_candidate_rc1_gate_smoke_test.py`.
- Обновлены smoke-тесты, где проверяется версия приложения.

## Совместимость

- Ломающей миграции нет.
- Новых обязательных таблиц нет.
- `BOT_DATA_DIR=/data` сохранён.
- Пользовательские данные должны сохраниться.
