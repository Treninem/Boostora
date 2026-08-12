from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent

def read(path): return (ROOT/path).read_text(encoding='utf-8')
def write(path, text): (ROOT/path).write_text(text, encoding='utf-8')

runtime_files = [
'app/db.py','app/services/ad_broadcasts.py','app/services/admin.py','app/services/client_dashboard.py',
'app/services/engagement_modes.py','app/services/holds.py','app/services/performer.py','app/services/promo.py',
'app/services/risk.py','app/services/standard_admin.py','app/services/vip.py']
for name in runtime_files:
    p=Path(name); s=read(p)
    if 'datetime.utcnow()' not in s:
        raise SystemExit(f'expected datetime.utcnow() in {name}')
    s=s.replace('datetime.utcnow()', 'utcnow()')
    if 'from app.time_utils import utcnow' not in s:
        lines=s.splitlines(); idx=next((i for i,l in enumerate(lines) if l.startswith('from app ') or l.startswith('from app.')), None)
        if idx is None: raise SystemExit(f'cannot place utcnow import in {name}')
        lines.insert(idx, 'from app.time_utils import utcnow'); s='\n'.join(lines)+'\n'
    write(p,s)

write(Path('app/time_utils.py'), '''from __future__ import annotations\n\nfrom datetime import datetime, timezone\n\n\ndef utcnow() -> datetime:\n    """Return naive UTC for compatibility with existing SQLite timestamp strings.\n\n    ``datetime.utcnow()`` is deprecated in modern Python.  Boostora historically\n    stores UTC timestamps without an offset, so this helper deliberately keeps\n    that representation while obtaining the clock from an aware UTC datetime.\n    """\n    return datetime.now(timezone.utc).replace(tzinfo=None)\n''')

s=read(Path('app/version.py'))
if "Boostora v3.6.5" not in s: raise SystemExit('unexpected source version')
write(Path('app/version.py'), s.replace('Boostora v3.6.5','Boostora v3.6.6'))

for p in (ROOT/'tests').glob('test_*.py'):
    s=p.read_text(encoding='utf-8').replace('Boostora v3.6.5','Boostora v3.6.6')
    p.write_text(s,encoding='utf-8')
write(Path('tests/test_v366_datetime_compat.py'), '''from __future__ import annotations\n\nfrom datetime import datetime, timezone\nfrom pathlib import Path\n\nfrom app.time_utils import utcnow\n\n\ndef test_utcnow_preserves_legacy_naive_utc_representation():\n    before = datetime.now(timezone.utc).replace(tzinfo=None)\n    value = utcnow()\n    after = datetime.now(timezone.utc).replace(tzinfo=None)\n    assert value.tzinfo is None\n    assert before <= value <= after\n\n\ndef test_runtime_code_has_no_deprecated_datetime_utcnow_calls():\n    offenders = []\n    for path in Path('app').rglob('*.py'):\n        if path.name == 'time_utils.py':\n            continue\n        if 'datetime.utcnow(' in path.read_text(encoding='utf-8'):\n            offenders.append(str(path))\n    assert offenders == []\n''')

p=Path('README.md'); s=read(p).replace('# Boostora v3.6.5','# Boostora v3.6.6',1)
marker='Boostora — Telegram-бот и встроенная Mini App для продвижения, выполнения заданий, покупки Telegram-услуг и участия в сети рекламных размещений.\n'
new='''\n## Что изменилось в v3.6.6\n\n### Современная UTC-совместимость без миграции БД\n\n- все рабочие вызовы устаревшего `datetime.utcnow()` заменены единым `app.time_utils.utcnow()`;\n- helper получает время через timezone-aware UTC, но возвращает naive UTC для полной совместимости с существующими SQLite-строками;\n- формат `isoformat(timespec='seconds')`, имена резервных копий и сравнение старых дат не меняются;\n- добавлен тест, запрещающий возврат `datetime.utcnow()` в runtime-код.\n\n'''
if '## Что изменилось в v3.6.6' not in s: s=s.replace(marker,marker+new,1)
write(p,s)

