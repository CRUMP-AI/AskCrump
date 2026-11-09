import json

import pytest

from app import app
from backend.agent_executor import AgentExecutor, build_today_brief
from backend.agent_run_service import AgentRunConflictError, AgentRunService
from backend.google_connector import ConnectionRequiredError
from conftest import iter_effective_routes

USER = '11111111-1111-1111-1111-111111111111'

MESSAGES = [
    {
        'id': 'm1',
        'from': 'Sender <s@example.com>',
        'subject': 'Invoice 42',
        'snippet': 'snippet-m1',
        'date': 'Sun, 8 Nov 2026 10:00:00 -0500',
    }
]
EVENTS = [
    {
        'id': 'e1',
        'summary': 'Standup',
        'start': '2026-11-09T14:00:00Z',
        'end': '2026-11-09T14:30:00Z',
        'location': 'Office',
        'attendees': ['a@example.com'],
    }
]


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
    """In-memory Google connector with a switchable connection state."""

    oauth_configured = True

    def __init__(self, *, connected: bool):
        self.connected = connected
        self.search_queries: list[str] = []

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

    async def search_messages(self, access_token, query, max_results=10):
        assert access_token == 'access-token-1'
        self.search_queries.append(query)
        return list(MESSAGES)

    async def list_events(self, access_token, time_min=None, time_max=None, max_results=50):
        assert access_token == 'access-token-1'
        return list(EVENTS)


def make_executor(*, connected: bool):
    db = FakeDB()
    # Adapter tests exercise dispatch for capabilities that are not
    # live yet and run while production execution is paused; both
    # fail-closed defaults are opted out here explicitly and covered
    # in tests/test_agent_execution_pause.py.
    service = AgentRunService(
        db, enforce_capability_status=False, enforce_access=False
    )
    connector = FakeGoogleConnector(connected=connected)
    executor = AgentExecutor(
        service, google_connector=connector, execution_paused=False
    )
    return executor, service, db, connector


def step_types(db):
    return [s['step_type'] for s in db.tables['agent_run_steps']]


def stored_run(db, run_id):
    return next(r for r in db.tables['agent_runs'] if r['id'] == run_id)


@pytest.mark.asyncio
async def test_today_brief_composes_real_sources_when_google_connected():
    executor, service, db, connector = make_executor(connected=True)
    pending = await service.create_run(
        user_id=USER,
        capability_id='calendar.create',
        payload={
            'summary': 'Dentist',
            'start': '2026-11-10T09:00:00-05:00',
            'end': '2026-11-10T10:00:00-05:00',
        },
    )
    await service.create_run(
        user_id=USER, capability_id='agent.today_brief', payload={}
    )
    brief = await build_today_brief(
        USER, run_service=service, google_connector=connector
    )
    assert brief['generatedAt']
    assert [a['id'] for a in brief['pendingApprovals']] == [
        pending['pendingAction']['id']
    ]
    assert len(brief['recentRuns']) == 2
    assert brief['connections']['google']['connected'] is True
    assert brief['connections']['google']['status'] == 'connected'
    assert brief['calendar'] == EVENTS
    assert brief['inboxHighlights'] == MESSAGES


@pytest.mark.asyncio
async def test_today_brief_degrades_google_sources_when_not_connected():
    executor, service, db, connector = make_executor(connected=False)
    await service.create_run(
        user_id=USER, capability_id='agent.today_brief', payload={}
    )
    brief = await build_today_brief(
        USER, run_service=service, google_connector=connector
    )
    assert brief['connections']['google']['connected'] is False
    assert brief['connections']['google']['status'] == 'not_connected'
    assert isinstance(brief['calendar'], str)
    assert brief['calendar'].startswith('unavailable:')
    assert isinstance(brief['inboxHighlights'], str)
    assert brief['inboxHighlights'].startswith('unavailable:')
    # Ledger-backed sections still come through with real data.
    assert brief['pendingApprovals'] == []
    assert len(brief['recentRuns']) == 1


