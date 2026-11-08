"""Fail-closed, content-free orchestration for connected mail and calendars."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field, fields
from datetime import datetime, timedelta, timezone
from enum import StrEnum
import hashlib
import json
import re
from typing import Protocol, TypeAlias, TypeVar
from uuid import UUID, uuid4

from .connected_app_contracts import (
    AmbiguousProviderResult,
    CalendarCancelRequest,
    CalendarCreateRequest,
    CalendarFreeBusyRequest,
    CalendarGetRequest,
    CalendarListRequest,
    CalendarUpdateRequest,
    ConnectedAccountRef,
    ConnectedAuthorizationSnapshot,
    CredentialHandleRef,
    MailDraftRequest,
    MailGetRequest,
    MailReplyRequest,
    MailSearchRequest,
    MailSendRequest,
    ProviderReceipt,
)
from .connected_app_policy import (
    ConnectedActionIntent,
    ConnectedActionPolicy,
    ConnectedApprovalEvidence,
    ConnectedTaskGrant,
    ConnectorActionKind,
    ConnectorDecisionKind,
    ConnectorProvider,
    ConnectorResource,
    implemented_runtime_actions,
)
from .connected_app_scopes import scopes_cover

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_VERSION = re.compile(r"^[^\x00-\x1f\x7f]{1,512}$")
_AUTHORITATIVE_RECEIPT_ACTIONS = frozenset(
    {
        ConnectorActionKind.MAIL_CREATE_DRAFT,
        ConnectorActionKind.MAIL_SEND,
        # Reply adapters reconcile the newly sent message before returning a
        # receipt.  Re-reading the source message cannot prove the newly
        # created reply and its version can never equal the reply receipt.
        ConnectorActionKind.MAIL_REPLY,
        ConnectorActionKind.CALENDAR_CREATE,
    }
)
_LEDGER_AUTHORITY_CODES = frozenset(
    {
        "CONNECTED_TASK_CANCELLED",
        "CONNECTED_TASK_STATE_REVISION_CHANGED",
        "CONNECTED_AUTHORIZATION_INACTIVE",
        "CONNECTED_AUTHORIZATION_CHANGED",
        "CONNECTED_AUTHORIZATION_ACTION_INSUFFICIENT",
        "CONNECTED_AUTHORIZATION_SCOPE_INSUFFICIENT",
        "CONNECTED_CLAIM_EXPIRED",
        "CONNECTED_LEDGER_FENCE_REJECTED",
        "CONNECTED_LEDGER_ACCESS_AUTHORITY_MISMATCH",
        "CONNECTED_LEDGER_ACCESS_NONCE_MISMATCH",
        "CONNECTED_LEDGER_ACCESS_RECOVERY_REJECTED",
        "CONNECTED_LEDGER_EFFECT_AUTHORITY_MISMATCH",
        "CONNECTED_LEDGER_EFFECT_NONCE_MISMATCH",
        "CONNECTED_LEDGER_POSTOBSERVE_AUTHORITY_MISMATCH",
        "CONNECTED_LEDGER_POSTOBSERVE_NONCE_MISMATCH",
    }
)


def _uuid(value: str, name: str) -> str:
    try:
        canonical = str(UUID(str(value)))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError(f"{name} must be a UUID") from exc
    if value != canonical:
        raise ValueError(f"{name} must use canonical UUID form")
    return canonical


def _sha(value: str, name: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ValueError(f"{name} must be a lowercase SHA-256 digest")
    return value


def _aware(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _canonical(value: object) -> object:
    if value is None or type(value) in {bool, int, str}:
        return value
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, datetime):
        return _aware(value, "datetime").isoformat()
    if isinstance(value, (tuple, list, set, frozenset)):
        result = [_canonical(item) for item in value]
        return sorted(result, key=lambda item: json.dumps(item, sort_keys=True))
    raise TypeError("record contains a non-content-free field")


def _record_hash(value: object) -> str:
    data = {item.name: _canonical(getattr(value, item.name)) for item in fields(value)}
    encoded = json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


class ConnectedAppRuntimeError(RuntimeError):
    """Content-free runtime failure."""

    def __init__(self, code: str, *, retryable: bool = False) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable


class ConnectedActionClaimStatus(StrEnum):
    CLAIMED = "claimed"
    ACCESS_GRANTED = "access_granted"
    EFFECT_POSSIBLE = "effect_possible"
    BUSY = "busy"
    REPLAY_READ = "replay_read"
    REPLAY_SUCCEEDED = "replay_succeeded"
    REPLAY_AMBIGUOUS = "replay_ambiguous"


class ConnectedActionOutcome(StrEnum):
    READ = "read"
    SUCCEEDED = "succeeded"
    AMBIGUOUS = "ambiguous"


class ConnectedCredentialPhase(StrEnum):
    """Exact one-use purpose of a broker-issued child credential lease."""

    READ = "read"
    PREOBSERVE = "preobserve"
    EFFECT = "effect"
    POSTOBSERVE = "postobserve"


_T = TypeVar("_T")


@dataclass(frozen=True, slots=True, repr=False)
class ConnectedReadObservation:
    operation_id: str
    provider: ConnectorProvider
    resource: ConnectorResource
    value: object = field(repr=False, compare=False)
    observed_at: datetime
    resource_version: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "operation_id", _uuid(self.operation_id, "operation_id"))
        object.__setattr__(self, "observed_at", _aware(self.observed_at, "observed_at"))
        if not isinstance(self.provider, ConnectorProvider) or not isinstance(
            self.resource, ConnectorResource
        ):
            raise ValueError("provider/resource is invalid")
        if self.resource_version is not None and not _VERSION.fullmatch(self.resource_version):
            raise ValueError("resource_version is invalid")

    def __repr__(self) -> str:
        return f"ConnectedReadObservation(operation_id={self.operation_id!r}, untrusted=True)"


ProviderRequest: TypeAlias = (
    MailSearchRequest
    | MailGetRequest
    | MailDraftRequest
    | MailSendRequest
    | MailReplyRequest
    | CalendarListRequest
    | CalendarFreeBusyRequest
    | CalendarGetRequest
    | CalendarCreateRequest
    | CalendarUpdateRequest
    | CalendarCancelRequest
)
_REQUESTS: dict[ConnectorActionKind, type[object]] = {
    ConnectorActionKind.MAIL_SEARCH: MailSearchRequest,
    ConnectorActionKind.MAIL_GET: MailGetRequest,
    ConnectorActionKind.MAIL_CREATE_DRAFT: MailDraftRequest,
    ConnectorActionKind.MAIL_SEND: MailSendRequest,
    ConnectorActionKind.MAIL_REPLY: MailReplyRequest,
    ConnectorActionKind.CALENDAR_LIST: CalendarListRequest,
    ConnectorActionKind.CALENDAR_FREE_BUSY: CalendarFreeBusyRequest,
    ConnectorActionKind.CALENDAR_GET: CalendarGetRequest,
    ConnectorActionKind.CALENDAR_CREATE: CalendarCreateRequest,
    ConnectorActionKind.CALENDAR_UPDATE: CalendarUpdateRequest,
    ConnectorActionKind.CALENDAR_CANCEL: CalendarCancelRequest,
}
_READS = frozenset(
    {
        ConnectorActionKind.MAIL_SEARCH,
        ConnectorActionKind.MAIL_GET,
        ConnectorActionKind.CALENDAR_LIST,
        ConnectorActionKind.CALENDAR_FREE_BUSY,
        ConnectorActionKind.CALENDAR_GET,
    }
)
_OUTCOMES = {
    ConnectorActionKind.MAIL_CREATE_DRAFT: "drafted",
    ConnectorActionKind.MAIL_SEND: "sent",
    ConnectorActionKind.MAIL_REPLY: "sent",
    ConnectorActionKind.CALENDAR_CREATE: "created",
    ConnectorActionKind.CALENDAR_UPDATE: "updated",
    ConnectorActionKind.CALENDAR_CANCEL: "cancelled",
}
if frozenset(_REQUESTS) != implemented_runtime_actions() or (
    _READS | frozenset(_OUTCOMES)
) != frozenset(_REQUESTS):
    raise RuntimeError("connected action dispatch is not exhaustive")


@dataclass(frozen=True, slots=True, repr=False)
class ConnectedActionInvocation:
    intent: ConnectedActionIntent
    request: ProviderRequest = field(repr=False, compare=False)
    # Keyed vault commitment over the encrypted action envelope.  This value is
    # safe to persist as the control-plane parameters binding; it is not the
    # predictable SHA-256 of the recipient, subject, body, or provider IDs.
    payload_sha256: str
    # Plain provider-target digest recovered from inside the encrypted envelope.
    # It is verified in memory and must never be copied into durable metadata.
    request_target_binding_sha256: str = field(repr=False)
    expected_resource_version: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        expected_type = _REQUESTS.get(self.intent.action)
        if expected_type is None or type(self.request) is not expected_type:
            raise ValueError("request type does not match the action")
        commitment = _sha(self.payload_sha256, "payload_sha256")
        if commitment != self.intent.parameters_sha256:
            raise ValueError("request does not match authorized parameters")
        target_binding = _sha(
            self.request_target_binding_sha256,
            "request_target_binding_sha256",
        )
        if target_binding != self.request.target_binding_sha256:
            raise ValueError("request target does not match encrypted payload")
        if self.expected_resource_version is None:
            if self.intent.resource_version_sha256 is not None:
                raise ValueError("expected resource version is missing")
        elif (
            not _VERSION.fullmatch(self.expected_resource_version)
            or _hash(self.expected_resource_version) != self.intent.resource_version_sha256
        ):
            raise ValueError("expected resource version does not match the intent")

    @property
    def binding_sha256(self) -> str:
        return _record_hash(self.intent)

    def __repr__(self) -> str:
        return (
            f"ConnectedActionInvocation(action={self.intent.action.value!r}, request='<untrusted>')"
        )


@dataclass(frozen=True, slots=True, repr=False)
class ConnectedAccountBinding:
    account: ConnectedAccountRef
    authorization: ConnectedAuthorizationSnapshot = field(repr=False)

    def __post_init__(self) -> None:
        if not self.authorization.binds(self.account):
            raise ValueError("authorization does not bind account")

    def __repr__(self) -> str:
        return "ConnectedAccountBinding(account='<redacted>', authorization='<redacted>')"


@dataclass(frozen=True, slots=True, repr=False)
class ConnectedActionLookupRecord:
    operation_id: str
    owner_id: str
    task_id: str
    turn_id: str
    connection_id: str
    provider: ConnectorProvider
    resource: ConnectorResource
    action: ConnectorActionKind
    parameters_sha256: str
    resource_version_sha256: str | None
    binding_sha256: str
    idempotency_key_hash: str

    def __post_init__(self) -> None:
        for name in ("operation_id", "owner_id", "task_id", "turn_id", "connection_id"):
            object.__setattr__(self, name, _uuid(getattr(self, name), name))
        if not isinstance(self.provider, ConnectorProvider):
            raise ValueError("provider is invalid")
        if not isinstance(self.resource, ConnectorResource):
            raise ValueError("resource is invalid")
        if not isinstance(self.action, ConnectorActionKind):
            raise ValueError("action is invalid")
        _sha(self.parameters_sha256, "parameters_sha256")
        if self.resource_version_sha256 is not None:
            _sha(self.resource_version_sha256, "resource_version_sha256")
        _sha(self.binding_sha256, "binding_sha256")
        _sha(self.idempotency_key_hash, "idempotency_key_hash")

    def __repr__(self) -> str:
        return f"ConnectedActionLookupRecord(action={self.action.value!r}, hashes='<redacted>')"


@dataclass(frozen=True, slots=True, repr=False)
class ConnectedActionAuthorityRecord:
    grant_id: str
    grant_sha256: str
    grant_expires_at: datetime
    approval_id: str | None
    approval_sha256: str | None
    approval_expires_at: datetime | None
    authorization_revision: int
    authorization_snapshot_sha256: str
    granted_actions_sha256: str
    granted_scopes_sha256: str
    task_state_revision: int
    policy_version: str
    decided_at: datetime

    def __post_init__(self) -> None:
        _uuid(self.grant_id, "grant_id")
        _sha(self.grant_sha256, "grant_sha256")
        _aware(self.grant_expires_at, "grant_expires_at")
        present = (self.approval_id, self.approval_sha256, self.approval_expires_at)
        if any(v is None for v in present) and any(v is not None for v in present):
            raise ValueError("approval authority is partial")
        if self.approval_id:
            _uuid(self.approval_id, "approval_id")
            _sha(self.approval_sha256 or "", "approval_sha256")
            _aware(self.approval_expires_at, "approval_expires_at")  # type: ignore[arg-type]
        if type(self.authorization_revision) is not int or self.authorization_revision < 1:
            raise ValueError("authorization revision is invalid")
        _sha(self.authorization_snapshot_sha256, "authorization_snapshot_sha256")
        _sha(self.granted_actions_sha256, "granted_actions_sha256")
        _sha(self.granted_scopes_sha256, "granted_scopes_sha256")
        if type(self.task_state_revision) is not int or self.task_state_revision < 1:
            raise ValueError("task state revision is invalid")
        if not isinstance(self.policy_version, str) or not self.policy_version:
            raise ValueError("policy version is invalid")
        _aware(self.decided_at, "decided_at")

    @property
    def authority_sha256(self) -> str:
        return _record_hash(self)

    def __repr__(self) -> str:
        return "ConnectedActionAuthorityRecord(authority='<redacted>')"


@dataclass(frozen=True, slots=True, repr=False)
class ConnectedActionClaimRequest:
    lookup: ConnectedActionLookupRecord
    claim_request_id: str
    authority_sha256: str
    granted_actions_sha256: str
    mutates_external_state: bool
    requested_at: datetime
    execution_deadline: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.lookup, ConnectedActionLookupRecord):
            raise ValueError("lookup is invalid")
        _uuid(self.claim_request_id, "claim_request_id")
        _sha(self.authority_sha256, "authority_sha256")
        _sha(self.granted_actions_sha256, "granted_actions_sha256")
        if type(self.mutates_external_state) is not bool:
            raise ValueError("mutates_external_state is invalid")
        requested = _aware(self.requested_at, "requested_at")
        if _aware(self.execution_deadline, "execution_deadline") <= requested:
            raise ValueError("execution deadline must be after request")

    def __repr__(self) -> str:
        return "ConnectedActionClaimRequest(binding='<redacted>', authority='<redacted>')"


@dataclass(frozen=True, slots=True, repr=False)
class ConnectedCredentialLease:
    """One-use broker lease.  Only a dispatcher may unwrap ``credential``.

    A dispatcher implementation must atomically consume ``use_nonce`` immediately
    before it passes the opaque handle to a typed provider method.  It must also
    verify the claim/fencing token remains the broker's current durable capability.
    A consumed, expired, or access-recovery-fenced lease must never be accepted
    again, even after process recovery.
    """

    credential: CredentialHandleRef = field(repr=False, compare=False)
    owner_id: str
    connection_id: str
    provider: ConnectorProvider
    resource: ConnectorResource
    authorization_revision: int
    authorization_snapshot_sha256: str
    granted_actions_sha256: str
    granted_scopes_sha256: str
    authority_sha256: str
    task_state_revision: int
    claim_id: str
    fencing_token: int
    phase: ConnectedCredentialPhase
    use_nonce: str
    issued_at: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        for name in ("owner_id", "connection_id", "claim_id", "use_nonce"):
            object.__setattr__(self, name, _uuid(getattr(self, name), name))
        if not isinstance(self.provider, ConnectorProvider):
            raise ValueError("provider is invalid")
        if not isinstance(self.resource, ConnectorResource):
            raise ValueError("resource is invalid")
        if type(self.authorization_revision) is not int or self.authorization_revision < 1:
            raise ValueError("authorization revision is invalid")
        if type(self.task_state_revision) is not int or self.task_state_revision < 1:
            raise ValueError("task state revision is invalid")
        if type(self.fencing_token) is not int or self.fencing_token < 1:
            raise ValueError("fencing token is invalid")
        if not isinstance(self.phase, ConnectedCredentialPhase):
            raise ValueError("credential phase is invalid")
        _sha(self.authorization_snapshot_sha256, "authorization_snapshot_sha256")
        _sha(self.granted_actions_sha256, "granted_actions_sha256")
        _sha(self.granted_scopes_sha256, "granted_scopes_sha256")
        _sha(self.authority_sha256, "authority_sha256")
        issued = _aware(self.issued_at, "issued_at")
        if _aware(self.expires_at, "expires_at") <= issued:
            raise ValueError("credential lease expiry is invalid")
        if (
            self.credential.owner_id != self.owner_id
            or self.credential.connection_id != self.connection_id
            or self.credential.provider is not self.provider
        ):
            raise ValueError("credential handle does not bind the lease")

    def __repr__(self) -> str:
        return "ConnectedCredentialLease(handle='<redacted>', authority='<redacted>')"


@dataclass(frozen=True, slots=True, repr=False)
class ConnectedActionEffectRequest:
    """Content-free input to the ledger's atomic effect linearization point."""

    lookup: ConnectedActionLookupRecord
    claim_request_id: str
    claim_id: str
    approval_id: str
    fencing_token: int
    authority_sha256: str
    task_state_revision: int
    authorization_revision: int
    authorization_snapshot_sha256: str
    granted_actions_sha256: str
    granted_scopes_sha256: str
    approval_binding_sha256: str
    credential_use_nonce: str
    credential_expires_at: datetime
    requested_at: datetime
    execution_deadline: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.lookup, ConnectedActionLookupRecord):
            raise ValueError("lookup is invalid")
        for name in (
            "claim_request_id",
            "claim_id",
            "approval_id",
            "credential_use_nonce",
        ):
            object.__setattr__(self, name, _uuid(getattr(self, name), name))
        if type(self.fencing_token) is not int or self.fencing_token < 1:
            raise ValueError("fencing token is invalid")
        if type(self.task_state_revision) is not int or self.task_state_revision < 1:
            raise ValueError("task state revision is invalid")
        if type(self.authorization_revision) is not int or self.authorization_revision < 1:
            raise ValueError("authorization revision is invalid")
        for name in (
            "authority_sha256",
            "authorization_snapshot_sha256",
            "granted_actions_sha256",
            "granted_scopes_sha256",
            "approval_binding_sha256",
        ):
            _sha(getattr(self, name), name)
        requested = _aware(self.requested_at, "requested_at")
        expires = _aware(self.credential_expires_at, "credential_expires_at")
        deadline = _aware(self.execution_deadline, "execution_deadline")
        if expires <= requested or deadline <= requested or expires > deadline:
            raise ValueError("effect deadline must be after request")

    def __repr__(self) -> str:
        return "ConnectedActionEffectRequest(binding='<redacted>', authority='<redacted>')"


