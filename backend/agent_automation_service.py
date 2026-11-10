"""User automations: standing daily schedules for agent capabilities.

An automation is the durable form of a standing rule the user set —
"brief me every morning" — stored as one row naming a capability, a
daily local time, and a timezone. This increment keeps the model
deliberately small: the only schedule kind is ``daily`` and the only
schedulable capability is ``agent.morning_brief``. Anything else fails
closed with a specific error code instead of being stored and silently
never running.

The cron trigger (see ``routes/agent.py``) asks this service for due
automations, creates and executes a run for each through the run
ledger, and then stamps ``last_run_at`` / ``next_run_at`` here, so the
schedule advances exactly once per trigger pass.
"""
from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
import json
import re
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .agent_registry import get_capability
from .db import SupabaseDB, eq, lte
from .security import iso_now, new_uuid

# Capabilities a standing schedule may run unattended. A capability
# joins this set only when its registry approval mode allows standing
# rules and it needs no per-run user input.
SCHEDULABLE_CAPABILITIES = frozenset({'agent.morning_brief'})

SCHEDULE_KINDS = frozenset({'daily'})
MAX_PAYLOAD_BYTES = 16000
MAX_DUE_PER_PASS = 100

_TIME_RE = re.compile(r'^([01][0-9]|2[0-3]):([0-5][0-9])$')


class AgentAutomationError(RuntimeError):
    def __init__(
        self, message: str, status_code: int = 400, code: str = 'AGENT_AUTOMATION_ERROR'
    ):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code


class AgentAutomationNotFoundError(AgentAutomationError):
    def __init__(self, message: str = 'Automation not found.'):
        super().__init__(message, 404, 'AUTOMATION_NOT_FOUND')


def _parse_local_time(value: Any) -> tuple[int, int]:
    match = _TIME_RE.match(str(value or '').strip())
    if match is None:
        raise AgentAutomationError(
            'Schedule time must be a daily local time in HH:MM format.',
            400,
            'INVALID_AUTOMATION_SCHEDULE',
        )
    return int(match.group(1)), int(match.group(2))


def _load_timezone(value: Any) -> ZoneInfo:
    name = str(value or '').strip()
    if not name or len(name) > 64:
        raise AgentAutomationError(
            'Schedule timezone must be a valid IANA timezone name.',
            400,
            'INVALID_AUTOMATION_SCHEDULE',
        )
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        raise AgentAutomationError(
            'Schedule timezone must be a valid IANA timezone name.',
            400,
            'INVALID_AUTOMATION_SCHEDULE',
        ) from None


def normalize_schedule(raw: Any) -> dict[str, Any]:
    """Validate a schedule spec and return its canonical stored shape."""
    if not isinstance(raw, dict):
        raise AgentAutomationError(
            'A schedule with a daily local time and timezone is required.',
            400,
            'INVALID_AUTOMATION_SCHEDULE',
        )
    kind = str(raw.get('kind') or 'daily').strip()
    if kind not in SCHEDULE_KINDS:
        raise AgentAutomationError(
            'Only daily schedules are supported right now.',
            400,
            'INVALID_AUTOMATION_SCHEDULE',
        )
    hour, minute = _parse_local_time(raw.get('time'))
    zone = _load_timezone(raw.get('timezone') or 'UTC')
    return {
        'kind': kind,
        'time': f'{hour:02d}:{minute:02d}',
        'timezone': str(zone),
    }


def compute_next_run(schedule: dict[str, Any], *, after: datetime) -> datetime:
    """Next daily occurrence of the schedule strictly after ``after``.

    The local time is interpreted in the schedule's timezone; the
    result is an aware UTC datetime. A local time that falls in a
    daylight-saving gap resolves with the pre-transition offset, which
    keeps the computed instant within the gap hour rather than
    skipping a day.
    """
    if after.tzinfo is None:
        after = after.replace(tzinfo=timezone.utc)
    hour, minute = _parse_local_time(schedule.get('time'))
    zone = _load_timezone(schedule.get('timezone') or 'UTC')
    local_after = after.astimezone(zone)
    candidate = datetime.combine(
        local_after.date(), time(hour=hour, minute=minute), tzinfo=zone
    )
    if candidate <= local_after:
        candidate = datetime.combine(
            local_after.date() + timedelta(days=1),
            time(hour=hour, minute=minute),
            tzinfo=zone,
        )
    return candidate.astimezone(timezone.utc)


