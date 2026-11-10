"""Automation lifecycle: one run per occurrence, poison rows, crashes.

The run-due pass used to claim a due automation by stamping its
schedule forward before the run existed, and to hand the claim back
whenever creation or execution failed. Three defects followed, each
pinned here with a deterministic scenario:

- Duplicate runs per occurrence: while execution was paused (or
  execution threw), every minute pass minted a new queued run for
  the same occurrence. A pass now files the occurrence's run under a
  deterministic conversation id and advances the schedule only once
  the run exists, so repeated passes find the one outstanding run
  instead of minting more.
- Poison rows starved the queue: the due scan was a global
  oldest-first window of 100, and terminally invalid rows were
  re-scanned forever. Terminally invalid rows are now disabled on
  sight (with the reason logged), and the scan selects its window
  round-robin across tenants, so another tenant's valid due row is
  always reached in the same pass.
- A crash after the claim consumed the schedule: the claim is now a
  lease that never advances ``next_run_at``. The schedule advances
  only on confirmed run creation, so a process that dies between
  lease and creation leaves the occurrence due — behind the lease
  until it expires, then retried exactly once.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from backend import agent_automation_service as automation_module
from backend.agent_automation_service import AgentAutomationService
from backend.agent_executor import AgentExecutor
from backend.agent_run_service import AgentRunService
from backend.routes import agent as agent_routes
from test_agent_automations import FakeDB, FakeGoogleConnector

USER = '11111111-1111-1111-1111-111111111111'
OTHER = '22222222-2222-2222-2222-222222222222'
THIRD = '33333333-3333-3333-3333-333333333333'
OLD = '2026-11-01T00:00:00+00:00'


def wire(monkeypatch, db, *, paused=False):
    """Point the run-due lane at ``db`` with a working Google double."""
    db.tables['users'] = [
        {'id': USER, 'is_guest': False},
        {'id': OTHER, 'is_guest': False},
        {'id': THIRD, 'is_guest': False},
    ]
    runs = AgentRunService(db)
    automations = AgentAutomationService(db)
    monkeypatch.setattr(agent_routes, 'db', db)
    monkeypatch.setattr(agent_routes, 'agent_runs', runs)
    monkeypatch.setattr(
        agent_routes,
        '_google_connector',
        lambda: FakeGoogleConnector(connected=True),
    )
    if not paused:
        monkeypatch.setattr(
            agent_routes,
            '_executor',
            lambda: AgentExecutor(
                runs,
                google_connector=FakeGoogleConnector(connected=True),
                execution_paused=False,
            ),
        )
    # With paused=True the production executor factory stays in
    # place: paused by default, wired to the patched run service.
    return runs, automations


def seed(db, *, automation_id, user_id=USER, next_run_at, updated_at=OLD, **overrides):
    row = {
        'id': automation_id,
        'user_id': user_id,
        'capability_id': 'agent.morning_brief',
        'schedule_kind': 'daily',
        'local_time': '07:30',
        'timezone': 'UTC',
        'payload': {},
        'enabled': True,
        'last_run_at': None,
        'next_run_at': next_run_at,
        'created_at': '2026-11-01T00:00:00+00:00',
        'updated_at': updated_at,
    }
    row.update(overrides)
    db.tables['agent_automations'].append(row)
    return row


def stored(db, automation_id):
    return next(
        row for row in db.tables['agent_automations'] if row['id'] == automation_id
    )


# -- terminal vs transient classification ------------------------------------


def test_terminal_invalid_reason_classification(monkeypatch):
    row = {
        'capability_id': 'agent.morning_brief',
        'schedule_kind': 'daily',
        'local_time': '07:30',
        'timezone': 'UTC',
        'payload': {},
    }
    reason = AgentAutomationService.terminal_invalid_reason
    assert reason(row) is None
    assert reason({**row, 'capability_id': 'agent.retired_brief'}) == (
        'CAPABILITY_NOT_FOUND'
    )
    assert reason({**row, 'capability_id': 'gmail.search'}) == (
        'AUTOMATION_CAPABILITY_NOT_SCHEDULABLE'
    )
    assert reason({**row, 'local_time': '7am'}) == 'INVALID_AUTOMATION_SCHEDULE'
    assert reason({**row, 'timezone': 'Not/AZone'}) == 'INVALID_AUTOMATION_SCHEDULE'
    assert reason({**row, 'schedule_kind': 'weekly'}) == (
        'INVALID_AUTOMATION_SCHEDULE'
    )
    assert reason({**row, 'payload': 'not-an-object'}) == 'INVALID_AUTOMATION_INPUT'
    # A schedulable capability that is no longer live is terminal too.
    monkeypatch.setattr(
        automation_module,
        'get_capability',
        lambda capability_id: SimpleNamespace(id=capability_id, status='planned'),
    )
    assert reason(row) == 'CAPABILITY_NOT_LIVE'


# -- defect 1: one outstanding run per occurrence -----------------------------


@pytest.mark.asyncio
async def test_paused_executor_three_passes_create_exactly_one_run(monkeypatch):
    db = FakeDB()
    _runs, automations = wire(monkeypatch, db, paused=True)
    created = await automations.create_automation(
        user_id=USER,
        capability_id='agent.morning_brief',
        schedule={'time': '07:30', 'timezone': 'UTC'},
        now=datetime(2020, 1, 1, tzinfo=timezone.utc),
    )
    assert created['nextRunAt'] == '2020-01-01T07:30:00+00:00'

    results = [await agent_routes.process_due_automations() for _ in range(3)]

    # Exactly one queued run exists for the occurrence after three
    # minute ticks against the paused executor.
    assert len(db.tables['agent_runs']) == 1
    run = db.tables['agent_runs'][0]
    assert run['status'] == 'queued'
    assert run['conversation_id'] == (
        f"automation:{created['id']}:2020-01-01T07:30:00+00:00"
    )
    # The first pass created and confirmed the run; execution stayed
    # paused, so it counts as an error and not a trigger. The
    # occurrence is consumed, so later passes do not even see it due.
    assert results[0]['due'] == 1
    assert results[0]['triggered'] == 0
    assert results[0]['errors'] == 1
    assert results[1]['due'] == 0
    assert results[2]['due'] == 0
    row = stored(db, created['id'])
    assert row['last_run_at'] is not None
    assert row['next_run_at'] > '2020-01-01T07:30:00+00:00'


# -- defect 2: poison rows are marked and cannot starve the queue -------------


@pytest.mark.asyncio
async def test_poison_rows_are_disabled_and_never_starve_another_tenant(
    monkeypatch,
):
    db = FakeDB()
    wire(monkeypatch, db)
    past = datetime.now(timezone.utc) - timedelta(days=2)
    for index in range(100):
        seed(
            db,
            automation_id=f'poison-{index:03d}',
            user_id=USER,
            next_run_at=(past + timedelta(minutes=index)).isoformat(),
            capability_id='agent.retired_brief',
        )
    seed(
        db,
        automation_id='valid-b',
        user_id=OTHER,
        next_run_at=(past + timedelta(seconds=30)).isoformat(),
    )

    first = await agent_routes.process_due_automations()
    # The pass window holds 100 rows, selected fairly: tenant B's
    # valid row is reached in the same pass despite tenant A's 100
    # older poison rows, and its run is created.
    assert first['due'] == 100
    assert first['triggered'] == 1
    assert first['errors'] == 0
    assert first['disabled'] == 99
    b_runs = [run for run in db.tables['agent_runs'] if run['user_id'] == OTHER]
    assert len(b_runs) == 1
    assert b_runs[0]['status'] == 'succeeded'
    assert b_runs[0]['conversation_id'].startswith('automation:valid-b:')
    # The marking is durable: 99 poison rows are disabled already,
    # and tenant B's automation advanced normally.
    assert sum(1 for i in range(100) if not stored(db, f'poison-{i:03d}')['enabled']) == 99
    assert stored(db, 'valid-b')['enabled'] is True
    assert stored(db, 'valid-b')['last_run_at'] is not None

    # The one poison row the first window could not hold is disabled
    # by the next pass; after that, poison never re-enters the scan.
    second = await agent_routes.process_due_automations()
    assert second['due'] == 1
    assert second['disabled'] == 1
    assert all(not stored(db, f'poison-{i:03d}')['enabled'] for i in range(100))
    third = await agent_routes.process_due_automations()
    assert third['due'] == 0
    assert len(db.tables['agent_runs']) == 1


@pytest.mark.asyncio
async def test_creation_proven_terminal_rows_are_disabled(monkeypatch):
    db = FakeDB()
    wire(monkeypatch, db)
    # The stored payload passes the automation-level checks (it is a
    # small object) but fails the capability schema at run creation:
    # ``schedule`` must be a string. Creation proves it terminal.
    seed(
        db,
        automation_id='bad-payload',
        next_run_at='2020-01-01T07:30:00+00:00',
        payload={'schedule': 42},
    )
    result = await agent_routes.process_due_automations()
    assert result['disabled'] == 1
    assert result['errors'] == 0
    assert db.tables['agent_runs'] == []
    assert stored(db, 'bad-payload')['enabled'] is False
    assert (await agent_routes.process_due_automations())['due'] == 0


# -- defect 3: a crash after the claim never consumes the schedule ------------


class SimulatedCrash(BaseException):
    """Process death, not a handled failure: BaseException on purpose."""


@pytest.mark.asyncio
async def test_crash_after_claim_leaves_occurrence_due_and_retries_once(
    monkeypatch,
):
    db = FakeDB()
    runs, _automations = wire(monkeypatch, db)
    seed(db, automation_id='crash-1', next_run_at='2020-01-01T07:30:00+00:00')
    original_create = runs.create_run

    async def crashing_create(**kwargs):
        raise SimulatedCrash()

    monkeypatch.setattr(runs, 'create_run', crashing_create)
    with pytest.raises(SimulatedCrash):
        await agent_routes.process_due_automations()

    # The claim was only a lease: the schedule did not advance and
    # no run exists, so the occurrence was not consumed.
    row = stored(db, 'crash-1')
    assert row['next_run_at'] == '2020-01-01T07:30:00+00:00'
    assert row['last_run_at'] is None
    assert db.tables['agent_runs'] == []

    # While the lease is live the row stays out of later passes —
    # the crashed pass might still be finishing elsewhere.
    held = await agent_routes.process_due_automations()
    assert held['due'] == 0
    assert db.tables['agent_runs'] == []

    # Once the lease has expired (its stamp is now in the past), the
    # next pass recovers the occurrence and creates its run once.
    row['updated_at'] = (
        datetime.now(timezone.utc) - timedelta(minutes=10)
    ).isoformat()
    monkeypatch.setattr(runs, 'create_run', original_create)
    recovered = await agent_routes.process_due_automations()
    assert recovered['triggered'] == 1
    assert recovered['errors'] == 0
    assert len(db.tables['agent_runs']) == 1
    assert db.tables['agent_runs'][0]['status'] == 'succeeded'
    row = stored(db, 'crash-1')
    assert row['last_run_at'] is not None
    assert row['next_run_at'] > '2020-01-01T07:30:00+00:00'
    assert (await agent_routes.process_due_automations())['due'] == 0
    assert len(db.tables['agent_runs']) == 1


@pytest.mark.asyncio
async def test_crash_after_creation_is_recovered_without_a_second_run(
    monkeypatch,
):
    db = FakeDB()
    runs, _automations = wire(monkeypatch, db)
    row = seed(db, automation_id='crash-2', next_run_at='2020-01-01T07:30:00+00:00')
    # A pass that created the occurrence's run and died before
    # confirming it leaves exactly this state behind.
    created = await runs.create_run(
        user_id=USER,
        capability_id='agent.morning_brief',
        payload=AgentAutomationService.run_payload_for(dict(row)),
        conversation_id=AgentAutomationService.occurrence_conversation_id(
            dict(row)
        ),
    )
    assert created['status'] == 'queued'
    assert stored(db, 'crash-2')['next_run_at'] == '2020-01-01T07:30:00+00:00'

    result = await agent_routes.process_due_automations()
    assert len(db.tables['agent_runs']) == 1
    assert result['triggered'] == 1
    assert result['errors'] == 0
    assert result['runs'][0]['runId'] == created['id']
    assert result['runs'][0]['status'] == 'succeeded'
    row = stored(db, 'crash-2')
    assert row['last_run_at'] is not None
    assert row['next_run_at'] > '2020-01-01T07:30:00+00:00'
    assert (await agent_routes.process_due_automations())['due'] == 0


# -- transient failures keep the row due ---------------------------------------


@pytest.mark.asyncio
async def test_transient_creation_failure_releases_the_lease_for_retry(
    monkeypatch,
):
    db = FakeDB()
    runs, _automations = wire(monkeypatch, db)
    seed(db, automation_id='flaky-1', next_run_at='2020-01-01T07:30:00+00:00')
    original_create = runs.create_run

    async def failing_create(**kwargs):
        raise RuntimeError('database unavailable')

    monkeypatch.setattr(runs, 'create_run', failing_create)
    failed = await agent_routes.process_due_automations()
    assert failed['errors'] == 1
    assert failed['triggered'] == 0
    assert db.tables['agent_runs'] == []
    row = stored(db, 'flaky-1')
    assert row['enabled'] is True
    assert row['next_run_at'] == '2020-01-01T07:30:00+00:00'
    # The lease was handed back, not left to expire: the row carries
    # its pre-claim stamp again and is retryable on the next pass.
    assert row['updated_at'] == OLD

    monkeypatch.setattr(runs, 'create_run', original_create)
    retried = await agent_routes.process_due_automations()
    assert retried['triggered'] == 1
    assert retried['errors'] == 0
    assert len(db.tables['agent_runs']) == 1


# -- fairness of the due scan ---------------------------------------------------


@pytest.mark.asyncio
async def test_due_scan_selects_round_robin_across_tenants():
    db = FakeDB()
    service = AgentAutomationService(db)
    base = datetime(2026, 11, 9, 7, 30, tzinfo=timezone.utc)
    users = [USER, OTHER, THIRD]
    for rank in range(3):
        for offset, user_id in enumerate(users):
            seed(
                db,
                automation_id=f'u{offset}-r{rank}',
                user_id=user_id,
                next_run_at=(base + timedelta(minutes=offset + 3 * rank)).isoformat(),
            )
    now = datetime(2026, 11, 10, tzinfo=timezone.utc)
    due = await service.due_automations(now, limit=4)
    # One row per tenant first, then the oldest tenant's second row:
    # nobody's second row is served before every tenant's first.
    assert [row['id'] for row in due] == ['u0-r0', 'u1-r0', 'u2-r0', 'u0-r1']
    # The default pass limit still caps a single tenant's backlog.
    assert len(await service.due_automations(now)) == 9