@dataclass(frozen=True, slots=True, repr=False)
class ConnectedActionAccessRequest:
    """Content-free input to the ledger's atomic read-access boundary."""

    lookup: ConnectedActionLookupRecord
    claim_request_id: str
    claim_id: str
    fencing_token: int
    authority_sha256: str
    task_state_revision: int
    authorization_revision: int
    authorization_snapshot_sha256: str
    granted_actions_sha256: str
    granted_scopes_sha256: str
    phase: ConnectedCredentialPhase
    credential_use_nonce: str
    credential_expires_at: datetime
    requested_at: datetime
    execution_deadline: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.lookup, ConnectedActionLookupRecord):
            raise ValueError("lookup is invalid")
        for name in ("claim_request_id", "claim_id", "credential_use_nonce"):
            object.__setattr__(self, name, _uuid(getattr(self, name), name))
        if type(self.fencing_token) is not int or self.fencing_token < 1:
            raise ValueError("fencing token is invalid")
        if type(self.task_state_revision) is not int or self.task_state_revision < 1:
            raise ValueError("task state revision is invalid")
        if type(self.authorization_revision) is not int or self.authorization_revision < 1:
            raise ValueError("authorization revision is invalid")
        if self.phase not in {
            ConnectedCredentialPhase.READ,
            ConnectedCredentialPhase.PREOBSERVE,
        }:
            raise ValueError("read access phase is invalid")
        for name in (
            "authority_sha256",
            "authorization_snapshot_sha256",
            "granted_actions_sha256",
            "granted_scopes_sha256",
        ):
            _sha(getattr(self, name), name)
        requested = _aware(self.requested_at, "requested_at")
        expires = _aware(self.credential_expires_at, "credential_expires_at")
        deadline = _aware(self.execution_deadline, "execution_deadline")
        if expires <= requested or deadline <= requested or expires > deadline:
            raise ValueError("read access time bounds are invalid")

    def __repr__(self) -> str:
        return "ConnectedActionAccessRequest(binding='<redacted>', authority='<redacted>')"


@dataclass(frozen=True, slots=True, repr=False)
class ConnectedActionAccessRecoveryRequest:
    """Atomic reclaim of an expired access-only row under fresh authority."""

    lookup: ConnectedActionLookupRecord
    expired_claim_id: str
    claim_request_id: str
    authority_sha256: str
    task_state_revision: int
    authorization_revision: int
    authorization_snapshot_sha256: str
    granted_actions_sha256: str
    granted_scopes_sha256: str
    phase: ConnectedCredentialPhase
    credential_use_nonce: str
    credential_expires_at: datetime
    requested_at: datetime
    execution_deadline: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.lookup, ConnectedActionLookupRecord):
            raise ValueError("lookup is invalid")
        for name in ("expired_claim_id", "claim_request_id", "credential_use_nonce"):
            object.__setattr__(self, name, _uuid(getattr(self, name), name))
        if type(self.task_state_revision) is not int or self.task_state_revision < 1:
            raise ValueError("task state revision is invalid")
        if type(self.authorization_revision) is not int or self.authorization_revision < 1:
            raise ValueError("authorization revision is invalid")
        if self.phase not in {
            ConnectedCredentialPhase.READ,
            ConnectedCredentialPhase.PREOBSERVE,
        }:
            raise ValueError("access recovery phase is invalid")
        for name in (
            "authority_sha256",
            "authorization_snapshot_sha256",
            "granted_actions_sha256",
            "granted_scopes_sha256",
        ):
            _sha(getattr(self, name), name)
        requested = _aware(self.requested_at, "requested_at")
        expires = _aware(self.credential_expires_at, "credential_expires_at")
        deadline = _aware(self.execution_deadline, "execution_deadline")
        if expires <= requested or deadline <= requested or expires > deadline:
            raise ValueError("access recovery time bounds are invalid")

    def __repr__(self) -> str:
        return "ConnectedActionAccessRecoveryRequest(binding='<redacted>', authority='<redacted>')"


@dataclass(frozen=True, slots=True, repr=False)
class ConnectedActionPostobserveRequest:
    """Read-only post-effect access fence; it cannot authorize an effect."""

    lookup: ConnectedActionLookupRecord
    claim_request_id: str
    claim_id: str
    fencing_token: int
    authority_sha256: str
    task_state_revision: int
    authorization_revision: int
    authorization_snapshot_sha256: str
    granted_actions_sha256: str
    granted_scopes_sha256: str
    effect_use_nonce: str
    credential_use_nonce: str
    credential_expires_at: datetime
    requested_at: datetime
    execution_deadline: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.lookup, ConnectedActionLookupRecord):
            raise ValueError("lookup is invalid")
        for name in (
            "claim_request_id",
            "claim_id",
            "effect_use_nonce",
            "credential_use_nonce",
        ):
            object.__setattr__(self, name, _uuid(getattr(self, name), name))
        if type(self.fencing_token) is not int or self.fencing_token < 1:
            raise ValueError("fencing token is invalid")
        if type(self.task_state_revision) is not int or self.task_state_revision < 1:
            raise ValueError("task state revision is invalid")
        if type(self.authorization_revision) is not int or self.authorization_revision < 1:
            raise ValueError("authorization revision is invalid")
        for name in (
            "authority_sha256",
            "authorization_snapshot_sha256",
            "granted_actions_sha256",
            "granted_scopes_sha256",
        ):
            _sha(getattr(self, name), name)
        requested = _aware(self.requested_at, "requested_at")
        expires = _aware(self.credential_expires_at, "credential_expires_at")
        deadline = _aware(self.execution_deadline, "execution_deadline")
        if expires <= requested or deadline <= requested or expires > deadline:
            raise ValueError("post-observation time bounds are invalid")
        if self.effect_use_nonce == self.credential_use_nonce:
            raise ValueError("post-observation nonce must be distinct from effect")

    def __repr__(self) -> str:
        return "ConnectedActionPostobserveRequest(binding='<redacted>', authority='<redacted>')"


@dataclass(frozen=True, slots=True, repr=False)
class _Terminal:
    operation_id: str
    provider: ConnectorProvider
    resource: ConnectorResource
    action: ConnectorActionKind
    binding_sha256: str
    authority_sha256: str
    idempotency_key_hash: str
    observed_at: datetime

    def __post_init__(self) -> None:
        _uuid(self.operation_id, "operation_id")
        if not isinstance(self.provider, ConnectorProvider):
            raise ValueError("provider is invalid")
        if not isinstance(self.resource, ConnectorResource):
            raise ValueError("resource is invalid")
        if not isinstance(self.action, ConnectorActionKind):
            raise ValueError("action is invalid")
        for name in ("binding_sha256", "authority_sha256", "idempotency_key_hash"):
            _sha(getattr(self, name), name)
        _aware(self.observed_at, "observed_at")

    def __repr__(self) -> str:
        return f"{type(self).__name__}(action={self.action.value!r}, hashes='<redacted>')"


@dataclass(frozen=True, slots=True, repr=False)
class ConnectedReadTerminalRecord(_Terminal):
    resource_version_sha256: str | None = None

    def __post_init__(self) -> None:
        super(ConnectedReadTerminalRecord, self).__post_init__()
        if self.resource_version_sha256 is not None:
            _sha(self.resource_version_sha256, "resource_version_sha256")


@dataclass(frozen=True, slots=True, repr=False)
class ConnectedWriteTerminalRecord(_Terminal):
    receipt_outcome: str
    provider_request_id_hash: str
    resource_id_hash: str
    resource_version_sha256: str

    def __post_init__(self) -> None:
        super(ConnectedWriteTerminalRecord, self).__post_init__()
        if not isinstance(self.receipt_outcome, str) or not self.receipt_outcome:
            raise ValueError("receipt_outcome is invalid")
        for name in ("provider_request_id_hash", "resource_id_hash", "resource_version_sha256"):
            _sha(getattr(self, name), name)


@dataclass(frozen=True, slots=True, repr=False)
class ConnectedAmbiguousTerminalRecord(_Terminal):
    code: str = "CONNECTED_PROVIDER_RESULT_AMBIGUOUS"
    retryable: bool = False

    def __post_init__(self) -> None:
        super(ConnectedAmbiguousTerminalRecord, self).__post_init__()
        if self.code != "CONNECTED_PROVIDER_RESULT_AMBIGUOUS" or self.retryable:
            raise ValueError("ambiguous terminal is fixed and nonretryable")


LedgerTerminal: TypeAlias = (
    ConnectedReadTerminalRecord | ConnectedWriteTerminalRecord | ConnectedAmbiguousTerminalRecord
)


@dataclass(frozen=True, slots=True, repr=False)
class ConnectedDurableReadResult:
    """A decrypted result proven to bind the exact settled read terminal."""

    terminal: ConnectedReadTerminalRecord
    observation: ConnectedReadObservation = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if type(self.terminal) is not ConnectedReadTerminalRecord or type(
            self.observation
        ) is not ConnectedReadObservation:
            raise ValueError("durable read result shape is invalid")
        if (
            self.observation.operation_id != self.terminal.operation_id
            or self.observation.provider is not self.terminal.provider
            or self.observation.resource is not self.terminal.resource
            or self.observation.observed_at != self.terminal.observed_at
            or (
                self.observation.resource_version is None
                and self.terminal.resource_version_sha256 is not None
            )
            or (
                self.observation.resource_version is not None
                and _hash(self.observation.resource_version)
                != self.terminal.resource_version_sha256
            )
        ):
            raise ValueError("durable read result binding is invalid")

    def __repr__(self) -> str:
        return "ConnectedDurableReadResult(content='<encrypted>')"


