from __future__ import annotations

import base64
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from email import policy
from email.parser import BytesParser
import hashlib
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from backend.connected_app_contracts import (
    CalendarCancelRequest,
    CalendarCreateRequest,
    CalendarFreeBusyRequest,
    CalendarGetRequest,
    CalendarListRequest,
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
)
from backend.connected_app_google import (
    CALENDAR_HOST,
    GMAIL_HOST,
    GoogleConnectedAppProvider,
    GoogleEffectUnknown,
    GoogleNotDispatched,
    GoogleProviderError,
    GoogleTransportSecurityPolicy,
    GoogleTransportRequest,
    GoogleTransportResponse,
)
from backend.connected_app_policy import ConnectorProvider, ConnectorResource


NOW = datetime(2026, 11, 7, 20, 0, tzinfo=timezone.utc)
OWNER = str(uuid4())
CONNECTION = str(uuid4())
KEY = hashlib.sha256(b"idempotency").hexdigest()


def account(resource: ConnectorResource) -> ConnectedAccountRef:
    return ConnectedAccountRef(
        owner_id=OWNER,
        connection_id=CONNECTION,
        provider=ConnectorProvider.GOOGLE,
        resource=resource,
        account_kind=ConnectorAccountKind.PERSONAL,
        external_account_id_hash="a" * 64,
    )


def credential() -> CredentialHandleRef:
    return CredentialHandleRef(
        owner_id=OWNER,
        connection_id=CONNECTION,
        provider=ConnectorProvider.GOOGLE,
        handle_id="broker/google/credential-handle-0001",
    )


class FakeTransport:
    def __init__(self, *responses: object) -> None:
        self.security_policy = GoogleTransportSecurityPolicy()
        self.responses = list(responses)
        self.calls: list[GoogleTransportRequest] = []

    async def request(self, *, account, credential, request):
        assert credential.handle_id == "broker/google/credential-handle-0001"
        self.calls.append(request)
        value = self.responses.pop(0)
        if isinstance(value, BaseException):
            raise value
        return value


def response(body=None, *, status=200, request_id="request-1"):
    return GoogleTransportResponse(status, body, {"x-goog-request-id": request_id})


def gmail_message(
    *,
    message_id="m1",
    history="h1",
    body_text="hello",
    thread="t1",
    subject="Private subject",
    rfc_message_id="<rfc-message@example.com>",
    references=None,
    internal_date="1794081600000",
    labels=("INBOX",),
):
    encoded = base64.urlsafe_b64encode(body_text.encode()).decode().rstrip("=")
    result = {
        "id": message_id,
        "threadId": thread,
        "historyId": history,
        "internalDate": internal_date,
        "labelIds": list(labels),
        "payload": {
            "partId": "",
            "mimeType": "multipart/alternative",
            "filename": "",
            "headers": [
                {"name": "Subject", "value": subject},
                {"name": "From", "value": "sender@example.com"},
                {"name": "To", "value": "owner@example.com"},
                {"name": "Message-ID", "value": rfc_message_id},
            ],
            "body": {"size": 0},
            "parts": [
                {
                    "partId": "0",
                    "mimeType": "text/plain",
                    "filename": "",
                    "headers": [
                        {"name": "Content-Type", "value": "text/plain; charset=UTF-8"}
                    ],
                    "body": {"size": len(body_text.encode()), "data": encoded},
                }
            ],
        },
    }
    if references is not None:
        result["payload"]["headers"].append({"name": "References", "value": references})
    return result


def calendar_event(*, event_id="event1", etag='"etag1"'):
    return {
        "id": event_id,
        "etag": etag,
        "status": "confirmed",
        "summary": "Private meeting",
        "description": "Private notes",
        "location": "Office",
        "start": {"dateTime": "2026-11-07T21:00:00Z", "timeZone": "UTC"},
        "end": {"dateTime": "2026-11-07T22:00:00Z", "timeZone": "UTC"},
        "attendees": [{"email": "guest@example.com"}],
        "organizer": {"email": "owner@example.com"},
    }


def draft(*, reply=False) -> MailDraftSpec:
    return MailDraftSpec(
        to=("recipient@example.com",),
        subject="Private subject",
        body_text="Private body",
        reply_to_message_id="m/source" if reply else None,
        expected_resource_version="source-history" if reply else None,
    )


def approved_gmail_message(
    *,
    spec=None,
    message_id="m1",
    history="h1",
    thread="t1",
    in_reply_to=None,
    references=None,
    labels=("SENT",),
):
    spec = spec or draft()
    encoded = base64.urlsafe_b64encode(spec.body_text.encode()).decode().rstrip("=")
    headers = [
        {"name": "To", "value": ", ".join(spec.to)},
        {"name": "Subject", "value": spec.subject},
    ]
    if spec.cc:
        headers.append({"name": "Cc", "value": ", ".join(spec.cc)})
    if spec.bcc:
        headers.append({"name": "Bcc", "value": ", ".join(spec.bcc)})
    if in_reply_to is not None:
        headers.append({"name": "In-Reply-To", "value": in_reply_to})
    if references is not None:
        headers.append({"name": "References", "value": references})
    return {
        "id": message_id,
        "threadId": thread,
        "historyId": history,
        "internalDate": "1794081600000",
        "labelIds": list(labels),
        "payload": {
            "mimeType": "text/plain",
            "headers": headers,
            "body": {"data": encoded},
        },
    }


def gmail_write_response(
    *,
    message_id="sent1",
    thread="thread1",
    history="h1",
    labels=("SENT",),
):
    return {
        "id": message_id,
        "threadId": thread,
        "historyId": history,
        "labelIds": list(labels),
    }


def freebusy_response(*, calendars=None, time_min=None, time_max=None):
    return {
        "timeMin": time_min or NOW.isoformat().replace("+00:00", "Z"),
        "timeMax": time_max
        or (NOW + timedelta(days=1)).isoformat().replace("+00:00", "Z"),
        "calendars": calendars if calendars is not None else {},
    }


def calendar_query():
    from backend.connected_app_contracts import CalendarQuery

    return CalendarQuery(
        calendar_ids=("primary/calendar",),
        starts_at=NOW,
        ends_at=NOW + timedelta(days=1),
        time_zone="UTC",
        limit=10,
    )


def event_spec(*, update=False, attendees=("guest@example.com",)):
    return EventSpec(
        calendar_id="primary/calendar",
        title="Private meeting",
        starts_at=datetime(2026, 11, 9, 10, tzinfo=ZoneInfo("America/New_York")),
        ends_at=datetime(2026, 11, 9, 11, tzinfo=ZoneInfo("America/New_York")),
        time_zone="America/New_York",
        attendees=attendees,
        source_event_id="event/source" if update else None,
        expected_resource_version='"old-etag"' if update else None,
    )


def approved_calendar_event(
    *,
    spec=None,
    event_id="event1",
    etag='"etag1"',
    status="confirmed",
):
    spec = spec or event_spec()
    return {
        "id": event_id,
        "etag": etag,
        "status": status,
        "summary": spec.title,
        "description": spec.description,
        "location": spec.location,
        "start": {"dateTime": spec.starts_at.isoformat(), "timeZone": spec.time_zone},
        "end": {"dateTime": spec.ends_at.isoformat(), "timeZone": spec.time_zone},
        "attendees": [{"email": address} for address in spec.attendees],
        "organizer": {"email": "owner@example.com"},
    }


def decode_raw(raw: str):
    payload = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))
    return BytesParser(policy=policy.default).parsebytes(payload)


def test_transport_boundary_fixes_hosts_and_redacts_content():
    request = GoogleTransportRequest(
        "POST", GMAIL_HOST, "/gmail/v1/users/me/messages/send", json_body={"raw": "secret"}
    )
    assert "secret" not in repr(request)
    assert "messages/send" not in repr(request)
    with pytest.raises(ValueError):
        GoogleTransportRequest("GET", "evil.example", "/steal")
    with pytest.raises(ValueError):
        GoogleTransportRequest("GET", GMAIL_HOST, "https://evil.example/steal")
    with pytest.raises(ValueError):
        GoogleTransportRequest("GET", GMAIL_HOST, "//evil.example/steal")
    with pytest.raises(ValueError):
        GoogleTransportRequest("GET", GMAIL_HOST, "/ok", headers=(("Authorization", "Bearer x"),))


