import json

import pytest

from backend import agent_registry
from backend.agent_executor import AgentExecutor
from backend.agent_run_service import AgentRunService
from backend.google_connector import InsufficientScopeError

USER = '11111111-1111-1111-1111-111111111111'


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


def make_executor():
    db = FakeDB()
    # Adapter tests set up runs for capabilities that are not live yet
    # and exercise dispatch while production execution is paused; both
    # fail-closed defaults are opted out here explicitly and covered in
    # tests/test_agent_execution_pause.py. The browser test below still
    # proves the adapter-level gate, which sits behind the executor's.
    service = AgentRunService(
        db, enforce_capability_status=False, enforce_access=False
    )
    executor = AgentExecutor(
        service, google_connector=object(), execution_paused=False
    )
    return executor, service, db


@pytest.mark.asyncio
async def test_browser_read_dispatch_is_paused_and_never_fetches(monkeypatch):
    # Emergency pause: the executor's browser adapter fails closed with
    # AGENT_EXECUTION_PAUSED and the page fetch is never invoked. The
    # success/error dispatch behavior returns with the pinned-fetch fix;
    # it stays covered at module level in tests/test_browser_agent.py.
    executor, service, db = make_executor()
    calls = []

    async def fake_browser_execute(capability_id, user_id, payload):
        calls.append((capability_id, user_id, payload))
        return {}

    monkeypatch.setattr(
        'backend.agent_executor.browser_agent.execute', fake_browser_execute
    )
    run = await service.create_run(
        user_id=USER,
        capability_id='browser.read',
        payload={'url': 'https://example.com/story'},
    )
    result = await executor.execute_run(user_id=USER, run_id=run['id'])
    assert result['status'] == 'failed'
    assert (
        json.loads(result['resultSummary'])['error']['code']
        == 'AGENT_EXECUTION_PAUSED'
    )
    assert calls == []


@pytest.mark.asyncio
async def test_gmail_send_dispatch_maps_scope_errors(monkeypatch):
    executor, service, db = make_executor()

    async def scope_execute(capability_id, user_id, payload, *, connector=None):
        raise InsufficientScopeError()

    monkeypatch.setattr(
        'backend.agent_executor.agent_gmail_write.execute', scope_execute
    )
    run = await service.create_run(
        user_id=USER,
        capability_id='gmail.send',
        payload={'to': 'a@example.com', 'subject': 'Hi', 'body': 'Hello'},
    )
    decided = await service.decide_approval(
        user_id=USER,
        action_id=run['pendingAction']['id'],
        decision='approved',
    )
    assert decided['run']['status'] == 'queued'
    result = await executor.execute_run(user_id=USER, run_id=run['id'])
    assert result['status'] == 'failed'
    assert (
        json.loads(result['resultSummary'])['error']['code'] == 'INSUFFICIENT_SCOPE'
    )


def test_browser_read_is_paused_and_gmail_write_stays_planned():
    # browser.read is paused (planned) until the pinned-fetch fix lands:
    # the current fetch validates one DNS resolution and connects by
    # hostname on a second one. Gmail write stays planned until a
    # write-scope connect flow exists, even though dispatch is wired.
    assert agent_registry.require_capability('browser.read').status == 'planned'
    assert agent_registry.require_capability('gmail.draft').status == 'planned'
    assert agent_registry.require_capability('gmail.send').status == 'planned'
