from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import types
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

dotenv_mod = types.ModuleType('dotenv')
dotenv_mod.load_dotenv = lambda *args, **kwargs: None
sys.modules.setdefault('dotenv', dotenv_mod)

os.environ['BOT_TOKEN'] = '123:TEST'
os.environ['ADMIN_IDS'] = '1'
data_dir = tempfile.mkdtemp(prefix='boostora_v303_')
os.environ['BOT_DATA_DIR'] = data_dir
os.environ['DB_PATH'] = str(Path(data_dir) / f'boostora_patch_{uuid.uuid4().hex}.db')
os.environ['ENABLE_XTR_PAYMENTS'] = '1'

from app import db
from app.config import settings
from app.services.release_readiness import ReleaseReadinessService
from app.version import APP_STAGE, APP_VERSION

assert APP_VERSION == 'Boostora v3.0.3'
assert APP_STAGE == 'stable_patch_db_runtime_guard'

db.init_db()

with db.get_connection() as connection:
    timeout_row = connection.execute('PRAGMA busy_timeout').fetchone()
    journal_row = connection.execute('PRAGMA journal_mode').fetchone()
    assert int(timeout_row[0]) >= 5000
    assert str(journal_row[0]).lower() in {'wal', 'delete', 'memory', 'off', 'truncate', 'persist'}

runtime = ReleaseReadinessService.runtime_safety_summary()
assert runtime['connect_ok'] == 1, runtime
assert runtime['status'] in {'ready', 'warning'}, runtime

stable = ReleaseReadinessService.stable_release_summary()
assert any(row['code'] == 'runtime_safety' for row in stable['rows']), stable
assert 'stable_contract_patch_303_policy' in ReleaseReadinessService.stable_release_contract()

texts_source = (PROJECT_ROOT / 'app' / 'texts.py').read_text(encoding='utf-8')
assert 'Stable gate v3.0.3' in texts_source
assert 'Runtime-защита и очереди' in texts_source

db_source = (PROJECT_ROOT / 'app' / 'db.py').read_text(encoding='utf-8')
assert 'busy_timeout = 5000' in db_source
assert 'journal_mode = WAL' in db_source

print('stable_patch_v303_smoke_test: OK')
