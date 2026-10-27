from pathlib import Path
from types import SimpleNamespace

import pytest
from starlette.requests import Request
from starlette.responses import Response

from backend import http
from backend.routes import auth as auth_routes
from backend.auth_service import (
    AuthenticationError,
    AuthenticatedUser,
    authenticate_request,
    session_tokens_from_request,
    touch_authenticated_session,
)
from backend.db import eq
from backend.policy_consent import CURRENT_POLICY_BUNDLE_HASH, CURRENT_POLICY_BUNDLE_ID
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
    assert "CrumpAuthTransport.request('/api/auth/check-session'" in source
    assert 'for (const delay of [0, 100, 300, 750, 1500])' in source
    assert 'for (const delay of [0, 150, 500, 1000, 2000])' in source
    assert "code !== 'AUTH_REQUEST_TIMEOUT'" in source
    assert 'for (let attempt = 0; attempt < 2; attempt += 1)' not in source
    assert "code: 'SESSION_ESTABLISHMENT_FAILED'" in source
    assert 'src="/device-auth.js?v=5.9.76-account-owner-boundary-1"' in shell
    assert "'/device-auth.js?v=5.9.76-account-owner-boundary-1'" in worker
    assert "url.pathname === '/device-auth.js'" in worker


def test_sleeping_pwa_checks_for_updates_and_adopts_safe_signed_out_runtime():
    installer = (PUBLIC / 'install-prompt.js').read_text(encoding='utf-8')
    styles = (PUBLIC / 'install-prompt.css').read_text(encoding='utf-8')
    shell = (PUBLIC / 'app.html').read_text(encoding='utf-8')
    worker = (PUBLIC / 'sw.js').read_text(encoding='utf-8')

    assert "navigator.serviceWorker.addEventListener('controllerchange'" in installer
    assert "document.addEventListener('visibilitychange'" in installer
    assert "window.addEventListener('pageshow'" in installer
    assert 'serviceWorkerRegistration.update()' in installer
    assert "runtimeWorkRequiresDeferral()" in installer
    assert "document.body.classList.contains('crump-precision-open')" in installer
    assert "document.body.classList.contains('crump50-sending')" in installer
    assert "visibleElementHasWork(document.getElementById('userInput'))" in installer
    assert "filePreview.childElementCount" in installer
    assert "#appContainer [aria-busy=\"true\"]" in installer
    assert "runtimeUpdateWasDeferred" in installer
    assert "updateNoticeDismissed" in installer
    assert "window.sessionStorage.setItem(reloadGuardKey" in installer
    assert 'Reload when you’re ready to use the latest reliability fixes.' in installer
    assert '.runtime-update-notice' in styles
    assert 'src="/install-prompt.js?v=5.9.76-update-work-guard-1"' in shell
    assert "'/install-prompt.js?v=5.9.76-update-work-guard-1'" in worker
    assert "url.pathname === '/install-prompt.js'" in worker


def test_runtime_update_guard_distinguishes_unchecked_controls_from_real_auth_work():
    installer = (PUBLIC / 'install-prompt.js').read_text(encoding='utf-8')
    fixture = (ROOT / 'tests' / 'fixtures' / 'runtime-update-auth-guard.html').read_text(
        encoding='utf-8',
    )
    verifier = (ROOT / 'scripts' / 'verify-runtime-update-auth-guard.cjs').read_text(
        encoding='utf-8',
    )

    assert "type === 'checkbox' || type === 'radio'" in installer
    assert 'input.checked === true' in installer
    assert "type === 'file'" in installer
    assert 'Boolean(input.files?.length)' in installer
    assert ".some(authInputHasWork)" in installer
    assert "some(input => Boolean(input.value))" not in installer
    assert 'runtime-update-auth-guard-fixture-1' in fixture
    assert "mode === 'typed'" in fixture
    assert "mode === 'checked'" in fixture
    assert "open('clean')" in verifier
    assert "runDeferred('typed'" in verifier
    assert "runDeferred('checked'" in verifier
    assert "runDeferred('draft'" in verifier
    assert "runDeferred('file'" in verifier
    assert "runDeferred('precision'" in verifier
    assert "runDeferred('sending'" in verifier
    assert "open('signedin')" in verifier
    assert "clean.status, 'reloaded'" in verifier
    assert "result.before.status, 'deferred'" in verifier
    assert "result.before.notice, 0" in verifier
    assert "lateDraft.notice, 0" in verifier
    assert "latePrecision.reloadGuard, false" in verifier


