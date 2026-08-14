from __future__ import annotations

import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_v370_simplifies_primary_navigation() -> None:
    html = (ROOT / 'miniapp_example' / 'index.html').read_text(encoding='utf-8')
    nav = re.search(r'<nav class="bottom".*?</nav>', html, flags=re.S)
    assert nav, 'bottom nav missing'
    assert nav.group(0).count('data-page=') == 3
    assert 'data-page="home"' in nav.group(0)
    assert 'data-page="work"' in nav.group(0)
    assert 'data-page="cabinet"' in nav.group(0)
    assert 'data-page="wallet"' not in nav.group(0)
    assert 'data-page="profile"' not in nav.group(0)
    assert 'data-page="services"' not in nav.group(0)
    assert 'renderCabinet()' in html
    assert "['wallet','profile','services','management'].includes(name)?'cabinet':name" in html


def test_v370_frontend_has_safe_request_dedup_and_read_retry_only() -> None:
    html = (ROOT / 'miniapp_example' / 'index.html').read_text(encoding='utf-8')
    assert 'const inFlightRequests = new Map()' in html
    assert 'const READ_ONLY_OPS = new Set(' in html
    assert "const attempts=READ_ONLY_OPS.has(operation)?2:1" in html
    assert 'AbortController' in html
    assert 'inFlightRequests.has(requestKey)' in html


def test_v370_server_serializes_mutations_and_exposes_readiness() -> None:
    web = (ROOT / 'app' / 'webapp.py').read_text(encoding='utf-8')
    assert 'MINIAPP_USER_LOCK_STRIPES = 64' in web
    assert '_READ_ONLY_MINIAPP_OPERATIONS' in web
    assert 'with lock:' in web
    assert "'/health/ready'" in web
    assert "server_version = 'BoostoraWeb/3.7.0'" in web


def test_v370_sqlite_transaction_core_is_hardened() -> None:
    source = (ROOT / 'app' / 'db.py').read_text(encoding='utf-8')
    assert "connection.execute('BEGIN IMMEDIATE')" in source
    assert "connection.execute('PRAGMA synchronous = NORMAL')" in source
    assert "connection.execute('PRAGMA wal_autocheckpoint = 1000')" in source
    assert 'def health_status()' in source


def test_v370_health_snapshot_runs_against_real_test_db() -> None:
    os.environ.update({
        'BOT_TOKEN': '123456:TESTTOKEN',
        'ADMIN_IDS': '999',
        'BOT_DATA_DIR': tempfile.mkdtemp(prefix='boostora-v370-health-'),
        'DB_PATH': 'test.db',
        'WEBAPP_ENABLED': '0',
        'LEGACY_DB_MIRROR_ENABLED': '0',
        'BOOSTORE_ENABLED': '0',
    })
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from app import db
    from app.services.system_health import SystemHealthService

    db.init_db()
    SystemHealthService.record_startup()
    SystemHealthService.record_heartbeat()
    health = SystemHealthService.snapshot()
    assert health['database']['ok'] is True
    assert health['worker']['ok'] is True
    assert health['status'] in {'ok', 'warning'}
    assert health['version'] == 'Boostora v3.7.0'


def test_v370_owner_audit_understands_current_contract() -> None:
    source = (ROOT / 'app' / 'services' / 'final_audit.py').read_text(encoding='utf-8')
    assert "APP_STAGE == 'simplified_shell_hardened_core'" in source
    assert "nav.count('data-page=') == 3" in source
    assert "'embedded_mini_app_runtime'" in source
