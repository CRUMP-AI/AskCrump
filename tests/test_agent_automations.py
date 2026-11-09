import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import app as app_module
from backend.agent_automation_service import (
    AgentAutomationError,
    AgentAutomationService,
    compute_next_run,
    normalize_schedule,
)
from backend.agent_executor import AgentExecutor
from backend.agent_registry import require_capability
from backend.agent_run_service import AgentRunService
from backend.google_connector import ConnectionRequiredError
from backend.routes import agent as agent_routes
from conftest import iter_effective_routes

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = (
    ROOT / 'migrations' / '20261109130000_agent_automations.sql'
).read_text()

CLIENT = TestClient(app_module.app)
CRON_SECRET = 'test-cron-secret-value'

USER = '11111111-1111-1111-1111-111111111111'
OTHER = '22222222-2222-2222-2222-222222222222'

MESSAGES = [
    {
        'id': 'm1',
        'from': 'Sender <s@example.com>',
        'subject': 'Invoice 42',
        'snippet': 'snippet-m1',
        'date': 'Sun, 8 Nov 2026 10:00:00 -0500',
    }
]
EVENTS = [
    {
        'id': 'e1',
        'summary': 'Standup',
        'start': '2026-11-09T14:00:00Z',
        'end': '2026-11-09T14:30:00Z',
        'location': 'Office',
        'attendees': ['a@example.com'],
    }
]


class FakeDB:
    """Minimal in-memory stand-in for SupabaseDB used by the agent tests."""

    def __init__(self):
        self.tables: dict[str, list[dict]] = {
            'agent_runs': [],
            'agent_run_steps': [],
            'agent_pending_actions': [],
            'agent_automations': [],
        }
        self._step_id = 0

    def _matches(self, row, filters):
        for key, raw in (filters or {}).items():
            value = row.get(key)
            if isinstance(raw, str) and raw.startswith('eq.'):
                expected = raw[3:]
                if isinstance(value, bool):
                    if expected != str(value).lower():
                        return False
                elif str(value) != expected:
                    return False
            elif isinstance(raw, str) and raw == 'is.null':
                if value is not None:
                    return False
            elif isinstance(raw, str) and raw.startswith('lte.'):
                if value is None or str(value) > raw[4:]:
                    return False
            elif isinstance(raw, str) and raw.startswith('lt.'):
                if value is None or str(value) >= raw[3:]:
                    return False
            elif row.get(key) != raw:
                return False
        return True

    async def select(self, table, *, columns='*', filters=None, order=None, limit=None):
        rows = [dict(r) for r in self.tables[table] if self._matches(r, filters)]
        if order:
            field, _, direction = order.partition('.')
            rows.sort(key=lambda r: str(r.get(field) or ''), reverse=direction == 'desc')
        if limit is not None:
            rows = rows[:limit]
        return rows

    async def select_one(self, table, *, columns='*', filters=None):
        rows = await self.select(table, filters=filters, limit=1)
        return rows[0] if rows else None

    async def insert(self, table, payload):
        row = dict(payload)
        if table == 'agent_run_steps':
            self._step_id += 1
            row['id'] = self._step_id
        self.tables[table].append(row)
        return [row]

    async def update(self, table, payload, *, filters, **kwargs):
        updated = []
        for row in self.tables[table]:
            if self._matches(row, filters):
                row.update(payload)
                updated.append(dict(row))
        return updated

    async def delete(self, table, *, filters):
        deleted = []
        kept = []
        for row in self.tables[table]:
            if self._matches(row, filters):
                deleted.append(dict(row))
            else:
                kept.append(row)
        self.tables[table] = kept
        return deleted


class FakeGoogleConnector:
    oauth_configured = True

    def __init__(self, *, connected: bool):
        self.connected = connected

    async def status(self, user_id):
        accounts = (
            [{'email': 'person@example.com', 'scopes': [], 'status': 'connected'}]
            if self.connected
            else []
        )
        return {'connected': self.connected, 'accounts': accounts}

    async def access_token_for(self, user_id, account_email=None):
        if not self.connected:
            raise ConnectionRequiredError()
        return 'access-token-1'

    async def search_messages(self, access_token, query, max_results=10):
        assert access_token == 'access-token-1'
        return list(MESSAGES)

    async def list_events(self, access_token, time_min=None, time_max=None, max_results=50):
        assert access_token == 'access-token-1'
        return list(EVENTS)


