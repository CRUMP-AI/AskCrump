"""The due scan must reach every tenant, not just the loudest.

The keyset-paged scan shipped with the fairness fix read at most
1,000 rows x 10 pages before applying its per-tenant cap, so a
tenant with more than 10,000 older due rows filled the entire
read horizon and a quiet tenant's row was never even seen. Its
cursor was the timestamp alone: when a full page shared one exact
timestamp, the scan fell back to advancing strictly past that
timestamp, skipping every remaining tied row behind the page —
including other tenants' rows at the same instant.

The scan now walks tenant blocks, not one global window. Blocks
are visited in tenant order and paged oldest-first within the
block on a stable (next_run_at, id) cursor, so a tie block is
walked completely, row by row, however wide it is. A tenant
contributes at most the pass limit of candidates; once it hits
the cap, the rest of its block is skipped unread, so a backlog
costs the scan at most a page past the cap no matter how deep it
runs — the cap sits below the horizon by construction, and every
other tenant's oldest rows are reached in the same pass.
"""
from datetime import datetime, timedelta, timezone

import pytest

from backend.agent_automation_service import AgentAutomationService
from backend.routes import agent as agent_routes
from test_agent_automation_lifecycle import seed, wire
from test_agent_automations import FakeDB

USER = '11111111-1111-1111-1111-111111111111'
OTHER = '22222222-2222-2222-2222-222222222222'


@pytest.mark.asyncio
async def test_quiet_tenant_reached_beyond_ten_thousand_flooded_rows():
    db = FakeDB()
    service = AgentAutomationService(db)
    past = datetime.now(timezone.utc) - timedelta(days=2)
    for index in range(10_500):
        seed(
            db,
            automation_id=f'flood-{index:05d}',
            user_id=USER,
            next_run_at=(past + timedelta(seconds=index)).isoformat(),
        )
    seed(
        db,
        automation_id='quiet-1',
        user_id=OTHER,
        next_run_at=(past + timedelta(days=1)).isoformat(),
    )
    due = await service.due_automations(datetime.now(timezone.utc))
    ids = [row['id'] for row in due]
    # The quiet tenant's only row is selected in the same pass,
    # beyond the flooded tenant's 10,500-row backlog...
    assert 'quiet-1' in ids
    # ...and the flood is still capped at the pass limit.
    assert sum(1 for row in due if row['user_id'] == USER) <= 100


@pytest.mark.asyncio
async def test_tie_block_beyond_one_page_still_reaches_quiet_tenant():
    db = FakeDB()
    service = AgentAutomationService(db)
    stamp = '2026-11-01T07:30:00+00:00'
    for index in range(1_500):
        seed(
            db,
            automation_id=f'tie-{index:04d}',
            user_id=USER,
            next_run_at=stamp,
        )
    # The quiet tenant's row shares the exact same timestamp and
    # sorts last inside the tie: a timestamp-only cursor that
    # advances strictly past the stamp after one full page never
    # sees it.
    seed(db, automation_id='tie-quiet', user_id=OTHER, next_run_at=stamp)
    due = await service.due_automations(
        datetime(2026, 11, 9, tzinfo=timezone.utc)
    )
    ids = [row['id'] for row in due]
    assert 'tie-quiet' in ids
    assert sum(1 for row in due if row['user_id'] == USER) <= 100


@pytest.mark.asyncio
async def test_flooded_poison_never_starves_another_tenants_run(monkeypatch):
    db = FakeDB()
    wire(monkeypatch, db)
    past = datetime.now(timezone.utc) - timedelta(days=9)
    for index in range(10_500):
        seed(
            db,
            automation_id=f'poison-{index:05d}',
            user_id=USER,
            next_run_at=(past + timedelta(minutes=index)).isoformat(),
            capability_id='agent.retired_brief',
        )
    # Tenant B's row is due but sits past all 10,500 of tenant A's
    # rows in the scan order — beyond the old scan's entire read
    # horizon of 1,000 rows x 10 pages.
    seed(
        db,
        automation_id='valid-b',
        user_id=OTHER,
        next_run_at=(past + timedelta(days=8)).isoformat(),
    )
    first = await agent_routes.process_due_automations()
    # The pass window holds 100 rows selected fairly across
    # tenants: tenant B's valid row is reached despite tenant A's
    # 10,500 older poison rows, its run is created, and the poison
    # in the window is disabled.
    assert first['due'] == 100
    assert first['triggered'] == 1
    assert first['disabled'] == 99
    b_runs = [run for run in db.tables['agent_runs'] if run['user_id'] == OTHER]
    assert len(b_runs) == 1
    assert b_runs[0]['status'] == 'succeeded'
