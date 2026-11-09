import json

import pytest

from backend import agent_registry
from backend.agent_executor import AgentExecutor
from backend.agent_run_service import AgentRunService
from backend.google_connector import ConnectionRequiredError, InsufficientScopeError

USER = '11111111-1111-1111-1111-111111111111'

EVENT_PAYLOAD = {
    'summary': 'Dentist',
    'start': '2026-11-10T09:00:00-05:00',
    'end': '2026-11-10T10:00:00-05:00',
    'attendees': ['a@example.com'],
}

MESSAGE = {
    'id': 'm1',
    'from': 'Sender <s@example.com>',
    'subject': 'Invoice 42',
    'snippet': 'snippet-m1',
    'date': 'Sun, 8 Nov 2026 10:00:00 -0500',
}


class FakeDB:
    """Minimal in-memory stand-in for SupabaseDB's select/insert/update."""

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
            rows.sort(key=lambda r: str(r.get(field) or ''), reverse=direction == 'desc')
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


class FakeGoogleConnector:
    """In-memory Google connector with a switchable connection state.

    ``create_event`` records the exact keyword arguments it was called
    with so tests can prove the executor dispatched the approved
    payload and nothing else.
    """

    oauth_configured = True

    def __init__(self, *, connected: bool = True, message=None, create_error=None):
        self.connected = connected
        self.message = message
        self.create_error = create_error
        self.created_events: list[dict] = []
        self.read_message_ids: list[str] = []

    async def status(self, user_id):
        accounts = (
            [{'email': 'person@example.com', 'scopes': [], 'status': 'connected'}]
            if self.connected
            else []
        )
        return {'connected': self.connected, 'accounts': accounts}

    async def access_token_for(self, user_id, account_email=None):
        if not self.connected:
            raise ConnectionRequiredError()
        return 'access-token-1'

    async def create_event(self, access_token, **kwargs):
        assert access_token == 'access-token-1'
        if self.create_error is not None:
            raise self.create_error
        self.created_events.append(dict(kwargs))
        return {
            'id': 'e-created',
            'summary': kwargs.get('summary') or '',
            'start': kwargs.get('start') or '',
            'end': kwargs.get('end') or '',
            'location': 'Office',
            'attendees': list(kwargs.get('attendees') or []),
        }

    async def get_message(self, access_token, message_id):
        assert access_token == 'access-token-1'
        self.read_message_ids.append(message_id)
        if self.message is not None:
            return dict(self.message)
        return dict(MESSAGE)


def make_executor(*, connected: bool = True, message=None, create_error=None):
    db = FakeDB()
    # Adapter tests exercise dispatch for capabilities that are not
    # live yet and run while production execution is paused; both
    # fail-closed defaults are opted out here explicitly and covered
    # in tests/test_agent_execution_pause.py.
    service = AgentRunService(db, enforce_capability_status=False)
    connector = FakeGoogleConnector(
        connected=connected, message=message, create_error=create_error
    )
    executor = AgentExecutor(
        service, google_connector=connector, execution_paused=False
    )
    return executor, service, db, connector


async def approve_run(service, run):
    decided = await service.decide_approval(
        user_id=USER,
        action_id=run['pendingAction']['id'],
        decision='approved',
    )
    assert decided['run']['status'] == 'queued'


@pytest.mark.asyncio
async def test_calendar_create_executes_the_frozen_approved_payload():
    executor, service, db, connector = make_executor()
    run = await service.create_run(
        user_id=USER, capability_id='calendar.create', payload=dict(EVENT_PAYLOAD)
    )
    await approve_run(service, run)
    # No payload argument: the executor must resolve the payload frozen
    # on the approved action and dispatch exactly those fields.
    result = await executor.execute_run(user_id=USER, run_id=run['id'])
    assert result['status'] == 'succeeded'
    assert connector.created_events == [EVENT_PAYLOAD]
    summary = json.loads(result['resultSummary'])
    assert summary == {
        'kind': 'calendar.create',
        'eventId': 'e-created',
        'summary': 'Dentist',
        'start': EVENT_PAYLOAD['start'],
        'end': EVENT_PAYLOAD['end'],
    }


@pytest.mark.asyncio
async def test_calendar_create_without_attendees_sends_required_fields_only():
    executor, service, db, connector = make_executor()
    payload = {
        'summary': 'Focus block',
        'start': '2026-11-10T13:00:00-05:00',
        'end': '2026-11-10T14:00:00-05:00',
    }
    run = await service.create_run(
        user_id=USER, capability_id='calendar.create', payload=dict(payload)
    )
    await approve_run(service, run)
    result = await executor.execute_run(user_id=USER, run_id=run['id'])
    assert result['status'] == 'succeeded'
    assert connector.created_events == [payload]


