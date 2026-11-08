"""Encrypted, exactly-once custody for connected-app read results.

Provider mail and calendar content is untrusted customer data.  This module
serializes only the five implemented read-result shapes, seals that content in
the connected payload vault, and persists only an opaque result reference plus
content-free authority metadata.  A terminal replay always decrypts the
previously settled result; it never calls a provider a second time.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
import hashlib
import hmac
import re
from typing import Any, Callable, Protocol
from uuid import UUID, uuid5

from .connected_app_contracts import (
    EventSnapshot,
    FreeBusyWindow,
    MessageSnapshot,
    MessageSummary,
)
from .connected_app_durable_stores import ConnectedPayloadReferenceResolver
from .connected_app_payload_vault import (
    ConnectedPayloadRef,
    ConnectedPayloadVault,
    ConnectedPayloadVaultError,
)
from .connected_app_policy import ConnectorActionKind, ConnectorProvider, ConnectorResource
from .connected_app_runtime import (
    ConnectedActionClaim,
    ConnectedActionClaimStatus,
    ConnectedActionInvocation,
    ConnectedActionLookupRecord,
    ConnectedDurableReadResult,
    ConnectedReadObservation,
    ConnectedReadTerminalRecord,
)


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_KEY_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
_COMPLETION_NAMESPACE = UUID("f7af6f00-bd3a-5fb7-bdd0-27895e8c7c4f")
_PAYLOAD_NAMESPACE = UUID("ec03ba18-d4a0-5c81-aef2-651d48d8404d")
_ENVELOPE_VERSION = "connected-read-result-v1"
_MAX_RETENTION = timedelta(days=7)
_MAX_COLLECTION = 1_000

_READ_ACTION_RESOURCE = {
    ConnectorActionKind.MAIL_SEARCH: ConnectorResource.MAIL,
    ConnectorActionKind.MAIL_GET: ConnectorResource.MAIL,
    ConnectorActionKind.CALENDAR_LIST: ConnectorResource.CALENDAR,
    ConnectorActionKind.CALENDAR_GET: ConnectorResource.CALENDAR,
    ConnectorActionKind.CALENDAR_FREE_BUSY: ConnectorResource.CALENDAR,
}
_RESULT_KIND = {
    ConnectorActionKind.MAIL_SEARCH: "mail_summary_list",
    ConnectorActionKind.MAIL_GET: "mail_message",
    ConnectorActionKind.CALENDAR_LIST: "calendar_event_list",
    ConnectorActionKind.CALENDAR_GET: "calendar_event",
    ConnectorActionKind.CALENDAR_FREE_BUSY: "calendar_free_busy_list",
}


def _uuid(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise ConnectedReadResultError("CONNECTED_READ_RESULT_INVALID")
    try:
        canonical = str(UUID(value))
    except (TypeError, ValueError, AttributeError):
        raise ConnectedReadResultError("CONNECTED_READ_RESULT_INVALID") from None
    if canonical != value:
        raise ConnectedReadResultError("CONNECTED_READ_RESULT_INVALID")
    return value


def _sha(value: object) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ConnectedReadResultError("CONNECTED_READ_RESULT_INVALID")
    return value


def _key_id(value: object) -> str:
    if not isinstance(value, str) or not _KEY_ID.fullmatch(value):
        raise ConnectedReadResultError("CONNECTED_READ_RESULT_INVALID")
    return value


def _aware(value: object) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ConnectedReadResultError("CONNECTED_READ_RESULT_INVALID")
    return value.astimezone(UTC)


def _time(value: object) -> datetime:
    if not isinstance(value, str) or not value or len(value) > 64:
        raise ConnectedReadResultError("CONNECTED_READ_RESULT_INVALID")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ConnectedReadResultError("CONNECTED_READ_RESULT_INVALID") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ConnectedReadResultError("CONNECTED_READ_RESULT_INVALID")
    return parsed.astimezone(UTC)


def _iso(value: datetime) -> str:
    return _aware(value).isoformat()


def _exact(value: object, keys: frozenset[str]) -> dict[str, object]:
    if type(value) is not dict or frozenset(value) != keys:
        raise ConnectedReadResultError("CONNECTED_READ_RESULT_INVALID")
    return value  # type: ignore[return-value]


def _text(value: object, *, nullable: bool = False, maximum: int = 512_000) -> str | None:
    if nullable and value is None:
        return None
    if not isinstance(value, str) or len(value.encode("utf-8")) > maximum:
        raise ConnectedReadResultError("CONNECTED_READ_RESULT_INVALID")
    return value


def _list(value: object, *, maximum: int) -> list[object]:
    if type(value) is not list or len(value) > maximum:
        raise ConnectedReadResultError("CONNECTED_READ_RESULT_INVALID")
    return value


def _strings(value: object, *, maximum: int) -> tuple[str, ...]:
    return tuple(
        _text(item, maximum=8_192) or "" for item in _list(value, maximum=maximum)
    )


def _provider(value: object) -> ConnectorProvider:
    try:
        return ConnectorProvider(value)
    except (TypeError, ValueError):
        raise ConnectedReadResultError("CONNECTED_READ_RESULT_INVALID") from None


def _resource(value: object) -> ConnectorResource:
    try:
        return ConnectorResource(value)
    except (TypeError, ValueError):
        raise ConnectedReadResultError("CONNECTED_READ_RESULT_INVALID") from None


def _action(value: object) -> ConnectorActionKind:
    try:
        action = ConnectorActionKind(value)
    except (TypeError, ValueError):
        raise ConnectedReadResultError("CONNECTED_READ_RESULT_INVALID") from None
    if action not in _READ_ACTION_RESOURCE:
        raise ConnectedReadResultError("CONNECTED_READ_RESULT_INVALID")
    return action


class ConnectedReadResultError(RuntimeError):
    """Content-free encrypted-result failure."""

    _ALLOWED = frozenset(
        {
            "CONNECTED_READ_RESULT_BINDING_MISMATCH",
            "CONNECTED_READ_RESULT_EFFECT_UNKNOWN",
            "CONNECTED_READ_RESULT_EXPIRED",
            "CONNECTED_READ_RESULT_INVALID",
            "CONNECTED_READ_RESULT_NOT_FOUND",
            "CONNECTED_READ_RESULT_STORE_UNAVAILABLE",
            "CONNECTED_READ_RESULT_TOO_LARGE",
        }
    )

    def __init__(self, code: str) -> None:
        if code not in self._ALLOWED:
            raise ValueError("invalid connected read-result error")
        self.code = code
        super().__init__(code)


class ConnectedReadResultStatus(StrEnum):
    ABSENT = "absent"
    NOT_CONSUMED = "not_consumed"
    CONSUMED_UNKNOWN = "consumed_unknown"
    TERMINAL = "terminal"


@dataclass(frozen=True, slots=True, repr=False)
class ConnectedReadResultRecord:
    completion_id: str
    operation_id: str
    action_id: str
    owner_id: str
    connection_id: str
    provider: ConnectorProvider
    resource: ConnectorResource
    action: ConnectorActionKind
    result_payload_id: str
    result_commitment_key_id: str
    result_payload_sha256: str
    result_reference_binding_sha256: str
    terminal_binding_sha256: str
    authority_sha256: str
    idempotency_key_sha256: str
    claim_id: str
    fencing_token: int
    read_use_nonce: str
    observed_at: datetime
    resource_version_sha256: str | None
    completed_at: datetime | None

    def __post_init__(self) -> None:
        for name in (
            "completion_id",
            "operation_id",
            "action_id",
            "owner_id",
            "connection_id",
            "result_payload_id",
            "claim_id",
            "read_use_nonce",
        ):
            object.__setattr__(self, name, _uuid(getattr(self, name), name))
        if self.operation_id != self.action_id:
            raise ConnectedReadResultError("CONNECTED_READ_RESULT_INVALID")
        if not isinstance(self.provider, ConnectorProvider) or not isinstance(
            self.resource, ConnectorResource
        ):
            raise ConnectedReadResultError("CONNECTED_READ_RESULT_INVALID")
        if (
            not isinstance(self.action, ConnectorActionKind)
            or self.action not in _READ_ACTION_RESOURCE
            or _READ_ACTION_RESOURCE[self.action] is not self.resource
        ):
            raise ConnectedReadResultError("CONNECTED_READ_RESULT_INVALID")
        object.__setattr__(
            self,
            "result_commitment_key_id",
            _key_id(self.result_commitment_key_id),
        )
        for name in (
            "result_payload_sha256",
            "result_reference_binding_sha256",
            "terminal_binding_sha256",
            "authority_sha256",
            "idempotency_key_sha256",
        ):
            object.__setattr__(self, name, _sha(getattr(self, name)))
        if self.resource_version_sha256 is not None:
            object.__setattr__(
                self,
                "resource_version_sha256",
                _sha(self.resource_version_sha256),
            )
        if type(self.fencing_token) is not int or self.fencing_token < 1:
            raise ConnectedReadResultError("CONNECTED_READ_RESULT_INVALID")
        object.__setattr__(self, "observed_at", _aware(self.observed_at))
        if self.completed_at is not None:
            completed = _aware(self.completed_at)
            if completed < self.observed_at:
                raise ConnectedReadResultError("CONNECTED_READ_RESULT_INVALID")
            object.__setattr__(self, "completed_at", completed)

    def __repr__(self) -> str:
        return (
            "ConnectedReadResultRecord("
            f"action={self.action.value!r}, content='<encrypted>')"
        )


@dataclass(frozen=True, slots=True, repr=False)
class ConnectedReadResultInspection:
    status: ConnectedReadResultStatus
    record: ConnectedReadResultRecord | None

    def __post_init__(self) -> None:
        if not isinstance(self.status, ConnectedReadResultStatus):
            raise ConnectedReadResultError("CONNECTED_READ_RESULT_INVALID")
        if (self.status is ConnectedReadResultStatus.TERMINAL) != (
            self.record is not None
        ):
            raise ConnectedReadResultError("CONNECTED_READ_RESULT_INVALID")
        if self.record is not None and self.record.completed_at is None:
            raise ConnectedReadResultError("CONNECTED_READ_RESULT_INVALID")

    def __repr__(self) -> str:
        return f"ConnectedReadResultInspection(status={self.status.value!r})"


class ConnectedReadResultRPC(Protocol):
    async def rpc(
        self,
        function_name: str,
        payload: dict[str, Any],
        *,
        retry_transient: bool = False,
    ) -> Any: ...


class ConnectedReadResultStore(Protocol):
    async def settle_once(
        self, candidate: ConnectedReadResultRecord
    ) -> ConnectedReadResultRecord: ...

    async def inspect(
        self,
        *,
        owner_id: str,
        operation_id: str,
        completion_id: str,
        idempotency_key_sha256: str,
    ) -> ConnectedReadResultInspection: ...


_RECORD_KEYS = frozenset(
    {
        "completion_id",
        "operation_id",
        "action_id",
        "owner_id",
        "connection_id",
        "provider",
        "resource",
        "action",
        "result_payload_id",
        "result_commitment_key_id",
        "result_payload_sha256",
        "result_reference_binding_sha256",
        "terminal_binding_sha256",
        "authority_sha256",
        "idempotency_key_sha256",
        "claim_id",
        "fencing_token",
        "read_use_nonce",
        "observed_at",
        "resource_version_sha256",
        "completed_at",
    }
)


def _record(value: object) -> ConnectedReadResultRecord:
    row = _exact(value, _RECORD_KEYS)
    completed = row["completed_at"]
    return ConnectedReadResultRecord(
        completion_id=_uuid(row["completion_id"], "completion_id"),
        operation_id=_uuid(row["operation_id"], "operation_id"),
        action_id=_uuid(row["action_id"], "action_id"),
        owner_id=_uuid(row["owner_id"], "owner_id"),
        connection_id=_uuid(row["connection_id"], "connection_id"),
        provider=_provider(row["provider"]),
        resource=_resource(row["resource"]),
        action=_action(row["action"]),
        result_payload_id=_uuid(row["result_payload_id"], "result_payload_id"),
        result_commitment_key_id=_key_id(row["result_commitment_key_id"]),
        result_payload_sha256=_sha(row["result_payload_sha256"]),
        result_reference_binding_sha256=_sha(row["result_reference_binding_sha256"]),
        terminal_binding_sha256=_sha(row["terminal_binding_sha256"]),
        authority_sha256=_sha(row["authority_sha256"]),
        idempotency_key_sha256=_sha(row["idempotency_key_sha256"]),
        claim_id=_uuid(row["claim_id"], "claim_id"),
        fencing_token=(
            row["fencing_token"]
            if type(row["fencing_token"]) is int
            else (_ for _ in ()).throw(
                ConnectedReadResultError("CONNECTED_READ_RESULT_INVALID")
            )
        ),
        read_use_nonce=_uuid(row["read_use_nonce"], "read_use_nonce"),
        observed_at=_time(row["observed_at"]),
        resource_version_sha256=(
            None
            if row["resource_version_sha256"] is None
            else _sha(row["resource_version_sha256"])
        ),
        completed_at=None if completed is None else _time(completed),
    )


def _record_parameters(candidate: ConnectedReadResultRecord) -> dict[str, object]:
    return {
        "p_completion_id": candidate.completion_id,
        "p_operation_id": candidate.operation_id,
        "p_action_id": candidate.action_id,
        "p_owner_id": candidate.owner_id,
        "p_connection_id": candidate.connection_id,
        "p_provider": candidate.provider.value,
        "p_resource": candidate.resource.value,
        "p_action": candidate.action.value,
        "p_result_payload_id": candidate.result_payload_id,
        "p_result_commitment_key_id": candidate.result_commitment_key_id,
        "p_result_payload_sha256": candidate.result_payload_sha256,
        "p_result_reference_binding_sha256": candidate.result_reference_binding_sha256,
        "p_terminal_binding_sha256": candidate.terminal_binding_sha256,
        "p_authority_sha256": candidate.authority_sha256,
        "p_idempotency_key_sha256": candidate.idempotency_key_sha256,
        "p_claim_id": candidate.claim_id,
        "p_fencing_token": candidate.fencing_token,
        "p_read_use_nonce": candidate.read_use_nonce,
        "p_observed_at": _iso(candidate.observed_at),
        "p_resource_version_sha256": candidate.resource_version_sha256,
    }


class SupabaseConnectedReadResultStore:
    """Strict PostgREST boundary for the read-result settlement RPCs."""

    def __init__(self, rpc: ConnectedReadResultRPC) -> None:
        if not callable(getattr(rpc, "rpc", None)):
            raise TypeError("read-result RPC is invalid")
        self._rpc = rpc

    async def _call(
        self, name: str, payload: dict[str, object], *, read: bool = False
    ) -> object:
        try:
            return await self._rpc.rpc(name, payload, retry_transient=read)
        except ConnectedReadResultError:
            raise
        except Exception:
            raise ConnectedReadResultError(
                "CONNECTED_READ_RESULT_STORE_UNAVAILABLE"
            ) from None

    async def inspect(
        self,
        *,
        owner_id: str,
        operation_id: str,
        completion_id: str,
        idempotency_key_sha256: str,
    ) -> ConnectedReadResultInspection:
        result = await self._call(
            "connected_app_read_read_result_v1",
            {
                "p_owner_id": _uuid(owner_id, "owner_id"),
                "p_operation_id": _uuid(operation_id, "operation_id"),
                "p_completion_id": _uuid(completion_id, "completion_id"),
                "p_idempotency_key_sha256": _sha(idempotency_key_sha256),
            },
            read=True,
        )
        envelope = _exact(result, frozenset({"status", "record"}))
        try:
            status = ConnectedReadResultStatus(envelope["status"])
        except (TypeError, ValueError):
            raise ConnectedReadResultError("CONNECTED_READ_RESULT_INVALID") from None
        value = envelope["record"]
        return ConnectedReadResultInspection(
            status=status,
            record=None if value is None else _record(value),
        )

    async def settle_once(
        self, candidate: ConnectedReadResultRecord
    ) -> ConnectedReadResultRecord:
        if not isinstance(candidate, ConnectedReadResultRecord):
            raise TypeError("candidate must be ConnectedReadResultRecord")
        try:
            result = await self._call(
                "connected_app_settle_read_result_v1",
                _record_parameters(candidate),
            )
            envelope = _exact(result, frozenset({"status", "record"}))
            if envelope["status"] != ConnectedReadResultStatus.TERMINAL.value:
                raise ConnectedReadResultError("CONNECTED_READ_RESULT_INVALID")
            settled = _record(envelope["record"])
            if settled.completed_at is None:
                raise ConnectedReadResultError("CONNECTED_READ_RESULT_INVALID")
        except ConnectedReadResultError:
            inspection = await self.inspect(
                owner_id=candidate.owner_id,
                operation_id=candidate.operation_id,
                completion_id=candidate.completion_id,
                idempotency_key_sha256=candidate.idempotency_key_sha256,
            )
            if inspection.status is not ConnectedReadResultStatus.TERMINAL:
                raise ConnectedReadResultError(
                    "CONNECTED_READ_RESULT_EFFECT_UNKNOWN"
                ) from None
            assert inspection.record is not None
            settled = inspection.record
        if settled != candidate:
            # The database owns completed_at, so compare the exact candidate
            # after substituting that one authoritative field.
            expected = ConnectedReadResultRecord(
                **{
                    name: getattr(candidate, name)
                    for name in ConnectedReadResultRecord.__dataclass_fields__
                    if name != "completed_at"
                },
                completed_at=settled.completed_at,
            )
            if settled != expected:
                raise ConnectedReadResultError(
                    "CONNECTED_READ_RESULT_BINDING_MISMATCH"
                )
        return settled


def _message_summary(value: MessageSummary) -> dict[str, object]:
    return {
        "messageId": value.message_id,
        "threadId": value.thread_id,
        "resourceVersion": value.resource_version,
        "receivedAt": _iso(value.received_at),
        "subject": value.subject,
        "sender": value.sender,
        "recipients": list(value.recipients),
        "labels": list(value.labels),
        "hasAttachments": value.has_attachments,
    }


def _parse_message_summary(value: object) -> MessageSummary:
    row = _exact(
        value,
        frozenset(
            {
                "messageId",
                "threadId",
                "resourceVersion",
                "receivedAt",
                "subject",
                "sender",
                "recipients",
                "labels",
                "hasAttachments",
            }
        ),
    )
    if type(row["hasAttachments"]) is not bool:
        raise ConnectedReadResultError("CONNECTED_READ_RESULT_INVALID")
    return MessageSummary(
        message_id=_text(row["messageId"], maximum=512) or "",
        thread_id=_text(row["threadId"], nullable=True, maximum=512),
        resource_version=_text(row["resourceVersion"], maximum=512) or "",
        received_at=_time(row["receivedAt"]),
        subject=_text(row["subject"], maximum=8_192) or "",
        sender=_text(row["sender"], maximum=2_048) or "",
        recipients=_strings(row["recipients"], maximum=100),
        labels=_strings(row["labels"], maximum=100),
        has_attachments=row["hasAttachments"],
    )


def _message(value: MessageSnapshot) -> dict[str, object]:
    return {
        "messageId": value.message_id,
        "threadId": value.thread_id,
        "resourceVersion": value.resource_version,
        "receivedAt": _iso(value.received_at),
        "subject": value.subject,
        "sender": value.sender,
        "recipients": list(value.recipients),
        "bodyText": value.body_text,
        "attachmentCount": value.attachment_count,
    }


def _parse_message(value: object) -> MessageSnapshot:
    row = _exact(
        value,
        frozenset(
            {
                "messageId",
                "threadId",
                "resourceVersion",
                "receivedAt",
                "subject",
                "sender",
                "recipients",
                "bodyText",
                "attachmentCount",
            }
        ),
    )
    if type(row["attachmentCount"]) is not int:
        raise ConnectedReadResultError("CONNECTED_READ_RESULT_INVALID")
    return MessageSnapshot(
        message_id=_text(row["messageId"], maximum=512) or "",
        thread_id=_text(row["threadId"], nullable=True, maximum=512),
        resource_version=_text(row["resourceVersion"], maximum=512) or "",
        received_at=_time(row["receivedAt"]),
        subject=_text(row["subject"], maximum=8_192) or "",
        sender=_text(row["sender"], maximum=2_048) or "",
        recipients=_strings(row["recipients"], maximum=100),
        body_text=_text(row["bodyText"], maximum=512_000) or "",
        attachment_count=row["attachmentCount"],
    )


def _event(value: EventSnapshot) -> dict[str, object]:
    return {
        "eventId": value.event_id,
        "calendarId": value.calendar_id,
        "resourceVersion": value.resource_version,
        "startsAt": _iso(value.starts_at),
        "endsAt": _iso(value.ends_at),
        "timeZone": value.time_zone,
        "title": value.title,
        "description": value.description,
        "location": value.location,
        "attendees": list(value.attendees),
        "organizer": value.organizer,
        "status": value.status,
    }


def _parse_event(value: object) -> EventSnapshot:
    row = _exact(
        value,
        frozenset(
            {
                "eventId",
                "calendarId",
                "resourceVersion",
                "startsAt",
                "endsAt",
                "timeZone",
                "title",
                "description",
                "location",
                "attendees",
                "organizer",
                "status",
            }
        ),
    )
    return EventSnapshot(
        event_id=_text(row["eventId"], maximum=512) or "",
        calendar_id=_text(row["calendarId"], maximum=512) or "",
        resource_version=_text(row["resourceVersion"], maximum=512) or "",
        starts_at=_time(row["startsAt"]),
        ends_at=_time(row["endsAt"]),
        time_zone=_text(row["timeZone"], maximum=100) or "",
        title=_text(row["title"], maximum=8_192) or "",
        description=_text(row["description"], maximum=200_000) or "",
        location=_text(row["location"], maximum=8_192) or "",
        attendees=_strings(row["attendees"], maximum=100),
        organizer=_text(row["organizer"], nullable=True, maximum=320),
        status=_text(row["status"], maximum=32) or "",
    )


def _busy(value: FreeBusyWindow) -> dict[str, object]:
    return {
        "calendarId": value.calendar_id,
        "startsAt": _iso(value.starts_at),
        "endsAt": _iso(value.ends_at),
        "status": value.status,
    }


def _parse_busy(value: object) -> FreeBusyWindow:
    row = _exact(
        value,
        frozenset({"calendarId", "startsAt", "endsAt", "status"}),
    )
    return FreeBusyWindow(
        calendar_id=_text(row["calendarId"], maximum=512) or "",
        starts_at=_time(row["startsAt"]),
        ends_at=_time(row["endsAt"]),
        status=_text(row["status"], maximum=32) or "",
    )


def _serialize_value(action: ConnectorActionKind, value: object) -> object:
    if action is ConnectorActionKind.MAIL_SEARCH:
        if type(value) is not tuple or len(value) > 100 or any(
            type(item) is not MessageSummary for item in value
        ):
            raise ConnectedReadResultError("CONNECTED_READ_RESULT_INVALID")
        return [_message_summary(item) for item in value]
    if action is ConnectorActionKind.MAIL_GET:
        if type(value) is not MessageSnapshot:
            raise ConnectedReadResultError("CONNECTED_READ_RESULT_INVALID")
        return _message(value)
    if action is ConnectorActionKind.CALENDAR_LIST:
        if type(value) is not tuple or len(value) > 250 or any(
            type(item) is not EventSnapshot for item in value
        ):
            raise ConnectedReadResultError("CONNECTED_READ_RESULT_INVALID")
        return [_event(item) for item in value]
    if action is ConnectorActionKind.CALENDAR_GET:
        if type(value) is not EventSnapshot:
            raise ConnectedReadResultError("CONNECTED_READ_RESULT_INVALID")
        return _event(value)
    if action is ConnectorActionKind.CALENDAR_FREE_BUSY:
        if type(value) is not tuple or len(value) > _MAX_COLLECTION or any(
            type(item) is not FreeBusyWindow for item in value
        ):
            raise ConnectedReadResultError("CONNECTED_READ_RESULT_INVALID")
        return [_busy(item) for item in value]
    raise ConnectedReadResultError("CONNECTED_READ_RESULT_INVALID")


def _parse_value(action: ConnectorActionKind, value: object) -> object:
    try:
        if action is ConnectorActionKind.MAIL_SEARCH:
            return tuple(
                _parse_message_summary(item)
                for item in _list(value, maximum=100)
            )
        if action is ConnectorActionKind.MAIL_GET:
            return _parse_message(value)
        if action is ConnectorActionKind.CALENDAR_LIST:
            return tuple(
                _parse_event(item) for item in _list(value, maximum=250)
            )
        if action is ConnectorActionKind.CALENDAR_GET:
            return _parse_event(value)
        if action is ConnectorActionKind.CALENDAR_FREE_BUSY:
            return tuple(
                _parse_busy(item)
                for item in _list(value, maximum=_MAX_COLLECTION)
            )
    except ConnectedReadResultError:
        raise
    except (TypeError, ValueError):
        raise ConnectedReadResultError("CONNECTED_READ_RESULT_INVALID") from None
    raise ConnectedReadResultError("CONNECTED_READ_RESULT_INVALID")


_ENVELOPE_KEYS = frozenset(
    {
        "version",
        "completionId",
        "resultPayloadId",
        "operationId",
        "ownerId",
        "connectionId",
        "provider",
        "resource",
        "action",
        "claimId",
        "fencingToken",
        "readUseNonce",
        "terminalBindingSha256",
        "authoritySha256",
        "idempotencyKeySha256",
        "observedAt",
        "resourceVersion",
        "resourceVersionSha256",
        "resultKind",
        "value",
    }
)


@dataclass(frozen=True, slots=True, repr=False)
class _DecodedEnvelope:
    durable: ConnectedDurableReadResult
    completion_id: str
    result_payload_id: str
    owner_id: str
    connection_id: str
    claim_id: str
    fencing_token: int
    read_use_nonce: str

    def __repr__(self) -> str:
        return "_DecodedEnvelope(content='<redacted>')"


def _envelope(
    *,
    completion_id: str,
    result_payload_id: str,
    owner_id: str,
    connection_id: str,
    claim: ConnectedActionClaim,
    terminal: ConnectedReadTerminalRecord,
    observation: ConnectedReadObservation,
) -> dict[str, object]:
    if (
        claim.status is not ConnectedActionClaimStatus.ACCESS_GRANTED
        or type(claim.fencing_token) is not int
        or claim.fencing_token < 1
        or claim.access_use_nonce is None
        or claim.authority_sha256 != terminal.authority_sha256
        or observation.operation_id != terminal.operation_id
        or observation.provider is not terminal.provider
        or observation.resource is not terminal.resource
        or observation.observed_at != terminal.observed_at
        or (
            observation.resource_version is None
            and terminal.resource_version_sha256 is not None
        )
        or (
            observation.resource_version is not None
            and hashlib.sha256(observation.resource_version.encode("utf-8")).hexdigest()
            != terminal.resource_version_sha256
        )
    ):
        raise ConnectedReadResultError("CONNECTED_READ_RESULT_BINDING_MISMATCH")
    return {
        "version": _ENVELOPE_VERSION,
        "completionId": completion_id,
        "resultPayloadId": result_payload_id,
        "operationId": terminal.operation_id,
        "ownerId": owner_id,
        "connectionId": connection_id,
        "provider": terminal.provider.value,
        "resource": terminal.resource.value,
        "action": terminal.action.value,
        "claimId": claim.claim_id,
        "fencingToken": claim.fencing_token,
        "readUseNonce": claim.access_use_nonce,
        "terminalBindingSha256": terminal.binding_sha256,
        "authoritySha256": terminal.authority_sha256,
        "idempotencyKeySha256": terminal.idempotency_key_hash,
        "observedAt": _iso(terminal.observed_at),
        "resourceVersion": observation.resource_version,
        "resourceVersionSha256": terminal.resource_version_sha256,
        "resultKind": _RESULT_KIND[terminal.action],
        "value": _serialize_value(terminal.action, observation.value),
    }


def _decode_envelope(value: object) -> _DecodedEnvelope:
    row = _exact(value, _ENVELOPE_KEYS)
    if row["version"] != _ENVELOPE_VERSION:
        raise ConnectedReadResultError("CONNECTED_READ_RESULT_INVALID")
    action = _action(row["action"])
    provider = _provider(row["provider"])
    resource = _resource(row["resource"])
    if resource is not _READ_ACTION_RESOURCE[action] or row["resultKind"] != _RESULT_KIND[action]:
        raise ConnectedReadResultError("CONNECTED_READ_RESULT_BINDING_MISMATCH")
    fence = row["fencingToken"]
    if type(fence) is not int or fence < 1:
        raise ConnectedReadResultError("CONNECTED_READ_RESULT_INVALID")
    resource_version = _text(row["resourceVersion"], nullable=True, maximum=512)
    resource_version_sha = (
        None if row["resourceVersionSha256"] is None else _sha(row["resourceVersionSha256"])
    )
    observed = _time(row["observedAt"])
    operation_id = _uuid(row["operationId"], "operationId")
    terminal = ConnectedReadTerminalRecord(
        operation_id=operation_id,
        provider=provider,
        resource=resource,
        action=action,
        binding_sha256=_sha(row["terminalBindingSha256"]),
        authority_sha256=_sha(row["authoritySha256"]),
        idempotency_key_hash=_sha(row["idempotencyKeySha256"]),
        observed_at=observed,
        resource_version_sha256=resource_version_sha,
    )
    observation = ConnectedReadObservation(
        operation_id=operation_id,
        provider=provider,
        resource=resource,
        value=_parse_value(action, row["value"]),
        observed_at=observed,
        resource_version=resource_version,
    )
    return _DecodedEnvelope(
        durable=ConnectedDurableReadResult(terminal=terminal, observation=observation),
        completion_id=_uuid(row["completionId"], "completionId"),
        result_payload_id=_uuid(row["resultPayloadId"], "resultPayloadId"),
        owner_id=_uuid(row["ownerId"], "ownerId"),
        connection_id=_uuid(row["connectionId"], "connectionId"),
        claim_id=_uuid(row["claimId"], "claimId"),
        fencing_token=fence,
        read_use_nonce=_uuid(row["readUseNonce"], "readUseNonce"),
    )


class ConnectedReadResultCoordinator:
    """Seal results, settle their opaque references, and replay exactly once."""

    def __init__(
        self,
        *,
        vault: ConnectedPayloadVault,
        references: ConnectedPayloadReferenceResolver,
        store: ConnectedReadResultStore,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        retention: timedelta = timedelta(days=7),
    ) -> None:
        if not isinstance(vault, ConnectedPayloadVault):
            raise TypeError("vault must be ConnectedPayloadVault")
        if not callable(getattr(references, "resolve_reference", None)):
            raise TypeError("payload reference resolver is invalid")
        if not callable(getattr(store, "settle_once", None)) or not callable(
            getattr(store, "inspect", None)
        ):
            raise TypeError("read-result store is invalid")
        if retention <= timedelta(0) or retention > _MAX_RETENTION:
            raise ValueError("read-result retention is invalid")
        self._vault = vault
        self._references = references
        self._store = store
        self._now = now
        self._retention = retention

    @staticmethod
    def completion_id(operation_id: str) -> str:
        return str(uuid5(_COMPLETION_NAMESPACE, _uuid(operation_id, "operation_id")))

    @staticmethod
    def payload_id(operation_id: str) -> str:
        return str(uuid5(_PAYLOAD_NAMESPACE, _uuid(operation_id, "operation_id")))

    @staticmethod
    def _same_record(actual: ConnectedReadResultRecord, expected: ConnectedReadResultRecord) -> bool:
        for name in ConnectedReadResultRecord.__dataclass_fields__:
            if name == "completed_at":
                continue
            left = getattr(actual, name)
            right = getattr(expected, name)
            if isinstance(left, str) and isinstance(right, str) and name.endswith("sha256"):
                if not hmac.compare_digest(left, right):
                    return False
            elif left != right:
                return False
        return True

    @staticmethod
    def _candidate(
        *,
        reference: ConnectedPayloadRef,
        decoded: _DecodedEnvelope,
    ) -> ConnectedReadResultRecord:
        terminal = decoded.durable.terminal
        return ConnectedReadResultRecord(
            completion_id=decoded.completion_id,
            operation_id=terminal.operation_id,
            action_id=terminal.operation_id,
            owner_id=decoded.owner_id,
            connection_id=decoded.connection_id,
            provider=terminal.provider,
            resource=terminal.resource,
            action=terminal.action,
            result_payload_id=decoded.result_payload_id,
            result_commitment_key_id=reference.commitment_key_id,
            result_payload_sha256=reference.payload_sha256,
            result_reference_binding_sha256=reference.binding_sha256,
            terminal_binding_sha256=terminal.binding_sha256,
            authority_sha256=terminal.authority_sha256,
            idempotency_key_sha256=terminal.idempotency_key_hash,
            claim_id=decoded.claim_id,
            fencing_token=decoded.fencing_token,
            read_use_nonce=decoded.read_use_nonce,
            observed_at=terminal.observed_at,
            resource_version_sha256=terminal.resource_version_sha256,
            completed_at=None,
        )

    @staticmethod
    def _validate_expected(
        decoded: _DecodedEnvelope,
        *,
        lookup: ConnectedActionLookupRecord,
        reference: ConnectedPayloadRef,
        terminal: ConnectedReadTerminalRecord | None = None,
    ) -> None:
        actual_terminal = decoded.durable.terminal
        if (
            decoded.completion_id != ConnectedReadResultCoordinator.completion_id(
                lookup.operation_id
            )
            or decoded.result_payload_id
            != ConnectedReadResultCoordinator.payload_id(lookup.operation_id)
            or decoded.owner_id != lookup.owner_id
            or decoded.connection_id != lookup.connection_id
            or actual_terminal.operation_id != lookup.operation_id
            or actual_terminal.provider is not lookup.provider
            or actual_terminal.resource is not lookup.resource
            or actual_terminal.action is not lookup.action
            or actual_terminal.binding_sha256 != lookup.binding_sha256
            or actual_terminal.idempotency_key_hash != lookup.idempotency_key_hash
            or reference.payload_id != decoded.result_payload_id
            or reference.owner_id != decoded.owner_id
            or reference.connection_id != decoded.connection_id
            or reference.action_id != lookup.operation_id
            or reference.provider is not lookup.provider
            or reference.action is not lookup.action
            or (terminal is not None and actual_terminal != terminal)
        ):
            raise ConnectedReadResultError(
                "CONNECTED_READ_RESULT_BINDING_MISMATCH"
            )

    async def _resolve_reference(
        self, lookup: ConnectedActionLookupRecord
    ) -> ConnectedPayloadRef | None:
        try:
            return await self._references.resolve_reference(
                owner_id=lookup.owner_id,
                payload_id=self.payload_id(lookup.operation_id),
                connection_id=lookup.connection_id,
                action_id=lookup.operation_id,
                provider=lookup.provider,
                action=lookup.action,
            )
        except Exception:
            raise ConnectedReadResultError(
                "CONNECTED_READ_RESULT_STORE_UNAVAILABLE"
            ) from None

    async def _open(
        self,
        reference: ConnectedPayloadRef,
        *,
        lookup: ConnectedActionLookupRecord,
        terminal: ConnectedReadTerminalRecord | None = None,
    ) -> _DecodedEnvelope:
        try:
            decoded = _decode_envelope(await self._vault.open_json(reference))
        except ConnectedPayloadVaultError as error:
            if error.code == "PAYLOAD_EXPIRED":
                raise ConnectedReadResultError("CONNECTED_READ_RESULT_EXPIRED") from None
            if error.code == "PAYLOAD_NOT_FOUND":
                raise ConnectedReadResultError("CONNECTED_READ_RESULT_NOT_FOUND") from None
            raise ConnectedReadResultError(
                "CONNECTED_READ_RESULT_BINDING_MISMATCH"
            ) from None
        except ConnectedReadResultError:
            raise
        except Exception:
            raise ConnectedReadResultError(
                "CONNECTED_READ_RESULT_BINDING_MISMATCH"
            ) from None
        self._validate_expected(decoded, lookup=lookup, reference=reference, terminal=terminal)
        return decoded

    async def _settle_decoded(
        self,
        *,
        lookup: ConnectedActionLookupRecord,
        reference: ConnectedPayloadRef,
        decoded: _DecodedEnvelope,
    ) -> ConnectedDurableReadResult:
        candidate = self._candidate(reference=reference, decoded=decoded)
        try:
            settled = await self._store.settle_once(candidate)
        except ConnectedReadResultError:
            raise
        except Exception:
            raise ConnectedReadResultError(
                "CONNECTED_READ_RESULT_EFFECT_UNKNOWN"
            ) from None
        if not self._same_record(settled, candidate):
            raise ConnectedReadResultError(
                "CONNECTED_READ_RESULT_BINDING_MISMATCH"
            )
        self._validate_expected(decoded, lookup=lookup, reference=reference)
        return decoded.durable

    async def settle(
        self,
        *,
        invocation: ConnectedActionInvocation,
        claim: ConnectedActionClaim,
        terminal: ConnectedReadTerminalRecord,
        observation: ConnectedReadObservation,
        deadline: datetime,
    ) -> ConnectedDurableReadResult:
        if not isinstance(invocation, ConnectedActionInvocation):
            raise TypeError("invocation must be ConnectedActionInvocation")
        lookup = ConnectedActionLookupRecord(
            operation_id=invocation.intent.action_id,
            owner_id=invocation.intent.owner_id,
            task_id=invocation.intent.task_id,
            turn_id=invocation.intent.turn_id,
            connection_id=invocation.intent.connection_id,
            provider=invocation.intent.provider,
            resource=invocation.intent.resource,
            action=invocation.intent.action,
            parameters_sha256=invocation.intent.parameters_sha256,
            resource_version_sha256=invocation.intent.resource_version_sha256,
            binding_sha256=invocation.binding_sha256,
            idempotency_key_hash=terminal.idempotency_key_hash,
        )
        reference_time = _aware(self._now())
        if reference_time >= _aware(deadline):
            raise ConnectedReadResultError("CONNECTED_READ_RESULT_EFFECT_UNKNOWN")
        completion_id = self.completion_id(lookup.operation_id)
        payload_id = self.payload_id(lookup.operation_id)
        value = _envelope(
            completion_id=completion_id,
            result_payload_id=payload_id,
            owner_id=lookup.owner_id,
            connection_id=lookup.connection_id,
            claim=claim,
            terminal=terminal,
            observation=observation,
        )
        try:
            reference = await self._vault.seal_json(
                payload_id=payload_id,
                owner_id=lookup.owner_id,
                connection_id=lookup.connection_id,
                action_id=lookup.operation_id,
                provider=lookup.provider,
                action=lookup.action,
                value=value,
                created_at=reference_time,
                expires_at=reference_time + self._retention,
            )
        except ConnectedPayloadVaultError as error:
            code = (
                "CONNECTED_READ_RESULT_TOO_LARGE"
                if error.code == "PAYLOAD_TOO_LARGE"
                else "CONNECTED_READ_RESULT_EFFECT_UNKNOWN"
            )
            raise ConnectedReadResultError(code) from None
        decoded = await self._open(reference, lookup=lookup, terminal=terminal)
        return await self._settle_decoded(
            lookup=lookup,
            reference=reference,
            decoded=decoded,
        )

    async def replay(
        self,
        *,
        lookup: ConnectedActionLookupRecord,
        terminal: ConnectedReadTerminalRecord,
        deadline: datetime,
    ) -> ConnectedDurableReadResult:
        if _aware(self._now()) >= _aware(deadline):
            raise ConnectedReadResultError("CONNECTED_READ_RESULT_STORE_UNAVAILABLE")
        inspection = await self._store.inspect(
            owner_id=lookup.owner_id,
            operation_id=lookup.operation_id,
            completion_id=self.completion_id(lookup.operation_id),
            idempotency_key_sha256=lookup.idempotency_key_hash,
        )
        if inspection.status is not ConnectedReadResultStatus.TERMINAL:
            raise ConnectedReadResultError("CONNECTED_READ_RESULT_NOT_FOUND")
        assert inspection.record is not None
        reference = await self._resolve_reference(lookup)
        if reference is None:
            raise ConnectedReadResultError("CONNECTED_READ_RESULT_NOT_FOUND")
        decoded = await self._open(reference, lookup=lookup, terminal=terminal)
        expected = self._candidate(reference=reference, decoded=decoded)
        if not self._same_record(inspection.record, expected):
            raise ConnectedReadResultError(
                "CONNECTED_READ_RESULT_BINDING_MISMATCH"
            )
        return decoded.durable

    async def recover(
        self,
        *,
        lookup: ConnectedActionLookupRecord,
        claim: ConnectedActionClaim,
        deadline: datetime,
    ) -> ConnectedDurableReadResult | None:
        """Recover a staged result or prove a fresh read lease may be issued.

        Once the durable one-use read nonce was consumed, absence of a staged
        encrypted result is EffectUnknown.  The caller must never issue another
        provider read for that action.
        """

        if _aware(self._now()) >= _aware(deadline):
            raise ConnectedReadResultError("CONNECTED_READ_RESULT_EFFECT_UNKNOWN")
        inspection = await self._store.inspect(
            owner_id=lookup.owner_id,
            operation_id=lookup.operation_id,
            completion_id=self.completion_id(lookup.operation_id),
            idempotency_key_sha256=lookup.idempotency_key_hash,
        )
        if inspection.status is ConnectedReadResultStatus.TERMINAL:
            assert inspection.record is not None
            terminal = ConnectedReadTerminalRecord(
                operation_id=inspection.record.operation_id,
                provider=inspection.record.provider,
                resource=inspection.record.resource,
                action=inspection.record.action,
                binding_sha256=inspection.record.terminal_binding_sha256,
                authority_sha256=inspection.record.authority_sha256,
                idempotency_key_hash=inspection.record.idempotency_key_sha256,
                observed_at=inspection.record.observed_at,
                resource_version_sha256=inspection.record.resource_version_sha256,
            )
            return await self.replay(lookup=lookup, terminal=terminal, deadline=deadline)
        if inspection.status is ConnectedReadResultStatus.NOT_CONSUMED:
            return None
        if inspection.status is ConnectedReadResultStatus.ABSENT:
            raise ConnectedReadResultError("CONNECTED_READ_RESULT_EFFECT_UNKNOWN")
        if (
            claim.status is not ConnectedActionClaimStatus.ACCESS_GRANTED
            or claim.binding_sha256 != lookup.binding_sha256
        ):
            raise ConnectedReadResultError("CONNECTED_READ_RESULT_EFFECT_UNKNOWN")
        reference = await self._resolve_reference(lookup)
        if reference is None:
            raise ConnectedReadResultError("CONNECTED_READ_RESULT_EFFECT_UNKNOWN")
        try:
            decoded = await self._open(reference, lookup=lookup)
            if (
                decoded.durable.terminal.authority_sha256 != claim.authority_sha256
                or (claim.fencing_token is not None and decoded.fencing_token != claim.fencing_token)
                or (claim.access_use_nonce is not None and decoded.read_use_nonce != claim.access_use_nonce)
            ):
                raise ConnectedReadResultError(
                    "CONNECTED_READ_RESULT_BINDING_MISMATCH"
                )
            return await self._settle_decoded(
                lookup=lookup,
                reference=reference,
                decoded=decoded,
            )
        except ConnectedReadResultError as error:
            if error.code == "CONNECTED_READ_RESULT_BINDING_MISMATCH":
                raise
            raise ConnectedReadResultError("CONNECTED_READ_RESULT_EFFECT_UNKNOWN") from None


__all__ = [
    "ConnectedReadResultCoordinator",
    "ConnectedReadResultError",
    "ConnectedReadResultInspection",
    "ConnectedReadResultRecord",
    "ConnectedReadResultStatus",
    "ConnectedReadResultStore",
    "SupabaseConnectedReadResultStore",
]
