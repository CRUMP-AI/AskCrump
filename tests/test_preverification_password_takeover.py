from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import Request, Response

from backend import auth_service
from backend.auth_service import AuthenticatedUser, complete_initial_password_setup
from backend.policy_consent import CURRENT_POLICY_BUNDLE_HASH
from backend.routes import auth as auth_routes
from backend.schemas import CURRENT_TERMS_VERSION, LoginRequest, RegisterRequest
from backend.security import PENDING_PASSWORD_HASH, hash_password, token_hash, verify_password


ROOT = Path(__file__).resolve().parents[1]
ATTACKER_PASSWORD = 'AttackerPlanted123'
VICTIM_PASSWORD = 'VictimChosen456'


def request(path: str, *, bearer: str | None = None) -> Request:
    headers = [(b'host', b'www.askcrump.com'), (b'user-agent', b'pytest')]
    if bearer:
        headers.append((b'authorization', f'Bearer {bearer}'.encode()))
    return Request({
        'type': 'http',
        'method': 'POST',
        'path': path,
        'headers': headers,
        'client': ('127.0.0.1', 12345),
    })


class NewRegistrationDB:
    def __init__(self) -> None:
        self.user: dict | None = None

    async def select_one(self, *_args, **_kwargs):
        return None

    async def insert(self, table, payload):
        assert table == 'users'
        self.user = dict(payload)
        return [dict(payload)]

    async def upsert(self, *_args, **_kwargs):
        return []

    async def rpc(self, function_name, payload):
        assert function_name == 'record_policy_acceptance_v1'
        return [{
            'receipt_id': 'registration-consent-receipt',
            'accepted_at': '2026-10-27T08:00:00+00:00',
            'bundle_id': payload['p_bundle_id'],
            'bundle_hash': CURRENT_POLICY_BUNDLE_HASH,
        }]


@pytest.mark.asyncio
async def test_registration_never_persists_the_unverified_submitted_password(
    monkeypatch,
) -> None:
    database = NewRegistrationDB()

    async def no_rate_limit(*_args, **_kwargs):
        return None

    async def no_event(*_args, **_kwargs):
        return False

    async def enqueue(**_kwargs):
        return None

    monkeypatch.setattr(auth_routes, 'db', database)
    monkeypatch.setattr(auth_routes, 'enforce_auth_rate_limit', no_rate_limit)
    monkeypatch.setattr(auth_routes, 'record_account_created_event', no_event)
    monkeypatch.setattr(auth_routes, 'record_product_event', no_event)
    monkeypatch.setattr(
        auth_routes,
        'verification_emails',
        SimpleNamespace(enqueue_resend=enqueue),
    )
    monkeypatch.setattr(
        auth_routes,
        'hash_password',
        lambda _password: (_ for _ in ()).throw(
            AssertionError('registration must not hash or persist an unverified password')
        ),
    )

    result = await auth_routes.register(
        RegisterRequest(
            email='victim@example.com',
            password=ATTACKER_PASSWORD,
            termsAccepted=True,
            privacyNoticeAcknowledged=True,
            age17PlusAttested=True,
            aiProviderTransmissionAuthorized=True,
            termsVersion=CURRENT_TERMS_VERSION,
        ),
        request('/api/auth/register'),
    )

    assert result['success'] is True
    assert database.user is not None
    assert database.user['password_hash'] == PENDING_PASSWORD_HASH
    assert database.user['password_setup_required'] is True
    assert verify_password(ATTACKER_PASSWORD, database.user['password_hash']) is False


