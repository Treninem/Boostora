from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_v362_chat_start_gate_in_isolated_process() -> None:
    script = r'''
import os, sys, tempfile, types
from pathlib import Path
from types import SimpleNamespace
root=Path(sys.argv[1]); sys.path.insert(0,str(root))
os.environ.update({
    'BOT_TOKEN':'123456:TESTTOKEN','ADMIN_IDS':'999','BOT_DATA_DIR':tempfile.mkdtemp(prefix='boostora-v362-'),
    'DB_PATH':'test.db','WEBAPP_ENABLED':'0','LEGACY_DB_MIRROR_ENABLED':'0','SUPPORT_USERNAME':'@BoostoraTestBot',
    'CHAT_START_GATE_ENABLED':'1','CHAT_START_GATE_CHAT_REF':'@Boostorachat',
    'CHAT_START_GATE_CHAT_LINK':'https://t.me/Boostorachat','CHAT_START_GATE_START_PARAMETER':'chat_access',
})
telebot=types.ModuleType('telebot'); t=types.ModuleType('telebot.types')
class InlineKeyboardButton:
    def __init__(self,text,url=None,**kwargs): self.text=text; self.url=url; self.kwargs=kwargs
class InlineKeyboardMarkup:
    def __init__(self,*args,**kwargs): self.buttons=[]
    def add(self,*buttons): self.buttons.extend(buttons); return self
class User: pass
t.InlineKeyboardButton=InlineKeyboardButton; t.InlineKeyboardMarkup=InlineKeyboardMarkup; t.User=User
telebot.types=t; sys.modules['telebot']=telebot; sys.modules['telebot.types']=t

from app import db
from app.services.chat_start_gate import ChatStartGateService

db.init_db()
db.upsert_user(100,'olduser','Старый',None)
columns={r['name'] for r in db.fetch_all('PRAGMA table_info(users)')}
assert 'chat_gate_started_at' in columns
assert not ChatStartGateService.has_started(100), 'existing users must start again after update'

class Bot:
    def __init__(self): self.deleted=[]; self.sent=[]; self.next_id=700
    def get_me(self): return SimpleNamespace(username='BoostoraTestBot')
    def delete_message(self,chat_id,message_id): self.deleted.append((int(chat_id),int(message_id)))
    def send_message(self,chat_id,text,**kwargs):
        self.next_id += 1
        msg=SimpleNamespace(chat=SimpleNamespace(id=chat_id),message_id=self.next_id)
        self.sent.append((int(chat_id),text,kwargs,msg.message_id)); return msg

bot=Bot()
chat=SimpleNamespace(id=-100123,username='BoostoraChat',type='supergroup')
user=SimpleNamespace(id=100,is_bot=False,first_name='Иван <тест>',username='ivan')
message=SimpleNamespace(chat=chat,from_user=user,message_id=55,content_type='text')
assert ChatStartGateService.is_protected_chat(chat)
assert ChatStartGateService.should_block_message(message)
ChatStartGateService.block_message(bot,message)
assert bot.deleted[0]==(-100123,55)
assert len(bot.sent)==1
warning=bot.sent[0]
assert 'ваше сообщение удалено' in warning[1]
assert 'Иван &lt;тест&gt;' in warning[1]
button=warning[2]['reply_markup'].buttons[0]
assert button.text=='🚀 Запустить Boostora'
assert button.url=='https://t.me/BoostoraTestBot?start=chat_access'
notice=db.fetch_one('SELECT * FROM chat_start_gate_notices WHERE chat_id=? AND user_id=?',(-100123,100))
assert int(notice['warning_message_id'])==warning[3]

assert ChatStartGateService.mark_started(100)
assert ChatStartGateService.has_started(100)
ChatStartGateService.clear_notices_for_user(bot,100)
assert (-100123,warning[3]) in bot.deleted
assert not ChatStartGateService.should_block_message(message)
assert not ChatStartGateService.mark_started(100)

bot_user=SimpleNamespace(id=200,is_bot=True,first_name='Bot',username='helper')
bot_message=SimpleNamespace(chat=chat,from_user=bot_user,message_id=99,content_type='text')
assert not ChatStartGateService.should_block_message(bot_message)
other_chat=SimpleNamespace(id=-100999,username='AnotherChat',type='supergroup')
assert ChatStartGateService.is_protected_chat(other_chat)
print('V362_CHAT_START_GATE_OK')
'''
    result = subprocess.run([sys.executable, '-c', script, str(ROOT)], cwd=ROOT, text=True, capture_output=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'V362_CHAT_START_GATE_OK' in result.stdout


def test_v362_handler_priority_and_configuration() -> None:
    start = (ROOT / 'app' / 'handlers' / 'start.py').read_text(encoding='utf-8')
    config = (ROOT / 'app' / 'config.py').read_text(encoding='utf-8')
    env = (ROOT / '.env.example').read_text(encoding='utf-8')
    version = (ROOT / 'app' / 'version.py').read_text(encoding='utf-8')
    assert start.index('def handle_chat_start_gate') < start.index("@bot.message_handler(commands=['start'])")
    assert 'ChatStartGateService.block_message(bot, message)' in start
    assert 'ChatStartGateService.mark_started(message.from_user.id)' in start
    assert "message.chat.type != 'private'" in start
    assert 'CHAT_START_GATE_ENABLED' in config and 'CHAT_START_GATE_CHAT_REF' in config
    assert 'CHAT_START_GATE_ENABLED=1' in env and 'CHAT_START_GATE_CHAT_REF=@Boostorachat' in env
    assert "APP_VERSION = 'Boostora v3.6.6'" in version
    assert "APP_STAGE = 'boostorachat_start_gate'" in version
