"""Crash-safe resolution of encrypted connected-action payloads.

The control plane persists only an opaque payload ID and keyed commitment.  A
trusted, owner-scoped reference lookup recovers the nonsecret vault metadata;
the payload vault then decrypts the strict envelope.  No caller-supplied target
digest or request object is accepted at this boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from .connected_app_payload_envelope import (
    ConnectedActionPayloadEnvelope,
    expected_resource_version,
)
from .connected_app_payload_vault import ConnectedPayloadRef
from .connected_app_policy import (
    ConnectedActionIntent,
    ConnectedActionPolicy,
    ConnectorActionKind,
    ConnectorProvider,
)
from .connected_app_runtime import ConnectedActionInvocation


class ConnectedPayloadResolutionError(RuntimeError):
    _CODES = frozenset(
        {
            "CONNECTED_PAYLOAD_NOT_FOUND",
            "CONNECTED_PAYLOAD_INVALID",
            "CONNECTED_PAYLOAD_BINDING_MISMATCH",
            "CONNECTED_PAYLOAD_UNAVAILABLE",
        }
    )

    def __init__(self, code: str) -> None:
        if code not in self._CODES:
            raise ValueError("payload resolution error is invalid")
        self.code = code
        super().__init__(code)


class ConnectedPayloadReferenceLookup(Protocol):
    async def resolve_reference(
        self,
        *,
        owner_id: str,
        payload_id: str,
        connection_id: str,
        action_id: str,
        provider: ConnectorProvider,
        action: ConnectorActionKind,
    ) -> ConnectedPayloadRef | None: ...


class ConnectedPayloadReader(Protocol):
    async def open_json(self, reference: ConnectedPayloadRef) -> object: ...


def _uuid(value: str, name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} is invalid")
    try:
        parsed = UUID(value)
    except (TypeError, ValueError, AttributeError):
        raise ValueError(f"{name} is invalid") from None
    if str(parsed) != value:
        raise ValueError(f"{name} is invalid")
    return value


@dataclass(frozen=True, slots=True, repr=False)
class ConnectedResolvedActionPayload:
    reference: ConnectedPayloadRef
    invocation: ConnectedActionInvocation

    def __post_init__(self) -> None:
        if not isinstance(self.reference, ConnectedPayloadRef):
            raise TypeError("payload reference is invalid")
        if not isinstance(self.invocation, ConnectedActionInvocation):
            raise TypeError("payload invocation is invalid")

    def __repr__(self) -> str:
        return "ConnectedResolvedActionPayload(content='<redacted>')"


class ConnectedActionPayloadResolver:
    def __init__(
        self,
        *,
        references: ConnectedPayloadReferenceLookup,
        payloads: ConnectedPayloadReader,
    ) -> None:
        if not callable(getattr(references, "resolve_reference", None)):
            raise TypeError("payload reference lookup is invalid")
        if not callable(getattr(payloads, "open_json", None)):
            raise TypeError("payload reader is invalid")
        self._references = references
        self._payloads = payloads

    async def resolve(
        self,
        *,
        payload_id: str,
        intent: ConnectedActionIntent,
    ) -> ConnectedResolvedActionPayload:
        try:
            _uuid(payload_id, "payload_id")
            if not isinstance(intent, ConnectedActionIntent):
                raise TypeError("intent is invalid")
            if ConnectedActionPolicy.requirement(intent.action).resource is not intent.resource:
                raise ValueError("intent resource is invalid")
        except (TypeError, ValueError):
            raise ConnectedPayloadResolutionError("CONNECTED_PAYLOAD_INVALID") from None
        try:
            reference = await self._references.resolve_reference(
                owner_id=intent.owner_id,
                payload_id=payload_id,
                connection_id=intent.connection_id,
                action_id=intent.action_id,
                provider=intent.provider,
                action=intent.action,
            )
        except Exception:
            raise ConnectedPayloadResolutionError("CONNECTED_PAYLOAD_UNAVAILABLE") from None
        if reference is None:
            raise ConnectedPayloadResolutionError("CONNECTED_PAYLOAD_NOT_FOUND")
        if not isinstance(reference, ConnectedPayloadRef):
            raise ConnectedPayloadResolutionError("CONNECTED_PAYLOAD_INVALID")
        if (
            reference.payload_id != payload_id
            or reference.owner_id != intent.owner_id
            or reference.connection_id != intent.connection_id
            or reference.action_id != intent.action_id
            or reference.provider is not intent.provider
            or reference.action is not intent.action
            or reference.payload_sha256 != intent.parameters_sha256
        ):
            raise ConnectedPayloadResolutionError("CONNECTED_PAYLOAD_BINDING_MISMATCH")
        try:
            value = await self._payloads.open_json(reference)
        except Exception:
            raise ConnectedPayloadResolutionError("CONNECTED_PAYLOAD_UNAVAILABLE") from None
        try:
            envelope = ConnectedActionPayloadEnvelope.from_value(value)
            if envelope.action is not intent.action:
                raise ValueError("payload action mismatch")
            invocation = ConnectedActionInvocation(
                intent=intent,
                request=envelope.request,
                payload_sha256=reference.payload_sha256,
                request_target_binding_sha256=envelope.request_target_binding_sha256,
                expected_resource_version=expected_resource_version(envelope.request),
            )
        except (TypeError, ValueError):
            raise ConnectedPayloadResolutionError("CONNECTED_PAYLOAD_BINDING_MISMATCH") from None
        return ConnectedResolvedActionPayload(reference=reference, invocation=invocation)

    def __repr__(self) -> str:
        return "ConnectedActionPayloadResolver(secrets='<redacted>')"
