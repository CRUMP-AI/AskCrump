"""A staged RevenueCat webhook must not silently activate native billing."""

from pathlib import Path

import pytest

from backend import config


ROOT = Path(__file__).resolve().parents[1]
VALID_WEBHOOK = 'Bearer ' + 'a1b2c3d4' * 5
VALID_API_KEY = 'sk_' + 'a1b2c3d4' * 5


@pytest.fixture(autouse=True)
def native_billing_settings(monkeypatch):
    monkeypatch.setenv('APP_ENV', 'test')
    monkeypatch.setenv('SUPABASE_URL', 'https://example.supabase.co')
    monkeypatch.setenv('SUPABASE_SERVICE_KEY', 'test-service-key')
    monkeypatch.delenv('CRUMP_ENABLE_NATIVE_BILLING', raising=False)
    monkeypatch.delenv('REVENUECAT_WEBHOOK_AUTH', raising=False)
    monkeypatch.delenv('REVENUECAT_SECRET_API_KEY', raising=False)
    config.get_settings.cache_clear()
    yield
    config.get_settings.cache_clear()


def test_web_only_deployment_does_not_infer_native_billing_from_staged_webhook(monkeypatch):
    monkeypatch.setenv('REVENUECAT_WEBHOOK_AUTH', 'Bearer REPLACE_WITH_RANDOM_SECRET')

    settings = config.get_settings()

    assert settings.native_billing_enabled is False
    runtime = (ROOT / 'backend' / 'runtime.py').read_text(encoding='utf-8')
    assert 'revenuecat_required=settings.native_billing_enabled' in runtime
    assert 'revenuecat_required=bool(settings.revenuecat_webhook_auth)' not in runtime


@pytest.mark.parametrize(
    'webhook_auth',
    (
        None,
        'Bearer REPLACE_WITH_RANDOM_SECRET',
        'Bearer too-short',
        'not-bearer ' + 'a1b2c3d4' * 5,
    ),
)
def test_native_billing_rejects_missing_or_placeholder_webhook(monkeypatch, webhook_auth):
    monkeypatch.setenv('CRUMP_ENABLE_NATIVE_BILLING', 'true')
    monkeypatch.setenv('REVENUECAT_SECRET_API_KEY', VALID_API_KEY)
    if webhook_auth is not None:
        monkeypatch.setenv('REVENUECAT_WEBHOOK_AUTH', webhook_auth)

    with pytest.raises(RuntimeError, match='REVENUECAT_WEBHOOK_AUTH'):
        config.get_settings()


@pytest.mark.parametrize(
    'api_key',
    (None, '', 'REPLACE_WITH_SECRET', 'too-short'),
)
def test_native_billing_rejects_missing_or_placeholder_server_key(monkeypatch, api_key):
    monkeypatch.setenv('CRUMP_ENABLE_NATIVE_BILLING', 'true')
    monkeypatch.setenv('REVENUECAT_WEBHOOK_AUTH', VALID_WEBHOOK)
    if api_key is not None:
        monkeypatch.setenv('REVENUECAT_SECRET_API_KEY', api_key)

    with pytest.raises(RuntimeError, match='REVENUECAT_SECRET_API_KEY'):
        config.get_settings()


def test_native_billing_accepts_deliberately_configured_secret_pair(monkeypatch):
    monkeypatch.setenv('CRUMP_ENABLE_NATIVE_BILLING', 'true')
    monkeypatch.setenv('REVENUECAT_WEBHOOK_AUTH', VALID_WEBHOOK)
    monkeypatch.setenv('REVENUECAT_SECRET_API_KEY', VALID_API_KEY)

    settings = config.get_settings()

    assert settings.native_billing_enabled is True
    assert settings.revenuecat_webhook_auth == VALID_WEBHOOK
    assert settings.revenuecat_secret_api_key == VALID_API_KEY
