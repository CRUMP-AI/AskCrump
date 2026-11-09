import asyncio
from dataclasses import replace
import json
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from app import app
from backend.config import get_settings
from backend.db import eq
from backend.google_connector import (
    READ_SCOPES,
    GoogleConnector,
    GoogleConnectorError,
)
from backend.google_vault import GoogleVault, GoogleVaultError
from backend.routes import connected_apps
from conftest import iter_effective_routes

ROOT = Path(__file__).resolve().parents[1]
USER_ID = '11111111-1111-1111-1111-111111111111'
ACCOUNT = 'person@example.com'


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


def _unconfigured_settings():
    return _settings(
        google_oauth_client_id=None,
        google_oauth_client_secret=None,
        google_oauth_redirect_uri=None,
    )


class FakeVault:
    @property
    def configured(self):
        return True

    def encrypt(self, plaintext):
        return f'enc:{plaintext[::-1]}' if plaintext else ''

    def decrypt(self, ciphertext):
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


def _google_handler(captured):
    def handler(request):
        captured.append(request)
        url = request.url.path
        if url.endswith('/messages'):
            return httpx.Response(
                200, json={'messages': [{'id': 'm1'}, {'id': 'm2'}]}
            )
        if '/messages/' in url:
            message_id = url.rsplit('/', 1)[-1]
            return httpx.Response(
                200,
                json={
                    'id': message_id,
                    'snippet': f'snippet-{message_id}',
                    'payload': {
                        'headers': [
                            {'name': 'From', 'value': 'Sender <s@example.com>'},
                            {'name': 'Subject', 'value': f'Subject {message_id}'},
                            {'name': 'Date', 'value': 'Sun, 8 Nov 2026 10:00:00 -0500'},
                        ]
                    },
                },
            )
        if url.endswith('/profile'):
            return httpx.Response(200, json={'emailAddress': ACCOUNT})
        if url.endswith('/token'):
            return httpx.Response(
                200,
                json={
                    'access_token': 'access-token-1',
                    'refresh_token': 'refresh-token-1',
                    'expires_in': 3600,
                    'scope': ' '.join(READ_SCOPES),
                },
            )
        if url.endswith('/events') and request.method == 'GET':
            return httpx.Response(
                200,
                json={
                    'items': [
                        {
                            'id': 'e1',
                            'summary': 'Standup',
                            'start': {'dateTime': '2026-11-09T14:00:00Z'},
                            'end': {'dateTime': '2026-11-09T14:30:00Z'},
                            'location': 'Office',
                            'attendees': [{'email': 'a@example.com'}],
                        }
                    ]
                },
            )
        if url.endswith('/events') and request.method == 'POST':
            body = json.loads(request.content.decode('utf-8'))
            return httpx.Response(
                200,
                json={
                    'id': 'e2',
                    'summary': body['summary'],
                    'start': body['start'],
                    'end': body['end'],
                },
            )
        return httpx.Response(404, json={})

    return handler


def _connector(db=None, settings=None, captured=None):
    transport = httpx.MockTransport(_google_handler(captured if captured is not None else []))
    return GoogleConnector(
        settings=settings or _settings(),
        db=db if db is not None else FakeDB(),
        vault=FakeVault(),
        http_client=httpx.AsyncClient(transport=transport),
    )


def test_config_absence_means_not_configured_and_connect_fails_closed(monkeypatch):
    connector = GoogleConnector(
        settings=_unconfigured_settings(), db=FakeDB(), vault=FakeVault()
    )
    assert connector.oauth_configured is False
    with pytest.raises(GoogleConnectorError) as caught:
        connector.authorization_url(USER_ID)
    assert caught.value.code == 'GOOGLE_NOT_CONFIGURED'
    assert caught.value.status_code == 503

    monkeypatch.setattr(connected_apps, 'settings', _unconfigured_settings())
    monkeypatch.setattr(connected_apps, 'authenticate_request', _fake_auth)
    status = asyncio.run(connected_apps.google_status(FakeRequest()))
    body = json.loads(status.body.decode('utf-8'))
    assert status.status_code == 200
    assert body['configured'] is False
    assert body['connected'] is False

    connect = asyncio.run(connected_apps.google_connect(FakeRequest()))
    assert connect.status_code == 503
    assert json.loads(connect.body.decode('utf-8'))['code'] == 'GOOGLE_NOT_CONFIGURED'


def test_authorization_url_uses_exactly_the_registry_read_scopes():
    url = _connector().authorization_url(USER_ID)
    query = parse_qs(urlparse(url).query)
    scopes = set(query['scope'][0].split())
    assert scopes == set(READ_SCOPES)
    assert any('gmail.readonly' in scope for scope in scopes)
    assert any('calendar.readonly' in scope for scope in scopes)
    assert not any('gmail.send' in scope for scope in scopes)
    assert not any('gmail.compose' in scope for scope in scopes)
    assert query['state'][0]
    assert query['access_type'] == ['offline']


def test_state_validation_rejects_mismatched_and_tampered_state():
    connector = _connector()
    state = connector.make_state(USER_ID)
    assert connector.validate_state(state, USER_ID)['uid'] == USER_ID
    with pytest.raises(GoogleConnectorError) as caught:
        connector.validate_state(state, '22222222-2222-2222-2222-222222222222')
    assert caught.value.code == 'GOOGLE_STATE_INVALID'
    with pytest.raises(GoogleConnectorError):
        connector.validate_state(state + 'x', USER_ID)
    with pytest.raises(GoogleConnectorError):
        connector.validate_state('not-a-state', USER_ID)