def test_auth_outcome_logs_are_categorical_and_identity_free():
    source = (ROOT / 'backend' / 'routes' / 'auth.py').read_text(encoding='utf-8')

    assert 'Auth login outcome=invalid_credentials client=%s' in source
    assert 'Auth login outcome=verification_required client=%s' in source
    assert 'Auth login outcome=session_issued client=%s' in source
    assert 'Auth session outcome=unauthenticated client=%s' in source
    assert 'Auth session outcome=authenticated client=%s' in source
    assert "logger.info('Auth login outcome=session_issued client=%s', email" not in source


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

    async def rpc(self, name, payload, **_kwargs):
        assert name == 'read_current_policy_acceptance_v1'
        return [{
            'receipt_id': '33333333-3333-4333-8333-333333333333',
            'accepted_at': '2026-10-27T00:00:00+00:00',
            'bundle_id': CURRENT_POLICY_BUNDLE_ID,
            'bundle_hash': CURRENT_POLICY_BUNDLE_HASH,
        }]


class ExpectedOwnerDB:
    owner_id = '22222222-2222-4222-8222-222222222222'

    def __init__(self):
        self.updates = []
        self.selects = []

    async def select_one(self, table, *, columns='*', filters=None):
        self.selects.append(table)
        if table == 'sessions':
            return {
                'id': 'session-owner-boundary',
                'user_id': self.owner_id,
                'last_activity': None,
                'expires_at': '2099-01-01T00:00:00+00:00',
            }
        if table == 'users':
            return {'id': self.owner_id, 'email': 'owner@example.test', 'deleted_at': None}
        return None

    async def update(self, table, payload, *, filters):
        self.updates.append((table, dict(payload), dict(filters)))
        return []

    async def rpc(self, name, payload, **_kwargs):
        assert name == 'read_current_policy_acceptance_v1'
        return [{
            'receipt_id': '33333333-3333-4333-8333-333333333333',
            'accepted_at': '2026-10-27T00:00:00+00:00',
            'bundle_id': CURRENT_POLICY_BUNDLE_ID,
            'bundle_hash': CURRENT_POLICY_BUNDLE_HASH,
        }]


def owner_request(*, expected_owner=None, bearer=False):
    headers = []
    if bearer:
        headers.append((b'authorization', b'Bearer owner-token'))
    else:
        headers.append((b'cookie', b'crump_session=owner-token'))
    if expected_owner is not None:
        headers.append((b'x-ask-crump-expected-owner', str(expected_owner).encode('utf-8')))
    return Request({
        'type': 'http',
        'method': 'PATCH',
        'path': '/api/account/profile',
        'headers': headers,
        'client': ('127.0.0.1', 12345),
    })


@pytest.mark.asyncio
async def test_cookie_owner_precondition_matches_before_normal_session_touch():
    db = ExpectedOwnerDB()
    settings = SimpleNamespace(session_cookie_name='crump_session', session_days=365)

    auth = await authenticate_request(
        owner_request(expected_owner=db.owner_id),
        db,
        settings,
        require_expected_owner_header=True,
    )

    assert auth.user['id'] == db.owner_id
    assert [call[0] for call in db.updates] == ['sessions']


