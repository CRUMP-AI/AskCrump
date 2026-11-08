"""Provider protocols for direct, owner-connected mail and calendar APIs.

Implementations receive only a broker handle, never a bearer or refresh token.
Writes return either a durable content-free receipt or an explicit ambiguous
result that must be reconciled before any retry.
"""
from __future__ import annotations

from typing import Protocol

from .connected_app_contracts import (
    AmbiguousProviderResult,
    CalendarCancelRequest,
    CalendarCreateRequest,
    CalendarFreeBusyRequest,
    CalendarGetRequest,
    CalendarListRequest,
    CalendarUpdateRequest,
    ConnectedAccountRef,
    CredentialHandleRef,
    EventSnapshot,
    FreeBusyWindow,
    MailDraftRequest,
    MailGetRequest,
    MailReplyRequest,
    MailSearchRequest,
    MailSendRequest,
    MessageSnapshot,
    MessageSummary,
    ProviderReceipt,
)


ProviderWriteResult = ProviderReceipt | AmbiguousProviderResult


class MailReadProvider(Protocol):
    async def search_mail(
        self,
        *,
        account: ConnectedAccountRef,
        credential: CredentialHandleRef,
        request: MailSearchRequest,
    ) -> tuple[MessageSummary, ...]: ...

    async def get_message(
        self,
        *,
        account: ConnectedAccountRef,
        credential: CredentialHandleRef,
        request: MailGetRequest,
    ) -> MessageSnapshot: ...


class MailWriteProvider(Protocol):
    async def create_draft(
        self,
        *,
        account: ConnectedAccountRef,
        credential: CredentialHandleRef,
        request: MailDraftRequest,
        operation_id: str,
        idempotency_key: str,
    ) -> ProviderWriteResult: ...

    async def send_mail(
        self,
        *,
        account: ConnectedAccountRef,
        credential: CredentialHandleRef,
        request: MailSendRequest,
        operation_id: str,
        idempotency_key: str,
    ) -> ProviderWriteResult: ...

    async def reply_mail(
        self,
        *,
        account: ConnectedAccountRef,
        credential: CredentialHandleRef,
        request: MailReplyRequest,
        operation_id: str,
        idempotency_key: str,
    ) -> ProviderWriteResult: ...


class CalendarReadProvider(Protocol):
    async def list_events(
        self,
        *,
        account: ConnectedAccountRef,
        credential: CredentialHandleRef,
        request: CalendarListRequest,
    ) -> tuple[EventSnapshot, ...]: ...

    async def free_busy(
        self,
        *,
        account: ConnectedAccountRef,
        credential: CredentialHandleRef,
        request: CalendarFreeBusyRequest,
    ) -> tuple[FreeBusyWindow, ...]: ...

    async def get_event(
        self,
        *,
        account: ConnectedAccountRef,
        credential: CredentialHandleRef,
        request: CalendarGetRequest,
    ) -> EventSnapshot: ...


class CalendarWriteProvider(Protocol):
    async def create_event(
        self,
        *,
        account: ConnectedAccountRef,
        credential: CredentialHandleRef,
        request: CalendarCreateRequest,
        operation_id: str,
        idempotency_key: str,
    ) -> ProviderWriteResult: ...

    async def update_event(
        self,
        *,
        account: ConnectedAccountRef,
        credential: CredentialHandleRef,
        request: CalendarUpdateRequest,
        operation_id: str,
        idempotency_key: str,
    ) -> ProviderWriteResult: ...

    async def cancel_event(
        self,
        *,
        account: ConnectedAccountRef,
        credential: CredentialHandleRef,
        request: CalendarCancelRequest,
        operation_id: str,
        idempotency_key: str,
    ) -> ProviderWriteResult: ...


class ConnectedAppProvider(
    MailReadProvider,
    MailWriteProvider,
    CalendarReadProvider,
    CalendarWriteProvider,
    Protocol,
):
    """Complete direct provider boundary; browser automation is not a fallback."""
