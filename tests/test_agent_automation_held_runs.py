"""Automation runs are held non-executable until confirmed.

The occurrence fence shipped earlier created the run first and
retired the loser afterwards: a pass whose lease expired during
creation created a second, fully queued run, and when its
confirmation reported the fence lost it cancelled that run best
effort — cancellation failure was swallowed, and a concurrent
execution claim could beat the cancel. The duplicate stayed
executable: a queued run in the user's ledger that any execution
path could claim, for an occurrence that already had its run.

Automation runs are now created held, in the ledger's waiting
state (``waiting_user``), which the execution claim refuses: a
held run cannot execute, full stop. Only the pass whose
confirmation advances the schedule releases its run to the queue,
immediately before executing it. The loser of a takeover is
therefore non-executable by construction — cancelling it is
cleanup, retried by a sweep on the run-due lane until it lands,
not a safety mechanism. A pass that dies after creating a held run
and before confirming leaves it held and the occurrence due; the
next pass adopts, confirms, releases, and executes it — still
exactly one run, exactly one execution.
"""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from backend.agent_automation_service import AgentAutomationService
from backend.agent_run_service import AgentRunConflictError
from backend.routes import agent as agent_routes
from test_agent_automation_lifecycle import seed, stored, wire
from test_agent_automations import FakeDB, FakeGoogleConnector

USER = '11111111-1111-1111-1111-111111111111'


class SimulatedCrash(BaseException):
    """Process death, not a handled failure: BaseException on purpose."""


@pytest.fixture
def provider_calls(monkeypatch):
    """Count the brief's provider contacts across every connector
    instance the passes construct."""
    calls = {'count': 0}
    real_events = FakeGoogleConnector.list_events
    real_search = FakeGoogleConnector.search_messages

    async def counting_events(self, *args, **kwargs):
        calls['count'] += 1
        return await real_events(self, *args, **kwargs)

    async def counting_search(self, *args, **kwargs):
        calls['count'] += 1
        return await real_search(self, *args, **kwargs)

    monkeypatch.setattr(FakeGoogleConnector, 'list_events', counting_events)
    monkeypatch.setattr(FakeGoogleConnector, 'search_messages', counting_search)
    return calls


def runs_by_status(db):
    by_status = {}
    for run in db.tables['agent_runs']:
        by_status.setdefault(run['status'], []).append(run)
    return by_status


async def takeover_interleave(monkeypatch, db, runs):
    """Drive two passes into the takeover shape: the first pass is
    held inside run creation while its lease expires and a second
    pass claims, creates, confirms, and executes the occurrence's
    run. Returns (first_pass_task, release_first_create)."""
    original_create = runs.create_run
    create_started = asyncio.Event()
    create_release = asyncio.Event()
    calls = {'count': 0}

    async def slow_first_create(**kwargs):
        calls['count'] += 1
        if calls['count'] == 1:
            create_started.set()
            await create_release.wait()
        return await original_create(**kwargs)

    monkeypatch.setattr(runs, 'create_run', slow_first_create)
    first_pass = asyncio.create_task(agent_routes.process_due_automations())
    await create_started.wait()
    row = stored(db, 'dup-1')
    row['updated_at'] = (
        datetime.now(timezone.utc) - timedelta(minutes=10)
    ).isoformat()
    second = await agent_routes.process_due_automations()
    assert second['triggered'] == 1
    assert second['errors'] == 0
    return first_pass, create_release


# -- the loser: non-executable by construction -----------------------------------


@pytest.mark.asyncio
async def test_loser_stays_non_executable_when_retirement_fails(
    monkeypatch, provider_calls
):
    db = FakeDB()
    runs, _automations = wire(monkeypatch, db)
    seed(db, automation_id='dup-1', next_run_at='2020-01-01T07:30:00+00:00')
    first_pass, release = await takeover_interleave(monkeypatch, db, runs)
    winner_calls = provider_calls['count']
    assert winner_calls > 0

    # The losing pass's retirement now fails outright — the exact
    # hole in the best-effort cleanup: cancellation unavailable.
    real_cancel = runs.cancel_run
    cancel_gate = {'fail': True}

    async def flaky_cancel(**kwargs):
        if cancel_gate['fail']:
            raise RuntimeError('cancellation unavailable')
        return await real_cancel(**kwargs)

    monkeypatch.setattr(runs, 'cancel_run', flaky_cancel)
    release.set()
    first = await first_pass
    assert first['triggered'] == 0

    by_status = runs_by_status(db)
    assert len(db.tables['agent_runs']) == 2
    assert len(by_status.get('succeeded', [])) == 1
    # The loser was never released to the queue: it sits in the
    # waiting state the execution claim refuses, not in 'queued'
    # where any execution path could claim it.
    assert len(by_status.get('waiting_user', [])) == 1
    assert by_status.get('queued', []) == []
    loser = by_status['waiting_user'][0]

    # An execution attempt on the loser is refused before any
    # provider contact: the occurrence keeps exactly one execution.
    executor = agent_routes._executor()
    with pytest.raises(AgentRunConflictError):
        await executor.execute_run(user_id=USER, run_id=str(loser['id']))
    assert provider_calls['count'] == winner_calls

    # Retirement is retried by the lane itself: with cancellation
    # healthy again, a later pass — the automation long since
    # advanced, nothing due — retires the held loser through the
    # sweep, and still nothing else executes.
    cancel_gate['fail'] = False
    followup = await agent_routes.process_due_automations()
    assert followup['due'] == 0
    assert followup['retiredHeldRuns'] == 1
    by_status = runs_by_status(db)
    assert len(by_status.get('cancelled', [])) == 1
    assert by_status.get('waiting_user', []) == []
    assert len(by_status.get('succeeded', [])) == 1
    assert provider_calls['count'] == winner_calls