def make_service():
    db = FakeDB()
    return AgentAutomationService(db), db


def utc(year, month, day, hour=0, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


# -- validation -----------------------------------------------------------


@pytest.mark.asyncio
async def test_create_rejects_unknown_capability():
    service, db = make_service()
    with pytest.raises(AgentAutomationError) as exc:
        await service.create_automation(
            user_id=USER,
            capability_id='agent.nightly_brief',
            schedule={'time': '07:30', 'timezone': 'UTC'},
        )
    assert exc.value.code == 'CAPABILITY_NOT_FOUND'
    assert exc.value.status_code == 404
    assert db.tables['agent_automations'] == []


@pytest.mark.asyncio
async def test_create_rejects_non_schedulable_capability():
    service, db = make_service()
    with pytest.raises(AgentAutomationError) as exc:
        await service.create_automation(
            user_id=USER,
            capability_id='gmail.search',
            schedule={'time': '07:30', 'timezone': 'UTC'},
        )
    assert exc.value.code == 'AUTOMATION_CAPABILITY_NOT_SCHEDULABLE'
    assert db.tables['agent_automations'] == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'schedule',
    [
        {'time': '7am', 'timezone': 'UTC'},
        {'time': '25:00', 'timezone': 'UTC'},
        {'time': '07:60', 'timezone': 'UTC'},
        {'time': '07:30', 'timezone': 'Not/AZone'},
        {'kind': 'weekly', 'time': '07:30', 'timezone': 'UTC'},
        {'timezone': 'UTC'},
        'daily 07:30',
        None,
    ],
)
async def test_create_rejects_bad_schedules(schedule):
    service, db = make_service()
    with pytest.raises(AgentAutomationError) as exc:
        await service.create_automation(
            user_id=USER,
            capability_id='agent.morning_brief',
            schedule=schedule,
        )
    assert exc.value.code == 'INVALID_AUTOMATION_SCHEDULE'
    assert db.tables['agent_automations'] == []


@pytest.mark.asyncio
async def test_create_rejects_non_object_payload():
    service, db = make_service()
    with pytest.raises(AgentAutomationError) as exc:
        await service.create_automation(
            user_id=USER,
            capability_id='agent.morning_brief',
            schedule={'time': '07:30', 'timezone': 'UTC'},
            payload='not-an-object',
        )
    assert exc.value.code == 'INVALID_AUTOMATION_INPUT'


# -- next-run math ----------------------------------------------------------

def test_next_run_later_today_in_local_timezone():
    schedule = normalize_schedule({'time': '07:30', 'timezone': 'America/New_York'})
    # 12:00 UTC is 07:00 EST, so today's 07:30 local is still ahead.
    assert compute_next_run(schedule, after=utc(2026, 11, 9, 12, 0)) == utc(
        2026, 11, 9, 12, 30
    )


def test_next_run_rolls_to_tomorrow_once_local_time_passes():
    schedule = normalize_schedule({'time': '07:30', 'timezone': 'America/New_York'})
    # 13:00 UTC is 08:00 EST; the next 07:30 local is tomorrow.
    assert compute_next_run(schedule, after=utc(2026, 11, 9, 13, 0)) == utc(
        2026, 11, 10, 12, 30
    )


def test_next_run_at_exact_local_time_moves_to_next_day():
    schedule = normalize_schedule({'time': '07:30', 'timezone': 'UTC'})
    assert compute_next_run(schedule, after=utc(2026, 11, 9, 7, 30)) == utc(
        2026, 11, 10, 7, 30
    )


def test_next_run_across_the_date_line():
    schedule = normalize_schedule({'time': '00:30', 'timezone': 'Pacific/Auckland'})
    # 2026-11-09 12:00 UTC is already 2026-11-10 01:00 in Auckland
    # (NZDT, UTC+13), so the next 00:30 local is 2026-11-11 there,
    # which is still 2026-11-10 in UTC.
    assert compute_next_run(schedule, after=utc(2026, 11, 9, 12, 0)) == utc(
        2026, 11, 10, 11, 30
    )
    early = normalize_schedule({'time': '02:00', 'timezone': 'Pacific/Auckland'})
    assert compute_next_run(early, after=utc(2026, 11, 9, 12, 0)) == utc(
        2026, 11, 9, 13, 0
    )


