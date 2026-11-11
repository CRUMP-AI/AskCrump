"""Credit debit/refund durability: a reservation must never strand.

Fix B reserved a run's fixed cost atomically before execution and
released it on the failure paths the executor handles — but the
money was not durable across the paths it does not:

- the reservation was taken BEFORE the execution claim, so a run
  cancelled between load and claim was debited and then refused by
  the claim, stranding the debit with no owner;
- a crash (BaseException) after the reservation left the run stuck
  in ``running`` with the debit standing and nothing that could
  find it again;
- a failed refund was swallowed silently, stranding the debit with
  no record that a release was still owed.

The reservation's lifecycle is now recorded in the run's own step
ledger the moment it happens (``run.credits_reserved`` /
``run.credits_released``), the claim is taken before any money
moves, and ``reconcile_run_credits`` settles a terminal
non-success run's reserved-but-unreleased debit through the same
idempotent refund RPC — wired into cancellation (the recovery
path for a stuck run) and into a bounded terminal sweep on the
run-due lane. A succeeded run's reservation is its charge and is
never refunded.
"""
import pytest

from backend import agent_registry
from backend.agent_executor import AgentExecutor
from backend.agent_run_service import (
    AgentRunConflictError,
    AgentRunService,
)
from test_agent_entitlement_cost import (
    FIXED_COST,
    PAID_FIXED_MEMORY_LIST,
    PRO_ACCOUNT,
    CountingIntelligenceService,
    seed_account,
)
from test_agent_execution_integrity import (
    FailingIntelligenceService,
    YieldingFakeDB,
)
from test_agent_execution_security import FakeGoogleConnector

USER = '11111111-1111-1111-1111-111111111111'


class SimulatedCrash(BaseException):
    """Process death, not a handled failure: BaseException on purpose."""


class CrashingIntelligenceService:
    def __init__(self):
        self.list_calls = []

    async def list_memories(self, user_id, *, limit=100):
        self.list_calls.append((user_id, limit))
        raise SimulatedCrash()


class FlakyRefundDB(YieldingFakeDB):
    """YieldingFakeDB whose refund RPC fails a set number of times
    before recovering — the transient refund outage."""

    def __init__(self, refund_failures=0):
        super().__init__()
        self.refund_failures = refund_failures

    async def rpc(self, name, params, **kwargs):
        if name == 'refund_credit_spend' and self.refund_failures > 0:
            self.refund_failures -= 1
            raise RuntimeError('refund unavailable')
        return await super().rpc(name, params, **kwargs)


@pytest.fixture
def fixed_registry(monkeypatch):
    real_get = agent_registry.get_capability

    def patched(capability_id):
        if capability_id == PAID_FIXED_MEMORY_LIST.id:
            return PAID_FIXED_MEMORY_LIST
        return real_get(capability_id)

    monkeypatch.setattr('backend.agent_run_service.get_capability', patched)


def make_executor(db, memory):
    service = AgentRunService(db)
    executor = AgentExecutor(
        service,
        google_connector=FakeGoogleConnector(),
        intelligence_service=memory,
        execution_paused=False,
    )
    return executor, service


def debits(db):
    return [e for e in db.tables['credit_ledger'] if e['delta'] < 0]


def refunds(db):
    return [e for e in db.tables['credit_ledger'] if e['reason'] == 'refund']


def balance(db):
    return db.tables['credit_accounts'][0]['balance']


def credit_steps(db, step_type):
    return [
        s for s in db.tables['agent_run_steps'] if s['step_type'] == step_type
    ]


# -- boundary 1: cancel lands between load and claim ---------------------------


@pytest.mark.asyncio
async def test_cancelled_before_claim_never_debits(fixed_registry):
    db = YieldingFakeDB()
    seed_account(db, PRO_ACCOUNT, balance=100)
    executor, service = make_executor(db, CountingIntelligenceService())
    created = await service.create_run(
        user_id=USER, capability_id='memory.list', payload={}
    )
    # A worker loaded the run row while it was queued; the user
    # cancelled it before the worker got to execute.
    stale_loaded_run = dict(db.tables['agent_runs'][0])
    assert stale_loaded_run['status'] == 'queued'
    await service.cancel_run(user_id=USER, run_id=created['id'])
    with pytest.raises(AgentRunConflictError):
        await executor.execute_run_record(stale_loaded_run)
    # The claim refused before any money moved: no debit exists to
    # strand, and the balance is untouched.
    assert db.tables['credit_ledger'] == []
    assert balance(db) == 100
    assert db.tables['agent_runs'][0]['status'] == 'cancelled'


# -- boundary 2: crash after the reservation ------------------------------------