@pytest.mark.parametrize(
    'expected_owner',
    ('11111111-1111-4111-8111-111111111111', 'not-a-uuid', 'é' * 24),
)
@pytest.mark.asyncio
async def test_cookie_owner_precondition_rejects_before_any_session_touch(expected_owner):
    db = ExpectedOwnerDB()
    settings = SimpleNamespace(session_cookie_name='crump_session', session_days=365)

    with pytest.raises(AuthenticationError) as captured:
        await authenticate_request(
            owner_request(expected_owner=expected_owner),
            db,
            settings,
            require_expected_owner_header=True,
        )

    assert captured.value.status_code == 409
    assert captured.value.code == 'AUTH_OWNER_MISMATCH'
    assert captured.value.details == {'staleAuth': True, 'retryable': True}
    assert db.updates == []
    assert db.selects == ['sessions']


@pytest.mark.asyncio
async def test_legacy_cookie_without_owner_claim_remains_compatible_during_rollout():
    db = ExpectedOwnerDB()
    settings = SimpleNamespace(session_cookie_name='crump_session', session_days=365)

    auth = await authenticate_request(
        owner_request(),
        db,
        settings,
        require_expected_owner_header=True,
    )

    assert auth.user['id'] == db.owner_id
    assert db.selects == ['sessions', 'users']
    assert [call[0] for call in db.updates] == ['sessions']


@pytest.mark.asyncio
async def test_supplied_owner_precondition_is_enforced_on_legacy_unflagged_routes():
    db = ExpectedOwnerDB()
    settings = SimpleNamespace(session_cookie_name='crump_session', session_days=365)

    with pytest.raises(AuthenticationError) as captured:
        await authenticate_request(
            owner_request(expected_owner='11111111-1111-4111-8111-111111111111'),
            db,
            settings,
        )

    assert captured.value.status_code == 409
    assert captured.value.code == 'AUTH_OWNER_MISMATCH'
    assert db.updates == []
    assert db.selects == ['sessions']


@pytest.mark.asyncio
async def test_legacy_native_bearer_without_owner_claim_remains_compatible():
    db = ExpectedOwnerDB()
    settings = SimpleNamespace(session_cookie_name='crump_session', session_days=365)

    auth = await authenticate_request(
        owner_request(bearer=True),
        db,
        settings,
        require_expected_owner_header=True,
    )

    assert auth.user['id'] == db.owner_id
    assert [call[0] for call in db.updates] == ['sessions']


@pytest.mark.asyncio
async def test_session_health_preserves_owner_mismatch_for_private_ui_scrub(monkeypatch):
    async def reject_owner_mismatch(*_args, **_kwargs):
        raise AuthenticationError(
            'The signed-in account changed.',
            status_code=409,
            code='AUTH_OWNER_MISMATCH',
            details={'staleAuth': True, 'retryable': True},
        )

    monkeypatch.setattr(auth_routes, 'authenticate_request', reject_owner_mismatch)
    request = Request({
        'type': 'http',
        'method': 'GET',
        'path': '/api/auth/check-session',
        'headers': [(b'x-ask-crump-expected-owner', ExpectedOwnerDB.owner_id.encode())],
        'client': ('127.0.0.1', 12345),
    })

    with pytest.raises(AuthenticationError) as captured:
        await auth_routes.check_session(request, Response())

    assert captured.value.status_code == 409
    assert captured.value.code == 'AUTH_OWNER_MISMATCH'
    assert captured.value.details == {'staleAuth': True, 'retryable': True}


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


@pytest.mark.asyncio
async def test_deferred_session_touch_preserves_the_ordinary_renewal_contract():
    class TouchDB:
        def __init__(self):
            self.updates = []

        async def update(self, table, payload, *, filters):
            self.updates.append((table, dict(payload), dict(filters)))
            return []

    db = TouchDB()
    settings = SimpleNamespace(session_days=365)
    auth = AuthenticatedUser(
        user={'id': 'user-1'},
        session={'id': 'session-1', 'last_activity': None, 'expires_at': 'old'},
        token='token',
    )

    await touch_authenticated_session(
        db,
        settings,
        auth,
        now='2026-10-24T06:30:00+00:00',
    )

    assert len(db.updates) == 1
    table, payload, filters = db.updates[0]
    assert table == 'sessions'
    assert filters == {'id': eq('session-1')}
    assert payload['last_activity'] == '2026-10-24T06:30:00+00:00'
    assert payload['expires_at'] != 'old'
    assert auth.session['last_activity'] == payload['last_activity']
    assert auth.session['expires_at'] == payload['expires_at']


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
    assert 'commit && this.clearLocalState(expectedOwnerId || null) === false' in source


