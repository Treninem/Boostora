import os
import sys
import tempfile
from pathlib import Path
import random

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault('BOT_TOKEN', '123:abc')
store = Path(tempfile.mkdtemp(prefix='boostora_trust_'))
os.environ['BOT_DATA_DIR'] = str(store)
os.environ['DB_PATH'] = f'trust_{random.randint(1000,999999)}.db'

from app.db import init_db, execute
from app.services.trust import TrustService

PERFORMER_ID = random.randint(100000, 199999)
OWNER_ID = PERFORMER_ID + 1

init_db()
execute("INSERT INTO users (user_id, username, first_name, language_code, role, status, risk_score) VALUES (?,?,?,?,?,?,?)", (OWNER_ID,'owner','Owner','ru','client','active',0))
execute("INSERT INTO wallets (user_id, internal_balance, bonus_balance, available_balance, hold_balance, lifetime_earned, total_withdrawn) VALUES (?,?,?,?,?,?,?)", (OWNER_ID,0,0,0,0,0,0))
execute("INSERT INTO users (user_id, username, first_name, language_code, role, status, risk_score) VALUES (?,?,?,?,?,?,?)", (PERFORMER_ID,'u','U','ru','performer','active',5))
execute("INSERT INTO wallets (user_id, internal_balance, bonus_balance, available_balance, hold_balance, lifetime_earned, total_withdrawn) VALUES (?,?,?,?,?,?,?)", (PERFORMER_ID,0,0,0,0,0,0))
campaign_id = execute("INSERT INTO campaigns (owner_user_id, title, task_type, target_url, reward_amount, unit_price, reward_budget_total, service_fee_total, is_funded, total_quantity, budget_total, status) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (OWNER_ID,'T','channel_subscribe','@x',10,14,1000,400,1,100,1400,'active'))
for _ in range(12):
    execute("INSERT INTO task_submissions (campaign_id, performer_user_id, status) VALUES (?, ?, 'approved')", (campaign_id, PERFORMER_ID))
execute("INSERT INTO task_submissions (campaign_id, performer_user_id, status) VALUES (?, ?, 'rejected')", (campaign_id, PERFORMER_ID))
summary = TrustService.summary(PERFORMER_ID, language='ru')
assert summary['score'] >= 50, summary
assert summary['approval_rate'] >= 90, summary
print('OK: trust engine smoke test passed')
