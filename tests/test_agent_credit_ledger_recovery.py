"""Credit recovery when the reservation record itself is missing.

The step-ledger reconciliation shipped with the credit durability
fix discovers a stranded debit only from the run's own
``run.credits_reserved`` step — but the executor commits the debit
first and records that step second. A crash (or a failed step
insert) in between leaves a real debit with no step to discover it
from, on a run stuck in ``running`` that the terminal-only sweep
never looks at; and the sweep itself reads only the newest 50
terminal rows, so older residue hides behind newer runs forever.

Recovery is now keyed on the credits ledger itself: a run's spend
is filed under the deterministic action key
``agent-run:<run id>:<capability id>``, so reconciliation finds the
debit whether or not the step landed, settles stale ``running``
residue (a claim whose owner died with the process), and pages
through every stranded run instead of the newest 50. A fresh
``running`` run is never touched — its executor may still be
working — and a succeeded run's spend is its charge, step or no
step.
"""
from datetime import datetime, timedelta, timezone

import pytest

from backend import agent_registry
from backend.agent_executor import AgentExecutor
from backend.agent_run_service import AgentRunService
from test_agent_entitlement_cost import (
    FIXED_COST,
    PAID_FIXED_MEMORY_LIST,
    PRO_ACCOUNT,
    CountingIntelligenceService,
    seed_account,
)
from test_agent_execution_integrity import YieldingFakeDB
from test_agent_execution_security import FakeGoogleConnector

USER = '11111111-1111-1111-1111-111111111111'


class SimulatedCrash(BaseException):
    """Process death, not a handled failure: BaseException on purpose."""


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


async def crash_after_debit_commit(monkeypatch, db, service):
    """Execute a run whose reservation-step insert dies immediately
    after the debit commits — the gap in the executor's reserve path.
    Returns the created run's public shape."""
    created = await service.create_run(
        user_id=USER, capability_id='memory.list', payload={}
    )

    async def dying_record(run, ledger_id):
        raise SimulatedCrash()

    monkeypatch.setattr(service, 'record_credit_reservation', dying_record)
    executor = AgentExecutor(
        service,
        google_connector=FakeGoogleConnector(),
        intelligence_service=CountingIntelligenceService(),
        execution_paused=False,
    )
    with pytest.raises(SimulatedCrash):
        await executor.execute_run(user_id=USER, run_id=created['id'])
    return created


# -- the gap: debit committed, reservation step never landed -------------------


@pytest.mark.asyncio
async def test_crash_after_debit_commit_is_recovered_from_the_ledger(
    fixed_registry, monkeypatch
):
    db = YieldingFakeDB()
    seed_account(db, PRO_ACCOUNT, balance=100)
    service = AgentRunService(db)
    created = await crash_after_debit_commit(monkeypatch, db, service)

    stored = db.tables['agent_runs'][0]
    # The debit is real and stands; the reservation step never
    # landed, and the run is stuck in running.
    assert stored['status'] == 'running'
    assert len(debits(db)) == 1
    assert credit_steps(db, 'run.credits_reserved') == []
    assert balance(db) == 100 - FIXED_COST

    # A fresh running run is never reconciled: its executor may
    # still be working, so the stranded-looking debit is left alone
    # while the claim is young.
    assert await service.reconcile_run_credits(stored) is False
    assert refunds(db) == []
    assert db.tables['agent_runs'][0]['status'] == 'running'

    # Once the claim is stale (its stamp rewritten into the past,
    # the pattern the lifecycle suite uses to simulate time
    # passing), reconciliation recovers the debit from the ledger
    # itself — no step was ever written to find it by — exactly once.
    stored['updated_at'] = (
        datetime.now(timezone.utc) - timedelta(minutes=20)
    ).isoformat()
    assert await service.reconcile_run_credits(stored) is True
    assert db.tables['agent_runs'][0]['status'] == 'failed'
    assert balance(db) == 100
    assert len(refunds(db)) == 1
    assert refunds(db)[0]['related_ledger_id'] == debits(db)[0]['id']
    assert len(credit_steps(db, 'run.credits_released')) == 1
    assert await service.reconcile_run_credits(
        db.tables['agent_runs'][0]
    ) is False
    assert len(refunds(db)) == 1
    assert balance(db) == 100
    assert created['id'] == stored['id']


