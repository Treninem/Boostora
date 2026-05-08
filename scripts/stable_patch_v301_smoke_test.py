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

# Set env before importing app modules.
os.environ['BOT_TOKEN'] = '123:TEST'
os.environ['ADMIN_IDS'] = 'bad, 1, -4, 1'
data_dir = tempfile.mkdtemp(prefix='boostora_v301_')
os.environ['BOT_DATA_DIR'] = data_dir
os.environ['DB_PATH'] = str(Path(data_dir) / f'boostora_patch_{uuid.uuid4().hex}.db')
os.environ['DEFAULT_HOLD_HOURS'] = 'wrong'
os.environ['DEMO_HOLD_MINUTES'] = '0'
os.environ['PROMO_INTERVAL_HOURS'] = '99999'
os.environ['ENABLE_XTR_PAYMENTS'] = '1'

from app import db
from app.config import CONFIG_WARNINGS, settings
from app.services.release_readiness import ReleaseReadinessService
from app.version import APP_STAGE, APP_VERSION

assert APP_VERSION == 'Boostora v3.0.3'
assert APP_STAGE == 'stable_patch_db_runtime_guard'
assert settings.admin_ids == [1]
assert settings.default_hold_hours == 24
assert settings.demo_hold_minutes == 3
assert settings.promo_interval_hours == 18
assert CONFIG_WARNINGS, 'invalid env values must be recorded as warnings'

db.init_db()
config_summary = ReleaseReadinessService.config_warning_summary()
assert config_summary['warnings'] >= 1
integrity = ReleaseReadinessService.data_integrity_summary()
assert integrity['status'] == 'ready'

# Create an impossible wallet state and verify the gate can catch it.
db.execute(
    """
    INSERT INTO users (user_id, language_code, role, status, risk_score)
    VALUES (101, 'ru', 'client', 'active', 0)
    ON CONFLICT(user_id) DO NOTHING
    """
)
db.execute(
    """
    INSERT INTO wallets (user_id, available_balance, hold_balance, internal_balance, bonus_balance)
    VALUES (101, -1, 0, 0, 0)
    ON CONFLICT(user_id) DO UPDATE SET available_balance = -1
    """
)
integrity_bad = ReleaseReadinessService.data_integrity_summary()
assert integrity_bad['status'] == 'blocker'
assert integrity_bad['negative_wallets'] >= 1

stable = ReleaseReadinessService.stable_release_summary()
assert any(row['code'] == 'data_integrity' for row in stable['rows'])
assert any(row['code'] == 'config_parse' for row in stable['rows'])

print('stable_patch_v301_smoke_test: OK')
