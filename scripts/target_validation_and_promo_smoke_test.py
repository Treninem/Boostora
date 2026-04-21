import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db import init_db
from app.services.users import UserService
from app.services.wallets import WalletService
from app.services.client_campaigns import ClientCampaignService
from app.services.bot_chats import BotChatService
from telebot.types import User

class _StubBot:
    class _Me:
        id = 42
    class _Member:
        def __init__(self, status):
            self.status = status
            self.is_member = status in {'member', 'administrator', 'creator'}
    def get_me(self):
        return self._Me()
    def get_chat_member(self, chat_ref, user_id):
        return self._Member('administrator')

def _user(uid: int):
    return User(id=uid, is_bot=False, first_name='Test')

init_db()
UserService.ensure_user(_user(9001))
WalletService.credit_internal_balance(9001, 10000, entry_type='test', note='test')

ok, _ = ClientCampaignService.start_draft(9001, 'channel_subscribe')
assert ok
ok, key, mode = ClientCampaignService.consume_target(9001, '@boostorachat', bot=_StubBot())
assert ok, key
assert mode == 'campaign_quantity'

ok, _ = ClientCampaignService.start_draft(9001, 'mini_app_open')
assert ok
ok, key, _ = ClientCampaignService.consume_target(9001, 'https://t.me/BoostoraBot/app?startapp=promo42', bot=_StubBot())
assert ok, key

BotChatService.upsert_chat(chat_id=-1001, chat_ref='@promochat', title='Promo Chat', chat_type='supergroup', username='promochat')
rows = BotChatService.list_promotable_chats()
assert rows, 'No promotable chats found'
print('OK: target validation and promo smoke test passed')
