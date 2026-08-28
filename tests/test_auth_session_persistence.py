from pathlib import Path
from types import SimpleNamespace

import pytest
from starlette.requests import Request
from starlette.responses import Response

from backend import http
from backend.auth_service import authenticate_request, session_tokens_from_request
from backend.db import eq
from backend.security import token_hash


ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / 'public'


def test_same_page_login_is_serialized_and_confirmed():
    source = (PUBLIC / 'device-auth.js').read_text(encoding='utf-8')
    shell = (PUBLIC / 'app.html').read_text(encoding='utf-8')
    worker = (PUBLIC / 'sw.js').read_text(encoding='utf-8')
    assert 'this.loginPromise = null' in source
    assert 'if (this.loginPromise) return this.loginPromise' in source
    assert 'confirmIssuedSession()' in source
    assert "fetch('/api/auth/check-session'" in source
    assert 'for (const delay of [0, 75, 200])' in source
    assert 'for (let attempt = 0; attempt < 2; attempt += 1)' not in source
    assert "code: 'SESSION_ESTABLISHMENT_FAILED'" in source
    assert 'src="/device-auth.js?v=5.9.43"' in shell
    assert "'/device-auth.js?v=5.9.43'" in worker
    assert "url.pathname === '/device-auth.js'" in worker


class DuplicateCookieDB:
    def __init__(self):
        self.session_hashes = []

    async def select_one(self, table, *, columns='*', filters=None):
        if table == 'sessions':
            self.session_hashes.append(filters['token_hash'])
            if filters['token_hash'] == eq(token_hash('fresh-token')):
                return {
                    'id': 'session-1',
                    'user_id': 'user-1',
                    'last_activity': None,
                    'expires_at': '2099-01-01T00:00:00+00:00',
                }
            return None
        if table == 'users':
            return {'id': 'user-1', 'email': 'user@example.com', 'deleted_at': None}
        return None


@pytest.mark.asyncio
async def test_duplicate_session_cookies_use_the_valid_candidate():
    request = Request({
        'type': 'http',
        'method': 'GET',
        'path': '/api/auth/check-session',
        'headers': [
            (b'cookie', b'crump_session=stale-token; crump_session=fresh-token'),
        ],
        'client': ('127.0.0.1', 12345),
    })
    settings = SimpleNamespace(session_cookie_name='crump_session', session_days=365)
    db = DuplicateCookieDB()

    assert session_tokens_from_request(request, settings) == ('stale-token', 'fresh-token')
    authenticated = await authenticate_request(request, db, settings, touch=False)

    assert authenticated.token == 'fresh-token'
    assert db.session_hashes == [eq(token_hash('stale-token')), eq(token_hash('fresh-token'))]


def test_explicit_bearer_token_does_not_fall_back_to_browser_cookies():
    request = Request({
        'type': 'http',
        'method': 'GET',
        'path': '/api/auth/check-session',
        'headers': [
            (b'authorization', b'Bearer native-token'),
            (b'cookie', b'crump_session=browser-token'),
        ],
        'client': ('127.0.0.1', 12345),
    })
    settings = SimpleNamespace(session_cookie_name='crump_session')

    assert session_tokens_from_request(request, settings) == ('native-token',)


def test_web_login_retires_a_legacy_parent_domain_cookie(monkeypatch):
    monkeypatch.setattr(http, 'settings', SimpleNamespace(
        app_url='https://www.askcrump.com',
        cookie_domain=None,
        cookie_secure=True,
        session_cookie_name='crump_session',
        session_days=365,
    ))
    request = Request({
        'type': 'http',
        'method': 'POST',
        'path': '/api/auth/login',
        'headers': [(b'host', b'www.askcrump.com')],
        'client': ('127.0.0.1', 12345),
    })
    response = Response()

    http.set_session_cookie(response, 'fresh-token', request)

    cookies = [
        value.decode('latin-1')
        for name, value in response.raw_headers
        if name.lower() == b'set-cookie'
    ]
    assert any('Domain=askcrump.com' in value and 'Max-Age=0' in value for value in cookies)
    assert any('crump_session=fresh-token' in value and 'Domain=' not in value for value in cookies)


def test_transient_session_check_does_not_clear_persisted_identity():
    source = (PUBLIC / 'device-auth.js').read_text(encoding='utf-8')
    assert 'if (!response.ok)' in source
    assert 'return this.sessionUnavailable' in source
    assert 'A definitive successful response saying "not authenticated" is the only' in source
    assert 'this.clearLocalState();' in source


def test_bootstrap_surfaces_unavailable_without_claiming_logout():
    source = (PUBLIC / 'auth-controller.js').read_text(encoding='utf-8')
    assert 'if (session.unavailable)' in source
    assert 'Your saved sign-in was preserved' in source


def test_explicit_logout_still_clears_native_and_local_state():
    source = (PUBLIC / 'device-auth.js').read_text(encoding='utf-8')
    assert 'await window.CrumpAPI?.clearSessionToken?.();' in source
    assert 'this.clearLocalState();' in source
