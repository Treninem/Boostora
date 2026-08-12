from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_callback_and_message_hotfix_in_isolated_process() -> None:
    script = r'''
import os, sys, tempfile, types
from pathlib import Path
root = Path(sys.argv[1]); sys.path.insert(0, str(root))
os.environ['BOT_TOKEN'] = '123456:TESTTOKEN'
os.environ['ADMIN_IDS'] = '2097006037'
os.environ['BOT_DATA_DIR'] = tempfile.mkdtemp(prefix='boostora-v331-hotfix-')
os.environ['DB_PATH'] = 'boostora.db'
os.environ['WEBAPP_ENABLED'] = '0'
try:
    import telebot  # noqa: F401
except ModuleNotFoundError:
    telebot = types.ModuleType('telebot')
    telebot_types = types.ModuleType('telebot.types')
    class Dummy:
        def __init__(self, *args, **kwargs):
            for key, value in kwargs.items(): setattr(self, key, value)
        def add(self, *args, **kwargs): return self
        def row(self, *args, **kwargs): return self
    for name in ('User','Message','CallbackQuery','InlineKeyboardMarkup','InlineKeyboardButton','ReplyKeyboardMarkup','KeyboardButton','ReplyKeyboardRemove','PreCheckoutQuery','WebAppInfo','MenuButtonWebApp','BotCommand','LabeledPrice'):
        setattr(telebot_types, name, type(name, (Dummy,), {}))
    telebot.TeleBot = type('TeleBot', (), {})
    telebot.types = telebot_types
    sys.modules['telebot'] = telebot
    sys.modules['telebot.types'] = telebot_types
try:
    import dotenv  # noqa: F401
except ModuleNotFoundError:
    dotenv = types.ModuleType('dotenv'); dotenv.load_dotenv = lambda *args, **kwargs: False
    sys.modules['dotenv'] = dotenv

from app import db
db.init_db()
from app.services.users import UserService
from app.router import _build_owner_release_text
from app.utils.ui import _fit_telegram_text

report = UserService.t(2097006037, 'boostore_check_report', state='ok', score=100, key='abc…xyz', balance='1', cached=2, whitelist=1, result='ok', error='—')
assert 'abc…xyz' in report
release = _build_owner_release_text(2097006037)
assert len(release) < 4096, len(release)
assert 'Boostora v3.6.4' in release
oversized = '<b>Title</b>\n' + ('очень длинная строка\n' * 500)
fitted = _fit_telegram_text(oversized, screen_key='test')
assert len(fitted) <= 4096
assert '<b>Title</b>' not in fitted
'''
    result = subprocess.run([sys.executable, '-c', script, str(ROOT)], cwd=ROOT, text=True, capture_output=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
