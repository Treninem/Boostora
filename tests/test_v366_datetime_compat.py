from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from app.time_utils import utcnow


def test_utcnow_preserves_legacy_naive_utc_representation():
    before = datetime.now(timezone.utc).replace(tzinfo=None)
    value = utcnow()
    after = datetime.now(timezone.utc).replace(tzinfo=None)
    assert value.tzinfo is None
    assert before <= value <= after


def test_runtime_code_has_no_deprecated_datetime_utcnow_calls():
    offenders = []
    for path in Path('app').rglob('*.py'):
        if path.name == 'time_utils.py':
            continue
        if 'datetime.utcnow(' in path.read_text(encoding='utf-8'):
            offenders.append(str(path))
    assert offenders == []
