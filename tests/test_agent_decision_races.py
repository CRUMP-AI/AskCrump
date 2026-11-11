"""Cancel-versus-decision races: exactly one outcome wins.

``decide_approval`` claims its decision with a compare-and-swap on
the pending action, but ``cancel_run`` did not play by the same
discipline: it rewrote the run's pending actions with an
unconditional update (no status filter) and set the run cancelled
with an unconditional status write, and the deny path of
``decide_approval`` set the run cancelled unconditionally too. Two
decisions racing on the same run could therefore both be told they
succeeded while overwriting each other — an approval that landed
(and queued the run) silently rewritten to cancelled by a cancel
that started earlier, or a denial overwritten the same way.

Every decision path now claims the action with the same
status='pending' compare-and-swap and moves the run with a
compare-and-swap on the status it observed. Exactly one terminal
outcome wins; the loser gets ``AgentRunConflictError`` with no side
effects. The interleavings below are deterministic: a gated fake
holds one decision's write at an exact point until the other
decision has completed, never a sleep.
"""
import asyncio

import pytest

from backend.agent_run_service import (
    AgentRunConflictError,
    AgentRunService,
)
from test_agent_execution_security import EVENT_A, FakeDB

USER = '11111111-1111-1111-1111-111111111111'


class DecisionGateDB(FakeDB):
    """FakeDB that holds the first update matching an armed
    (table, status) pair until the test releases it, so a second
    decision can run to completion at an exact point inside the
    first — a deterministic interleaving, not a timing race."""

    def __init__(self):
        super().__init__()
        self._gate_key = None
        self._gate_consumed = False
        self.gate_reached = asyncio.Event()
        self.gate_release = asyncio.Event()

    def arm(self, table, status):
        self._gate_key = (table, status)

    async def update(self, table, payload, **kwargs):
        if (
            not self._gate_consumed
            and self._gate_key is not None
            and table == self._gate_key[0]
            and payload.get('status') == self._gate_key[1]
        ):
            self._gate_consumed = True
            self.gate_reached.set()
            await self.gate_release.wait()
        return await super().update(table, payload, **kwargs)


def make_service(db):
    return AgentRunService(
        db, enforce_capability_status=False, enforce_access=False
    )


async def _gated_run(service):
    run = await service.create_run(
        user_id=USER, capability_id='calendar.create', payload=dict(EVENT_A)
    )
    assert run['status'] == 'waiting_approval'
    return run


def stored_action(db):
    return db.tables['agent_pending_actions'][0]


def stored_run(db):
    return db.tables['agent_runs'][0]


@pytest.mark.asyncio
async def test_approve_wins_cancel_gets_conflict():
    db = DecisionGateDB()
    service = make_service(db)
    run = await _gated_run(service)
    action_id = run['pendingAction']['id']
    # Hold the cancel's action write: the cancel has loaded the run
    # and seen the action still pending, but has not written yet.
    db.arm('agent_pending_actions', 'cancelled')
    cancel_task = asyncio.create_task(
        service.cancel_run(user_id=USER, run_id=run['id'])
    )
    await db.gate_reached.wait()
    # The approval runs to completion in the gap.
    decided = await service.decide_approval(
        user_id=USER, action_id=action_id, decision='approved'
    )
    assert decided['run']['status'] == 'queued'
    db.gate_release.set()
    with pytest.raises(AgentRunConflictError):
        await cancel_task
    # The approval stands exactly as decided; nothing was rewritten.
    assert stored_action(db)['status'] == 'approved'
    assert stored_run(db)['status'] == 'queued'


@pytest.mark.asyncio
async def test_cancel_wins_approve_gets_conflict():
    db = DecisionGateDB()
    service = make_service(db)
    run = await _gated_run(service)
    action_id = run['pendingAction']['id']
    # Hold the approval's claim write; the cancel completes first.
    db.arm('agent_pending_actions', 'approved')
    approve_task = asyncio.create_task(
        service.decide_approval(
            user_id=USER, action_id=action_id, decision='approved'
        )
    )
    await db.gate_reached.wait()
    cancelled = await service.cancel_run(user_id=USER, run_id=run['id'])
    assert cancelled['status'] == 'cancelled'
    db.gate_release.set()
    with pytest.raises(AgentRunConflictError):
        await approve_task
    assert stored_action(db)['status'] == 'cancelled'
    assert stored_run(db)['status'] == 'cancelled'


@pytest.mark.asyncio
async def test_deny_wins_cancel_cannot_rewrite_the_decision():
    db = DecisionGateDB()
    service = make_service(db)
    run = await _gated_run(service)
    action_id = run['pendingAction']['id']
    # Hold the cancel's action write; the denial completes first.
    db.arm('agent_pending_actions', 'cancelled')
    cancel_task = asyncio.create_task(
        service.cancel_run(user_id=USER, run_id=run['id'])
    )
    await db.gate_reached.wait()
    decided = await service.decide_approval(
        user_id=USER, action_id=action_id, decision='denied'
    )
    assert decided['run']['status'] == 'cancelled'
    db.gate_release.set()
    with pytest.raises(AgentRunConflictError):
        await cancel_task
    # The recorded decision is the denial the user made — a racing
    # cancel must not rewrite it after the fact.
    assert stored_action(db)['status'] == 'denied'
    assert stored_run(db)['status'] == 'cancelled'


@pytest.mark.asyncio
async def test_two_cancels_exactly_one_succeeds():
    db = DecisionGateDB()
    service = make_service(db)
    run = await _gated_run(service)
    db.arm('agent_pending_actions', 'cancelled')
    first = asyncio.create_task(
        service.cancel_run(user_id=USER, run_id=run['id'])
    )
    await db.gate_reached.wait()
    second = await service.cancel_run(user_id=USER, run_id=run['id'])
    assert second['status'] == 'cancelled'
    db.gate_release.set()
    with pytest.raises(AgentRunConflictError):
        await first
    assert stored_action(db)['status'] == 'cancelled'
    assert stored_run(db)['status'] == 'cancelled'


@pytest.mark.asyncio
async def test_sequential_decisions_still_work():
    db = DecisionGateDB()
    service = make_service(db)
    # Approve, then cancel the queued run before it executes: a
    # legitimate sequence, not a race. The approval stays on record.
    run = await _gated_run(service)
    decided = await service.decide_approval(
        user_id=USER,
        action_id=run['pendingAction']['id'],
        decision='approved',
    )
    assert decided['run']['status'] == 'queued'
    cancelled = await service.cancel_run(user_id=USER, run_id=run['id'])
    assert cancelled['status'] == 'cancelled'
    assert stored_action(db)['status'] == 'approved'
    assert stored_run(db)['status'] == 'cancelled'

    # A plain cancel of a run still waiting on its approval.
    db2 = DecisionGateDB()
    service2 = make_service(db2)
    run2 = await _gated_run(service2)
    cancelled2 = await service2.cancel_run(user_id=USER, run_id=run2['id'])
    assert cancelled2['status'] == 'cancelled'
    assert stored_action(db2)['status'] == 'cancelled'
    assert stored_run(db2)['status'] == 'cancelled'
