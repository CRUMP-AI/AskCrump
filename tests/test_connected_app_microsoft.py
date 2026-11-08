from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from backend.connected_app_contracts import (
    AmbiguousProviderResult,
    CalendarCancelRequest,
    CalendarCreateRequest,
    CalendarFreeBusyRequest,
    CalendarGetRequest,
    CalendarListRequest,
    CalendarQuery,
    CalendarUpdateRequest,
    ConnectedAccountRef,
    ConnectorAccountKind,
    CredentialHandleRef,
    EventSpec,
    MailDraftRequest,
    MailDraftSpec,
    MailGetRequest,
    MailQuery,
    MailReplyRequest,
    MailSearchRequest,
    MailSendRequest,
    ProviderReceipt,
)
from backend.connected_app_microsoft import (
    GRAPH_HOST,
    MicrosoftConnectedAppProvider,
    MicrosoftEffectUnknown,
    MicrosoftNotDispatched,
    MicrosoftProviderError,
    MicrosoftTransportRequest,
    MicrosoftTransportResponse,
    MicrosoftTransportSecurityPolicy,
)
from backend.connected_app_policy import ConnectorProvider, ConnectorResource


NOW = datetime(2026, 11, 7, 20, 0, tzinfo=timezone.utc)
OWNER = str(uuid4())
CONNECTION = str(uuid4())
OPERATION = str(uuid4())
KEY = "microsoft-idempotency-key-0001"


def account(
    resource: ConnectorResource,
    *,
    kind: ConnectorAccountKind = ConnectorAccountKind.PERSONAL,
) -> ConnectedAccountRef:
    return ConnectedAccountRef(
        owner_id=OWNER,
        connection_id=CONNECTION,
        provider=ConnectorProvider.MICROSOFT,
        resource=resource,
        account_kind=kind,
        external_account_id_hash="a" * 64,
    )


def credential() -> CredentialHandleRef:
    return CredentialHandleRef(
        owner_id=OWNER,
        connection_id=CONNECTION,
        provider=ConnectorProvider.MICROSOFT,
        handle_id="broker/microsoft/credential-handle-0001",
    )


class FakeTransport:
    def __init__(self, *responses: object) -> None:
        self.security_policy = MicrosoftTransportSecurityPolicy()
        self.responses = list(responses)
        self.calls: list[MicrosoftTransportRequest] = []

    async def request(self, *, account, credential, request):
        assert credential.handle_id == "broker/microsoft/credential-handle-0001"
        self.calls.append(request)
        if not self.responses:
            raise AssertionError("unexpected Microsoft transport call")
        value = self.responses.pop(0)
        if isinstance(value, BaseException):
            raise value
        return value


class FakeSleeper:
    def __init__(self) -> None:
        self.delays: list[float] = []

    async def __call__(self, delay: float) -> None:
        self.delays.append(delay)


def response(body=None, *, status=200, request_id="request-1", headers=None, **sizes):
    values = {"request-id": request_id} if headers is None else headers
    return MicrosoftTransportResponse(status, body, values, **sizes)


def version(value: str) -> tuple[str, str]:
    return f'W/"{value}"', value


def marker(kind: str) -> str:
    return hashlib.sha256(f"{kind}:{OPERATION}:{KEY}".encode()).hexdigest()


def mail_spec(*, reply=False) -> MailDraftSpec:
    return MailDraftSpec(
        to=("recipient@example.com",),
        cc=("copy@example.com",),
        bcc=("blind@example.com",),
        subject="Private subject",
        body_text="Private body",
        reply_to_message_id="source/message" if reply else None,
        expected_resource_version='W/"source-key"' if reply else None,
    )


def mail_row(
    *,
    message_id="message-1",
    conversation_id="conversation-1",
    key="change-key-1",
    folder="folder-inbox",
    draft=False,
    spec=None,
    operation_marker=None,
    body_type="text",
    body=None,
    has_attachments=False,
    received="2026-11-07T20:00:00Z",
    internet_message_id="<message-1@example.com>",
    headers=None,
):
    spec = spec or mail_spec()
    etag, change_key = version(key)
    result = {
        "@odata.etag": etag,
        "id": message_id,
        "conversationId": conversation_id,
        "changeKey": change_key,
        "parentFolderId": folder,
        "receivedDateTime": received,
        "subject": spec.subject,
        "from": {"emailAddress": {"address": "sender@example.com"}},
        "toRecipients": [{"emailAddress": {"address": address}} for address in spec.to],
        "ccRecipients": [{"emailAddress": {"address": address}} for address in spec.cc],
        "bccRecipients": [{"emailAddress": {"address": address}} for address in spec.bcc],
        "body": {
            "contentType": body_type,
            "content": spec.body_text if body is None else body,
        },
        "hasAttachments": has_attachments,
        "isDraft": draft,
        "internetMessageId": internet_message_id,
        "internetMessageHeaders": headers
        if headers is not None
        else [{"name": "Message-ID", "value": internet_message_id}],
    }
    if operation_marker is not None:
        result["singleValueExtendedProperties"] = [
            {
                "id": "String {6f23f3dc-8f7b-4b7e-9c2c-7a928fe87f1d} Name AskCrumpOperation",
                "value": operation_marker,
            }
        ]
    return result


def create_mail_row(
    *, message_id="message-1", conversation_id="conversation-1", folder="folder-drafts"
):
    row = mail_row(
        message_id=message_id,
        conversation_id=conversation_id,
        folder=folder,
        draft=True,
    )
    return {
        key: row[key]
        for key in (
            "@odata.etag",
            "id",
            "conversationId",
            "changeKey",
            "parentFolderId",
            "isDraft",
        )
    }


def attachments(*items):
    return response(
        {
            "value": [
                {"id": attachment_id, "isInline": is_inline} for attachment_id, is_inline in items
            ]
        }
    )


def event_spec(
    *,
    update=False,
    title="Private meeting",
    attendees=("guest@example.com",),
    location="Office",
):
    return EventSpec(
        calendar_id="calendar-1",
        title=title,
        starts_at=datetime(2026, 11, 9, 10, tzinfo=ZoneInfo("America/New_York")),
        ends_at=datetime(2026, 11, 9, 11, tzinfo=ZoneInfo("America/New_York")),
        time_zone="America/New_York",
        description="Private notes",
        location=location,
        attendees=attendees,
        source_event_id="event-1" if update else None,
        expected_resource_version='W/"old-key"' if update else None,
    )


