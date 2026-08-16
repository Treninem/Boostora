from __future__ import annotations

from collections import Counter
import threading
import time
from typing import Any


class RuntimeMetrics:
    """Small bounded in-memory telemetry without storing request payloads or user ids."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._started = time.monotonic()
        self._requests = 0
        self._errors = 0
        self._rate_limited = 0
        self._api_queries = 0
        self._idempotent_replays = 0
        self._operations: Counter[str] = Counter()

    def record_request(self, *, error: bool = False) -> None:
        with self._lock:
            self._requests += 1
            if error:
                self._errors += 1

    def record_api(self, operation: str, *, rate_limited: bool = False, replayed: bool = False, error: bool = False) -> None:
        normalized = str(operation or 'unknown').strip().lower()[:80] or 'unknown'
        with self._lock:
            self._api_queries += 1
            self._operations[normalized] += 1
            if rate_limited:
                self._rate_limited += 1
            if replayed:
                self._idempotent_replays += 1
            if error:
                self._errors += 1
            if len(self._operations) > 256:
                self._operations = Counter(dict(self._operations.most_common(128)))

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                'uptime_seconds': max(0, int(time.monotonic() - self._started)),
                'requests': self._requests,
                'api_queries': self._api_queries,
                'errors': self._errors,
                'rate_limited': self._rate_limited,
                'idempotent_replays': self._idempotent_replays,
                'top_operations': dict(self._operations.most_common(10)),
            }


RUNTIME_METRICS = RuntimeMetrics()
