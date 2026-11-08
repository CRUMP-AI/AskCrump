"""Fail-closed production composition contract for connected applications.

Importing this module has no side effects and cannot enable a public route.  A
caller must supply every durable boundary plus a short-lived, exact manifest
attestation and the separate source release decision before an operator can be
constructed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import re
from typing import Callable

from .connected_app_dispatch import (
    ConnectedCredentialLeaseConsumer,
    DirectConnectedProviderResolver,
)
from .connected_app_policy import ConnectedActionPolicy
from .connected_app_provider import ConnectedAppProvider
from .connected_app_runtime import (
    ConnectedAccountRegistry,
    ConnectedActionLedger,
    ConnectedAppRuntime,
    ConnectedCredentialBroker,
    ConnectedReadResultDurability,
)
from .connected_app_scheduler import (
    ConnectedScheduleRunResolver,
    ConnectedScheduleStore,
    ConnectedScheduleWorker,
    ConnectedSchedulerError,
)


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MAX_ATTESTATION_LIFETIME = timedelta(minutes=15)
_FUTURE_SKEW = timedelta(seconds=5)


def _sha(value: str, name: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ValueError(f"{name} is invalid")
    return value


def _aware(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(timezone.utc)


@dataclass(frozen=True, slots=True)
class ConnectedProductionReadiness:
    composition_manifest_sha256: str
    checked_at: datetime
    expires_at: datetime
    durable_control_plane: bool
    durable_payload_vault: bool
    payload_binding_contract_attested: bool
    durable_credential_vault: bool
    trusted_key_manager: bool
    cross_host_refresh_serialization: bool
    oauth_registrations_attested: bool
    provider_contracts_attested: bool
    provider_smoke_attested: bool
    scheduler_store_attested: bool
    deletion_cleanup_attested: bool
    no_browser_fallback_attested: bool

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "composition_manifest_sha256",
            _sha(self.composition_manifest_sha256, "composition_manifest_sha256"),
        )
        checked = _aware(self.checked_at, "checked_at")
        expires = _aware(self.expires_at, "expires_at")
        if expires <= checked or expires - checked > _MAX_ATTESTATION_LIFETIME:
            raise ValueError("readiness lifetime is invalid")
        for name in (
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
        ):
            if type(getattr(self, name)) is not bool:
                raise ValueError(f"{name} must be boolean")

    def is_ready(self, *, expected_manifest_sha256: str, now: datetime) -> bool:
        reference = _aware(now, "now")
        return (
            self.composition_manifest_sha256
            == _sha(expected_manifest_sha256, "expected_manifest_sha256")
            and self.checked_at <= reference + _FUTURE_SKEW
            and self.expires_at > reference
            and self.durable_control_plane
            and self.durable_payload_vault
            and self.payload_binding_contract_attested
            and self.durable_credential_vault
            and self.trusted_key_manager
            and self.cross_host_refresh_serialization
            and self.oauth_registrations_attested
            and self.provider_contracts_attested
            and self.provider_smoke_attested
            and self.scheduler_store_attested
            and self.deletion_cleanup_attested
            and self.no_browser_fallback_attested
        )


@dataclass(frozen=True, slots=True, repr=False)
class ConnectedProductionDependencies:
    accounts: ConnectedAccountRegistry
    credentials: ConnectedCredentialBroker
    ledger: ConnectedActionLedger
    lease_consumer: ConnectedCredentialLeaseConsumer
    google_provider: ConnectedAppProvider
    microsoft_provider: ConnectedAppProvider
    read_results: ConnectedReadResultDurability
    schedule_store: ConnectedScheduleStore
    schedule_resolver: ConnectedScheduleRunResolver | None
    schedule_resolver_factory: (
        Callable[[ConnectedAppRuntime], ConnectedScheduleRunResolver] | None
    ) = None

    def __repr__(self) -> str:
        return "ConnectedProductionDependencies(secrets='<redacted>')"


@dataclass(frozen=True, slots=True, repr=False)
class ConnectedOperatorComposition:
    runtime: ConnectedAppRuntime
    scheduler: ConnectedScheduleWorker
    providers: DirectConnectedProviderResolver
    composition_manifest_sha256: str
    composed_at: datetime

    def __repr__(self) -> str:
        return "ConnectedOperatorComposition(readiness='attested')"


def compose_connected_operator(
    *,
    source_released: bool,
    readiness_source: Callable[[], ConnectedProductionReadiness],
    expected_manifest_sha256: str,
    dependencies: ConnectedProductionDependencies | None,
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> ConnectedOperatorComposition:
    """Construct only an exact, currently attested production dependency graph."""

    if source_released is not True:
        raise ConnectedSchedulerError("CONNECTED_APPS_NOT_RELEASED")
    reference = _aware(now(), "now")
    if not callable(readiness_source):
        raise ConnectedSchedulerError("CONNECTED_APPS_NOT_READY")

    def current_readiness() -> ConnectedProductionReadiness:
        try:
            value = readiness_source()
        except Exception:
            raise ConnectedSchedulerError("CONNECTED_APPS_NOT_READY") from None
        if type(value) is not ConnectedProductionReadiness or not value.is_ready(
            expected_manifest_sha256=expected_manifest_sha256,
            now=_aware(now(), "now"),
        ):
            raise ConnectedSchedulerError("CONNECTED_APPS_NOT_READY")
        return value

    readiness = current_readiness()
    if type(dependencies) is not ConnectedProductionDependencies:
        raise ConnectedSchedulerError("CONNECTED_APPS_NOT_READY")
    assert dependencies is not None
    direct_resolver = dependencies.schedule_resolver
    resolver_factory = dependencies.schedule_resolver_factory
    if (direct_resolver is None) == (resolver_factory is None) or (
        resolver_factory is not None and not callable(resolver_factory)
    ):
        raise ConnectedSchedulerError("CONNECTED_APPS_NOT_READY")
    if direct_resolver is not None and not callable(
        getattr(direct_resolver, "prepare", None)
    ):
        raise ConnectedSchedulerError("CONNECTED_APPS_NOT_READY")
    providers = DirectConnectedProviderResolver(
        google=dependencies.google_provider,
        microsoft=dependencies.microsoft_provider,
        leases=dependencies.lease_consumer,
        now=now,
    )
    runtime = ConnectedAppRuntime(
        accounts=dependencies.accounts,
        credentials=dependencies.credentials,
        policy=ConnectedActionPolicy(),
        ledger=dependencies.ledger,
        providers=providers,
        read_results=dependencies.read_results,
        now=now,
    )

    resolver = direct_resolver
    if resolver_factory is not None:
        try:
            resolver = resolver_factory(runtime)
        except Exception:
            raise ConnectedSchedulerError("CONNECTED_APPS_NOT_READY") from None
    if resolver is None or not callable(getattr(resolver, "prepare", None)):
        raise ConnectedSchedulerError("CONNECTED_APPS_NOT_READY")

    def require_ready() -> None:
        current_readiness()

    scheduler = ConnectedScheduleWorker(
        store=dependencies.schedule_store,
        resolver=resolver,
        runtime=runtime,
        require_ready=require_ready,
        now=now,
    )
    return ConnectedOperatorComposition(
        runtime=runtime,
        scheduler=scheduler,
        providers=providers,
        composition_manifest_sha256=readiness.composition_manifest_sha256,
        composed_at=reference,
    )
