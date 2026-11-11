"""Missing approval row: an approval-gated run must never fall back
to its original creation payload.

Fix B made the approved-payload lookup fail closed when the approved
action's payload cannot be loaded — but only when an approved action
row exists. When the row itself is missing at execution time (deleted,
or its status rewritten after the approval landed), the lookup
reported "no approved action" and execution silently fell back to the
run's original creation payload. For a run whose approval EDITED the
payload, that executes exactly the payload the user did not approve —
the substitution Fix B exists to prevent, reached through the
missing-row path instead of the read-error path.

The gate is a property of the run, not of the row's current status:
a run is approval-gated when its record shows it went through
approval (a pending-action row in any state, or the
``approval.requested`` step creation writes only for gated runs).
A gated run executes only with an approved row carrying a usable
payload; anything else refuses with ``APPROVED_PAYLOAD_UNAVAILABLE``
before any provider contact. A run that was never gated keeps
executing its creation payload, unchanged.
"""
import pytest

from backend.agent_executor import AgentExecutor
from backend.agent_run_service import AgentRunService
from test_agent_execution_security import EVENT_A, FakeDB, FakeGoogleConnector

USER = '11111111-1111-1111-1111-111111111111'

EDITED = {
    'summary': 'Edited follow-up visit',
    'start': '2026-11-12T09:00:00-05:00',
    'end': '2026-11-12T10:00:00-05:00',
    'attendees': ['person@example.com'],
}


def make_executor():
    db = FakeDB()
    service = AgentRunService(
        db, enforce_capability_status=False, enforce_access=False
    )
    connector = FakeGoogleConnector()
    executor = AgentExecutor(
        service, google_connector=connector, execution_paused=False
    )
    return executor, service, db, connector


async def _approved_run_with_edit(service):
    """A calendar.create run approved with an edited payload: the
    payload of record is EDITED, never the creation payload EVENT_A."""
    run = await service.create_run(
        user_id=USER, capability_id='calendar.create', payload=dict(EVENT_A)
    )
    await service.decide_approval(
        user_id=USER,
        action_id=run['pendingAction']['id'],
        decision='approved',
        edited_payload=dict(EDITED),
    )
    return run


@pytest.mark.asyncio
async def test_deleted_approval_row_refuses_execution():
    executor, service, db, connector = make_executor()
    run = await _approved_run_with_edit(service)
    # The approved row is gone by execution time.
    db.tables['agent_pending_actions'].clear()
    result = await executor.execute_run(user_id=USER, run_id=run['id'])
    assert result['status'] == 'failed'
    stored = db.tables['agent_runs'][0]
    assert stored['status'] == 'failed'
    assert 'APPROVED_PAYLOAD_UNAVAILABLE' in (stored['result_summary'] or '')
    # Neither the edited payload nor the original creation payload
    # reached a provider.
    assert connector.created_events == []


@pytest.mark.asyncio
async def test_rewritten_approval_row_status_refuses_execution():
    executor, service, db, connector = make_executor()
    run = await _approved_run_with_edit(service)
    # The row still exists but no longer reads as approved.
    db.tables['agent_pending_actions'][0]['status'] = 'cancelled'
    result = await executor.execute_run(user_id=USER, run_id=run['id'])
    assert result['status'] == 'failed'
    stored = db.tables['agent_runs'][0]
    assert stored['status'] == 'failed'
    assert 'APPROVED_PAYLOAD_UNAVAILABLE' in (stored['result_summary'] or '')
    assert connector.created_events == []


@pytest.mark.asyncio
async def test_approved_row_executes_the_edited_payload():
    executor, service, db, connector = make_executor()
    run = await _approved_run_with_edit(service)
    result = await executor.execute_run(user_id=USER, run_id=run['id'])
    assert result['status'] == 'succeeded'
    assert len(connector.created_events) == 1
    created = connector.created_events[0]
    assert created['summary'] == EDITED['summary']
    assert created['attendees'] == EDITED['attendees']


@pytest.mark.asyncio
async def test_never_gated_run_executes_its_creation_payload():
    executor, service, db, connector = make_executor()
    run = await service.create_run(
        user_id=USER, capability_id='gmail.search', payload={'query': 'invoice'}
    )
    assert run['status'] == 'queued'
    result = await executor.execute_run(user_id=USER, run_id=run['id'])
    assert result['status'] == 'succeeded'
    assert connector.search_queries == ['invoice']
