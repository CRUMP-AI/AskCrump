"""Durable, bounded multi-step connected mail/calendar orchestration.

Every loop is owner/session/chat/turn bound and limited to eight steps. A model
may propose one typed next operation, but database state, connection authority,
approval policy, encrypted custody, cancellation, and execution remain trusted
server boundaries. Ambiguous work becomes effect-unknown and is never blindly
retried.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from enum import StrEnum
import hashlib
import hmac
import json
import re
import secrets
from typing import Callable, Mapping, Protocol
from uuid import UUID, uuid5
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .connected_app_agent import ConnectedOperatorDisposition, ConnectedOperatorPlan
from .connected_app_contracts import (
    CalendarCancelRequest,
    CalendarGetRequest,
    CalendarUpdateRequest,
    ConnectionAuthorizationState,
    MailDraftRequest,
    MailGetRequest,
    MailReplyRequest,
)
from .connected_app_payload_envelope import ConnectedActionPayloadEnvelope
from .connected_app_policy import (
    ConnectedActionPolicy,
    ConnectorActionKind,
    ConnectorProvider,
    ConnectorResource,
    implemented_runtime_actions,
)
from .connected_app_service import ConnectedConnectionView


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_KEY_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
_MAX_STEPS = 8
_MAX_PROPOSAL_BYTES = 64 * 1024
_LOOP_NS = UUID("e327b22a-bc07-554f-bf64-aae44f93f783")
_STEP_NS = UUID("be62a7b5-0a32-53a5-95b4-61ed1ba9f6e3")
_PROPOSAL_NS = UUID("cdbfba14-95fd-5930-8dc9-d70a5765ec07")


def connected_multi_step_calendar_grounding_token(
    calendar_id: str, event_id: str
) -> str:
    """Bind an event identifier to its exact calendar without exposing either."""

    calendar = _text(calendar_id, "calendar_id", 512)
    event = _text(event_id, "event_id", 512)
    digest = hashlib.sha256(
        json.dumps(
            {"calendarId": calendar, "eventId": event},
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return f"calendar-event:{digest}"


def _uuid(value: object, name: str = "id") -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} is invalid")
    try:
        canonical = str(UUID(value))
    except (TypeError, ValueError, AttributeError):
        raise ValueError(f"{name} is invalid") from None
    if canonical != value:
        raise ValueError(f"{name} is invalid")
    return value


def _sha(value: object, name: str = "binding") -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ValueError(f"{name} is invalid")
    return value


def _aware(value: object, name: str = "timestamp") -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} is invalid")
    return value.astimezone(UTC)


def _text(value: object, name: str, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.encode("utf-8")) > maximum:
        raise ValueError(f"{name} is invalid")
    if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
        raise ValueError(f"{name} is invalid")
    return value


def _canonical(value: object) -> bytes:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError):
        raise ConnectedMultiStepError("CONNECTED_MULTI_STEP_PROPOSAL_INVALID") from None
    if not encoded or len(encoded) > _MAX_PROPOSAL_BYTES:
        raise ConnectedMultiStepError("CONNECTED_MULTI_STEP_PROPOSAL_INVALID")
    return encoded


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _unb64(value: object, minimum: int, maximum: int) -> bytes:
    if not isinstance(value, str) or not value or len(value) > maximum * 2:
        raise ConnectedMultiStepError("CONNECTED_MULTI_STEP_CUSTODY_CORRUPT")
    try:
        decoded = base64.b64decode(
            value + "=" * (-len(value) % 4), altchars=b"-_", validate=True
        )
    except (TypeError, ValueError):
        raise ConnectedMultiStepError("CONNECTED_MULTI_STEP_CUSTODY_CORRUPT") from None
    if not minimum <= len(decoded) <= maximum or _b64(decoded) != value:
        raise ConnectedMultiStepError("CONNECTED_MULTI_STEP_CUSTODY_CORRUPT")
    return decoded


def _unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


class ConnectedMultiStepError(RuntimeError):
    _CODES = frozenset(
        {
            "CONNECTED_MULTI_STEP_BUSY",
            "CONNECTED_MULTI_STEP_CANCELLED",
            "CONNECTED_MULTI_STEP_CUSTODY_CORRUPT",
            "CONNECTED_MULTI_STEP_CUSTODY_FAILED",
            "CONNECTED_MULTI_STEP_EFFECT_UNKNOWN",
            "CONNECTED_MULTI_STEP_EXPIRED",
            "CONNECTED_MULTI_STEP_FAILED",
            "CONNECTED_MULTI_STEP_INVALID",
            "CONNECTED_MULTI_STEP_LIMIT_REACHED",
            "CONNECTED_MULTI_STEP_PROPOSAL_INVALID",
            "CONNECTED_MULTI_STEP_UNAUTHORIZED",
        }
    )

    def __init__(self, code: str, *, retryable: bool = False) -> None:
        self.code = code if code in self._CODES else "CONNECTED_MULTI_STEP_FAILED"
        self.retryable = bool(retryable)
        super().__init__(self.code)


class ConnectedMultiStepStatus(StrEnum):
    ACTIVE = "active"
    WAITING_APPROVAL = "waiting_approval"
    CLARIFICATION = "clarification"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    EFFECT_UNKNOWN = "effect_unknown"
    LIMIT_REACHED = "limit_reached"


class ConnectedMultiStepState(StrEnum):
    CLAIMED = "claimed"
    INVOKED = "invoked"
    SETTLED = "settled"
    EFFECT_UNKNOWN = "effect_unknown"
    CANCELLED = "cancelled"


class ConnectedMultiStepProposalKind(StrEnum):
    COMPLETE = "complete"
    CLARIFY = "clarify"
    ACTION = "action"


class ConnectedMultiStepExecutionKind(StrEnum):
    READ_COMPLETE = "read_complete"
    PENDING_APPROVAL = "pending_approval"
    ACTION_COMPLETE = "action_complete"


_TERMINAL = frozenset(
    {
        ConnectedMultiStepStatus.CLARIFICATION,
        ConnectedMultiStepStatus.COMPLETED,
        ConnectedMultiStepStatus.FAILED,
        ConnectedMultiStepStatus.CANCELLED,
        ConnectedMultiStepStatus.EXPIRED,
        ConnectedMultiStepStatus.EFFECT_UNKNOWN,
        ConnectedMultiStepStatus.LIMIT_REACHED,
    }
)


@dataclass(frozen=True, slots=True, repr=False)
class ConnectedMultiStepStartCommand:
    loop_id: str
    owner_id: str
    session_id: str = field(repr=False)
    session_binding_sha256: str = field(repr=False)
    chat_id: str
    message_id: str
    turn_id: str
    turn_claim_token: str = field(repr=False)
    time_zone: str
    request_binding_sha256: str = field(repr=False)
    requested_at: datetime
    expires_at: datetime
    max_steps: int = _MAX_STEPS

    def __post_init__(self) -> None:
        for name in (
            "loop_id",
            "owner_id",
            "session_id",
            "chat_id",
            "message_id",
            "turn_id",
            "turn_claim_token",
        ):
            _uuid(getattr(self, name), name)
        try:
            ZoneInfo(_text(self.time_zone, "time_zone", 128))
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("time_zone is invalid") from None
        _sha(self.session_binding_sha256, "session_binding_sha256")
        _sha(self.request_binding_sha256, "request_binding_sha256")
        requested = _aware(self.requested_at, "requested_at")
        expires = _aware(self.expires_at, "expires_at")
        if expires <= requested or expires - requested > timedelta(minutes=30):
            raise ValueError("loop lifetime is invalid")
        if self.max_steps != _MAX_STEPS:
            raise ValueError("loop step limit is invalid")
        object.__setattr__(self, "requested_at", requested)
        object.__setattr__(self, "expires_at", expires)

    @classmethod
    def build(cls, **values: object) -> ConnectedMultiStepStartCommand:
        turn_id = _uuid(values["turn_id"], "turn_id")
        return cls(loop_id=str(uuid5(_LOOP_NS, turn_id)), **values)  # type: ignore[arg-type]

    def __repr__(self) -> str:
        return (
            "ConnectedMultiStepStartCommand("
            f"loop_id={self.loop_id!r}, owner_id={self.owner_id!r}, content='<redacted>')"
        )


@dataclass(frozen=True, slots=True)
class ConnectedMultiStepLoopRecord:
    loop_id: str
    owner_id: str
    session_id: str
    session_binding_sha256: str
    chat_id: str
    message_id: str
    turn_id: str
    turn_claim_token: str
    time_zone: str
    request_binding_sha256: str
    status: ConnectedMultiStepStatus
    current_step: int
    max_steps: int
    task_state_revision: int
    pending_approval_id: str | None
    last_result_reference_id: str | None
    last_result_binding_sha256: str | None
    expires_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        for name in (
            "loop_id",
            "owner_id",
            "session_id",
            "chat_id",
            "message_id",
            "turn_id",
            "turn_claim_token",
        ):
            _uuid(getattr(self, name), name)
        try:
            ZoneInfo(_text(self.time_zone, "time_zone", 128))
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("time_zone is invalid") from None
        _sha(self.session_binding_sha256, "session_binding_sha256")
        _sha(self.request_binding_sha256, "request_binding_sha256")
        if not isinstance(self.status, ConnectedMultiStepStatus):
            raise ValueError("loop status is invalid")
        if type(self.current_step) is not int or not 0 <= self.current_step <= _MAX_STEPS:
            raise ValueError("current_step is invalid")
        if self.max_steps != _MAX_STEPS:
            raise ValueError("max_steps is invalid")
        if type(self.task_state_revision) is not int or self.task_state_revision < 1:
            raise ValueError("task_state_revision is invalid")
        if self.pending_approval_id is not None:
            _uuid(self.pending_approval_id, "pending_approval_id")
        if (self.status is ConnectedMultiStepStatus.WAITING_APPROVAL) != (
            self.pending_approval_id is not None
        ):
            raise ValueError("pending approval binding is invalid")
        if (self.last_result_reference_id is None) != (
            self.last_result_binding_sha256 is None
        ):
            raise ValueError("last result binding is invalid")
        if self.last_result_reference_id is not None:
            _uuid(self.last_result_reference_id, "last_result_reference_id")
            _sha(self.last_result_binding_sha256, "last_result_binding_sha256")
        expires, updated = _aware(self.expires_at), _aware(self.updated_at)
        if updated >= expires:
            raise ValueError("loop timestamps are invalid")
        object.__setattr__(self, "expires_at", expires)
        object.__setattr__(self, "updated_at", updated)

    @property
    def terminal(self) -> bool:
        return self.status in _TERMINAL

    def public_record(self) -> ConnectedMultiStepPublicRecord:
        return ConnectedMultiStepPublicRecord(
            loop_id=self.loop_id,
            chat_id=self.chat_id,
            turn_id=self.turn_id,
            status=self.status,
            current_step=self.current_step,
            max_steps=self.max_steps,
            task_state_revision=self.task_state_revision,
            pending_approval_id=self.pending_approval_id,
            last_result_reference_id=self.last_result_reference_id,
            expires_at=self.expires_at,
            updated_at=self.updated_at,
        )

    def public(self) -> dict[str, object]:
        return self.public_record().public()


@dataclass(frozen=True, slots=True)
class ConnectedMultiStepPublicRecord:
    """Content-free owner projection safe for authenticated HTTP/UI responses."""

    loop_id: str
    chat_id: str
    turn_id: str
    status: ConnectedMultiStepStatus
    current_step: int
    max_steps: int
    task_state_revision: int
    pending_approval_id: str | None
    last_result_reference_id: str | None
    expires_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        for name in ("loop_id", "chat_id", "turn_id"):
            _uuid(getattr(self, name), name)
        if not isinstance(self.status, ConnectedMultiStepStatus):
            raise ValueError("public loop status is invalid")
        if type(self.current_step) is not int or not 0 <= self.current_step <= 8:
            raise ValueError("public loop current step is invalid")
        if self.max_steps != 8:
            raise ValueError("public loop max steps is invalid")
        if type(self.task_state_revision) is not int or self.task_state_revision < 1:
            raise ValueError("public loop revision is invalid")
        if self.pending_approval_id is not None:
            _uuid(self.pending_approval_id, "pending_approval_id")
        if (self.status is ConnectedMultiStepStatus.WAITING_APPROVAL) != (
            self.pending_approval_id is not None
        ):
            raise ValueError("public loop approval binding is invalid")
        if self.last_result_reference_id is not None:
            _uuid(self.last_result_reference_id, "last_result_reference_id")
        expires, updated = _aware(self.expires_at), _aware(self.updated_at)
        if updated >= expires:
            raise ValueError("public loop timestamps are invalid")
        object.__setattr__(self, "expires_at", expires)
        object.__setattr__(self, "updated_at", updated)

    @property
    def terminal(self) -> bool:
        return self.status in _TERMINAL

    def public(self) -> dict[str, object]:
        return {
            "loopId": self.loop_id,
            "chatId": self.chat_id,
            "turnId": self.turn_id,
            "status": self.status.value,
            "currentStep": self.current_step,
            "maxSteps": self.max_steps,
            "taskStateRevision": self.task_state_revision,
            "pendingApprovalId": self.pending_approval_id,
            "lastResultReferenceId": self.last_result_reference_id,
            "expiresAt": self.expires_at.isoformat(),
            "updatedAt": self.updated_at.isoformat(),
        }


@dataclass(frozen=True, slots=True, repr=False)
class ConnectedMultiStepObservation:
    result_reference_id: str
    result_binding_sha256: str
    summary: str = field(repr=False)
    item_count: int
    grounded_resource_ids: tuple[str, ...] = field(default=(), repr=False)

    def __post_init__(self) -> None:
        _uuid(self.result_reference_id, "result_reference_id")
        _sha(self.result_binding_sha256, "result_binding_sha256")
        _text(self.summary, "summary", 8_000)
        if type(self.item_count) is not int or not 0 <= self.item_count <= 10_000:
            raise ValueError("item_count is invalid")
        if (
            not isinstance(self.grounded_resource_ids, tuple)
            or len(self.grounded_resource_ids) > 100
            or len(set(self.grounded_resource_ids)) != len(self.grounded_resource_ids)
        ):
            raise ValueError("grounded_resource_ids is invalid")
        for value in self.grounded_resource_ids:
            _text(value, "grounded resource", 512)

    @property
    def grounding_sha256(self) -> str:
        return hashlib.sha256(
            _canonical(
                {
                    "version": "connected-multi-step-grounding-v1",
                    "resultReferenceId": self.result_reference_id,
                    "resultBindingSha256": self.result_binding_sha256,
                    "itemCount": self.item_count,
                    "groundedResourceIds": list(self.grounded_resource_ids),
                }
            )
        ).hexdigest()

    def __repr__(self) -> str:
        return (
            "ConnectedMultiStepObservation("
            f"result_reference_id={self.result_reference_id!r}, content='<redacted>')"
        )


@dataclass(frozen=True, slots=True, repr=False)
class ConnectedMultiStepPlanningContext:
    command: ConnectedMultiStepStartCommand
    step_id: str
    step_index: int
    instruction: str = field(repr=False)
    observation: ConnectedMultiStepObservation | None = field(default=None, repr=False)
    connections: tuple[ConnectedConnectionView, ...] = field(default=(), repr=False)

    def __post_init__(self) -> None:
        if type(self.command) is not ConnectedMultiStepStartCommand:
            raise ValueError("command is invalid")
        _uuid(self.step_id, "step_id")
        if type(self.step_index) is not int or not 0 <= self.step_index < _MAX_STEPS:
            raise ValueError("step_index is invalid")
        _text(self.instruction, "instruction", 12_000)
        if self.observation is not None and type(self.observation) is not ConnectedMultiStepObservation:
            raise ValueError("observation is invalid")
        if not isinstance(self.connections, tuple) or not self.connections:
            raise ValueError("connections are invalid")
        seen: set[str] = set()
        for item in self.connections:
            if not isinstance(item, ConnectedConnectionView) or item.connection_id in seen:
                raise ValueError("connections are invalid")
            seen.add(item.connection_id)
        if self.step_id != step_id(self.command.loop_id, self.step_index):
            raise ValueError("step identity is invalid")

    @property
    def planning_binding_sha256(self) -> str:
        """Bind the model attempt to exact non-authoritative context.

        The summary remains untrusted data. Its digest and opaque source
        reference make replay drift detectable, but neither can grant an
        action or select a connection.
        """

        observation = None
        if self.observation is not None:
            observation = {
                "resultReferenceId": self.observation.result_reference_id,
                "resultBindingSha256": self.observation.result_binding_sha256,
                "summarySha256": hashlib.sha256(
                    self.observation.summary.encode("utf-8")
                ).hexdigest(),
                "groundingSha256": self.observation.grounding_sha256,
            }
        connections = [
            {
                "connectionId": item.connection_id,
                "provider": item.provider.value,
                "resource": item.resource.value,
                "authorizationState": item.authorization_state.value,
                "authorizationRevision": item.authorization_revision,
                "authorizationSnapshotSha256": item.authorization_snapshot_sha256,
                "grantedActions": [action.value for action in item.granted_actions],
                "expiresAt": None if item.expires_at is None else item.expires_at.isoformat(),
            }
            for item in sorted(self.connections, key=lambda value: value.connection_id)
        ]
        return hashlib.sha256(
            _canonical(
                {
                    "version": "connected-multi-step-planning-binding-v1",
                    "loopId": self.command.loop_id,
                    "ownerId": self.command.owner_id,
                    "sessionId": self.command.session_id,
                    "sessionBindingSha256": self.command.session_binding_sha256,
                    "chatId": self.command.chat_id,
                    "messageId": self.command.message_id,
                    "turnId": self.command.turn_id,
                    "turnClaimToken": self.command.turn_claim_token,
                    "timeZone": self.command.time_zone,
                    "requestBindingSha256": self.command.request_binding_sha256,
                    "stepId": self.step_id,
                    "stepIndex": self.step_index,
                    "instructionSha256": hashlib.sha256(
                        self.instruction.encode("utf-8")
                    ).hexdigest(),
                    "observation": observation,
                    "connections": connections,
                }
            )
        ).hexdigest()

    def __repr__(self) -> str:
        return (
            "ConnectedMultiStepPlanningContext("
            f"step_id={self.step_id!r}, step_index={self.step_index}, content='<redacted>')"
        )


@dataclass(frozen=True, slots=True, repr=False)
class ConnectedMultiStepProposal:
    kind: ConnectedMultiStepProposalKind
    plan: ConnectedOperatorPlan | None = field(default=None, repr=False)
    question: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.kind, ConnectedMultiStepProposalKind):
            raise ValueError("proposal kind is invalid")
        if self.kind is ConnectedMultiStepProposalKind.ACTION:
            if type(self.plan) is not ConnectedOperatorPlan or self.question is not None:
                raise ValueError("action proposal is invalid")
            if self.plan.disposition is not ConnectedOperatorDisposition.ACTION:
                raise ValueError("multi-step schedules are unsupported")
        elif self.kind is ConnectedMultiStepProposalKind.CLARIFY:
            if self.plan is not None:
                raise ValueError("clarification proposal is invalid")
            _text(self.question, "question", 500)
        elif self.plan is not None or self.question is not None:
            raise ValueError("completion proposal is invalid")

    def to_value(self) -> dict[str, object]:
        plan = None
        if self.plan is not None:
            plan = {
                "connectionId": self.plan.connection_id,
                "provider": self.plan.provider.value,
                "resource": self.plan.resource.value,
                "action": self.plan.action.value,
                "requiresApproval": self.plan.requires_approval,
                "payload": ConnectedActionPayloadEnvelope.build(
                    action=self.plan.action, request=self.plan.request
                ).to_value(),
            }
        return {
            "version": "connected-multi-step-proposal-v1",
            "kind": self.kind.value,
            "plan": plan,
            "question": self.question,
        }

    @classmethod
    def from_value(cls, value: object) -> ConnectedMultiStepProposal:
        if type(value) is not dict or set(value) != {"version", "kind", "plan", "question"}:
            raise ValueError("proposal is invalid")
        if value["version"] != "connected-multi-step-proposal-v1":
            raise ValueError("proposal is invalid")
        kind = ConnectedMultiStepProposalKind(value["kind"])
        if kind is not ConnectedMultiStepProposalKind.ACTION:
            return cls(kind=kind, question=value["question"])
        row = value["plan"]
        if type(row) is not dict or set(row) != {
            "connectionId", "provider", "resource", "action", "requiresApproval", "payload"
        }:
            raise ValueError("proposal plan is invalid")
        envelope = ConnectedActionPayloadEnvelope.from_value(row["payload"])
        action = ConnectorActionKind(row["action"])
        if envelope.action is not action:
            raise ValueError("proposal plan is invalid")
        return cls(
            kind=kind,
            plan=ConnectedOperatorPlan(
                disposition=ConnectedOperatorDisposition.ACTION,
                connection_id=_uuid(row["connectionId"], "connection_id"),
                provider=ConnectorProvider(row["provider"]),
                resource=ConnectorResource(row["resource"]),
                action=action,
                request=envelope.request,
                schedule=None,
                requires_approval=row["requiresApproval"],
            ),
        )

    def __repr__(self) -> str:
        return f"ConnectedMultiStepProposal(kind={self.kind.value!r}, content='<redacted>')"


@dataclass(frozen=True, slots=True, repr=False)
class ConnectedMultiStepExecutionResult:
    kind: ConnectedMultiStepExecutionKind
    action_id: str | None = None
    approval_id: str | None = None
    observation: ConnectedMultiStepObservation | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.kind, ConnectedMultiStepExecutionKind):
            raise ValueError("execution kind is invalid")
        if self.action_id is not None:
            _uuid(self.action_id, "action_id")
        if self.approval_id is not None:
            _uuid(self.approval_id, "approval_id")
        if self.kind is ConnectedMultiStepExecutionKind.READ_COMPLETE:
            valid = self.action_id is not None and self.approval_id is None and self.observation is not None
        elif self.kind is ConnectedMultiStepExecutionKind.PENDING_APPROVAL:
            valid = self.action_id is not None and self.approval_id is not None and self.observation is None
        else:
            valid = self.action_id is not None and self.approval_id is None and self.observation is None
        if not valid:
            raise ValueError("execution result is invalid")


@dataclass(frozen=True, slots=True, repr=False)
class ConnectedMultiStepEnvelopeReference:
    proposal_id: str
    loop_id: str
    step_id: str
    owner_id: str
    turn_id: str
    step_index: int
    planning_binding_sha256: str = field(repr=False)
    commitment_key_id: str
    proposal_sha256: str = field(repr=False)
    binding_sha256: str = field(repr=False)
    created_at: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        for name in ("proposal_id", "loop_id", "step_id", "owner_id", "turn_id"):
            _uuid(getattr(self, name), name)
        if type(self.step_index) is not int or not 0 <= self.step_index < _MAX_STEPS:
            raise ValueError("step_index is invalid")
        _sha(self.planning_binding_sha256, "planning_binding_sha256")
        if not isinstance(self.commitment_key_id, str) or not _KEY_ID.fullmatch(
            self.commitment_key_id
        ):
            raise ValueError("commitment_key_id is invalid")
        _sha(self.proposal_sha256, "proposal_sha256")
        _sha(self.binding_sha256, "binding_sha256")
        created, expires = _aware(self.created_at), _aware(self.expires_at)
        if expires <= created or expires - created > timedelta(minutes=30):
            raise ValueError("proposal lifetime is invalid")
        object.__setattr__(self, "created_at", created)
        object.__setattr__(self, "expires_at", expires)

    def __repr__(self) -> str:
        return (
            "ConnectedMultiStepEnvelopeReference("
            f"proposal_id={self.proposal_id!r}, step_index={self.step_index}, "
            "content='<redacted>')"
        )


@dataclass(frozen=True, slots=True, repr=False)
class ConnectedMultiStepEncryptedEnvelope:
    reference: ConnectedMultiStepEnvelopeReference
    key_id: str
    wrapped_key_nonce: str = field(repr=False)
    wrapped_key_ciphertext: str = field(repr=False)
    payload_nonce: str = field(repr=False)
    payload_ciphertext: str = field(repr=False)
    record_binding_sha256: str = field(repr=False)

    def __post_init__(self) -> None:
        if type(self.reference) is not ConnectedMultiStepEnvelopeReference:
            raise ValueError("reference is invalid")
        if not isinstance(self.key_id, str) or not _KEY_ID.fullmatch(self.key_id):
            raise ValueError("key_id is invalid")
        _unb64(self.wrapped_key_nonce, 12, 12)
        _unb64(self.wrapped_key_ciphertext, 48, 80)
        _unb64(self.payload_nonce, 12, 12)
        _unb64(self.payload_ciphertext, 17, _MAX_PROPOSAL_BYTES + 16)
        _sha(self.record_binding_sha256, "record_binding_sha256")

    def __repr__(self) -> str:
        return (
            "ConnectedMultiStepEncryptedEnvelope("
            f"proposal_id={self.reference.proposal_id!r}, ciphertext='<redacted>')"
        )


@dataclass(frozen=True, slots=True, repr=False)
class ConnectedMultiStepMasterKey:
    key_id: str
    secret: bytes = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.key_id, str) or not _KEY_ID.fullmatch(self.key_id):
            raise ValueError("multi-step master key ID is invalid")
        if type(self.secret) is not bytes or len(self.secret) != 32:
            raise ValueError("multi-step master key is invalid")

    def __repr__(self) -> str:
        return f"ConnectedMultiStepMasterKey(key_id={self.key_id!r}, secret='<redacted>')"

    def __reduce__(self) -> object:
        raise TypeError("multi-step master key cannot be serialized")


@dataclass(frozen=True, slots=True, repr=False)
class ConnectedMultiStepCommitmentKey:
    key_id: str
    secret: bytes = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.key_id, str) or not _KEY_ID.fullmatch(self.key_id):
            raise ValueError("multi-step commitment key ID is invalid")
        if type(self.secret) is not bytes or len(self.secret) != 32:
            raise ValueError("multi-step commitment key is invalid")

    def __repr__(self) -> str:
        return (
            f"ConnectedMultiStepCommitmentKey(key_id={self.key_id!r}, secret='<redacted>')"
        )

    def __reduce__(self) -> object:
        raise TypeError("multi-step commitment key cannot be serialized")


class ConnectedMultiStepEnvelopeStore(Protocol):
    async def put_once(
        self, record: ConnectedMultiStepEncryptedEnvelope
    ) -> ConnectedMultiStepEncryptedEnvelope: ...

    async def read_exact(
        self, *, owner_id: str, loop_id: str, step_id: str, proposal_id: str
    ) -> ConnectedMultiStepEncryptedEnvelope | None: ...


class ConnectedMultiStepProposalVault:
    """Envelope-encrypted proposal custody, one immutable proposal per step."""

    def __init__(
        self,
        *,
        store: ConnectedMultiStepEnvelopeStore,
        master_keys: Mapping[str, ConnectedMultiStepMasterKey],
        active_master_key_id: str,
        commitment_keys: Mapping[str, ConnectedMultiStepCommitmentKey],
        active_commitment_key_id: str,
        random_bytes: Callable[[int], bytes] = secrets.token_bytes,
    ) -> None:
        if any(not callable(getattr(store, method, None)) for method in ("put_once", "read_exact")):
            raise TypeError("multi-step envelope store is invalid")
        if not callable(random_bytes):
            raise TypeError("multi-step random source is invalid")
        self._store = store
        self._master_keys = dict(master_keys)
        self._commitment_keys = dict(commitment_keys)
        self._active_master_key_id = active_master_key_id
        self._active_commitment_key_id = active_commitment_key_id
        self._random = random_bytes
        if (
            active_master_key_id not in self._master_keys
            or active_commitment_key_id not in self._commitment_keys
            or any(key_id != key.key_id for key_id, key in self._master_keys.items())
            or any(key_id != key.key_id for key_id, key in self._commitment_keys.items())
        ):
            raise ValueError("multi-step keyset is invalid")

    @staticmethod
    def _aad(reference: ConnectedMultiStepEnvelopeReference, wrapping: bool) -> bytes:
        return _canonical(
            {
                "version": (
                    "connected-multi-step-wrap-aad-v1"
                    if wrapping
                    else "connected-multi-step-payload-aad-v1"
                ),
                "referenceBindingSha256": reference.binding_sha256,
            }
        )

    @staticmethod
    def _commitment(
        key: ConnectedMultiStepCommitmentKey,
        *,
        loop_id: str,
        step_id: str,
        owner_id: str,
        step_index: int,
        plaintext: bytes,
    ) -> str:
        return hmac.new(
            key.secret,
            _canonical(
                {
                    "version": "connected-multi-step-commitment-v1",
                    "loopId": loop_id,
                    "stepId": step_id,
                    "ownerId": owner_id,
                    "stepIndex": step_index,
                }
            )
            + b"\x00"
            + plaintext,
            hashlib.sha256,
        ).hexdigest()

    async def seal(
        self,
        *,
        command: ConnectedMultiStepStartCommand,
        step_id: str,
        step_index: int,
        planning_binding_sha256: str,
        proposal: ConnectedMultiStepProposal,
        created_at: datetime,
    ) -> ConnectedMultiStepEnvelopeReference:
        if type(command) is not ConnectedMultiStepStartCommand or type(
            proposal
        ) is not ConnectedMultiStepProposal:
            raise ConnectedMultiStepError("CONNECTED_MULTI_STEP_PROPOSAL_INVALID")
        step_id = _uuid(step_id, "step_id")
        planning_binding_sha256 = _sha(planning_binding_sha256)
        created_at = _aware(created_at)
        plaintext = _canonical(proposal.to_value())
        commitment_key = self._commitment_keys[self._active_commitment_key_id]
        proposal_id = str(uuid5(_PROPOSAL_NS, step_id))
        proposal_sha256 = self._commitment(
            commitment_key,
            loop_id=command.loop_id,
            step_id=step_id,
            owner_id=command.owner_id,
            step_index=step_index,
            plaintext=plaintext,
        )
        reference_values = {
            "proposalId": proposal_id,
            "loopId": command.loop_id,
            "stepId": step_id,
            "ownerId": command.owner_id,
            "turnId": command.turn_id,
            "stepIndex": step_index,
            "planningBindingSha256": planning_binding_sha256,
            "commitmentKeyId": commitment_key.key_id,
            "proposalSha256": proposal_sha256,
            "createdAt": created_at.isoformat(),
            "expiresAt": command.expires_at.isoformat(),
        }
        reference = ConnectedMultiStepEnvelopeReference(
            proposal_id=proposal_id,
            loop_id=command.loop_id,
            step_id=step_id,
            owner_id=command.owner_id,
            turn_id=command.turn_id,
            step_index=step_index,
            planning_binding_sha256=planning_binding_sha256,
            commitment_key_id=commitment_key.key_id,
            proposal_sha256=proposal_sha256,
            binding_sha256=hashlib.sha256(
                _canonical({"version": "connected-multi-step-reference-v1", **reference_values})
            ).hexdigest(),
            created_at=created_at,
            expires_at=command.expires_at,
        )
        data_key, wrap_nonce, payload_nonce = (
            self._random(32), self._random(12), self._random(12)
        )
        if len(data_key) != 32 or len(wrap_nonce) != 12 or len(payload_nonce) != 12:
            raise ConnectedMultiStepError("CONNECTED_MULTI_STEP_CUSTODY_FAILED")
        master = self._master_keys[self._active_master_key_id]
        wrapped_key = AESGCM(master.secret).encrypt(
            wrap_nonce, data_key, self._aad(reference, True)
        )
        payload_ciphertext = AESGCM(data_key).encrypt(
            payload_nonce, plaintext, self._aad(reference, False)
        )
        values = {
            "referenceBindingSha256": reference.binding_sha256,
            "keyId": master.key_id,
            "wrappedKeyNonce": _b64(wrap_nonce),
            "wrappedKeyCiphertext": _b64(wrapped_key),
            "payloadNonce": _b64(payload_nonce),
            "payloadCiphertext": _b64(payload_ciphertext),
        }
        candidate = ConnectedMultiStepEncryptedEnvelope(
            reference=reference,
            key_id=master.key_id,
            wrapped_key_nonce=values["wrappedKeyNonce"],
            wrapped_key_ciphertext=values["wrappedKeyCiphertext"],
            payload_nonce=values["payloadNonce"],
            payload_ciphertext=values["payloadCiphertext"],
            record_binding_sha256=hashlib.sha256(
                _canonical({"version": "connected-multi-step-record-v1", **values})
            ).hexdigest(),
        )
        try:
            stored = await self._store.put_once(candidate)
        except Exception:
            stored = await self._store.read_exact(
                owner_id=command.owner_id,
                loop_id=command.loop_id,
                step_id=step_id,
                proposal_id=proposal_id,
            )
        if type(stored) is not ConnectedMultiStepEncryptedEnvelope:
            raise ConnectedMultiStepError("CONNECTED_MULTI_STEP_CUSTODY_FAILED")
        opened = self._open_record(stored, created_at)
        if (
            stored.reference != reference
            or not hmac.compare_digest(
                _canonical(opened.to_value()),
                plaintext,
            )
        ):
            raise ConnectedMultiStepError("CONNECTED_MULTI_STEP_CUSTODY_CORRUPT")
        return stored.reference

    def _open_record(
        self, record: ConnectedMultiStepEncryptedEnvelope, now: datetime
    ) -> ConnectedMultiStepProposal:
        if record.reference.expires_at <= now:
            raise ConnectedMultiStepError("CONNECTED_MULTI_STEP_EXPIRED")
        master = self._master_keys.get(record.key_id)
        commitment = self._commitment_keys.get(record.reference.commitment_key_id)
        if master is None or commitment is None:
            raise ConnectedMultiStepError("CONNECTED_MULTI_STEP_CUSTODY_FAILED")
        values = {
            "referenceBindingSha256": record.reference.binding_sha256,
            "keyId": record.key_id,
            "wrappedKeyNonce": record.wrapped_key_nonce,
            "wrappedKeyCiphertext": record.wrapped_key_ciphertext,
            "payloadNonce": record.payload_nonce,
            "payloadCiphertext": record.payload_ciphertext,
        }
        expected_record = hashlib.sha256(
            _canonical({"version": "connected-multi-step-record-v1", **values})
        ).hexdigest()
        if not hmac.compare_digest(expected_record, record.record_binding_sha256):
            raise ConnectedMultiStepError("CONNECTED_MULTI_STEP_CUSTODY_CORRUPT")
        try:
            data_key = AESGCM(master.secret).decrypt(
                _unb64(record.wrapped_key_nonce, 12, 12),
                _unb64(record.wrapped_key_ciphertext, 48, 80),
                self._aad(record.reference, True),
            )
            plaintext = AESGCM(data_key).decrypt(
                _unb64(record.payload_nonce, 12, 12),
                _unb64(record.payload_ciphertext, 17, _MAX_PROPOSAL_BYTES + 16),
                self._aad(record.reference, False),
            )
        except (InvalidTag, ValueError):
            raise ConnectedMultiStepError("CONNECTED_MULTI_STEP_CUSTODY_CORRUPT") from None
        expected = self._commitment(
            commitment,
            loop_id=record.reference.loop_id,
            step_id=record.reference.step_id,
            owner_id=record.reference.owner_id,
            step_index=record.reference.step_index,
            plaintext=plaintext,
        )
        if not hmac.compare_digest(expected, record.reference.proposal_sha256):
            raise ConnectedMultiStepError("CONNECTED_MULTI_STEP_CUSTODY_CORRUPT")
        try:
            value = json.loads(
                plaintext.decode("utf-8"),
                object_pairs_hook=_unique,
                parse_constant=lambda _value: (_ for _ in ()).throw(ValueError()),
            )
            return ConnectedMultiStepProposal.from_value(value)
        except Exception:
            raise ConnectedMultiStepError("CONNECTED_MULTI_STEP_CUSTODY_CORRUPT") from None

    async def open(
        self,
        *,
        owner_id: str,
        loop_id: str,
        step_id: str,
        proposal_id: str,
        now: datetime,
    ) -> tuple[ConnectedMultiStepEnvelopeReference, ConnectedMultiStepProposal]:
        try:
            record = await self._store.read_exact(
                owner_id=_uuid(owner_id),
                loop_id=_uuid(loop_id),
                step_id=_uuid(step_id),
                proposal_id=_uuid(proposal_id),
            )
        except Exception:
            raise ConnectedMultiStepError("CONNECTED_MULTI_STEP_CUSTODY_FAILED") from None
        if record is None:
            raise ConnectedMultiStepError("CONNECTED_MULTI_STEP_CUSTODY_FAILED")
        proposal = self._open_record(record, _aware(now))
        if (
            record.reference.owner_id != owner_id
            or record.reference.loop_id != loop_id
            or record.reference.step_id != step_id
            or record.reference.proposal_id != proposal_id
        ):
            raise ConnectedMultiStepError("CONNECTED_MULTI_STEP_CUSTODY_CORRUPT")
        return record.reference, proposal

    def __repr__(self) -> str:
        return "ConnectedMultiStepProposalVault(keys='<redacted>')"


@dataclass(frozen=True, slots=True)
class ConnectedMultiStepProposalBinding:
    """Content-free database binding for one encrypted proposal."""

    reference: ConnectedMultiStepEnvelopeReference
    kind: ConnectedMultiStepProposalKind
    connection_id: str | None = None
    provider: ConnectorProvider | None = None
    resource: ConnectorResource | None = None
    action: ConnectorActionKind | None = None
    authorization_revision: int | None = None
    authorization_snapshot_sha256: str | None = None

    def __post_init__(self) -> None:
        if type(self.reference) is not ConnectedMultiStepEnvelopeReference:
            raise ValueError("proposal reference is invalid")
        if not isinstance(self.kind, ConnectedMultiStepProposalKind):
            raise ValueError("proposal kind is invalid")
        action_values = (
            self.connection_id,
            self.provider,
            self.resource,
            self.action,
            self.authorization_revision,
            self.authorization_snapshot_sha256,
        )
        if self.kind is ConnectedMultiStepProposalKind.ACTION:
            if any(value is None for value in action_values):
                raise ValueError("action proposal binding is incomplete")
            _uuid(self.connection_id, "connection_id")
            if not isinstance(self.provider, ConnectorProvider):
                raise ValueError("provider is invalid")
            if not isinstance(self.resource, ConnectorResource):
                raise ValueError("resource is invalid")
            if not isinstance(self.action, ConnectorActionKind):
                raise ValueError("action is invalid")
            if (
                type(self.authorization_revision) is not int
                or self.authorization_revision < 1
            ):
                raise ValueError("authorization revision is invalid")
            _sha(
                self.authorization_snapshot_sha256,
                "authorization_snapshot_sha256",
            )
        elif any(value is not None for value in action_values):
            raise ValueError("non-action proposal contains authority")

    @classmethod
    def build(
        cls,
        *,
        reference: ConnectedMultiStepEnvelopeReference,
        proposal: ConnectedMultiStepProposal,
        connections: tuple[ConnectedConnectionView, ...],
    ) -> ConnectedMultiStepProposalBinding:
        if proposal.plan is None:
            return cls(reference=reference, kind=proposal.kind)
        connection = next(
            (
                item
                for item in connections
                if item.connection_id == proposal.plan.connection_id
            ),
            None,
        )
        if connection is None or connection.authorization_snapshot_sha256 is None:
            raise ConnectedMultiStepError("CONNECTED_MULTI_STEP_UNAUTHORIZED")
        return cls(
            reference=reference,
            kind=proposal.kind,
            connection_id=connection.connection_id,
            provider=connection.provider,
            resource=connection.resource,
            action=proposal.plan.action,
            authorization_revision=connection.authorization_revision,
            authorization_snapshot_sha256=connection.authorization_snapshot_sha256,
        )


@dataclass(frozen=True, slots=True)
class ConnectedMultiStepClaim:
    loop: ConnectedMultiStepLoopRecord
    step_id: str
    step_index: int
    state: ConnectedMultiStepState
    claim_request_id: str
    claim_token: str
    planning_binding_sha256: str
    lease_expires_at: datetime
    invocation_id: str | None = None
    invocation_expires_at: datetime | None = None
    proposal_id: str | None = None
    proposal_sha256: str | None = None
    proposal_binding_sha256: str | None = None
    proposal_kind: ConnectedMultiStepProposalKind | None = None
    connection_id: str | None = None
    provider: ConnectorProvider | None = None
    resource: ConnectorResource | None = None
    action: ConnectorActionKind | None = None
    authorization_revision: int | None = None
    authorization_snapshot_sha256: str | None = None
    invoke_permitted: bool = False

    def __post_init__(self) -> None:
        if type(self.loop) is not ConnectedMultiStepLoopRecord:
            raise ValueError("loop is invalid")
        for name in ("step_id", "claim_request_id", "claim_token"):
            _uuid(getattr(self, name), name)
        if type(self.step_index) is not int or not 0 <= self.step_index < _MAX_STEPS:
            raise ValueError("step_index is invalid")
        if not isinstance(self.state, ConnectedMultiStepState):
            raise ValueError("step state is invalid")
        _sha(self.planning_binding_sha256, "planning_binding_sha256")
        object.__setattr__(self, "lease_expires_at", _aware(self.lease_expires_at))
        if self.invocation_id is not None:
            _uuid(self.invocation_id, "invocation_id")
        if self.invocation_expires_at is not None:
            object.__setattr__(
                self, "invocation_expires_at", _aware(self.invocation_expires_at)
            )
        if self.proposal_id is not None:
            _uuid(self.proposal_id, "proposal_id")
        if self.proposal_sha256 is not None:
            _sha(self.proposal_sha256, "proposal_sha256")
        if self.proposal_binding_sha256 is not None:
            _sha(self.proposal_binding_sha256, "proposal_binding_sha256")
        proposal_values = (
            self.proposal_id,
            self.proposal_sha256,
            self.proposal_binding_sha256,
            self.proposal_kind,
        )
        if any(value is not None for value in proposal_values) and any(
            value is None for value in proposal_values
        ):
            raise ValueError("proposal attachment is incomplete")
        authority_values = (
            self.connection_id,
            self.provider,
            self.resource,
            self.action,
            self.authorization_revision,
            self.authorization_snapshot_sha256,
        )
        if self.proposal_kind is ConnectedMultiStepProposalKind.ACTION:
            if any(value is None for value in authority_values):
                raise ValueError("proposal authority is incomplete")
            _uuid(self.connection_id, "connection_id")
            if not isinstance(self.provider, ConnectorProvider):
                raise ValueError("proposal provider is invalid")
            if not isinstance(self.resource, ConnectorResource):
                raise ValueError("proposal resource is invalid")
            if not isinstance(self.action, ConnectorActionKind):
                raise ValueError("proposal action is invalid")
            if (
                type(self.authorization_revision) is not int
                or self.authorization_revision < 1
            ):
                raise ValueError("proposal authorization revision is invalid")
            _sha(
                self.authorization_snapshot_sha256,
                "authorization_snapshot_sha256",
            )
        elif any(value is not None for value in authority_values):
            raise ValueError("non-action proposal contains authority")
        if type(self.invoke_permitted) is not bool:
            raise ValueError("invoke_permitted is invalid")


@dataclass(frozen=True, slots=True)
class ConnectedMultiStepSettlement:
    loop: ConnectedMultiStepLoopRecord
    step_id: str
    step_index: int
    proposal_id: str
    proposal_sha256: str
    proposal_binding_sha256: str
    action_id: str | None = None
    approval_id: str | None = None
    result_reference_id: str | None = None
    result_binding_sha256: str | None = None

    def __post_init__(self) -> None:
        if type(self.loop) is not ConnectedMultiStepLoopRecord:
            raise ValueError("loop is invalid")
        for name in ("step_id", "proposal_id"):
            _uuid(getattr(self, name), name)
        if type(self.step_index) is not int or not 0 <= self.step_index < _MAX_STEPS:
            raise ValueError("step_index is invalid")
        _sha(self.proposal_sha256, "proposal_sha256")
        _sha(self.proposal_binding_sha256, "proposal_binding_sha256")
        for name in ("action_id", "approval_id", "result_reference_id"):
            if getattr(self, name) is not None:
                _uuid(getattr(self, name), name)
        if self.result_binding_sha256 is not None:
            _sha(self.result_binding_sha256, "result_binding_sha256")
        if (self.result_reference_id is None) != (self.result_binding_sha256 is None):
            raise ValueError("settlement result binding is incomplete")
        if self.loop.status is ConnectedMultiStepStatus.WAITING_APPROVAL:
            if (
                self.action_id is None
                or self.approval_id is None
                or self.result_reference_id is not None
            ):
                raise ValueError("approval settlement is invalid")
        elif self.loop.status in {
            ConnectedMultiStepStatus.ACTIVE,
            ConnectedMultiStepStatus.LIMIT_REACHED,
        }:
            if (
                self.action_id is None
                or self.result_reference_id is None
                or (
                    self.approval_id is not None
                    and self.result_reference_id != self.action_id
                )
            ):
                raise ValueError("action result settlement is invalid")
        elif any(
            value is not None
            for value in (
                self.action_id,
                self.approval_id,
                self.result_reference_id,
                self.result_binding_sha256,
            )
        ):
            raise ValueError("terminal proposal settlement contains action result")


class ConnectedMultiStepStore(Protocol):
    async def start(
        self, command: ConnectedMultiStepStartCommand
    ) -> ConnectedMultiStepLoopRecord: ...

    async def read_loop(
        self, *, owner_id: str, loop_id: str
    ) -> ConnectedMultiStepLoopRecord | None: ...

    async def list_owner(
        self, *, owner_id: str, limit: int
    ) -> tuple[ConnectedMultiStepPublicRecord, ...]: ...

    async def owner_status(
        self, *, owner_id: str, loop_id: str
    ) -> ConnectedMultiStepPublicRecord | None: ...

    async def cancel_owner(
        self,
        *,
        owner_id: str,
        loop_id: str,
        expected_revision: int,
        now: datetime,
    ) -> ConnectedMultiStepPublicRecord: ...

    async def claim(
        self,
        *,
        owner_id: str,
        loop_id: str,
        expected_step_id: str,
        expected_revision: int,
        claim_request_id: str,
        claim_token: str,
        planning_binding_sha256: str,
        now: datetime,
        lease_seconds: int,
    ) -> ConnectedMultiStepClaim: ...

    async def mark_invoked(
        self,
        *,
        claim: ConnectedMultiStepClaim,
        invocation_id: str,
        now: datetime,
        invocation_seconds: int,
    ) -> ConnectedMultiStepClaim: ...

    async def attach_proposal(
        self,
        *,
        claim: ConnectedMultiStepClaim,
        binding: ConnectedMultiStepProposalBinding,
        now: datetime,
    ) -> ConnectedMultiStepClaim: ...

    async def settle(
        self,
        *,
        claim: ConnectedMultiStepClaim,
        reference: ConnectedMultiStepEnvelopeReference,
        status: ConnectedMultiStepStatus,
        execution: ConnectedMultiStepExecutionResult | None,
        now: datetime,
    ) -> ConnectedMultiStepSettlement: ...

    async def read_step(
        self, *, owner_id: str, loop_id: str, step_id: str
    ) -> ConnectedMultiStepClaim | ConnectedMultiStepSettlement | None: ...

    async def mark_effect_unknown(
        self, *, claim: ConnectedMultiStepClaim, now: datetime
    ) -> ConnectedMultiStepLoopRecord: ...

    async def stop(
        self,
        *,
        command: ConnectedMultiStepStartCommand,
        expected_revision: int,
        status: ConnectedMultiStepStatus,
        now: datetime,
    ) -> ConnectedMultiStepLoopRecord: ...

    async def resume_approved(
        self,
        *,
        command: ConnectedMultiStepStartCommand,
        expected_revision: int,
        step_id: str,
        action_id: str,
        approval_id: str,
        result_reference_id: str,
        result_binding_sha256: str,
        now: datetime,
    ) -> ConnectedMultiStepLoopRecord: ...

    async def read_write_result(
        self,
        *,
        owner_id: str,
        loop_id: str,
        step_id: str,
        action_id: str,
        approval_id: str,
    ) -> ConnectedMultiStepObservation: ...


class ConnectedMultiStepProposer(Protocol):
    async def propose(
        self, *, context: ConnectedMultiStepPlanningContext
    ) -> ConnectedMultiStepProposal: ...


class ConnectedMultiStepExecutor(Protocol):
    async def execute_once(
        self,
        *,
        context: ConnectedMultiStepPlanningContext,
        proposal: ConnectedMultiStepProposal,
        claim: ConnectedMultiStepClaim,
    ) -> ConnectedMultiStepExecutionResult: ...


class ConnectedMultiStepObservationSource(Protocol):
    """Trusted resolver for encrypted, content-reduced tool observations."""

    async def resolve(
        self,
        *,
        owner_id: str,
        result_reference_id: str,
        result_binding_sha256: str,
    ) -> ConnectedMultiStepObservation: ...


class ConnectedMultiStepCoordinator:
    """At most one durable model continuation and one typed action per step."""

    def __init__(
        self,
        *,
        store: ConnectedMultiStepStore,
        vault: ConnectedMultiStepProposalVault,
        proposer: ConnectedMultiStepProposer,
        executor: ConnectedMultiStepExecutor,
        observations: ConnectedMultiStepObservationSource,
        require_ready: Callable[[], None],
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        lease_seconds: int = 30,
        invocation_seconds: int = 60,
    ) -> None:
        for value, methods, name in (
            (
                store,
                (
                    "start",
                    "read_loop",
                    "claim",
                    "mark_invoked",
                    "attach_proposal",
                    "settle",
                    "read_step",
                    "mark_effect_unknown",
                    "stop",
                    "resume_approved",
                ),
                "store",
            ),
            (vault, ("seal", "open"), "vault"),
            (proposer, ("propose",), "proposer"),
            (executor, ("execute_once",), "executor"),
            (observations, ("resolve",), "observation source"),
        ):
            if any(not callable(getattr(value, method, None)) for method in methods):
                raise TypeError(f"multi-step {name} is invalid")
        if not callable(require_ready) or not callable(now):
            raise TypeError("multi-step readiness boundary is invalid")
        if not 5 <= lease_seconds <= 120 or not 5 <= invocation_seconds <= 120:
            raise ValueError("multi-step lease is invalid")
        self._store, self._vault = store, vault
        self._proposer, self._executor = proposer, executor
        self._observations = observations
        self._require_ready, self._now = require_ready, now
        self._lease_seconds, self._invocation_seconds = lease_seconds, invocation_seconds

    @staticmethod
    def _loop_matches(
        command: ConnectedMultiStepStartCommand,
        loop: ConnectedMultiStepLoopRecord,
    ) -> bool:
        return bool(
            loop.loop_id == command.loop_id
            and loop.owner_id == command.owner_id
            and loop.session_id == command.session_id
            and hmac.compare_digest(
                loop.session_binding_sha256,
                command.session_binding_sha256,
            )
            and loop.chat_id == command.chat_id
            and loop.message_id == command.message_id
            and loop.turn_id == command.turn_id
            and loop.turn_claim_token == command.turn_claim_token
            and loop.time_zone == command.time_zone
            and hmac.compare_digest(
                loop.request_binding_sha256,
                command.request_binding_sha256,
            )
            and loop.max_steps == command.max_steps
            and loop.expires_at == command.expires_at
        )

    @staticmethod
    def _authority(
        plan: ConnectedOperatorPlan,
        connections: tuple[ConnectedConnectionView, ...],
        now: datetime,
    ) -> ConnectedConnectionView:
        connection = next(
            (item for item in connections if item.connection_id == plan.connection_id), None
        )
        if (
            plan.action not in implemented_runtime_actions()
            or connection is None
            or connection.authorization_state is not ConnectionAuthorizationState.ACTIVE
            or connection.provider is not plan.provider
            or connection.resource is not plan.resource
            or plan.action not in connection.granted_actions
            or connection.authorization_revision < 1
            or connection.authorization_snapshot_sha256 is None
            or connection.expires_at is None
            or connection.expires_at <= now
            or ConnectedActionPolicy.requirement(plan.action).resource is not plan.resource
        ):
            raise ConnectedMultiStepError("CONNECTED_MULTI_STEP_UNAUTHORIZED")
        return connection

    @staticmethod
    def _ground_continuation_proposal(
        proposal: ConnectedMultiStepProposal,
        observation: ConnectedMultiStepObservation | None,
    ) -> ConnectedMultiStepProposal:
        """Fence opaque continuation targets to the prior structured result.

        The first step is grounded in the user's request.  Later message/event
        identifiers must have appeared in the database-opened structured tool
        result; untrusted bodies and model guesses can never widen that set.
        """

        if observation is None or proposal.plan is None:
            return proposal
        request = proposal.plan.request
        required: tuple[str, ...] = ()
        if type(request) is MailGetRequest:
            required = (request.message_id,)
        elif type(request) in {MailDraftRequest, MailReplyRequest}:
            message_id = request.spec.reply_to_message_id
            required = () if message_id is None else (message_id,)
        elif type(request) in {CalendarGetRequest, CalendarCancelRequest}:
            required = (
                request.calendar_id,
                request.event_id,
                connected_multi_step_calendar_grounding_token(
                    request.calendar_id,
                    request.event_id,
                ),
            )
        elif type(request) is CalendarUpdateRequest:
            event_id = request.spec.source_event_id
            if event_id is not None:
                required = (
                    request.spec.calendar_id,
                    event_id,
                    connected_multi_step_calendar_grounding_token(
                        request.spec.calendar_id,
                        event_id,
                    ),
                )
        grounded = frozenset(observation.grounded_resource_ids)
        if all(value in grounded for value in required):
            return proposal
        return ConnectedMultiStepProposal(
            kind=ConnectedMultiStepProposalKind.CLARIFY,
            question=(
                "Please choose a message or calendar event from the results I just found."
            ),
        )

    @staticmethod
    def _status(
        claim: ConnectedMultiStepClaim,
        proposal: ConnectedMultiStepProposal,
        execution: ConnectedMultiStepExecutionResult | None,
    ) -> ConnectedMultiStepStatus:
        if proposal.kind is ConnectedMultiStepProposalKind.COMPLETE:
            return ConnectedMultiStepStatus.COMPLETED
        if proposal.kind is ConnectedMultiStepProposalKind.CLARIFY:
            return ConnectedMultiStepStatus.CLARIFICATION
        if proposal.plan is None or execution is None:
            raise ConnectedMultiStepError("CONNECTED_MULTI_STEP_INVALID")
        mutates = ConnectedActionPolicy.requirement(proposal.plan.action).mutates_external_state
        if mutates:
            if execution.kind is not ConnectedMultiStepExecutionKind.PENDING_APPROVAL:
                raise ConnectedMultiStepError("CONNECTED_MULTI_STEP_UNAUTHORIZED")
            return ConnectedMultiStepStatus.WAITING_APPROVAL
        if execution.kind is not ConnectedMultiStepExecutionKind.READ_COMPLETE:
            raise ConnectedMultiStepError("CONNECTED_MULTI_STEP_INVALID")
        if claim.step_index + 1 >= _MAX_STEPS:
            return ConnectedMultiStepStatus.LIMIT_REACHED
        return ConnectedMultiStepStatus.ACTIVE

    @staticmethod
    def _context(
        *,
        command: ConnectedMultiStepStartCommand,
        loop: ConnectedMultiStepLoopRecord,
        instruction: str,
        observation: ConnectedMultiStepObservation | None,
        connections: tuple[ConnectedConnectionView, ...],
    ) -> ConnectedMultiStepPlanningContext:
        if (loop.last_result_reference_id is None) != (observation is None):
            raise ConnectedMultiStepError("CONNECTED_MULTI_STEP_INVALID")
        if observation is not None and (
            observation.result_reference_id != loop.last_result_reference_id
            or not hmac.compare_digest(
                observation.result_binding_sha256,
                loop.last_result_binding_sha256 or "",
            )
        ):
            raise ConnectedMultiStepError("CONNECTED_MULTI_STEP_UNAUTHORIZED")
        return ConnectedMultiStepPlanningContext(
            command=command,
            step_id=step_id(command.loop_id, loop.current_step),
            step_index=loop.current_step,
            instruction=instruction,
            observation=observation,
            connections=connections,
        )

    @staticmethod
    def _attachment_matches(
        claim: ConnectedMultiStepClaim,
        binding: ConnectedMultiStepProposalBinding,
    ) -> bool:
        reference = binding.reference
        return bool(
            claim.proposal_id == reference.proposal_id
            and hmac.compare_digest(
                claim.proposal_sha256 or "",
                reference.proposal_sha256,
            )
            and hmac.compare_digest(
                claim.proposal_binding_sha256 or "",
                reference.binding_sha256,
            )
            and claim.proposal_kind is binding.kind
            and claim.connection_id == binding.connection_id
            and claim.provider is binding.provider
            and claim.resource is binding.resource
            and claim.action is binding.action
            and claim.authorization_revision == binding.authorization_revision
            and (
                claim.authorization_snapshot_sha256
                == binding.authorization_snapshot_sha256
            )
        )

    @staticmethod
    def _settlement_matches(
        command: ConnectedMultiStepStartCommand,
        claim: ConnectedMultiStepClaim,
        reference: ConnectedMultiStepEnvelopeReference,
        settled: object,
    ) -> bool:
        return bool(
            type(settled) is ConnectedMultiStepSettlement
            and ConnectedMultiStepCoordinator._loop_matches(command, settled.loop)
            and settled.step_id == claim.step_id
            and settled.step_index == claim.step_index
            and settled.proposal_id == reference.proposal_id
            and hmac.compare_digest(
                settled.proposal_sha256,
                reference.proposal_sha256,
            )
            and hmac.compare_digest(
                settled.proposal_binding_sha256,
                reference.binding_sha256,
            )
        )

    async def _read_loop(
        self, command: ConnectedMultiStepStartCommand
    ) -> ConnectedMultiStepLoopRecord | None:
        try:
            value = await self._store.read_loop(
                owner_id=command.owner_id,
                loop_id=command.loop_id,
            )
        except Exception:
            return None
        if value is not None and (
            type(value) is not ConnectedMultiStepLoopRecord
            or not self._loop_matches(command, value)
        ):
            raise ConnectedMultiStepError("CONNECTED_MULTI_STEP_EFFECT_UNKNOWN")
        return value

    async def status(
        self, *, command: ConnectedMultiStepStartCommand
    ) -> ConnectedMultiStepLoopRecord:
        """Read one exact owner/session/chat/turn-bound loop without advancing it."""

        if type(command) is not ConnectedMultiStepStartCommand:
            raise ConnectedMultiStepError("CONNECTED_MULTI_STEP_INVALID")
        value = await self._read_loop(command)
        if value is None:
            raise ConnectedMultiStepError("CONNECTED_MULTI_STEP_INVALID")
        return value

    async def list_owner(
        self, *, owner_id: str, limit: int = 50
    ) -> tuple[ConnectedMultiStepPublicRecord, ...]:
        """Return only content-free control-plane rows for the authenticated owner."""

        try:
            owner = _uuid(owner_id, "owner_id")
        except ValueError:
            raise ConnectedMultiStepError("CONNECTED_MULTI_STEP_INVALID") from None
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ConnectedMultiStepError("CONNECTED_MULTI_STEP_INVALID")
        method = getattr(self._store, "list_owner", None)
        if not callable(method):
            raise ConnectedMultiStepError("CONNECTED_MULTI_STEP_FAILED", retryable=True)
        try:
            value = await method(owner_id=owner, limit=limit)
        except Exception:
            raise ConnectedMultiStepError(
                "CONNECTED_MULTI_STEP_FAILED", retryable=True
            ) from None
        if (
            not isinstance(value, tuple)
            or len(value) > limit
            or any(type(item) is not ConnectedMultiStepPublicRecord for item in value)
        ):
            raise ConnectedMultiStepError("CONNECTED_MULTI_STEP_EFFECT_UNKNOWN")
        return value

    async def owner_status(
        self, *, owner_id: str, loop_id: str
    ) -> ConnectedMultiStepPublicRecord:
        """Read the safe owner projection without exposing execution bindings."""

        try:
            owner, loop = _uuid(owner_id, "owner_id"), _uuid(loop_id, "loop_id")
        except ValueError:
            raise ConnectedMultiStepError("CONNECTED_MULTI_STEP_INVALID") from None
        method = getattr(self._store, "owner_status", None)
        if not callable(method):
            raise ConnectedMultiStepError("CONNECTED_MULTI_STEP_FAILED", retryable=True)
        try:
            value = await method(owner_id=owner, loop_id=loop)
        except Exception:
            raise ConnectedMultiStepError(
                "CONNECTED_MULTI_STEP_FAILED", retryable=True
            ) from None
        if type(value) is not ConnectedMultiStepPublicRecord or value.loop_id != loop:
            raise ConnectedMultiStepError("CONNECTED_MULTI_STEP_INVALID")
        return value

    async def cancel_owner(
        self,
        *,
        owner_id: str,
        loop_id: str,
        expected_revision: int,
    ) -> ConnectedMultiStepPublicRecord:
        """Atomically cancel only the exact owner loop revision."""

        try:
            owner, loop = _uuid(owner_id, "owner_id"), _uuid(loop_id, "loop_id")
        except ValueError:
            raise ConnectedMultiStepError("CONNECTED_MULTI_STEP_INVALID") from None
        if type(expected_revision) is not int or expected_revision < 1:
            raise ConnectedMultiStepError("CONNECTED_MULTI_STEP_INVALID")
        method = getattr(self._store, "cancel_owner", None)
        if not callable(method):
            raise ConnectedMultiStepError("CONNECTED_MULTI_STEP_FAILED", retryable=True)
        try:
            value = await method(
                owner_id=owner,
                loop_id=loop,
                expected_revision=expected_revision,
                now=_aware(self._now()),
            )
        except Exception:
            raise ConnectedMultiStepError(
                "CONNECTED_MULTI_STEP_FAILED", retryable=True
            ) from None
        if (
            type(value) is not ConnectedMultiStepPublicRecord
            or value.loop_id != loop
            or value.status is not ConnectedMultiStepStatus.CANCELLED
            or value.task_state_revision not in {
                expected_revision,
                expected_revision + 1,
            }
        ):
            raise ConnectedMultiStepError("CONNECTED_MULTI_STEP_EFFECT_UNKNOWN")
        return value

    async def _effect_unknown(
        self,
        claim: ConnectedMultiStepClaim,
        now: datetime,
    ) -> None:
        try:
            await self._store.mark_effect_unknown(claim=claim, now=now)
        except Exception:
            pass

    async def _expire(
        self,
        command: ConnectedMultiStepStartCommand,
        loop: ConnectedMultiStepLoopRecord,
        now: datetime,
    ) -> ConnectedMultiStepLoopRecord:
        try:
            value = await self._store.stop(
                command=command,
                expected_revision=loop.task_state_revision,
                status=ConnectedMultiStepStatus.EXPIRED,
                now=now,
            )
        except Exception:
            value = await self._read_loop(command)
        if (
            type(value) is not ConnectedMultiStepLoopRecord
            or not self._loop_matches(command, value)
            or value.status is not ConnectedMultiStepStatus.EXPIRED
        ):
            raise ConnectedMultiStepError("CONNECTED_MULTI_STEP_EFFECT_UNKNOWN")
        return value

    async def run_once(
        self,
        *,
        command: ConnectedMultiStepStartCommand,
        instruction: str,
        observation: ConnectedMultiStepObservation | None,
        connections: tuple[ConnectedConnectionView, ...],
        wake_id: str,
    ) -> ConnectedMultiStepSettlement | ConnectedMultiStepLoopRecord:
        if type(command) is not ConnectedMultiStepStartCommand:
            raise ConnectedMultiStepError("CONNECTED_MULTI_STEP_INVALID")
        instruction, wake_id = _text(instruction, "instruction", 12_000), _uuid(wake_id)
        try:
            self._require_ready()
        except Exception:
            raise ConnectedMultiStepError("CONNECTED_MULTI_STEP_FAILED", retryable=True) from None
        now = _aware(self._now())
        try:
            loop = await self._store.start(command)
        except Exception:
            loop = await self._read_loop(command)
        if (
            type(loop) is not ConnectedMultiStepLoopRecord
            or not self._loop_matches(command, loop)
        ):
            raise ConnectedMultiStepError("CONNECTED_MULTI_STEP_EFFECT_UNKNOWN")
        if loop.terminal or loop.status is ConnectedMultiStepStatus.WAITING_APPROVAL:
            return loop
        if now >= command.expires_at or now >= loop.expires_at:
            return await self._expire(command, loop, now)
        context = self._context(
            command=command,
            loop=loop,
            instruction=instruction,
            observation=observation,
            connections=connections,
        )
        claim_request_id = wake_id
        claim_token = str(uuid5(_STEP_NS, f"{context.step_id}:{wake_id}:claim"))
        try:
            claim = await self._store.claim(
                owner_id=command.owner_id,
                loop_id=command.loop_id,
                expected_step_id=context.step_id,
                expected_revision=loop.task_state_revision,
                claim_request_id=claim_request_id,
                claim_token=claim_token,
                planning_binding_sha256=context.planning_binding_sha256,
                now=now,
                lease_seconds=self._lease_seconds,
            )
        except Exception:
            claim = await self._store.read_step(
                owner_id=command.owner_id,
                loop_id=command.loop_id,
                step_id=context.step_id,
            )
        if type(claim) is ConnectedMultiStepSettlement:
            if not self._loop_matches(command, claim.loop):
                raise ConnectedMultiStepError("CONNECTED_MULTI_STEP_EFFECT_UNKNOWN")
            return claim
        if (
            type(claim) is not ConnectedMultiStepClaim
            or not self._loop_matches(command, claim.loop)
            or claim.step_id != context.step_id
            or claim.step_index != context.step_index
            or not hmac.compare_digest(
                claim.planning_binding_sha256,
                context.planning_binding_sha256,
            )
        ):
            raise ConnectedMultiStepError("CONNECTED_MULTI_STEP_EFFECT_UNKNOWN")
        if claim.state is ConnectedMultiStepState.EFFECT_UNKNOWN:
            raise ConnectedMultiStepError("CONNECTED_MULTI_STEP_EFFECT_UNKNOWN")
        if claim.state is ConnectedMultiStepState.CANCELLED:
            raise ConnectedMultiStepError("CONNECTED_MULTI_STEP_CANCELLED")

        proposal: ConnectedMultiStepProposal | None = None
        reference: ConnectedMultiStepEnvelopeReference | None = None
        if claim.state is ConnectedMultiStepState.INVOKED:
            if claim.proposal_id is not None:
                reference, proposal = await self._vault.open(
                    owner_id=command.owner_id,
                    loop_id=command.loop_id,
                    step_id=claim.step_id,
                    proposal_id=claim.proposal_id,
                    now=now,
                )
                binding = ConnectedMultiStepProposalBinding.build(
                    reference=reference,
                    proposal=proposal,
                    connections=connections,
                )
                if not self._attachment_matches(claim, binding):
                    raise ConnectedMultiStepError("CONNECTED_MULTI_STEP_EFFECT_UNKNOWN")
            elif claim.invocation_expires_at and claim.invocation_expires_at > now:
                raise ConnectedMultiStepError("CONNECTED_MULTI_STEP_BUSY", retryable=True)
            else:
                await self._effect_unknown(claim, now)
                raise ConnectedMultiStepError("CONNECTED_MULTI_STEP_EFFECT_UNKNOWN")
        else:
            invocation_id = str(
                uuid5(_STEP_NS, f"{claim.step_id}:{claim.claim_token}:invocation")
            )
            try:
                invoked = await self._store.mark_invoked(
                    claim=claim,
                    invocation_id=invocation_id,
                    now=now,
                    invocation_seconds=self._invocation_seconds,
                )
            except Exception:
                invoked = await self._store.read_step(
                    owner_id=command.owner_id,
                    loop_id=command.loop_id,
                    step_id=claim.step_id,
                )
            if type(invoked) is not ConnectedMultiStepClaim:
                raise ConnectedMultiStepError("CONNECTED_MULTI_STEP_EFFECT_UNKNOWN")
            # A committed mark-invoked whose response was lost must not strand the
            # exact winner behind the normal read projection's invoke_permitted=false
            # value.  Recovery is limited to the same deterministic invocation and
            # its still-live lease; a sibling or expired invocation remains fenced.
            if (
                not invoked.invoke_permitted
                and invoked.state is ConnectedMultiStepState.INVOKED
                and invoked.invocation_id == invocation_id
                and invoked.invocation_expires_at is not None
                and invoked.invocation_expires_at > now
            ):
                invoked = replace(invoked, invoke_permitted=True)
            if not invoked.invoke_permitted:
                raise ConnectedMultiStepError("CONNECTED_MULTI_STEP_BUSY", retryable=True)
            claim = invoked
            try:
                proposal = await self._proposer.propose(context=context)
                if type(proposal) is not ConnectedMultiStepProposal:
                    raise TypeError("invalid proposal")
                proposal = self._ground_continuation_proposal(proposal, observation)
                if proposal.plan is not None:
                    self._authority(proposal.plan, connections, now)
                reference = await self._vault.seal(
                    command=command,
                    step_id=claim.step_id,
                    step_index=claim.step_index,
                    planning_binding_sha256=claim.planning_binding_sha256,
                    proposal=proposal,
                    created_at=now,
                )
                binding = ConnectedMultiStepProposalBinding.build(
                    reference=reference,
                    proposal=proposal,
                    connections=connections,
                )
                try:
                    attached = await self._store.attach_proposal(
                        claim=claim,
                        binding=binding,
                        now=now,
                    )
                except Exception:
                    attached = await self._store.read_step(
                        owner_id=command.owner_id,
                        loop_id=command.loop_id,
                        step_id=claim.step_id,
                    )
                if (
                    type(attached) is not ConnectedMultiStepClaim
                    or not self._attachment_matches(attached, binding)
                ):
                    raise ConnectedMultiStepError("CONNECTED_MULTI_STEP_EFFECT_UNKNOWN")
                claim = attached
            except Exception:
                await self._effect_unknown(claim, now)
                raise ConnectedMultiStepError("CONNECTED_MULTI_STEP_EFFECT_UNKNOWN") from None
        assert proposal is not None and reference is not None
        execution = None
        if proposal.plan is not None:
            self._authority(proposal.plan, connections, now)
            try:
                self._require_ready()
                execution = await self._executor.execute_once(
                    context=context,
                    proposal=proposal,
                    claim=claim,
                )
            except Exception:
                await self._effect_unknown(claim, now)
                raise ConnectedMultiStepError("CONNECTED_MULTI_STEP_EFFECT_UNKNOWN") from None
            if type(execution) is not ConnectedMultiStepExecutionResult:
                await self._effect_unknown(claim, now)
                raise ConnectedMultiStepError("CONNECTED_MULTI_STEP_EFFECT_UNKNOWN")
        status = self._status(claim, proposal, execution)
        try:
            settled = await self._store.settle(
                claim=claim,
                reference=reference,
                status=status,
                execution=execution,
                now=_aware(self._now()),
            )
        except Exception:
            settled = await self._store.read_step(
                owner_id=command.owner_id,
                loop_id=command.loop_id,
                step_id=claim.step_id,
            )
        if not self._settlement_matches(command, claim, reference, settled):
            raise ConnectedMultiStepError("CONNECTED_MULTI_STEP_EFFECT_UNKNOWN")
        return settled

    async def _resolve_last_observation(
        self,
        *,
        command: ConnectedMultiStepStartCommand,
        loop: ConnectedMultiStepLoopRecord,
    ) -> ConnectedMultiStepObservation:
        """Resolve either encrypted read data or a database-authored write receipt."""

        reference = loop.last_result_reference_id
        binding = loop.last_result_binding_sha256
        if reference is None or binding is None:
            raise ConnectedMultiStepError("CONNECTED_MULTI_STEP_EFFECT_UNKNOWN")
        try:
            observation = await self._observations.resolve(
                owner_id=command.owner_id,
                result_reference_id=reference,
                result_binding_sha256=binding,
            )
        except Exception:
            observation = None
        if observation is None:
            prior_index = loop.current_step - 1
            prior = None
            if prior_index >= 0:
                try:
                    prior = await self._store.read_step(
                        owner_id=command.owner_id,
                        loop_id=command.loop_id,
                        step_id=step_id(command.loop_id, prior_index),
                    )
                except Exception:
                    prior = None
            method = getattr(self._store, "read_write_result", None)
            if (
                type(prior) is not ConnectedMultiStepSettlement
                or not self._loop_matches(command, prior.loop)
                or prior.step_index != prior_index
                or prior.action_id != reference
                or prior.approval_id is None
                or prior.result_reference_id != reference
                or not hmac.compare_digest(
                    prior.result_binding_sha256 or "",
                    binding,
                )
                or not callable(method)
            ):
                raise ConnectedMultiStepError(
                    "CONNECTED_MULTI_STEP_FAILED", retryable=True
                )
            try:
                observation = await method(
                    owner_id=command.owner_id,
                    loop_id=command.loop_id,
                    step_id=prior.step_id,
                    action_id=prior.action_id,
                    approval_id=prior.approval_id,
                )
            except Exception:
                raise ConnectedMultiStepError(
                    "CONNECTED_MULTI_STEP_FAILED", retryable=True
                ) from None
        if (
            type(observation) is not ConnectedMultiStepObservation
            or observation.result_reference_id != reference
            or not hmac.compare_digest(
                observation.result_binding_sha256,
                binding,
            )
        ):
            raise ConnectedMultiStepError("CONNECTED_MULTI_STEP_EFFECT_UNKNOWN")
        return observation

    async def run_until_stop(
        self,
        *,
        command: ConnectedMultiStepStartCommand,
        instruction: str,
        connections: tuple[ConnectedConnectionView, ...],
        wake_id: str,
    ) -> ConnectedMultiStepSettlement | ConnectedMultiStepLoopRecord:
        """Continue bounded reads until a clean stop state is reached."""

        observation = None
        wake_id = _uuid(wake_id, "wake_id")
        for offset in range(_MAX_STEPS):
            loop = await self._read_loop(command)
            if loop is not None and loop.last_result_reference_id is not None:
                observation = await self._resolve_last_observation(
                    command=command,
                    loop=loop,
                )
            result = await self.run_once(
                command=command,
                instruction=instruction,
                observation=observation,
                connections=connections,
                wake_id=str(uuid5(_STEP_NS, f"{wake_id}:{offset}")),
            )
            loop = result.loop if isinstance(result, ConnectedMultiStepSettlement) else result
            if loop.status is not ConnectedMultiStepStatus.ACTIVE:
                return result
            observation = None
        raise ConnectedMultiStepError("CONNECTED_MULTI_STEP_LIMIT_REACHED")

    async def cancel(
        self,
        *,
        command: ConnectedMultiStepStartCommand,
    ) -> ConnectedMultiStepLoopRecord:
        if type(command) is not ConnectedMultiStepStartCommand:
            raise ConnectedMultiStepError("CONNECTED_MULTI_STEP_INVALID")
        loop = await self._read_loop(command)
        if loop is None:
            raise ConnectedMultiStepError("CONNECTED_MULTI_STEP_INVALID")
        if loop.terminal:
            return loop
        try:
            result = await self._store.stop(
                command=command,
                expected_revision=loop.task_state_revision,
                status=ConnectedMultiStepStatus.CANCELLED,
                now=_aware(self._now()),
            )
        except Exception:
            result = await self._read_loop(command)
        if (
            type(result) is not ConnectedMultiStepLoopRecord
            or not self._loop_matches(command, result)
            or result.status is not ConnectedMultiStepStatus.CANCELLED
        ):
            raise ConnectedMultiStepError("CONNECTED_MULTI_STEP_EFFECT_UNKNOWN")
        return result

    async def resume_after_approval(
        self,
        *,
        command: ConnectedMultiStepStartCommand,
        step_id: str,
        action_id: str,
        approval_id: str,
        observation: ConnectedMultiStepObservation,
    ) -> ConnectedMultiStepLoopRecord:
        """Resume only after the database proves a fresh approval was consumed."""

        if (
            type(command) is not ConnectedMultiStepStartCommand
            or type(observation) is not ConnectedMultiStepObservation
        ):
            raise ConnectedMultiStepError("CONNECTED_MULTI_STEP_INVALID")
        loop = await self._read_loop(command)
        if loop is None or loop.status is not ConnectedMultiStepStatus.WAITING_APPROVAL:
            raise ConnectedMultiStepError("CONNECTED_MULTI_STEP_INVALID")
        if loop.pending_approval_id != _uuid(approval_id, "approval_id"):
            raise ConnectedMultiStepError("CONNECTED_MULTI_STEP_UNAUTHORIZED")
        try:
            result = await self._store.resume_approved(
                command=command,
                expected_revision=loop.task_state_revision,
                step_id=_uuid(step_id, "step_id"),
                action_id=_uuid(action_id, "action_id"),
                approval_id=approval_id,
                result_reference_id=observation.result_reference_id,
                result_binding_sha256=observation.result_binding_sha256,
                now=_aware(self._now()),
            )
        except Exception:
            result = await self._read_loop(command)
        if (
            type(result) is not ConnectedMultiStepLoopRecord
            or not self._loop_matches(command, result)
            or result.status
            not in {ConnectedMultiStepStatus.ACTIVE, ConnectedMultiStepStatus.LIMIT_REACHED}
            or result.last_result_reference_id != observation.result_reference_id
            or not hmac.compare_digest(
                result.last_result_binding_sha256 or "",
                observation.result_binding_sha256,
            )
        ):
            raise ConnectedMultiStepError("CONNECTED_MULTI_STEP_EFFECT_UNKNOWN")
        return result

    async def resume_from_approved_action(
        self,
        *,
        command: ConnectedMultiStepStartCommand,
        step_id: str,
        action_id: str,
        approval_id: str,
    ) -> ConnectedMultiStepLoopRecord:
        """Resolve the database-authored write receipt before resuming the loop."""

        if type(command) is not ConnectedMultiStepStartCommand:
            raise ConnectedMultiStepError("CONNECTED_MULTI_STEP_INVALID")
        try:
            step, action, approval = (
                _uuid(step_id, "step_id"),
                _uuid(action_id, "action_id"),
                _uuid(approval_id, "approval_id"),
            )
        except ValueError:
            raise ConnectedMultiStepError("CONNECTED_MULTI_STEP_INVALID") from None
        method = getattr(self._store, "read_write_result", None)
        if not callable(method):
            raise ConnectedMultiStepError("CONNECTED_MULTI_STEP_FAILED", retryable=True)
        try:
            observation = await method(
                owner_id=command.owner_id,
                loop_id=command.loop_id,
                step_id=step,
                action_id=action,
                approval_id=approval,
            )
        except Exception:
            raise ConnectedMultiStepError(
                "CONNECTED_MULTI_STEP_FAILED", retryable=True
            ) from None
        if (
            type(observation) is not ConnectedMultiStepObservation
            or observation.result_reference_id != action
        ):
            raise ConnectedMultiStepError("CONNECTED_MULTI_STEP_EFFECT_UNKNOWN")
        return await self.resume_after_approval(
            command=command,
            step_id=step,
            action_id=action,
            approval_id=approval,
            observation=observation,
        )

    def __repr__(self) -> str:
        return "ConnectedMultiStepCoordinator(dependencies='<redacted>')"


def step_id(loop_id: str, step_index: int) -> str:
    loop_id = _uuid(loop_id, "loop_id")
    if type(step_index) is not int or not 0 <= step_index < _MAX_STEPS:
        raise ValueError("step_index is invalid")
    return str(uuid5(_STEP_NS, f"{loop_id}:{step_index}"))


__all__ = [name for name in globals() if name.startswith("ConnectedMultiStep")] + ["step_id"]