p=Path('BOTHOST_START.md'); s=read(p).replace('Boostora v3.6.5','Boostora v3.6.6').replace('Boostora_v3.6.5_RUNTIME.zip','Boostora_v3.6.6_RUNTIME.zip').replace('## Проверка v3.6.5','## Проверка v3.6.6'); write(p,s)
write(Path('HOTFIX_NOTES.md'), '''# Boostora v3.6.6 — UTC compatibility cleanup\n\nОбновление поверх **v3.6.5** без изменения схемы SQLite и без сброса допусков пользователей.\n\n## Исправлено\n\n- удалены все рабочие вызовы deprecated `datetime.utcnow()`;\n- добавлен единый `app.time_utils.utcnow()`;\n- старый формат naive UTC сохранён намеренно, поэтому существующие строки SQLite и сравнения дат совместимы;\n- резервные имена и ISO-строки времени сохраняют прежний формат.\n\nГлобальная защита групп из v3.6.5 не меняется.\n''')
write(Path('PATCH_INSTALL.md'), '''# Установка PATCH v3.6.6 поверх v3.6.5\n\n1. Остановите Boostora.\n2. Сохраните `/app/data/boostora.db`.\n3. Распакуйте PATCH в корень проекта с заменой файлов.\n4. Не заменяйте рабочий `.env` и не удаляйте `/app/data`.\n5. Запустите новый деплой.\n6. Проверьте запуск бота, Mini App и одно сообщение в группе.\n\nМиграция SQLite не требуется. Формат сохранённых UTC-дат не меняется.\n''')
write(Path('PATCH_MANIFEST.md'), '''# PATCH Boostora v3.6.6\n\nБыстрое обновление поверх **Boostora v3.6.5**.\n\n## Файлы в архиве PATCH\n\n- `app/time_utils.py`\n- `app/db.py`\n- `app/services/ad_broadcasts.py`\n- `app/services/admin.py`\n- `app/services/client_dashboard.py`\n- `app/services/engagement_modes.py`\n- `app/services/holds.py`\n- `app/services/performer.py`\n- `app/services/promo.py`\n- `app/services/risk.py`\n- `app/services/standard_admin.py`\n- `app/services/vip.py`\n- `app/version.py`\n- `HOTFIX_NOTES.md`\n- `RELEASE_REPORT_v3.6.6.md`\n- `PATCH_INSTALL.md`\n- `PATCH_MANIFEST.md`\n- `DELETE_FILES.txt` — пустой.\n''')
write(Path('TRANSFER_NOTES.md'), '''# Boostora v3.6.6 — контрольная точка\n\nСледующая работа должна начинаться от **v3.6.6**. Глобальный gate из v3.6.5 сохранён; anonymous/sender_chat закрыт, automatic discussion forwards не блокируются, pyTelegramBotAPI = 4.36.0. В v3.6.6 устаревший `datetime.utcnow()` удалён из runtime-кода с сохранением legacy naive UTC формата SQLite. Уже выданный доступ пользователей сохраняется.\n''')
write(Path('RELEASE_REPORT_v3.6.6.md'), '''# Boostora v3.6.6 — совместимое обновление UTC\n\n## Реализовано\n\n- 29 вызовов `datetime.utcnow()` заменены на единый helper `app.time_utils.utcnow()`;\n- helper использует `datetime.now(timezone.utc)` и затем намеренно снимает `tzinfo`, сохраняя существующий naive UTC контракт проекта;\n- SQLite-схема, строки `CURRENT_TIMESTAMP`, существующие ISO-значения и имена резервных копий не меняются;\n- добавлены регрессионные тесты на naive UTC и отсутствие deprecated-вызовов в runtime-коде.\n\n## Совместимость\n\nОбновление не сбрасывает базу, балансы, задания, кампании, историю или `chat_gate_started_at`.\n''')
p=Path('app/services/final_audit.py'); s=read(p).replace('The v3.6.3 audit contains an exact historical version equality check. v3.6.4\nkeeps that audit as the cumulative baseline while adding the all-groups start\ngate separately, so a newer application version must not become a false\nblocker in the legacy checklist.', 'The v3.6.3 audit contains an exact historical version equality check. Newer\nreleases keep that audit as a cumulative baseline, so the current application\nversion must not become a false blocker in the legacy checklist.'); write(p,s)

subprocess.run(['python','-m','compileall','-q','app','tests'],check=True)
subprocess.run(['python','-m','pytest','-q','-W','error::DeprecationWarning'],check=True)
