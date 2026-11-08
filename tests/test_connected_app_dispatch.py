from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
from uuid import uuid4

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
    EventSnapshot,
    EventSpec,
    FreeBusyWindow,
    MailDraftRequest,
    MailDraftSpec,
    MailGetRequest,
    MailQuery,
    MailReplyRequest,
    MailSearchRequest,
    MailSendRequest,
    MessageSnapshot,
    MessageSummary,
    ProviderReceipt,
)
from backend.connected_app_dispatch import (
    ConnectedDispatchError,
    ConnectedLeaseConsumption,
    DirectConnectedProviderResolver,
)
from backend.connected_app_policy import (
    ConnectorActionKind,
    ConnectorProvider,
    ConnectorResource,
)
from backend.connected_app_runtime import ConnectedCredentialLease, ConnectedCredentialPhase


NOW = datetime(2026, 11, 7, 20, 0, tzinfo=timezone.utc)
OWNER = "11111111-1111-4111-8111-111111111111"
CONNECTION = "22222222-2222-4222-8222-222222222222"
CLAIM = "33333333-3333-4333-8333-333333333333"
OPERATION = "44444444-4444-4444-8444-444444444444"
USE = "55555555-5555-4555-8555-555555555555"
SHA = hashlib.sha256(b"binding").hexdigest()


def account(provider: ConnectorProvider, resource: ConnectorResource) -> ConnectedAccountRef:
    return ConnectedAccountRef(
        OWNER,
        CONNECTION,
        provider,
        resource,
        ConnectorAccountKind.PERSONAL,
        SHA,
    )


def lease(
    provider: ConnectorProvider,
    resource: ConnectorResource,
    phase: ConnectedCredentialPhase,
) -> ConnectedCredentialLease:
    return ConnectedCredentialLease(
        credential=CredentialHandleRef(
            OWNER,
            CONNECTION,
            provider,
            "broker-handle-ref-0001",
        ),
        owner_id=OWNER,
        connection_id=CONNECTION,
        provider=provider,
        resource=resource,
        authorization_revision=1,
        authorization_snapshot_sha256=SHA,
        granted_actions_sha256=SHA,
        granted_scopes_sha256=SHA,
        authority_sha256=SHA,
        task_state_revision=1,
        claim_id=CLAIM,
        fencing_token=7,
        phase=phase,
        use_nonce=USE,
        issued_at=NOW - timedelta(seconds=1),
        expires_at=NOW + timedelta(seconds=30),
    )


class FakeLeaseConsumer:
    def __init__(self) -> None:
        self.calls: list[tuple[ConnectedCredentialPhase, ConnectorActionKind]] = []
        self.override: ConnectedLeaseConsumption | None = None

    async def consume_once(self, *, lease, operation_id, action):
        self.calls.append((lease.phase, action))
        return self.override or ConnectedLeaseConsumption(
            operation_id=operation_id,
            owner_id=lease.owner_id,
            connection_id=lease.connection_id,
            claim_id=lease.claim_id,
            fencing_token=lease.fencing_token,
            provider=lease.provider,
            resource=lease.resource,
            action=action,
            phase=lease.phase,
            use_nonce=lease.use_nonce,
            consumed_at=NOW,
        )