def attendee(address="guest@example.com", response_type="accepted"):
    return {
        "emailAddress": {"address": address, "name": "Untrusted name"},
        "type": "required",
        "status": {"response": response_type, "time": "2026-11-07T20:00:00Z"},
        "proposedNewTime": None,
    }


def event_row(
    *,
    spec=None,
    event_id="event-1",
    key="event-key-1",
    transaction_id=None,
    attendees=None,
    online=False,
    location=None,
    locations=None,
    is_cancelled=False,
    is_organizer=True,
    response_type=None,
    show_as="busy",
):
    spec = spec or event_spec()
    etag, change_key = version(key)
    values = [attendee(address) for address in spec.attendees] if attendees is None else attendees
    if location is None:
        primary_location = {
            "displayName": spec.location,
            "locationType": "default",
            "uniqueId": spec.location,
            "uniqueIdType": "private",
        }
        default_locations = [
            {
                "displayName": spec.location,
                "locationType": "default",
                "uniqueId": spec.location,
                "uniqueIdType": "unknown",
            }
        ]
    else:
        primary_location = location
        default_locations = [deepcopy(primary_location)]
    location_rows = default_locations if locations is None else locations
    response_type = response_type or ("organizer" if is_organizer else "accepted")
    result = {
        "@odata.etag": etag,
        "id": event_id,
        "changeKey": change_key,
        "subject": spec.title,
        "body": {"contentType": "text", "content": spec.description},
        "start": {
            "dateTime": spec.starts_at.replace(tzinfo=None).isoformat(timespec="microseconds"),
            "timeZone": spec.time_zone,
        },
        "end": {
            "dateTime": spec.ends_at.replace(tzinfo=None).isoformat(timespec="microseconds"),
            "timeZone": spec.time_zone,
        },
        "location": primary_location,
        "locations": location_rows,
        "attendees": values,
        "organizer": {"emailAddress": {"address": "owner@example.com"}},
        "isCancelled": is_cancelled,
        "isOrganizer": is_organizer,
        "responseStatus": {
            "response": response_type,
            "time": "2026-11-07T20:00:00Z",
        },
        "showAs": show_as,
        "isOnlineMeeting": online,
    }
    if transaction_id is not None:
        result["transactionId"] = transaction_id
    return result


def calendar_query(*, calendars=("calendar-1",), zone="America/New_York"):
    return CalendarQuery(
        calendar_ids=calendars,
        starts_at=datetime(2026, 11, 9, 0, tzinfo=ZoneInfo(zone)),
        ends_at=datetime(2026, 11, 10, 0, tzinfo=ZoneInfo(zone)),
        time_zone=zone,
        limit=10,
    )


def assert_immutable_calendar_requests(calls):
    assert calls
    assert all('IdType="ImmutableId"' in dict(call.headers).get("Prefer", "") for call in calls)


def test_transport_surface_is_locked_and_content_free():
    policy = MicrosoftTransportSecurityPolicy()
    assert policy.allowed_hosts == (GRAPH_HOST,)
    assert not policy.follow_redirects
    assert not policy.automatic_retries
    assert not policy.use_environment_proxies

    request = MicrosoftTransportRequest("GET", GRAPH_HOST, "/v1.0/me/messages", (("$top", "1"),))
    assert "messages" not in repr(request)
    with pytest.raises(ValueError):
        MicrosoftTransportRequest("GET", "evil.example", "/v1.0/me/messages")
    with pytest.raises(ValueError):
        MicrosoftTransportRequest("GET", GRAPH_HOST, "/v1.0/../secrets")
    with pytest.raises(ValueError):
        MicrosoftTransportRequest(
            "GET", GRAPH_HOST, "/v1.0/me/messages", headers=(("Authorization", "secret"),)
        )
    with pytest.raises(ValueError, match="duplicate"):
        MicrosoftTransportResponse(
            200,
            {},
            (("request-id", "one"), ("Request-Id", "two")),
        )
    with pytest.raises(ValueError, match="size"):
        MicrosoftTransportResponse(
            200,
            {},
            raw_size_bytes=1_000_001,
            decompressed_size_bytes=1_000_001,
        )


@pytest.mark.asyncio
async def test_search_mail_revalidates_folder_bounds_and_inline_attachments():
    query = MailQuery(
        query="private search",
        folder_ids=("inbox",),
        after=NOW - timedelta(hours=1),
        before=NOW + timedelta(hours=1),
        limit=5,
    )
    transport = FakeTransport(
        response({"id": "folder-inbox"}),
        response({"value": [{"id": "message-1"}]}),
        response(
            mail_row(
                spec=MailDraftSpec(
                    to=("owner@example.com",),
                    subject="Private subject",
                    body_text="Private body",
                ),
                has_attachments=False,
            )
        ),
        attachments(("inline-1", True)),
    )
    provider = MicrosoftConnectedAppProvider(transport, now=lambda: NOW)

    results = await provider.search_mail(
        account=account(ConnectorResource.MAIL),
        credential=credential(),
        request=MailSearchRequest.build(query),
    )

    assert len(results) == 1
    assert results[0].has_attachments is True
    assert results[0].labels == ("folder-inbox",)
    assert all(
        call.host == GRAPH_HOST and call.path.startswith("/v1.0/") for call in transport.calls
    )
    search_parameters = dict(transport.calls[1].query)
    assert "$search" in search_parameters
    assert "$filter" not in search_parameters
    assert "$orderby" not in search_parameters
    assert not transport.responses


@pytest.mark.asyncio
async def test_search_mail_rejects_strict_boundary_and_hostile_next_link():
    query = MailQuery(
        query="",
        folder_ids=("inbox",),
        after=NOW,
        before=NOW + timedelta(hours=1),
        limit=5,
    )
    boundary = mail_row(
        spec=MailDraftSpec(to=("owner@example.com",), subject="x", body_text="x"),
        received=NOW.isoformat().replace("+00:00", "Z"),
    )
    boundary_transport = FakeTransport(
        response({"id": "folder-inbox"}),
        response({"value": [{"id": "message-1"}]}),
        response(boundary),
        attachments(),
    )
    provider = MicrosoftConnectedAppProvider(boundary_transport)
    with pytest.raises(MicrosoftProviderError, match="OUT_OF_BOUNDS"):
        await provider.search_mail(
            account=account(ConnectorResource.MAIL),
            credential=credential(),
            request=MailSearchRequest.build(query),
        )
    empty_parameters = dict(boundary_transport.calls[1].query)
    assert "$search" not in empty_parameters
    assert empty_parameters["$filter"].startswith("receivedDateTime gt ")
    assert empty_parameters["$orderby"] == "receivedDateTime desc"

    provider = MicrosoftConnectedAppProvider(
        FakeTransport(
            response({"id": "folder-inbox"}),
            response(
                {
                    "value": [],
                    "@odata.nextLink": "https://evil.example/v1.0/me/mailFolders/inbox/messages?$skiptoken=x",
                }
            ),
        )
    )
    with pytest.raises(MicrosoftProviderError, match="PAGINATION_INVALID"):
        await provider.search_mail(
            account=account(ConnectorResource.MAIL),
            credential=credential(),
            request=MailSearchRequest.build(query),
        )


