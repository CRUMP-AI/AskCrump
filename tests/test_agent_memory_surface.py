import json

import pytest

from backend.agent_executor import AgentExecutor
from backend.agent_registry import require_capability, validate_registry
from backend.agent_run_service import AgentRunService

USER = '11111111-1111-1111-1111-111111111111'
OTHER = '22222222-2222-2222-2222-222222222222'

SECRET_ONE = 'secret-memory-body-one'
SECRET_TWO = 'secret-memory-body-two'

RECORDS = [
    {
        '_user_id': USER,
        'id': 'mem-1',
        'kind': 'preference',
        'content': SECRET_ONE,
        'importance': 5,
        'confidence': 0.9,
        'source_chat_id': 'chat-1',
        'created_at': '2026-11-01T10:00:00+00:00',
        'updated_at': '2026-11-01T10:00:00+00:00',
        'last_used_at': None,
    },
    {
        '_user_id': USER,
        'id': 'mem-2',
        'kind': 'goal',
        'content': SECRET_TWO,
        'importance': 4,
        'confidence': 0.8,
        'source_chat_id': 'chat-2',
        'created_at': '2026-11-02T10:00:00+00:00',
        'updated_at': '2026-11-02T10:00:00+00:00',
        'last_used_at': None,
    },
    {
        '_user_id': OTHER,
        'id': 'mem-other',
        'kind': 'preference',
        'content': 'other-user-secret',
        'importance': 3,
        'confidence': 0.7,
        'source_chat_id': 'chat-3',
        'created_at': '2026-11-03T10:00:00+00:00',
        'updated_at': '2026-11-03T10:00:00+00:00',
        'last_used_at': None,
    },
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


class FakeIntelligenceService:
    """Owner-scoped stand-in for IntelligenceService's memory API.

    Mirrors the real service's contract: ``list_memories`` and
    ``delete_memory`` both take the owner's user id first, and delete
    only succeeds for a memory that belongs to that user.
    """

    def __init__(self, records=None):
        self._records = [dict(r) for r in (RECORDS if records is None else records)]
        self.list_calls: list[tuple] = []
        self.delete_calls: list[tuple] = []

    async def list_memories(self, user_id, *, limit=100):
        self.list_calls.append((user_id, limit))
        rows = [
            r
            for r in self._records
            if r['_user_id'] == user_id and not r.get('_deleted')
        ]
        return [
            {k: v for k, v in r.items() if not k.startswith('_')}
            for r in rows[:limit]
        ]

    async def delete_memory(self, user_id, memory_id):
        self.delete_calls.append((user_id, memory_id))
        for record in self._records:
            if (
                record['_user_id'] == user_id
                and record['id'] == memory_id
                and not record.get('_deleted')
            ):
                record['_deleted'] = True
                return True
        return False


def make_executor():
    db = FakeDB()
    service = AgentRunService(db)
    memory = FakeIntelligenceService()
    # Memory capabilities are live, so run creation stays enforced;
    # dispatch tests opt out of the production execution pause
    # explicitly (covered in tests/test_agent_execution_pause.py).
    executor = AgentExecutor(
        service, intelligence_service=memory, execution_paused=False
    )
    return executor, service, db, memory


def test_memory_capabilities_are_registered_with_honest_risk_and_approval():
    validate_registry()

    listed = require_capability('memory.list')
    assert listed.risk_class == 'read'
    assert listed.approval == 'never'
    assert listed.connector == 'internal'
    assert listed.status == 'live'
    assert listed.credit_cost_kind == 'none'
    assert listed.credit_cost is None
    assert listed.result_card == 'list'

    forget = require_capability('memory.forget')
    assert forget.risk_class == 'write_irreversible'
    assert forget.approval == 'card'
    assert forget.connector == 'internal'
    assert forget.status == 'live'
    assert forget.credit_cost_kind == 'none'
    assert forget.credit_cost is None
    assert forget.input_schema['required'] == ['memoryId']


@pytest.mark.asyncio
async def test_memory_list_succeeds_and_redacts_memory_bodies():
    executor, service, db, memory = make_executor()
    run = await service.create_run(
        user_id=USER, capability_id='memory.list', payload={}
    )
    assert run['status'] == 'queued'

    result = await executor.execute_run(user_id=USER, run_id=run['id'])

    assert result['status'] == 'succeeded'
    assert memory.list_calls == [(USER, 100)]
    summary = json.loads(result['resultSummary'])
    assert summary['kind'] == 'memory.list'
    assert summary['count'] == 2
    assert [item['id'] for item in summary['memories']] == ['mem-1', 'mem-2']
    for item in summary['memories']:
        assert set(item) == {'id', 'kind', 'created_at'}
    # No memory body or other stored field leaks into the summary.
    assert SECRET_ONE not in result['resultSummary']
    assert SECRET_TWO not in result['resultSummary']
    assert 'content' not in result['resultSummary']
    assert 'other-user-secret' not in result['resultSummary']


@pytest.mark.asyncio
async def test_memory_forget_through_approval_flow_deletes_owner_memory():
    executor, service, db, memory = make_executor()
    run = await service.create_run(
        user_id=USER,
        capability_id='memory.forget',
        payload={'memoryId': 'mem-1'},
    )
    assert run['status'] == 'waiting_approval'

    decided = await service.decide_approval(
        user_id=USER,
        action_id=run['pendingAction']['id'],
        decision='approved',
    )
    assert decided['run']['status'] == 'queued'

    # No payload is supplied at execute time: the frozen approved
    # payload on the pending action is the payload of record.
    result = await executor.execute_run(user_id=USER, run_id=run['id'])

    assert result['status'] == 'succeeded'
    assert memory.delete_calls == [(USER, 'mem-1')]
    summary = json.loads(result['resultSummary'])
    assert summary['kind'] == 'memory.forget'
    assert summary['memoryId'] == 'mem-1'
    assert summary['deleted'] is True
    remaining = await memory.list_memories(USER)
    assert [item['id'] for item in remaining] == ['mem-2']


@pytest.mark.asyncio
async def test_memory_forget_missing_memory_fails_with_memory_not_found():
    executor, service, db, memory = make_executor()
    run = await service.create_run(
        user_id=USER,
        capability_id='memory.forget',
        payload={'memoryId': 'mem-missing'},
    )
    await service.decide_approval(
        user_id=USER,
        action_id=run['pendingAction']['id'],
        decision='approved',
    )

    result = await executor.execute_run(user_id=USER, run_id=run['id'])

    assert result['status'] == 'failed'
    summary = json.loads(result['resultSummary'])
    assert summary['error']['code'] == 'MEMORY_NOT_FOUND'
    assert memory.delete_calls == [(USER, 'mem-missing')]


@pytest.mark.asyncio
async def test_memory_forget_cannot_delete_another_users_memory():
    executor, service, db, memory = make_executor()
    run = await service.create_run(
        user_id=USER,
        capability_id='memory.forget',
        payload={'memoryId': 'mem-other'},
    )
    await service.decide_approval(
        user_id=USER,
        action_id=run['pendingAction']['id'],
        decision='approved',
    )

    result = await executor.execute_run(user_id=USER, run_id=run['id'])

    assert result['status'] == 'failed'
    assert json.loads(result['resultSummary'])['error']['code'] == (
        'MEMORY_NOT_FOUND'
    )
    assert memory.delete_calls == [(USER, 'mem-other')]
    other_memories = await memory.list_memories(OTHER)
    assert [item['id'] for item in other_memories] == ['mem-other']
