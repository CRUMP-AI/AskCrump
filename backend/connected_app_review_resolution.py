"""Encrypted approval-review envelopes and owner-scoped preview resolution."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol
from uuid import UUID
from zoneinfo import ZoneInfo

from .connected_app_contracts import EventSnapshot
from .connected_app_payload_envelope import ConnectedActionPayloadEnvelope
from .connected_app_payload_vault import ConnectedPayloadRef
from .connected_app_policy import ConnectorActionKind, ConnectorProvider
from .connected_app_service import (
    ConnectedApprovalReviewPreview,
    ConnectedCalendarReviewPayload,
    ConnectedMailReviewPayload,
    ConnectedReviewPayload,
)


_VERSION = "connected-approval-review-envelope-v1"
_MAIL_ACTIONS = frozenset(
    {
        ConnectorActionKind.MAIL_CREATE_DRAFT,
        ConnectorActionKind.MAIL_SEND,
        ConnectorActionKind.MAIL_REPLY,
    }
)
_CALENDAR_ACTIONS = frozenset(
    {
        ConnectorActionKind.CALENDAR_CREATE,
        ConnectorActionKind.CALENDAR_UPDATE,
        ConnectorActionKind.CALENDAR_CANCEL,
    }
)


class ConnectedReviewResolutionError(RuntimeError):
    _CODES = frozenset(
        {
            "CONNECTED_PREVIEW_NOT_FOUND",
            "CONNECTED_PREVIEW_BINDING_MISMATCH",
            "CONNECTED_PREVIEW_UNAVAILABLE",
        }
    )

    def __init__(self, code: str) -> None:
        if code not in self._CODES:
            raise ValueError("preview resolution error is invalid")
        self.code = code
        super().__init__(code)


class ConnectedReviewReferenceLookup(Protocol):
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


class ConnectedReviewPayloadReader(Protocol):
    async def open_json(self, reference: ConnectedPayloadRef) -> object: ...


def _exact(value: object, keys: frozenset[str]) -> dict[str, object]:
    if type(value) is not dict or set(value) != keys:
        raise ValueError("review envelope shape is invalid")
    return value


def _text(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("review envelope text is invalid")
    return value


def _optional_text(value: object) -> str | None:
    return None if value is None else _text(value)


def _strings(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError("review envelope list is invalid")
    return tuple(_text(item) for item in value)


def _integer(value: object) -> int:
    if type(value) is not int:
        raise ValueError("review envelope integer is invalid")
    return value


def _uuid(value: object) -> str:
    text = _text(value)
    try:
        parsed = UUID(text)
    except (ValueError, TypeError, AttributeError):
        raise ValueError("review envelope UUID is invalid") from None
    if str(parsed) != text:
        raise ValueError("review envelope UUID is invalid")
    return text


def _instant(value: object) -> datetime:
    try:
        parsed = datetime.fromisoformat(_text(value).replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("review envelope datetime is invalid") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("review envelope datetime is invalid")
    return parsed.astimezone(timezone.utc)


def _instant_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _review_payload_value(value: ConnectedReviewPayload) -> dict[str, object]:
    if isinstance(value, ConnectedMailReviewPayload):
        return {"kind": "mail", "value": value.public()}
    if isinstance(value, ConnectedCalendarReviewPayload):
        return {"kind": "calendar", "value": value.public()}
    raise TypeError("review payload is invalid")


def _review_payload(value: object) -> ConnectedReviewPayload:
    row = _exact(value, frozenset({"kind", "value"}))
    kind = _text(row["kind"])
    if kind == "mail":
        payload = _exact(
            row["value"],
            frozenset({"account", "to", "cc", "bcc", "subject", "bodyText", "replyContext"}),
        )
        return ConnectedMailReviewPayload(
            account=_text(payload["account"]),
            to=_strings(payload["to"]),
            cc=_strings(payload["cc"]),
            bcc=_strings(payload["bcc"]),
            subject=_text(payload["subject"]),
            body_text=_text(payload["bodyText"]),
            reply_context=_optional_text(payload["replyContext"]),
        )
    if kind == "calendar":
        payload = _exact(
            row["value"],
            frozenset(
                {
                    "calendar",
                    "eventContext",
                    "title",
                    "start",
                    "end",
                    "timeZone",
                    "attendees",
                    "location",
                    "description",
                }
            ),
        )
        return ConnectedCalendarReviewPayload(
            calendar=_text(payload["calendar"]),
            event_context=_optional_text(payload["eventContext"]),
            title=_text(payload["title"]),
            start=_text(payload["start"]),
            end=_text(payload["end"]),
            time_zone=_text(payload["timeZone"]),
            attendees=_strings(payload["attendees"]),
            location=_text(payload["location"]),
            description=_text(payload["description"]),
        )
    raise ValueError("review payload kind is invalid")


def _event_value(value: EventSnapshot | None) -> dict[str, object] | None:
    if value is None:
        return None
    return {
        "eventId": value.event_id,
        "calendarId": value.calendar_id,
        "resourceVersion": value.resource_version,
        "startsAt": _instant_text(value.starts_at),
        "endsAt": _instant_text(value.ends_at),
        "timeZone": value.time_zone,
        "title": value.title,
        "description": value.description,
        "location": value.location,
        "attendees": list(value.attendees),
        "organizer": value.organizer,
        "status": value.status,
    }


def _event(value: object) -> EventSnapshot | None:
    if value is None:
        return None
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
    zone = _text(row["timeZone"])
    try:
        starts = _instant(row["startsAt"]).astimezone(ZoneInfo(zone))
        ends = _instant(row["endsAt"]).astimezone(ZoneInfo(zone))
    except (TypeError, ValueError):
        raise ValueError("review envelope timezone is invalid") from None
    return EventSnapshot(
        event_id=_text(row["eventId"]),
        calendar_id=_text(row["calendarId"]),
        resource_version=_text(row["resourceVersion"]),
        starts_at=starts,
        ends_at=ends,
        time_zone=zone,
        title=_text(row["title"]),
        description=_text(row["description"]),
        location=_text(row["location"]),
        attendees=_strings(row["attendees"]),
        organizer=_optional_text(row["organizer"]),
        status=_text(row["status"]),
    )


@dataclass(frozen=True, slots=True, repr=False)
class ConnectedApprovalReviewEnvelope:
    approval_id: str
    action_id: str
    connection_id: str
    parameters_sha256: str = field(repr=False)
    resource_version_sha256: str | None = field(repr=False)
    action_payload: ConnectedActionPayloadEnvelope = field(repr=False, compare=False)
    review_payload: ConnectedReviewPayload = field(repr=False, compare=False)
    authoritative_event: EventSnapshot | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        for value in (self.approval_id, self.action_id, self.connection_id):
            _uuid(value)
        # Constructing the service preview is the single source of truth for
        # exact request-to-preview and cancellation-snapshot validation.
        ConnectedApprovalReviewPreview(
            # The approval binding is deliberately not stored inside this
            # envelope.  It includes the encrypted preview commitment, so
            # embedding it in the preview would create an impossible circular
            # commitment.  Resolution supplies the authoritative binding from
            # the database row after the ciphertext commitment is known.
            approval_binding_sha256="0" * 64,
            parameters_sha256=self.parameters_sha256,
            preview_sha256="0" * 64,
            payload=self.review_payload,
            connection_id=self.connection_id,
            action=self.action_payload.action,
            resource_version_sha256=self.resource_version_sha256,
            provider_request=self.action_payload.request,
            authoritative_event=self.authoritative_event,
        )

    def to_value(self) -> dict[str, object]:
        return {
            "version": _VERSION,
            "approvalId": self.approval_id,
            "actionId": self.action_id,
            "connectionId": self.connection_id,
            "parametersSha256": self.parameters_sha256,
            "resourceVersionSha256": self.resource_version_sha256,
            "actionPayload": self.action_payload.to_value(),
            "reviewPayload": _review_payload_value(self.review_payload),
            "authoritativeEvent": _event_value(self.authoritative_event),
        }

    @classmethod
    def from_value(cls, value: object) -> ConnectedApprovalReviewEnvelope:
        row = _exact(
            value,
            frozenset(
                {
                    "version",
                    "approvalId",
                    "actionId",
                    "connectionId",
                    "parametersSha256",
                    "resourceVersionSha256",
                    "actionPayload",
                    "reviewPayload",
                    "authoritativeEvent",
                }
            ),
        )
        if row["version"] != _VERSION:
            raise ValueError("review envelope version is invalid")
        return cls(
            approval_id=_uuid(row["approvalId"]),
            action_id=_uuid(row["actionId"]),
            connection_id=_uuid(row["connectionId"]),
            parameters_sha256=_text(row["parametersSha256"]),
            resource_version_sha256=_optional_text(row["resourceVersionSha256"]),
            action_payload=ConnectedActionPayloadEnvelope.from_value(row["actionPayload"]),
            review_payload=_review_payload(row["reviewPayload"]),
            authoritative_event=_event(row["authoritativeEvent"]),
        )

    def __repr__(self) -> str:
        return "ConnectedApprovalReviewEnvelope(content='<redacted>')"


class ConnectedApprovalPreviewVaultResolver:
    """Concrete ``ConnectedApprovalPreviewResolver`` over the encrypted vault."""

    def __init__(
        self, *, references: ConnectedReviewReferenceLookup, payloads: ConnectedReviewPayloadReader
    ):
        if not callable(getattr(references, "resolve_reference", None)):
            raise TypeError("review reference lookup is invalid")
        if not callable(getattr(payloads, "open_json", None)):
            raise TypeError("review payload reader is invalid")
        self._references = references
        self._payloads = payloads

    async def resolve(
        self,
        *,
        owner_id: str,
        approval_id: str,
        connection_id: str,
        action_id: str,
        provider: ConnectorProvider,
        action: ConnectorActionKind,
        approval_binding_sha256: str,
        parameters_sha256: str,
        resource_version_sha256: str | None,
        review_payload_ref: str,
        preview_sha256: str,
    ) -> ConnectedApprovalReviewPreview:
        try:
            _uuid(owner_id)
            _uuid(approval_id)
            _uuid(connection_id)
            _uuid(action_id)
            _uuid(review_payload_ref)
            if not isinstance(provider, ConnectorProvider) or not isinstance(
                action, ConnectorActionKind
            ):
                raise ValueError("review authority is invalid")
            for value in (approval_binding_sha256, parameters_sha256, preview_sha256):
                if not isinstance(value, str) or len(value) != 64:
                    raise ValueError("review authority is invalid")
                int(value, 16)
            if resource_version_sha256 is not None:
                if not isinstance(resource_version_sha256, str) or len(
                    resource_version_sha256
                ) != 64:
                    raise ValueError("review authority is invalid")
                int(resource_version_sha256, 16)
        except (TypeError, ValueError):
            raise ConnectedReviewResolutionError("CONNECTED_PREVIEW_BINDING_MISMATCH") from None
        try:
            reference = await self._references.resolve_reference(
                owner_id=owner_id,
                payload_id=review_payload_ref,
                connection_id=connection_id,
                action_id=action_id,
                provider=provider,
                action=action,
            )
        except Exception:
            raise ConnectedReviewResolutionError("CONNECTED_PREVIEW_UNAVAILABLE") from None
        if reference is None:
            raise ConnectedReviewResolutionError("CONNECTED_PREVIEW_NOT_FOUND")
        if (
            not isinstance(reference, ConnectedPayloadRef)
            or reference.payload_id != review_payload_ref
            or reference.owner_id != owner_id
            or reference.connection_id != connection_id
            or reference.action_id != action_id
            or reference.provider is not provider
            or reference.action is not action
            or reference.payload_sha256 != preview_sha256
        ):
            raise ConnectedReviewResolutionError("CONNECTED_PREVIEW_BINDING_MISMATCH")
        try:
            value = await self._payloads.open_json(reference)
            envelope = ConnectedApprovalReviewEnvelope.from_value(value)
        except Exception:
            raise ConnectedReviewResolutionError("CONNECTED_PREVIEW_UNAVAILABLE") from None
        if (
            envelope.approval_id != approval_id
            or envelope.action_id != action_id
            or envelope.connection_id != connection_id
            or envelope.action_payload.action is not action
            or envelope.parameters_sha256 != parameters_sha256
            or envelope.resource_version_sha256 != resource_version_sha256
        ):
            raise ConnectedReviewResolutionError("CONNECTED_PREVIEW_BINDING_MISMATCH")
        try:
            return ConnectedApprovalReviewPreview(
                approval_binding_sha256=approval_binding_sha256,
                parameters_sha256=envelope.parameters_sha256,
                preview_sha256=preview_sha256,
                payload=envelope.review_payload,
                connection_id=envelope.connection_id,
                action=envelope.action_payload.action,
                resource_version_sha256=envelope.resource_version_sha256,
                provider_request=envelope.action_payload.request,
                authoritative_event=envelope.authoritative_event,
            )
        except (TypeError, ValueError):
            raise ConnectedReviewResolutionError("CONNECTED_PREVIEW_BINDING_MISMATCH") from None

    def __repr__(self) -> str:
        return "ConnectedApprovalPreviewVaultResolver(secrets='<redacted>')"
