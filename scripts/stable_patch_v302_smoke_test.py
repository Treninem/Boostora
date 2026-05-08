from __future__ import annotations

import os
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
data_dir = tempfile.mkdtemp(prefix='boostora_v302_')
os.environ['BOT_DATA_DIR'] = data_dir
os.environ['DB_PATH'] = str(Path(data_dir) / f'boostora_patch_{uuid.uuid4().hex}.db')
os.environ['ENABLE_XTR_PAYMENTS'] = '1'

from app import db
from app.services.release_readiness import ReleaseReadinessService
from app.version import APP_STAGE, APP_VERSION

assert APP_VERSION == 'Boostora v3.0.3'
assert APP_STAGE == 'stable_patch_db_runtime_guard'

db.init_db()

persistence = ReleaseReadinessService.persistence_summary()
assert persistence['status'] == 'ready', persistence
assert persistence['data_dir_exists'] == 1
assert persistence['db_parent_exists'] == 1
assert persistence['db_inside_data'] == 1

stable = ReleaseReadinessService.stable_release_summary()
assert any(row['code'] == 'persistence_safety' for row in stable['rows'])
assert 'stable_contract_patch_302_policy' in ReleaseReadinessService.stable_release_contract()

bot_source = (PROJECT_ROOT / 'app' / 'bot.py').read_text(encoding='utf-8')
assert '_clear_stale_lock' in bot_source
assert '_read_lock_pid' in bot_source
assert '_write_lock_payload' in bot_source

print('stable_patch_v302_smoke_test: OK')
