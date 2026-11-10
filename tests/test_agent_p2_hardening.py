"""P2 hardening bundle coverage.

Three of the bundle's four items are pinned here:

- Run creation enforces the registry's declared input schemas:
  property types, the formats the registry actually declares
  (``date-time`` and ``email``, including array item formats),
  ``additionalProperties: false``, and the declared enum / length /
  range constraints. Rejections use the existing
  ``INVALID_RUN_INPUT`` error with a field-level message.
- The automation run-due claim is a compare-and-swap lease on the
  due row's observed ``next_run_at`` / ``updated_at``: two
  concurrent passes over the same due automation create its run
  exactly once, and a failed run creation hands the lease back so
  the automation stays due. The lease never advances the schedule —
  that split (and the poison/fairness/crash lifecycle around it) is
  covered in full in ``tests/test_agent_automation_lifecycle.py``.
- ``tzdata`` is declared with a Windows platform marker in both
  dependency files, so ``zoneinfo`` has a tz database on Windows
  dev/test machines. There is no Windows runner here; the pin is
  the declaration itself plus the suite staying green on Linux.

The fourth item (vault AAD binding) is document-only in this change
and carries no code or tests; see the pull request description.
"""
import asyncio
from datetime import datetime, timezone
from pathlib import Path

import pytest

from backend import agent_registry
from backend.agent_automation_service import AgentAutomationService
from backend.agent_executor import AgentExecutor
from backend.agent_run_service import AgentRunError, AgentRunService
from backend.routes import agent as agent_routes
from test_agent_automations import FakeDB as AutomationFakeDB
from test_agent_automations import FakeGoogleConnector
from test_agent_run_service import FakeDB as RunFakeDB

ROOT = Path(__file__).resolve().parents[1]
USER = '11111111-1111-1111-1111-111111111111'


def make_service(db=None):
    return AgentRunService(
        db if db is not None else RunFakeDB(),
        enforce_capability_status=False,
        enforce_access=False,
    )


# -- schema enforcement: valid payloads -------------------------------------

# One known-good payload per live capability. The map must cover the
# live registry exactly, so a capability that goes live without a
# sample here fails this test loudly instead of slipping through.
LIVE_SAMPLES = {
    'chat.respond': {'message': 'Hello there'},
    'research.web_search': {'query': 'Savannah weather history'},
    'weather.lookup': {'location': 'Savannah, GA'},
    'image.generate': {'prompt': 'A lighthouse at dawn'},
    'video.generate': {'prompt': 'Waves on a beach', 'mode': 'quick'},
    'voice.synthesize': {'text': 'Read this aloud.'},
    'files.manage': {'fileId': 'file-1'},
    'memory.user': {'note': 'Prefers tea over coffee'},
    'memory.list': {},
    'memory.forget': {'memoryId': 'memory-1'},
    'agent.today_brief': {},
    'agent.morning_brief': {'schedule': 'daily 07:30 America/New_York'},
}


def test_live_sample_map_covers_the_live_registry_exactly():
    live = {
        item.id for item in agent_registry.capabilities() if item.status == 'live'
    }
    assert set(LIVE_SAMPLES) == live


@pytest.mark.asyncio
@pytest.mark.parametrize('capability_id', sorted(LIVE_SAMPLES))
async def test_valid_payloads_for_live_capabilities_are_accepted(capability_id):
    db = RunFakeDB()
    # Status enforcement stays on: these are live capabilities and
    # their valid payloads must still create runs.
    service = AgentRunService(db, enforce_access=False)
    run = await service.create_run(
        user_id=USER,
        capability_id=capability_id,
        payload=dict(LIVE_SAMPLES[capability_id]),
    )
    assert run['capabilityId'] == capability_id


