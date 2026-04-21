# Boostora — этап 8

Финальная сборка проекта после доскональной проверки структуры, БД, пользовательских сценариев, админки, антифрода и упаковки под запуск на Bothost.

## Запуск

1. Загрузите файлы в корень проекта на Bothost.
2. Создайте `.env` на основе `.env.example`.
3. Установите зависимости из `requirements.txt`.
4. Команда запуска: `python3 main.py`
5. Для админки используйте `/admin` от пользователя из `ADMIN_IDS`.

## Что входит в финальную сборку

- стартовый поток `/start`;
- выбор языка и роли;
- обязательная подписка на чат;
- inline-навигация с обновлением текущего сообщения;
- кабинет исполнителя: задания, подтверждение, холды, кошелёк, история;
- кабинет заказчика: кампании, статусы, аналитика;
- VIP, награды, внутренняя валюта, рефералы;
- админка, ручная модерация, блокировки, корректировки;
- антифрод и перевод спорных кейсов в `manual_review`.

## Что дополнительно вычищено на этапе 8

- возвращён `.env.example` в архив;
- удалены `__pycache__` и `.pyc` из финальной упаковки;
- добавлены `__init__.py` в подпакеты для более чистой структуры;
- усилена защита от битых и подменённых callback-данных;
- скорректирована правка `risk_score`, чтобы значение не уходило ниже нуля;
- добавлен `scripts/stage8_smoke_test.py`.

## Быстрая локальная проверка

```bash
python3 scripts/db_smoke_test.py
python3 scripts/stage3_smoke_test.py
python3 scripts/stage4_smoke_test.py
python3 scripts/stage5_smoke_test.py
python3 scripts/stage6_smoke_test.py
python3 scripts/stage7_smoke_test.py
python3 scripts/stage8_smoke_test.py
```

Ожидаемый результат:

```bash
OK: stage 2 smoke test passed
OK: stage 3 smoke test passed
OK: stage 4 smoke test passed
OK: stage 5 smoke test passed
OK: stage 6 smoke test passed
OK: stage 7 smoke test passed
OK: stage 8 smoke test passed
```
