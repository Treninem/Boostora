from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _literal_translation_calls() -> list[tuple[Path, int, str, set[str]]]:
    calls: list[tuple[Path, int, str, set[str]]] = []
    for path in (ROOT / 'app').rglob('*.py'):
        tree = ast.parse(path.read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Attribute) or node.func.attr != 't':
                continue
            if len(node.args) < 2 or not isinstance(node.args[1], ast.Constant):
                continue
            text_key = node.args[1].value
            if not isinstance(text_key, str):
                continue
            kwargs = {item.arg for item in node.keywords if item.arg}
            calls.append((path, node.lineno, text_key, kwargs))
    return calls


def test_translation_calls_and_placeholders_are_consistent() -> None:
    namespace: dict[str, object] = {}
    exec((ROOT / 'app' / 'texts.py').read_text(encoding='utf-8'), namespace)
    texts = namespace['TEXTS']
    calls = _literal_translation_calls()
    assert calls

    missing_ru = sorted({key for _, _, key, _ in calls if key not in texts['ru']})
    missing_en = sorted({key for _, _, key, _ in calls if key not in texts['en']})
    assert not missing_ru
    assert not missing_en

    placeholder_pattern = re.compile(r'(?<!{){([A-Za-z_][A-Za-z0-9_]*)[^}]*}')
    missing_arguments: list[tuple[str, int, str, list[str]]] = []
    for path, line, key, kwargs in calls:
        template = texts['ru'].get(key) or texts['en'].get(key) or ''
        placeholders = set(placeholder_pattern.findall(template))
        missing = sorted(placeholders - kwargs)
        if missing:
            missing_arguments.append((str(path.relative_to(ROOT)), line, key, missing))
    assert not missing_arguments


def test_public_messages_hide_internal_configuration_in_all_languages() -> None:
    namespace: dict[str, object] = {}
    exec((ROOT / 'app' / 'texts.py').read_text(encoding='utf-8'), namespace)
    texts = namespace['TEXTS']
    public_keys = {
        'subscription_check_unavailable',
        'section_stub',
        'campaign_target_require_miniapp_senddata',
        'campaign_target_mini_app_invalid',
        'campaign_target_saved_miniapp',
        'marketplace_screen',
        'marketplace_empty',
        'boostore_temporarily_unavailable',
    }
    forbidden = ('required_chat_id', 'whitelist', '.env', 'api key', 'ключ api', 'initdata')
    unfinished = ('следующий этап', 'later phase', 'späteren phase', 'etapa posterior', 'etapa posterior', 'sonraki bir aşama')
    for language, dictionary in texts.items():
        for key in public_keys:
            value = dictionary.get(key)
            if value is None:
                continue
            lowered = value.lower()
            assert not any(term in lowered for term in forbidden), (language, key, value)
            assert not any(term in lowered for term in unfinished), (language, key, value)


def test_catalog_is_current_only_and_external_html_is_escaped() -> None:
    provider = (ROOT / 'app' / 'services' / 'boostore_provider.py').read_text(encoding='utf-8')
    router = (ROOT / 'app' / 'router.py').read_text(encoding='utf-8')
    version = (ROOT / 'app' / 'version.py').read_text(encoding='utf-8')
    release = (ROOT / 'app' / 'services' / 'release_readiness.py').read_text(encoding='utf-8')
    env_example = (ROOT / '.env.example').read_text(encoding='utf-8')
    gitignore = (ROOT / '.gitignore').read_text(encoding='utf-8')

    assert "APP_VERSION = 'Boostora v3.6.6'" in version
    assert 'current_only=True' in provider
    assert provider.count('last_synced_at IS NOT NULL') >= 4
    assert 'rows = data' in provider and 'data[:safe_limit]' in provider
    assert "SET is_enabled = 0" in provider
    assert 'html.escape(str(row[' in router
    assert 'stable_contract_patch_331_policy' in release
    for name in ('WEBAPP_PORT=', 'PUBLIC_BASE_URL=', 'DOMAIN='):
        assert name in env_example
    for pattern in ('.env', '*.db', '__pycache__/', '*.log'):
        assert pattern in gitignore
