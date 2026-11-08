"""Bounded durable scheduler for owner-connected mail and calendar actions.

The scheduler owns no payloads or credentials.  A durable store claims one
content-free schedule row, while a trusted run resolver reconstructs the exact
encrypted template, current task grant, and (for every write) a fresh one-use
approval.  Provider effects remain exclusively inside ``ConnectedAppRuntime``.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import Callable, Protocol
from uuid import UUID, uuid4, uuid5
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .connected_app_policy import (
    ConnectedActionPolicy,
    ConnectedApprovalEvidence,
    ConnectedTaskGrant,
    ConnectorActionKind,
    ConnectorProvider,
    ConnectorResource,
    implemented_runtime_actions,
)
from .connected_app_runtime import (
    ConnectedActionInvocation,
    ConnectedActionOutcome,
    ConnectedActionRuntimeResult,
    ConnectedAppRuntime,
)


def _uuid(value: str, name: str) -> str:
    try:
        canonical = str(UUID(value))
    except (TypeError, ValueError, AttributeError):
        raise ValueError(f"{name} must be a UUID") from None
    if canonical != value:
        raise ValueError(f"{name} must be canonical")
    return value


def _aware(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(timezone.utc)


class ConnectedScheduleRunOutcome(StrEnum):
    READ = "read"
    SUCCEEDED = "succeeded"
    AMBIGUOUS = "ambiguous"
    WAITING_APPROVAL = "waiting_approval"
    INVALID_TEMPLATE = "invalid_template"
    FAILED_NO_RETRY = "failed_no_retry"
    CANCELLED_UNKNOWN = "cancelled_unknown"


class ConnectedSchedulerError(RuntimeError):
    def __init__(self, code: str, *, retryable: bool = False) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable


@dataclass(frozen=True, slots=True, repr=False)
class ConnectedScheduleClaim:
    schedule_id: str
    owner_id: str
    connection_id: str
    task_id: str
    provider: ConnectorProvider
    resource: ConnectorResource
    action: ConnectorActionKind
    action_template_ref: str
    parameters_sha256: str
    task_state_revision: int
    time_zone: str
    cadence_seconds: int
    quiet_start_minute: int | None
    quiet_end_minute: int | None
    requires_approval_every_run: bool
    scheduled_for: datetime
    claim_id: str
    claimed_at: datetime
    claim_expires_at: datetime
    # V2 claims include server-attested template and live-authorization
    # bindings.  Optional defaults preserve the generic scheduler contract;
    # the concrete encrypted-template resolver rejects incomplete v1 claims.
    turn_id: str | None = None
    grant_id: str | None = None
    plan_payload_id: str | None = None
    plan_reference_binding_sha256: str | None = None
    authorization_revision: int | None = None
    authorization_snapshot_sha256: str | None = None
    granted_actions_sha256: str | None = None
    granted_scopes_sha256: str | None = None
    template_reference_binding_sha256: str | None = None
    resource_version_sha256: str | None = None
    # Mutating schedules use one durable occurrence identity across claim
    # lease expiry and approval polling.  Reads deliberately leave this
    # quartet empty because they never wait for user approval.
    occurrence_id: str | None = None
    occurrence_action_id: str | None = None
    occurrence_approval_id: str | None = None
    occurrence_created_at: datetime | None = None

    def __post_init__(self) -> None:
        for name in (
            "schedule_id",
            "owner_id",
            "connection_id",
            "task_id",
            "action_template_ref",
            "claim_id",
        ):
            object.__setattr__(self, name, _uuid(getattr(self, name), name))
        if not isinstance(self.provider, ConnectorProvider):
            raise ValueError("provider is invalid")
        if not isinstance(self.resource, ConnectorResource):
            raise ValueError("resource is invalid")
        if self.action not in implemented_runtime_actions():
            raise ValueError("action is not implemented")
        if ConnectedActionPolicy.requirement(self.action).resource is not self.resource:
            raise ValueError("action/resource mismatch")
        if (
            not isinstance(self.parameters_sha256, str)
            or len(self.parameters_sha256) != 64
            or any(character not in "0123456789abcdef" for character in self.parameters_sha256)
        ):
            raise ValueError("parameters_sha256 is invalid")
        if type(self.task_state_revision) is not int or self.task_state_revision < 1:
            raise ValueError("task_state_revision is invalid")
        try:
            ZoneInfo(self.time_zone)
        except (ZoneInfoNotFoundError, ValueError, TypeError):
            raise ValueError("time_zone is invalid") from None
        if type(self.cadence_seconds) is not int or not 60 <= self.cadence_seconds <= 2_678_400:
            raise ValueError("cadence_seconds is invalid")
        if (self.quiet_start_minute is None) != (self.quiet_end_minute is None):
            raise ValueError("quiet hours are partial")
        for value in (self.quiet_start_minute, self.quiet_end_minute):
            if value is not None and (type(value) is not int or not 0 <= value <= 1439):
                raise ValueError("quiet minute is invalid")
        if self.quiet_start_minute == self.quiet_end_minute and self.quiet_start_minute is not None:
            raise ValueError("quiet hours are ambiguous")
        if type(self.requires_approval_every_run) is not bool:
            raise ValueError("requires_approval_every_run is invalid")
        if (
            self.requires_approval_every_run
            is not ConnectedActionPolicy.requirement(self.action).mutates_external_state
        ):
            raise ValueError("schedule approval mode does not match action authority")
        scheduled = _aware(self.scheduled_for, "scheduled_for")
        claimed = _aware(self.claimed_at, "claimed_at")
        expires = _aware(self.claim_expires_at, "claim_expires_at")
        if expires <= claimed or expires - claimed > timedelta(minutes=5):
            raise ValueError("claim lease is invalid")
        if scheduled > claimed + timedelta(minutes=5):
            raise ValueError("schedule was claimed before it was due")
        for name in ("turn_id", "grant_id", "plan_payload_id"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _uuid(value, name))
        for name in (
            "plan_reference_binding_sha256",
            "authorization_snapshot_sha256",
            "granted_actions_sha256",
            "granted_scopes_sha256",
            "template_reference_binding_sha256",
            "resource_version_sha256",
        ):
            value = getattr(self, name)
            if value is not None and (
                not isinstance(value, str)
                or len(value) != 64
                or any(character not in "0123456789abcdef" for character in value)
            ):
                raise ValueError(f"{name} is invalid")
        if self.authorization_revision is not None and (
            type(self.authorization_revision) is not int or self.authorization_revision < 1
        ):
            raise ValueError("authorization_revision is invalid")
        occurrence_values = (
            self.occurrence_id,
            self.occurrence_action_id,
            self.occurrence_approval_id,
            self.occurrence_created_at,
        )
        if any(value is not None for value in occurrence_values):
            if any(value is None for value in occurrence_values):
                raise ValueError("schedule occurrence authority is partial")
            for name in (
                "occurrence_id",
                "occurrence_action_id",
                "occurrence_approval_id",
            ):
                object.__setattr__(self, name, _uuid(getattr(self, name), name))
            occurrence_created = _aware(
                self.occurrence_created_at, "occurrence_created_at"  # type: ignore[arg-type]
            )
            object.__setattr__(self, "occurrence_created_at", occurrence_created)
            if not self.requires_approval_every_run:
                raise ValueError("read schedule cannot contain write occurrence authority")
            if occurrence_created > claimed:
                raise ValueError("schedule occurrence cannot begin after its claim")
        elif self.requires_approval_every_run:
            # V2 records remain constructible for migration/compatibility
            # tests, but the concrete V3 resolver refuses them before any
            # provider-capable boundary.
            pass

    def __repr__(self) -> str:
        return (
            f"ConnectedScheduleClaim(schedule_id={self.schedule_id!r}, "
            f"action={self.action.value!r}, bindings='<redacted>')"
        )


@dataclass(frozen=True, slots=True, repr=False)
class ConnectedScheduledRun:
    invocation: ConnectedActionInvocation
    grant: ConnectedTaskGrant
    approval: ConnectedApprovalEvidence | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if type(self.invocation) is not ConnectedActionInvocation:
            raise ValueError("invocation is invalid")
        if type(self.grant) is not ConnectedTaskGrant:
            raise ValueError("grant is invalid")
        if self.approval is not None and type(self.approval) is not ConnectedApprovalEvidence:
            raise ValueError("approval is invalid")

    def __repr__(self) -> str:
        return "ConnectedScheduledRun(bindings='<redacted>', payload='<redacted>')"


@dataclass(frozen=True, slots=True, repr=False)
class ConnectedScheduleFinish:
    completion_id: str
    schedule_id: str
    owner_id: str
    claim_id: str
    task_state_revision: int
    outcome: ConnectedScheduleRunOutcome
    operation_id: str | None
    next_run_at: datetime
    finished_at: datetime
    occurrence_id: str | None = None

    def __post_init__(self) -> None:
        for name in ("completion_id", "schedule_id", "owner_id", "claim_id"):
            object.__setattr__(self, name, _uuid(getattr(self, name), name))
        if self.occurrence_id is not None:
            object.__setattr__(
                self,
                "occurrence_id",
                _uuid(self.occurrence_id, "occurrence_id"),
            )
        if self.operation_id is not None:
            object.__setattr__(self, "operation_id", _uuid(self.operation_id, "operation_id"))
        if type(self.task_state_revision) is not int or self.task_state_revision < 1:
            raise ValueError("task_state_revision is invalid")
        if not isinstance(self.outcome, ConnectedScheduleRunOutcome):
            raise ValueError("outcome is invalid")
        finished = _aware(self.finished_at, "finished_at")
        next_run = _aware(self.next_run_at, "next_run_at")
        if next_run < finished + timedelta(seconds=60) or next_run > finished + timedelta(days=31):
            raise ValueError("next_run_at is invalid")

    def __repr__(self) -> str:
        return f"ConnectedScheduleFinish(outcome={self.outcome.value!r}, bindings='<redacted>')"


@dataclass(frozen=True, slots=True, repr=False)
class ConnectedScheduleCompletion:
    finish: ConnectedScheduleFinish
    recorded_at: datetime

    def __post_init__(self) -> None:
        if type(self.finish) is not ConnectedScheduleFinish:
            raise ValueError("finish is invalid")
        object.__setattr__(self, "recorded_at", _aware(self.recorded_at, "recorded_at"))

    def __repr__(self) -> str:
        return f"ConnectedScheduleCompletion(outcome={self.finish.outcome.value!r})"


class ConnectedScheduleStore(Protocol):
    async def claim_once(
        self, *, claim_id: str, lease_seconds: int
    ) -> ConnectedScheduleClaim | None: ...

    async def readback_claim(self, *, claim_id: str) -> ConnectedScheduleClaim | None: ...

    async def finish_once(self, finish: ConnectedScheduleFinish) -> ConnectedScheduleCompletion: ...

    async def readback_finish(
        self, *, schedule_id: str, claim_id: str, completion_id: str
    ) -> ConnectedScheduleCompletion | None: ...


class ConnectedScheduleRunResolver(Protocol):
    """Decrypt and bind one immutable template without logging its contents."""

    async def prepare(self, claim: ConnectedScheduleClaim) -> ConnectedScheduledRun: ...


class ConnectedScheduleRuntime(Protocol):
    async def run(
        self,
        invocation: ConnectedActionInvocation,
        *,
        grant: ConnectedTaskGrant,
        approval: ConnectedApprovalEvidence | None = None,
        task_state_revision: int,
    ) -> ConnectedActionRuntimeResult: ...


def _inside_quiet(claim: ConnectedScheduleClaim, instant: datetime) -> bool:
    start = claim.quiet_start_minute
    end = claim.quiet_end_minute
    if start is None or end is None:
        return False
    local = instant.astimezone(ZoneInfo(claim.time_zone))
    minute = local.hour * 60 + local.minute
    if start < end:
        return start <= minute < end
    return minute >= start or minute < end


def _next_run(
    claim: ConnectedScheduleClaim, reference: datetime, *, defer_seconds: int = 0
) -> datetime:
    reference = _aware(reference, "reference")
    candidate = max(
        claim.scheduled_for + timedelta(seconds=claim.cadence_seconds),
        reference + timedelta(seconds=max(60, defer_seconds)),
    )
    # Advance in absolute UTC minutes.  This stays monotonic and correct across
    # both nonexistent and repeated local wall-clock minutes at DST boundaries.
    for _ in range(2 * 24 * 60 + 1):
        if not _inside_quiet(claim, candidate):
            return candidate
        candidate += timedelta(minutes=1)
    raise ConnectedSchedulerError("CONNECTED_SCHEDULE_QUIET_WINDOW_INVALID")


class ConnectedScheduleWorker:
    _COMPLETION_NAMESPACE = UUID("e72007e2-1934-5364-bb62-2e39afba1b3f")

    def __init__(
        self,
        *,
        store: ConnectedScheduleStore,
        resolver: ConnectedScheduleRunResolver,
        runtime: ConnectedScheduleRuntime,
        require_ready: Callable[[], None],
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        lease_seconds: int = 120,
        max_concurrency: int = 4,
    ) -> None:
        if type(lease_seconds) is not int or not 30 <= lease_seconds <= 300:
            raise ValueError("lease_seconds is invalid")
        if type(max_concurrency) is not int or not 1 <= max_concurrency <= 32:
            raise ValueError("max_concurrency is invalid")
        if not callable(require_ready):
            raise TypeError("schedule readiness fence is invalid")
        self._store = store
        self._resolver = resolver
        self._runtime = runtime
        self._require_ready = require_ready
        self._now = now
        self._lease_seconds = lease_seconds
        self._max_concurrency = max_concurrency

    def _require_effect_ready(self) -> None:
        try:
            self._require_ready()
        except Exception:
            raise ConnectedSchedulerError(
                "CONNECTED_SCHEDULE_NOT_READY", retryable=True
            ) from None

    async def _claim(self, claim_id: str) -> ConnectedScheduleClaim | None:
        try:
            claim = await self._store.claim_once(
                claim_id=claim_id,
                lease_seconds=self._lease_seconds,
            )
        except Exception:
            try:
                claim = await self._store.readback_claim(claim_id=claim_id)
            except Exception:
                raise ConnectedSchedulerError(
                    "CONNECTED_SCHEDULE_CLAIM_UNCERTAIN", retryable=True
                ) from None
        if claim is not None and type(claim) is not ConnectedScheduleClaim:
            raise ConnectedSchedulerError("CONNECTED_SCHEDULE_CLAIM_INVALID")
        return claim

    @staticmethod
    def _validate_run(
        claim: ConnectedScheduleClaim,
        run: ConnectedScheduledRun,
        *,
        reference: datetime,
    ) -> None:
        intent = run.invocation.intent
        if (
            intent.owner_id != claim.owner_id
            or intent.task_id != claim.task_id
            or intent.connection_id != claim.connection_id
            or intent.provider is not claim.provider
            or intent.resource is not claim.resource
            or intent.action is not claim.action
            or intent.parameters_sha256 != claim.parameters_sha256
            or run.invocation.payload_sha256 != claim.parameters_sha256
            or run.grant.owner_id != claim.owner_id
            or run.grant.task_id != claim.task_id
            or run.grant.turn_id != intent.turn_id
            or run.grant.connection_id != claim.connection_id
            or run.grant.provider is not claim.provider
            or run.grant.resource is not claim.resource
            or run.grant.authorization_revision != intent.authorization_revision
            or run.grant.authorization_snapshot_sha256 != intent.authorization_snapshot_sha256
            or claim.action not in run.grant.actions
            or run.grant.expires_at <= reference
        ):
            raise ConnectedSchedulerError("CONNECTED_SCHEDULE_RUN_BINDING_MISMATCH")
        requirement = ConnectedActionPolicy.requirement(claim.action)
        if requirement.mutates_external_state:
            approval = run.approval
            if (
                claim.requires_approval_every_run is not True
                or claim.occurrence_action_id is None
                or intent.action_id != claim.occurrence_action_id
                or approval is None
                or claim.occurrence_approval_id is None
                or approval.approval_id != claim.occurrence_approval_id
                or approval.action_id != intent.action_id
                or approval.owner_id != claim.owner_id
                or approval.task_id != claim.task_id
                or approval.turn_id != intent.turn_id
                or approval.connection_id != claim.connection_id
                or approval.provider is not claim.provider
                or approval.resource is not claim.resource
                or approval.action is not claim.action
                or approval.authorization_revision != intent.authorization_revision
                or approval.authorization_snapshot_sha256 != intent.authorization_snapshot_sha256
                or approval.approval_class is not requirement.approval_class
                or approval.parameters_sha256 != claim.parameters_sha256
                or approval.resource_version_sha256 != intent.resource_version_sha256
                or claim.occurrence_created_at is None
                or approval.approved_at < claim.occurrence_created_at
                or approval.approved_at > reference
                or approval.expires_at <= reference
            ):
                raise ConnectedSchedulerError("CONNECTED_SCHEDULE_FRESH_APPROVAL_REQUIRED")
        elif run.approval is not None:
            raise ConnectedSchedulerError("CONNECTED_SCHEDULE_UNEXPECTED_APPROVAL")

    async def _finish(
        self,
        claim: ConnectedScheduleClaim,
        *,
        outcome: ConnectedScheduleRunOutcome,
        operation_id: str | None,
        defer_seconds: int = 0,
    ) -> ConnectedScheduleCompletion:
        reference = _aware(self._now(), "now")
        finish = ConnectedScheduleFinish(
            # Cross-process response-loss recovery requires one stable
            # completion identity for each durable claim occurrence.
            completion_id=str(
                uuid5(
                    self._COMPLETION_NAMESPACE,
                    f"{claim.schedule_id}:{claim.claim_id}",
                )
            ),
            schedule_id=claim.schedule_id,
            owner_id=claim.owner_id,
            claim_id=claim.claim_id,
            task_state_revision=claim.task_state_revision,
            outcome=outcome,
            operation_id=operation_id,
            next_run_at=_next_run(claim, reference, defer_seconds=defer_seconds),
            finished_at=reference,
            occurrence_id=claim.occurrence_id,
        )
        try:
            result = await self._store.finish_once(finish)
        except Exception:
            try:
                result = await self._store.readback_finish(
                    schedule_id=claim.schedule_id,
                    claim_id=claim.claim_id,
                    completion_id=finish.completion_id,
                )
            except Exception:
                result = None
            if result is None:
                raise ConnectedSchedulerError(
                    "CONNECTED_SCHEDULE_FINISH_UNCERTAIN", retryable=True
                ) from None
        if type(result) is not ConnectedScheduleCompletion or result.finish != finish:
            raise ConnectedSchedulerError("CONNECTED_SCHEDULE_FINISH_MISMATCH")
        return result

    async def run_one(self) -> ConnectedScheduleCompletion | None:
        # A batch can outlive its attestation.  Fence every individual claim,
        # then recheck immediately before the provider-capable runtime call.
        self._require_effect_ready()
        claim = await self._claim(str(uuid4()))
        if claim is None:
            return None
        now = _aware(self._now(), "now")
        if claim.claim_expires_at <= now:
            raise ConnectedSchedulerError("CONNECTED_SCHEDULE_CLAIM_EXPIRED", retryable=True)
        try:
            run = await self._resolver.prepare(claim)
            if type(run) is not ConnectedScheduledRun:
                raise ConnectedSchedulerError("CONNECTED_SCHEDULE_TEMPLATE_INVALID")
            validation_now = _aware(self._now(), "now")
            if claim.claim_expires_at <= validation_now:
                raise ConnectedSchedulerError("CONNECTED_SCHEDULE_CLAIM_EXPIRED", retryable=True)
            self._validate_run(claim, run, reference=validation_now)
        except ConnectedSchedulerError as exc:
            if exc.code == "CONNECTED_SCHEDULE_CLAIM_EXPIRED":
                raise
            if exc.code == "CONNECTED_SCHEDULE_FRESH_APPROVAL_REQUIRED":
                return await self._finish(
                    claim,
                    outcome=ConnectedScheduleRunOutcome.WAITING_APPROVAL,
                    operation_id=None,
                    defer_seconds=min(300, claim.cadence_seconds),
                )
            return await self._finish(
                claim,
                outcome=ConnectedScheduleRunOutcome.INVALID_TEMPLATE,
                operation_id=None,
                defer_seconds=min(3600, claim.cadence_seconds),
            )
        except Exception:
            return await self._finish(
                claim,
                outcome=ConnectedScheduleRunOutcome.INVALID_TEMPLATE,
                operation_id=None,
                defer_seconds=min(3600, claim.cadence_seconds),
            )

        operation_id = run.invocation.intent.action_id
        try:
            self._require_effect_ready()
            result = await self._runtime.run(
                run.invocation,
                grant=run.grant,
                approval=run.approval,
                task_state_revision=claim.task_state_revision,
            )
        except asyncio.CancelledError:
            try:
                await asyncio.shield(
                    self._finish(
                        claim,
                        outcome=ConnectedScheduleRunOutcome.CANCELLED_UNKNOWN,
                        operation_id=operation_id,
                    )
                )
            finally:
                raise
        except ConnectedSchedulerError as exc:
            if exc.code == "CONNECTED_SCHEDULE_NOT_READY":
                # No provider call occurred.  Leave the durable claim to its
                # bounded lease/reconciliation path so renewed readiness can
                # retry it without recording a false terminal failure.
                raise
            return await self._finish(
                claim,
                outcome=ConnectedScheduleRunOutcome.FAILED_NO_RETRY,
                operation_id=operation_id,
            )
        except Exception:
            # Runtime invocation can cross the effect boundary.  Never cause a
            # blind scheduler retry after an unknown exception; the same action
            # remains recoverable through the durable runtime ledger.
            return await self._finish(
                claim,
                outcome=ConnectedScheduleRunOutcome.FAILED_NO_RETRY,
                operation_id=operation_id,
            )
        if type(result) is not ConnectedActionRuntimeResult or result.operation_id != operation_id:
            return await self._finish(
                claim,
                outcome=ConnectedScheduleRunOutcome.FAILED_NO_RETRY,
                operation_id=operation_id,
            )
        outcome = {
            ConnectedActionOutcome.READ: ConnectedScheduleRunOutcome.READ,
            ConnectedActionOutcome.SUCCEEDED: ConnectedScheduleRunOutcome.SUCCEEDED,
            ConnectedActionOutcome.AMBIGUOUS: ConnectedScheduleRunOutcome.AMBIGUOUS,
        }[result.outcome]
        return await self._finish(claim, outcome=outcome, operation_id=operation_id)

    async def run_batch(self, *, maximum: int = 16) -> tuple[ConnectedScheduleCompletion, ...]:
        if type(maximum) is not int or not 1 <= maximum <= 128:
            raise ValueError("maximum is invalid")
        semaphore = asyncio.Semaphore(self._max_concurrency)

        async def run_limited() -> ConnectedScheduleCompletion | None:
            async with semaphore:
                return await self.run_one()

        results = await asyncio.gather(*(run_limited() for _ in range(maximum)))
        return tuple(result for result in results if result is not None)


def build_connected_schedule_worker(
    *,
    released: bool,
    readiness_attested: bool,
    store: ConnectedScheduleStore | None,
    resolver: ConnectedScheduleRunResolver | None,
    runtime: ConnectedAppRuntime | None,
    **kwargs: object,
) -> ConnectedScheduleWorker:
    """Fail-closed production factory; source release and readiness are both mandatory."""

    if released is not True:
        raise ConnectedSchedulerError("CONNECTED_APPS_NOT_RELEASED")
    if readiness_attested is not True or store is None or resolver is None or runtime is None:
        raise ConnectedSchedulerError("CONNECTED_APPS_NOT_READY")
    return ConnectedScheduleWorker(store=store, resolver=resolver, runtime=runtime, **kwargs)
