# Boostora v3.6.6 — совместимое обновление UTC

## Реализовано

- 29 вызовов `datetime.utcnow()` заменены на единый helper `app.time_utils.utcnow()`;
- helper использует `datetime.now(timezone.utc)` и затем намеренно снимает `tzinfo`, сохраняя существующий naive UTC контракт проекта;
- SQLite-схема, строки `CURRENT_TIMESTAMP`, существующие ISO-значения и имена резервных копий не меняются;
- добавлены регрессионные тесты на naive UTC и отсутствие deprecated-вызовов в runtime-коде.

## Совместимость

Обновление не сбрасывает базу, балансы, задания, кампании, историю или `chat_gate_started_at`.
