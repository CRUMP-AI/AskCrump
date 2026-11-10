"""Execution-integrity fixes: fail-closed payload lookup, execution-time
registry status, and atomic fixed-cost reservation.

Three defects, each pinned deterministically:

- when a run has an approved pending action, that action's frozen
  payload is the only payload execution may use — if loading it fails
  or it comes back unusable, execution is refused with
  ``APPROVED_PAYLOAD_UNAVAILABLE`` and no provider is contacted (the
  creation payload is never substituted);
- execution re-checks the capability's current registry status: a
  capability flipped live -> planned after approval refuses
  pre-provider with ``CAPABILITY_NOT_LIVE`` and leaves the run queued;
- a fixed registry cost is reserved atomically before the provider
  call through the existing confirmed-spend credits RPC, so two
  concurrent executions against a balance covering only one cost
  produce exactly one provider call and exactly one debit, and a run
  that fails after the reservation is refunded (charge-on-success).
"""
import asyncio
from dataclasses import replace

import pytest

from backend import agent_registry
from backend.agent_executor import AgentExecutor
from backend.agent_run_service import AgentRunError, AgentRunService
from test_agent_entitlement_cost import (
    FIXED_COST,
    PAID_FIXED_MEMORY_LIST,
    PRO_ACCOUNT,
    CountingIntelligenceService,
    FakeDB,
    seed_account,
)
from test_agent_execution_security import EVENT_A, FakeGoogleConnector

USER = '11111111-1111-1111-1111-111111111111'
PLANNED_FIXED_MEMORY_LIST = replace(PAID_FIXED_MEMORY_LIST, status='planned')


class YieldingFakeDB(FakeDB):
    """FakeDB whose operations yield once, so concurrent callers
    interleave the way production requests do. The credits RPC keeps
    its check-and-deduct inside one lock, mirroring the SQL
    function's advisory lock."""

    async def select(self, table, **kwargs):
        await asyncio.sleep(0)
        return await super().select(table, **kwargs)

    async def update(self, table, payload, **kwargs):
        await asyncio.sleep(0)
        return await super().update(table, payload, **kwargs)

    async def rpc(self, name, params, **kwargs):
        await asyncio.sleep(0)
        return await super().rpc(name, params, **kwargs)


class ActionReadFailingDB(YieldingFakeDB):
    """FakeDB that raises when the pending-actions table is read,
    once armed — the forced approved-action read failure."""

    def __init__(self):
        super().__init__()
        self.fail_action_reads = False

    async def select(self, table, **kwargs):
        if self.fail_action_reads and table == 'agent_pending_actions':
            raise RuntimeError('pending action read failed')
        return await super().select(table, **kwargs)


class FailingIntelligenceService:
    def __init__(self):
        self.list_calls = []

    async def list_memories(self, user_id, *, limit=100):
        self.list_calls.append((user_id, limit))
        raise RuntimeError('provider unavailable')


@pytest.fixture
def mutable_fixed_registry(monkeypatch):
    """Registry seam whose memory.list status tests can flip."""
    state = {'capability': PAID_FIXED_MEMORY_LIST}
    real_get = agent_registry.get_capability

    def patched(capability_id):
        if capability_id == PAID_FIXED_MEMORY_LIST.id:
            return state['capability']
        return real_get(capability_id)

    monkeypatch.setattr('backend.agent_run_service.get_capability', patched)
    return state


def make_paid_executor(db, memory=None):
    service = AgentRunService(db)
    memory = memory or CountingIntelligenceService()
    executor = AgentExecutor(
        service,
        google_connector=FakeGoogleConnector(),
        intelligence_service=memory,
        execution_paused=False,
    )
    return executor, service, memory


# -- defect 1: payload lookup fails closed ------------------------------------


async def _approved_calendar_run(service):
    run = await service.create_run(
        user_id=USER, capability_id='calendar.create', payload=dict(EVENT_A)
    )
    await service.decide_approval(
        user_id=USER,
        action_id=run['pendingAction']['id'],
        decision='approved',
    )
    return run


@pytest.mark.asyncio
async def test_approved_payload_read_failure_refuses_execution():
    db = ActionReadFailingDB()
    service = AgentRunService(
        db, enforce_capability_status=False, enforce_access=False
    )
    connector = FakeGoogleConnector()
    executor = AgentExecutor(
        service, google_connector=connector, execution_paused=False
    )
    run = await _approved_calendar_run(service)
    db.fail_action_reads = True
    result = await executor.execute_run(user_id=USER, run_id=run['id'])
    assert result['status'] == 'failed'
    stored = db.tables['agent_runs'][0]
    assert stored['status'] == 'failed'
    assert 'APPROVED_PAYLOAD_UNAVAILABLE' in (stored['result_summary'] or '')
    # Zero provider contact: the creation payload was NOT substituted.
    assert connector.created_events == []