class TakeoverRegressionDB:
    def __init__(self) -> None:
        self.user = {
            'id': '10000000-0000-4000-8000-000000000099',
            'email': 'victim@example.com',
            'password_hash': hash_password(ATTACKER_PASSWORD),
            'password_setup_required': False,
            'is_guest': False,
            'is_verified': False,
            'deleted_at': None,
            'verification_token_hash': token_hash('victim-inbox-token'),
            'verification_token_expires': '2099-01-01T00:00:00+00:00',
        }
        self.sessions: list[dict] = []
        self.finalize_calls = 0

    async def select_one(self, table, columns='*', filters=None):
        filters = filters or {}
        if table == 'users':
            expected_email = str(filters.get('email') or '').removeprefix('eq.')
            expected_id = str(filters.get('id') or '').removeprefix('eq.')
            expected_anchor = str(
                filters.get('verification_token_hash') or ''
            ).removeprefix('eq.')
            if expected_email and expected_email != self.user['email']:
                return None
            if expected_id and expected_id != self.user['id']:
                return None
            if expected_anchor and expected_anchor != self.user['verification_token_hash']:
                return None
            return dict(self.user)
        if table == 'sessions':
            expected_hash = str(filters.get('token_hash') or '').removeprefix('eq.')
            return next(
                (
                    dict(row)
                    for row in self.sessions
                    if row['token_hash'] == expected_hash and row['revoked_at'] is None
                ),
                None,
            )
        if table == 'user_settings':
            return None
        raise AssertionError(f'unexpected table {table}')

    async def rpc(self, name, payload):
        if name == 'verify_registered_and_create_session_v1':
            self.user.update({
                'is_verified': True,
                'password_hash': PENDING_PASSWORD_HASH,
                'password_setup_required': True,
                'verification_token_expires': '2099-01-01T00:15:00+00:00',
            })
            for session in self.sessions:
                session['revoked_at'] = '2026-10-27T00:00:00+00:00'
            session = {
                'id': payload['p_session_id'],
                'user_id': self.user['id'],
                'token_hash': payload['p_session_token_hash'],
                'device_id': payload['p_device_id'],
                'expires_at': payload['p_session_expires_at'],
                'revoked_at': None,
            }
            self.sessions.append(session)
            return [{
                'verification_applied': True,
                'user_data': dict(self.user),
                'session_data': dict(session),
                'pruned_sessions': 0,
            }]
        if name == 'finalize_password_login_v1':
            self.finalize_calls += 1
            raise AssertionError('the planted password must never reach login finalization')
        raise AssertionError(f'unexpected RPC {name}')


@pytest.mark.asyncio
async def test_pending_login_preserves_verification_resend_recovery(
    monkeypatch,
) -> None:
    database = TakeoverRegressionDB()

    async def no_rate_limit(*_args, **_kwargs):
        return None

    monkeypatch.setattr(auth_routes, 'db', database)
    monkeypatch.setattr(auth_routes, 'enforce_auth_rate_limit', no_rate_limit)
    monkeypatch.setattr(
        auth_routes,
        'verify_password',
        lambda *_args: (_ for _ in ()).throw(
            AssertionError('an unverified pending password must not be evaluated')
        ),
    )

    result = await auth_routes.login(
        LoginRequest(email='victim@example.com', password=ATTACKER_PASSWORD),
        request('/api/auth/login'),
        Response(),
    )

    assert result.status_code == 403
    payload = json.loads(result.body)
    assert payload['code'] == 'EMAIL_VERIFICATION_REQUIRED'
    assert payload['needsVerification'] is True


@pytest.mark.asyncio
async def test_planted_password_cannot_authenticate_after_victim_verifies(
    monkeypatch,
) -> None:
    database = TakeoverRegressionDB()
    issued_cookies: list[str] = []

    async def no_rate_limit(*_args, **_kwargs):
        return None

    monkeypatch.setattr(auth_routes, 'db', database)
    monkeypatch.setattr(
        auth_routes,
        'settings',
        SimpleNamespace(app_url='https://www.askcrump.com', session_days=365),
    )
    monkeypatch.setattr(auth_routes, 'enforce_auth_rate_limit', no_rate_limit)
    monkeypatch.setattr(auth_service, 'random_token', lambda _size: 'victim-session-token')
    monkeypatch.setattr(auth_service, 'new_uuid', lambda: 'victim-session-id')
    monkeypatch.setattr(
        auth_routes,
        'set_session_cookie',
        lambda _response, raw_token, _request: issued_cookies.append(raw_token),
    )

    verified = await auth_routes.verify_email(
        'victim-inbox-token',
        request('/api/auth/verify-email'),
    )
    rejected = await auth_routes.login(
        LoginRequest(email='victim@example.com', password=ATTACKER_PASSWORD),
        request('/api/auth/login'),
        Response(),
    )

    assert verified.status_code == 303
    assert issued_cookies == ['victim-session-token']
    assert database.user['is_verified'] is True
    assert database.user['password_setup_required'] is True
    assert database.user['password_hash'] == PENDING_PASSWORD_HASH
    assert verify_password(ATTACKER_PASSWORD, database.user['password_hash']) is False
    assert rejected.status_code == 401
    assert json.loads(rejected.body)['code'] == 'INVALID_CREDENTIALS'
    assert database.finalize_calls == 0


