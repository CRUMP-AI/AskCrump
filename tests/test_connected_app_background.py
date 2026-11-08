from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from backend.connected_app_background import (
    CONNECTED_BACKGROUND_MODE_EXTERNAL_WAKE,
    ConnectedBackgroundError,
    ConnectedOperatorBackgroundSupervisor,
)
from backend.connected_app_cleanup_reconciliation import (
    ConnectedExternalReconciliationResult,
)
from backend.connected_app_execution_outbox import ConnectedDispatchBatchResult
from backend.connected_app_multi_step_continuation import (
    ConnectedMultiStepContinuationBatchResult,
)
from backend.connected_app_payload_retention import ConnectedPayloadRetentionResult


class Dispatch:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.startups = 0
        self.cycles = 0

    async def reconcile_startup(self, *, owner_limit, per_owner_limit):
        self.startups += 1
        assert owner_limit == 2 and per_owner_limit == 3
        return ()

    async def run_bounded(self, *, owner_limit, per_owner_limit):
        self.cycles += 1
        if self.fail:
            raise RuntimeError("customer content must not escape")
        return ConnectedDispatchBatchResult(
            owners_scanned=1,
            actions_considered=2,
            actions_invoked=1,
            terminal_records=(),
        )


class Scheduler:
    def __init__(self, *, fail: bool = False, block: bool = False) -> None:
        self.fail = fail
        self.block = block
        self.cycles = 0
        self.entered = asyncio.Event()

    async def run_batch(self, *, maximum):
        self.cycles += 1
        assert maximum == 4
        self.entered.set()
        if self.block:
            await asyncio.Event().wait()
        if self.fail:
            raise RuntimeError("provider payload must not escape")
        return ()


class Reconciler:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[tuple[int, int]] = []

    async def run_bounded(self, *, cleanup_maximum, expiry_maximum):
        self.calls.append((cleanup_maximum, expiry_maximum))
        if self.fail:
            raise RuntimeError("provider cleanup detail")
        return ConnectedExternalReconciliationResult(
            cleanup_attempts=2,
            cleanup_terminal=1,
            expired_flows=3,
            expired_provisionals=4,
            cleanup_failed=False,
            expiry_failed=False,
            observed_at=datetime(2026, 11, 8, 8, 0, tzinfo=UTC),
        )


class Continuation:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[int] = []

    async def run_bounded(self, *, maximum):
        self.calls.append(maximum)
        if self.fail:
            raise RuntimeError("instruction content must not escape")
        return ConnectedMultiStepContinuationBatchResult(
            candidates_considered=3,
            claims_acquired=2,
            terminal_count=1,
            failed_count=0,
        )


class Retention:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[tuple[int, int, int]] = []

    async def run_bounded(self, *, payload_maximum, plan_maximum, loop_maximum):
        self.calls.append((payload_maximum, plan_maximum, loop_maximum))
        if self.fail:
            raise RuntimeError("ciphertext must not escape")
        return ConnectedPayloadRetentionResult(
            payloads_purged=2,
            plans_purged=3,
            loop_envelopes_purged=4,
        )


def supervisor(dispatch=None, scheduler=None, **values):
    return ConnectedOperatorBackgroundSupervisor(
        source_released=True,
        readiness_attested=True,
        require_ready=values.pop("require_ready", lambda: None),
        composition_manifest_sha256="f" * 64,
        dispatch=dispatch or Dispatch(),
        scheduler=scheduler or Scheduler(),
        interval_seconds=values.pop("interval_seconds", 0.1),
        owner_limit=2,
        per_owner_limit=3,
        schedule_limit=4,
        **values,
    )


def test_release_and_readiness_are_independent_fail_closed_gates() -> None:
    with pytest.raises(ConnectedBackgroundError, match="CONNECTED_BACKGROUND_NOT_RELEASED"):
        ConnectedOperatorBackgroundSupervisor(
            source_released=False,
            readiness_attested=True,
            require_ready=lambda: None,
            composition_manifest_sha256="f" * 64,
            dispatch=Dispatch(),
            scheduler=Scheduler(),
        )
    with pytest.raises(ConnectedBackgroundError, match="CONNECTED_BACKGROUND_NOT_READY"):
        ConnectedOperatorBackgroundSupervisor(
            source_released=True,
            readiness_attested=False,
            require_ready=lambda: None,
            composition_manifest_sha256="f" * 64,
            dispatch=Dispatch(),
            scheduler=Scheduler(),
        )

    with pytest.raises(ConnectedBackgroundError, match="CONNECTED_BACKGROUND_NOT_READY"):
        ConnectedOperatorBackgroundSupervisor(
            source_released=True,
            readiness_attested=True,
            require_ready=None,  # type: ignore[arg-type]
            composition_manifest_sha256="f" * 64,
            dispatch=Dispatch(),
            scheduler=Scheduler(),
        )


