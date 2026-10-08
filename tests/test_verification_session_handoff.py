from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.routes import auth as auth_routes
from backend.security import token_hash


class VerificationDB:
    def __init__(self, user):
        self.user = dict(user) if user else None
        self.updates = []

    async def select_one(self, table, **kwargs):
        assert table == 'users'
        filters = kwargs['filters']
        if not self.user or filters.get('verification_token_hash') != f"eq.{token_hash('verification-token')}":
            return None
        return dict(self.user)

    async def update(self, table, values, *, filters):
        assert table == 'users'
        assert filters == {'id': f"eq.{self.user['id']}"}
        self.updates.append(dict(values))
        self.user.update(values)
        return [dict(self.user)]


class RecoveryVerificationDB:
    def __init__(self):
        self.calls = []
        self.user = {
            'id': 'user-recovered',
            'email': 'recovered@example.com',
            'is_verified': True,
        }

    async def select_one(self, table, **kwargs):
        assert table == 'users'
        filters = kwargs['filters']
        if 'verification_token_hash' in filters:
            return None
        assert filters == {'id': 'eq.user-recovered'}
        return dict(self.user)

    async def rpc(self, name, payload, **kwargs):
        self.calls.append((name, dict(payload), dict(kwargs)))
        return [{'consume_verification_email_recovery_token': 'user-recovered'}]


class DualLinkVerificationDB:
    def __init__(self, *, original_valid=True, recovery_valid=True):
        self.original_hash = token_hash('original-token')
        self.recovery_hash = token_hash('recovery-token')
        self.original_valid = original_valid
        self.recovery_valid = recovery_valid
        self.handoff_valid = original_valid or recovery_valid
        self.user = {
            'id': 'user-dual-link',
            'email': 'dual-link@example.com',
            'is_verified': False,
            'verification_token_hash': self.original_hash,
            'verification_token_expires': '2099-01-01T00:00:00+00:00',
        }
        self.foreign_user = {
            'id': 'user-foreign',
            'email': 'foreign@example.com',
            'is_verified': False,
            'verification_token_hash': token_hash('foreign-original-token'),
        }
        self.updates = []
        self.recovery_calls = []

    async def select_one(self, table, **kwargs):
        assert table == 'users'
        filters = kwargs['filters']
        if 'verification_token_hash' in filters:
            if (
                self.original_valid
                and filters['verification_token_hash'] == f'eq.{self.original_hash}'
            ):
                return dict(self.user)
            return None
        if filters == {'id': f"eq.{self.user['id']}"}:
            return dict(self.user)
        if filters == {'id': f"eq.{self.foreign_user['id']}"}:
            return dict(self.foreign_user)
        return None

    async def update(self, table, values, *, filters):
        assert table == 'users'
        assert filters == {'id': f"eq.{self.user['id']}"}
        self.updates.append(dict(values))
        self.user.update(values)
        self.handoff_valid = True
        return [dict(self.user)]

    async def rpc(self, name, payload, **kwargs):
        assert name == 'consume_verification_email_recovery_token'
        self.recovery_calls.append((dict(payload), dict(kwargs)))
        result = None
        if (
            payload == {
                'p_recovery_token_hash': self.recovery_hash,
                'p_environment': 'test',
            }
            and self.recovery_valid
            and self.handoff_valid
        ):
            # Models the SQL consumer: verification is idempotent, the original
            # digest survives, and the recovery digest stays usable only during
            # the same bounded handoff window.
            self.user['is_verified'] = True
            result = self.user['id']
        return [{'consume_verification_email_recovery_token': result}]


