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
ledger, and then stamps ``last_run_at`` / ``next_run_at`` here. The
claim/confirm discipline is an outbox split in two steps: a claim is
only a lease (it never advances the schedule), and the schedule
advances solely in ``confirm_run_created``, after the run row exists.
A process that dies between the two leaves the occurrence due with an
expiring lease, so the next pass recovers it instead of the schedule
silently consuming it.
"""
from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
import json
import logging
import re
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .agent_registry import get_capability
from .db import SupabaseDB, eq, gt, in_, lte
from .security import iso_now, new_uuid

logger = logging.getLogger('askcrump.agent_automations')

# Capabilities a standing schedule may run unattended. A capability
# joins this set only when its registry approval mode allows standing
# rules and it needs no per-run user input.
SCHEDULABLE_CAPABILITIES = frozenset({'agent.morning_brief'})

SCHEDULE_KINDS = frozenset({'daily'})
MAX_PAYLOAD_BYTES = 16000
MAX_DUE_PER_PASS = 100
# The due scan discovers candidates tenant block by tenant block
# (see ``due_automations``), paging within a block in keyset pages
# of this size on the composite (next_run_at, id) cursor. A block
# page is several times the per-tenant cap, so a tenant normally
# costs the scan a single page; the rest of its block is skipped
# unread once the cap is reached.
DUE_DISCOVERY_PAGE = 200
# Upper bound on select calls one due scan may make per pass —
# block heads plus block pages. The bound caps work per pass, not
# coverage: blocks are visited in tenant order and every tenant's
# oldest rows are reached within a few calls each, so the bound
# is only approached when hundreds of tenants are due at once.
MAX_DUE_DISCOVERY_QUERIES = 400
# A claim lease is stamped into ``updated_at`` as a short-lived future
# instant. While that instant is still ahead the row is leased to the
# claiming pass; once it passes with no run created, the lease is
# expired and any later pass may claim the occurrence again.
CLAIM_LEASE = timedelta(seconds=120)

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


def _parse_timestamp(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _lease_active(row: dict[str, Any], *, now: datetime) -> bool:
    """Whether ``row`` currently carries a live claim lease.

    A lease is the one deliberate future ``updated_at`` a claim writes
    (``now + CLAIM_LEASE`` at claim time). Ordinary updates stamp the
    current instant, so only a timestamp ahead of ``now`` — and no
    further ahead than one lease — reads as a lease; anything else,
    including implausibly far-future values, is not one.
    """
    updated = _parse_timestamp(row.get('updated_at'))
    if updated is None:
        return False
    return now < updated <= now + CLAIM_LEASE


def _fair_window(
    rows: list[dict[str, Any]], limit: int
) -> list[dict[str, Any]]:
    """Select up to ``limit`` rows round-robin across tenants.

    ``rows`` arrives oldest-first. Each tenant contributes its oldest
    remaining row per round, so no tenant's backlog can consume the
    whole pass window while another tenant's due row waits: with at
    least as many slots as tenants, every tenant's oldest due row is
    always reached.
    """
    by_user: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_user.setdefault(str(row.get('user_id') or ''), []).append(row)
    selected: list[dict[str, Any]] = []
    rank = 0
    while len(selected) < limit:
        progressed = False
        for bucket in by_user.values():
            if rank < len(bucket):
                selected.append(bucket[rank])
                progressed = True
                if len(selected) >= limit:
                    break
        if not progressed:
            break
        rank += 1
    return selected


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

    @staticmethod
    def occurrence_conversation_id(row: dict[str, Any]) -> str:
        """Stable identity of one scheduled occurrence of an automation.

        The run ledger's ``conversation_id`` column is the run record's
        free-text slot (capped at 160 characters, validated at run
        creation), and the automation run payload itself cannot carry
        extra keys — the capability schemas are closed — so the
        occurrence key rides there: automation id plus the scheduled
        instant the row carried when the occurrence came due. Every
        pass derives the same key for the same occurrence, which is
        what lets a later pass find the run an earlier pass created
        instead of minting a second one.
        """
        return (
            f"automation:{row.get('id')}:{row.get('next_run_at') or ''}"
        )[:160]

    @staticmethod
    def terminal_invalid_reason(row: dict[str, Any]) -> str | None:
        """Error code when a due row can never produce a run, else None.

        Terminal invalidity is a property of the stored row and the
        registry alone: an unknown or unschedulable capability, a
        capability that is no longer live, a malformed schedule, or a
        stored payload that fails the automation input rules. Anything
        that depends on the moment — a paused executor, a provider or
        database outage, an entitlement or balance change — is
        transient, is not classified here, and leaves the row due.
        """
        capability_id = str(row.get('capability_id') or '')
        capability = get_capability(capability_id) if capability_id else None
        if capability is None:
            return 'CAPABILITY_NOT_FOUND'
        if capability.id not in SCHEDULABLE_CAPABILITIES:
            return 'AUTOMATION_CAPABILITY_NOT_SCHEDULABLE'
        if capability.status != 'live':
            return 'CAPABILITY_NOT_LIVE'
        try:
            normalize_schedule(
                {
                    'kind': row.get('schedule_kind') or 'daily',
                    'time': row.get('local_time'),
                    'timezone': row.get('timezone') or 'UTC',
                }
            )
            _validate_payload(row.get('payload'))
        except AgentAutomationError as exc:
            return exc.code
        return None

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
        """Enabled automations whose next run is at or before ``now``.

        The scan discovers candidates tenant block by tenant block
        instead of reading one global oldest-first window: a single
        window lets a tenant with more due rows than the window
        holds fill it entirely, and every other tenant starves
        outside it no matter how the results are later balanced.
        Blocks are visited in tenant order; within a block, rows
        are paged oldest-first on the stable composite
        ``(next_run_at, id)`` cursor, so a block of rows sharing
        one exact timestamp is walked completely, row by row,
        however wide the tie is. Each tenant contributes at most
        ``pass_limit`` candidates, and once a tenant reaches the
        cap the rest of its block is skipped unread — a backlog
        costs the scan at most a page past the cap, so the cap
        sits below the read horizon by construction and every
        tenant's oldest due rows are reached in the same pass.
        The round-robin window (see ``_fair_window``) then selects
        from the candidates. Rows carrying a live claim lease are
        not due for this pass: another pass is creating (or
        crashed creating) their run, and the lease decides when
        they surface again.

        Discovery reads narrow rows (id, tenant, schedule stamp,
        lease stamp); the candidates' full rows are fetched
        afterwards and re-validated, since a row can move between
        the two reads. The claim compare-and-swap downstream is
        the fence that keeps that race safe.
        """
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        pass_limit = max(
            1, min(int(limit or MAX_DUE_PER_PASS), MAX_DUE_PER_PASS)
        )
        now_iso = now.isoformat()
        candidate_ids = await self._discover_due_candidates(
            now, now_iso, pass_limit
        )
        if not candidate_ids:
            return []
        rows = await self._fetch_candidate_rows(candidate_ids, now, now_iso)
        return _fair_window(rows, pass_limit)

    async def _discover_due_candidates(
        self, now: datetime, now_iso: str, pass_limit: int
    ) -> list[str]:
        """Candidate row ids for one pass, oldest first per tenant.

        Walks tenant blocks in tenant order under a per-pass query
        budget (see ``MAX_DUE_DISCOVERY_QUERIES``). A tenant whose
        rows are all leased or not yet due contributes nothing and
        costs one block scan; a flooded tenant costs one page past
        its cap.
        """
        candidates: list[str] = []
        queries = 0
        cursor_user: str | None = None
        while queries < MAX_DUE_DISCOVERY_QUERIES:
            filters: dict[str, Any] = {
                'enabled': eq(True),
                'next_run_at': lte(now_iso),
            }
            if cursor_user is not None:
                filters['user_id'] = gt(cursor_user)
            head = await self.db.select(
                'agent_automations',
                columns='id,user_id,next_run_at,updated_at',
                filters=filters,
                order='user_id.asc,next_run_at.asc,id.asc',
                limit=1,
            )
            queries += 1
            if not head:
                break
            tenant = str(head[0].get('user_id') or '')
            cursor_user = tenant
            taken = 0
            cursor: tuple[str, str] | None = None
            while taken < pass_limit and queries < MAX_DUE_DISCOVERY_QUERIES:
                page, cursor, used = await self._due_block_page(
                    tenant, now_iso, cursor
                )
                queries += used
                if not page:
                    break
                block_done = cursor is None
                for row in page:
                    if str(row.get('next_run_at') or '') > now_iso:
                        # Oldest first within the block: nothing
                        # later in it is due either.
                        block_done = True
                        break
                    if _lease_active(row, now=now):
                        continue
                    candidates.append(str(row.get('id')))
                    taken += 1
                    if taken >= pass_limit:
                        break
                if block_done:
                    break
        return candidates

    async def _due_block_page(
        self,
        tenant: str,
        now_iso: str,
        cursor: tuple[str, str] | None,
    ) -> tuple[list[dict[str, Any]], tuple[str, str] | None, int]:
        """One keyset page within one tenant's block of due rows.

        The cursor is the composite ``(next_run_at, id)`` of the
        last row read, so a page ending inside a block of rows
        sharing one timestamp continues within the tie (same
        stamp, greater id) instead of skipping the rest of it.
        Returns the page — sorted by ``(next_run_at, id)`` — the
        next cursor (None when the block is exhausted), and how
        many select calls the page took.
        """
        base: dict[str, Any] = {'enabled': eq(True), 'user_id': eq(tenant)}
        columns = 'id,user_id,next_run_at,updated_at'
        order = 'next_run_at.asc,id.asc'
        if cursor is None:
            rows = await self.db.select(
                'agent_automations',
                columns=columns,
                filters={**base, 'next_run_at': lte(now_iso)},
                order=order,
                limit=DUE_DISCOVERY_PAGE,
            )
            used = 1
        else:
            cursor_ts, cursor_id = cursor
            tie = await self.db.select(
                'agent_automations',
                columns=columns,
                filters={
                    **base,
                    'next_run_at': eq(cursor_ts),
                    'id': gt(cursor_id),
                },
                order=order,
                limit=DUE_DISCOVERY_PAGE,
            )
            used = 1
            rows = list(tie)
            remaining = DUE_DISCOVERY_PAGE - len(tie)
            if remaining > 0:
                rest = await self.db.select(
                    'agent_automations',
                    columns=columns,
                    filters={**base, 'next_run_at': gt(cursor_ts)},
                    order=order,
                    limit=remaining,
                )
                used += 1
                rows += rest
        rows = sorted(
            rows,
            key=lambda row: (
                str(row.get('next_run_at') or ''),
                str(row.get('id') or ''),
            ),
        )
        if len(rows) < DUE_DISCOVERY_PAGE:
            return rows, None, used
        last = rows[-1]
        return rows, (str(last.get('next_run_at')), str(last.get('id'))), used

    async def _fetch_candidate_rows(
        self, candidate_ids: list[str], now: datetime, now_iso: str
    ) -> list[dict[str, Any]]:
        """Full rows for discovered candidates, in discovery order.

        Re-validated against the present: a row disabled, advanced,
        or leased since discovery is dropped here, and the claim
        compare-and-swap remains the fence for anything that moves
        after this read.
        """
        by_id: dict[str, dict[str, Any]] = {}
        for start in range(0, len(candidate_ids), 250):
            chunk = candidate_ids[start:start + 250]
            rows = await self.db.select(
                'agent_automations',
                filters={'id': in_(chunk)},
                limit=len(chunk),
            )
            for row in rows:
                by_id[str(row.get('id'))] = row
        selected: list[dict[str, Any]] = []
        for candidate_id in candidate_ids:
            row = by_id.get(candidate_id)
            if row is None:
                continue
            if (
                not row.get('enabled')
                or not row.get('next_run_at')
                or str(row['next_run_at']) > now_iso
                or _lease_active(row, now=now)
            ):
                continue
            selected.append(row)
        return selected

    async def claim_due_automation(
        self, row: dict[str, Any], *, ran_at: datetime
    ) -> dict[str, Any] | None:
        """Lease a due automation to this pass; never advances it.

        The lease is a compare-and-swap stamping only ``updated_at``
        with the lease expiry instant (see ``CLAIM_LEASE``): the
        update lands only while the row still carries the
        ``next_run_at`` and ``updated_at`` this pass observed (and is
        still enabled), so when two run-due passes race over the same
        due automation exactly one of them holds the lease. The loser
        gets ``None`` — already claimed — and must not create a run
        for it. A row whose previous lease has expired (its claimant
        died before creating a run) is claimable again, which is how
        a crashed pass's occurrence is recovered instead of consumed.

        The schedule itself advances only in ``confirm_run_created``,
        after the run exists; a caller whose run creation fails hands
        the lease back with ``release_claim`` so the automation stays
        due for the next pass.
        """
        if not row.get('next_run_at') or _lease_active(row, now=ran_at):
            return None
        lease_stamp = (ran_at.astimezone(timezone.utc) + CLAIM_LEASE).isoformat()
        updated = await self.db.update(
            'agent_automations',
            {'updated_at': lease_stamp},
            filters={
                'id': eq(row['id']),
                'user_id': eq(row['user_id']),
                'enabled': eq(True),
                'next_run_at': eq(row.get('next_run_at')),
                'updated_at': eq(row.get('updated_at')),
            },
        )
        if isinstance(updated, list) and updated:
            return updated[0]
        return None

    async def release_claim(
        self, row: dict[str, Any], claimed: dict[str, Any]
    ) -> None:
        """Hand a lease back after a failed run creation, best effort.

        The claim never touched the schedule, so releasing only
        restores the pre-claim ``updated_at`` — filtered on the lease
        stamp, so a row another pass has since claimed or advanced
        is left alone. A failed release just lets the lease expire,
        which is the safe direction: the occurrence stays due and is
        retried once the lease lapses.
        """
        await self.db.update(
            'agent_automations',
            {'updated_at': row.get('updated_at') or iso_now()},
            filters={
                'id': eq(row['id']),
                'user_id': eq(row['user_id']),
                'next_run_at': eq(row.get('next_run_at')),
                'updated_at': eq(claimed.get('updated_at')),
            },
        )

    async def confirm_run_created(
        self,
        row: dict[str, Any],
        claimed: dict[str, Any],
        *,
        ran_at: datetime,
    ) -> dict[str, Any] | None:
        """Advance the schedule now that the occurrence's run exists.

        This is the sole schedule-advancing step of a claimed pass,
        and it is fenced by the lease: the stamp lands only while the
        row still carries the observed ``next_run_at`` under this
        pass's lease stamp, so a stale claimant cannot advance a row
        another pass has already handled. ``None`` means the advance
        already happened (or the row moved on) — the run exists
        either way, which is what the confirmation exists to prove.
        """
        return await self.record_run(
            row,
            ran_at=ran_at,
            expected_next_run_at=row.get('next_run_at'),
            expected_updated_at=claimed.get('updated_at'),
        )

    async def confirm_existing_run(
        self, row: dict[str, Any], *, ran_at: datetime
    ) -> dict[str, Any] | None:
        """Advance the schedule for a run an earlier pass created.

        Used when a pass finds the occurrence's run already in the
        ledger but the row still due — the earlier pass died after
        creating the run and before confirming it. The stamp is the
        same compare-and-swap on the observed ``next_run_at``;
        ``None`` means another pass already advanced it.
        """
        return await self.record_run(
            row,
            ran_at=ran_at,
            expected_next_run_at=row.get('next_run_at'),
        )

    async def disable_automation(
        self, row: dict[str, Any], *, reason: str
    ) -> bool:
        """Durably exclude a terminally invalid automation from due scans.

        Disabling is fenced on the observed ``next_run_at`` so a row
        another pass has advanced is left alone. The reason is
        recorded in the service log with the row's identity; the row
        itself keeps its payload untouched for the owner to inspect
        or delete.
        """
        updated = await self.db.update(
            'agent_automations',
            {'enabled': False, 'updated_at': iso_now()},
            filters={
                'id': eq(row['id']),
                'user_id': eq(row['user_id']),
                'enabled': eq(True),
                'next_run_at': eq(row.get('next_run_at')),
            },
        )
        if isinstance(updated, list) and updated:
            logger.warning(
                'Automation disabled automation_id=%s user_id=%s reason=%s',
                row.get('id'),
                row.get('user_id'),
                reason,
            )
            return True
        return False

    async def record_run(
        self,
        row: dict[str, Any],
        *,
        ran_at: datetime,
        expected_next_run_at: Any = None,
        expected_updated_at: Any = None,
    ) -> dict[str, Any] | None:
        """Stamp a triggered automation and advance its schedule.

        With ``expected_next_run_at`` / ``expected_updated_at`` the
        stamp is a compare-and-swap (see ``confirm_run_created``):
        zero updated rows means the row no longer carries the
        observed values, and the call returns ``None`` instead of a
        stamped row.
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
        if expected_updated_at is not None:
            filters['updated_at'] = eq(expected_updated_at)
        updated = await self.db.update(
            'agent_automations',
            updates,
            filters=filters,
        )
        if isinstance(updated, list) and updated:
            return updated[0]
        if expected_next_run_at is not None or expected_updated_at is not None:
            return None
        return {**row, **updates}