@pytest.mark.asyncio
async def test_cycle_records_only_content_free_counts_and_isolates_failures() -> None:
    result = await supervisor(dispatch=Dispatch(fail=True)).run_cycle()

    assert result.dispatch_failed is True
    assert result.scheduler_failed is False
    assert result.dispatch_actions_invoked == 0
    assert result.schedule_completion_count == 0
    assert "content" not in repr(result).lower()


@pytest.mark.asyncio
async def test_continuation_is_inert_while_its_separate_source_lock_is_false() -> None:
    continuation = Continuation()
    result = await supervisor(
        multi_step_continuation=continuation,
        continuation_released=False,
    ).run_cycle()

    assert continuation.calls == []
    assert result.continuation_candidates_considered == 0
    assert result.continuation_claims_acquired == 0


@pytest.mark.asyncio
async def test_released_continuation_is_bounded_and_reports_content_free_counts() -> None:
    continuation = Continuation()
    result = await supervisor(
        multi_step_continuation=continuation,
        continuation_released=True,
        continuation_limit=5,
    ).run_cycle()

    assert continuation.calls == [5]
    assert result.continuation_candidates_considered == 3
    assert result.continuation_claims_acquired == 2
    assert result.continuation_terminal_count == 1
    assert result.continuation_failed_count == 0
    assert result.continuation_failed is False


@pytest.mark.asyncio
async def test_retention_is_bounded_readiness_fenced_and_content_free() -> None:
    retention = Retention()
    result = await supervisor(
        payload_retention=retention,
        payload_retention_limit=7,
        plan_retention_limit=9,
        loop_retention_limit=11,
    ).run_cycle()

    assert retention.calls == [(7, 9, 11)]
    assert result.expired_payloads_purged == 2
    assert result.expired_plans_purged == 3
    assert result.expired_loop_envelopes_purged == 4
    assert result.retention_failed is False


@pytest.mark.asyncio
async def test_retention_failure_is_quarantined_from_other_lanes() -> None:
    result = await supervisor(payload_retention=Retention(fail=True)).run_cycle()
    assert result.retention_failed is True
    assert result.expired_payloads_purged == 0
    assert result.dispatch_actions_invoked == 1


@pytest.mark.asyncio
async def test_startup_periodic_wake_and_clean_drain() -> None:
    dispatch = Dispatch()
    scheduler = Scheduler()
    subject = supervisor(dispatch=dispatch, scheduler=scheduler)

    await subject.startup()
    await asyncio.wait_for(scheduler.entered.wait(), timeout=1)
    assert dispatch.startups == 1
    assert dispatch.cycles >= 1
    subject.wake()
    await asyncio.sleep(0.15)
    assert dispatch.cycles >= 2
    assert await subject.shutdown(timeout_seconds=1) is True
    assert subject.running is False


@pytest.mark.asyncio
async def test_shutdown_timeout_cancels_only_after_durable_worker_entry() -> None:
    scheduler = Scheduler(block=True)
    subject = supervisor(scheduler=scheduler)
    await subject.startup()
    await asyncio.wait_for(scheduler.entered.wait(), timeout=1)

    assert await subject.shutdown(timeout_seconds=0.01) is False
    assert subject.running is False


@pytest.mark.asyncio
async def test_double_start_is_refused() -> None:
    subject = supervisor()
    await subject.startup()
    try:
        with pytest.raises(ConnectedBackgroundError, match="CONNECTED_BACKGROUND_ALREADY_STARTED"):
            await subject.startup()
    finally:
        await subject.shutdown(timeout_seconds=1)


@pytest.mark.asyncio
async def test_expired_readiness_stops_every_provider_capable_lane() -> None:
    dispatch = Dispatch()
    scheduler = Scheduler()
    ready = True

    def require_ready() -> None:
        if not ready:
            raise RuntimeError("expired")

    subject = supervisor(
        dispatch=dispatch,
        scheduler=scheduler,
        require_ready=require_ready,
    )
    await subject.run_cycle()
    assert dispatch.cycles == 1
    assert scheduler.cycles == 1

    ready = False
    with pytest.raises(ConnectedBackgroundError, match="CONNECTED_BACKGROUND_NOT_READY"):
        await subject.run_cycle()
    assert dispatch.cycles == 1
    assert scheduler.cycles == 1