@pytest.mark.asyncio
async def test_search_mode_client_filters_exact_date_bounds_without_invalid_odata_mix():
    query = MailQuery(
        query="natural language",
        folder_ids=("inbox",),
        after=NOW - timedelta(hours=1),
        before=NOW + timedelta(hours=1),
        limit=5,
    )
    private_spec = MailDraftSpec(
        to=("owner@example.com",),
        subject="x",
        body_text="x",
    )
    transport = FakeTransport(
        response({"id": "folder-inbox"}),
        response({"value": [{"id": "outside"}, {"id": "inside"}]}),
        response(
            mail_row(
                message_id="outside",
                spec=private_spec,
                received="2026-11-07T18:00:00Z",
            )
        ),
        attachments(),
        response(mail_row(message_id="inside", spec=private_spec)),
        attachments(),
    )
    results = await MicrosoftConnectedAppProvider(transport).search_mail(
        account=account(ConnectorResource.MAIL),
        credential=credential(),
        request=MailSearchRequest.build(query),
    )
    assert [result.message_id for result in results] == ["inside"]
    parameters = dict(transport.calls[1].query)
    assert set(parameters) == {"$select", "$top", "$search"}


@pytest.mark.asyncio
async def test_get_message_sanitizes_html_and_checks_exact_version():
    row = mail_row(
        spec=MailDraftSpec(to=("owner@example.com",), subject="x", body_text="ignored"),
        body_type="html",
        body="<p>Hello <b>world</b></p><script>secret()</script>",
    )
    transport = FakeTransport(response(row), attachments())
    result = await MicrosoftConnectedAppProvider(transport).get_message(
        account=account(ConnectorResource.MAIL),
        credential=credential(),
        request=MailGetRequest.build(
            message_id="message-1", expected_resource_version='W/"change-key-1"'
        ),
    )
    assert result.body_text == "Hello world"
    assert "secret" not in result.body_text

    bad = deepcopy(row)
    bad["@odata.etag"] = 'W/"different"'
    provider = MicrosoftConnectedAppProvider(FakeTransport(response(bad), attachments()))
    with pytest.raises(MicrosoftProviderError, match="VERSION_MISMATCH"):
        await provider.get_message(
            account=account(ConnectorResource.MAIL),
            credential=credential(),
            request=MailGetRequest.build(message_id="message-1"),
        )


@pytest.mark.asyncio
async def test_create_draft_requires_authoritative_exact_readback():
    spec = mail_spec()
    transport = FakeTransport(
        response({"id": "folder-drafts"}),
        response(create_mail_row(), status=201),
        response(
            mail_row(
                folder="folder-drafts",
                draft=True,
                spec=spec,
                operation_marker=marker("mail.draft"),
            )
        ),
        attachments(),
    )
    result = await MicrosoftConnectedAppProvider(transport, now=lambda: NOW).create_draft(
        account=account(ConnectorResource.MAIL),
        credential=credential(),
        request=MailDraftRequest.build(spec),
        operation_id=OPERATION,
        idempotency_key=KEY,
    )
    assert isinstance(result, ProviderReceipt)
    assert result.outcome == "drafted"
    assert transport.calls[1].method == "POST"
    assert "Authorization" not in dict(transport.calls[1].headers)


@pytest.mark.asyncio
async def test_write_not_dispatched_is_definite_but_response_loss_is_ambiguous():
    spec = mail_spec()
    provider = MicrosoftConnectedAppProvider(
        FakeTransport(response({"id": "folder-drafts"}), MicrosoftNotDispatched())
    )
    with pytest.raises(MicrosoftProviderError, match="NOT_DISPATCHED") as caught:
        await provider.create_draft(
            account=account(ConnectorResource.MAIL),
            credential=credential(),
            request=MailDraftRequest.build(spec),
            operation_id=OPERATION,
            idempotency_key=KEY,
        )
    assert caught.value.retryable is True

    result = await MicrosoftConnectedAppProvider(
        FakeTransport(response({"id": "folder-drafts"}), MicrosoftEffectUnknown())
    ).create_draft(
        account=account(ConnectorResource.MAIL),
        credential=credential(),
        request=MailDraftRequest.build(spec),
        operation_id=OPERATION,
        idempotency_key=KEY,
    )
    assert isinstance(result, AmbiguousProviderResult)
    assert result.retryable is False


@pytest.mark.asyncio
async def test_send_uses_immutable_draft_and_requires_sentitems_readback():
    spec = mail_spec()
    sent = mail_row(
        folder="folder-sent",
        draft=False,
        spec=spec,
        operation_marker=marker("mail.send"),
        key="sent-key",
    )
    transport = FakeTransport(
        response({"id": "folder-drafts"}),
        response({"id": "folder-sent"}),
        response(create_mail_row(), status=201),
        response(
            mail_row(
                folder="folder-drafts",
                draft=True,
                spec=spec,
                operation_marker=marker("mail.send"),
            )
        ),
        attachments(),
        response(None, status=202),
        response(sent),
        attachments(),
    )
    result = await MicrosoftConnectedAppProvider(transport, now=lambda: NOW).send_mail(
        account=account(ConnectorResource.MAIL),
        credential=credential(),
        request=MailSendRequest.build(spec),
        operation_id=OPERATION,
        idempotency_key=KEY,
    )
    assert isinstance(result, ProviderReceipt)
    assert result.outcome == "sent"
    assert transport.calls[5].path.endswith("/messages/message-1/send")
    assert all(
        'IdType="ImmutableId"' in dict(call.headers).get("Prefer", "") for call in transport.calls
    )
    assert not transport.responses


