"""Provider-neutral, content-safe contracts for owner-connected applications.

These types deliberately separate opaque control-plane identity from email and
calendar content.  Provider tokens never cross this boundary.  Mail and event
payloads are always marked as untrusted data and are excluded from ``repr`` so
logs cannot accidentally turn customer content into audit metadata.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import StrEnum
import hashlib
import json
import re
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .connected_app_policy import (
    ConnectorActionKind,
    ConnectorProvider,
    ConnectorResource,
    action_set_sha256,
)


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_OPAQUE_HANDLE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+=-]{15,255}$")
_PROVIDER_ID = re.compile(r"^[^\x00-\x20\x7f]{1,512}$")
_RESOURCE_VERSION = re.compile(r"^[^\x00-\x1f\x7f]{1,512}$")
_LABEL = re.compile(r"^[^\x00-\x1f\x7f]{1,200}$")
_IDEMPOTENCY_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{15,199}$")
_IANA_SEGMENT = re.compile(r"^[A-Za-z][A-Za-z0-9_+.-]{0,63}$")
_IANA_AREAS = frozenset(
    {
        "Africa",
        "America",
        "Antarctica",
        "Arctic",
        "Asia",
        "Atlantic",
        "Australia",
        "Europe",
        "Indian",
        "Pacific",
        "Etc",
    }
)
_DOMAIN_LABEL = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")

UNTRUSTED_EXTERNAL_DATA = "untrusted_external_data"
UNTRUSTED_PROPOSED_CONTENT = "untrusted_proposed_content"
_AUTHORIZATION_BINDING_VERSION = "connected-authorization-v2"


def _uuid(value: str, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a UUID string")
    try:
        parsed = UUID(value)
    except (ValueError, AttributeError) as exc:
        raise ValueError(f"{name} must be a UUID") from exc
    canonical = str(parsed)
    if value != canonical:
        raise ValueError(f"{name} must use canonical lowercase UUID form")
    return canonical


def _sha256(value: str, name: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ValueError(f"{name} must be a lowercase SHA-256 digest")
    return value


def _opaque_handle(value: str, name: str) -> str:
    if not isinstance(value, str) or not _OPAQUE_HANDLE.fullmatch(value):
        raise ValueError(f"{name} must be an opaque non-secret handle")
    return value


def _provider_id(value: str, name: str) -> str:
    if not isinstance(value, str) or not _PROVIDER_ID.fullmatch(value):
        raise ValueError(f"{name} must be a bounded opaque provider identifier")
    return value


def _resource_version(value: str, name: str = "resource_version") -> str:
    if not isinstance(value, str) or not _RESOURCE_VERSION.fullmatch(value):
        raise ValueError(f"{name} must be a bounded provider resource version")
    return value


def _aware(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value


def _utc_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _utc(value: datetime, name: str) -> datetime:
    return _aware(value, name).astimezone(timezone.utc)


def _scope(value: str) -> str:
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= 512
        or value != value.strip()
        or any(char.isspace() or ord(char) < 33 or ord(char) == 127 for char in value)
    ):
        raise ValueError("granted scopes must be bounded non-whitespace strings")
    return value


def _scope_set_hash(scopes: frozenset[str]) -> str:
    encoded = json.dumps(
        sorted(scopes),
        ensure_ascii=True,
        separators=(",", ":"),
    ).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


def _canonical_sha256(value: dict[str, Any]) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _exact_binding(actual: str, expected: str) -> str:
    normalized = _sha256(actual, "target_binding_sha256")
    if normalized != expected:
        raise ValueError("target_binding_sha256 does not match the exact provider target")
    return normalized


def _zone(value: str) -> ZoneInfo:
    if not isinstance(value, str) or not value or len(value) > 100:
        raise ValueError("time_zone must be a bounded IANA timezone")
    if value not in {"UTC", "GMT"}:
        parts = value.split("/")
        if (
            len(parts) < 2
            or len(parts) > 3
            or parts[0] not in _IANA_AREAS
            or any(not _IANA_SEGMENT.fullmatch(part) for part in parts)
        ):
            raise ValueError("time_zone must use a valid IANA timezone identifier")
    try:
        return ZoneInfo(value)
    except ZoneInfoNotFoundError as exc:
        raise ValueError("time_zone must name an installed IANA timezone") from exc


def _timezone(value: str) -> str:
    return _zone(value).key


def _zoned_datetime(value: datetime, time_zone: str, name: str) -> datetime:
    aware = _aware(value, name)
    zone = _zone(time_zone)
    local_wall_time = aware.replace(tzinfo=None)
    zoned_candidate = local_wall_time.replace(tzinfo=zone, fold=aware.fold)
    round_trip = zoned_candidate.astimezone(timezone.utc).astimezone(zone)
    if (
        round_trip.replace(tzinfo=None) != local_wall_time
        or round_trip.fold != aware.fold
        or aware.utcoffset() != zoned_candidate.utcoffset()
    ):
        raise ValueError(
            f"{name} is nonexistent, incorrectly folded, or mismatched to time_zone"
        )
    return aware


def _external_text(value: str, name: str, *, limit: int, allow_empty: bool) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be text")
    if any(ord(char) < 32 and char not in "\t\r\n" for char in value) or "\x7f" in value:
        raise ValueError(f"{name} contains forbidden control characters")
    if any(
        char in value
        for char in (
            "\u061c",
            "\u200e",
            "\u200f",
            "\u202a",
            "\u202b",
            "\u202c",
            "\u202d",
            "\u202e",
            "\u2066",
            "\u2067",
            "\u2068",
            "\u2069",
        )
    ):
        raise ValueError(f"{name} contains forbidden bidirectional controls")
    if not allow_empty and not value.strip():
        raise ValueError(f"{name} cannot be empty")
    if len(value.encode("utf-8")) > limit:
        raise ValueError(f"{name} exceeds its byte limit")
    return value


def _single_line_external_text(
    value: str,
    name: str,
    *,
    limit: int,
    allow_empty: bool,
) -> str:
    """Validate outbound text that will occupy one provider header/field.

    Newlines are valid inside message bodies and event descriptions, but never
    inside subjects, titles, or locations.  Rejecting them at the provider-
    neutral boundary prevents a later raw-MIME adapter from receiving a value
    that could be interpreted as an injected header.
    """

    normalized = _external_text(value, name, limit=limit, allow_empty=allow_empty)
    if any(separator in normalized for separator in ("\r", "\n", "\x85", "\u2028", "\u2029")):
        raise ValueError(f"{name} must be a single line")
    return normalized


def _label(value: str, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be text")
    normalized = " ".join(value.split())
    if not _LABEL.fullmatch(normalized):
        raise ValueError(f"{name} must be a bounded printable label")
    return normalized


def _email_address(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError("recipient addresses must be text")
    candidate = value.strip()
    if (
        len(candidate) > 320
        or candidate.count("@") != 1
        or any(char.isspace() or ord(char) < 33 or ord(char) == 127 for char in candidate)
        or any(char in candidate for char in "<>()[],:;\\\"")
        or any(
            char in candidate
            for char in (
                "\u061c",
                "\u200e",
                "\u200f",
                "\u202a",
                "\u202b",
                "\u202c",
                "\u202d",
                "\u202e",
                "\u2066",
                "\u2067",
                "\u2068",
                "\u2069",
            )
        )
    ):
        raise ValueError("recipient address is invalid")
    local, domain = candidate.rsplit("@", 1)
    if not local or len(local.encode("utf-8")) > 64 or not domain or "." not in domain:
        raise ValueError("recipient address is invalid")
    try:
        ascii_domain = domain.encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise ValueError("recipient address domain is invalid") from exc
    labels = ascii_domain.split(".")
    if (
        len(ascii_domain) > 255
        or len(labels) < 2
        or any(not _DOMAIN_LABEL.fullmatch(label) for label in labels)
        or local.startswith(".")
        or local.endswith(".")
        or ".." in local
    ):
        raise ValueError("recipient address domain is invalid")
    return f"{local}@{ascii_domain}"


def _addresses(values: tuple[str, ...], name: str, *, maximum: int) -> tuple[str, ...]:
    if not isinstance(values, tuple):
        raise TypeError(f"{name} must be a tuple")
    if len(values) > maximum:
        raise ValueError(f"{name} exceeds its recipient limit")
    normalized = tuple(_email_address(value) for value in values)
    if len({value.casefold() for value in normalized}) != len(normalized):
        raise ValueError(f"{name} contains duplicate recipients")
    return normalized


def _provider_ids(values: tuple[str, ...], name: str, *, maximum: int) -> tuple[str, ...]:
    if not isinstance(values, tuple):
        raise TypeError(f"{name} must be a tuple")
    if not values or len(values) > maximum:
        raise ValueError(f"{name} must contain between 1 and {maximum} identifiers")
    normalized = tuple(_provider_id(value, name) for value in values)
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{name} contains duplicate identifiers")
    return normalized


@dataclass(frozen=True, slots=True)
class ConnectedAccountRef:
    """Content-free reference to one owner-scoped provider resource."""

    owner_id: str
    connection_id: str
    provider: ConnectorProvider
    resource: ConnectorResource
    account_kind: ConnectorAccountKind
    external_account_id_hash: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "owner_id", _uuid(self.owner_id, "owner_id"))
        object.__setattr__(self, "connection_id", _uuid(self.connection_id, "connection_id"))
        if not isinstance(self.provider, ConnectorProvider):
            raise TypeError("provider must be a ConnectorProvider")
        if not isinstance(self.resource, ConnectorResource):
            raise TypeError("resource must be a ConnectorResource")
        if not isinstance(self.account_kind, ConnectorAccountKind):
            raise TypeError("account_kind must be a ConnectorAccountKind")
        object.__setattr__(
            self,
            "external_account_id_hash",
            _sha256(self.external_account_id_hash, "external_account_id_hash"),
        )


class ConnectorAccountKind(StrEnum):
    PERSONAL = "personal"
    WORK_SCHOOL = "work_school"


class ConnectionAuthorizationState(StrEnum):
    ACTIVE = "active"
    REVOKED = "revoked"


@dataclass(frozen=True, slots=True, repr=False)
class ConnectedAuthorizationSnapshot:
    """Server-owned delegated authority for one exact connection revision.

    ``revision`` is monotonic within a connection.  Callers bind the revision
    and ``snapshot_sha256`` into every intent and task grant, then re-read this
    snapshot immediately before credential issuance and provider execution.
    """

    owner_id: str
    connection_id: str
    provider: ConnectorProvider
    resource: ConnectorResource
    account_kind: ConnectorAccountKind
    revision: int
    granted_actions: frozenset[ConnectorActionKind] = field(repr=False)
    granted_actions_sha256: str
    granted_scopes: frozenset[str] = field(repr=False)
    granted_scopes_sha256: str
    state: ConnectionAuthorizationState
    issued_at: datetime
    expires_at: datetime
    revoked_at: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "owner_id", _uuid(self.owner_id, "owner_id"))
        object.__setattr__(self, "connection_id", _uuid(self.connection_id, "connection_id"))
        if not isinstance(self.provider, ConnectorProvider):
            raise TypeError("provider must be a ConnectorProvider")
        if not isinstance(self.resource, ConnectorResource):
            raise TypeError("resource must be a ConnectorResource")
        if not isinstance(self.account_kind, ConnectorAccountKind):
            raise TypeError("account_kind must be a ConnectorAccountKind")
        if type(self.revision) is not int or self.revision < 1:
            raise ValueError("authorization revision must be a positive integer")
        if not isinstance(self.granted_actions, frozenset) or not self.granted_actions:
            raise ValueError("granted_actions must be a nonempty frozen set")
        normalized_actions = frozenset(self.granted_actions)
        if any(not isinstance(action, ConnectorActionKind) for action in normalized_actions):
            raise ValueError("granted_actions must contain ConnectorActionKind values")
        object.__setattr__(self, "granted_actions", normalized_actions)
        object.__setattr__(
            self,
            "granted_actions_sha256",
            _sha256(self.granted_actions_sha256, "granted_actions_sha256"),
        )
        if self.granted_actions_sha256 != action_set_sha256(normalized_actions):
            raise ValueError("granted_actions_sha256 does not match the exact action set")
        if not isinstance(self.granted_scopes, frozenset) or not self.granted_scopes:
            raise ValueError("granted_scopes must be a nonempty frozen set")
        normalized = frozenset(_scope(scope) for scope in self.granted_scopes)
        object.__setattr__(self, "granted_scopes", normalized)
        expected_scope_hash = _scope_set_hash(normalized)
        object.__setattr__(
            self,
            "granted_scopes_sha256",
            _sha256(self.granted_scopes_sha256, "granted_scopes_sha256"),
        )
        if self.granted_scopes_sha256 != expected_scope_hash:
            raise ValueError("granted_scopes_sha256 does not match the exact scope set")
        if not isinstance(self.state, ConnectionAuthorizationState):
            raise TypeError("state must be a ConnectionAuthorizationState")
        _aware(self.issued_at, "issued_at")
        _aware(self.expires_at, "expires_at")
        if _utc(self.expires_at, "expires_at") <= _utc(self.issued_at, "issued_at"):
            raise ValueError("expires_at must be after issued_at")
        if self.state is ConnectionAuthorizationState.ACTIVE:
            if self.revoked_at is not None:
                raise ValueError("an active authorization cannot have revoked_at")
        else:
            if self.revoked_at is None:
                raise ValueError("a revoked authorization requires revoked_at")
            _aware(self.revoked_at, "revoked_at")
            if _utc(self.revoked_at, "revoked_at") < _utc(self.issued_at, "issued_at"):
                raise ValueError("revoked_at cannot precede issued_at")

    @classmethod
    def build(
        cls,
        *,
        owner_id: str,
        connection_id: str,
        provider: ConnectorProvider,
        resource: ConnectorResource,
        account_kind: ConnectorAccountKind,
        revision: int,
        granted_actions: frozenset[ConnectorActionKind],
        granted_scopes: frozenset[str],
        state: ConnectionAuthorizationState,
        issued_at: datetime,
        expires_at: datetime,
        revoked_at: datetime | None = None,
    ) -> ConnectedAuthorizationSnapshot:
        normalized_actions = frozenset(granted_actions)
        normalized = frozenset(_scope(scope) for scope in granted_scopes)
        return cls(
            owner_id=owner_id,
            connection_id=connection_id,
            provider=provider,
            resource=resource,
            account_kind=account_kind,
            revision=revision,
            granted_actions=normalized_actions,
            granted_actions_sha256=action_set_sha256(normalized_actions),
            granted_scopes=normalized,
            granted_scopes_sha256=_scope_set_hash(normalized),
            state=state,
            issued_at=issued_at,
            expires_at=expires_at,
            revoked_at=revoked_at,
        )

    @property
    def snapshot_sha256(self) -> str:
        encoded = json.dumps(
            {
                "version": _AUTHORIZATION_BINDING_VERSION,
                "owner_id": self.owner_id,
                "connection_id": self.connection_id,
                "provider": self.provider.value,
                "resource": self.resource.value,
                "account_kind": self.account_kind.value,
                "revision": self.revision,
                "granted_actions_sha256": self.granted_actions_sha256,
                "granted_scopes_sha256": self.granted_scopes_sha256,
                "state": self.state.value,
                "issued_at": _utc_text(self.issued_at),
                "expires_at": _utc_text(self.expires_at),
                "revoked_at": _utc_text(self.revoked_at) if self.revoked_at else None,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def active_at(self, now: datetime) -> bool:
        reference = _aware(now, "now").astimezone(timezone.utc)
        return (
            self.state is ConnectionAuthorizationState.ACTIVE
            and self.revoked_at is None
            and self.issued_at.astimezone(timezone.utc) <= reference
            and reference < self.expires_at.astimezone(timezone.utc)
        )

    def binds(self, account: ConnectedAccountRef) -> bool:
        return (
            self.owner_id == account.owner_id
            and self.connection_id == account.connection_id
            and self.provider is account.provider
            and self.resource is account.resource
            and self.account_kind is account.account_kind
        )

    def __repr__(self) -> str:
        return (
            "ConnectedAuthorizationSnapshot("
            f"connection_id={self.connection_id!r}, revision={self.revision}, "
            f"state={self.state.value!r}, action_count={len(self.granted_actions)}, "
            f"scope_count={len(self.granted_scopes)})"
        )


@dataclass(frozen=True, slots=True, repr=False)
class CredentialHandleRef:
    """Reference to broker-held credentials; never an access or refresh token."""

    owner_id: str
    connection_id: str
    provider: ConnectorProvider
    handle_id: str = field(repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "owner_id", _uuid(self.owner_id, "owner_id"))
        object.__setattr__(self, "connection_id", _uuid(self.connection_id, "connection_id"))
        if not isinstance(self.provider, ConnectorProvider):
            raise TypeError("provider must be a ConnectorProvider")
        object.__setattr__(self, "handle_id", _opaque_handle(self.handle_id, "handle_id"))

    def __repr__(self) -> str:
        return (
            "CredentialHandleRef("
            f"provider={self.provider.value!r}, handle_id='<redacted>')"
        )


@dataclass(frozen=True, slots=True, repr=False)
class MailQuery:
    query: str = field(repr=False)
    folder_ids: tuple[str, ...] = field(default=("inbox",), repr=False)
    after: datetime | None = None
    before: datetime | None = None
    limit: int = 25

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "query",
            _external_text(self.query, "query", limit=2_000, allow_empty=True),
        )
        object.__setattr__(
            self,
            "folder_ids",
            _provider_ids(self.folder_ids, "folder_ids", maximum=20),
        )
        if self.after is not None:
            _aware(self.after, "after")
        if self.before is not None:
            _aware(self.before, "before")
        if (
            self.after is not None
            and self.before is not None
            and _utc(self.after, "after") >= _utc(self.before, "before")
        ):
            raise ValueError("after must be earlier than before")
        if type(self.limit) is not int or not 1 <= self.limit <= 100:
            raise ValueError("limit must be between 1 and 100")

    def __repr__(self) -> str:
        return f"MailQuery(folders={len(self.folder_ids)}, limit={self.limit})"


@dataclass(frozen=True, slots=True, repr=False)
class MessageSummary:
    message_id: str = field(repr=False)
    thread_id: str | None = field(default=None, repr=False)
    resource_version: str = field(default="", repr=False)
    received_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc),
        repr=False,
    )
    subject: str = field(default="", repr=False)
    sender: str = field(default="", repr=False)
    recipients: tuple[str, ...] = field(default=(), repr=False)
    labels: tuple[str, ...] = field(default=(), repr=False)
    has_attachments: bool = False
    trust_boundary: str = field(
        default=UNTRUSTED_EXTERNAL_DATA,
        init=False,
        repr=False,
    )

    def __post_init__(self) -> None:
        object.__setattr__(self, "message_id", _provider_id(self.message_id, "message_id"))
        if self.thread_id is not None:
            object.__setattr__(self, "thread_id", _provider_id(self.thread_id, "thread_id"))
        object.__setattr__(self, "resource_version", _resource_version(self.resource_version))
        _aware(self.received_at, "received_at")
        object.__setattr__(
            self,
            "subject",
            _external_text(self.subject, "subject", limit=8_192, allow_empty=True),
        )
        object.__setattr__(
            self,
            "sender",
            _external_text(self.sender, "sender", limit=2_048, allow_empty=False),
        )
        object.__setattr__(self, "recipients", _addresses(self.recipients, "recipients", maximum=100))
        if not isinstance(self.labels, tuple) or len(self.labels) > 100:
            raise ValueError("labels must be a bounded tuple")
        object.__setattr__(
            self,
            "labels",
            tuple(_label(value, "label") for value in self.labels),
        )
        if type(self.has_attachments) is not bool:
            raise TypeError("has_attachments must be a boolean")

    def __repr__(self) -> str:
        return "MessageSummary(untrusted=True)"


@dataclass(frozen=True, slots=True, repr=False)
class MessageSnapshot:
    message_id: str = field(repr=False)
    thread_id: str | None = field(default=None, repr=False)
    resource_version: str = field(default="", repr=False)
    received_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc),
        repr=False,
    )
    subject: str = field(default="", repr=False)
    sender: str = field(default="", repr=False)
    recipients: tuple[str, ...] = field(default=(), repr=False)
    body_text: str = field(default="", repr=False)
    attachment_count: int = 0
    trust_boundary: str = field(
        default=UNTRUSTED_EXTERNAL_DATA,
        init=False,
        repr=False,
    )

    def __post_init__(self) -> None:
        object.__setattr__(self, "message_id", _provider_id(self.message_id, "message_id"))
        if self.thread_id is not None:
            object.__setattr__(self, "thread_id", _provider_id(self.thread_id, "thread_id"))
        object.__setattr__(self, "resource_version", _resource_version(self.resource_version))
        _aware(self.received_at, "received_at")
        object.__setattr__(
            self,
            "subject",
            _external_text(self.subject, "subject", limit=8_192, allow_empty=True),
        )
        object.__setattr__(
            self,
            "sender",
            _external_text(self.sender, "sender", limit=2_048, allow_empty=False),
        )
        object.__setattr__(self, "recipients", _addresses(self.recipients, "recipients", maximum=100))
        object.__setattr__(
            self,
            "body_text",
            _external_text(self.body_text, "body_text", limit=512_000, allow_empty=True),
        )
        if type(self.attachment_count) is not int or not 0 <= self.attachment_count <= 100:
            raise ValueError("attachment_count must be between 0 and 100")

    def __repr__(self) -> str:
        return "MessageSnapshot(untrusted=True)"


@dataclass(frozen=True, slots=True, repr=False)
class MailDraftSpec:
    to: tuple[str, ...] = field(repr=False)
    subject: str = field(repr=False)
    body_text: str = field(repr=False)
    cc: tuple[str, ...] = field(default=(), repr=False)
    bcc: tuple[str, ...] = field(default=(), repr=False)
    reply_to_message_id: str | None = field(default=None, repr=False)
    expected_resource_version: str | None = field(default=None, repr=False)
    trust_boundary: str = field(
        default=UNTRUSTED_PROPOSED_CONTENT,
        init=False,
        repr=False,
    )

    def __post_init__(self) -> None:
        object.__setattr__(self, "to", _addresses(self.to, "to", maximum=50))
        object.__setattr__(self, "cc", _addresses(self.cc, "cc", maximum=50))
        object.__setattr__(self, "bcc", _addresses(self.bcc, "bcc", maximum=50))
        if not self.to:
            raise ValueError("at least one direct recipient is required")
        all_recipients = (*self.to, *self.cc, *self.bcc)
        if len(all_recipients) > 50:
            raise ValueError("a draft can contain at most 50 recipients")
        if len({value.casefold() for value in all_recipients}) != len(all_recipients):
            raise ValueError("recipients cannot repeat across to, cc, and bcc")
        object.__setattr__(
            self,
            "subject",
            _single_line_external_text(
                self.subject,
                "subject",
                limit=8_192,
                allow_empty=True,
            ),
        )
        object.__setattr__(
            self,
            "body_text",
            _external_text(self.body_text, "body_text", limit=200_000, allow_empty=True),
        )
        if (self.reply_to_message_id is None) != (self.expected_resource_version is None):
            raise ValueError(
                "reply_to_message_id and expected_resource_version must be supplied together"
            )
        if self.reply_to_message_id is not None:
            object.__setattr__(
                self,
                "reply_to_message_id",
                _provider_id(self.reply_to_message_id, "reply_to_message_id"),
            )
            object.__setattr__(
                self,
                "expected_resource_version",
                _resource_version(self.expected_resource_version or ""),
            )

    def __repr__(self) -> str:
        return (
            "MailDraftSpec("
            f"recipients={len(self.to) + len(self.cc) + len(self.bcc)}, untrusted=True)"
        )


@dataclass(frozen=True, slots=True, repr=False)
class CalendarQuery:
    calendar_ids: tuple[str, ...] = field(repr=False)
    starts_at: datetime = field(repr=False)
    ends_at: datetime = field(repr=False)
    time_zone: str
    limit: int = 100

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "calendar_ids",
            _provider_ids(self.calendar_ids, "calendar_ids", maximum=20),
        )
        object.__setattr__(self, "time_zone", _timezone(self.time_zone))
        _zoned_datetime(self.starts_at, self.time_zone, "starts_at")
        _zoned_datetime(self.ends_at, self.time_zone, "ends_at")
        start_utc = _utc(self.starts_at, "starts_at")
        end_utc = _utc(self.ends_at, "ends_at")
        if start_utc >= end_utc:
            raise ValueError("starts_at must be earlier than ends_at")
        if end_utc - start_utc > timedelta(days=366):
            raise ValueError("calendar queries cannot span more than 366 days")
        if type(self.limit) is not int or not 1 <= self.limit <= 250:
            raise ValueError("limit must be between 1 and 250")

    def __repr__(self) -> str:
        return f"CalendarQuery(calendars={len(self.calendar_ids)}, limit={self.limit})"


@dataclass(frozen=True, slots=True, repr=False)
class FreeBusyWindow:
    calendar_id: str = field(repr=False)
    starts_at: datetime = field(repr=False)
    ends_at: datetime = field(repr=False)
    status: str = "busy"
    trust_boundary: str = field(
        default=UNTRUSTED_EXTERNAL_DATA,
        init=False,
        repr=False,
    )

    def __post_init__(self) -> None:
        object.__setattr__(self, "calendar_id", _provider_id(self.calendar_id, "calendar_id"))
        if _utc(self.starts_at, "starts_at") >= _utc(self.ends_at, "ends_at"):
            raise ValueError("starts_at must be earlier than ends_at")
        if self.status not in {"busy", "tentative", "out_of_office", "working_elsewhere"}:
            raise ValueError("status is not a supported busy state")

    def __repr__(self) -> str:
        return f"FreeBusyWindow(status={self.status!r}, untrusted=True)"


@dataclass(frozen=True, slots=True, repr=False)
class EventSnapshot:
    event_id: str = field(repr=False)
    calendar_id: str = field(repr=False)
    resource_version: str = field(repr=False)
    starts_at: datetime = field(repr=False)
    ends_at: datetime = field(repr=False)
    time_zone: str
    title: str = field(repr=False)
    description: str = field(default="", repr=False)
    location: str = field(default="", repr=False)
    attendees: tuple[str, ...] = field(default=(), repr=False)
    organizer: str | None = field(default=None, repr=False)
    status: str = "confirmed"
    trust_boundary: str = field(
        default=UNTRUSTED_EXTERNAL_DATA,
        init=False,
        repr=False,
    )

    def __post_init__(self) -> None:
        object.__setattr__(self, "event_id", _provider_id(self.event_id, "event_id"))
        object.__setattr__(self, "calendar_id", _provider_id(self.calendar_id, "calendar_id"))
        object.__setattr__(self, "resource_version", _resource_version(self.resource_version))
        object.__setattr__(self, "time_zone", _timezone(self.time_zone))
        _zoned_datetime(self.starts_at, self.time_zone, "starts_at")
        _zoned_datetime(self.ends_at, self.time_zone, "ends_at")
        if _utc(self.starts_at, "starts_at") >= _utc(self.ends_at, "ends_at"):
            raise ValueError("starts_at must be earlier than ends_at")
        object.__setattr__(
            self,
            "title",
            _external_text(self.title, "title", limit=8_192, allow_empty=False),
        )
        object.__setattr__(
            self,
            "description",
            _external_text(self.description, "description", limit=200_000, allow_empty=True),
        )
        object.__setattr__(
            self,
            "location",
            _external_text(self.location, "location", limit=8_192, allow_empty=True),
        )
        object.__setattr__(
            self,
            "attendees",
            _addresses(self.attendees, "attendees", maximum=100),
        )
        if self.organizer is not None:
            object.__setattr__(self, "organizer", _email_address(self.organizer))
        if self.status not in {"confirmed", "tentative", "cancelled"}:
            raise ValueError("status is not a supported event state")

    def __repr__(self) -> str:
        return f"EventSnapshot(status={self.status!r}, untrusted=True)"


@dataclass(frozen=True, slots=True, repr=False)
class EventSpec:
    calendar_id: str = field(repr=False)
    title: str = field(repr=False)
    starts_at: datetime = field(repr=False)
    ends_at: datetime = field(repr=False)
    time_zone: str
    description: str = field(default="", repr=False)
    location: str = field(default="", repr=False)
    attendees: tuple[str, ...] = field(default=(), repr=False)
    source_event_id: str | None = field(default=None, repr=False)
    expected_resource_version: str | None = field(default=None, repr=False)
    trust_boundary: str = field(
        default=UNTRUSTED_PROPOSED_CONTENT,
        init=False,
        repr=False,
    )

    def __post_init__(self) -> None:
        object.__setattr__(self, "calendar_id", _provider_id(self.calendar_id, "calendar_id"))
        object.__setattr__(
            self,
            "title",
            _single_line_external_text(
                self.title,
                "title",
                limit=8_192,
                allow_empty=False,
            ),
        )
        object.__setattr__(self, "time_zone", _timezone(self.time_zone))
        _zoned_datetime(self.starts_at, self.time_zone, "starts_at")
        _zoned_datetime(self.ends_at, self.time_zone, "ends_at")
        start_utc = _utc(self.starts_at, "starts_at")
        end_utc = _utc(self.ends_at, "ends_at")
        if start_utc >= end_utc:
            raise ValueError("starts_at must be earlier than ends_at")
        if end_utc - start_utc > timedelta(days=366):
            raise ValueError("events cannot span more than 366 days")
        object.__setattr__(
            self,
            "description",
            _external_text(self.description, "description", limit=200_000, allow_empty=True),
        )
        object.__setattr__(
            self,
            "location",
            _single_line_external_text(
                self.location,
                "location",
                limit=8_192,
                allow_empty=True,
            ),
        )
        object.__setattr__(
            self,
            "attendees",
            _addresses(self.attendees, "attendees", maximum=100),
        )
        if (self.source_event_id is None) != (self.expected_resource_version is None):
            raise ValueError(
                "source_event_id and expected_resource_version must be supplied together"
            )
        if self.source_event_id is not None:
            object.__setattr__(
                self,
                "source_event_id",
                _provider_id(self.source_event_id, "source_event_id"),
            )
            object.__setattr__(
                self,
                "expected_resource_version",
                _resource_version(self.expected_resource_version or ""),
            )

    def __repr__(self) -> str:
        return f"EventSpec(attendees={len(self.attendees)}, untrusted=True)"


def _mail_query_target(query: MailQuery) -> dict[str, Any]:
    return {
        "query": query.query,
        "folder_ids": list(query.folder_ids),
        "after": _utc_text(query.after) if query.after else None,
        "before": _utc_text(query.before) if query.before else None,
        "limit": query.limit,
    }


def _mail_spec_target(spec: MailDraftSpec) -> dict[str, Any]:
    return {
        "to": list(spec.to),
        "cc": list(spec.cc),
        "bcc": list(spec.bcc),
        "subject": spec.subject,
        "body_text": spec.body_text,
        "reply_to_message_id": spec.reply_to_message_id,
        "expected_resource_version": spec.expected_resource_version,
    }


def _calendar_query_target(query: CalendarQuery) -> dict[str, Any]:
    return {
        "calendar_ids": list(query.calendar_ids),
        "starts_at": _utc_text(query.starts_at),
        "ends_at": _utc_text(query.ends_at),
        "time_zone": query.time_zone,
        "limit": query.limit,
    }


def _event_spec_target(spec: EventSpec) -> dict[str, Any]:
    return {
        "calendar_id": spec.calendar_id,
        "title": spec.title,
        "starts_at": _utc_text(spec.starts_at),
        "ends_at": _utc_text(spec.ends_at),
        "time_zone": spec.time_zone,
        "description": spec.description,
        "location": spec.location,
        "attendees": list(spec.attendees),
        "source_event_id": spec.source_event_id,
        "expected_resource_version": spec.expected_resource_version,
    }


@dataclass(frozen=True, slots=True, repr=False)
class MailSearchRequest:
    query: MailQuery = field(repr=False)
    target_binding_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.query, MailQuery):
            raise TypeError("query must be a MailQuery")
        expected = _canonical_sha256({"kind": "mail.search", **_mail_query_target(self.query)})
        object.__setattr__(
            self,
            "target_binding_sha256",
            _exact_binding(self.target_binding_sha256, expected),
        )

    @classmethod
    def build(cls, query: MailQuery) -> MailSearchRequest:
        binding = _canonical_sha256({"kind": "mail.search", **_mail_query_target(query)})
        return cls(query=query, target_binding_sha256=binding)

    def __repr__(self) -> str:
        return "MailSearchRequest(target='<redacted>')"


@dataclass(frozen=True, slots=True, repr=False)
class MailGetRequest:
    message_id: str = field(repr=False)
    expected_resource_version: str | None = field(default=None, repr=False)
    target_binding_sha256: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "message_id", _provider_id(self.message_id, "message_id"))
        if self.expected_resource_version is not None:
            object.__setattr__(
                self,
                "expected_resource_version",
                _resource_version(self.expected_resource_version),
            )
        expected = _canonical_sha256(
            {
                "kind": "mail.get",
                "message_id": self.message_id,
                "expected_resource_version": self.expected_resource_version,
            }
        )
        object.__setattr__(
            self,
            "target_binding_sha256",
            _exact_binding(self.target_binding_sha256, expected),
        )

    @classmethod
    def build(
        cls,
        *,
        message_id: str,
        expected_resource_version: str | None = None,
    ) -> MailGetRequest:
        normalized_id = _provider_id(message_id, "message_id")
        normalized_version = (
            _resource_version(expected_resource_version)
            if expected_resource_version is not None
            else None
        )
        binding = _canonical_sha256(
            {
                "kind": "mail.get",
                "message_id": normalized_id,
                "expected_resource_version": normalized_version,
            }
        )
        return cls(normalized_id, normalized_version, binding)

    def __repr__(self) -> str:
        return "MailGetRequest(target='<redacted>')"


@dataclass(frozen=True, slots=True, repr=False)
class MailDraftRequest:
    spec: MailDraftSpec = field(repr=False)
    target_binding_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.spec, MailDraftSpec):
            raise TypeError("spec must be a MailDraftSpec")
        expected = _canonical_sha256({"kind": "mail.create_draft", **_mail_spec_target(self.spec)})
        object.__setattr__(
            self,
            "target_binding_sha256",
            _exact_binding(self.target_binding_sha256, expected),
        )

    @classmethod
    def build(cls, spec: MailDraftSpec) -> MailDraftRequest:
        binding = _canonical_sha256({"kind": "mail.create_draft", **_mail_spec_target(spec)})
        return cls(spec=spec, target_binding_sha256=binding)

    def __repr__(self) -> str:
        return "MailDraftRequest(target='<redacted>')"


@dataclass(frozen=True, slots=True, repr=False)
class MailSendRequest:
    spec: MailDraftSpec = field(repr=False)
    target_binding_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.spec, MailDraftSpec):
            raise TypeError("spec must be a MailDraftSpec")
        if self.spec.reply_to_message_id is not None:
            raise ValueError("reply content must use MailReplyRequest")
        expected = _canonical_sha256({"kind": "mail.send", **_mail_spec_target(self.spec)})
        object.__setattr__(
            self,
            "target_binding_sha256",
            _exact_binding(self.target_binding_sha256, expected),
        )

    @classmethod
    def build(cls, spec: MailDraftSpec) -> MailSendRequest:
        binding = _canonical_sha256({"kind": "mail.send", **_mail_spec_target(spec)})
        return cls(spec=spec, target_binding_sha256=binding)

    def __repr__(self) -> str:
        return "MailSendRequest(target='<redacted>')"


@dataclass(frozen=True, slots=True, repr=False)
class MailReplyRequest:
    spec: MailDraftSpec = field(repr=False)
    target_binding_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.spec, MailDraftSpec):
            raise TypeError("spec must be a MailDraftSpec")
        if self.spec.reply_to_message_id is None:
            raise ValueError("reply requests require an exact source message and version")
        expected = _canonical_sha256({"kind": "mail.reply", **_mail_spec_target(self.spec)})
        object.__setattr__(
            self,
            "target_binding_sha256",
            _exact_binding(self.target_binding_sha256, expected),
        )

    @classmethod
    def build(cls, spec: MailDraftSpec) -> MailReplyRequest:
        binding = _canonical_sha256({"kind": "mail.reply", **_mail_spec_target(spec)})
        return cls(spec=spec, target_binding_sha256=binding)

    def __repr__(self) -> str:
        return "MailReplyRequest(target='<redacted>')"


@dataclass(frozen=True, slots=True, repr=False)
class CalendarListRequest:
    query: CalendarQuery = field(repr=False)
    target_binding_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.query, CalendarQuery):
            raise TypeError("query must be a CalendarQuery")
        expected = _canonical_sha256({"kind": "calendar.list", **_calendar_query_target(self.query)})
        object.__setattr__(self, "target_binding_sha256", _exact_binding(self.target_binding_sha256, expected))

    @classmethod
    def build(cls, query: CalendarQuery) -> CalendarListRequest:
        binding = _canonical_sha256({"kind": "calendar.list", **_calendar_query_target(query)})
        return cls(query=query, target_binding_sha256=binding)

    def __repr__(self) -> str:
        return "CalendarListRequest(target='<redacted>')"


@dataclass(frozen=True, slots=True, repr=False)
class CalendarFreeBusyRequest:
    query: CalendarQuery = field(repr=False)
    target_binding_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.query, CalendarQuery):
            raise TypeError("query must be a CalendarQuery")
        expected = _canonical_sha256(
            {"kind": "calendar.free_busy", **_calendar_query_target(self.query)}
        )
        object.__setattr__(self, "target_binding_sha256", _exact_binding(self.target_binding_sha256, expected))

    @classmethod
    def build(cls, query: CalendarQuery) -> CalendarFreeBusyRequest:
        binding = _canonical_sha256(
            {"kind": "calendar.free_busy", **_calendar_query_target(query)}
        )
        return cls(query=query, target_binding_sha256=binding)

    def __repr__(self) -> str:
        return "CalendarFreeBusyRequest(target='<redacted>')"


@dataclass(frozen=True, slots=True, repr=False)
class CalendarGetRequest:
    calendar_id: str = field(repr=False)
    event_id: str = field(repr=False)
    expected_resource_version: str | None = field(default=None, repr=False)
    target_binding_sha256: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "calendar_id", _provider_id(self.calendar_id, "calendar_id"))
        object.__setattr__(self, "event_id", _provider_id(self.event_id, "event_id"))
        if self.expected_resource_version is not None:
            object.__setattr__(self, "expected_resource_version", _resource_version(self.expected_resource_version))
        expected = _canonical_sha256(
            {
                "kind": "calendar.get",
                "calendar_id": self.calendar_id,
                "event_id": self.event_id,
                "expected_resource_version": self.expected_resource_version,
            }
        )
        object.__setattr__(self, "target_binding_sha256", _exact_binding(self.target_binding_sha256, expected))

    @classmethod
    def build(
        cls,
        *,
        calendar_id: str,
        event_id: str,
        expected_resource_version: str | None = None,
    ) -> CalendarGetRequest:
        normalized_calendar = _provider_id(calendar_id, "calendar_id")
        normalized_event = _provider_id(event_id, "event_id")
        normalized_version = (
            _resource_version(expected_resource_version)
            if expected_resource_version is not None
            else None
        )
        binding = _canonical_sha256(
            {
                "kind": "calendar.get",
                "calendar_id": normalized_calendar,
                "event_id": normalized_event,
                "expected_resource_version": normalized_version,
            }
        )
        return cls(normalized_calendar, normalized_event, normalized_version, binding)

    def __repr__(self) -> str:
        return "CalendarGetRequest(target='<redacted>')"


@dataclass(frozen=True, slots=True, repr=False)
class CalendarCreateRequest:
    spec: EventSpec = field(repr=False)
    target_binding_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.spec, EventSpec):
            raise TypeError("spec must be an EventSpec")
        if self.spec.source_event_id is not None:
            raise ValueError("create requests cannot identify an existing event")
        expected = _canonical_sha256({"kind": "calendar.create", **_event_spec_target(self.spec)})
        object.__setattr__(self, "target_binding_sha256", _exact_binding(self.target_binding_sha256, expected))

    @classmethod
    def build(cls, spec: EventSpec) -> CalendarCreateRequest:
        binding = _canonical_sha256({"kind": "calendar.create", **_event_spec_target(spec)})
        return cls(spec=spec, target_binding_sha256=binding)

    def __repr__(self) -> str:
        return "CalendarCreateRequest(target='<redacted>')"


@dataclass(frozen=True, slots=True, repr=False)
class CalendarUpdateRequest:
    spec: EventSpec = field(repr=False)
    target_binding_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.spec, EventSpec):
            raise TypeError("spec must be an EventSpec")
        if self.spec.source_event_id is None:
            raise ValueError("update requests require an exact source event and version")
        expected = _canonical_sha256({"kind": "calendar.update", **_event_spec_target(self.spec)})
        object.__setattr__(self, "target_binding_sha256", _exact_binding(self.target_binding_sha256, expected))

    @classmethod
    def build(cls, spec: EventSpec) -> CalendarUpdateRequest:
        binding = _canonical_sha256({"kind": "calendar.update", **_event_spec_target(spec)})
        return cls(spec=spec, target_binding_sha256=binding)

    def __repr__(self) -> str:
        return "CalendarUpdateRequest(target='<redacted>')"


@dataclass(frozen=True, slots=True, repr=False)
class CalendarCancelRequest:
    calendar_id: str = field(repr=False)
    event_id: str = field(repr=False)
    expected_resource_version: str = field(repr=False)
    target_binding_sha256: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "calendar_id", _provider_id(self.calendar_id, "calendar_id"))
        object.__setattr__(self, "event_id", _provider_id(self.event_id, "event_id"))
        object.__setattr__(self, "expected_resource_version", _resource_version(self.expected_resource_version))
        expected = _canonical_sha256(
            {
                "kind": "calendar.cancel",
                "calendar_id": self.calendar_id,
                "event_id": self.event_id,
                "expected_resource_version": self.expected_resource_version,
            }
        )
        object.__setattr__(self, "target_binding_sha256", _exact_binding(self.target_binding_sha256, expected))

    @classmethod
    def build(
        cls,
        *,
        calendar_id: str,
        event_id: str,
        expected_resource_version: str,
    ) -> CalendarCancelRequest:
        normalized_calendar = _provider_id(calendar_id, "calendar_id")
        normalized_event = _provider_id(event_id, "event_id")
        normalized_version = _resource_version(expected_resource_version)
        binding = _canonical_sha256(
            {
                "kind": "calendar.cancel",
                "calendar_id": normalized_calendar,
                "event_id": normalized_event,
                "expected_resource_version": normalized_version,
            }
        )
        return cls(normalized_calendar, normalized_event, normalized_version, binding)

    def __repr__(self) -> str:
        return "CalendarCancelRequest(target='<redacted>')"


@dataclass(frozen=True, slots=True, repr=False)
class ProviderReceipt:
    operation_id: str
    provider: ConnectorProvider
    resource: ConnectorResource
    outcome: str
    provider_request_id_hash: str
    resource_id_hash: str
    resource_version: str
    idempotency_key_hash: str
    observed_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "operation_id", _uuid(self.operation_id, "operation_id"))
        if not isinstance(self.provider, ConnectorProvider):
            raise TypeError("provider must be a ConnectorProvider")
        if not isinstance(self.resource, ConnectorResource):
            raise TypeError("resource must be a ConnectorResource")
        if self.outcome not in {"drafted", "sent", "created", "updated", "cancelled"}:
            raise ValueError("outcome is not supported")
        object.__setattr__(
            self,
            "provider_request_id_hash",
            _sha256(self.provider_request_id_hash, "provider_request_id_hash"),
        )
        object.__setattr__(
            self,
            "resource_id_hash",
            _sha256(self.resource_id_hash, "resource_id_hash"),
        )
        object.__setattr__(self, "resource_version", _resource_version(self.resource_version))
        object.__setattr__(
            self,
            "idempotency_key_hash",
            _sha256(self.idempotency_key_hash, "idempotency_key_hash"),
        )
        _aware(self.observed_at, "observed_at")

    def __repr__(self) -> str:
        return (
            "ProviderReceipt("
            f"operation_id={self.operation_id!r}, outcome={self.outcome!r})"
        )


@dataclass(frozen=True, slots=True, repr=False)
class AmbiguousProviderResult:
    """A provider may have applied the effect, so the caller must reconcile."""

    operation_id: str
    provider: ConnectorProvider
    resource: ConnectorResource
    idempotency_key_hash: str
    observed_at: datetime
    retryable: bool = False
    code: str = "CONNECTED_PROVIDER_RESULT_AMBIGUOUS"

    def __post_init__(self) -> None:
        object.__setattr__(self, "operation_id", _uuid(self.operation_id, "operation_id"))
        if not isinstance(self.provider, ConnectorProvider):
            raise TypeError("provider must be a ConnectorProvider")
        if not isinstance(self.resource, ConnectorResource):
            raise TypeError("resource must be a ConnectorResource")
        object.__setattr__(
            self,
            "idempotency_key_hash",
            _sha256(self.idempotency_key_hash, "idempotency_key_hash"),
        )
        _aware(self.observed_at, "observed_at")
        if type(self.retryable) is not bool or self.retryable:
            raise ValueError("ambiguous provider effects cannot be blindly retried")
        if self.code != "CONNECTED_PROVIDER_RESULT_AMBIGUOUS":
            raise ValueError("ambiguous result code is fixed")

    def __repr__(self) -> str:
        return (
            "AmbiguousProviderResult("
            f"operation_id={self.operation_id!r}, retryable=False)"
        )


def validate_operation_inputs(
    *,
    account: ConnectedAccountRef,
    credential: CredentialHandleRef,
    operation_id: str,
    idempotency_key: str,
) -> tuple[str, str]:
    """Validate the shared owner/connection/provider binding for a provider call."""

    if account.owner_id != credential.owner_id:
        raise ValueError("credential owner does not match the connected account")
    if account.connection_id != credential.connection_id:
        raise ValueError("credential connection does not match the connected account")
    if account.provider is not credential.provider:
        raise ValueError("credential provider does not match the connected account")
    operation = _uuid(operation_id, "operation_id")
    if not isinstance(idempotency_key, str) or not _IDEMPOTENCY_KEY.fullmatch(idempotency_key):
        raise ValueError("idempotency_key must be a bounded opaque key")
    return operation, idempotency_key


def content_free_audit(value: Any) -> dict[str, Any]:
    """Return the only audit metadata these contracts permit.

    This intentionally excludes subjects, bodies, addresses, titles, locations,
    provider identifiers, resource versions, queries, credential handles, and
    every other customer-content field.
    """

    if isinstance(value, ConnectedAccountRef):
        return {
            "provider": value.provider.value,
            "resource": value.resource.value,
            "account_kind": value.account_kind.value,
            "connection_id": value.connection_id,
            "external_account_id_hash": value.external_account_id_hash,
        }
    if isinstance(value, ConnectedAuthorizationSnapshot):
        return {
            "provider": value.provider.value,
            "resource": value.resource.value,
            "account_kind": value.account_kind.value,
            "connection_id": value.connection_id,
            "authorization_revision": value.revision,
            "authorization_snapshot_sha256": value.snapshot_sha256,
            "granted_actions_sha256": value.granted_actions_sha256,
            "action_count": len(value.granted_actions),
            "granted_scopes_sha256": value.granted_scopes_sha256,
            "scope_count": len(value.granted_scopes),
            "state": value.state.value,
        }
    if isinstance(value, (MessageSummary, MessageSnapshot)):
        return {"resource": "mail", "untrusted": True}
    if isinstance(value, MailDraftSpec):
        return {
            "resource": "mail",
            "untrusted": True,
            "recipient_count": len(value.to) + len(value.cc) + len(value.bcc),
        }
    if isinstance(value, (FreeBusyWindow, EventSnapshot)):
        return {"resource": "calendar", "untrusted": True}
    if isinstance(value, EventSpec):
        return {
            "resource": "calendar",
            "untrusted": True,
            "attendee_count": len(value.attendees),
        }
    if isinstance(value, ProviderReceipt):
        return {
            "operation_id": value.operation_id,
            "provider": value.provider.value,
            "resource": value.resource.value,
            "outcome": value.outcome,
            "idempotency_key_hash": value.idempotency_key_hash,
        }
    if isinstance(value, AmbiguousProviderResult):
        return {
            "operation_id": value.operation_id,
            "provider": value.provider.value,
            "resource": value.resource.value,
            "outcome": "ambiguous",
            "retryable": False,
            "idempotency_key_hash": value.idempotency_key_hash,
        }
    raise TypeError("unsupported connected-app audit value")