class FakeProvider:
    def __init__(self, provider: ConnectorProvider) -> None:
        self.provider = provider
        self.calls: list[str] = []
        self.not_found = False
        self.return_ambiguous = False

    async def search_mail(self, **_):
        self.calls.append("search_mail")
        return (
            MessageSummary(
                "message-1",
                resource_version="v1",
                received_at=NOW,
                sender="sender@example.com",
            ),
        )

    async def get_message(self, **_):
        self.calls.append("get_message")
        return MessageSnapshot(
            "message-1",
            resource_version="v1",
            received_at=NOW,
            sender="sender@example.com",
        )

    async def create_draft(self, **kwargs):
        return self._write("create_draft", "drafted", kwargs)

    async def send_mail(self, **kwargs):
        return self._write("send_mail", "sent", kwargs)

    async def reply_mail(self, **kwargs):
        return self._write("reply_mail", "sent", kwargs)

    async def list_events(self, **_):
        self.calls.append("list_events")
        return (self._event(),)

    async def free_busy(self, **_):
        self.calls.append("free_busy")
        return (FreeBusyWindow("calendar-1", NOW, NOW + timedelta(hours=1)),)

    async def get_event(self, **_):
        self.calls.append("get_event")
        if self.not_found:
            error = RuntimeError("not found")
            error.code = (
                "GOOGLE_RESOURCE_NOT_FOUND"
                if self.provider is ConnectorProvider.GOOGLE
                else "MICROSOFT_RESOURCE_NOT_FOUND"
            )
            raise error
        return self._event()

    async def create_event(self, **kwargs):
        return self._write("create_event", "created", kwargs)

    async def update_event(self, **kwargs):
        return self._write("update_event", "updated", kwargs)

    async def cancel_event(self, **kwargs):
        return self._write("cancel_event", "cancelled", kwargs)

    def _event(self):
        return EventSnapshot(
            "event-1",
            "calendar-1",
            "v1",
            NOW + timedelta(hours=1),
            NOW + timedelta(hours=2),
            "UTC",
            "untrusted event",
        )

    def _write(self, name, outcome, kwargs):
        self.calls.append(name)
        if self.return_ambiguous:
            return AmbiguousProviderResult(
                kwargs["operation_id"],
                self.provider,
                kwargs["account"].resource,
                hashlib.sha256(kwargs["idempotency_key"].encode()).hexdigest(),
                NOW,
            )
        return ProviderReceipt(
            kwargs["operation_id"],
            self.provider,
            kwargs["account"].resource,
            outcome,
            SHA,
            SHA,
            "v2",
            hashlib.sha256(kwargs["idempotency_key"].encode()).hexdigest(),
            NOW,
        )


def mail_spec(*, reply: bool = False) -> MailDraftSpec:
    return MailDraftSpec(
        ("recipient@example.com",),
        "subject",
        "body",
        reply_to_message_id="message-1" if reply else None,
        expected_resource_version="v1" if reply else None,
    )


def event_spec(*, update: bool = False) -> EventSpec:
    return EventSpec(
        "calendar-1",
        "title",
        NOW + timedelta(hours=1),
        NOW + timedelta(hours=2),
        "UTC",
        source_event_id="event-1" if update else None,
        expected_resource_version="v1" if update else None,
    )


def request(action: ConnectorActionKind):
    query = CalendarQuery(("calendar-1",), NOW, NOW + timedelta(hours=3), "UTC")
    return {
        ConnectorActionKind.MAIL_SEARCH: MailSearchRequest.build(MailQuery("query")),
        ConnectorActionKind.MAIL_GET: MailGetRequest.build(message_id="message-1"),
        ConnectorActionKind.MAIL_CREATE_DRAFT: MailDraftRequest.build(mail_spec()),
        ConnectorActionKind.MAIL_SEND: MailSendRequest.build(mail_spec()),
        ConnectorActionKind.MAIL_REPLY: MailReplyRequest.build(mail_spec(reply=True)),
        ConnectorActionKind.CALENDAR_LIST: CalendarListRequest.build(query),
        ConnectorActionKind.CALENDAR_FREE_BUSY: CalendarFreeBusyRequest.build(query),
        ConnectorActionKind.CALENDAR_GET: CalendarGetRequest.build(
            calendar_id="calendar-1", event_id="event-1"
        ),
        ConnectorActionKind.CALENDAR_CREATE: CalendarCreateRequest.build(event_spec()),
        ConnectorActionKind.CALENDAR_UPDATE: CalendarUpdateRequest.build(event_spec(update=True)),
        ConnectorActionKind.CALENDAR_CANCEL: CalendarCancelRequest.build(
            calendar_id="calendar-1", event_id="event-1", expected_resource_version="v1"
        ),
    }[action]


def resource(action: ConnectorActionKind) -> ConnectorResource:
    return (
        ConnectorResource.MAIL if action.value.startswith("mail.") else ConnectorResource.CALENDAR
    )


