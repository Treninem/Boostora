import os
import sys
import types
from types import SimpleNamespace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault('BOT_TOKEN', '123:abc')
os.environ.setdefault('DB_PATH', 'start_profile_wallet_smoke_test.db')

telebot = types.ModuleType('telebot')
telebot.TeleBot = object
telebot_types = types.ModuleType('telebot.types')

class InlineKeyboardButton:
    def __init__(self, text='', callback_data=None, url=None):
        self.text = text
        self.callback_data = callback_data
        self.url = url

class InlineKeyboardMarkup:
    def __init__(self, *args, **kwargs):
        self.rows = []
    def add(self, *args):
        self.rows.append(args)
    def row(self, *args):
        self.rows.append(args)

class ReplyKeyboardMarkup:
    def __init__(self, *args, **kwargs):
        self.rows = []
    def row(self, *args):
        self.rows.append(args)

class KeyboardButton:
    def __init__(self, text=''):
        self.text = text

class Message:
    pass

class CallbackQuery:
    pass

class User:
    pass

telebot_types.InlineKeyboardButton = InlineKeyboardButton
telebot_types.InlineKeyboardMarkup = InlineKeyboardMarkup
telebot_types.ReplyKeyboardMarkup = ReplyKeyboardMarkup
telebot_types.KeyboardButton = KeyboardButton
telebot_types.Message = Message
telebot_types.CallbackQuery = CallbackQuery
telebot_types.User = User
sys.modules.setdefault('telebot', telebot)
sys.modules.setdefault('telebot.types', telebot_types)

from app import db
from app.router import SCREEN_PROFILE, SCREEN_WALLET, render_entry, render_screen
from app.services.users import UserService


def main() -> None:
    db_path = os.environ['DB_PATH']
    if os.path.exists(db_path):
        os.remove(db_path)
    db.init_db()

    class FakeMessage(Message):
        def __init__(self):
            self.chat = SimpleNamespace(id=1, username=None)
            self.from_user = SimpleNamespace(
                id=2097006037,
                is_bot=False,
                first_name='Owner',
                last_name=None,
                username='owner',
                language_code='ru',
            )
            self.message_id = 10

    class FakeBot:
        def __init__(self):
            self.calls = []
        def send_message(self, chat_id, text, reply_markup=None):
            self.calls.append(('send', chat_id, text))
            return SimpleNamespace(message_id=len(self.calls) + 100)
        def edit_message_text(self, chat_id, message_id, text, reply_markup=None):
            self.calls.append(('edit', chat_id, message_id, text))
            return None
        def get_chat_member(self, chat_id, user_id):
            return SimpleNamespace(status='member')

    bot = FakeBot()
    message = FakeMessage()
    UserService.ensure_user(message.from_user)
    render_entry(bot, message, force_language=True)
    render_screen(bot, message, SCREEN_PROFILE)
    render_screen(bot, message, SCREEN_WALLET)
    if len(bot.calls) < 3:
        raise RuntimeError('Expected language, profile and wallet renders')
    print('OK: start/profile/wallet smoke test passed')


if __name__ == '__main__':
    main()
