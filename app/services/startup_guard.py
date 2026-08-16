from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import logging
import os
import shutil
import tempfile
from typing import Any

from app import db
from app.config import settings


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class StartupReport:
    ok: bool
    checks: dict[str, bool]
    warnings: tuple[str, ...]

    def public_payload(self) -> dict[str, Any]:
        return {
            'ok': self.ok,
            'checks': dict(self.checks),
            'warnings_count': len(self.warnings),
        }


_LAST_REPORT = StartupReport(False, {'not_run': False}, ('startup guard has not run yet',))


def _data_dir_writable(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        fd, probe = tempfile.mkstemp(prefix='.boostora-write-', dir=str(path))
        os.close(fd)
        os.unlink(probe)
        return True
    except Exception:
        return False


def run_startup_guard(static_root: Path) -> StartupReport:
    global _LAST_REPORT

    warnings: list[str] = []
    data_dir = Path(settings.data_dir)
    checks: dict[str, bool] = {
        'data_dir_writable': _data_dir_writable(data_dir),
        'database': bool(db.health_status().get('ok')),
        'miniapp_index': static_root.joinpath('index.html').is_file(),
        'bot_token_shape': ':' in settings.bot_token and len(settings.bot_token) >= 20,
    }

    try:
        usage = shutil.disk_usage(data_dir)
        checks['disk_free'] = usage.free >= 128 * 1024 * 1024
    except Exception:
        checks['disk_free'] = False

    if settings.mini_app_url and not settings.mini_app_url.lower().startswith('https://'):
        warnings.append('Mini App public URL is not HTTPS')
    if not settings.mini_app_url:
        warnings.append('Mini App public URL is empty')
    if not settings.admin_ids:
        warnings.append('ADMIN_IDS is empty; owner/admin tools may be unavailable')

    critical = ('data_dir_writable', 'database', 'miniapp_index', 'bot_token_shape', 'disk_free')
    ok = all(checks.get(name, False) for name in critical)
    _LAST_REPORT = StartupReport(ok, checks, tuple(warnings))

    if ok:
        LOGGER.info('Boostora startup guard passed%s', f' with {len(warnings)} warning(s)' if warnings else '')
    else:
        failed = ', '.join(name for name in critical if not checks.get(name, False))
        LOGGER.error('Boostora startup guard found critical readiness problems: %s', failed)
    for warning in warnings:
        LOGGER.warning('Startup guard: %s', warning)
    return _LAST_REPORT


def last_startup_report() -> StartupReport:
    return _LAST_REPORT
