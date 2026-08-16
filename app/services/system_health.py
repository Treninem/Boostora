from __future__ import annotations

from datetime import datetime
from pathlib import Path
import shutil
from typing import Any

from app import db
from app.config import settings
from app.services.api_guard import GLOBAL_API_GUARD
from app.services.runtime_metrics import RUNTIME_METRICS
from app.time_utils import utcnow
from app.version import APP_VERSION


class SystemHealthService:
    """Local health view used by readiness and the owner-only diagnostics screen."""

    HEARTBEAT_KEY = 'runtime_background_heartbeat'
    STARTED_KEY = 'runtime_started_at'

    @staticmethod
    def _set_meta(key: str, value: str) -> None:
        # Heartbeats are runtime metadata; they do not need legacy DB mirroring.
        with db.get_connection() as connection:
            connection.execute(
                """INSERT INTO app_meta (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)
                   ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=CURRENT_TIMESTAMP""",
                (key, value),
            )

    @classmethod
    def record_startup(cls) -> None:
        cls._set_meta(cls.STARTED_KEY, utcnow().isoformat(timespec='seconds'))

    @classmethod
    def record_heartbeat(cls) -> None:
        cls._set_meta(cls.HEARTBEAT_KEY, utcnow().isoformat(timespec='seconds'))

    @staticmethod
    def _meta(key: str) -> str:
        row = db.fetch_one('SELECT value FROM app_meta WHERE key=?', (key,))
        return str(row['value'] or '') if row else ''

    @staticmethod
    def _age_seconds(value: str) -> int | None:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None
        return max(0, int((utcnow() - parsed).total_seconds()))

    @classmethod
    def snapshot(cls) -> dict[str, Any]:
        database = db.health_status()
        data_path = Path(settings.data_dir)
        try:
            data_path.mkdir(parents=True, exist_ok=True)
            usage = shutil.disk_usage(data_path)
            disk = {
                'ok': usage.free >= 128 * 1024 * 1024,
                'free_bytes': int(usage.free),
                'total_bytes': int(usage.total),
                'used_percent': round((usage.used / usage.total) * 100, 1) if usage.total else 0.0,
            }
        except Exception as exc:
            disk = {
                'ok': False,
                'free_bytes': 0,
                'total_bytes': 0,
                'used_percent': 0.0,
                'error': exc.__class__.__name__,
            }

        heartbeat = cls._meta(cls.HEARTBEAT_KEY)
        heartbeat_age = cls._age_seconds(heartbeat)
        worker_limit = max(180, int(settings.background_worker_interval_seconds) * 3)
        worker_ok = heartbeat_age is not None and heartbeat_age <= worker_limit

        counts: dict[str, int] = {}
        for key, query in {
            'active_campaigns': "SELECT COUNT(*) AS n FROM campaigns WHERE status='active'",
            'active_holds': "SELECT COUNT(*) AS n FROM holds WHERE status='active'",
            'manual_review': "SELECT COUNT(*) AS n FROM task_submissions WHERE status='manual_review'",
            'active_groups': "SELECT COUNT(*) AS n FROM bot_chats WHERE is_active=1 AND chat_type IN ('group','supergroup')",
        }.items():
            try:
                row = db.fetch_one(query)
                counts[key] = int(row['n'] or 0) if row else 0
            except Exception:
                counts[key] = -1

        critical = not bool(database.get('ok')) or not bool(disk.get('ok'))
        warning = not worker_ok
        return {
            'status': 'critical' if critical else 'warning' if warning else 'ok',
            'version': APP_VERSION,
            'database': database,
            'disk': disk,
            'worker': {
                'ok': worker_ok,
                'heartbeat_at': heartbeat or None,
                'age_seconds': heartbeat_age,
                'max_age_seconds': worker_limit,
            },
            'started_at': cls._meta(cls.STARTED_KEY) or None,
            'counts': counts,
            'gateway': GLOBAL_API_GUARD.snapshot(),
            'runtime': RUNTIME_METRICS.snapshot(),
            'provider_enabled': bool(settings.boostore_enabled),
            'webapp_enabled': bool(settings.webapp_enabled),
        }