def configure_dual_link_route(monkeypatch, database):
    sessions = []

    async def fake_create_session(db, settings, user, request, **kwargs):
        assert db is database
        assert user['is_verified'] is True
        sessions.append(user['id'])
        return f"session-{len(sessions)}", {'id': f"session-{len(sessions)}"}

    monkeypatch.setattr(auth_routes, 'db', database)
    monkeypatch.setattr(
        auth_routes,
        'settings',
        SimpleNamespace(
            app_url='https://www.askcrump.com',
            environment='test',
            verification_email_recovery_enabled=True,
        ),
    )
    monkeypatch.setattr(auth_routes, 'create_session', fake_create_session)
    monkeypatch.setattr(auth_routes, 'set_session_cookie', lambda *_args: None)
    monkeypatch.setattr(
        auth_routes,
        'expiry_iso',
        lambda **kwargs: '2099-01-01T00:15:00+00:00'
        if kwargs == {'minutes': 15}
        else '',
    )
    return SimpleNamespace(headers={}, client=SimpleNamespace(host='127.0.0.1')), sessions


@pytest.mark.asyncio
async def test_verification_issues_a_session_and_keeps_a_short_scanner_safe_replay(monkeypatch):
    database = VerificationDB({
        'id': 'user-1',
        'email': 'new-user@example.com',
        'is_verified': False,
        'verification_token_hash': token_hash('verification-token'),
        'verification_token_expires': '2099-01-01T00:00:00+00:00',
    })
    session_users = []
    cookies = []

    async def fake_create_session(db, settings, user, request, **kwargs):
        assert db is database
        assert user['is_verified'] is True
        assert kwargs == {'device_name': 'Verified email link', 'platform': 'web'}
        session_users.append(dict(user))
        return f'session-token-{len(session_users)}', {'id': f'session-{len(session_users)}'}

    def fake_set_session_cookie(response, raw_token, request):
        cookies.append(raw_token)

    monkeypatch.setattr(auth_routes, 'db', database)
    monkeypatch.setattr(
        auth_routes,
        'settings',
        SimpleNamespace(app_url='https://www.askcrump.com'),
    )
    monkeypatch.setattr(auth_routes, 'create_session', fake_create_session)
    monkeypatch.setattr(auth_routes, 'set_session_cookie', fake_set_session_cookie)
    monkeypatch.setattr(
        auth_routes,
        'expiry_iso',
        lambda **kwargs: '2099-01-01T00:15:00+00:00' if kwargs == {'minutes': 15} else '',
    )
    request = SimpleNamespace(headers={}, client=SimpleNamespace(host='127.0.0.1'))

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
    assert replay.headers['location'] == first.headers['location']
    assert database.updates[0]['is_verified'] is True
    assert database.updates[0]['verification_token_expires'] == '2099-01-01T00:15:00+00:00'
    assert 'verification_token_hash' not in database.updates[0]
    assert len(database.updates) == 1
    assert len(session_users) == 2
    assert cookies == ['session-token-1', 'session-token-2']


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
async def test_authorized_durable_recovery_token_can_issue_session(monkeypatch):
    database = RecoveryVerificationDB()

    async def fake_create_session(db, settings, user, request, **kwargs):
        assert db is database
        assert user['is_verified'] is True
        return 'recovered-session', {'id': 'session-recovered'}

    monkeypatch.setattr(auth_routes, 'db', database)
    monkeypatch.setattr(
        auth_routes,
        'settings',
        SimpleNamespace(
            app_url='https://www.askcrump.com',
            environment='test',
            verification_email_recovery_enabled=True,
        ),
    )
    monkeypatch.setattr(auth_routes, 'create_session', fake_create_session)
    monkeypatch.setattr(auth_routes, 'set_session_cookie', lambda *_args: None)
    request = SimpleNamespace(headers={}, client=SimpleNamespace(host='127.0.0.1'))

    response = await auth_routes.verify_email('recovery-token', request)

    assert response.status_code == 303
    assert response.headers['location'].endswith('/app?verification=success')
    assert database.calls == [
        (
            'consume_verification_email_recovery_token',
            {
                'p_recovery_token_hash': token_hash('recovery-token'),
                'p_environment': 'test',
            },
            {'retry_transient': True, 'timeout': 3.0},
        )
    ]


