from __future__ import annotations

from collections import OrderedDict, deque
from dataclasses import dataclass
import os
import threading
import time
from typing import Any, Callable


@dataclass(frozen=True)
class RateDecision:
    allowed: bool
    remaining: int
    retry_after_seconds: int = 0


@dataclass(frozen=True)
class CachedResponse:
    status: int
    payload: dict[str, Any]


class ApiGuard:
    """In-process protection for Mini App API calls.

    The guard deliberately keeps no Telegram init data, usernames, tokens or other
    personal payloads. Rate buckets are keyed only by numeric Telegram user id and
    request class. Idempotency entries are short lived and bounded.
    """

    def __init__(
        self,
        *,
        read_limit: int = 180,
        mutation_limit: int = 45,
        window_seconds: int = 60,
        idempotency_ttl_seconds: int = 180,
        max_idempotency_entries: int = 4096,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.read_limit = max(1, int(read_limit))
        self.mutation_limit = max(1, int(mutation_limit))
        self.window_seconds = max(1, int(window_seconds))
        self.idempotency_ttl_seconds = max(1, int(idempotency_ttl_seconds))
        self.max_idempotency_entries = max(128, int(max_idempotency_entries))
        self._clock = clock
        self._lock = threading.RLock()
        self._buckets: dict[tuple[int, str], deque[float]] = {}
        self._idempotency: OrderedDict[tuple[int, str, str], tuple[float, CachedResponse]] = OrderedDict()

    @staticmethod
    def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
        raw = os.getenv(name, '').strip()
        if not raw:
            return default
        try:
            value = int(raw)
        except ValueError:
            return default
        return min(max(value, minimum), maximum)

    @classmethod
    def from_environment(cls) -> 'ApiGuard':
        return cls(
            read_limit=cls._env_int('BOOSTORA_API_READS_PER_MINUTE', 180, 30, 3000),
            mutation_limit=cls._env_int('BOOSTORA_API_MUTATIONS_PER_MINUTE', 45, 10, 1000),
            window_seconds=cls._env_int('BOOSTORA_API_RATE_WINDOW_SECONDS', 60, 10, 300),
            idempotency_ttl_seconds=cls._env_int('BOOSTORA_IDEMPOTENCY_TTL_SECONDS', 180, 30, 1800),
            max_idempotency_entries=cls._env_int('BOOSTORA_IDEMPOTENCY_CACHE_MAX', 4096, 128, 50000),
        )

    def allow(self, user_id: int, *, read_only: bool) -> RateDecision:
        now = self._clock()
        kind = 'read' if read_only else 'mutation'
        limit = self.read_limit if read_only else self.mutation_limit
        key = (int(user_id), kind)
        cutoff = now - self.window_seconds

        with self._lock:
            bucket = self._buckets.setdefault(key, deque())
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if len(bucket) >= limit:
                retry_after = max(1, int(self.window_seconds - (now - bucket[0])) + 1)
                return RateDecision(False, 0, retry_after)
            bucket.append(now)
            remaining = max(0, limit - len(bucket))
            if not bucket:
                self._buckets.pop(key, None)
            return RateDecision(True, remaining, 0)

    @staticmethod
    def normalize_idempotency_key(raw: Any) -> str:
        if not isinstance(raw, str):
            return ''
        value = raw.strip()
        if not value or len(value) > 128:
            return ''
        if any(ord(ch) < 33 or ord(ch) > 126 for ch in value):
            return ''
        return value

    def _purge_expired_locked(self, now: float) -> None:
        expired = [key for key, (expires_at, _) in self._idempotency.items() if expires_at <= now]
        for key in expired:
            self._idempotency.pop(key, None)
        while len(self._idempotency) > self.max_idempotency_entries:
            self._idempotency.popitem(last=False)

    def lookup(self, user_id: int, operation: str, key: str) -> CachedResponse | None:
        normalized = self.normalize_idempotency_key(key)
        if not normalized:
            return None
        cache_key = (int(user_id), str(operation).lower(), normalized)
        now = self._clock()
        with self._lock:
            self._purge_expired_locked(now)
            entry = self._idempotency.get(cache_key)
            if entry is None:
                return None
            expires_at, response = entry
            if expires_at <= now:
                self._idempotency.pop(cache_key, None)
                return None
            self._idempotency.move_to_end(cache_key)
            return CachedResponse(response.status, dict(response.payload))

    def store(self, user_id: int, operation: str, key: str, *, status: int, payload: dict[str, Any]) -> None:
        normalized = self.normalize_idempotency_key(key)
        if not normalized:
            return
        cache_key = (int(user_id), str(operation).lower(), normalized)
        now = self._clock()
        cached = CachedResponse(int(status), dict(payload))
        with self._lock:
            self._purge_expired_locked(now)
            self._idempotency[cache_key] = (now + self.idempotency_ttl_seconds, cached)
            self._idempotency.move_to_end(cache_key)
            self._purge_expired_locked(now)

    def snapshot(self) -> dict[str, int]:
        now = self._clock()
        with self._lock:
            self._purge_expired_locked(now)
            return {
                'active_rate_buckets': len(self._buckets),
                'idempotency_entries': len(self._idempotency),
                'read_limit': self.read_limit,
                'mutation_limit': self.mutation_limit,
                'window_seconds': self.window_seconds,
            }


GLOBAL_API_GUARD = ApiGuard.from_environment()
