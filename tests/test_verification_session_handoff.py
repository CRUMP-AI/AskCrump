import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.routes import auth as auth_routes
from backend.schemas import ResetPasswordRequest
from backend.security import token_hash


class VerificationDB:
    def __init__(self, user):
        self.user = dict(user) if user else None
        self.updates = []
        self.successful_updates = []

    @staticmethod
    def _matches(row, filters):
        for key, raw_filter in filters.items():
            if raw_filter == 'is.null':
                if row.get(key) is not None:
                    return False
                continue
            if isinstance(raw_filter, str) and raw_filter.startswith('eq.'):
                expected = raw_filter[3:]
                if expected == 'true':
                    expected = True
                elif expected == 'false':
                    expected = False
                if row.get(key) != expected:
                    return False
                continue
            if isinstance(raw_filter, str) and raw_filter.startswith('gt.'):
                if not row.get(key) or str(row.get(key)) <= raw_filter[3:]:
                    return False
                continue
            if row.get(key) != raw_filter:
                return False
        return True

    async def select_one(self, table, **kwargs):
        assert table == 'users'
        if not self.user or not self._matches(self.user, kwargs['filters']):
            return None
        return dict(self.user)

    async def update(self, table, values, *, filters):
        assert table == 'users'
        self.updates.append(dict(values))
        if not self.user or not self._matches(self.user, filters):
            return []
        self.user.update(values)
        self.successful_updates.append(dict(values))
        return [dict(self.user)]


class VerificationRaceDB(VerificationDB):
    def __init__(
        self,
        user,
        *,
        pause_after_verification_select=False,
        synchronize_verification_selects=False,
    ):
        super().__init__(user)
        self.pause_after_verification_select = pause_after_verification_select
        self.synchronize_verification_selects = synchronize_verification_selects
        self.verification_selected = asyncio.Event()
        self.resume_verification = asyncio.Event()
        self.verification_select_count = 0
        self.all_verifications_selected = asyncio.Event()
        self.sessions = []
        self.session_updates = []
        self._reset_lock = asyncio.Lock()

    async def select_one(self, table, **kwargs):
        selected = await super().select_one(table, **kwargs)
        filters = kwargs['filters']
        is_initial_verification = (
            table == 'users'
            and 'verification_token_hash' in filters
            and 'id' not in filters
        )
        if selected and is_initial_verification and self.pause_after_verification_select:
            self.pause_after_verification_select = False
            self.verification_selected.set()
            await asyncio.wait_for(self.resume_verification.wait(), timeout=2)
        elif selected and is_initial_verification and self.synchronize_verification_selects:
            self.verification_select_count += 1
            if self.verification_select_count == 2:
                self.all_verifications_selected.set()
            await asyncio.wait_for(self.all_verifications_selected.wait(), timeout=2)
        return selected

    async def update(self, table, values, *, filters):
        if table == 'users':
            return await super().update(table, values, filters=filters)
        assert table == 'sessions'
        self.session_updates.append({'values': dict(values), 'filters': dict(filters)})
        updated = []
        for session in self.sessions:
            if self._matches(session, filters):
                session.update(values)
                updated.append(dict(session))
        return updated

    async def rpc(self, function_name, payload):
        assert function_name == 'consume_password_reset'
        async with self._reset_lock:
            if (
                self.user['password_reset_token_hash']
                != payload['p_presented_token_hash']
                or self.user['password_reset_expires'] <= payload['p_now']
            ):
                return None
            was_verified = bool(self.user.get('is_verified'))
            self.user.update({
                'password_hash': payload['p_new_password_hash'],
                'auth_generation': int(self.user.get('auth_generation') or 0) + 1,
                'is_verified': True,
                'verification_token_hash': None,
                'verification_token_expires': None,
                'password_reset_token_hash': None,
                'password_reset_expires': None,
                'updated_at': payload['p_now'],
            })
            if not was_verified:
                self.user.update({
                    'full_name': None,
                    'terms_accepted_at': None,
                    'terms_version': None,
                })
            for session in self.sessions:
                if session['user_id'] == self.user['id'] and session['revoked_at'] is None:
                    session['revoked_at'] = payload['p_now']
            return {
                'id': self.user['id'],
                'auth_generation': self.user['auth_generation'],
            }

    def persist_session(self, raw_token, *, session_id='verification-session-1'):
        session = {
            'id': session_id,
            'user_id': self.user['id'],
            'token_hash': token_hash(raw_token),
            'revoked_at': None,
            'auth_generation': int(self.user.get('auth_generation') or 0),
        }
        self.sessions.append(session)
        return dict(session)


RESET_TOKEN = 'owner-password-reset-token'


def verification_user():
    return {
        'id': 'user-1',
        'email': 'new-user@example.com',
        'password_hash': 'original-password-hash',
        'full_name': 'Unproven Name',
        'terms_accepted_at': '2026-09-01T00:00:00+00:00',
        'terms_version': '2026-08-23',
        'is_verified': False,
        'verification_token_hash': token_hash('verification-token'),
        'verification_token_expires': '2099-01-01T00:00:00+00:00',
        'password_reset_token_hash': token_hash(RESET_TOKEN),
        'password_reset_expires': '2099-01-01T00:00:00+00:00',
    }


def auth_request():
    return SimpleNamespace(headers={}, client=SimpleNamespace(host='127.0.0.1'))


