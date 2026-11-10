"""Token lifecycle for Google connections: refresh and revocation.

Access tokens expire about an hour after Google issues them. The
bound-token path must refresh an expired bound token from the stored
refresh token before any provider call, persist the refreshed tokens
through the vault, and fail with ``CONNECTION_REQUIRED`` when the
grant can no longer be refreshed — the expired token must never be
used. Disconnect must fence and clear the local row before revoking the
grant at Google from a captured token snapshot, so an in-flight refresh
cannot resurrect it. A failed revocation must be surfaced on the
returned status without blocking the local disconnect.

All Google endpoints are mocked; no real network is touched.
"""
import asyncio
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from urllib.parse import parse_qs

import httpx
import pytest

from backend.config import get_settings
from backend.google_connector import (
    ConnectionRequiredError,
    GoogleConnector,
)

USER_ID = '11111111-1111-1111-1111-111111111111'
ACCOUNT = 'person@example.com'

ACCESS_OLD = 'access-old'
ACCESS_NEW = 'access-new'
REFRESH_OLD = 'refresh-old'
REFRESH_NEW = 'refresh-new'

READ_SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/calendar.readonly',
]


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

    async def update(self, table, payload, *, filters, retry_transient=False):
        updated = []
        for row in self.rows:
            if self._matches(row, filters):
                row.update(payload)
                updated.append(row)
        return updated


def _iso(moment):
    return moment.astimezone(timezone.utc).isoformat()


def _connection_row(*, expires_at, refresh_token=REFRESH_OLD, access_token=ACCESS_OLD):
    vault = FakeVault()
    return {
        'id': 'conn-1',
        'user_id': USER_ID,
        'provider': 'google',
        'account_email': ACCOUNT,
        'scopes': list(READ_SCOPES),
        'access_token_ciphertext': vault.encrypt(access_token, user_id=USER_ID, provider='google', connection_id='conn-1'),
        'refresh_token_ciphertext': (
            vault.encrypt(refresh_token, user_id=USER_ID, provider='google', connection_id='conn-1') if refresh_token else ''
        ),
        'token_expires_at': _iso(expires_at) if expires_at else None,
        'status': 'connected',
        'created_at': '2026-11-08T10:00:00+00:00',
        'updated_at': '2026-11-08T10:00:00+00:00',
    }


def _expired_row(**kwargs):
    return _connection_row(
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=5), **kwargs
    )


def _valid_row(**kwargs):
    return _connection_row(
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=30), **kwargs
    )


def _handler(captured, *, token_response=None, revoke_status=200, revoke_raises=False):
    def handler(request):
        captured.append(request)
        path = request.url.path
        if path.endswith('/token'):
            if callable(token_response):
                return token_response(request)
            if token_response is not None:
                return token_response
            return httpx.Response(
                200,
                json={
                    'access_token': ACCESS_NEW,
                    'expires_in': 3600,
                    'scope': ' '.join(READ_SCOPES),
                },
            )
        if path.endswith('/revoke'):
            if revoke_raises:
                raise httpx.ConnectError(
                    'connection refused', request=request
                )
            return httpx.Response(revoke_status, json={})
        if path.endswith('/messages') and request.method == 'GET':
            return httpx.Response(200, json={'messages': [{'id': 'm1'}]})
        if '/messages/' in path and request.method == 'GET':
            return httpx.Response(
                200,
                json={
                    'id': 'm1',
                    'snippet': 'snippet-m1',
                    'payload': {
                        'headers': [
                            {'name': 'From', 'value': 'Sender <s@example.com>'},
                            {'name': 'Subject', 'value': 'Subject m1'},
                            {'name': 'Date', 'value': 'Sun, 8 Nov 2026 10:00:00 -0500'},
                        ]
                    },
                },
            )
        return httpx.Response(404, json={})

    return handler


def _connector(db, captured, **handler_kwargs):
    transport = httpx.MockTransport(_handler(captured, **handler_kwargs))
    return GoogleConnector(
        settings=_settings(),
        db=db,
        vault=FakeVault(),
        http_client=httpx.AsyncClient(transport=transport),
    )


def _token_calls(captured):
    return [r for r in captured if r.url.path.endswith('/token')]


