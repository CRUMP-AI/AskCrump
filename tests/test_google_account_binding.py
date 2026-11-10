"""Account binding for Google agent execution.

A user can connect two Google accounts. Every run must execute
against ONE bound connection: a connection named in the run payload
binds, otherwise the default connection (earliest connected,
tie-broken by connection id) binds. Scopes are evaluated against the
bound connection alone — never unioned across connections — and the
provider call must carry the bound connection's own token.

These tests run the real connector and the real executor against a
fake store and a fake provider transport, with two connections whose
grants differ: account A holds only the read scopes, account B holds
only the write scopes.
"""
import asyncio
from dataclasses import replace
import json

import httpx
import pytest

from backend.agent_executor import AgentExecutor
from backend.agent_gmail_write import execute as adapter_execute
from backend.agent_run_service import AgentRunService
from backend.config import get_settings
from backend.google_connector import (
    ConnectionRequiredError,
    GoogleConnector,
    GoogleConnectorError,
)

USER_ID = '11111111-1111-1111-1111-111111111111'
ACCOUNT_A = 'a@example.com'
ACCOUNT_B = 'b@example.com'
TOKEN_A = 'token-a'
TOKEN_B = 'token-b'

GMAIL_READONLY = 'https://www.googleapis.com/auth/gmail.readonly'
CALENDAR_READONLY = 'https://www.googleapis.com/auth/calendar.readonly'
GMAIL_COMPOSE = 'https://www.googleapis.com/auth/gmail.compose'
GMAIL_SEND = 'https://www.googleapis.com/auth/gmail.send'
CALENDAR_EVENTS = 'https://www.googleapis.com/auth/calendar.events'

READ_GRANT = (GMAIL_READONLY, CALENDAR_READONLY)
WRITE_GRANT = (GMAIL_COMPOSE, GMAIL_SEND, CALENDAR_EVENTS)

RECIPIENT = 'person@example.com'
SUBJECT = 'Quarterly update'
BODY = 'Hello,\n\nThe quarterly numbers are attached below.\n'


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

    def encrypt(self, plaintext):
        return f'enc:{plaintext[::-1]}' if plaintext else ''

    def decrypt(self, ciphertext):
        return ciphertext[4:][::-1] if ciphertext.startswith('enc:') else ''


class FakeConnectionDB:
    """In-memory agent_connections store (connector-side fake)."""

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


def _connection_row(
    connection_id,
    email,
    token,
    scopes,
    *,
    created_at,
    status='connected',
):
    return {
        'id': connection_id,
        'user_id': USER_ID,
        'provider': 'google',
        'account_email': email,
        'scopes': list(scopes),
        'access_token_ciphertext': FakeVault().encrypt(token),
        'refresh_token_ciphertext': '',
        'token_expires_at': '2026-11-09T00:00:00+00:00',
        'status': status,
        'created_at': created_at,
    }


def _row_a(**overrides):
    row = _connection_row(
        'conn-a',
        ACCOUNT_A,
        TOKEN_A,
        READ_GRANT,
        created_at='2026-11-08T10:00:00+00:00',
    )
    row.update(overrides)
    return row


def _row_b(**overrides):
    row = _connection_row(
        'conn-b',
        ACCOUNT_B,
        TOKEN_B,
        WRITE_GRANT,
        created_at='2026-11-09T10:00:00+00:00',
    )
    row.update(overrides)
    return row


def _provider_handler(captured):
    def handler(request):
        captured.append(request)
        path = request.url.path
        if path.endswith('/drafts') and request.method == 'POST':
            return httpx.Response(
                200,
                json={
                    'id': 'draft-1',
                    'message': {'id': 'm-draft-1', 'threadId': 'thread-1'},
                },
            )
        if path.endswith('/messages/send') and request.method == 'POST':
            return httpx.Response(
                200,
                json={'id': 'm-sent-1', 'threadId': 'thread-2', 'labelIds': ['SENT']},
            )
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
        if path.endswith('/events') and request.method == 'GET':
            return httpx.Response(200, json={'items': []})
        if path.endswith('/events') and request.method == 'POST':
            body = json.loads(request.content.decode('utf-8'))
            return httpx.Response(
                200,
                json={
                    'id': 'e-created',
                    'summary': body['summary'],
                    'start': body['start'],
                    'end': body['end'],
                },
            )
        return httpx.Response(404, json={})

    return handler


