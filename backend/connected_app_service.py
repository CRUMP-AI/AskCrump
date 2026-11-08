"""Content-free application boundary for owner-connected mail and calendars.

This module deliberately has no database, OAuth client, credential broker,
provider transport, or release switch. It validates user-initiated commands
and delegates them to one injected durable control plane. Provider content is
represented only by a bounded, explicitly reviewed write preview; it is never
an authority source, is redacted from reprs, and is bound to the exact typed
provider request. All other public records are content-free.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import re
from dataclasses import InitVar, dataclass, field
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import Awaitable, Callable, Protocol, TypeVar
from urllib.parse import parse_qsl, urlsplit
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .connected_app_contracts import (
    CalendarCancelRequest,
    CalendarCreateRequest,
    CalendarUpdateRequest,
    ConnectionAuthorizationState,
    ConnectorAccountKind,
    EventSnapshot,
    MailDraftRequest,
    MailReplyRequest,
    MailSendRequest,
)
from .connected_app_oauth import (
    OAuthCallbackSecrets,
    OAuthRedirectAllowlist,
    OAuthStateSecret,
)
from .connected_app_policy import (
    ConnectedActionPolicy,
    ConnectorActionKind,
    ConnectorProvider,
    ConnectorResource,
    implemented_runtime_actions,
)
from .connected_app_scopes import ConnectedAppScopeError, delegated_scope_plan


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_LABEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_TIME = re.compile(r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]$")
_OAUTH_CLIENT_ID = re.compile(r"^[A-Za-z0-9._-]{3,512}$")
_PKCE_CHALLENGE = re.compile(r"^[A-Za-z0-9_-]{43}$")
_MICROSOFT_AUTHORIZE_PATH = re.compile(r"^/(?:consumers|organizations)/oauth2/v2\.0/authorize$")
_MAX_PUBLIC_ITEMS = 100
_MAX_APPROVAL_RESPONSE_BYTES = 240_000
_MAX_SINGLE_APPROVAL_BYTES = 220_000
_MAX_DEPENDENCY_SECONDS = 5.0
_APPROVAL_MAX_TTL = timedelta(minutes=15)
_READINESS_FUTURE_SKEW = timedelta(seconds=30)
# A valid quiet window can span almost 24 wall-clock hours.  During an IANA
# fall-back transition that is almost 25 elapsed hours, so 24 hours is not a
# safe upper bound for a provider-neutral schedule contract.
_MAX_SCHEDULE_QUIET_DELAY = timedelta(hours=25)
_PROVIDER_AUTH_HOSTS = {
    ConnectorProvider.GOOGLE: frozenset({"accounts.google.com"}),
    ConnectorProvider.MICROSOFT: frozenset({"login.microsoftonline.com"}),
}
_OAUTH_REQUIRED_QUERY_KEYS = frozenset(
    {
        "client_id",
        "redirect_uri",
        "response_type",
        "scope",
        "state",
        "code_challenge",
        "code_challenge_method",
    }
)
_OAUTH_OPTIONAL_QUERY_KEYS = {
    ConnectorProvider.GOOGLE: frozenset({"access_type", "prompt", "include_granted_scopes"}),
    ConnectorProvider.MICROSOFT: frozenset({"response_mode", "prompt"}),
}
_OAUTH_FORBIDDEN_QUERY_KEYS = frozenset(
    {
        "access_token",
        "authorization_code",
        "client_assertion",
        "client_assertion_type",
        "client_secret",
        "code",
        "code_verifier",
        "id_token",
        "refresh_token",
        "token",
    }
)
_PREVIEW_FORBIDDEN_CODEPOINTS = frozenset((*range(9), 11, 12, *range(14, 32), 127))


def _uuid(value: str, name: str) -> str:
    if not isinstance(value, str):
        raise ConnectedAppServiceError("CONNECTED_INPUT_INVALID", 400)
    try:
        parsed = UUID(value)
    except (ValueError, AttributeError, TypeError):
        raise ConnectedAppServiceError("CONNECTED_INPUT_INVALID", 400) from None
    if str(parsed) != value:
        raise ConnectedAppServiceError("CONNECTED_INPUT_INVALID", 400)
    return value


def _sha(value: str, name: str = "binding") -> str:
    del name
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ConnectedAppServiceError("CONNECTED_INPUT_INVALID", 400)
    return value


def _aware(value: datetime, name: str = "timestamp") -> datetime:
    del name
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ConnectedAppServiceError("CONNECTED_RECORD_INVALID", 500)
    return value.astimezone(timezone.utc)


def _bounded_label(value: str, name: str = "label") -> str:
    del name
    if not isinstance(value, str) or not _LABEL.fullmatch(value):
        raise ConnectedAppServiceError("CONNECTED_INPUT_INVALID", 400)
    return value


def _digest_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _canonical_hash(value: dict[str, object]) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=True,
        separators=(",", ":"),
    ).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


def connected_app_readiness_attestation_sha256(
    *,
    ready: bool,
    composition_manifest_sha256: str,
    checked_at: datetime,
    expires_at: datetime,
) -> str:
    """Bind one short-lived readiness result to its exact composition manifest."""

    if type(ready) is not bool:
        raise ValueError("ready must be boolean")
    checked = _aware(checked_at)
    expires = _aware(expires_at)
    manifest = _sha(composition_manifest_sha256)
    if expires <= checked or expires - checked > timedelta(minutes=15):
        raise ValueError("readiness attestation lifetime is invalid")
    return _canonical_hash(
        {
            "version": "connected-app-readiness-v1",
            "ready": ready,
            "composition_manifest_sha256": manifest,
            "checked_at": checked.isoformat(),
            "expires_at": expires.isoformat(),
        }
    )


def _enum(value: object, expected: type[StrEnum]) -> None:
    if not isinstance(value, expected):
        raise ConnectedAppServiceError("CONNECTED_RECORD_INVALID", 500)


def _public_time(value: datetime | None) -> str | None:
    if value is None:
        return None
    return _aware(value).isoformat().replace("+00:00", "Z")


def _public_enum(value: StrEnum) -> str:
    return value.value


def _parse_quiet(value: str | None) -> int | None:
    if value is None:
        return None
    if not isinstance(value, str) or not _TIME.fullmatch(value):
        raise ConnectedAppServiceError("CONNECTED_SCHEDULE_INVALID", 400)
    hours, minutes = value.split(":", 1)
    return int(hours) * 60 + int(minutes)


def _iana_zone(value: str) -> str:
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= 100
        or value != value.strip()
        or "/" not in value
        or value.startswith(("+", "-"))
    ):
        raise ConnectedAppServiceError("CONNECTED_SCHEDULE_INVALID", 400)
    try:
        zone = ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError, TypeError):
        raise ConnectedAppServiceError("CONNECTED_SCHEDULE_INVALID", 400) from None
    if zone.key != value:
        raise ConnectedAppServiceError("CONNECTED_SCHEDULE_INVALID", 400)
    return value


class ConnectedAppServiceError(RuntimeError):
    """Fixed, content-free failure safe for an API response."""

    def __init__(
        self,
        code: str,
        status_code: int = 400,
        *,
        retryable: bool = False,
    ) -> None:
        if not isinstance(code, str) or not re.fullmatch(r"CONNECTED_[A-Z0-9_]{1,80}", code):
            code = "CONNECTED_OPERATION_FAILED"
            status_code = 500
            retryable = False
        super().__init__(code)
        self.code = code
        self.status_code = status_code
        self.retryable = retryable

    def __repr__(self) -> str:
        return (
            f"ConnectedAppServiceError(code={self.code!r}, "
            f"status_code={self.status_code!r}, retryable={self.retryable!r})"
        )


@dataclass(frozen=True, slots=True, repr=False)
class ConnectedAppReadiness:
    ready: bool
    attestation_sha256: str
    composition_manifest_sha256: str
    checked_at: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        expected = connected_app_readiness_attestation_sha256(
            ready=self.ready,
            composition_manifest_sha256=self.composition_manifest_sha256,
            checked_at=self.checked_at,
            expires_at=self.expires_at,
        )
        if _sha(self.attestation_sha256) != expected:
            raise ValueError("readiness attestation binding is invalid")

    def __repr__(self) -> str:
        return (
            f"ConnectedAppReadiness(ready={self.ready!r}, "
            "attestation='<redacted>', composition='<redacted>')"
        )


@dataclass(frozen=True, slots=True, repr=False)
class ConnectedConnectionView:
    connection_id: str
    provider: ConnectorProvider
    resource: ConnectorResource
    account_kind: ConnectorAccountKind
    granted_actions: tuple[ConnectorActionKind, ...]
    authorization_state: ConnectionAuthorizationState
    authorization_revision: int
    authorization_snapshot_sha256: str | None
    expires_at: datetime | None
    updated_at: datetime

    def __post_init__(self) -> None:
        _uuid(self.connection_id, "connection_id")
        _enum(self.provider, ConnectorProvider)
        _enum(self.resource, ConnectorResource)
        _enum(self.account_kind, ConnectorAccountKind)
        if (
            not isinstance(self.granted_actions, tuple)
            or not self.granted_actions
            or len(self.granted_actions) > 12
            or len(self.granted_actions) != len(set(self.granted_actions))
            or tuple(sorted(self.granted_actions, key=lambda action: action.value))
            != self.granted_actions
            or any(
                not isinstance(action, ConnectorActionKind)
                or action not in implemented_runtime_actions()
                or ConnectedActionPolicy.requirement(action).resource is not self.resource
                for action in self.granted_actions
            )
        ):
            raise ValueError("granted actions are invalid")
        _enum(self.authorization_state, ConnectionAuthorizationState)
        if type(self.authorization_revision) is not int or self.authorization_revision < 0:
            raise ValueError("authorization revision is invalid")
        if self.authorization_snapshot_sha256 is not None:
            _sha(self.authorization_snapshot_sha256)
        if self.authorization_state is ConnectionAuthorizationState.ACTIVE:
            if self.authorization_revision < 1 or self.authorization_snapshot_sha256 is None:
                raise ValueError("active authorization is incomplete")
        if self.expires_at is not None:
            _aware(self.expires_at)
        _aware(self.updated_at)

    def public(self) -> dict[str, object]:
        return {
            "connectionId": self.connection_id,
            "provider": _public_enum(self.provider),
            "resource": _public_enum(self.resource),
            "accountKind": _public_enum(self.account_kind),
            "grantedActions": [action.value for action in self.granted_actions],
            "authorizationState": _public_enum(self.authorization_state),
            "authorizationRevision": self.authorization_revision,
            "expiresAt": _public_time(self.expires_at),
            "updatedAt": _public_time(self.updated_at),
        }

    def __repr__(self) -> str:
        return (
            "ConnectedConnectionView("
            f"connection_id={self.connection_id!r}, provider={self.provider.value!r}, "
            f"resource={self.resource.value!r}, authority='<redacted>')"
        )


@dataclass(frozen=True, slots=True, repr=False)
class ConnectedConnectionAuthorityView:
    """Current content-free delegated authority used for approval revalidation."""

    connection_id: str
    provider: ConnectorProvider
    resource: ConnectorResource
    authorization_state: ConnectionAuthorizationState
    authorization_revision: int
    authorization_snapshot_sha256: str
    granted_scopes_sha256: str
    granted_actions: tuple[ConnectorActionKind, ...]
    expires_at: datetime

    def __post_init__(self) -> None:
        _uuid(self.connection_id, "connection_id")
        _enum(self.provider, ConnectorProvider)
        _enum(self.resource, ConnectorResource)
        _enum(self.authorization_state, ConnectionAuthorizationState)
        if self.authorization_state is not ConnectionAuthorizationState.ACTIVE:
            raise ValueError("connection authority is not active")
        if type(self.authorization_revision) is not int or self.authorization_revision < 1:
            raise ValueError("authorization revision is invalid")
        _sha(self.authorization_snapshot_sha256)
        _sha(self.granted_scopes_sha256)
        if (
            not isinstance(self.granted_actions, tuple)
            or not self.granted_actions
            or len(self.granted_actions) > 12
            or len(self.granted_actions) != len(set(self.granted_actions))
            or tuple(sorted(self.granted_actions, key=lambda action: action.value))
            != self.granted_actions
            or any(
                not isinstance(action, ConnectorActionKind)
                or action not in implemented_runtime_actions()
                or ConnectedActionPolicy.requirement(action).resource is not self.resource
                for action in self.granted_actions
            )
        ):
            raise ValueError("granted actions are invalid")
        _aware(self.expires_at)

    def __repr__(self) -> str:
        return (
            "ConnectedConnectionAuthorityView("
            f"connection_id={self.connection_id!r}, authority='<redacted>')"
        )


@dataclass(frozen=True, slots=True, repr=False)
class DisconnectView:
    """Content-free proof of the complete durable disconnect transaction."""

    connection: ConnectedConnectionView
    grants_invalidated: bool
    schedules_invalidated: bool
    broker_cleanup_enqueued: bool
    updated_at: datetime

    def __post_init__(self) -> None:
        if (
            type(self.connection) is not ConnectedConnectionView
            or self.connection.authorization_state is not ConnectionAuthorizationState.REVOKED
        ):
            raise ValueError("disconnect authorization state is invalid")
        if (
            self.grants_invalidated is not True
            or self.schedules_invalidated is not True
            or self.broker_cleanup_enqueued is not True
        ):
            raise ValueError("disconnect side effects are incomplete")
        _aware(self.updated_at)

    def public(self) -> dict[str, object]:
        return {
            "connection": self.connection.public(),
            "grantsInvalidated": True,
            "schedulesInvalidated": True,
            "brokerCleanupEnqueued": True,
            "updatedAt": _public_time(self.updated_at),
        }

    def __repr__(self) -> str:
        return (
            f"DisconnectView(connection_id={self.connection.connection_id!r}, cleanup='<redacted>')"
        )


class ConnectedScheduleStatus(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    CANCELLED = "cancelled"


def schedule_transition_allowed(
    current: ConnectedScheduleStatus,
    target: ConnectedScheduleStatus,
) -> bool:
    """Return the only legal durable schedule-state graph edges."""

    if not isinstance(current, ConnectedScheduleStatus) or not isinstance(
        target, ConnectedScheduleStatus
    ):
        return False
    return (current, target) in {
        (ConnectedScheduleStatus.ACTIVE, ConnectedScheduleStatus.PAUSED),
        (ConnectedScheduleStatus.PAUSED, ConnectedScheduleStatus.ACTIVE),
        (ConnectedScheduleStatus.ACTIVE, ConnectedScheduleStatus.CANCELLED),
        (ConnectedScheduleStatus.PAUSED, ConnectedScheduleStatus.CANCELLED),
    }


@dataclass(frozen=True, slots=True, repr=False)
class ConnectedScheduleView:
    schedule_id: str
    connection_id: str
    task_id: str
    provider: ConnectorProvider
    resource: ConnectorResource
    action: ConnectorActionKind
    action_template_ref: str
    parameters_sha256: str
    task_state_revision: int
    time_zone: str
    cadence_seconds: int
    quiet_start_minute: int | None
    quiet_end_minute: int | None
    requires_approval_every_run: bool
    status: ConnectedScheduleStatus
    next_run_at: datetime | None
    updated_at: datetime

    def __post_init__(self) -> None:
        for value, name in (
            (self.schedule_id, "schedule_id"),
            (self.connection_id, "connection_id"),
            (self.task_id, "task_id"),
        ):
            _uuid(value, name)
        _enum(self.provider, ConnectorProvider)
        _enum(self.resource, ConnectorResource)
        _enum(self.action, ConnectorActionKind)
        _enum(self.status, ConnectedScheduleStatus)
        _uuid(self.action_template_ref, "action_template_ref")
        _sha(self.parameters_sha256)
        if type(self.task_state_revision) is not int or self.task_state_revision < 1:
            raise ValueError("schedule task revision is invalid")
        _iana_zone(self.time_zone)
        if type(self.cadence_seconds) is not int or not 60 <= self.cadence_seconds <= 2_678_400:
            raise ValueError("schedule cadence is invalid")
        for minute in (self.quiet_start_minute, self.quiet_end_minute):
            if minute is not None and (type(minute) is not int or not 0 <= minute <= 1439):
                raise ValueError("quiet minute is invalid")
        if (self.quiet_start_minute is None) != (self.quiet_end_minute is None):
            raise ValueError("quiet hours are partial")
        if self.quiet_start_minute is not None and self.quiet_start_minute == self.quiet_end_minute:
            raise ValueError("quiet hours are ambiguous")
        if type(self.requires_approval_every_run) is not bool:
            raise ValueError("schedule approval marker is invalid")
        if self.next_run_at is not None:
            _aware(self.next_run_at)
        if self.status is ConnectedScheduleStatus.ACTIVE and self.next_run_at is None:
            raise ValueError("active schedule requires a next run")
        if self.status is not ConnectedScheduleStatus.ACTIVE and self.next_run_at is not None:
            raise ValueError("inactive schedule cannot retain a next run")
        _aware(self.updated_at)

    def public(self) -> dict[str, object]:
        quiet_start = None
        quiet_end = None
        if self.quiet_start_minute is not None:
            quiet_start = f"{self.quiet_start_minute // 60:02d}:{self.quiet_start_minute % 60:02d}"
            quiet_end = f"{self.quiet_end_minute // 60:02d}:{self.quiet_end_minute % 60:02d}"
        return {
            "scheduleId": self.schedule_id,
            "connectionId": self.connection_id,
            "taskId": self.task_id,
            "provider": self.provider.value,
            "resource": self.resource.value,
            "action": self.action.value,
            "actionTemplateRef": self.action_template_ref,
            "parametersSha256": self.parameters_sha256,
            "taskStateRevision": self.task_state_revision,
            "timeZone": self.time_zone,
            "cadenceSeconds": self.cadence_seconds,
            "quietStart": quiet_start,
            "quietEnd": quiet_end,
            "requiresApprovalEveryRun": self.requires_approval_every_run,
            "status": self.status.value,
            "nextRunAt": _public_time(self.next_run_at),
            "updatedAt": _public_time(self.updated_at),
        }

    def __repr__(self) -> str:
        return (
            f"ConnectedScheduleView(schedule_id={self.schedule_id!r}, "
            f"action={self.action.value!r}, bindings='<redacted>')"
        )


_PREVIEW_VERSION = "connected-approval-preview-v1"
_MAIL_PREVIEW_ACTIONS = frozenset(
    {
        ConnectorActionKind.MAIL_CREATE_DRAFT,
        ConnectorActionKind.MAIL_SEND,
        ConnectorActionKind.MAIL_REPLY,
    }
)
_CALENDAR_PREVIEW_ACTIONS = frozenset(
    {
        ConnectorActionKind.CALENDAR_CREATE,
        ConnectorActionKind.CALENDAR_UPDATE,
        ConnectorActionKind.CALENDAR_CANCEL,
    }
)


def _preview_text(value: object, maximum: int, *, nullable: bool = False) -> str | None:
    if nullable and value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("approval preview text is invalid")
    if any(
        ord(character) in _PREVIEW_FORBIDDEN_CODEPOINTS or 0xD800 <= ord(character) <= 0xDFFF
        for character in value
    ):
        raise ValueError("approval preview text is invalid")
    if len(value.encode("utf-8")) > maximum:
        raise ValueError("approval preview text is invalid")
    return value


def _preview_list(value: object, maximum_items: int) -> tuple[str, ...]:
    if not isinstance(value, tuple) or len(value) > maximum_items:
        raise ValueError("approval preview list is invalid")
    normalized = tuple(_preview_text(item, 320) for item in value)
    if len(normalized) != len(set(normalized)):
        raise ValueError("approval preview list is invalid")
    return normalized  # type: ignore[return-value]


def _preview_instant(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("approval preview instant is invalid") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("approval preview instant is invalid")
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True, slots=True, repr=False)
class ConnectedMailReviewPayload:
    account: str
    to: tuple[str, ...]
    cc: tuple[str, ...]
    bcc: tuple[str, ...]
    subject: str
    body_text: str
    reply_context: str | None

    def __post_init__(self) -> None:
        _preview_text(self.account, 320)
        _preview_list(self.to, 50)
        _preview_list(self.cc, 50)
        _preview_list(self.bcc, 50)
        _preview_text(self.subject, 998)
        _preview_text(self.body_text, 100_000)
        _preview_text(self.reply_context, 1_000, nullable=True)

    def public(self) -> dict[str, object]:
        return {
            "account": self.account,
            "to": list(self.to),
            "cc": list(self.cc),
            "bcc": list(self.bcc),
            "subject": self.subject,
            "bodyText": self.body_text,
            "replyContext": self.reply_context,
        }

    def __repr__(self) -> str:
        return "ConnectedMailReviewPayload(content='<redacted>')"


@dataclass(frozen=True, slots=True, repr=False)
class ConnectedCalendarReviewPayload:
    calendar: str
    event_context: str | None
    title: str
    start: str
    end: str
    time_zone: str
    attendees: tuple[str, ...]
    location: str
    description: str

    def __post_init__(self) -> None:
        _preview_text(self.calendar, 320)
        _preview_text(self.event_context, 1_000, nullable=True)
        if not (_preview_text(self.title, 1_000) or "").strip():
            raise ValueError("approval preview title is invalid")
        _preview_text(self.start, 80)
        _preview_text(self.end, 80)
        if _preview_instant(self.end) <= _preview_instant(self.start):
            raise ValueError("approval preview interval is invalid")
        _iana_zone(self.time_zone)
        _preview_list(self.attendees, 200)
        _preview_text(self.location, 1_000)
        _preview_text(self.description, 100_000)

    def public(self) -> dict[str, object]:
        return {
            "calendar": self.calendar,
            "eventContext": self.event_context,
            "title": self.title,
            "start": self.start,
            "end": self.end,
            "timeZone": self.time_zone,
            "attendees": list(self.attendees),
            "location": self.location,
            "description": self.description,
        }

    def __repr__(self) -> str:
        return "ConnectedCalendarReviewPayload(content='<redacted>')"


ConnectedReviewPayload = ConnectedMailReviewPayload | ConnectedCalendarReviewPayload
ConnectedWriteRequest = (
    MailDraftRequest
    | MailSendRequest
    | MailReplyRequest
    | CalendarCreateRequest
    | CalendarUpdateRequest
    | CalendarCancelRequest
)
_PREVIEW_REQUEST_TYPES: dict[ConnectorActionKind, type] = {
    ConnectorActionKind.MAIL_CREATE_DRAFT: MailDraftRequest,
    ConnectorActionKind.MAIL_SEND: MailSendRequest,
    ConnectorActionKind.MAIL_REPLY: MailReplyRequest,
    ConnectorActionKind.CALENDAR_CREATE: CalendarCreateRequest,
    ConnectorActionKind.CALENDAR_UPDATE: CalendarUpdateRequest,
    ConnectorActionKind.CALENDAR_CANCEL: CalendarCancelRequest,
}


def approval_execution_parameters_sha256(
    *,
    action: ConnectorActionKind,
    provider_request: ConnectedWriteRequest,
    payload_commitment_sha256: str,
) -> str:
    """Validate and return the vault-keyed encrypted-payload commitment.

    The provider request's plain target digest is intentionally *not* returned
    or persisted.  It remains inside the encrypted payload envelope and is
    checked separately when that envelope is opened for execution.
    """

    _enum(action, ConnectorActionKind)
    if type(provider_request) is not _PREVIEW_REQUEST_TYPES.get(action):
        raise ValueError("approval provider request does not match its action")
    _sha(provider_request.target_binding_sha256)
    return _sha(payload_commitment_sha256)


def _review_payload_matches_request(
    action: ConnectorActionKind,
    payload: ConnectedReviewPayload,
    provider_request: ConnectedWriteRequest,
) -> bool:
    if action in _MAIL_PREVIEW_ACTIONS:
        if type(payload) is not ConnectedMailReviewPayload or type(provider_request) not in {
            MailDraftRequest,
            MailSendRequest,
            MailReplyRequest,
        }:
            return False
        spec = provider_request.spec
        return bool(
            payload.to == spec.to
            and payload.cc == spec.cc
            and payload.bcc == spec.bcc
            and payload.subject == spec.subject
            and payload.body_text == spec.body_text
            and payload.reply_context == spec.reply_to_message_id
        )
    if type(payload) is not ConnectedCalendarReviewPayload:
        return False
    if type(provider_request) in {CalendarCreateRequest, CalendarUpdateRequest}:
        spec = provider_request.spec
        return bool(
            payload.calendar == spec.calendar_id
            and payload.event_context == spec.source_event_id
            and payload.title == spec.title
            and _preview_instant(payload.start) == spec.starts_at.astimezone(timezone.utc)
            and _preview_instant(payload.end) == spec.ends_at.astimezone(timezone.utc)
            and payload.time_zone == spec.time_zone
            and payload.attendees == spec.attendees
            and payload.location == spec.location
            and payload.description == spec.description
        )
    if type(provider_request) is CalendarCancelRequest:
        return False
    return False


def _request_resource_version(provider_request: ConnectedWriteRequest) -> str | None:
    if type(provider_request) in {MailDraftRequest, MailSendRequest, MailReplyRequest}:
        return provider_request.spec.expected_resource_version
    if type(provider_request) in {CalendarCreateRequest, CalendarUpdateRequest}:
        return provider_request.spec.expected_resource_version
    if type(provider_request) is CalendarCancelRequest:
        return provider_request.expected_resource_version
    raise ValueError("approval provider request is invalid")


def _cancel_payload_matches_snapshot(
    payload: ConnectedReviewPayload,
    provider_request: ConnectedWriteRequest,
    authoritative_event: EventSnapshot | None,
) -> bool:
    if (
        type(payload) is not ConnectedCalendarReviewPayload
        or type(provider_request) is not CalendarCancelRequest
        or type(authoritative_event) is not EventSnapshot
    ):
        return False
    return bool(
        authoritative_event.calendar_id == provider_request.calendar_id
        and authoritative_event.event_id == provider_request.event_id
        and authoritative_event.resource_version == provider_request.expected_resource_version
        and payload.calendar == authoritative_event.calendar_id
        and payload.event_context == authoritative_event.event_id
        and payload.title == authoritative_event.title
        and _preview_instant(payload.start)
        == authoritative_event.starts_at.astimezone(timezone.utc)
        and _preview_instant(payload.end) == authoritative_event.ends_at.astimezone(timezone.utc)
        and payload.time_zone == authoritative_event.time_zone
        and payload.attendees == authoritative_event.attendees
        and payload.location == authoritative_event.location
        and payload.description == authoritative_event.description
    )


def approval_review_preview_sha256(
    *,
    approval_id: str,
    action_id: str,
    action: ConnectorActionKind,
    approval_binding_sha256: str,
    parameters_sha256: str,
    resource_version_sha256: str | None,
    payload: ConnectedReviewPayload,
    preview_commitment_sha256: str,
) -> str:
    """Validate and return a vault-keyed commitment to the encrypted preview.

    Exact preview derivation is checked in ``ConnectedApprovalReviewPreview``.
    A public deterministic digest of recipients or event details would permit
    offline guessing, so this helper never hashes the plaintext preview.
    """

    _uuid(approval_id, "approval_id")
    _uuid(action_id, "action_id")
    _enum(action, ConnectorActionKind)
    _sha(approval_binding_sha256)
    _sha(parameters_sha256)
    if resource_version_sha256 is not None:
        _sha(resource_version_sha256)
    if (
        action not in _MAIL_PREVIEW_ACTIONS | _CALENDAR_PREVIEW_ACTIONS
        or (action in _MAIL_PREVIEW_ACTIONS and type(payload) is not ConnectedMailReviewPayload)
        or (
            action in _CALENDAR_PREVIEW_ACTIONS
            and type(payload) is not ConnectedCalendarReviewPayload
        )
    ):
        raise ValueError("approval review payload is invalid")
    return _sha(preview_commitment_sha256)


def approval_review_display_sha256(
    *,
    approval_id: str,
    action_id: str,
    action: ConnectorActionKind,
    approval_binding_sha256: str,
    parameters_sha256: str,
    resource_version_sha256: str | None,
    payload: ConnectedReviewPayload,
) -> str:
    """Hash the exact plaintext preview returned in this no-store response.

    This response-only digest lets the browser detect display-payload drift. It
    is deliberately separate from ``preview_sha256``, which is a durable keyed
    commitment and cannot be recomputed by an untrusted browser.
    """

    _uuid(approval_id, "approval_id")
    _uuid(action_id, "action_id")
    _enum(action, ConnectorActionKind)
    _sha(approval_binding_sha256)
    _sha(parameters_sha256)
    if resource_version_sha256 is not None:
        _sha(resource_version_sha256)
    if (
        action not in _MAIL_PREVIEW_ACTIONS | _CALENDAR_PREVIEW_ACTIONS
        or (action in _MAIL_PREVIEW_ACTIONS and type(payload) is not ConnectedMailReviewPayload)
        or (
            action in _CALENDAR_PREVIEW_ACTIONS
            and type(payload) is not ConnectedCalendarReviewPayload
        )
    ):
        raise ValueError("approval review payload is invalid")
    canonical = json.dumps(
        {
            "version": _PREVIEW_VERSION,
            "approvalId": approval_id,
            "actionId": action_id,
            "action": action.value,
            "approvalBindingSha256": approval_binding_sha256,
            "parametersSha256": parameters_sha256,
            "resourceVersionSha256": resource_version_sha256,
            "payload": payload.public(),
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return _digest_text(canonical)


@dataclass(frozen=True, slots=True, repr=False)
class ConnectedApprovalReviewPreview:
    approval_binding_sha256: str
    parameters_sha256: str
    preview_sha256: str
    payload: ConnectedReviewPayload
    connection_id: str
    action: ConnectorActionKind
    resource_version_sha256: str | None
    provider_request: InitVar[ConnectedWriteRequest]
    authoritative_event: InitVar[EventSnapshot | None] = None
    request_target_binding_sha256: str = field(init=False, repr=False)

    def __post_init__(
        self,
        provider_request: ConnectedWriteRequest,
        authoritative_event: EventSnapshot | None,
    ) -> None:
        _sha(self.approval_binding_sha256)
        _sha(self.parameters_sha256)
        _sha(self.preview_sha256)
        _uuid(self.connection_id, "connection_id")
        _enum(self.action, ConnectorActionKind)
        if self.resource_version_sha256 is not None:
            _sha(self.resource_version_sha256)
        if type(self.payload) not in {
            ConnectedMailReviewPayload,
            ConnectedCalendarReviewPayload,
        }:
            raise ValueError("approval review payload is invalid")
        if type(provider_request) not in set(_PREVIEW_REQUEST_TYPES.values()):
            raise ValueError("approval provider request is invalid")
        target_binding = _sha(provider_request.target_binding_sha256)
        expected_resource_version = _request_resource_version(provider_request)
        expected_resource_version_sha256 = (
            _digest_text(expected_resource_version)
            if expected_resource_version is not None
            else None
        )
        if self.resource_version_sha256 != expected_resource_version_sha256:
            raise ValueError("approval preview resource version is invalid")
        if self.action in _MAIL_PREVIEW_ACTIONS:
            if authoritative_event is not None:
                raise ValueError("mail approval cannot carry a calendar snapshot")
            if (
                type(self.payload) is not ConnectedMailReviewPayload
                or self.payload.account != self.connection_id
                or not _review_payload_matches_request(
                    self.action,
                    self.payload,
                    provider_request,
                )
            ):
                raise ValueError("approval preview is not derived from the provider request")
        elif self.action is ConnectorActionKind.CALENDAR_CANCEL:
            if not _cancel_payload_matches_snapshot(
                self.payload,
                provider_request,
                authoritative_event,
            ):
                raise ValueError("calendar cancellation preview is not authoritative")
        elif self.action in _CALENDAR_PREVIEW_ACTIONS:
            if authoritative_event is not None or not _review_payload_matches_request(
                self.action,
                self.payload,
                provider_request,
            ):
                raise ValueError("approval preview is not derived from the provider request")
        else:
            raise ValueError("approval action has no review-preview contract")
        object.__setattr__(self, "request_target_binding_sha256", target_binding)

    def public(self) -> dict[str, object]:
        return {
            "version": _PREVIEW_VERSION,
            "approvalBindingSha256": self.approval_binding_sha256,
            "parametersSha256": self.parameters_sha256,
            "previewSha256": self.preview_sha256,
            "payload": self.payload.public(),
        }

    def public_for(self, *, approval_id: str, action_id: str) -> dict[str, object]:
        value = self.public()
        value["displaySha256"] = approval_review_display_sha256(
            approval_id=approval_id,
            action_id=action_id,
            action=self.action,
            approval_binding_sha256=self.approval_binding_sha256,
            parameters_sha256=self.parameters_sha256,
            resource_version_sha256=self.resource_version_sha256,
            payload=self.payload,
        )
        return value

    def __repr__(self) -> str:
        return "ConnectedApprovalReviewPreview(content='<redacted>')"


class ConnectedActionPublicStatus(StrEnum):
    PENDING_APPROVAL = "pending_approval"
    CLAIMED = "claimed"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    AMBIGUOUS = "ambiguous"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True, repr=False)
class ConnectedActionView:
    action_id: str
    connection_id: str
    task_id: str
    turn_id: str
    provider: ConnectorProvider
    resource: ConnectorResource
    action: ConnectorActionKind
    authorization_revision: int
    authorization_snapshot_sha256: str
    granted_scopes_sha256: str
    policy_version: str
    action_revision: int
    status: ConnectedActionPublicStatus
    parameters_sha256: str
    resource_version_sha256: str | None
    preview_sha256: str | None
    updated_at: datetime

    def __post_init__(self) -> None:
        for value, name in (
            (self.action_id, "action_id"),
            (self.connection_id, "connection_id"),
            (self.task_id, "task_id"),
            (self.turn_id, "turn_id"),
        ):
            _uuid(value, name)
        _enum(self.provider, ConnectorProvider)
        _enum(self.resource, ConnectorResource)
        _enum(self.action, ConnectorActionKind)
        _enum(self.status, ConnectedActionPublicStatus)
        if ConnectedActionPolicy.requirement(self.action).resource is not self.resource:
            raise ValueError("action resource is invalid")
        if type(self.authorization_revision) is not int or self.authorization_revision < 1:
            raise ValueError("authorization revision is invalid")
        _sha(self.authorization_snapshot_sha256)
        _sha(self.granted_scopes_sha256)
        _bounded_label(self.policy_version, "policy_version")
        if type(self.action_revision) is not int or self.action_revision < 1:
            raise ValueError("action revision is invalid")
        _sha(self.parameters_sha256)
        if self.resource_version_sha256 is not None:
            _sha(self.resource_version_sha256)
        requirement = ConnectedActionPolicy.requirement(self.action)
        if requirement.mutates_external_state:
            if self.preview_sha256 is None:
                raise ValueError("write action preview binding is missing")
            _sha(self.preview_sha256)
        elif self.preview_sha256 is not None:
            raise ValueError("read action cannot carry a preview binding")
        _aware(self.updated_at)

    def public(self) -> dict[str, object]:
        return {
            "actionId": self.action_id,
            "connectionId": self.connection_id,
            "taskId": self.task_id,
            "turnId": self.turn_id,
            "provider": self.provider.value,
            "resource": self.resource.value,
            "action": self.action.value,
            "authorizationRevision": self.authorization_revision,
            "authorizationSnapshotSha256": self.authorization_snapshot_sha256,
            "grantedScopesSha256": self.granted_scopes_sha256,
            "policyVersion": self.policy_version,
            "actionRevision": self.action_revision,
            "status": self.status.value,
            "parametersSha256": self.parameters_sha256,
            "resourceVersionSha256": self.resource_version_sha256,
            "previewSha256": self.preview_sha256,
            "updatedAt": _public_time(self.updated_at),
        }

    def __repr__(self) -> str:
        return (
            f"ConnectedActionView(action_id={self.action_id!r}, "
            f"action={self.action.value!r}, bindings='<redacted>')"
        )


class ConnectedApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    EXPIRED = "expired"


@dataclass(frozen=True, slots=True, repr=False)
class ConnectedApprovalView:
    approval_id: str
    action_id: str
    connection_id: str
    task_id: str
    turn_id: str
    provider: ConnectorProvider
    resource: ConnectorResource
    action: ConnectorActionKind
    authorization_revision: int
    authorization_snapshot_sha256: str
    granted_scopes_sha256: str
    policy_version: str
    action_revision: int
    status: ConnectedApprovalStatus
    approval_binding_sha256: str
    parameters_sha256: str
    resource_version_sha256: str | None
    preview_sha256: str
    review_preview: ConnectedApprovalReviewPreview
    decision_id: str | None
    decision_session_binding_sha256: str | None
    expires_at: datetime
    decided_at: datetime | None

    def __post_init__(self) -> None:
        for value, name in (
            (self.approval_id, "approval_id"),
            (self.action_id, "action_id"),
            (self.connection_id, "connection_id"),
            (self.task_id, "task_id"),
            (self.turn_id, "turn_id"),
        ):
            _uuid(value, name)
        _enum(self.provider, ConnectorProvider)
        _enum(self.resource, ConnectorResource)
        _enum(self.action, ConnectorActionKind)
        _enum(self.status, ConnectedApprovalStatus)
        if ConnectedActionPolicy.requirement(self.action).resource is not self.resource:
            raise ValueError("approval action resource is invalid")
        if type(self.authorization_revision) is not int or self.authorization_revision < 1:
            raise ValueError("authorization revision is invalid")
        _sha(self.authorization_snapshot_sha256)
        _sha(self.granted_scopes_sha256)
        _bounded_label(self.policy_version, "policy_version")
        if type(self.action_revision) is not int or self.action_revision < 1:
            raise ValueError("action revision is invalid")
        _sha(self.approval_binding_sha256)
        _sha(self.parameters_sha256)
        if self.resource_version_sha256 is not None:
            _sha(self.resource_version_sha256)
        _sha(self.preview_sha256)
        if type(self.review_preview) is not ConnectedApprovalReviewPreview:
            raise ValueError("approval review preview is invalid")
        if (
            self.review_preview.approval_binding_sha256 != self.approval_binding_sha256
            or self.review_preview.parameters_sha256 != self.parameters_sha256
            or self.review_preview.preview_sha256 != self.preview_sha256
            or self.review_preview.connection_id != self.connection_id
            or self.review_preview.action is not self.action
            or self.review_preview.resource_version_sha256 != self.resource_version_sha256
        ):
            raise ValueError("approval review preview binding is invalid")
        payload = self.review_preview.payload
        if self.action in _MAIL_PREVIEW_ACTIONS:
            if type(payload) is not ConnectedMailReviewPayload:
                raise ValueError("mail approval preview is invalid")
            if self.action is ConnectorActionKind.MAIL_REPLY:
                if not payload.reply_context:
                    raise ValueError("mail reply preview is incomplete")
            elif payload.reply_context is not None:
                raise ValueError("mail preview has an invalid reply context")
            if self.action is not ConnectorActionKind.MAIL_CREATE_DRAFT and not (
                payload.to or payload.cc or payload.bcc
            ):
                raise ValueError("mail approval preview has no recipient")
        elif self.action in _CALENDAR_PREVIEW_ACTIONS:
            if type(payload) is not ConnectedCalendarReviewPayload:
                raise ValueError("calendar approval preview is invalid")
            if self.action is ConnectorActionKind.CALENDAR_CREATE:
                if payload.event_context is not None:
                    raise ValueError("calendar create preview has an event context")
            elif not payload.event_context:
                raise ValueError("calendar approval preview has no event context")
        else:
            raise ValueError("approval action has no review-preview contract")
        if (
            len(
                json.dumps(
                    self.public_preview_only(),
                    ensure_ascii=False,
                    separators=(",", ":"),
                ).encode("utf-8")
            )
            > _MAX_SINGLE_APPROVAL_BYTES
        ):
            raise ValueError("approval review preview is too large")
        if self.decision_id is not None:
            _uuid(self.decision_id, "decision_id")
        if self.decision_session_binding_sha256 is not None:
            _sha(self.decision_session_binding_sha256)
        _aware(self.expires_at)
        if self.decided_at is not None:
            _aware(self.decided_at)
        if self.status in {
            ConnectedApprovalStatus.APPROVED,
            ConnectedApprovalStatus.DENIED,
        }:
            if (
                self.decision_id is None
                or self.decision_session_binding_sha256 is None
                or self.decided_at is None
            ):
                raise ValueError("decided approval is missing its exact decision binding")
        elif (
            self.decision_id is not None
            or self.decision_session_binding_sha256 is not None
            or self.decided_at is not None
        ):
            raise ValueError("undecided approval has a decision binding")

    def public_preview_only(self) -> dict[str, object]:
        return {
            "approvalId": self.approval_id,
            "actionId": self.action_id,
            "connectionId": self.connection_id,
            "taskId": self.task_id,
            "turnId": self.turn_id,
            "provider": self.provider.value,
            "resource": self.resource.value,
            "action": self.action.value,
            "reviewPreview": self.review_preview.public_for(
                approval_id=self.approval_id,
                action_id=self.action_id,
            ),
        }

    def public(self) -> dict[str, object]:
        return {
            "approvalId": self.approval_id,
            "actionId": self.action_id,
            "connectionId": self.connection_id,
            "taskId": self.task_id,
            "turnId": self.turn_id,
            "provider": self.provider.value,
            "resource": self.resource.value,
            "action": self.action.value,
            "authorizationRevision": self.authorization_revision,
            "authorizationSnapshotSha256": self.authorization_snapshot_sha256,
            "grantedScopesSha256": self.granted_scopes_sha256,
            "policyVersion": self.policy_version,
            "actionRevision": self.action_revision,
            "status": self.status.value,
            "approvalBindingSha256": self.approval_binding_sha256,
            "parametersSha256": self.parameters_sha256,
            "resourceVersionSha256": self.resource_version_sha256,
            "previewSha256": self.preview_sha256,
            "reviewPreview": self.review_preview.public_for(
                approval_id=self.approval_id,
                action_id=self.action_id,
            ),
            "decisionId": self.decision_id,
            "expiresAt": _public_time(self.expires_at),
            "decidedAt": _public_time(self.decided_at),
        }

    def __repr__(self) -> str:
        return (
            f"ConnectedApprovalView(approval_id={self.approval_id!r}, "
            f"status={self.status.value!r}, bindings='<redacted>')"
        )


@dataclass(frozen=True, slots=True, repr=False)
class OAuthStartCommand:
    request_id: str
    owner_id: str
    session_binding_sha256: str
    provider: ConnectorProvider
    resource: ConnectorResource
    account_kind: ConnectorAccountKind
    actions: frozenset[ConnectorActionKind]
    redirect_uri: str
    connection_id: str | None
    requested_at: datetime

    def __post_init__(self) -> None:
        _uuid(self.request_id, "request_id")
        _uuid(self.owner_id, "owner_id")
        _sha(self.session_binding_sha256)
        _enum(self.provider, ConnectorProvider)
        _enum(self.resource, ConnectorResource)
        _enum(self.account_kind, ConnectorAccountKind)
        if (
            not isinstance(self.actions, frozenset)
            or not self.actions
            or any(not isinstance(value, ConnectorActionKind) for value in self.actions)
        ):
            raise ValueError("OAuth actions are invalid")
        for action in self.actions:
            if (
                action not in implemented_runtime_actions()
                or ConnectedActionPolicy.requirement(action).resource is not self.resource
            ):
                raise ValueError("OAuth action is not implemented for resource")
        try:
            delegated_scope_plan(
                self.provider,
                self.actions,
                account_kind=self.account_kind,
            )
        except (ConnectedAppScopeError, TypeError, ValueError):
            raise ValueError("OAuth actions have no safe delegated scope plan") from None
        if self.connection_id is not None:
            _uuid(self.connection_id, "connection_id")
        _aware(self.requested_at)

    def __repr__(self) -> str:
        return (
            f"OAuthStartCommand(request_id={self.request_id!r}, "
            f"provider={self.provider.value!r}, resource={self.resource.value!r}, "
            "bindings='<redacted>')"
        )


@dataclass(frozen=True, slots=True, repr=False)
class OAuthStartView:
    request_id: str
    flow_id: str
    connection_id: str
    provider: ConnectorProvider
    authorization_url: str
    state_sha256: str
    pkce_challenge: str
    command_binding_sha256: str
    expires_at: datetime

    def __post_init__(self) -> None:
        _uuid(self.request_id, "request_id")
        _uuid(self.flow_id, "flow_id")
        _uuid(self.connection_id, "connection_id")
        _enum(self.provider, ConnectorProvider)
        _sha(self.state_sha256)
        _sha(self.command_binding_sha256)
        if not isinstance(self.pkce_challenge, str) or not _PKCE_CHALLENGE.fullmatch(
            self.pkce_challenge
        ):
            raise ValueError("PKCE challenge is invalid")
        if (
            not isinstance(self.authorization_url, str)
            or not 1 <= len(self.authorization_url) <= 4096
        ):
            raise ValueError("authorization URL is invalid")
        parsed = urlsplit(self.authorization_url)
        if (
            parsed.scheme != "https"
            or parsed.hostname not in _PROVIDER_AUTH_HOSTS[self.provider]
            or parsed.username is not None
            or parsed.password is not None
            or parsed.port is not None
            or parsed.fragment
            or not parsed.query
        ):
            raise ValueError("authorization URL is outside provider boundary")
        if self.provider is ConnectorProvider.GOOGLE:
            if parsed.path != "/o/oauth2/v2/auth":
                raise ValueError("authorization URL path is invalid")
        elif not _MICROSOFT_AUTHORIZE_PATH.fullmatch(parsed.path):
            raise ValueError("authorization URL path is invalid")
        try:
            query = parse_qsl(
                parsed.query,
                keep_blank_values=True,
                strict_parsing=True,
                max_num_fields=32,
            )
        except ValueError:
            raise ValueError("authorization URL query is invalid") from None
        keys = [key for key, _ in query]
        parameters = dict(query)
        if (
            len(keys) != len(set(keys))
            or any(key != key.casefold() for key in keys)
            or _OAUTH_REQUIRED_QUERY_KEYS.difference(parameters)
            or set(parameters).difference(
                _OAUTH_REQUIRED_QUERY_KEYS | _OAUTH_OPTIONAL_QUERY_KEYS[self.provider]
            )
            or set(parameters).intersection(_OAUTH_FORBIDDEN_QUERY_KEYS)
            or any(
                not value
                or len(value) > 2048
                or any(ord(character) < 32 or ord(character) == 127 for character in value)
                for value in parameters.values()
            )
            or parameters["response_type"] != "code"
            or parameters["code_challenge_method"] != "S256"
            or parameters["code_challenge"] != self.pkce_challenge
        ):
            raise ValueError("authorization URL query is invalid")
        try:
            state = OAuthStateSecret(parameters["state"])
        except (TypeError, ValueError):
            raise ValueError("authorization URL state is invalid") from None
        if _digest_text(state.value) != self.state_sha256:
            raise ValueError("authorization URL state binding is invalid")
        scopes = parameters["scope"].split(" ")
        if not scopes or any(not scope for scope in scopes) or len(scopes) != len(set(scopes)):
            raise ValueError("authorization URL scope set is invalid")
        if self.provider is ConnectorProvider.GOOGLE:
            if parameters.get("access_type", "offline") != "offline":
                raise ValueError("authorization URL access type is invalid")
            if parameters.get("include_granted_scopes", "false") != "false":
                raise ValueError("authorization URL incremental scopes are forbidden")
            if parameters.get("prompt", "consent") not in {"consent", "select_account"}:
                raise ValueError("authorization URL prompt is invalid")
        else:
            if parameters.get("response_mode", "query") != "query":
                raise ValueError("authorization URL response mode is invalid")
            if parameters.get("prompt", "select_account") not in {
                "consent",
                "select_account",
            }:
                raise ValueError("authorization URL prompt is invalid")
        _aware(self.expires_at)

    def query_parameters(self) -> dict[str, str]:
        """Return the already-validated public authorization parameters."""

        return dict(
            parse_qsl(
                urlsplit(self.authorization_url).query,
                keep_blank_values=True,
                strict_parsing=True,
                max_num_fields=32,
            )
        )

    def public(self) -> dict[str, object]:
        return {
            "requestId": self.request_id,
            "flowId": self.flow_id,
            "connectionId": self.connection_id,
            "provider": self.provider.value,
            "authorizationUrl": self.authorization_url,
            "expiresAt": _public_time(self.expires_at),
        }

    def __repr__(self) -> str:
        return (
            f"OAuthStartView(request_id={self.request_id!r}, "
            f"provider={self.provider.value!r}, authorization_url='<redacted>')"
        )


def oauth_start_result_binding_sha256(
    command: OAuthStartCommand,
    *,
    flow_id: str,
    connection_id: str,
    authorization_url: str,
    state_sha256: str,
    pkce_challenge: str,
    expires_at: datetime,
) -> str:
    """Bind one public OAuth start result to its entire immutable command."""

    if type(command) is not OAuthStartCommand:
        raise TypeError("command must be an OAuthStartCommand")
    return _canonical_hash(
        {
            "version": "connected-app-service-oauth-start-v1",
            "request_id": command.request_id,
            "owner_id": command.owner_id,
            "session_binding_sha256": command.session_binding_sha256,
            "provider": command.provider.value,
            "resource": command.resource.value,
            "account_kind": command.account_kind.value,
            "actions": sorted(action.value for action in command.actions),
            "redirect_uri": command.redirect_uri,
            "requested_connection_id": command.connection_id,
            "flow_id": _uuid(flow_id, "flow_id"),
            "result_connection_id": _uuid(connection_id, "connection_id"),
            "authorization_url_sha256": _digest_text(authorization_url),
            "state_sha256": _sha(state_sha256),
            "pkce_challenge": pkce_challenge,
            "expires_at": _aware(expires_at).isoformat(),
        }
    )


@dataclass(frozen=True, slots=True, repr=False)
class OAuthCallbackCommand:
    owner_id: str
    session_binding_sha256: str = field(repr=False)
    provider: ConnectorProvider
    secrets: OAuthCallbackSecrets
    callback_binding_sha256: str
    received_at: datetime

    def __post_init__(self) -> None:
        _uuid(self.owner_id, "owner_id")
        _sha(self.session_binding_sha256)
        _enum(self.provider, ConnectorProvider)
        if not isinstance(self.secrets, OAuthCallbackSecrets):
            raise ConnectedAppServiceError("CONNECTED_OAUTH_CALLBACK_INVALID", 400)
        _sha(self.callback_binding_sha256)
        expected = _canonical_hash(
            {
                "owner_id": self.owner_id,
                "session_binding_sha256": self.session_binding_sha256,
                "provider": self.provider.value,
                "state": self.secrets.state.value,
                "code": self.secrets.authorization_code.value,
            }
        )
        if self.callback_binding_sha256 != expected:
            raise ConnectedAppServiceError("CONNECTED_OAUTH_CALLBACK_INVALID", 400)
        _aware(self.received_at)

    @classmethod
    def build(
        cls,
        *,
        owner_id: str,
        session_id: str,
        provider: ConnectorProvider,
        state: str,
        code: str,
        received_at: datetime,
    ) -> "OAuthCallbackCommand":
        try:
            secrets = OAuthCallbackSecrets(authorization_code=code, state=state)
        except (TypeError, ValueError):
            raise ConnectedAppServiceError("CONNECTED_OAUTH_CALLBACK_INVALID", 400) from None
        owner_id = _uuid(owner_id, "owner_id")
        session_binding_sha256 = _digest_text(_uuid(session_id, "session_id"))
        return cls(
            owner_id=owner_id,
            session_binding_sha256=session_binding_sha256,
            provider=provider,
            secrets=secrets,
            callback_binding_sha256=_canonical_hash(
                {
                    "owner_id": owner_id,
                    "session_binding_sha256": session_binding_sha256,
                    "provider": provider.value,
                    "state": state,
                    "code": code,
                }
            ),
            received_at=received_at,
        )

    def __repr__(self) -> str:
        return (
            f"OAuthCallbackCommand(provider={self.provider.value!r}, "
            "state='<redacted>', code='<redacted>', binding='<redacted>')"
        )

    def __getstate__(self) -> None:
        raise TypeError("OAuth callback command cannot be serialized")

    def __reduce_ex__(self, _protocol: int) -> None:
        raise TypeError("OAuth callback command cannot be serialized")


@dataclass(frozen=True, slots=True, repr=False)
class DisconnectCommand:
    request_id: str
    owner_id: str
    session_binding_sha256: str
    connection_id: str
    requested_at: datetime

    def __post_init__(self) -> None:
        for value, name in (
            (self.request_id, "request_id"),
            (self.owner_id, "owner_id"),
            (self.connection_id, "connection_id"),
        ):
            _uuid(value, name)
        _sha(self.session_binding_sha256)
        _aware(self.requested_at)

    def __repr__(self) -> str:
        return f"DisconnectCommand(request_id={self.request_id!r}, bindings='<redacted>')"


@dataclass(frozen=True, slots=True, repr=False)
class ScheduleCreateCommand:
    request_id: str
    owner_id: str
    session_binding_sha256: str
    connection_id: str
    task_id: str
    provider: ConnectorProvider
    resource: ConnectorResource
    action: ConnectorActionKind
    action_template_ref: str
    parameters_sha256: str
    time_zone: str
    cadence_seconds: int
    quiet_start_minute: int | None
    quiet_end_minute: int | None
    requires_approval_every_run: bool
    requested_at: datetime

    def __post_init__(self) -> None:
        for value, name in (
            (self.request_id, "request_id"),
            (self.owner_id, "owner_id"),
            (self.connection_id, "connection_id"),
            (self.task_id, "task_id"),
            (self.action_template_ref, "action_template_ref"),
        ):
            _uuid(value, name)
        _sha(self.session_binding_sha256)
        _sha(self.parameters_sha256)
        _enum(self.provider, ConnectorProvider)
        _enum(self.resource, ConnectorResource)
        _enum(self.action, ConnectorActionKind)
        if (
            self.action not in implemented_runtime_actions()
            or ConnectedActionPolicy.requirement(self.action).resource is not self.resource
        ):
            raise ConnectedAppServiceError("CONNECTED_SCHEDULE_INVALID", 400)
        _iana_zone(self.time_zone)
        if type(self.cadence_seconds) is not int or not 60 <= self.cadence_seconds <= 2_678_400:
            raise ConnectedAppServiceError("CONNECTED_SCHEDULE_INVALID", 400)
        for minute in (self.quiet_start_minute, self.quiet_end_minute):
            if minute is not None and (type(minute) is not int or not 0 <= minute <= 1439):
                raise ConnectedAppServiceError("CONNECTED_SCHEDULE_INVALID", 400)
        if (self.quiet_start_minute is None) != (self.quiet_end_minute is None):
            raise ConnectedAppServiceError("CONNECTED_SCHEDULE_INVALID", 400)
        if self.quiet_start_minute is not None and self.quiet_start_minute == self.quiet_end_minute:
            raise ConnectedAppServiceError("CONNECTED_SCHEDULE_INVALID", 400)
        if type(self.requires_approval_every_run) is not bool:
            raise ConnectedAppServiceError("CONNECTED_SCHEDULE_INVALID", 400)
        requirement = ConnectedActionPolicy.requirement(self.action)
        if requirement.mutates_external_state and not self.requires_approval_every_run:
            raise ConnectedAppServiceError("CONNECTED_SCHEDULE_APPROVAL_REQUIRED", 400)
        _aware(self.requested_at)

    def __repr__(self) -> str:
        return (
            f"ScheduleCreateCommand(request_id={self.request_id!r}, "
            f"action={self.action.value!r}, bindings='<redacted>')"
        )


def schedule_create_result_matches(
    command: ScheduleCreateCommand,
    result: object,
) -> bool:
    """Validate the exact record a control plane may atomically persist."""

    return bool(
        type(command) is ScheduleCreateCommand
        and type(result) is ConnectedScheduleView
        and result.connection_id == command.connection_id
        and result.task_id == command.task_id
        and result.provider is command.provider
        and result.resource is command.resource
        and result.action is command.action
        and result.action_template_ref == command.action_template_ref
        and result.parameters_sha256 == command.parameters_sha256
        and result.time_zone == command.time_zone
        and result.cadence_seconds == command.cadence_seconds
        and result.quiet_start_minute == command.quiet_start_minute
        and result.quiet_end_minute == command.quiet_end_minute
        and result.requires_approval_every_run is command.requires_approval_every_run
        and result.status is ConnectedScheduleStatus.ACTIVE
        and result.task_state_revision == 1
        and result.next_run_at is not None
        and result.next_run_at > command.requested_at
        and result.next_run_at
        <= command.requested_at
        + timedelta(seconds=command.cadence_seconds)
        + _MAX_SCHEDULE_QUIET_DELAY
    )


@dataclass(frozen=True, slots=True, repr=False)
class ScheduleTransitionCommand:
    request_id: str
    owner_id: str
    session_binding_sha256: str
    schedule_id: str
    expected_task_state_revision: int
    expected_status: ConnectedScheduleStatus
    target: ConnectedScheduleStatus
    requested_at: datetime

    def __post_init__(self) -> None:
        for value, name in (
            (self.request_id, "request_id"),
            (self.owner_id, "owner_id"),
            (self.schedule_id, "schedule_id"),
        ):
            _uuid(value, name)
        _sha(self.session_binding_sha256)
        if (
            type(self.expected_task_state_revision) is not int
            or self.expected_task_state_revision < 1
        ):
            raise ConnectedAppServiceError("CONNECTED_SCHEDULE_INVALID", 400)
        _enum(self.expected_status, ConnectedScheduleStatus)
        _enum(self.target, ConnectedScheduleStatus)
        if not schedule_transition_allowed(self.expected_status, self.target):
            raise ConnectedAppServiceError("CONNECTED_SCHEDULE_TRANSITION_INVALID", 409)
        _aware(self.requested_at)

    def __repr__(self) -> str:
        return (
            f"ScheduleTransitionCommand(request_id={self.request_id!r}, "
            f"expected_status={self.expected_status.value!r}, "
            f"target={self.target.value!r}, bindings='<redacted>')"
        )


class ConnectedApprovalDecision(StrEnum):
    APPROVED = "approved"
    DENIED = "denied"


@dataclass(frozen=True, slots=True, repr=False)
class ApprovalDecisionCommand:
    decision_id: str
    owner_id: str
    session_binding_sha256: str
    approval_id: str
    action_id: str
    connection_id: str
    task_id: str
    turn_id: str
    provider: ConnectorProvider
    resource: ConnectorResource
    action: ConnectorActionKind
    authorization_revision: int
    authorization_snapshot_sha256: str
    granted_scopes_sha256: str
    policy_version: str
    action_revision: int
    approval_binding_sha256: str
    parameters_sha256: str
    resource_version_sha256: str | None
    preview_sha256: str
    decision: ConnectedApprovalDecision
    decided_at: datetime

    def __post_init__(self) -> None:
        for value, name in (
            (self.decision_id, "decision_id"),
            (self.owner_id, "owner_id"),
            (self.approval_id, "approval_id"),
            (self.action_id, "action_id"),
            (self.connection_id, "connection_id"),
            (self.task_id, "task_id"),
            (self.turn_id, "turn_id"),
        ):
            _uuid(value, name)
        _enum(self.provider, ConnectorProvider)
        _enum(self.resource, ConnectorResource)
        _enum(self.action, ConnectorActionKind)
        if type(self.authorization_revision) is not int or self.authorization_revision < 1:
            raise ConnectedAppServiceError("CONNECTED_APPROVAL_BINDING_MISMATCH", 409)
        _sha(self.authorization_snapshot_sha256)
        _sha(self.granted_scopes_sha256)
        _bounded_label(self.policy_version, "policy_version")
        if self.policy_version != ConnectedActionPolicy.version:
            raise ConnectedAppServiceError("CONNECTED_APPROVAL_BINDING_MISMATCH", 409)
        if type(self.action_revision) is not int or self.action_revision < 1:
            raise ConnectedAppServiceError("CONNECTED_APPROVAL_BINDING_MISMATCH", 409)
        _sha(self.session_binding_sha256)
        _sha(self.approval_binding_sha256)
        _sha(self.parameters_sha256)
        if self.resource_version_sha256 is not None:
            _sha(self.resource_version_sha256)
        _sha(self.preview_sha256)
        _enum(self.decision, ConnectedApprovalDecision)
        _aware(self.decided_at)

    def __repr__(self) -> str:
        return (
            f"ApprovalDecisionCommand(decision_id={self.decision_id!r}, "
            f"decision={self.decision.value!r}, bindings='<redacted>')"
        )


class ConnectedAppControlPlane(Protocol):
    """Durable, owner-scoped coordinator contract.

    Implementations must treat every ``*_once`` method and its readback key as
    one idempotency domain. ``start_oauth_once`` must atomically consume a
    pre-existing, server-minted explicit-user-action record keyed by
    ``request_id`` and bound to the exact owner, session, provider, resource,
    account kind, action set, redirect, and optional connection; it may never
    synthesize that authority from model or inbound content. ``disconnect_once``
    atomically revokes delegated
    authority, invalidates action grants and schedules, and durably enqueues
    credential-broker cleanup before returning ``DisconnectView``.
    ``create_schedule_once`` must atomically revalidate the exact current
    authorization revision and requested action membership, then validate
    ``schedule_create_result_matches(command, candidate)`` before inserting;
    an invalid candidate is never durable even when the returned response is
    malformed. ``transition_schedule_once`` atomically revalidates exact owner, current
    status and task revision, then applies only an allowed graph edge and a
    one-step revision increment. ``decide_approval_once`` atomically re-reads
    the current connection authority and action, then revalidates owner,
    session, task, turn, provider, resource, authorization revision/snapshot,
    granted scopes and actions, policy/action version, pending state, exclusive expiry,
    parameters, resource version, and exact verified review-preview digest
    before recording the exact decision.
    Neither inbound provider content nor model text is an authority source for
    any method here.
    """

    async def list_connections(self, *, owner_id: str) -> tuple[ConnectedConnectionView, ...]: ...

    async def get_connection_authority(
        self, *, owner_id: str, connection_id: str
    ) -> ConnectedConnectionAuthorityView | None: ...

    async def start_oauth_once(self, command: OAuthStartCommand) -> OAuthStartView: ...

    async def readback_oauth_start(
        self, *, owner_id: str, request_id: str
    ) -> OAuthStartView | None: ...

    async def complete_oauth_callback(
        self, command: OAuthCallbackCommand
    ) -> ConnectedConnectionView: ...

    async def deny_oauth_callback(
        self,
        *,
        owner_id: str,
        session_binding_sha256: str,
        provider: ConnectorProvider,
        state_sha256: str,
        received_at: datetime,
    ) -> None: ...

    async def readback_oauth_callback(
        self, *, provider: ConnectorProvider, callback_binding_sha256: str
    ) -> ConnectedConnectionView | None: ...

    async def disconnect_once(self, command: DisconnectCommand) -> DisconnectView: ...

    async def readback_disconnect(
        self, *, owner_id: str, connection_id: str, request_id: str
    ) -> DisconnectView | None: ...

    async def list_schedules(self, *, owner_id: str) -> tuple[ConnectedScheduleView, ...]: ...

    async def get_schedule(
        self, *, owner_id: str, schedule_id: str
    ) -> ConnectedScheduleView | None: ...

    async def create_schedule_once(
        self, command: ScheduleCreateCommand
    ) -> ConnectedScheduleView: ...

    async def readback_schedule_create(
        self, *, owner_id: str, request_id: str
    ) -> ConnectedScheduleView | None: ...

    async def transition_schedule_once(
        self, command: ScheduleTransitionCommand
    ) -> ConnectedScheduleView: ...

    async def readback_schedule_transition(
        self, *, owner_id: str, schedule_id: str, request_id: str
    ) -> ConnectedScheduleView | None: ...

    async def list_actions(self, *, owner_id: str) -> tuple[ConnectedActionView, ...]: ...

    async def get_action(self, *, owner_id: str, action_id: str) -> ConnectedActionView | None: ...

    async def list_approvals(self, *, owner_id: str) -> tuple[ConnectedApprovalView, ...]: ...

    async def get_approval(
        self, *, owner_id: str, approval_id: str
    ) -> ConnectedApprovalView | None: ...

    async def decide_approval_once(
        self, command: ApprovalDecisionCommand
    ) -> ConnectedApprovalView: ...

    async def readback_approval_decision(
        self, *, owner_id: str, approval_id: str, decision_id: str
    ) -> ConnectedApprovalView | None: ...


T = TypeVar("T")


class ConnectedAppService:
    """Validate owner/user commands and delegate to one durable control plane."""

    def __init__(
        self,
        *,
        control_plane: ConnectedAppControlPlane,
        readiness_source: Callable[[], ConnectedAppReadiness],
        expected_composition_manifest_sha256: str,
        redirect_allowlist: dict[ConnectorProvider, frozenset[str]],
        oauth_client_ids: dict[ConnectorProvider, str],
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self._control_plane = control_plane
        if not callable(readiness_source):
            raise ValueError("readiness source is invalid")
        self._readiness_source = readiness_source
        self._expected_composition_manifest_sha256 = _sha(expected_composition_manifest_sha256)
        self._now = now
        if set(redirect_allowlist) != set(ConnectorProvider):
            raise ValueError("every provider requires an OAuth redirect allowlist")
        normalized: dict[ConnectorProvider, frozenset[str]] = {}
        for provider, values in redirect_allowlist.items():
            if not isinstance(values, frozenset) or not values:
                raise ValueError("redirect allowlist must be nonempty")
            try:
                checked = OAuthRedirectAllowlist(values)
            except (TypeError, ValueError):
                raise ValueError("redirect allowlist contains an invalid URI") from None
            normalized[provider] = checked.allowed_redirect_uris
        self._redirect_allowlist = normalized
        if set(oauth_client_ids) != set(ConnectorProvider):
            raise ValueError("every provider requires an expected OAuth client ID")
        normalized_client_ids: dict[ConnectorProvider, str] = {}
        for provider, client_id in oauth_client_ids.items():
            if not isinstance(client_id, str) or not _OAUTH_CLIENT_ID.fullmatch(client_id):
                raise ValueError("OAuth client ID is invalid")
            normalized_client_ids[provider] = client_id
        self._oauth_client_ids = normalized_client_ids

    @property
    def readiness(self) -> ConnectedAppReadiness:
        readiness = self._readiness_source()
        if type(readiness) is not ConnectedAppReadiness:
            raise ValueError("readiness source returned an invalid attestation")
        return readiness

    def require_ready(self) -> None:
        reference = _aware(self._now())
        try:
            readiness = self.readiness
        except Exception:
            raise ConnectedAppServiceError("CONNECTED_APPS_NOT_READY", 503) from None
        if (
            not readiness.ready
            or readiness.composition_manifest_sha256
            != self._expected_composition_manifest_sha256
            or readiness.checked_at > reference + _READINESS_FUTURE_SKEW
            or readiness.expires_at <= reference
        ):
            raise ConnectedAppServiceError("CONNECTED_APPS_NOT_READY", 503)

    def public_readiness_manifest(self) -> dict[str, object]:
        """Return the exact public capability surface of this ready composition.

        OAuth client identifiers are public protocol identifiers, not secrets.
        The method still refuses to expose them until the independently supplied
        composition attestation is current and exact.  Returning fresh containers
        prevents callers from mutating the service's private configuration.
        """

        self.require_ready()
        providers = tuple(sorted(ConnectorProvider, key=lambda item: item.value))
        actions = tuple(sorted((item.value for item in implemented_runtime_actions())))
        return {
            "providers": [provider.value for provider in providers],
            "capabilities": {provider.value: list(actions) for provider in providers},
            "oauthClientIds": {
                provider.value: self._oauth_client_ids[provider] for provider in providers
            },
        }

    async def list_connections(self, *, owner_id: str) -> tuple[ConnectedConnectionView, ...]:
        self.require_ready()
        owner_id = _uuid(owner_id, "owner_id")
        result = await self._dependency(
            lambda: self._control_plane.list_connections(owner_id=owner_id),
            "CONNECTED_CONNECTION_LIST_FAILED",
        )
        return self._records(result, ConnectedConnectionView)

    async def start_oauth(
        self,
        *,
        request_id: str,
        owner_id: str,
        session_id: str,
        provider: ConnectorProvider,
        resource: ConnectorResource,
        account_kind: ConnectorAccountKind,
        actions: frozenset[ConnectorActionKind],
        redirect_uri: str,
        connection_id: str | None,
        confirmed: bool,
    ) -> OAuthStartView:
        self.require_ready()
        if confirmed is not True:
            raise ConnectedAppServiceError("CONNECTED_USER_ACTION_REQUIRED", 400)
        if redirect_uri not in self._redirect_allowlist.get(provider, frozenset()):
            raise ConnectedAppServiceError("CONNECTED_OAUTH_REDIRECT_NOT_ALLOWED", 400)
        command = OAuthStartCommand(
            request_id=_uuid(request_id, "request_id"),
            owner_id=_uuid(owner_id, "owner_id"),
            session_binding_sha256=_digest_text(_uuid(session_id, "session_id")),
            provider=provider,
            resource=resource,
            account_kind=account_kind,
            actions=actions,
            redirect_uri=redirect_uri,
            connection_id=connection_id,
            requested_at=_aware(self._now()),
        )
        try:
            result = await self._dependency(
                lambda: self._control_plane.start_oauth_once(command),
                "CONNECTED_OAUTH_START_FAILED",
            )
        except ConnectedAppServiceError:
            result = await self._dependency(
                lambda: self._control_plane.readback_oauth_start(
                    owner_id=command.owner_id,
                    request_id=command.request_id,
                ),
                "CONNECTED_OAUTH_START_FAILED",
            )
            if result is None:
                raise ConnectedAppServiceError(
                    "CONNECTED_OAUTH_START_FAILED", 503, retryable=True
                ) from None
        if (
            type(result) is not OAuthStartView
            or result.request_id != command.request_id
            or result.provider is not command.provider
            or (command.connection_id is not None and result.connection_id != command.connection_id)
            or result.expires_at <= command.requested_at
            or result.expires_at - command.requested_at > timedelta(minutes=10)
            or result.command_binding_sha256
            != oauth_start_result_binding_sha256(
                command,
                flow_id=result.flow_id,
                connection_id=result.connection_id,
                authorization_url=result.authorization_url,
                state_sha256=result.state_sha256,
                pkce_challenge=result.pkce_challenge,
                expires_at=result.expires_at,
            )
        ):
            raise ConnectedAppServiceError("CONNECTED_OAUTH_START_RESULT_INVALID", 502)
        parameters = result.query_parameters()
        try:
            scope_plan = delegated_scope_plan(
                command.provider,
                command.actions,
                account_kind=command.account_kind,
            )
        except ConnectedAppScopeError:
            raise ConnectedAppServiceError("CONNECTED_OAUTH_START_RESULT_INVALID", 502) from None
        returned_scopes = parameters["scope"].split(" ")
        expected_microsoft_path = (
            "/consumers/oauth2/v2.0/authorize"
            if command.account_kind is ConnectorAccountKind.PERSONAL
            else "/organizations/oauth2/v2.0/authorize"
        )
        if (
            parameters["client_id"] != self._oauth_client_ids[command.provider]
            or parameters["redirect_uri"] != command.redirect_uri
            or tuple(sorted(returned_scopes)) != scope_plan.delegated_scopes
            or (
                command.provider is ConnectorProvider.MICROSOFT
                and urlsplit(result.authorization_url).path != expected_microsoft_path
            )
        ):
            raise ConnectedAppServiceError("CONNECTED_OAUTH_START_RESULT_INVALID", 502)
        return result

    async def complete_oauth_callback(
        self,
        *,
        owner_id: str,
        session_id: str,
        provider: ConnectorProvider,
        state: str,
        code: str,
    ) -> ConnectedConnectionView:
        self.require_ready()
        command = OAuthCallbackCommand.build(
            owner_id=owner_id,
            session_id=session_id,
            provider=provider,
            state=state,
            code=code,
            received_at=_aware(self._now()),
        )
        try:
            result = await self._dependency(
                lambda: self._control_plane.complete_oauth_callback(command),
                "CONNECTED_OAUTH_CALLBACK_FAILED",
            )
        except ConnectedAppServiceError:
            result = await self._dependency(
                lambda: self._control_plane.readback_oauth_callback(
                    provider=provider,
                    callback_binding_sha256=command.callback_binding_sha256,
                ),
                "CONNECTED_OAUTH_CALLBACK_FAILED",
            )
            if result is None:
                raise ConnectedAppServiceError(
                    "CONNECTED_OAUTH_CALLBACK_FAILED", 503, retryable=False
                ) from None
        if (
            type(result) is not ConnectedConnectionView
            or result.provider is not provider
            or result.authorization_state is not ConnectionAuthorizationState.ACTIVE
        ):
            raise ConnectedAppServiceError("CONNECTED_OAUTH_CALLBACK_RESULT_INVALID", 502)
        return result

    async def deny_oauth_callback(
        self,
        *,
        owner_id: str,
        session_id: str,
        provider: ConnectorProvider,
        state: str,
        error: str,
    ) -> None:
        self.require_ready()
        if error != "access_denied" or not isinstance(provider, ConnectorProvider):
            raise ConnectedAppServiceError("CONNECTED_OAUTH_CALLBACK_INVALID", 400)
        try:
            state_secret = OAuthStateSecret(state)
        except (TypeError,ValueError):
            raise ConnectedAppServiceError("CONNECTED_OAUTH_CALLBACK_INVALID", 400) from None
        await self._dependency(
            lambda: self._control_plane.deny_oauth_callback(
                owner_id=_uuid(owner_id, "owner_id"),
                session_binding_sha256=_digest_text(_uuid(session_id, "session_id")),
                provider=provider,
                state_sha256=_digest_text(state_secret.value),
                received_at=_aware(self._now()),
            ),
            "CONNECTED_OAUTH_CALLBACK_FAILED",
        )

    async def disconnect(
        self,
        *,
        request_id: str,
        owner_id: str,
        session_id: str,
        connection_id: str,
        confirmed: bool,
    ) -> DisconnectView:
        self.require_ready()
        if confirmed is not True:
            raise ConnectedAppServiceError("CONNECTED_USER_ACTION_REQUIRED", 400)
        command = DisconnectCommand(
            request_id=request_id,
            owner_id=owner_id,
            session_binding_sha256=_digest_text(_uuid(session_id, "session_id")),
            connection_id=connection_id,
            requested_at=_aware(self._now()),
        )
        try:
            result = await self._dependency(
                lambda: self._control_plane.disconnect_once(command),
                "CONNECTED_DISCONNECT_FAILED",
            )
        except ConnectedAppServiceError:
            result = await self._dependency(
                lambda: self._control_plane.readback_disconnect(
                    owner_id=command.owner_id,
                    connection_id=command.connection_id,
                    request_id=command.request_id,
                ),
                "CONNECTED_DISCONNECT_FAILED",
            )
            if result is None:
                raise ConnectedAppServiceError(
                    "CONNECTED_DISCONNECT_FAILED", 503, retryable=True
                ) from None
        if (
            type(result) is not DisconnectView
            or result.connection.connection_id != command.connection_id
        ):
            raise ConnectedAppServiceError("CONNECTED_DISCONNECT_RESULT_INVALID", 502)
        return result

    async def list_schedules(self, *, owner_id: str) -> tuple[ConnectedScheduleView, ...]:
        self.require_ready()
        owner_id = _uuid(owner_id, "owner_id")
        result = await self._dependency(
            lambda: self._control_plane.list_schedules(owner_id=owner_id),
            "CONNECTED_SCHEDULE_LIST_FAILED",
        )
        return self._records(result, ConnectedScheduleView)

    async def create_schedule(
        self,
        *,
        request_id: str,
        owner_id: str,
        session_id: str,
        connection_id: str,
        task_id: str,
        provider: ConnectorProvider,
        resource: ConnectorResource,
        action: ConnectorActionKind,
        action_template_ref: str,
        parameters_sha256: str,
        time_zone: str,
        cadence_seconds: int,
        quiet_start: str | None,
        quiet_end: str | None,
        requires_approval_every_run: bool,
        confirmed: bool,
    ) -> ConnectedScheduleView:
        self.require_ready()
        if confirmed is not True:
            raise ConnectedAppServiceError("CONNECTED_USER_ACTION_REQUIRED", 400)
        command = ScheduleCreateCommand(
            request_id=request_id,
            owner_id=owner_id,
            session_binding_sha256=_digest_text(_uuid(session_id, "session_id")),
            connection_id=connection_id,
            task_id=task_id,
            provider=provider,
            resource=resource,
            action=action,
            action_template_ref=action_template_ref,
            parameters_sha256=parameters_sha256,
            time_zone=time_zone,
            cadence_seconds=cadence_seconds,
            quiet_start_minute=_parse_quiet(quiet_start),
            quiet_end_minute=_parse_quiet(quiet_end),
            requires_approval_every_run=requires_approval_every_run,
            requested_at=_aware(self._now()),
        )
        authority = await self._dependency(
            lambda: self._control_plane.get_connection_authority(
                owner_id=command.owner_id,
                connection_id=command.connection_id,
            ),
            "CONNECTED_CONNECTION_AUTHORITY_READ_FAILED",
        )
        if (
            type(authority) is not ConnectedConnectionAuthorityView
            or authority.connection_id != command.connection_id
            or authority.provider is not command.provider
            or authority.resource is not command.resource
            or command.action not in authority.granted_actions
            or authority.expires_at <= command.requested_at
        ):
            raise ConnectedAppServiceError("CONNECTED_ACTION_NOT_GRANTED", 409)
        try:
            result = await self._dependency(
                lambda: self._control_plane.create_schedule_once(command),
                "CONNECTED_SCHEDULE_CREATE_FAILED",
            )
        except ConnectedAppServiceError:
            result = await self._dependency(
                lambda: self._control_plane.readback_schedule_create(
                    owner_id=command.owner_id, request_id=command.request_id
                ),
                "CONNECTED_SCHEDULE_CREATE_FAILED",
            )
            if result is None:
                raise ConnectedAppServiceError(
                    "CONNECTED_SCHEDULE_CREATE_FAILED", 503, retryable=True
                ) from None
        if not schedule_create_result_matches(command, result):
            raise ConnectedAppServiceError("CONNECTED_SCHEDULE_RESULT_INVALID", 502)
        return result

    async def transition_schedule(
        self,
        *,
        request_id: str,
        owner_id: str,
        session_id: str,
        schedule_id: str,
        expected_task_state_revision: int,
        expected_status: ConnectedScheduleStatus,
        target: ConnectedScheduleStatus,
        confirmed: bool,
    ) -> ConnectedScheduleView:
        self.require_ready()
        if confirmed is not True:
            raise ConnectedAppServiceError("CONNECTED_USER_ACTION_REQUIRED", 400)
        command = ScheduleTransitionCommand(
            request_id=request_id,
            owner_id=owner_id,
            session_binding_sha256=_digest_text(_uuid(session_id, "session_id")),
            schedule_id=schedule_id,
            expected_task_state_revision=expected_task_state_revision,
            expected_status=expected_status,
            target=target,
            requested_at=_aware(self._now()),
        )
        current = await self._dependency(
            lambda: self._control_plane.get_schedule(
                owner_id=command.owner_id,
                schedule_id=command.schedule_id,
            ),
            "CONNECTED_SCHEDULE_READ_FAILED",
        )
        if current is None:
            raise ConnectedAppServiceError("CONNECTED_SCHEDULE_NOT_FOUND", 404)
        if (
            type(current) is not ConnectedScheduleView
            or current.schedule_id != command.schedule_id
            or current.status is not command.expected_status
            or current.task_state_revision != command.expected_task_state_revision
            or not schedule_transition_allowed(current.status, command.target)
        ):
            raise ConnectedAppServiceError("CONNECTED_SCHEDULE_TRANSITION_INVALID", 409)
        try:
            result = await self._dependency(
                lambda: self._control_plane.transition_schedule_once(command),
                "CONNECTED_SCHEDULE_TRANSITION_FAILED",
            )
        except ConnectedAppServiceError:
            result = await self._dependency(
                lambda: self._control_plane.readback_schedule_transition(
                    owner_id=command.owner_id,
                    schedule_id=command.schedule_id,
                    request_id=command.request_id,
                ),
                "CONNECTED_SCHEDULE_TRANSITION_FAILED",
            )
            if result is None:
                raise ConnectedAppServiceError(
                    "CONNECTED_SCHEDULE_TRANSITION_FAILED", 503, retryable=True
                ) from None
        if (
            type(result) is not ConnectedScheduleView
            or result.schedule_id != command.schedule_id
            or result.status is not target
            or result.task_state_revision != command.expected_task_state_revision + 1
            or result.connection_id != current.connection_id
            or result.task_id != current.task_id
            or result.provider is not current.provider
            or result.resource is not current.resource
            or result.action is not current.action
            or result.action_template_ref != current.action_template_ref
            or result.parameters_sha256 != current.parameters_sha256
            or result.time_zone != current.time_zone
            or result.cadence_seconds != current.cadence_seconds
            or result.quiet_start_minute != current.quiet_start_minute
            or result.quiet_end_minute != current.quiet_end_minute
            or result.requires_approval_every_run is not current.requires_approval_every_run
            or (
                result.status is ConnectedScheduleStatus.ACTIVE
                and (
                    result.next_run_at is None
                    or result.next_run_at <= command.requested_at
                    or result.next_run_at
                    > command.requested_at
                    + timedelta(seconds=result.cadence_seconds)
                    + _MAX_SCHEDULE_QUIET_DELAY
                )
            )
        ):
            raise ConnectedAppServiceError("CONNECTED_SCHEDULE_RESULT_INVALID", 502)
        return result

    async def list_actions(self, *, owner_id: str) -> tuple[ConnectedActionView, ...]:
        self.require_ready()
        owner_id = _uuid(owner_id, "owner_id")
        result = await self._dependency(
            lambda: self._control_plane.list_actions(owner_id=owner_id),
            "CONNECTED_ACTION_LIST_FAILED",
        )
        return self._records(result, ConnectedActionView)

    async def get_action(self, *, owner_id: str, action_id: str) -> ConnectedActionView:
        self.require_ready()
        owner_id = _uuid(owner_id, "owner_id")
        action_id = _uuid(action_id, "action_id")
        result = await self._dependency(
            lambda: self._control_plane.get_action(owner_id=owner_id, action_id=action_id),
            "CONNECTED_ACTION_READ_FAILED",
        )
        if result is None:
            raise ConnectedAppServiceError("CONNECTED_ACTION_NOT_FOUND", 404)
        if type(result) is not ConnectedActionView or result.action_id != action_id:
            raise ConnectedAppServiceError("CONNECTED_ACTION_RESULT_INVALID", 502)
        return result

    async def list_approvals(self, *, owner_id: str) -> tuple[ConnectedApprovalView, ...]:
        self.require_ready()
        owner_id = _uuid(owner_id, "owner_id")
        result = await self._dependency(
            lambda: self._control_plane.list_approvals(owner_id=owner_id),
            "CONNECTED_APPROVAL_LIST_FAILED",
        )
        records = self._records(result, ConnectedApprovalView)
        encoded_size = 2
        for index, record in enumerate(records):
            encoded_size += len(
                json.dumps(
                    record.public(),
                    ensure_ascii=False,
                    separators=(",", ":"),
                ).encode("utf-8")
            )
            if index:
                encoded_size += 1
            if encoded_size > _MAX_APPROVAL_RESPONSE_BYTES:
                raise ConnectedAppServiceError("CONNECTED_RESULT_INVALID", 502)
        return records

    async def decide_approval(
        self,
        *,
        decision_id: str,
        owner_id: str,
        session_id: str,
        approval_id: str,
        action_id: str,
        connection_id: str,
        task_id: str,
        turn_id: str,
        provider: ConnectorProvider,
        resource: ConnectorResource,
        action: ConnectorActionKind,
        authorization_revision: int,
        authorization_snapshot_sha256: str,
        granted_scopes_sha256: str,
        policy_version: str,
        action_revision: int,
        approval_binding_sha256: str,
        parameters_sha256: str,
        resource_version_sha256: str | None,
        preview_sha256: str,
        decision: ConnectedApprovalDecision,
        confirmed: bool,
    ) -> ConnectedApprovalView:
        self.require_ready()
        if confirmed is not True:
            raise ConnectedAppServiceError("CONNECTED_USER_ACTION_REQUIRED", 400)
        command = ApprovalDecisionCommand(
            decision_id=decision_id,
            owner_id=owner_id,
            session_binding_sha256=_digest_text(_uuid(session_id, "session_id")),
            approval_id=approval_id,
            action_id=action_id,
            connection_id=connection_id,
            task_id=task_id,
            turn_id=turn_id,
            provider=provider,
            resource=resource,
            action=action,
            authorization_revision=authorization_revision,
            authorization_snapshot_sha256=authorization_snapshot_sha256,
            granted_scopes_sha256=granted_scopes_sha256,
            policy_version=policy_version,
            action_revision=action_revision,
            approval_binding_sha256=approval_binding_sha256,
            parameters_sha256=parameters_sha256,
            resource_version_sha256=resource_version_sha256,
            preview_sha256=preview_sha256,
            decision=decision,
            decided_at=_aware(self._now()),
        )
        expected_status = (
            ConnectedApprovalStatus.APPROVED
            if decision is ConnectedApprovalDecision.APPROVED
            else ConnectedApprovalStatus.DENIED
        )
        pending = await self._dependency(
            lambda: self._control_plane.get_approval(
                owner_id=command.owner_id,
                approval_id=command.approval_id,
            ),
            "CONNECTED_APPROVAL_READ_FAILED",
        )
        if pending is None:
            raise ConnectedAppServiceError("CONNECTED_APPROVAL_NOT_FOUND", 404)
        if not self._approval_bindings_match(pending, command):
            raise ConnectedAppServiceError("CONNECTED_APPROVAL_BINDING_MISMATCH", 409)
        # A completed decision is an idempotent readback, not a fresh external
        # write.  Return the exact prior decision even if the action has since
        # advanced or the delegated connection has since been revoked.
        if pending.status is not ConnectedApprovalStatus.PENDING:
            readback = await self._dependency(
                lambda: self._control_plane.readback_approval_decision(
                    owner_id=command.owner_id,
                    approval_id=command.approval_id,
                    decision_id=command.decision_id,
                ),
                "CONNECTED_APPROVAL_DECISION_FAILED",
            )
            if self._approval_result_matches(readback, command, expected_status):
                if (
                    len(
                        json.dumps(
                            readback.public(),
                            ensure_ascii=False,
                            separators=(",", ":"),
                        ).encode("utf-8")
                    )
                    > _MAX_APPROVAL_RESPONSE_BYTES
                ):
                    raise ConnectedAppServiceError("CONNECTED_APPROVAL_RESULT_INVALID", 502)
                return readback
            raise ConnectedAppServiceError("CONNECTED_APPROVAL_ALREADY_DECIDED", 409)
        current_action = await self._dependency(
            lambda: self._control_plane.get_action(
                owner_id=command.owner_id,
                action_id=command.action_id,
            ),
            "CONNECTED_ACTION_READ_FAILED",
        )
        authority = await self._dependency(
            lambda: self._control_plane.get_connection_authority(
                owner_id=command.owner_id,
                connection_id=command.connection_id,
            ),
            "CONNECTED_CONNECTION_AUTHORITY_READ_FAILED",
        )
        if not self._action_bindings_match(
            current_action, command
        ) or not self._authority_bindings_match(authority, command):
            raise ConnectedAppServiceError("CONNECTED_APPROVAL_BINDING_MISMATCH", 409)
        if (
            pending.expires_at <= command.decided_at
            or pending.expires_at - command.decided_at > _APPROVAL_MAX_TTL
            or authority.expires_at <= command.decided_at
        ):
            raise ConnectedAppServiceError("CONNECTED_APPROVAL_EXPIRED", 409)
        try:
            result = await self._dependency(
                lambda: self._control_plane.decide_approval_once(command),
                "CONNECTED_APPROVAL_DECISION_FAILED",
            )
        except ConnectedAppServiceError:
            result = await self._dependency(
                lambda: self._control_plane.readback_approval_decision(
                    owner_id=command.owner_id,
                    approval_id=command.approval_id,
                    decision_id=command.decision_id,
                ),
                "CONNECTED_APPROVAL_DECISION_FAILED",
            )
            if result is None:
                raise ConnectedAppServiceError(
                    "CONNECTED_APPROVAL_DECISION_FAILED", 503, retryable=True
                ) from None
        if not self._approval_result_matches(result, command, expected_status):
            raise ConnectedAppServiceError("CONNECTED_APPROVAL_RESULT_INVALID", 502)
        if (
            len(
                json.dumps(
                    result.public(),
                    ensure_ascii=False,
                    separators=(",", ":"),
                ).encode("utf-8")
            )
            > _MAX_APPROVAL_RESPONSE_BYTES
        ):
            raise ConnectedAppServiceError("CONNECTED_APPROVAL_RESULT_INVALID", 502)
        return result

    @staticmethod
    def _approval_result_matches(
        result: object,
        command: ApprovalDecisionCommand,
        expected_status: ConnectedApprovalStatus,
    ) -> bool:
        return bool(
            type(result) is ConnectedApprovalView
            and ConnectedAppService._approval_bindings_match(result, command)
            and result.decision_id == command.decision_id
            and result.decision_session_binding_sha256 == command.session_binding_sha256
            and result.status is expected_status
            and result.decided_at is not None
            and result.decided_at <= result.expires_at
        )

    @staticmethod
    def _approval_bindings_match(
        result: object,
        command: ApprovalDecisionCommand,
    ) -> bool:
        return bool(
            type(result) is ConnectedApprovalView
            and result.approval_id == command.approval_id
            and result.action_id == command.action_id
            and result.connection_id == command.connection_id
            and result.task_id == command.task_id
            and result.turn_id == command.turn_id
            and result.provider is command.provider
            and result.resource is command.resource
            and result.action is command.action
            and result.authorization_revision == command.authorization_revision
            and result.authorization_snapshot_sha256 == command.authorization_snapshot_sha256
            and result.granted_scopes_sha256 == command.granted_scopes_sha256
            and result.policy_version == command.policy_version
            and result.action_revision == command.action_revision
            and result.approval_binding_sha256 == command.approval_binding_sha256
            and result.parameters_sha256 == command.parameters_sha256
            and result.resource_version_sha256 == command.resource_version_sha256
            and result.preview_sha256 == command.preview_sha256
        )

    @staticmethod
    def _action_bindings_match(
        result: object,
        command: ApprovalDecisionCommand,
    ) -> bool:
        return bool(
            type(result) is ConnectedActionView
            and result.action_id == command.action_id
            and result.connection_id == command.connection_id
            and result.task_id == command.task_id
            and result.turn_id == command.turn_id
            and result.provider is command.provider
            and result.resource is command.resource
            and result.action is command.action
            and result.authorization_revision == command.authorization_revision
            and result.authorization_snapshot_sha256 == command.authorization_snapshot_sha256
            and result.granted_scopes_sha256 == command.granted_scopes_sha256
            and result.policy_version == command.policy_version
            and result.action_revision == command.action_revision
            and result.parameters_sha256 == command.parameters_sha256
            and result.resource_version_sha256 == command.resource_version_sha256
            and result.preview_sha256 == command.preview_sha256
            and result.status is ConnectedActionPublicStatus.PENDING_APPROVAL
        )

    @staticmethod
    def _authority_bindings_match(
        result: object,
        command: ApprovalDecisionCommand,
    ) -> bool:
        return bool(
            type(result) is ConnectedConnectionAuthorityView
            and result.connection_id == command.connection_id
            and result.provider is command.provider
            and result.resource is command.resource
            and result.authorization_revision == command.authorization_revision
            and result.authorization_snapshot_sha256 == command.authorization_snapshot_sha256
            and result.granted_scopes_sha256 == command.granted_scopes_sha256
            and command.action in result.granted_actions
        )

    async def _dependency(
        self,
        factory: Callable[[], Awaitable[T]],
        failure_code: str,
    ) -> T:
        """Quarantine dependency details and bound ordinary waits.

        Production composition must still use killable transports.  This layer
        never detaches a provider write; it only wraps content-free repository
        and coordinator calls.
        """

        try:
            awaitable = factory()
        except Exception:
            raise ConnectedAppServiceError(failure_code, 503, retryable=True) from None
        if not inspect.isawaitable(awaitable):
            raise ConnectedAppServiceError(failure_code, 502) from None
        try:
            import asyncio

            return await asyncio.wait_for(awaitable, timeout=_MAX_DEPENDENCY_SECONDS)
        except Exception:
            raise ConnectedAppServiceError(failure_code, 503, retryable=True) from None

    @staticmethod
    def _records(value: object, expected: type[T]) -> tuple[T, ...]:
        if not isinstance(value, tuple) or len(value) > _MAX_PUBLIC_ITEMS:
            raise ConnectedAppServiceError("CONNECTED_RESULT_INVALID", 502)
        if any(type(item) is not expected for item in value):
            raise ConnectedAppServiceError("CONNECTED_RESULT_INVALID", 502)
        return value


def parse_provider(value: object) -> ConnectorProvider:
    try:
        return ConnectorProvider(value)
    except (ValueError, TypeError):
        raise ConnectedAppServiceError("CONNECTED_INPUT_INVALID", 400) from None


def parse_resource(value: object) -> ConnectorResource:
    try:
        return ConnectorResource(value)
    except (ValueError, TypeError):
        raise ConnectedAppServiceError("CONNECTED_INPUT_INVALID", 400) from None


def parse_account_kind(value: object) -> ConnectorAccountKind:
    try:
        return ConnectorAccountKind(value)
    except (ValueError, TypeError):
        raise ConnectedAppServiceError("CONNECTED_INPUT_INVALID", 400) from None


def parse_action(value: object) -> ConnectorActionKind:
    try:
        return ConnectorActionKind(value)
    except (ValueError, TypeError):
        raise ConnectedAppServiceError("CONNECTED_INPUT_INVALID", 400) from None


def parse_actions(value: object) -> frozenset[ConnectorActionKind]:
    if not isinstance(value, list) or not 1 <= len(value) <= 16:
        raise ConnectedAppServiceError("CONNECTED_INPUT_INVALID", 400)
    actions = tuple(parse_action(item) for item in value)
    if len(set(actions)) != len(actions):
        raise ConnectedAppServiceError("CONNECTED_INPUT_INVALID", 400)
    return frozenset(actions)


def parse_schedule_status(value: object) -> ConnectedScheduleStatus:
    try:
        return ConnectedScheduleStatus(value)
    except (ValueError, TypeError):
        raise ConnectedAppServiceError("CONNECTED_INPUT_INVALID", 400) from None


def parse_approval_decision(value: object) -> ConnectedApprovalDecision:
    try:
        return ConnectedApprovalDecision(value)
    except (ValueError, TypeError):
        raise ConnectedAppServiceError("CONNECTED_INPUT_INVALID", 400) from None


def new_operation_id() -> str:
    return str(uuid4())