def resolver(provider: ConnectorProvider = ConnectorProvider.GOOGLE):
    leases = FakeLeaseConsumer()
    google = FakeProvider(ConnectorProvider.GOOGLE)
    microsoft = FakeProvider(ConnectorProvider.MICROSOFT)
    value = DirectConnectedProviderResolver(
        google=google,
        microsoft=microsoft,
        leases=leases,
        now=lambda: NOW,
    )
    adapter = google if provider is ConnectorProvider.GOOGLE else microsoft
    return value, leases, adapter


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "action,call",
    [
        (ConnectorActionKind.MAIL_SEARCH, "search_mail"),
        (ConnectorActionKind.MAIL_GET, "get_message"),
        (ConnectorActionKind.CALENDAR_LIST, "list_events"),
        (ConnectorActionKind.CALENDAR_FREE_BUSY, "free_busy"),
        (ConnectorActionKind.CALENDAR_GET, "get_event"),
    ],
)
async def test_read_dispatch_is_exhaustive_and_consumes_exact_lease(action, call):
    value, leases, adapter = resolver()
    dispatcher = value.resolve_read(
        provider=ConnectorProvider.GOOGLE,
        resource=resource(action),
        action=action,
    )
    result = await dispatcher.execute_read(
        account=account(ConnectorProvider.GOOGLE, resource(action)),
        credential=lease(ConnectorProvider.GOOGLE, resource(action), ConnectedCredentialPhase.READ),
        request=request(action),
        operation_id=OPERATION,
    )
    assert result.operation_id == OPERATION
    assert result.provider is ConnectorProvider.GOOGLE
    assert adapter.calls == [call]
    assert leases.calls == [(ConnectedCredentialPhase.READ, action)]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "action,call",
    [
        (ConnectorActionKind.MAIL_CREATE_DRAFT, "create_draft"),
        (ConnectorActionKind.MAIL_SEND, "send_mail"),
        (ConnectorActionKind.MAIL_REPLY, "reply_mail"),
        (ConnectorActionKind.CALENDAR_CREATE, "create_event"),
        (ConnectorActionKind.CALENDAR_UPDATE, "update_event"),
        (ConnectorActionKind.CALENDAR_CANCEL, "cancel_event"),
    ],
)
async def test_write_dispatch_is_exhaustive_and_never_reuses_lease(action, call):
    value, leases, adapter = resolver(ConnectorProvider.MICROSOFT)
    dispatcher = value.resolve_write(
        provider=ConnectorProvider.MICROSOFT,
        resource=resource(action),
        action=action,
    )
    result = await dispatcher.execute_write(
        account=account(ConnectorProvider.MICROSOFT, resource(action)),
        credential=lease(
            ConnectorProvider.MICROSOFT, resource(action), ConnectedCredentialPhase.EFFECT
        ),
        request=request(action),
        operation_id=OPERATION,
        idempotency_key="idempotency-key-0001",
    )
    assert type(result) is ProviderReceipt
    assert adapter.calls == [call]
    assert leases.calls == [(ConnectedCredentialPhase.EFFECT, action)]


@pytest.mark.asyncio
async def test_malformed_consumption_receipt_blocks_provider_call():
    value, leases, adapter = resolver()
    dispatcher = value.resolve_read(
        provider=ConnectorProvider.GOOGLE,
        resource=ConnectorResource.MAIL,
        action=ConnectorActionKind.MAIL_SEARCH,
    )
    valid = ConnectedLeaseConsumption(
        OPERATION,
        OWNER,
        CONNECTION,
        CLAIM,
        7,
        ConnectorProvider.GOOGLE,
        ConnectorResource.MAIL,
        ConnectorActionKind.MAIL_SEARCH,
        ConnectedCredentialPhase.READ,
        USE,
        NOW,
    )
    leases.override = replace(valid, operation_id=str(uuid4()))
    with pytest.raises(ConnectedDispatchError, match="CONNECTED_DISPATCH_LEASE_RECEIPT_MISMATCH"):
        await dispatcher.execute_read(
            account=account(ConnectorProvider.GOOGLE, ConnectorResource.MAIL),
            credential=lease(
                ConnectorProvider.GOOGLE,
                ConnectorResource.MAIL,
                ConnectedCredentialPhase.READ,
            ),
            request=request(ConnectorActionKind.MAIL_SEARCH),
            operation_id=OPERATION,
        )
    assert adapter.calls == []