def _connector(rows, captured=None):
    transport = httpx.MockTransport(
        _provider_handler(captured if captured is not None else [])
    )
    return GoogleConnector(
        settings=_settings(),
        db=FakeConnectionDB(rows),
        vault=FakeVault(),
        http_client=httpx.AsyncClient(transport=transport),
    )


def _two_account_connector(captured=None):
    # B is stored first on purpose: binding must come from the
    # deterministic rule, never from store return order.
    return _connector([_row_b(), _row_a()], captured=captured)


def _authorizations(captured):
    return [request.headers.get('authorization') for request in captured]


# -- Default binding -------------------------------------------------------


def test_default_binding_is_the_earliest_connected_and_is_stable():
    connector = _two_account_connector()
    for _ in range(3):
        bound = asyncio.run(connector.bound_connection(USER_ID))
        assert bound['id'] == 'conn-a'
        assert bound['account_email'] == ACCOUNT_A
    token = asyncio.run(connector.access_token_for(USER_ID))
    assert token == TOKEN_A


def test_default_binding_does_not_depend_on_store_return_order():
    connector = _connector([_row_a(), _row_b()])
    bound = asyncio.run(connector.bound_connection(USER_ID))
    assert bound['id'] == 'conn-a'


def test_default_binding_tie_breaks_by_connection_id():
    same_instant = '2026-11-08T10:00:00+00:00'
    connector = _connector(
        [_row_b(created_at=same_instant), _row_a(created_at=same_instant)]
    )
    bound = asyncio.run(connector.bound_connection(USER_ID))
    assert bound['id'] == 'conn-a'


def test_revoked_connections_are_not_eligible_for_binding():
    connector = _connector([_row_a(status='revoked'), _row_b()])
    bound = asyncio.run(connector.bound_connection(USER_ID))
    assert bound['id'] == 'conn-b'


# -- Explicit binding --------------------------------------------------------


def test_explicit_binding_by_account_email_and_by_connection_id():
    connector = _two_account_connector()
    by_email = asyncio.run(
        connector.bound_connection(USER_ID, account_email=ACCOUNT_B)
    )
    assert by_email['id'] == 'conn-b'
    by_id = asyncio.run(connector.bound_connection(USER_ID, connection_id='conn-b'))
    assert by_id['account_email'] == ACCOUNT_B
    token = asyncio.run(
        connector.access_token_for(USER_ID, account_email=ACCOUNT_B)
    )
    assert token == TOKEN_B


def test_named_connection_that_is_not_connected_fails_without_fallback():
    connector = _two_account_connector()
    with pytest.raises(ConnectionRequiredError) as caught:
        asyncio.run(
            connector.bound_connection(USER_ID, account_email='gone@example.com')
        )
    assert caught.value.code == 'CONNECTION_REQUIRED'
    with pytest.raises(ConnectionRequiredError):
        asyncio.run(connector.bound_connection(USER_ID, connection_id='conn-nope'))
    # A named connection that was revoked must not silently fall back
    # to the other account either.
    revoked_b = _connector([_row_a(), _row_b(status='revoked')])
    with pytest.raises(ConnectionRequiredError):
        asyncio.run(revoked_b.bound_connection(USER_ID, account_email=ACCOUNT_B))


# -- Per-connection scope evaluation -----------------------------------------


def test_scopes_are_evaluated_per_bound_connection_never_unioned():
    connector = _two_account_connector()
    # A holds the read grant: it passes a read check and fails a write
    # check even though B (another of the user's connections) holds
    # the write grant.
    _row, token = asyncio.run(
        connector.bound_access_token(
            USER_ID, account_email=ACCOUNT_A, required_scopes=(GMAIL_READONLY,)
        )
    )
    assert token == TOKEN_A
    with pytest.raises(GoogleConnectorError) as caught:
        asyncio.run(
            connector.bound_access_token(
                USER_ID, account_email=ACCOUNT_A, required_scopes=(GMAIL_SEND,)
            )
        )
    assert caught.value.code == 'INSUFFICIENT_SCOPE'
    # Vice versa: B holds the write grant, passes a write check, and
    # fails a read check — it cannot borrow A's read grant.
    _row, token = asyncio.run(
        connector.bound_access_token(
            USER_ID, account_email=ACCOUNT_B, required_scopes=(GMAIL_SEND,)
        )
    )
    assert token == TOKEN_B
    with pytest.raises(GoogleConnectorError) as caught:
        asyncio.run(
            connector.bound_access_token(
                USER_ID, account_email=ACCOUNT_B, required_scopes=(GMAIL_READONLY,)
            )
        )
    assert caught.value.code == 'INSUFFICIENT_SCOPE'