def test_transport_requires_exact_locked_down_security_attestation():
    policy = GoogleTransportSecurityPolicy()
    assert policy.scheme == "https"
    assert policy.allowed_hosts == (GMAIL_HOST, CALENDAR_HOST)
    assert policy.require_host_header_match and policy.require_sni_match
    assert not policy.follow_redirects
    assert not policy.automatic_retries
    assert not policy.use_environment_proxies
    with pytest.raises(ValueError):
        GoogleTransportSecurityPolicy(follow_redirects=True)

    class Unattested:
        async def request(self, **kwargs):  # pragma: no cover - constructor rejects it
            return kwargs

    with pytest.raises(ValueError, match="attested"):
        GoogleConnectedAppProvider(Unattested())


def test_response_is_bounded_and_redacted():
    item = GoogleTransportResponse(200, {"private": "value"})
    assert "private" not in repr(item) and "value" not in repr(item)
    with pytest.raises(ValueError):
        GoogleTransportResponse(200, {"value": "x" * 1_000_001})
    with pytest.raises(ValueError):
        GoogleTransportResponse(
            200,
            {"value": "small"},
            decompressed_size_bytes=1_000_001,
        )


@pytest.mark.asyncio
async def test_mail_search_uses_list_then_full_get_and_returns_untrusted_summary():
    transport = FakeTransport(response({"messages": [{"id": "id/one"}]}), response(gmail_message(message_id="id/one")))
    provider = GoogleConnectedAppProvider(transport, now=lambda: NOW)
    result = await provider.search_mail(
        account=account(ConnectorResource.MAIL),
        credential=credential(),
        request=MailSearchRequest.build(MailQuery(query="from:boss", limit=1)),
    )
    assert len(result) == 1 and result[0].message_id == "id/one"
    assert result[0].trust_boundary == "untrusted_external_data"
    assert transport.calls[0].path == "/gmail/v1/users/me/messages"
    assert transport.calls[1].path.endswith("/id%2Fone")
    assert transport.calls[1].query == (("format", "full"),)
    assert ("q", "from:boss") in transport.calls[0].query
    assert ("labelIds", "INBOX") in transport.calls[0].query
    assert all("label:" not in value for name, value in transport.calls[0].query if name == "q")
    assert "Private subject" not in repr(result[0])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "attachment_part",
    [
        {
            "partId": "1",
            "mimeType": "application/pdf",
            "filename": "report.pdf",
            "headers": [],
            "body": {"size": 3, "data": "cGRm"},
        },
        {
            "partId": "1",
            "mimeType": "application/pdf",
            "filename": "",
            "headers": [],
            "body": {"size": 3, "attachmentId": "attachment/1"},
        },
        {
            "partId": "1",
            "mimeType": "text/plain",
            "filename": "",
            "headers": [
                {"name": "Content-Disposition", "value": "attachment"}
            ],
            "body": {"size": 3, "data": "cGRm"},
        },
    ],
    ids=("filename", "attachment-id", "content-disposition"),
)
async def test_mail_search_full_mime_truthfully_detects_attachments(attachment_part):
    item = gmail_message(message_id="m1")
    item["payload"]["mimeType"] = "multipart/mixed"
    item["payload"]["parts"].append(attachment_part)
    transport = FakeTransport(
        response({"messages": [{"id": "m1"}]}),
        response(item),
    )
    provider = GoogleConnectedAppProvider(transport)

    result = await provider.search_mail(
        account=account(ConnectorResource.MAIL),
        credential=credential(),
        request=MailSearchRequest.build(MailQuery(query="", limit=1)),
    )

    assert result[0].has_attachments is True
    assert transport.calls[1].query == (("format", "full"),)


@pytest.mark.asyncio
async def test_mail_search_rejects_metadata_shaped_detail_instead_of_false_no_attachment():
    item = gmail_message(message_id="m1")
    item["payload"] = {
        "partId": "",
        "mimeType": "multipart/mixed",
        "filename": "",
        "headers": item["payload"]["headers"],
        "body": {"size": 0},
        # A metadata-shaped response omits the authoritative MIME children.
    }
    transport = FakeTransport(
        response({"messages": [{"id": "m1"}]}),
        response(item),
    )
    provider = GoogleConnectedAppProvider(transport)

    with pytest.raises(GoogleProviderError) as captured:
        await provider.search_mail(
            account=account(ConnectorResource.MAIL),
            credential=credential(),
            request=MailSearchRequest.build(MailQuery(query="", limit=1)),
        )

    assert captured.value.code == "GOOGLE_RESPONSE_MALFORMED"
    assert len(transport.calls) == 2


@pytest.mark.asyncio
async def test_mail_search_paginates_with_nonrepeating_tokens_to_global_limit():
    transport = FakeTransport(
        response({"messages": [{"id": "m1"}], "nextPageToken": "page/2"}),
        response(gmail_message(message_id="m1")),
        response({"messages": [{"id": "m2"}]}),
        response(gmail_message(message_id="m2")),
    )
    provider = GoogleConnectedAppProvider(transport)
    result = await provider.search_mail(
        account=account(ConnectorResource.MAIL),
        credential=credential(),
        request=MailSearchRequest.build(MailQuery(query="", limit=2)),
    )
    assert [item.message_id for item in result] == ["m1", "m2"]
    assert ("pageToken", "page/2") in transport.calls[2].query
    assert ("maxResults", "1") in transport.calls[2].query


@pytest.mark.asyncio
async def test_mail_search_rejects_repeated_pagination_tokens():
    transport = FakeTransport(
        response({"messages": [], "nextPageToken": "same"}),
        response({"messages": [], "nextPageToken": "same"}),
    )
    provider = GoogleConnectedAppProvider(transport)
    with pytest.raises(GoogleProviderError, match="GOOGLE_PAGINATION_INVALID"):
        await provider.search_mail(
            account=account(ConnectorResource.MAIL),
            credential=credential(),
            request=MailSearchRequest.build(MailQuery(query="", limit=2)),
        )
    assert len(transport.calls) == 2


@pytest.mark.asyncio
async def test_mail_search_rejects_detail_identity_substitution():
    transport = FakeTransport(
        response({"messages": [{"id": "listed"}]}),
        response(gmail_message(message_id="substituted")),
    )
    provider = GoogleConnectedAppProvider(transport)
    with pytest.raises(GoogleProviderError) as captured:
        await provider.search_mail(
            account=account(ConnectorResource.MAIL),
            credential=credential(),
            request=MailSearchRequest.build(MailQuery(query="", limit=1)),
        )
    assert captured.value.code == "GOOGLE_RESPONSE_RESOURCE_MISMATCH"


@pytest.mark.asyncio
async def test_mail_search_uses_exact_repeated_labels_and_exact_millisecond_window():
    query = MailQuery(
        query="from:boss",
        folder_ids=("Label_custom/123", "sent"),
        after=NOW + timedelta(milliseconds=500),
        before=NOW + timedelta(seconds=1, milliseconds=500),
        limit=1,
    )
    transport = FakeTransport(
        response({"messages": [{"id": "m1"}]}),
        response(
            gmail_message(
                message_id="m1",
                internal_date="1794081600501",
                labels=("Label_custom/123", "SENT"),
            )
        ),
    )
    provider = GoogleConnectedAppProvider(transport)
    result = await provider.search_mail(
        account=account(ConnectorResource.MAIL),
        credential=credential(),
        request=MailSearchRequest.build(query),
    )
    assert [item.message_id for item in result] == ["m1"]
    assert transport.calls[0].query == (
        ("q", "from:boss after:1794081600 before:1794081602"),
        ("maxResults", "1"),
        ("labelIds", "Label_custom/123"),
        ("labelIds", "SENT"),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "internal_date",
    [
        "1794081600499",
        "1794081600500",
        "1794081601500",
        "1794081601501",
    ],
)
async def test_mail_search_rejects_stale_or_exact_boundary_details(internal_date):
    query = MailQuery(
        query="",
        folder_ids=("inbox",),
        after=NOW + timedelta(milliseconds=500),
        before=NOW + timedelta(seconds=1, milliseconds=500),
        limit=1,
    )
    transport = FakeTransport(
        response({"messages": [{"id": "m1"}]}),
        response(gmail_message(message_id="m1", internal_date=internal_date)),
    )
    provider = GoogleConnectedAppProvider(transport)
    with pytest.raises(GoogleProviderError) as captured:
        await provider.search_mail(
            account=account(ConnectorResource.MAIL),
            credential=credential(),
            request=MailSearchRequest.build(query),
        )
    assert captured.value.code == "GOOGLE_RESPONSE_OUT_OF_BOUNDS"
    assert transport.calls[0].query == (
        ("q", "after:1794081600 before:1794081602"),
        ("maxResults", "1"),
        ("labelIds", "INBOX"),
    )


