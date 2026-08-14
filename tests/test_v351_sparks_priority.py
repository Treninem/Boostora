from pathlib import Path

from app.services.economy import INTERNAL_CURRENCY_NAME_RU
from app.services.runtime_settings import RuntimeSettingsService
from app.version import APP_VERSION, APP_STAGE

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / 'miniapp_example' / 'index.html').read_text(encoding='utf-8')
TEXTS = (ROOT / 'app' / 'texts.py').read_text(encoding='utf-8')
KEYBOARDS = (ROOT / 'app' / 'keyboards' / 'inline.py').read_text(encoding='utf-8')


def test_version_and_currency_name():
    assert APP_VERSION == 'Boostora v3.7.0'
    assert APP_STAGE == 'simplified_shell_hardened_core'
    assert INTERNAL_CURRENCY_NAME_RU == 'Искры'
    assert 'Кредитов за 1 Star' not in [spec.label for spec in RuntimeSettingsService.SPECS.values()]
    assert any('Искр за 1 Star' == spec.label for spec in RuntimeSettingsService.SPECS.values())


def test_miniapp_core_precedes_optional_catalogue():
    nav = HTML.split('<nav class="bottom"', 1)[1].split('</nav>', 1)[0]
    assert nav.index('data-page="work"') < nav.index('data-page="cabinet"')
    assert 'data-page="services"' not in nav
    assert 'Сеть рекламных размещений' in HTML
    assert 'Зарабатывай Искры' in HTML
    assert 'Дополнительные услуги' in HTML
    assert '>Кабинет</button>' in HTML
    assert 'всё второстепенное здесь' in HTML


def test_user_visible_currency_is_sparks():
    visible_forbidden = [
        'Недостаточно кредитов', 'Купить кредиты', 'оплатить кредитами',
        'потрачено кредитов', ' кредитов</', ' кредитов<br>',
    ]
    for item in visible_forbidden:
        assert item not in HTML
    assert 'Недостаточно Искр' in HTML
    assert 'Кошелёк Искр' in HTML


def test_provider_is_secondary_in_bot_navigation():
    assert "'marketplace_button': '🧰 Дополнительные услуги'" in TEXTS
    hub = KEYBOARDS.split('def smart_hub_keyboard', 1)[1].split('def engagement_growth_keyboard', 1)[0]
    assert hub.rfind("'marketplace_button'") > hub.rfind("'community_rules_button'")
