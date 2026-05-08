from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.economy import calculate_campaign_pricing, completion_speed_explanation, recommend_unit_prices
from app.version import APP_STAGE, APP_VERSION

assert APP_VERSION.startswith('Boostora v2.')
assert isinstance(APP_STAGE, str) and APP_STAGE

advisory = recommend_unit_prices('channel_subscribe', 100)
assert advisory['client_floor_price'] >= advisory['performer_floor_reward'] + 2
assert advisory['recommended_unit_price'] > advisory['client_floor_price']
assert advisory['fast_unit_price'] > advisory['recommended_unit_price']
assert advisory['priority_unit_price'] > advisory['fast_unit_price']

base = calculate_campaign_pricing('channel_subscribe', 100, None)
recommended = calculate_campaign_pricing('channel_subscribe', 100, advisory['recommended_unit_price'])
fast = calculate_campaign_pricing('channel_subscribe', 100, advisory['fast_unit_price'])

assert base['speed_index'] <= recommended['speed_index'] <= fast['speed_index']
assert base['budget_total'] < recommended['budget_total'] < fast['budget_total']
assert recommended['price_position_percent'] > base['price_position_percent']
assert 'медленнее' in completion_speed_explanation(base['speed_index'], base['client_unit_price'], advisory['recommended_unit_price'], 'ru')

print('OK: economy advisor smoke test passed')
