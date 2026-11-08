"""Deterministic authority boundary for connected mail and calendar actions.

This module is deliberately pure. It does not hold credentials, inspect message
or event content, call a provider, persist data, or expose a release switch.
The model may propose an action, but only a server-authored, owner-bound task
grant and (for writes) an exact approval can authorize it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum
import hashlib
import json
import re
from typing import Iterable
from uuid import UUID


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_POLICY_VERSION = "connected-app-policy-v1"


class ConnectorProvider(StrEnum):
    GOOGLE = "google"
    MICROSOFT = "microsoft"


class ConnectorResource(StrEnum):
    MAIL = "mail"
    CALENDAR = "calendar"


class ConnectorActionKind(StrEnum):
    MAIL_SEARCH = "mail.search"
    MAIL_LIST = "mail.list"
    MAIL_GET = "mail.get"
    MAIL_CREATE_DRAFT = "mail.create_draft"
    MAIL_SEND = "mail.send"
    MAIL_REPLY = "mail.reply"
    MAIL_FORWARD = "mail.forward"
    MAIL_LABEL = "mail.label"
    MAIL_ARCHIVE = "mail.archive"
    MAIL_TRASH = "mail.trash"
    MAIL_DELETE_PERMANENT = "mail.delete_permanent"
    MAIL_CONNECT = "mail.connect"
    MAIL_EXPAND_SCOPES = "mail.expand_scopes"
    MAIL_REGISTER_WATCH = "mail.register_watch"
    CALENDAR_LIST = "calendar.list"
    CALENDAR_GET = "calendar.get"
    CALENDAR_FREE_BUSY = "calendar.free_busy"
    CALENDAR_CREATE = "calendar.create"
    CALENDAR_UPDATE = "calendar.update"
    CALENDAR_CANCEL = "calendar.cancel"
    CALENDAR_DELETE = "calendar.delete"
    CALENDAR_CONNECT = "calendar.connect"
    CALENDAR_EXPAND_SCOPES = "calendar.expand_scopes"
    CALENDAR_REGISTER_WATCH = "calendar.register_watch"


class ConnectorApprovalClass(StrEnum):
    NONE = "none"
    EXTERNAL_WRITE_REVERSIBLE = "external_write_reversible"
    EXTERNAL_COMMUNICATION = "external_communication"
    CALENDAR_WRITE = "calendar_write"
    DESTRUCTIVE = "destructive"
    PERSISTENT_PERMISSION = "persistent_permission"


class ConnectorDecisionKind(StrEnum):
    ALLOW = "allow"
    REQUIRE_APPROVAL = "require_approval"
    DENY = "deny"


class ConnectorDecisionReason(StrEnum):
    AUTHORIZED_READ = "authorized_read"
    APPROVED_WRITE = "approved_write"
    APPROVAL_REQUIRED = "approval_required"
    ACTION_NOT_GRANTED = "action_not_granted"
    GRANT_BINDING_MISMATCH = "grant_binding_mismatch"
    GRANT_EXPIRED = "grant_expired"
    ACTION_RESOURCE_MISMATCH = "action_resource_mismatch"
    ACTION_NOT_IMPLEMENTED = "action_not_implemented"
    APPROVAL_BINDING_MISMATCH = "approval_binding_mismatch"
    APPROVAL_NOT_YET_VALID = "approval_not_yet_valid"
    APPROVAL_EXPIRED = "approval_expired"
    PERSISTENT_PERMISSION_USER_REQUIRED = "persistent_permission_user_required"


def _uuid(value: str, label: str) -> str:
    try:
        parsed = UUID(str(value))
    except (ValueError, AttributeError, TypeError) as exc:
        raise ValueError(f"{label} must be a UUID") from exc
    canonical = str(parsed)
    if str(value) != canonical:
        raise ValueError(f"{label} must be a canonical UUID")
    return canonical


def _sha256(value: str | None, label: str, *, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _aware(value: datetime, label: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError(f"{label} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _enum(value: object, expected: type[StrEnum], label: str) -> None:
    if not isinstance(value, expected):
        raise ValueError(f"{label} must be a {expected.__name__}")


def _frozen_actions(values: Iterable[ConnectorActionKind]) -> frozenset[ConnectorActionKind]:
    actions = frozenset(values)
    if not actions or any(not isinstance(value, ConnectorActionKind) for value in actions):
        raise ValueError("actions must contain ConnectorActionKind values")
    return actions


def action_set_sha256(values: Iterable[ConnectorActionKind]) -> str:
    """Canonical digest for an exact delegated action set."""

    actions = _frozen_actions(values)
    encoded = json.dumps(
        sorted(action.value for action in actions),
        ensure_ascii=True,
        separators=(",", ":"),
    ).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True, repr=False)
class ConnectedActionIntent:
    """Content-free identity of one proposed connected-app operation."""

    action_id: str
    owner_id: str
    task_id: str
    turn_id: str
    connection_id: str
    provider: ConnectorProvider
    resource: ConnectorResource
    authorization_revision: int
    authorization_snapshot_sha256: str
    action: ConnectorActionKind
    parameters_sha256: str
    resource_version_sha256: str | None
    untrusted_context_sha256: str | None
    idempotency_key: str
    requested_at: datetime

    def __post_init__(self) -> None:
        for field in ("action_id", "owner_id", "task_id", "turn_id", "connection_id"):
            _uuid(getattr(self, field), field)
        _enum(self.provider, ConnectorProvider, "provider")
        _enum(self.resource, ConnectorResource, "resource")
        if type(self.authorization_revision) is not int or self.authorization_revision < 1:
            raise ValueError("authorization_revision must be a positive integer")
        _sha256(
            self.authorization_snapshot_sha256,
            "authorization_snapshot_sha256",
        )
        _enum(self.action, ConnectorActionKind, "action")
        _sha256(self.parameters_sha256, "parameters_sha256")
        _sha256(self.resource_version_sha256, "resource_version_sha256", optional=True)
        _sha256(self.untrusted_context_sha256, "untrusted_context_sha256", optional=True)
        _sha256(self.idempotency_key, "idempotency_key")
        _aware(self.requested_at, "requested_at")
        if self.idempotency_key != self.expected_idempotency_key():
            raise ValueError("idempotency_key does not match the connected action")

    def expected_idempotency_key(self) -> str:
        components = (
            _POLICY_VERSION,
            self.owner_id,
            self.task_id,
            self.turn_id,
            self.connection_id,
            self.provider.value,
            self.resource.value,
            str(self.authorization_revision),
            self.authorization_snapshot_sha256,
            self.action.value,
            self.parameters_sha256,
            self.resource_version_sha256 or "",
        )
        return hashlib.sha256("\x00".join(components).encode("utf-8")).hexdigest()

    @classmethod
    def build(
        cls,
        *,
        action_id: str,
        owner_id: str,
        task_id: str,
        turn_id: str,
        connection_id: str,
        provider: ConnectorProvider,
        resource: ConnectorResource,
        authorization_revision: int,
        authorization_snapshot_sha256: str,
        action: ConnectorActionKind,
        parameters_sha256: str,
        resource_version_sha256: str | None = None,
        untrusted_context_sha256: str | None = None,
        requested_at: datetime,
    ) -> ConnectedActionIntent:
        _enum(provider, ConnectorProvider, "provider")
        _enum(resource, ConnectorResource, "resource")
        _enum(action, ConnectorActionKind, "action")
        components = (
            _POLICY_VERSION,
            owner_id,
            task_id,
            turn_id,
            connection_id,
            provider.value,
            resource.value,
            str(authorization_revision),
            authorization_snapshot_sha256,
            action.value,
            parameters_sha256,
            resource_version_sha256 or "",
        )
        idempotency_key = hashlib.sha256("\x00".join(components).encode("utf-8")).hexdigest()
        return cls(
            action_id=action_id,
            owner_id=owner_id,
            task_id=task_id,
            turn_id=turn_id,
            connection_id=connection_id,
            provider=provider,
            resource=resource,
            authorization_revision=authorization_revision,
            authorization_snapshot_sha256=authorization_snapshot_sha256,
            action=action,
            parameters_sha256=parameters_sha256,
            resource_version_sha256=resource_version_sha256,
            untrusted_context_sha256=untrusted_context_sha256,
            idempotency_key=idempotency_key,
            requested_at=requested_at,
        )

    def __repr__(self) -> str:
        return (
            "ConnectedActionIntent("
            f"action_id={self.action_id!r}, action={self.action.value!r}, "
            "bindings='<redacted>')"
        )


@dataclass(frozen=True, slots=True, repr=False)
class ConnectedTaskGrant:
    """Server-authored capability grant for one task turn and connection."""

    grant_id: str
    owner_id: str
    task_id: str
    turn_id: str
    connection_id: str
    provider: ConnectorProvider
    resource: ConnectorResource
    authorization_revision: int
    authorization_snapshot_sha256: str
    actions: frozenset[ConnectorActionKind]
    actions_sha256: str
    expires_at: datetime

    def __post_init__(self) -> None:
        for field in ("grant_id", "owner_id", "task_id", "turn_id", "connection_id"):
            _uuid(getattr(self, field), field)
        _enum(self.provider, ConnectorProvider, "provider")
        _enum(self.resource, ConnectorResource, "resource")
        if type(self.authorization_revision) is not int or self.authorization_revision < 1:
            raise ValueError("authorization_revision must be a positive integer")
        _sha256(
            self.authorization_snapshot_sha256,
            "authorization_snapshot_sha256",
        )
        object.__setattr__(self, "actions", _frozen_actions(self.actions))
        normalized_hash = _sha256(self.actions_sha256, "actions_sha256")
        if normalized_hash != action_set_sha256(self.actions):
            raise ValueError("actions_sha256 does not match the exact action set")
        _aware(self.expires_at, "expires_at")

    def __repr__(self) -> str:
        return (
            "ConnectedTaskGrant("
            f"grant_id={self.grant_id!r}, actions={len(self.actions)}, "
            "bindings='<redacted>')"
        )


@dataclass(frozen=True, slots=True, repr=False)
class ConnectedApprovalEvidence:
    """Exact, short-lived owner approval for one immutable action proposal."""

    approval_id: str
    action_id: str
    owner_id: str
    task_id: str
    turn_id: str
    connection_id: str
    provider: ConnectorProvider
    resource: ConnectorResource
    action: ConnectorActionKind
    authorization_revision: int
    authorization_snapshot_sha256: str
    approval_class: ConnectorApprovalClass
    approval_binding_sha256: str
    parameters_sha256: str
    resource_version_sha256: str | None
    approved_at: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        for field in (
            "approval_id",
            "action_id",
            "owner_id",
            "task_id",
            "turn_id",
            "connection_id",
        ):
            _uuid(getattr(self, field), field)
        _enum(self.provider, ConnectorProvider, "provider")
        _enum(self.resource, ConnectorResource, "resource")
        _enum(self.action, ConnectorActionKind, "action")
        if type(self.authorization_revision) is not int or self.authorization_revision < 1:
            raise ValueError("authorization_revision must be a positive integer")
        _sha256(
            self.authorization_snapshot_sha256,
            "authorization_snapshot_sha256",
        )
        _enum(self.approval_class, ConnectorApprovalClass, "approval_class")
        _sha256(self.approval_binding_sha256, "approval_binding_sha256")
        _sha256(self.parameters_sha256, "parameters_sha256")
        _sha256(self.resource_version_sha256, "resource_version_sha256", optional=True)
        approved = _aware(self.approved_at, "approved_at")
        expires = _aware(self.expires_at, "expires_at")
        if expires <= approved:
            raise ValueError("expires_at must be after approved_at")
        if expires - approved > timedelta(minutes=15):
            raise ValueError("approval lifetime cannot exceed 15 minutes")

    def __repr__(self) -> str:
        return (
            "ConnectedApprovalEvidence("
            f"approval_id={self.approval_id!r}, action={self.action.value!r}, "
            f"approval_class={self.approval_class.value!r}, bindings='<redacted>')"
        )


@dataclass(frozen=True, slots=True)
class ConnectedActionRequirement:
    resource: ConnectorResource
    approval_class: ConnectorApprovalClass
    mutates_external_state: bool
    persistent_permission: bool = False


@dataclass(frozen=True, slots=True)
class ConnectedActionDecision:
    kind: ConnectorDecisionKind
    reason: ConnectorDecisionReason
    action_id: str
    approval_class: ConnectorApprovalClass
    mutates_external_state: bool
    policy_version: str = _POLICY_VERSION


_MAIL = ConnectorResource.MAIL
_CALENDAR = ConnectorResource.CALENDAR
_NONE = ConnectorApprovalClass.NONE
_REVERSIBLE = ConnectorApprovalClass.EXTERNAL_WRITE_REVERSIBLE
_COMMUNICATION = ConnectorApprovalClass.EXTERNAL_COMMUNICATION
_CALENDAR_WRITE = ConnectorApprovalClass.CALENDAR_WRITE
_DESTRUCTIVE = ConnectorApprovalClass.DESTRUCTIVE
_PERSISTENT = ConnectorApprovalClass.PERSISTENT_PERMISSION


_REQUIREMENTS: dict[ConnectorActionKind, ConnectedActionRequirement] = {
    ConnectorActionKind.MAIL_SEARCH: ConnectedActionRequirement(_MAIL, _NONE, False),
    ConnectorActionKind.MAIL_LIST: ConnectedActionRequirement(_MAIL, _NONE, False),
    ConnectorActionKind.MAIL_GET: ConnectedActionRequirement(_MAIL, _NONE, False),
    ConnectorActionKind.MAIL_CREATE_DRAFT: ConnectedActionRequirement(_MAIL, _REVERSIBLE, True),
    ConnectorActionKind.MAIL_SEND: ConnectedActionRequirement(_MAIL, _COMMUNICATION, True),
    ConnectorActionKind.MAIL_REPLY: ConnectedActionRequirement(_MAIL, _COMMUNICATION, True),
    ConnectorActionKind.MAIL_FORWARD: ConnectedActionRequirement(_MAIL, _COMMUNICATION, True),
    ConnectorActionKind.MAIL_LABEL: ConnectedActionRequirement(_MAIL, _REVERSIBLE, True),
    ConnectorActionKind.MAIL_ARCHIVE: ConnectedActionRequirement(_MAIL, _REVERSIBLE, True),
    ConnectorActionKind.MAIL_TRASH: ConnectedActionRequirement(_MAIL, _DESTRUCTIVE, True),
    ConnectorActionKind.MAIL_DELETE_PERMANENT: ConnectedActionRequirement(
        _MAIL, _DESTRUCTIVE, True
    ),
    ConnectorActionKind.MAIL_CONNECT: ConnectedActionRequirement(_MAIL, _PERSISTENT, True, True),
    ConnectorActionKind.MAIL_EXPAND_SCOPES: ConnectedActionRequirement(
        _MAIL, _PERSISTENT, True, True
    ),
    ConnectorActionKind.MAIL_REGISTER_WATCH: ConnectedActionRequirement(
        _MAIL, _PERSISTENT, True, True
    ),
    ConnectorActionKind.CALENDAR_LIST: ConnectedActionRequirement(_CALENDAR, _NONE, False),
    ConnectorActionKind.CALENDAR_GET: ConnectedActionRequirement(_CALENDAR, _NONE, False),
    ConnectorActionKind.CALENDAR_FREE_BUSY: ConnectedActionRequirement(
        _CALENDAR, _NONE, False
    ),
    ConnectorActionKind.CALENDAR_CREATE: ConnectedActionRequirement(
        _CALENDAR, _CALENDAR_WRITE, True
    ),
    ConnectorActionKind.CALENDAR_UPDATE: ConnectedActionRequirement(
        _CALENDAR, _CALENDAR_WRITE, True
    ),
    ConnectorActionKind.CALENDAR_CANCEL: ConnectedActionRequirement(
        _CALENDAR, _CALENDAR_WRITE, True
    ),
    ConnectorActionKind.CALENDAR_DELETE: ConnectedActionRequirement(
        _CALENDAR, _DESTRUCTIVE, True
    ),
    ConnectorActionKind.CALENDAR_CONNECT: ConnectedActionRequirement(
        _CALENDAR, _PERSISTENT, True, True
    ),
    ConnectorActionKind.CALENDAR_EXPAND_SCOPES: ConnectedActionRequirement(
        _CALENDAR, _PERSISTENT, True, True
    ),
    ConnectorActionKind.CALENDAR_REGISTER_WATCH: ConnectedActionRequirement(
        _CALENDAR, _PERSISTENT, True, True
    ),
}


_IMPLEMENTED_RUNTIME_ACTIONS = frozenset(
    {
        ConnectorActionKind.MAIL_SEARCH,
        ConnectorActionKind.MAIL_GET,
        ConnectorActionKind.MAIL_CREATE_DRAFT,
        ConnectorActionKind.MAIL_SEND,
        ConnectorActionKind.MAIL_REPLY,
        ConnectorActionKind.CALENDAR_LIST,
        ConnectorActionKind.CALENDAR_GET,
        ConnectorActionKind.CALENDAR_FREE_BUSY,
        ConnectorActionKind.CALENDAR_CREATE,
        ConnectorActionKind.CALENDAR_UPDATE,
        ConnectorActionKind.CALENDAR_CANCEL,
    }
)


def implemented_runtime_actions() -> frozenset[ConnectorActionKind]:
    """Return the explicit provider-protocol allowlist.

    New enum members default to denied until deliberately added here and to a
    typed provider method/contract test.
    """

    return _IMPLEMENTED_RUNTIME_ACTIONS


def runtime_action_implemented(action: ConnectorActionKind) -> bool:
    if not isinstance(action, ConnectorActionKind):
        return False
    return action in _IMPLEMENTED_RUNTIME_ACTIONS


class ConnectedActionPolicy:
    """Evaluate one proposal without consulting model-authored content."""

    version = _POLICY_VERSION

    @staticmethod
    def requirement(action: ConnectorActionKind) -> ConnectedActionRequirement:
        if not isinstance(action, ConnectorActionKind):
            raise ValueError("action must be a ConnectorActionKind")
        return _REQUIREMENTS[action]

    def decide(
        self,
        intent: ConnectedActionIntent,
        *,
        grant: ConnectedTaskGrant | None,
        approval: ConnectedApprovalEvidence | None = None,
        now: datetime | None = None,
    ) -> ConnectedActionDecision:
        reference = _aware(now or datetime.now(timezone.utc), "now")
        requirement = self.requirement(intent.action)

        if requirement.resource is not intent.resource:
            return self._decision(
                intent,
                ConnectorDecisionKind.DENY,
                ConnectorDecisionReason.ACTION_RESOURCE_MISMATCH,
                requirement,
            )
        if not runtime_action_implemented(intent.action):
            return self._decision(
                intent,
                ConnectorDecisionKind.DENY,
                ConnectorDecisionReason.ACTION_NOT_IMPLEMENTED,
                requirement,
            )
        if grant is None or not self._grant_matches(intent, grant):
            return self._decision(
                intent,
                ConnectorDecisionKind.DENY,
                ConnectorDecisionReason.GRANT_BINDING_MISMATCH,
                requirement,
            )
        if grant.expires_at.astimezone(timezone.utc) <= reference:
            return self._decision(
                intent,
                ConnectorDecisionKind.DENY,
                ConnectorDecisionReason.GRANT_EXPIRED,
                requirement,
            )
        if intent.action not in grant.actions:
            return self._decision(
                intent,
                ConnectorDecisionKind.DENY,
                ConnectorDecisionReason.ACTION_NOT_GRANTED,
                requirement,
            )
        if requirement.persistent_permission:
            return self._decision(
                intent,
                ConnectorDecisionKind.DENY,
                ConnectorDecisionReason.PERSISTENT_PERMISSION_USER_REQUIRED,
                requirement,
            )
        if requirement.approval_class is ConnectorApprovalClass.NONE:
            return self._decision(
                intent,
                ConnectorDecisionKind.ALLOW,
                ConnectorDecisionReason.AUTHORIZED_READ,
                requirement,
            )
        if approval is None:
            return self._decision(
                intent,
                ConnectorDecisionKind.REQUIRE_APPROVAL,
                ConnectorDecisionReason.APPROVAL_REQUIRED,
                requirement,
            )
        if not self._approval_matches(intent, approval, requirement):
            return self._decision(
                intent,
                ConnectorDecisionKind.DENY,
                ConnectorDecisionReason.APPROVAL_BINDING_MISMATCH,
                requirement,
            )
        if approval.approved_at.astimezone(timezone.utc) > reference:
            return self._decision(
                intent,
                ConnectorDecisionKind.DENY,
                ConnectorDecisionReason.APPROVAL_NOT_YET_VALID,
                requirement,
            )
        if approval.expires_at.astimezone(timezone.utc) <= reference:
            return self._decision(
                intent,
                ConnectorDecisionKind.DENY,
                ConnectorDecisionReason.APPROVAL_EXPIRED,
                requirement,
            )
        return self._decision(
            intent,
            ConnectorDecisionKind.ALLOW,
            ConnectorDecisionReason.APPROVED_WRITE,
            requirement,
        )

    @staticmethod
    def _grant_matches(intent: ConnectedActionIntent, grant: ConnectedTaskGrant) -> bool:
        return (
            grant.owner_id == intent.owner_id
            and grant.task_id == intent.task_id
            and grant.turn_id == intent.turn_id
            and grant.connection_id == intent.connection_id
            and grant.provider is intent.provider
            and grant.resource is intent.resource
            and grant.authorization_revision == intent.authorization_revision
            and grant.authorization_snapshot_sha256
            == intent.authorization_snapshot_sha256
        )

    @staticmethod
    def _approval_matches(
        intent: ConnectedActionIntent,
        approval: ConnectedApprovalEvidence,
        requirement: ConnectedActionRequirement,
    ) -> bool:
        return (
            approval.action_id == intent.action_id
            and approval.owner_id == intent.owner_id
            and approval.task_id == intent.task_id
            and approval.turn_id == intent.turn_id
            and approval.connection_id == intent.connection_id
            and approval.provider is intent.provider
            and approval.resource is intent.resource
            and approval.action is intent.action
            and approval.authorization_revision == intent.authorization_revision
            and approval.authorization_snapshot_sha256
            == intent.authorization_snapshot_sha256
            and approval.approval_class is requirement.approval_class
            and approval.parameters_sha256 == intent.parameters_sha256
            and approval.resource_version_sha256 == intent.resource_version_sha256
            and approval.approved_at.astimezone(timezone.utc)
            >= intent.requested_at.astimezone(timezone.utc)
        )

    @staticmethod
    def _decision(
        intent: ConnectedActionIntent,
        kind: ConnectorDecisionKind,
        reason: ConnectorDecisionReason,
        requirement: ConnectedActionRequirement,
    ) -> ConnectedActionDecision:
        return ConnectedActionDecision(
            kind=kind,
            reason=reason,
            action_id=intent.action_id,
            approval_class=requirement.approval_class,
            mutates_external_state=requirement.mutates_external_state,
        )