@pytest.mark.asyncio
async def test_create_stores_row_with_computed_next_run():
    service, db = make_service()
    created = await service.create_automation(
        user_id=USER,
        capability_id='agent.morning_brief',
        schedule={'time': '07:30', 'timezone': 'America/New_York'},
        now=utc(2026, 11, 9, 13, 0),
    )
    assert created['capabilityId'] == 'agent.morning_brief'
    assert created['schedule'] == {
        'kind': 'daily',
        'time': '07:30',
        'timezone': 'America/New_York',
    }
    assert created['nextRunAt'] == '2026-11-10T12:30:00+00:00'
    assert created['lastRunAt'] is None
    assert created['enabled'] is True
    assert created['payload'] == {}
    assert len(db.tables['agent_automations']) == 1


# -- due selection ----------------------------------------------------------


def _seed_automation(db, *, automation_id, user_id=USER, enabled=True, next_run_at):
    db.tables['agent_automations'].append(
        {
            'id': automation_id,
            'user_id': user_id,
            'capability_id': 'agent.morning_brief',
            'schedule_kind': 'daily',
            'local_time': '07:30',
            'timezone': 'UTC',
            'payload': {},
            'enabled': enabled,
            'last_run_at': None,
            'next_run_at': next_run_at,
            'created_at': '2026-11-09T00:00:00+00:00',
            'updated_at': '2026-11-09T00:00:00+00:00',
        }
    )


@pytest.mark.asyncio
async def test_due_automations_selects_only_enabled_and_due():
    service, db = make_service()
    _seed_automation(db, automation_id='a-due', next_run_at='2026-11-09T07:30:00+00:00')
    _seed_automation(
        db, automation_id='a-future', next_run_at='2026-11-10T07:30:00+00:00'
    )
    _seed_automation(
        db,
        automation_id='a-disabled',
        enabled=False,
        next_run_at='2026-11-09T07:30:00+00:00',
    )
    _seed_automation(db, automation_id='a-unscheduled', next_run_at=None)
    due = await service.due_automations(utc(2026, 11, 9, 12, 0))
    assert [row['id'] for row in due] == ['a-due']


# -- owner isolation ----------------------------------------------------------


@pytest.mark.asyncio
async def test_list_and_delete_are_owner_scoped():
    service, db = make_service()
    created = await service.create_automation(
        user_id=USER,
        capability_id='agent.morning_brief',
        schedule={'time': '07:30', 'timezone': 'UTC'},
        now=utc(2026, 11, 9, 0, 0),
    )
    assert [a['id'] for a in await service.list_automations(user_id=USER)] == [
        created['id']
    ]
    assert await service.list_automations(user_id=OTHER) == []
    with pytest.raises(AgentAutomationError) as exc:
        await service.delete_automation(user_id=OTHER, automation_id=created['id'])
    assert exc.value.code == 'AUTOMATION_NOT_FOUND'
    assert len(db.tables['agent_automations']) == 1
    deleted = await service.delete_automation(
        user_id=USER, automation_id=created['id']
    )
    assert deleted['id'] == created['id']
    assert await service.list_automations(user_id=USER) == []
    with pytest.raises(AgentAutomationError):
        await service.delete_automation(user_id=USER, automation_id=created['id'])


# -- executor -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_executor_morning_brief_run_succeeds():
    db = FakeDB()
    runs = AgentRunService(db)
    executor = AgentExecutor(
        runs,
        google_connector=FakeGoogleConnector(connected=True),
        execution_paused=False,
    )
    run = await runs.create_run(
        user_id=USER,
        capability_id='agent.morning_brief',
        payload={'schedule': 'daily 07:30 America/New_York'},
    )
    assert run['status'] == 'queued'
    result = await executor.execute_run(user_id=USER, run_id=run['id'])
    assert result['status'] == 'succeeded'
    summary = json.loads(result['resultSummary'])
    assert summary['kind'] == 'agent.morning_brief'
    assert summary['googleConnected'] is True
    assert summary['calendar'] == 1
    assert summary['inboxHighlights'] == 1


def test_morning_brief_is_live_and_free():
    capability = require_capability('agent.morning_brief')
    assert capability.status == 'live'
    assert capability.credit_cost_kind == 'none'
    assert capability.credit_cost is None


# -- run-due endpoint ---------------------------------------------------------


