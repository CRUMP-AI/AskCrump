import asyncio
import base64
from dataclasses import replace
import json
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from backend.agent_gmail_write import execute as gmail_write_execute
from backend.config import get_settings
from backend.db import eq
from backend.google_connector import (
    READ_SCOPES,
    WRITE_SCOPES,
    GoogleConnector,
    GoogleConnectorError,
)
from backend.routes import connected_apps

USER_ID = '11111111-1111-1111-1111-111111111111'
ACCOUNT = 'person@example.com'
COMPOSE_SCOPE = next(scope for scope in WRITE_SCOPES if 'gmail.compose' in scope)
SEND_SCOPE = next(scope for scope in WRITE_SCOPES if 'gmail.send' in scope)


def _settings(**overrides):
    base = get_settings()
    values = {
        'google_oauth_client_id': 'client-123',
        'google_oauth_client_secret': 'secret-xyz',
        'google_oauth_redirect_uri': (
            'https://askcrump.com/api/connections/google/callback'
        ),
    }
    values.update(overrides)
    return replace(base, **values)


class FakeVault:
    @property
    def configured(self):
        return True

    def encrypt(self, plaintext, *, user_id, provider, connection_id):
        return f'enc:{plaintext[::-1]}' if plaintext else ''

    def decrypt(self, ciphertext, *, user_id, provider, connection_id):
        return ciphertext[4:][::-1] if ciphertext.startswith('enc:') else ''


class FakeDB:
    def __init__(self, rows=None):
        self.rows = list(rows or [])

    @staticmethod
    def _matches(row, filters):
        for key, raw in (filters or {}).items():
            expected = raw[3:] if str(raw).startswith('eq.') else raw
            if str(row.get(key)) != str(expected):
                return False
        return True

    async def select(self, table, *, columns='*', filters=None, order=None, limit=None):
        return [row for row in self.rows if self._matches(row, filters)]

    async def select_one(self, table, *, columns='*', filters=None):
        rows = await self.select(table, columns=columns, filters=filters)
        return rows[0] if rows else None

    async def insert(self, table, payload):
        row = dict(payload)
        row.setdefault('id', 'conn-1')
        self.rows.append(row)
        return [row]

    async def upsert(self, table, payload, *, on_conflict):
        existing = await self.select_one(
            table,
            filters={
                'user_id': eq(payload['user_id']),
                'provider': eq(payload['provider']),
                'account_email': eq(payload['account_email']),
            },
        )
        if existing:
            existing.update(payload)
            return [existing]
        return await self.insert(table, payload)

    async def update(self, table, payload, *, filters, retry_transient=False):
        updated = []
        for row in self.rows:
            if self._matches(row, filters):
                row.update(payload)
                updated.append(row)
        return updated


class FakeRequest:
    def __init__(self, payload=None, query=None):
        self._payload = payload or {}
        self.query_params = query or {}

    async def json(self):
        return self._payload


async def _fake_auth(request, db, settings, **kwargs):
    return SimpleNamespace(user={'id': USER_ID})


def _google_handler(captured, *, granted_scope):
    def handler(request):
        captured.append(request)
        url = request.url.path
        if url.endswith('/token'):
            body = {
                'access_token': 'access-token-1',
                'refresh_token': 'refresh-token-1',
                'expires_in': 3600,
            }
            if granted_scope is not None:
                body['scope'] = granted_scope
            return httpx.Response(200, json=body)
        if url.endswith('/profile'):
            return httpx.Response(200, json={'emailAddress': ACCOUNT})
        if url.endswith('/drafts') and request.method == 'POST':
            return httpx.Response(
                200,
                json={
                    'id': 'draft-1',
                    'message': {'id': 'm-draft-1', 'threadId': 'thread-1'},
                },
            )
        if url.endswith('/messages/send') and request.method == 'POST':
            return httpx.Response(
                200, json={'id': 'm-sent-1', 'threadId': 'thread-2', 'labelIds': ['SENT']}
            )
        return httpx.Response(404, json={})

    return handler


def _connector(db=None, captured=None, *, granted_scope=' '.join(WRITE_SCOPES)):
    transport = httpx.MockTransport(
        _google_handler(
            captured if captured is not None else [], granted_scope=granted_scope
        )
    )
    return GoogleConnector(
        settings=_settings(),
        db=db if db is not None else FakeDB(),
        vault=FakeVault(),
        http_client=httpx.AsyncClient(transport=transport),
    )


def _scopes_in(url):
    query = parse_qs(urlparse(url).query)
    return set(query['scope'][0].split()), query


def _patch_routes(monkeypatch, connector):
    monkeypatch.setattr(connected_apps, 'authenticate_request', _fake_auth)
    monkeypatch.setattr(connected_apps, 'get_connector', lambda: connector)


# -- Connect URL scope sets -------------------------------------------------