@pytest.mark.asyncio
async def test_provider_exception_after_effect_consumption_is_effect_unknown():
    class BrokenProvider(FakeProvider):
        async def send_mail(self, **_):
            self.calls.append("send_mail")
            raise TimeoutError

    leases = FakeLeaseConsumer()
    broken = BrokenProvider(ConnectorProvider.GOOGLE)
    value = DirectConnectedProviderResolver(
        google=broken,
        microsoft=FakeProvider(ConnectorProvider.MICROSOFT),
        leases=leases,
        now=lambda: NOW,
    )
    dispatcher = value.resolve_write(
        provider=ConnectorProvider.GOOGLE,
        resource=ConnectorResource.MAIL,
        action=ConnectorActionKind.MAIL_SEND,
    )
    with pytest.raises(ConnectedDispatchError, match="CONNECTED_PROVIDER_EFFECT_UNKNOWN"):
        await dispatcher.execute_write(
            account=account(ConnectorProvider.GOOGLE, ConnectorResource.MAIL),
            credential=lease(
                ConnectorProvider.GOOGLE,
                ConnectorResource.MAIL,
                ConnectedCredentialPhase.EFFECT,
            ),
            request=request(ConnectorActionKind.MAIL_SEND),
            operation_id=OPERATION,
            idempotency_key="idempotency-key-0001",
        )
    assert leases.calls == [(ConnectedCredentialPhase.EFFECT, ConnectorActionKind.MAIL_SEND)]
    assert broken.calls == ["send_mail"]


@pytest.mark.asyncio
async def test_cancel_postobserve_requires_authoritative_absence():
    value, leases, adapter = resolver()
    adapter.not_found = True
    dispatcher = value.resolve_write(
        provider=ConnectorProvider.GOOGLE,
        resource=ConnectorResource.CALENDAR,
        action=ConnectorActionKind.CALENDAR_CANCEL,
    )
    observed = await dispatcher.observe_resource_version(
        account=account(ConnectorProvider.GOOGLE, ConnectorResource.CALENDAR),
        credential=lease(
            ConnectorProvider.GOOGLE,
            ConnectorResource.CALENDAR,
            ConnectedCredentialPhase.POSTOBSERVE,
        ),
        request=request(ConnectorActionKind.CALENDAR_CANCEL),
        operation_id=OPERATION,
    )
    assert observed == "v1"
    assert adapter.calls == ["get_event"]
    assert leases.calls == [
        (ConnectedCredentialPhase.POSTOBSERVE, ConnectorActionKind.CALENDAR_CANCEL)
    ]


def test_resolver_rejects_action_resource_and_read_write_substitution():
    value, _, _ = resolver()
    with pytest.raises(ConnectedDispatchError, match="CONNECTED_DISPATCH_NOT_IMPLEMENTED"):
        value.resolve_read(
            provider=ConnectorProvider.GOOGLE,
            resource=ConnectorResource.CALENDAR,
            action=ConnectorActionKind.MAIL_GET,
        )
    with pytest.raises(ConnectedDispatchError, match="CONNECTED_DISPATCH_NOT_IMPLEMENTED"):
        value.resolve_read(
            provider=ConnectorProvider.GOOGLE,
            resource=ConnectorResource.MAIL,
            action=ConnectorActionKind.MAIL_SEND,
        )


def test_secrets_and_untrusted_content_are_not_in_reprs():
    record = ConnectedLeaseConsumption(
        OPERATION,
        OWNER,
        CONNECTION,
        CLAIM,
        7,
        ConnectorProvider.GOOGLE,
        ConnectorResource.MAIL,
        ConnectorActionKind.MAIL_SEND,
        ConnectedCredentialPhase.EFFECT,
        USE,
        NOW,
    )
    assert "broker" not in repr(record)
    assert OWNER not in repr(record)