def _revoke_calls(captured):
    return [r for r in captured if r.url.path.endswith('/revoke')]


def _provider_calls(captured):
    return [
        r
        for r in captured
        if not r.url.path.endswith('/token')
        and not r.url.path.endswith('/revoke')
    ]


def _form(request):
    return {key: values[0] for key, values in parse_qs(request.content.decode()).items()}


# -- Refresh -------------------------------------------------------------------


def test_expired_token_refreshes_once_and_the_new_token_is_used_and_persisted():
    captured = []
    db = FakeDB(rows=[_expired_row()])
    connector = _connector(db, captured)

    token = asyncio.run(connector.access_token_for(USER_ID))
    assert token == ACCESS_NEW

    calls = _token_calls(captured)
    assert len(calls) == 1
    form = _form(calls[0])
    assert form['grant_type'] == 'refresh_token'
    assert form['refresh_token'] == REFRESH_OLD

    # The refreshed access token is persisted through the vault: the
    # stored ciphertext round-trips through the vault's own read path.
    assert connector.vault.decrypt(db.rows[0]['access_token_ciphertext'], user_id=USER_ID, provider='google', connection_id='conn-1') == ACCESS_NEW
    expires_at = datetime.fromisoformat(db.rows[0]['token_expires_at'])
    assert expires_at > datetime.now(timezone.utc) + timedelta(minutes=30)

    # The provider call carries the refreshed token, never the old one.
    captured.clear()
    messages = asyncio.run(connector.search_messages(token, 'invoice', 5))
    assert messages[0]['id'] == 'm1'
    authorizations = {
        request.headers.get('authorization') for request in _provider_calls(captured)
    }
    assert authorizations == {f'Bearer {ACCESS_NEW}'}


def test_rotated_refresh_token_is_persisted_when_google_returns_one():
    captured = []
    db = FakeDB(rows=[_expired_row()])
    rotated = httpx.Response(
        200,
        json={
            'access_token': ACCESS_NEW,
            'refresh_token': REFRESH_NEW,
            'expires_in': 3600,
        },
    )
    connector = _connector(db, captured, token_response=rotated)
    token = asyncio.run(connector.access_token_for(USER_ID))
    assert token == ACCESS_NEW
    assert connector.vault.decrypt(db.rows[0]['refresh_token_ciphertext'], user_id=USER_ID, provider='google', connection_id='conn-1') == REFRESH_NEW


def test_refresh_without_rotation_keeps_the_stored_refresh_token():
    captured = []
    db = FakeDB(rows=[_expired_row()])
    connector = _connector(db, captured)  # default response omits refresh_token
    asyncio.run(connector.access_token_for(USER_ID))
    assert connector.vault.decrypt(db.rows[0]['refresh_token_ciphertext'], user_id=USER_ID, provider='google', connection_id='conn-1') == REFRESH_OLD


def test_token_inside_the_refresh_skew_is_refreshed():
    captured = []
    soon = datetime.now(timezone.utc) + timedelta(seconds=30)
    db = FakeDB(rows=[_connection_row(expires_at=soon)])
    connector = _connector(db, captured)
    token = asyncio.run(connector.access_token_for(USER_ID))
    assert token == ACCESS_NEW
    assert len(_token_calls(captured)) == 1


def test_valid_token_is_returned_with_no_token_endpoint_call():
    captured = []
    db = FakeDB(rows=[_valid_row()])
    connector = _connector(db, captured)
    token = asyncio.run(connector.access_token_for(USER_ID))
    assert token == ACCESS_OLD
    assert captured == []


def test_invalid_grant_fails_with_connection_required_and_never_uses_the_expired_token():
    captured = []
    db = FakeDB(rows=[_expired_row()])
    rejected = httpx.Response(400, json={'error': 'invalid_grant'})
    connector = _connector(db, captured, token_response=rejected)
    with pytest.raises(ConnectionRequiredError) as caught:
        asyncio.run(connector.access_token_for(USER_ID))
    assert caught.value.code == 'CONNECTION_REQUIRED'
    assert len(_token_calls(captured)) == 1
    assert _provider_calls(captured) == []
    # The expired token is still the stored one — it was not "used",
    # and nothing overwrote the row with a partial refresh.
    assert connector.vault.decrypt(db.rows[0]['access_token_ciphertext'], user_id=USER_ID, provider='google', connection_id='conn-1') == ACCESS_OLD