@pytest.mark.asyncio
async def test_crash_after_reservation_is_recovered_by_cancel(fixed_registry):
    db = YieldingFakeDB()
    seed_account(db, PRO_ACCOUNT, balance=100)
    crashing = CrashingIntelligenceService()
    executor, service = make_executor(db, crashing)
    created = await service.create_run(
        user_id=USER, capability_id='memory.list', payload={}
    )
    with pytest.raises(SimulatedCrash):
        await executor.execute_run(user_id=USER, run_id=created['id'])
    # The crash leaves the run stuck in running with the debit
    # standing — and the reservation recorded on the run's ledger.
    assert db.tables['agent_runs'][0]['status'] == 'running'
    assert len(debits(db)) == 1
    assert refunds(db) == []
    assert balance(db) == 100 - FIXED_COST
    assert len(credit_steps(db, 'run.credits_reserved')) == 1
    # Cancelling the stuck run is the recovery path: the stranded
    # debit is refunded exactly once and the release is recorded.
    cancelled = await service.cancel_run(user_id=USER, run_id=created['id'])
    assert cancelled['status'] == 'cancelled'
    assert balance(db) == 100
    assert len(refunds(db)) == 1
    assert refunds(db)[0]['related_ledger_id'] == debits(db)[0]['id']
    assert len(credit_steps(db, 'run.credits_released')) == 1


# -- boundary 3: the refund itself fails -----------------------------------------


@pytest.mark.asyncio
async def test_failed_refund_leaves_residue_reconciled_exactly_once(
    fixed_registry,
):
    db = FlakyRefundDB(refund_failures=1)
    seed_account(db, PRO_ACCOUNT, balance=100)
    executor, service = make_executor(db, FailingIntelligenceService())
    created = await service.create_run(
        user_id=USER, capability_id='memory.list', payload={}
    )
    result = await executor.execute_run(user_id=USER, run_id=created['id'])
    # The run failed and its inline release was attempted, but the
    # refund RPC was down: the debit stands, visibly — a reserved
    # step with no release step.
    assert result['status'] == 'failed'
    assert balance(db) == 100 - FIXED_COST
    assert refunds(db) == []
    assert len(credit_steps(db, 'run.credits_reserved')) == 1
    assert credit_steps(db, 'run.credits_released') == []
    # Reconciliation settles it through the idempotent refund, once.
    stored = db.tables['agent_runs'][0]
    assert await service.reconcile_run_credits(stored) is True
    assert balance(db) == 100
    assert len(refunds(db)) == 1
    assert refunds(db)[0]['related_ledger_id'] == debits(db)[0]['id']
    # A second pass is a no-op: the release is on record.
    assert await service.reconcile_run_credits(stored) is False
    assert len(refunds(db)) == 1
    assert balance(db) == 100


@pytest.mark.asyncio
async def test_terminal_sweep_recovers_stranded_reservations(fixed_registry):
    db = FlakyRefundDB(refund_failures=1)
    seed_account(db, PRO_ACCOUNT, balance=100)
    executor, service = make_executor(db, FailingIntelligenceService())
    created = await service.create_run(
        user_id=USER, capability_id='memory.list', payload={}
    )
    await executor.execute_run(user_id=USER, run_id=created['id'])
    assert balance(db) == 100 - FIXED_COST
    # The bounded sweep the run-due lane runs settles the residue
    # without anyone opening the run.
    assert await service.reconcile_terminal_run_credits() == 1
    assert balance(db) == 100
    assert len(refunds(db)) == 1
    assert await service.reconcile_terminal_run_credits() == 0


# -- guards ------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_succeeded_run_is_never_refunded(fixed_registry):
    db = YieldingFakeDB()
    seed_account(db, PRO_ACCOUNT, balance=100)
    executor, service = make_executor(db, CountingIntelligenceService())
    created = await service.create_run(
        user_id=USER, capability_id='memory.list', payload={}
    )
    result = await executor.execute_run(user_id=USER, run_id=created['id'])
    assert result['status'] == 'succeeded'
    assert balance(db) == 100 - FIXED_COST
    # A succeeded run's reservation is the charge, not a stranding:
    # reconciliation leaves it exactly as it is.
    stored = db.tables['agent_runs'][0]
    assert await service.reconcile_run_credits(stored) is False
    assert balance(db) == 100 - FIXED_COST
    assert refunds(db) == []


@pytest.mark.asyncio
async def test_inline_release_settles_reservation_no_double_refund(
    fixed_registry,
):
    db = YieldingFakeDB()
    seed_account(db, PRO_ACCOUNT, balance=100)
    executor, service = make_executor(db, FailingIntelligenceService())
    created = await service.create_run(
        user_id=USER, capability_id='memory.list', payload={}
    )
    result = await executor.execute_run(user_id=USER, run_id=created['id'])
    assert result['status'] == 'failed'
    # The healthy inline release already refunded and recorded the
    # release; reconciliation finds nothing left to do.
    assert balance(db) == 100
    assert len(refunds(db)) == 1
    assert len(credit_steps(db, 'run.credits_reserved')) == 1
    assert len(credit_steps(db, 'run.credits_released')) == 1
    stored = db.tables['agent_runs'][0]
    assert await service.reconcile_run_credits(stored) is False
    assert len(refunds(db)) == 1
