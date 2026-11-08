from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from backend.connected_app_contracts import (
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
from backend.connected_app_payload_envelope import (
    ConnectedActionPayloadEnvelope,
    expected_resource_version,
)
from backend.connected_app_policy import ConnectorActionKind


def _values() -> tuple[tuple[ConnectorActionKind, object], ...]:
    ny = ZoneInfo("America/New_York")
    start = datetime(2026, 11, 1, 1, 30, tzinfo=ny, fold=1)
    end = start + timedelta(hours=1)
    query = CalendarQuery(("primary",), start, end, "America/New_York", 25)
    create = EventSpec("primary", "Planning", start, end, "America/New_York")
    update = EventSpec(
        "primary",
        "Planning moved",
        start,
        end,
        "America/New_York",
        source_event_id="event-1",
        expected_resource_version="etag-1",
    )
    mail = MailDraftSpec(
        ("owner@example.com",),
        "Subject",
        "Body",
    )
    reply = MailDraftSpec(
        ("owner@example.com",),
        "Re: Subject",
        "Reply",
        reply_to_message_id="message-1",
        expected_resource_version="etag-1",
    )
    return (
        (
            ConnectorActionKind.MAIL_SEARCH,
            MailSearchRequest.build(
                MailQuery(
                    "from:someone@example.com",
                    ("inbox",),
                    datetime(2026, 1, 1, tzinfo=timezone.utc),
                    datetime(2026, 2, 1, tzinfo=timezone.utc),
                    10,
                )
            ),
        ),
        (
            ConnectorActionKind.MAIL_GET,
            MailGetRequest.build(message_id="message-1", expected_resource_version="etag-1"),
        ),
        (ConnectorActionKind.MAIL_CREATE_DRAFT, MailDraftRequest.build(mail)),
        (ConnectorActionKind.MAIL_SEND, MailSendRequest.build(mail)),
        (ConnectorActionKind.MAIL_REPLY, MailReplyRequest.build(reply)),
        (ConnectorActionKind.CALENDAR_LIST, CalendarListRequest.build(query)),
        (ConnectorActionKind.CALENDAR_FREE_BUSY, CalendarFreeBusyRequest.build(query)),
        (
            ConnectorActionKind.CALENDAR_GET,
            CalendarGetRequest.build(
                calendar_id="primary",
                event_id="event-1",
                expected_resource_version="etag-1",
            ),
        ),
        (ConnectorActionKind.CALENDAR_CREATE, CalendarCreateRequest.build(create)),
        (ConnectorActionKind.CALENDAR_UPDATE, CalendarUpdateRequest.build(update)),
        (
            ConnectorActionKind.CALENDAR_CANCEL,
            CalendarCancelRequest.build(
                calendar_id="primary",
                event_id="event-1",
                expected_resource_version="etag-1",
            ),
        ),
    )


@pytest.mark.parametrize(("action", "provider_request"), _values())
def test_all_action_envelopes_round_trip(action, provider_request) -> None:
    envelope = ConnectedActionPayloadEnvelope.build(action=action, request=provider_request)
    restored = ConnectedActionPayloadEnvelope.from_value(envelope.to_value())

    assert restored.action is action
    assert type(restored.request) is type(provider_request)
    assert restored.request.target_binding_sha256 == provider_request.target_binding_sha256
    assert restored.to_value() == envelope.to_value()
    assert "owner@example.com" not in repr(envelope)
    assert "Subject" not in repr(envelope)


def test_ambiguous_local_calendar_instant_round_trips_with_fold() -> None:
    action, request = next(
        item for item in _values() if item[0] is ConnectorActionKind.CALENDAR_LIST
    )
    restored = ConnectedActionPayloadEnvelope.from_value(
        ConnectedActionPayloadEnvelope.build(action=action, request=request).to_value()
    )

    assert restored.request.query.starts_at.fold == 1
    assert restored.request.query.starts_at.utcoffset() == timedelta(hours=-5)


def test_target_binding_tamper_is_rejected() -> None:
    action, request = _values()[3]
    value = ConnectedActionPayloadEnvelope.build(action=action, request=request).to_value()
    value["requestTargetBindingSha256"] = "0" * 64

    with pytest.raises(ValueError, match="target binding"):
        ConnectedActionPayloadEnvelope.from_value(value)


def test_plaintext_request_tamper_is_rejected_by_intrinsic_binding() -> None:
    action, request = _values()[3]
    value = ConnectedActionPayloadEnvelope.build(action=action, request=request).to_value()
    value["request"]["bodyText"] = "Changed after approval"

    with pytest.raises(ValueError, match="target binding"):
        ConnectedActionPayloadEnvelope.from_value(value)


def test_action_substitution_and_extra_fields_are_rejected() -> None:
    action, request = _values()[3]
    original = ConnectedActionPayloadEnvelope.build(action=action, request=request).to_value()
    substituted = deepcopy(original)
    substituted["action"] = ConnectorActionKind.MAIL_CREATE_DRAFT.value
    with pytest.raises(ValueError, match="target binding"):
        ConnectedActionPayloadEnvelope.from_value(substituted)

    extra = deepcopy(original)
    extra["authority"] = "model-granted"
    with pytest.raises(ValueError, match="shape"):
        ConnectedActionPayloadEnvelope.from_value(extra)


def test_expected_resource_version_is_derived_only_from_typed_request() -> None:
    versions = {action: expected_resource_version(request) for action, request in _values()}

    assert versions[ConnectorActionKind.MAIL_SEARCH] is None
    assert versions[ConnectorActionKind.MAIL_SEND] is None
    assert versions[ConnectorActionKind.MAIL_REPLY] == "etag-1"
    assert versions[ConnectorActionKind.CALENDAR_CREATE] is None
    assert versions[ConnectorActionKind.CALENDAR_UPDATE] == "etag-1"
    assert versions[ConnectorActionKind.CALENDAR_CANCEL] == "etag-1"
