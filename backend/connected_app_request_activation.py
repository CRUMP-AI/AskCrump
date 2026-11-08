"""Request-scoped activation for Vercel OIDC-backed connected operators.

Vercel Functions place a rotating OIDC assertion on the incoming request.  A
process-start factory therefore cannot safely unwrap the connected-operator
root key. This module lets an already-authenticated route acquire the exact
production graph, then renews it behind a bounded in-flight request drain.

Importing and configuring this module is inert. With either release lock off,
acquisition does not inspect the assertion source, call KMS, derive a key, or
evaluate the graph-input builder. There is deliberately no broad HTTP
middleware entry point: each connected boundary authenticates before calling
``acquire_connected_request_activation``.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
import re
from typing import Awaitable, Callable, Protocol, TypeVar

from . import config
from .connected_app_activation import (
    ConnectedApplicationActivation,
    ConnectedApplicationActivationError,
    configure_connected_application_activation,
)
from .connected_app_key_derivation import ConnectedDerivedKeyset, ConnectedRootKeyMaterial
from .connected_app_kms import ConnectedVercelOIDCAssertion
from .connected_app_production_keys import ConnectedProductionKeys
from .runtime import settings


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_T = TypeVar("_T")


class ConnectedRequestActivationError(RuntimeError):
    """Content-free lazy activation failure."""

    _CODES = frozenset(
        {
            "CONNECTED_REQUEST_ACTIVATION_INVALID",
            "CONNECTED_REQUEST_ACTIVATION_NOT_RELEASED",
            "CONNECTED_REQUEST_ACTIVATION_NOT_READY",
            "CONNECTED_REQUEST_ACTIVATION_DRAIN_TIMEOUT",
            "CONNECTED_REQUEST_ACTIVATION_CLOSED",
        }
    )

    def __init__(self, code: str) -> None:
        self.code = code if code in self._CODES else "CONNECTED_REQUEST_ACTIVATION_NOT_READY"
        super().__init__(self.code)


class ConnectedRequestRootLoader(Protocol):
    async def load(
        self,
        *,
        assertion: ConnectedVercelOIDCAssertion,
    ) -> ConnectedRootKeyMaterial: ...


class ConnectedRequestGraphInputBuilder(Protocol):
    async def build(
        self,
        *,
        keys: ConnectedProductionKeys,
        expected_manifest_sha256: str,
        assertion: ConnectedVercelOIDCAssertion,
    ) -> object: ...


class ConnectedRequestActivationHost(Protocol):
    async def install(
        self,
        *,
        inputs: object,
        keys: ConnectedProductionKeys,
        expected_manifest_sha256: str,
        now: Callable[[], datetime],
    ) -> object: ...

    async def replace(
        self,
        *,
        current: object,
        inputs: object,
        keys: ConnectedProductionKeys,
        expected_manifest_sha256: str,
        now: Callable[[], datetime],
    ) -> object: ...

    async def shutdown(self, current: object) -> bool: ...


def _aware(value: object) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ConnectedRequestActivationError("CONNECTED_REQUEST_ACTIVATION_INVALID")
    return value.astimezone(UTC)


def _locks_enabled() -> bool:
    return (
        config.connected_apps_release_candidate_source_released() is True
        and settings.connected_apps_enabled is True
    )


class _ProductionRequestActivationHost:
    """Atomic adapter over the concrete production factory and activation globals."""

    __slots__ = ("_inputs", "_registered", "_source")

    def __init__(self) -> None:
        self._inputs: object | None = None
        self._registered = False

        def source() -> object:
            value = self._inputs
            if value is None:
                raise ConnectedRequestActivationError(
                    "CONNECTED_REQUEST_ACTIVATION_NOT_READY"
                )
            return value

        self._source = source

    @staticmethod
    def _require_inputs(
        inputs: object,
        keys: ConnectedProductionKeys,
        expected_manifest_sha256: str,
    ) -> None:
        # Import lazily so lock-false application imports never touch production
        # graph construction or secret-bearing dependency types.
        from .connected_app_production import ConnectedProductionGraphInputs

        if (
            type(inputs) is not ConnectedProductionGraphInputs
            or inputs.keys is not keys
            or keys.composition_manifest_sha256 != expected_manifest_sha256
            or config.CONNECTED_APPS_COMPOSITION_MANIFEST_SHA256
            != expected_manifest_sha256
        ):
            raise ConnectedRequestActivationError(
                "CONNECTED_REQUEST_ACTIVATION_NOT_READY"
            )

    @staticmethod
    def _clear_inactive_activation(activation: object) -> None:
        from . import connected_app_activation as activation_module

        if (
            activation_module.connected_application_activation is activation
            and getattr(activation, "active", None) is False
        ):
            configure_connected_application_activation(None)

    async def install(
        self,
        *,
        inputs: object,
        keys: ConnectedProductionKeys,
        expected_manifest_sha256: str,
        now: Callable[[], datetime],
    ) -> ConnectedApplicationActivation:
        from . import connected_app_activation as activation_module
        from . import connected_app_bootstrap as bootstrap_module
        from . import connected_app_production as production_module

        self._require_inputs(inputs, keys, expected_manifest_sha256)
        if activation_module.connected_application_activation is not None:
            raise ConnectedRequestActivationError(
                "CONNECTED_REQUEST_ACTIVATION_NOT_READY"
            )
        if not self._registered:
            if (
                production_module.connected_production_inputs_source is not None
                or bootstrap_module.connected_application_factory is not None
            ):
                raise ConnectedRequestActivationError(
                    "CONNECTED_REQUEST_ACTIVATION_NOT_READY"
                )
            self._inputs = inputs
            production_module.configure_connected_production_inputs_source(self._source)
            try:
                factory = (
                    production_module.register_connected_production_application_factory()
                )
                if type(factory) is not production_module.ConnectedProductionApplicationFactory:
                    raise ConnectedRequestActivationError(
                        "CONNECTED_REQUEST_ACTIVATION_NOT_READY"
                    )
            except BaseException:
                self._inputs = None
                if (
                    bootstrap_module.connected_application_factory is None
                    and production_module.connected_production_inputs_source is self._source
                ):
                    production_module.configure_connected_production_inputs_source(None)
                raise
            self._registered = True
        else:
            self._inputs = inputs
        activation = bootstrap_module.prepare_connected_application_activation(now=now)
        if type(activation) is not ConnectedApplicationActivation:
            self._inputs = None
            raise ConnectedRequestActivationError(
                "CONNECTED_REQUEST_ACTIVATION_NOT_READY"
            )
        try:
            await activation.startup()
        except BaseException:
            self._inputs = None
            self._clear_inactive_activation(activation)
            raise
        return activation

    async def replace(
        self,
        *,
        current: object,
        inputs: object,
        keys: ConnectedProductionKeys,
        expected_manifest_sha256: str,
        now: Callable[[], datetime],
    ) -> ConnectedApplicationActivation:
        if type(current) is not ConnectedApplicationActivation or not current.active:
            raise ConnectedRequestActivationError(
                "CONNECTED_REQUEST_ACTIVATION_NOT_READY"
            )
        self._require_inputs(inputs, keys, expected_manifest_sha256)
        if not await current.shutdown():
            self._clear_inactive_activation(current)
            raise ConnectedRequestActivationError(
                "CONNECTED_REQUEST_ACTIVATION_NOT_READY"
            )
        configure_connected_application_activation(None)
        self._inputs = inputs

        from . import connected_app_bootstrap as bootstrap_module

        activation = bootstrap_module.prepare_connected_application_activation(now=now)
        if type(activation) is not ConnectedApplicationActivation:
            self._inputs = None
            raise ConnectedRequestActivationError(
                "CONNECTED_REQUEST_ACTIVATION_NOT_READY"
            )
        try:
            await activation.startup()
        except BaseException:
            self._inputs = None
            self._clear_inactive_activation(activation)
            raise
        return activation

    async def shutdown(self, current: object) -> bool:
        if type(current) is not ConnectedApplicationActivation:
            return False
        result = await current.shutdown()
        if result:
            configure_connected_application_activation(None)
        return result

    def __getstate__(self) -> object:
        raise TypeError("connected request activation hosts cannot be serialized")

    def __reduce__(self) -> object:
        raise TypeError("connected request activation hosts cannot be serialized")


class ConnectedRequestActivationLease:
    """One counted request reference; release is idempotent and content-free."""

    __slots__ = ("_coordinator", "_released")

    def __init__(self, coordinator: ConnectedRequestActivationCoordinator) -> None:
        self._coordinator = coordinator
        self._released = False

    async def release(self) -> None:
        if self._released:
            return
        self._released = True
        await self._coordinator._release()

    async def __aenter__(self) -> ConnectedRequestActivationLease:
        return self

    async def __aexit__(self, _exc_type, _exc, _traceback) -> None:
        await self.release()


class ConnectedRequestActivationCoordinator:
    """Single-winner first activation and bounded, in-flight-safe renewal."""

    def __init__(
        self,
        *,
        root_loader: ConnectedRequestRootLoader,
        inputs_builder: ConnectedRequestGraphInputBuilder,
        expected_manifest_sha256: str,
        host: ConnectedRequestActivationHost | None = None,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        renewal_margin: timedelta = timedelta(seconds=60),
        drain_timeout_seconds: float = 30.0,
    ) -> None:
        if (
            not callable(getattr(root_loader, "load", None))
            or not callable(getattr(inputs_builder, "build", None))
            or not isinstance(expected_manifest_sha256, str)
            or not _SHA256.fullmatch(expected_manifest_sha256)
            or not callable(now)
            or type(renewal_margin) is not timedelta
            or not timedelta(0) < renewal_margin <= timedelta(minutes=5)
            or type(drain_timeout_seconds) not in (int, float)
            or not 0 < drain_timeout_seconds <= 300
            or float(drain_timeout_seconds) >= renewal_margin.total_seconds()
        ):
            raise ConnectedRequestActivationError(
                "CONNECTED_REQUEST_ACTIVATION_INVALID"
            )
        selected_host = host or _ProductionRequestActivationHost()
        if any(
            not callable(getattr(selected_host, method, None))
            for method in ("install", "replace", "shutdown")
        ):
            raise ConnectedRequestActivationError(
                "CONNECTED_REQUEST_ACTIVATION_INVALID"
            )
        self._root_loader = root_loader
        self._inputs_builder = inputs_builder
        self._expected_manifest_sha256 = expected_manifest_sha256
        self._host = selected_host
        self._now = now
        self._renewal_margin = renewal_margin
        self._drain_timeout_seconds = float(drain_timeout_seconds)
        self._condition = asyncio.Condition()
        self._current: object | None = None
        self._expires_at: datetime | None = None
        self._in_flight = 0
        self._transition = False
        self._closing = False

    @property
    def expected_manifest_sha256(self) -> str:
        return self._expected_manifest_sha256

    @property
    def active(self) -> bool:
        return self._current is not None and self._expires_at is not None

    @property
    def in_flight(self) -> int:
        return self._in_flight

    @property
    def reconfigurable(self) -> bool:
        return not (
            self.active
            or self._in_flight
            or self._transition
            or self._closing
        )

    def _require_released(self) -> None:
        if (
            not _locks_enabled()
            or config.CONNECTED_APPS_COMPOSITION_MANIFEST_SHA256
            != self._expected_manifest_sha256
        ):
            raise ConnectedRequestActivationError(
                "CONNECTED_REQUEST_ACTIVATION_NOT_RELEASED"
            )

    def _fresh(self, reference: datetime) -> bool:
        return (
            self._current is not None
            and self._expires_at is not None
            and reference + self._renewal_margin < self._expires_at
        )

    @staticmethod
    async def _bounded(
        operation: Awaitable[_T],
        *,
        deadline: float,
    ) -> _T:
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            if asyncio.iscoroutine(operation):
                operation.close()
            raise ConnectedRequestActivationError(
                "CONNECTED_REQUEST_ACTIVATION_DRAIN_TIMEOUT"
            )
        try:
            return await asyncio.wait_for(operation, timeout=remaining)
        except TimeoutError:
            raise ConnectedRequestActivationError(
                "CONNECTED_REQUEST_ACTIVATION_DRAIN_TIMEOUT"
            ) from None

    async def _clear_stopped_current(self, current: object | None) -> None:
        if current is None or getattr(current, "active", None) is not False:
            return
        async with self._condition:
            if self._current is current:
                self._current = None
                self._expires_at = None

    async def _discard_activated(self, activated: object | None) -> None:
        if activated is None:
            return
        try:
            await asyncio.wait_for(
                self._host.shutdown(activated),
                timeout=self._drain_timeout_seconds,
            )
        except BaseException:
            pass

    async def acquire(
        self,
        assertion_source: Callable[[], str | None],
    ) -> ConnectedRequestActivationLease:
        """Acquire an active graph reference, loading the assertion only if needed."""

        if not callable(assertion_source):
            raise ConnectedRequestActivationError(
                "CONNECTED_REQUEST_ACTIVATION_INVALID"
            )
        self._require_released()
        while True:
            reference = _aware(self._now())
            async with self._condition:
                if self._closing:
                    raise ConnectedRequestActivationError(
                        "CONNECTED_REQUEST_ACTIVATION_CLOSED"
                    )
                if self._fresh(reference):
                    self._in_flight += 1
                    return ConnectedRequestActivationLease(self)
                if self._transition:
                    await self._condition.wait()
                    continue
                self._transition = True
                current = self._current
                break

        transition_budget = self._drain_timeout_seconds
        if self._expires_at is not None:
            transition_budget = min(
                transition_budget,
                max(0.0, (self._expires_at - reference).total_seconds() - 1.0),
            )
        transition_deadline = asyncio.get_running_loop().time() + transition_budget
        activated: object | None = None
        try:
            assertion_value = assertion_source()
            if not isinstance(assertion_value, str):
                raise ConnectedRequestActivationError(
                    "CONNECTED_REQUEST_ACTIVATION_NOT_READY"
                )
            assertion = ConnectedVercelOIDCAssertion(assertion_value)
            root = await self._bounded(
                self._root_loader.load(assertion=assertion),
                deadline=transition_deadline,
            )
            if type(root) is not ConnectedRootKeyMaterial:
                raise ConnectedRequestActivationError(
                    "CONNECTED_REQUEST_ACTIVATION_NOT_READY"
                )
            keyset = ConnectedDerivedKeyset(
                root=root,
                composition_manifest_sha256=self._expected_manifest_sha256,
                now=self._now,
            )
            keys = ConnectedProductionKeys.build(keyset, now=self._now)
            expires_at = _aware(keys.expires_at)
            if _aware(self._now()) + self._renewal_margin >= expires_at:
                raise ConnectedRequestActivationError(
                    "CONNECTED_REQUEST_ACTIVATION_NOT_READY"
                )
            inputs = await self._bounded(
                self._inputs_builder.build(
                    keys=keys,
                    expected_manifest_sha256=self._expected_manifest_sha256,
                    assertion=assertion,
                ),
                deadline=transition_deadline,
            )

            async with self._condition:
                while self._in_flight:
                    remaining = (
                        transition_deadline - asyncio.get_running_loop().time()
                    )
                    if remaining <= 0:
                        raise ConnectedRequestActivationError(
                            "CONNECTED_REQUEST_ACTIVATION_DRAIN_TIMEOUT"
                        )
                    try:
                        await asyncio.wait_for(self._condition.wait(), timeout=remaining)
                    except TimeoutError:
                        raise ConnectedRequestActivationError(
                            "CONNECTED_REQUEST_ACTIVATION_DRAIN_TIMEOUT"
                        ) from None
                if self._closing:
                    raise ConnectedRequestActivationError(
                        "CONNECTED_REQUEST_ACTIVATION_CLOSED"
                    )

            if current is None:
                activated = await self._bounded(
                    self._host.install(
                        inputs=inputs,
                        keys=keys,
                        expected_manifest_sha256=self._expected_manifest_sha256,
                        now=self._now,
                    ),
                    deadline=transition_deadline,
                )
            else:
                activated = await self._bounded(
                    self._host.replace(
                        current=current,
                        inputs=inputs,
                        keys=keys,
                        expected_manifest_sha256=self._expected_manifest_sha256,
                        now=self._now,
                    ),
                    deadline=transition_deadline,
                )
            if _aware(self._now()) + self._renewal_margin >= expires_at:
                raise ConnectedRequestActivationError(
                    "CONNECTED_REQUEST_ACTIVATION_NOT_READY"
                )
            async with self._condition:
                if self._closing:
                    # The host graph exists but no request may enter it while a
                    # process shutdown is waiting.  The shutdown path owns it.
                    self._current = activated
                    self._expires_at = expires_at
                    activated = None
                    raise ConnectedRequestActivationError(
                        "CONNECTED_REQUEST_ACTIVATION_CLOSED"
                    )
                self._current = activated
                self._expires_at = expires_at
                self._in_flight += 1
                return ConnectedRequestActivationLease(self)
        except asyncio.CancelledError:
            await self._discard_activated(activated)
            await self._clear_stopped_current(current)
            raise
        except ConnectedRequestActivationError:
            await self._discard_activated(activated)
            await self._clear_stopped_current(current)
            raise
        except Exception:
            await self._discard_activated(activated)
            await self._clear_stopped_current(current)
            raise ConnectedRequestActivationError(
                "CONNECTED_REQUEST_ACTIVATION_NOT_READY"
            ) from None
        finally:
            async with self._condition:
                self._transition = False
                self._condition.notify_all()

    async def _release(self) -> None:
        async with self._condition:
            if self._in_flight <= 0:
                raise ConnectedRequestActivationError(
                    "CONNECTED_REQUEST_ACTIVATION_INVALID"
                )
            self._in_flight -= 1
            self._condition.notify_all()

    async def shutdown(self) -> bool:
        """Stop new acquisitions, drain counted requests, then clear the graph."""

        deadline = asyncio.get_running_loop().time() + self._drain_timeout_seconds
        async with self._condition:
            self._closing = True
            while self._transition or self._in_flight:
                remaining = deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    return False
                try:
                    await asyncio.wait_for(self._condition.wait(), timeout=remaining)
                except TimeoutError:
                    return False
            current = self._current
        if current is None:
            return True
        try:
            stopped = bool(await self._host.shutdown(current))
        except Exception:
            stopped = False
        if stopped:
            async with self._condition:
                self._current = None
                self._expires_at = None
                self._condition.notify_all()
        return stopped

    def __repr__(self) -> str:
        return "ConnectedRequestActivationCoordinator(authority='request-oidc', secrets='<redacted>')"

    def __getstate__(self) -> object:
        raise TypeError("connected request activation coordinators cannot be serialized")

    def __reduce__(self) -> object:
        raise TypeError("connected request activation coordinators cannot be serialized")


connected_request_activation_coordinator: ConnectedRequestActivationCoordinator | None = None


def configure_connected_request_activation(
    coordinator: ConnectedRequestActivationCoordinator | None,
) -> None:
    global connected_request_activation_coordinator
    current = connected_request_activation_coordinator
    if current is not None and not current.reconfigurable:
        raise ConnectedRequestActivationError(
            "CONNECTED_REQUEST_ACTIVATION_NOT_READY"
        )
    if coordinator is not None and type(coordinator) is not ConnectedRequestActivationCoordinator:
        raise ConnectedRequestActivationError("CONNECTED_REQUEST_ACTIVATION_INVALID")
    connected_request_activation_coordinator = coordinator


def connected_request_activation_deferred() -> bool:
    """Return true only for an exact released manifest with a configured edge."""

    coordinator = connected_request_activation_coordinator
    if not _locks_enabled() or coordinator is None:
        return False
    if (
        coordinator.expected_manifest_sha256
        != config.CONNECTED_APPS_COMPOSITION_MANIFEST_SHA256
    ):
        raise ConnectedApplicationActivationError("CONNECTED_APPLICATION_NOT_READY")
    return True


async def acquire_connected_request_activation(
    assertion_source: Callable[[], str | None],
) -> ConnectedRequestActivationLease | None:
    """Acquire the released graph for an already-authenticated connected request.

    Connected routes call this only after authentication (and chat after its
    deterministic connected-intent filter). The absence of a broad middleware
    keeps an OIDC or KMS outage from disabling unrelated Ask Crump traffic.
    """

    coordinator = connected_request_activation_coordinator
    if not _locks_enabled() or coordinator is None:
        return None
    if not callable(assertion_source):
        raise ConnectedRequestActivationError("CONNECTED_REQUEST_ACTIVATION_INVALID")
    return await coordinator.acquire(assertion_source)


async def shutdown_connected_request_activation() -> bool | None:
    coordinator = connected_request_activation_coordinator
    if coordinator is None:
        return None
    return await coordinator.shutdown()


__all__ = [
    "ConnectedRequestActivationCoordinator",
    "ConnectedRequestActivationError",
    "ConnectedRequestActivationHost",
    "ConnectedRequestActivationLease",
    "ConnectedRequestGraphInputBuilder",
    "ConnectedRequestRootLoader",
    "acquire_connected_request_activation",
    "configure_connected_request_activation",
    "connected_request_activation_deferred",
    "shutdown_connected_request_activation",
]
