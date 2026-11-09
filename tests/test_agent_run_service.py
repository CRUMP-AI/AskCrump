from pathlib import Path

import pytest

from app import app
from backend.agent_run_service import (
    AgentRunConflictError,
    AgentRunError,
    AgentRunService,
)
from conftest import iter_effective_routes

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = (ROOT / 'migrations' / '20261109090000_agent_run_ledger.sql').read_text()

USER = '11111111-1111-1111-1111-111111111111'
OTHER = '22222222-2222-2222-2222-222222222222'


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


def make_service():
    db = FakeDB()
    return AgentRunService(db), db


@pytest.mark.asyncio
async def test_read_capability_run_queues_without_approval():
    service, db = make_service()
    run = await service.create_run(
        user_id=USER,
        capability_id='gmail.search',
        payload={'query': 'invoice'},
    )
    assert run['status'] == 'queued'
    assert 'pendingAction' not in run
    assert [s['step_type'] for s in db.tables['agent_run_steps']] == [
        'run.created',
        'run.queued',
    ]
    # The ledger stores a redacted summary, never the raw query text.
    assert run['inputSummary']['query'] == {'type': 'string', 'length': 7}


@pytest.mark.asyncio
async def test_write_capability_run_waits_for_approval_with_exact_payload():
    service, db = make_service()
    payload = {
        'summary': 'Dentist',
        'start': '2026-11-10T09:00:00-05:00',
        'end': '2026-11-10T10:00:00-05:00',
    }
    run = await service.create_run(
        user_id=USER, capability_id='calendar.create', payload=payload
    )
    assert run['status'] == 'waiting_approval'
    action = run['pendingAction']
    assert action['payload'] == payload
    approvals = await service.list_approvals(user_id=USER)
    assert [item['id'] for item in approvals] == [action['id']]


@pytest.mark.asyncio
async def test_approve_moves_run_to_queued_and_freezes_edited_payload():
    service, db = make_service()
    payload = {
        'summary': 'Dentist',
        'start': '2026-11-10T09:00:00-05:00',
        'end': '2026-11-10T10:00:00-05:00',
    }
    run = await service.create_run(
        user_id=USER, capability_id='calendar.create', payload=payload
    )
    action_id = run['pendingAction']['id']
    edited = {**payload, 'summary': 'Dentist (cleaning)'}
    result = await service.decide_approval(
        user_id=USER,
        action_id=action_id,
        decision='approved',
        edited_payload=edited,
    )
    assert result['action']['status'] == 'approved'
    assert result['action']['payload'] == edited
    assert result['run']['status'] == 'queued'
    with pytest.raises(AgentRunConflictError):
        await service.decide_approval(
            user_id=USER, action_id=action_id, decision='approved'
        )


@pytest.mark.asyncio
async def test_deny_cancels_the_run():
    service, db = make_service()
    run = await service.create_run(
        user_id=USER,
        capability_id='gmail.send',
        payload={'to': 'a@example.com', 'subject': 'Hi', 'body': 'Hello'},
    )
    result = await service.decide_approval(
        user_id=USER,
        action_id=run['pendingAction']['id'],
        decision='denied',
    )
    assert result['run']['status'] == 'cancelled'
    assert await service.list_approvals(user_id=USER) == []


@pytest.mark.asyncio
async def test_unknown_capability_and_missing_input_fail_closed():
    service, db = make_service()
    with pytest.raises(AgentRunError) as unknown:
        await service.create_run(
            user_id=USER, capability_id='gmail.delete_everything', payload={}
        )
    assert unknown.value.code == 'CAPABILITY_NOT_FOUND'
    with pytest.raises(AgentRunError) as invalid:
        await service.create_run(
            user_id=USER, capability_id='calendar.create', payload={'summary': 'x'}
        )
    assert invalid.value.code == 'INVALID_RUN_INPUT'
    assert db.tables['agent_runs'] == []


@pytest.mark.asyncio
async def test_runs_are_owner_isolated_and_cancellable():
    service, db = make_service()
    run = await service.create_run(
        user_id=USER, capability_id='agent.today_brief', payload={}
    )
    assert await service.list_runs(user_id=OTHER) == []
    with pytest.raises(AgentRunError):
        await service.get_run(user_id=OTHER, run_id=run['id'])
    detail = await service.get_run(user_id=USER, run_id=run['id'])
    assert detail['steps'][0]['type'] == 'run.created'
    cancelled = await service.cancel_run(user_id=USER, run_id=run['id'])
    assert cancelled['status'] == 'cancelled'
    with pytest.raises(AgentRunConflictError):
        await service.cancel_run(user_id=USER, run_id=run['id'])


def test_ledger_migration_declares_tables_statuses_and_rls():
    normalized = MIGRATION.lower()
    for table in ('agent_runs', 'agent_run_steps', 'agent_pending_actions'):
        assert f'create table if not exists public.{table}' in normalized
        assert f'alter table public.{table} enable row level security' in normalized
        assert f'revoke all privileges on public.{table} from anon, authenticated' in normalized
    for status in ('waiting_approval', 'succeeded', 'failed', 'cancelled'):
        assert f"'{status}'" in normalized
    assert "'approval.requested'" in normalized
    assert "'approval.decided'" in normalized


def test_agent_run_routes_are_registered():
    actual = {
        (method, route.path)
        for route in iter_effective_routes(app)
        for method in getattr(route, 'methods', set())
        if method not in {'HEAD', 'OPTIONS'}
    }
    assert ('POST', '/api/agent/runs') in actual
    assert ('GET', '/api/agent/runs') in actual
    assert ('GET', '/api/agent/runs/{run_id}') in actual
    assert ('POST', '/api/agent/runs/{run_id}/cancel') in actual
    assert ('GET', '/api/agent/approvals') in actual
    assert ('POST', '/api/agent/approvals/{action_id}/decision') in actual