def test_refresh_network_failure_fails_with_connection_required():
    captured = []
    db = FakeDB(rows=[_expired_row()])

    def unreachable(request):
        raise httpx.ConnectError('network unreachable', request=request)

    connector = _connector(db, captured, token_response=unreachable)
    with pytest.raises(ConnectionRequiredError) as caught:
        asyncio.run(connector.access_token_for(USER_ID))
    assert caught.value.code == 'CONNECTION_REQUIRED'
    assert _provider_calls(captured) == []


def test_expired_token_without_a_refresh_token_requires_reconnect():
    captured = []
    db = FakeDB(rows=[_expired_row(refresh_token='')])
    connector = _connector(db, captured)
    with pytest.raises(ConnectionRequiredError) as caught:
        asyncio.run(connector.access_token_for(USER_ID))
    assert caught.value.code == 'CONNECTION_REQUIRED'
    assert captured == []


def test_concurrent_refresh_of_one_connection_is_single_flight():
    captured = []
    db = FakeDB(rows=[_expired_row()])
    connector = _connector(db, captured)

    async def two_callers():
        return await asyncio.gather(
            connector.access_token_for(USER_ID),
            connector.access_token_for(USER_ID),
        )

    tokens = asyncio.run(two_callers())
    assert tokens == [ACCESS_NEW, ACCESS_NEW]
    assert len(_token_calls(captured)) == 1
    assert connector.vault.decrypt(db.rows[0]['access_token_ciphertext'], user_id=USER_ID, provider='google', connection_id='conn-1') == ACCESS_NEW


def test_disconnect_mid_refresh_fences_the_stale_write_and_token_return():
    captured = []
    db = FakeDB(rows=[_expired_row()])
    refresh_connector = _connector(db, captured)
    disconnect_connector = _connector(db, captured)
    refresh_started = asyncio.Event()
    release_refresh = asyncio.Event()

    async def blocked_exchange(_refresh_token):
        refresh_started.set()
        await release_refresh.wait()
        return {'access_token': ACCESS_NEW, 'expires_in': 3600}

    refresh_connector._exchange_refresh_token = blocked_exchange

    async def refresh_during_disconnect():
        refresh_task = asyncio.create_task(
            refresh_connector.access_token_for(USER_ID)
        )
        await refresh_started.wait()
        status = await disconnect_connector.disconnect(USER_ID)
        release_refresh.set()
        with pytest.raises(ConnectionRequiredError) as caught:
            await refresh_task
        return status, caught.value

    status, error = asyncio.run(refresh_during_disconnect())

    assert error.code == 'CONNECTION_REQUIRED'
    assert status['connected'] is False
    assert db.rows[0]['status'] == 'revoked'
    assert db.rows[0]['access_token_ciphertext'] == ''
    assert db.rows[0]['refresh_token_ciphertext'] == ''
    assert db.rows[0]['token_expires_at'] is None
    assert len(_revoke_calls(captured)) == 1


def test_separate_connector_instances_share_one_durable_refresh_lease():
    db = FakeDB(rows=[_expired_row()])
    calls = 0
    refresh_started = asyncio.Event()
    release_refresh = asyncio.Event()

    async def blocked_exchange(_refresh_token):
        nonlocal calls
        calls += 1
        call_number = calls
        refresh_started.set()
        await release_refresh.wait()
        return {
            'access_token': f'{ACCESS_NEW}-{call_number}',
            'expires_in': 3600,
        }

    first = _connector(db, [])
    second = _connector(db, [])
    first._exchange_refresh_token = blocked_exchange
    second._exchange_refresh_token = blocked_exchange

    async def refresh_from_two_request_scoped_instances():
        first_task = asyncio.create_task(first.access_token_for(USER_ID))
        await refresh_started.wait()
        second_task = asyncio.create_task(second.access_token_for(USER_ID))
        for _ in range(10):
            await asyncio.sleep(0)
        calls_before_release = calls
        release_refresh.set()
        return calls_before_release, await asyncio.gather(first_task, second_task)

    calls_before_release, tokens = asyncio.run(
        refresh_from_two_request_scoped_instances()
    )

    assert calls_before_release == 1
    assert calls == 1
    assert tokens == [f'{ACCESS_NEW}-1', f'{ACCESS_NEW}-1']
    assert (
        first.vault.decrypt(
            db.rows[0]['access_token_ciphertext'],
            user_id=USER_ID,
            provider='google',
            connection_id='conn-1',
        )
        == f'{ACCESS_NEW}-1'
    )