@pytest.mark.asyncio
async def test_calendar_create_without_connection_fails_honestly():
    executor, service, db, connector = make_executor(connected=False)
    run = await service.create_run(
        user_id=USER, capability_id='calendar.create', payload=dict(EVENT_PAYLOAD)
    )
    await approve_run(service, run)
    result = await executor.execute_run(user_id=USER, run_id=run['id'])
    assert result['status'] == 'failed'
    summary = json.loads(result['resultSummary'])
    assert summary['error']['code'] == 'CONNECTION_REQUIRED'
    assert connector.created_events == []


@pytest.mark.asyncio
async def test_calendar_create_maps_insufficient_scope_from_the_connector():
    executor, service, db, connector = make_executor(
        create_error=InsufficientScopeError()
    )
    run = await service.create_run(
        user_id=USER, capability_id='calendar.create', payload=dict(EVENT_PAYLOAD)
    )
    await approve_run(service, run)
    result = await executor.execute_run(user_id=USER, run_id=run['id'])
    assert result['status'] == 'failed'
    summary = json.loads(result['resultSummary'])
    assert summary['error']['code'] == 'INSUFFICIENT_SCOPE'
    assert connector.created_events == []


@pytest.mark.asyncio
async def test_calendar_create_missing_fields_fail_before_any_provider_call():
    executor, service, db, connector = make_executor()
    run = await service.create_run(
        user_id=USER, capability_id='calendar.create', payload=dict(EVENT_PAYLOAD)
    )
    await approve_run(service, run)
    result = await executor.execute_run(user_id=USER, run_id=run['id'], payload={})
    assert result['status'] == 'failed'
    summary = json.loads(result['resultSummary'])
    assert summary['error']['code'] == 'INVALID_RUN_INPUT'
    assert connector.created_events == []


@pytest.mark.asyncio
async def test_gmail_read_success_returns_the_message_summary():
    executor, service, db, connector = make_executor()
    run = await service.create_run(
        user_id=USER, capability_id='gmail.read', payload={'messageId': 'm1'}
    )
    result = await executor.execute_run(
        user_id=USER, run_id=run['id'], payload={'messageId': 'm1'}
    )
    assert result['status'] == 'succeeded'
    assert connector.read_message_ids == ['m1']
    summary = json.loads(result['resultSummary'])
    assert summary['kind'] == 'gmail.read'
    assert summary['message'] == MESSAGE


@pytest.mark.asyncio
async def test_gmail_read_summary_never_carries_a_message_body():
    oversized_body = 'body-text-' + 'x' * 5000
    message = {
        **MESSAGE,
        'snippet': 's' * 1000,
        'body': oversized_body,
    }
    executor, service, db, connector = make_executor(message=message)
    run = await service.create_run(
        user_id=USER, capability_id='gmail.read', payload={'messageId': 'm1'}
    )
    result = await executor.execute_run(
        user_id=USER, run_id=run['id'], payload={'messageId': 'm1'}
    )
    assert result['status'] == 'succeeded'
    summary_text = result['resultSummary']
    assert 'body' not in json.loads(summary_text)['message']
    assert oversized_body not in summary_text
    summary = json.loads(summary_text)
    # Fields are fenced to the same per-field cap as a search summary.
    assert summary['message']['snippet'] == 's' * 300
    assert set(summary['message']) == {'id', 'from', 'subject', 'snippet', 'date'}


@pytest.mark.asyncio
async def test_gmail_read_missing_message_id_fails_honestly():
    executor, service, db, connector = make_executor()
    run = await service.create_run(
        user_id=USER, capability_id='gmail.read', payload={'messageId': 'm1'}
    )
    result = await executor.execute_run(user_id=USER, run_id=run['id'], payload={})
    assert result['status'] == 'failed'
    summary = json.loads(result['resultSummary'])
    assert summary['error']['code'] == 'INVALID_RUN_INPUT'
    assert connector.read_message_ids == []


@pytest.mark.asyncio
async def test_gmail_read_without_connection_fails_honestly():
    executor, service, db, connector = make_executor(connected=False)
    run = await service.create_run(
        user_id=USER, capability_id='gmail.read', payload={'messageId': 'm1'}
    )
    result = await executor.execute_run(
        user_id=USER, run_id=run['id'], payload={'messageId': 'm1'}
    )
    assert result['status'] == 'failed'
    summary = json.loads(result['resultSummary'])
    assert summary['error']['code'] == 'CONNECTION_REQUIRED'
    assert connector.read_message_ids == []


def test_calendar_create_and_gmail_read_stay_planned_in_the_registry():
    # The adapters are wired here, but the registry status flips only
    # once the Google OAuth round-trip is verified in production.
    assert agent_registry.require_capability('calendar.create').status == 'planned'
    assert agent_registry.require_capability('gmail.read').status == 'planned'