async def allow_rate_limit(*_args, **_kwargs):
    return None


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
async def test_concurrent_scanner_replay_keeps_token_and_issues_both_sessions(monkeypatch):
    database = VerificationRaceDB(
        verification_user(),
        synchronize_verification_selects=True,
    )
    session_users = []
    cookies = []

    async def fake_create_session(db, settings, user, request, **kwargs):
        assert db is database
        session_users.append(dict(user))
        sequence = len(session_users)
        return f'scanner-session-token-{sequence}', {'id': f'scanner-session-{sequence}'}

    monkeypatch.setattr(auth_routes, 'db', database)
    monkeypatch.setattr(auth_routes, 'settings', SimpleNamespace(app_url='https://www.askcrump.com'))
    monkeypatch.setattr(auth_routes, 'create_session', fake_create_session)
    monkeypatch.setattr(
        auth_routes,
        'set_session_cookie',
        lambda _response, raw_token, _request: cookies.append(raw_token),
    )

    responses = await asyncio.gather(
        auth_routes.verify_email('verification-token', auth_request()),
        auth_routes.verify_email('verification-token', auth_request()),
    )

    assert all(response.status_code == 303 for response in responses)
    assert all('verification=success' in response.headers['location'] for response in responses)
    assert database.user['is_verified'] is True
    assert database.user['verification_token_hash'] == token_hash('verification-token')
    assert len(database.updates) == 2
    assert len(database.successful_updates) == 1
    assert len(session_users) == 2
    assert cookies == ['scanner-session-token-1', 'scanner-session-token-2']


@pytest.mark.asyncio
async def test_password_reset_wins_after_stale_verification_select(monkeypatch):
    database = VerificationRaceDB(
        verification_user(),
        pause_after_verification_select=True,
    )
    cookies = []

    async def fail_create_session(*_args, **_kwargs):
        raise AssertionError('stale verification must not create a session')

    monkeypatch.setattr(auth_routes, 'db', database)
    monkeypatch.setattr(auth_routes, 'settings', SimpleNamespace(app_url='https://www.askcrump.com'))
    monkeypatch.setattr(auth_routes, 'create_session', fail_create_session)
    monkeypatch.setattr(
        auth_routes,
        'set_session_cookie',
        lambda _response, raw_token, _request: cookies.append(raw_token),
    )
    monkeypatch.setattr(auth_routes, 'enforce_auth_rate_limit', allow_rate_limit)
    monkeypatch.setattr(auth_routes, 'hash_password', lambda _password: 'new-password-hash')

    verification_task = asyncio.create_task(
        auth_routes.verify_email('verification-token', auth_request())
    )
    await asyncio.wait_for(database.verification_selected.wait(), timeout=2)
    reset = await auth_routes.reset_password(
        ResetPasswordRequest(token=RESET_TOKEN, newPassword='InboxOwnerPass2'),
        auth_request(),
    )
    database.resume_verification.set()
    verification = await verification_task

    assert reset['success'] is True
    assert verification.status_code == 303
    assert verification.headers['location'] == 'https://www.askcrump.com/app?verification=failed'
    assert 'set-cookie' not in verification.headers
    assert cookies == []
    assert database.sessions == []
    assert database.user['verification_token_hash'] is None
    assert database.user['password_reset_token_hash'] is None


@pytest.mark.asyncio
async def test_password_reset_between_session_persist_and_postcheck_revokes_exact_session(
    monkeypatch,
):
    database = VerificationRaceDB(verification_user())
    session_persisted = asyncio.Event()
    resume_session_creation = asyncio.Event()
    cookies = []
    raw_session_token = 'persisted-verification-session-token'

    async def paused_create_session(db, settings, user, request, **kwargs):
        assert db is database
        session = database.persist_session(raw_session_token)
        session_persisted.set()
        await asyncio.wait_for(resume_session_creation.wait(), timeout=2)
        return raw_session_token, session

    monkeypatch.setattr(auth_routes, 'db', database)
    monkeypatch.setattr(auth_routes, 'settings', SimpleNamespace(app_url='https://www.askcrump.com'))
    monkeypatch.setattr(auth_routes, 'create_session', paused_create_session)
    monkeypatch.setattr(
        auth_routes,
        'set_session_cookie',
        lambda _response, raw_token, _request: cookies.append(raw_token),
    )
    monkeypatch.setattr(auth_routes, 'enforce_auth_rate_limit', allow_rate_limit)
    monkeypatch.setattr(auth_routes, 'hash_password', lambda _password: 'new-password-hash')

    verification_task = asyncio.create_task(
        auth_routes.verify_email('verification-token', auth_request())
    )
    await asyncio.wait_for(session_persisted.wait(), timeout=2)
    reset = await auth_routes.reset_password(
        ResetPasswordRequest(token=RESET_TOKEN, newPassword='InboxOwnerPass2'),
        auth_request(),
    )
    resume_session_creation.set()
    verification = await verification_task

    assert reset['success'] is True
    assert verification.status_code == 303
    assert verification.headers['location'] == 'https://www.askcrump.com/app?verification=failed'
    assert 'set-cookie' not in verification.headers
    assert cookies == []
    assert len(database.sessions) == 1
    assert database.sessions[0]['revoked_at'] is not None
    assert not [session for session in database.sessions if session['revoked_at'] is None]
    exact_revoke = database.session_updates[-1]
    assert exact_revoke['filters'] == {
        'id': 'eq.verification-session-1',
        'user_id': 'eq.user-1',
        'token_hash': f'eq.{token_hash(raw_session_token)}',
        'revoked_at': 'is.null',
    }


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
