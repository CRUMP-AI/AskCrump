from pathlib import Path
from types import SimpleNamespace

import pytest

from backend import auth_service
from backend.policy_consent import CURRENT_POLICY_BUNDLE_HASH, CURRENT_POLICY_BUNDLE_ID
from backend.routes import auth as auth_routes
from backend.security import token_hash
from backend.verification_tokens import create_resend_verification_alias


class VerificationDB:
    def __init__(self, user):
        self.user = dict(user) if user else None
        self.rpc_calls = []
        self.sessions = []

    async def select_one(self, table, **kwargs):
        assert table == 'users'
        filters = kwargs['filters']
        expected_hash = filters.get('verification_token_hash')
        if not self.user or (
            expected_hash
            and expected_hash != f"eq.{token_hash('verification-token')}"
        ):
            return None
        if filters.get('id') and filters['id'] != f"eq.{self.user['id']}":
            return None
        return dict(self.user)

    async def rpc(self, name, payload):
        assert name == 'verify_registered_and_create_session_v1'
        self.rpc_calls.append((name, dict(payload)))
        assert payload['p_user_id'] == self.user['id']
        assert payload['p_verification_token_hash'] == self.user['verification_token_hash']
        if self.user.get('is_verified'):
            return [{'verification_applied': False}]
        self.user.update({
            'is_verified': True,
            'verification_token_expires': '2099-01-01T00:15:00+00:00',
        })
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


@pytest.mark.asyncio
async def test_verification_issues_only_one_session_and_replay_never_overwrites_cookie(monkeypatch):
    database = VerificationDB({
        'id': 'user-1',
        'email': 'new-user@example.com',
        'is_guest': False,
        'is_verified': False,
        'verification_token_hash': token_hash('verification-token'),
        'verification_token_expires': '2099-01-01T00:00:00+00:00',
    })
    cookies = []

    async def fail_create_session(*_args, **_kwargs):
        raise AssertionError('registered verification must not use split session writes')

    def fake_set_session_cookie(response, raw_token, request):
        cookies.append(raw_token)

    monkeypatch.setattr(auth_routes, 'db', database)
    monkeypatch.setattr(
        auth_routes,
        'settings',
        SimpleNamespace(app_url='https://www.askcrump.com', session_days=365),
    )
    monkeypatch.setattr(auth_routes, 'create_session', fail_create_session)
    monkeypatch.setattr(auth_service, 'random_token', lambda _size: 'session-token-1')
    monkeypatch.setattr(auth_service, 'new_uuid', lambda: 'session-1')
    monkeypatch.setattr(auth_routes, 'set_session_cookie', fake_set_session_cookie)
    request = SimpleNamespace(
        headers={},
        cookies={'ask_crump_session': 'another-account-session'},
        client=SimpleNamespace(host='127.0.0.1'),
    )

    first = await auth_routes.verify_email(
        'verification-token',
        request,
        intent='presentation',
        plan='professional',
    )
    replay = await auth_routes.verify_email(
        'verification-token',
        request,
        intent='presentation',
        plan='professional',
    )

    assert first.status_code == 303
    assert first.headers['location'] == (
        'https://www.askcrump.com/app?verification=success'
        '&intent=presentation&plan=professional'
    )
    assert replay.status_code == 303
    assert replay.headers['location'] == (
        'https://www.askcrump.com/app?verification=already_verified'
        '&intent=presentation&plan=professional'
    )
    assert database.user['is_verified'] is True
    assert database.user['verification_token_expires'] == '2099-01-01T00:15:00+00:00'
    assert len(database.rpc_calls) == 1
    assert len(database.sessions) == 1
    assert cookies == ['session-token-1']


