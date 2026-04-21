import os
import sys
import tempfile
import types
from pathlib import Path
from types import SimpleNamespace

workdir = Path(tempfile.mkdtemp(prefix='boostora_regression_'))
os.environ['BOT_TOKEN'] = '123:abc'
os.environ['DB_PATH'] = str(workdir / 'regression.db')
os.environ['ADMIN_IDS'] = '2097006037'
os.environ.setdefault('REQUIRED_CHAT_ID', '@Boostorachat')
os.environ.setdefault('REQUIRED_CHAT_INVITE_LINK', 'https://t.me/Boostorachat')

telebot = types.ModuleType('telebot')
types_mod = types.ModuleType('telebot.types')
apihelper_mod = types.ModuleType('telebot.apihelper')

class DummyApiTelegramException(Exception):
    pass

class DummyTeleBot:
    def __init__(self, *args, **kwargs):
        self.handlers = []
    def message_handler(self, *args, **kwargs):
        def deco(fn):
            self.handlers.append(fn)
            return fn
        return deco
    def callback_query_handler(self, *args, **kwargs):
        def deco(fn):
            self.handlers.append(fn)
            return fn
        return deco
    def pre_checkout_query_handler(self, *args, **kwargs):
        def deco(fn):
            self.handlers.append(fn)
            return fn
        return deco
    def send_message(self, *args, **kwargs):
        class M: message_id = 1
        return M()
    def edit_message_text(self, *args, **kwargs):
        return None
    def delete_message(self, *args, **kwargs):
        return None
    def answer_callback_query(self, *args, **kwargs):
        return None
    def answer_pre_checkout_query(self, *args, **kwargs):
        return None
    def send_invoice(self, *args, **kwargs):
        sp = kwargs.get('start_parameter')
        assert sp and ':' not in sp and len(sp) <= 64
        return None
    def remove_webhook(self, *args, **kwargs):
        return None
    def infinity_polling(self, *args, **kwargs):
        return None

class DummyInlineKeyboardMarkup:
    def __init__(self, row_width=1): self.rows=[]
    def add(self, *buttons): self.rows.append(buttons)
class DummyInlineKeyboardButton:
    def __init__(self, text=None, callback_data=None, url=None): self.text=text; self.callback_data=callback_data; self.url=url
class DummyReplyKeyboardMarkup:
    def __init__(self, *args, **kwargs): self.rows=[]
    def row(self,*buttons): self.rows.append(buttons)
class DummyKeyboardButton:
    def __init__(self, text=None): self.text=text
class DummyLabeledPrice:
    def __init__(self, label, amount): self.label=label; self.amount=amount
class DummyMessage: pass
class DummyCallbackQuery: pass
class DummyPreCheckoutQuery: pass
class DummyUser: pass

telebot.TeleBot = DummyTeleBot
types_mod.InlineKeyboardMarkup = DummyInlineKeyboardMarkup
types_mod.InlineKeyboardButton = DummyInlineKeyboardButton
types_mod.ReplyKeyboardMarkup = DummyReplyKeyboardMarkup
types_mod.KeyboardButton = DummyKeyboardButton
types_mod.LabeledPrice = DummyLabeledPrice
types_mod.Message = DummyMessage
types_mod.CallbackQuery = DummyCallbackQuery
types_mod.PreCheckoutQuery = DummyPreCheckoutQuery
types_mod.User = DummyUser
apihelper_mod.ApiTelegramException = DummyApiTelegramException

sys.modules['telebot'] = telebot
sys.modules['telebot.types'] = types_mod
sys.modules['telebot.apihelper'] = apihelper_mod

from app import db
from app.router import _build_campaign_input_text, _build_task_detail_text, _build_wallet_text, _build_profile_text
from app.handlers.callbacks import _send_stars_invoice
from app.services.client_campaigns import ClientCampaignService
from app.services.campaigns import CampaignService
from app.services.performer import PerformerService
from app.services.users import UserService

db.init_db()
owner = SimpleNamespace(id=11, username='client', first_name='Client', last_name='Owner')
worker = SimpleNamespace(id=12, username='worker', first_name='Worker', last_name='User')
UserService.ensure_user(owner)
UserService.ensure_user(worker)
UserService.set_role(11, 'client')
UserService.set_role(12, 'performer')

ok, _ = ClientCampaignService.start_draft(11, 'post_like')
assert ok
assert 'Лайк поста' in _build_campaign_input_text(11, 'target')
ok, _, _ = ClientCampaignService.consume_target(11, '@chan')
assert ok
ok, _, _ = ClientCampaignService.consume_quantity(11, '5')
assert ok
ok, _, _ = ClientCampaignService.consume_price(11, '10')
assert ok
ok, _, campaign_id = ClientCampaignService.finalize_draft(11, True)
assert ok and campaign_id
text, meta = _build_task_detail_text(12, campaign_id)
assert 'Лайк поста' in text
assert str(meta['target_url']).startswith('https://t.me/')
assert 'Искры✨' in _build_wallet_text(12, 0)
assert 'Искры✨' in _build_profile_text(12)

class DummyCall:
    class UserObj: id = 12
    from_user = UserObj()
call = DummyCall()
bot = DummyTeleBot()
ok, err = _send_stars_invoice(bot, call, title='Пополнение Искр', description='Пакет', payload='sparks:spk_760:12', amount_stars=100)
assert ok and err is None
print('OK: regression full UI smoke test passed')
