from __future__ import annotations

import asyncio
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI, Request, Response

from backend import http
from backend.auth_service import AuthenticatedUser, AuthenticationError
from backend.db import DatabaseError
from backend.routes import auth as auth_routes
from backend.schemas import LoginRequest


USER = {
    'id': '10000000-0000-4000-8000-000000000001',
    'email': 'settings@example.com',
    'is_verified': True,
    'password_hash': '$argon2id$only-a-test-fixture',
    'password_setup_required': False,
}
SESSION = {'id': 'session-1', 'expires_at': '2099-01-01T00:00:00+00:00'}


@pytest.fixture
def auth_setup(monkeypatch):
    state = {'validated': False, 'settings_calls': [], 'cancelled': False}

    async def allow_rate_limit(*_args, **_kwargs):
        return None

    async def finalized_login(*_args, **_kwargs):
        state['validated'] = True
        return 'issued-test-token', dict(USER), dict(SESSION)

    async def authenticated_session(*_args, **_kwargs):
        state['validated'] = True
        return AuthenticatedUser(dict(USER), dict(SESSION), 'existing-test-token')

    monkeypatch.setattr(auth_routes, 'enforce_auth_rate_limit', allow_rate_limit)
    monkeypatch.setattr(auth_routes, 'verify_password', lambda *_args: True)
    monkeypatch.setattr(auth_routes, 'password_hash_needs_upgrade', lambda *_args: False)
    monkeypatch.setattr(auth_routes, 'finalize_login_session', finalized_login)
    monkeypatch.setattr(auth_routes, 'authenticate_request', authenticated_session)
    monkeypatch.setattr(auth_routes, '_AUTH_SETTINGS_TIMEOUT_SECONDS', 0.01)
    monkeypatch.setattr(http, 'settings', SimpleNamespace(
        app_url='http://testserver',
        cookie_domain=None,
        cookie_secure=False,
        session_cookie_name='test_session',
        session_days=365,
    ))
    return state


def mock_settings_database(monkeypatch, state, *, outcome):
    async def select_one(table, **kwargs):
        if table == 'users':
            return dict(USER)
        assert table == 'user_settings'
        assert state['validated'], 'preferences must follow essential authentication'
        state['settings_calls'].append(kwargs['filters'])
        if outcome == 'hang':
            try:
                await asyncio.Event().wait()
            finally:
                state['cancelled'] = True
        if outcome == 'failure':
            raise DatabaseError('settings unavailable', 503)
        return outcome

    monkeypatch.setattr(auth_routes, 'db', SimpleNamespace(select_one=select_one))


async def call_auth_route(endpoint, *, native=False):
    headers = [(b'host', b'testserver')]
    if native:
        headers.append((b'x-crump-client', b'native'))
    request = Request({
        'type': 'http',
        'method': 'POST' if endpoint == 'login' else 'GET',
        'path': f'/api/auth/{endpoint}',
        'headers': headers,
        'client': ('127.0.0.1', 12345),
    })
    response = Response()
    if endpoint == 'login':
        result = await auth_routes.login(
            LoginRequest(email=USER['email'], password='FixturePassword1'),
            request,
            response,
        )
    else:
        result = await auth_routes.check_session(request, response)
    return result, response


@pytest.mark.asyncio
@pytest.mark.parametrize('endpoint', ['login', 'check-session'])
@pytest.mark.parametrize('outcome', ['hang', 'failure'])
async def test_optional_preferences_do_not_withhold_authentication(
    monkeypatch, auth_setup, endpoint, outcome,
):
    mock_settings_database(monkeypatch, auth_setup, outcome=outcome)

    result, response = await asyncio.wait_for(call_auth_route(endpoint), timeout=0.5)

    assert result['success'] is True
    if endpoint == 'check-session':
        assert result['authenticated'] is True
    else:
        assert 'test_session=issued-test-token' in response.headers['set-cookie']
    assert result['data']['user']['id'] == USER['id']
    assert result['data']['expiresAt'] == SESSION['expires_at']
    assert result['data']['settings'] is None
    assert result['data']['settingsUnavailable'] is True
    assert auth_setup['settings_calls'] == [{'user_id': f"eq.{USER['id']}"}]
    assert auth_setup['cancelled'] is (outcome == 'hang')


@pytest.mark.asyncio
@pytest.mark.parametrize('outcome', ['hang', 'failure'])
async def test_native_login_keeps_issued_token_when_settings_are_unavailable(
    monkeypatch, auth_setup, outcome,
):
    mock_settings_database(monkeypatch, auth_setup, outcome=outcome)

    result, response = await asyncio.wait_for(
        call_auth_route('login', native=True), timeout=0.5,
    )

    assert result['success'] is True
    assert result['data']['sessionToken'] == 'issued-test-token'
    assert result['data']['settings'] is None
    assert result['data']['settingsUnavailable'] is True
    assert 'set-cookie' not in response.headers