@pytest.mark.asyncio
async def test_signed_alias_first_click_and_shortened_expiry_replay_share_one_session(
    monkeypatch,
):
    user_id = '11111111-1111-4111-8111-111111111111'
    original_expiry = '2099-01-02T00:00:00+00:00'
    signing_secret = 'verification-replay-signing-key-' + ('1' * 48)
    database = VerificationDB({
        'id': user_id,
        'email': 'new-user@example.com',
        'is_guest': False,
        'is_verified': False,
        'verification_token_hash': token_hash('verification-token'),
        'verification_token_expires': original_expiry,
    })
    alias = create_resend_verification_alias(
        signing_secret,
        key_id='k1',
        user_id=user_id,
        verification_token_hash=token_hash('verification-token'),
        expires_at=original_expiry,
        nonce='first_click_replay_nonce_123',
    )
    cookies = []

    monkeypatch.setattr(auth_routes, 'db', database)
    monkeypatch.setattr(
        auth_routes,
        'settings',
        SimpleNamespace(app_url='https://www.askcrump.com', session_days=365),
    )
    monkeypatch.setattr(
        auth_routes,
        '_verification_alias_signing_keys',
        lambda: {'k1': signing_secret},
    )
    monkeypatch.setattr(auth_service, 'random_token', lambda _size: 'session-token-1')
    monkeypatch.setattr(auth_service, 'new_uuid', lambda: 'session-1')
    monkeypatch.setattr(
        auth_routes,
        'set_session_cookie',
        lambda _response, raw_token, _request: cookies.append(raw_token),
    )
    request = SimpleNamespace(
        headers={},
        cookies={'ask_crump_session': 'another-account-session'},
        client=SimpleNamespace(host='127.0.0.1'),
    )

    first = await auth_routes.verify_email(alias, request)
    replay = await auth_routes.verify_email(alias, request)

    assert first.status_code == replay.status_code == 303
    assert first.headers['location'] == 'https://www.askcrump.com/app?verification=success'
    assert replay.headers['location'] == (
        'https://www.askcrump.com/app?verification=already_verified'
    )
    assert database.user['is_verified'] is True
    assert database.user['verification_token_expires'] == '2099-01-01T00:15:00+00:00'
    assert len(database.rpc_calls) == 1
    assert len(database.sessions) == 1
    assert cookies == ['session-token-1']


