"""Automation occurrence uniqueness under a lease takeover.

Fix A keyed each occurrence by a deterministic conversation id and
fenced the schedule advance on the claim lease — but the run-due
pass ignored the fence's verdict. When the lease expired while the
claimant was still inside run creation (a slow creation, a stalled
worker), a second pass could legitimately take the occurrence over,
create and execute its run, and advance the schedule — and then
the first pass's creation landed too, its confirmation returned
None (fence lost), and the pass executed its run anyway: two runs,
two executions, one occurrence. The pre-claim dedupe check could
not see it either, because the second run did not exist yet when
the first pass looked.

The pass now treats the confirmation as the fence it is: a claimed
pass re-checks for the occurrence's run after claiming (closing
the window between the pre-claim check and the claim), and when
its confirmation reports the fence lost, it retires its own run
through the same CAS-guarded cancellation instead of executing
it. Exactly one run per occurrence is ever live.
"""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from backend.routes import agent as agent_routes
from test_agent_automation_lifecycle import seed, stored, wire
from test_agent_automations import FakeDB

USER = '11111111-1111-1111-1111-111111111111'


@pytest.mark.asyncio
async def test_lease_takeover_retires_the_losing_pass_run(monkeypatch):
    db = FakeDB()
    runs, _automations = wire(monkeypatch, db)
    seed(db, automation_id='dup-1', next_run_at='2020-01-01T07:30:00+00:00')
    original_create = runs.create_run
    create_started = asyncio.Event()
    create_release = asyncio.Event()
    calls = {'count': 0}

    async def slow_first_create(**kwargs):
        calls['count'] += 1
        if calls['count'] == 1:
            # The first pass holds its lease and is stuck inside
            # run creation — a slow insert, a stalled worker.
            create_started.set()
            await create_release.wait()
        return await original_create(**kwargs)

    monkeypatch.setattr(runs, 'create_run', slow_first_create)

    first_pass = asyncio.create_task(agent_routes.process_due_automations())
    await create_started.wait()
    # The first pass's lease expires while it is stuck (its stamp is
    # rewritten into the past, the pattern the lifecycle suite uses
    # to simulate lease expiry).
    row = stored(db, 'dup-1')
    row['updated_at'] = (
        datetime.now(timezone.utc) - timedelta(minutes=10)
    ).isoformat()
    # A second pass legitimately takes the occurrence over: it
    # claims, creates, confirms, and executes the occurrence's run.
    second = await agent_routes.process_due_automations()
    assert second['triggered'] == 1
    assert second['errors'] == 0
    # The first pass's creation finally lands. Its confirmation is
    # fenced out — the schedule already advanced under the second
    # pass's claim — so the first pass must retire its own run
    # instead of executing a second one for the same occurrence.
    create_release.set()
    first = await first_pass
    assert first['triggered'] == 0
    assert first['errors'] == 0

    runs_by_status = {}
    for run in db.tables['agent_runs']:
        runs_by_status.setdefault(run['status'], []).append(run)
    # Exactly one live run for the occurrence: the second pass's,
    # executed once. The losing pass's run exists only as a
    # cancelled record — created, never executed.
    assert len(db.tables['agent_runs']) == 2
    assert len(runs_by_status.get('succeeded', [])) == 1
    assert len(runs_by_status.get('cancelled', [])) == 1
    live = runs_by_status['succeeded'][0]
    assert live['conversation_id'].startswith('automation:dup-1:')
    assert second['runs'][0]['runId'] == live['id']
    # The schedule advanced exactly once, under the winning claim.
    row = stored(db, 'dup-1')
    assert row['last_run_at'] is not None
    assert row['next_run_at'] > '2020-01-01T07:30:00+00:00'
    assert (await agent_routes.process_due_automations())['due'] == 0
    assert len(db.tables['agent_runs']) == 2


@pytest.mark.asyncio
async def test_concurrent_claims_have_exactly_one_lease_holder(monkeypatch):
    db = FakeDB()
    _runs, automations = wire(monkeypatch, db)
    seed(db, automation_id='race-1', next_run_at='2020-01-01T07:30:00+00:00')
    now = datetime.now(timezone.utc)
    due = await automations.due_automations(now)
    assert len(due) == 1
    row = due[0]
    # Two passes race the claim on the same observed row: the
    # compare-and-swap admits exactly one lease holder.
    first, second = await asyncio.gather(
        automations.claim_due_automation(row, ran_at=now),
        automations.claim_due_automation(dict(row), ran_at=now),
    )
    assert (first is None) != (second is None)