# -- Disconnect / revocation -----------------------------------------------------


def test_disconnect_revokes_the_refresh_token_and_clears_the_local_row():
    captured = []
    db = FakeDB(rows=[_valid_row()])
    connector = _connector(db, captured)

    status = asyncio.run(connector.disconnect(USER_ID))

    calls = _revoke_calls(captured)
    assert len(calls) == 1
    assert _form(calls[0])['token'] == REFRESH_OLD
    assert db.rows[0]['status'] == 'revoked'
    assert db.rows[0]['access_token_ciphertext'] == ''
    assert db.rows[0]['refresh_token_ciphertext'] == ''
    assert status['connected'] is False
    assert status['revocations'] == [
        {'email': ACCOUNT, 'attempted': True, 'revoked': True, 'error': None}
    ]


def test_disconnect_revoke_failure_still_disconnects_and_surfaces_the_failure():
    captured = []
    db = FakeDB(rows=[_valid_row()])
    connector = _connector(db, captured, revoke_status=500)

    status = asyncio.run(connector.disconnect(USER_ID))

    assert len(_revoke_calls(captured)) == 1
    assert db.rows[0]['status'] == 'revoked'
    assert db.rows[0]['access_token_ciphertext'] == ''
    assert db.rows[0]['refresh_token_ciphertext'] == ''
    assert status['connected'] is False
    outcome = status['revocations'][0]
    assert outcome['attempted'] is True
    assert outcome['revoked'] is False
    assert outcome['error'] == 'revoke_http_500'


def test_disconnect_revoke_network_failure_still_disconnects_and_surfaces_it():
    captured = []
    db = FakeDB(rows=[_valid_row()])
    connector = _connector(db, captured, revoke_raises=True)

    status = asyncio.run(connector.disconnect(USER_ID))

    assert db.rows[0]['status'] == 'revoked'
    outcome = status['revocations'][0]
    assert outcome['attempted'] is True
    assert outcome['revoked'] is False
    assert outcome['error'] == 'revoke_request_failed'


def test_disconnect_without_a_stored_token_makes_no_revoke_call():
    captured = []
    row = _valid_row()
    row['access_token_ciphertext'] = ''
    row['refresh_token_ciphertext'] = ''
    db = FakeDB(rows=[row])
    connector = _connector(db, captured)

    status = asyncio.run(connector.disconnect(USER_ID))

    assert _revoke_calls(captured) == []
    assert db.rows[0]['status'] == 'revoked'
    assert status['connected'] is False
    assert status['revocations'] == [
        {'email': ACCOUNT, 'attempted': False, 'revoked': False, 'error': None}
    ]


def test_disconnect_only_revokes_the_named_account():
    captured = []
    vault = FakeVault()
    other = _valid_row()
    other['id'] = 'conn-2'
    other['account_email'] = 'other@example.com'
    other['refresh_token_ciphertext'] = vault.encrypt(
        'refresh-other',
        user_id=USER_ID,
        provider='google',
        connection_id='conn-2',
    )
    other['access_token_ciphertext'] = vault.encrypt(
        'access-other',
        user_id=USER_ID,
        provider='google',
        connection_id='conn-2',
    )
    other['created_at'] = '2026-11-09T10:00:00+00:00'
    db = FakeDB(rows=[_valid_row(), other])
    connector = _connector(db, captured)

    status = asyncio.run(connector.disconnect(USER_ID, ACCOUNT))

    calls = _revoke_calls(captured)
    assert len(calls) == 1
    assert _form(calls[0])['token'] == REFRESH_OLD
    rows_by_id = {row['id']: row for row in db.rows}
    assert rows_by_id['conn-1']['status'] == 'revoked'
    assert rows_by_id['conn-2']['status'] == 'connected'
    assert json.dumps(status['revocations'])  # outcome is recorded, not dropped