class AtomicGuestVerificationDB:
    def __init__(self):
        self.user = {
            'id': 'guest-user-1',
            'email': 'converted@example.com',
            'is_guest': True,
            'is_verified': False,
            'verification_token_hash': token_hash('verification-token'),
            'verification_token_expires': '2099-01-01T00:00:00+00:00',
        }
        self.sessions = [
            {
                'id': 'guest-session-browser',
                'user_id': self.user['id'],
                'token_hash': token_hash('original-guest-token'),
                'device_id': 'browser-installation',
                'device_info': {'client': 'web', 'platform': 'web'},
                'created_at': '2026-10-22T00:00:00+00:00',
                'last_activity': '2026-10-22T00:00:00+00:00',
                'expires_at': '2099-01-01T00:00:00+00:00',
                'revoked_at': None,
            },
            {
                'id': 'guest-session-other-device',
                'user_id': self.user['id'],
                'token_hash': token_hash('other-guest-token'),
                'device_id': 'other-installation',
                'device_info': {'client': 'web', 'platform': 'web'},
                'created_at': '2026-10-22T00:00:00+00:00',
                'last_activity': '2026-10-22T00:00:00+00:00',
                'expires_at': '2099-01-01T00:00:00+00:00',
                'revoked_at': None,
            },
        ]
        self.rpc_calls = []

    async def select_one(self, table, columns='*', filters=None):
        filters = filters or {}
        if table == 'users':
            expected_hash = filters.get('verification_token_hash')
            if expected_hash and expected_hash != f"eq.{self.user['verification_token_hash']}":
                return None
            expected_id = filters.get('id')
            if expected_id and expected_id != f"eq.{self.user['id']}":
                return None
            return dict(self.user)
        if table == 'sessions':
            expected_hash = str(filters.get('token_hash') or '').removeprefix('eq.')
            return next(
                (
                    dict(session)
                    for session in self.sessions
                    if session['token_hash'] == expected_hash
                    and session['revoked_at'] is None
                ),
                None,
            )
        if table == 'user_settings':
            return None
        raise AssertionError(f'unexpected table: {table}')

    async def update(self, table, payload, *, filters, **_kwargs):
        if table == 'sessions':
            session_id = str(filters['id']).removeprefix('eq.')
            session = next(row for row in self.sessions if row['id'] == session_id)
            session.update(payload)
            return [dict(session)]
        raise AssertionError(f'unexpected update: {table}')

    async def rpc(self, name, payload, **_kwargs):
        if name == 'read_current_policy_acceptance_v1':
            return [{
                'receipt_id': 'guest-consent-receipt',
                'accepted_at': '2026-10-27T08:00:00+00:00',
                'bundle_id': CURRENT_POLICY_BUNDLE_ID,
                'bundle_hash': CURRENT_POLICY_BUNDLE_HASH,
            }]
        assert name == 'verify_guest_and_create_session_v1'
        self.rpc_calls.append((name, dict(payload)))
        assert payload['p_user_id'] == self.user['id']
        assert payload['p_verification_token_hash'] == self.user['verification_token_hash']
        assert payload['p_device_id'] == 'browser-installation'
        if self.user['is_verified']:
            return []

        revoked = 0
        for session in self.sessions:
            if session['user_id'] == self.user['id'] and session['revoked_at'] is None:
                session['revoked_at'] = '2026-10-23T00:00:00+00:00'
                revoked += 1

        self.user.update({
            'is_guest': False,
            'is_verified': True,
            'verification_token_expires': '2099-01-01T00:15:00+00:00',
        })
        replacement = next(
            session
            for session in self.sessions
            if session['device_id'] == payload['p_device_id']
        )
        replacement.update({
            'user_id': self.user['id'],
            'token_hash': payload['p_session_token_hash'],
            'device_name': payload['p_device_name'],
            'platform': payload['p_platform'],
            'device_info': payload['p_device_info'],
            'ip_address': payload['p_ip_address'],
            'user_agent': payload['p_user_agent'],
            'created_at': '2026-10-23T00:00:00+00:00',
            'last_activity': '2026-10-23T00:00:00+00:00',
            'expires_at': payload['p_session_expires_at'],
            'revoked_at': None,
        })
        return [{
            'converted': True,
            'user_data': dict(self.user),
            'session_data': dict(replacement),
            'revoked_sessions': revoked,
        }]


def bearer_request(token, **headers):
    return SimpleNamespace(
        headers={'authorization': f'Bearer {token}', **headers},
        cookies={},
        scope={'headers': []},
        client=SimpleNamespace(host='127.0.0.1'),
    )


@pytest.mark.asyncio
async def test_guest_verification_atomically_invalidates_original_token(monkeypatch):
    database = AtomicGuestVerificationDB()
    settings = SimpleNamespace(
        app_url='https://www.askcrump.com',
        session_days=365,
        session_cookie_name='ask_crump_session',
    )
    cookies = []
    monkeypatch.setattr(auth_routes, 'db', database)
    monkeypatch.setattr(auth_routes, 'settings', settings)
    monkeypatch.setattr(auth_service, 'random_token', lambda _size: 'fresh-account-token')
    monkeypatch.setattr(
        auth_routes,
        'set_session_cookie',
        lambda _response, raw_token, _request: cookies.append(raw_token),
    )

    response = await auth_routes.verify_email(
        'verification-token',
        bearer_request(
            'original-guest-token',
            **{'x-installation-id': 'browser-installation'},
        ),
    )
    replay = await auth_routes.verify_email(
        'verification-token',
        bearer_request(
            'another-account-token',
            **{'x-installation-id': 'different-installation'},
        ),
    )

    assert response.status_code == 303
    assert replay.status_code == 303
    assert replay.headers['location'] == (
        'https://www.askcrump.com/app?verification=already_verified'
    )
    assert cookies == ['fresh-account-token']
    assert len(database.rpc_calls) == 1
    assert sum(session['revoked_at'] is None for session in database.sessions) == 1
    assert not any(
        session['token_hash'] == token_hash('original-guest-token')
        and session['revoked_at'] is None
        for session in database.sessions
    )

    with pytest.raises(auth_service.AuthenticationError) as excinfo:
        await auth_service.authenticate_request(
            bearer_request('original-guest-token'),
            database,
            settings,
            touch=False,
        )
    assert excinfo.value.status_code == 401

    authenticated = await auth_service.authenticate_request(
        bearer_request('fresh-account-token'),
        database,
        settings,
        touch=False,
    )
    assert authenticated.user['is_guest'] is False
    assert authenticated.user['is_verified'] is True


