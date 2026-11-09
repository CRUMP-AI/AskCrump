"""Emergency execution pause — completed fail-closed state.

Two verified criticals are open against the agent executor: the
``POST /api/agent/runs/{run_id}/execute`` route accepted caller input
that could substitute the approved payload, and the browser fetch
validates one DNS resolution while connecting by hostname on a second
one (rebinding/TOCTOU). The first pause (route-level) was partial:
approval decisions and automation triggers could still execute runs.
The completed state, proven here:

- the pause lives in ``AgentExecutor.execute_run_record`` — the single
  choke point every caller (execute route, approval decisions,
  automation triggers) goes through — and raises
  ``AGENT_EXECUTION_PAUSED`` for every capability before any provider
  contact, leaving the run queued;
- the execute route ALSO fails closed on its own (defense in depth);
- ``browser.read`` is ``planned`` in the registry, and the executor's
  browser adapter fails closed behind the executor gate;
- approval decisions are compare-and-swap: the action update filters
  on ``status='pending'``, so concurrent decisions produce exactly one
  execution and one conflict;
- run creation enforces registry status: non-live capabilities are
  rejected with ``CAPABILITY_NOT_LIVE``.

Execution stays disabled until the payload-of-record/CAS execution fix
and the pinned browser fetch land and are re-reviewed.
"""
import asyncio
import threading
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import app as app_module
from backend import agent_registry
from backend.agent_automation_service import AgentAutomationService
from backend.agent_executor import AgentExecutor
from backend.agent_run_service import (
    AgentRunConflictError,
    AgentRunError,
    AgentRunService,
)
from backend.routes import agent as agent_routes
from test_agent_automations import FakeDB as AutomationFakeDB
from test_agent_automations import FakeGoogleConnector
from test_agent_executor_adapters import FakeDB, USER

CLIENT = TestClient(app_module.app)
RUN_ID = '22222222-2222-2222-2222-222222222222'


def seed_queued_run(db, *, capability_id='browser.read'):
    row = {
        'id': RUN_ID,
        'user_id': USER,
        'project_id': None,
        'conversation_id': None,
        'capability_id': capability_id,
        'status': 'queued',
        'input_summary': {},
        'result_summary': None,
        'credit_cost': None,
        'created_at': '2026-11-09T00:00:00+00:00',
        'updated_at': '2026-11-09T00:00:00+00:00',
    }
    db.tables['agent_runs'].append(row)
    return row


# -- execute route (defense in depth) --------------------------------------


class _RecordingExecutor:
    def __init__(self):
        self.calls = []

    async def execute_run(self, **kwargs):
        self.calls.append(kwargs)
        raise AssertionError('executor must not be called while paused')


@pytest.fixture
def paused_route(monkeypatch):
    recorder = _RecordingExecutor()

    async def fake_auth(request):
        return SimpleNamespace(user={'id': USER})

    monkeypatch.setattr(agent_routes, '_auth', fake_auth)
    monkeypatch.setattr(agent_routes, '_executor', lambda: recorder)
    return recorder


def test_execute_route_fails_closed_and_never_executes(paused_route):
    response = CLIENT.post(
        f'/api/agent/runs/{RUN_ID}/execute',
        json={'input': {'url': 'https://example.com/substituted'}},
    )
    assert response.status_code == 503
    body = response.json()
    assert body['success'] is False
    assert body['code'] == 'AGENT_EXECUTION_PAUSED'
    assert paused_route.calls == []


# -- executor choke point ----------------------------------------------------


@pytest.mark.asyncio
async def test_executor_pause_blocks_every_capability_before_providers(
    monkeypatch,
):
    db = FakeDB()
    service = AgentRunService(db, enforce_capability_status=False)
    connector = FakeGoogleConnector(connected=True)
    executor = AgentExecutor(service, google_connector=connector)
    provider_calls = []

    async def counting_search(*args, **kwargs):
        provider_calls.append((args, kwargs))
        return []

    monkeypatch.setattr(connector, 'search_messages', counting_search)
    run = await service.create_run(
        user_id=USER,
        capability_id='gmail.search',
        payload={'query': 'invoice'},
    )
    with pytest.raises(AgentRunError) as excinfo:
        await executor.execute_run(user_id=USER, run_id=run['id'])
    assert excinfo.value.code == 'AGENT_EXECUTION_PAUSED'
    assert excinfo.value.status_code == 503
    assert provider_calls == []
    # The run was never claimed: it stays queued for the unpaused world.
    assert db.tables['agent_runs'][0]['status'] == 'queued'