def test_search_messages_maps_google_json_to_summaries():
    messages = asyncio.run(_connector().search_messages('token', 'hello', 10))
    assert messages == [
        {
            'id': 'm1',
            'from': 'Sender <s@example.com>',
            'subject': 'Subject m1',
            'snippet': 'snippet-m1',
            'date': 'Sun, 8 Nov 2026 10:00:00 -0500',
        },
        {
            'id': 'm2',
            'from': 'Sender <s@example.com>',
            'subject': 'Subject m2',
            'snippet': 'snippet-m2',
            'date': 'Sun, 8 Nov 2026 10:00:00 -0500',
        },
    ]


def test_calendar_list_and_create_event_map_google_json():
    connector = _connector()
    events = asyncio.run(
        connector.list_events('token', '2026-11-09T00:00:00Z', '2026-11-10T00:00:00Z')
    )
    assert events[0]['summary'] == 'Standup'
    assert events[0]['attendees'] == ['a@example.com']
    created = asyncio.run(
        connector.create_event(
            'token',
            summary='Dentist',
            start='2026-11-10T15:00:00Z',
            end='2026-11-10T16:00:00Z',
            attendees=['a@example.com'],
        )
    )
    assert created['id'] == 'e2'
    assert created['summary'] == 'Dentist'


def test_exchange_code_stores_tokens_only_as_vault_ciphertext():
    db = FakeDB()
    connector = _connector(db=db)
    state = connector.make_state(USER_ID)
    result = asyncio.run(
        connector.exchange_code('code-1', user_id=USER_ID, state=state)
    )
    assert result['email'] == ACCOUNT
    assert len(db.rows) == 1
    row = db.rows[0]
    assert row['access_token_ciphertext'] == 'enc:1-nekot-ssecca'
    assert 'access-token-1' not in row['access_token_ciphertext']
    assert 'refresh-token-1' not in row['refresh_token_ciphertext']
    token = asyncio.run(connector.access_token_for(USER_ID))
    assert token == 'access-token-1'


def test_disconnect_clears_tokens_and_marks_revoked():
    db = FakeDB(
        rows=[
            {
                'id': 'conn-1',
                'user_id': USER_ID,
                'provider': 'google',
                'account_email': ACCOUNT,
                'scopes': list(READ_SCOPES),
                'access_token_ciphertext': 'enc:x',
                'refresh_token_ciphertext': 'enc:y',
                'token_expires_at': '2026-11-09T00:00:00+00:00',
                'status': 'connected',
            }
        ]
    )
    status = asyncio.run(_connector(db=db).disconnect(USER_ID))
    assert status['connected'] is False
    assert db.rows[0]['status'] == 'revoked'
    assert db.rows[0]['access_token_ciphertext'] == ''
    assert db.rows[0]['refresh_token_ciphertext'] == ''


def test_vault_fails_closed_without_a_key_and_never_stores_plaintext():
    vault = GoogleVault(encryption_key='')
    assert vault.configured is False
    with pytest.raises(GoogleVaultError) as caught:
        vault.encrypt('token')
    assert caught.value.code == 'GOOGLE_VAULT_NOT_CONFIGURED'

    configured = GoogleVault(encryption_key='test-vault-key-for-unit-tests')
    sealed = configured.encrypt('token-value')
    assert sealed != 'token-value'
    assert 'token-value' not in sealed
    assert configured.decrypt(sealed) == 'token-value'


def test_executor_endpoints_require_a_connection(monkeypatch):
    connector = _connector(db=FakeDB())
    monkeypatch.setattr(connected_apps, 'authenticate_request', _fake_auth)
    monkeypatch.setattr(connected_apps, 'get_connector', lambda: connector)
    search = asyncio.run(
        connected_apps.google_search(FakeRequest({'query': 'invoice'}))
    )
    assert search.status_code == 409
    assert json.loads(search.body.decode('utf-8'))['code'] == 'CONNECTION_REQUIRED'
    calendar = asyncio.run(connected_apps.google_calendar(FakeRequest({})))
    assert calendar.status_code == 409


def test_migration_contract_for_agent_connections():
    sql = (ROOT / 'migrations' / '20261109120000_google_connections.sql').read_text(
        encoding='utf-8'
    )
    assert 'create table if not exists public.agent_connections' in sql
    assert "check (provider in ('google'))" in sql
    assert "check (status in ('connected', 'revoked', 'error'))" in sql
    assert 'unique (user_id, provider, account_email)' in sql
    assert 'references public.users(id) on delete cascade' in sql
    assert 'alter table public.agent_connections enable row level security' in sql
    assert (
        'revoke all privileges on public.agent_connections from anon, authenticated'
        in sql
    )
    assert 'access_token_ciphertext' in sql
    assert 'refresh_token_ciphertext' in sql


def test_connected_app_routes_are_registered():
    actual = {
        (method, route.path)
        for route in iter_effective_routes(app)
        for method in getattr(route, 'methods', set())
        if method not in {'HEAD', 'OPTIONS'}
    }
    assert ('GET', '/api/connections/google/status') in actual
    assert ('GET', '/api/connections/google/connect') in actual
    assert ('GET', '/api/connections/google/callback') in actual
    assert ('POST', '/api/connections/google/disconnect') in actual
    assert ('POST', '/api/agent/google/search') in actual
    assert ('POST', '/api/agent/google/calendar') in actual