@pytest.mark.asyncio
async def test_mail_search_rejects_detail_missing_an_exact_custom_label():
    transport = FakeTransport(
        response({"messages": [{"id": "m1"}]}),
        response(gmail_message(message_id="m1", labels=("INBOX",))),
    )
    provider = GoogleConnectedAppProvider(transport)
    with pytest.raises(GoogleProviderError) as captured:
        await provider.search_mail(
            account=account(ConnectorResource.MAIL),
            credential=credential(),
            request=MailSearchRequest.build(
                MailQuery(
                    query="",
                    folder_ids=("Label_custom/123",),
                    limit=1,
                )
            ),
        )
    assert captured.value.code == "GOOGLE_RESPONSE_RESOURCE_MISMATCH"
    assert ("labelIds", "Label_custom/123") in transport.calls[0].query


@pytest.mark.asyncio
async def test_mail_get_enforces_exact_history_version():
    provider = GoogleConnectedAppProvider(FakeTransport(response(gmail_message(history="new"))))
    with pytest.raises(GoogleProviderError, match="GOOGLE_RESOURCE_VERSION_CONFLICT"):
        await provider.get_message(
            account=account(ConnectorResource.MAIL),
            credential=credential(),
            request=MailGetRequest.build(message_id="m1", expected_resource_version="old"),
        )


@pytest.mark.asyncio
async def test_mail_get_rejects_response_identity_substitution():
    provider = GoogleConnectedAppProvider(
        FakeTransport(response(gmail_message(message_id="wrong")))
    )
    with pytest.raises(GoogleProviderError) as captured:
        await provider.get_message(
            account=account(ConnectorResource.MAIL),
            credential=credential(),
            request=MailGetRequest.build(message_id="requested"),
        )
    assert captured.value.code == "GOOGLE_RESPONSE_RESOURCE_MISMATCH"


@pytest.mark.asyncio
async def test_mail_mime_prefers_plain_counts_actual_attachments_and_sanitizes_html():
    item = gmail_message(body_text="unused")
    encode = lambda value: base64.urlsafe_b64encode(value.encode()).decode().rstrip("=")
    item["payload"] = {
        "mimeType": "multipart/mixed",
        "headers": gmail_message()["payload"]["headers"],
        "body": {},
        "parts": [
            {
                "mimeType": "multipart/alternative",
                "filename": "",
                "body": {},
                "parts": [
                    {"mimeType": "text/html", "filename": "", "body": {"data": encode("<p>HTML secret</p>")}},
                    {"mimeType": "text/plain", "filename": "", "body": {"data": encode("plain wins")}},
                ],
            },
            {
                "mimeType": "application/pdf",
                "filename": "",
                "body": {"attachmentId": "attachment/1", "size": 50},
            },
        ],
    }
    provider = GoogleConnectedAppProvider(FakeTransport(response(item)))
    result = await provider.get_message(
        account=account(ConnectorResource.MAIL),
        credential=credential(),
        request=MailGetRequest.build(message_id="m1"),
    )
    assert result.body_text == "plain wins"
    assert "HTML secret" not in result.body_text
    assert result.attachment_count == 1

    html_only = gmail_message()
    html_only["payload"] = {
        "mimeType": "text/html",
        "headers": gmail_message()["payload"]["headers"],
        "body": {
            "data": encode("<p>Hello <b>world</b></p><script>steal()</script><div>Next</div>")
        },
    }
    provider = GoogleConnectedAppProvider(FakeTransport(response(html_only)))
    result = await provider.get_message(
        account=account(ConnectorResource.MAIL),
        credential=credential(),
        request=MailGetRequest.build(message_id="m1"),
    )
    assert "Hello world" in result.body_text
    assert "Next" in result.body_text
    assert "steal" not in result.body_text


@pytest.mark.asyncio
async def test_create_draft_builds_safe_mime_and_returns_content_free_receipt():
    draft_message = approved_gmail_message(
        message_id="message/draft",
        history="h2",
        thread="draft-thread",
        labels=("DRAFT",),
    )
    transport = FakeTransport(
        response({"id": "draft1", "message": {"id": "message/draft"}}),
        response({"id": "draft1", "message": draft_message}),
    )
    provider = GoogleConnectedAppProvider(transport, now=lambda: NOW)
    receipt = await provider.create_draft(
        account=account(ConnectorResource.MAIL), credential=credential(),
        request=MailDraftRequest.build(draft()), operation_id=str(uuid4()), idempotency_key=KEY,
    )
    message = decode_raw(transport.calls[0].json_body["message"]["raw"])
    assert message["To"] == "recipient@example.com"
    assert message["Subject"] == "Private subject"
    assert "Private body" in message.get_content()
    assert receipt.outcome == "drafted"
    assert "Private" not in repr(receipt)
    assert transport.calls[1].path.endswith("/drafts/draft1")
    assert transport.calls[1].query == (("format", "full"),)


@pytest.mark.asyncio
async def test_create_draft_reads_authoritative_history_when_create_omits_it():
    transport = FakeTransport(
        response({"id": "draft1"}),
        response(
            {
                "id": "draft1",
                "message": {
                    "id": "message/draft",
                    "threadId": "draft-thread",
                    "historyId": "authoritative-history",
                    "labelIds": ["DRAFT"],
                },
            }
        ),
        response(
            approved_gmail_message(
                message_id="message/draft",
                history="authoritative-history",
                thread="draft-thread",
                labels=("DRAFT",),
            )
        ),
    )
    provider = GoogleConnectedAppProvider(transport, now=lambda: NOW)
    receipt = await provider.create_draft(
        account=account(ConnectorResource.MAIL), credential=credential(),
        request=MailDraftRequest.build(draft()), operation_id=str(uuid4()), idempotency_key=KEY,
    )
    assert transport.calls[1].path.endswith("/drafts/draft1")
    assert transport.calls[2].path.endswith("/messages/message%2Fdraft")
    assert receipt.resource_version == "authoritative-history"


@pytest.mark.asyncio
@pytest.mark.parametrize("drift", ["recipient", "body", "attachment", "missing_payload"])
async def test_create_draft_authoritative_content_drift_is_ambiguous(drift):
    authoritative = approved_gmail_message(
        message_id="message/draft",
        thread="draft-thread",
        labels=("DRAFT",),
    )
    if drift == "recipient":
        authoritative["payload"]["headers"][0]["value"] = "other@example.com"
    elif drift == "body":
        authoritative["payload"]["body"]["data"] = base64.urlsafe_b64encode(
            b"different body"
        ).decode().rstrip("=")
    elif drift == "attachment":
        authoritative["payload"] = {
            "mimeType": "multipart/mixed",
            "headers": authoritative["payload"]["headers"],
            "body": {},
            "parts": [
                {
                    "mimeType": "text/plain",
                    "filename": "",
                    "body": authoritative["payload"]["body"],
                },
                {
                    "mimeType": "application/pdf",
                    "filename": "file.pdf",
                    "body": {"attachmentId": "a1"},
                },
            ],
        }
    elif drift == "missing_payload":
        authoritative.pop("payload")
    responses = [
        response({"id": "draft1", "message": {"id": "message/draft"}}),
        response({"id": "draft1", "message": authoritative}),
    ]
    if drift == "missing_payload":
        responses.append(response(authoritative))
    transport = FakeTransport(*responses)
    provider = GoogleConnectedAppProvider(transport, now=lambda: NOW)
    result = await provider.create_draft(
        account=account(ConnectorResource.MAIL),
        credential=credential(),
        request=MailDraftRequest.build(draft()),
        operation_id=str(uuid4()),
        idempotency_key=KEY,
    )
    assert result.code == "CONNECTED_PROVIDER_RESULT_AMBIGUOUS"
    assert [call.method for call in transport.calls] == [
        "POST",
        "GET",
        *(["GET"] if drift == "missing_payload" else []),
    ]


