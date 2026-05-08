import os
import sys
import tempfile
import types
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault('BOT_TOKEN', '123:abc')
fd, temp_db = tempfile.mkstemp(prefix='boostora_v203_render_', suffix='.db')
os.close(fd)
os.environ['DB_PATH'] = temp_db

telebot = types.ModuleType('telebot')
telebot.TeleBot = object
telebot_types = types.ModuleType('telebot.types')

class InlineKeyboardButton:
    def __init__(self, *args, **kwargs): pass
class InlineKeyboardMarkup:
    def __init__(self, *args, **kwargs): self.rows = []
    def add(self, *args): self.rows.append(args)
    def row(self, *args): self.rows.append(args)
class ReplyKeyboardMarkup:
    def __init__(self, *args, **kwargs): self.rows = []
    def row(self, *args): self.rows.append(args)
class KeyboardButton:
    def __init__(self, *args, **kwargs): pass
class CallbackQuery: pass
class Message: pass
class User: pass

telebot_types.InlineKeyboardButton = InlineKeyboardButton
telebot_types.InlineKeyboardMarkup = InlineKeyboardMarkup
telebot_types.ReplyKeyboardMarkup = ReplyKeyboardMarkup
telebot_types.KeyboardButton = KeyboardButton
telebot_types.CallbackQuery = CallbackQuery
telebot_types.Message = Message
telebot_types.User = User
telebot.types = telebot_types
sys.modules.setdefault('telebot', telebot)
sys.modules.setdefault('telebot.types', telebot_types)

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import db
from app.router import _build_campaign_input_text, _build_campaign_preview_text
from app.services.client_campaigns import ClientCampaignService
from app.services.users import UserService

try:
    Path(temp_db).unlink(missing_ok=True)
    db.init_db()
    UserService.ensure_user(SimpleNamespace(id=1, username='u', first_name='U', last_name=None, language_code='ru'))
    ok, _ = ClientCampaignService.start_draft(1, 'channel_subscribe')
    assert ok
    ok, _, _ = ClientCampaignService.consume_target(1, 'https://t.me/testchannel')
    assert ok
    ok, _, _ = ClientCampaignService.consume_quantity(1, '100')
    assert ok
    text = _build_campaign_input_text(1, 'price')
    assert 'Рекомендовано' in text and 'приоритет' in text.lower(), text
    ok, _, _ = ClientCampaignService.consume_price(1, 'auto')
    assert ok
    preview = _build_campaign_preview_text(1)
    assert 'Рекомендованная цена' in preview and 'Почему так' in preview, preview
    print('OK: economy render smoke test passed')
finally:
    Path(temp_db).unlink(missing_ok=True)
