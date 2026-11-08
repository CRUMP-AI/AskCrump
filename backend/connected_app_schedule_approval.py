"""Durable fresh-per-occurrence approval for connected schedules.

The schedule worker may poll an occurrence across several short claims.  This
module keeps the action and approval identities stable for that occurrence,
stores only opaque IDs and keyed commitments in Postgres, and keeps the exact
mail/calendar preview encrypted in the existing payload vault.  It never
turns a schedule-level preference into write authority: every external write
still needs a distinct, unexpired owner decision.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Protocol
from uuid import UUID, uuid5

from .connected_app_action_preparation import (
    action_preparation_approval_binding_sha256,
)
from .connected_app_contracts import (
    CalendarCancelRequest,
    CalendarCreateRequest,
    CalendarUpdateRequest,
    EventSnapshot,
    MailDraftRequest,
    MailReplyRequest,
    MailSendRequest,
)
from .connected_app_payload_envelope import ConnectedActionPayloadEnvelope
from .connected_app_payload_vault import ConnectedPayloadVault
from .connected_app_policy import (
    ConnectedActionIntent,
    ConnectedActionPolicy,
    ConnectedApprovalEvidence,
    ConnectorActionKind,
    ConnectorApprovalClass,
    ConnectorProvider,
    ConnectorResource,
)
from .connected_app_review_resolution import ConnectedApprovalReviewEnvelope
from .connected_app_scheduler import ConnectedScheduleClaim, ConnectedSchedulerError
from .connected_app_service import (
    ConnectedCalendarReviewPayload,
    ConnectedMailReviewPayload,
    ConnectedReviewPayload,
)


_PREVIEW_NAMESPACE = UUID("c98e7d38-19c0-5d2f-9779-d820f938734f")
_SHA = frozenset("0123456789abcdef")


def _uuid(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} is invalid")
    try:
        canonical = str(UUID(value))
    except (TypeError, ValueError, AttributeError):
        raise ValueError(f"{name} is invalid") from None
    if canonical != value:
        raise ValueError(f"{name} is invalid")
    return value


def _sha(value: object, name: str, *, optional: bool = False) -> str | None:
    if optional and value is None:
        return None
    if not isinstance(value, str) or len(value) != 64 or any(c not in _SHA for c in value):
        raise ValueError(f"{name} is invalid")
    return value


def _time(value: object, name: str, *, optional: bool = False) -> datetime | None:
    if optional and value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            raise ValueError(f"{name} is invalid") from None
    else:
        raise ValueError(f"{name} is invalid")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{name} is invalid")
    return parsed.astimezone(UTC)


class ConnectedScheduleApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    EXECUTED = "executed"


@dataclass(frozen=True, slots=True, repr=False)
class ConnectedScheduleApprovalRecord:
    occurrence_id: str
    schedule_id: str
    owner_id: str
    approval_id: str
    action_id: str
    task_id: str
    turn_id: str
    connection_id: str
    provider: ConnectorProvider
    resource: ConnectorResource
    action: ConnectorActionKind
    authorization_revision: int
    authorization_snapshot_sha256: str
    granted_scopes_sha256: str
    policy_version: str
    action_revision: int
    approval_class: ConnectorApprovalClass
    approval_binding_sha256: str
    parameters_sha256: str
    resource_version_sha256: str | None
    preview_sha256: str
    review_payload_ref: str
    status: ConnectedScheduleApprovalStatus
    occurrence_created_at: datetime
    expires_at: datetime
    decided_at: datetime | None
    approved_at: datetime | None
    consumed_at: datetime | None

    def __post_init__(self) -> None:
        for name in (
            "occurrence_id",
            "schedule_id",
            "owner_id",
            "approval_id",
            "action_id",
            "task_id",
            "turn_id",
            "connection_id",
            "review_payload_ref",
        ):
            object.__setattr__(self, name, _uuid(getattr(self, name), name))
        if not isinstance(self.provider, ConnectorProvider):
            raise ValueError("provider is invalid")
        if not isinstance(self.resource, ConnectorResource):
            raise ValueError("resource is invalid")
        if not isinstance(self.action, ConnectorActionKind):
            raise ValueError("action is invalid")
        if not isinstance(self.approval_class, ConnectorApprovalClass):
            raise ValueError("approval_class is invalid")
        if not isinstance(self.status, ConnectedScheduleApprovalStatus):
            raise ValueError("status is invalid")
        if type(self.authorization_revision) is not int or self.authorization_revision < 1:
            raise ValueError("authorization_revision is invalid")
        if type(self.action_revision) is not int or self.action_revision < 1:
            raise ValueError("action_revision is invalid")
        if not isinstance(self.policy_version, str) or not 1 <= len(self.policy_version) <= 128:
            raise ValueError("policy_version is invalid")
        for name in (
            "authorization_snapshot_sha256",
            "granted_scopes_sha256",
            "approval_binding_sha256",
            "parameters_sha256",
            "preview_sha256",
        ):
            _sha(getattr(self, name), name)
        _sha(self.resource_version_sha256, "resource_version_sha256", optional=True)
        created = _time(self.occurrence_created_at, "occurrence_created_at")
        expires = _time(self.expires_at, "expires_at")
        decided = _time(self.decided_at, "decided_at", optional=True)
        approved = _time(self.approved_at, "approved_at", optional=True)
        consumed = _time(self.consumed_at, "consumed_at", optional=True)
        object.__setattr__(self, "occurrence_created_at", created)
        object.__setattr__(self, "expires_at", expires)
        object.__setattr__(self, "decided_at", decided)
        object.__setattr__(self, "approved_at", approved)
        object.__setattr__(self, "consumed_at", consumed)
        if expires <= created or expires > created + timedelta(minutes=15):
            raise ValueError("approval lifetime is invalid")
        if self.status in {
            ConnectedScheduleApprovalStatus.APPROVED,
            ConnectedScheduleApprovalStatus.EXECUTED,
        }:
            if approved is None or decided is None or not created <= approved < expires:
                raise ValueError("approved schedule occurrence is invalid")
        elif self.status is ConnectedScheduleApprovalStatus.CANCELLED:
            if approved is not None and (
                decided is None or not created <= approved < expires
            ):
                raise ValueError("cancelled schedule occurrence approval is invalid")
        elif approved is not None:
            raise ValueError("non-approved schedule occurrence carries approval time")

    def evidence(self) -> ConnectedApprovalEvidence | None:
        if (
            self.status is not ConnectedScheduleApprovalStatus.APPROVED
            or self.approved_at is None
            or self.consumed_at is not None
        ):
            return None
        return ConnectedApprovalEvidence(
            approval_id=self.approval_id,
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
            approval_binding_sha256=self.approval_binding_sha256,
            parameters_sha256=self.parameters_sha256,
            resource_version_sha256=self.resource_version_sha256,
            approved_at=self.approved_at,
            expires_at=self.expires_at,
        )

    def __repr__(self) -> str:
        return (
            "ConnectedScheduleApprovalRecord("
            f"occurrence_id={self.occurrence_id!r}, status={self.status.value!r}, "
            "bindings='<redacted>')"
        )


class ConnectedScheduleApprovalStore(Protocol):
    async def read(
        self, *, owner_id: str, occurrence_id: str
    ) -> ConnectedScheduleApprovalRecord | None: ...

    async def put_pending(
        self,
        *,
        claim: ConnectedScheduleClaim,
        intent: ConnectedActionIntent,
        approval_binding_sha256: str,
        preview_payload_ref: str,
        preview_reference_binding_sha256: str,
        preview_sha256: str,
        created_at: datetime,
        expires_at: datetime,
    ) -> ConnectedScheduleApprovalRecord: ...


class ConnectedScheduleApprovalRPC(Protocol):
    async def rpc(
        self,
        function: str,
        params: dict[str, object],
        *,
        retry_transient: bool = False,
    ) -> object: ...


_RECORD_KEYS = frozenset(
    {
        "occurrence_id",
        "schedule_id",
        "owner_id",
        "approval_id",
        "action_id",
        "task_id",
        "turn_id",
        "connection_id",
        "provider",
        "resource",
        "action",
        "authorization_revision",
        "authorization_snapshot_sha256",
        "granted_scopes_sha256",
        "policy_version",
        "action_revision",
        "approval_class",
        "approval_binding_sha256",
        "parameters_sha256",
        "resource_version_sha256",
        "preview_sha256",
        "review_payload_ref",
        "status",
        "occurrence_created_at",
        "expires_at",
        "decided_at",
        "approved_at",
        "consumed_at",
    }
)


class SupabaseConnectedScheduleApprovalStore:
    """Exact-shape service-role RPC adapter for schedule approvals."""

    def __init__(self, database: ConnectedScheduleApprovalRPC) -> None:
        if not callable(getattr(database, "rpc", None)):
            raise TypeError("schedule approval database is invalid")
        self._database = database

    async def _rpc(self, function: str, params: dict[str, object], *, read: bool) -> object:
        value = await self._database.rpc(function, params, retry_transient=read)
        if isinstance(value, list):
            if len(value) != 1:
                raise ConnectedSchedulerError("CONNECTED_SCHEDULE_APPROVAL_RESULT_INVALID")
            value = value[0]
        return value

    @staticmethod
    def _record(value: object) -> ConnectedScheduleApprovalRecord | None:
        if value is None:
            return None
        if type(value) is not dict or frozenset(value) != _RECORD_KEYS:
            raise ConnectedSchedulerError("CONNECTED_SCHEDULE_APPROVAL_RESULT_INVALID")
        row = value
        try:
            return ConnectedScheduleApprovalRecord(
                occurrence_id=row["occurrence_id"],
                schedule_id=row["schedule_id"],
                owner_id=row["owner_id"],
                approval_id=row["approval_id"],
                action_id=row["action_id"],
                task_id=row["task_id"],
                turn_id=row["turn_id"],
                connection_id=row["connection_id"],
                provider=ConnectorProvider(row["provider"]),
                resource=ConnectorResource(row["resource"]),
                action=ConnectorActionKind(row["action"]),
                authorization_revision=row["authorization_revision"],
                authorization_snapshot_sha256=row["authorization_snapshot_sha256"],
                granted_scopes_sha256=row["granted_scopes_sha256"],
                policy_version=row["policy_version"],
                action_revision=row["action_revision"],
                approval_class=ConnectorApprovalClass(row["approval_class"]),
                approval_binding_sha256=row["approval_binding_sha256"],
                parameters_sha256=row["parameters_sha256"],
                resource_version_sha256=row["resource_version_sha256"],
                preview_sha256=row["preview_sha256"],
                review_payload_ref=row["review_payload_ref"],
                status=ConnectedScheduleApprovalStatus(row["status"]),
                occurrence_created_at=_time(
                    row["occurrence_created_at"], "occurrence_created_at"
                ),
                expires_at=_time(row["expires_at"], "expires_at"),
                decided_at=_time(row["decided_at"], "decided_at", optional=True),
                approved_at=_time(row["approved_at"], "approved_at", optional=True),
                consumed_at=_time(row["consumed_at"], "consumed_at", optional=True),
            )
        except ConnectedSchedulerError:
            raise
        except Exception:
            raise ConnectedSchedulerError(
                "CONNECTED_SCHEDULE_APPROVAL_RESULT_INVALID"
            ) from None

    async def read(
        self, *, owner_id: str, occurrence_id: str
    ) -> ConnectedScheduleApprovalRecord | None:
        return self._record(
            await self._rpc(
                "connected_app_read_schedule_approval_v1",
                {
                    "p_owner_id": _uuid(owner_id, "owner_id"),
                    "p_occurrence_id": _uuid(occurrence_id, "occurrence_id"),
                },
                read=True,
            )
        )

    async def put_pending(
        self,
        *,
        claim: ConnectedScheduleClaim,
        intent: ConnectedActionIntent,
        approval_binding_sha256: str,
        preview_payload_ref: str,
        preview_reference_binding_sha256: str,
        preview_sha256: str,
        created_at: datetime,
        expires_at: datetime,
    ) -> ConnectedScheduleApprovalRecord:
        requirement = ConnectedActionPolicy.requirement(claim.action)
        value = await self._rpc(
            "connected_app_put_schedule_approval_v1",
            {
                "p_occurrence_id": claim.occurrence_id,
                "p_schedule_id": claim.schedule_id,
                "p_owner_id": claim.owner_id,
                "p_claim_id": claim.claim_id,
                "p_approval_id": claim.occurrence_approval_id,
                "p_action_id": intent.action_id,
                "p_task_id": claim.task_id,
                "p_turn_id": claim.turn_id,
                "p_connection_id": claim.connection_id,
                "p_provider": claim.provider.value,
                "p_resource": claim.resource.value,
                "p_action": claim.action.value,
                "p_authorization_revision": claim.authorization_revision,
                "p_authorization_snapshot_sha256": (
                    claim.authorization_snapshot_sha256
                ),
                "p_granted_scopes_sha256": claim.granted_scopes_sha256,
                "p_policy_version": ConnectedActionPolicy.version,
                "p_action_revision": claim.task_state_revision,
                "p_approval_class": requirement.approval_class.value,
                "p_approval_binding_sha256": _sha(
                    approval_binding_sha256, "approval_binding_sha256"
                ),
                "p_parameters_sha256": claim.parameters_sha256,
                "p_resource_version_sha256": claim.resource_version_sha256,
                "p_preview_sha256": _sha(preview_sha256, "preview_sha256"),
                "p_review_payload_ref": _uuid(
                    preview_payload_ref, "preview_payload_ref"
                ),
                "p_preview_reference_binding_sha256": _sha(
                    preview_reference_binding_sha256,
                    "preview_reference_binding_sha256",
                ),
                "p_created_at": created_at.isoformat(),
                "p_expires_at": expires_at.isoformat(),
            },
            read=False,
        )
        record = self._record(value)
        if record is None:
            raise ConnectedSchedulerError("CONNECTED_SCHEDULE_APPROVAL_RESULT_INVALID")
        return record


class ConnectedScheduleCancellationSnapshotSource(Protocol):
    async def read_authoritative_event(
        self,
        *,
        claim: ConnectedScheduleClaim,
        request: CalendarCancelRequest,
    ) -> EventSnapshot: ...


class ConnectedScheduleApprovalCoordinator:
    """Create/read one encrypted approval preview for one occurrence."""

    def __init__(
        self,
        *,
        store: ConnectedScheduleApprovalStore,
        payload_vault: ConnectedPayloadVault,
        cancellation_snapshots: ConnectedScheduleCancellationSnapshotSource | None = None,
        now=lambda: datetime.now(UTC),
    ) -> None:
        for method in ("read", "put_pending"):
            if not callable(getattr(store, method, None)):
                raise TypeError("schedule approval store is invalid")
        if not callable(getattr(payload_vault, "seal_json", None)):
            raise TypeError("schedule approval payload vault is invalid")
        if cancellation_snapshots is not None and not callable(
            getattr(cancellation_snapshots, "read_authoritative_event", None)
        ):
            raise TypeError("schedule cancellation snapshot source is invalid")
        if not callable(now):
            raise TypeError("schedule approval clock is invalid")
        self._store = store
        self._payload_vault = payload_vault
        self._cancellation_snapshots = cancellation_snapshots
        self._now = now

    async def _preview(
        self,
        *,
        claim: ConnectedScheduleClaim,
        payload: ConnectedActionPayloadEnvelope,
    ) -> tuple[ConnectedReviewPayload, EventSnapshot | None]:
        request = payload.request
        if type(request) in {MailDraftRequest, MailSendRequest, MailReplyRequest}:
            spec = request.spec
            return (
                ConnectedMailReviewPayload(
                    account=claim.connection_id,
                    to=spec.to,
                    cc=spec.cc,
                    bcc=spec.bcc,
                    subject=spec.subject,
                    body_text=spec.body_text,
                    reply_context=spec.reply_to_message_id,
                ),
                None,
            )
        if type(request) in {CalendarCreateRequest, CalendarUpdateRequest}:
            spec = request.spec
            return (
                ConnectedCalendarReviewPayload(
                    calendar=spec.calendar_id,
                    event_context=spec.source_event_id,
                    title=spec.title,
                    start=spec.starts_at.isoformat(),
                    end=spec.ends_at.isoformat(),
                    time_zone=spec.time_zone,
                    attendees=spec.attendees,
                    location=spec.location,
                    description=spec.description,
                ),
                None,
            )
        if type(request) is CalendarCancelRequest:
            if self._cancellation_snapshots is None:
                raise ConnectedSchedulerError("CONNECTED_SCHEDULE_FRESH_APPROVAL_REQUIRED")
            try:
                event = await self._cancellation_snapshots.read_authoritative_event(
                    claim=claim,
                    request=request,
                )
            except Exception:
                raise ConnectedSchedulerError(
                    "CONNECTED_SCHEDULE_FRESH_APPROVAL_REQUIRED"
                ) from None
            if (
                type(event) is not EventSnapshot
                or event.calendar_id != request.calendar_id
                or event.event_id != request.event_id
                or event.resource_version != request.expected_resource_version
            ):
                raise ConnectedSchedulerError("CONNECTED_SCHEDULE_FRESH_APPROVAL_REQUIRED")
            return (
                ConnectedCalendarReviewPayload(
                    calendar=event.calendar_id,
                    event_context=event.event_id,
                    title=event.title,
                    start=event.starts_at.isoformat(),
                    end=event.ends_at.isoformat(),
                    time_zone=event.time_zone,
                    attendees=event.attendees,
                    location=event.location,
                    description=event.description,
                ),
                event,
            )
        raise ConnectedSchedulerError("CONNECTED_SCHEDULE_FRESH_APPROVAL_REQUIRED")

    @staticmethod
    def _matches(
        record: ConnectedScheduleApprovalRecord,
        *,
        claim: ConnectedScheduleClaim,
        intent: ConnectedActionIntent,
    ) -> bool:
        requirement = ConnectedActionPolicy.requirement(claim.action)
        return bool(
            record.occurrence_id == claim.occurrence_id
            and record.schedule_id == claim.schedule_id
            and record.owner_id == claim.owner_id
            and record.approval_id == claim.occurrence_approval_id
            and record.action_id == intent.action_id
            and record.task_id == claim.task_id
            and record.turn_id == claim.turn_id
            and record.connection_id == claim.connection_id
            and record.provider is claim.provider
            and record.resource is claim.resource
            and record.action is claim.action
            and record.authorization_revision == claim.authorization_revision
            and record.authorization_snapshot_sha256
            == claim.authorization_snapshot_sha256
            and record.granted_scopes_sha256 == claim.granted_scopes_sha256
            and record.policy_version == ConnectedActionPolicy.version
            and record.action_revision == claim.task_state_revision
            and record.approval_class is requirement.approval_class
            and record.parameters_sha256 == claim.parameters_sha256
            and record.resource_version_sha256 == claim.resource_version_sha256
            and record.occurrence_created_at == claim.occurrence_created_at
        )

    async def fresh_approval(
        self,
        *,
        claim: ConnectedScheduleClaim,
        intent: ConnectedActionIntent,
        action_payload: ConnectedActionPayloadEnvelope,
    ) -> ConnectedApprovalEvidence | None:
        if (
            type(claim) is not ConnectedScheduleClaim
            or type(intent) is not ConnectedActionIntent
            or type(action_payload) is not ConnectedActionPayloadEnvelope
            or action_payload.action is not claim.action
            or any(
                value is None
                for value in (
                    claim.occurrence_id,
                    claim.occurrence_action_id,
                    claim.occurrence_approval_id,
                    claim.occurrence_created_at,
                )
            )
        ):
            raise ConnectedSchedulerError("CONNECTED_SCHEDULE_FRESH_APPROVAL_REQUIRED")
        now = _time(self._now(), "now")
        try:
            record = await self._store.read(
                owner_id=claim.owner_id,
                occurrence_id=str(claim.occurrence_id),
            )
        except Exception:
            raise ConnectedSchedulerError(
                "CONNECTED_SCHEDULE_FRESH_APPROVAL_REQUIRED", retryable=True
            ) from None
        if record is None:
            created_at = claim.occurrence_created_at
            expires_at = created_at + timedelta(minutes=15)  # type: ignore[operator]
            if expires_at <= now:  # type: ignore[operator]
                return None
            review, authoritative_event = await self._preview(
                claim=claim,
                payload=action_payload,
            )
            envelope = ConnectedApprovalReviewEnvelope(
                approval_id=str(claim.occurrence_approval_id),
                action_id=intent.action_id,
                connection_id=claim.connection_id,
                parameters_sha256=claim.parameters_sha256,
                resource_version_sha256=claim.resource_version_sha256,
                action_payload=action_payload,
                review_payload=review,
                authoritative_event=authoritative_event,
            )
            preview_id = str(
                uuid5(_PREVIEW_NAMESPACE, str(claim.occurrence_id))
            )
            try:
                preview_ref = await self._payload_vault.seal_json(
                    payload_id=preview_id,
                    owner_id=claim.owner_id,
                    connection_id=claim.connection_id,
                    action_id=intent.action_id,
                    provider=claim.provider,
                    action=claim.action,
                    value=envelope.to_value(),
                    created_at=created_at,  # type: ignore[arg-type]
                    expires_at=expires_at,
                )
                binding = action_preparation_approval_binding_sha256(
                    request_id=str(claim.occurrence_id),
                    owner_id=claim.owner_id,
                    action_id=intent.action_id,
                    approval_id=str(claim.occurrence_approval_id),
                    connection_id=claim.connection_id,
                    action=claim.action,
                    parameters_sha256=claim.parameters_sha256,
                    preview_sha256=preview_ref.payload_sha256,
                    preview_reference_binding_sha256=preview_ref.binding_sha256,
                )
                record = await self._store.put_pending(
                    claim=claim,
                    intent=intent,
                    approval_binding_sha256=binding,
                    preview_payload_ref=preview_ref.payload_id,
                    preview_reference_binding_sha256=preview_ref.binding_sha256,
                    preview_sha256=preview_ref.payload_sha256,
                    created_at=created_at,  # type: ignore[arg-type]
                    expires_at=expires_at,
                )
            except Exception:
                try:
                    record = await self._store.read(
                        owner_id=claim.owner_id,
                        occurrence_id=str(claim.occurrence_id)
                    )
                except Exception:
                    record = None
                if record is None:
                    raise ConnectedSchedulerError(
                        "CONNECTED_SCHEDULE_FRESH_APPROVAL_REQUIRED", retryable=True
                    ) from None
        if not self._matches(record, claim=claim, intent=intent):
            raise ConnectedSchedulerError("CONNECTED_SCHEDULE_FRESH_APPROVAL_REQUIRED")
        evidence = record.evidence()
        if evidence is None or evidence.expires_at <= now:  # type: ignore[operator]
            return None
        return evidence


__all__ = [
    "ConnectedScheduleApprovalCoordinator",
    "ConnectedScheduleApprovalRecord",
    "ConnectedScheduleApprovalRPC",
    "ConnectedScheduleApprovalStatus",
    "ConnectedScheduleApprovalStore",
    "ConnectedScheduleCancellationSnapshotSource",
    "SupabaseConnectedScheduleApprovalStore",
]