@pytest.mark.asyncio
async def test_normal_account_verification_uses_atomic_session_path(monkeypatch):
    database = VerificationDB({
        'id': 'user-2',
        'email': 'normal@example.com',
        'is_guest': False,
        'is_verified': False,
        'verification_token_hash': token_hash('verification-token'),
        'verification_token_expires': '2099-01-01T00:00:00+00:00',
    })
    async def fail_create_session(*_args, **_kwargs):
        raise AssertionError('normal verification must not use create_session')

    monkeypatch.setattr(auth_routes, 'db', database)
    monkeypatch.setattr(
        auth_routes,
        'settings',
        SimpleNamespace(app_url='https://www.askcrump.com', session_days=365),
    )
    monkeypatch.setattr(auth_routes, 'create_session', fail_create_session)
    monkeypatch.setattr(auth_service, 'random_token', lambda _size: 'normal-account-token')
    monkeypatch.setattr(auth_service, 'new_uuid', lambda: 'normal-account-session')
    monkeypatch.setattr(auth_routes, 'set_session_cookie', lambda *_args: None)

    response = await auth_routes.verify_email(
        'verification-token',
        SimpleNamespace(headers={}, client=SimpleNamespace(host='127.0.0.1')),
    )

    assert response.status_code == 303
    assert database.user['is_verified'] is True
    assert database.user['is_guest'] is False
    assert len(database.rpc_calls) == 1
    assert len(database.sessions) == 1


@pytest.mark.asyncio
async def test_concurrent_ordinary_verification_loser_rereads_and_never_mints(monkeypatch):
    class ConcurrentWinnerDB(VerificationDB):
        async def rpc(self, name, payload):
            assert name == 'verify_registered_and_create_session_v1'
            self.rpc_calls.append((name, dict(payload)))
            self.user.update({
                'is_verified': True,
                'verification_token_expires': '2099-01-01T00:15:00+00:00',
            })
            return [{'verification_applied': False}]

    database = ConcurrentWinnerDB({
        'id': 'user-race',
        'email': 'race@example.com',
        'is_guest': False,
        'is_verified': False,
        'verification_token_hash': token_hash('verification-token'),
        'verification_token_expires': '2099-01-01T00:00:00+00:00',
    })

    async def fail_create_session(*_args, **_kwargs):
        raise AssertionError('the conditional-update loser must not mint a session')

    cookies = []
    monkeypatch.setattr(auth_routes, 'db', database)
    monkeypatch.setattr(
        auth_routes,
        'settings',
        SimpleNamespace(app_url='https://www.askcrump.com', session_days=365),
    )
    monkeypatch.setattr(auth_routes, 'create_session', fail_create_session)
    monkeypatch.setattr(
        auth_routes,
        'set_session_cookie',
        lambda *_args, **_kwargs: cookies.append('unexpected'),
    )

    response = await auth_routes.verify_email(
        'verification-token',
        SimpleNamespace(
            headers={'x-installation-id': 'not-authentication'},
            cookies={'ask_crump_session': 'another-account-session'},
            client=SimpleNamespace(host='127.0.0.1'),
        ),
    )

    assert response.status_code == 303
    assert response.headers['location'] == (
        'https://www.askcrump.com/app?verification=already_verified'
    )
    assert cookies == []