@dataclass(frozen=True, slots=True, repr=False)
class ConnectedActionClaim:
    claim_id: str
    status: ConnectedActionClaimStatus
    binding_sha256: str
    authority_sha256: str
    granted_actions_sha256: str
    fencing_token: int | None = None
    lease_expires_at: datetime | None = None
    execution_deadline: datetime | None = None
    access_started_at: datetime | None = None
    effect_started_at: datetime | None = None
    postobserve_started_at: datetime | None = None
    access_phase: ConnectedCredentialPhase | None = None
    access_use_nonce: str | None = None
    effect_use_nonce: str | None = None
    postobserve_use_nonce: str | None = None
    postobserve_expires_at: datetime | None = None
    terminal: LedgerTerminal | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        _uuid(self.claim_id, "claim_id")
        _sha(self.binding_sha256, "binding_sha256")
        _sha(self.authority_sha256, "authority_sha256")
        _sha(self.granted_actions_sha256, "granted_actions_sha256")
        active = self.status in {
            ConnectedActionClaimStatus.CLAIMED,
            ConnectedActionClaimStatus.ACCESS_GRANTED,
            ConnectedActionClaimStatus.EFFECT_POSSIBLE,
            ConnectedActionClaimStatus.BUSY,
        }
        if active:
            if (
                self.terminal is not None
                or self.lease_expires_at is None
                or self.execution_deadline is None
            ):
                raise ValueError("active claim shape is invalid")
            if self.status is ConnectedActionClaimStatus.CLAIMED:
                if type(self.fencing_token) is not int or self.fencing_token < 1:
                    raise ValueError("owned action requires a fencing token")
            elif self.status in {
                ConnectedActionClaimStatus.ACCESS_GRANTED,
                ConnectedActionClaimStatus.EFFECT_POSSIBLE,
            }:
                nonce = (
                    self.access_use_nonce
                    if self.status is ConnectedActionClaimStatus.ACCESS_GRANTED
                    else self.effect_use_nonce
                )
                disclosed = (self.fencing_token is not None, nonce is not None)
                if disclosed[0] != disclosed[1]:
                    raise ValueError("effect ownership disclosure is partial")
                if disclosed[0] and (type(self.fencing_token) is not int or self.fencing_token < 1):
                    raise ValueError("effect owner fence is invalid")
            elif self.fencing_token is not None:
                raise ValueError("busy response cannot disclose a fence")
            if self.status is ConnectedActionClaimStatus.EFFECT_POSSIBLE:
                if self.effect_started_at is None or self.access_started_at is not None:
                    raise ValueError("effect start time is invalid")
                _aware(self.effect_started_at, "effect_started_at")
                if self.effect_use_nonce is not None:
                    _uuid(self.effect_use_nonce, "effect_use_nonce")
                postobserve = (
                    self.postobserve_started_at,
                    self.postobserve_use_nonce,
                    self.postobserve_expires_at,
                )
                if any(value is None for value in postobserve) and any(
                    value is not None for value in postobserve
                ):
                    raise ValueError("post-observation disclosure is partial")
                if self.postobserve_started_at is not None:
                    started = _aware(self.postobserve_started_at, "postobserve_started_at")
                    expires = _aware(self.postobserve_expires_at, "postobserve_expires_at")
                    _uuid(self.postobserve_use_nonce or "", "postobserve_use_nonce")
                    if expires <= started:
                        raise ValueError("post-observation expiry is invalid")
            elif self.effect_use_nonce is not None or self.effect_started_at is not None:
                raise ValueError("only effect-possible state may bind a use nonce")
            elif (
                self.postobserve_started_at is not None
                or self.postobserve_use_nonce is not None
                or self.postobserve_expires_at is not None
            ):
                raise ValueError("only effect-possible state may bind post-observation")
            if self.status is ConnectedActionClaimStatus.ACCESS_GRANTED:
                if self.access_started_at is None:
                    raise ValueError("access start time is missing")
                _aware(self.access_started_at, "access_started_at")
                if self.access_use_nonce is not None:
                    _uuid(self.access_use_nonce, "access_use_nonce")
                if self.access_phase not in {
                    ConnectedCredentialPhase.READ,
                    ConnectedCredentialPhase.PREOBSERVE,
                }:
                    raise ValueError("access phase is invalid")
            elif self.access_phase is not None or self.access_started_at is not None:
                raise ValueError("only access-granted state may bind an access phase")
            if (
                self.status is not ConnectedActionClaimStatus.ACCESS_GRANTED
                and self.access_use_nonce is not None
            ):
                raise ValueError("only access-granted state may bind a use nonce")
            if _aware(self.lease_expires_at, "lease_expires_at") > _aware(
                self.execution_deadline, "execution_deadline"
            ):
                raise ValueError("lease exceeds deadline")
        elif (
            self.terminal is None
            or self.fencing_token is not None
            or self.lease_expires_at is not None
            or self.access_started_at is not None
            or self.effect_started_at is not None
            or self.postobserve_started_at is not None
            or self.access_phase is not None
            or self.access_use_nonce is not None
            or self.effect_use_nonce is not None
            or self.postobserve_use_nonce is not None
            or self.postobserve_expires_at is not None
        ):
            raise ValueError("replay claim shape is invalid")

    def __repr__(self) -> str:
        return f"ConnectedActionClaim(status={self.status.value!r}, binding='<redacted>')"


@dataclass(frozen=True, slots=True, repr=False)
class ConnectedActionRuntimeResult:
    operation_id: str
    outcome: ConnectedActionOutcome
    replayed: bool
    terminal: LedgerTerminal
    provider_result: ConnectedReadObservation | ProviderReceipt | AmbiguousProviderResult | None = (
        field(default=None, repr=False, compare=False)
    )

    def __repr__(self) -> str:
        return (
            f"ConnectedActionRuntimeResult(outcome={self.outcome.value!r}, "
            f"replayed={self.replayed!r}, provider_result='<redacted>')"
        )


class ConnectedAccountRegistry(Protocol):
    async def get_binding(
        self, *, owner_id: str, connection_id: str
    ) -> ConnectedAccountBinding | None: ...


class ConnectedCredentialBroker(Protocol):
    async def issue_child_lease(
        self,
        *,
        account: ConnectedAccountRef,
        authorization: ConnectedAuthorizationSnapshot,
        intent: ConnectedActionIntent,
        claim: ConnectedActionClaim,
        authority: ConnectedActionAuthorityRecord,
        phase: ConnectedCredentialPhase,
        use_nonce: str,
        hard_expires_at: datetime,
    ) -> ConnectedCredentialLease: ...


class ConnectedActionLedger(Protocol):
    """Durable authority ledger for read access and external write effects.

    ``begin_access`` is the read/pre-observation linearization point and must transactionally
    re-read live task and connection authority, then bind the claim fence,
    phase, one-use credential nonce/expiry, and execution deadline before returning
    ``ACCESS_GRANTED``.  Without that exact response no provider read or write
    pre-observation may run.
    ``begin_effect`` is the write linearization point.  Its implementation must,
    in one durable transaction, re-read the live task and connection authority,
    compare every revision/hash in ``record`` to those rows and the claimed
    authority, verify the claim/fence/deadline, and only then transition to
    ``EFFECT_POSSIBLE``.  A refused transition means no provider write is allowed.
    An ``EFFECT_POSSIBLE`` row is never reclaimable for blind execution.
    ``begin_postobserve`` may only add a read-only reconciliation lease to an
    existing ``EFFECT_POSSIBLE`` row.  It must never create or repeat an effect.
    ``recover_access`` may replace only an expired, access-only row and must
    atomically issue a new claim/fence/access nonce under fresh live authority.
    Content-free readback must surface such a row as ``ACCESS_GRANTED`` (while
    withholding its nonce/fence from unrelated requests) so expiry recovery is
    possible without allowing a second provider call before expiry.
    """

    async def readback(
        self, record: ConnectedActionLookupRecord | ConnectedActionClaimRequest
    ) -> ConnectedActionClaim | None: ...

    async def claim(
        self,
        record: ConnectedActionClaimRequest,
        authority: ConnectedActionAuthorityRecord,
    ) -> ConnectedActionClaim: ...

    async def begin_access(
        self,
        record: ConnectedActionAccessRequest,
        claim: ConnectedActionClaim,
    ) -> ConnectedActionClaim: ...

    async def begin_effect(
        self,
        record: ConnectedActionEffectRequest,
        claim: ConnectedActionClaim,
    ) -> ConnectedActionClaim: ...

    async def begin_postobserve(
        self,
        record: ConnectedActionPostobserveRequest,
        claim: ConnectedActionClaim,
    ) -> ConnectedActionClaim: ...

    async def recover_access(
        self,
        record: ConnectedActionAccessRecoveryRequest,
        authority: ConnectedActionAuthorityRecord,
    ) -> ConnectedActionClaim: ...

    async def settle(
        self, claim: ConnectedActionClaim, terminal: LedgerTerminal
    ) -> ConnectedActionClaim: ...


class ConnectedReadResultDurability(Protocol):
    """Encrypted read-result settlement and exact terminal replay boundary."""

    async def settle(
        self,
        *,
        invocation: ConnectedActionInvocation,
        claim: ConnectedActionClaim,
        terminal: ConnectedReadTerminalRecord,
        observation: ConnectedReadObservation,
        deadline: datetime,
    ) -> ConnectedDurableReadResult: ...

    async def replay(
        self,
        *,
        lookup: ConnectedActionLookupRecord,
        terminal: ConnectedReadTerminalRecord,
        deadline: datetime,
    ) -> ConnectedDurableReadResult: ...

    async def recover(
        self,
        *,
        lookup: ConnectedActionLookupRecord,
        claim: ConnectedActionClaim,
        deadline: datetime,
    ) -> ConnectedDurableReadResult | None: ...


class ConnectedReadActionDispatcher(Protocol):
    """Read transport that atomically consumes the access lease just-in-time."""

    action: ConnectorActionKind

    async def execute_read(
        self,
        *,
        account: ConnectedAccountRef,
        credential: ConnectedCredentialLease,
        request: ProviderRequest,
        operation_id: str,
    ) -> ConnectedReadObservation: ...


class ConnectedWriteActionDispatcher(Protocol):
    """Action-bound transport boundary.

    Every method must atomically consume its phase-bound lease's one-use nonce
    and then pass only ``credential.credential`` to the typed provider adapter.
    Pre-observation, effect, and post-observation leases are distinct and may
    never be accepted for another phase or reused.
    """

    action: ConnectorActionKind

    async def observe_resource_version(
        self,
        *,
        account: ConnectedAccountRef,
        credential: ConnectedCredentialLease,
        request: ProviderRequest,
        operation_id: str,
    ) -> str | None: ...

    async def execute_write(
        self,
        *,
        account: ConnectedAccountRef,
        credential: ConnectedCredentialLease,
        request: ProviderRequest,
        operation_id: str,
        idempotency_key: str,
    ) -> ProviderReceipt | AmbiguousProviderResult: ...


class ConnectedProviderResolver(Protocol):
    def resolve_read(
        self,
        *,
        provider: ConnectorProvider,
        resource: ConnectorResource,
        action: ConnectorActionKind,
    ) -> ConnectedReadActionDispatcher: ...

    def resolve_write(
        self,
        *,
        provider: ConnectorProvider,
        resource: ConnectorResource,
        action: ConnectorActionKind,
    ) -> ConnectedWriteActionDispatcher: ...


@dataclass(slots=True)
class _ConnectionLockEntry:
    lock: asyncio.Lock
    references: int = 0


class _TaskQuarantine:
    """Bounded registry for dependency tasks that resist cancellation."""

    def __init__(self, maximum: int) -> None:
        if type(maximum) is not int or maximum < 1:
            raise ValueError("quarantine maximum is invalid")
        self._maximum = maximum
        self._tasks: set[asyncio.Task[object]] = set()

    @property
    def size(self) -> int:
        return len(self._tasks)

    async def _run(self, awaitable: Awaitable[_T]) -> _T:
        return await awaitable

    def spawn(self, awaitable: Awaitable[_T]) -> asyncio.Task[_T]:
        if len(self._tasks) >= self._maximum:
            if asyncio.iscoroutine(awaitable):
                awaitable.close()
            raise ConnectedAppRuntimeError(
                "CONNECTED_DEPENDENCY_QUARANTINE_CAPACITY", retryable=True
            )
        task = asyncio.create_task(self._run(awaitable))
        self._tasks.add(task)  # type: ignore[arg-type]
        task.add_done_callback(self._finished)
        return task

    def _finished(self, task: asyncio.Task[object]) -> None:
        self._tasks.discard(task)
        self._finished_untracked(task)

    @staticmethod
    def _finished_untracked(task: asyncio.Future[object]) -> None:
        try:
            task.result()
        except BaseException:
            pass


class _ConnectionLockPool:
    """Bounded, refcounted per-connection serialization with prompt cleanup."""

    def __init__(self, maximum: int) -> None:
        if type(maximum) is not int or maximum < 1:
            raise ValueError("connection lock maximum is invalid")
        self._maximum = maximum
        self._entries: dict[tuple[str, str], _ConnectionLockEntry] = {}
        self._guard = asyncio.Lock()

    @property
    def size(self) -> int:
        return len(self._entries)

    async def _drop_unused(
        self,
        key: tuple[str, str],
        entry: _ConnectionLockEntry,
    ) -> None:
        async with self._guard:
            if entry.references == 0 and not entry.lock.locked():
                self._entries.pop(key, None)

    def _late_acquire_finished(
        self,
        key: tuple[str, str],
        entry: _ConnectionLockEntry,
        task: asyncio.Task[bool],
    ) -> None:
        try:
            acquired = task.result()
        except BaseException:
            acquired = False
        if acquired and entry.lock.locked():
            entry.lock.release()
        cleanup = asyncio.create_task(self._drop_unused(key, entry))
        cleanup.add_done_callback(_TaskQuarantine._finished_untracked)

    async def _cancel_or_reconcile_acquire(
        self,
        key: tuple[str, str],
        entry: _ConnectionLockEntry,
        task: asyncio.Task[bool],
    ) -> bool:
        """Cancel an acquire and release a raced handoff before returning when possible.

        Returns true only when a late callback owns cleanup beyond the bounded
        reconciliation window.
        """

        if not task.done():
            task.cancel()
        try:
            done, _ = await asyncio.wait({task}, timeout=0.05)
        except asyncio.CancelledError:
            done = set()
        if done or task.done():
            try:
                acquired = task.result()
            except BaseException:
                acquired = False
            if acquired and entry.lock.locked():
                entry.lock.release()
            return False
        task.add_done_callback(lambda finished: self._late_acquire_finished(key, entry, finished))
        return True

    @asynccontextmanager
    async def hold(self, key: tuple[str, str], timeout: float) -> AsyncIterator[None]:
        if timeout <= 0:
            raise ConnectedAppRuntimeError("CONNECTED_CONNECTION_LOCK_TIMEOUT", retryable=True)
        async with self._guard:
            entry = self._entries.get(key)
            if entry is None:
                if len(self._entries) >= self._maximum:
                    raise ConnectedAppRuntimeError(
                        "CONNECTED_CONNECTION_LOCK_CAPACITY", retryable=True
                    )
                entry = _ConnectionLockEntry(asyncio.Lock())
                self._entries[key] = entry
            entry.references += 1
        acquired = False
        acquire_task: asyncio.Task[bool] | None = None
        try:
            acquire_task = asyncio.create_task(entry.lock.acquire())
            done, _ = await asyncio.wait({acquire_task}, timeout=timeout)
            if not done:
                await self._cancel_or_reconcile_acquire(key, entry, acquire_task)
                raise ConnectedAppRuntimeError("CONNECTED_CONNECTION_LOCK_TIMEOUT", retryable=True)
            acquire_task.result()
            acquired = True
            yield
        except asyncio.CancelledError:
            if acquire_task is not None and not acquire_task.done():
                await self._cancel_or_reconcile_acquire(key, entry, acquire_task)
            elif acquire_task is not None and not acquired:
                try:
                    acquired = acquire_task.result()
                except BaseException:
                    acquired = False
            raise
        finally:
            if acquired:
                entry.lock.release()
            async with self._guard:
                entry.references -= 1
                if (
                    entry.references == 0
                    and not entry.lock.locked()
                    and (acquire_task is None or acquire_task.done())
                ):
                    self._entries.pop(key, None)