@pytest.mark.asyncio
async def test_send_never_recreates_or_resends_after_possible_effect():
    spec = mail_spec()
    sleeper = FakeSleeper()
    transport = FakeTransport(
        response({"id": "folder-drafts"}),
        response({"id": "folder-sent"}),
        response(create_mail_row(), status=201),
        response(
            mail_row(
                folder="folder-drafts",
                draft=True,
                spec=spec,
                operation_marker=marker("mail.send"),
            )
        ),
        attachments(),
        MicrosoftEffectUnknown(),
    )
    result = await MicrosoftConnectedAppProvider(transport, sleep=sleeper).send_mail(
        account=account(ConnectorResource.MAIL),
        credential=credential(),
        request=MailSendRequest.build(spec),
        operation_id=OPERATION,
        idempotency_key=KEY,
    )
    assert isinstance(result, AmbiguousProviderResult)
    assert [call.method for call in transport.calls].count("POST") == 2
    assert sleeper.delays == [0.05, 0.15]
    assert not transport.responses


@pytest.mark.asyncio
async def test_send_response_loss_reconciles_delayed_move_without_second_send():
    spec = mail_spec()
    sent = mail_row(
        folder="folder-sent",
        draft=False,
        spec=spec,
        operation_marker=marker("mail.send"),
        key="sent-key",
    )
    sleeper = FakeSleeper()
    transport = FakeTransport(
        response({"id": "folder-drafts"}),
        response({"id": "folder-sent"}),
        response(create_mail_row(), status=201),
        response(
            mail_row(
                folder="folder-drafts",
                draft=True,
                spec=spec,
                operation_marker=marker("mail.send"),
            )
        ),
        attachments(),
        MicrosoftEffectUnknown(),
        response({"error": {}}, status=404),
        response(sent),
        attachments(),
    )
    result = await MicrosoftConnectedAppProvider(
        transport,
        now=lambda: NOW,
        sleep=sleeper,
    ).send_mail(
        account=account(ConnectorResource.MAIL),
        credential=credential(),
        request=MailSendRequest.build(spec),
        operation_id=OPERATION,
        idempotency_key=KEY,
    )
    assert isinstance(result, ProviderReceipt)
    assert result.outcome == "sent"
    assert sleeper.delays == [0.05]
    assert sum(call.path.endswith("/send") for call in transport.calls) == 1
    assert [call.method for call in transport.calls].count("POST") == 2
    assert not transport.responses


@pytest.mark.asyncio
async def test_reply_version_checks_source_and_proves_conversation_headers():
    spec = mail_spec(reply=True)
    source_headers = [
        {"name": "Message-ID", "value": "<source@example.com>"},
        {"name": "References", "value": "<older@example.com>"},
    ]
    source = mail_row(
        message_id="source/message",
        conversation_id="source-conversation",
        key="source-key",
        folder="folder-inbox",
        spec=spec,
        internet_message_id="<source@example.com>",
        headers=source_headers,
    )
    create_reply = create_mail_row(
        message_id="reply-1",
        conversation_id="source-conversation",
    )
    draft_reply = mail_row(
        message_id="reply-1",
        conversation_id="source-conversation",
        folder="folder-drafts",
        draft=True,
        spec=spec,
        operation_marker=marker("mail.reply"),
    )
    sent_headers = [
        {"name": "Message-ID", "value": "<reply@example.com>"},
        {"name": "In-Reply-To", "value": "<source@example.com>"},
        {
            "name": "References",
            "value": "<older@example.com> <source@example.com>",
        },
    ]
    sent_reply = mail_row(
        message_id="reply-1",
        conversation_id="source-conversation",
        folder="folder-sent",
        draft=False,
        spec=spec,
        key="sent-reply-key",
        operation_marker=marker("mail.reply"),
        internet_message_id="<reply@example.com>",
        headers=sent_headers,
    )
    transport = FakeTransport(
        response(source),
        attachments(),
        response({"id": "folder-drafts"}),
        response({"id": "folder-sent"}),
        response(create_reply, status=201),
        response(create_reply, status=200),
        response(draft_reply),
        attachments(),
        response(None, status=202),
        response({"error": {}}, status=404),
        response(sent_reply),
        attachments(),
    )
    sleeper = FakeSleeper()
    result = await MicrosoftConnectedAppProvider(
        transport,
        now=lambda: NOW,
        sleep=sleeper,
    ).reply_mail(
        account=account(ConnectorResource.MAIL),
        credential=credential(),
        request=MailReplyRequest.build(spec),
        operation_id=OPERATION,
        idempotency_key=KEY,
    )
    assert isinstance(result, ProviderReceipt)
    assert result.outcome == "sent"
    assert "/createReply" in transport.calls[4].path
    assert transport.calls[5].method == "PATCH"
    assert dict(transport.calls[5].headers)["If-Match"] == 'W/"change-key-1"'
    assert sleeper.delays == [0.05]
    assert sum(call.path.endswith("/send") for call in transport.calls) == 1


@pytest.mark.asyncio
async def test_reply_rejects_duplicate_critical_source_headers_before_effect():
    spec = mail_spec(reply=True)
    source = mail_row(
        message_id="source/message",
        key="source-key",
        spec=spec,
        internet_message_id="<source@example.com>",
        headers=[
            {"name": "Message-ID", "value": "<source@example.com>"},
            {"name": "Message-ID", "value": "<source@example.com>"},
        ],
    )
    transport = FakeTransport(response(source), attachments())
    with pytest.raises(MicrosoftProviderError, match="CARDINALITY"):
        await MicrosoftConnectedAppProvider(transport).reply_mail(
            account=account(ConnectorResource.MAIL),
            credential=credential(),
            request=MailReplyRequest.build(spec),
            operation_id=OPERATION,
            idempotency_key=KEY,
        )
    assert all("createReply" not in call.path for call in transport.calls)


@pytest.mark.asyncio
async def test_list_events_validates_half_open_window_and_pagination_identity():
    query = calendar_query()
    transport = FakeTransport(response({"value": [event_row()]}))
    result = await MicrosoftConnectedAppProvider(transport).list_events(
        account=account(ConnectorResource.CALENDAR),
        credential=credential(),
        request=CalendarListRequest.build(query),
    )
    assert len(result) == 1
    assert result[0].calendar_id == "calendar-1"
    assert result[0].time_zone == "America/New_York"
    assert "calendarView" in transport.calls[0].path
    assert_immutable_calendar_requests(transport.calls)

    outside = event_row()
    outside["start"] = {
        "dateTime": "2026-11-10T00:00:00.000000",
        "timeZone": "America/New_York",
    }
    outside["end"] = {
        "dateTime": "2026-11-10T01:00:00.000000",
        "timeZone": "America/New_York",
    }
    with pytest.raises(MicrosoftProviderError, match="OUT_OF_BOUNDS"):
        await MicrosoftConnectedAppProvider(
            FakeTransport(response({"value": [outside]}))
        ).list_events(
            account=account(ConnectorResource.CALENDAR),
            credential=credential(),
            request=CalendarListRequest.build(query),
        )


