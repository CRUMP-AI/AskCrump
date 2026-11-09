"""Emergency execution pause.

Two verified criticals are open against the agent executor: the
``POST /api/agent/runs/{run_id}/execute`` route accepted caller input
that could substitute the approved payload, and the browser fetch
validates one DNS resolution while connecting by hostname on a second
one (rebinding/TOCTOU). Until the payload-of-record/CAS execution fix
and the pinned-fetch fix land, the vulnerable surface fails closed:

- the execute route returns 503 ``AGENT_EXECUTION_PAUSED`` and never
  reaches the executor;
- ``browser.read`` is ``planned`` in the registry, and the executor's
  browser adapter fails the run with ``AGENT_EXECUTION_PAUSED`` before
  any page fetch happens.
"""
import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import app as app_module
from backend import agent_registry
from backend.agent_executor import AgentExecutor
from backend.agent_run_service import AgentRunService
from backend.routes import agent as agent_routes
from test_agent_executor_adapters import FakeDB, USER

CLIENT = TestClient(app_module.app)


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
        '/api/agent/runs/22222222-2222-2222-2222-222222222222/execute',
        json={'input': {'url': 'https://example.com/substituted'}},
    )
    assert response.status_code == 503
    body = response.json()
    assert body['success'] is False
    assert body['code'] == 'AGENT_EXECUTION_PAUSED'
    assert paused_route.calls == []


def test_browser_read_is_planned_in_the_registry():
    capability = agent_registry.require_capability('browser.read')
    assert capability.status == 'planned'
    catalog = {item['id']: item for item in agent_registry.public_catalog()['capabilities']}
    assert catalog['browser.read']['status'] == 'planned'


@pytest.mark.asyncio
async def test_browser_read_run_fails_closed_before_any_fetch(monkeypatch):
    db = FakeDB()
    service = AgentRunService(db)
    executor = AgentExecutor(service, google_connector=object())
    fetches = []

    async def recording_fetch(capability_id, user_id, payload):
        fetches.append((capability_id, payload))
        return {}

    monkeypatch.setattr(
        'backend.agent_executor.browser_agent.execute', recording_fetch
    )
    run = await service.create_run(
        user_id=USER,
        capability_id='browser.read',
        payload={'url': 'http://169.254.169.254/latest/meta-data/'},
    )
    result = await executor.execute_run(user_id=USER, run_id=run['id'])
    assert result['status'] == 'failed'
    assert (
        json.loads(result['resultSummary'])['error']['code']
        == 'AGENT_EXECUTION_PAUSED'
    )
    assert fetches == []