@pytest.mark.asyncio
async def test_browser_read_run_fails_closed_before_any_fetch(monkeypatch):
    db = FakeDB()
    seed_queued_run(db)
    service = AgentRunService(db)
    executor = AgentExecutor(service, google_connector=object())
    fetches = []

    async def recording_fetch(capability_id, user_id, payload):
        fetches.append((capability_id, payload))
        return {}

    monkeypatch.setattr(
        'backend.agent_executor.browser_agent.execute', recording_fetch
    )
    with pytest.raises(AgentRunError) as excinfo:
        await executor.execute_run(user_id=USER, run_id=RUN_ID)
    assert excinfo.value.code == 'AGENT_EXECUTION_PAUSED'
    assert fetches == []
    assert db.tables['agent_runs'][0]['status'] == 'queued'


def test_browser_read_is_planned_in_the_registry():
    capability = agent_registry.require_capability('browser.read')
    assert capability.status == 'planned'
    catalog = {
        item['id']: item
        for item in agent_registry.public_catalog()['capabilities']
    }
    assert catalog['browser.read']['status'] == 'planned'


# -- create-time status enforcement ------------------------------------------


@pytest.mark.asyncio
async def test_planned_capability_create_is_rejected():
    service = AgentRunService(FakeDB())
    with pytest.raises(AgentRunError) as excinfo:
        await service.create_run(
            user_id=USER,
            capability_id='gmail.search',
            payload={'query': 'invoice'},
        )
    assert excinfo.value.code == 'CAPABILITY_NOT_LIVE'
    assert excinfo.value.status_code == 409


@pytest.mark.asyncio
async def test_live_capability_create_still_works():
    service = AgentRunService(FakeDB())
    run = await service.create_run(
        user_id=USER,
        capability_id='agent.today_brief',
        payload={},
    )
    assert run['status'] == 'queued'


# -- approval decisions: CAS + pause ------------------------------------------


class YieldingFakeDB(FakeDB):
    """FakeDB whose reads/writes yield once, so concurrent callers
    interleave exactly the way production requests do."""

    async def select_one(self, table, *, columns='*', filters=None):
        await asyncio.sleep(0)
        return await super().select_one(
            table, columns=columns, filters=filters
        )

    async def update(self, table, payload, *, filters, **kwargs):
        await asyncio.sleep(0)
        return await super().update(
            table, payload, filters=filters, **kwargs
        )


def counting_gmail_write(monkeypatch):
    calls = []

    async def counting_execute(
        capability_id, user_id, payload, *, connector=None
    ):
        calls.append((capability_id, payload))
        return {'messageId': 'message-1'}

    monkeypatch.setattr(
        'backend.agent_executor.agent_gmail_write.execute', counting_execute
    )
    return calls


async def _gmail_send_run(service):
    run = await service.create_run(
        user_id=USER,
        capability_id='gmail.send',
        payload={'to': 'a@example.com', 'subject': 'Hi', 'body': 'Hello'},
    )
    return run, run['pendingAction']['id']


@pytest.mark.asyncio
async def test_concurrent_decisions_execute_exactly_once(monkeypatch):
    provider_calls = counting_gmail_write(monkeypatch)
    db = YieldingFakeDB()
    service = AgentRunService(db, enforce_capability_status=False)
    executor = AgentExecutor(
        service,
        google_connector=FakeGoogleConnector(connected=True),
        execution_paused=False,
    )
    run, action_id = await _gmail_send_run(service)

    async def decide():
        return await service.decide_approval(
            user_id=USER, action_id=action_id, decision='approved'
        )

    results = await asyncio.gather(decide(), decide(), return_exceptions=True)
    successes = [r for r in results if not isinstance(r, Exception)]
    conflicts = [r for r in results if isinstance(r, AgentRunConflictError)]
    assert len(successes) == 1
    assert len(conflicts) == 1
    # Only the winning decision's run may execute, and only once.
    executed = await executor.execute_run(user_id=USER, run_id=run['id'])
    assert executed['status'] == 'succeeded'
    assert len(provider_calls) == 1


