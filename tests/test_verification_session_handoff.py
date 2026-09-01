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