def test_bootstrap_surfaces_unavailable_without_claiming_logout():
    source = (PUBLIC / 'auth-controller.js').read_text(encoding='utf-8')
    assert 'if (session.unavailable)' in source
    assert 'Your saved sign-in was preserved' in source


def test_explicit_logout_still_clears_native_and_local_state():
    source = (PUBLIC / 'device-auth.js').read_text(encoding='utf-8')
    assert 'await window.CrumpAPI?.clearSessionToken?.(nativeToken);' in source
    assert 'if (window.CrumpAPI?.isNative && cleared === false) return {stale: true};' in source
    assert 'if (this.clearLocalState(ownerId || null) === false)' in source


class RecordingSessionRevocationDB:
    def __init__(self):
        self.updates = []
        self.selected = []

    async def update(self, table, payload, *, filters, **_kwargs):
        self.updates.append((table, dict(payload), dict(filters)))
        return []

    async def select_one(self, table, *, columns='*', filters=None):
        self.selected.append((table, columns, dict(filters or {})))
        return {
            'id': 'session-a',
            'device_id': 'installation-a',
            'token_hash': 'hash-a',
        }


def auth_request(path: str) -> Request:
    return Request({
        'type': 'http',
        'method': 'POST',
        'path': path,
        'headers': [],
        'query_string': b'',
    })


@pytest.mark.asyncio
async def test_logout_and_device_revoke_use_session_generation_cas(monkeypatch):
    database = RecordingSessionRevocationDB()
    authenticated = AuthenticatedUser(
        user={'id': 'owner-a'},
        session={
            'id': 'session-a',
            'token_hash': 'hash-a',
            'device_id': 'installation-a',
        },
        token='raw-a',
    )

    async def authenticate(*_args, **_kwargs):
        return authenticated

    monkeypatch.setattr(auth_routes, 'db', database)
    monkeypatch.setattr(auth_routes, 'authenticate_request', authenticate)

    await auth_routes.logout(auth_request('/api/auth/logout'), Response())
    assert database.updates == [(
        'sessions',
        {'revoked_at': database.updates[0][1]['revoked_at']},
        {
            'id': 'eq.session-a',
            'user_id': 'eq.owner-a',
            'token_hash': 'eq.hash-a',
            'revoked_at': 'is.null',
        },
    )]

    database.updates.clear()
    await auth_routes.revoke_device(
        auth_routes.RevokeDeviceRequest(sessionId='session-a'),
        auth_request('/api/auth/revoke-device'),
    )
    assert database.selected[0][1] == 'id,device_id,token_hash'
    assert database.updates[0][0] == 'sessions'
    assert database.updates[0][2] == {
        'id': 'eq.session-a',
        'user_id': 'eq.owner-a',
        'token_hash': 'eq.hash-a',
        'revoked_at': 'is.null',
    }
    assert all(table != 'push_tokens' for table, _payload, _filters in database.updates)


@pytest.mark.asyncio
async def test_logout_all_relies_on_generation_trigger_not_broad_push_update(monkeypatch):
    database = RecordingSessionRevocationDB()
    authenticated = AuthenticatedUser(
        user={'id': 'owner-a'},
        session={'id': 'session-a', 'token_hash': 'hash-a'},
        token='raw-a',
    )

    async def authenticate(*_args, **_kwargs):
        return authenticated

    monkeypatch.setattr(auth_routes, 'db', database)
    monkeypatch.setattr(auth_routes, 'authenticate_request', authenticate)
    await auth_routes.logout_all(auth_request('/api/auth/logout-all'), Response())

    assert len(database.updates) == 1
    assert database.updates[0][0] == 'sessions'
    assert database.updates[0][2] == {
        'user_id': 'eq.owner-a',
        'revoked_at': 'is.null',
    }