class ConnectedAppRuntime:
    """Run lookup -> policy -> claim -> (write effect boundary) -> reconcile."""

    def __init__(
        self,
        *,
        accounts: ConnectedAccountRegistry,
        credentials: ConnectedCredentialBroker,
        policy: ConnectedActionPolicy,
        ledger: ConnectedActionLedger,
        providers: ConnectedProviderResolver,
        read_results: ConnectedReadResultDurability | None = None,
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        claim_lease: timedelta = timedelta(seconds=30),
        execution_window: timedelta = timedelta(minutes=2),
        contention_wait_seconds: float = 0.25,
        max_connection_locks: int = 1024,
        max_quarantined_tasks: int = 128,
    ) -> None:
        if claim_lease <= timedelta(0) or execution_window <= timedelta(0):
            raise ValueError("claim bounds must be positive")
        if claim_lease > execution_window:
            raise ValueError("claim lease cannot exceed execution window")
        if not 0 <= contention_wait_seconds <= 5:
            raise ValueError("contention wait is invalid")
        self._accounts = accounts
        self._credentials = credentials
        self._policy = policy
        self._ledger = ledger
        self._providers = providers
        if read_results is not None and any(
            not callable(getattr(read_results, method, None))
            for method in ("settle", "replay", "recover")
        ):
            raise TypeError("read_results is invalid")
        self._read_results = read_results
        self._now = now
        self._claim_lease = claim_lease
        self._execution_window = execution_window
        self._contention_wait_seconds = contention_wait_seconds
        self._connection_locks = _ConnectionLockPool(max_connection_locks)
        self._quarantine = _TaskQuarantine(max_quarantined_tasks)

    async def run(
        self,
        invocation: ConnectedActionInvocation,
        *,
        grant: ConnectedTaskGrant,
        approval: ConnectedApprovalEvidence | None = None,
        task_state_revision: int,
    ) -> ConnectedActionRuntimeResult:
        if type(task_state_revision) is not int or task_state_revision < 1:
            raise ConnectedAppRuntimeError("CONNECTED_TASK_STATE_REVISION_INVALID")
        intent = invocation.intent
        lock_timeout = min(
            self._execution_window.total_seconds(),
            self._contention_wait_seconds if self._contention_wait_seconds > 0 else 0.001,
        )
        async with self._connection_locks.hold(
            (intent.owner_id, intent.connection_id), lock_timeout
        ):
            return await self._run_locked(
                invocation,
                grant=grant,
                approval=approval,
                task_state_revision=task_state_revision,
            )

    async def _run_locked(
        self,
        invocation: ConnectedActionInvocation,
        *,
        grant: ConnectedTaskGrant,
        approval: ConnectedApprovalEvidence | None,
        task_state_revision: int,
    ) -> ConnectedActionRuntimeResult:
        intent = invocation.intent
        decision_time = _aware(self._now(), "now")
        provisional_deadline = decision_time + self._execution_window
        first = await self._await_dependency(
            self._dependency_awaitable(
                lambda: self._accounts.get_binding(
                    owner_id=intent.owner_id,
                    connection_id=intent.connection_id,
                ),
                code="CONNECTED_ACCOUNT_REGISTRY_FAILED",
                retryable=True,
            ),
            deadline=provisional_deadline,
            code="CONNECTED_ACCOUNT_REGISTRY_FAILED",
            retryable=True,
        )
        if first is None:
            raise ConnectedAppRuntimeError("CONNECTED_ACCOUNT_NOT_FOUND")
        if type(first) is not ConnectedAccountBinding:
            raise ConnectedAppRuntimeError("CONNECTED_ACCOUNT_BINDING_INVALID")
        self._validate_account(first.account, intent)
        lookup = self._lookup(invocation)

        # Exact settled replay is available after approval expiry, but only
        # after the owner/account binding is re-established.
        recoverable_access: ConnectedActionClaim | None = None
        prior = await self._readback(lookup, provisional_deadline)
        if prior is not None:
            if self._expired_access_recoverable(prior, lookup, decision_time):
                if (
                    self._read_results is not None
                    and prior.access_phase is ConnectedCredentialPhase.READ
                ):
                    recovered = await self._recover_durable_read(
                        lookup,
                        prior,
                        provisional_deadline,
                    )
                    if recovered is not None:
                        return self._result(
                            recovered.terminal,
                            replayed=True,
                            provider_result=recovered.observation,
                        )
                recoverable_access = prior
            else:
                replay = await self._replay_or_wait(prior, lookup, provisional_deadline)
                if replay is not None:
                    return replay

        if intent.action not in _REQUESTS:
            raise ConnectedAppRuntimeError("CONNECTED_ACTION_UNSUPPORTED")
        self._validate_authorization(first.authorization, intent, decision_time)
        decision = self._policy.decide(intent, grant=grant, approval=approval, now=decision_time)
        if decision.action_id != intent.action_id:
            raise ConnectedAppRuntimeError("CONNECTED_POLICY_RESULT_INVALID")
        if decision.kind is ConnectorDecisionKind.REQUIRE_APPROVAL:
            raise ConnectedAppRuntimeError("CONNECTED_ACTION_APPROVAL_REQUIRED")
        if decision.kind is not ConnectorDecisionKind.ALLOW:
            raise ConnectedAppRuntimeError("CONNECTED_ACTION_DENIED")
        if decision.mutates_external_state != (intent.action in _OUTCOMES):
            raise ConnectedAppRuntimeError("CONNECTED_ACTION_DISPATCH_MISMATCH")

        authority = self._authority(
            grant=grant,
            approval=approval,
            authorization=first.authorization,
            task_state_revision=task_state_revision,
            decided_at=decision_time,
        )
        deadline_options = [
            decision_time + self._execution_window,
            _aware(grant.expires_at, "grant.expires_at"),
            _aware(first.authorization.expires_at, "authorization.expires_at"),
        ]
        if approval is not None:
            deadline_options.append(_aware(approval.expires_at, "approval.expires_at"))
        deadline = min(deadline_options)
        if deadline <= decision_time:
            raise ConnectedAppRuntimeError("CONNECTED_ACTION_AUTHORITY_EXPIRED")
        request = ConnectedActionClaimRequest(
            lookup=lookup,
            claim_request_id=str(uuid4()),
            authority_sha256=authority.authority_sha256,
            granted_actions_sha256=authority.granted_actions_sha256,
            mutates_external_state=decision.mutates_external_state,
            requested_at=decision_time,
            execution_deadline=deadline,
        )
        prepared_access: (
            tuple[
                ConnectedActionAccessRecoveryRequest,
                ConnectedActionClaim,
            ]
            | None
        ) = None
        if recoverable_access is not None:
            phase = (
                ConnectedCredentialPhase.PREOBSERVE
                if decision.mutates_external_state
                else ConnectedCredentialPhase.READ
            )
            access_nonce = self._new_phase_nonce()
            access_expiry = self._fresh_access_expiry(
                decision_time,
                first.authorization,
                deadline,
            )
            recovery = ConnectedActionAccessRecoveryRequest(
                lookup=lookup,
                expired_claim_id=recoverable_access.claim_id,
                claim_request_id=request.claim_request_id,
                authority_sha256=authority.authority_sha256,
                task_state_revision=authority.task_state_revision,
                authorization_revision=first.authorization.revision,
                authorization_snapshot_sha256=first.authorization.snapshot_sha256,
                granted_actions_sha256=first.authorization.granted_actions_sha256,
                granted_scopes_sha256=first.authorization.granted_scopes_sha256,
                phase=phase,
                credential_use_nonce=access_nonce,
                credential_expires_at=access_expiry,
                requested_at=decision_time,
                execution_deadline=deadline,
            )
            claim = await self._recover_access_with_readback(
                recovery,
                recoverable_access,
                authority,
                request,
            )
            self._validate_recovered_access_claim(
                claim,
                recovery,
                recoverable_access,
            )
            prepared_access = (recovery, claim)
        else:
            claim = await self._claim_with_readback(request, authority, deadline)
            if claim.status is not ConnectedActionClaimStatus.CLAIMED:
                replay = await self._replay_or_wait(claim, lookup, deadline)
                if replay is not None:
                    return replay
                if claim.status is ConnectedActionClaimStatus.EFFECT_POSSIBLE:
                    raise ConnectedAppRuntimeError(
                        "CONNECTED_ACTION_EFFECT_POSSIBLE", retryable=False
                    )
                raise ConnectedAppRuntimeError("CONNECTED_ACTION_ALREADY_CLAIMED", retryable=True)
            self._validate_fresh_claim(claim, request)

        if decision.mutates_external_state:
            try:
                dispatcher = self._providers.resolve_write(
                    provider=intent.provider,
                    resource=intent.resource,
                    action=intent.action,
                )
                dispatcher_matches = dispatcher.action is intent.action
            except Exception:
                raise ConnectedAppRuntimeError("CONNECTED_ACTION_DISPATCH_FAILED") from None
            if not dispatcher_matches:
                raise ConnectedAppRuntimeError("CONNECTED_ACTION_DISPATCH_MISMATCH")
            return await self._execute_write(
                invocation,
                dispatcher=dispatcher,
                claim=claim,
                claim_request=request,
                authority=authority,
                grant=grant,
                approval=approval,
                prepared_access=prepared_access,
            )
        try:
            dispatcher = self._providers.resolve_read(
                provider=intent.provider,
                resource=intent.resource,
                action=intent.action,
            )
            dispatcher_matches = dispatcher.action is intent.action
        except Exception:
            raise ConnectedAppRuntimeError("CONNECTED_ACTION_DISPATCH_FAILED") from None
        if not dispatcher_matches:
            raise ConnectedAppRuntimeError("CONNECTED_ACTION_DISPATCH_MISMATCH")
        return await self._execute_read(
            invocation,
            dispatcher=dispatcher,
            claim=claim,
            claim_request=request,
            authority=authority,
            grant=grant,
            approval=approval,
            prepared_access=prepared_access,
        )

    async def _execute_read(
        self,
        invocation: ConnectedActionInvocation,
        *,
        dispatcher: ConnectedReadActionDispatcher,
        claim: ConnectedActionClaim,
        claim_request: ConnectedActionClaimRequest,
        authority: ConnectedActionAuthorityRecord,
        grant: ConnectedTaskGrant,
        approval: ConnectedApprovalEvidence | None,
        prepared_access: tuple[
            ConnectedActionAccessRecoveryRequest,
            ConnectedActionClaim,
        ]
        | None,
    ) -> ConnectedActionRuntimeResult:
        intent = invocation.intent
        current = await self._live_binding(
            intent,
            authority=authority,
            deadline=claim_request.execution_deadline,
        )
        access_time = _aware(self._now(), "now")
        fresh_decision = self._policy.decide(
            intent, grant=grant, approval=approval, now=access_time
        )
        if (
            fresh_decision.kind is not ConnectorDecisionKind.ALLOW
            or fresh_decision.mutates_external_state
        ):
            raise ConnectedAppRuntimeError("CONNECTED_ACTION_AUTHORITY_CHANGED")
        if prepared_access is None:
            self._validate_claim_live(claim)
            access_nonce = self._new_phase_nonce()
            hard_expiry = self._phase_expiry(
                claim,
                current.authorization,
                claim_request.execution_deadline,
            )
            access_request: ConnectedActionAccessRequest | ConnectedActionAccessRecoveryRequest = (
                ConnectedActionAccessRequest(
                    lookup=claim_request.lookup,
                    claim_request_id=claim_request.claim_request_id,
                    claim_id=claim.claim_id,
                    fencing_token=claim.fencing_token or 0,
                    authority_sha256=authority.authority_sha256,
                    task_state_revision=authority.task_state_revision,
                    authorization_revision=current.authorization.revision,
                    authorization_snapshot_sha256=current.authorization.snapshot_sha256,
                    granted_actions_sha256=current.authorization.granted_actions_sha256,
                    granted_scopes_sha256=current.authorization.granted_scopes_sha256,
                    phase=ConnectedCredentialPhase.READ,
                    credential_use_nonce=access_nonce,
                    credential_expires_at=hard_expiry,
                    requested_at=access_time,
                    execution_deadline=claim_request.execution_deadline,
                )
            )
            access_claim = await self._begin_access_with_readback(
                access_request, claim, claim_request
            )
            self._validate_access_claim(access_claim, access_request)
        else:
            access_request, access_claim = prepared_access
            access_nonce = access_request.credential_use_nonce
            hard_expiry = access_request.credential_expires_at
            self._validate_recovered_access_claim(
                access_claim,
                access_request,
                None,
            )
        credential = await self._issue_child_lease(
            account=current.account,
            authorization=current.authorization,
            intent=intent,
            claim=access_claim,
            authority=authority,
            phase=ConnectedCredentialPhase.READ,
            use_nonce=access_nonce,
            hard_expiry=hard_expiry,
            deadline=claim_request.execution_deadline,
        )
        try:
            observation = await self._await_dependency(
                self._provider_awaitable(
                    lambda: dispatcher.execute_read(
                        account=current.account,
                        credential=credential,
                        request=invocation.request,
                        operation_id=intent.action_id,
                    ),
                    code="CONNECTED_PROVIDER_FAILURE",
                    retryable=True,
                ),
                deadline=claim_request.execution_deadline,
                code="CONNECTED_PROVIDER_FAILURE",
                retryable=True,
            )
        except asyncio.CancelledError:
            raise
        except ConnectedAppRuntimeError:
            if self._read_results is not None:
                # The dispatcher consumed the durable one-use read lease before
                # entering the adapter.  A missing response is therefore an
                # exact-result unknown, never authority for a blind second read.
                raise ConnectedAppRuntimeError(
                    "CONNECTED_READ_RESULT_EFFECT_UNKNOWN", retryable=False
                ) from None
            raise
        if type(observation) is not ConnectedReadObservation:
            raise ConnectedAppRuntimeError("CONNECTED_PROVIDER_RESULT_INVALID")
        self._validate_provider_identity(observation, intent)
        self._validate_provider_observed_at(
            observation.observed_at,
            earliest=access_claim.access_started_at or access_request.requested_at,
            latest=min(
                claim_request.execution_deadline,
                _aware(self._now(), "now"),
            ),
        )
        terminal = ConnectedReadTerminalRecord(
            operation_id=intent.action_id,
            provider=intent.provider,
            resource=intent.resource,
            action=intent.action,
            binding_sha256=invocation.binding_sha256,
            authority_sha256=access_claim.authority_sha256,
            idempotency_key_hash=_hash(intent.idempotency_key),
            observed_at=observation.observed_at,
            resource_version_sha256=(
                _hash(observation.resource_version)
                if observation.resource_version is not None
                else None
            ),
        )
        if self._read_results is None:
            settled = await self._settle_read(access_claim, claim_request, terminal)
            return self._result(settled, replayed=False, provider_result=observation)
        durable = await self._settle_durable_read(
            invocation=invocation,
            claim=access_claim,
            terminal=terminal,
            observation=observation,
            deadline=claim_request.execution_deadline,
        )
        return self._result(
            durable.terminal,
            replayed=False,
            provider_result=durable.observation,
        )

    async def _execute_write(
        self,
        invocation: ConnectedActionInvocation,
        *,
        dispatcher: ConnectedWriteActionDispatcher,
        claim: ConnectedActionClaim,
        claim_request: ConnectedActionClaimRequest,
        authority: ConnectedActionAuthorityRecord,
        grant: ConnectedTaskGrant,
        approval: ConnectedApprovalEvidence | None,
        prepared_access: tuple[
            ConnectedActionAccessRecoveryRequest,
            ConnectedActionClaim,
        ]
        | None,
    ) -> ConnectedActionRuntimeResult:
        intent = invocation.intent
        preobserve_current = await self._live_binding(
            intent,
            authority=authority,
            deadline=claim_request.execution_deadline,
        )
        preobserve_time = _aware(self._now(), "now")
        preobserve_decision = self._policy.decide(
            intent, grant=grant, approval=approval, now=preobserve_time
        )
        if (
            preobserve_decision.kind is not ConnectorDecisionKind.ALLOW
            or not preobserve_decision.mutates_external_state
        ):
            raise ConnectedAppRuntimeError("CONNECTED_ACTION_AUTHORITY_CHANGED")
        if prepared_access is None:
            self._validate_claim_live(claim)
            preobserve_nonce = self._new_phase_nonce()
            preobserve_expiry = self._phase_expiry(
                claim,
                preobserve_current.authorization,
                claim_request.execution_deadline,
            )
            preobserve_request: (
                ConnectedActionAccessRequest | ConnectedActionAccessRecoveryRequest
            ) = ConnectedActionAccessRequest(
                lookup=claim_request.lookup,
                claim_request_id=claim_request.claim_request_id,
                claim_id=claim.claim_id,
                fencing_token=claim.fencing_token or 0,
                authority_sha256=authority.authority_sha256,
                task_state_revision=authority.task_state_revision,
                authorization_revision=preobserve_current.authorization.revision,
                authorization_snapshot_sha256=preobserve_current.authorization.snapshot_sha256,
                granted_actions_sha256=(preobserve_current.authorization.granted_actions_sha256),
                granted_scopes_sha256=preobserve_current.authorization.granted_scopes_sha256,
                phase=ConnectedCredentialPhase.PREOBSERVE,
                credential_use_nonce=preobserve_nonce,
                credential_expires_at=preobserve_expiry,
                requested_at=preobserve_time,
                execution_deadline=claim_request.execution_deadline,
            )
            preobserve_claim = await self._begin_access_with_readback(
                preobserve_request, claim, claim_request
            )
            self._validate_access_claim(preobserve_claim, preobserve_request)
        else:
            preobserve_request, preobserve_claim = prepared_access
            preobserve_nonce = preobserve_request.credential_use_nonce
            preobserve_expiry = preobserve_request.credential_expires_at
            self._validate_recovered_access_claim(
                preobserve_claim,
                preobserve_request,
                None,
            )
        preobserve_credential = await self._issue_child_lease(
            account=preobserve_current.account,
            authorization=preobserve_current.authorization,
            intent=intent,
            claim=preobserve_claim,
            authority=authority,
            phase=ConnectedCredentialPhase.PREOBSERVE,
            use_nonce=preobserve_nonce,
            hard_expiry=preobserve_expiry,
            deadline=claim_request.execution_deadline,
        )
        before = await self._await_dependency(
            self._provider_awaitable(
                lambda: dispatcher.observe_resource_version(
                    account=preobserve_current.account,
                    credential=preobserve_credential,
                    request=invocation.request,
                    operation_id=intent.action_id,
                ),
                code="CONNECTED_PROVIDER_PREOBSERVE_FAILED",
                retryable=True,
            ),
            deadline=claim_request.execution_deadline,
            code="CONNECTED_PROVIDER_PREOBSERVE_FAILED",
            retryable=True,
        )
        if (
            invocation.expected_resource_version is not None
            and before != invocation.expected_resource_version
        ):
            raise ConnectedAppRuntimeError("CONNECTED_RESOURCE_VERSION_STALE")
        if type(preobserve_request) is ConnectedActionAccessRequest:
            self._validate_access_claim(preobserve_claim, preobserve_request)
        else:
            self._validate_recovered_access_claim(
                preobserve_claim,
                preobserve_request,
                None,
            )

        current = await self._live_binding(
            intent,
            authority=authority,
            deadline=claim_request.execution_deadline,
        )
        effect_time = _aware(self._now(), "now")
        fresh_decision = self._policy.decide(
            intent, grant=grant, approval=approval, now=effect_time
        )
        if (
            fresh_decision.kind is not ConnectorDecisionKind.ALLOW
            or not fresh_decision.mutates_external_state
        ):
            raise ConnectedAppRuntimeError("CONNECTED_ACTION_AUTHORITY_CHANGED")
        effect_nonce = self._new_phase_nonce(preobserve_nonce)
        effect_expiry = self._phase_expiry(
            preobserve_claim,
            current.authorization,
            claim_request.execution_deadline,
        )
        effect_request = ConnectedActionEffectRequest(
            lookup=claim_request.lookup,
            claim_request_id=claim_request.claim_request_id,
            claim_id=claim.claim_id,
            approval_id=authority.approval_id or "",
            fencing_token=claim.fencing_token or 0,
            authority_sha256=authority.authority_sha256,
            task_state_revision=authority.task_state_revision,
            authorization_revision=current.authorization.revision,
            authorization_snapshot_sha256=current.authorization.snapshot_sha256,
            granted_actions_sha256=current.authorization.granted_actions_sha256,
            granted_scopes_sha256=current.authorization.granted_scopes_sha256,
            approval_binding_sha256=approval.approval_binding_sha256,
            credential_use_nonce=effect_nonce,
            credential_expires_at=effect_expiry,
            requested_at=effect_time,
            execution_deadline=claim_request.execution_deadline,
        )
        effect_claim = await self._begin_effect_with_readback(
            effect_request, preobserve_claim, claim_request
        )
        self._validate_effect_claim(effect_claim, effect_request)

        try:
            effect_credential = await self._issue_child_lease(
                account=current.account,
                authorization=current.authorization,
                intent=intent,
                claim=effect_claim,
                authority=authority,
                phase=ConnectedCredentialPhase.EFFECT,
                use_nonce=effect_nonce,
                hard_expiry=effect_expiry,
                deadline=claim_request.execution_deadline,
            )
            provider_result = await self._await_dependency(
                self._provider_awaitable(
                    lambda: dispatcher.execute_write(
                        account=current.account,
                        credential=effect_credential,
                        request=invocation.request,
                        operation_id=intent.action_id,
                        idempotency_key=intent.idempotency_key,
                    ),
                    code="CONNECTED_PROVIDER_EFFECT_UNKNOWN",
                    retryable=False,
                ),
                deadline=claim_request.execution_deadline,
                code="CONNECTED_PROVIDER_EFFECT_UNKNOWN",
                retryable=False,
            )
        except asyncio.CancelledError:
            await self._shield_post_effect_cancellation(
                effect_claim,
                claim_request,
                self._ambiguous_terminal(intent, invocation, effect_claim),
            )
            raise
        except ConnectedAppRuntimeError:
            terminal = self._ambiguous_terminal(intent, invocation, effect_claim)
            settled = await self._settle_post_effect(effect_claim, claim_request, terminal)
            return self._result(
                settled,
                replayed=False,
                provider_result=self._ambiguous_provider(intent),
            )

        if type(provider_result) is AmbiguousProviderResult:
            try:
                self._validate_ambiguous_result(
                    provider_result,
                    intent,
                    earliest=effect_claim.effect_started_at or effect_request.requested_at,
                    latest=claim_request.execution_deadline,
                )
            except ConnectedAppRuntimeError:
                provider_result = self._ambiguous_provider(intent)
            terminal = self._ambiguous_terminal(intent, invocation, effect_claim)
            settled = await self._settle_post_effect(effect_claim, claim_request, terminal)
            return self._result(settled, replayed=False, provider_result=provider_result)

        if type(provider_result) is not ProviderReceipt:
            terminal = self._ambiguous_terminal(intent, invocation, effect_claim)
            settled = await self._settle_post_effect(effect_claim, claim_request, terminal)
            return self._result(settled, replayed=False, provider_result=None)
        try:
            self._validate_receipt(
                provider_result,
                intent,
                earliest=effect_claim.effect_started_at or effect_request.requested_at,
                latest=claim_request.execution_deadline,
            )
        except ConnectedAppRuntimeError:
            terminal = self._ambiguous_terminal(intent, invocation, effect_claim)
            settled = await self._settle_post_effect(effect_claim, claim_request, terminal)
            return self._result(settled, replayed=False, provider_result=None)

        receipt_terminal = ConnectedWriteTerminalRecord(
            operation_id=intent.action_id,
            provider=intent.provider,
            resource=intent.resource,
            action=intent.action,
            binding_sha256=invocation.binding_sha256,
            authority_sha256=effect_claim.authority_sha256,
            idempotency_key_hash=_hash(intent.idempotency_key),
            observed_at=provider_result.observed_at,
            receipt_outcome=provider_result.outcome,
            provider_request_id_hash=provider_result.provider_request_id_hash,
            resource_id_hash=provider_result.resource_id_hash,
            resource_version_sha256=_hash(provider_result.resource_version),
        )
        # Create/send/reply requests do not contain the newly created provider ID, so
        # blind post-observation through the original request cannot identify
        # the effect.  Their typed provider adapters return ProviderReceipt only
        # after authoritative provider-side reconciliation; that receipt is the
        # success proof and no second write is attempted.
        if intent.action in _AUTHORITATIVE_RECEIPT_ACTIONS:
            settled = await self._settle_post_effect(
                effect_claim,
                claim_request,
                receipt_terminal,
            )
            return self._result(
                settled,
                replayed=False,
                provider_result=provider_result,
            )

        settlement_claim = effect_claim
        try:
            loop = asyncio.get_running_loop()
            reconciliation_end = loop.time() + min(
                5.0,
                self._remaining_seconds(claim_request.execution_deadline),
            )
            postobserve_current = await self._live_binding(
                intent,
                authority=authority,
                deadline=claim_request.execution_deadline,
            )
            postobserve_time = _aware(self._now(), "now")
            postobserve_nonce = self._new_phase_nonce(
                preobserve_nonce,
                effect_nonce,
            )
            postobserve_expiry = self._phase_expiry(
                effect_claim,
                postobserve_current.authorization,
                claim_request.execution_deadline,
                max_seconds=5.0,
            )
            postobserve_request = ConnectedActionPostobserveRequest(
                lookup=claim_request.lookup,
                claim_request_id=claim_request.claim_request_id,
                claim_id=effect_claim.claim_id,
                fencing_token=effect_claim.fencing_token or 0,
                authority_sha256=authority.authority_sha256,
                task_state_revision=authority.task_state_revision,
                authorization_revision=postobserve_current.authorization.revision,
                authorization_snapshot_sha256=(postobserve_current.authorization.snapshot_sha256),
                granted_actions_sha256=(postobserve_current.authorization.granted_actions_sha256),
                granted_scopes_sha256=(postobserve_current.authorization.granted_scopes_sha256),
                effect_use_nonce=effect_nonce,
                credential_use_nonce=postobserve_nonce,
                credential_expires_at=postobserve_expiry,
                requested_at=postobserve_time,
                execution_deadline=claim_request.execution_deadline,
            )
            postobserve_claim = await self._begin_postobserve_with_readback(
                postobserve_request,
                effect_claim,
                claim_request,
            )
            self._validate_postobserve_claim(
                postobserve_claim,
                postobserve_request,
            )
            settlement_claim = postobserve_claim
            postobserve_credential = await self._issue_child_lease(
                account=postobserve_current.account,
                authorization=postobserve_current.authorization,
                intent=intent,
                claim=postobserve_claim,
                authority=authority,
                phase=ConnectedCredentialPhase.POSTOBSERVE,
                use_nonce=postobserve_nonce,
                hard_expiry=postobserve_expiry,
                deadline=claim_request.execution_deadline,
                timeout_cap=self._monotonic_remaining(reconciliation_end),
            )
            after = await self._await_dependency(
                self._provider_awaitable(
                    lambda: dispatcher.observe_resource_version(
                        account=postobserve_current.account,
                        credential=postobserve_credential,
                        request=invocation.request,
                        operation_id=intent.action_id,
                    ),
                    code="CONNECTED_PROVIDER_POSTOBSERVE_FAILED",
                    retryable=False,
                ),
                deadline=claim_request.execution_deadline,
                code="CONNECTED_PROVIDER_POSTOBSERVE_FAILED",
                retryable=False,
                timeout_cap=self._monotonic_remaining(reconciliation_end),
            )
        except asyncio.CancelledError:
            await self._shield_post_effect_cancellation(
                settlement_claim,
                claim_request,
                self._ambiguous_terminal(intent, invocation, settlement_claim),
            )
            raise
        except ConnectedAppRuntimeError:
            terminal = self._ambiguous_terminal(intent, invocation, settlement_claim)
            settled = await self._settle_post_effect(
                settlement_claim,
                claim_request,
                terminal,
            )
            return self._result(settled, replayed=False, provider_result=None)
        if after != provider_result.resource_version or self._claim_expired(effect_claim):
            terminal = self._ambiguous_terminal(intent, invocation, effect_claim)
            settled = await self._settle_post_effect(
                settlement_claim,
                claim_request,
                terminal,
            )
            return self._result(settled, replayed=False, provider_result=None)

        settled = await self._settle_post_effect(
            settlement_claim,
            claim_request,
            receipt_terminal,
        )
        return self._result(settled, replayed=False, provider_result=provider_result)

    async def _claim_with_readback(
        self,
        request: ConnectedActionClaimRequest,
        authority: ConnectedActionAuthorityRecord,
        deadline: datetime,
    ) -> ConnectedActionClaim:
        try:
            claim = await self._await_dependency(
                self._dependency_awaitable(
                    lambda: self._ledger.claim(request, authority),
                    code="CONNECTED_LEDGER_CLAIM_UNCERTAIN",
                    retryable=True,
                ),
                deadline=deadline,
                code="CONNECTED_LEDGER_CLAIM_UNCERTAIN",
                retryable=True,
            )
        except asyncio.CancelledError:
            raise
        except ConnectedAppRuntimeError:
            claim = await self._readback(request, deadline)
            if claim is None:
                raise ConnectedAppRuntimeError(
                    "CONNECTED_LEDGER_CLAIM_UNCERTAIN", retryable=True
                ) from None
        if type(claim) is not ConnectedActionClaim:
            raise ConnectedAppRuntimeError("CONNECTED_LEDGER_CLAIM_INVALID")
        return claim

    async def _begin_effect_with_readback(
        self,
        effect: ConnectedActionEffectRequest,
        claim: ConnectedActionClaim,
        request: ConnectedActionClaimRequest,
    ) -> ConnectedActionClaim:
        try:
            response = await self._await_dependency(
                self._dependency_awaitable(
                    lambda: self._ledger.begin_effect(effect, claim),
                    code="CONNECTED_LEDGER_EFFECT_UNCERTAIN",
                    retryable=False,
                ),
                deadline=request.execution_deadline,
                code="CONNECTED_LEDGER_EFFECT_UNCERTAIN",
                retryable=False,
                trusted_codes=_LEDGER_AUTHORITY_CODES,
            )
        except asyncio.CancelledError:
            raise
        except ConnectedAppRuntimeError as error:
            if error.code != "CONNECTED_LEDGER_EFFECT_UNCERTAIN":
                raise
            response = await self._readback(request, request.execution_deadline)
            if (
                response is None
                or response.status is not ConnectedActionClaimStatus.EFFECT_POSSIBLE
            ):
                raise ConnectedAppRuntimeError(
                    "CONNECTED_LEDGER_EFFECT_UNCERTAIN", retryable=False
                ) from None
        if type(response) is not ConnectedActionClaim:
            raise ConnectedAppRuntimeError("CONNECTED_LEDGER_CLAIM_INVALID")
        return response

    async def _begin_access_with_readback(
        self,
        access: ConnectedActionAccessRequest,
        claim: ConnectedActionClaim,
        request: ConnectedActionClaimRequest,
    ) -> ConnectedActionClaim:
        try:
            response = await self._await_dependency(
                self._dependency_awaitable(
                    lambda: self._ledger.begin_access(access, claim),
                    code="CONNECTED_LEDGER_ACCESS_UNCERTAIN",
                    retryable=False,
                ),
                deadline=request.execution_deadline,
                code="CONNECTED_LEDGER_ACCESS_UNCERTAIN",
                retryable=False,
                trusted_codes=_LEDGER_AUTHORITY_CODES,
            )
        except asyncio.CancelledError:
            raise
        except ConnectedAppRuntimeError as error:
            if error.code != "CONNECTED_LEDGER_ACCESS_UNCERTAIN":
                raise
            response = await self._readback(request, request.execution_deadline)
            if response is None or response.status is not ConnectedActionClaimStatus.ACCESS_GRANTED:
                raise ConnectedAppRuntimeError(
                    "CONNECTED_LEDGER_ACCESS_UNCERTAIN", retryable=False
                ) from None
        if type(response) is not ConnectedActionClaim:
            raise ConnectedAppRuntimeError("CONNECTED_LEDGER_CLAIM_INVALID")
        return response

    async def _begin_postobserve_with_readback(
        self,
        postobserve: ConnectedActionPostobserveRequest,
        claim: ConnectedActionClaim,
        request: ConnectedActionClaimRequest,
    ) -> ConnectedActionClaim:
        try:
            response = await self._await_dependency(
                self._dependency_awaitable(
                    lambda: self._ledger.begin_postobserve(postobserve, claim),
                    code="CONNECTED_LEDGER_POSTOBSERVE_UNCERTAIN",
                    retryable=False,
                ),
                deadline=request.execution_deadline,
                code="CONNECTED_LEDGER_POSTOBSERVE_UNCERTAIN",
                retryable=False,
                trusted_codes=_LEDGER_AUTHORITY_CODES,
            )
        except asyncio.CancelledError:
            raise
        except ConnectedAppRuntimeError as error:
            if error.code != "CONNECTED_LEDGER_POSTOBSERVE_UNCERTAIN":
                raise
            response = await self._readback(request, request.execution_deadline)
            if (
                response is None
                or response.status is not ConnectedActionClaimStatus.EFFECT_POSSIBLE
            ):
                raise ConnectedAppRuntimeError(
                    "CONNECTED_LEDGER_POSTOBSERVE_UNCERTAIN",
                    retryable=False,
                ) from None
        if type(response) is not ConnectedActionClaim:
            raise ConnectedAppRuntimeError("CONNECTED_LEDGER_CLAIM_INVALID")
        return response

    async def _recover_access_with_readback(
        self,
        recovery: ConnectedActionAccessRecoveryRequest,
        expired: ConnectedActionClaim,
        authority: ConnectedActionAuthorityRecord,
        request: ConnectedActionClaimRequest,
    ) -> ConnectedActionClaim:
        try:
            response = await self._await_dependency(
                self._dependency_awaitable(
                    lambda: self._ledger.recover_access(recovery, authority),
                    code="CONNECTED_LEDGER_ACCESS_RECOVERY_UNCERTAIN",
                    retryable=True,
                ),
                deadline=request.execution_deadline,
                code="CONNECTED_LEDGER_ACCESS_RECOVERY_UNCERTAIN",
                retryable=True,
                trusted_codes=_LEDGER_AUTHORITY_CODES,
            )
        except asyncio.CancelledError:
            raise
        except ConnectedAppRuntimeError as error:
            if error.code != "CONNECTED_LEDGER_ACCESS_RECOVERY_UNCERTAIN":
                raise
            response = await self._readback(request, request.execution_deadline)
            if response is None or response.status is not ConnectedActionClaimStatus.ACCESS_GRANTED:
                raise ConnectedAppRuntimeError(
                    "CONNECTED_LEDGER_ACCESS_RECOVERY_UNCERTAIN",
                    retryable=True,
                ) from None
        if type(response) is not ConnectedActionClaim:
            raise ConnectedAppRuntimeError("CONNECTED_LEDGER_CLAIM_INVALID")
        if response.claim_id == expired.claim_id:
            raise ConnectedAppRuntimeError("CONNECTED_LEDGER_ACCESS_RECOVERY_INVALID")
        return response

    async def _settle_read(
        self,
        claim: ConnectedActionClaim,
        request: ConnectedActionClaimRequest,
        terminal: ConnectedReadTerminalRecord,
    ) -> LedgerTerminal:
        try:
            response = await self._await_dependency(
                self._dependency_awaitable(
                    lambda: self._ledger.settle(claim, terminal),
                    code="CONNECTED_LEDGER_SETTLEMENT_UNCERTAIN",
                    retryable=True,
                ),
                deadline=request.execution_deadline,
                code="CONNECTED_LEDGER_SETTLEMENT_UNCERTAIN",
                retryable=True,
            )
        except asyncio.CancelledError:
            raise
        except ConnectedAppRuntimeError:
            response = await self._readback(request, request.execution_deadline)
            if response is None:
                raise ConnectedAppRuntimeError(
                    "CONNECTED_LEDGER_SETTLEMENT_UNCERTAIN", retryable=True
                ) from None
        self._validate_replay_claim(response, request.lookup)
        if response.terminal != terminal:
            raise ConnectedAppRuntimeError("CONNECTED_LEDGER_TERMINAL_MISMATCH")
        assert response.terminal is not None
        return response.terminal

    async def _settle_durable_read(
        self,
        *,
        invocation: ConnectedActionInvocation,
        claim: ConnectedActionClaim,
        terminal: ConnectedReadTerminalRecord,
        observation: ConnectedReadObservation,
        deadline: datetime,
    ) -> ConnectedDurableReadResult:
        assert self._read_results is not None
        try:
            durable = await self._await_dependency(
                self._dependency_awaitable(
                    lambda: self._read_results.settle(
                        invocation=invocation,
                        claim=claim,
                        terminal=terminal,
                        observation=observation,
                        deadline=deadline,
                    ),
                    code="CONNECTED_READ_RESULT_EFFECT_UNKNOWN",
                    retryable=False,
                ),
                deadline=deadline,
                code="CONNECTED_READ_RESULT_EFFECT_UNKNOWN",
                retryable=False,
            )
        except asyncio.CancelledError:
            raise
        except ConnectedAppRuntimeError:
            raise ConnectedAppRuntimeError(
                "CONNECTED_READ_RESULT_EFFECT_UNKNOWN", retryable=False
            ) from None
        self._validate_durable_read(durable, terminal=terminal)
        return durable

    async def _recover_durable_read(
        self,
        lookup: ConnectedActionLookupRecord,
        claim: ConnectedActionClaim,
        deadline: datetime,
    ) -> ConnectedDurableReadResult | None:
        assert self._read_results is not None
        try:
            durable = await self._await_dependency(
                self._dependency_awaitable(
                    lambda: self._read_results.recover(
                        lookup=lookup,
                        claim=claim,
                        deadline=deadline,
                    ),
                    code="CONNECTED_READ_RESULT_EFFECT_UNKNOWN",
                    retryable=False,
                ),
                deadline=deadline,
                code="CONNECTED_READ_RESULT_EFFECT_UNKNOWN",
                retryable=False,
            )
        except asyncio.CancelledError:
            raise
        except ConnectedAppRuntimeError:
            raise ConnectedAppRuntimeError(
                "CONNECTED_READ_RESULT_EFFECT_UNKNOWN", retryable=False
            ) from None
        if durable is not None:
            self._validate_durable_read(durable, lookup=lookup)
        return durable

    async def _replay_durable_read(
        self,
        lookup: ConnectedActionLookupRecord,
        terminal: ConnectedReadTerminalRecord,
        deadline: datetime,
    ) -> ConnectedDurableReadResult:
        assert self._read_results is not None
        try:
            durable = await self._await_dependency(
                self._dependency_awaitable(
                    lambda: self._read_results.replay(
                        lookup=lookup,
                        terminal=terminal,
                        deadline=deadline,
                    ),
                    code="CONNECTED_READ_RESULT_UNAVAILABLE",
                    retryable=False,
                ),
                deadline=deadline,
                code="CONNECTED_READ_RESULT_UNAVAILABLE",
                retryable=False,
            )
        except asyncio.CancelledError:
            raise
        except ConnectedAppRuntimeError:
            raise ConnectedAppRuntimeError(
                "CONNECTED_READ_RESULT_UNAVAILABLE", retryable=False
            ) from None
        self._validate_durable_read(durable, terminal=terminal, lookup=lookup)
        return durable

    @staticmethod
    def _validate_durable_read(
        durable: ConnectedDurableReadResult,
        *,
        terminal: ConnectedReadTerminalRecord | None = None,
        lookup: ConnectedActionLookupRecord | None = None,
    ) -> None:
        if type(durable) is not ConnectedDurableReadResult:
            raise ConnectedAppRuntimeError("CONNECTED_READ_RESULT_BINDING_MISMATCH")
        if terminal is not None and durable.terminal != terminal:
            raise ConnectedAppRuntimeError("CONNECTED_READ_RESULT_BINDING_MISMATCH")
        if lookup is not None and (
            durable.terminal.operation_id != lookup.operation_id
            or durable.terminal.provider is not lookup.provider
            or durable.terminal.resource is not lookup.resource
            or durable.terminal.action is not lookup.action
            or durable.terminal.binding_sha256 != lookup.binding_sha256
            or durable.terminal.idempotency_key_hash != lookup.idempotency_key_hash
        ):
            raise ConnectedAppRuntimeError("CONNECTED_READ_RESULT_BINDING_MISMATCH")

    async def _settle_post_effect(
        self,
        claim: ConnectedActionClaim,
        request: ConnectedActionClaimRequest,
        terminal: ConnectedWriteTerminalRecord | ConnectedAmbiguousTerminalRecord,
    ) -> LedgerTerminal:
        try:
            return await self._reconcile_post_effect(claim, request, terminal)
        except asyncio.CancelledError:
            await self._shield_post_effect_cancellation(claim, request, terminal)
            raise

    async def _reconcile_post_effect(
        self,
        claim: ConnectedActionClaim,
        request: ConnectedActionClaimRequest,
        terminal: ConnectedWriteTerminalRecord | ConnectedAmbiguousTerminalRecord,
    ) -> LedgerTerminal:
        loop = asyncio.get_running_loop()
        reconciliation_end = loop.time() + min(
            5.0,
            self._remaining_seconds(request.execution_deadline),
        )
        try:
            existing = await self._readback(
                request,
                request.execution_deadline,
                timeout_cap=self._monotonic_remaining(reconciliation_end),
            )
            if existing is not None and existing.status not in {
                ConnectedActionClaimStatus.CLAIMED,
                ConnectedActionClaimStatus.BUSY,
                ConnectedActionClaimStatus.EFFECT_POSSIBLE,
            }:
                self._validate_replay_claim(existing, request.lookup)
                if existing.terminal != terminal:
                    raise ConnectedAppRuntimeError("CONNECTED_LEDGER_TERMINAL_MISMATCH")
                assert existing.terminal is not None
                return existing.terminal
            response = await self._await_dependency(
                self._dependency_awaitable(
                    lambda: self._ledger.settle(claim, terminal),
                    code="CONNECTED_ACTION_EFFECT_POSSIBLE",
                    retryable=False,
                ),
                deadline=request.execution_deadline,
                code="CONNECTED_ACTION_EFFECT_POSSIBLE",
                retryable=False,
                timeout_cap=self._monotonic_remaining(reconciliation_end),
            )
            self._validate_replay_claim(response, request.lookup)
            if response.terminal != terminal:
                raise ConnectedAppRuntimeError("CONNECTED_LEDGER_TERMINAL_MISMATCH")
            assert response.terminal is not None
            return response.terminal
        except asyncio.CancelledError:
            raise
        except ConnectedAppRuntimeError as error:
            if error.code in {
                "CONNECTED_LEDGER_TERMINAL_MISMATCH",
                "CONNECTED_LEDGER_TERMINAL_STATE_INVALID",
                "CONNECTED_LEDGER_TERMINAL_BINDING_MISMATCH",
            }:
                raise
            try:
                final = await self._readback(
                    request,
                    request.execution_deadline,
                    timeout_cap=self._monotonic_remaining(reconciliation_end),
                )
            except ConnectedAppRuntimeError:
                final = None
            if final is not None and final.status not in {
                ConnectedActionClaimStatus.CLAIMED,
                ConnectedActionClaimStatus.BUSY,
                ConnectedActionClaimStatus.EFFECT_POSSIBLE,
            }:
                self._validate_replay_claim(final, request.lookup)
                if final.terminal != terminal:
                    raise ConnectedAppRuntimeError("CONNECTED_LEDGER_TERMINAL_MISMATCH")
                assert final.terminal is not None
                return final.terminal
            raise ConnectedAppRuntimeError(
                "CONNECTED_ACTION_EFFECT_POSSIBLE", retryable=False
            ) from None

    async def _shield_post_effect_cancellation(
        self,
        claim: ConnectedActionClaim,
        request: ConnectedActionClaimRequest,
        terminal: ConnectedWriteTerminalRecord | ConnectedAmbiguousTerminalRecord,
    ) -> None:
        seconds = self._remaining_seconds(request.execution_deadline, cap=5.0)
        if seconds <= 0:
            return
        try:
            task = self._quarantine.spawn(self._reconcile_post_effect(claim, request, terminal))
        except ConnectedAppRuntimeError:
            return
        try:
            done, _ = await asyncio.wait({task}, timeout=seconds)
            if done:
                try:
                    task.result()
                except ConnectedAppRuntimeError:
                    pass
            else:
                task.cancel()
        except asyncio.CancelledError:
            task.cancel()

    async def _readback(
        self,
        record: ConnectedActionLookupRecord | ConnectedActionClaimRequest,
        deadline: datetime,
        *,
        timeout_cap: float | None = None,
    ) -> ConnectedActionClaim | None:
        result = await self._await_dependency(
            self._dependency_awaitable(
                lambda: self._ledger.readback(record),
                code="CONNECTED_LEDGER_READBACK_FAILED",
                retryable=True,
            ),
            deadline=deadline,
            code="CONNECTED_LEDGER_READBACK_FAILED",
            retryable=True,
            timeout_cap=timeout_cap,
        )
        if result is not None and type(result) is not ConnectedActionClaim:
            raise ConnectedAppRuntimeError("CONNECTED_LEDGER_CLAIM_INVALID")
        return result

    async def _replay_or_wait(
        self,
        claim: ConnectedActionClaim,
        lookup: ConnectedActionLookupRecord,
        deadline: datetime,
    ) -> ConnectedActionRuntimeResult | None:
        if claim.status not in {
            ConnectedActionClaimStatus.CLAIMED,
            ConnectedActionClaimStatus.ACCESS_GRANTED,
            ConnectedActionClaimStatus.BUSY,
            ConnectedActionClaimStatus.EFFECT_POSSIBLE,
        }:
            self._validate_replay_claim(claim, lookup)
            assert claim.terminal is not None
            if type(claim.terminal) is ConnectedReadTerminalRecord:
                if self._read_results is not None:
                    durable = await self._replay_durable_read(
                        lookup,
                        claim.terminal,
                        deadline,
                    )
                    return self._result(
                        durable.terminal,
                        replayed=True,
                        provider_result=durable.observation,
                    )
                raise ConnectedAppRuntimeError(
                    "CONNECTED_READ_CONTENT_NOT_RETAINED", retryable=True
                )
            return self._result(claim.terminal, replayed=True, provider_result=None)
        last = claim
        loop = asyncio.get_running_loop()
        end = loop.time() + self._contention_wait_seconds
        while (remaining := end - loop.time()) > 0:
            await asyncio.sleep(min(0.001, remaining))
            remaining = end - loop.time()
            if remaining <= 0:
                break
            current = await self._readback(
                lookup,
                deadline,
                timeout_cap=remaining,
            )
            if current is None:
                return None
            last = current
            if current.status not in {
                ConnectedActionClaimStatus.CLAIMED,
                ConnectedActionClaimStatus.ACCESS_GRANTED,
                ConnectedActionClaimStatus.BUSY,
                ConnectedActionClaimStatus.EFFECT_POSSIBLE,
            }:
                self._validate_replay_claim(current, lookup)
                assert current.terminal is not None
                if type(current.terminal) is ConnectedReadTerminalRecord:
                    if self._read_results is not None:
                        durable = await self._replay_durable_read(
                            lookup,
                            current.terminal,
                            deadline,
                        )
                        return self._result(
                            durable.terminal,
                            replayed=True,
                            provider_result=durable.observation,
                        )
                    raise ConnectedAppRuntimeError(
                        "CONNECTED_READ_CONTENT_NOT_RETAINED", retryable=True
                    )
                return self._result(current.terminal, replayed=True, provider_result=None)
        if last.status is ConnectedActionClaimStatus.EFFECT_POSSIBLE:
            raise ConnectedAppRuntimeError("CONNECTED_ACTION_EFFECT_POSSIBLE", retryable=False)
        if last.status is ConnectedActionClaimStatus.ACCESS_GRANTED:
            raise ConnectedAppRuntimeError("CONNECTED_READ_ACCESS_IN_PROGRESS", retryable=True)
        return None

    async def _await_dependency(
        self,
        awaitable: Awaitable[_T],
        *,
        deadline: datetime,
        code: str,
        retryable: bool,
        trusted_codes: frozenset[str] = frozenset(),
        timeout_cap: float | None = None,
    ) -> _T:
        seconds = self._remaining_seconds(deadline)
        if timeout_cap is not None:
            if not isinstance(timeout_cap, (int, float)) or timeout_cap < 0:
                if asyncio.iscoroutine(awaitable):
                    awaitable.close()
                raise ConnectedAppRuntimeError(code, retryable=retryable)
            seconds = min(seconds, float(timeout_cap))
        if seconds <= 0:
            if asyncio.iscoroutine(awaitable):
                awaitable.close()
            raise ConnectedAppRuntimeError(code, retryable=retryable)
        task = self._quarantine.spawn(awaitable)
        try:
            done, _ = await asyncio.wait({task}, timeout=seconds)
        except asyncio.CancelledError:
            task.cancel()
            raise
        if not done:
            task.cancel()
            raise ConnectedAppRuntimeError(code, retryable=retryable) from None
        try:
            return task.result()
        except asyncio.CancelledError:
            raise ConnectedAppRuntimeError(code, retryable=retryable) from None
        except ConnectedAppRuntimeError as error:
            if error.code in trusted_codes:
                raise ConnectedAppRuntimeError(error.code, retryable=False) from None
            raise ConnectedAppRuntimeError(code, retryable=retryable) from None
        except Exception:
            raise ConnectedAppRuntimeError(code, retryable=retryable) from None

    @staticmethod
    def _dependency_awaitable(
        factory: Callable[[], Awaitable[_T]],
        *,
        code: str,
        retryable: bool,
    ) -> Awaitable[_T]:
        """Construct an awaitable without trusting synchronous dependency code."""

        try:
            return factory()
        except Exception:
            raise ConnectedAppRuntimeError(code, retryable=retryable) from None

    @staticmethod
    def _provider_awaitable(
        factory: Callable[[], Awaitable[_T]],
        *,
        code: str,
        retryable: bool,
    ) -> Awaitable[_T]:
        """Construct a provider awaitable without trusting synchronous adapter code."""

        try:
            return factory()
        except Exception:
            raise ConnectedAppRuntimeError(code, retryable=retryable) from None

    async def _live_binding(
        self,
        intent: ConnectedActionIntent,
        *,
        authority: ConnectedActionAuthorityRecord,
        deadline: datetime,
    ) -> ConnectedAccountBinding:
        current = await self._await_dependency(
            self._dependency_awaitable(
                lambda: self._accounts.get_binding(
                    owner_id=intent.owner_id,
                    connection_id=intent.connection_id,
                ),
                code="CONNECTED_ACCOUNT_REGISTRY_FAILED",
                retryable=True,
            ),
            deadline=deadline,
            code="CONNECTED_ACCOUNT_REGISTRY_FAILED",
            retryable=True,
        )
        if current is None:
            raise ConnectedAppRuntimeError("CONNECTED_ACCOUNT_NOT_FOUND")
        if type(current) is not ConnectedAccountBinding:
            raise ConnectedAppRuntimeError("CONNECTED_ACCOUNT_BINDING_INVALID")
        self._validate_account(current.account, intent)
        self._validate_authorization(current.authorization, intent, self._now())
        if (
            current.authorization.snapshot_sha256 != authority.authorization_snapshot_sha256
            or current.authorization.revision != authority.authorization_revision
            or current.authorization.granted_actions_sha256 != authority.granted_actions_sha256
            or current.authorization.granted_scopes_sha256 != authority.granted_scopes_sha256
        ):
            raise ConnectedAppRuntimeError("CONNECTED_AUTHORIZATION_CHANGED")
        return current

    def _phase_expiry(
        self,
        claim: ConnectedActionClaim,
        authorization: ConnectedAuthorizationSnapshot,
        deadline: datetime,
        *,
        max_seconds: float | None = None,
    ) -> datetime:
        if claim.lease_expires_at is None:
            raise ConnectedAppRuntimeError("CONNECTED_CREDENTIAL_BINDING_MISMATCH")
        current = _aware(self._now(), "now")
        options = [
            _aware(deadline, "deadline"),
            _aware(claim.lease_expires_at, "claim.lease_expires_at"),
            _aware(authorization.expires_at, "authorization.expires_at"),
        ]
        if max_seconds is not None:
            options.append(current + timedelta(seconds=max_seconds))
        expires = min(options)
        if expires <= current:
            raise ConnectedAppRuntimeError("CONNECTED_CREDENTIAL_LEASE_EXPIRED")
        return expires

    def _fresh_access_expiry(
        self,
        current: datetime,
        authorization: ConnectedAuthorizationSnapshot,
        deadline: datetime,
    ) -> datetime:
        issued = _aware(current, "current")
        expires = min(
            issued + self._claim_lease,
            _aware(authorization.expires_at, "authorization.expires_at"),
            _aware(deadline, "deadline"),
        )
        if expires <= issued:
            raise ConnectedAppRuntimeError("CONNECTED_CREDENTIAL_LEASE_EXPIRED")
        return expires

    async def _issue_child_lease(
        self,
        *,
        account: ConnectedAccountRef,
        authorization: ConnectedAuthorizationSnapshot,
        intent: ConnectedActionIntent,
        claim: ConnectedActionClaim,
        authority: ConnectedActionAuthorityRecord,
        phase: ConnectedCredentialPhase,
        use_nonce: str,
        hard_expiry: datetime,
        deadline: datetime,
        timeout_cap: float | None = None,
    ) -> ConnectedCredentialLease:
        if phase in {
            ConnectedCredentialPhase.READ,
            ConnectedCredentialPhase.PREOBSERVE,
        }:
            if (
                claim.status is not ConnectedActionClaimStatus.ACCESS_GRANTED
                or claim.access_phase is not phase
                or claim.access_use_nonce != use_nonce
            ):
                raise ConnectedAppRuntimeError("CONNECTED_CREDENTIAL_BINDING_MISMATCH")
        elif phase is ConnectedCredentialPhase.EFFECT:
            if (
                claim.status is not ConnectedActionClaimStatus.EFFECT_POSSIBLE
                or claim.effect_use_nonce != use_nonce
                or claim.lease_expires_at != hard_expiry
            ):
                raise ConnectedAppRuntimeError("CONNECTED_CREDENTIAL_BINDING_MISMATCH")
        elif (
            phase is not ConnectedCredentialPhase.POSTOBSERVE
            or claim.status is not ConnectedActionClaimStatus.EFFECT_POSSIBLE
            or claim.postobserve_use_nonce != use_nonce
            or claim.postobserve_expires_at != hard_expiry
            or claim.effect_use_nonce == use_nonce
        ):
            raise ConnectedAppRuntimeError("CONNECTED_CREDENTIAL_BINDING_MISMATCH")
        awaitable = self._dependency_awaitable(
            lambda: self._credentials.issue_child_lease(
                account=account,
                authorization=authorization,
                intent=intent,
                claim=claim,
                authority=authority,
                phase=phase,
                use_nonce=use_nonce,
                hard_expires_at=hard_expiry,
            ),
            code="CONNECTED_CREDENTIAL_BROKER_FAILED",
            retryable=True,
        )
        credential = await self._await_dependency(
            awaitable,
            deadline=deadline,
            code="CONNECTED_CREDENTIAL_BROKER_FAILED",
            retryable=True,
            timeout_cap=timeout_cap,
        )
        self._validate_credential(
            credential,
            intent,
            claim,
            authority,
            phase=phase,
            use_nonce=use_nonce,
            hard_expiry=hard_expiry,
        )
        return credential

    def _remaining_seconds(self, deadline: datetime, *, cap: float | None = None) -> float:
        remaining = max(
            0.0,
            (_aware(deadline, "deadline") - _aware(self._now(), "now")).total_seconds(),
        )
        return min(remaining, cap) if cap is not None else remaining

    @staticmethod
    def _monotonic_remaining(end: float) -> float:
        return max(0.0, end - asyncio.get_running_loop().time())

    @staticmethod
    def _new_phase_nonce(*used: str) -> str:
        forbidden = frozenset(used)
        while (nonce := str(uuid4())) in forbidden:
            pass
        return nonce

    @staticmethod
    def _lookup(invocation: ConnectedActionInvocation) -> ConnectedActionLookupRecord:
        intent = invocation.intent
        return ConnectedActionLookupRecord(
            operation_id=intent.action_id,
            owner_id=intent.owner_id,
            task_id=intent.task_id,
            turn_id=intent.turn_id,
            connection_id=intent.connection_id,
            provider=intent.provider,
            resource=intent.resource,
            action=intent.action,
            parameters_sha256=intent.parameters_sha256,
            resource_version_sha256=intent.resource_version_sha256,
            binding_sha256=invocation.binding_sha256,
            idempotency_key_hash=_hash(intent.idempotency_key),
        )

    def _authority(
        self,
        *,
        grant: ConnectedTaskGrant,
        approval: ConnectedApprovalEvidence | None,
        authorization: ConnectedAuthorizationSnapshot,
        task_state_revision: int,
        decided_at: datetime,
    ) -> ConnectedActionAuthorityRecord:
        return ConnectedActionAuthorityRecord(
            grant_id=grant.grant_id,
            grant_sha256=_record_hash(grant),
            grant_expires_at=grant.expires_at,
            approval_id=approval.approval_id if approval else None,
            approval_sha256=_record_hash(approval) if approval else None,
            approval_expires_at=approval.expires_at if approval else None,
            authorization_revision=authorization.revision,
            authorization_snapshot_sha256=authorization.snapshot_sha256,
            granted_actions_sha256=authorization.granted_actions_sha256,
            granted_scopes_sha256=authorization.granted_scopes_sha256,
            task_state_revision=task_state_revision,
            policy_version=self._policy.version,
            decided_at=decided_at,
        )

    @staticmethod
    def _validate_account(account: ConnectedAccountRef, intent: ConnectedActionIntent) -> None:
        if (
            account.owner_id != intent.owner_id
            or account.connection_id != intent.connection_id
            or account.provider is not intent.provider
            or account.resource is not intent.resource
        ):
            raise ConnectedAppRuntimeError("CONNECTED_ACCOUNT_BINDING_MISMATCH")

    @staticmethod
    def _validate_authorization(
        authorization: ConnectedAuthorizationSnapshot,
        intent: ConnectedActionIntent,
        now: datetime,
    ) -> None:
        if (
            authorization.owner_id != intent.owner_id
            or authorization.connection_id != intent.connection_id
            or authorization.provider is not intent.provider
            or authorization.resource is not intent.resource
            or authorization.revision != intent.authorization_revision
            or authorization.snapshot_sha256 != intent.authorization_snapshot_sha256
        ):
            raise ConnectedAppRuntimeError("CONNECTED_AUTHORIZATION_BINDING_MISMATCH")
        if not authorization.active_at(_aware(now, "now")):
            raise ConnectedAppRuntimeError("CONNECTED_AUTHORIZATION_INACTIVE")
        if intent.action not in authorization.granted_actions:
            raise ConnectedAppRuntimeError("CONNECTED_AUTHORIZATION_ACTION_INSUFFICIENT")
        if not scopes_cover(
            provider=authorization.provider,
            account_kind=authorization.account_kind,
            granted_scopes=authorization.granted_scopes,
            actions={intent.action},
        ):
            raise ConnectedAppRuntimeError("CONNECTED_AUTHORIZATION_SCOPE_INSUFFICIENT")

    def _validate_credential(
        self,
        credential: ConnectedCredentialLease,
        intent: ConnectedActionIntent,
        claim: ConnectedActionClaim,
        authority: ConnectedActionAuthorityRecord,
        *,
        phase: ConnectedCredentialPhase,
        use_nonce: str,
        hard_expiry: datetime,
    ) -> None:
        if (
            type(credential) is not ConnectedCredentialLease
            or credential.owner_id != intent.owner_id
            or credential.connection_id != intent.connection_id
            or credential.provider is not intent.provider
            or credential.resource is not intent.resource
            or credential.authorization_revision != authority.authorization_revision
            or credential.authorization_snapshot_sha256 != authority.authorization_snapshot_sha256
            or credential.granted_actions_sha256 != authority.granted_actions_sha256
            or credential.granted_scopes_sha256 != authority.granted_scopes_sha256
            or credential.authority_sha256 != authority.authority_sha256
            or credential.task_state_revision != authority.task_state_revision
            or credential.claim_id != claim.claim_id
            or credential.fencing_token != claim.fencing_token
            or credential.phase is not phase
            or credential.use_nonce != use_nonce
            or credential.expires_at != hard_expiry
        ):
            raise ConnectedAppRuntimeError("CONNECTED_CREDENTIAL_BINDING_MISMATCH")
        now = _aware(self._now(), "now")
        if credential.expires_at <= credential.issued_at or credential.expires_at <= now:
            # Broker time is wall clock, not the injectable policy clock; a lease
            # that is already dead must never reach the provider boundary.
            raise ConnectedAppRuntimeError("CONNECTED_CREDENTIAL_LEASE_EXPIRED")

    def _validate_fresh_claim(
        self, claim: ConnectedActionClaim, request: ConnectedActionClaimRequest
    ) -> None:
        assert claim.lease_expires_at is not None
        if (
            claim.binding_sha256 != request.lookup.binding_sha256
            or claim.authority_sha256 != request.authority_sha256
            or claim.granted_actions_sha256 != request.granted_actions_sha256
            or claim.execution_deadline != request.execution_deadline
            or claim.lease_expires_at > request.requested_at + self._claim_lease
        ):
            raise ConnectedAppRuntimeError("CONNECTED_LEDGER_BINDING_MISMATCH")
        self._validate_claim_live(claim)

    def _validate_effect_claim(
        self,
        claim: ConnectedActionClaim,
        request: ConnectedActionEffectRequest,
    ) -> None:
        if (
            claim.status is not ConnectedActionClaimStatus.EFFECT_POSSIBLE
            or claim.claim_id != request.claim_id
            or claim.fencing_token != request.fencing_token
            or claim.binding_sha256 != request.lookup.binding_sha256
            or claim.authority_sha256 != request.authority_sha256
            or claim.granted_actions_sha256 != request.granted_actions_sha256
            or claim.effect_use_nonce != request.credential_use_nonce
            or claim.execution_deadline != request.execution_deadline
            or claim.lease_expires_at != request.credential_expires_at
            or claim.effect_started_at is None
        ):
            raise ConnectedAppRuntimeError("CONNECTED_LEDGER_EFFECT_BINDING_MISMATCH")
        assert claim.execution_deadline is not None
        started = _aware(claim.effect_started_at, "effect_started_at")
        if (
            started < _aware(request.requested_at, "requested_at")
            or started >= request.credential_expires_at
            or _aware(self._now(), "now") >= request.credential_expires_at
            or _aware(self._now(), "now") >= claim.execution_deadline
        ):
            raise ConnectedAppRuntimeError("CONNECTED_ACTION_EFFECT_POSSIBLE", retryable=False)

    def _validate_access_claim(
        self,
        claim: ConnectedActionClaim,
        request: ConnectedActionAccessRequest,
    ) -> None:
        if (
            claim.status is not ConnectedActionClaimStatus.ACCESS_GRANTED
            or claim.claim_id != request.claim_id
            or claim.fencing_token != request.fencing_token
            or claim.binding_sha256 != request.lookup.binding_sha256
            or claim.authority_sha256 != request.authority_sha256
            or claim.granted_actions_sha256 != request.granted_actions_sha256
            or claim.access_phase is not request.phase
            or claim.access_use_nonce != request.credential_use_nonce
            or claim.execution_deadline != request.execution_deadline
            or claim.lease_expires_at != request.credential_expires_at
            or claim.access_started_at is None
        ):
            raise ConnectedAppRuntimeError("CONNECTED_LEDGER_ACCESS_BINDING_MISMATCH")
        current = _aware(self._now(), "now")
        started = _aware(claim.access_started_at, "access_started_at")
        if (
            started < _aware(request.requested_at, "requested_at")
            or started >= request.credential_expires_at
            or current >= request.credential_expires_at
            or current >= request.execution_deadline
        ):
            raise ConnectedAppRuntimeError("CONNECTED_CREDENTIAL_LEASE_EXPIRED")

    def _validate_recovered_access_claim(
        self,
        claim: ConnectedActionClaim,
        request: ConnectedActionAccessRecoveryRequest,
        expired: ConnectedActionClaim | None,
    ) -> None:
        if (
            claim.status is not ConnectedActionClaimStatus.ACCESS_GRANTED
            or claim.binding_sha256 != request.lookup.binding_sha256
            or claim.authority_sha256 != request.authority_sha256
            or claim.granted_actions_sha256 != request.granted_actions_sha256
            or claim.access_phase is not request.phase
            or claim.access_use_nonce != request.credential_use_nonce
            or claim.execution_deadline != request.execution_deadline
            or claim.lease_expires_at != request.credential_expires_at
            or claim.access_started_at is None
            or type(claim.fencing_token) is not int
            or claim.fencing_token < 1
            or (expired is not None and claim.claim_id == expired.claim_id)
        ):
            raise ConnectedAppRuntimeError("CONNECTED_LEDGER_ACCESS_RECOVERY_INVALID")
        current = _aware(self._now(), "now")
        started = _aware(claim.access_started_at, "access_started_at")
        if (
            started < _aware(request.requested_at, "requested_at")
            or started >= request.credential_expires_at
            or current >= request.credential_expires_at
            or current >= request.execution_deadline
        ):
            raise ConnectedAppRuntimeError("CONNECTED_CREDENTIAL_LEASE_EXPIRED")

    def _validate_postobserve_claim(
        self,
        claim: ConnectedActionClaim,
        request: ConnectedActionPostobserveRequest,
    ) -> None:
        if (
            claim.status is not ConnectedActionClaimStatus.EFFECT_POSSIBLE
            or claim.claim_id != request.claim_id
            or claim.fencing_token != request.fencing_token
            or claim.binding_sha256 != request.lookup.binding_sha256
            or claim.authority_sha256 != request.authority_sha256
            or claim.granted_actions_sha256 != request.granted_actions_sha256
            or claim.effect_use_nonce != request.effect_use_nonce
            or claim.postobserve_use_nonce != request.credential_use_nonce
            or claim.postobserve_expires_at != request.credential_expires_at
            or claim.execution_deadline != request.execution_deadline
            or claim.postobserve_started_at is None
        ):
            raise ConnectedAppRuntimeError("CONNECTED_LEDGER_POSTOBSERVE_BINDING_MISMATCH")
        current = _aware(self._now(), "now")
        started = _aware(claim.postobserve_started_at, "postobserve_started_at")
        if (
            started < _aware(request.requested_at, "requested_at")
            or started >= request.credential_expires_at
            or current >= request.credential_expires_at
            or current >= request.execution_deadline
        ):
            raise ConnectedAppRuntimeError("CONNECTED_CREDENTIAL_LEASE_EXPIRED")

    def _validate_claim_live(self, claim: ConnectedActionClaim) -> None:
        if claim.status is not ConnectedActionClaimStatus.CLAIMED:
            raise ConnectedAppRuntimeError("CONNECTED_CLAIM_NOT_ACTIVE")
        current = _aware(self._now(), "now")
        assert claim.lease_expires_at is not None
        assert claim.execution_deadline is not None
        if current >= claim.lease_expires_at or current >= claim.execution_deadline:
            raise ConnectedAppRuntimeError("CONNECTED_CLAIM_EXPIRED")

    def _claim_expired(self, claim: ConnectedActionClaim) -> bool:
        current = _aware(self._now(), "now")
        assert claim.lease_expires_at is not None
        assert claim.execution_deadline is not None
        return current >= claim.lease_expires_at or current >= claim.execution_deadline

    @staticmethod
    def _expired_access_recoverable(
        claim: ConnectedActionClaim,
        lookup: ConnectedActionLookupRecord,
        now: datetime,
    ) -> bool:
        if claim.status is not ConnectedActionClaimStatus.ACCESS_GRANTED:
            return False
        if claim.binding_sha256 != lookup.binding_sha256:
            raise ConnectedAppRuntimeError("CONNECTED_LEDGER_BINDING_MISMATCH")
        assert claim.lease_expires_at is not None
        return _aware(claim.lease_expires_at, "lease_expires_at") <= _aware(now, "now")

    @staticmethod
    def _validate_provider_identity(
        result: ConnectedReadObservation | ProviderReceipt | AmbiguousProviderResult,
        intent: ConnectedActionIntent,
    ) -> None:
        if (
            result.operation_id != intent.action_id
            or result.provider is not intent.provider
            or result.resource is not intent.resource
        ):
            raise ConnectedAppRuntimeError("CONNECTED_PROVIDER_RESULT_BINDING_MISMATCH")

    @classmethod
    def _validate_receipt(
        cls,
        receipt: ProviderReceipt,
        intent: ConnectedActionIntent,
        *,
        earliest: datetime,
        latest: datetime,
    ) -> None:
        cls._validate_provider_identity(receipt, intent)
        if (
            receipt.idempotency_key_hash != _hash(intent.idempotency_key)
            or receipt.outcome != _OUTCOMES[intent.action]
        ):
            raise ConnectedAppRuntimeError("CONNECTED_PROVIDER_RESULT_BINDING_MISMATCH")
        cls._validate_provider_observed_at(receipt.observed_at, earliest=earliest, latest=latest)

    @classmethod
    def _validate_ambiguous_result(
        cls,
        result: AmbiguousProviderResult,
        intent: ConnectedActionIntent,
        *,
        earliest: datetime,
        latest: datetime,
    ) -> None:
        cls._validate_provider_identity(result, intent)
        if result.idempotency_key_hash != _hash(intent.idempotency_key):
            raise ConnectedAppRuntimeError("CONNECTED_PROVIDER_RESULT_BINDING_MISMATCH")
        cls._validate_provider_observed_at(result.observed_at, earliest=earliest, latest=latest)

    @staticmethod
    def _validate_provider_observed_at(
        observed_at: datetime,
        *,
        earliest: datetime,
        latest: datetime,
    ) -> None:
        try:
            observed = _aware(observed_at, "observed_at")
            lower = _aware(earliest, "earliest")
            upper = _aware(latest, "latest")
        except (TypeError, ValueError):
            raise ConnectedAppRuntimeError("CONNECTED_PROVIDER_RESULT_BINDING_MISMATCH") from None
        if observed < lower or observed > upper:
            raise ConnectedAppRuntimeError("CONNECTED_PROVIDER_RESULT_BINDING_MISMATCH")

    @classmethod
    def _validate_replay_claim(
        cls, claim: ConnectedActionClaim, lookup: ConnectedActionLookupRecord
    ) -> None:
        if type(claim) is not ConnectedActionClaim or claim.terminal is None:
            raise ConnectedAppRuntimeError("CONNECTED_LEDGER_TERMINAL_STATE_INVALID")
        terminal = claim.terminal
        if claim.status is ConnectedActionClaimStatus.REPLAY_READ:
            expected: type[object] = ConnectedReadTerminalRecord
            if lookup.action not in _READS:
                raise ConnectedAppRuntimeError("CONNECTED_LEDGER_TERMINAL_STATE_INVALID")
        elif claim.status is ConnectedActionClaimStatus.REPLAY_SUCCEEDED:
            expected = ConnectedWriteTerminalRecord
            if lookup.action not in _OUTCOMES:
                raise ConnectedAppRuntimeError("CONNECTED_LEDGER_TERMINAL_STATE_INVALID")
        elif claim.status is ConnectedActionClaimStatus.REPLAY_AMBIGUOUS:
            expected = ConnectedAmbiguousTerminalRecord
            if lookup.action not in _OUTCOMES:
                raise ConnectedAppRuntimeError("CONNECTED_LEDGER_TERMINAL_STATE_INVALID")
        else:
            raise ConnectedAppRuntimeError("CONNECTED_LEDGER_TERMINAL_STATE_INVALID")
        if type(terminal) is not expected:
            raise ConnectedAppRuntimeError("CONNECTED_LEDGER_TERMINAL_STATE_INVALID")
        if (
            terminal.operation_id != lookup.operation_id
            or terminal.provider is not lookup.provider
            or terminal.resource is not lookup.resource
            or terminal.action is not lookup.action
            or terminal.binding_sha256 != lookup.binding_sha256
            or terminal.idempotency_key_hash != lookup.idempotency_key_hash
            or claim.binding_sha256 != lookup.binding_sha256
            or terminal.authority_sha256 != claim.authority_sha256
        ):
            raise ConnectedAppRuntimeError("CONNECTED_LEDGER_TERMINAL_BINDING_MISMATCH")
        if type(terminal) is ConnectedWriteTerminalRecord and (
            terminal.receipt_outcome != _OUTCOMES[lookup.action]
        ):
            raise ConnectedAppRuntimeError("CONNECTED_LEDGER_TERMINAL_STATE_INVALID")

    def _ambiguous_provider(self, intent: ConnectedActionIntent) -> AmbiguousProviderResult:
        return AmbiguousProviderResult(
            operation_id=intent.action_id,
            provider=intent.provider,
            resource=intent.resource,
            idempotency_key_hash=_hash(intent.idempotency_key),
            observed_at=_aware(self._now(), "now"),
        )

    def _ambiguous_terminal(
        self,
        intent: ConnectedActionIntent,
        invocation: ConnectedActionInvocation | None,
        claim: ConnectedActionClaim,
    ) -> ConnectedAmbiguousTerminalRecord:
        return ConnectedAmbiguousTerminalRecord(
            operation_id=intent.action_id,
            provider=intent.provider,
            resource=intent.resource,
            action=intent.action,
            binding_sha256=(
                invocation.binding_sha256 if invocation is not None else claim.binding_sha256
            ),
            authority_sha256=claim.authority_sha256,
            idempotency_key_hash=_hash(intent.idempotency_key),
            observed_at=_aware(self._now(), "now"),
        )

    @staticmethod
    def _result(
        terminal: LedgerTerminal,
        *,
        replayed: bool,
        provider_result: ConnectedReadObservation
        | ProviderReceipt
        | AmbiguousProviderResult
        | None,
    ) -> ConnectedActionRuntimeResult:
        if type(terminal) is ConnectedAmbiguousTerminalRecord:
            outcome = ConnectedActionOutcome.AMBIGUOUS
        elif type(terminal) is ConnectedWriteTerminalRecord:
            outcome = ConnectedActionOutcome.SUCCEEDED
        else:
            outcome = ConnectedActionOutcome.READ
        return ConnectedActionRuntimeResult(
            operation_id=terminal.operation_id,
            outcome=outcome,
            replayed=replayed,
            terminal=terminal,
            provider_result=provider_result,
        )
