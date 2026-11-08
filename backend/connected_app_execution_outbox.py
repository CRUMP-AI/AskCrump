"""Durable approval/readiness-to-execution dispatch for connected apps.

The encrypted preparation and approval rows remain the source of truth.  This
module only coordinates a content-free database outbox with the already
fenced :class:`ConnectedAppRuntime`; it never treats an in-memory queue or a
workflow retry as execution authority.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
import hashlib
import re
from typing import Any, Callable, Protocol
from uuid import UUID, uuid4

from .connected_app_action_preparation import ConnectedActionPreparationStatus
from .connected_app_payload_resolution import (
    ConnectedActionPayloadResolver,
    ConnectedPayloadResolutionError,
)
from .connected_app_policy import (
    ConnectedActionIntent,
    ConnectedActionPolicy,
    ConnectedApprovalEvidence,
    ConnectedTaskGrant,
    ConnectorActionKind,
    ConnectorApprovalClass,
    ConnectorProvider,
    ConnectorResource,
    action_set_sha256,
)
from .connected_app_runtime import (
    ConnectedActionRuntimeResult,
    ConnectedAppRuntime,
)


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MAX_LIMIT = 100
_MAX_LEASE_SECONDS = 300
_DEFAULT_LEASE_SECONDS = 180


class ConnectedDispatchError(RuntimeError):
    """Content-free durable-dispatch failure."""

    _CODES = frozenset(
        {
            "CONNECTED_DISPATCH_INVALID",
            "CONNECTED_DISPATCH_RPC_FAILED",
            "CONNECTED_DISPATCH_RPC_SHAPE_INVALID",
            "CONNECTED_DISPATCH_PAYLOAD_INVALID",
            "CONNECTED_DISPATCH_NOT_READY",
            "CONNECTED_DISPATCH_RUNTIME_FAILED",
            "CONNECTED_DISPATCH_SETTLEMENT_FAILED",
        }
    )

    def __init__(self, code: str, *, retryable: bool = False) -> None:
        if code not in self._CODES:
            raise ValueError("dispatch error code is invalid")
        self.code = code
        self.retryable = bool(retryable)
        super().__init__(code)


class ConnectedDispatchStatus(StrEnum):
    QUEUED = "queued"
    LEASED = "leased"
    INVOKED = "invoked"
    READ_SUCCEEDED = "read_succeeded"
    WRITE_SUCCEEDED = "write_succeeded"
    AMBIGUOUS = "ambiguous"
    FAILED = "failed"
    CANCELLED = "cancelled"
    AUTHORITY_STALE = "authority_stale"
    EFFECT_UNKNOWN = "effect_unknown"


_TERMINAL = frozenset(
    {
        ConnectedDispatchStatus.READ_SUCCEEDED,
        ConnectedDispatchStatus.WRITE_SUCCEEDED,
        ConnectedDispatchStatus.AMBIGUOUS,
        ConnectedDispatchStatus.FAILED,
        ConnectedDispatchStatus.CANCELLED,
        ConnectedDispatchStatus.AUTHORITY_STALE,
        ConnectedDispatchStatus.EFFECT_UNKNOWN,
    }
)
_RECEIPT_OUTCOMES = frozenset(
    {"drafted", "sent", "created", "updated", "cancelled"}
)


def _uuid(value: object, name: str, *, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    if not isinstance(value, str):
        raise ConnectedDispatchError("CONNECTED_DISPATCH_RPC_SHAPE_INVALID")
    try:
        canonical = str(UUID(value))
    except (TypeError, ValueError, AttributeError):
        raise ConnectedDispatchError("CONNECTED_DISPATCH_RPC_SHAPE_INVALID") from None
    if canonical != value:
        raise ConnectedDispatchError("CONNECTED_DISPATCH_RPC_SHAPE_INVALID")
    return canonical


def _sha(value: object, *, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ConnectedDispatchError("CONNECTED_DISPATCH_RPC_SHAPE_INVALID")
    return value


def _instant(value: object, *, optional: bool = False) -> datetime | None:
    if value is None and optional:
        return None
    if not isinstance(value, str):
        raise ConnectedDispatchError("CONNECTED_DISPATCH_RPC_SHAPE_INVALID")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ConnectedDispatchError("CONNECTED_DISPATCH_RPC_SHAPE_INVALID") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ConnectedDispatchError("CONNECTED_DISPATCH_RPC_SHAPE_INVALID")
    return parsed.astimezone(UTC)


def _enum(value: object, enum_type: type[StrEnum]) -> StrEnum:
    if not isinstance(value, str):
        raise ConnectedDispatchError("CONNECTED_DISPATCH_RPC_SHAPE_INVALID")
    try:
        return enum_type(value)
    except ValueError:
        raise ConnectedDispatchError("CONNECTED_DISPATCH_RPC_SHAPE_INVALID") from None


def _positive(value: object, *, allow_zero: bool = False) -> int:
    minimum = 0 if allow_zero else 1
    if type(value) is not int or value < minimum:
        raise ConnectedDispatchError("CONNECTED_DISPATCH_RPC_SHAPE_INVALID")
    return value


def _failure_hash(code: str) -> str:
    if not isinstance(code, str) or not code or len(code) > 128:
        code = "CONNECTED_DISPATCH_DEPENDENCY_FAILED"
    return hashlib.sha256(code.encode("ascii", errors="replace")).hexdigest()


@dataclass(frozen=True, slots=True, repr=False)
class ConnectedDispatchRecord:
    operation_id: str
    request_id: str
    owner_id: str
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
    grant_actions: tuple[ConnectorActionKind, ...]
    grant_actions_sha256: str = field(repr=False)
    task_state_revision: int
    payload_id: str
    payload_reference_binding_sha256: str = field(repr=False)
    parameters_sha256: str = field(repr=False)
    resource_version_sha256: str | None = field(repr=False)
    policy_version: str
    mutates_external_state: bool
    approval_class: ConnectorApprovalClass
    preparation_status: ConnectedActionPreparationStatus
    requested_at: datetime
    preparation_expires_at: datetime
    grant_expires_at: datetime
    approval_id: str | None
    approval_binding_sha256: str | None = field(repr=False)
    approval_approved_at: datetime | None
    approval_expires_at: datetime | None
    status: ConnectedDispatchStatus
    next_attempt_at: datetime | None
    attempt_count: int
    claim_id: str | None
    fencing_token: int | None
    lease_expires_at: datetime | None
    invocation_started_at: datetime | None
    terminal_outcome: str | None
    read_result_ref: str | None
    receipt_outcome: str | None
    provider_request_id_sha256: str | None = field(repr=False)
    provider_resource_id_sha256: str | None = field(repr=False)
    result_resource_version_sha256: str | None = field(repr=False)
    terminal_binding_sha256: str | None = field(repr=False)
    failure_code_sha256: str | None = field(repr=False)
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        for name in (
            "operation_id",
            "request_id",
            "owner_id",
            "grant_id",
            "action_id",
            "task_id",
            "turn_id",
            "connection_id",
            "payload_id",
        ):
            _uuid(getattr(self, name), name)
        if self.operation_id != self.action_id:
            raise ConnectedDispatchError("CONNECTED_DISPATCH_RPC_SHAPE_INVALID")
        if not isinstance(self.provider, ConnectorProvider) or not isinstance(
            self.resource, ConnectorResource
        ) or not isinstance(self.action, ConnectorActionKind):
            raise ConnectedDispatchError("CONNECTED_DISPATCH_RPC_SHAPE_INVALID")
        requirement = ConnectedActionPolicy.requirement(self.action)
        if requirement.resource is not self.resource:
            raise ConnectedDispatchError("CONNECTED_DISPATCH_RPC_SHAPE_INVALID")
        for name in (
            "authorization_snapshot_sha256",
            "granted_actions_sha256",
            "granted_scopes_sha256",
            "grant_actions_sha256",
            "payload_reference_binding_sha256",
            "parameters_sha256",
        ):
            _sha(getattr(self, name))
        if self.resource_version_sha256 is not None:
            _sha(self.resource_version_sha256)
        if type(self.authorization_revision) is not int or self.authorization_revision < 1:
            raise ConnectedDispatchError("CONNECTED_DISPATCH_RPC_SHAPE_INVALID")
        if type(self.task_state_revision) is not int or self.task_state_revision < 1:
            raise ConnectedDispatchError("CONNECTED_DISPATCH_RPC_SHAPE_INVALID")
        if not self.grant_actions or any(
            not isinstance(item, ConnectorActionKind) for item in self.grant_actions
        ):
            raise ConnectedDispatchError("CONNECTED_DISPATCH_RPC_SHAPE_INVALID")
        if self.action not in self.grant_actions or action_set_sha256(self.grant_actions) != (
            self.grant_actions_sha256
        ):
            raise ConnectedDispatchError("CONNECTED_DISPATCH_RPC_SHAPE_INVALID")
        if self.policy_version != ConnectedActionPolicy.version:
            raise ConnectedDispatchError("CONNECTED_DISPATCH_RPC_SHAPE_INVALID")
        if type(self.mutates_external_state) is not bool or (
            self.mutates_external_state != requirement.mutates_external_state
            or self.approval_class is not requirement.approval_class
        ):
            raise ConnectedDispatchError("CONNECTED_DISPATCH_RPC_SHAPE_INVALID")
        if not isinstance(self.preparation_status, ConnectedActionPreparationStatus):
            raise ConnectedDispatchError("CONNECTED_DISPATCH_RPC_SHAPE_INVALID")
        for name in (
            "requested_at",
            "preparation_expires_at",
            "grant_expires_at",
            "created_at",
            "updated_at",
        ):
            value = getattr(self, name)
            if (
                not isinstance(value, datetime)
                or value.tzinfo is None
                or value.utcoffset() is None
            ):
                raise ConnectedDispatchError("CONNECTED_DISPATCH_RPC_SHAPE_INVALID")
        for name in (
            "approval_approved_at",
            "approval_expires_at",
            "next_attempt_at",
            "lease_expires_at",
            "invocation_started_at",
            "completed_at",
        ):
            value = getattr(self, name)
            if value is not None and (
                not isinstance(value, datetime)
                or value.tzinfo is None
                or value.utcoffset() is None
            ):
                raise ConnectedDispatchError("CONNECTED_DISPATCH_RPC_SHAPE_INVALID")
        if self.preparation_expires_at <= self.requested_at:
            raise ConnectedDispatchError("CONNECTED_DISPATCH_RPC_SHAPE_INVALID")
        if self.grant_expires_at < self.preparation_expires_at:
            raise ConnectedDispatchError("CONNECTED_DISPATCH_RPC_SHAPE_INVALID")
        approval_shape = (
            self.approval_id,
            self.approval_binding_sha256,
            self.approval_approved_at,
            self.approval_expires_at,
        )
        if self.mutates_external_state:
            if self.preparation_status is not ConnectedActionPreparationStatus.PENDING_APPROVAL:
                raise ConnectedDispatchError("CONNECTED_DISPATCH_RPC_SHAPE_INVALID")
            if any(value is None for value in approval_shape):
                raise ConnectedDispatchError("CONNECTED_DISPATCH_RPC_SHAPE_INVALID")
            _uuid(self.approval_id, "approval_id")
            _sha(self.approval_binding_sha256)
            if (
                self.approval_expires_at <= self.approval_approved_at  # type: ignore[operator]
                or self.approval_expires_at > self.preparation_expires_at  # type: ignore[operator]
            ):
                raise ConnectedDispatchError("CONNECTED_DISPATCH_RPC_SHAPE_INVALID")
        elif self.preparation_status is not ConnectedActionPreparationStatus.READY or any(
            value is not None for value in approval_shape
        ):
            raise ConnectedDispatchError("CONNECTED_DISPATCH_RPC_SHAPE_INVALID")
        if not isinstance(self.status, ConnectedDispatchStatus):
            raise ConnectedDispatchError("CONNECTED_DISPATCH_RPC_SHAPE_INVALID")
        if type(self.attempt_count) is not int or self.attempt_count < 0:
            raise ConnectedDispatchError("CONNECTED_DISPATCH_RPC_SHAPE_INVALID")
        if self.claim_id is not None:
            _uuid(self.claim_id, "claim_id")
        if self.fencing_token is not None and (
            type(self.fencing_token) is not int or self.fencing_token < 1
        ):
            raise ConnectedDispatchError("CONNECTED_DISPATCH_RPC_SHAPE_INVALID")
        if self.terminal_outcome not in {
            None,
            "read",
            "succeeded",
            "ambiguous",
            "failed",
            "cancelled",
            "authority_stale",
        }:
            raise ConnectedDispatchError("CONNECTED_DISPATCH_RPC_SHAPE_INVALID")
        if self.receipt_outcome not in _RECEIPT_OUTCOMES | {None}:
            raise ConnectedDispatchError("CONNECTED_DISPATCH_RPC_SHAPE_INVALID")
        if self.read_result_ref is not None:
            _uuid(self.read_result_ref, "read_result_ref")
        for name in (
            "provider_request_id_sha256",
            "provider_resource_id_sha256",
            "result_resource_version_sha256",
            "terminal_binding_sha256",
            "failure_code_sha256",
        ):
            if getattr(self, name) is not None:
                _sha(getattr(self, name))
        result_values = (
            self.read_result_ref,
            self.receipt_outcome,
            self.provider_request_id_sha256,
            self.provider_resource_id_sha256,
            self.result_resource_version_sha256,
            self.terminal_binding_sha256,
            self.failure_code_sha256,
        )
        if self.status is ConnectedDispatchStatus.QUEUED:
            if self.next_attempt_at is None or any(
                value is not None
                for value in (
                    self.claim_id,
                    self.fencing_token,
                    self.lease_expires_at,
                    self.invocation_started_at,
                    self.completed_at,
                )
            ) or self.terminal_outcome is not None or any(
                value is not None for value in result_values
            ):
                raise ConnectedDispatchError("CONNECTED_DISPATCH_RPC_SHAPE_INVALID")
        elif self.status is ConnectedDispatchStatus.LEASED:
            if any(
                value is None
                for value in (self.claim_id, self.fencing_token, self.lease_expires_at)
            ) or any(
                value is not None
                for value in (self.next_attempt_at, self.invocation_started_at, self.completed_at)
            ) or self.terminal_outcome is not None or any(
                value is not None for value in result_values
            ):
                raise ConnectedDispatchError("CONNECTED_DISPATCH_RPC_SHAPE_INVALID")
        elif self.status is ConnectedDispatchStatus.INVOKED:
            if any(
                value is None
                for value in (
                    self.claim_id,
                    self.fencing_token,
                    self.lease_expires_at,
                    self.invocation_started_at,
                )
            ) or self.next_attempt_at is not None or self.completed_at is not None or (
                self.terminal_outcome is not None
                or any(value is not None for value in result_values)
            ):
                raise ConnectedDispatchError("CONNECTED_DISPATCH_RPC_SHAPE_INVALID")
        elif self.status in _TERMINAL:
            if (
                self.completed_at is None
                or self.next_attempt_at is not None
                or self.terminal_outcome is None
            ):
                raise ConnectedDispatchError("CONNECTED_DISPATCH_RPC_SHAPE_INVALID")
            if self.status is ConnectedDispatchStatus.READ_SUCCEEDED:
                valid_result = (
                    self.terminal_outcome == "read"
                    and self.read_result_ref is not None
                    and self.terminal_binding_sha256 is not None
                    and self.receipt_outcome is None
                    and self.provider_request_id_sha256 is None
                    and self.provider_resource_id_sha256 is None
                    and self.failure_code_sha256 is None
                )
            elif self.status is ConnectedDispatchStatus.WRITE_SUCCEEDED:
                valid_result = (
                    self.terminal_outcome == "succeeded"
                    and self.read_result_ref is None
                    and self.receipt_outcome is not None
                    and self.provider_request_id_sha256 is not None
                    and self.provider_resource_id_sha256 is not None
                    and self.result_resource_version_sha256 is not None
                    and self.terminal_binding_sha256 is not None
                    and self.failure_code_sha256 is None
                )
            elif self.status is ConnectedDispatchStatus.AMBIGUOUS:
                valid_result = (
                    self.terminal_outcome == "ambiguous"
                    and self.read_result_ref is None
                    and self.receipt_outcome is None
                    and self.provider_request_id_sha256 is None
                    and self.provider_resource_id_sha256 is None
                    and self.result_resource_version_sha256 is None
                    and self.terminal_binding_sha256 is not None
                    and self.failure_code_sha256 is None
                )
            elif self.status is ConnectedDispatchStatus.EFFECT_UNKNOWN:
                valid_result = (
                    self.terminal_outcome == "ambiguous"
                    and self.read_result_ref is None
                    and self.receipt_outcome is None
                    and self.provider_request_id_sha256 is None
                    and self.provider_resource_id_sha256 is None
                    and self.result_resource_version_sha256 is None
                    and self.failure_code_sha256 is None
                )
            elif self.status is ConnectedDispatchStatus.FAILED:
                valid_result = (
                    self.terminal_outcome == "failed"
                    and self.read_result_ref is None
                    and self.receipt_outcome is None
                    and self.provider_request_id_sha256 is None
                    and self.provider_resource_id_sha256 is None
                    and self.result_resource_version_sha256 is None
                    and self.failure_code_sha256 is not None
                )
            else:
                valid_result = (
                    self.terminal_outcome == self.status.value
                    and self.read_result_ref is None
                    and self.receipt_outcome is None
                    and self.provider_request_id_sha256 is None
                    and self.provider_resource_id_sha256 is None
                    and self.result_resource_version_sha256 is None
                    and self.terminal_binding_sha256 is None
                    and self.failure_code_sha256 is None
                )
            if not valid_result:
                raise ConnectedDispatchError("CONNECTED_DISPATCH_RPC_SHAPE_INVALID")

    @property
    def terminal(self) -> bool:
        return self.status in _TERMINAL

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
            actions=frozenset(self.grant_actions),
            actions_sha256=self.grant_actions_sha256,
            expires_at=self.grant_expires_at,
        )

    def approval(self) -> ConnectedApprovalEvidence | None:
        if not self.mutates_external_state:
            return None
        return ConnectedApprovalEvidence(
            approval_id=self.approval_id or "",
            action_id=self.action_id,
            owner_id=self.owner_id,
            task_id=self.task_id,
            turn_id=self.turn_id,
            connection_id=self.connection_id,
            provider=self.provider,
            resource=self.resource,
            action=self.action,
            authorization_revision=self.authorization_revision,
            authorization_snapshot_sha256=self.authorization_snapshot_sha256,
            approval_class=self.approval_class,
            approval_binding_sha256=self.approval_binding_sha256 or "",
            parameters_sha256=self.parameters_sha256,
            resource_version_sha256=self.resource_version_sha256,
            approved_at=self.approval_approved_at or datetime.min.replace(tzinfo=UTC),
            expires_at=self.approval_expires_at or datetime.min.replace(tzinfo=UTC),
        )

    def __repr__(self) -> str:
        return (
            "ConnectedDispatchRecord("
            f"operation_id={self.operation_id!r}, status={self.status.value!r}, "
            "bindings='<redacted>')"
        )


_RECORD_KEYS = frozenset(ConnectedDispatchRecord.__dataclass_fields__)


def _record(value: object) -> ConnectedDispatchRecord:
    if not isinstance(value, dict) or set(value) != _RECORD_KEYS:
        raise ConnectedDispatchError("CONNECTED_DISPATCH_RPC_SHAPE_INVALID")
    grant_actions_value = value["grant_actions"]
    if (
        not isinstance(grant_actions_value, list)
        or not grant_actions_value
        or len(grant_actions_value) > 16
    ):
        raise ConnectedDispatchError("CONNECTED_DISPATCH_RPC_SHAPE_INVALID")
    grant_actions = tuple(
        _enum(item, ConnectorActionKind) for item in grant_actions_value
    )
    if len(set(grant_actions)) != len(grant_actions):
        raise ConnectedDispatchError("CONNECTED_DISPATCH_RPC_SHAPE_INVALID")
    if type(value["mutates_external_state"]) is not bool:
        raise ConnectedDispatchError("CONNECTED_DISPATCH_RPC_SHAPE_INVALID")
    return ConnectedDispatchRecord(
        operation_id=_uuid(value["operation_id"], "operation_id") or "",
        request_id=_uuid(value["request_id"], "request_id") or "",
        owner_id=_uuid(value["owner_id"], "owner_id") or "",
        grant_id=_uuid(value["grant_id"], "grant_id") or "",
        action_id=_uuid(value["action_id"], "action_id") or "",
        task_id=_uuid(value["task_id"], "task_id") or "",
        turn_id=_uuid(value["turn_id"], "turn_id") or "",
        connection_id=_uuid(value["connection_id"], "connection_id") or "",
        provider=_enum(value["provider"], ConnectorProvider),  # type: ignore[arg-type]
        resource=_enum(value["resource"], ConnectorResource),  # type: ignore[arg-type]
        action=_enum(value["action"], ConnectorActionKind),  # type: ignore[arg-type]
        authorization_revision=_positive(value["authorization_revision"]),
        authorization_snapshot_sha256=_sha(
            value["authorization_snapshot_sha256"]
        ) or "",
        granted_actions_sha256=_sha(value["granted_actions_sha256"]) or "",
        granted_scopes_sha256=_sha(value["granted_scopes_sha256"]) or "",
        grant_actions=grant_actions,  # type: ignore[arg-type]
        grant_actions_sha256=_sha(value["grant_actions_sha256"]) or "",
        task_state_revision=_positive(value["task_state_revision"]),
        payload_id=_uuid(value["payload_id"], "payload_id") or "",
        payload_reference_binding_sha256=_sha(
            value["payload_reference_binding_sha256"]
        ) or "",
        parameters_sha256=_sha(value["parameters_sha256"]) or "",
        resource_version_sha256=_sha(
            value["resource_version_sha256"], optional=True
        ),
        policy_version=value["policy_version"],
        mutates_external_state=value["mutates_external_state"],
        approval_class=_enum(
            value["approval_class"], ConnectorApprovalClass
        ),  # type: ignore[arg-type]
        preparation_status=_enum(
            value["preparation_status"], ConnectedActionPreparationStatus
        ),  # type: ignore[arg-type]
        requested_at=_instant(value["requested_at"]) or datetime.min.replace(tzinfo=UTC),
        preparation_expires_at=_instant(value["preparation_expires_at"])
        or datetime.min.replace(tzinfo=UTC),
        grant_expires_at=_instant(value["grant_expires_at"])
        or datetime.min.replace(tzinfo=UTC),
        approval_id=_uuid(value["approval_id"], "approval_id", optional=True),
        approval_binding_sha256=_sha(
            value["approval_binding_sha256"], optional=True
        ),
        approval_approved_at=_instant(value["approval_approved_at"], optional=True),
        approval_expires_at=_instant(value["approval_expires_at"], optional=True),
        status=_enum(value["status"], ConnectedDispatchStatus),  # type: ignore[arg-type]
        next_attempt_at=_instant(value["next_attempt_at"], optional=True),
        attempt_count=_positive(value["attempt_count"], allow_zero=True),
        claim_id=_uuid(value["claim_id"], "claim_id", optional=True),
        fencing_token=(
            None
            if value["fencing_token"] is None
            else _positive(value["fencing_token"])
        ),
        lease_expires_at=_instant(value["lease_expires_at"], optional=True),
        invocation_started_at=_instant(value["invocation_started_at"], optional=True),
        terminal_outcome=value["terminal_outcome"],
        read_result_ref=_uuid(
            value["read_result_ref"], "read_result_ref", optional=True
        ),
        receipt_outcome=value["receipt_outcome"],
        provider_request_id_sha256=_sha(
            value["provider_request_id_sha256"], optional=True
        ),
        provider_resource_id_sha256=_sha(
            value["provider_resource_id_sha256"], optional=True
        ),
        result_resource_version_sha256=_sha(
            value["result_resource_version_sha256"], optional=True
        ),
        terminal_binding_sha256=_sha(
            value["terminal_binding_sha256"], optional=True
        ),
        failure_code_sha256=_sha(value["failure_code_sha256"], optional=True),
        completed_at=_instant(value["completed_at"], optional=True),
        created_at=_instant(value["created_at"]) or datetime.min.replace(tzinfo=UTC),
        updated_at=_instant(value["updated_at"]) or datetime.min.replace(tzinfo=UTC),
    )


class ConnectedDispatchRPC(Protocol):
    async def rpc(
        self,
        function_name: str,
        payload: dict[str, Any],
        *,
        retry_transient: bool = False,
    ) -> Any: ...


class ConnectedDispatchStore(Protocol):
    async def ensure(
        self, *, owner_id: str, request_id: str
    ) -> ConnectedDispatchRecord | None: ...

    async def scan_owners(self, *, limit: int) -> tuple[str, ...]: ...

    async def reconcile_owner(
        self, *, owner_id: str, limit: int
    ) -> tuple[ConnectedDispatchRecord, ...]: ...

    async def claim(
        self,
        *,
        owner_id: str,
        action_id: str,
        claim_id: str,
        lease_seconds: int,
    ) -> ConnectedDispatchRecord | None: ...

    async def mark_invoked(
        self,
        *,
        owner_id: str,
        action_id: str,
        claim_id: str,
        fencing_token: int,
    ) -> ConnectedDispatchRecord | None: ...

    async def preflight_failure(
        self,
        *,
        owner_id: str,
        action_id: str,
        claim_id: str,
        fencing_token: int,
        retryable: bool,
        failure_code_sha256: str,
    ) -> ConnectedDispatchRecord | None: ...

    async def settle(
        self,
        *,
        owner_id: str,
        action_id: str,
        claim_id: str,
        fencing_token: int,
    ) -> ConnectedDispatchRecord | None: ...

    async def runtime_exit(
        self,
        *,
        owner_id: str,
        action_id: str,
        claim_id: str,
        fencing_token: int,
    ) -> ConnectedDispatchRecord | None: ...

    async def read(
        self, *, owner_id: str, action_id: str
    ) -> ConnectedDispatchRecord | None: ...


class SupabaseConnectedDispatchStore:
    """Strict service-role adapter for the connected-dispatch RPC family."""

    def __init__(self, *, database: ConnectedDispatchRPC) -> None:
        if not callable(getattr(database, "rpc", None)):
            raise TypeError("dispatch RPC boundary is invalid")
        self._database = database

    async def _rpc(self, name: str, payload: dict[str, Any]) -> Any:
        try:
            return await self._database.rpc(name, payload, retry_transient=False)
        except ConnectedDispatchError:
            raise
        except Exception:
            raise ConnectedDispatchError(
                "CONNECTED_DISPATCH_RPC_FAILED", retryable=True
            ) from None

    @staticmethod
    def _limit(value: int) -> int:
        if type(value) is not int or not 1 <= value <= _MAX_LIMIT:
            raise ConnectedDispatchError("CONNECTED_DISPATCH_INVALID")
        return value

    async def scan_owners(self, *, limit: int) -> tuple[str, ...]:
        value = await self._rpc(
            "connected_dispatch_scan_owners_v1", {"p_limit": self._limit(limit)}
        )
        if not isinstance(value, list) or len(value) > limit:
            raise ConnectedDispatchError("CONNECTED_DISPATCH_RPC_SHAPE_INVALID")
        owners = tuple(_uuid(item, "owner_id") or "" for item in value)
        if len(set(owners)) != len(owners):
            raise ConnectedDispatchError("CONNECTED_DISPATCH_RPC_SHAPE_INVALID")
        return owners

    async def ensure(
        self, *, owner_id: str, request_id: str
    ) -> ConnectedDispatchRecord | None:
        return await self._record_rpc(
            "connected_dispatch_ensure_v1",
            {
                "p_owner_id": _uuid(owner_id, "owner_id"),
                "p_request_id": _uuid(request_id, "request_id"),
            },
        )

    async def reconcile_owner(
        self, *, owner_id: str, limit: int
    ) -> tuple[ConnectedDispatchRecord, ...]:
        value = await self._rpc(
            "connected_dispatch_reconcile_owner_v1",
            {
                "p_owner_id": _uuid(owner_id, "owner_id"),
                "p_limit": self._limit(limit),
            },
        )
        if not isinstance(value, dict) or set(value) != {
            "owner_id",
            "ensured_count",
            "reconciled_count",
            "ready",
        }:
            raise ConnectedDispatchError("CONNECTED_DISPATCH_RPC_SHAPE_INVALID")
        if _uuid(value["owner_id"], "owner_id") != owner_id:
            raise ConnectedDispatchError("CONNECTED_DISPATCH_RPC_SHAPE_INVALID")
        _positive(value["ensured_count"], allow_zero=True)
        _positive(value["reconciled_count"], allow_zero=True)
        rows = value["ready"]
        if not isinstance(rows, list) or len(rows) > limit:
            raise ConnectedDispatchError("CONNECTED_DISPATCH_RPC_SHAPE_INVALID")
        result = tuple(_record(row) for row in rows)
        if any(row.owner_id != owner_id or row.status is not ConnectedDispatchStatus.QUEUED for row in result):
            raise ConnectedDispatchError("CONNECTED_DISPATCH_RPC_SHAPE_INVALID")
        if len({row.action_id for row in result}) != len(result):
            raise ConnectedDispatchError("CONNECTED_DISPATCH_RPC_SHAPE_INVALID")
        return result

    async def _record_rpc(self, name: str, payload: dict[str, Any]) -> ConnectedDispatchRecord | None:
        value = await self._rpc(name, payload)
        if value is None:
            return None
        return _record(value)

    async def claim(
        self,
        *,
        owner_id: str,
        action_id: str,
        claim_id: str,
        lease_seconds: int,
    ) -> ConnectedDispatchRecord | None:
        if type(lease_seconds) is not int or not 30 <= lease_seconds <= _MAX_LEASE_SECONDS:
            raise ConnectedDispatchError("CONNECTED_DISPATCH_INVALID")
        return await self._record_rpc(
            "connected_dispatch_claim_v1",
            {
                "p_owner_id": _uuid(owner_id, "owner_id"),
                "p_action_id": _uuid(action_id, "action_id"),
                "p_claim_id": _uuid(claim_id, "claim_id"),
                "p_lease_seconds": lease_seconds,
            },
        )

    async def mark_invoked(
        self,
        *,
        owner_id: str,
        action_id: str,
        claim_id: str,
        fencing_token: int,
    ) -> ConnectedDispatchRecord | None:
        return await self._record_rpc(
            "connected_dispatch_mark_invoked_v1",
            {
                "p_owner_id": _uuid(owner_id, "owner_id"),
                "p_action_id": _uuid(action_id, "action_id"),
                "p_claim_id": _uuid(claim_id, "claim_id"),
                "p_fencing_token": _positive(fencing_token),
            },
        )

    async def preflight_failure(
        self,
        *,
        owner_id: str,
        action_id: str,
        claim_id: str,
        fencing_token: int,
        retryable: bool,
        failure_code_sha256: str,
    ) -> ConnectedDispatchRecord | None:
        if type(retryable) is not bool:
            raise ConnectedDispatchError("CONNECTED_DISPATCH_INVALID")
        return await self._record_rpc(
            "connected_dispatch_preflight_failure_v1",
            {
                "p_owner_id": _uuid(owner_id, "owner_id"),
                "p_action_id": _uuid(action_id, "action_id"),
                "p_claim_id": _uuid(claim_id, "claim_id"),
                "p_fencing_token": _positive(fencing_token),
                "p_retryable": retryable,
                "p_failure_code_sha256": _sha(failure_code_sha256),
            },
        )

    async def settle(
        self,
        *,
        owner_id: str,
        action_id: str,
        claim_id: str,
        fencing_token: int,
    ) -> ConnectedDispatchRecord | None:
        return await self._record_rpc(
            "connected_dispatch_settle_v1",
            {
                "p_owner_id": _uuid(owner_id, "owner_id"),
                "p_action_id": _uuid(action_id, "action_id"),
                "p_claim_id": _uuid(claim_id, "claim_id"),
                "p_fencing_token": _positive(fencing_token),
            },
        )

    async def runtime_exit(
        self,
        *,
        owner_id: str,
        action_id: str,
        claim_id: str,
        fencing_token: int,
    ) -> ConnectedDispatchRecord | None:
        return await self._record_rpc(
            "connected_dispatch_report_runtime_exit_v1",
            {
                "p_owner_id": _uuid(owner_id, "owner_id"),
                "p_action_id": _uuid(action_id, "action_id"),
                "p_claim_id": _uuid(claim_id, "claim_id"),
                "p_fencing_token": _positive(fencing_token),
            },
        )

    async def read(
        self, *, owner_id: str, action_id: str
    ) -> ConnectedDispatchRecord | None:
        return await self._record_rpc(
            "connected_dispatch_read_v1",
            {
                "p_owner_id": _uuid(owner_id, "owner_id"),
                "p_action_id": _uuid(action_id, "action_id"),
            },
        )

    def __repr__(self) -> str:
        return "SupabaseConnectedDispatchStore(database='<redacted>')"


class ConnectedDispatchRuntime(Protocol):
    async def run(
        self,
        invocation: Any,
        *,
        grant: ConnectedTaskGrant,
        approval: ConnectedApprovalEvidence | None = None,
        task_state_revision: int,
    ) -> ConnectedActionRuntimeResult: ...


@dataclass(frozen=True, slots=True)
class ConnectedDispatchBatchResult:
    owners_scanned: int
    actions_considered: int
    actions_invoked: int
    terminal_records: tuple[ConnectedDispatchRecord, ...]


@dataclass(frozen=True, slots=True)
class ConnectedDispatchResumeResult:
    record: ConnectedDispatchRecord | None
    invoked: bool


class ConnectedDispatchCoordinator:
    """Bounded, no-sleep worker over the database-authoritative outbox."""

    def __init__(
        self,
        *,
        store: ConnectedDispatchStore,
        payloads: ConnectedActionPayloadResolver,
        runtime: ConnectedDispatchRuntime | ConnectedAppRuntime,
        require_ready: Callable[[], None],
        new_uuid: Any = lambda: str(uuid4()),
        lease_seconds: int = _DEFAULT_LEASE_SECONDS,
    ) -> None:
        required = (
            "ensure",
            "scan_owners",
            "reconcile_owner",
            "claim",
            "mark_invoked",
            "preflight_failure",
            "settle",
            "runtime_exit",
            "read",
        )
        if any(not callable(getattr(store, name, None)) for name in required):
            raise TypeError("dispatch store is invalid")
        if not callable(getattr(payloads, "resolve", None)):
            raise TypeError("payload resolver is invalid")
        if not callable(getattr(runtime, "run", None)):
            raise TypeError("connected runtime is invalid")
        if not callable(require_ready):
            raise TypeError("dispatch readiness fence is invalid")
        if not callable(new_uuid):
            raise TypeError("dispatch UUID factory is invalid")
        if type(lease_seconds) is not int or not 30 <= lease_seconds <= _MAX_LEASE_SECONDS:
            raise ValueError("dispatch lease is invalid")
        self._store = store
        self._payloads = payloads
        self._runtime = runtime
        self._require_ready = require_ready
        self._new_uuid = new_uuid
        self._lease_seconds = lease_seconds

    def _require_effect_ready(self) -> None:
        try:
            self._require_ready()
        except Exception:
            raise ConnectedDispatchError(
                "CONNECTED_DISPATCH_NOT_READY", retryable=True
            ) from None

    async def resume_prepared(
        self, *, owner_id: str, request_id: str
    ) -> ConnectedDispatchResumeResult:
        """Ensure and run one exact READY/APPROVED durable preparation.

        This is the post-route wake-up interface.  It never makes a pending,
        denied, expired, or stale preparation executable; the database source
        rows are revalidated by ``connected_dispatch_ensure_v1`` before a row
        can be claimed.
        """

        owner_id = _uuid(owner_id, "owner_id") or ""
        request_id = _uuid(request_id, "request_id") or ""
        try:
            record = await self._store.ensure(
                owner_id=owner_id, request_id=request_id
            )
        except Exception:
            # An ensure is content-free and has no provider effect.  One exact
            # idempotent read/ensure retry closes the route-response-loss gap;
            # startup reconciliation remains the host-crash recovery path.
            record = await self._store.ensure(
                owner_id=owner_id, request_id=request_id
            )
        if record is None or record.status is not ConnectedDispatchStatus.QUEUED:
            return ConnectedDispatchResumeResult(record=record, invoked=False)
        if record.owner_id != owner_id or record.request_id != request_id:
            raise ConnectedDispatchError("CONNECTED_DISPATCH_RPC_SHAPE_INVALID")
        settled, invoked = await self._run_candidate(record)
        return ConnectedDispatchResumeResult(record=settled, invoked=invoked)

    async def reconcile_startup(
        self, *, owner_limit: int = 25, per_owner_limit: int = 25
    ) -> tuple[ConnectedDispatchRecord, ...]:
        if not 1 <= owner_limit <= _MAX_LIMIT or not 1 <= per_owner_limit <= _MAX_LIMIT:
            raise ConnectedDispatchError("CONNECTED_DISPATCH_INVALID")
        owners = await self._store.scan_owners(limit=owner_limit)
        ready: list[ConnectedDispatchRecord] = []
        for owner_id in owners:
            ready.extend(
                await self._store.reconcile_owner(
                    owner_id=owner_id, limit=per_owner_limit
                )
            )
        return tuple(ready)

    async def run_bounded(
        self, *, owner_limit: int = 10, per_owner_limit: int = 10
    ) -> ConnectedDispatchBatchResult:
        if not 1 <= owner_limit <= _MAX_LIMIT or not 1 <= per_owner_limit <= _MAX_LIMIT:
            raise ConnectedDispatchError("CONNECTED_DISPATCH_INVALID")
        owners = await self._store.scan_owners(limit=owner_limit)
        considered = 0
        invoked = 0
        terminal: list[ConnectedDispatchRecord] = []
        for owner_id in owners:
            ready = await self._store.reconcile_owner(
                owner_id=owner_id, limit=per_owner_limit
            )
            considered += len(ready)
            for candidate in ready:
                result, did_invoke = await self._run_candidate(candidate)
                invoked += int(did_invoke)
                if result is not None and result.terminal:
                    terminal.append(result)
        return ConnectedDispatchBatchResult(
            owners_scanned=len(owners),
            actions_considered=considered,
            actions_invoked=invoked,
            terminal_records=tuple(terminal),
        )

    async def _readback(self, candidate: ConnectedDispatchRecord) -> ConnectedDispatchRecord | None:
        try:
            value = await self._store.read(
                owner_id=candidate.owner_id, action_id=candidate.action_id
            )
        except Exception:
            return None
        if value is not None and (
            value.owner_id != candidate.owner_id
            or value.action_id != candidate.action_id
            or value.request_id != candidate.request_id
        ):
            raise ConnectedDispatchError("CONNECTED_DISPATCH_RPC_SHAPE_INVALID")
        return value

    async def _claim_with_readback(
        self, candidate: ConnectedDispatchRecord, claim_id: str
    ) -> ConnectedDispatchRecord | None:
        try:
            claimed = await self._store.claim(
                owner_id=candidate.owner_id,
                action_id=candidate.action_id,
                claim_id=claim_id,
                lease_seconds=self._lease_seconds,
            )
        except Exception:
            claimed = await self._readback(candidate)
        if (
            claimed is None
            or claimed.status is not ConnectedDispatchStatus.LEASED
            or claimed.claim_id != claim_id
            or claimed.fencing_token is None
        ):
            return None
        return claimed

    async def _mark_invoked_with_readback(
        self, claimed: ConnectedDispatchRecord
    ) -> ConnectedDispatchRecord | None:
        try:
            invoked = await self._store.mark_invoked(
                owner_id=claimed.owner_id,
                action_id=claimed.action_id,
                claim_id=claimed.claim_id or "",
                fencing_token=claimed.fencing_token or 0,
            )
        except Exception:
            invoked = await self._readback(claimed)
        if (
            invoked is None
            or invoked.status is not ConnectedDispatchStatus.INVOKED
            or invoked.claim_id != claimed.claim_id
            or invoked.fencing_token != claimed.fencing_token
        ):
            return None
        return invoked

    async def _run_candidate(
        self, candidate: ConnectedDispatchRecord
    ) -> tuple[ConnectedDispatchRecord | None, bool]:
        # Fence each individual durable claim.  A batch-level attestation is
        # insufficient because a bounded batch can outlive its proof.
        self._require_effect_ready()
        claim_id = _uuid(self._new_uuid(), "claim_id") or ""
        claimed = await self._claim_with_readback(candidate, claim_id)
        if claimed is None:
            return None, False
        intent = claimed.intent()
        try:
            resolved = await self._payloads.resolve(
                payload_id=claimed.payload_id, intent=intent
            )
            if resolved.invocation.intent != intent:
                raise ConnectedPayloadResolutionError(
                    "CONNECTED_PAYLOAD_BINDING_MISMATCH"
                )
        except ConnectedPayloadResolutionError as error:
            retryable = error.code == "CONNECTED_PAYLOAD_UNAVAILABLE"
            record = await self._store.preflight_failure(
                owner_id=claimed.owner_id,
                action_id=claimed.action_id,
                claim_id=claimed.claim_id or "",
                fencing_token=claimed.fencing_token or 0,
                retryable=retryable,
                failure_code_sha256=_failure_hash(error.code),
            )
            return record, False
        except Exception:
            record = await self._store.preflight_failure(
                owner_id=claimed.owner_id,
                action_id=claimed.action_id,
                claim_id=claimed.claim_id or "",
                fencing_token=claimed.fencing_token or 0,
                retryable=True,
                failure_code_sha256=_failure_hash(
                    "CONNECTED_DISPATCH_PAYLOAD_INVALID"
                ),
            )
            return record, False

        # Payload resolution can be slow; recheck before crossing into the
        # durable invoked/effect phase.
        self._require_effect_ready()
        invoked = await self._mark_invoked_with_readback(claimed)
        if invoked is None:
            return None, False
        try:
            # The database transition above is an await point.  Recheck once
            # more immediately before the provider-capable runtime call.
            self._require_effect_ready()
        except ConnectedDispatchError:
            try:
                await self._store.runtime_exit(
                    owner_id=invoked.owner_id,
                    action_id=invoked.action_id,
                    claim_id=invoked.claim_id or "",
                    fencing_token=invoked.fencing_token or 0,
                )
            except Exception:
                await self._readback(invoked)
            raise
        try:
            runtime_result = await self._runtime.run(
                resolved.invocation,
                grant=invoked.grant(),
                approval=invoked.approval(),
                task_state_revision=invoked.task_state_revision,
            )
            if (
                type(runtime_result) is not ConnectedActionRuntimeResult
                or runtime_result.operation_id != invoked.operation_id
            ):
                raise ConnectedDispatchError("CONNECTED_DISPATCH_RUNTIME_FAILED")
        except Exception:
            try:
                record = await self._store.runtime_exit(
                    owner_id=invoked.owner_id,
                    action_id=invoked.action_id,
                    claim_id=invoked.claim_id or "",
                    fencing_token=invoked.fencing_token or 0,
                )
            except Exception:
                record = await self._readback(invoked)
            return record, True

        try:
            settled = await self._store.settle(
                owner_id=invoked.owner_id,
                action_id=invoked.action_id,
                claim_id=invoked.claim_id or "",
                fencing_token=invoked.fencing_token or 0,
            )
        except Exception:
            settled = await self._readback(invoked)
        if settled is None or not settled.terminal:
            try:
                settled = await self._store.runtime_exit(
                    owner_id=invoked.owner_id,
                    action_id=invoked.action_id,
                    claim_id=invoked.claim_id or "",
                    fencing_token=invoked.fencing_token or 0,
                )
            except Exception:
                settled = await self._readback(invoked)
        if settled is None or not settled.terminal:
            raise ConnectedDispatchError(
                "CONNECTED_DISPATCH_SETTLEMENT_FAILED", retryable=True
            )
        return settled, True

    def __repr__(self) -> str:
        return "ConnectedDispatchCoordinator(authority='database', runtime='<redacted>')"