def test_default_connect_url_carries_exactly_the_read_scopes(monkeypatch):
    connector = _connector()
    scopes, query = _scopes_in(connector.authorization_url(USER_ID))
    assert scopes == set(READ_SCOPES)
    assert query['access_type'] == ['offline']

    _patch_routes(monkeypatch, connector)
    response = asyncio.run(connected_apps.google_connect(FakeRequest()))
    assert response.status_code == 200
    body = json.loads(response.body.decode('utf-8'))
    route_scopes, _ = _scopes_in(body['authorizationUrl'])
    assert route_scopes == set(READ_SCOPES)

    explicit = asyncio.run(
        connected_apps.google_connect(FakeRequest(query={'level': 'read'}))
    )
    assert explicit.status_code == 200
    explicit_scopes, _ = _scopes_in(
        json.loads(explicit.body.decode('utf-8'))['authorizationUrl']
    )
    assert explicit_scopes == set(READ_SCOPES)


def test_write_connect_url_carries_the_full_write_set(monkeypatch):
    connector = _connector()
    scopes, _ = _scopes_in(connector.authorization_url(USER_ID, level='write'))
    assert scopes == set(WRITE_SCOPES)
    assert set(READ_SCOPES) < scopes
    assert COMPOSE_SCOPE in scopes
    assert SEND_SCOPE in scopes
    assert any('calendar.events' in scope for scope in scopes)

    _patch_routes(monkeypatch, connector)
    response = asyncio.run(
        connected_apps.google_connect(FakeRequest(query={'level': 'write'}))
    )
    assert response.status_code == 200
    body = json.loads(response.body.decode('utf-8'))
    route_scopes, _ = _scopes_in(body['authorizationUrl'])
    assert route_scopes == set(WRITE_SCOPES)


def test_bogus_level_is_a_400(monkeypatch):
    connector = _connector()
    _patch_routes(monkeypatch, connector)
    for level in ('admin', 'WRITE', 'read-write', 'full'):
        response = asyncio.run(
            connected_apps.google_connect(FakeRequest(query={'level': level}))
        )
        assert response.status_code == 400
        body = json.loads(response.body.decode('utf-8'))
        assert body['success'] is False
        assert body['code'] == 'INVALID_CONNECT_LEVEL'


def test_connector_rejects_a_bogus_level():
    connector = _connector()
    with pytest.raises(GoogleConnectorError) as caught:
        connector.authorization_url(USER_ID, level='admin')
    assert caught.value.code == 'INVALID_CONNECT_LEVEL'
    assert caught.value.status_code == 400
    with pytest.raises(GoogleConnectorError):
        connector.make_state(USER_ID, level='admin')


# -- State binding ------------------------------------------------------------


def test_state_binds_the_requested_level():
    connector = _connector()
    read_state = connector.make_state(USER_ID)
    assert connector.validate_state(read_state, USER_ID)['level'] == 'read'
    assert (
        connector.validate_state(read_state, USER_ID, expected_level='read')['uid']
        == USER_ID
    )
    with pytest.raises(GoogleConnectorError) as caught:
        connector.validate_state(read_state, USER_ID, expected_level='write')
    assert caught.value.code == 'GOOGLE_STATE_INVALID'

    write_state = connector.make_state(USER_ID, level='write')
    assert connector.validate_state(write_state, USER_ID)['level'] == 'write'
    assert (
        connector.validate_state(write_state, USER_ID, expected_level='write')['uid']
        == USER_ID
    )
    with pytest.raises(GoogleConnectorError) as caught:
        connector.validate_state(write_state, USER_ID, expected_level='read')
    assert caught.value.code == 'GOOGLE_STATE_INVALID'


def test_authorization_url_state_matches_the_requested_level():
    connector = _connector()
    _, read_query = _scopes_in(connector.authorization_url(USER_ID))
    read_payload = connector.validate_state(read_query['state'][0], USER_ID)
    assert read_payload['level'] == 'read'
    _, write_query = _scopes_in(connector.authorization_url(USER_ID, level='write'))
    write_payload = connector.validate_state(write_query['state'][0], USER_ID)
    assert write_payload['level'] == 'write'
    with pytest.raises(GoogleConnectorError):
        connector.validate_state(
            write_query['state'][0], USER_ID, expected_level='read'
        )


def test_legacy_state_without_a_level_validates_as_read_only():
    connector = _connector()
    payload = {'uid': USER_ID, 'nonce': 'legacy', 'exp': 9999999999}
    part = (
        base64.urlsafe_b64encode(
            json.dumps(payload, separators=(',', ':')).encode('utf-8')
        )
        .decode('ascii')
        .rstrip('=')
    )
    legacy_state = f'{part}.{connector._sign(part)}'
    assert (
        connector.validate_state(legacy_state, USER_ID, expected_level='read')['uid']
        == USER_ID
    )
    with pytest.raises(GoogleConnectorError):
        connector.validate_state(legacy_state, USER_ID, expected_level='write')


def test_tampered_state_level_fails_validation():
    connector = _connector()
    state = connector.make_state(USER_ID)
    part, signature = state.split('.', 1)
    payload = json.loads(
        base64.urlsafe_b64decode(part + '=' * (-len(part) % 4)).decode('utf-8')
    )
    payload['level'] = 'write'
    forged_part = (
        base64.urlsafe_b64encode(
            json.dumps(payload, separators=(',', ':')).encode('utf-8')
        )
        .decode('ascii')
        .rstrip('=')
    )
    forged = f'{forged_part}.{signature}'
    with pytest.raises(GoogleConnectorError) as caught:
        connector.validate_state(forged, USER_ID)
    assert caught.value.code == 'GOOGLE_STATE_INVALID'
    with pytest.raises(GoogleConnectorError):
        connector.validate_state(forged, USER_ID, expected_level='write')