class PasswordSetupRPCDB:
    def __init__(self, result):
        self.result = result
        self.calls: list[tuple[str, dict]] = []

    async def rpc(self, name, payload):
        self.calls.append((name, dict(payload)))
        return self.result


@pytest.mark.asyncio
async def test_initial_password_setup_is_bound_to_exact_verified_session() -> None:
    updated_user = {
        'id': '10000000-0000-4000-8000-000000000099',
        'is_verified': True,
        'is_guest': False,
        'password_setup_required': False,
    }
    database = PasswordSetupRPCDB([{
        'password_setup_applied': True,
        'user_data': updated_user,
        'revoked_sessions': 2,
    }])
    authenticated = AuthenticatedUser(
        user={'id': updated_user['id']},
        session={
            'id': '20000000-0000-4000-8000-000000000099',
            'token_hash': 'a' * 64,
        },
        token='raw-session-token-that-must-not-cross-the-rpc-boundary',
    )

    result = await complete_initial_password_setup(
        database,
        authenticated,
        password_hash='$argon2id$victim-selected-password-hash',
    )

    assert result == (updated_user, 2)
    assert database.calls == [(
        'complete_initial_password_setup_v1',
        {
            'p_user_id': updated_user['id'],
            'p_session_id': authenticated.session['id'],
            'p_session_token_hash': 'a' * 64,
            'p_password_hash': '$argon2id$victim-selected-password-hash',
        },
    )]
    assert 'raw-session-token' not in json.dumps(database.calls)


def test_migration_closes_registered_guest_resend_and_reset_paths() -> None:
    migration = (
        ROOT / 'migrations' / '20261027013000_preverification_password_takeover_fix.sql'
    ).read_text(encoding='utf-8')

    assert migration.count("password_hash = '!pending-inbox-password-setup-v1!'") >= 3
    assert 'password_setup_required = true' in migration
    assert 'password_setup_required = false' in migration
    assert 'password_inbox_bound_at = v_now' in migration
    assert 'v_user.password_inbox_bound_at is null' in migration
    assert 'v_user.password_setup_required is not false' in migration
    assert 'complete_initial_password_setup_v1' in migration
    assert "'passwordSetupProof', 'inbox-verification-v1'" in migration
    assert "session.device_info ->> 'passwordSetupProof'" in migration
    assert 'verify_registered_and_create_session_v1' in migration
    assert 'verify_guest_and_create_session_v1' in migration
    assert "account.verification_token_hash is not null" in migration
    assert "session.revoked_at is null" in migration
    assert 'lock table public.users in exclusive mode' in migration
    assert 'lock table public.sessions in exclusive mode' in migration
    assert 'account.is_verified is true' in migration
    assert 'account.is_guest is false' in migration
    assert 'Password provenance was not recorded before this repair.' in migration

    login_rpc = migration[
        migration.index('create or replace function public.finalize_password_login_v1'):
        migration.index('create or replace function public.verify_registered_and_create_session_v1')
    ]
    registered_verification_rpc = migration[
        migration.index('create or replace function public.verify_registered_and_create_session_v1'):
        migration.index('create or replace function public.verify_guest_and_create_session_v1')
    ]
    guest_verification_rpc = migration[
        migration.index('create or replace function public.verify_guest_and_create_session_v1'):
        migration.index('create or replace function public.complete_initial_password_setup_v1')
    ]
    assert 'passwordSetupProof' not in login_rpc
    assert 'passwordSetupProof' in registered_verification_rpc
    assert 'passwordSetupProof' in guest_verification_rpc
