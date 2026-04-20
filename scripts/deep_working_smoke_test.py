import os
import sys
import tempfile
import types
from pathlib import Path
from types import SimpleNamespace

# Configure isolated environment before importing the app.
workdir = Path(tempfile.mkdtemp(prefix='boostora_smoke_'))
os.environ['BOT_TOKEN'] = '123:abc'
os.environ['DB_PATH'] = str(workdir / 'smoke.db')
os.environ['ADMIN_IDS'] = '2097006037'
os.environ.setdefault('REQUIRED_CHAT_ID', '@Boostorachat')
os.environ.setdefault('REQUIRED_CHAT_INVITE_LINK', 'https://t.me/Boostorachat')

# Minimal telebot stub for import-time dependencies.
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
        return None
    def edit_message_text(self, *args, **kwargs):
        return None
    def delete_message(self, *args, **kwargs):
        return None
    def answer_callback_query(self, *args, **kwargs):
        return None
    def answer_pre_checkout_query(self, *args, **kwargs):
        return None
    def send_invoice(self, *args, **kwargs):
        return None
    def remove_webhook(self, *args, **kwargs):
        return None
    def infinity_polling(self, *args, **kwargs):
        return None

class DummyInlineKeyboardMarkup:
    def __init__(self, row_width=1):
        self.row_width = row_width
        self.rows = []
    def add(self, *buttons):
        self.rows.append(buttons)

class DummyInlineKeyboardButton:
    def __init__(self, text=None, callback_data=None, url=None):
        self.text = text
        self.callback_data = callback_data
        self.url = url

class DummyLabeledPrice:
    def __init__(self, label, amount):
        self.label = label
        self.amount = amount

class DummyMessage: pass
class DummyCallbackQuery: pass
class DummyPreCheckoutQuery: pass
class DummyUser: pass

telebot.TeleBot = DummyTeleBot
types_mod.InlineKeyboardMarkup = DummyInlineKeyboardMarkup
types_mod.InlineKeyboardButton = DummyInlineKeyboardButton
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
from app.router import (
    _build_campaign_card_text,
    _build_campaign_preview_text,
    _build_campaigns_text,
    _build_history_text,
    _build_profile_text,
    _build_rewards_text,
    _build_stats_text,
    _build_vip_text,
    _build_wallet_text,
)
from app.services.campaigns import CampaignService
from app.services.client_campaigns import ClientCampaignService
from app.services.performer import PerformerService
from app.services.users import UserService
from app.services.wallets import WalletService
from app.services.payments import parse_payload
from app.handlers.start import register_start_handlers
from app.handlers.callbacks import register_callback_handlers

db.init_db()

owner = SimpleNamespace(id=1, username='owner', first_name='Owner', last_name='Bot')
worker = SimpleNamespace(id=2, username='worker', first_name='Worker', last_name='User')
UserService.ensure_user(owner)
UserService.ensure_user(worker)
UserService.set_role(1, 'client')
UserService.set_role(2, 'performer')

# New user bonus exists and is bonus-only.
summary_owner = WalletService.get_summary(1)
assert summary_owner['bonus_balance'] == 300, summary_owner
assert summary_owner['internal_balance'] == 0, summary_owner

# Build screens that used to crash.
assert 'Искры✨' in _build_profile_text(2)
assert 'Кошелёк' in _build_wallet_text(1, 0)
assert 'Стартовый бонус' in _build_history_text(1)
assert 'VIP' in _build_vip_text(1)
assert 'Telegram Premium' in _build_rewards_text(1)

# Campaign creation flow.
ok, key = ClientCampaignService.start_draft(1, 'channel_subscribe')
assert ok and key == 'campaign_type_saved'
ok, key, _ = ClientCampaignService.consume_target(1, '@demochannel')
assert ok, key
ok, key, _ = ClientCampaignService.consume_quantity(1, '10')
assert ok, key
ok, key, _ = ClientCampaignService.consume_price(1, '28')
assert ok, key
preview = _build_campaign_preview_text(1)
assert 'Ваша цена за 1' in preview
ok, key, campaign_id = ClientCampaignService.finalize_draft(1, launch_now=True)
assert ok and campaign_id, key
campaign = CampaignService.get_owned_campaign(1, campaign_id)
assert campaign is not None and str(campaign['status']) == 'active'
assert int(campaign['is_funded']) == 1
assert int(WalletService.get_summary(1)['campaign_balance']) == 300 - int(campaign['budget_total'])
assert 'Задание #' in _build_campaign_card_text(1, campaign_id)
assert 'Аналитика' in _build_stats_text(1)
assert 'Ваши задания' in _build_campaigns_text(1, CampaignService.get_campaigns_for_owner(1))

# Performer flow.
tasks = PerformerService.list_available_tasks(2)
assert len(tasks) == 1
ok, key, submission_id = PerformerService.take_task(2, campaign_id)
assert ok and submission_id, key
ok, key, _ = PerformerService.submit_proof(2, submission_id, 'https://t.me/demochannel/1')
assert ok, key
wallet_worker = WalletService.get_summary(2)
assert wallet_worker['hold_balance'] > 0
history_worker = _build_history_text(2)
assert 'Награда за задание в холде' in history_worker

# Payment payloads.
assert parse_payload('sparks:spk_760:2') == ('sparks', 'spk_760', 2)
assert parse_payload('vip:vipstars7:2') == ('vip', 'vipstars7', 2)

# Handler registration does not crash.
bot = DummyTeleBot()
register_start_handlers(bot)
register_callback_handlers(bot)
assert bot.handlers, 'handlers not registered'

print('OK: deep working smoke test passed')
