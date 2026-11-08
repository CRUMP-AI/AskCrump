"""Atomic FastAPI lifecycle for the connected-operator application.

The connected operator spans public routes, the chat interception path, an
owner-only result viewer, and two durable background workers.  Publishing any
subset would create a misleading or unsafe product, so this module installs
and removes the entire graph as one lifecycle operation.

Importing the module is inert.  The checked-in source release lock and the
environment release switch are both supplied explicitly by the separately
reviewed production bootstrap; neither a module import nor an environment
variable can activate the feature by itself.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
import re
from typing import AsyncIterator, Callable, Protocol

from fastapi import FastAPI

from .connected_app_background import ConnectedOperatorBackgroundSupervisor
from .connected_app_chat_operator import ConnectedOperatorChatService
from .connected_app_read_surface import ConnectedOwnerReadResultService
from .connected_app_service import ConnectedAppService
from .routes import chat, connected_apps


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_process_activation_lock = asyncio.Lock()
_activation_transition: ConnectedApplicationActivation | None = None
_route_owner: ConnectedApplicationActivation | None = None


class ConnectedApplicationActivationError(RuntimeError):
    _CODES = frozenset(
        {
            "CONNECTED_APPLICATION_ALREADY_ACTIVE",
            "CONNECTED_APPLICATION_GRAPH_INVALID",
            "CONNECTED_APPLICATION_NOT_RELEASED",
            "CONNECTED_APPLICATION_NOT_READY",
        }
    )

    def __init__(self, code: str) -> None:
        self.code = code if code in self._CODES else "CONNECTED_APPLICATION_GRAPH_INVALID"
        super().__init__(self.code)


class ConnectedApplicationService(Protocol):
    @property
    def readiness(self) -> object: ...

    def require_ready(self) -> None: ...


class ConnectedApplicationChat(Protocol):
    def require_ready(self) -> None: ...

    async def handle(self, request: object) -> object: ...


class ConnectedApplicationReadResults(Protocol):
    async def get(self, *, owner_id: str, result_reference_id: str) -> object: ...


class ConnectedApplicationBackground(Protocol):
    @property
    def running(self) -> bool: ...

    @property
    def external_wake(self) -> bool: ...

    async def startup(self) -> None: ...

    async def run_cycle(self) -> object: ...

    async def shutdown(self, *, timeout_seconds: float = 30.0) -> bool: ...


@dataclass(frozen=True, slots=True, repr=False)
class ConnectedApplicationBundle:
    """The exact application-facing graph produced by production composition."""

    service: ConnectedAppService
    chat: ConnectedOperatorChatService
    read_results: ConnectedOwnerReadResultService
    background: ConnectedOperatorBackgroundSupervisor
    composition_manifest_sha256: str
    # Composed for exact review and future background wakes, but activation
    # deliberately installs no route for this boundary while its source lock
    # remains false.
    multi_step_worker: object | None = None
    multi_step_released: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.composition_manifest_sha256, str) or not _SHA256.fullmatch(
            self.composition_manifest_sha256
        ):
            raise ConnectedApplicationActivationError(
                "CONNECTED_APPLICATION_GRAPH_INVALID"
            )
        boundaries = (
            (self.service, ("require_ready",), "service"),
            (self.chat, ("require_ready", "handle"), "chat"),
            (self.read_results, ("get",), "read_results"),
            (self.background, ("startup", "run_cycle", "shutdown"), "background"),
        )
        for boundary, methods, _name in boundaries:
            if any(not callable(getattr(boundary, method, None)) for method in methods):
                raise ConnectedApplicationActivationError(
                    "CONNECTED_APPLICATION_GRAPH_INVALID"
                )
        if type(self.multi_step_released) is not bool:
            raise ConnectedApplicationActivationError(
                "CONNECTED_APPLICATION_GRAPH_INVALID"
            )
        if self.multi_step_released and self.multi_step_worker is None:
            raise ConnectedApplicationActivationError(
                "CONNECTED_APPLICATION_GRAPH_INVALID"
            )
        if self.multi_step_worker is not None and any(
            not callable(getattr(self.multi_step_worker, method, None))
            for method in (
                "start_from_chat",
                "wake",
                "cancel",
                "status",
                "list_status",
                "owner_status",
                "cancel_owner",
                "resume_after_approval",
            )
        ):
            raise ConnectedApplicationActivationError(
                "CONNECTED_APPLICATION_GRAPH_INVALID"
            )
        service_readiness = getattr(self.service, "readiness", None)
        component_manifests = (
            getattr(service_readiness, "composition_manifest_sha256", None),
            getattr(self.chat, "composition_manifest_sha256", None),
            getattr(self.read_results, "composition_manifest_sha256", None),
            getattr(self.background, "composition_manifest_sha256", None),
        )
        if any(value != self.composition_manifest_sha256 for value in component_manifests):
            raise ConnectedApplicationActivationError(
                "CONNECTED_APPLICATION_GRAPH_INVALID"
            )
        if type(getattr(self.background, "external_wake", None)) is not bool:
            raise ConnectedApplicationActivationError(
                "CONNECTED_APPLICATION_GRAPH_INVALID"
            )

    def __repr__(self) -> str:
        return "ConnectedApplicationBundle(authority='attested', secrets='<redacted>')"


class ConnectedApplicationActivation:
    """Install, supervise, and drain all connected-operator entry points."""

    def __init__(
        self,
        *,
        source_released: bool,
        environment_enabled: bool,
        expected_manifest_sha256: str,
        bundle: ConnectedApplicationBundle,
        shutdown_timeout_seconds: float = 30.0,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if type(source_released) is not bool or type(environment_enabled) is not bool:
            raise ConnectedApplicationActivationError(
                "CONNECTED_APPLICATION_GRAPH_INVALID"
            )
        if not isinstance(expected_manifest_sha256, str) or not _SHA256.fullmatch(
            expected_manifest_sha256
        ):
            raise ConnectedApplicationActivationError(
                "CONNECTED_APPLICATION_GRAPH_INVALID"
            )
        if type(bundle) is not ConnectedApplicationBundle or not callable(now):
            raise ConnectedApplicationActivationError(
                "CONNECTED_APPLICATION_GRAPH_INVALID"
            )
        if (
            not isinstance(shutdown_timeout_seconds, (int, float))
            or not 0 < shutdown_timeout_seconds <= 300
        ):
            raise ConnectedApplicationActivationError(
                "CONNECTED_APPLICATION_GRAPH_INVALID"
            )
        self._source_released = source_released
        self._environment_enabled = environment_enabled
        self._expected_manifest_sha256 = expected_manifest_sha256
        self._bundle = bundle
        self._shutdown_timeout_seconds = float(shutdown_timeout_seconds)
        self._now = now
        self._lock = asyncio.Lock()
        self._active = False

    @property
    def active(self) -> bool:
        return self._active

    def _require_ready(self) -> None:
        if (
            not self._source_released
            or not self._environment_enabled
            or connected_apps.settings.connected_apps_enabled is not True
        ):
            raise ConnectedApplicationActivationError(
                "CONNECTED_APPLICATION_NOT_RELEASED"
            )
        if self._bundle.composition_manifest_sha256 != self._expected_manifest_sha256:
            raise ConnectedApplicationActivationError(
                "CONNECTED_APPLICATION_NOT_READY"
            )
        try:
            reference = self._now()
            if (
                not isinstance(reference, datetime)
                or reference.tzinfo is None
                or reference.utcoffset() is None
            ):
                raise ValueError("invalid activation clock")
            self._bundle.service.require_ready()
            self._bundle.chat.require_ready()
        except Exception:
            raise ConnectedApplicationActivationError(
                "CONNECTED_APPLICATION_NOT_READY"
            ) from None

    @staticmethod
    def _routes_are_clear() -> bool:
        return (
            _route_owner is None
            and _activation_transition is None
            and connected_apps.connected_app_service is None
            and connected_apps.connected_read_result_service is None
            and connected_apps.connected_background_worker is None
            and connected_apps.connected_multi_step_worker is None
            and chat.connected_operator_chat_service is None
        )

    def _clear_owned_routes(self) -> None:
        global _route_owner
        if _route_owner is not self:
            return
        connected_apps.connected_app_service = None
        connected_apps.connected_read_result_service = None
        connected_apps.connected_background_worker = None
        connected_apps.connected_multi_step_worker = None
        chat.connected_operator_chat_service = None
        _route_owner = None

    async def startup(self) -> None:
        global _activation_transition, _route_owner
        async with _process_activation_lock, self._lock:
            if self._active or not self._routes_are_clear():
                raise ConnectedApplicationActivationError(
                    "CONNECTED_APPLICATION_ALREADY_ACTIVE"
                )
            _activation_transition = self
            startup_attempted = False
            try:
                self._require_ready()
                startup_attempted = True
                await self._bundle.background.startup()
                self._require_ready()
                if not self._bundle.background.running:
                    raise ConnectedApplicationActivationError(
                        "CONNECTED_APPLICATION_NOT_READY"
                    )
                # No await occurs while the three entry points are installed.
                # A request therefore observes the entire graph or none of it.
                connected_apps.connected_app_service = self._bundle.service
                connected_apps.connected_read_result_service = self._bundle.read_results
                if self._bundle.background.external_wake:
                    connected_apps.connected_background_worker = self._bundle.background
                if self._bundle.multi_step_released:
                    connected_apps.connected_multi_step_worker = self._bundle.multi_step_worker
                chat.connected_operator_chat_service = self._bundle.chat
                _route_owner = self
                self._active = True
            except BaseException as exc:
                self._clear_owned_routes()
                if startup_attempted or self._bundle.background.running:
                    try:
                        await self._bundle.background.shutdown(
                            timeout_seconds=self._shutdown_timeout_seconds
                        )
                    except Exception:
                        pass
                if isinstance(exc, asyncio.CancelledError):
                    raise
                if isinstance(exc, ConnectedApplicationActivationError):
                    raise
                raise ConnectedApplicationActivationError(
                    "CONNECTED_APPLICATION_NOT_READY"
                ) from None
            finally:
                if _activation_transition is self:
                    _activation_transition = None

    async def shutdown(self) -> bool:
        global _activation_transition
        async with _process_activation_lock, self._lock:
            _activation_transition = self
            # Refuse new requests before draining workers.  Every in-flight
            # provider effect remains recoverable from its durable fence.
            self._clear_owned_routes()
            self._active = False
            try:
                return bool(
                    await self._bundle.background.shutdown(
                        timeout_seconds=self._shutdown_timeout_seconds
                    )
                )
            except Exception:
                return False
            finally:
                if _activation_transition is self:
                    _activation_transition = None

    def __repr__(self) -> str:
        return "ConnectedApplicationActivation(release='double-locked', secrets='<none>')"


connected_application_activation: ConnectedApplicationActivation | None = None


def configure_connected_application_activation(
    activation: ConnectedApplicationActivation | None,
) -> None:
    """Configure the separately composed graph before FastAPI startup.

    This setter does not start workers or expose routes.  Reconfiguration while
    an application is active is refused so a process cannot swap authorities
    underneath an in-flight provider action.
    """

    global connected_application_activation
    current = connected_application_activation
    if (
        (current is not None and current.active)
        or _activation_transition is not None
        or _route_owner is not None
    ):
        raise ConnectedApplicationActivationError(
            "CONNECTED_APPLICATION_ALREADY_ACTIVE"
        )
    if activation is not None and type(activation) is not ConnectedApplicationActivation:
        raise ConnectedApplicationActivationError(
            "CONNECTED_APPLICATION_GRAPH_INVALID"
        )
    connected_application_activation = activation


@asynccontextmanager
async def connected_application_lifespan(_application: FastAPI) -> AsyncIterator[None]:
    """FastAPI lifespan that keeps the default checked-in build inert."""

    activation = connected_application_activation
    if activation is not None:
        await activation.startup()
    try:
        yield
    finally:
        # A Vercel request-scoped KMS edge can install the activation after
        # lifespan startup.  Let its coordinator drain counted requests first;
        # otherwise drain whichever eager activation is current at shutdown.
        from .connected_app_request_activation import (
            shutdown_connected_request_activation,
        )

        request_shutdown = await shutdown_connected_request_activation()
        # False means the request edge could not complete its bounded in-flight
        # drain.  Never bypass that lease fence by directly stopping the graph.
        if request_shutdown is not False:
            current = connected_application_activation
            if current is not None and current.active:
                await current.shutdown()


__all__ = [
    "ConnectedApplicationActivation",
    "ConnectedApplicationActivationError",
    "ConnectedApplicationBundle",
    "configure_connected_application_activation",
    "connected_application_lifespan",
]