def _validate_payload(payload: Any) -> dict[str, Any]:
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise AgentAutomationError(
            'Automation input must be an object.', 400, 'INVALID_AUTOMATION_INPUT'
        )
    if len(json.dumps(payload, default=str).encode()) > MAX_PAYLOAD_BYTES:
        raise AgentAutomationError(
            'Automation input is too large.', 400, 'INVALID_AUTOMATION_INPUT'
        )
    return payload


class AgentAutomationService:
    def __init__(self, db: SupabaseDB) -> None:
        self.db = db

    # -- shape ------------------------------------------------------------
    @staticmethod
    def public_automation(row: dict[str, Any]) -> dict[str, Any]:
        return {
            'id': row.get('id'),
            'capabilityId': row.get('capability_id'),
            'schedule': {
                'kind': row.get('schedule_kind') or 'daily',
                'time': row.get('local_time'),
                'timezone': row.get('timezone'),
            },
            'payload': row.get('payload') or {},
            'enabled': bool(row.get('enabled')),
            'lastRunAt': row.get('last_run_at'),
            'nextRunAt': row.get('next_run_at'),
            'createdAt': row.get('created_at'),
            'updatedAt': row.get('updated_at'),
        }

    @staticmethod
    def run_payload_for(row: dict[str, Any]) -> dict[str, Any]:
        """Build the run payload for a due automation.

        The registry requires ``schedule`` for ``agent.morning_brief``;
        when the stored payload does not carry one, the standing
        schedule itself is the value of record.
        """
        payload = dict(row.get('payload') or {})
        if 'schedule' not in payload:
            payload['schedule'] = (
                f"{row.get('schedule_kind') or 'daily'} "
                f"{row.get('local_time') or ''} "
                f"{row.get('timezone') or 'UTC'}"
            ).strip()
        return payload

    # -- CRUD ---------------------------------------------------------------
    async def create_automation(
        self,
        *,
        user_id: str,
        capability_id: str,
        schedule: Any,
        payload: Any = None,
        enabled: bool = True,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        capability = get_capability(capability_id)
        if capability is None:
            raise AgentAutomationError(
                'That capability is not available.', 404, 'CAPABILITY_NOT_FOUND'
            )
        if capability.id not in SCHEDULABLE_CAPABILITIES:
            raise AgentAutomationError(
                'That capability cannot be scheduled yet.',
                400,
                'AUTOMATION_CAPABILITY_NOT_SCHEDULABLE',
            )
        normalized = normalize_schedule(schedule)
        payload = _validate_payload(payload)
        moment = now or datetime.now(timezone.utc)
        next_run = compute_next_run(normalized, after=moment)
        timestamp = iso_now()
        row = {
            'id': new_uuid(),
            'user_id': user_id,
            'capability_id': capability.id,
            'schedule_kind': normalized['kind'],
            'local_time': normalized['time'],
            'timezone': normalized['timezone'],
            'payload': payload,
            'enabled': bool(enabled),
            'last_run_at': None,
            'next_run_at': next_run.isoformat(),
            'created_at': timestamp,
            'updated_at': timestamp,
        }
        await self.db.insert('agent_automations', row)
        return self.public_automation(row)

    async def list_automations(self, *, user_id: str) -> list[dict[str, Any]]:
        rows = await self.db.select(
            'agent_automations',
            filters={'user_id': eq(user_id)},
            order='created_at.desc',
            limit=100,
        )
        return [self.public_automation(row) for row in rows]

    async def _get_owned(
        self, *, user_id: str, automation_id: str
    ) -> dict[str, Any]:
        row = await self.db.select_one(
            'agent_automations',
            filters={'id': eq(str(automation_id)), 'user_id': eq(user_id)},
        )
        if not row:
            raise AgentAutomationNotFoundError()
        return row

    async def delete_automation(
        self, *, user_id: str, automation_id: str
    ) -> dict[str, Any]:
        row = await self._get_owned(user_id=user_id, automation_id=automation_id)
        await self.db.delete(
            'agent_automations',
            filters={'id': eq(row['id']), 'user_id': eq(user_id)},
        )
        return self.public_automation(row)

    # -- trigger support ----------------------------------------------------
    async def due_automations(
        self, now: datetime, *, limit: int = MAX_DUE_PER_PASS
    ) -> list[dict[str, Any]]:
        """Enabled automations whose next run is at or before ``now``."""
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        rows = await self.db.select(
            'agent_automations',
            filters={'enabled': eq(True), 'next_run_at': lte(now.isoformat())},
            order='next_run_at.asc',
            limit=max(1, min(int(limit or MAX_DUE_PER_PASS), MAX_DUE_PER_PASS)),
        )
        # Guard against rows whose stored timestamp does not compare
        # due (for example a null next_run_at on a legacy row).
        due = [
            row
            for row in rows
            if row.get('next_run_at') and str(row['next_run_at']) <= now.isoformat()
        ]
        return due

    async def claim_due_automation(
        self, row: dict[str, Any], *, ran_at: datetime
    ) -> dict[str, Any] | None:
        """Claim a due automation for this pass and advance its schedule.

        The claim is a compare-and-swap in the same discipline as the
        run ledger's claim: the update only lands while the row still
        carries the ``next_run_at`` this pass observed (and is still
        enabled), so when two run-due passes race over the same due
        automation exactly one of them stamps it forward. The loser
        gets ``None`` — already claimed — and must not create a run
        for it. Claiming stamps ``last_run_at`` / ``next_run_at``
        exactly the way ``record_run`` does; a caller whose run then
        fails hands the claim back with ``release_claim`` so the
        automation stays due for the next pass.
        """
        claimed = await self.record_run(
            row,
            ran_at=ran_at,
            expected_next_run_at=row.get('next_run_at'),
        )
        return claimed

    async def release_claim(
        self, row: dict[str, Any], claimed: dict[str, Any]
    ) -> None:
        """Hand a claim back after a failed run, best effort.

        Restores the schedule values the row carried before the claim,
        filtered on the claimed ``next_run_at`` so a row another pass
        has since advanced is left alone. A failed release leaves the
        schedule advanced — the run was attempted and its outcome is
        in the ledger — which is the safe direction.
        """
        updates = {
            'last_run_at': row.get('last_run_at'),
            'next_run_at': row.get('next_run_at'),
            'updated_at': iso_now(),
        }
        await self.db.update(
            'agent_automations',
            updates,
            filters={
                'id': eq(row['id']),
                'user_id': eq(row['user_id']),
                'next_run_at': eq(claimed.get('next_run_at')),
            },
        )

    async def record_run(
        self,
        row: dict[str, Any],
        *,
        ran_at: datetime,
        expected_next_run_at: Any = None,
    ) -> dict[str, Any] | None:
        """Stamp a triggered automation and advance its schedule.

        With ``expected_next_run_at`` the stamp is a compare-and-swap
        (see ``claim_due_automation``): zero updated rows means the
        row no longer carries the observed schedule value, and the
        call returns ``None`` instead of a stamped row.
        """
        schedule = {
            'kind': row.get('schedule_kind') or 'daily',
            'time': row.get('local_time'),
            'timezone': row.get('timezone') or 'UTC',
        }
        next_run = compute_next_run(schedule, after=ran_at)
        updates = {
            'last_run_at': ran_at.astimezone(timezone.utc).isoformat(),
            'next_run_at': next_run.isoformat(),
            'updated_at': iso_now(),
        }
        filters: dict[str, Any] = {
            'id': eq(row['id']),
            'user_id': eq(row['user_id']),
        }
        if expected_next_run_at is not None:
            filters['enabled'] = eq(True)
            filters['next_run_at'] = eq(expected_next_run_at)
        updated = await self.db.update(
            'agent_automations',
            updates,
            filters=filters,
        )
        if isinstance(updated, list) and updated:
            return updated[0]
        if expected_next_run_at is not None:
            return None
        return {**row, **updates}