# -- schema enforcement: rejections -----------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'capability_id,payload,field',
    [
        # Wrong declared type.
        ('chat.respond', {'message': 42}, 'message'),
        ('gmail.search', {'query': 'invoice', 'maxResults': '10'}, 'maxResults'),
        ('gmail.search', {'query': 'invoice', 'maxResults': True}, 'maxResults'),
        ('calendar.create', {
            'summary': 'Dentist',
            'start': '2026-11-10T09:00:00-05:00',
            'end': '2026-11-10T10:00:00-05:00',
            'attendees': 'a@example.com',
        }, 'attendees'),
        # Undeclared property on a closed schema.
        ('memory.list', {'bogus': 1}, 'bogus'),
        ('chat.respond', {'message': 'hi', 'extra': 'x'}, 'extra'),
        # Declared format violations.
        ('gmail.send', {
            'to': 'not-an-email', 'subject': 'Hi', 'body': 'Hello',
        }, 'to'),
        ('calendar.create', {
            'summary': 'Dentist', 'start': 'tomorrow',
            'end': '2026-11-10T10:00:00-05:00',
        }, 'start'),
        ('calendar.list', {'timeMin': '2026-11-09'}, 'timeMin'),
        ('calendar.create', {
            'summary': 'Dentist',
            'start': '2026-11-10T09:00:00-05:00',
            'end': '2026-11-10T10:00:00-05:00',
            'attendees': ['not-an-email'],
        }, 'attendees'),
        # Declared enum / length / range violations.
        ('video.generate', {'prompt': 'Waves', 'mode': 'slow'}, 'mode'),
        ('files.manage', {'fileId': ''}, 'fileId'),
        ('gmail.search', {'query': 'invoice', 'maxResults': 0}, 'maxResults'),
        ('gmail.search', {'query': 'invoice', 'maxResults': 51}, 'maxResults'),
    ],
)
async def test_schema_violations_are_rejected_with_field_messages(
    capability_id, payload, field
):
    db = RunFakeDB()
    service = make_service(db)
    with pytest.raises(AgentRunError) as excinfo:
        await service.create_run(
            user_id=USER, capability_id=capability_id, payload=payload
        )
    assert excinfo.value.code == 'INVALID_RUN_INPUT'
    assert excinfo.value.status_code == 400
    assert field in excinfo.value.message
    assert db.tables['agent_runs'] == []


@pytest.mark.asyncio
async def test_binding_selectors_are_envelope_fields_not_undeclared_input():
    # P1-B account binding: connectionId / accountEmail ride in the
    # payload of Google capability runs and are read by the executor,
    # so the closed schemas accept them — as strings.
    db = RunFakeDB()
    service = make_service(db)
    run = await service.create_run(
        user_id=USER,
        capability_id='gmail.search',
        payload={'query': 'invoice', 'accountEmail': 'person@example.com'},
    )
    assert run['status'] == 'queued'
    with pytest.raises(AgentRunError) as excinfo:
        await service.create_run(
            user_id=USER,
            capability_id='gmail.search',
            payload={'query': 'invoice', 'connectionId': 42},
        )
    assert excinfo.value.code == 'INVALID_RUN_INPUT'
    assert 'connectionId' in excinfo.value.message


@pytest.mark.asyncio
async def test_edited_approval_payload_is_validated_against_the_schema():
    db = RunFakeDB()
    service = make_service(db)
    run = await service.create_run(
        user_id=USER,
        capability_id='calendar.create',
        payload={
            'summary': 'Dentist',
            'start': '2026-11-10T09:00:00-05:00',
            'end': '2026-11-10T10:00:00-05:00',
        },
    )
    with pytest.raises(AgentRunError) as excinfo:
        await service.decide_approval(
            user_id=USER,
            action_id=run['pendingAction']['id'],
            decision='approved',
            edited_payload={
                'summary': 'Dentist',
                'start': '2026-11-10T09:00:00-05:00',
                'end': '2026-11-10T10:00:00-05:00',
                'attendees': ['not-an-email'],
            },
        )
    assert excinfo.value.code == 'INVALID_RUN_INPUT'
    # The action was never decided: it is still pending.
    assert db.tables['agent_pending_actions'][0]['status'] == 'pending'


# -- automation claim: compare-and-swap --------------------------------------


class YieldingAutomationDB(AutomationFakeDB):
    """Automation FakeDB whose reads/writes yield once, so concurrent
    run-due passes interleave the way production requests do."""

    async def select(self, table, *, columns='*', filters=None, order=None,
                     limit=None):
        await asyncio.sleep(0)
        return await super().select(
            table, columns=columns, filters=filters, order=order, limit=limit
        )

    async def update(self, table, payload, *, filters, **kwargs):
        await asyncio.sleep(0)
        return await super().update(table, payload, filters=filters, **kwargs)