@pytest.mark.asyncio
async def test_recovery_then_original_and_both_replays_share_one_handoff(monkeypatch):
    database = DualLinkVerificationDB()
    request, sessions = configure_dual_link_route(monkeypatch, database)

    responses = [
        await auth_routes.verify_email('recovery-token', request),
        await auth_routes.verify_email('original-token', request),
        await auth_routes.verify_email('recovery-token', request),
        await auth_routes.verify_email('original-token', request),
    ]

    assert all(response.status_code == 303 for response in responses)
    assert all(response.headers['location'].endswith('verification=success') for response in responses)
    assert database.user['verification_token_hash'] == database.original_hash
    assert database.foreign_user['is_verified'] is False
    assert database.updates == []
    assert sessions == ['user-dual-link'] * 4


@pytest.mark.asyncio
async def test_original_then_recovery_and_both_replays_share_one_handoff(monkeypatch):
    database = DualLinkVerificationDB()
    request, sessions = configure_dual_link_route(monkeypatch, database)

    responses = [
        await auth_routes.verify_email('original-token', request),
        await auth_routes.verify_email('recovery-token', request),
        await auth_routes.verify_email('original-token', request),
        await auth_routes.verify_email('recovery-token', request),
    ]

    assert all(response.status_code == 303 for response in responses)
    assert all(response.headers['location'].endswith('verification=success') for response in responses)
    assert len(database.updates) == 1
    assert 'verification_token_hash' not in database.updates[0]
    assert database.user['verification_token_hash'] == database.original_hash
    assert database.foreign_user['is_verified'] is False
    assert sessions == ['user-dual-link'] * 4


@pytest.mark.asyncio
async def test_expired_or_foreign_dual_link_cannot_verify_or_issue_session(monkeypatch):
    database = DualLinkVerificationDB(original_valid=False, recovery_valid=False)
    database.handoff_valid = False
    request, sessions = configure_dual_link_route(monkeypatch, database)

    expired_original = await auth_routes.verify_email('original-token', request)
    expired_recovery = await auth_routes.verify_email('recovery-token', request)
    foreign_recovery = await auth_routes.verify_email('foreign-recovery-token', request)

    assert expired_original.headers['location'].endswith('verification=failed')
    assert expired_recovery.headers['location'].endswith('verification=failed')
    assert foreign_recovery.headers['location'].endswith('verification=failed')
    assert database.user['is_verified'] is False
    assert database.foreign_user['is_verified'] is False
    assert database.updates == []
    assert sessions == []


@pytest.mark.asyncio
async def test_successful_verification_discards_unknown_destination_values(monkeypatch):
    database = VerificationDB({
        'id': 'user-1',
        'email': 'new-user@example.com',
        'is_verified': True,
        'verification_token_hash': token_hash('verification-token'),
        'verification_token_expires': '2099-01-01T00:00:00+00:00',
    })

    async def fake_create_session(*_args, **_kwargs):
        return 'session-token', {'id': 'session-1'}

    monkeypatch.setattr(auth_routes, 'db', database)
    monkeypatch.setattr(auth_routes, 'settings', SimpleNamespace(app_url='https://www.askcrump.com'))
    monkeypatch.setattr(auth_routes, 'create_session', fake_create_session)
    monkeypatch.setattr(auth_routes, 'set_session_cookie', lambda *_args, **_kwargs: None)
    request = SimpleNamespace(headers={}, client=SimpleNamespace(host='127.0.0.1'))

    response = await auth_routes.verify_email(
        'verification-token',
        request,
        intent='private customer prompt',
        plan='free',
    )

    assert response.headers['location'] == 'https://www.askcrump.com/app?verification=success'


def test_verification_email_promises_the_one_click_workspace_handoff():
    source = Path(auth_routes.__file__).resolve().parents[1] / 'email_service.py'
    email_source = source.read_text(encoding='utf-8')

    assert 'Confirm your email and open your Ask Crump workspace.' in email_source
    assert 'Verify &amp; open Ask Crump' in email_source
    assert 'same link can open your workspace for 15 minutes' in email_source
