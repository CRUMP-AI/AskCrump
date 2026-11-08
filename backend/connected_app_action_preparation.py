"""Atomic, content-free preparation of one connected-app action.

The ordinary-language planner may propose a typed request, but this boundary
accepts only references to payloads that have already been encrypted by the
payload vault.  The database transaction revalidates current delegated
authority, authors a one-action task grant, and records either a ready read or
a pending write review.  It never claims or executes the action.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
import hashlib
import hmac
import json
import re
from typing import Protocol
from uuid import UUID

from .connected_app_payload_vault import ConnectedPayloadRef
from .connected_app_policy import (
    ConnectedActionIntent,
    ConnectedActionPolicy,
    ConnectedTaskGrant,
    ConnectorActionKind,
    ConnectorApprovalClass,
    ConnectorProvider,
    ConnectorResource,
    action_set_sha256,
)


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MAX_PREPARATION_TTL = timedelta(minutes=15)
_MAX_DEPENDENCY_SECONDS = 10.0
_COMMAND_VERSION = "connected-action-preparation-v1"
_APPROVAL_VERSION = "connected-action-preparation-approval-v1"


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


def _sha(value: str, name: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ValueError(f"{name} is invalid")
    return value


def _aware(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} is invalid")
    return value.astimezone(UTC)


def _canonical_sha256(value: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
    ).hexdigest()


class ConnectedActionPreparationStatus(StrEnum):
    READY = "ready"
    PENDING_APPROVAL = "pending_approval"


class ConnectedActionPreparationError(RuntimeError):
    """Fixed, content-free preparation failure."""

    _ALLOWED = frozenset(
        {
            "CONNECTED_ACTION_PREPARATION_FAILED",
            "CONNECTED_ACTION_PREPARATION_INVALID",
            "CONNECTED_ACTION_PREPARATION_RESULT_INVALID",
        }
    )

    def __init__(self, code: str, *, retryable: bool = False) -> None:
        if code not in self._ALLOWED:
            code = "CONNECTED_ACTION_PREPARATION_FAILED"
        self.code = code
        self.retryable = retryable is True
        super().__init__(code)


def action_preparation_approval_binding_sha256(
    *,
    request_id: str,
    owner_id: str,
    action_id: str,
    approval_id: str,
    connection_id: str,
    action: ConnectorActionKind,
    parameters_sha256: str,
    preview_sha256: str,
    preview_reference_binding_sha256: str,
) -> str:
    """Bind a pending review without hashing predictable customer content."""

    if not isinstance(action, ConnectorActionKind):
        raise ValueError("action is invalid")
    return _canonical_sha256(
        {
            "version": _APPROVAL_VERSION,
            "request_id": _uuid(request_id, "request_id"),
            "owner_id": _uuid(owner_id, "owner_id"),
            "action_id": _uuid(action_id, "action_id"),
            "approval_id": _uuid(approval_id, "approval_id"),
            "connection_id": _uuid(connection_id, "connection_id"),
            "action": action.value,
            "parameters_sha256": _sha(parameters_sha256, "parameters_sha256"),
            "preview_sha256": _sha(preview_sha256, "preview_sha256"),
            "preview_reference_binding_sha256": _sha(
                preview_reference_binding_sha256,
                "preview_reference_binding_sha256",
            ),
        }
    )


def _command_binding_values(
    *,
    request_id: str,
    owner_id: str,
    session_id: str,
    session_binding_sha256: str,
    grant_id: str,
    action_id: str,
    task_id: str,
    turn_id: str,
    connection_id: str,
    provider: ConnectorProvider,
    resource: ConnectorResource,
    action: ConnectorActionKind,
    authorization_revision: int,
    authorization_snapshot_sha256: str,
    granted_actions_sha256: str,
    granted_scopes_sha256: str,
    task_state_revision: int,
    payload: ConnectedPayloadRef,
    resource_version_sha256: str | None,
    approval_id: str | None,
    approval_binding_sha256: str | None,
    review_payload: ConnectedPayloadRef | None,
    requested_at: datetime,
    expires_at: datetime,
) -> dict[str, object]:
    return {
        "version": _COMMAND_VERSION,
        "request_id": request_id,
        "owner_id": owner_id,
        "session_id": session_id,
        "session_binding_sha256": session_binding_sha256,
        "grant_id": grant_id,
        "action_id": action_id,
        "task_id": task_id,
        "turn_id": turn_id,
        "connection_id": connection_id,
        "provider": provider.value,
        "resource": resource.value,
        "action": action.value,
        "authorization_revision": authorization_revision,
        "authorization_snapshot_sha256": authorization_snapshot_sha256,
        "granted_actions_sha256": granted_actions_sha256,
        "granted_scopes_sha256": granted_scopes_sha256,
        "task_state_revision": task_state_revision,
        "payload_id": payload.payload_id,
        "payload_reference_binding_sha256": payload.binding_sha256,
        "parameters_sha256": payload.payload_sha256,
        "resource_version_sha256": resource_version_sha256,
        "approval_id": approval_id,
        "approval_binding_sha256": approval_binding_sha256,
        "preview_payload_id": None if review_payload is None else review_payload.payload_id,
        "preview_reference_binding_sha256": (
            None if review_payload is None else review_payload.binding_sha256
        ),
        "preview_sha256": None if review_payload is None else review_payload.payload_sha256,
        "requested_at": requested_at.isoformat(),
        "expires_at": expires_at.isoformat(),
    }


@dataclass(frozen=True, slots=True, repr=False)
class ConnectedActionPreparationCommand:
    """Exact server-authored preparation command after request authentication."""

    request_id: str
    owner_id: str
    session_id: str = field(repr=False)
    session_binding_sha256: str = field(repr=False)
    command_binding_sha256: str = field(repr=False)
    grant_id: str
    action_id: str
    task_id: str
    turn_id: str
    connection_id: str
    provider: ConnectorProvider
    resource: ConnectorResource
    action: ConnectorActionKind
    authorization_revision: int
    authorization_snapshot_sha256: str = field(repr=False)
    granted_actions_sha256: str = field(repr=False)
    granted_scopes_sha256: str = field(repr=False)
    task_state_revision: int
    payload: ConnectedPayloadRef = field(repr=False)
    resource_version_sha256: str | None = field(default=None, repr=False)
    approval_id: str | None = None
    approval_binding_sha256: str | None = field(default=None, repr=False)
    review_payload: ConnectedPayloadRef | None = field(default=None, repr=False)
    requested_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime = field(default_factory=lambda: datetime.now(UTC) + timedelta(minutes=10))

    def __post_init__(self) -> None:
        for value, name in (
            (self.request_id, "request_id"),
            (self.owner_id, "owner_id"),
            (self.session_id, "session_id"),
            (self.grant_id, "grant_id"),
            (self.action_id, "action_id"),
            (self.task_id, "task_id"),
            (self.turn_id, "turn_id"),
            (self.connection_id, "connection_id"),
        ):
            _uuid(value, name)
        _sha(self.session_binding_sha256, "session_binding_sha256")
        _sha(self.command_binding_sha256, "command_binding_sha256")
        if not isinstance(self.provider, ConnectorProvider):
            raise ValueError("provider is invalid")
        if not isinstance(self.resource, ConnectorResource):
            raise ValueError("resource is invalid")
        if not isinstance(self.action, ConnectorActionKind):
            raise ValueError("action is invalid")
        requirement = ConnectedActionPolicy.requirement(self.action)
        if requirement.resource is not self.resource:
            raise ValueError("action resource is invalid")
        if type(self.authorization_revision) is not int or self.authorization_revision < 1:
            raise ValueError("authorization_revision is invalid")
        _sha(self.authorization_snapshot_sha256, "authorization_snapshot_sha256")
        _sha(self.granted_actions_sha256, "granted_actions_sha256")
        _sha(self.granted_scopes_sha256, "granted_scopes_sha256")
        if type(self.task_state_revision) is not int or self.task_state_revision < 1:
            raise ValueError("task_state_revision is invalid")
        if not isinstance(self.payload, ConnectedPayloadRef):
            raise ValueError("payload reference is invalid")
        if (
            self.payload.owner_id != self.owner_id
            or self.payload.connection_id != self.connection_id
            or self.payload.action_id != self.action_id
            or self.payload.provider is not self.provider
            or self.payload.action is not self.action
        ):
            raise ValueError("payload reference binding is invalid")
        if self.resource_version_sha256 is not None:
            _sha(self.resource_version_sha256, "resource_version_sha256")
        requested_at = _aware(self.requested_at, "requested_at")
        expires_at = _aware(self.expires_at, "expires_at")
        if expires_at <= requested_at or expires_at - requested_at > _MAX_PREPARATION_TTL:
            raise ValueError("preparation lifetime is invalid")
        if self.payload.created_at != requested_at or self.payload.expires_at != expires_at:
            raise ValueError("payload lifetime is not preparation-bound")
        if requirement.mutates_external_state:
            if (
                self.approval_id is None
                or self.approval_binding_sha256 is None
                or self.review_payload is None
            ):
                raise ValueError("write preparation requires a review")
            _uuid(self.approval_id, "approval_id")
            _sha(self.approval_binding_sha256, "approval_binding_sha256")
            if (
                self.review_payload.owner_id != self.owner_id
                or self.review_payload.connection_id != self.connection_id
                or self.review_payload.action_id != self.action_id
                or self.review_payload.provider is not self.provider
                or self.review_payload.action is not self.action
                or self.review_payload.created_at != requested_at
                or self.review_payload.expires_at != expires_at
            ):
                raise ValueError("review payload reference binding is invalid")
            expected_approval = action_preparation_approval_binding_sha256(
                request_id=self.request_id,
                owner_id=self.owner_id,
                action_id=self.action_id,
                approval_id=self.approval_id,
                connection_id=self.connection_id,
                action=self.action,
                parameters_sha256=self.payload.payload_sha256,
                preview_sha256=self.review_payload.payload_sha256,
                preview_reference_binding_sha256=self.review_payload.binding_sha256,
            )
            if not hmac.compare_digest(self.approval_binding_sha256, expected_approval):
                raise ValueError("approval binding is invalid")
        elif any(
            value is not None
            for value in (
                self.approval_id,
                self.approval_binding_sha256,
                self.review_payload,
            )
        ):
            raise ValueError("read preparation cannot carry a review")
        expected_command = _canonical_sha256(
            _command_binding_values(
                request_id=self.request_id,
                owner_id=self.owner_id,
                session_id=self.session_id,
                session_binding_sha256=self.session_binding_sha256,
                grant_id=self.grant_id,
                action_id=self.action_id,
                task_id=self.task_id,
                turn_id=self.turn_id,
                connection_id=self.connection_id,
                provider=self.provider,
                resource=self.resource,
                action=self.action,
                authorization_revision=self.authorization_revision,
                authorization_snapshot_sha256=self.authorization_snapshot_sha256,
                granted_actions_sha256=self.granted_actions_sha256,
                granted_scopes_sha256=self.granted_scopes_sha256,
                task_state_revision=self.task_state_revision,
                payload=self.payload,
                resource_version_sha256=self.resource_version_sha256,
                approval_id=self.approval_id,
                approval_binding_sha256=self.approval_binding_sha256,
                review_payload=self.review_payload,
                requested_at=requested_at,
                expires_at=expires_at,
            )
        )
        if not hmac.compare_digest(self.command_binding_sha256, expected_command):
            raise ValueError("command binding is invalid")

    @property
    def grant_actions_sha256(self) -> str:
        return action_set_sha256((self.action,))

    @classmethod
    def build(
        cls,
        *,
        request_id: str,
        owner_id: str,
        session_id: str,
        session_binding_sha256: str,
        grant_id: str,
        action_id: str,
        task_id: str,
        turn_id: str,
        connection_id: str,
        provider: ConnectorProvider,
        resource: ConnectorResource,
        action: ConnectorActionKind,
        authorization_revision: int,
        authorization_snapshot_sha256: str,
        granted_actions_sha256: str,
        granted_scopes_sha256: str,
        task_state_revision: int,
        payload: ConnectedPayloadRef,
        resource_version_sha256: str | None,
        requested_at: datetime,
        expires_at: datetime,
        approval_id: str | None = None,
        review_payload: ConnectedPayloadRef | None = None,
    ) -> ConnectedActionPreparationCommand:
        approval_binding = None
        if approval_id is not None and review_payload is not None:
            approval_binding = action_preparation_approval_binding_sha256(
                request_id=request_id,
                owner_id=owner_id,
                action_id=action_id,
                approval_id=approval_id,
                connection_id=connection_id,
                action=action,
                parameters_sha256=payload.payload_sha256,
                preview_sha256=review_payload.payload_sha256,
                preview_reference_binding_sha256=review_payload.binding_sha256,
            )
        values = _command_binding_values(
            request_id=request_id,
            owner_id=owner_id,
            session_id=session_id,
            session_binding_sha256=session_binding_sha256,
            grant_id=grant_id,
            action_id=action_id,
            task_id=task_id,
            turn_id=turn_id,
            connection_id=connection_id,
            provider=provider,
            resource=resource,
            action=action,
            authorization_revision=authorization_revision,
            authorization_snapshot_sha256=authorization_snapshot_sha256,
            granted_actions_sha256=granted_actions_sha256,
            granted_scopes_sha256=granted_scopes_sha256,
            task_state_revision=task_state_revision,
            payload=payload,
            resource_version_sha256=resource_version_sha256,
            approval_id=approval_id,
            approval_binding_sha256=approval_binding,
            review_payload=review_payload,
            requested_at=_aware(requested_at, "requested_at"),
            expires_at=_aware(expires_at, "expires_at"),
        )
        return cls(
            request_id=request_id,
            owner_id=owner_id,
            session_id=session_id,
            session_binding_sha256=session_binding_sha256,
            command_binding_sha256=_canonical_sha256(values),
            grant_id=grant_id,
            action_id=action_id,
            task_id=task_id,
            turn_id=turn_id,
            connection_id=connection_id,
            provider=provider,
            resource=resource,
            action=action,
            authorization_revision=authorization_revision,
            authorization_snapshot_sha256=authorization_snapshot_sha256,
            granted_actions_sha256=granted_actions_sha256,
            granted_scopes_sha256=granted_scopes_sha256,
            task_state_revision=task_state_revision,
            payload=payload,
            resource_version_sha256=resource_version_sha256,
            approval_id=approval_id,
            approval_binding_sha256=approval_binding,
            review_payload=review_payload,
            requested_at=requested_at,
            expires_at=expires_at,
        )

    def __repr__(self) -> str:
        return (
            f"ConnectedActionPreparationCommand(request_id={self.request_id!r}, "
            f"action={self.action.value!r}, bindings='<redacted>')"
        )


@dataclass(frozen=True, slots=True, repr=False)
class ConnectedActionPreparationView:
    request_id: str
    owner_id: str
    command_binding_sha256: str = field(repr=False)
    grant_id: str
    action_id: str
    task_id: str
    turn_id: str
    connection_id: str
    provider: ConnectorProvider
    resource: ConnectorResource
    action: ConnectorActionKind
    authorization_revision: int
    authorization_snapshot_sha256: str = field(repr=False)
    granted_actions_sha256: str = field(repr=False)
    granted_scopes_sha256: str = field(repr=False)
    grant_actions_sha256: str = field(repr=False)
    task_state_revision: int
    payload_id: str
    payload_reference_binding_sha256: str = field(repr=False)
    parameters_sha256: str = field(repr=False)
    resource_version_sha256: str | None = field(repr=False)
    policy_version: str
    mutates_external_state: bool
    approval_class: ConnectorApprovalClass
    status: ConnectedActionPreparationStatus
    approval_id: str | None
    approval_binding_sha256: str | None = field(repr=False)
    preview_payload_id: str | None
    preview_reference_binding_sha256: str | None = field(repr=False)
    preview_sha256: str | None = field(repr=False)
    requested_at: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        for value, name in (
            (self.request_id, "request_id"),
            (self.owner_id, "owner_id"),
            (self.grant_id, "grant_id"),
            (self.action_id, "action_id"),
            (self.task_id, "task_id"),
            (self.turn_id, "turn_id"),
            (self.connection_id, "connection_id"),
            (self.payload_id, "payload_id"),
        ):
            _uuid(value, name)
        for value, name in (
            (self.command_binding_sha256, "command_binding_sha256"),
            (self.authorization_snapshot_sha256, "authorization_snapshot_sha256"),
            (self.granted_actions_sha256, "granted_actions_sha256"),
            (self.granted_scopes_sha256, "granted_scopes_sha256"),
            (self.grant_actions_sha256, "grant_actions_sha256"),
            (self.payload_reference_binding_sha256, "payload_reference_binding_sha256"),
            (self.parameters_sha256, "parameters_sha256"),
        ):
            _sha(value, name)
        if not isinstance(self.provider, ConnectorProvider):
            raise ValueError("provider is invalid")
        if not isinstance(self.resource, ConnectorResource):
            raise ValueError("resource is invalid")
        if not isinstance(self.action, ConnectorActionKind):
            raise ValueError("action is invalid")
        requirement = ConnectedActionPolicy.requirement(self.action)
        if requirement.resource is not self.resource:
            raise ValueError("action resource is invalid")
        if type(self.authorization_revision) is not int or self.authorization_revision < 1:
            raise ValueError("authorization_revision is invalid")
        if type(self.task_state_revision) is not int or self.task_state_revision < 1:
            raise ValueError("task_state_revision is invalid")
        if self.grant_actions_sha256 != action_set_sha256((self.action,)):
            raise ValueError("grant action binding is invalid")
        if self.resource_version_sha256 is not None:
            _sha(self.resource_version_sha256, "resource_version_sha256")
        if self.policy_version != ConnectedActionPolicy.version:
            raise ValueError("policy version is invalid")
        if type(self.mutates_external_state) is not bool:
            raise ValueError("mutation classification is invalid")
        if not isinstance(self.approval_class, ConnectorApprovalClass):
            raise ValueError("approval class is invalid")
        if not isinstance(self.status, ConnectedActionPreparationStatus):
            raise ValueError("preparation status is invalid")
        if (
            self.mutates_external_state != requirement.mutates_external_state
            or self.approval_class is not requirement.approval_class
        ):
            raise ValueError("database action classification is invalid")
        if self.mutates_external_state:
            if self.status is not ConnectedActionPreparationStatus.PENDING_APPROVAL:
                raise ValueError("write preparation status is invalid")
            for value, name in (
                (self.approval_id, "approval_id"),
                (self.preview_payload_id, "preview_payload_id"),
            ):
                _uuid(value or "", name)
            for value, name in (
                (self.approval_binding_sha256, "approval_binding_sha256"),
                (
                    self.preview_reference_binding_sha256,
                    "preview_reference_binding_sha256",
                ),
                (self.preview_sha256, "preview_sha256"),
            ):
                _sha(value or "", name)
        elif self.status is not ConnectedActionPreparationStatus.READY or any(
            value is not None
            for value in (
                self.approval_id,
                self.approval_binding_sha256,
                self.preview_payload_id,
                self.preview_reference_binding_sha256,
                self.preview_sha256,
            )
        ):
            raise ValueError("read preparation review shape is invalid")
        requested_at = _aware(self.requested_at, "requested_at")
        expires_at = _aware(self.expires_at, "expires_at")
        if expires_at <= requested_at or expires_at - requested_at > _MAX_PREPARATION_TTL:
            raise ValueError("preparation lifetime is invalid")

    def intent(self) -> ConnectedActionIntent:
        return ConnectedActionIntent.build(
            action_id=self.action_id,
            owner_id=self.owner_id,
            task_id=self.task_id,
            turn_id=self.turn_id,
            connection_id=self.connection_id,
            provider=self.provider,
            resource=self.resource,
            authorization_revision=self.authorization_revision,
            authorization_snapshot_sha256=self.authorization_snapshot_sha256,
            action=self.action,
            parameters_sha256=self.parameters_sha256,
            resource_version_sha256=self.resource_version_sha256,
            requested_at=self.requested_at,
        )

    def grant(self) -> ConnectedTaskGrant:
        return ConnectedTaskGrant(
            grant_id=self.grant_id,
            owner_id=self.owner_id,
            task_id=self.task_id,
            turn_id=self.turn_id,
            connection_id=self.connection_id,
            provider=self.provider,
            resource=self.resource,
            authorization_revision=self.authorization_revision,
            authorization_snapshot_sha256=self.authorization_snapshot_sha256,
            actions=frozenset({self.action}),
            actions_sha256=self.grant_actions_sha256,
            expires_at=self.expires_at,
        )

    def __repr__(self) -> str:
        return (
            f"ConnectedActionPreparationView(request_id={self.request_id!r}, "
            f"status={self.status.value!r}, bindings='<redacted>')"
        )


def action_preparation_result_matches(
    command: ConnectedActionPreparationCommand,
    result: object,
) -> bool:
    if (
        type(command) is not ConnectedActionPreparationCommand
        or type(result) is not ConnectedActionPreparationView
    ):
        return False
    review = command.review_payload
    return bool(
        result.request_id == command.request_id
        and result.owner_id == command.owner_id
        and hmac.compare_digest(result.command_binding_sha256, command.command_binding_sha256)
        and result.grant_id == command.grant_id
        and result.action_id == command.action_id
        and result.task_id == command.task_id
        and result.turn_id == command.turn_id
        and result.connection_id == command.connection_id
        and result.provider is command.provider
        and result.resource is command.resource
        and result.action is command.action
        and result.authorization_revision == command.authorization_revision
        and result.authorization_snapshot_sha256 == command.authorization_snapshot_sha256
        and result.granted_actions_sha256 == command.granted_actions_sha256
        and result.granted_scopes_sha256 == command.granted_scopes_sha256
        and result.grant_actions_sha256 == command.grant_actions_sha256
        and result.task_state_revision == command.task_state_revision
        and result.payload_id == command.payload.payload_id
        and result.payload_reference_binding_sha256 == command.payload.binding_sha256
        and result.parameters_sha256 == command.payload.payload_sha256
        and result.resource_version_sha256 == command.resource_version_sha256
        and result.policy_version == ConnectedActionPolicy.version
        and result.approval_id == command.approval_id
        and result.approval_binding_sha256 == command.approval_binding_sha256
        and result.preview_payload_id == (None if review is None else review.payload_id)
        and result.preview_reference_binding_sha256
        == (None if review is None else review.binding_sha256)
        and result.preview_sha256 == (None if review is None else review.payload_sha256)
        and result.requested_at == command.requested_at.astimezone(UTC)
        and result.expires_at == command.expires_at.astimezone(UTC)
    )


class ConnectedActionPreparationControlPlane(Protocol):
    async def prepare_action_once(
        self, command: ConnectedActionPreparationCommand
    ) -> ConnectedActionPreparationView: ...

    async def readback_action_preparation(
        self,
        *,
        owner_id: str,
        request_id: str,
    ) -> ConnectedActionPreparationView | None: ...


class ConnectedActionPreparationService:
    """Response-loss-safe service boundary; it never invokes a provider."""

    def __init__(self, *, control_plane: ConnectedActionPreparationControlPlane) -> None:
        if any(
            not callable(getattr(control_plane, method, None))
            for method in ("prepare_action_once", "readback_action_preparation")
        ):
            raise TypeError("action preparation control plane is invalid")
        self._control_plane = control_plane

    async def prepare(
        self,
        command: ConnectedActionPreparationCommand,
    ) -> ConnectedActionPreparationView:
        if type(command) is not ConnectedActionPreparationCommand:
            raise ConnectedActionPreparationError("CONNECTED_ACTION_PREPARATION_INVALID")
        try:
            result = await asyncio.wait_for(
                self._control_plane.prepare_action_once(command),
                timeout=_MAX_DEPENDENCY_SECONDS,
            )
        except Exception:
            try:
                result = await asyncio.wait_for(
                    self._control_plane.readback_action_preparation(
                        owner_id=command.owner_id,
                        request_id=command.request_id,
                    ),
                    timeout=_MAX_DEPENDENCY_SECONDS,
                )
            except Exception:
                result = None
            if result is None:
                raise ConnectedActionPreparationError(
                    "CONNECTED_ACTION_PREPARATION_FAILED",
                    retryable=True,
                ) from None
        if not action_preparation_result_matches(command, result):
            raise ConnectedActionPreparationError("CONNECTED_ACTION_PREPARATION_RESULT_INVALID")
        return result

    def __repr__(self) -> str:
        return "ConnectedActionPreparationService(control_plane='<redacted>')"
