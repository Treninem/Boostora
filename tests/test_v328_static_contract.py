from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / 'miniapp_example' / 'index.html').read_text(encoding='utf-8')
WEB = (ROOT / 'app' / 'webapp.py').read_text(encoding='utf-8')
START = (ROOT / 'app' / 'handlers' / 'start.py').read_text(encoding='utf-8')
KEYBOARDS = (ROOT / 'app' / 'keyboards' / 'inline.py').read_text(encoding='utf-8')
VERSION = (ROOT / 'app' / 'version.py').read_text(encoding='utf-8')


def test_current_static_contract() -> None:
    assert "Boostora v3.6.6" in VERSION
    assert "fetch('/api/miniapp/query'" in HTML
    assert "fetch('/api/miniapp/action'" not in HTML
    assert "sendData(" not in HTML
    for page in ('home', 'services', 'work', 'wallet', 'profile'):
        assert f'data-page="{page}"' in HTML
    assert "session.access.is_admin" in HTML
    assert "session.access.is_owner" in HTML
    assert "owner.get" in HTML
    assert "admin.get" in HTML
    assert "'/api/miniapp/query'" in WEB
    assert "'/api/miniapp/action'" in WEB  # compatibility endpoint only
    assert "UserService.is_owner(user_id)" in WEB
    assert "UserService.is_admin(user_id)" in WEB
    assert "WEBAPP_START_PREFIX = 'wa_'" in START
    assert "if not UserService.is_admin(message.from_user.id):" in START
    assert KEYBOARDS.count("if UserService.is_admin(user_id):") >= 4
