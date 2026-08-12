from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_webapp_role_gates_in_isolated_process() -> None:
    script = r'''
import hashlib, hmac, json, os, sys, tempfile, threading, time, types
import urllib.error, urllib.parse, urllib.request
from pathlib import Path

root = Path(sys.argv[1])
sys.path.insert(0, str(root))
os.environ['BOT_TOKEN'] = '123456:TESTTOKEN'
os.environ['ADMIN_IDS'] = '1001,1002'
os.environ['SUPPORT_USERNAME'] = '@BoostoraTestBot'
os.environ['LEGACY_DB_MIRROR_ENABLED'] = '0'
os.environ['WEBAPP_URL'] = 'https://boostora.example'
os.environ['BOT_DATA_DIR'] = tempfile.mkdtemp(prefix='boostora-v331-role-')
os.environ['DB_PATH'] = 'boostora.db'
try:
    import telebot  # noqa: F401
except ModuleNotFoundError:
    telebot = types.ModuleType('telebot')
    telebot_types = types.ModuleType('telebot.types')
    telebot_types.User = type('User', (), {})
    telebot.types = telebot_types
    sys.modules['telebot'] = telebot
    sys.modules['telebot.types'] = telebot_types

from app import db
from app.webapp import BoostoraWebHandler, _ReusableThreadingHTTPServer

db.init_db()
for uid, role in ((1001, 'client'), (1002, 'performer'), (2001, 'client'), (2002, 'performer')):
    db.upsert_user(uid, f'u{uid}', f'User{uid}', None)
    db.set_user_role(uid, role)
    db.ensure_wallet(uid)

server = _ReusableThreadingHTTPServer(('127.0.0.1', 0), BoostoraWebHandler)
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
base = f'http://127.0.0.1:{server.server_address[1]}'

def signed(uid: int) -> str:
    pairs = {
        'auth_date': str(int(time.time())),
        'query_id': f'q{uid}',
        'user': json.dumps({'id': uid, 'first_name': f'User{uid}', 'username': f'u{uid}'}, separators=(',', ':')),
    }
    check = '\n'.join(f'{key}={value}' for key, value in sorted(pairs.items()))
    secret = hmac.new(b'WebAppData', os.environ['BOT_TOKEN'].encode(), hashlib.sha256).digest()
    pairs['hash'] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urllib.parse.urlencode(pairs)

def post(path: str, payload: dict):
    request = urllib.request.Request(base + path, data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(request) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())

checks = (
    (2001, 'campaigns', 200), (2001, 'tasks', 403), (2001, 'admin', 403),
    (2001, 'owner_release', 403), (2002, 'tasks', 200), (2002, 'campaigns', 403),
    (1002, 'admin_queue', 200), (1002, 'owner_release', 403), (1001, 'owner_release', 200),
)
for uid, action, expected in checks:
    status, payload = post('/api/miniapp/action', {'init_data': signed(uid), 'action': action})
    assert status == expected, (uid, action, status, payload)

status, client = post('/api/telegram/session', {'init_data': signed(2001)})
assert status == 200 and 'owner_meta' not in client and not client['access']['is_admin']
status, owner = post('/api/telegram/session', {'init_data': signed(1001)})
assert status == 200 and owner['access']['is_owner'] and owner['owner_meta']['version'] == 'Boostora v3.6.4'

server.shutdown(); server.server_close(); thread.join(timeout=2)
'''
    result = subprocess.run(
        [sys.executable, '-c', script, str(ROOT)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
