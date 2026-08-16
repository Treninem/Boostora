# Boostora v4.0.0 — global runtime hardening

Крупное обновление поверх стабильного функционального ядра v3.7.0. Пользовательская схема данных не сбрасывается.

## Runtime

- `main.py` переведён на `app.runtime_v4`;
- Telegram polling, background jobs и существующие сервисы остаются на проверенном core;
- новый `app.webapp_v4` подключается как совместимый gateway-слой;
- rollback gateway не требует отката пользовательской БД.

## Mini App gateway

- отдельные per-user лимиты для read-only и mutation запросов;
- rate buckets и idempotency cache имеют жёсткие границы памяти;
- mutation idempotency привязана к user id + operation + payload fingerprint + client key;
- повтор успешной операции возвращает сохранённый результат;
- каждый ответ получает `X-Request-ID` и версию Boostora;
- публичный readiness не раскрывает внутренние счётчики пользователей/операций.

## Resilient client

Добавлен `miniapp_example/v4-client.js`, который gateway внедряет в существующий Mini App без переписывания большого `index.html`.

- mutations получают client request id;
- при обычном успешном ответе временный ключ сразу забывается;
- после транспортного сбоя ключ сохраняется 180 секунд;
- ручной повтор того же действия использует тот же ключ;
- offline/online и rate limit показываются пользователю понятным сообщением;
- автоматический retry mutations не добавлен.

## Startup / health

- startup guard проверяет writable data directory;
- проверяется SQLite health;
- проверяются `index.html` и v4 client asset;
- проверяется базовая форма BOT_TOKEN;
- проверяется минимум 128 MiB свободного диска;
- `/health/live` отделён от `/health/ready`;
- `/api/capabilities` публикует контракт gateway 4.0;
- owner-only `owner.system_health` дополнен runtime/gateway telemetry.

## Репозиторий

- удалены `storage/start_profile_wallet_smoke_test.db` и `storage/test_ad.db`;
- рабочий `storage/boostora.db` в этом релизе автоматически не удалялся, чтобы не допустить потери данных на старом нестандартном деплое;
- `.gitignore` уже блокирует новые `*.db`, `storage/`, `data/`, `.env` и runtime output;
- добавлен GitHub Actions quality gate.

## Quality gate

Workflow `.github/workflows/boostora-quality.yml`:

1. Python 3.12;
2. установка `requirements.txt`;
3. `compileall` для приложения и тестов;
4. `python -m unittest -v tests.test_v400_global_update`.

Regression contract проверяет rate limiting, восстановление окна, независимость read/mutation buckets, ограничение памяти, idempotency TTL, v4 entrypoint, client injection, owner telemetry, env contract и отсутствие тестовых БД.

## Новые настройки

```env
BOOSTORA_API_READS_PER_MINUTE=180
BOOSTORA_API_MUTATIONS_PER_MINUTE=45
BOOSTORA_API_RATE_WINDOW_SECONDS=60
BOOSTORA_IDEMPOTENCY_TTL_SECONDS=180
BOOSTORA_IDEMPOTENCY_CACHE_MAX=4096
BOOSTORA_RATE_BUCKETS_MAX=20000
```

Все значения имеют встроенные безопасные defaults и bounds.

## Совместимость

V4.0.0 не вводит миграцию бизнес-таблиц. Сохраняются:

- пользователи и роли;
- балансы, бонусы, удержания и транзакции;
- кампании, задания и submissions;
- рекламная сеть;
- обязательства Standard/PRO;
- документы/согласия;
- доступы групп;
- настройки владельца.

Перед деплоем обязательна резервная копия рабочей `/app/data/boostora.db`.