@pytest.mark.asyncio
async def test_executor_calendar_list_success_records_steps_and_summary():
    executor, service, db, connector = make_executor(connected=True)
    run = await service.create_run(
        user_id=USER, capability_id='calendar.list', payload={}
    )
    result = await executor.execute_run(user_id=USER, run_id=run['id'])
    assert result['status'] == 'succeeded'
    summary = json.loads(result['resultSummary'])
    assert summary['kind'] == 'calendar.list'
    assert summary['count'] == 1
    assert summary['events'][0]['summary'] == 'Standup'
    types = step_types(db)
    assert types[0] == 'run.created'
    assert 'run.started' in types
    assert 'step.started' in types
    assert 'step.completed' in types
    assert types[-1] == 'run.completed'
    detail = await service.get_run(user_id=USER, run_id=run['id'])
    assert detail['steps'][-1]['type'] == 'run.completed'


@pytest.mark.asyncio
async def test_executor_gmail_search_success_with_stored_payload():
    executor, service, db, connector = make_executor(connected=True)
    run = await service.create_run(
        user_id=USER, capability_id='gmail.search', payload={'query': 'invoice'}
    )
    result = await executor.execute_run(user_id=USER, run_id=run['id'])
    assert result['status'] == 'succeeded'
    summary = json.loads(result['resultSummary'])
    assert summary['kind'] == 'gmail.search'
    assert summary['count'] == 1
    assert summary['messages'][0]['subject'] == 'Invoice 42'
    assert connector.search_queries == ['invoice']


@pytest.mark.asyncio
async def test_executor_gmail_search_without_connection_fails_honestly():
    executor, service, db, connector = make_executor(connected=False)
    run = await service.create_run(
        user_id=USER, capability_id='gmail.search', payload={'query': 'invoice'}
    )
    result = await executor.execute_run(user_id=USER, run_id=run['id'])
    assert result['status'] == 'failed'
    summary = json.loads(result['resultSummary'])
    assert summary['error']['code'] == 'CONNECTION_REQUIRED'
    types = step_types(db)
    assert 'step.failed' in types
    assert types[-1] == 'run.failed'
    failed_step = next(
        s for s in db.tables['agent_run_steps'] if s['step_type'] == 'step.failed'
    )
    assert failed_step['payload']['code'] == 'CONNECTION_REQUIRED'


@pytest.mark.asyncio
async def test_executor_calendar_list_without_connection_fails_honestly():
    executor, service, db, connector = make_executor(connected=False)
    run = await service.create_run(
        user_id=USER, capability_id='calendar.list', payload={}
    )
    result = await executor.execute_run(user_id=USER, run_id=run['id'])
    assert result['status'] == 'failed'
    assert json.loads(result['resultSummary'])['error']['code'] == (
        'CONNECTION_REQUIRED'
    )
    assert stored_run(db, run['id'])['status'] == 'failed'


@pytest.mark.asyncio
async def test_executor_without_adapter_fails_with_not_available():
    executor, service, db, connector = make_executor(connected=True)
    run = await service.create_run(
        user_id=USER, capability_id='chat.respond', payload={'message': 'hi'}
    )
    result = await executor.execute_run(user_id=USER, run_id=run['id'])
    assert result['status'] == 'failed'
    summary = json.loads(result['resultSummary'])
    assert summary['error']['code'] == 'EXECUTOR_NOT_AVAILABLE'
    assert step_types(db)[-1] == 'run.failed'


@pytest.mark.asyncio
async def test_executor_today_brief_run_succeeds():
    executor, service, db, connector = make_executor(connected=True)
    run = await service.create_run(
        user_id=USER, capability_id='agent.today_brief', payload={}
    )
    result = await executor.execute_run(user_id=USER, run_id=run['id'])
    assert result['status'] == 'succeeded'
    summary = json.loads(result['resultSummary'])
    assert summary['kind'] == 'agent.today_brief'
    assert summary['googleConnected'] is True
    assert summary['calendar'] == 1
    assert summary['inboxHighlights'] == 1