@pytest.mark.asyncio
async def test_approved_payload_missing_refuses_execution():
    db = YieldingFakeDB()
    service = AgentRunService(
        db, enforce_capability_status=False, enforce_access=False
    )
    connector = FakeGoogleConnector()
    executor = AgentExecutor(
        service, google_connector=connector, execution_paused=False
    )
    run = await _approved_calendar_run(service)
    # The approved action's frozen payload is gone/unusable.
    db.tables['agent_pending_actions'][0]['exact_payload'] = None
    result = await executor.execute_run(user_id=USER, run_id=run['id'])
    assert result['status'] == 'failed'
    stored = db.tables['agent_runs'][0]
    assert 'APPROVED_PAYLOAD_UNAVAILABLE' in (stored['result_summary'] or '')
    assert connector.created_events == []


# -- defect 2: execution-time registry status re-check -------------------------


@pytest.mark.asyncio
async def test_status_flip_after_creation_refuses_pre_provider(
    mutable_fixed_registry,
):
    db = YieldingFakeDB()
    seed_account(db, PRO_ACCOUNT, balance=100)
    executor, service, memory = make_paid_executor(db)
    run = await service.create_run(
        user_id=USER, capability_id='memory.list', payload={}
    )
    assert run['status'] == 'queued'
    # The capability is flipped away from live after creation.
    mutable_fixed_registry['capability'] = PLANNED_FIXED_MEMORY_LIST
    with pytest.raises(AgentRunError) as excinfo:
        await executor.execute_run(user_id=USER, run_id=run['id'])
    assert excinfo.value.code == 'CAPABILITY_NOT_LIVE'
    assert excinfo.value.status_code == 409
    assert memory.list_calls == []
    # Consistent with the execute-time entitlement rejection: the run
    # is left queued, and nothing was reserved.
    assert db.tables['agent_runs'][0]['status'] == 'queued'
    assert db.tables['credit_ledger'] == []
    assert db.tables['credit_accounts'][0]['balance'] == 100


# -- defect 3: atomic fixed-cost reservation -----------------------------------


@pytest.mark.asyncio
async def test_concurrent_executions_debit_exactly_once(
    mutable_fixed_registry,
):
    db = YieldingFakeDB()
    # Balance covers exactly one run.
    seed_account(db, PRO_ACCOUNT, balance=FIXED_COST)
    executor, service, memory = make_paid_executor(db)
    first = await service.create_run(
        user_id=USER, capability_id='memory.list', payload={}
    )
    second = await service.create_run(
        user_id=USER, capability_id='memory.list', payload={}
    )
    results = await asyncio.gather(
        executor.execute_run(user_id=USER, run_id=first['id']),
        executor.execute_run(user_id=USER, run_id=second['id']),
        return_exceptions=True,
    )
    successes = [r for r in results if isinstance(r, dict)]
    failures = [r for r in results if isinstance(r, AgentRunError)]
    assert len(successes) == 1
    assert successes[0]['status'] == 'succeeded'
    assert len(failures) == 1
    assert failures[0].code == 'INSUFFICIENT_CREDITS'
    assert failures[0].status_code == 402
    # Exactly one provider contact, exactly one debit of the exact
    # cost, and the balance is fully spent — not overspent.
    assert len(memory.list_calls) == 1
    debits = [e for e in db.tables['credit_ledger'] if e['delta'] < 0]
    assert len(debits) == 1
    assert debits[0]['delta'] == -FIXED_COST
    assert db.tables['credit_accounts'][0]['balance'] == 0


@pytest.mark.asyncio
async def test_provider_failure_after_reservation_refunds(
    mutable_fixed_registry,
):
    db = YieldingFakeDB()
    seed_account(db, PRO_ACCOUNT, balance=100)
    failing = FailingIntelligenceService()
    executor, service, _memory = make_paid_executor(db, memory=failing)
    run = await service.create_run(
        user_id=USER, capability_id='memory.list', payload={}
    )
    result = await executor.execute_run(user_id=USER, run_id=run['id'])
    assert result['status'] == 'failed'
    assert failing.list_calls == [(USER, 100)]
    # Charge-on-success: the reservation was released, restoring the
    # balance, with the debit and its refund both on the ledger.
    account = db.tables['credit_accounts'][0]
    assert account['balance'] == 100
    assert account['lifetime_spent'] == 0
    debits = [e for e in db.tables['credit_ledger'] if e['delta'] < 0]
    refunds = [
        e for e in db.tables['credit_ledger'] if e['reason'] == 'refund'
    ]
    assert len(debits) == 1
    assert debits[0]['delta'] == -FIXED_COST
    assert len(refunds) == 1
    assert refunds[0]['related_ledger_id'] == debits[0]['id']
