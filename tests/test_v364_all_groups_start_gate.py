from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_v364_all_groups_start_gate_in_isolated_process() -> None:
    script = r'''
import os, sys, tempfile, types
from pathlib import Path
from types import SimpleNamespace
root=Path(sys.argv[1]); sys.path.insert(0,str(root))
os.environ.update({
    'BOT_TOKEN':'123456:TESTTOKEN','ADMIN_IDS':'999','BOT_DATA_DIR':tempfile.mkdtemp(prefix='boostora-v364-'),
    'DB_PATH':'test.db','WEBAPP_ENABLED':'0','LEGACY_DB_MIRROR_ENABLED':'0','SUPPORT_USERNAME':'@BoostoraTestBot',
    'CHAT_START_GATE_ENABLED':'1','CHAT_START_GATE_CHAT_REF':'@Boostorachat',
    'CHAT_START_GATE_CHAT_LINK':'https://t.me/Boostorachat','CHAT_START_GATE_START_PARAMETER':'chat_access',
    'CHAT_START_GATE_NOTICE_COOLDOWN_SECONDS':'15',
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
user=SimpleNamespace(id=100,is_bot=False,first_name='Иван',username='ivan')
for chat in (
    SimpleNamespace(id=-10,username='',type='group'),
    SimpleNamespace(id=-10020,username='OtherPublicGroup',type='supergroup'),
):
    msg=SimpleNamespace(chat=chat,from_user=user,message_id=1,content_type='text')
    assert ChatStartGateService.is_protected_chat(chat)
    assert ChatStartGateService.should_block_message(msg)

assert not ChatStartGateService.is_protected_chat(SimpleNamespace(id=100,username='',type='private'))
assert not ChatStartGateService.is_protected_chat(SimpleNamespace(id=-10030,username='News',type='channel'))

assert ChatStartGateService.mark_started(100)
assert ChatStartGateService.has_started(100)
for chat in (
    SimpleNamespace(id=-10,username='',type='group'),
    SimpleNamespace(id=-10020,username='OtherPublicGroup',type='supergroup'),
):
    msg=SimpleNamespace(chat=chat,from_user=user,message_id=2,content_type='text')
    assert not ChatStartGateService.should_block_message(msg)
print('V364_ALL_GROUPS_GATE_OK')
'''
    result = subprocess.run([sys.executable, '-c', script, str(ROOT)], cwd=ROOT, text=True, capture_output=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'V364_ALL_GROUPS_GATE_OK' in result.stdout


def test_v364_all_groups_release_contract() -> None:
    config = (ROOT / 'app' / 'config.py').read_text(encoding='utf-8')
    service = (ROOT / 'app' / 'services' / 'chat_start_gate.py').read_text(encoding='utf-8')
    env = (ROOT / '.env.example').read_text(encoding='utf-8')
    version = (ROOT / 'app' / 'version.py').read_text(encoding='utf-8')
    assert "return chat_type in {'group', 'supergroup'}" in service
    assert "APP_VERSION = 'Boostora v3.6.4'" in version
