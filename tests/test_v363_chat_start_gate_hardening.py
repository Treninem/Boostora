from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_v363_chat_start_gate_hardening_in_isolated_process() -> None:
    script = r'''
import os, sys, tempfile, types
from pathlib import Path
from types import SimpleNamespace
root=Path(sys.argv[1]); sys.path.insert(0,str(root))
os.environ.update({
    'BOT_TOKEN':'123456:TESTTOKEN','ADMIN_IDS':'999','BOT_DATA_DIR':tempfile.mkdtemp(prefix='boostora-v363-'),
    'DB_PATH':'test.db','WEBAPP_ENABLED':'0','LEGACY_DB_MIRROR_ENABLED':'0','SUPPORT_USERNAME':'@BoostoraTestBot',
    'CHAT_START_GATE_ENABLED':'1','CHAT_START_GATE_CHAT_REF':'@Boostorachat',
    'CHAT_START_GATE_CHAT_LINK':'https://t.me/Boostorachat','CHAT_START_GATE_START_PARAMETER':'chat_access',
    'CHAT_START_GATE_NOTICE_COOLDOWN_SECONDS':'60',
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

db.init_db(); db.upsert_user(100,'ivan','Иван',None)
class Bot:
    def __init__(self): self.deleted=[]; self.sent=[]; self.next_id=700; self.get_me_calls=0; self.fail_delete=False
    def get_me(self): self.get_me_calls += 1; return SimpleNamespace(username='BoostoraTestBot')
    def delete_message(self,chat_id,message_id):
        if self.fail_delete: raise RuntimeError('no delete rights')
        self.deleted.append((int(chat_id),int(message_id)))
    def send_message(self,chat_id,text,**kwargs):
        self.next_id += 1
        msg=SimpleNamespace(chat=SimpleNamespace(id=chat_id),message_id=self.next_id)
        self.sent.append((int(chat_id),text,kwargs,msg.message_id)); return msg
bot=Bot(); chat=SimpleNamespace(id=-100123,username='BoostoraChat',type='supergroup')
user=SimpleNamespace(id=100,is_bot=False,first_name='Иван',username='ivan')
def msg(mid): return SimpleNamespace(chat=chat,from_user=user,message_id=mid,content_type='text')
ChatStartGateService.block_message(bot,msg(1))
ChatStartGateService.block_message(bot,msg(2))
assert bot.deleted == [(-100123,1),(-100123,2)], bot.deleted
assert len(bot.sent) == 1
assert bot.get_me_calls == 1
# Force a fresh notice and simulate missing delete rights.
db.execute('DELETE FROM chat_start_gate_notices WHERE chat_id=? AND user_id=?',(-100123,100))
bot.fail_delete=True
ChatStartGateService.block_message(bot,msg(3))
assert len(bot.sent) == 2
assert 'ваше сообщение удалено' not in bot.sent[-1][1]
assert 'доступ к сообщениям пока закрыт' in bot.sent[-1][1]
print('V363_CHAT_GATE_HARDENING_OK')
'''
    result = subprocess.run([sys.executable, '-c', script, str(ROOT)], cwd=ROOT, text=True, capture_output=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'V363_CHAT_GATE_HARDENING_OK' in result.stdout


def test_v363_configuration_and_release_contract() -> None:
    config = (ROOT / 'app' / 'config.py').read_text(encoding='utf-8')
    env = (ROOT / '.env.example').read_text(encoding='utf-8')
    version = (ROOT / 'app' / 'version.py').read_text(encoding='utf-8')
    service = (ROOT / 'app' / 'services' / 'chat_start_gate.py').read_text(encoding='utf-8')
    assert 'chat_start_gate_notice_cooldown_seconds' in config
    assert 'CHAT_START_GATE_NOTICE_COOLDOWN_SECONDS=15' in env
    assert '_NOTICE_LOCKS' in service and '_notice_is_recent' in service
    assert "APP_VERSION = 'Boostora v3.6.4'" in version
