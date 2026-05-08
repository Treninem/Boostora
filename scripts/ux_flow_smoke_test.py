from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.ux_flow import broadcast_step_status, campaign_step_status
from app.texts import TEXTS
from app.version import APP_STAGE, APP_VERSION

assert APP_VERSION.startswith('Boostora v2.')
assert isinstance(APP_STAGE, str) and APP_STAGE
assert campaign_step_status('target') == '● ○ ○ · Шаг 1/3 · Цель задания'
assert campaign_step_status('quantity') == '● ● ○ · Шаг 2/3 · Количество'
assert campaign_step_status('price') == '● ● ● · Шаг 3/3 · Цена за выполнение'
assert broadcast_step_status('text') == '● ○ ○ · Шаг 1/3 · Текст рекламы'
assert broadcast_step_status('schedule', language='en') == '● ● ● · Step 3/3 · Schedule'
assert '{step_status}' in TEXTS['ru']['campaign_input_screen']
assert '{step_status}' in TEXTS['ru']['broadcast_text_screen']
assert 'v2.1.0' in APP_VERSION
print('OK: ux flow smoke test passed')