@pytest.mark.asyncio
async def test_cancel_recovers_a_debit_whose_step_never_landed(
    fixed_registry, monkeypatch
):
    db = YieldingFakeDB()
    seed_account(db, PRO_ACCOUNT, balance=100)
    service = AgentRunService(db)
    created = await crash_after_debit_commit(monkeypatch, db, service)
    assert credit_steps(db, 'run.credits_reserved') == []
    assert balance(db) == 100 - FIXED_COST

    # Cancelling the stuck run is a recovery path: its reconciliation
    # must find the debit in the ledger even though the run's step
    # ledger holds no reservation to discover it from.
    cancelled = await service.cancel_run(user_id=USER, run_id=created['id'])
    assert cancelled['status'] == 'cancelled'
    assert balance(db) == 100
    assert len(refunds(db)) == 1
    assert refunds(db)[0]['related_ledger_id'] == debits(db)[0]['id']


@pytest.mark.asyncio
async def test_stale_running_residue_is_recovered_by_the_sweep(
    fixed_registry, monkeypatch
):
    db = YieldingFakeDB()
    seed_account(db, PRO_ACCOUNT, balance=100)
    service = AgentRunService(db)
    await crash_after_debit_commit(monkeypatch, db, service)
    stored = db.tables['agent_runs'][0]
    assert stored['status'] == 'running'
    # The run-due lane's sweep leaves the fresh claim alone...
    assert await service.reconcile_terminal_run_credits() == 0
    assert balance(db) == 100 - FIXED_COST
    # ...and settles it once the claim is stale (its stamp rewritten
    # into the past, the pattern the lifecycle suite uses to
    # simulate time passing).
    stored['updated_at'] = (
        datetime.now(timezone.utc) - timedelta(minutes=20)
    ).isoformat()
    assert await service.reconcile_terminal_run_credits() == 1
    assert db.tables['agent_runs'][0]['status'] == 'failed'
    assert balance(db) == 100
    assert len(refunds(db)) == 1
    assert await service.reconcile_terminal_run_credits() == 0


# -- the sweep horizon: every stranded run, not the newest 50 -------------------


@pytest.mark.asyncio
async def test_sweep_recovers_more_than_fifty_stranded_runs(fixed_registry):
    db = YieldingFakeDB()
    total = 60
    seed_account(db, PRO_ACCOUNT, balance=total * FIXED_COST)
    service = AgentRunService(db)
    stamp = '2026-11-01T00:00:00+00:00'
    for _ in range(total):
        created = await service.create_run(
            user_id=USER, capability_id='memory.list', payload={}
        )
        run = next(
            r for r in db.tables['agent_runs'] if r['id'] == created['id']
        )
        ledger_id = await service.reserve_run_credits(run)
        assert ledger_id
        await service.record_credit_reservation(run, ledger_id)
        # Every run failed with its release never landing, and all
        # sixty share one updated_at stamp: the sweep's paging must
        # walk the tie completely instead of stopping at a page of
        # look-alike rows.
        run['status'] = 'failed'
        run['updated_at'] = stamp
    assert balance(db) == 0
    assert len(debits(db)) == total

    assert await service.reconcile_terminal_run_credits() == total
    assert balance(db) == total * FIXED_COST
    assert len(refunds(db)) == total
    assert len({r['related_ledger_id'] for r in refunds(db)}) == total
    assert await service.reconcile_terminal_run_credits() == 0


# -- guards ------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_succeeded_run_spend_is_never_recovered(fixed_registry):
    db = YieldingFakeDB()
    seed_account(db, PRO_ACCOUNT, balance=100)
    executor, service = make_executor(db, CountingIntelligenceService())
    created = await service.create_run(
        user_id=USER, capability_id='memory.list', payload={}
    )
    result = await executor.execute_run(user_id=USER, run_id=created['id'])
    assert result['status'] == 'succeeded'
    # Even with the reservation steps deleted, ledger discovery must
    # not turn a succeeded run's charge into a refund.
    db.tables['agent_run_steps'] = [
        s
        for s in db.tables['agent_run_steps']
        if s['step_type'] not in {'run.credits_reserved', 'run.credits_released'}
    ]
    stored = db.tables['agent_runs'][0]
    assert await service.reconcile_run_credits(stored) is False
    assert await service.reconcile_terminal_run_credits() == 0
    assert balance(db) == 100 - FIXED_COST
    assert refunds(db) == []