@pytest.mark.asyncio
async def test_readiness_is_rechecked_between_dispatch_and_schedule() -> None:
    scheduler = Scheduler()
    ready = True

    class ExpiringDispatch(Dispatch):
        async def run_bounded(self, *, owner_limit, per_owner_limit):
            nonlocal ready
            result = await super().run_bounded(
                owner_limit=owner_limit,
                per_owner_limit=per_owner_limit,
            )
            ready = False
            return result

    def require_ready() -> None:
        if not ready:
            raise RuntimeError("expired")

    subject = supervisor(
        dispatch=ExpiringDispatch(),
        scheduler=scheduler,
        require_ready=require_ready,
    )
    result = await subject.run_cycle()
    assert result.dispatch_actions_invoked == 1
    assert result.scheduler_failed is True
    assert scheduler.cycles == 0


@pytest.mark.asyncio
async def test_periodic_worker_recovers_after_readiness_is_renewed() -> None:
    dispatch = Dispatch()
    scheduler = Scheduler()
    ready = True

    def require_ready() -> None:
        if not ready:
            raise RuntimeError("expired")

    subject = supervisor(
        dispatch=dispatch,
        scheduler=scheduler,
        require_ready=require_ready,
    )
    await subject.startup()
    try:
        await asyncio.wait_for(scheduler.entered.wait(), timeout=1)
        ready = False
        completed_before_lapse = dispatch.cycles
        subject.wake()
        await asyncio.sleep(0.15)
        assert subject.running is True
        assert dispatch.cycles == completed_before_lapse

        ready = True
        subject.wake()
        for _ in range(20):
            if dispatch.cycles > completed_before_lapse:
                break
            await asyncio.sleep(0.01)
        assert dispatch.cycles > completed_before_lapse
    finally:
        await subject.shutdown(timeout_seconds=1)


@pytest.mark.asyncio
async def test_external_wake_mode_starts_without_a_daemon_or_cold_start_scan() -> None:
    dispatch = Dispatch()
    scheduler = Scheduler()
    subject = supervisor(
        dispatch=dispatch,
        scheduler=scheduler,
        execution_mode=CONNECTED_BACKGROUND_MODE_EXTERNAL_WAKE,
    )

    await subject.startup()
    assert subject.running is True
    assert subject.external_wake is True
    assert subject.execution_mode == CONNECTED_BACKGROUND_MODE_EXTERNAL_WAKE
    assert dispatch.startups == 0
    assert dispatch.cycles == 0

    subject.wake()
    await asyncio.sleep(0.15)
    assert dispatch.cycles == 0

    result = await subject.run_cycle()
    assert result.dispatch_actions_invoked == 1
    assert dispatch.cycles == 1
    assert scheduler.cycles == 1
    assert await subject.shutdown(timeout_seconds=1) is True
    assert subject.running is False

    with pytest.raises(ConnectedBackgroundError, match="CONNECTED_BACKGROUND_NOT_READY"):
        await subject.run_cycle()


def test_external_wake_mode_is_exact_and_unknown_modes_fail_closed() -> None:
    with pytest.raises(ConnectedBackgroundError, match="CONNECTED_BACKGROUND_INVALID"):
        supervisor(execution_mode="serverless-ish")


@pytest.mark.asyncio
async def test_external_wake_runs_the_optional_bounded_reconciliation_lane_first() -> None:
    reconciler = Reconciler()
    subject = supervisor(
        reconciler=reconciler,
        cleanup_limit=5,
        expiry_limit=6,
        execution_mode=CONNECTED_BACKGROUND_MODE_EXTERNAL_WAKE,
    )
    await subject.startup()
    try:
        result = await subject.run_cycle()
    finally:
        await subject.shutdown(timeout_seconds=1)

    assert reconciler.calls == [(5, 6)]
    assert result.cleanup_attempts == 2
    assert result.cleanup_terminal_count == 1
    assert result.expired_oauth_flow_count == 3
    assert result.expired_oauth_provisional_count == 4
    assert result.reconciliation_failed is False


def test_external_reconciler_cannot_be_attached_to_the_continuous_loop() -> None:
    with pytest.raises(ConnectedBackgroundError, match="CONNECTED_BACKGROUND_INVALID"):
        supervisor(reconciler=Reconciler())