def test_write_bound_to_the_readonly_connection_fails_before_any_call():
    captured = []
    connector = _two_account_connector(captured=captured)
    # No selector: the default binding is A (read-only), so the write
    # must fail rather than silently switching to B, which could send.
    with pytest.raises(GoogleConnectorError) as caught:
        asyncio.run(
            adapter_execute(
                'gmail.send',
                USER_ID,
                {'to': RECIPIENT, 'subject': SUBJECT, 'body': BODY},
                connector=connector,
            )
        )
    assert caught.value.code == 'INSUFFICIENT_SCOPE'
    assert captured == []
    # Naming A explicitly fails the same way, for send and for draft.
    for capability_id in ('gmail.send', 'gmail.draft'):
        with pytest.raises(GoogleConnectorError) as caught:
            asyncio.run(
                adapter_execute(
                    capability_id,
                    USER_ID,
                    {
                        'to': RECIPIENT,
                        'subject': SUBJECT,
                        'body': BODY,
                        'accountEmail': ACCOUNT_A,
                    },
                    connector=connector,
                )
            )
        assert caught.value.code == 'INSUFFICIENT_SCOPE'
    assert captured == []


def test_write_bound_to_the_write_connection_uses_that_connections_token():
    captured = []
    connector = _two_account_connector(captured=captured)
    sent = asyncio.run(
        adapter_execute(
            'gmail.send',
            USER_ID,
            {
                'to': RECIPIENT,
                'subject': SUBJECT,
                'body': BODY,
                'accountEmail': ACCOUNT_B,
            },
            connector=connector,
        )
    )
    assert sent['status'] == 'sent'
    assert _authorizations(captured) == [f'Bearer {TOKEN_B}']

    captured.clear()
    drafted = asyncio.run(
        adapter_execute(
            'gmail.draft',
            USER_ID,
            {
                'to': RECIPIENT,
                'subject': SUBJECT,
                'body': BODY,
                'connectionId': 'conn-b',
            },
            connector=connector,
        )
    )
    assert drafted['status'] == 'draft_created'
    assert _authorizations(captured) == [f'Bearer {TOKEN_B}']


def test_single_connection_behavior_is_unchanged():
    captured = []
    row = _connection_row(
        'conn-only',
        ACCOUNT_A,
        TOKEN_A,
        READ_GRANT + WRITE_GRANT,
        created_at='2026-11-08T10:00:00+00:00',
    )
    connector = _connector([row], captured=captured)
    bound = asyncio.run(connector.bound_connection(USER_ID))
    assert bound['id'] == 'conn-only'
    assert asyncio.run(connector.access_token_for(USER_ID)) == TOKEN_A
    sent = asyncio.run(
        adapter_execute(
            'gmail.send',
            USER_ID,
            {'to': RECIPIENT, 'subject': SUBJECT, 'body': BODY},
            connector=connector,
        )
    )
    assert sent['status'] == 'sent'
    assert _authorizations(captured) == [f'Bearer {TOKEN_A}']


# -- Executor-level binding ----------------------------------------------------


class FakeRunDB:
    """Minimal in-memory stand-in for the run-ledger store."""

    def __init__(self):
        self.tables: dict[str, list[dict]] = {
            'agent_runs': [],
            'agent_run_steps': [],
            'agent_pending_actions': [],
        }
        self._step_id = 0

    def _matches(self, row, filters):
        for key, raw in (filters or {}).items():
            if isinstance(raw, str) and raw.startswith('eq.'):
                if str(row.get(key)) != raw[3:]:
                    return False
            elif isinstance(raw, str) and raw == 'is.null':
                if row.get(key) is not None:
                    return False
            elif row.get(key) != raw:
                return False
        return True

    async def select(self, table, *, columns='*', filters=None, order=None, limit=None):
        rows = [dict(r) for r in self.tables[table] if self._matches(r, filters)]
        if order:
            field, _, direction = order.partition('.')
            rows.sort(
                key=lambda r: str(r.get(field) or ''), reverse=direction == 'desc'
            )
        if limit is not None:
            rows = rows[:limit]
        return rows

    async def select_one(self, table, *, columns='*', filters=None):
        rows = await self.select(table, filters=filters, limit=1)
        return rows[0] if rows else None

    async def insert(self, table, payload):
        row = dict(payload)
        if table == 'agent_run_steps':
            self._step_id += 1
            row['id'] = self._step_id
        self.tables[table].append(row)
        return [row]

    async def update(self, table, payload, *, filters, **kwargs):
        updated = []
        for row in self.tables[table]:
            if self._matches(row, filters):
                row.update(payload)
                updated.append(dict(row))
        return updated