@pytest.mark.asyncio
async def test_create_draft_missing_message_identity_and_failed_draft_read_is_ambiguous():
    transport = FakeTransport(
        response({"id": "draft1"}),
        response(
            {
                "id": "draft1",
                "message": {
                    "id": "message/draft",
                    "threadId": "draft-thread",
                    "historyId": "draft-history",
                    "labelIds": ["DRAFT"],
                },
            }
        ),
        GoogleEffectUnknown("private draft read loss"),
    )
    provider = GoogleConnectedAppProvider(transport, now=lambda: NOW)
    result = await provider.create_draft(
        account=account(ConnectorResource.MAIL),
        credential=credential(),
        request=MailDraftRequest.build(draft()),
        operation_id=str(uuid4()),
        idempotency_key=KEY,
    )
    assert result.code == "CONNECTED_PROVIDER_RESULT_AMBIGUOUS"
    assert [call.method for call in transport.calls] == ["POST", "GET", "GET"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("wrapper_id", "wrapper_message_id"),
    [("other-draft", "message/draft"), ("draft1", "other-message")],
)
async def test_create_draft_binds_authoritative_wrapper_and_nested_identity(
    wrapper_id,
    wrapper_message_id,
):
    nested = approved_gmail_message(
        message_id=wrapper_message_id,
        thread="draft-thread",
        labels=("DRAFT",),
    )
    transport = FakeTransport(
        response({"id": "draft1", "message": {"id": "message/draft"}}),
        response({"id": wrapper_id, "message": nested}),
    )
    provider = GoogleConnectedAppProvider(transport, now=lambda: NOW)
    result = await provider.create_draft(
        account=account(ConnectorResource.MAIL),
        credential=credential(),
        request=MailDraftRequest.build(draft()),
        operation_id=str(uuid4()),
        idempotency_key=KEY,
    )
    assert result.code == "CONNECTED_PROVIDER_RESULT_AMBIGUOUS"
    assert [call.method for call in transport.calls] == ["POST", "GET"]


@pytest.mark.asyncio
@pytest.mark.parametrize("labels", [("SENT",), (), ("DRAFT", "SENT")])
async def test_create_draft_requires_draft_state_and_rejects_sent_state(labels):
    nested = approved_gmail_message(
        message_id="message/draft",
        thread="draft-thread",
        labels=labels,
    )
    transport = FakeTransport(
        response({"id": "draft1", "message": {"id": "message/draft"}}),
        response({"id": "draft1", "message": nested}),
    )
    provider = GoogleConnectedAppProvider(transport, now=lambda: NOW)
    result = await provider.create_draft(
        account=account(ConnectorResource.MAIL),
        credential=credential(),
        request=MailDraftRequest.build(draft()),
        operation_id=str(uuid4()),
        idempotency_key=KEY,
    )
    assert result.code == "CONNECTED_PROVIDER_RESULT_AMBIGUOUS"
    assert len(transport.calls) == 2


@pytest.mark.asyncio
async def test_send_response_loss_is_ambiguous_and_never_retried():
    transport = FakeTransport(GoogleEffectUnknown("lost after dispatch"))
    provider = GoogleConnectedAppProvider(transport, now=lambda: NOW)
    result = await provider.send_mail(
        account=account(ConnectorResource.MAIL), credential=credential(),
        request=MailSendRequest.build(draft()), operation_id=str(uuid4()), idempotency_key=KEY,
    )
    assert result.code == "CONNECTED_PROVIDER_RESULT_AMBIGUOUS"
    assert result.retryable is False
    assert len(transport.calls) == 1


@pytest.mark.asyncio
async def test_send_settles_only_after_exact_authoritative_full_readback():
    approved = MailDraftSpec(
        to=("recipient@example.com",),
        cc=("copy@example.com",),
        bcc=("blind@example.com",),
        subject="Private subject",
        body_text="Private body",
    )
    transport = FakeTransport(
        response(
            gmail_write_response(
                message_id="sent1",
                thread="thread1",
                history="read-history",
            )
        ),
        response(
            approved_gmail_message(
                spec=approved,
                message_id="sent1",
                history="read-history",
                thread="thread1",
            )
        ),
    )
    provider = GoogleConnectedAppProvider(transport, now=lambda: NOW)
    receipt = await provider.send_mail(
        account=account(ConnectorResource.MAIL),
        credential=credential(),
        request=MailSendRequest.build(approved),
        operation_id=str(uuid4()),
        idempotency_key=KEY,
    )
    assert receipt.outcome == "sent"
    assert receipt.resource_version == "read-history"
    assert [call.method for call in transport.calls] == ["POST", "GET"]
    assert ("format", "full") in transport.calls[1].query


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "drift",
    [
        "missing_id",
        "missing_payload",
        "recipient",
        "extra_cc",
        "extra_bcc",
        "duplicate_subject",
        "body",
    ],
)
async def test_send_missing_identity_or_authoritative_content_drift_is_ambiguous(drift):
    write = gmail_write_response(message_id="sent1", thread="thread1", history="h1")
    authoritative = approved_gmail_message(message_id="sent1", thread="thread1")
    responses = [response(write)]
    if drift == "missing_id":
        write.pop("id")
    else:
        if drift == "missing_payload":
            authoritative.pop("payload")
        elif drift == "recipient":
            authoritative["payload"]["headers"][0]["value"] = "other@example.com"
        elif drift == "extra_cc":
            authoritative["payload"]["headers"].append(
                {"name": "Cc", "value": "other@example.com"}
            )
        elif drift == "extra_bcc":
            authoritative["payload"]["headers"].append(
                {"name": "Bcc", "value": "other@example.com"}
            )
        elif drift == "duplicate_subject":
            authoritative["payload"]["headers"].append(
                {"name": "Subject", "value": draft().subject}
            )
        elif drift == "body":
            authoritative["payload"]["body"]["data"] = base64.urlsafe_b64encode(
                b"different body"
            ).decode().rstrip("=")
        responses.append(response(authoritative))
    transport = FakeTransport(*responses)
    provider = GoogleConnectedAppProvider(transport, now=lambda: NOW)
    result = await provider.send_mail(
        account=account(ConnectorResource.MAIL),
        credential=credential(),
        request=MailSendRequest.build(draft()),
        operation_id=str(uuid4()),
        idempotency_key=KEY,
    )
    assert result.code == "CONNECTED_PROVIDER_RESULT_AMBIGUOUS"
    assert len(transport.calls) == len(responses)


@pytest.mark.asyncio
@pytest.mark.parametrize("drift", ["write_label", "read_label", "thread", "history"])
async def test_send_binds_exact_state_thread_and_history_across_readback(drift):
    write = gmail_write_response(
        message_id="sent1",
        thread="thread1",
        history="history1",
    )
    authoritative = approved_gmail_message(
        message_id="sent1",
        thread="thread1",
        history="history1",
    )
    if drift == "write_label":
        write["labelIds"] = ["DRAFT"]
    elif drift == "read_label":
        authoritative["labelIds"] = ["DRAFT"]
    elif drift == "thread":
        authoritative["threadId"] = "other-thread"
    elif drift == "history":
        authoritative["historyId"] = "other-history"
    responses = [response(write)]
    if drift != "write_label":
        responses.append(response(authoritative))
    transport = FakeTransport(*responses)
    provider = GoogleConnectedAppProvider(transport, now=lambda: NOW)
    result = await provider.send_mail(
        account=account(ConnectorResource.MAIL),
        credential=credential(),
        request=MailSendRequest.build(draft()),
        operation_id=str(uuid4()),
        idempotency_key=KEY,
    )
    assert result.code == "CONNECTED_PROVIDER_RESULT_AMBIGUOUS"
    assert len(transport.calls) == len(responses)