@pytest.mark.asyncio
async def test_event_status_uses_response_lifecycle_not_show_as():
    query = calendar_query()
    rows = [
        event_row(event_id="event-organizer", show_as="tentative"),
        event_row(
            event_id="event-pending",
            is_organizer=False,
            response_type="notResponded",
            show_as="busy",
        ),
        event_row(
            event_id="event-declined",
            is_organizer=False,
            response_type="declined",
            show_as="free",
        ),
    ]
    results = await MicrosoftConnectedAppProvider(
        FakeTransport(response({"value": rows}))
    ).list_events(
        account=account(ConnectorResource.CALENDAR),
        credential=credential(),
        request=CalendarListRequest.build(query),
    )
    assert [event.status for event in results] == ["confirmed", "tentative", "cancelled"]


@pytest.mark.asyncio
async def test_calendar_read_fails_closed_on_dst_fold_without_offset_proof():
    query = CalendarQuery(
        calendar_ids=("calendar-1",),
        starts_at=datetime(2026, 11, 1, 0, tzinfo=ZoneInfo("America/New_York")),
        ends_at=datetime(2026, 11, 1, 3, tzinfo=ZoneInfo("America/New_York")),
        time_zone="America/New_York",
        limit=10,
    )
    row = event_row()
    row["start"] = {
        "dateTime": "2026-11-01T01:30:00.000000",
        "timeZone": "America/New_York",
    }
    row["end"] = {
        "dateTime": "2026-11-01T02:30:00.000000",
        "timeZone": "America/New_York",
    }
    with pytest.raises(MicrosoftProviderError, match="AMBIGUOUS_LOCAL_TIME"):
        await MicrosoftConnectedAppProvider(FakeTransport(response({"value": [row]}))).list_events(
            account=account(ConnectorResource.CALENDAR),
            credential=credential(),
            request=CalendarListRequest.build(query),
        )


