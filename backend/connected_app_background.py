"""Bounded lifecycle supervisor for connected-app durable workers.

The supervisor is deliberately a thin composition boundary.  Provider-effect
authority remains in the database-backed dispatch outbox and schedule worker;
this loop only wakes those durable coordinators.  Importing the module cannot
start work, and construction fails unless the separately attested source and
runtime release gates are both true.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging
from typing import Callable, Protocol

from .connected_app_cleanup_reconciliation import ConnectedExternalReconciliationResult
from .connected_app_execution_outbox import ConnectedDispatchBatchResult
from .connected_app_multi_step_continuation import (
    ConnectedMultiStepContinuationBatchResult,
)
from .connected_app_payload_retention import ConnectedPayloadRetentionResult
from .connected_app_scheduler import ConnectedScheduleCompletion


logger = logging.getLogger(__name__)
_HEX = frozenset("0123456789abcdef")
CONNECTED_BACKGROUND_MODE_CONTINUOUS = "continuous"
CONNECTED_BACKGROUND_MODE_EXTERNAL_WAKE = "external_wake"
_EXECUTION_MODES = frozenset(
    {
        CONNECTED_BACKGROUND_MODE_CONTINUOUS,
        CONNECTED_BACKGROUND_MODE_EXTERNAL_WAKE,
    }
)


class ConnectedBackgroundError(RuntimeError):
    """Fixed, content-free worker lifecycle failure."""

    _CODES = frozenset(
        {
            "CONNECTED_BACKGROUND_ALREADY_STARTED",
            "CONNECTED_BACKGROUND_INVALID",
            "CONNECTED_BACKGROUND_NOT_RELEASED",
            "CONNECTED_BACKGROUND_NOT_READY",
        }
    )

    def __init__(self, code: str) -> None:
        self.code = code if code in self._CODES else "CONNECTED_BACKGROUND_INVALID"
        super().__init__(self.code)


class ConnectedDispatchWake(Protocol):
    async def reconcile_startup(
        self, *, owner_limit: int, per_owner_limit: int
    ) -> tuple[object, ...]: ...

    async def run_bounded(
        self, *, owner_limit: int, per_owner_limit: int
    ) -> ConnectedDispatchBatchResult: ...


class ConnectedScheduleWake(Protocol):
    async def run_batch(self, *, maximum: int) -> tuple[ConnectedScheduleCompletion, ...]: ...


class ConnectedReconciliationWake(Protocol):
    async def run_bounded(
        self,
        *,
        cleanup_maximum: int,
        expiry_maximum: int,
    ) -> ConnectedExternalReconciliationResult: ...


class ConnectedMultiStepContinuationWake(Protocol):
    async def run_bounded(
        self, *, maximum: int
    ) -> ConnectedMultiStepContinuationBatchResult: ...


class ConnectedPayloadRetentionWake(Protocol):
    async def run_bounded(
        self, *, payload_maximum: int, plan_maximum: int, loop_maximum: int
    ) -> ConnectedPayloadRetentionResult: ...


@dataclass(frozen=True, slots=True)
class ConnectedBackgroundCycle:
    dispatch_owners_scanned: int
    dispatch_actions_considered: int
    dispatch_actions_invoked: int
    dispatch_terminal_count: int
    schedule_completion_count: int
    dispatch_failed: bool
    scheduler_failed: bool
    cleanup_attempts: int = 0
    cleanup_terminal_count: int = 0
    expired_oauth_flow_count: int = 0
    expired_oauth_provisional_count: int = 0
    cleanup_failed: bool = False
    oauth_expiry_failed: bool = False
    reconciliation_failed: bool = False
    continuation_candidates_considered: int = 0
    continuation_claims_acquired: int = 0
    continuation_terminal_count: int = 0
    continuation_failed_count: int = 0
    continuation_failed: bool = False
    expired_payloads_purged: int = 0
    expired_plans_purged: int = 0
    expired_loop_envelopes_purged: int = 0
    retention_failed: bool = False

    def __post_init__(self) -> None:
        for name in (
            "dispatch_owners_scanned",
            "dispatch_actions_considered",
            "dispatch_actions_invoked",
            "dispatch_terminal_count",
            "schedule_completion_count",
            "cleanup_attempts",
            "cleanup_terminal_count",
            "expired_oauth_flow_count",
            "expired_oauth_provisional_count",
            "continuation_candidates_considered",
            "continuation_claims_acquired",
            "continuation_terminal_count",
            "continuation_failed_count",
            "expired_payloads_purged",
            "expired_plans_purged",
            "expired_loop_envelopes_purged",
        ):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise ConnectedBackgroundError("CONNECTED_BACKGROUND_INVALID")
        for name in (
            "dispatch_failed",
            "scheduler_failed",
            "cleanup_failed",
            "oauth_expiry_failed",
            "reconciliation_failed",
            "continuation_failed",
            "retention_failed",
        ):
            if type(getattr(self, name)) is not bool:
                raise ConnectedBackgroundError("CONNECTED_BACKGROUND_INVALID")


class ConnectedOperatorBackgroundSupervisor:
    """Start, wake, and drain the durable dispatch and schedule workers.

    The loop never queues customer content and never retries a provider effect
    itself.  A failure is reduced to one categorical flag; the next cycle asks
    the database-authoritative coordinator to reconcile durable state.

    ``continuous`` preserves the ordinary long-lived ASGI behavior.  The
    ``external_wake`` mode is for scale-to-zero hosts: startup publishes
    readiness without creating an asyncio task, and an authenticated external
    scheduler invokes exactly one bounded ``run_cycle`` per request.
    """

    def __init__(
        self,
        *,
        source_released: bool,
        readiness_attested: bool,
        require_ready: Callable[[], None],
        composition_manifest_sha256: str,
        dispatch: ConnectedDispatchWake,
        scheduler: ConnectedScheduleWake,
        reconciler: ConnectedReconciliationWake | None = None,
        multi_step_continuation: ConnectedMultiStepContinuationWake | None = None,
        continuation_released: bool = False,
        payload_retention: ConnectedPayloadRetentionWake | None = None,
        interval_seconds: float = 10.0,
        owner_limit: int = 25,
        per_owner_limit: int = 25,
        schedule_limit: int = 16,
        cleanup_limit: int = 16,
        expiry_limit: int = 32,
        continuation_limit: int = 8,
        payload_retention_limit: int = 32,
        plan_retention_limit: int = 32,
        loop_retention_limit: int = 32,
        execution_mode: str = CONNECTED_BACKGROUND_MODE_CONTINUOUS,
    ) -> None:
        if source_released is not True:
            raise ConnectedBackgroundError("CONNECTED_BACKGROUND_NOT_RELEASED")
        if readiness_attested is not True:
            raise ConnectedBackgroundError("CONNECTED_BACKGROUND_NOT_READY")
        if not callable(require_ready):
            raise ConnectedBackgroundError("CONNECTED_BACKGROUND_NOT_READY")
        if (
            not isinstance(composition_manifest_sha256, str)
            or len(composition_manifest_sha256) != 64
            or any(character not in _HEX for character in composition_manifest_sha256)
        ):
            raise ConnectedBackgroundError("CONNECTED_BACKGROUND_NOT_READY")
        if any(
            not callable(getattr(dispatch, name, None))
            for name in ("reconcile_startup", "run_bounded")
        ) or not callable(getattr(scheduler, "run_batch", None)):
            raise ConnectedBackgroundError("CONNECTED_BACKGROUND_INVALID")
        if not isinstance(interval_seconds, (int, float)) or not 0.1 <= interval_seconds <= 300:
            raise ConnectedBackgroundError("CONNECTED_BACKGROUND_INVALID")
        for value, maximum in (
            (owner_limit, 100),
            (per_owner_limit, 100),
            (schedule_limit, 128),
            (cleanup_limit, 100),
            (expiry_limit, 100),
            (continuation_limit, 32),
            (payload_retention_limit, 100),
            (plan_retention_limit, 100),
            (loop_retention_limit, 100),
        ):
            if type(value) is not int or not 1 <= value <= maximum:
                raise ConnectedBackgroundError("CONNECTED_BACKGROUND_INVALID")
        if type(execution_mode) is not str or execution_mode not in _EXECUTION_MODES:
            raise ConnectedBackgroundError("CONNECTED_BACKGROUND_INVALID")
        if reconciler is not None and (
            execution_mode != CONNECTED_BACKGROUND_MODE_EXTERNAL_WAKE
            or not callable(getattr(reconciler, "run_bounded", None))
        ):
            raise ConnectedBackgroundError("CONNECTED_BACKGROUND_INVALID")
        if type(continuation_released) is not bool or (
            continuation_released and multi_step_continuation is None
        ):
            raise ConnectedBackgroundError("CONNECTED_BACKGROUND_INVALID")
        if multi_step_continuation is not None and not callable(
            getattr(multi_step_continuation, "run_bounded", None)
        ):
            raise ConnectedBackgroundError("CONNECTED_BACKGROUND_INVALID")
        if payload_retention is not None and not callable(
            getattr(payload_retention, "run_bounded", None)
        ):
            raise ConnectedBackgroundError("CONNECTED_BACKGROUND_INVALID")
        self._dispatch = dispatch
        self._scheduler = scheduler
        self._reconciler = reconciler
        self._multi_step_continuation = multi_step_continuation
        self._continuation_released = continuation_released
        self._payload_retention = payload_retention
        self._require_ready = require_ready
        self._composition_manifest_sha256 = composition_manifest_sha256
        self._interval_seconds = float(interval_seconds)
        self._owner_limit = owner_limit
        self._per_owner_limit = per_owner_limit
        self._schedule_limit = schedule_limit
        self._cleanup_limit = cleanup_limit
        self._expiry_limit = expiry_limit
        self._continuation_limit = continuation_limit
        self._payload_retention_limit = payload_retention_limit
        self._plan_retention_limit = plan_retention_limit
        self._loop_retention_limit = loop_retention_limit
        self._execution_mode = execution_mode
        self._stopping = asyncio.Event()
        self._wake = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self._external_active = False
        self._cycle_lock = asyncio.Lock()
        self._last_cycle: ConnectedBackgroundCycle | None = None

    @property
    def running(self) -> bool:
        if self.external_wake:
            return self._external_active
        return self._task is not None and not self._task.done()

    @property
    def execution_mode(self) -> str:
        return self._execution_mode

    @property
    def external_wake(self) -> bool:
        return self._execution_mode == CONNECTED_BACKGROUND_MODE_EXTERNAL_WAKE

    @property
    def last_cycle(self) -> ConnectedBackgroundCycle | None:
        return self._last_cycle

    @property
    def composition_manifest_sha256(self) -> str:
        return self._composition_manifest_sha256

    async def startup(self) -> None:
        if self._task is not None or self._external_active:
            raise ConnectedBackgroundError("CONNECTED_BACKGROUND_ALREADY_STARTED")
        try:
            self._require_ready()
        except Exception:
            raise ConnectedBackgroundError("CONNECTED_BACKGROUND_NOT_READY") from None
        self._stopping.clear()
        self._wake.clear()
        if self.external_wake:
            # A scale-to-zero request must never leave a daemon behind or scan
            # durable work merely because an unrelated endpoint caused a cold
            # start.  The authenticated cron request owns the one bounded scan.
            self._external_active = True
            return
        # Discovery is intentionally separate from execution.  If startup
        # discovery fails, the first periodic cycle can safely retry it through
        # run_bounded without inventing provider authority.
        try:
            await self._dispatch.reconcile_startup(
                owner_limit=self._owner_limit,
                per_owner_limit=self._per_owner_limit,
            )
        except Exception:
            logger.warning("Connected dispatch startup reconciliation unavailable.")
        self._task = asyncio.create_task(self._run(), name="connected-operator-workers")

    def wake(self) -> None:
        if not self.external_wake and self.running:
            self._wake.set()

    async def run_cycle(self) -> ConnectedBackgroundCycle:
        async with self._cycle_lock:
            if self.external_wake and not self._external_active:
                raise ConnectedBackgroundError("CONNECTED_BACKGROUND_NOT_READY")
            try:
                self._require_ready()
            except Exception:
                raise ConnectedBackgroundError("CONNECTED_BACKGROUND_NOT_READY") from None
            dispatch_failed = False
            scheduler_failed = False
            reconciliation_failed = False
            continuation_failed = False
            retention_failed = False
            dispatch_result: ConnectedDispatchBatchResult | None = None
            completions: tuple[ConnectedScheduleCompletion, ...] = ()
            reconciliation: ConnectedExternalReconciliationResult | None = None
            continuation: ConnectedMultiStepContinuationBatchResult | None = None
            retention: ConnectedPayloadRetentionResult | None = None
            if self._reconciler is not None:
                try:
                    # Cleanup and OAuth expiry can revoke provider authority;
                    # run that bounded lane first and fence it independently.
                    self._require_ready()
                    reconciliation = await self._reconciler.run_bounded(
                        cleanup_maximum=self._cleanup_limit,
                        expiry_maximum=self._expiry_limit,
                    )
                    if type(reconciliation) is not ConnectedExternalReconciliationResult:
                        raise TypeError("invalid reconciliation result")
                except asyncio.CancelledError:
                    raise
                except Exception:
                    reconciliation_failed = True
                    logger.warning("Connected external reconciliation unavailable.")
            if self._payload_retention is not None:
                try:
                    # Ciphertext expiry is database-authoritative and content
                    # free, but still requires the exact current readiness
                    # attestation before destructive custody maintenance.
                    self._require_ready()
                    retention = await self._payload_retention.run_bounded(
                        payload_maximum=self._payload_retention_limit,
                        plan_maximum=self._plan_retention_limit,
                        loop_maximum=self._loop_retention_limit,
                    )
                    if type(retention) is not ConnectedPayloadRetentionResult:
                        raise TypeError("invalid payload retention result")
                except asyncio.CancelledError:
                    raise
                except Exception:
                    retention_failed = True
                    logger.warning("Connected ciphertext retention unavailable.")
            try:
                # Recheck immediately before the first provider-capable lane.
                self._require_ready()
                dispatch_result = await self._dispatch.run_bounded(
                    owner_limit=self._owner_limit,
                    per_owner_limit=self._per_owner_limit,
                )
                if type(dispatch_result) is not ConnectedDispatchBatchResult:
                    raise TypeError("invalid dispatch result")
            except asyncio.CancelledError:
                raise
            except Exception:
                dispatch_failed = True
                logger.warning("Connected dispatch cycle unavailable.")
            try:
                # A long dispatch batch may outlive a short attestation.  Do
                # not let the independent schedule lane inherit stale proof.
                self._require_ready()
                completions = await self._scheduler.run_batch(maximum=self._schedule_limit)
                if not isinstance(completions, tuple) or any(
                    type(item) is not ConnectedScheduleCompletion for item in completions
                ):
                    raise TypeError("invalid scheduler result")
            except asyncio.CancelledError:
                raise
            except Exception:
                scheduler_failed = True
                completions = ()
                logger.warning("Connected schedule cycle unavailable.")
            if self._continuation_released:
                try:
                    # Dispatch may have just durably completed an approved
                    # write.  The continuation queue independently proves that
                    # receipt and claims the exact loop before model work.
                    self._require_ready()
                    assert self._multi_step_continuation is not None
                    continuation = await self._multi_step_continuation.run_bounded(
                        maximum=self._continuation_limit
                    )
                    if type(continuation) is not ConnectedMultiStepContinuationBatchResult:
                        raise TypeError("invalid continuation result")
                except asyncio.CancelledError:
                    raise
                except Exception:
                    continuation_failed = True
                    logger.warning("Connected multi-step continuation unavailable.")
            cycle = ConnectedBackgroundCycle(
                dispatch_owners_scanned=(
                    0 if dispatch_result is None else dispatch_result.owners_scanned
                ),
                dispatch_actions_considered=(
                    0 if dispatch_result is None else dispatch_result.actions_considered
                ),
                dispatch_actions_invoked=(
                    0 if dispatch_result is None else dispatch_result.actions_invoked
                ),
                dispatch_terminal_count=(
                    0 if dispatch_result is None else len(dispatch_result.terminal_records)
                ),
                schedule_completion_count=len(completions),
                dispatch_failed=dispatch_failed,
                scheduler_failed=scheduler_failed,
                cleanup_attempts=(
                    0 if reconciliation is None else reconciliation.cleanup_attempts
                ),
                cleanup_terminal_count=(
                    0 if reconciliation is None else reconciliation.cleanup_terminal
                ),
                expired_oauth_flow_count=(
                    0 if reconciliation is None else reconciliation.expired_flows
                ),
                expired_oauth_provisional_count=(
                    0 if reconciliation is None else reconciliation.expired_provisionals
                ),
                cleanup_failed=(
                    False if reconciliation is None else reconciliation.cleanup_failed
                ),
                oauth_expiry_failed=(
                    False if reconciliation is None else reconciliation.expiry_failed
                ),
                reconciliation_failed=reconciliation_failed,
                continuation_candidates_considered=(
                    0 if continuation is None else continuation.candidates_considered
                ),
                continuation_claims_acquired=(
                    0 if continuation is None else continuation.claims_acquired
                ),
                continuation_terminal_count=(
                    0 if continuation is None else continuation.terminal_count
                ),
                continuation_failed_count=(
                    0 if continuation is None else continuation.failed_count
                ),
                continuation_failed=continuation_failed,
                expired_payloads_purged=(
                    0 if retention is None else retention.payloads_purged
                ),
                expired_plans_purged=(
                    0 if retention is None else retention.plans_purged
                ),
                expired_loop_envelopes_purged=(
                    0 if retention is None else retention.loop_envelopes_purged
                ),
                retention_failed=retention_failed,
            )
            self._last_cycle = cycle
            return cycle

    async def _run(self) -> None:
        while not self._stopping.is_set():
            try:
                await self.run_cycle()
            except asyncio.CancelledError:
                raise
            except ConnectedBackgroundError as exc:
                if exc.code != "CONNECTED_BACKGROUND_NOT_READY":
                    raise
                # A short-lived attestation may lapse while the process stays
                # healthy.  Remain fail-closed, but keep the supervisor alive
                # so a trusted readiness source can renew it without a process
                # restart.  No provider-capable lane ran in this cycle.
                logger.warning("Connected workers are waiting for renewed readiness.")
            self._wake.clear()
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=self._interval_seconds)
            except TimeoutError:
                pass

    async def shutdown(self, *, timeout_seconds: float = 30.0) -> bool:
        if not isinstance(timeout_seconds, (int, float)) or not 0 < timeout_seconds <= 300:
            raise ConnectedBackgroundError("CONNECTED_BACKGROUND_INVALID")
        if self.external_wake:
            if not self._external_active:
                return True
            # Stop admitting new external wakes before waiting for the current
            # in-process request, if any, to release the cycle lock.  Cross-host
            # exclusion remains database-authoritative.
            self._external_active = False
            self._stopping.set()

            async def wait_for_cycle_drain() -> None:
                async with self._cycle_lock:
                    return

            try:
                await asyncio.wait_for(
                    wait_for_cycle_drain(),
                    timeout=float(timeout_seconds),
                )
            except TimeoutError:
                return False
            return True
        task = self._task
        if task is None:
            return True
        self._stopping.set()
        self._wake.set()
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=float(timeout_seconds))
            drained = True
        except TimeoutError:
            # Process termination can interrupt a provider call after its
            # effect fence.  Cancellation is safe only because the invoked
            # outbox/schedule claim remains durable and startup reconciliation
            # will classify it without blindly re-executing the effect.
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            drained = False
        finally:
            self._task = None
        return drained

    def __repr__(self) -> str:
        return "ConnectedOperatorBackgroundSupervisor(authority='durable', content='<none>')"