def _make_executor(captured):
    run_db = FakeRunDB()
    service = AgentRunService(
        run_db, enforce_capability_status=False, enforce_access=False
    )
    connector = _two_account_connector(captured=captured)
    executor = AgentExecutor(
        service, google_connector=connector, execution_paused=False
    )
    return executor, service


async def _create_and_approve(service, capability_id, payload):
    run = await service.create_run(
        user_id=USER_ID, capability_id=capability_id, payload=payload
    )
    if run.get('pendingAction'):
        decided = await service.decide_approval(
            user_id=USER_ID,
            action_id=run['pendingAction']['id'],
            decision='approved',
        )
        assert decided['run']['status'] == 'queued'
    return run


@pytest.mark.asyncio
async def test_executor_read_binds_the_default_connection():
    captured = []
    executor, service = _make_executor(captured)
    run = await _create_and_approve(
        service, 'gmail.search', {'query': 'invoice'}
    )
    result = await executor.execute_run(user_id=USER_ID, run_id=run['id'])
    assert result['status'] == 'succeeded'
    assert captured
    assert set(_authorizations(captured)) == {f'Bearer {TOKEN_A}'}


@pytest.mark.asyncio
async def test_executor_read_bound_to_the_write_only_account_fails_scope():
    captured = []
    executor, service = _make_executor(captured)
    # B cannot read (it holds no read grant); binding the search to B
    # must fail on B's own scopes instead of borrowing A's read grant.
    run = await _create_and_approve(
        service,
        'gmail.search',
        {'query': 'invoice', 'accountEmail': ACCOUNT_B},
    )
    result = await executor.execute_run(user_id=USER_ID, run_id=run['id'])
    assert result['status'] == 'failed'
    assert json.loads(result['resultSummary'])['error']['code'] == (
        'INSUFFICIENT_SCOPE'
    )
    assert captured == []


@pytest.mark.asyncio
async def test_executor_calendar_create_binds_the_named_write_account():
    captured = []
    executor, service = _make_executor(captured)
    run = await _create_and_approve(
        service,
        'calendar.create',
        {
            'summary': 'Dentist',
            'start': '2026-11-10T09:00:00-05:00',
            'end': '2026-11-10T10:00:00-05:00',
            'accountEmail': ACCOUNT_B,
        },
    )
    result = await executor.execute_run(user_id=USER_ID, run_id=run['id'])
    assert result['status'] == 'succeeded'
    assert _authorizations(captured) == [f'Bearer {TOKEN_B}']


@pytest.mark.asyncio
async def test_executor_calendar_create_on_the_default_readonly_account_fails():
    captured = []
    executor, service = _make_executor(captured)
    run = await _create_and_approve(
        service,
        'calendar.create',
        {
            'summary': 'Dentist',
            'start': '2026-11-10T09:00:00-05:00',
            'end': '2026-11-10T10:00:00-05:00',
        },
    )
    result = await executor.execute_run(user_id=USER_ID, run_id=run['id'])
    assert result['status'] == 'failed'
    assert json.loads(result['resultSummary'])['error']['code'] == (
        'INSUFFICIENT_SCOPE'
    )
    assert captured == []


@pytest.mark.asyncio
async def test_executor_gmail_send_uses_the_bound_accounts_token():
    captured = []
    executor, service = _make_executor(captured)
    run = await _create_and_approve(
        service,
        'gmail.send',
        {
            'to': RECIPIENT,
            'subject': SUBJECT,
            'body': BODY,
            'accountEmail': ACCOUNT_B,
        },
    )
    result = await executor.execute_run(user_id=USER_ID, run_id=run['id'])
    assert result['status'] == 'succeeded'
    assert _authorizations(captured) == [f'Bearer {TOKEN_B}']
