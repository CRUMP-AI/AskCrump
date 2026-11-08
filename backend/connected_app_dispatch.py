"""Fail-closed bridge from durable action leases to typed provider adapters.

The runtime deliberately cannot unwrap an OAuth credential.  This module is the
single boundary that consumes a database-owned, one-use phase lease immediately
before invoking a direct Google or Microsoft provider method.  Browser
automation is never a fallback.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Protocol
from uuid import UUID

from .connected_app_contracts import (
    AmbiguousProviderResult,
    CalendarCancelRequest,
    CalendarCreateRequest,
    CalendarFreeBusyRequest,
    CalendarGetRequest,
    CalendarListRequest,
    CalendarUpdateRequest,
    ConnectedAccountRef,
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
from .connected_app_policy import (
    ConnectorActionKind,
    ConnectorProvider,
    ConnectorResource,
    implemented_runtime_actions,
)
from .connected_app_provider import ConnectedAppProvider
from .connected_app_runtime import (
    ConnectedCredentialLease,
    ConnectedCredentialPhase,
    ConnectedReadObservation,
    ProviderRequest,
)


_FUTURE_SKEW = timedelta(seconds=5)
_READ_ACTIONS = frozenset(
    {
        ConnectorActionKind.MAIL_SEARCH,
        ConnectorActionKind.MAIL_GET,
        ConnectorActionKind.CALENDAR_LIST,
        ConnectorActionKind.CALENDAR_FREE_BUSY,
        ConnectorActionKind.CALENDAR_GET,
    }
)
_WRITE_ACTIONS = frozenset(
    {
        ConnectorActionKind.MAIL_CREATE_DRAFT,
        ConnectorActionKind.MAIL_SEND,
        ConnectorActionKind.MAIL_REPLY,
        ConnectorActionKind.CALENDAR_CREATE,
        ConnectorActionKind.CALENDAR_UPDATE,
        ConnectorActionKind.CALENDAR_CANCEL,
    }
)
_ACTION_RESOURCE = {
    ConnectorActionKind.MAIL_SEARCH: ConnectorResource.MAIL,
    ConnectorActionKind.MAIL_GET: ConnectorResource.MAIL,
    ConnectorActionKind.MAIL_CREATE_DRAFT: ConnectorResource.MAIL,
    ConnectorActionKind.MAIL_SEND: ConnectorResource.MAIL,
    ConnectorActionKind.MAIL_REPLY: ConnectorResource.MAIL,
    ConnectorActionKind.CALENDAR_LIST: ConnectorResource.CALENDAR,
    ConnectorActionKind.CALENDAR_FREE_BUSY: ConnectorResource.CALENDAR,
    ConnectorActionKind.CALENDAR_GET: ConnectorResource.CALENDAR,
    ConnectorActionKind.CALENDAR_CREATE: ConnectorResource.CALENDAR,
    ConnectorActionKind.CALENDAR_UPDATE: ConnectorResource.CALENDAR,
    ConnectorActionKind.CALENDAR_CANCEL: ConnectorResource.CALENDAR,
}
if (_READ_ACTIONS | _WRITE_ACTIONS) != implemented_runtime_actions() or set(
    _ACTION_RESOURCE
) != implemented_runtime_actions():
    raise RuntimeError("connected provider dispatch is not exhaustive")


def _uuid(value: str, name: str) -> str:
    try:
        canonical = str(UUID(value))
    except (TypeError, ValueError, AttributeError):
        raise ValueError(f"{name} must be a UUID") from None
    if canonical != value:
        raise ValueError(f"{name} must be canonical")
    return value


def _aware(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(timezone.utc)


class ConnectedDispatchError(RuntimeError):
    """Content-free provider dispatch failure."""

    def __init__(self, code: str, *, retryable: bool = False) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable


@dataclass(frozen=True, slots=True, repr=False)
class ConnectedLeaseConsumption:
    """Exact durable receipt for one phase-credential consumption."""

    operation_id: str
    owner_id: str
    connection_id: str
    claim_id: str
    fencing_token: int
    provider: ConnectorProvider
    resource: ConnectorResource
    action: ConnectorActionKind
    phase: ConnectedCredentialPhase
    use_nonce: str
    consumed_at: datetime

    def __post_init__(self) -> None:
        for name in ("operation_id", "owner_id", "connection_id", "claim_id", "use_nonce"):
            object.__setattr__(self, name, _uuid(getattr(self, name), name))
        if type(self.fencing_token) is not int or self.fencing_token < 1:
            raise ValueError("fencing_token is invalid")
        if not isinstance(self.provider, ConnectorProvider):
            raise ValueError("provider is invalid")
        if not isinstance(self.resource, ConnectorResource):
            raise ValueError("resource is invalid")
        if not isinstance(self.action, ConnectorActionKind):
            raise ValueError("action is invalid")
        if not isinstance(self.phase, ConnectedCredentialPhase):
            raise ValueError("phase is invalid")
        object.__setattr__(self, "consumed_at", _aware(self.consumed_at, "consumed_at"))

    def __repr__(self) -> str:
        return "ConnectedLeaseConsumption(authority='<redacted>')"


class ConnectedCredentialLeaseConsumer(Protocol):
    async def consume_once(
        self,
        *,
        lease: ConnectedCredentialLease,
        operation_id: str,
        action: ConnectorActionKind,
    ) -> ConnectedLeaseConsumption: ...


class _ActionDispatcher:
    def __init__(
        self,
        *,
        action: ConnectorActionKind,
        provider: ConnectorProvider,
        adapter: ConnectedAppProvider,
        leases: ConnectedCredentialLeaseConsumer,
        now: Callable[[], datetime],
    ) -> None:
        if action not in implemented_runtime_actions():
            raise ValueError("action is not implemented")
        if not isinstance(provider, ConnectorProvider):
            raise ValueError("provider is invalid")
        self.action = action
        self._provider = provider
        self._resource = _ACTION_RESOURCE[action]
        self._adapter = adapter
        self._leases = leases
        self._now = now

    async def _consume(
        self,
        *,
        account: ConnectedAccountRef,
        credential: ConnectedCredentialLease,
        operation_id: str,
        phase: ConnectedCredentialPhase,
    ) -> None:
        operation_id = _uuid(operation_id, "operation_id")
        if (
            type(credential) is not ConnectedCredentialLease
            or credential.phase is not phase
            or credential.owner_id != account.owner_id
            or credential.connection_id != account.connection_id
            or credential.provider is not self._provider
            or account.provider is not self._provider
            or credential.resource is not self._resource
            or account.resource is not self._resource
        ):
            raise ConnectedDispatchError("CONNECTED_DISPATCH_LEASE_MISMATCH")
        reference = _aware(self._now(), "now")
        if credential.expires_at <= reference:
            raise ConnectedDispatchError("CONNECTED_DISPATCH_LEASE_EXPIRED")
        try:
            receipt = await self._leases.consume_once(
                lease=credential,
                operation_id=operation_id,
                action=self.action,
            )
        except ConnectedDispatchError:
            raise
        except Exception:
            raise ConnectedDispatchError(
                "CONNECTED_DISPATCH_LEASE_UNCERTAIN", retryable=False
            ) from None
        if type(receipt) is not ConnectedLeaseConsumption:
            raise ConnectedDispatchError("CONNECTED_DISPATCH_LEASE_RECEIPT_INVALID")
        if (
            receipt.operation_id != operation_id
            or receipt.owner_id != credential.owner_id
            or receipt.connection_id != credential.connection_id
            or receipt.claim_id != credential.claim_id
            or receipt.fencing_token != credential.fencing_token
            or receipt.provider is not credential.provider
            or receipt.resource is not credential.resource
            or receipt.action is not self.action
            or receipt.phase is not phase
            or receipt.use_nonce != credential.use_nonce
            or receipt.consumed_at < credential.issued_at
            or receipt.consumed_at >= credential.expires_at
            or receipt.consumed_at > reference + _FUTURE_SKEW
            or _aware(self._now(), "now") >= credential.expires_at
        ):
            raise ConnectedDispatchError("CONNECTED_DISPATCH_LEASE_RECEIPT_MISMATCH")

    async def execute_read(
        self,
        *,
        account: ConnectedAccountRef,
        credential: ConnectedCredentialLease,
        request: ProviderRequest,
        operation_id: str,
    ) -> ConnectedReadObservation:
        if self.action not in _READ_ACTIONS:
            raise ConnectedDispatchError("CONNECTED_DISPATCH_ACTION_MISMATCH")
        await self._consume(
            account=account,
            credential=credential,
            operation_id=operation_id,
            phase=ConnectedCredentialPhase.READ,
        )
        try:
            if (
                self.action is ConnectorActionKind.MAIL_SEARCH
                and type(request) is MailSearchRequest
            ):
                value = await self._adapter.search_mail(
                    account=account, credential=credential.credential, request=request
                )
                if type(value) is not tuple or any(
                    type(item) is not MessageSummary for item in value
                ):
                    raise ConnectedDispatchError("CONNECTED_PROVIDER_RESULT_INVALID")
                version = None
            elif self.action is ConnectorActionKind.MAIL_GET and type(request) is MailGetRequest:
                value = await self._adapter.get_message(
                    account=account, credential=credential.credential, request=request
                )
                if type(value) is not MessageSnapshot:
                    raise ConnectedDispatchError("CONNECTED_PROVIDER_RESULT_INVALID")
                version = value.resource_version
            elif (
                self.action is ConnectorActionKind.CALENDAR_LIST
                and type(request) is CalendarListRequest
            ):
                value = await self._adapter.list_events(
                    account=account, credential=credential.credential, request=request
                )
                if type(value) is not tuple or any(
                    type(item) is not EventSnapshot for item in value
                ):
                    raise ConnectedDispatchError("CONNECTED_PROVIDER_RESULT_INVALID")
                version = None
            elif (
                self.action is ConnectorActionKind.CALENDAR_FREE_BUSY
                and type(request) is CalendarFreeBusyRequest
            ):
                value = await self._adapter.free_busy(
                    account=account, credential=credential.credential, request=request
                )
                if type(value) is not tuple or any(
                    type(item) is not FreeBusyWindow for item in value
                ):
                    raise ConnectedDispatchError("CONNECTED_PROVIDER_RESULT_INVALID")
                version = None
            elif (
                self.action is ConnectorActionKind.CALENDAR_GET
                and type(request) is CalendarGetRequest
            ):
                value = await self._adapter.get_event(
                    account=account, credential=credential.credential, request=request
                )
                if type(value) is not EventSnapshot:
                    raise ConnectedDispatchError("CONNECTED_PROVIDER_RESULT_INVALID")
                version = value.resource_version
            else:
                raise ConnectedDispatchError("CONNECTED_DISPATCH_REQUEST_MISMATCH")
        except ConnectedDispatchError:
            raise
        except Exception:
            raise ConnectedDispatchError("CONNECTED_PROVIDER_FAILURE", retryable=True) from None
        return ConnectedReadObservation(
            operation_id=operation_id,
            provider=self._provider,
            resource=self._resource,
            value=value,
            observed_at=_aware(self._now(), "now"),
            resource_version=version,
        )

    async def observe_resource_version(
        self,
        *,
        account: ConnectedAccountRef,
        credential: ConnectedCredentialLease,
        request: ProviderRequest,
        operation_id: str,
    ) -> str | None:
        if self.action not in _WRITE_ACTIONS:
            raise ConnectedDispatchError("CONNECTED_DISPATCH_ACTION_MISMATCH")
        if credential.phase not in {
            ConnectedCredentialPhase.PREOBSERVE,
            ConnectedCredentialPhase.POSTOBSERVE,
        }:
            raise ConnectedDispatchError("CONNECTED_DISPATCH_LEASE_MISMATCH")
        phase = credential.phase
        await self._consume(
            account=account,
            credential=credential,
            operation_id=operation_id,
            phase=phase,
        )
        try:
            if self.action in {
                ConnectorActionKind.MAIL_CREATE_DRAFT,
                ConnectorActionKind.MAIL_SEND,
                ConnectorActionKind.CALENDAR_CREATE,
            }:
                if not (
                    (
                        self.action is ConnectorActionKind.MAIL_CREATE_DRAFT
                        and type(request) is MailDraftRequest
                    )
                    or (
                        self.action is ConnectorActionKind.MAIL_SEND
                        and type(request) is MailSendRequest
                    )
                    or (
                        self.action is ConnectorActionKind.CALENDAR_CREATE
                        and type(request) is CalendarCreateRequest
                    )
                ):
                    raise ConnectedDispatchError("CONNECTED_DISPATCH_REQUEST_MISMATCH")
                return None
            if self.action is ConnectorActionKind.MAIL_REPLY and type(request) is MailReplyRequest:
                source = request.spec.reply_to_message_id
                if source is None:
                    raise ConnectedDispatchError("CONNECTED_DISPATCH_REQUEST_MISMATCH")
                value = await self._adapter.get_message(
                    account=account,
                    credential=credential.credential,
                    request=MailGetRequest.build(message_id=source),
                )
                if type(value) is not MessageSnapshot:
                    raise ConnectedDispatchError("CONNECTED_PROVIDER_RESULT_INVALID")
                return value.resource_version
            if (
                self.action is ConnectorActionKind.CALENDAR_UPDATE
                and type(request) is CalendarUpdateRequest
            ):
                source = request.spec.source_event_id
                if source is None:
                    raise ConnectedDispatchError("CONNECTED_DISPATCH_REQUEST_MISMATCH")
                value = await self._adapter.get_event(
                    account=account,
                    credential=credential.credential,
                    request=CalendarGetRequest.build(
                        calendar_id=request.spec.calendar_id,
                        event_id=source,
                    ),
                )
                if type(value) is not EventSnapshot:
                    raise ConnectedDispatchError("CONNECTED_PROVIDER_RESULT_INVALID")
                return value.resource_version
            if (
                self.action is ConnectorActionKind.CALENDAR_CANCEL
                and type(request) is CalendarCancelRequest
            ):
                try:
                    value = await self._adapter.get_event(
                        account=account,
                        credential=credential.credential,
                        request=CalendarGetRequest.build(
                            calendar_id=request.calendar_id,
                            event_id=request.event_id,
                        ),
                    )
                except Exception as exc:
                    code = getattr(exc, "code", None)
                    if phase is ConnectedCredentialPhase.POSTOBSERVE and code in {
                        "GOOGLE_RESOURCE_NOT_FOUND",
                        "MICROSOFT_RESOURCE_NOT_FOUND",
                    }:
                        return request.expected_resource_version
                    raise
                if type(value) is not EventSnapshot:
                    raise ConnectedDispatchError("CONNECTED_PROVIDER_RESULT_INVALID")
                return value.resource_version
        except ConnectedDispatchError:
            raise
        except Exception:
            raise ConnectedDispatchError(
                "CONNECTED_PROVIDER_OBSERVE_FAILED",
                retryable=phase is ConnectedCredentialPhase.PREOBSERVE,
            ) from None
        raise ConnectedDispatchError("CONNECTED_DISPATCH_REQUEST_MISMATCH")

    async def execute_write(
        self,
        *,
        account: ConnectedAccountRef,
        credential: ConnectedCredentialLease,
        request: ProviderRequest,
        operation_id: str,
        idempotency_key: str,
    ) -> ProviderReceipt | AmbiguousProviderResult:
        if self.action not in _WRITE_ACTIONS:
            raise ConnectedDispatchError("CONNECTED_DISPATCH_ACTION_MISMATCH")
        await self._consume(
            account=account,
            credential=credential,
            operation_id=operation_id,
            phase=ConnectedCredentialPhase.EFFECT,
        )
        try:
            if (
                self.action is ConnectorActionKind.MAIL_CREATE_DRAFT
                and type(request) is MailDraftRequest
            ):
                result = await self._adapter.create_draft(
                    account=account,
                    credential=credential.credential,
                    request=request,
                    operation_id=operation_id,
                    idempotency_key=idempotency_key,
                )
            elif self.action is ConnectorActionKind.MAIL_SEND and type(request) is MailSendRequest:
                result = await self._adapter.send_mail(
                    account=account,
                    credential=credential.credential,
                    request=request,
                    operation_id=operation_id,
                    idempotency_key=idempotency_key,
                )
            elif (
                self.action is ConnectorActionKind.MAIL_REPLY and type(request) is MailReplyRequest
            ):
                result = await self._adapter.reply_mail(
                    account=account,
                    credential=credential.credential,
                    request=request,
                    operation_id=operation_id,
                    idempotency_key=idempotency_key,
                )
            elif (
                self.action is ConnectorActionKind.CALENDAR_CREATE
                and type(request) is CalendarCreateRequest
            ):
                result = await self._adapter.create_event(
                    account=account,
                    credential=credential.credential,
                    request=request,
                    operation_id=operation_id,
                    idempotency_key=idempotency_key,
                )
            elif (
                self.action is ConnectorActionKind.CALENDAR_UPDATE
                and type(request) is CalendarUpdateRequest
            ):
                result = await self._adapter.update_event(
                    account=account,
                    credential=credential.credential,
                    request=request,
                    operation_id=operation_id,
                    idempotency_key=idempotency_key,
                )
            elif (
                self.action is ConnectorActionKind.CALENDAR_CANCEL
                and type(request) is CalendarCancelRequest
            ):
                result = await self._adapter.cancel_event(
                    account=account,
                    credential=credential.credential,
                    request=request,
                    operation_id=operation_id,
                    idempotency_key=idempotency_key,
                )
            else:
                raise ConnectedDispatchError("CONNECTED_DISPATCH_REQUEST_MISMATCH")
        except ConnectedDispatchError:
            raise
        except Exception:
            # The phase lease has been consumed.  A provider exception after
            # this point is effect-unknown; the caller must settle ambiguous
            # and must never redispatch the write.
            raise ConnectedDispatchError("CONNECTED_PROVIDER_EFFECT_UNKNOWN") from None
        if type(result) not in {ProviderReceipt, AmbiguousProviderResult}:
            raise ConnectedDispatchError("CONNECTED_PROVIDER_EFFECT_UNKNOWN")
        return result


class DirectConnectedProviderResolver:
    """Exact provider/resource/action resolver with no dynamic fallback."""

    def __init__(
        self,
        *,
        google: ConnectedAppProvider,
        microsoft: ConnectedAppProvider,
        leases: ConnectedCredentialLeaseConsumer,
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self._dispatchers: dict[
            tuple[ConnectorProvider, ConnectorResource, ConnectorActionKind],
            _ActionDispatcher,
        ] = {}
        for provider, adapter in (
            (ConnectorProvider.GOOGLE, google),
            (ConnectorProvider.MICROSOFT, microsoft),
        ):
            for action, resource in _ACTION_RESOURCE.items():
                self._dispatchers[(provider, resource, action)] = _ActionDispatcher(
                    action=action,
                    provider=provider,
                    adapter=adapter,
                    leases=leases,
                    now=now,
                )

    def _resolve(
        self,
        *,
        provider: ConnectorProvider,
        resource: ConnectorResource,
        action: ConnectorActionKind,
        allowed: frozenset[ConnectorActionKind],
    ) -> _ActionDispatcher:
        if (
            not isinstance(provider, ConnectorProvider)
            or not isinstance(resource, ConnectorResource)
            or not isinstance(action, ConnectorActionKind)
            or action not in allowed
            or _ACTION_RESOURCE.get(action) is not resource
        ):
            raise ConnectedDispatchError("CONNECTED_DISPATCH_NOT_IMPLEMENTED")
        try:
            return self._dispatchers[(provider, resource, action)]
        except KeyError:
            raise ConnectedDispatchError("CONNECTED_DISPATCH_NOT_IMPLEMENTED") from None

    def resolve_read(self, *, provider, resource, action):
        return self._resolve(
            provider=provider,
            resource=resource,
            action=action,
            allowed=_READ_ACTIONS,
        )

    def resolve_write(self, *, provider, resource, action):
        return self._resolve(
            provider=provider,
            resource=resource,
            action=action,
            allowed=_WRITE_ACTIONS,
        )
