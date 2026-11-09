"""Execution-integrity regressions for the agent run executor.

Execution must use only the payload of record — the approved action's
frozen exact payload for approval-gated runs, the run's stored
creation payload otherwise — and claiming a queued run must be a
compare-and-swap so concurrent executes run a provider exactly once.
These tests pin both properties: a caller-supplied payload can never
reach a provider, and a second concurrent execute gets a conflict.
"""
import asyncio
import inspect
import json

import pytest

from backend.agent_executor import AgentExecutor
from backend.agent_run_service import AgentRunConflictError, AgentRunService
from backend.routes import agent as agent_routes

USER = '11111111-1111-1111-1111-111111111111'

EVENT_A = {
    'summary': 'Approved dentist visit',
    'start': '2026-11-10T09:00:00-05:00',
    'end': '2026-11-10T10:00:00-05:00',
    'attendees': ['a@example.com'],
}
EVENT_B = {
    'summary': 'Substituted event',
    'start': '2026-12-24T09:00:00-05:00',
    'end': '2026-12-24T10:00:00-05:00',
    'attendees': ['attacker@example.com'],
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
    oauth_configured = True

    def __init__(self):
        self.search_queries: list[str] = []
        self.created_events: list[dict] = []

    async def status(self, user_id):
        return {
            'connected': True,
            'accounts': [{'email': 'person@example.com', 'scopes': [], 'status': 'connected'}],
        }

    async def access_token_for(self, user_id, account_email=None):
        return 'access-token-1'

    async def search_messages(self, access_token, query, max_results=10):
        self.search_queries.append(query)
        return []

    async def create_event(self, access_token, **kwargs):
        self.created_events.append(dict(kwargs))
        return {
            'id': 'e-created',
            'summary': kwargs.get('summary') or '',
            'start': kwargs.get('start') or '',
            'end': kwargs.get('end') or '',
        }


def make_executor():
    db = FakeDB()
    # These tests exercise payload-of-record and CAS behavior, not the
    # emergency pause or the registry-status gate: both fail-closed
    # defaults are opted out explicitly, the same pattern the adapter
    # suites use. The pause itself is covered unchanged in
    # tests/test_agent_execution_pause.py.
    service = AgentRunService(
        db, enforce_capability_status=False, enforce_access=False
    )
    connector = FakeGoogleConnector()
    executor = AgentExecutor(
        service, google_connector=connector, execution_paused=False
    )
    return executor, service, db, connector


def test_execution_entry_points_accept_no_caller_payload():
    # The substitution vector was a caller-controlled payload argument
    # on the executor and the /execute route. Neither may accept one.
    for fn in (
        AgentExecutor.execute_run,
        AgentExecutor.execute_run_record,
        AgentExecutor.execute_run_dict,
    ):
        assert 'payload' not in inspect.signature(fn).parameters
    assert 'payload' not in inspect.signature(agent_routes.execute_run).parameters


@pytest.mark.asyncio
async def test_approved_payload_executes_and_substituted_payload_cannot():
    executor, service, db, connector = make_executor()
    run = await service.create_run(
        user_id=USER, capability_id='calendar.create', payload=dict(EVENT_A)
    )
    decided = await service.decide_approval(
        user_id=USER,
        action_id=run['pendingAction']['id'],
        decision='approved',
    )
    assert decided['run']['status'] == 'queued'
    # The old attack: pass payload B at execution time. The executor
    # has no such parameter anymore, so B can never reach a provider.
    with pytest.raises(TypeError):
        await executor.execute_run(user_id=USER, run_id=run['id'], payload=EVENT_B)
    result = await executor.execute_run(user_id=USER, run_id=run['id'])
    assert result['status'] == 'succeeded'
    assert len(connector.created_events) == 1
    created = connector.created_events[0]
    assert created['summary'] == EVENT_A['summary']
    assert created['attendees'] == EVENT_A['attendees']
    assert 'attacker@example.com' not in json.dumps(connector.created_events)


@pytest.mark.asyncio
async def test_concurrent_executes_run_the_provider_exactly_once():
    executor, service, db, connector = make_executor()
    run = await service.create_run(
        user_id=USER, capability_id='gmail.search', payload={'query': 'invoice'}
    )
    results = await asyncio.gather(
        executor.execute_run(user_id=USER, run_id=run['id']),
        executor.execute_run(user_id=USER, run_id=run['id']),
        return_exceptions=True,
    )
    conflicts = [r for r in results if isinstance(r, AgentRunConflictError)]
    successes = [r for r in results if isinstance(r, dict)]
    assert len(conflicts) == 1
    assert len(successes) == 1
    assert successes[0]['status'] == 'succeeded'
    # Exactly one provider call, with the stored creation payload.
    assert connector.search_queries == ['invoice']


@pytest.mark.asyncio
async def test_concurrent_approval_decisions_execute_exactly_once():
    executor, service, db, connector = make_executor()
    run = await service.create_run(
        user_id=USER, capability_id='calendar.create', payload=dict(EVENT_A)
    )
    action_id = run['pendingAction']['id']
    results = await asyncio.gather(
        service.decide_approval(user_id=USER, action_id=action_id, decision='approved'),
        service.decide_approval(user_id=USER, action_id=action_id, decision='approved'),
        return_exceptions=True,
    )
    decided = [r for r in results if isinstance(r, dict)]
    conflicts = [r for r in results if isinstance(r, AgentRunConflictError)]
    assert len(decided) == 1
    assert len(conflicts) == 1
    result = await executor.execute_run(user_id=USER, run_id=run['id'])
    assert result['status'] == 'succeeded'
    assert len(connector.created_events) == 1
    assert connector.created_events[0]['summary'] == EVENT_A['summary']
    # And the executed run cannot be claimed a second time.
    with pytest.raises(AgentRunConflictError):
        await executor.execute_run(user_id=USER, run_id=run['id'])
    assert len(connector.created_events) == 1
