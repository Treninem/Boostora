import os
import sys
sys.dont_write_bytecode = True
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

required_files = [
    ROOT / 'main.py',
    ROOT / '.env.example',
    ROOT / 'requirements.txt',
    ROOT / 'app' / 'handlers' / '__init__.py',
    ROOT / 'app' / 'keyboards' / '__init__.py',
    ROOT / 'app' / 'services' / '__init__.py',
    ROOT / 'app' / 'utils' / '__init__.py',
]
for path in required_files:
    assert path.exists(), f'Missing required file: {path}'

for pycache in ROOT.rglob('__pycache__'):
    raise AssertionError(f'Unexpected cache directory in artifact: {pycache}')

from app.config import settings
from app.handlers.callbacks import _safe_int
from app.services.admin import AdminService
from app.services.users import UserService

assert settings.run_command == 'python3 main.py'
assert _safe_int('123') == 123
assert _safe_int(' 42 ') == 42
assert _safe_int('abc') is None
assert _safe_int('-7') is None

user_id = 999001
admin_id = 2097006037
from app import db
from app.db import init_db
init_db()
db.upsert_user(admin_id, 'admin', 'Admin', None)
db.ensure_wallet(admin_id)
db.upsert_user(user_id, 'user', 'User', None)
db.ensure_wallet(user_id)

ok, key, current = AdminService.adjust_risk_score(admin_id, user_id, -999, reason='stage8 clamp check')
assert ok and key == 'admin_risk_adjusted'
assert current == 0
assert UserService.get_user(user_id)['risk_score'] == 0

print('OK: stage 8 smoke test passed')