@pytest.mark.asyncio
async def test_only_explicit_not_dispatched_is_safe_retryable_for_a_write():
    transport = FakeTransport(GoogleNotDispatched("private connect detail"))
    provider = GoogleConnectedAppProvider(transport, now=lambda: NOW)
    with pytest.raises(GoogleProviderError) as captured:
        await provider.send_mail(
            account=account(ConnectorResource.MAIL),
            credential=credential(),
            request=MailSendRequest.build(draft()),
            operation_id=str(uuid4()),
            idempotency_key=KEY,
        )
    assert captured.value.code == "GOOGLE_TRANSPORT_NOT_DISPATCHED"
    assert captured.value.retryable is True
    assert "private" not in repr(captured.value)
    assert len(transport.calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure",
    [
        TimeoutError("private timeout"),
        ConnectionResetError("private reset"),
        ValueError("private compressed bomb"),
        RuntimeError("private response decode"),
    ],
)
async def test_every_other_write_transport_failure_is_ambiguous_single_dispatch(failure):
    transport = FakeTransport(failure)
    provider = GoogleConnectedAppProvider(transport, now=lambda: NOW)
    result = await provider.send_mail(
        account=account(ConnectorResource.MAIL),
        credential=credential(),
        request=MailSendRequest.build(draft()),
        operation_id=str(uuid4()),
        idempotency_key=KEY,
    )
    assert result.code == "CONNECTED_PROVIDER_RESULT_AMBIGUOUS"
    assert "private" not in repr(result)
    assert len(transport.calls) == 1


@pytest.mark.asyncio
async def test_redirect_response_is_not_followed_or_rehosted():
    transport = FakeTransport(response({"location": "https://evil.example"}, status=302))
    provider = GoogleConnectedAppProvider(transport)
    with pytest.raises(GoogleProviderError, match="GOOGLE_REQUEST_REJECTED"):
        await provider.get_message(
            account=account(ConnectorResource.MAIL),
            credential=credential(),
            request=MailGetRequest.build(message_id="m1"),
        )
    assert len(transport.calls) == 1
    assert transport.calls[0].host == GMAIL_HOST


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "provider_response",
    [response({"missing": "receipt"}), response({"error": "server"}, status=500)],
)
async def test_malformed_or_server_error_after_write_is_ambiguous(provider_response):
    transport = FakeTransport(provider_response)
    provider = GoogleConnectedAppProvider(transport, now=lambda: NOW)
    result = await provider.send_mail(
        account=account(ConnectorResource.MAIL), credential=credential(),
        request=MailSendRequest.build(draft()), operation_id=str(uuid4()), idempotency_key=KEY,
    )
    assert result.code == "CONNECTED_PROVIDER_RESULT_AMBIGUOUS"
    assert result.retryable is False
    assert len(transport.calls) == 1


@pytest.mark.asyncio
async def test_read_response_loss_is_categorical_and_content_free():
    provider = GoogleConnectedAppProvider(FakeTransport(GoogleEffectUnknown("private socket detail")))
    with pytest.raises(GoogleProviderError) as captured:
        await provider.get_message(
            account=account(ConnectorResource.MAIL), credential=credential(),
            request=MailGetRequest.build(message_id="m1"),
        )
    assert captured.value.code == "GOOGLE_TRANSPORT_UNAVAILABLE"
    assert "private socket detail" not in repr(captured.value)


@pytest.mark.asyncio
async def test_reply_verifies_source_version_and_threads_exact_message():
    source = gmail_message(
        message_id="m/source",
        history="source-history",
        thread="thread/source",
        references="<prior@example.com>",
    )
    write_receipt = gmail_write_response(
        message_id="sent1",
        history="sent-history",
        thread="thread/source",
    )
    references = "<prior@example.com> <rfc-message@example.com>"
    authoritative = approved_gmail_message(
        spec=draft(reply=True),
        message_id="sent1",
        history="sent-history",
        thread="thread/source",
        in_reply_to="<rfc-message@example.com>",
        references=references,
    )
    transport = FakeTransport(
        response(source),
        response(write_receipt),
        response(authoritative),
    )
    provider = GoogleConnectedAppProvider(transport, now=lambda: NOW)
    receipt = await provider.reply_mail(
        account=account(ConnectorResource.MAIL), credential=credential(),
        request=MailReplyRequest.build(draft(reply=True)), operation_id=str(uuid4()), idempotency_key=KEY,
    )
    assert transport.calls[0].path.endswith("/m%2Fsource")
    assert transport.calls[1].json_body["threadId"] == "thread/source"
    message = decode_raw(transport.calls[1].json_body["raw"])
    assert message["In-Reply-To"] == "<rfc-message@example.com>"
    assert "<prior@example.com>" in message["References"]
    assert "<rfc-message@example.com>" in message["References"]
    assert transport.calls[2].path.endswith("/messages/sent1")
    assert receipt.outcome == "sent"


@pytest.mark.asyncio
@pytest.mark.parametrize("drift", ["thread", "history", "in_reply_to", "references"])
async def test_reply_authoritative_thread_headers_must_match_exact_approval(drift):
    source = gmail_message(
        message_id="m/source",
        history="source-history",
        thread="thread/source",
        references="<prior@example.com>",
    )
    authoritative = approved_gmail_message(
        spec=draft(reply=True),
        message_id="sent1",
        thread="thread/source",
        in_reply_to="<rfc-message@example.com>",
        references="<prior@example.com> <rfc-message@example.com>",
    )
    if drift == "thread":
        authoritative["threadId"] = "other/thread"
    elif drift == "history":
        authoritative["historyId"] = "other-history"
    elif drift == "in_reply_to":
        next(
            item
            for item in authoritative["payload"]["headers"]
            if item["name"] == "In-Reply-To"
        )["value"] = "<other@example.com>"
    elif drift == "references":
        next(
            item
            for item in authoritative["payload"]["headers"]
            if item["name"] == "References"
        )["value"] = "<other@example.com>"
    transport = FakeTransport(
        response(source),
        response(
            gmail_write_response(
                message_id="sent1",
                thread="thread/source",
                history="h1",
            )
        ),
        response(authoritative),
    )
    provider = GoogleConnectedAppProvider(transport, now=lambda: NOW)
    result = await provider.reply_mail(
        account=account(ConnectorResource.MAIL),
        credential=credential(),
        request=MailReplyRequest.build(draft(reply=True)),
        operation_id=str(uuid4()),
        idempotency_key=KEY,
    )
    assert result.code == "CONNECTED_PROVIDER_RESULT_AMBIGUOUS"
    assert len(transport.calls) == 3


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "source",
    [
        gmail_message(
            message_id="m/source",
            history="source-history",
            subject="Changed subject",
        ),
        gmail_message(
            message_id="m/source",
            history="source-history",
            rfc_message_id="invalid-message-id",
        ),
        gmail_message(
            message_id="m/source",
            history="source-history",
            references="not-a-message-id",
        ),
    ],
)
async def test_reply_fails_closed_before_send_on_subject_or_thread_header_drift(source):
    transport = FakeTransport(response(source))
    provider = GoogleConnectedAppProvider(transport)
    with pytest.raises(GoogleProviderError):
        await provider.reply_mail(
            account=account(ConnectorResource.MAIL),
            credential=credential(),
            request=MailReplyRequest.build(draft(reply=True)),
            operation_id=str(uuid4()),
            idempotency_key=KEY,
        )
    assert len(transport.calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("header_name", "duplicate_value"),
    [
        ("Subject", "Private subject"),
        ("Subject", "Conflicting subject"),
        ("Message-ID", "<rfc-message@example.com>"),
        ("Message-ID", "<other-message@example.com>"),
        ("References", "<prior@example.com>"),
        ("References", "<other@example.com>"),
        ("In-Reply-To", "<prior@example.com>"),
        ("In-Reply-To", "<other@example.com>"),
    ],
)
async def test_reply_rejects_duplicate_critical_headers_before_post(
    header_name,
    duplicate_value,
):
    source = gmail_message(
        message_id="m/source",
        history="source-history",
        references="<prior@example.com>" if header_name == "References" else None,
    )
    if header_name == "In-Reply-To":
        source["payload"]["headers"].append(
            {"name": "In-Reply-To", "value": "<prior@example.com>"}
        )
    source["payload"]["headers"].append(
        {"name": header_name, "value": duplicate_value}
    )
    transport = FakeTransport(response(source))
    provider = GoogleConnectedAppProvider(transport)

    with pytest.raises(GoogleProviderError) as captured:
        await provider.reply_mail(
            account=account(ConnectorResource.MAIL),
            credential=credential(),
            request=MailReplyRequest.build(draft(reply=True)),
            operation_id=str(uuid4()),
            idempotency_key=KEY,
        )

    assert captured.value.code == "GOOGLE_REPLY_HEADER_CARDINALITY_INVALID"
    assert [call.method for call in transport.calls] == ["GET"]


