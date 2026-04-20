import os
import sys
import tempfile
import types
from pathlib import Path
from types import SimpleNamespace

workdir = Path(tempfile.mkdtemp(prefix="boostora_smoke_"))
os.environ["BOT_TOKEN"] = "123:abc"
os.environ["DB_PATH"] = str(workdir / "stats_payment.db")
os.environ.setdefault("ADMIN_IDS", "2097006037")

telebot = types.ModuleType("telebot")
types_mod = types.ModuleType("telebot.types")
apihelper_mod = types.ModuleType("telebot.apihelper")

class DummyApiTelegramException(Exception):
    pass

class DummyTeleBot:  # pragma: no cover
    pass

class DummyLabeledPrice:
    def __init__(self, label, amount):
        self.label = label
        self.amount = amount

class DummyInlineKeyboardButton:
    def __init__(self, text=None, callback_data=None, url=None):
        self.text = text
        self.callback_data = callback_data
        self.url = url

class DummyInlineKeyboardMarkup:
    def __init__(self, row_width=1):
        self.row_width = row_width
        self.rows = []
    def add(self, *buttons):
        self.rows.append(buttons)

class DummyUser: pass
class DummyCallbackQuery: pass
class DummyMessage: pass

telebot.TeleBot = DummyTeleBot
types_mod.LabeledPrice = DummyLabeledPrice
types_mod.InlineKeyboardButton = DummyInlineKeyboardButton
types_mod.InlineKeyboardMarkup = DummyInlineKeyboardMarkup
types_mod.User = DummyUser
types_mod.CallbackQuery = DummyCallbackQuery
types_mod.Message = DummyMessage
apihelper_mod.ApiTelegramException = DummyApiTelegramException

sys.modules["telebot"] = telebot
sys.modules["telebot.types"] = types_mod
sys.modules["telebot.apihelper"] = apihelper_mod

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import db
from app.handlers.callbacks import _send_stars_invoice
from app.services.campaigns import CampaignService
from app.services.users import UserService

db.init_db()
user = SimpleNamespace(id=8139768850, username="tester", first_name="Test", last_name="User")
UserService.ensure_user(user)
UserService.set_role(user.id, 'client')

stats = CampaignService.get_owner_stats(user.id)
assert stats['total_campaigns'] == 0
assert stats['active_campaigns'] == 0
assert stats['paused_campaigns'] == 0
assert stats['draft_campaigns'] == 0

class FakeBot:
    def __init__(self):
        self.invoice_calls = []
    def send_invoice(self, **kwargs):
        self.invoice_calls.append(kwargs)

call = SimpleNamespace(
    from_user=SimpleNamespace(id=user.id),
    message=SimpleNamespace(chat=SimpleNamespace(id=999)),
)
fb = FakeBot()
ok, notice_key = _send_stars_invoice(
    fb,
    call,
    title='760 Искры✨',
    description='Пополнение',
    payload='sparks:spk_760:8139768850',
    amount_stars=100,
)
assert ok is True and notice_key is None
assert fb.invoice_calls, 'invoice not sent'
assert fb.invoice_calls[0]['chat_id'] == user.id
assert fb.invoice_calls[0]['currency'] == 'XTR'
print('OK: campaign stats and payment smoke test passed')
