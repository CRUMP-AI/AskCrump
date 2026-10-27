from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from starlette.requests import Request

from backend.routes import auth as auth_routes
from backend.policy_consent import CURRENT_POLICY_BUNDLE_HASH, CURRENT_POLICY_BUNDLE_ID
from backend.schemas import (
    CURRENT_TERMS_VERSION,
    RegisterRequest,
    TermsAcceptanceRequest,
)


class RegistrationDB:
    def __init__(self) -> None:
        self.inserted_user: dict | None = None
        self.receipt_calls: list[dict] = []

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

    async def rpc(self, name, payload, **_kwargs):
        assert name == 'record_policy_acceptance_v1'
        self.receipt_calls.append(dict(payload))
        return [{
            'receipt_id': '11111111-1111-4111-8111-111111111111',
            'accepted_at': '2026-10-27T00:00:00+00:00',
            'bundle_id': CURRENT_POLICY_BUNDLE_ID,
            'bundle_hash': CURRENT_POLICY_BUNDLE_HASH,
        }]


class QueuedVerificationEmail:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def enqueue_resend(self, **kwargs):
        self.calls.append(dict(kwargs))


@pytest.mark.asyncio
async def test_current_registration_consent_is_saved_before_verification(monkeypatch):
    fake_db = RegistrationDB()
    queue = QueuedVerificationEmail()

    async def allow_rate_limit(*args, **kwargs):
        return None

    async def reject_product_event(*args, **kwargs):
        return False

    monkeypatch.setattr(auth_routes, 'db', fake_db)
    monkeypatch.setattr(auth_routes, 'verification_emails', queue)
    monkeypatch.setattr(auth_routes, 'enforce_auth_rate_limit', allow_rate_limit)
    monkeypatch.setattr(auth_routes, 'hash_password', lambda password: 'hashed-password')
    monkeypatch.setattr(auth_routes, 'record_account_created_event', reject_product_event)
    monkeypatch.setattr(auth_routes, 'record_product_event', reject_product_event)

    response = await auth_routes.register(
        RegisterRequest(
            email='new-user@example.com',
            password='StrongPass1',
            source='facebook',
            termsAccepted=True,
            privacyNoticeAcknowledged=True,
            age17PlusAttested=True,
            aiProviderTransmissionAuthorized=True,
            termsVersion=CURRENT_TERMS_VERSION,
        ),
        Request({
            "type": "http", "method": "POST", "path": "/api/auth/register",
            "scheme": "https", "server": ("www.askcrump.com", 443),
            "client": ("127.0.0.1", 12345), "headers": [],
        }),
    )

    assert response['success'] is True
    assert fake_db.inserted_user is not None
    assert 'terms_version' not in fake_db.inserted_user
    assert 'terms_accepted_at' not in fake_db.inserted_user
    assert fake_db.receipt_calls[0]['p_bundle_id'] == CURRENT_TERMS_VERSION
    assert fake_db.receipt_calls[0]['p_acceptance_source'] == 'registration'
    assert (
        fake_db.inserted_user['registration_submitted_at']
        == fake_db.inserted_user['created_at']
    )
    assert fake_db.inserted_user['registration_environment'] == 'production'
    assert response['emailSent'] is False
    assert response['emailQueued'] is True
    assert queue.calls == [{
        'email': 'new-user@example.com',
        'intent': None,
        'plan': None,
    }]


def test_registration_omission_cannot_create_an_unconsented_account():
    with pytest.raises(ValidationError):
        RegisterRequest(
            email='legacy-client@example.com',
            password='StrongPass1',
        )


