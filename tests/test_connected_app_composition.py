from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib

import pytest

from backend.connected_app_composition import (
    ConnectedOperatorComposition,
    ConnectedProductionDependencies,
    ConnectedProductionReadiness,
    compose_connected_operator,
)
from backend.connected_app_runtime import ConnectedAppRuntime
from backend.connected_app_scheduler import ConnectedSchedulerError


NOW = datetime(2026, 11, 7, 20, 0, tzinfo=timezone.utc)
MANIFEST = hashlib.sha256(b"exact production composition").hexdigest()


def readiness() -> ConnectedProductionReadiness:
    return ConnectedProductionReadiness(
        MANIFEST,
        NOW,
        NOW + timedelta(minutes=5),
        True,
        True,
        True,
        True,
        True,
        True,
        True,
        True,
        True,
        True,
        True,
        True,
    )


def dependencies() -> ConnectedProductionDependencies:
    # Construction is deliberately structural.  Individual durable adapters
    # remain independently attested and are exercised only after composition.
    boundary = object()

    class ReadResults:
        async def settle(self, **_kwargs):
            return None

        async def replay(self, **_kwargs):
            return None

        async def recover(self, **_kwargs):
            return None

    class ScheduleResolver:
        async def prepare(self, _claim):
            return None

    return ConnectedProductionDependencies(
        accounts=boundary,
        credentials=boundary,
        ledger=boundary,
        lease_consumer=boundary,
        google_provider=boundary,
        microsoft_provider=boundary,
        read_results=ReadResults(),
        schedule_store=boundary,
        schedule_resolver=ScheduleResolver(),
    )


def test_composition_requires_separate_source_release_decision():
    with pytest.raises(ConnectedSchedulerError, match="CONNECTED_APPS_NOT_RELEASED"):
        compose_connected_operator(
            source_released=False,
            readiness_source=readiness,
            expected_manifest_sha256=MANIFEST,
            dependencies=dependencies(),
            now=lambda: NOW,
        )


@pytest.mark.parametrize(
    "field",
    [
        "durable_control_plane",
        "durable_payload_vault",
        "payload_binding_contract_attested",
        "durable_credential_vault",
        "trusted_key_manager",
        "cross_host_refresh_serialization",
        "oauth_registrations_attested",
        "provider_contracts_attested",
        "provider_smoke_attested",
        "scheduler_store_attested",
        "deletion_cleanup_attested",
        "no_browser_fallback_attested",
    ],
)
def test_every_attestation_is_mandatory(field):
    with pytest.raises(ConnectedSchedulerError, match="CONNECTED_APPS_NOT_READY"):
        compose_connected_operator(
            source_released=True,
            readiness_source=lambda: replace(readiness(), **{field: False}),
            expected_manifest_sha256=MANIFEST,
            dependencies=dependencies(),
            now=lambda: NOW,
        )


def test_manifest_expiry_future_timestamp_and_dependency_absence_fail_closed():
    cases = (
        (readiness(), hashlib.sha256(b"wrong").hexdigest(), dependencies()),
        (
            replace(
                readiness(),
                checked_at=NOW - timedelta(minutes=2),
                expires_at=NOW - timedelta(minutes=1),
            ),
            MANIFEST,
            dependencies(),
        ),
        (
            replace(
                readiness(),
                checked_at=NOW + timedelta(seconds=6),
                expires_at=NOW + timedelta(minutes=10),
            ),
            MANIFEST,
            dependencies(),
        ),
        (readiness(), MANIFEST, None),
    )
    for attestation, manifest, values in cases:
        with pytest.raises(ConnectedSchedulerError, match="CONNECTED_APPS_NOT_READY"):
            compose_connected_operator(
                source_released=True,
                readiness_source=lambda attestation=attestation: attestation,
                expected_manifest_sha256=manifest,
                dependencies=values,
                now=lambda: NOW,
            )


def test_exact_current_attestation_builds_only_the_injected_graph():
    result = compose_connected_operator(
        source_released=True,
        readiness_source=readiness,
        expected_manifest_sha256=MANIFEST,
        dependencies=dependencies(),
        now=lambda: NOW,
    )
    assert type(result) is ConnectedOperatorComposition
    assert result.composition_manifest_sha256 == MANIFEST
    assert result.composed_at == NOW
    assert "object" not in repr(result)


def test_readiness_is_revalidated_for_every_provider_capable_scheduler_call():
    current = readiness()
    result = compose_connected_operator(
        source_released=True,
        readiness_source=lambda: current,
        expected_manifest_sha256=MANIFEST,
        dependencies=dependencies(),
        now=lambda: NOW,
    )
    current = replace(
        current,
        checked_at=NOW - timedelta(minutes=2),
        expires_at=NOW - timedelta(minutes=1),
    )
    with pytest.raises(ConnectedSchedulerError, match="CONNECTED_APPS_NOT_READY"):
        result.scheduler._require_ready()


def test_runtime_bound_schedule_resolver_factory_is_invoked_exactly_once():
    calls: list[ConnectedAppRuntime] = []

    class ScheduleResolver:
        async def prepare(self, _claim):
            return None

    resolver = ScheduleResolver()

    def factory(runtime: ConnectedAppRuntime):
        assert type(runtime) is ConnectedAppRuntime
        calls.append(runtime)
        return resolver

    result = compose_connected_operator(
        source_released=True,
        readiness_source=readiness,
        expected_manifest_sha256=MANIFEST,
        dependencies=replace(
            dependencies(),
            schedule_resolver=None,
            schedule_resolver_factory=factory,
        ),
        now=lambda: NOW,
    )

    assert calls == [result.runtime]
    assert result.scheduler._resolver is resolver


@pytest.mark.parametrize(
    "values",
    [
        {"schedule_resolver": None, "schedule_resolver_factory": None},
        {"schedule_resolver_factory": lambda _runtime: object()},
        {
            "schedule_resolver": None,
            "schedule_resolver_factory": lambda _runtime: object(),
        },
        {"schedule_resolver": object()},
    ],
)
def test_schedule_resolver_selection_and_protocol_fail_closed(values):
    with pytest.raises(ConnectedSchedulerError, match="CONNECTED_APPS_NOT_READY"):
        compose_connected_operator(
            source_released=True,
            readiness_source=readiness,
            expected_manifest_sha256=MANIFEST,
            dependencies=replace(dependencies(), **values),
            now=lambda: NOW,
        )


def test_schedule_resolver_factory_failure_is_content_free():
    def broken(_runtime):
        raise RuntimeError("provider-secret-must-not-escape")

    with pytest.raises(ConnectedSchedulerError) as caught:
        compose_connected_operator(
            source_released=True,
            readiness_source=readiness,
            expected_manifest_sha256=MANIFEST,
            dependencies=replace(
                dependencies(),
                schedule_resolver=None,
                schedule_resolver_factory=broken,
            ),
            now=lambda: NOW,
        )
    assert "provider-secret" not in str(caught.value)
