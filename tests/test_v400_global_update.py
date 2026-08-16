from __future__ import annotations

from pathlib import Path
import unittest

from app.services.api_guard import ApiGuard


ROOT = Path(__file__).resolve().parents[1]


class MutableClock:
    def __init__(self) -> None:
        self.value = 1000.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


class ApiGuardTests(unittest.TestCase):
    def test_mutation_rate_limit_and_recovery(self) -> None:
        clock = MutableClock()
        guard = ApiGuard(read_limit=3, mutation_limit=2, window_seconds=10, clock=clock)

        self.assertTrue(guard.allow(42, read_only=False).allowed)
        self.assertTrue(guard.allow(42, read_only=False).allowed)
        blocked = guard.allow(42, read_only=False)
        self.assertFalse(blocked.allowed)
        self.assertGreaterEqual(blocked.retry_after_seconds, 1)

        clock.advance(11)
        self.assertTrue(guard.allow(42, read_only=False).allowed)

    def test_read_and_mutation_buckets_are_independent(self) -> None:
        guard = ApiGuard(read_limit=1, mutation_limit=1, window_seconds=60)
        self.assertTrue(guard.allow(7, read_only=True).allowed)
        self.assertFalse(guard.allow(7, read_only=True).allowed)
        self.assertTrue(guard.allow(7, read_only=False).allowed)
        self.assertFalse(guard.allow(7, read_only=False).allowed)

    def test_rate_bucket_memory_is_bounded(self) -> None:
        guard = ApiGuard(read_limit=10, mutation_limit=10, max_rate_buckets=256)
        for user_id in range(1000, 1500):
            self.assertTrue(guard.allow(user_id, read_only=True).allowed)
        self.assertLessEqual(guard.snapshot()['active_rate_buckets'], 256)

    def test_idempotency_is_scoped_and_expires(self) -> None:
        clock = MutableClock()
        guard = ApiGuard(idempotency_ttl_seconds=30, clock=clock)
        guard.store(11, 'wallet.topup', 'abc-123', status=200, payload={'ok': True, 'value': 5})

        replay = guard.lookup(11, 'wallet.topup', 'abc-123')
        self.assertIsNotNone(replay)
        self.assertEqual(replay.status, 200)
        self.assertEqual(replay.payload['value'], 5)
        self.assertIsNone(guard.lookup(12, 'wallet.topup', 'abc-123'))
        self.assertIsNone(guard.lookup(11, 'other.operation', 'abc-123'))

        clock.advance(31)
        self.assertIsNone(guard.lookup(11, 'wallet.topup', 'abc-123'))

    def test_idempotency_key_validation(self) -> None:
        self.assertEqual(ApiGuard.normalize_idempotency_key('  req-123  '), 'req-123')
        self.assertEqual(ApiGuard.normalize_idempotency_key(''), '')
        self.assertEqual(ApiGuard.normalize_idempotency_key('contains space'), '')
        self.assertEqual(ApiGuard.normalize_idempotency_key('x' * 129), '')


class GlobalRuntimeContractTests(unittest.TestCase):
    def test_v4_entrypoint_is_active(self) -> None:
        main_source = ROOT.joinpath('main.py').read_text(encoding='utf-8')
        version_source = ROOT.joinpath('app', 'version.py').read_text(encoding='utf-8')
        runtime_source = ROOT.joinpath('app', 'runtime_v4.py').read_text(encoding='utf-8')
        gateway_source = ROOT.joinpath('app', 'webapp_v4.py').read_text(encoding='utf-8')
        client_source = ROOT.joinpath('miniapp_example', 'v4-client.js').read_text(encoding='utf-8')
        health_source = ROOT.joinpath('app', 'services', 'system_health.py').read_text(encoding='utf-8')

        self.assertIn('from app.runtime_v4 import run', main_source)
        self.assertIn("Boostora v4.0.0", version_source)
        self.assertIn('start_webapp_server_v4', runtime_source)
        self.assertIn('per_user_rate_limit', gateway_source)
        self.assertIn('mutation_idempotency', gateway_source)
        self.assertIn('/health/live', gateway_source)
        self.assertIn('/api/capabilities', gateway_source)
        self.assertIn('v4-client.js?v=400', gateway_source)
        self.assertIn('body.request_id = mutationKey', client_source)
        self.assertIn('pendingMutationKeys', client_source)
        self.assertIn("'gateway': GLOBAL_API_GUARD.snapshot()", health_source)
        self.assertIn("'runtime': RUNTIME_METRICS.snapshot()", health_source)

    def test_v4_environment_contract_is_documented(self) -> None:
        env_source = ROOT.joinpath('.env.example').read_text(encoding='utf-8')
        for variable in (
            'BOOSTORA_API_READS_PER_MINUTE',
            'BOOSTORA_API_MUTATIONS_PER_MINUTE',
            'BOOSTORA_API_RATE_WINDOW_SECONDS',
            'BOOSTORA_IDEMPOTENCY_TTL_SECONDS',
            'BOOSTORA_IDEMPOTENCY_CACHE_MAX',
            'BOOSTORA_RATE_BUCKETS_MAX',
        ):
            self.assertIn(variable, env_source)

    def test_test_databases_are_not_shipped(self) -> None:
        self.assertFalse(ROOT.joinpath('storage', 'start_profile_wallet_smoke_test.db').exists())
        self.assertFalse(ROOT.joinpath('storage', 'test_ad.db').exists())
        gitignore = ROOT.joinpath('.gitignore').read_text(encoding='utf-8')
        self.assertIn('*.db', gitignore)
        self.assertIn('storage/', gitignore)


if __name__ == '__main__':
    unittest.main()
