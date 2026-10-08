from __future__ import annotations

import base64

import pytest

from backend import config


VALID_SECRET = 'whsec_' + base64.b64encode(
    b'ask-crump-recovery-config-secret'
).decode('ascii')


def _enable(monkeypatch) -> None:
    monkeypatch.setattr(config, 'VERIFICATION_EMAIL_RECOVERY_RELEASED', True)
    values = {
        'APP_ENV': 'development',
        'APP_URL': 'http://localhost:3000',
        'SUPABASE_URL': 'http://localhost:54321',
        'SUPABASE_SERVICE_KEY': 'service-test',
        'CRUMP_ENABLE_VERIFICATION_EMAIL_RECOVERY': 'true',
        'RESEND_API_KEY': 're_test',
        'RESEND_WEBHOOK_SECRET': VALID_SECRET,
        'CRON_SECRET': 'cron-test',
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    config.get_settings.cache_clear()


def test_complete_recovery_configuration_can_start(monkeypatch):
    _enable(monkeypatch)
    try:
        settings = config.get_settings()
        assert settings.verification_email_recovery_enabled is True
    finally:
        config.get_settings.cache_clear()


@pytest.mark.parametrize(
    ('missing', 'expected'),
    (
        ('RESEND_API_KEY', 'RESEND_API_KEY'),
        ('RESEND_WEBHOOK_SECRET', 'RESEND_WEBHOOK_SECRET'),
        ('CRON_SECRET', 'CRON_SECRET'),
    ),
)
def test_enabled_recovery_fails_startup_when_prerequisite_is_missing(
    monkeypatch,
    missing,
    expected,
):
    _enable(monkeypatch)
    monkeypatch.delenv(missing)
    config.get_settings.cache_clear()
    try:
        with pytest.raises(RuntimeError, match=expected):
            config.get_settings()
    finally:
        config.get_settings.cache_clear()


def test_enabled_recovery_fails_startup_for_invalid_webhook_secret(monkeypatch):
    _enable(monkeypatch)
    monkeypatch.setenv('RESEND_WEBHOOK_SECRET', 'whsec_not-valid-base64!')
    config.get_settings.cache_clear()
    try:
        with pytest.raises(RuntimeError, match='valid whsec_ signing secret'):
            config.get_settings()
    finally:
        config.get_settings.cache_clear()


def test_enabled_recovery_fails_startup_for_unowned_environment(monkeypatch):
    _enable(monkeypatch)
    monkeypatch.setenv('APP_ENV', 'staging')
    config.get_settings.cache_clear()
    try:
        with pytest.raises(RuntimeError, match='allowlisted APP_ENV'):
            config.get_settings()
    finally:
        config.get_settings.cache_clear()