@pytest.mark.asyncio
async def test_guest_registration_preserves_existing_settings_without_redundant_upsert(monkeypatch):
    class GuestRegistrationDB:
        def __init__(self) -> None:
            self.user = {
                'id': 'guest-user',
                'email': 'guest-guest-user@guest.askcrump.local',
                'is_guest': True,
                'is_verified': False,
                'full_name': None,
                'created_at': '2026-10-23T18:00:00+00:00',
                'registration_environment': 'production',
            }
            self.updated_user: dict | None = None

        async def select_one(self, table, **kwargs):
            assert table == 'users'
            return None

        async def update(self, table, payload, *, filters):
            assert table == 'users'
            assert filters == {'id': 'eq.guest-user'}
            self.user.update(payload)
            self.updated_user = dict(self.user)
            return [dict(self.user)]

        async def upsert(self, *_args, **_kwargs):
            raise AssertionError('guest conversion must preserve its existing settings row')

        async def rpc(self, name, payload, **_kwargs):
            assert name == 'record_policy_acceptance_v1'
            assert payload['p_user_id'] == 'guest-user'
            assert payload['p_acceptance_source'] == 'registration'
            return [{
                'receipt_id': '11111111-1111-4111-8111-111111111111',
                'accepted_at': '2026-10-27T00:00:00+00:00',
                'bundle_id': CURRENT_POLICY_BUNDLE_ID,
                'bundle_hash': CURRENT_POLICY_BUNDLE_HASH,
            }]

    fake_db = GuestRegistrationDB()
    queue = QueuedVerificationEmail()

    async def allow_rate_limit(*_args, **_kwargs):
        return None

    async def guest_identity(*_args, **_kwargs):
        return SimpleNamespace(user=dict(fake_db.user))

    async def accept_product_event(*_args, **_kwargs):
        return True

    monkeypatch.setattr(auth_routes, 'db', fake_db)
    monkeypatch.setattr(auth_routes, 'verification_emails', queue)
    monkeypatch.setattr(auth_routes, 'enforce_auth_rate_limit', allow_rate_limit)
    monkeypatch.setattr(auth_routes, 'authenticate_guest_for_registration', guest_identity)
    monkeypatch.setattr(auth_routes, 'hash_password', lambda _password: 'hashed-password')
    monkeypatch.setattr(auth_routes, 'record_account_created_event', accept_product_event)
    monkeypatch.setattr(auth_routes, 'record_product_event', accept_product_event)

    response = await auth_routes.register(
        RegisterRequest(
            email='converted@example.com',
            password='StrongPass1',
            termsAccepted=True,
            privacyNoticeAcknowledged=True,
            age17PlusAttested=True,
            aiProviderTransmissionAuthorized=True,
            termsVersion=CURRENT_TERMS_VERSION,
        ),
        Request({
            'type': 'http', 'method': 'POST', 'path': '/api/auth/register',
            'scheme': 'https', 'server': ('www.askcrump.com', 443),
            'client': ('127.0.0.1', 12345), 'headers': [],
        }),
    )

    assert response['success'] is True
    assert response['emailSent'] is False
    assert response['emailQueued'] is True
    assert queue.calls == [{
        'email': 'converted@example.com',
        'intent': None,
        'plan': None,
    }]
    assert fake_db.updated_user is not None
    assert fake_db.updated_user['email'] == 'converted@example.com'
    assert fake_db.updated_user['is_guest'] is True
    assert fake_db.updated_user['created_at'] == '2026-10-23T18:00:00+00:00'
    assert fake_db.updated_user['registration_submitted_at']
    assert fake_db.updated_user['registration_environment'] == 'production'


def test_stale_legal_versions_are_rejected_by_both_consent_contracts():
    assert CURRENT_TERMS_VERSION == 'ask-crump-legal-2026-08-01-a44e8c36'
    with pytest.raises(ValidationError):
        TermsAcceptanceRequest()
    with pytest.raises(ValidationError):
        RegisterRequest(
            email='stale@example.com',
            password='StrongPass1',
            termsAccepted=True,
            privacyNoticeAcknowledged=True,
            age17PlusAttested=True,
            aiProviderTransmissionAuthorized=True,
            termsVersion='2026-07-30',
        )
    with pytest.raises(ValidationError):
        TermsAcceptanceRequest(
            version='2026-07-30',
            termsAccepted=True,
            privacyNoticeAcknowledged=True,
            age17PlusAttested=True,
            aiProviderTransmissionAuthorized=True,
        )