@pytest.mark.asyncio
async def test_reply_send_thread_mismatch_is_ambiguous():
    source = gmail_message(message_id="m/source", history="source-history", thread="thread/source")
    sent = gmail_message(message_id="sent", history="new", thread="wrong-thread")
    transport = FakeTransport(response(source), response(sent))
    provider = GoogleConnectedAppProvider(transport, now=lambda: NOW)
    result = await provider.reply_mail(
        account=account(ConnectorResource.MAIL),
        credential=credential(),
        request=MailReplyRequest.build(draft(reply=True)),
        operation_id=str(uuid4()),
        idempotency_key=KEY,
    )
    assert result.code == "CONNECTED_PROVIDER_RESULT_AMBIGUOUS"
    assert len(transport.calls) == 2


@pytest.mark.asyncio
async def test_reply_rejects_source_identity_substitution_before_send():
    source = gmail_message(
        message_id="wrong/source",
        history="source-history",
        thread="thread/source",
    )
    transport = FakeTransport(response(source))
    provider = GoogleConnectedAppProvider(transport)
    with pytest.raises(GoogleProviderError) as captured:
        await provider.reply_mail(
            account=account(ConnectorResource.MAIL),
            credential=credential(),
            request=MailReplyRequest.build(draft(reply=True)),
            operation_id=str(uuid4()),
            idempotency_key=KEY,
        )
    assert captured.value.code == "GOOGLE_RESPONSE_RESOURCE_MISMATCH"
    assert len(transport.calls) == 1


@pytest.mark.asyncio
async def test_calendar_list_and_get_encode_ids_and_preserve_etag():
    transport = FakeTransport(
        response({"items": [calendar_event()]}),
        response(calendar_event(event_id="event/one")),
    )
    provider = GoogleConnectedAppProvider(transport)
    listed = await provider.list_events(
        account=account(ConnectorResource.CALENDAR), credential=credential(),
        request=CalendarListRequest.build(calendar_query()),
    )
    fetched = await provider.get_event(
        account=account(ConnectorResource.CALENDAR), credential=credential(),
        request=CalendarGetRequest.build(calendar_id="primary/calendar", event_id="event/one", expected_resource_version='"etag1"'),
    )
    assert listed[0].resource_version == '"etag1"' and fetched.event_id == "event/one"
    assert transport.calls[0].path.startswith("/calendar/v3/calendars/primary%2Fcalendar/")
    assert transport.calls[1].path.endswith("/event%2Fone")


@pytest.mark.asyncio
async def test_calendar_get_rejects_response_identity_substitution():
    provider = GoogleConnectedAppProvider(
        FakeTransport(response(calendar_event(event_id="wrong")))
    )
    with pytest.raises(GoogleProviderError) as captured:
        await provider.get_event(
            account=account(ConnectorResource.CALENDAR),
            credential=credential(),
            request=CalendarGetRequest.build(
                calendar_id="primary/calendar",
                event_id="requested",
            ),
        )
    assert captured.value.code == "GOOGLE_RESPONSE_RESOURCE_MISMATCH"


@pytest.mark.asyncio
async def test_calendar_list_paginates_to_global_limit_and_rejects_token_loop():
    transport = FakeTransport(
        response({"items": [calendar_event(event_id="e1")], "nextPageToken": "next"}),
        response({"items": [calendar_event(event_id="e2")]}),
    )
    provider = GoogleConnectedAppProvider(transport)
    query = calendar_query()
    query = type(query)(
        calendar_ids=query.calendar_ids,
        starts_at=query.starts_at,
        ends_at=query.ends_at,
        time_zone=query.time_zone,
        limit=2,
    )
    events = await provider.list_events(
        account=account(ConnectorResource.CALENDAR),
        credential=credential(),
        request=CalendarListRequest.build(query),
    )
    assert [event.event_id for event in events] == ["e1", "e2"]
    assert ("pageToken", "next") in transport.calls[1].query
    assert ("maxResults", "1") in transport.calls[1].query

    loop = FakeTransport(
        response({"items": [], "nextPageToken": "same"}),
        response({"items": [], "nextPageToken": "same"}),
    )
    provider = GoogleConnectedAppProvider(loop)
    with pytest.raises(GoogleProviderError, match="GOOGLE_PAGINATION_INVALID"):
        await provider.list_events(
            account=account(ConnectorResource.CALENDAR),
            credential=credential(),
            request=CalendarListRequest.build(query),
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("position", ["ends_at_start", "starts_at_end", "after"])
async def test_calendar_list_rejects_events_outside_approved_half_open_window(position):
    item = calendar_event()
    if position == "ends_at_start":
        item["start"]["dateTime"] = "2026-11-07T19:00:00Z"
        item["end"]["dateTime"] = "2026-11-07T20:00:00Z"
    elif position == "starts_at_end":
        item["start"]["dateTime"] = "2026-11-08T20:00:00Z"
        item["end"]["dateTime"] = "2026-11-08T21:00:00Z"
    else:
        item["start"]["dateTime"] = "2026-11-09T20:00:00Z"
        item["end"]["dateTime"] = "2026-11-09T21:00:00Z"
    provider = GoogleConnectedAppProvider(
        FakeTransport(response({"items": [item]}))
    )
    with pytest.raises(GoogleProviderError) as captured:
        await provider.list_events(
            account=account(ConnectorResource.CALENDAR),
            credential=credential(),
            request=CalendarListRequest.build(calendar_query()),
        )
    assert captured.value.code == "GOOGLE_RESPONSE_OUT_OF_BOUNDS"


@pytest.mark.asyncio
async def test_calendar_list_accepts_events_touching_inside_query_boundaries():
    item = calendar_event()
    item["start"]["dateTime"] = "2026-11-07T20:00:00Z"
    item["end"]["dateTime"] = "2026-11-08T20:00:00Z"
    provider = GoogleConnectedAppProvider(
        FakeTransport(response({"items": [item]}))
    )
    result = await provider.list_events(
        account=account(ConnectorResource.CALENDAR),
        credential=credential(),
        request=CalendarListRequest.build(calendar_query()),
    )
    assert [event.event_id for event in result] == ["event1"]


@pytest.mark.asyncio
async def test_freebusy_uses_exact_calendars_and_returns_bounded_windows():
    body = freebusy_response(
        calendars={
            "primary/calendar": {
                "busy": [
                    {
                        "start": "2026-11-07T21:00:00Z",
                        "end": "2026-11-07T22:00:00Z",
                    }
                ]
            }
        }
    )
    transport = FakeTransport(response(body))
    provider = GoogleConnectedAppProvider(transport)
    windows = await provider.free_busy(
        account=account(ConnectorResource.CALENDAR), credential=credential(),
        request=CalendarFreeBusyRequest.build(calendar_query()),
    )
    assert len(windows) == 1
    assert transport.calls[0].host == CALENDAR_HOST
    assert transport.calls[0].json_body["items"] == [{"id": "primary/calendar"}]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("body", "expected", "retryable"),
    [
        (freebusy_response(), "GOOGLE_FREEBUSY_INCOMPLETE", False),
        (
            freebusy_response(
                calendars={
                    "primary/calendar": {"errors": [{"reason": "notFound"}]}
                }
            ),
            "GOOGLE_FREEBUSY_REJECTED",
            False,
        ),
        (
            freebusy_response(
                calendars={
                    "primary/calendar": {
                        "errors": [{"reason": "internalError"}]
                    }
                }
            ),
            "GOOGLE_PROVIDER_UNAVAILABLE",
            True,
        ),
    ],
)
async def test_freebusy_requires_every_calendar_and_error_free_results(body, expected, retryable):
    provider = GoogleConnectedAppProvider(FakeTransport(response(body)))
    with pytest.raises(GoogleProviderError) as captured:
        await provider.free_busy(
            account=account(ConnectorResource.CALENDAR),
            credential=credential(),
            request=CalendarFreeBusyRequest.build(calendar_query()),
        )
    assert captured.value.code == expected
    assert captured.value.retryable is retryable


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body",
    [
        {
            "timeMax": "2026-11-08T20:00:00Z",
            "calendars": {"primary/calendar": {"busy": []}},
        },
        freebusy_response(
            time_min="2026-11-07T20:00:01Z",
            calendars={"primary/calendar": {"busy": []}},
        ),
        freebusy_response(
            calendars={
                "primary/calendar": {
                    "busy": [
                        {
                            "start": "2026-11-07T19:59:59Z",
                            "end": "2026-11-07T21:00:00Z",
                        }
                    ]
                }
            }
        ),
        freebusy_response(
            calendars={
                "primary/calendar": {
                    "busy": [
                        {
                            "start": "2026-11-07T21:00:00Z",
                            "end": "2026-11-07T21:00:00Z",
                        }
                    ]
                }
            }
        ),
    ],
)
async def test_freebusy_rejects_missing_drifted_or_out_of_bounds_windows(body):
    provider = GoogleConnectedAppProvider(FakeTransport(response(body)))
    with pytest.raises(GoogleProviderError) as captured:
        await provider.free_busy(
            account=account(ConnectorResource.CALENDAR),
            credential=credential(),
            request=CalendarFreeBusyRequest.build(calendar_query()),
        )
    assert captured.value.code in {
        "GOOGLE_RESPONSE_MALFORMED",
        "GOOGLE_RESPONSE_OUT_OF_BOUNDS",
    }


