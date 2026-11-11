"""Durable agent run ledger and approval service.

A run is one user outcome requested through a registered capability.
Steps are append-only: the Tasks view and the audit trail read from the
ledger, never from chat text. Capabilities that require an approval
card create a pending action holding the exact payload; approving it
executes that stored payload exactly, so the payload is frozen here at
creation and can only change through an explicit user edit, which
re-validates against the capability schema's required fields.

Execution adapters (Gmail, Calendar, browser, and the other registry
connectors) claim queued runs in a later increment. This service owns
the lifecycle every adapter shares: queued, waiting_approval,
waiting_user, running, succeeded, failed, cancelled.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import re
from typing import Any

from .agent_registry import Capability, get_capability
from .auth_service import is_guest_user, paid_tools_entitled
from .db import SupabaseDB, eq, gt
from .security import iso_now, new_uuid
from .usage_service import credit_status, refund_usage

RUN_STATUSES = frozenset(
    {
        'queued', 'planning', 'running', 'waiting_approval',
        'waiting_user', 'succeeded', 'failed', 'cancelled',
    }
)
TERMINAL_STATUSES = frozenset({'succeeded', 'failed', 'cancelled'})
APPROVAL_TTL = timedelta(hours=24)
MAX_PAYLOAD_BYTES = 16000
# A run whose execution claim (the queued -> running transition) is
# older than this is residue, not work in progress: the claiming
# process died with the run in ``running`` and no executor will ever
# finish it. Reconciliation fails such a run and settles its
# reservation; a younger claim is never touched, because its
# executor may still be working.
STALE_RUNNING_AFTER = timedelta(minutes=15)
# The reconciliation sweep pages its candidate streams in
# (updated_at, id) keyset pages of this size, up to this many pages
# per stream per pass — a bound on work per pass, not on coverage:
# pages are walked oldest-first and reconciled runs stay settled,
# so any residue past the bound is reached on the next pass.
RECONCILE_PAGE_SIZE = 100
RECONCILE_MAX_PAGES = 200


def _parse_run_timestamp(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _running_claim_is_stale(run: dict[str, Any]) -> bool:
    """Whether a ``running`` run's claim has outlived any executor.

    Judged on the run row's ``updated_at`` — the claim transition
    stamps it, and a live executor's own transitions keep it moving.
    An unparseable stamp is never judged stale: recovery does not
    touch what it cannot date.
    """
    updated = _parse_run_timestamp(run.get('updated_at'))
    if updated is None:
        return False
    return updated <= datetime.now(timezone.utc) - STALE_RUNNING_AFTER


class AgentRunError(RuntimeError):
    def __init__(self, message: str, status_code: int = 400, code: str = 'AGENT_RUN_ERROR'):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code


class AgentRunNotFoundError(AgentRunError):
    def __init__(self, message: str = 'Run not found.'):
        super().__init__(message, 404, 'AGENT_RUN_NOT_FOUND')


class AgentActionNotFoundError(AgentRunError):
    def __init__(self, message: str = 'That action is no longer waiting.'):
        super().__init__(message, 404, 'AGENT_ACTION_NOT_FOUND')


class AgentRunConflictError(AgentRunError):
    def __init__(self, message: str):
        super().__init__(message, 409, 'AGENT_RUN_CONFLICT')


def _summarize_input(payload: dict[str, Any]) -> dict[str, Any]:
    """Redacted step/ledger summary: field names and sizes, never values
    that look like message bodies or credentials."""
    summary: dict[str, Any] = {}
    for key, value in payload.items():
        if isinstance(value, str):
            summary[key] = {'type': 'string', 'length': len(value)}
        elif isinstance(value, list):
            summary[key] = {'type': 'array', 'length': len(value)}
        elif isinstance(value, dict):
            summary[key] = {'type': 'object', 'keys': sorted(value)[:20]}
        elif isinstance(value, bool) or value is None or isinstance(value, (int, float)):
            summary[key] = value
        else:
            summary[key] = {'type': type(value).__name__}
    return summary


_EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')

# Run-envelope fields, not capability inputs: the Google account
# binding selectors (see ``google_connector.binding_selectors``) ride
# in the payload of any Google capability's run and are read by the
# executor at execution time, so the closed capability schemas must
# not reject them. They are still type-checked here as strings.
_BINDING_SELECTOR_FIELDS = frozenset(
    {'connectionId', 'connection_id', 'accountEmail', 'account_email'}
)


def _matches_declared_type(value: Any, declared: str) -> bool:
    if declared == 'string':
        return isinstance(value, str)
    if declared == 'integer':
        return isinstance(value, int) and not isinstance(value, bool)
    if declared == 'number':
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if declared == 'boolean':
        return isinstance(value, bool)
    if declared == 'array':
        return isinstance(value, list)
    if declared == 'object':
        return isinstance(value, dict)
    # A declared type this validator does not know is a registry bug,
    # not a caller error; the registry validator owns schema sanity.
    return True


def _is_date_time(value: str) -> bool:
    # The registry's date-time fields carry full RFC 3339 timestamps
    # (for example '2026-11-10T09:00:00-05:00'); a bare date or a
    # free-text value is not one.
    if 'T' not in value and 't' not in value:
        return False
    try:
        datetime.fromisoformat(value)
    except ValueError:
        return False
    return True


def _validate_field(name: str, value: Any, spec: dict[str, Any]) -> None:
    """Enforce one declared property schema against a supplied value."""
    declared = spec.get('type')
    if declared and not _matches_declared_type(value, str(declared)):
        raise AgentRunError(
            f'Invalid input: {name} must be of type {declared}.',
            400,
            'INVALID_RUN_INPUT',
        )
    enum = spec.get('enum')
    if enum is not None and value not in enum:
        raise AgentRunError(
            f"Invalid input: {name} must be one of: "
            f"{', '.join(str(item) for item in enum)}.",
            400,
            'INVALID_RUN_INPUT',
        )
    if isinstance(value, str):
        fmt = spec.get('format')
        if fmt == 'email' and not _EMAIL_RE.match(value):
            raise AgentRunError(
                f'Invalid input: {name} must be a valid email address.',
                400,
                'INVALID_RUN_INPUT',
            )
        if fmt == 'date-time' and not _is_date_time(value):
            raise AgentRunError(
                f'Invalid input: {name} must be a valid date-time.',
                400,
                'INVALID_RUN_INPUT',
            )
        min_length = spec.get('minLength')
        if min_length is not None and len(value) < int(min_length):
            raise AgentRunError(
                f'Invalid input: {name} must be at least '
                f'{min_length} characters long.',
                400,
                'INVALID_RUN_INPUT',
            )
        max_length = spec.get('maxLength')
        if max_length is not None and len(value) > int(max_length):
            raise AgentRunError(
                f'Invalid input: {name} must be at most '
                f'{max_length} characters long.',
                400,
                'INVALID_RUN_INPUT',
            )
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        minimum = spec.get('minimum')
        if minimum is not None and value < minimum:
            raise AgentRunError(
                f'Invalid input: {name} must be at least {minimum}.',
                400,
                'INVALID_RUN_INPUT',
            )
        maximum = spec.get('maximum')
        if maximum is not None and value > maximum:
            raise AgentRunError(
                f'Invalid input: {name} must be at most {maximum}.',
                400,
                'INVALID_RUN_INPUT',
            )
    items = spec.get('items')
    if isinstance(value, list) and isinstance(items, dict):
        for index, item in enumerate(value):
            _validate_field(f'{name}[{index}]', item, items)


def _validate_payload(capability: Capability, payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise AgentRunError('Run input must be an object.', 400, 'INVALID_RUN_INPUT')
    if len(json.dumps(payload, default=str).encode()) > MAX_PAYLOAD_BYTES:
        raise AgentRunError('Run input is too large.', 400, 'INVALID_RUN_INPUT')
    required = capability.input_schema.get('required') or []
    missing = [name for name in required if payload.get(name) in (None, '')]
    if missing:
        raise AgentRunError(
            f"Missing required input: {', '.join(missing)}.",
            400,
            'INVALID_RUN_INPUT',
        )
    schema = capability.input_schema
    properties = schema.get('properties') or {}
    if schema.get('additionalProperties') is False:
        undeclared = sorted(
            name
            for name in payload
            if name not in properties and name not in _BINDING_SELECTOR_FIELDS
        )
        if undeclared:
            raise AgentRunError(
                f"Unexpected input: {', '.join(undeclared)}.",
                400,
                'INVALID_RUN_INPUT',
            )
    for name, value in payload.items():
        spec = properties.get(name)
        if isinstance(spec, dict):
            _validate_field(name, value, spec)
        elif name in _BINDING_SELECTOR_FIELDS and value is not None:
            _validate_field(name, value, {'type': 'string'})
    return payload


class AgentRunService:
    def __init__(
        self,
        db: SupabaseDB,
        *,
        enforce_capability_status: bool = True,
        enforce_access: bool = True,
    ) -> None:
        self.db = db
        # Registry status is enforced at run creation: only live
        # capabilities may create runs. Production wiring never opts
        # out; the flag exists so adapter unit tests can set up runs
        # for capabilities that are not live yet.
        self.enforce_capability_status = enforce_capability_status
        # Registry entitlement and credit cost are enforced at run
        # creation and again at execution time (see
        # ``enforce_capability_access``). Production wiring never opts
        # out; the flag exists so adapter unit tests can set up runs
        # without seeding account and billing rows.
        self.enforce_access = enforce_access

    # -- shape ------------------------------------------------------------
    @staticmethod
    def public_run(row: dict[str, Any]) -> dict[str, Any]:
        return {
            'id': row.get('id'),
            'capabilityId': row.get('capability_id'),
            'status': row.get('status'),
            'projectId': row.get('project_id'),
            'conversationId': row.get('conversation_id'),
            'inputSummary': row.get('input_summary') or {},
            'resultSummary': row.get('result_summary'),
            'creditCost': row.get('credit_cost'),
            'createdAt': row.get('created_at'),
            'updatedAt': row.get('updated_at'),
        }

    @staticmethod
    def public_action(row: dict[str, Any]) -> dict[str, Any]:
        return {
            'id': row.get('id'),
            'runId': row.get('run_id'),
            'capabilityId': row.get('capability_id'),
            'summary': row.get('rendered_summary'),
            'payload': row.get('exact_payload') or {},
            'creditCost': row.get('credit_cost'),
            'status': row.get('status'),
            'expiresAt': row.get('expires_at'),
            'decidedAt': row.get('decided_at'),
            'createdAt': row.get('created_at'),
        }

    @staticmethod
    def public_step(row: dict[str, Any]) -> dict[str, Any]:
        return {
            'id': row.get('id'),
            'capabilityId': row.get('capability_id'),
            'type': row.get('step_type'),
            'payload': row.get('payload') or {},
            'createdAt': row.get('created_at'),
        }

    # -- internals ----------------------------------------------------------
    async def _record_step(
        self,
        *,
        run: dict[str, Any],
        step_type: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        await self.db.insert(
            'agent_run_steps',
            {
                'run_id': run['id'],
                'user_id': run['user_id'],
                'capability_id': run['capability_id'],
                'step_type': step_type,
                'payload': payload or {},
            },
        )

    async def _set_status(
        self,
        run: dict[str, Any],
        status: str,
        *,
        expected_status: str | None = None,
    ) -> dict[str, Any]:
        if status not in RUN_STATUSES:
            raise AgentRunError(f'Unknown run status: {status}', 500, 'AGENT_RUN_ERROR')
        filters: dict[str, Any] = {'id': eq(run['id']), 'user_id': eq(run['user_id'])}
        if expected_status is not None:
            # Compare-and-swap: the transition only lands while the run
            # is still in the state the caller observed. Zero updated
            # rows means another caller already moved the run.
            filters['status'] = eq(expected_status)
        updated = await self.db.update(
            'agent_runs',
            {'status': status, 'updated_at': iso_now()},
            filters=filters,
        )
        if expected_status is not None:
            if not (isinstance(updated, list) and updated):
                raise AgentRunConflictError(
                    'This run has already been claimed or has finished.'
                )
            return updated[0]
        row = updated[0] if isinstance(updated, list) and updated else {**run, 'status': status}
        return row

    async def claim_run(self, run: dict[str, Any]) -> dict[str, Any]:
        """Claim a queued run for execution (queued -> running).

        The transition is a compare-and-swap on ``status='queued'``:
        exactly one concurrent caller wins it, and every other caller
        gets a conflict instead of executing the run a second time.
        """
        if run.get('status') != 'queued':
            raise AgentRunConflictError('This run is not queued for execution.')
        return await self._set_status(run, 'running', expected_status='queued')

    async def _get_owned_run(self, *, user_id: str, run_id: str) -> dict[str, Any]:
        row = await self.db.select_one(
            'agent_runs',
            filters={'id': eq(str(run_id)), 'user_id': eq(user_id)},
        )
        if not row:
            raise AgentRunNotFoundError()
        return row

    async def find_run_by_conversation_id(
        self, *, user_id: str, conversation_id: str
    ) -> dict[str, Any] | None:
        """Return the raw run row filed under a conversation id, if any.

        Automation triggers file each occurrence's run under a
        deterministic conversation id (see
        ``AgentAutomationService.occurrence_conversation_id``), so a
        later trigger pass can find the run an earlier pass already
        created for the same occurrence instead of minting a second.
        """
        if not conversation_id:
            return None
        return await self.db.select_one(
            'agent_runs',
            filters={
                'user_id': eq(str(user_id)),
                'conversation_id': eq(str(conversation_id)),
            },
        )

    # -- access enforcement -------------------------------------------------

    async def _load_user(self, user_id: str) -> dict[str, Any] | None:
        row = await self.db.select_one(
            'users', columns='*', filters={'id': eq(str(user_id))}
        )
        return row if isinstance(row, dict) else None

    async def enforce_capability_access(
        self, capability: Capability, user_id: str
    ) -> None:
        """Fail closed unless the caller holds the registry entitlement
        and satisfies the registry credit-cost rule for ``capability``.

        Entitlement derives from the account's existing plan state —
        the same server-authoritative helpers the paid-tool routes use
        (``paid_tools_entitled`` / ``is_guest_user`` over the verified
        tier in ``usage_service.tier_name``):

        - ``free`` capabilities are open to every caller;
        - ``account`` capabilities require a registered (non-guest)
          account row;
        - ``paid`` capabilities require a verified paid entitlement.

        The credit-cost rule comes from the registry entry alone,
        never from caller input. A ``fixed`` cost names the exact
        credit figure, and the caller's balance (read through the
        existing credits authority, ``usage_service.credit_status``)
        must cover it before any provider work. A ``quote`` cost names
        no figure in the registry — its exact price is produced by the
        feature-quote path before an approval card is rendered — so
        the registry rule for those capabilities is the paid
        entitlement gate above. This check never charges: the fixed
        cost is reserved atomically at execution time through the
        confirmed-spend credits RPC (see ``reserve_run_credits``) and
        released again if the run does not succeed, so charging stays
        charge-on-success.
        """
        if not self.enforce_access:
            return
        if capability.entitlement in {'account', 'paid'}:
            user = await self._load_user(user_id)
            if capability.entitlement == 'account':
                entitled = user is not None and not is_guest_user(user)
            else:
                entitled = paid_tools_entitled(user)
            if not entitled:
                raise AgentRunError(
                    'That capability is not included with this account.',
                    403,
                    'CAPABILITY_NOT_ENTITLED',
                )
        elif capability.entitlement != 'free':
            # Unknown entitlement labels fail closed; the registry
            # validator rejects them at import, so this is unreachable
            # for shipped entries.
            raise AgentRunError(
                'That capability is not included with this account.',
                403,
                'CAPABILITY_NOT_ENTITLED',
            )
        if capability.credit_cost_kind == 'fixed':
            cost = int(capability.credit_cost or 0)
            if cost > 0:
                credits = await credit_status(self.db, str(user_id))
                if credits['balance'] < cost:
                    raise AgentRunError(
                        f'This capability costs {cost} credits and the '
                        'account balance is too low.',
                        402,
                        'INSUFFICIENT_CREDITS',
                    )

    async def enforce_run_access(self, run: dict[str, Any]) -> None:
        """Re-check access for a stored run at execution time.

        A run created while the caller was entitled must not execute
        after the entitlement lapses or the balance drops below the
        registry cost, so execution re-resolves the capability from
        the registry and the account state fresh, exactly as creation
        does. The capability's current registry status is re-checked
        the same way: a capability flipped away from ``live`` after
        the run was created (or after its approval) refuses here,
        before the run is claimed and before any provider contact,
        with the same ``CAPABILITY_NOT_LIVE`` shape creation uses.
        The rejection leaves the run queued, like the entitlement and
        balance rejections below.
        """
        if not self.enforce_access:
            return
        capability = get_capability(str(run.get('capability_id') or ''))
        if capability is None:
            raise AgentRunError(
                'That capability is not available.', 404, 'CAPABILITY_NOT_FOUND'
            )
        if self.enforce_capability_status and capability.status != 'live':
            raise AgentRunError(
                'That capability is not live yet.',
                409,
                'CAPABILITY_NOT_LIVE',
            )
        await self.enforce_capability_access(
            capability, str(run.get('user_id') or '')
        )

    async def approved_action_payload(
        self, run: dict[str, Any]
    ) -> tuple[bool, dict[str, Any] | None]:
        """Return ``(is_approval_gated, exact_payload)`` for a run.

        The first element says whether the run's execution depends on
        an approval at all; the second is the approved action's frozen
        exact payload, or ``None`` when no usable payload of record
        exists. Read errors propagate to the caller: payload
        resolution must fail closed, never guess.

        A run is approval-gated when its durable record shows it went
        through approval: a pending-action row exists for it in any
        state, or its step ledger carries the ``approval.requested``
        step creation writes only for gated runs. For a gated run the
        approved row is the only payload of record — when that row is
        missing at execution time (deleted, or its status rewritten
        after the approval landed), the result is ``(True, None)``
        and execution refuses. The creation payload is never
        substituted for the payload the user approved; it remains
        the payload of record only for runs that were never gated,
        which return ``(False, None)``.
        """
        rows = await self.db.select(
            'agent_pending_actions',
            filters={
                'run_id': eq(str(run['id'])),
                'user_id': eq(str(run['user_id'])),
            },
            order='created_at.desc',
            limit=50,
        )
        approved = [row for row in rows if row.get('status') == 'approved']
        if approved:
            payload = approved[0].get('exact_payload')
            return True, payload if isinstance(payload, dict) else None
        if rows:
            return True, None
        steps = await self.db.select(
            'agent_run_steps',
            filters={
                'run_id': eq(str(run['id'])),
                'user_id': eq(str(run['user_id'])),
                'step_type': eq('approval.requested'),
            },
            limit=1,
        )
        if steps:
            return True, None
        return False, None

    async def reserve_run_credits(self, run: dict[str, Any]) -> str | None:
        """Atomically reserve a fixed-cost run's registry cost.

        The reservation is the existing confirmed-spend credits RPC
        (``spend_credits_confirmed`` — the same atomic boundary the
        feature billing path uses): it takes the per-account advisory
        lock, checks the balance, and deducts in one transaction, so
        two concurrent executions against a balance that covers only
        one cost cannot both pass. The spend is idempotent per run
        (action key ``agent-run:<run id>``, component = capability
        id, confirmed maximum = the exact registry cost), so a retry
        of the same run never double-charges. Returns the ledger id
        of the spend, or ``None`` when the capability carries no
        fixed cost (``none`` and ``quote`` costs reserve nothing
        here — quote prices come from the feature-quote path).
        Raises ``INSUFFICIENT_CREDITS`` when the atomic spend refuses.
        """
        if not self.enforce_access:
            return None
        capability = get_capability(str(run.get('capability_id') or ''))
        if capability is None or capability.credit_cost_kind != 'fixed':
            return None
        cost = int(capability.credit_cost or 0)
        if cost <= 0:
            return None
        user_id = str(run.get('user_id') or '')
        result = await self.db.rpc(
            'spend_credits_confirmed',
            {
                'p_user_id': user_id,
                'p_amount': cost,
                'p_reason': 'agent_run',
                'p_action_key': f'agent-run:{run["id"]}',
                'p_component': capability.id,
                'p_confirmed_max': cost,
                'p_metadata': {
                    'runId': str(run['id']),
                    'capabilityId': capability.id,
                },
            },
        )
        row = (
            result[0]
            if isinstance(result, list) and result
            else (result or {})
        )
        if row.get('limit_exceeded'):
            raise AgentRunError(
                'This run already used its approved credit maximum. '
                'Start the run again for a fresh review.',
                409,
                'CREDIT_SPEND_LIMIT_EXCEEDED',
            )
        if not row.get('allowed'):
            raise AgentRunError(
                f'This capability costs {cost} credits and the '
                'account balance is too low.',
                402,
                'INSUFFICIENT_CREDITS',
            )
        ledger_id = row.get('ledger_id')
        return str(ledger_id) if ledger_id else None

    async def refund_run_credits(
        self, user_id: str, ledger_id: str | None
    ) -> None:
        """Release a reserved run cost through the existing refund
        mechanics (``refund_credit_spend``, via ``refund_usage``), so
        a run that does not succeed does not keep the money."""
        if not ledger_id:
            return
        await refund_usage(self.db, str(user_id), f'credit:{ledger_id}')

    async def release_run_claim(self, run: dict[str, Any]) -> None:
        """Hand an execution claim back (running -> queued) when the
        credit reservation refuses after the claim was taken, so the
        run returns to exactly the state the pre-claim reservation
        design left it in: queued, with no money moved."""
        await self._set_status(run, 'queued', expected_status='running')

    # -- credit reservation lifecycle ------------------------------------
    #
    # The credits ledger is the source of truth for money; the run's
    # step ledger records each reservation's lifecycle against it, so
    # a reservation whose release never landed is discoverable from
    # the run record itself instead of stranding silently.

    async def record_credit_reservation(
        self, run: dict[str, Any], ledger_id: str
    ) -> None:
        await self._record_step(
            run=run,
            step_type='run.credits_reserved',
            payload={'ledgerId': str(ledger_id)},
        )

    async def record_credit_release(
        self, run: dict[str, Any], ledger_id: str
    ) -> None:
        await self._record_step(
            run=run,
            step_type='run.credits_released',
            payload={'ledgerId': str(ledger_id)},
        )

    async def _ledger_reservation(
        self, run: dict[str, Any]
    ) -> tuple[str | None, bool]:
        """The run's confirmed spend in the credits ledger itself.

        The executor commits the debit before it records the
        reservation step, so the step ledger cannot be the only
        discovery path: a crash in that gap leaves a real debit no
        step names. The spend is filed under the deterministic
        external key ``agent-run:<run id>:<capability id>`` (the
        confirmed-spend RPC's idempotency key), so the debit is
        findable from the run row alone. Returns the spend's ledger
        id and whether a refund row already reverses it.
        """
        external_id = f'agent-run:{run["id"]}:{run["capability_id"]}'
        rows = await self.db.select(
            'credit_ledger',
            filters={
                'user_id': eq(str(run['user_id'])),
                'provider': eq('feature-spend'),
                'external_id': eq(external_id),
            },
            limit=1,
        )
        if not rows:
            return None, False
        ledger_id = str(rows[0]['id'])
        return ledger_id, await self._ledger_refund_exists(run, ledger_id)

    async def _ledger_refund_exists(
        self, run: dict[str, Any], ledger_id: str
    ) -> bool:
        """Whether the credits ledger already reverses a spend.

        The refund RPC enforces refund-at-most-once in the ledger
        (a unique index on the reversing row), so this row is the
        durable proof a release landed — even when the release's
        step record did not.
        """
        rows = await self.db.select(
            'credit_ledger',
            filters={
                'user_id': eq(str(run['user_id'])),
                'related_ledger_id': eq(str(ledger_id)),
                'reason': eq('refund'),
            },
            limit=1,
        )
        return bool(rows)

    async def _fail_stale_running_run(
        self, run: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Fail a ``running`` run whose claim is stale.

        The transition is a compare-and-swap on the exact row the
        caller observed — status still ``running`` under the same
        ``updated_at`` stamp — so a live executor that moves the
        run first wins, and this recovery backs off instead of
        failing work in progress. Returns the failed row, or None
        when the compare-and-swap lost.
        """
        updated = await self.db.update(
            'agent_runs',
            {'status': 'failed', 'updated_at': iso_now()},
            filters={
                'id': eq(str(run['id'])),
                'user_id': eq(str(run['user_id'])),
                'status': eq('running'),
                'updated_at': eq(str(run.get('updated_at'))),
            },
        )
        if not (isinstance(updated, list) and updated):
            return None
        failed = updated[0]
        await self._record_step(
            run=failed,
            step_type='run.failed',
            payload={'code': 'STALE_RUNNING_RECOVERED'},
        )
        return failed

    async def reconcile_run_credits(self, run: dict[str, Any]) -> bool:
        """Refund a non-success run's stranded reservation.

        A reserved debit with no matching release on a run that
        ended failed or cancelled is money whose release never
        landed — the executor crashed after reserving, or the
        refund itself failed. Discovery reads both ledgers: the
        run's step ledger (``run.credits_reserved`` without
        ``run.credits_released``) and the credits ledger itself,
        keyed by the spend's deterministic action key, which finds
        the debit even when the reservation step was never written
        — the executor commits the debit first and records the step
        second, and a crash between them must not strand the money.
        A ``running`` run is recovered too once its claim is stale
        (see ``STALE_RUNNING_AFTER``): it is failed under a
        compare-and-swap first, so a live executor is never
        disturbed. A fresh ``running`` run and a succeeded run are
        never touched: the one's executor may still be working,
        and the other's reservation is its charge.

        The refund goes through the same idempotent refund RPC as
        the inline release, so reconciling twice, or racing the
        executor's own late release, refunds at most once; a
        successful refund is recorded with the release step so
        later passes see the run as settled. Returns True when
        this call issued a refund.
        """
        status = str(run.get('status') or '')
        if status == 'running':
            if not _running_claim_is_stale(run):
                return False
            failed = await self._fail_stale_running_run(run)
            if failed is None:
                return False
            run = failed
            status = 'failed'
        if status not in {'failed', 'cancelled'}:
            return False
        steps = await self.db.select(
            'agent_run_steps',
            filters={
                'run_id': eq(str(run['id'])),
                'user_id': eq(str(run['user_id'])),
            },
            order='id.asc',
            limit=500,
        )
        reserved: list[str] = []
        released: set[str] = set()
        for step in steps:
            payload = step.get('payload') or {}
            ledger_id = payload.get('ledgerId')
            if not ledger_id:
                continue
            if step.get('step_type') == 'run.credits_reserved':
                reserved.append(str(ledger_id))
            elif step.get('step_type') == 'run.credits_released':
                released.add(str(ledger_id))
        ledger_id, _refunded = await self._ledger_reservation(run)
        if ledger_id and ledger_id not in reserved:
            reserved.append(ledger_id)
        refunded = False
        for candidate in reserved:
            if candidate in released:
                continue
            if await self._ledger_refund_exists(run, candidate):
                # The refund landed but its release step did not:
                # heal the run's record so later passes see the run
                # as settled. No money moves — it already came back.
                await self.record_credit_release(run, candidate)
                released.add(candidate)
                continue
            await self.refund_run_credits(str(run['user_id']), candidate)
            await self.record_credit_release(run, candidate)
            refunded = True
        return refunded

    async def _run_page(
        self,
        *,
        status: str,
        cursor: tuple[str, str] | None,
        page_size: int = RECONCILE_PAGE_SIZE,
    ) -> tuple[list[dict[str, Any]], tuple[str, str] | None]:
        """One (updated_at, id) keyset page of runs in ``status``.

        The cursor is composite, so a page that ends inside a block
        of rows sharing one ``updated_at`` continues within the tie
        (same stamp, greater id) instead of skipping the rest of
        it. Returns the page — sorted by (updated_at, id) — and the
        next cursor, or None when the page was short and the stream
        is exhausted.
        """
        if cursor is None:
            rows = await self.db.select(
                'agent_runs',
                filters={'status': eq(status)},
                order='updated_at.asc,id.asc',
                limit=page_size,
            )
        else:
            cursor_ts, cursor_id = cursor
            tie = await self.db.select(
                'agent_runs',
                filters={
                    'status': eq(status),
                    'updated_at': eq(cursor_ts),
                    'id': gt(cursor_id),
                },
                order='updated_at.asc,id.asc',
                limit=page_size,
            )
            rest = await self.db.select(
                'agent_runs',
                filters={'status': eq(status), 'updated_at': gt(cursor_ts)},
                order='updated_at.asc,id.asc',
                limit=page_size - len(tie),
            )
            rows = tie + rest
        rows = sorted(
            rows,
            key=lambda row: (
                str(row.get('updated_at') or ''),
                str(row.get('id') or ''),
            ),
        )
        if len(rows) < page_size:
            return rows, None
        last = rows[-1]
        return rows, (str(last.get('updated_at')), str(last.get('id')))

    async def _reconcile_run_stream(self, status: str) -> int:
        """Reconcile one candidate stream to exhaustion, oldest first."""
        settled = 0
        cursor: tuple[str, str] | None = None
        for _page in range(RECONCILE_MAX_PAGES):
            rows, cursor = await self._run_page(status=status, cursor=cursor)
            if not rows:
                break
            for row in rows:
                if status == 'running' and not _running_claim_is_stale(row):
                    # Oldest first: every later claim is younger, so
                    # nothing past this row can be stale either.
                    return settled
                try:
                    if await self.reconcile_run_credits(row):
                        settled += 1
                except Exception:
                    continue
            if cursor is None:
                break
        return settled

    async def reconcile_terminal_run_credits(self) -> int:
        """Recovery sweep over every stranded reservation.

        Settles reserved-but-unreleased debits on failed and
        cancelled runs — and on stale ``running`` runs, whose
        claims outlived their executors — without anyone opening
        them (the run-due lane calls this once per pass). Each
        stream is paged oldest-first to exhaustion, so residue is
        settled no matter how many newer runs sit on top of it;
        the refund RPC's idempotency keeps every settlement
        exact-once across passes. One run's failure never blocks
        the rest. Returns how many runs this call refunded.
        """
        settled = 0
        for status in ('failed', 'cancelled', 'running'):
            settled += await self._reconcile_run_stream(status)
        return settled

    # -- runs ---------------------------------------------------------------
    async def create_run(
        self,
        *,
        user_id: str,
        capability_id: str,
        payload: Any,
        conversation_id: str | None = None,
        project_id: str | None = None,
    ) -> dict[str, Any]:
        capability = get_capability(capability_id)
        if capability is None:
            raise AgentRunError(
                'That capability is not available.', 404, 'CAPABILITY_NOT_FOUND'
            )
        if self.enforce_capability_status and capability.status != 'live':
            raise AgentRunError(
                'That capability is not live yet.',
                409,
                'CAPABILITY_NOT_LIVE',
            )
        await self.enforce_capability_access(capability, user_id)
        payload = _validate_payload(capability, payload)
        needs_approval = capability.approval in {'card', 'card_with_cost'}
        now = iso_now()
        run = {
            'id': new_uuid(),
            'user_id': user_id,
            'project_id': project_id or None,
            'conversation_id': (str(conversation_id)[:160] if conversation_id else None),
            'capability_id': capability.id,
            'status': 'waiting_approval' if needs_approval else 'queued',
            'input_payload': payload,
            'input_summary': _summarize_input(payload),
            'result_summary': None,
            'credit_cost': capability.credit_cost,
            'created_at': now,
            'updated_at': now,
        }
        await self.db.insert('agent_runs', run)
        await self._record_step(run=run, step_type='run.created')
        action = None
        if needs_approval:
            expires = datetime.now(timezone.utc) + APPROVAL_TTL
            action = {
                'id': new_uuid(),
                'run_id': run['id'],
                'user_id': user_id,
                'capability_id': capability.id,
                'exact_payload': payload,
                'rendered_summary': f'{capability.title} — {capability.verb_phrase}',
                'credit_cost': capability.credit_cost,
                'status': 'pending',
                'expires_at': expires.isoformat(),
                'decided_at': None,
                'created_at': now,
                'updated_at': now,
            }
            await self.db.insert('agent_pending_actions', action)
            await self._record_step(run=run, step_type='approval.requested')
        else:
            await self._record_step(run=run, step_type='run.queued')
        result = self.public_run(run)
        if action is not None:
            result['pendingAction'] = self.public_action(action)
        return result

    async def list_runs(
        self, *, user_id: str, status: str | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        filters: dict[str, Any] = {'user_id': eq(user_id)}
        if status:
            if status not in RUN_STATUSES:
                raise AgentRunError('Unknown run status filter.', 400, 'INVALID_RUN_STATUS')
            filters['status'] = eq(status)
        rows = await self.db.select(
            'agent_runs',
            filters=filters,
            order='created_at.desc',
            limit=max(1, min(int(limit or 100), 250)),
        )
        return [self.public_run(row) for row in rows]

    async def get_run(self, *, user_id: str, run_id: str) -> dict[str, Any]:
        run = await self._get_owned_run(user_id=user_id, run_id=run_id)
        steps = await self.db.select(
            'agent_run_steps',
            filters={'run_id': eq(run['id']), 'user_id': eq(user_id)},
            order='id.asc',
            limit=500,
        )
        actions = await self.db.select(
            'agent_pending_actions',
            filters={'run_id': eq(run['id']), 'user_id': eq(user_id)},
            order='created_at.desc',
            limit=50,
        )
        result = self.public_run(run)
        result['steps'] = [self.public_step(step) for step in steps]
        result['pendingActions'] = [self.public_action(item) for item in actions]
        return result

    async def cancel_run(self, *, user_id: str, run_id: str) -> dict[str, Any]:
        run = await self._get_owned_run(user_id=user_id, run_id=run_id)
        if run['status'] in TERMINAL_STATUSES:
            raise AgentRunConflictError('This run has already finished.')
        pending = await self.db.select(
            'agent_pending_actions',
            filters={
                'run_id': eq(run['id']),
                'user_id': eq(user_id),
                'status': eq('pending'),
            },
            limit=50,
        )
        for action in pending:
            # Compare-and-swap, the same discipline decide_approval
            # claims its decision with: the cancellation lands only
            # while the action is still pending. A decision that
            # landed concurrently makes this match zero rows, and
            # the cancel loses with a conflict instead of rewriting
            # the recorded decision after the fact.
            updated = await self.db.update(
                'agent_pending_actions',
                {'status': 'cancelled', 'updated_at': iso_now()},
                filters={
                    'id': eq(action['id']),
                    'user_id': eq(user_id),
                    'status': eq('pending'),
                },
            )
            if not updated:
                raise AgentRunConflictError(
                    'This run has already been decided.'
                )
        # The run transition is a compare-and-swap on the observed
        # status too: a decision (or an execution claim) that moved
        # the run first wins, and this cancel reports the conflict
        # rather than overwriting the outcome.
        current_status = str(run.get('status') or '')
        if current_status:
            run = await self._set_status(
                run, 'cancelled', expected_status=current_status
            )
        else:
            run = await self._set_status(run, 'cancelled')
        await self._record_step(run=run, step_type='run.cancelled')
        # Recovery: cancelling a run that was claimed and reserved
        # before it got stuck settles its stranded reservation here.
        # Best effort — a reconcile failure never masks the
        # cancellation; the residue stays on the run's step ledger
        # for the terminal sweep.
        try:
            await self.reconcile_run_credits(run)
        except Exception:
            pass
        return self.public_run(run)

    # -- approvals ------------------------------------------------------------
    async def list_approvals(self, *, user_id: str) -> list[dict[str, Any]]:
        rows = await self.db.select(
            'agent_pending_actions',
            filters={'user_id': eq(user_id), 'status': eq('pending')},
            order='created_at.desc',
            limit=100,
        )
        return [self.public_action(row) for row in rows]

    async def decide_approval(
        self,
        *,
        user_id: str,
        action_id: str,
        decision: str,
        edited_payload: Any = None,
    ) -> dict[str, Any]:
        normalized = str(decision or '').strip().lower()
        if normalized not in {'approved', 'denied'}:
            raise AgentRunError('Invalid approval decision.', 400, 'INVALID_APPROVAL')
        action = await self.db.select_one(
            'agent_pending_actions',
            filters={'id': eq(str(action_id)), 'user_id': eq(user_id)},
        )
        if not action:
            raise AgentActionNotFoundError()
        if action['status'] != 'pending':
            raise AgentRunConflictError('This action has already been decided.')
        expires_at = str(action.get('expires_at') or '')
        if expires_at and expires_at <= iso_now():
            expired = await self.db.update(
                'agent_pending_actions',
                {'status': 'expired', 'updated_at': iso_now()},
                filters={
                    'id': eq(action['id']),
                    'user_id': eq(user_id),
                    'status': eq('pending'),
                },
            )
            if not expired:
                raise AgentRunConflictError(
                    'This action has already been decided.'
                )
            raise AgentRunConflictError('This approval has expired.')
        run = await self._get_owned_run(user_id=user_id, run_id=str(action['run_id']))
        payload = action.get('exact_payload') or {}
        if normalized == 'approved' and edited_payload is not None:
            capability = get_capability(str(action['capability_id']))
            if capability is None:
                raise AgentRunError(
                    'That capability is not available.', 404, 'CAPABILITY_NOT_FOUND'
                )
            payload = _validate_payload(capability, edited_payload)
        now = iso_now()
        # Compare-and-swap: the decision lands only while the action is
        # still pending. A concurrent decision that already landed makes
        # this update match zero rows, and the loser gets a conflict
        # instead of queueing (and executing) the run a second time.
        updated = await self.db.update(
            'agent_pending_actions',
            {
                'status': normalized,
                'exact_payload': payload,
                'decided_at': now,
                'updated_at': now,
            },
            filters={
                'id': eq(action['id']),
                'user_id': eq(user_id),
                'status': eq('pending'),
            },
        )
        if not updated:
            raise AgentRunConflictError('This action has already been decided.')
        decided = {**action, 'status': normalized, 'exact_payload': payload, 'decided_at': now}
        if normalized == 'approved':
            current_status = str(run.get('status') or '')
            if current_status:
                run = await self._set_status(
                    run, 'queued', expected_status=current_status
                )
            else:
                run = await self._set_status(run, 'queued')
            await self._record_step(
                run=run,
                step_type='approval.decided',
                payload={'decision': 'approved', 'actionId': action['id']},
            )
            await self._record_step(run=run, step_type='run.queued')
        else:
            # Same compare-and-swap discipline as the approve path:
            # the denial moves the run only from the status observed
            # when the action was loaded, so a cancel that landed
            # first is never overwritten by a late denial.
            current_status = str(run.get('status') or '')
            if current_status:
                run = await self._set_status(
                    run, 'cancelled', expected_status=current_status
                )
            else:
                run = await self._set_status(run, 'cancelled')
            await self._record_step(
                run=run,
                step_type='approval.decided',
                payload={'decision': 'denied', 'actionId': action['id']},
            )
            await self._record_step(run=run, step_type='run.cancelled')
        return {'action': self.public_action(decided), 'run': self.public_run(run)}
