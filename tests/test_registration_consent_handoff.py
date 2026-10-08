from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from backend.routes import auth as auth_routes
from backend.schemas import (
    CURRENT_TERMS_VERSION,
    RegisterRequest,
    TermsAcceptanceRequest,
)


class RegistrationDB:
    def __init__(self) -> None:
        self.inserted_user: dict | None = None

    async def select_one(self, table, **kwargs):
        return None

    async def insert(self, table, payload):
        assert table == 'users'
        self.inserted_user = dict(payload)
        return [dict(payload)]

    async def upsert(self, table, payload, *, on_conflict):
        assert table == 'user_settings'
        assert on_conflict == 'user_id'
        return [dict(payload)]

    async def update(self, *args, **kwargs):
        return []


class SentVerificationEmail:
    async def send_verification(self, *args, **kwargs):
        return True


class PendingRegistrationDB:
    def __init__(self) -> None:
        self.user = {
            'id': 'pending-user',
            'email': 'pending@example.com',
            'password_hash': 'old-hash',
            'full_name': None,
            'is_verified': False,
        }
        self.updated: dict | None = None

    async def select_one(self, table, **kwargs):
        assert table == 'users'
        return dict(self.user)

    async def update(self, table, payload, *, filters):
        assert table == 'users'
        assert filters == {'id': 'eq.pending-user'}
        self.updated = dict(payload)
        self.user.update(payload)
        return [dict(self.user)]


@pytest.mark.asyncio
async def test_current_registration_consent_is_saved_before_verification(monkeypatch):
    fake_db = RegistrationDB()

    async def allow_rate_limit(*args, **kwargs):
        return None

    async def accept_product_event(*args, **kwargs):
        return True

    monkeypatch.setattr(auth_routes, 'db', fake_db)
    monkeypatch.setattr(auth_routes, 'email_service', SentVerificationEmail())
    monkeypatch.setattr(auth_routes, 'enforce_auth_rate_limit', allow_rate_limit)
    monkeypatch.setattr(auth_routes, 'hash_password', lambda password: 'hashed-password')
    monkeypatch.setattr(auth_routes, 'record_account_created_event', accept_product_event)
    monkeypatch.setattr(auth_routes, 'record_product_event', accept_product_event)

    response = await auth_routes.register(
        RegisterRequest(
            email='new-user@example.com',
            password='StrongPass1',
            source='facebook',
            termsAccepted=True,
            termsVersion=CURRENT_TERMS_VERSION,
        ),
        SimpleNamespace(),
    )

    assert response['success'] is True
    assert fake_db.inserted_user is not None
    assert fake_db.inserted_user['terms_version'] == CURRENT_TERMS_VERSION
    assert fake_db.inserted_user['terms_accepted_at']


@pytest.mark.asyncio
async def test_pending_registration_keeps_its_password_and_explains_the_handoff(monkeypatch):
    fake_db = PendingRegistrationDB()

    async def allow_rate_limit(*args, **kwargs):
        return None

    monkeypatch.setattr(auth_routes, 'db', fake_db)
    monkeypatch.setattr(auth_routes, 'email_service', SentVerificationEmail())
    monkeypatch.setattr(auth_routes, 'enforce_auth_rate_limit', allow_rate_limit)
    monkeypatch.setattr(auth_routes, 'hash_password', lambda password: f'hashed:{password}')

    response = await auth_routes.register(
        RegisterRequest(
            email='pending@example.com',
            password='ReplacementPass1',
            termsAccepted=True,
            termsVersion=CURRENT_TERMS_VERSION,
        ),
        SimpleNamespace(),
    )

    assert response['success'] is True
    assert response['pendingAccount'] is True
    assert 'password already set for this account' in response['message']
    assert fake_db.updated is not None
    assert 'password_hash' not in fake_db.updated
    assert fake_db.updated['verification_token_hash']
    assert fake_db.updated['verification_token_expires']


def test_legacy_registration_omission_keeps_the_authenticated_terms_fallback():
    payload = RegisterRequest(
        email='legacy-client@example.com',
        password='StrongPass1',
    )

    assert payload.termsAccepted is False
    assert payload.termsVersion is None
    assert auth_routes._registration_terms_values(payload, accepted_at='2026-08-29T00:00:00Z') == {}


def test_stale_legal_versions_are_rejected_by_both_consent_contracts():
    assert CURRENT_TERMS_VERSION == '2026-08-01'
    with pytest.raises(ValidationError):
        RegisterRequest(
            email='stale@example.com',
            password='StrongPass1',
            termsAccepted=True,
            termsVersion='2026-07-30',
        )
    with pytest.raises(ValidationError):
        TermsAcceptanceRequest(version='2026-07-30')