@pytest.mark.asyncio
async def test_registered_verification_db_clock_refusal_redirects_failed(monkeypatch):
    class ExpiredAtDatabaseDB(VerificationDB):
        async def rpc(self, name, payload):
            assert name == 'verify_registered_and_create_session_v1'
            self.rpc_calls.append((name, dict(payload)))
            return [{'verification_applied': False}]

    database = ExpiredAtDatabaseDB({
        'id': 'user-expiry-race',
        'email': 'expiry-race@example.com',
        'is_guest': False,
        'is_verified': False,
        'verification_token_hash': token_hash('verification-token'),
        'verification_token_expires': '2099-01-01T00:00:00+00:00',
    })
    cookies = []
    monkeypatch.setattr(auth_routes, 'db', database)
    monkeypatch.setattr(
        auth_routes,
        'settings',
        SimpleNamespace(app_url='https://www.askcrump.com', session_days=365),
    )
    monkeypatch.setattr(
        auth_routes,
        'set_session_cookie',
        lambda *_args, **_kwargs: cookies.append('unexpected'),
    )

    response = await auth_routes.verify_email(
        'verification-token',
        SimpleNamespace(headers={}, client=SimpleNamespace(host='127.0.0.1')),
    )

    assert response.status_code == 303
    assert response.headers['location'] == (
        'https://www.askcrump.com/app?verification=failed'
    )
    assert cookies == []


@pytest.mark.asyncio
async def test_invalid_verification_link_never_issues_a_session(monkeypatch):
    database = VerificationDB(None)

    async def fail_create_session(*args, **kwargs):
        raise AssertionError('invalid verification must not create a session')

    monkeypatch.setattr(auth_routes, 'db', database)
    monkeypatch.setattr(
        auth_routes,
        'settings',
        SimpleNamespace(app_url='https://www.askcrump.com'),
    )
    monkeypatch.setattr(auth_routes, 'create_session', fail_create_session)
    request = SimpleNamespace(headers={}, client=SimpleNamespace(host='127.0.0.1'))

    response = await auth_routes.verify_email('verification-token', request)

    assert response.status_code == 303
    assert response.headers['location'] == 'https://www.askcrump.com/app?verification=failed'


@pytest.mark.asyncio
async def test_successful_verification_discards_unknown_destination_values(monkeypatch):
    database = VerificationDB({
        'id': 'user-1',
        'email': 'new-user@example.com',
        'is_verified': True,
        'verification_token_hash': token_hash('verification-token'),
        'verification_token_expires': '2099-01-01T00:00:00+00:00',
    })

    async def fail_create_session(*_args, **_kwargs):
        raise AssertionError('a verified-link replay must not create a session')

    monkeypatch.setattr(auth_routes, 'db', database)
    monkeypatch.setattr(auth_routes, 'settings', SimpleNamespace(app_url='https://www.askcrump.com'))
    monkeypatch.setattr(auth_routes, 'create_session', fail_create_session)
    monkeypatch.setattr(auth_routes, 'set_session_cookie', lambda *_args, **_kwargs: None)
    request = SimpleNamespace(headers={}, client=SimpleNamespace(host='127.0.0.1'))

    response = await auth_routes.verify_email(
        'verification-token',
        request,
        intent='private customer prompt',
        plan='free',
    )

    assert response.headers['location'] == (
        'https://www.askcrump.com/app?verification=already_verified'
    )


def test_verification_email_promises_the_one_click_workspace_handoff():
    source = Path(auth_routes.__file__).resolve().parents[1] / 'email_service.py'
    email_source = source.read_text(encoding='utf-8')

    assert 'Confirm your email and open your Ask Crump workspace.' in email_source
    assert 'Verify &amp; open Ask Crump' in email_source
    assert 'later uses only confirm that the address is already verified' in email_source


def test_verification_result_copy_tells_replay_users_how_to_recover_password_setup():
    source = Path(auth_routes.__file__).resolve().parents[2] / 'public' / 'auth-controller.js'
    frontend = source.read_text(encoding='utf-8')

    assert (
        "already_verified: 'This email is already verified. Sign in, or use Forgot password "
        "if you have not set one yet.'"
    ) in frontend