def test_concurrent_decision_route_calls_execute_exactly_once(monkeypatch):
    provider_calls = counting_gmail_write(monkeypatch)
    db = YieldingFakeDB()
    service = AgentRunService(db, enforce_capability_status=False)
    executor = AgentExecutor(
        service,
        google_connector=FakeGoogleConnector(connected=True),
        execution_paused=False,
    )

    async def fake_auth(request):
        return SimpleNamespace(user={'id': USER})

    monkeypatch.setattr(agent_routes, '_auth', fake_auth)
    monkeypatch.setattr(agent_routes, 'agent_runs', service)
    monkeypatch.setattr(agent_routes, '_executor', lambda: executor)

    _run, action_id = asyncio.run(_gmail_send_run(service))
    statuses = []
    lock = threading.Lock()

    def call_route():
        with TestClient(app_module.app) as client:
            response = client.post(
                f'/api/agent/approvals/{action_id}/decision',
                json={'decision': 'approved'},
            )
        with lock:
            statuses.append(response.status_code)

    threads = [threading.Thread(target=call_route) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(statuses) == [200, 409]
    assert len(provider_calls) == 1


@pytest.mark.asyncio
async def test_decision_route_while_paused_never_calls_provider(monkeypatch):
    provider_calls = counting_gmail_write(monkeypatch)
    db = FakeDB()
    service = AgentRunService(db, enforce_capability_status=False)

    async def fake_auth(request):
        return SimpleNamespace(user={'id': USER})

    monkeypatch.setattr(agent_routes, '_auth', fake_auth)
    monkeypatch.setattr(agent_routes, 'agent_runs', service)
    # _executor keeps its production factory (paused by default); the
    # connector only needs to exist for the wiring.
    monkeypatch.setattr(
        agent_routes,
        '_google_connector',
        lambda: FakeGoogleConnector(connected=True),
    )
    _run, action_id = await _gmail_send_run(service)
    response = CLIENT.post(
        f'/api/agent/approvals/{action_id}/decision',
        json={'decision': 'approved'},
    )
    assert response.status_code == 200
    assert provider_calls == []
    # The decision itself landed; only execution is paused, so the run
    # waits queued instead of reaching the provider.
    assert db.tables['agent_pending_actions'][0]['status'] == 'approved'
    assert db.tables['agent_runs'][0]['status'] == 'queued'


# -- automations while paused ---------------------------------------------------


@pytest.mark.asyncio
async def test_automation_due_work_while_paused_never_calls_provider(
    monkeypatch,
):
    db = AutomationFakeDB()
    runs = AgentRunService(db)
    automations = AgentAutomationService(db)
    created = await automations.create_automation(
        user_id=USER,
        capability_id='agent.morning_brief',
        schedule={'time': '07:30', 'timezone': 'UTC'},
        now=datetime(2020, 1, 1, tzinfo=timezone.utc),
    )
    assert created['nextRunAt'] == '2020-01-01T07:30:00+00:00'

    connector = FakeGoogleConnector(connected=True)
    provider_calls = []

    async def counting(*args, **kwargs):
        provider_calls.append((args, kwargs))
        return []

    monkeypatch.setattr(connector, 'search_messages', counting)
    monkeypatch.setattr(connector, 'list_events', counting)
    monkeypatch.setattr(agent_routes, 'db', db)
    monkeypatch.setattr(agent_routes, 'agent_runs', runs)
    monkeypatch.setattr(agent_routes, '_google_connector', lambda: connector)
    # _executor keeps its production factory: paused by default.

    result = await agent_routes.process_due_automations()
    assert result['due'] == 1
    assert result['triggered'] == 0
    assert result['errors'] == 1
    assert provider_calls == []
    # The created run was never claimed; it stays queued.
    assert db.tables['agent_runs'][0]['status'] == 'queued'
    assert db.tables['agent_runs'][0]['result_summary'] is None