@pytest.mark.asyncio
@pytest.mark.parametrize('endpoint', ['login', 'check-session'])
@pytest.mark.parametrize('preferences', [None, {'assistant_name': 'Saved assistant'}])
async def test_optional_settings_preserve_loaded_and_absent_rows(
    monkeypatch, auth_setup, endpoint, preferences,
):
    mock_settings_database(monkeypatch, auth_setup, outcome=preferences)

    result, _response = await call_auth_route(endpoint)

    assert result['success'] is True
    assert result['data']['settings'] == preferences
    assert result['data']['settingsUnavailable'] is False


@pytest.mark.asyncio
@pytest.mark.parametrize('endpoint', ['login', 'check-session'])
async def test_essential_database_failure_is_not_optional(
    monkeypatch, auth_setup, endpoint,
):
    mock_settings_database(monkeypatch, auth_setup, outcome=None)

    async def essential_failure(*_args, **_kwargs):
        raise DatabaseError('essential auth unavailable', 503)

    monkeypatch.setattr(auth_routes, 'finalize_login_session', essential_failure)
    monkeypatch.setattr(auth_routes, 'authenticate_request', essential_failure)

    with pytest.raises(DatabaseError, match='essential auth unavailable'):
        await call_auth_route(endpoint)
    assert auth_setup['settings_calls'] == []


@pytest.mark.asyncio
async def test_session_owner_mismatch_still_fails_before_settings(monkeypatch, auth_setup):
    mock_settings_database(monkeypatch, auth_setup, outcome=None)

    async def owner_mismatch(*_args, **_kwargs):
        raise AuthenticationError(
            'Signed-in account changed.', status_code=409, code='AUTH_OWNER_MISMATCH',
        )

    monkeypatch.setattr(auth_routes, 'authenticate_request', owner_mismatch)

    with pytest.raises(AuthenticationError) as captured:
        await call_auth_route('check-session')
    assert captured.value.status_code == 409
    assert auth_setup['settings_calls'] == []


@pytest.mark.asyncio
@pytest.mark.parametrize('status, code', [
    (403, 'AUTH_REQUIRED'),
    (409, 'AUTH_OWNER_MISMATCH'),
    (503, 'AUTH_REQUIRED'),
])
async def test_session_health_preserves_non_401_failures_for_unavailable_client_state(
    monkeypatch, auth_setup, status, code,
):
    mock_settings_database(monkeypatch, auth_setup, outcome=None)

    async def unavailable_session(*_args, **_kwargs):
        raise AuthenticationError(
            'Session checking is temporarily unavailable.', status_code=status, code=code,
        )

    monkeypatch.setattr(auth_routes, 'authenticate_request', unavailable_session)
    application = FastAPI()
    application.include_router(auth_routes.router)
    http.register_exception_handlers(application)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url='http://testserver',
    ) as client:
        response = await client.get('/api/auth/check-session')

    assert response.status_code == status
    assert response.json() == {
        'success': False,
        'authenticated': False,
        'error': 'Session checking is temporarily unavailable.',
        'code': code,
    }
    assert auth_setup['settings_calls'] == []
    assert 'set-cookie' not in response.headers


@pytest.mark.asyncio
async def test_authoritative_expired_session_still_returns_signed_out(monkeypatch, auth_setup):
    mock_settings_database(monkeypatch, auth_setup, outcome=None)

    async def expired_session(*_args, **_kwargs):
        raise AuthenticationError('Your session has expired. Please sign in again.')

    monkeypatch.setattr(auth_routes, 'authenticate_request', expired_session)

    result, response = await call_auth_route('check-session')

    assert result == {'success': True, 'authenticated': False}
    assert auth_setup['settings_calls'] == []
    assert 'set-cookie' not in response.headers


@pytest.mark.asyncio
async def test_request_cancellation_does_not_become_settings_success(monkeypatch, auth_setup):
    mock_settings_database(monkeypatch, auth_setup, outcome='hang')
    monkeypatch.setattr(auth_routes, '_AUTH_SETTINGS_TIMEOUT_SECONDS', 10.0)
    task = asyncio.create_task(call_auth_route('check-session'))
    while not auth_setup['settings_calls']:
        await asyncio.sleep(0)

    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task
    assert auth_setup['cancelled'] is True