@pytest.mark.asyncio
async def test_freebusy_accepts_utc_equivalent_bounds_and_contained_boundary_window():
    body = freebusy_response(
        time_min="2026-11-07T15:00:00-05:00",
        time_max="2026-11-08T15:00:00-05:00",
        calendars={
            "primary/calendar": {
                "busy": [
                    {
                        "start": "2026-11-07T20:00:00Z",
                        "end": "2026-11-08T20:00:00Z",
                    }
                ]
            }
        },
    )
    provider = GoogleConnectedAppProvider(FakeTransport(response(body)))
    result = await provider.free_busy(
        account=account(ConnectorResource.CALENDAR),
        credential=credential(),
        request=CalendarFreeBusyRequest.build(calendar_query()),
    )
    assert len(result) == 1
    assert result[0].starts_at.astimezone(timezone.utc) == NOW
    assert result[0].ends_at.astimezone(timezone.utc) == NOW + timedelta(days=1)


@pytest.mark.asyncio
async def test_calendar_create_uses_deterministic_google_event_id():
    operation = str(uuid4())
    expected = "ac" + hashlib.sha256((operation + KEY).encode()).hexdigest()[:30]
    transport = FakeTransport(response(approved_calendar_event(event_id=expected, etag='"new"')))
    provider = GoogleConnectedAppProvider(transport, now=lambda: NOW)
    receipt = await provider.create_event(
        account=account(ConnectorResource.CALENDAR), credential=credential(),
        request=CalendarCreateRequest.build(event_spec()), operation_id=operation, idempotency_key=KEY,
    )
    assert transport.calls[0].json_body["id"] == expected
    assert receipt.outcome == "created" and receipt.resource_version == '"new"'


@pytest.mark.asyncio
async def test_calendar_create_reconciles_deterministic_id_once_without_repost():
    operation = str(uuid4())
    expected = "ac" + hashlib.sha256((operation + KEY).encode()).hexdigest()[:30]
    transport = FakeTransport(
        TimeoutError("private lost create response"),
        response(approved_calendar_event(event_id=expected, etag='"found"')),
    )
    provider = GoogleConnectedAppProvider(transport, now=lambda: NOW)
    result = await provider.create_event(
        account=account(ConnectorResource.CALENDAR),
        credential=credential(),
        request=CalendarCreateRequest.build(event_spec()),
        operation_id=operation,
        idempotency_key=KEY,
    )
    assert result.outcome == "created"
    assert [call.method for call in transport.calls] == ["POST", "GET"]
    assert transport.calls[1].path.endswith(f"/{expected}")


@pytest.mark.asyncio
async def test_calendar_create_mismatched_response_id_uses_read_reconciliation():
    operation = str(uuid4())
    expected = "ac" + hashlib.sha256((operation + KEY).encode()).hexdigest()[:30]
    transport = FakeTransport(
        response(calendar_event(event_id="wrong", etag='"wrong"')),
        response(approved_calendar_event(event_id=expected, etag='"found"')),
    )
    provider = GoogleConnectedAppProvider(transport, now=lambda: NOW)
    result = await provider.create_event(
        account=account(ConnectorResource.CALENDAR),
        credential=credential(),
        request=CalendarCreateRequest.build(event_spec()),
        operation_id=operation,
        idempotency_key=KEY,
    )
    assert result.outcome == "created"
    assert [call.method for call in transport.calls] == ["POST", "GET"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "drift",
    ["title", "description", "location", "start", "timezone", "attendees", "status"],
)
async def test_calendar_create_requires_exact_approved_event_equivalence(drift):
    operation = str(uuid4())
    expected = "ac" + hashlib.sha256((operation + KEY).encode()).hexdigest()[:30]
    event = approved_calendar_event(event_id=expected, etag='"drift"')
    if drift == "title":
        event["summary"] = "Other title"
    elif drift == "description":
        event["description"] = "Other description"
    elif drift == "location":
        event["location"] = "Other location"
    elif drift == "start":
        event["start"]["dateTime"] = "2026-11-09T11:00:00-05:00"
    elif drift == "timezone":
        event["start"]["timeZone"] = "UTC"
        event["end"]["timeZone"] = "UTC"
    elif drift == "attendees":
        event["attendees"] = [{"email": "other@example.com"}]
    elif drift == "status":
        event["status"] = "tentative"
    transport = FakeTransport(response(event), response(deepcopy(event)))
    provider = GoogleConnectedAppProvider(transport, now=lambda: NOW)
    result = await provider.create_event(
        account=account(ConnectorResource.CALENDAR),
        credential=credential(),
        request=CalendarCreateRequest.build(event_spec()),
        operation_id=operation,
        idempotency_key=KEY,
    )
    assert result.code == "CONNECTED_PROVIDER_RESULT_AMBIGUOUS"
    assert [call.method for call in transport.calls] == ["POST", "GET"]


@pytest.mark.asyncio
async def test_calendar_update_uses_patch_and_if_match():
    current = calendar_event(event_id="event/source", etag='"old-etag"')
    current["attendees"] = [
        {"email": "guest@example.com", "responseStatus": "accepted", "comment": "keep"}
    ]
    current["recurrence"] = ["RRULE:FREQ=WEEKLY"]
    transport = FakeTransport(
        response(current),
        response(
            approved_calendar_event(
                spec=event_spec(update=True),
                event_id="event/source",
                etag='"new-etag"',
            )
        ),
    )
    provider = GoogleConnectedAppProvider(transport, now=lambda: NOW)
    receipt = await provider.update_event(
        account=account(ConnectorResource.CALENDAR), credential=credential(),
        request=CalendarUpdateRequest.build(event_spec(update=True)), operation_id=str(uuid4()), idempotency_key=KEY,
    )
    call = transport.calls[1]
    assert call.method == "PATCH"
    assert ("If-Match", '"old-etag"') in call.headers
    assert call.path.endswith("/event%2Fsource")
    assert call.json_body["attendees"] == current["attendees"]
    assert "recurrence" not in call.json_body
    assert ("sendUpdates", "all") in call.query
    assert receipt.outcome == "updated"


@pytest.mark.asyncio
async def test_calendar_update_notifies_when_every_attendee_is_removed():
    current = calendar_event(event_id="event/source", etag='"old-etag"')
    current["attendees"] = [
        {"email": "guest@example.com", "responseStatus": "accepted", "optional": True}
    ]
    transport = FakeTransport(
        response(current),
        response(
            approved_calendar_event(
                spec=event_spec(update=True, attendees=()),
                event_id="event/source",
                etag='"new"',
            )
        ),
    )
    provider = GoogleConnectedAppProvider(transport, now=lambda: NOW)
    result = await provider.update_event(
        account=account(ConnectorResource.CALENDAR),
        credential=credential(),
        request=CalendarUpdateRequest.build(event_spec(update=True, attendees=())),
        operation_id=str(uuid4()),
        idempotency_key=KEY,
    )
    assert result.outcome == "updated"
    assert transport.calls[1].json_body["attendees"] == []
    assert ("sendUpdates", "all") in transport.calls[1].query