@pytest.mark.asyncio
async def test_executor_claims_and_executes_queued_runs():
    executor, service, db, connector = make_executor(connected=True)
    first = await service.create_run(
        user_id=USER, capability_id='calendar.list', payload={}
    )
    second = await service.create_run(
        user_id=USER, capability_id='agent.today_brief', payload={}
    )
    waiting = await service.create_run(
        user_id=USER,
        capability_id='calendar.create',
        payload={
            'summary': 'Dentist',
            'start': '2026-11-10T09:00:00-05:00',
            'end': '2026-11-10T10:00:00-05:00',
        },
    )
    results = await executor.execute_queued_runs(user_id=USER)
    assert {r['id'] for r in results} == {first['id'], second['id']}
    assert all(r['status'] == 'succeeded' for r in results)
    # Runs still waiting on an approval are never claimed.
    assert stored_run(db, waiting['id'])['status'] == 'waiting_approval'


@pytest.mark.asyncio
async def test_executor_dispatches_a_single_run_dict():
    executor, service, db, connector = make_executor(connected=True)
    run = await service.create_run(
        user_id=USER, capability_id='calendar.list', payload={}
    )
    result = await executor.execute_run_dict(
        {'id': run['id'], 'userId': USER, 'capabilityId': 'calendar.list',
         'status': 'queued'}
    )
    assert result['status'] == 'succeeded'


@pytest.mark.asyncio
async def test_executor_refuses_a_run_that_is_not_queued():
    executor, service, db, connector = make_executor(connected=True)
    run = await service.create_run(
        user_id=USER,
        capability_id='calendar.create',
        payload={
            'summary': 'Dentist',
            'start': '2026-11-10T09:00:00-05:00',
            'end': '2026-11-10T10:00:00-05:00',
        },
    )
    with pytest.raises(AgentRunConflictError):
        await executor.execute_run(user_id=USER, run_id=run['id'])
    assert stored_run(db, run['id'])['status'] == 'waiting_approval'


@pytest.mark.asyncio
async def test_approved_run_executes_its_frozen_payload(monkeypatch):
    executor, service, db, connector = make_executor(connected=True)
    # The approved pending action freezes the exact payload; dispatch
    # must hand the Gmail write adapter that payload, not a re-read.
    dispatched = {}

    async def fake_write_execute(capability_id, user_id, payload, *, connector=None):
        dispatched['capability_id'] = capability_id
        dispatched['payload'] = payload
        dispatched['connector'] = connector
        return {
            'capabilityId': capability_id,
            'status': 'draft_created',
            'draftId': 'd1',
            'messageId': 'm1',
            'threadId': 't1',
            'recipientDomain': 'example.com',
            'subjectLength': 0,
        }

    monkeypatch.setattr(
        'backend.agent_executor.agent_gmail_write.execute', fake_write_execute
    )
    run = await service.create_run(
        user_id=USER,
        capability_id='gmail.draft',
        payload={'to': 'a@example.com', 'body': 'Hello'},
    )
    decided = await service.decide_approval(
        user_id=USER,
        action_id=run['pendingAction']['id'],
        decision='approved',
    )
    assert decided['run']['status'] == 'queued'
    result = await executor.execute_run(user_id=USER, run_id=run['id'])
    assert result['status'] == 'succeeded'
    assert dispatched['capability_id'] == 'gmail.draft'
    assert dispatched['payload'] == {'to': 'a@example.com', 'body': 'Hello'}
    assert dispatched['connector'] is connector
    summary = json.loads(result['resultSummary'])
    assert summary['kind'] == 'gmail.draft'
    assert summary['status'] == 'draft_created'


def test_executor_routes_are_registered():
    actual = {
        (method, route.path)
        for route in iter_effective_routes(app)
        for method in getattr(route, 'methods', set())
        if method not in {'HEAD', 'OPTIONS'}
    }
    assert ('GET', '/api/agent/today') in actual
    assert ('POST', '/api/agent/runs/{run_id}/execute') in actual