@pytest.mark.asyncio
async def test_concurrent_claim_cannot_execute_the_loser(
    monkeypatch, provider_calls
):
    db = FakeDB()
    runs, _automations = wire(monkeypatch, db)
    seed(db, automation_id='dup-1', next_run_at='2020-01-01T07:30:00+00:00')
    first_pass, release = await takeover_interleave(monkeypatch, db, runs)
    winner_calls = provider_calls['count']

    # Retirement fails while the losing pass runs; it is healthy
    # again for the race itself.
    real_cancel = runs.cancel_run
    cancel_gate = {'fail': True}

    async def flaky_cancel(**kwargs):
        if cancel_gate['fail']:
            raise RuntimeError('cancellation unavailable')
        return await real_cancel(**kwargs)

    monkeypatch.setattr(runs, 'cancel_run', flaky_cancel)
    release.set()
    await first_pass
    loser = runs_by_status(db)['waiting_user'][0]
    cancel_gate['fail'] = False

    executor = agent_routes._executor()

    async def attempt_execution():
        try:
            await executor.execute_run(user_id=USER, run_id=str(loser['id']))
        except AgentRunConflictError:
            return 'refused'
        return 'executed'

    execution_result, _cancelled = await asyncio.gather(
        attempt_execution(),
        runs.cancel_run(user_id=USER, run_id=str(loser['id'])),
    )
    # Whichever side of the race ran first, the held loser could not
    # be claimed: exactly one provider execution exists overall.
    assert execution_result == 'refused'
    assert provider_calls['count'] == winner_calls
    by_status = runs_by_status(db)
    assert len(by_status.get('succeeded', [])) == 1
    assert len(by_status.get('cancelled', [])) == 1


# -- the held lifecycle: create, confirm, release, execute ------------------------


@pytest.mark.asyncio
async def test_held_run_is_released_and_executes_once_on_confirmation(
    monkeypatch, provider_calls
):
    db = FakeDB()
    runs, _automations = wire(monkeypatch, db)
    seed(db, automation_id='held-1', next_run_at='2020-01-01T07:30:00+00:00')
    result = await agent_routes.process_due_automations()
    assert result['triggered'] == 1
    assert result['errors'] == 0
    assert len(db.tables['agent_runs']) == 1
    run = db.tables['agent_runs'][0]
    assert run['status'] == 'succeeded'
    # The run's own ledger shows the held lifecycle: created held,
    # released to the queue only once its occurrence was confirmed.
    step_types = [
        step['step_type']
        for step in db.tables['agent_run_steps']
        if step['run_id'] == run['id']
    ]
    assert 'run.held' in step_types
    assert step_types.index('run.held') < step_types.index('run.queued')
    assert provider_calls['count'] > 0


@pytest.mark.asyncio
async def test_crash_after_held_creation_is_adopted_by_the_next_pass(
    monkeypatch, provider_calls
):
    db = FakeDB()
    runs, _automations = wire(monkeypatch, db)
    seed(db, automation_id='held-2', next_run_at='2020-01-01T07:30:00+00:00')
    real_confirm = AgentAutomationService.confirm_run_created
    crash_gate = {'armed': True}

    async def crashing_confirm(self, row, claimed, *, ran_at):
        if crash_gate['armed']:
            crash_gate['armed'] = False
            raise SimulatedCrash()
        return await real_confirm(self, row, claimed, ran_at=ran_at)

    monkeypatch.setattr(
        AgentAutomationService, 'confirm_run_created', crashing_confirm
    )
    with pytest.raises(SimulatedCrash):
        await agent_routes.process_due_automations()
    # The pass died after creating the run and before confirming:
    # the run waits held — not queued, not executable — and the
    # schedule never advanced, so the occurrence is still due.
    assert len(db.tables['agent_runs']) == 1
    assert db.tables['agent_runs'][0]['status'] == 'waiting_user'
    row = stored(db, 'held-2')
    assert row['next_run_at'] == '2020-01-01T07:30:00+00:00'
    assert provider_calls['count'] == 0

    # The crashed pass's claim lease expires (its stamp rewritten
    # into the past, the pattern the lifecycle suite uses).
    row['updated_at'] = (
        datetime.now(timezone.utc) - timedelta(minutes=10)
    ).isoformat()
    # The next pass adopts the held run: confirms the occurrence,
    # releases the run, executes it — no second run is created.
    recovered = await agent_routes.process_due_automations()
    assert recovered['triggered'] == 1
    assert recovered['errors'] == 0
    assert len(db.tables['agent_runs']) == 1
    assert db.tables['agent_runs'][0]['status'] == 'succeeded'
    assert provider_calls['count'] > 0
    assert (await agent_routes.process_due_automations())['due'] == 0