@pytest.mark.asyncio
async def test_calendar_update_suppresses_notifications_only_when_no_attendees_exist():
    current = calendar_event(event_id="event/source", etag='"old-etag"')
    current["attendees"] = []
    spec = event_spec(update=True, attendees=())
    transport = FakeTransport(
        response(current),
        response(approved_calendar_event(spec=spec, event_id="event/source", etag='"new"')),
    )
    provider = GoogleConnectedAppProvider(transport, now=lambda: NOW)
    result = await provider.update_event(
        account=account(ConnectorResource.CALENDAR),
        credential=credential(),
        request=CalendarUpdateRequest.build(spec),
        operation_id=str(uuid4()),
        idempotency_key=KEY,
    )
    assert result.outcome == "updated"
    assert ("sendUpdates", "none") in transport.calls[1].query


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("flag", "expected"),
    [
        (True, "GOOGLE_RESPONSE_ATTENDEES_INCOMPLETE"),
        ("true", "GOOGLE_RESPONSE_MALFORMED"),
        (1, "GOOGLE_RESPONSE_MALFORMED"),
    ],
)
async def test_calendar_update_rejects_omitted_or_malformed_attendee_snapshot(flag, expected):
    current = calendar_event(event_id="event/source", etag='"old-etag"')
    current["attendeesOmitted"] = flag
    transport = FakeTransport(response(current))
    provider = GoogleConnectedAppProvider(transport)
    with pytest.raises(GoogleProviderError) as captured:
        await provider.update_event(
            account=account(ConnectorResource.CALENDAR),
            credential=credential(),
            request=CalendarUpdateRequest.build(event_spec(update=True)),
            operation_id=str(uuid4()),
            idempotency_key=KEY,
        )
    assert captured.value.code == expected
    assert len(transport.calls) == 1


@pytest.mark.asyncio
async def test_calendar_update_stale_precondition_fails_before_patch():
    transport = FakeTransport(
        response(calendar_event(event_id="event/source", etag='"different"')),
    )
    provider = GoogleConnectedAppProvider(transport)
    with pytest.raises(GoogleProviderError, match="GOOGLE_RESOURCE_VERSION_CONFLICT"):
        await provider.update_event(
            account=account(ConnectorResource.CALENDAR),
            credential=credential(),
            request=CalendarUpdateRequest.build(event_spec(update=True)),
            operation_id=str(uuid4()),
            idempotency_key=KEY,
        )
    assert len(transport.calls) == 1


@pytest.mark.asyncio
async def test_calendar_update_response_id_mismatch_is_ambiguous():
    transport = FakeTransport(
        response(calendar_event(event_id="event/source", etag='"old-etag"')),
        response(
            approved_calendar_event(
                spec=event_spec(update=True),
                event_id="wrong",
                etag='"new"',
            )
        ),
    )
    provider = GoogleConnectedAppProvider(transport, now=lambda: NOW)
    result = await provider.update_event(
        account=account(ConnectorResource.CALENDAR),
        credential=credential(),
        request=CalendarUpdateRequest.build(event_spec(update=True)),
        operation_id=str(uuid4()),
        idempotency_key=KEY,
    )
    assert result.code == "CONNECTED_PROVIDER_RESULT_AMBIGUOUS"


@pytest.mark.asyncio
async def test_calendar_update_response_approved_field_drift_is_ambiguous():
    current = calendar_event(event_id="event/source", etag='"old-etag"')
    changed = approved_calendar_event(
        spec=event_spec(update=True),
        event_id="event/source",
        etag='"new"',
    )
    changed["description"] = "Provider drift"
    transport = FakeTransport(response(current), response(changed))
    provider = GoogleConnectedAppProvider(transport, now=lambda: NOW)
    result = await provider.update_event(
        account=account(ConnectorResource.CALENDAR),
        credential=credential(),
        request=CalendarUpdateRequest.build(event_spec(update=True)),
        operation_id=str(uuid4()),
        idempotency_key=KEY,
    )
    assert result.code == "CONNECTED_PROVIDER_RESULT_AMBIGUOUS"


@pytest.mark.asyncio
async def test_calendar_cancel_uses_delete_if_match_and_content_free_receipt():
    transport = FakeTransport(response(None, status=204))
    provider = GoogleConnectedAppProvider(transport, now=lambda: NOW)
    receipt = await provider.cancel_event(
        account=account(ConnectorResource.CALENDAR), credential=credential(),
        request=CalendarCancelRequest.build(calendar_id="primary/calendar", event_id="event/one", expected_resource_version='"etag"'),
        operation_id=str(uuid4()), idempotency_key=KEY,
    )
    call = transport.calls[0]
    assert call.method == "DELETE" and ("If-Match", '"etag"') in call.headers
    assert receipt.outcome == "cancelled"


@pytest.mark.asyncio
async def test_calendar_cancel_reconciles_absence_once_without_redelete():
    transport = FakeTransport(
        ConnectionResetError("private lost delete response"),
        response({"error": "not found"}, status=404),
    )
    provider = GoogleConnectedAppProvider(transport, now=lambda: NOW)
    result = await provider.cancel_event(
        account=account(ConnectorResource.CALENDAR),
        credential=credential(),
        request=CalendarCancelRequest.build(
            calendar_id="primary/calendar",
            event_id="event/one",
            expected_resource_version='"etag"',
        ),
        operation_id=str(uuid4()),
        idempotency_key=KEY,
    )
    assert result.outcome == "cancelled"
    assert [call.method for call in transport.calls] == ["DELETE", "GET"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "delete_response",
    [
        response({"id": "unrelated", "etag": '"other"'}, status=200),
        response({"unexpected": "body"}, status=204),
    ],
)
async def test_calendar_cancel_noncanonical_success_requires_absence_proof(delete_response):
    transport = FakeTransport(
        delete_response,
        response(calendar_event(event_id="event/one", etag='"still-here"')),
    )
    provider = GoogleConnectedAppProvider(transport, now=lambda: NOW)
    result = await provider.cancel_event(
        account=account(ConnectorResource.CALENDAR),
        credential=credential(),
        request=CalendarCancelRequest.build(
            calendar_id="primary/calendar",
            event_id="event/one",
            expected_resource_version='"etag"',
        ),
        operation_id=str(uuid4()),
        idempotency_key=KEY,
    )
    assert result.code == "CONNECTED_PROVIDER_RESULT_AMBIGUOUS"
    assert [call.method for call in transport.calls] == ["DELETE", "GET"]


@pytest.mark.asyncio
async def test_definite_errors_are_categorical_and_do_not_echo_provider_content():
    transport = FakeTransport(response({"error": {"message": "Private provider diagnostic"}}, status=400))
    provider = GoogleConnectedAppProvider(transport)
    with pytest.raises(GoogleProviderError) as captured:
        await provider.get_message(
            account=account(ConnectorResource.MAIL), credential=credential(),
            request=MailGetRequest.build(message_id="m1"),
        )
    assert captured.value.code == "GOOGLE_REQUEST_REJECTED"
    assert "Private provider diagnostic" not in repr(captured.value)


@pytest.mark.asyncio
async def test_malformed_untrusted_content_is_quarantined_behind_categorical_error():
    item = gmail_message()
    item["payload"]["headers"][2]["value"] = "not a valid mailbox\nprivate-value"
    provider = GoogleConnectedAppProvider(FakeTransport(response(item)))
    with pytest.raises(GoogleProviderError) as captured:
        await provider.get_message(
            account=account(ConnectorResource.MAIL), credential=credential(),
            request=MailGetRequest.build(message_id="m1"),
        )
    assert captured.value.code == "GOOGLE_RESPONSE_MALFORMED"
    assert "private-value" not in repr(captured.value)


@pytest.mark.asyncio
async def test_wrong_resource_and_credential_binding_fail_before_transport():
    transport = FakeTransport(response({}))
    provider = GoogleConnectedAppProvider(transport)
    with pytest.raises(GoogleProviderError, match="GOOGLE_ACCOUNT_RESOURCE_MISMATCH"):
        await provider.get_message(
            account=account(ConnectorResource.CALENDAR), credential=credential(),
            request=MailGetRequest.build(message_id="m1"),
        )
    assert not transport.calls
