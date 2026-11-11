"""Due-scan fairness: the scan cap must not starve other tenants.

The due scan read ONE global oldest-first window of 1,000 rows and
applied its per-tenant round-robin fairness to whatever that
window happened to hold. A tenant with more than 1,000 older due
rows filled the entire window, so every other tenant's due rows
sat outside it — fairness ran, but only ever over the flooding
tenant's backlog, and the other tenants starved pass after pass.

The scan now pages through the due rows in bounded keyset pages
and accumulates as it goes, capping each tenant at the pass limit
during accumulation: fairness bounds what one tenant can occupy
*within* the scan, so a valid row from a quiet tenant is selected
in the same pass no matter how deep another tenant's flood runs.
"""
from datetime import datetime, timedelta, timezone

import pytest

from backend.agent_automation_service import AgentAutomationService
from backend.routes import agent as agent_routes
from test_agent_automation_lifecycle import seed, wire
from test_agent_automations import FakeDB

USER = '11111111-1111-1111-1111-111111111111'
OTHER = '22222222-2222-2222-2222-222222222222'


def _flood(db, *, count, base, user_id=USER, **overrides):
    for index in range(count):
        seed(
            db,
            automation_id=f'flood-{index:04d}',
            user_id=user_id,
            next_run_at=(base + timedelta(minutes=index)).isoformat(),
            **overrides,
        )


@pytest.mark.asyncio
async def test_quiet_tenant_selected_beyond_the_scan_cap():
    db = FakeDB()
    service = AgentAutomationService(db)
    base = datetime(2026, 11, 1, tzinfo=timezone.utc)
    # One tenant's flood: 1,500 due rows, every one of them older
    # than the quiet tenant's single valid row — the quiet row sits
    # at position 1,501 in the global oldest-first order, far
    # outside any single 1,000-row window.
    _flood(db, count=1500, base=base)
    seed(
        db,
        automation_id='quiet-b',
        user_id=OTHER,
        next_run_at=(base + timedelta(minutes=1600)).isoformat(),
    )
    now = base + timedelta(days=2)
    due = await service.due_automations(now)
    ids = [row['id'] for row in due]
    assert 'quiet-b' in ids
    assert len(due) == 100
    # The flood still contributes its fair share — fairness bounds
    # the flood, it does not exclude it.
    assert sum(1 for i in ids if i.startswith('flood-')) == 99


@pytest.mark.asyncio
async def test_flooded_poison_never_starves_another_tenants_run(monkeypatch):
    db = FakeDB()
    wire(monkeypatch, db)
    past = datetime.now(timezone.utc) - timedelta(days=2)
    # 1,500 terminally invalid rows from one tenant, all older than
    # the other tenant's valid row.
    _flood(
        db,
        count=1500,
        base=past,
        capability_id='agent.retired_brief',
    )
    seed(
        db,
        automation_id='valid-b',
        user_id=OTHER,
        next_run_at=(past + timedelta(minutes=1600)).isoformat(),
    )
    first = await agent_routes.process_due_automations()
    # The valid row is reached in the same pass and its run is
    # created, alongside the fair share of poison disabling.
    assert first['due'] == 100
    assert first['triggered'] == 1
    assert first['disabled'] == 99
    b_runs = [run for run in db.tables['agent_runs'] if run['user_id'] == OTHER]
    assert len(b_runs) == 1
    assert b_runs[0]['status'] == 'succeeded'
    assert b_runs[0]['conversation_id'].startswith('automation:valid-b:')


@pytest.mark.asyncio
async def test_exact_timestamp_tie_flood_still_reaches_quiet_tenant():
    db = FakeDB()
    service = AgentAutomationService(db)
    stamp = '2026-11-01T07:30:00+00:00'
    # 1,200 rows share one exact next_run_at — more than one scan
    # page of ties. The quiet tenant's rows are interleaved through
    # the table, and the scan must terminate and still select them.
    for index in range(1100):
        seed(db, automation_id=f'tie-a-{index:04d}', next_run_at=stamp)
        if index % 11 == 0:
            seed(
                db,
                automation_id=f'tie-b-{index // 11:03d}',
                user_id=OTHER,
                next_run_at=stamp,
            )
    now = datetime(2026, 11, 2, tzinfo=timezone.utc)
    due = await service.due_automations(now)
    ids = [row['id'] for row in due]
    assert any(i.startswith('tie-b-') for i in ids)
    assert len(due) == 100
