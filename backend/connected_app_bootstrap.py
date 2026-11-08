"""Fail-closed production bootstrap for the connected-operator graph.

The secure host supplies one concrete dependency factory after provider app
registrations, KMS custody, database versions, and provider smokes have been
attested.  The ordinary FastAPI factory always calls this module, so a released
build cannot silently omit composition: it either installs the exact
source-pinned graph or refuses application construction.
"""

from __future__ import annotations

from datetime import UTC, datetime
import re
from typing import Callable, Protocol

from . import connected_app_activation as activation_module
from . import config
from .connected_app_activation import (
    ConnectedApplicationActivation,
    ConnectedApplicationActivationError,
    ConnectedApplicationBundle,
    configure_connected_application_activation,
)
from .runtime import settings


_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class ConnectedApplicationFactory(Protocol):
    """Secure production boundary that constructs the already-attested graph."""

    def build(
        self,
        *,
        expected_manifest_sha256: str,
        now: Callable[[], datetime],
    ) -> ConnectedApplicationBundle: ...


connected_application_factory: ConnectedApplicationFactory | None = None


def configure_connected_application_factory(
    factory: ConnectedApplicationFactory | None,
) -> None:
    """Register secret-backed production dependencies before ``create_app``."""

    global connected_application_factory
    if activation_module.connected_application_activation is not None:
        raise ConnectedApplicationActivationError(
            "CONNECTED_APPLICATION_ALREADY_ACTIVE"
        )
    if factory is not None and not callable(getattr(factory, "build", None)):
        raise ConnectedApplicationActivationError(
            "CONNECTED_APPLICATION_GRAPH_INVALID"
        )
    connected_application_factory = factory


def prepare_connected_application_activation(
    *,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> ConnectedApplicationActivation | None:
    """Build and configure the exact graph, or remain inert behind both locks."""

    source_released = config.connected_apps_release_candidate_source_released()
    environment_enabled = settings.connected_apps_enabled
    if not source_released or not environment_enabled:
        if activation_module.connected_application_activation is not None:
            configure_connected_application_activation(None)
        return None

    expected = config.CONNECTED_APPS_COMPOSITION_MANIFEST_SHA256
    factory = connected_application_factory
    if not isinstance(expected, str) or not _SHA256.fullmatch(expected):
        raise ConnectedApplicationActivationError(
            "CONNECTED_APPLICATION_NOT_READY"
        )
    if factory is None:
        raise ConnectedApplicationActivationError(
            "CONNECTED_APPLICATION_NOT_READY"
        )
    if not callable(now):
        raise ConnectedApplicationActivationError(
            "CONNECTED_APPLICATION_GRAPH_INVALID"
        )
    existing = activation_module.connected_application_activation
    if existing is not None:
        return existing
    try:
        bundle = factory.build(
            expected_manifest_sha256=expected,
            now=now,
        )
    except Exception:
        raise ConnectedApplicationActivationError(
            "CONNECTED_APPLICATION_NOT_READY"
        ) from None
    if (
        type(bundle) is not ConnectedApplicationBundle
        or bundle.composition_manifest_sha256 != expected
    ):
        raise ConnectedApplicationActivationError(
            "CONNECTED_APPLICATION_NOT_READY"
        )
    activation = ConnectedApplicationActivation(
        source_released=source_released,
        environment_enabled=environment_enabled,
        expected_manifest_sha256=expected,
        bundle=bundle,
        now=now,
    )
    configure_connected_application_activation(activation)
    return activation


__all__ = [
    "ConnectedApplicationFactory",
    "configure_connected_application_factory",
    "prepare_connected_application_activation",
]
