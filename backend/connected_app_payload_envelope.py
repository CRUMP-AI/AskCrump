"""Strict encrypted-payload envelope for connected mail and calendar actions.

The value produced here is content-bearing and must only be passed to
``ConnectedPayloadVault.seal_json``.  Its provider target digest deliberately
lives inside the encrypted value.  Durable control-plane rows bind the vault's
keyed commitment instead, so predictable recipients, subjects, message IDs,
and event details cannot be tested with an offline SHA-256 dictionary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hmac
import re
from typing import TypeAlias
from zoneinfo import ZoneInfo

from .connected_app_contracts import (
    CalendarCancelRequest,
    CalendarCreateRequest,
    CalendarFreeBusyRequest,
    CalendarGetRequest,
    CalendarListRequest,
    CalendarQuery,
    CalendarUpdateRequest,
    EventSpec,
    MailDraftRequest,
    MailDraftSpec,
    MailGetRequest,
    MailQuery,
    MailReplyRequest,
    MailSearchRequest,
    MailSendRequest,
)
from .connected_app_policy import ConnectorActionKind


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

_VERSION = "connected-action-payload-v1"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_REQUEST_TYPES: dict[ConnectorActionKind, type[ProviderRequest]] = {
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


def _exact(value: object, keys: frozenset[str]) -> dict[str, object]:
    if type(value) is not dict or set(value) != keys:
        raise ValueError("payload envelope shape is invalid")
    return value


def _text(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("payload envelope value is invalid")
    return value


def _optional_text(value: object) -> str | None:
    return None if value is None else _text(value)


def _string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError("payload envelope list is invalid")
    return tuple(_text(item) for item in value)


def _integer(value: object) -> int:
    if type(value) is not int:
        raise ValueError("payload envelope integer is invalid")
    return value


def _instant(value: object) -> datetime:
    try:
        result = datetime.fromisoformat(_text(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        raise ValueError("payload envelope datetime is invalid") from None
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("payload envelope datetime is invalid")
    return result.astimezone(timezone.utc)


def _optional_instant(value: object) -> datetime | None:
    return None if value is None else _instant(value)


def _zoned(value: object, zone: str) -> datetime:
    try:
        return _instant(value).astimezone(ZoneInfo(zone))
    except (TypeError, ValueError):
        raise ValueError("payload envelope timezone is invalid") from None


def _instant_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _mail_query_value(query: MailQuery) -> dict[str, object]:
    return {
        "query": query.query,
        "folderIds": list(query.folder_ids),
        "after": _instant_text(query.after) if query.after else None,
        "before": _instant_text(query.before) if query.before else None,
        "limit": query.limit,
    }


def _mail_query(value: object) -> MailQuery:
    row = _exact(value, frozenset({"query", "folderIds", "after", "before", "limit"}))
    return MailQuery(
        query=_text(row["query"]),
        folder_ids=_string_tuple(row["folderIds"]),
        after=_optional_instant(row["after"]),
        before=_optional_instant(row["before"]),
        limit=_integer(row["limit"]),
    )


def _mail_spec_value(spec: MailDraftSpec) -> dict[str, object]:
    return {
        "to": list(spec.to),
        "cc": list(spec.cc),
        "bcc": list(spec.bcc),
        "subject": spec.subject,
        "bodyText": spec.body_text,
        "replyToMessageId": spec.reply_to_message_id,
        "expectedResourceVersion": spec.expected_resource_version,
    }


def _mail_spec(value: object) -> MailDraftSpec:
    row = _exact(
        value,
        frozenset(
            {
                "to",
                "cc",
                "bcc",
                "subject",
                "bodyText",
                "replyToMessageId",
                "expectedResourceVersion",
            }
        ),
    )
    return MailDraftSpec(
        to=_string_tuple(row["to"]),
        cc=_string_tuple(row["cc"]),
        bcc=_string_tuple(row["bcc"]),
        subject=_text(row["subject"]),
        body_text=_text(row["bodyText"]),
        reply_to_message_id=_optional_text(row["replyToMessageId"]),
        expected_resource_version=_optional_text(row["expectedResourceVersion"]),
    )


def _calendar_query_value(query: CalendarQuery) -> dict[str, object]:
    return {
        "calendarIds": list(query.calendar_ids),
        "startsAt": _instant_text(query.starts_at),
        "endsAt": _instant_text(query.ends_at),
        "timeZone": query.time_zone,
        "limit": query.limit,
    }


def _calendar_query(value: object) -> CalendarQuery:
    row = _exact(
        value,
        frozenset({"calendarIds", "startsAt", "endsAt", "timeZone", "limit"}),
    )
    zone = _text(row["timeZone"])
    return CalendarQuery(
        calendar_ids=_string_tuple(row["calendarIds"]),
        starts_at=_zoned(row["startsAt"], zone),
        ends_at=_zoned(row["endsAt"], zone),
        time_zone=zone,
        limit=_integer(row["limit"]),
    )


def _event_spec_value(spec: EventSpec) -> dict[str, object]:
    return {
        "calendarId": spec.calendar_id,
        "title": spec.title,
        "startsAt": _instant_text(spec.starts_at),
        "endsAt": _instant_text(spec.ends_at),
        "timeZone": spec.time_zone,
        "description": spec.description,
        "location": spec.location,
        "attendees": list(spec.attendees),
        "sourceEventId": spec.source_event_id,
        "expectedResourceVersion": spec.expected_resource_version,
    }


def _event_spec(value: object) -> EventSpec:
    row = _exact(
        value,
        frozenset(
            {
                "calendarId",
                "title",
                "startsAt",
                "endsAt",
                "timeZone",
                "description",
                "location",
                "attendees",
                "sourceEventId",
                "expectedResourceVersion",
            }
        ),
    )
    zone = _text(row["timeZone"])
    return EventSpec(
        calendar_id=_text(row["calendarId"]),
        title=_text(row["title"]),
        starts_at=_zoned(row["startsAt"], zone),
        ends_at=_zoned(row["endsAt"], zone),
        time_zone=zone,
        description=_text(row["description"]),
        location=_text(row["location"]),
        attendees=_string_tuple(row["attendees"]),
        source_event_id=_optional_text(row["sourceEventId"]),
        expected_resource_version=_optional_text(row["expectedResourceVersion"]),
    )


def _request_value(action: ConnectorActionKind, request: ProviderRequest) -> dict[str, object]:
    if action is ConnectorActionKind.MAIL_SEARCH:
        return _mail_query_value(request.query)  # type: ignore[union-attr]
    if action is ConnectorActionKind.MAIL_GET:
        return {
            "messageId": request.message_id,  # type: ignore[union-attr]
            "expectedResourceVersion": request.expected_resource_version,  # type: ignore[union-attr]
        }
    if action in {
        ConnectorActionKind.MAIL_CREATE_DRAFT,
        ConnectorActionKind.MAIL_SEND,
        ConnectorActionKind.MAIL_REPLY,
    }:
        return _mail_spec_value(request.spec)  # type: ignore[union-attr]
    if action in {
        ConnectorActionKind.CALENDAR_LIST,
        ConnectorActionKind.CALENDAR_FREE_BUSY,
    }:
        return _calendar_query_value(request.query)  # type: ignore[union-attr]
    if action is ConnectorActionKind.CALENDAR_GET:
        return {
            "calendarId": request.calendar_id,  # type: ignore[union-attr]
            "eventId": request.event_id,  # type: ignore[union-attr]
            "expectedResourceVersion": request.expected_resource_version,  # type: ignore[union-attr]
        }
    if action in {
        ConnectorActionKind.CALENDAR_CREATE,
        ConnectorActionKind.CALENDAR_UPDATE,
    }:
        return _event_spec_value(request.spec)  # type: ignore[union-attr]
    if action is ConnectorActionKind.CALENDAR_CANCEL:
        return {
            "calendarId": request.calendar_id,  # type: ignore[union-attr]
            "eventId": request.event_id,  # type: ignore[union-attr]
            "expectedResourceVersion": request.expected_resource_version,  # type: ignore[union-attr]
        }
    raise ValueError("payload action is unsupported")


def _request(action: ConnectorActionKind, value: object) -> ProviderRequest:
    if action is ConnectorActionKind.MAIL_SEARCH:
        return MailSearchRequest.build(_mail_query(value))
    if action is ConnectorActionKind.MAIL_GET:
        row = _exact(value, frozenset({"messageId", "expectedResourceVersion"}))
        return MailGetRequest.build(
            message_id=_text(row["messageId"]),
            expected_resource_version=_optional_text(row["expectedResourceVersion"]),
        )
    if action is ConnectorActionKind.MAIL_CREATE_DRAFT:
        return MailDraftRequest.build(_mail_spec(value))
    if action is ConnectorActionKind.MAIL_SEND:
        return MailSendRequest.build(_mail_spec(value))
    if action is ConnectorActionKind.MAIL_REPLY:
        return MailReplyRequest.build(_mail_spec(value))
    if action is ConnectorActionKind.CALENDAR_LIST:
        return CalendarListRequest.build(_calendar_query(value))
    if action is ConnectorActionKind.CALENDAR_FREE_BUSY:
        return CalendarFreeBusyRequest.build(_calendar_query(value))
    if action is ConnectorActionKind.CALENDAR_GET:
        row = _exact(
            value,
            frozenset({"calendarId", "eventId", "expectedResourceVersion"}),
        )
        return CalendarGetRequest.build(
            calendar_id=_text(row["calendarId"]),
            event_id=_text(row["eventId"]),
            expected_resource_version=_optional_text(row["expectedResourceVersion"]),
        )
    if action is ConnectorActionKind.CALENDAR_CREATE:
        return CalendarCreateRequest.build(_event_spec(value))
    if action is ConnectorActionKind.CALENDAR_UPDATE:
        return CalendarUpdateRequest.build(_event_spec(value))
    if action is ConnectorActionKind.CALENDAR_CANCEL:
        row = _exact(
            value,
            frozenset({"calendarId", "eventId", "expectedResourceVersion"}),
        )
        return CalendarCancelRequest.build(
            calendar_id=_text(row["calendarId"]),
            event_id=_text(row["eventId"]),
            expected_resource_version=_text(row["expectedResourceVersion"]),
        )
    raise ValueError("payload action is unsupported")


@dataclass(frozen=True, slots=True, repr=False)
class ConnectedActionPayloadEnvelope:
    """One exact typed request, safe only inside the encrypted payload vault."""

    action: ConnectorActionKind
    request: ProviderRequest = field(repr=False, compare=False)
    request_target_binding_sha256: str = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.action, ConnectorActionKind):
            raise TypeError("payload action is invalid")
        expected_type = _REQUEST_TYPES.get(self.action)
        if expected_type is None or type(self.request) is not expected_type:
            raise ValueError("payload request does not match action")
        if not isinstance(self.request_target_binding_sha256, str) or not _SHA256.fullmatch(
            self.request_target_binding_sha256
        ):
            raise ValueError("payload target binding is invalid")
        if not hmac.compare_digest(
            self.request_target_binding_sha256,
            self.request.target_binding_sha256,
        ):
            raise ValueError("payload target binding does not match request")

    @classmethod
    def build(
        cls,
        *,
        action: ConnectorActionKind,
        request: ProviderRequest,
    ) -> ConnectedActionPayloadEnvelope:
        return cls(
            action=action,
            request=request,
            request_target_binding_sha256=request.target_binding_sha256,
        )

    def to_value(self) -> dict[str, object]:
        return {
            "version": _VERSION,
            "action": self.action.value,
            "requestTargetBindingSha256": self.request_target_binding_sha256,
            "request": _request_value(self.action, self.request),
        }

    @classmethod
    def from_value(cls, value: object) -> ConnectedActionPayloadEnvelope:
        row = _exact(
            value,
            frozenset({"version", "action", "requestTargetBindingSha256", "request"}),
        )
        if row["version"] != _VERSION:
            raise ValueError("payload envelope version is invalid")
        try:
            action = ConnectorActionKind(_text(row["action"]))
        except ValueError:
            raise ValueError("payload action is invalid") from None
        request = _request(action, row["request"])
        return cls(
            action=action,
            request=request,
            request_target_binding_sha256=_text(row["requestTargetBindingSha256"]),
        )

    def __repr__(self) -> str:
        return f"ConnectedActionPayloadEnvelope(action={self.action.value!r}, content='<redacted>')"


def expected_resource_version(request: ProviderRequest) -> str | None:
    """Extract the exact provider version without exposing request content in metadata."""

    if isinstance(request, (MailGetRequest, CalendarGetRequest)):
        return request.expected_resource_version
    if isinstance(request, (MailDraftRequest, MailSendRequest, MailReplyRequest)):
        return request.spec.expected_resource_version
    if isinstance(request, (CalendarCreateRequest, CalendarUpdateRequest)):
        return request.spec.expected_resource_version
    if isinstance(request, CalendarCancelRequest):
        return request.expected_resource_version
    return None