@pytest.fixture
def run_due_context(monkeypatch):
    db = FakeDB()
    runs = AgentRunService(db)
    automations = AgentAutomationService(db)
    monkeypatch.setattr(agent_routes, 'db', db)
    monkeypatch.setattr(agent_routes, 'agent_runs', runs)
    monkeypatch.setattr(
        agent_routes, 'settings', SimpleNamespace(cron_secret=CRON_SECRET)
    )
    monkeypatch.setattr(
        agent_routes,
        '_google_connector',
        lambda: FakeGoogleConnector(connected=True),
    )
    # The endpoint's happy-path test exercises dispatch, so it uses an
    # executor with the production pause explicitly lifted; the paused
    # due-work behavior is covered in tests/test_agent_execution_pause.py.
    monkeypatch.setattr(
        agent_routes,
        '_executor',
        lambda: AgentExecutor(
            runs,
            google_connector=FakeGoogleConnector(connected=True),
            execution_paused=False,
        ),
    )
    return db, runs, automations


@pytest.mark.asyncio
async def test_run_due_endpoint_executes_a_due_morning_brief(run_due_context):
    db, runs, automations = run_due_context
    created = await automations.create_automation(
        user_id=USER,
        capability_id='agent.morning_brief',
        schedule={'time': '07:30', 'timezone': 'UTC'},
        now=utc(2020, 1, 1, 0, 0),
    )
    assert created['nextRunAt'] == '2020-01-01T07:30:00+00:00'

    response = CLIENT.post(
        '/api/internal/agent/automations/run-due',
        headers={'Authorization': f'Bearer {CRON_SECRET}'},
    )
    assert response.status_code == 200
    body = response.json()
    assert body['success'] is True
    assert body['due'] == 1
    assert body['triggered'] == 1
    assert body['errors'] == 0
    assert body['runs'][0]['automationId'] == created['id']
    assert body['runs'][0]['status'] == 'succeeded'

    stored_runs = db.tables['agent_runs']
    assert len(stored_runs) == 1
    assert stored_runs[0]['capability_id'] == 'agent.morning_brief'
    assert stored_runs[0]['status'] == 'succeeded'
    summary = json.loads(stored_runs[0]['result_summary'])
    assert summary['kind'] == 'agent.morning_brief'

    row = db.tables['agent_automations'][0]
    assert row['last_run_at'] is not None
    assert row['next_run_at'] > row['last_run_at']
    # The automation is no longer due on a second pass.
    assert await automations.due_automations(datetime.now(timezone.utc)) == []


def test_run_due_endpoint_rejects_missing_and_wrong_secrets(run_due_context):
    db, runs, automations = run_due_context
    missing = CLIENT.post('/api/internal/agent/automations/run-due')
    assert missing.status_code == 401
    assert missing.json() == {'success': False, 'error': 'Unauthorized.'}
    wrong = CLIENT.post(
        '/api/internal/agent/automations/run-due',
        headers={'Authorization': 'Bearer not-the-secret'},
    )
    assert wrong.status_code == 401
    assert db.tables['agent_runs'] == []


def test_run_due_endpoint_rejects_when_secret_unconfigured(
    run_due_context, monkeypatch
):
    db, runs, automations = run_due_context
    monkeypatch.setattr(
        agent_routes, 'settings', SimpleNamespace(cron_secret=None)
    )
    response = CLIENT.post(
        '/api/internal/agent/automations/run-due',
        headers={'Authorization': f'Bearer {CRON_SECRET}'},
    )
    assert response.status_code == 401
    assert db.tables['agent_runs'] == []


# -- migration + routes -------------------------------------------------------


def test_automations_migration_declares_table_and_rls():
    normalized = MIGRATION.lower()
    assert 'create table if not exists public.agent_automations' in normalized
    assert (
        'user_id uuid not null references public.users(id) on delete cascade'
        in normalized
    )
    assert 'alter table public.agent_automations enable row level security' in normalized
    assert (
        'revoke all privileges on public.agent_automations from anon, authenticated'
        in normalized
    )
    for column in ('capability_id', 'payload', 'enabled', 'last_run_at', 'next_run_at'):
        assert column in normalized


def test_automation_routes_are_registered():
    actual = {
        (method, route.path)
        for route in iter_effective_routes(app_module.app)
        for method in getattr(route, 'methods', set())
        if method not in {'HEAD', 'OPTIONS'}
    }
    assert ('GET', '/api/agent/automations') in actual
    assert ('POST', '/api/agent/automations') in actual
    assert ('DELETE', '/api/agent/automations/{automation_id}') in actual
    assert ('POST', '/api/internal/agent/automations/run-due') in actual
    assert ('GET', '/api/internal/agent/automations/run-due') in actual