def test_exchange_rejects_a_state_replayed_for_another_level():
    captured = []
    connector = _connector(captured=captured)
    read_state = connector.make_state(USER_ID)
    with pytest.raises(GoogleConnectorError) as caught:
        asyncio.run(
            connector.exchange_code(
                'code-1', user_id=USER_ID, state=read_state, expected_level='write'
            )
        )
    assert caught.value.code == 'GOOGLE_STATE_INVALID'
    assert captured == []


# -- Callback: granted scopes are what get stored -----------------------------


def test_write_callback_stores_the_granted_scopes(monkeypatch):
    db = FakeDB()
    connector = _connector(db=db, granted_scope=' '.join(WRITE_SCOPES))
    _patch_routes(monkeypatch, connector)
    state = connector.make_state(USER_ID, level='write')
    response = asyncio.run(
        connected_apps.google_callback(
            FakeRequest(query={'code': 'code-1', 'state': state})
        )
    )
    assert response.status_code == 302
    assert response.headers['location'].endswith('/app?google=connected')
    assert len(db.rows) == 1
    assert set(db.rows[0]['scopes']) == set(WRITE_SCOPES)


def test_read_callback_still_stores_the_read_grant():
    db = FakeDB()
    connector = _connector(db=db, granted_scope=' '.join(READ_SCOPES))
    state = connector.make_state(USER_ID)
    result = asyncio.run(
        connector.exchange_code(
            'code-1', user_id=USER_ID, state=state, expected_level='read'
        )
    )
    assert set(result['scopes']) == set(READ_SCOPES)
    assert set(db.rows[0]['scopes']) == set(READ_SCOPES)


def test_write_callback_stores_a_granted_subset_and_the_adapter_refuses_send():
    granted = tuple(READ_SCOPES) + (COMPOSE_SCOPE,)
    db = FakeDB()
    captured = []
    connector = _connector(db=db, captured=captured, granted_scope=' '.join(granted))
    state = connector.make_state(USER_ID, level='write')
    result = asyncio.run(
        connector.exchange_code(
            'code-1', user_id=USER_ID, state=state, expected_level='write'
        )
    )
    # Google granted fewer scopes than the write set requested; the
    # stored record shows exactly that subset, not the request.
    assert set(result['scopes']) == set(granted)
    assert set(db.rows[0]['scopes']) == set(granted)
    assert SEND_SCOPE not in db.rows[0]['scopes']

    captured.clear()
    with pytest.raises(GoogleConnectorError) as caught:
        asyncio.run(
            gmail_write_execute(
                'gmail.send',
                USER_ID,
                {'to': 'person@example.com', 'subject': 'Hi', 'body': 'Hello'},
                connector=connector,
            )
        )
    assert caught.value.code == 'INSUFFICIENT_SCOPE'
    assert captured == []

    # The scope Google did grant still works through the same check.
    drafted = asyncio.run(
        gmail_write_execute(
            'gmail.draft',
            USER_ID,
            {'to': 'person@example.com', 'subject': 'Hi', 'body': 'Hello'},
            connector=connector,
        )
    )
    assert drafted['status'] == 'draft_created'
    assert len(captured) == 1


def test_token_response_without_a_scope_field_stores_no_scopes():
    db = FakeDB()
    connector = _connector(db=db, granted_scope=None)
    state = connector.make_state(USER_ID, level='write')
    result = asyncio.run(
        connector.exchange_code(
            'code-1', user_id=USER_ID, state=state, expected_level='write'
        )
    )
    assert result['scopes'] == []
    assert db.rows[0]['scopes'] == []


# -- Status -------------------------------------------------------------------


def test_status_reports_the_granted_scopes_per_account(monkeypatch):
    granted = list(READ_SCOPES) + [COMPOSE_SCOPE]
    db = FakeDB(
        rows=[
            {
                'id': 'conn-1',
                'user_id': USER_ID,
                'provider': 'google',
                'account_email': ACCOUNT,
                'scopes': granted,
                'access_token_ciphertext': 'enc:x',
                'refresh_token_ciphertext': 'enc:y',
                'token_expires_at': '2026-11-09T00:00:00+00:00',
                'status': 'connected',
            }
        ]
    )
    connector = _connector(db=db)
    status = asyncio.run(connector.status(USER_ID))
    assert status['connected'] is True
    assert status['accounts'][0]['email'] == ACCOUNT
    assert status['accounts'][0]['scopes'] == granted

    _patch_routes(monkeypatch, connector)
    response = asyncio.run(connected_apps.google_status(FakeRequest()))
    assert response.status_code == 200
    body = json.loads(response.body.decode('utf-8'))
    assert body['success'] is True
    assert body['accounts'][0]['scopes'] == granted