def ambiguous_event_spec(*, ambiguous_field: str, fold: int, update: bool) -> EventSpec:
    zone = ZoneInfo("America/New_York")
    if ambiguous_field == "start":
        starts_at = datetime(2026, 11, 1, 1, 30, tzinfo=zone, fold=fold)
        ends_at = datetime(2026, 11, 1, 2, 30, tzinfo=zone)
    else:
        starts_at = datetime(2026, 11, 1, 0, 30, tzinfo=zone)
        ends_at = datetime(2026, 11, 1, 1, 30, tzinfo=zone, fold=fold)
    return EventSpec(
        calendar_id="calendar-1",
        title="Private meeting",
        starts_at=starts_at,
        ends_at=ends_at,
        time_zone="America/New_York",
        description="Private notes",
        location="Office",
        attendees=("guest@example.com",),
        source_event_id="event-1" if update else None,
        expected_resource_version='W/"old-key"' if update else None,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("ambiguous_field", ["start", "end"])
@pytest.mark.parametrize("fold", [0, 1])
async def test_create_rejects_both_folds_of_ambiguous_start_or_end_before_post(
    ambiguous_field,
    fold,
):
    spec = ambiguous_event_spec(ambiguous_field=ambiguous_field, fold=fold, update=False)
    transport = FakeTransport()
    with pytest.raises(MicrosoftProviderError, match="AMBIGUOUS_LOCAL_TIME_UNSUPPORTED"):
        await MicrosoftConnectedAppProvider(transport).create_event(
            account=account(ConnectorResource.CALENDAR),
            credential=credential(),
            request=CalendarCreateRequest.build(spec),
            operation_id=OPERATION,
            idempotency_key=KEY,
        )
    assert not transport.calls


@pytest.mark.asyncio
@pytest.mark.parametrize("ambiguous_field", ["start", "end"])
@pytest.mark.parametrize("fold", [0, 1])
async def test_update_rejects_both_folds_of_ambiguous_start_or_end_before_patch(
    ambiguous_field,
    fold,
):
    spec = ambiguous_event_spec(ambiguous_field=ambiguous_field, fold=fold, update=True)
    transport = FakeTransport(response(event_row(spec=event_spec(), key="old-key")))
    with pytest.raises(MicrosoftProviderError, match="AMBIGUOUS_LOCAL_TIME_UNSUPPORTED"):
        await MicrosoftConnectedAppProvider(transport).update_event(
            account=account(ConnectorResource.CALENDAR),
            credential=credential(),
            request=CalendarUpdateRequest.build(spec),
            operation_id=OPERATION,
            idempotency_key=KEY,
        )
    assert [call.method for call in transport.calls] == ["GET"]


@pytest.mark.asyncio
async def test_free_busy_requires_every_schedule_no_error_and_exact_bounds():
    query = calendar_query(calendars=("room@example.com",))
    body = {
        "value": [
            {
                "scheduleId": "room@example.com",
                "error": None,
                "scheduleItems": [
                    {
                        "status": "oof",
                        "start": {
                            "dateTime": "2026-11-09T10:00:00.000000",
                            "timeZone": "America/New_York",
                        },
                        "end": {
                            "dateTime": "2026-11-09T11:00:00.000000",
                            "timeZone": "America/New_York",
                        },
                    }
                ],
            }
        ]
    }
    result = await MicrosoftConnectedAppProvider(FakeTransport(response(body))).free_busy(
        account=account(
            ConnectorResource.CALENDAR,
            kind=ConnectorAccountKind.WORK_SCHOOL,
        ),
        credential=credential(),
        request=CalendarFreeBusyRequest.build(query),
    )
    assert len(result) == 1
    assert result[0].status == "out_of_office"

    incomplete = deepcopy(body)
    incomplete["value"][0]["error"] = {"responseCode": "5006"}
    with pytest.raises(MicrosoftProviderError, match="FREEBUSY_REJECTED"):
        await MicrosoftConnectedAppProvider(FakeTransport(response(incomplete))).free_busy(
            account=account(
                ConnectorResource.CALENDAR,
                kind=ConnectorAccountKind.WORK_SCHOOL,
            ),
            credential=credential(),
            request=CalendarFreeBusyRequest.build(query),
        )


@pytest.mark.asyncio
async def test_free_busy_personal_account_fails_before_transport():
    transport = FakeTransport()
    with pytest.raises(MicrosoftProviderError, match="ACCOUNT_UNSUPPORTED"):
        await MicrosoftConnectedAppProvider(transport).free_busy(
            account=account(ConnectorResource.CALENDAR),
            credential=credential(),
            request=CalendarFreeBusyRequest.build(calendar_query(calendars=("room@example.com",))),
        )
    assert not transport.calls


@pytest.mark.asyncio
async def test_get_event_checks_identity_and_version():
    utc_spec = EventSpec(
        calendar_id="calendar-1",
        title="Private meeting",
        starts_at=datetime(2026, 11, 9, 15, tzinfo=timezone.utc),
        ends_at=datetime(2026, 11, 9, 16, tzinfo=timezone.utc),
        time_zone="UTC",
        description="Private notes",
        location="Office",
        attendees=("guest@example.com",),
    )
    transport = FakeTransport(response(event_row(spec=utc_spec, show_as="tentative")))
    result = await MicrosoftConnectedAppProvider(transport).get_event(
        account=account(ConnectorResource.CALENDAR),
        credential=credential(),
        request=CalendarGetRequest.build(
            calendar_id="calendar-1",
            event_id="event-1",
            expected_resource_version='W/"event-key-1"',
        ),
    )
    assert result.event_id == "event-1"
    assert result.status == "confirmed"
    assert_immutable_calendar_requests(transport.calls)

    with pytest.raises(MicrosoftProviderError, match="RESOURCE_MISMATCH"):
        await MicrosoftConnectedAppProvider(
            FakeTransport(response(event_row(spec=utc_spec, event_id="different")))
        ).get_event(
            account=account(ConnectorResource.CALENDAR),
            credential=credential(),
            request=CalendarGetRequest.build(calendar_id="calendar-1", event_id="event-1"),
        )


@pytest.mark.asyncio
async def test_create_event_uses_transaction_id_and_authoritative_readback():
    spec = event_spec()
    transaction_id = hashlib.sha256(f"calendar.create:{OPERATION}:{KEY}".encode()).hexdigest()
    created = event_row(transaction_id=transaction_id, show_as="tentative")
    transport = FakeTransport(
        response(created, status=201),
        response(created),
    )
    result = await MicrosoftConnectedAppProvider(transport, now=lambda: NOW).create_event(
        account=account(ConnectorResource.CALENDAR),
        credential=credential(),
        request=CalendarCreateRequest.build(spec),
        operation_id=OPERATION,
        idempotency_key=KEY,
    )
    assert isinstance(result, ProviderReceipt)
    assert result.outcome == "created"
    assert transport.calls[0].json_body["transactionId"] == transaction_id
    assert created["location"] == {
        "displayName": "Office",
        "locationType": "default",
        "uniqueId": "Office",
        "uniqueIdType": "private",
    }
    assert created["locations"] == [
        {
            "displayName": "Office",
            "locationType": "default",
            "uniqueId": "Office",
            "uniqueIdType": "unknown",
        }
    ]
    assert_immutable_calendar_requests(transport.calls)

    ambiguous = await MicrosoftConnectedAppProvider(
        FakeTransport(MicrosoftEffectUnknown())
    ).create_event(
        account=account(ConnectorResource.CALENDAR),
        credential=credential(),
        request=CalendarCreateRequest.build(spec),
        operation_id=OPERATION,
        idempotency_key=KEY,
    )
    assert isinstance(ambiguous, AmbiguousProviderResult)


@pytest.mark.asyncio
async def test_update_event_preserves_attendee_provider_fields_and_postreads():
    spec = event_spec(
        update=True,
        title="Updated meeting",
        attendees=("guest@example.com", "new@example.com"),
    )
    current_spec = event_spec(title="Private meeting")
    current = event_row(
        spec=current_spec,
        key="old-key",
        attendees=[attendee("guest@example.com", "accepted")],
        show_as="tentative",
    )
    updated = event_row(spec=spec, key="new-key", show_as="tentative")
    transport = FakeTransport(
        response(current),
        response(updated, status=200),
        response(updated),
    )
    result = await MicrosoftConnectedAppProvider(transport, now=lambda: NOW).update_event(
        account=account(ConnectorResource.CALENDAR),
        credential=credential(),
        request=CalendarUpdateRequest.build(spec),
        operation_id=OPERATION,
        idempotency_key=KEY,
    )
    assert isinstance(result, ProviderReceipt)
    patch = transport.calls[1].json_body
    assert "location" not in patch
    assert patch["attendees"][0]["status"]["response"] == "accepted"
    assert patch["attendees"][0]["proposedNewTime"] is None
    assert patch["attendees"][1] == {
        "emailAddress": {"address": "new@example.com"},
        "type": "required",
    }
    assert dict(transport.calls[1].headers)["If-Match"] == 'W/"old-key"'
    assert_immutable_calendar_requests(transport.calls)


@pytest.mark.asyncio
async def test_update_accepts_only_normalized_graph_scalar_location_identity():
    spec = event_spec(update=True, location="Other room")
    current = event_row(spec=event_spec(), key="old-key")
    updated = event_row(spec=spec, key="new-key")
    transport = FakeTransport(response(current), response(updated), response(updated))
    result = await MicrosoftConnectedAppProvider(transport, now=lambda: NOW).update_event(
        account=account(ConnectorResource.CALENDAR),
        credential=credential(),
        request=CalendarUpdateRequest.build(spec),
        operation_id=OPERATION,
        idempotency_key=KEY,
    )
    assert isinstance(result, ProviderReceipt)
    assert transport.calls[1].json_body["location"] == {"displayName": "Other room"}
    assert updated["location"] == {
        "displayName": "Other room",
        "locationType": "default",
        "uniqueId": "Other room",
        "uniqueIdType": "private",
    }
    assert updated["locations"][0]["uniqueIdType"] == "unknown"

    unnormalized = deepcopy(updated)
    unnormalized["location"] = {"displayName": "Other room"}
    unnormalized["locations"] = [{"displayName": "Other room"}]
    transport = FakeTransport(response(current), response(updated), response(unnormalized))
    result = await MicrosoftConnectedAppProvider(transport, now=lambda: NOW).update_event(
        account=account(ConnectorResource.CALENDAR),
        credential=credential(),
        request=CalendarUpdateRequest.build(spec),
        operation_id=OPERATION,
        idempotency_key=KEY,
    )
    assert isinstance(result, AmbiguousProviderResult)


@pytest.mark.asyncio
async def test_title_only_update_preserves_enriched_scalar_location_without_patch():
    spec = event_spec(update=True, title="Updated meeting")
    current = event_row(spec=event_spec(), key="old-key")
    updated = event_row(spec=spec, key="new-key")
    transport = FakeTransport(response(current), response(updated), response(updated))
    result = await MicrosoftConnectedAppProvider(transport, now=lambda: NOW).update_event(
        account=account(ConnectorResource.CALENDAR),
        credential=credential(),
        request=CalendarUpdateRequest.build(spec),
        operation_id=OPERATION,
        idempotency_key=KEY,
    )
    assert isinstance(result, ProviderReceipt)
    assert "location" not in transport.calls[1].json_body
    assert updated["location"] == current["location"]
    assert updated["locations"] == current["locations"]


@pytest.mark.asyncio
async def test_update_postread_requires_unchanged_provider_show_as_and_response_state():
    spec = event_spec(update=True, title="Updated meeting")
    current = event_row(spec=event_spec(), key="old-key", show_as="tentative")
    drifted = event_row(spec=spec, key="new-key", show_as="busy")
    transport = FakeTransport(response(current), response(drifted), response(drifted))
    result = await MicrosoftConnectedAppProvider(transport, now=lambda: NOW).update_event(
        account=account(ConnectorResource.CALENDAR),
        credential=credential(),
        request=CalendarUpdateRequest.build(spec),
        operation_id=OPERATION,
        idempotency_key=KEY,
    )
    assert isinstance(result, AmbiguousProviderResult)


@pytest.mark.asyncio
async def test_update_preserves_full_complex_locations_and_rejects_location_loss():
    complex_primary = {
        "displayName": "Office",
        "locationType": "conferenceRoom",
        "uniqueId": "room-42",
        "uniqueIdType": "directory",
        "address": {
            "street": "1 Private Way",
            "city": "Phoenix",
            "state": "AZ",
            "countryOrRegion": "US",
            "postalCode": "85001",
        },
        "coordinates": {"latitude": 33.4484, "longitude": -112.074},
    }
    secondary = {
        "displayName": "Video bridge",
        "locationType": "default",
        "uniqueId": "bridge-1",
        "uniqueIdType": "private",
    }
    spec = event_spec(update=True, title="Updated meeting")
    current = event_row(
        spec=event_spec(),
        key="old-key",
        location=deepcopy(complex_primary),
        locations=[deepcopy(complex_primary), deepcopy(secondary)],
    )
    updated = event_row(
        spec=spec,
        key="new-key",
        location=deepcopy(complex_primary),
        locations=[deepcopy(complex_primary), deepcopy(secondary)],
    )
    transport = FakeTransport(response(current), response(updated), response(updated))
    result = await MicrosoftConnectedAppProvider(transport, now=lambda: NOW).update_event(
        account=account(ConnectorResource.CALENDAR),
        credential=credential(),
        request=CalendarUpdateRequest.build(spec),
        operation_id=OPERATION,
        idempotency_key=KEY,
    )
    assert isinstance(result, ProviderReceipt)
    assert "location" not in transport.calls[1].json_body

    drifted = deepcopy(updated)
    drifted["locations"] = [deepcopy(complex_primary)]
    transport = FakeTransport(response(current), response(updated), response(drifted))
    result = await MicrosoftConnectedAppProvider(transport, now=lambda: NOW).update_event(
        account=account(ConnectorResource.CALENDAR),
        credential=credential(),
        request=CalendarUpdateRequest.build(spec),
        operation_id=OPERATION,
        idempotency_key=KEY,
    )
    assert isinstance(result, AmbiguousProviderResult)


@pytest.mark.asyncio
async def test_update_rejects_display_only_overwrite_of_complex_location_before_patch():
    complex_primary = {
        "displayName": "Office",
        "locationType": "conferenceRoom",
        "uniqueId": "room-42",
        "uniqueIdType": "directory",
        "address": {"city": "Phoenix"},
        "coordinates": {"latitude": 33.4484, "longitude": -112.074},
    }
    current = event_row(
        spec=event_spec(),
        key="old-key",
        location=complex_primary,
        locations=[complex_primary, {"displayName": "Secondary"}],
    )
    spec = event_spec(update=True, location="Other room")
    transport = FakeTransport(response(current))
    with pytest.raises(MicrosoftProviderError, match="COMPLEX_LOCATION_UPDATE_UNSUPPORTED"):
        await MicrosoftConnectedAppProvider(transport).update_event(
            account=account(ConnectorResource.CALENDAR),
            credential=credential(),
            request=CalendarUpdateRequest.build(spec),
            operation_id=OPERATION,
            idempotency_key=KEY,
        )
    assert [call.method for call in transport.calls] == ["GET"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "hostile_kind",
    ["minimal", "directory", "resource", "address", "coordinates", "extra", "multiple"],
)
async def test_location_display_change_rejects_each_non_scalar_provider_shape(hostile_kind):
    primary = {
        "displayName": "Office",
        "locationType": "default",
        "uniqueId": "Office",
        "uniqueIdType": "private",
    }
    locations = [
        {
            "displayName": "Office",
            "locationType": "default",
            "uniqueId": "Office",
            "uniqueIdType": "unknown",
        }
    ]
    if hostile_kind == "minimal":
        primary = {"displayName": "Office"}
        locations = [{"displayName": "Office"}]
    elif hostile_kind == "directory":
        primary["uniqueId"] = "directory-room-id"
        primary["uniqueIdType"] = "directory"
    elif hostile_kind == "resource":
        primary["locationType"] = "conferenceRoom"
    elif hostile_kind == "address":
        primary["address"] = {"city": "Phoenix"}
    elif hostile_kind == "coordinates":
        primary["coordinates"] = {"latitude": 33.4484, "longitude": -112.074}
    elif hostile_kind == "extra":
        primary["providerExtension"] = "must-preserve"
    else:
        locations.append(
            {
                "displayName": "Secondary",
                "locationType": "default",
                "uniqueId": "Secondary",
                "uniqueIdType": "unknown",
            }
        )
    current = event_row(
        spec=event_spec(),
        key="old-key",
        location=primary,
        locations=locations,
    )
    spec = event_spec(update=True, location="Other room")
    transport = FakeTransport(response(current))
    with pytest.raises(MicrosoftProviderError, match="COMPLEX_LOCATION_UPDATE_UNSUPPORTED"):
        await MicrosoftConnectedAppProvider(transport).update_event(
            account=account(ConnectorResource.CALENDAR),
            credential=credential(),
            request=CalendarUpdateRequest.build(spec),
            operation_id=OPERATION,
            idempotency_key=KEY,
        )
    assert [call.method for call in transport.calls] == ["GET"]


@pytest.mark.asyncio
async def test_update_rejects_partial_attendees_and_online_meeting_body_loss():
    spec = event_spec(update=True, title="Updated meeting")
    partial = event_row(spec=event_spec(), key="old-key")
    del partial["attendees"][0]["status"]
    with pytest.raises(MicrosoftProviderError, match="ATTENDEES_INCOMPLETE"):
        await MicrosoftConnectedAppProvider(FakeTransport(response(partial))).update_event(
            account=account(ConnectorResource.CALENDAR),
            credential=credential(),
            request=CalendarUpdateRequest.build(spec),
            operation_id=OPERATION,
            idempotency_key=KEY,
        )

    online = event_row(spec=event_spec(), key="old-key", online=True)
    online_spec = EventSpec(
        calendar_id="calendar-1",
        title="Private meeting",
        starts_at=event_spec().starts_at,
        ends_at=event_spec().ends_at,
        time_zone="America/New_York",
        description="Different body",
        location="Office",
        attendees=("guest@example.com",),
        source_event_id="event-1",
        expected_resource_version='W/"old-key"',
    )
    with pytest.raises(MicrosoftProviderError, match="BODY_UPDATE_UNSUPPORTED"):
        await MicrosoftConnectedAppProvider(FakeTransport(response(online))).update_event(
            account=account(ConnectorResource.CALENDAR),
            credential=credential(),
            request=CalendarUpdateRequest.build(online_spec),
            operation_id=OPERATION,
            idempotency_key=KEY,
        )


@pytest.mark.asyncio
async def test_cancel_exact_204_or_one_absence_proof_never_retries_delete():
    request = CalendarCancelRequest.build(
        calendar_id="calendar-1",
        event_id="event-1",
        expected_resource_version='W/"event-key-1"',
    )
    transport = FakeTransport(response(event_row()), response(None, status=204))
    result = await MicrosoftConnectedAppProvider(transport, now=lambda: NOW).cancel_event(
        account=account(ConnectorResource.CALENDAR),
        credential=credential(),
        request=request,
        operation_id=OPERATION,
        idempotency_key=KEY,
    )
    assert isinstance(result, ProviderReceipt)
    assert result.outcome == "cancelled"
    assert_immutable_calendar_requests(transport.calls)

    transport = FakeTransport(
        response(event_row()),
        MicrosoftEffectUnknown(),
        response({"error": {}}, status=404),
    )
    result = await MicrosoftConnectedAppProvider(transport, now=lambda: NOW).cancel_event(
        account=account(ConnectorResource.CALENDAR),
        credential=credential(),
        request=request,
        operation_id=OPERATION,
        idempotency_key=KEY,
    )
    assert isinstance(result, ProviderReceipt)
    assert [call.method for call in transport.calls].count("DELETE") == 1
    assert [call.method for call in transport.calls].count("GET") == 2
    assert transport.calls[-1].path == "/v1.0/me/events/event-1"
    assert_immutable_calendar_requests(transport.calls)


@pytest.mark.asyncio
async def test_cancel_rejects_attendee_event_before_effect():
    request = CalendarCancelRequest.build(
        calendar_id="calendar-1",
        event_id="event-1",
        expected_resource_version='W/"event-key-1"',
    )
    transport = FakeTransport(response(event_row(is_organizer=False, response_type="accepted")))
    with pytest.raises(MicrosoftProviderError, match="CANCEL_ATTENDEE_UNSUPPORTED"):
        await MicrosoftConnectedAppProvider(transport).cancel_event(
            account=account(ConnectorResource.CALENDAR),
            credential=credential(),
            request=request,
            operation_id=OPERATION,
            idempotency_key=KEY,
        )
    assert [call.method for call in transport.calls] == ["GET"]


@pytest.mark.asyncio
async def test_cancel_stale_calendar_path_does_not_claim_moved_event_cancelled():
    request = CalendarCancelRequest.build(
        calendar_id="calendar-1",
        event_id="event-1",
        expected_resource_version='W/"event-key-1"',
    )
    transport = FakeTransport(
        response(event_row()),
        response({"error": {}}, status=404),
        response({"id": "event-1"}),
    )
    result = await MicrosoftConnectedAppProvider(transport, now=lambda: NOW).cancel_event(
        account=account(ConnectorResource.CALENDAR),
        credential=credential(),
        request=request,
        operation_id=OPERATION,
        idempotency_key=KEY,
    )
    assert isinstance(result, AmbiguousProviderResult)
    assert [call.method for call in transport.calls].count("DELETE") == 1
    assert transport.calls[-1].path == "/v1.0/me/events/event-1"
    assert_immutable_calendar_requests(transport.calls)


@pytest.mark.asyncio
async def test_exact_account_credential_and_resource_bindings_are_required():
    other_owner = str(uuid4())
    bad_credential = CredentialHandleRef(
        owner_id=other_owner,
        connection_id=CONNECTION,
        provider=ConnectorProvider.MICROSOFT,
        handle_id="broker/microsoft/credential-handle-0002",
    )
    provider = MicrosoftConnectedAppProvider(FakeTransport())
    with pytest.raises(MicrosoftProviderError, match="CREDENTIAL_BINDING_MISMATCH"):
        await provider.get_message(
            account=account(ConnectorResource.MAIL),
            credential=bad_credential,
            request=MailGetRequest.build(message_id="message-1"),
        )
    with pytest.raises(MicrosoftProviderError, match="ACCOUNT_RESOURCE_MISMATCH"):
        await provider.get_message(
            account=account(ConnectorResource.CALENDAR),
            credential=credential(),
            request=MailGetRequest.build(message_id="message-1"),
        )


def test_repr_and_errors_do_not_echo_content_or_tokens():
    request = MicrosoftTransportRequest(
        "POST",
        GRAPH_HOST,
        "/v1.0/me/messages",
        json_body={"body": "private-content"},
    )
    response_value = MicrosoftTransportResponse(
        200, {"body": "private-content"}, {"request-id": "secret-id"}
    )
    error = MicrosoftProviderError("MICROSOFT_REQUEST_REJECTED")
    assert "private-content" not in repr(request)
    assert "private-content" not in repr(response_value)
    assert "secret-id" not in repr(response_value)
    assert str(error) == "MICROSOFT_REQUEST_REJECTED"
