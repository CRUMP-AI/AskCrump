"""Authenticated, owner-scoped projection of encrypted connected read results.

Provider mail and calendar values are untrusted customer data.  The public
surface in this module first obtains a content-free, database-attested index,
then asks :class:`ConnectedReadResultCoordinator` to re-open the exact settled
encrypted result.  It never accepts a client supplied action binding and never
logs or interpolates provider content.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Callable, Protocol
from uuid import UUID

from .connected_app_contracts import (
    EventSnapshot,
    FreeBusyWindow,
    MessageSnapshot,
    MessageSummary,
)
from .connected_app_policy import ConnectorActionKind, ConnectorProvider, ConnectorResource
from .connected_app_read_results import ConnectedReadResultCoordinator
from .connected_app_runtime import (
    ConnectedActionLookupRecord,
    ConnectedDurableReadResult,
    ConnectedReadTerminalRecord,
)


_READ_ACTIONS = frozenset(
    {
        ConnectorActionKind.MAIL_SEARCH,
        ConnectorActionKind.MAIL_GET,
        ConnectorActionKind.CALENDAR_LIST,
        ConnectorActionKind.CALENDAR_GET,
        ConnectorActionKind.CALENDAR_FREE_BUSY,
    }
)
_MAX_RESULT_LIFETIME = timedelta(days=7)
_OPEN_DEADLINE = timedelta(seconds=5)
_MAX_LIST_ITEMS = 100


class ConnectedOwnerReadResultError(RuntimeError):
    """Fixed, content-free error safe for an authenticated API response."""

    _CODES = frozenset(
        {
            "CONNECTED_READ_RESULT_EXPIRED",
            "CONNECTED_READ_RESULT_INVALID",
            "CONNECTED_READ_RESULT_NOT_FOUND",
            "CONNECTED_READ_RESULT_UNAVAILABLE",
        }
    )

    def __init__(self, code: str, status_code: int) -> None:
        self.code = code if code in self._CODES else "CONNECTED_READ_RESULT_UNAVAILABLE"
        self.status_code = status_code if 400 <= status_code <= 599 else 503
        super().__init__(self.code)


def _uuid(value: object) -> str:
    if not isinstance(value, str):
        raise ConnectedOwnerReadResultError("CONNECTED_READ_RESULT_INVALID", 502)
    try:
        canonical = str(UUID(value))
    except (TypeError, ValueError, AttributeError):
        raise ConnectedOwnerReadResultError("CONNECTED_READ_RESULT_INVALID", 502) from None
    if canonical != value:
        raise ConnectedOwnerReadResultError("CONNECTED_READ_RESULT_INVALID", 502)
    return value


def _sha(value: object) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ConnectedOwnerReadResultError("CONNECTED_READ_RESULT_INVALID", 502)
    return value


def _time(value: object) -> datetime:
    if not isinstance(value, str) or not 1 <= len(value) <= 64:
        raise ConnectedOwnerReadResultError("CONNECTED_READ_RESULT_INVALID", 502)
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ConnectedOwnerReadResultError("CONNECTED_READ_RESULT_INVALID", 502) from None
    if result.tzinfo is None or result.utcoffset() is None:
        raise ConnectedOwnerReadResultError("CONNECTED_READ_RESULT_INVALID", 502)
    return result.astimezone(UTC)


def _enum(value: object, expected: type[Any]) -> Any:
    try:
        return expected(value)
    except (TypeError, ValueError):
        raise ConnectedOwnerReadResultError("CONNECTED_READ_RESULT_INVALID", 502) from None


@dataclass(frozen=True, slots=True, repr=False)
class ConnectedOwnerReadResultIndex:
    operation_id: str
    owner_id: str
    task_id: str
    turn_id: str
    connection_id: str
    provider: ConnectorProvider
    resource: ConnectorResource
    action: ConnectorActionKind
    parameters_sha256: str
    request_resource_version_sha256: str | None
    terminal_resource_version_sha256: str | None
    invocation_binding_sha256: str
    idempotency_key_sha256: str
    terminal_binding_sha256: str
    authority_sha256: str
    observed_at: datetime
    result_payload_id: str
    expires_at: datetime

    def __post_init__(self) -> None:
        for name in (
            "operation_id",
            "owner_id",
            "task_id",
            "turn_id",
            "connection_id",
            "result_payload_id",
        ):
            object.__setattr__(self, name, _uuid(getattr(self, name)))
        if not isinstance(self.provider, ConnectorProvider) or not isinstance(
            self.resource, ConnectorResource
        ):
            raise ConnectedOwnerReadResultError("CONNECTED_READ_RESULT_INVALID", 502)
        if not isinstance(self.action, ConnectorActionKind) or self.action not in _READ_ACTIONS:
            raise ConnectedOwnerReadResultError("CONNECTED_READ_RESULT_INVALID", 502)
        for name in (
            "parameters_sha256",
            "invocation_binding_sha256",
            "idempotency_key_sha256",
            "terminal_binding_sha256",
            "authority_sha256",
        ):
            object.__setattr__(self, name, _sha(getattr(self, name)))
        for name in (
            "request_resource_version_sha256",
            "terminal_resource_version_sha256",
        ):
            if getattr(self, name) is not None:
                object.__setattr__(self, name, _sha(getattr(self, name)))
        if (
            not isinstance(self.observed_at, datetime)
            or self.observed_at.tzinfo is None
            or self.observed_at.utcoffset() is None
            or not isinstance(self.expires_at, datetime)
            or self.expires_at.tzinfo is None
            or self.expires_at.utcoffset() is None
        ):
            raise ConnectedOwnerReadResultError("CONNECTED_READ_RESULT_INVALID", 502)
        observed = self.observed_at.astimezone(UTC)
        expires = self.expires_at.astimezone(UTC)
        # The encrypted envelope's database constraint is the authoritative
        # seven-day lifetime. Observation can precede envelope creation by the
        # bounded provider/encoding step, so tolerate only that small skew in
        # this redundant public-boundary check.
        if expires <= observed or expires - observed > _MAX_RESULT_LIFETIME + timedelta(minutes=5):
            raise ConnectedOwnerReadResultError("CONNECTED_READ_RESULT_INVALID", 502)
        if self.action.value.split(".", 1)[0] != self.resource.value:
            raise ConnectedOwnerReadResultError("CONNECTED_READ_RESULT_INVALID", 502)
        object.__setattr__(self, "observed_at", observed)
        object.__setattr__(self, "expires_at", expires)
        if (
            ConnectedReadResultCoordinator.payload_id(self.operation_id)
            != self.result_payload_id
        ):
            raise ConnectedOwnerReadResultError("CONNECTED_READ_RESULT_INVALID", 502)
        if self.invocation_binding_sha256 != self.terminal_binding_sha256:
            raise ConnectedOwnerReadResultError("CONNECTED_READ_RESULT_INVALID", 502)

    def lookup(self) -> ConnectedActionLookupRecord:
        return ConnectedActionLookupRecord(
            operation_id=self.operation_id,
            owner_id=self.owner_id,
            task_id=self.task_id,
            turn_id=self.turn_id,
            connection_id=self.connection_id,
            provider=self.provider,
            resource=self.resource,
            action=self.action,
            parameters_sha256=self.parameters_sha256,
            resource_version_sha256=self.request_resource_version_sha256,
            binding_sha256=self.invocation_binding_sha256,
            idempotency_key_hash=self.idempotency_key_sha256,
        )

    def terminal(self) -> ConnectedReadTerminalRecord:
        return ConnectedReadTerminalRecord(
            operation_id=self.operation_id,
            provider=self.provider,
            resource=self.resource,
            action=self.action,
            binding_sha256=self.terminal_binding_sha256,
            authority_sha256=self.authority_sha256,
            idempotency_key_hash=self.idempotency_key_sha256,
            observed_at=self.observed_at,
            resource_version_sha256=self.terminal_resource_version_sha256,
        )

    def __repr__(self) -> str:
        return "ConnectedOwnerReadResultIndex(content='<encrypted>')"


class ConnectedOwnerReadResultRPC(Protocol):
    async def rpc(
        self,
        function_name: str,
        payload: dict[str, object],
        *,
        retry_transient: bool = False,
    ) -> object: ...


_INDEX_KEYS = frozenset(
    {
        "operation_id",
        "owner_id",
        "task_id",
        "turn_id",
        "connection_id",
        "provider",
        "resource",
        "action",
        "parameters_sha256",
        "request_resource_version_sha256",
        "terminal_resource_version_sha256",
        "invocation_binding_sha256",
        "idempotency_key_sha256",
        "terminal_binding_sha256",
        "authority_sha256",
        "observed_at",
        "result_payload_id",
        "expires_at",
    }
)


class SupabaseConnectedOwnerReadResultIndex:
    """Strict service-role adapter for the owner/result lookup RPC."""

    def __init__(self, database: ConnectedOwnerReadResultRPC) -> None:
        if not callable(getattr(database, "rpc", None)):
            raise TypeError("connected read-result index RPC is invalid")
        self._database = database

    async def get(
        self, *, owner_id: str, result_payload_id: str
    ) -> ConnectedOwnerReadResultIndex | None:
        owner = _uuid(owner_id)
        payload = _uuid(result_payload_id)
        try:
            value = await self._database.rpc(
                "connected_app_open_read_result_v1",
                {"p_owner_id": owner, "p_result_payload_id": payload},
                retry_transient=True,
            )
        except Exception:
            raise ConnectedOwnerReadResultError(
                "CONNECTED_READ_RESULT_UNAVAILABLE", 503
            ) from None
        if value is None:
            return None
        if isinstance(value, list):
            if len(value) != 1:
                raise ConnectedOwnerReadResultError("CONNECTED_READ_RESULT_INVALID", 502)
            value = value[0]
        if type(value) is not dict or frozenset(value) != _INDEX_KEYS:
            raise ConnectedOwnerReadResultError("CONNECTED_READ_RESULT_INVALID", 502)
        return ConnectedOwnerReadResultIndex(
            operation_id=_uuid(value["operation_id"]),
            owner_id=_uuid(value["owner_id"]),
            task_id=_uuid(value["task_id"]),
            turn_id=_uuid(value["turn_id"]),
            connection_id=_uuid(value["connection_id"]),
            provider=_enum(value["provider"], ConnectorProvider),
            resource=_enum(value["resource"], ConnectorResource),
            action=_enum(value["action"], ConnectorActionKind),
            parameters_sha256=_sha(value["parameters_sha256"]),
            request_resource_version_sha256=(
                None
                if value["request_resource_version_sha256"] is None
                else _sha(value["request_resource_version_sha256"])
            ),
            terminal_resource_version_sha256=(
                None
                if value["terminal_resource_version_sha256"] is None
                else _sha(value["terminal_resource_version_sha256"])
            ),
            invocation_binding_sha256=_sha(value["invocation_binding_sha256"]),
            idempotency_key_sha256=_sha(value["idempotency_key_sha256"]),
            terminal_binding_sha256=_sha(value["terminal_binding_sha256"]),
            authority_sha256=_sha(value["authority_sha256"]),
            observed_at=_time(value["observed_at"]),
            result_payload_id=_uuid(value["result_payload_id"]),
            expires_at=_time(value["expires_at"]),
        )


def _clip(value: str, maximum: int) -> tuple[str, bool]:
    encoded = value.encode("utf-8")
    if len(encoded) <= maximum:
        return value, False
    return encoded[:maximum].decode("utf-8", errors="ignore"), True


def _strings(values: tuple[str, ...], *, maximum: int, each: int) -> list[str]:
    return [_clip(value, each)[0] for value in values[:maximum]]


def _message_summary(value: MessageSummary) -> dict[str, object]:
    subject, truncated = _clip(value.subject, 2_048)
    return {
        "kind": "mail_summary",
        "messageId": value.message_id,
        "threadId": value.thread_id,
        "receivedAt": value.received_at.astimezone(UTC).isoformat(),
        "subject": subject,
        "subjectTruncated": truncated,
        "sender": _clip(value.sender, 512)[0],
        "recipients": _strings(value.recipients, maximum=20, each=512),
        "labels": _strings(value.labels, maximum=20, each=128),
        "hasAttachments": value.has_attachments,
        "trustBoundary": "untrusted_external_data",
    }


def _message(value: MessageSnapshot) -> dict[str, object]:
    subject, subject_truncated = _clip(value.subject, 2_048)
    body, body_truncated = _clip(value.body_text, 80_000)
    return {
        "kind": "mail_message",
        "messageId": value.message_id,
        "threadId": value.thread_id,
        "receivedAt": value.received_at.astimezone(UTC).isoformat(),
        "subject": subject,
        "subjectTruncated": subject_truncated,
        "sender": _clip(value.sender, 512)[0],
        "recipients": _strings(value.recipients, maximum=20, each=512),
        "bodyText": body,
        "bodyTruncated": body_truncated,
        "attachmentCount": value.attachment_count,
        "trustBoundary": "untrusted_external_data",
    }


def _event(value: EventSnapshot) -> dict[str, object]:
    title, title_truncated = _clip(value.title, 2_048)
    description, description_truncated = _clip(value.description, 16_000)
    return {
        "kind": "calendar_event",
        "eventId": value.event_id,
        "calendarId": value.calendar_id,
        "startsAt": value.starts_at.astimezone(UTC).isoformat(),
        "endsAt": value.ends_at.astimezone(UTC).isoformat(),
        "timeZone": value.time_zone,
        "title": title,
        "titleTruncated": title_truncated,
        "description": description,
        "descriptionTruncated": description_truncated,
        "location": _clip(value.location, 2_048)[0],
        "attendees": _strings(value.attendees, maximum=30, each=512),
        "organizer": None if value.organizer is None else _clip(value.organizer, 512)[0],
        "status": value.status,
        "trustBoundary": "untrusted_external_data",
    }


def _window(value: FreeBusyWindow) -> dict[str, object]:
    return {
        "kind": "calendar_busy_window",
        "calendarId": value.calendar_id,
        "startsAt": value.starts_at.astimezone(UTC).isoformat(),
        "endsAt": value.ends_at.astimezone(UTC).isoformat(),
        "status": value.status,
        "trustBoundary": "untrusted_external_data",
    }


def _project(result: ConnectedDurableReadResult) -> tuple[dict[str, object], ...]:
    value = result.observation.value
    action = result.terminal.action
    if action is ConnectorActionKind.MAIL_SEARCH:
        if not isinstance(value, tuple) or any(type(item) is not MessageSummary for item in value):
            raise ConnectedOwnerReadResultError("CONNECTED_READ_RESULT_INVALID", 502)
        return tuple(_message_summary(item) for item in value[:_MAX_LIST_ITEMS])
    if action is ConnectorActionKind.MAIL_GET and type(value) is MessageSnapshot:
        return (_message(value),)
    if action is ConnectorActionKind.CALENDAR_LIST:
        if not isinstance(value, tuple) or any(type(item) is not EventSnapshot for item in value):
            raise ConnectedOwnerReadResultError("CONNECTED_READ_RESULT_INVALID", 502)
        return tuple(_event(item) for item in value[:_MAX_LIST_ITEMS])
    if action is ConnectorActionKind.CALENDAR_GET and type(value) is EventSnapshot:
        return (_event(value),)
    if action is ConnectorActionKind.CALENDAR_FREE_BUSY:
        if not isinstance(value, tuple) or any(type(item) is not FreeBusyWindow for item in value):
            raise ConnectedOwnerReadResultError("CONNECTED_READ_RESULT_INVALID", 502)
        return tuple(_window(item) for item in value[:_MAX_LIST_ITEMS])
    raise ConnectedOwnerReadResultError("CONNECTED_READ_RESULT_INVALID", 502)


class ConnectedOwnerReadResultService:
    """Open one exact settled result for its authenticated owner."""

    def __init__(
        self,
        *,
        index: SupabaseConnectedOwnerReadResultIndex,
        results: ConnectedReadResultCoordinator,
        composition_manifest_sha256: str,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if not callable(getattr(index, "get", None)) or not callable(
            getattr(results, "replay", None)
        ):
            raise TypeError("connected read-result surface dependency is invalid")
        self._index = index
        self._results = results
        self._composition_manifest_sha256 = _sha(composition_manifest_sha256)
        self._now = now

    @property
    def composition_manifest_sha256(self) -> str:
        return self._composition_manifest_sha256

    async def get(self, *, owner_id: str, result_reference_id: str) -> dict[str, object]:
        owner = _uuid(owner_id)
        reference = _uuid(result_reference_id)
        index = await self._index.get(owner_id=owner, result_payload_id=reference)
        if index is None or index.owner_id != owner or index.result_payload_id != reference:
            raise ConnectedOwnerReadResultError("CONNECTED_READ_RESULT_NOT_FOUND", 404)
        now = self._now()
        if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
            raise ConnectedOwnerReadResultError("CONNECTED_READ_RESULT_UNAVAILABLE", 503)
        reference_time = now.astimezone(UTC)
        if index.expires_at <= reference_time:
            raise ConnectedOwnerReadResultError("CONNECTED_READ_RESULT_EXPIRED", 410)
        try:
            durable = await self._results.replay(
                lookup=index.lookup(),
                terminal=index.terminal(),
                deadline=reference_time + _OPEN_DEADLINE,
            )
        except Exception as exc:
            code = str(getattr(exc, "code", ""))
            if code == "CONNECTED_READ_RESULT_EXPIRED":
                raise ConnectedOwnerReadResultError(
                    "CONNECTED_READ_RESULT_EXPIRED", 410
                ) from None
            if code == "CONNECTED_READ_RESULT_NOT_FOUND":
                raise ConnectedOwnerReadResultError(
                    "CONNECTED_READ_RESULT_NOT_FOUND", 404
                ) from None
            raise ConnectedOwnerReadResultError(
                "CONNECTED_READ_RESULT_UNAVAILABLE", 503
            ) from None
        if durable.terminal != index.terminal():
            raise ConnectedOwnerReadResultError("CONNECTED_READ_RESULT_INVALID", 502)
        items = _project(durable)
        source_value = durable.observation.value
        source_item_count = len(source_value) if isinstance(source_value, tuple) else 1
        return {
            "version": 1,
            "resultReferenceId": reference,
            "actionId": index.operation_id,
            "provider": index.provider.value,
            "resource": index.resource.value,
            "action": index.action.value,
            "observedAt": index.observed_at.isoformat(),
            "expiresAt": index.expires_at.isoformat(),
            "items": list(items),
            "itemCount": len(items),
            "itemsTruncated": source_item_count > len(items),
            "trustBoundary": "untrusted_external_data",
        }

    def __repr__(self) -> str:
        return "ConnectedOwnerReadResultService(content='<encrypted>')"


__all__ = [
    "ConnectedOwnerReadResultError",
    "ConnectedOwnerReadResultIndex",
    "ConnectedOwnerReadResultService",
    "SupabaseConnectedOwnerReadResultIndex",
]