def utc(year, month, day, hour=0, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_claim_is_a_cas_and_release_restores_the_due_state():
    db = AutomationFakeDB()
    service = AgentAutomationService(db)
    created = await service.create_automation(
        user_id=USER,
        capability_id='agent.morning_brief',
        schedule={'time': '07:30', 'timezone': 'UTC'},
        now=utc(2020, 1, 1, 0, 0),
    )
    # Snapshot the row the way a run-due pass observes it: production
    # rows arrive as fresh dicts from the database read, never as
    # aliases of the stored row.
    row = dict(db.tables['agent_automations'][0])
    assert row['next_run_at'] == '2020-01-01T07:30:00+00:00'

    # The claim is a lease: it stamps only the lease expiry into
    # updated_at and never advances the schedule.
    claimed = await service.claim_due_automation(row, ran_at=utc(2020, 1, 1, 8, 0))
    assert claimed is not None
    assert claimed['next_run_at'] == '2020-01-01T07:30:00+00:00'
    assert claimed['last_run_at'] is None
    assert claimed['updated_at'] == '2020-01-01T08:02:00+00:00'

    # A second claim against the same observed row loses the race,
    # and a fresh read during the lease cannot claim either.
    assert (
        await service.claim_due_automation(row, ran_at=utc(2020, 1, 1, 8, 0))
        is None
    )
    fresh = dict(db.tables['agent_automations'][0])
    assert (
        await service.claim_due_automation(fresh, ran_at=utc(2020, 1, 1, 8, 1))
        is None
    )

    # Releasing the lease makes the automation claimable again, with
    # the schedule exactly as it was before the claim.
    await service.release_claim(row, claimed)
    stored = db.tables['agent_automations'][0]
    assert stored['next_run_at'] == '2020-01-01T07:30:00+00:00'
    assert stored['last_run_at'] is None
    assert stored['updated_at'] == row['updated_at']
    assert created['id'] == stored['id']

    # Claiming again and confirming a created run advances the
    # schedule exactly once; a stale confirmation cannot re-advance.
    claimed = await service.claim_due_automation(row, ran_at=utc(2020, 1, 1, 8, 0))
    assert claimed is not None
    confirmed = await service.confirm_run_created(
        row, claimed, ran_at=utc(2020, 1, 1, 8, 0)
    )
    assert confirmed is not None
    assert confirmed['last_run_at'] == '2020-01-01T08:00:00+00:00'
    assert confirmed['next_run_at'] == '2020-01-02T07:30:00+00:00'
    assert (
        await service.confirm_run_created(row, claimed, ran_at=utc(2020, 1, 1, 8, 0))
        is None
    )


@pytest.mark.asyncio
async def test_concurrent_run_due_passes_create_the_run_exactly_once(
    monkeypatch,
):
    db = YieldingAutomationDB()
    db.tables['users'] = [{'id': USER, 'is_guest': False}]
    runs = AgentRunService(db)
    automations = AgentAutomationService(db)
    await automations.create_automation(
        user_id=USER,
        capability_id='agent.morning_brief',
        schedule={'time': '07:30', 'timezone': 'UTC'},
        now=utc(2020, 1, 1, 0, 0),
    )
    monkeypatch.setattr(agent_routes, 'db', db)
    monkeypatch.setattr(agent_routes, 'agent_runs', runs)
    monkeypatch.setattr(
        agent_routes,
        '_google_connector',
        lambda: FakeGoogleConnector(connected=True),
    )
    monkeypatch.setattr(
        agent_routes,
        '_executor',
        lambda: AgentExecutor(
            runs,
            google_connector=FakeGoogleConnector(connected=True),
            execution_paused=False,
        ),
    )

    first, second = await asyncio.gather(
        agent_routes.process_due_automations(),
        agent_routes.process_due_automations(),
    )
    assert len(db.tables['agent_runs']) == 1
    assert first['triggered'] + second['triggered'] == 1
    assert first['errors'] + second['errors'] == 0
    # The schedule advanced exactly once and is no longer due.
    assert await automations.due_automations(datetime.now(timezone.utc)) == []


# -- tzdata declaration -------------------------------------------------------


def test_tzdata_is_declared_for_windows_in_both_dependency_files():
    pyproject = (ROOT / 'pyproject.toml').read_text()
    requirements = (ROOT / 'requirements.txt').read_text()
    for text in (pyproject, requirements):
        tzdata_lines = [
            line for line in text.splitlines() if 'tzdata' in line
        ]
        assert len(tzdata_lines) == 1
        assert 'sys_platform' in tzdata_lines[0]
        assert 'win32' in tzdata_lines[0]
