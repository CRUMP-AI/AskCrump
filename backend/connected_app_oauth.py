"""Inert OAuth Authorization Code + PKCE contracts for connected apps.

This module deliberately contains no route, provider adapter, HTTP client,
credential implementation, or release switch.  The credential broker owns
PKCE-verifier custody from flow creation through a durably recorded exchange
terminal.  Application-visible records contain only content-free bindings.
Authorization codes, browser state, and PKCE verifiers are redacted,
unserializable, and never modeled as durable application data.  Access and
refresh tokens are not represented at all.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import StrEnum
import hashlib
import hmac
import json
import re
import secrets
from typing import Protocol
from urllib.parse import urlsplit
from uuid import UUID

from .connected_app_contracts import (
    ConnectedAuthorizationSnapshot,
    ConnectionAuthorizationState,
    ConnectorAccountKind,
    CredentialHandleRef,
)
from .connected_app_policy import (
    ConnectedActionPolicy,
    ConnectorActionKind,
    ConnectorProvider,
    ConnectorResource,
)
from .connected_app_scopes import ConnectedAppScopeError, delegated_scope_plan


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_STATE = re.compile(r"^[A-Za-z0-9._~-]{43,256}$")
_PKCE_VERIFIER = re.compile(r"^[A-Za-z0-9._~-]{43,128}$")
_PKCE_CHALLENGE = re.compile(r"^[A-Za-z0-9_-]{43}$")
_PERMIT_CAPABILITY = re.compile(r"^[A-Za-z0-9._~-]{64,192}$")
_AUTHORIZATION_CODE = re.compile(r"^[^\x00-\x20\x7f]{16,4096}$")
_HOST_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_SCOPE = re.compile(r"^[^\x00-\x20\x7f]{1,512}$")
_FLOW_BINDING_VERSION = "connected-oauth-pkce-v3"
_CONSUME_BINDING_VERSION = "connected-oauth-consume-v2"
_EXCHANGE_BINDING_VERSION = "connected-oauth-exchange-v2"
_COMPLETION_BINDING_VERSION = "connected-oauth-completion-v2"
_EXCHANGE_PERMIT_BINDING_VERSION = "connected-oauth-exchange-permit-v1"
_CREDENTIAL_CLEANUP_BINDING_VERSION = "connected-oauth-credential-cleanup-v1"
_MAX_FLOW_TTL = timedelta(minutes=10)
_MAX_EXCHANGE_TTL = timedelta(minutes=2)
_EXTERNAL_FAILURE_CODES = frozenset(
    {
        "OAUTH_BROKER_FLOW_READ_FAILED",
        "OAUTH_BROKER_BEGIN_FAILED",
        "OAUTH_FLOW_READ_FAILED",
        "OAUTH_FLOW_CREATE_FAILED",
        "OAUTH_FLOW_REVALIDATE_FAILED",
        "OAUTH_CONSUMPTION_READ_FAILED",
        "OAUTH_CONSUMPTION_WRITE_FAILED",
        "OAUTH_EXCHANGE_PERMIT_READ_FAILED",
        "OAUTH_EXCHANGE_PERMIT_WRITE_FAILED",
        "OAUTH_EXCHANGE_READ_FAILED",
        "OAUTH_EXCHANGE_DISPATCH_FAILED",
        "OAUTH_COMPLETION_READ_FAILED",
        "OAUTH_COMPLETION_WRITE_FAILED",
        "OAUTH_CREDENTIAL_CLEANUP_READ_FAILED",
        "OAUTH_CREDENTIAL_CLEANUP_WRITE_FAILED",
    }
)


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


def _revision(value: int, name: str = "expected_base_revision") -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"{name} must be a nonnegative integer")
    return value


def _aware(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _scope(value: str) -> str:
    if not isinstance(value, str) or not _SCOPE.fullmatch(value) or value != value.strip():
        raise ValueError("OAuth scopes must be bounded non-whitespace strings")
    return value


def _scopes(values: frozenset[str]) -> frozenset[str]:
    if not isinstance(values, frozenset) or not values:
        raise ValueError("OAuth scopes must be a nonempty frozen set")
    return frozenset(_scope(value) for value in values)


def _scope_hash(values: frozenset[str]) -> str:
    encoded = json.dumps(sorted(values), ensure_ascii=True, separators=(",", ":")).encode(
        "ascii"
    )
    return hashlib.sha256(encoded).hexdigest()


def _actions(values: frozenset[ConnectorActionKind]) -> frozenset[ConnectorActionKind]:
    if (
        not isinstance(values, frozenset)
        or not values
        or any(not isinstance(value, ConnectorActionKind) for value in values)
    ):
        raise ValueError("actions must be a nonempty frozen set of ConnectorActionKind")
    return values


def _action_hash(values: frozenset[ConnectorActionKind]) -> str:
    encoded = json.dumps(
        sorted(value.value for value in values),
        ensure_ascii=True,
        separators=(",", ":"),
    ).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _canonical_hash(value: dict[str, object]) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


def _redirect_uri(value: str) -> str:
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= 2048
        or value != value.strip()
        or any(ord(char) < 33 or ord(char) > 126 for char in value)
        or "\\" in value
        or "%" in value
    ):
        raise ValueError("redirect_uri must be a canonical ASCII HTTPS URI")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("redirect_uri is invalid") from exc
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or port is not None
        or parsed.query
        or parsed.fragment
        or not parsed.path.startswith("/")
        or parsed.path == "/"
        or "//" in parsed.path
        or any(part in {".", ".."} for part in parsed.path.split("/"))
    ):
        raise ValueError("redirect_uri must be an exact HTTPS callback without authority confusion")
    host = parsed.hostname
    if host != host.lower() or len(host) > 253:
        raise ValueError("redirect_uri host must be canonical lowercase DNS")
    labels = host.split(".")
    if len(labels) < 2 or any(not _HOST_LABEL.fullmatch(label) for label in labels):
        raise ValueError("redirect_uri host must be canonical lowercase DNS")
    canonical = f"https://{host}{parsed.path}"
    if value != canonical:
        raise ValueError("redirect_uri must exactly match its canonical form")
    return value


def pkce_s256_challenge(verifier: str) -> str:
    """Return RFC 7636 S256 BASE64URL(SHA256(verifier)) without padding."""

    if not isinstance(verifier, str) or not _PKCE_VERIFIER.fullmatch(verifier):
        raise ValueError("PKCE verifier must be 43-128 RFC 7636 unreserved characters")
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).decode(
        "ascii"
    ).rstrip("=")


def _exact_plan(
    *,
    provider: ConnectorProvider,
    resource: ConnectorResource,
    account_kind: ConnectorAccountKind,
    actions: frozenset[ConnectorActionKind],
) -> tuple[frozenset[ConnectorActionKind], frozenset[str]]:
    normalized_actions = _actions(actions)
    if any(
        ConnectedActionPolicy.requirement(action).resource is not resource
        for action in normalized_actions
    ):
        raise ValueError("every OAuth action must target the flow resource")
    try:
        plan = delegated_scope_plan(provider, normalized_actions, account_kind=account_kind)
    except ConnectedAppScopeError as exc:
        raise ValueError("actions have no safe delegated OAuth scope plan") from exc
    return normalized_actions, frozenset(plan.delegated_scopes)


def _flow_binding(
    *,
    flow_id: str,
    nonce_id: str,
    owner_id: str,
    connection_id: str,
    connection_incarnation_id: str,
    expected_base_revision: int,
    current_flow_nonce_sha256: str,
    session_binding_sha256: str,
    provider: ConnectorProvider,
    resource: ConnectorResource,
    account_kind: ConnectorAccountKind,
    actions_sha256: str,
    requested_scopes_sha256: str,
    state_sha256: str,
    pkce_challenge: str,
    redirect_uri: str,
    created_at: datetime,
    expires_at: datetime,
) -> str:
    return _canonical_hash(
        {
            "version": _FLOW_BINDING_VERSION,
            "flow_id": flow_id,
            "nonce_id": nonce_id,
            "owner_id": owner_id,
            "connection_id": connection_id,
            "connection_incarnation_id": connection_incarnation_id,
            "expected_base_revision": expected_base_revision,
            "current_flow_nonce_sha256": current_flow_nonce_sha256,
            "session_binding_sha256": session_binding_sha256,
            "provider": provider.value,
            "resource": resource.value,
            "account_kind": account_kind.value,
            "actions_sha256": actions_sha256,
            "requested_scopes_sha256": requested_scopes_sha256,
            "state_sha256": state_sha256,
            "pkce_challenge": pkce_challenge,
            "redirect_uri": redirect_uri,
            "created_at": created_at.isoformat(),
            "expires_at": expires_at.isoformat(),
        }
    )


class OAuthFlowState(StrEnum):
    PENDING = "pending"
    CONSUMED = "consumed"


class OAuthContractError(ValueError):
    """Content-free OAuth contract failure safe for a route boundary."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _external_failure(code: str) -> OAuthContractError:
    if code not in _EXTERNAL_FAILURE_CODES:
        raise RuntimeError("external OAuth failure code is not allowlisted")
    return OAuthContractError(code)


class OAuthBrokerBeginResponseLost(RuntimeError):
    """The broker may have durably stored verifier custody before response loss."""

    def __init__(self) -> None:
        super().__init__("OAUTH_BROKER_BEGIN_RESPONSE_LOST")
        self.code = "OAUTH_BROKER_BEGIN_RESPONSE_LOST"


class OAuthConsumeResponseLost(RuntimeError):
    """The repository may have durably consumed the flow before response loss."""

    def __init__(self) -> None:
        super().__init__("OAUTH_CONSUME_RESPONSE_LOST")
        self.code = "OAUTH_CONSUME_RESPONSE_LOST"


class OAuthFlowCreateResponseLost(RuntimeError):
    """The repository may have durably created the pending flow."""

    def __init__(self) -> None:
        super().__init__("OAUTH_FLOW_CREATE_RESPONSE_LOST")
        self.code = "OAUTH_FLOW_CREATE_RESPONSE_LOST"


class OAuthExchangeResponseLost(RuntimeError):
    """The broker may have durably recorded an exchange before response loss."""

    def __init__(self) -> None:
        super().__init__("OAUTH_EXCHANGE_RESPONSE_LOST")
        self.code = "OAUTH_EXCHANGE_RESPONSE_LOST"


class OAuthExchangePermitResponseLost(RuntimeError):
    """The repository may have durably issued the one-use exchange permit."""

    def __init__(self) -> None:
        super().__init__("OAUTH_EXCHANGE_PERMIT_RESPONSE_LOST")
        self.code = "OAUTH_EXCHANGE_PERMIT_RESPONSE_LOST"


class OAuthCompletionResponseLost(RuntimeError):
    """The repository may have durably completed the connection before response loss."""

    def __init__(self) -> None:
        super().__init__("OAUTH_COMPLETION_RESPONSE_LOST")
        self.code = "OAUTH_COMPLETION_RESPONSE_LOST"


class OAuthCredentialCleanupResponseLost(RuntimeError):
    """The cleanup outbox may have durably accepted a broker credential."""

    def __init__(self) -> None:
        super().__init__("OAUTH_CREDENTIAL_CLEANUP_RESPONSE_LOST")
        self.code = "OAUTH_CREDENTIAL_CLEANUP_RESPONSE_LOST"


@dataclass(frozen=True, slots=True)
class OAuthRedirectAllowlist:
    allowed_redirect_uris: frozenset[str]

    def __post_init__(self) -> None:
        if not isinstance(self.allowed_redirect_uris, frozenset) or not self.allowed_redirect_uris:
            raise ValueError("allowed_redirect_uris must be a nonempty frozen set")
        object.__setattr__(
            self,
            "allowed_redirect_uris",
            frozenset(_redirect_uri(value) for value in self.allowed_redirect_uris),
        )

    def require(self, redirect_uri: str) -> str:
        canonical = _redirect_uri(redirect_uri)
        if canonical not in self.allowed_redirect_uris:
            raise OAuthContractError("OAUTH_REDIRECT_NOT_ALLOWED")
        return canonical


class _RedactedSecret:
    __slots__ = ("_value",)
    _label = "secret"

    def __init__(self, value: str) -> None:
        self._value = value

    @property
    def value(self) -> str:
        return self._value

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self._label}='<redacted>')"

    def __getstate__(self) -> None:
        raise TypeError(f"OAuth {self._label} cannot be serialized")

    def __reduce_ex__(self, _protocol: int) -> None:
        raise TypeError(f"OAuth {self._label} cannot be serialized")


class OAuthStateSecret(_RedactedSecret):
    _label = "state"

    def __init__(self, value: str) -> None:
        if not isinstance(value, str) or not _STATE.fullmatch(value):
            raise ValueError("state must be 43-256 unreserved characters")
        super().__init__(value)


class OAuthPkceVerifierSecret(_RedactedSecret):
    _label = "PKCE verifier"

    def __init__(self, value: str) -> None:
        pkce_s256_challenge(value)
        super().__init__(value)


class OAuthAuthorizationCodeSecret(_RedactedSecret):
    _label = "authorization code"

    def __init__(self, value: str) -> None:
        if not isinstance(value, str) or not _AUTHORIZATION_CODE.fullmatch(value):
            raise ValueError("authorization_code is invalid")
        super().__init__(value)


class OAuthCallbackSecrets:
    """Ephemeral callback values; the browser never supplies a PKCE verifier."""

    __slots__ = ("_authorization_code", "_state")

    def __init__(self, *, authorization_code: str, state: str) -> None:
        self._authorization_code = OAuthAuthorizationCodeSecret(authorization_code)
        self._state = OAuthStateSecret(state)

    @property
    def authorization_code(self) -> OAuthAuthorizationCodeSecret:
        return self._authorization_code

    @property
    def state(self) -> OAuthStateSecret:
        return self._state

    def __repr__(self) -> str:
        return "OAuthCallbackSecrets(authorization_code='<redacted>', state='<redacted>')"

    def __getstate__(self) -> None:
        raise TypeError("OAuth callback secrets cannot be serialized")

    def __reduce_ex__(self, _protocol: int) -> None:
        raise TypeError("OAuth callback secrets cannot be serialized")


@dataclass(frozen=True, slots=True, repr=False)
class OAuthBrokerFlowCommand:
    """Full immutable key under which the broker takes verifier custody."""

    flow_id: str
    nonce_id: str
    owner_id: str
    connection_id: str
    connection_incarnation_id: str
    expected_base_revision: int
    current_flow_nonce_sha256: str = field(repr=False)
    session_binding_sha256: str = field(repr=False)
    provider: ConnectorProvider
    resource: ConnectorResource
    account_kind: ConnectorAccountKind
    actions: frozenset[ConnectorActionKind] = field(repr=False)
    actions_sha256: str = field(repr=False)
    requested_scopes: frozenset[str] = field(repr=False)
    requested_scopes_sha256: str = field(repr=False)
    state_sha256: str = field(repr=False)
    pkce_challenge: str = field(repr=False)
    redirect_uri: str
    created_at: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        for name in (
            "flow_id",
            "nonce_id",
            "owner_id",
            "connection_id",
            "connection_incarnation_id",
        ):
            object.__setattr__(self, name, _uuid(getattr(self, name), name))
        object.__setattr__(
            self,
            "expected_base_revision",
            _revision(self.expected_base_revision),
        )
        object.__setattr__(
            self,
            "current_flow_nonce_sha256",
            _sha256(self.current_flow_nonce_sha256, "current_flow_nonce_sha256"),
        )
        if self.current_flow_nonce_sha256 != _digest(self.nonce_id):
            raise ValueError("current_flow_nonce_sha256 must bind the exact flow nonce")
        object.__setattr__(
            self,
            "session_binding_sha256",
            _sha256(self.session_binding_sha256, "session_binding_sha256"),
        )
        if not isinstance(self.provider, ConnectorProvider):
            raise TypeError("provider must be a ConnectorProvider")
        if not isinstance(self.resource, ConnectorResource):
            raise TypeError("resource must be a ConnectorResource")
        if not isinstance(self.account_kind, ConnectorAccountKind):
            raise TypeError("account_kind must be a ConnectorAccountKind")
        normalized_actions, planned_scopes = _exact_plan(
            provider=self.provider,
            resource=self.resource,
            account_kind=self.account_kind,
            actions=self.actions,
        )
        object.__setattr__(self, "actions", normalized_actions)
        object.__setattr__(self, "actions_sha256", _sha256(self.actions_sha256, "actions_sha256"))
        if self.actions_sha256 != _action_hash(normalized_actions):
            raise ValueError("actions_sha256 does not match the exact action set")
        normalized_scopes = _scopes(self.requested_scopes)
        object.__setattr__(self, "requested_scopes", normalized_scopes)
        if normalized_scopes != planned_scopes:
            raise ValueError("requested_scopes must exactly match the delegated action plan")
        object.__setattr__(
            self,
            "requested_scopes_sha256",
            _sha256(self.requested_scopes_sha256, "requested_scopes_sha256"),
        )
        if self.requested_scopes_sha256 != _scope_hash(normalized_scopes):
            raise ValueError("requested_scopes_sha256 does not match the exact scope set")
        object.__setattr__(self, "state_sha256", _sha256(self.state_sha256, "state_sha256"))
        if not isinstance(self.pkce_challenge, str) or not _PKCE_CHALLENGE.fullmatch(
            self.pkce_challenge
        ):
            raise ValueError("pkce_challenge must be an RFC 7636 S256 challenge")
        object.__setattr__(self, "redirect_uri", _redirect_uri(self.redirect_uri))
        created = _aware(self.created_at, "created_at")
        expires = _aware(self.expires_at, "expires_at")
        object.__setattr__(self, "created_at", created)
        object.__setattr__(self, "expires_at", expires)
        if expires <= created or expires - created > _MAX_FLOW_TTL:
            raise ValueError("OAuth flow lifetime must be positive and at most 10 minutes")

    @property
    def binding_sha256(self) -> str:
        return _flow_binding(
            flow_id=self.flow_id,
            nonce_id=self.nonce_id,
            owner_id=self.owner_id,
            connection_id=self.connection_id,
            connection_incarnation_id=self.connection_incarnation_id,
            expected_base_revision=self.expected_base_revision,
            current_flow_nonce_sha256=self.current_flow_nonce_sha256,
            session_binding_sha256=self.session_binding_sha256,
            provider=self.provider,
            resource=self.resource,
            account_kind=self.account_kind,
            actions_sha256=self.actions_sha256,
            requested_scopes_sha256=self.requested_scopes_sha256,
            state_sha256=self.state_sha256,
            pkce_challenge=self.pkce_challenge,
            redirect_uri=self.redirect_uri,
            created_at=self.created_at,
            expires_at=self.expires_at,
        )

    def __repr__(self) -> str:
        return (
            "OAuthBrokerFlowCommand("
            f"flow_id={self.flow_id!r}, provider={self.provider.value!r}, "
            f"resource={self.resource.value!r}, action_count={len(self.actions)}, "
            f"scope_count={len(self.requested_scopes)}, bindings='<redacted>')"
        )


@dataclass(frozen=True, slots=True, repr=False)
class OAuthBrokerFlowReceipt:
    flow_id: str
    connection_id: str
    connection_incarnation_id: str
    expected_base_revision: int
    current_flow_nonce_sha256: str = field(repr=False)
    flow_binding_sha256: str = field(repr=False)
    accepted_at: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        for name in ("flow_id", "connection_id", "connection_incarnation_id"):
            object.__setattr__(self, name, _uuid(getattr(self, name), name))
        object.__setattr__(
            self,
            "expected_base_revision",
            _revision(self.expected_base_revision),
        )
        object.__setattr__(
            self,
            "current_flow_nonce_sha256",
            _sha256(self.current_flow_nonce_sha256, "current_flow_nonce_sha256"),
        )
        object.__setattr__(
            self,
            "flow_binding_sha256",
            _sha256(self.flow_binding_sha256, "flow_binding_sha256"),
        )
        accepted = _aware(self.accepted_at, "accepted_at")
        expires = _aware(self.expires_at, "expires_at")
        object.__setattr__(self, "accepted_at", accepted)
        object.__setattr__(self, "expires_at", expires)
        if expires <= accepted:
            raise ValueError("broker verifier custody expiry must follow acceptance")

    def __repr__(self) -> str:
        return (
            "OAuthBrokerFlowReceipt("
            f"flow_id={self.flow_id!r}, accepted_at={self.accepted_at!r}, "
            "binding='<redacted>')"
        )


@dataclass(frozen=True, slots=True, repr=False)
class OAuthBrokerFlowLookup:
    flow_id: str
    owner_id: str
    connection_id: str
    connection_incarnation_id: str
    expected_base_revision: int
    current_flow_nonce_sha256: str = field(repr=False)

    def __post_init__(self) -> None:
        for name in (
            "flow_id",
            "owner_id",
            "connection_id",
            "connection_incarnation_id",
        ):
            object.__setattr__(self, name, _uuid(getattr(self, name), name))
        object.__setattr__(
            self,
            "expected_base_revision",
            _revision(self.expected_base_revision),
        )
        object.__setattr__(
            self,
            "current_flow_nonce_sha256",
            _sha256(self.current_flow_nonce_sha256, "current_flow_nonce_sha256"),
        )

    def __repr__(self) -> str:
        return (
            "OAuthBrokerFlowLookup("
            f"flow_id={self.flow_id!r}, connection_id={self.connection_id!r}, "
            "nonce='<redacted>')"
        )


@dataclass(frozen=True, slots=True, repr=False)
class OAuthBrokerStartRecovery:
    """Ephemeral recovery view over a broker-durable start record."""

    command: OAuthBrokerFlowCommand
    receipt: OAuthBrokerFlowReceipt
    authorization_state: OAuthStateSecret = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if not isinstance(self.command, OAuthBrokerFlowCommand):
            raise TypeError("command must be OAuthBrokerFlowCommand")
        if not isinstance(self.receipt, OAuthBrokerFlowReceipt):
            raise TypeError("receipt must be OAuthBrokerFlowReceipt")
        if not isinstance(self.authorization_state, OAuthStateSecret):
            raise TypeError("authorization_state must be OAuthStateSecret")
        if _digest(self.authorization_state.value) != self.command.state_sha256:
            raise ValueError("authorization_state does not bind the broker start record")

    def __repr__(self) -> str:
        return (
            "OAuthBrokerStartRecovery("
            f"flow_id={self.command.flow_id!r}, state='<redacted>', binding='<redacted>')"
        )

    def __getstate__(self) -> None:
        raise TypeError("OAuth broker start recovery cannot be serialized")

    def __reduce_ex__(self, _protocol: int) -> None:
        raise TypeError("OAuth broker start recovery cannot be serialized")


@dataclass(frozen=True, slots=True, repr=False)
class OAuthFlowRecord:
    flow_id: str
    nonce_id: str
    owner_id: str
    connection_id: str
    connection_incarnation_id: str
    expected_base_revision: int
    current_flow_nonce_sha256: str = field(repr=False)
    session_binding_sha256: str = field(repr=False)
    provider: ConnectorProvider
    resource: ConnectorResource
    account_kind: ConnectorAccountKind
    actions: frozenset[ConnectorActionKind] = field(repr=False)
    actions_sha256: str = field(repr=False)
    requested_scopes: frozenset[str] = field(repr=False)
    requested_scopes_sha256: str = field(repr=False)
    state_sha256: str = field(repr=False)
    pkce_challenge: str = field(repr=False)
    broker_flow_binding_sha256: str = field(repr=False)
    redirect_uri: str
    created_at: datetime
    expires_at: datetime
    state: OAuthFlowState = OAuthFlowState.PENDING
    consumed_at: datetime | None = None

    def __post_init__(self) -> None:
        command = OAuthBrokerFlowCommand(
            flow_id=self.flow_id,
            nonce_id=self.nonce_id,
            owner_id=self.owner_id,
            connection_id=self.connection_id,
            connection_incarnation_id=self.connection_incarnation_id,
            expected_base_revision=self.expected_base_revision,
            current_flow_nonce_sha256=self.current_flow_nonce_sha256,
            session_binding_sha256=self.session_binding_sha256,
            provider=self.provider,
            resource=self.resource,
            account_kind=self.account_kind,
            actions=self.actions,
            actions_sha256=self.actions_sha256,
            requested_scopes=self.requested_scopes,
            requested_scopes_sha256=self.requested_scopes_sha256,
            state_sha256=self.state_sha256,
            pkce_challenge=self.pkce_challenge,
            redirect_uri=self.redirect_uri,
            created_at=self.created_at,
            expires_at=self.expires_at,
        )
        for name in (
            "flow_id",
            "nonce_id",
            "owner_id",
            "connection_id",
            "connection_incarnation_id",
            "expected_base_revision",
            "current_flow_nonce_sha256",
            "session_binding_sha256",
            "provider",
            "resource",
            "account_kind",
            "actions",
            "actions_sha256",
            "requested_scopes",
            "requested_scopes_sha256",
            "state_sha256",
            "pkce_challenge",
            "redirect_uri",
            "created_at",
            "expires_at",
        ):
            object.__setattr__(self, name, getattr(command, name))
        object.__setattr__(
            self,
            "broker_flow_binding_sha256",
            _sha256(self.broker_flow_binding_sha256, "broker_flow_binding_sha256"),
        )
        if self.broker_flow_binding_sha256 != command.binding_sha256:
            raise ValueError("broker_flow_binding_sha256 must bind the exact OAuth flow")
        if not isinstance(self.state, OAuthFlowState):
            raise TypeError("state must be an OAuthFlowState")
        if self.state is OAuthFlowState.PENDING:
            if self.consumed_at is not None:
                raise ValueError("pending OAuth flow cannot have consumed_at")
        else:
            if self.consumed_at is None:
                raise ValueError("consumed OAuth flow requires consumed_at")
            consumed = _aware(self.consumed_at, "consumed_at")
            object.__setattr__(self, "consumed_at", consumed)
            if consumed < self.created_at or consumed >= self.expires_at:
                raise ValueError("consumed_at must fall before the exclusive OAuth expiry")

    @classmethod
    def from_broker_command(cls, command: OAuthBrokerFlowCommand) -> OAuthFlowRecord:
        return cls(
            flow_id=command.flow_id,
            nonce_id=command.nonce_id,
            owner_id=command.owner_id,
            connection_id=command.connection_id,
            connection_incarnation_id=command.connection_incarnation_id,
            expected_base_revision=command.expected_base_revision,
            current_flow_nonce_sha256=command.current_flow_nonce_sha256,
            session_binding_sha256=command.session_binding_sha256,
            provider=command.provider,
            resource=command.resource,
            account_kind=command.account_kind,
            actions=command.actions,
            actions_sha256=command.actions_sha256,
            requested_scopes=command.requested_scopes,
            requested_scopes_sha256=command.requested_scopes_sha256,
            state_sha256=command.state_sha256,
            pkce_challenge=command.pkce_challenge,
            broker_flow_binding_sha256=command.binding_sha256,
            redirect_uri=command.redirect_uri,
            created_at=command.created_at,
            expires_at=command.expires_at,
        )

    @property
    def binding_sha256(self) -> str:
        return self.broker_flow_binding_sha256

    def active_at(self, now: datetime) -> bool:
        reference = _aware(now, "now")
        return (
            self.state is OAuthFlowState.PENDING
            and self.consumed_at is None
            and self.created_at <= reference < self.expires_at
        )

    def __repr__(self) -> str:
        return (
            "OAuthFlowRecord("
            f"flow_id={self.flow_id!r}, provider={self.provider.value!r}, "
            f"resource={self.resource.value!r}, state={self.state.value!r}, "
            f"action_count={len(self.actions)}, scope_count={len(self.requested_scopes)}, "
            "bindings='<redacted>')"
        )


@dataclass(frozen=True, slots=True, repr=False)
class OAuthStartResult:
    flow: OAuthFlowRecord
    authorization_state: OAuthStateSecret = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if not isinstance(self.flow, OAuthFlowRecord):
            raise TypeError("flow must be an OAuthFlowRecord")
        if not isinstance(self.authorization_state, OAuthStateSecret):
            raise TypeError("authorization_state must be OAuthStateSecret")
        if _digest(self.authorization_state.value) != self.flow.state_sha256:
            raise ValueError("authorization_state does not bind the flow")

    def __repr__(self) -> str:
        return f"OAuthStartResult(flow_id={self.flow.flow_id!r}, state='<redacted>')"


def _validate_broker_flow_receipt(
    command: OAuthBrokerFlowCommand,
    receipt: OAuthBrokerFlowReceipt,
) -> None:
    if not isinstance(receipt, OAuthBrokerFlowReceipt):
        raise OAuthContractError("OAUTH_BROKER_FLOW_RECEIPT_INVALID")
    if (
        receipt.flow_id != command.flow_id
        or receipt.connection_id != command.connection_id
        or receipt.connection_incarnation_id != command.connection_incarnation_id
        or receipt.expected_base_revision != command.expected_base_revision
        or receipt.current_flow_nonce_sha256 != command.current_flow_nonce_sha256
        or receipt.flow_binding_sha256 != command.binding_sha256
        or receipt.accepted_at < command.created_at
        or receipt.accepted_at >= command.expires_at
        or receipt.expires_at != command.expires_at
    ):
        raise OAuthContractError("OAUTH_BROKER_FLOW_BINDING_MISMATCH")


def _validate_start_recovery(
    recovery: OAuthBrokerStartRecovery,
    *,
    lookup: OAuthBrokerFlowLookup,
    provider: ConnectorProvider,
    resource: ConnectorResource,
    account_kind: ConnectorAccountKind,
    actions: frozenset[ConnectorActionKind],
    redirect_uri: str,
    created_at: datetime,
    expires_at: datetime,
    session_binding_sha256: str,
) -> OAuthBrokerFlowCommand:
    if not isinstance(recovery, OAuthBrokerStartRecovery):
        raise OAuthContractError("OAUTH_BROKER_START_RECORD_INVALID")
    command = recovery.command
    _validate_broker_flow_receipt(command, recovery.receipt)
    if (
        command.flow_id != lookup.flow_id
        or command.owner_id != lookup.owner_id
        or command.connection_id != lookup.connection_id
        or command.connection_incarnation_id != lookup.connection_incarnation_id
        or command.expected_base_revision != lookup.expected_base_revision
        or command.current_flow_nonce_sha256 != lookup.current_flow_nonce_sha256
        or command.provider is not provider
        or command.resource is not resource
        or command.account_kind is not account_kind
        or command.actions != actions
        or command.redirect_uri != redirect_uri
        or command.created_at != created_at
        or command.expires_at != expires_at
        or command.session_binding_sha256 != session_binding_sha256
    ):
        raise OAuthContractError("OAUTH_BROKER_START_BINDING_MISMATCH")
    return command


class OAuthCredentialBroker(Protocol):
    """Broker boundary with internal one-use verifier custody.

    ``begin_flow`` is idempotent by ``flow_id`` plus the entire command binding.
    An identical replay returns the existing receipt; a binding mismatch must
    fail without replacing custody.  ``exchange_once`` similarly keys the
    durable attempt/terminal by exchange ID plus full exchange binding. It
    requires the repository-issued opaque capability.  A broker implementation
    is composed once with its trusted permit authority; that authority is not
    an application-callable argument and cannot be substituted for an exchange.
    At its attempt-fence boundary the broker calls only that bound authority,
    which atomically verifies provenance and current live connection state,
    consumes the permit, and records the durable dispatch fence.  Neither an
    authority nor a prebuilt claim may cross this protocol boundary.  The broker
    dispatches only for the fresh claim returned internally by its bound
    authority; the exact permit binding cannot be reused. Before a provider
    call it records an attempt
    fence; a crash or uncertain provider
    outcome is exposed by readback as a durable ``OAuthExchangeAmbiguous`` and
    never causes a second provider exchange.  It persists a successful grant
    before erasing the verifier and never erases verifier custody for an
    ambiguous exchange.  Under the same attempt-fence transaction, the broker
    uses its own trusted clock and records a durable ``deadline_expired`` fence
    instead of dispatching when broker-now is at or beyond ``deadline_at``;
    caller-provided time is never authoritative for dispatch.
    """

    async def begin_flow(
        self,
        *,
        command: OAuthBrokerFlowCommand,
        authorization_state: OAuthStateSecret,
        verifier: OAuthPkceVerifierSecret,
    ) -> OAuthBrokerStartRecovery: ...

    async def read_flow(
        self,
        *,
        lookup: OAuthBrokerFlowLookup,
    ) -> OAuthBrokerStartRecovery | None: ...

    async def exchange_once(
        self,
        *,
        command: OAuthExchangeCommand,
        permit: OAuthExchangePermit,
        authorization_code: OAuthAuthorizationCodeSecret,
    ) -> OAuthExchangeTerminal: ...

    async def read_exchange(
        self,
        *,
        command: OAuthExchangeCommand,
    ) -> OAuthExchangeTerminal | None: ...


async def start_oauth_flow(
    *,
    flow_id: str,
    nonce_id: str,
    owner_id: str,
    connection_id: str,
    connection_incarnation_id: str,
    expected_base_revision: int,
    current_flow_nonce_sha256: str,
    session_binding_sha256: str,
    provider: ConnectorProvider,
    resource: ConnectorResource,
    account_kind: ConnectorAccountKind,
    actions: frozenset[ConnectorActionKind],
    redirect_uri: str,
    redirect_allowlist: OAuthRedirectAllowlist,
    created_at: datetime,
    expires_at: datetime,
    broker: OAuthCredentialBroker,
    repository: OAuthFlowRepository,
) -> OAuthStartResult:
    """Recover or create one broker-custodied and repository-durable start."""

    if not isinstance(redirect_allowlist, OAuthRedirectAllowlist):
        raise TypeError("redirect_allowlist must be an OAuthRedirectAllowlist")
    allowed_redirect = redirect_allowlist.require(redirect_uri)
    canonical_nonce_id = _uuid(nonce_id, "nonce_id")
    normalized_flow_nonce_hash = _sha256(
        current_flow_nonce_sha256,
        "current_flow_nonce_sha256",
    )
    if normalized_flow_nonce_hash != _digest(canonical_nonce_id):
        raise ValueError("current_flow_nonce_sha256 must bind the exact flow nonce")
    created = _aware(created_at, "created_at")
    expires = _aware(expires_at, "expires_at")
    normalized_actions, planned_scopes = _exact_plan(
        provider=provider,
        resource=resource,
        account_kind=account_kind,
        actions=actions,
    )
    lookup = OAuthBrokerFlowLookup(
        flow_id=flow_id,
        owner_id=owner_id,
        connection_id=connection_id,
        connection_incarnation_id=connection_incarnation_id,
        expected_base_revision=expected_base_revision,
        current_flow_nonce_sha256=normalized_flow_nonce_hash,
    )

    async def read_broker_start() -> OAuthBrokerStartRecovery | None:
        try:
            return await broker.read_flow(lookup=lookup)
        except Exception:
            raise _external_failure("OAUTH_BROKER_FLOW_READ_FAILED") from None

    recovery = await read_broker_start()
    creating_broker_start = recovery is None
    if recovery is None:
        state = OAuthStateSecret(secrets.token_urlsafe(48))
        verifier = OAuthPkceVerifierSecret(secrets.token_urlsafe(64))
        command = OAuthBrokerFlowCommand(
            flow_id=flow_id,
            nonce_id=canonical_nonce_id,
            owner_id=owner_id,
            connection_id=connection_id,
            connection_incarnation_id=connection_incarnation_id,
            expected_base_revision=expected_base_revision,
            current_flow_nonce_sha256=normalized_flow_nonce_hash,
            session_binding_sha256=session_binding_sha256,
            provider=provider,
            resource=resource,
            account_kind=account_kind,
            actions=normalized_actions,
            actions_sha256=_action_hash(normalized_actions),
            requested_scopes=planned_scopes,
            requested_scopes_sha256=_scope_hash(planned_scopes),
            state_sha256=_digest(state.value),
            pkce_challenge=pkce_s256_challenge(verifier.value),
            redirect_uri=allowed_redirect,
            created_at=created,
            expires_at=expires,
        )

        async def begin_broker_start() -> OAuthBrokerStartRecovery | None:
            try:
                return await broker.begin_flow(
                    command=command,
                    authorization_state=state,
                    verifier=verifier,
                )
            except OAuthBrokerBeginResponseLost:
                return None
            except Exception:
                raise _external_failure("OAUTH_BROKER_BEGIN_FAILED") from None

        recovery = await begin_broker_start()
        if recovery is None:
            recovery = await read_broker_start()
            if recovery is None:
                recovery = await begin_broker_start()
                if recovery is None:
                    recovery = await read_broker_start()
                    if recovery is None:
                        raise OAuthContractError("OAUTH_BROKER_CUSTODY_UNCONFIRMED")

    if creating_broker_start:
        durable_recovery = await read_broker_start()
        if durable_recovery is None:
            raise OAuthContractError("OAUTH_BROKER_CUSTODY_UNCONFIRMED")
        recovery = durable_recovery

    command = _validate_start_recovery(
        recovery,
        lookup=lookup,
        provider=provider,
        resource=resource,
        account_kind=account_kind,
        actions=normalized_actions,
        redirect_uri=allowed_redirect,
        created_at=created,
        expires_at=expires,
        session_binding_sha256=_sha256(session_binding_sha256, "session_binding_sha256"),
    )
    flow = OAuthFlowRecord.from_broker_command(command)

    async def read_pending() -> OAuthFlowRecord | None:
        try:
            return await repository.read_pending(
                flow_id=flow.flow_id,
                expected_flow_binding_sha256=flow.binding_sha256,
            )
        except Exception:
            raise _external_failure("OAUTH_FLOW_READ_FAILED") from None

    pending = await read_pending()
    if pending is not None:
        if not isinstance(pending, OAuthFlowRecord) or pending != flow:
            raise OAuthContractError("OAUTH_PENDING_FLOW_BINDING_MISMATCH")
    else:
        async def create_pending() -> bool:
            try:
                await repository.create_pending(flow)
                return True
            except OAuthFlowCreateResponseLost:
                return False
            except Exception:
                raise _external_failure("OAUTH_FLOW_CREATE_FAILED") from None

        created_ok = await create_pending()
        if not created_ok:
            pending = await read_pending()
            if pending is None:
                created_ok = await create_pending()
                if not created_ok:
                    pending = await read_pending()
                    if pending is None:
                        raise OAuthContractError("OAUTH_FLOW_CREATE_UNCONFIRMED")
            elif not isinstance(pending, OAuthFlowRecord) or pending != flow:
                raise OAuthContractError("OAUTH_PENDING_FLOW_BINDING_MISMATCH")

    # Never return browser state from a detached pending-flow read. This final
    # repository operation takes the connection lock and revalidates active
    # state, base revision, incarnation, current-flow nonce, owner/session,
    # provider/resource/account kind, and the exact pending binding.
    try:
        validated_pending = await repository.revalidate_pending(flow)
    except Exception:
        raise _external_failure("OAUTH_FLOW_REVALIDATE_FAILED") from None
    if not isinstance(validated_pending, OAuthFlowRecord) or validated_pending != flow:
        raise OAuthContractError("OAUTH_PENDING_FLOW_BINDING_MISMATCH")
    return OAuthStartResult(
        flow=validated_pending,
        authorization_state=recovery.authorization_state,
    )


@dataclass(frozen=True, slots=True, repr=False)
class OAuthCallbackAttempt:
    flow_id: str
    owner_id: str
    session_binding_sha256: str = field(repr=False)
    provider: ConnectorProvider
    resource: ConnectorResource
    account_kind: ConnectorAccountKind
    redirect_uri: str
    secrets: OAuthCallbackSecrets = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "flow_id", _uuid(self.flow_id, "flow_id"))
        object.__setattr__(self, "owner_id", _uuid(self.owner_id, "owner_id"))
        object.__setattr__(
            self,
            "session_binding_sha256",
            _sha256(self.session_binding_sha256, "session_binding_sha256"),
        )
        if not isinstance(self.provider, ConnectorProvider):
            raise TypeError("provider must be a ConnectorProvider")
        if not isinstance(self.resource, ConnectorResource):
            raise TypeError("resource must be a ConnectorResource")
        if not isinstance(self.account_kind, ConnectorAccountKind):
            raise TypeError("account_kind must be a ConnectorAccountKind")
        object.__setattr__(self, "redirect_uri", _redirect_uri(self.redirect_uri))
        if not isinstance(self.secrets, OAuthCallbackSecrets):
            raise TypeError("secrets must be OAuthCallbackSecrets")

    def __repr__(self) -> str:
        return (
            "OAuthCallbackAttempt("
            f"flow_id={self.flow_id!r}, provider={self.provider.value!r}, "
            "session='<redacted>', secrets='<redacted>')"
        )


@dataclass(frozen=True, slots=True, repr=False)
class OAuthConsumeCommand:
    consumption_id: str
    flow_id: str
    owner_id: str
    connection_id: str
    connection_incarnation_id: str
    expected_base_revision: int
    current_flow_nonce_sha256: str = field(repr=False)
    session_binding_sha256: str = field(repr=False)
    provider: ConnectorProvider
    resource: ConnectorResource
    account_kind: ConnectorAccountKind
    redirect_uri: str
    state_sha256: str = field(repr=False)
    flow_binding_sha256: str = field(repr=False)
    flow_created_at: datetime
    flow_expires_at: datetime

    def __post_init__(self) -> None:
        for name in (
            "consumption_id",
            "flow_id",
            "owner_id",
            "connection_id",
            "connection_incarnation_id",
        ):
            object.__setattr__(self, name, _uuid(getattr(self, name), name))
        object.__setattr__(
            self,
            "expected_base_revision",
            _revision(self.expected_base_revision),
        )
        for name in (
            "current_flow_nonce_sha256",
            "session_binding_sha256",
            "state_sha256",
            "flow_binding_sha256",
        ):
            object.__setattr__(self, name, _sha256(getattr(self, name), name))
        if not isinstance(self.provider, ConnectorProvider):
            raise TypeError("provider must be a ConnectorProvider")
        if not isinstance(self.resource, ConnectorResource):
            raise TypeError("resource must be a ConnectorResource")
        if not isinstance(self.account_kind, ConnectorAccountKind):
            raise TypeError("account_kind must be a ConnectorAccountKind")
        object.__setattr__(self, "redirect_uri", _redirect_uri(self.redirect_uri))
        created = _aware(self.flow_created_at, "flow_created_at")
        expires = _aware(self.flow_expires_at, "flow_expires_at")
        object.__setattr__(self, "flow_created_at", created)
        object.__setattr__(self, "flow_expires_at", expires)
        if expires <= created or expires - created > _MAX_FLOW_TTL:
            raise ValueError("consume command must bind the exact bounded flow lifetime")

    @property
    def binding_sha256(self) -> str:
        return _canonical_hash(
            {
                "version": _CONSUME_BINDING_VERSION,
                "consumption_id": self.consumption_id,
                "flow_id": self.flow_id,
                "owner_id": self.owner_id,
                "connection_id": self.connection_id,
                "connection_incarnation_id": self.connection_incarnation_id,
                "expected_base_revision": self.expected_base_revision,
                "current_flow_nonce_sha256": self.current_flow_nonce_sha256,
                "session_binding_sha256": self.session_binding_sha256,
                "provider": self.provider.value,
                "resource": self.resource.value,
                "account_kind": self.account_kind.value,
                "redirect_uri": self.redirect_uri,
                "state_sha256": self.state_sha256,
                "flow_binding_sha256": self.flow_binding_sha256,
                "flow_created_at": self.flow_created_at.isoformat(),
                "flow_expires_at": self.flow_expires_at.isoformat(),
            }
        )

    def __repr__(self) -> str:
        return (
            "OAuthConsumeCommand("
            f"consumption_id={self.consumption_id!r}, flow_id={self.flow_id!r}, "
            f"provider={self.provider.value!r}, bindings='<redacted>')"
        )


@dataclass(frozen=True, slots=True, repr=False)
class OAuthFlowConsumption:
    consumption_id: str
    flow_id: str
    connection_id: str
    connection_incarnation_id: str
    expected_base_revision: int
    current_flow_nonce_sha256: str = field(repr=False)
    consume_binding_sha256: str = field(repr=False)
    flow_binding_sha256: str = field(repr=False)
    consumed_at: datetime

    def __post_init__(self) -> None:
        for name in (
            "consumption_id",
            "flow_id",
            "connection_id",
            "connection_incarnation_id",
        ):
            object.__setattr__(self, name, _uuid(getattr(self, name), name))
        object.__setattr__(
            self,
            "expected_base_revision",
            _revision(self.expected_base_revision),
        )
        for name in (
            "current_flow_nonce_sha256",
            "consume_binding_sha256",
            "flow_binding_sha256",
        ):
            object.__setattr__(self, name, _sha256(getattr(self, name), name))
        object.__setattr__(self, "consumed_at", _aware(self.consumed_at, "consumed_at"))

    @classmethod
    def build_for_command(
        cls,
        command: OAuthConsumeCommand,
        *,
        consumed_at: datetime,
    ) -> OAuthFlowConsumption:
        consumed = _aware(consumed_at, "consumed_at")
        if consumed < command.flow_created_at or consumed >= command.flow_expires_at:
            raise OAuthContractError("OAUTH_FLOW_EXPIRED_OR_CONSUMED")
        return cls(
            consumption_id=command.consumption_id,
            flow_id=command.flow_id,
            connection_id=command.connection_id,
            connection_incarnation_id=command.connection_incarnation_id,
            expected_base_revision=command.expected_base_revision,
            current_flow_nonce_sha256=command.current_flow_nonce_sha256,
            consume_binding_sha256=command.binding_sha256,
            flow_binding_sha256=command.flow_binding_sha256,
            consumed_at=consumed,
        )

    def __repr__(self) -> str:
        return (
            "OAuthFlowConsumption("
            f"consumption_id={self.consumption_id!r}, flow_id={self.flow_id!r}, "
            "bindings='<redacted>')"
        )


def _consume_command_for_flow(flow: OAuthFlowRecord) -> OAuthConsumeCommand:
    return OAuthConsumeCommand(
        consumption_id=flow.flow_id,
        flow_id=flow.flow_id,
        owner_id=flow.owner_id,
        connection_id=flow.connection_id,
        connection_incarnation_id=flow.connection_incarnation_id,
        expected_base_revision=flow.expected_base_revision,
        current_flow_nonce_sha256=flow.current_flow_nonce_sha256,
        session_binding_sha256=flow.session_binding_sha256,
        provider=flow.provider,
        resource=flow.resource,
        account_kind=flow.account_kind,
        redirect_uri=flow.redirect_uri,
        state_sha256=flow.state_sha256,
        flow_binding_sha256=flow.binding_sha256,
        flow_created_at=flow.created_at,
        flow_expires_at=flow.expires_at,
    )


def prepare_oauth_consumption(
    flow: OAuthFlowRecord,
    callback: OAuthCallbackAttempt,
    *,
    now: datetime,
) -> OAuthConsumeCommand:
    if not isinstance(flow, OAuthFlowRecord):
        raise TypeError("flow must be OAuthFlowRecord")
    if not isinstance(callback, OAuthCallbackAttempt):
        raise TypeError("callback must be OAuthCallbackAttempt")
    reference = _aware(now, "now")
    if not flow.active_at(reference):
        raise OAuthContractError("OAUTH_FLOW_EXPIRED_OR_CONSUMED")
    if (
        callback.flow_id != flow.flow_id
        or callback.owner_id != flow.owner_id
        or callback.session_binding_sha256 != flow.session_binding_sha256
        or callback.provider is not flow.provider
        or callback.resource is not flow.resource
        or callback.account_kind is not flow.account_kind
        or callback.redirect_uri != flow.redirect_uri
    ):
        raise OAuthContractError("OAUTH_CALLBACK_BINDING_MISMATCH")
    callback_state_hash = _digest(callback.secrets.state.value)
    if not hmac.compare_digest(callback_state_hash, flow.state_sha256):
        raise OAuthContractError("OAUTH_STATE_MISMATCH")
    # One flow has exactly one deterministic consumption identity.  This lets
    # a callback replay recover a response-lost atomic consume without minting
    # a second durable identity or persisting the authorization code.
    return _consume_command_for_flow(flow)


class OAuthFlowRepository(Protocol):
    """Atomic one-use flow store.

    ``create_pending`` is idempotent for the exact flow binding and, under the
    connection lock, verifies base revision/incarnation then installs the exact
    current-flow nonce, invalidating any older pending flow. ``consume_pending``
    takes both the connection and flow locks, requires the exact durable pending
    record, revalidates the active connection, owner, session, provider,
    resource, account kind, base revision, incarnation, and current-flow nonce,
    then uses the repository clock to reject an instant at or beyond the
    exclusive flow expiry. It is idempotent for the exact consumption ID and
    binding only after those live checks. A missing pending record—including a
    fresh repository—is a hard failure and can never synthesize consumption.

    ``issue_exchange_permit_once`` creates a CSPRNG capability. Only its digest
    and exact binding are stored in the durable permit row; recoverable raw
    capability material remains inside repository/broker secret custody and is
    returned solely as a redacted, unserializable object. ``read_exchange_permit``
    performs the same live-state validation.

    The broker, not application code, calls
    ``consume_exchange_permit_for_dispatch`` at attempt-fence time. Under the
    connection lock that operation authenticates the capability digest,
    revalidates active connection/current flow/revision/incarnation and the
    exact durable consumption, checks the repository clock and unconsumed row,
    then atomically marks the row consumed and records the durable dispatch
    attempt fence. Only the fresh transaction winner receives a claim. A
    revoked/replaced/newer-flow winner or any replay gets no dispatch claim.
    """

    async def create_pending(self, flow: OAuthFlowRecord) -> None: ...

    async def read_pending(
        self,
        *,
        flow_id: str,
        expected_flow_binding_sha256: str,
    ) -> OAuthFlowRecord | None: ...

    async def revalidate_pending(self, flow: OAuthFlowRecord) -> OAuthFlowRecord:
        """Atomically prove exact pending flow plus current live connection."""
        ...

    async def consume_pending(self, command: OAuthConsumeCommand) -> OAuthFlowConsumption: ...

    async def read_consumption(
        self,
        command: OAuthConsumeCommand,
    ) -> OAuthFlowConsumption | None: ...

    async def issue_exchange_permit_once(
        self,
        command: OAuthExchangeCommand,
    ) -> OAuthExchangePermit: ...

    async def read_exchange_permit(
        self,
        command: OAuthExchangeCommand,
    ) -> OAuthExchangePermit | None: ...

    async def consume_exchange_permit_for_dispatch(
        self,
        command: OAuthExchangeCommand,
        permit: OAuthExchangePermit,
    ) -> OAuthExchangePermitClaim: ...


def _validate_consumption(
    command: OAuthConsumeCommand,
    consumption: OAuthFlowConsumption,
) -> None:
    if not isinstance(consumption, OAuthFlowConsumption) or (
        consumption.consumption_id != command.consumption_id
        or consumption.flow_id != command.flow_id
        or consumption.connection_id != command.connection_id
        or consumption.connection_incarnation_id != command.connection_incarnation_id
        or consumption.expected_base_revision != command.expected_base_revision
        or consumption.current_flow_nonce_sha256 != command.current_flow_nonce_sha256
        or consumption.consume_binding_sha256 != command.binding_sha256
        or consumption.flow_binding_sha256 != command.flow_binding_sha256
        or consumption.consumed_at < command.flow_created_at
        or consumption.consumed_at >= command.flow_expires_at
    ):
        raise OAuthContractError("OAUTH_CONSUMPTION_BINDING_MISMATCH")


async def consume_oauth_flow_once(
    *,
    repository: OAuthFlowRepository,
    command: OAuthConsumeCommand,
) -> OAuthFlowConsumption:
    """Require an exact pending record and atomically consume under live authority."""

    async def read_consumption() -> OAuthFlowConsumption | None:
        try:
            return await repository.read_consumption(command)
        except Exception:
            raise _external_failure("OAUTH_CONSUMPTION_READ_FAILED") from None

    async def consume_pending() -> OAuthFlowConsumption | None:
        try:
            return await repository.consume_pending(command)
        except OAuthConsumeResponseLost:
            return None
        except Exception:
            raise _external_failure("OAUTH_CONSUMPTION_WRITE_FAILED") from None

    # Do not return a detached consumption readback before the repository has
    # atomically revalidated the durable pending record and live connection.
    # ``consume_pending`` is also the exact idempotent replay operation.
    consumption = await consume_pending()
    if consumption is None:
        consumption = await read_consumption()
        if consumption is None:
            # Safe only because the repository protocol requires an identical
            # key+binding replay and rejects every mismatched replay.
            consumption = await consume_pending()
            if consumption is None:
                consumption = await read_consumption()
                if consumption is None:
                    raise OAuthContractError("OAUTH_CONSUMPTION_UNCONFIRMED") from None
    _validate_consumption(command, consumption)
    return consumption


async def recover_oauth_flow_consumption(
    *,
    repository: OAuthFlowRepository,
    flow: OAuthFlowRecord,
) -> OAuthFlowConsumption | None:
    """Recover a consumed flow after process loss without callback secrets."""

    command = _consume_command_for_flow(flow)
    try:
        consumption = await repository.read_consumption(command)
    except Exception:
        raise _external_failure("OAUTH_CONSUMPTION_READ_FAILED") from None
    if consumption is None:
        return None
    _validate_consumption(command, consumption)
    return consumption


@dataclass(frozen=True, slots=True, repr=False)
class OAuthExchangeCommand:
    exchange_id: str
    consumption_id: str
    flow_id: str
    nonce_id: str
    owner_id: str
    connection_id: str
    connection_incarnation_id: str
    expected_base_revision: int
    current_flow_nonce_sha256: str = field(repr=False)
    session_binding_sha256: str = field(repr=False)
    provider: ConnectorProvider
    resource: ConnectorResource
    account_kind: ConnectorAccountKind
    redirect_uri: str
    actions_sha256: str = field(repr=False)
    requested_scopes_sha256: str = field(repr=False)
    flow_binding_sha256: str = field(repr=False)
    consume_binding_sha256: str = field(repr=False)
    pkce_challenge: str = field(repr=False)
    issued_at: datetime
    deadline_at: datetime

    def __post_init__(self) -> None:
        for name in (
            "exchange_id",
            "consumption_id",
            "flow_id",
            "nonce_id",
            "owner_id",
            "connection_id",
            "connection_incarnation_id",
        ):
            object.__setattr__(self, name, _uuid(getattr(self, name), name))
        object.__setattr__(
            self,
            "expected_base_revision",
            _revision(self.expected_base_revision),
        )
        for name in (
            "current_flow_nonce_sha256",
            "session_binding_sha256",
            "actions_sha256",
            "requested_scopes_sha256",
            "flow_binding_sha256",
            "consume_binding_sha256",
        ):
            object.__setattr__(self, name, _sha256(getattr(self, name), name))
        if not isinstance(self.provider, ConnectorProvider):
            raise TypeError("provider must be a ConnectorProvider")
        if not isinstance(self.resource, ConnectorResource):
            raise TypeError("resource must be a ConnectorResource")
        if not isinstance(self.account_kind, ConnectorAccountKind):
            raise TypeError("account_kind must be a ConnectorAccountKind")
        object.__setattr__(self, "redirect_uri", _redirect_uri(self.redirect_uri))
        if not isinstance(self.pkce_challenge, str) or not _PKCE_CHALLENGE.fullmatch(
            self.pkce_challenge
        ):
            raise ValueError("pkce_challenge must be an RFC 7636 S256 challenge")
        issued = _aware(self.issued_at, "issued_at")
        deadline = _aware(self.deadline_at, "deadline_at")
        object.__setattr__(self, "issued_at", issued)
        object.__setattr__(self, "deadline_at", deadline)
        if deadline <= issued or deadline - issued > _MAX_EXCHANGE_TTL:
            raise ValueError("OAuth exchange deadline must be positive and at most 2 minutes")

    @property
    def binding_sha256(self) -> str:
        return _canonical_hash(
            {
                "version": _EXCHANGE_BINDING_VERSION,
                "exchange_id": self.exchange_id,
                "consumption_id": self.consumption_id,
                "flow_id": self.flow_id,
                "nonce_id": self.nonce_id,
                "owner_id": self.owner_id,
                "connection_id": self.connection_id,
                "connection_incarnation_id": self.connection_incarnation_id,
                "expected_base_revision": self.expected_base_revision,
                "current_flow_nonce_sha256": self.current_flow_nonce_sha256,
                "session_binding_sha256": self.session_binding_sha256,
                "provider": self.provider.value,
                "resource": self.resource.value,
                "account_kind": self.account_kind.value,
                "redirect_uri": self.redirect_uri,
                "actions_sha256": self.actions_sha256,
                "requested_scopes_sha256": self.requested_scopes_sha256,
                "flow_binding_sha256": self.flow_binding_sha256,
                "consume_binding_sha256": self.consume_binding_sha256,
                "pkce_challenge": self.pkce_challenge,
                "issued_at": self.issued_at.isoformat(),
                "deadline_at": self.deadline_at.isoformat(),
            }
        )

    def __repr__(self) -> str:
        return (
            "OAuthExchangeCommand("
            f"exchange_id={self.exchange_id!r}, provider={self.provider.value!r}, "
            f"resource={self.resource.value!r}, redirect_uri={self.redirect_uri!r}, "
            "bindings='<redacted>')"
        )


@dataclass(frozen=True, slots=True, repr=False)
class OAuthExchangePermitRecord:
    """Durable repository row; stores only a digest of the opaque capability."""

    permit_id: str
    exchange_id: str
    consumption_id: str
    nonce_id: str
    owner_id: str
    connection_id: str
    connection_incarnation_id: str
    expected_base_revision: int
    current_flow_nonce_sha256: str = field(repr=False)
    session_binding_sha256: str = field(repr=False)
    provider: ConnectorProvider
    resource: ConnectorResource
    account_kind: ConnectorAccountKind
    flow_binding_sha256: str = field(repr=False)
    consume_binding_sha256: str = field(repr=False)
    exchange_binding_sha256: str = field(repr=False)
    capability_sha256: str = field(repr=False)
    issued_at: datetime
    expires_at: datetime
    consumed_at: datetime | None = None

    def __post_init__(self) -> None:
        for name in (
            "permit_id",
            "exchange_id",
            "consumption_id",
            "nonce_id",
            "owner_id",
            "connection_id",
            "connection_incarnation_id",
        ):
            object.__setattr__(self, name, _uuid(getattr(self, name), name))
        object.__setattr__(self, "expected_base_revision", _revision(self.expected_base_revision))
        for name in (
            "current_flow_nonce_sha256",
            "session_binding_sha256",
            "flow_binding_sha256",
            "consume_binding_sha256",
            "exchange_binding_sha256",
            "capability_sha256",
        ):
            object.__setattr__(self, name, _sha256(getattr(self, name), name))
        if self.permit_id != self.exchange_id:
            raise ValueError("permit_id must equal the exact exchange identity")
        if self.current_flow_nonce_sha256 != _digest(self.nonce_id):
            raise ValueError("exchange permit must bind the exact current-flow nonce")
        if not isinstance(self.provider, ConnectorProvider):
            raise TypeError("provider must be a ConnectorProvider")
        if not isinstance(self.resource, ConnectorResource):
            raise TypeError("resource must be a ConnectorResource")
        if not isinstance(self.account_kind, ConnectorAccountKind):
            raise TypeError("account_kind must be a ConnectorAccountKind")
        issued = _aware(self.issued_at, "issued_at")
        expires = _aware(self.expires_at, "expires_at")
        object.__setattr__(self, "issued_at", issued)
        object.__setattr__(self, "expires_at", expires)
        if expires <= issued or expires - issued > _MAX_EXCHANGE_TTL:
            raise ValueError("exchange permit lifetime must be positive and bounded")
        if self.consumed_at is not None:
            consumed = _aware(self.consumed_at, "consumed_at")
            object.__setattr__(self, "consumed_at", consumed)
            if consumed < issued or consumed >= expires:
                raise ValueError("permit consumption must precede the exclusive deadline")

    @property
    def binding_sha256(self) -> str:
        return _canonical_hash(
            {
                "version": _EXCHANGE_PERMIT_BINDING_VERSION,
                "permit_id": self.permit_id,
                "exchange_id": self.exchange_id,
                "consumption_id": self.consumption_id,
                "nonce_id": self.nonce_id,
                "owner_id": self.owner_id,
                "connection_id": self.connection_id,
                "connection_incarnation_id": self.connection_incarnation_id,
                "expected_base_revision": self.expected_base_revision,
                "current_flow_nonce_sha256": self.current_flow_nonce_sha256,
                "session_binding_sha256": self.session_binding_sha256,
                "provider": self.provider.value,
                "resource": self.resource.value,
                "account_kind": self.account_kind.value,
                "flow_binding_sha256": self.flow_binding_sha256,
                "consume_binding_sha256": self.consume_binding_sha256,
                "exchange_binding_sha256": self.exchange_binding_sha256,
                "capability_sha256": self.capability_sha256,
                "issued_at": self.issued_at.isoformat(),
                "expires_at": self.expires_at.isoformat(),
            }
        )

    def __repr__(self) -> str:
        return (
            "OAuthExchangePermitRecord("
            f"permit_id={self.permit_id!r}, consumed={self.consumed_at is not None}, "
            "bindings='<redacted>')"
        )


_EXCHANGE_PERMIT_FACTORY_KEY = object()


class OAuthExchangePermit:
    """Ephemeral opaque capability; raw material is redacted and unserializable."""

    __slots__ = (
        "_capability_secret",
        "_exchange_binding_sha256",
        "_permit_binding_sha256",
        "_permit_id",
    )

    def __init__(
        self,
        *,
        permit_id: str,
        exchange_binding_sha256: str,
        permit_binding_sha256: str,
        capability_secret: str,
        _factory_key: object,
    ) -> None:
        if _factory_key is not _EXCHANGE_PERMIT_FACTORY_KEY:
            raise TypeError("OAuth exchange permits are repository-issued capabilities")
        self._permit_id = _uuid(permit_id, "permit_id")
        self._exchange_binding_sha256 = _sha256(
            exchange_binding_sha256,
            "exchange_binding_sha256",
        )
        self._permit_binding_sha256 = _sha256(
            permit_binding_sha256,
            "permit_binding_sha256",
        )
        if not isinstance(capability_secret, str) or not _PERMIT_CAPABILITY.fullmatch(
            capability_secret
        ):
            raise ValueError("permit capability must be high-entropy unreserved text")
        self._capability_secret = capability_secret

    @property
    def permit_id(self) -> str:
        return self._permit_id

    @property
    def exchange_binding_sha256(self) -> str:
        return self._exchange_binding_sha256

    @property
    def permit_binding_sha256(self) -> str:
        return self._permit_binding_sha256

    def __repr__(self) -> str:
        return (
            "OAuthExchangePermit("
            f"permit_id={self.permit_id!r}, capability='<redacted>', "
            "bindings='<redacted>')"
        )

    def __getstate__(self) -> None:
        raise TypeError("OAuth exchange permit capability cannot be serialized")

    def __reduce_ex__(self, _protocol: int) -> None:
        raise TypeError("OAuth exchange permit capability cannot be serialized")


@dataclass(frozen=True, slots=True, repr=False)
class OAuthExchangePermitClaim:
    """Fresh transaction-winner claim created with the durable attempt fence."""

    permit_id: str
    exchange_binding_sha256: str = field(repr=False)
    permit_binding_sha256: str = field(repr=False)
    consumed_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "permit_id", _uuid(self.permit_id, "permit_id"))
        for name in ("exchange_binding_sha256", "permit_binding_sha256"):
            object.__setattr__(self, name, _sha256(getattr(self, name), name))
        object.__setattr__(self, "consumed_at", _aware(self.consumed_at, "consumed_at"))

    def __repr__(self) -> str:
        return (
            "OAuthExchangePermitClaim("
            f"permit_id={self.permit_id!r}, bindings='<redacted>')"
        )


def _exchange_permit_capability_sha256(permit: OAuthExchangePermit) -> str:
    if not isinstance(permit, OAuthExchangePermit):
        raise TypeError("permit must be an OAuthExchangePermit")
    return _digest(permit._capability_secret)


def _issue_exchange_permit(
    command: OAuthExchangeCommand,
    *,
    issued_at: datetime,
) -> tuple[OAuthExchangePermitRecord, OAuthExchangePermit]:
    """Repository implementation helper; raw capability never enters a durable row."""

    if not isinstance(command, OAuthExchangeCommand):
        raise TypeError("command must be OAuthExchangeCommand")
    issued = _aware(issued_at, "issued_at")
    if issued < command.issued_at or issued >= command.deadline_at:
        raise ValueError("permit issuance must precede the exclusive exchange deadline")
    capability_secret = secrets.token_urlsafe(72)
    if not _PERMIT_CAPABILITY.fullmatch(capability_secret):
        raise ValueError("CSPRNG returned an invalid permit capability")
    record = OAuthExchangePermitRecord(
        permit_id=command.exchange_id,
        exchange_id=command.exchange_id,
        consumption_id=command.consumption_id,
        nonce_id=command.nonce_id,
        owner_id=command.owner_id,
        connection_id=command.connection_id,
        connection_incarnation_id=command.connection_incarnation_id,
        expected_base_revision=command.expected_base_revision,
        current_flow_nonce_sha256=command.current_flow_nonce_sha256,
        session_binding_sha256=command.session_binding_sha256,
        provider=command.provider,
        resource=command.resource,
        account_kind=command.account_kind,
        flow_binding_sha256=command.flow_binding_sha256,
        consume_binding_sha256=command.consume_binding_sha256,
        exchange_binding_sha256=command.binding_sha256,
        capability_sha256=_digest(capability_secret),
        issued_at=issued,
        expires_at=command.deadline_at,
    )
    capability = OAuthExchangePermit(
        permit_id=record.permit_id,
        exchange_binding_sha256=record.exchange_binding_sha256,
        permit_binding_sha256=record.binding_sha256,
        capability_secret=capability_secret,
        _factory_key=_EXCHANGE_PERMIT_FACTORY_KEY,
    )
    return record, capability


def _validate_exchange_permit_record(
    command: OAuthExchangeCommand,
    record: OAuthExchangePermitRecord,
) -> None:
    if not isinstance(record, OAuthExchangePermitRecord) or (
        record.permit_id != command.exchange_id
        or record.exchange_id != command.exchange_id
        or record.consumption_id != command.consumption_id
        or record.nonce_id != command.nonce_id
        or record.owner_id != command.owner_id
        or record.connection_id != command.connection_id
        or record.connection_incarnation_id != command.connection_incarnation_id
        or record.expected_base_revision != command.expected_base_revision
        or record.current_flow_nonce_sha256 != command.current_flow_nonce_sha256
        or record.session_binding_sha256 != command.session_binding_sha256
        or record.provider is not command.provider
        or record.resource is not command.resource
        or record.account_kind is not command.account_kind
        or record.flow_binding_sha256 != command.flow_binding_sha256
        or record.consume_binding_sha256 != command.consume_binding_sha256
        or record.exchange_binding_sha256 != command.binding_sha256
        or record.issued_at < command.issued_at
        or record.issued_at >= command.deadline_at
        or record.expires_at != command.deadline_at
    ):
        raise OAuthContractError("OAUTH_EXCHANGE_PERMIT_RECORD_BINDING_MISMATCH")


def prepare_oauth_exchange(
    flow: OAuthFlowRecord,
    consumption: OAuthFlowConsumption,
) -> OAuthExchangeCommand:
    """Build a time-stable broker command without returning or accepting a verifier."""

    if not isinstance(flow, OAuthFlowRecord):
        raise TypeError("flow must be OAuthFlowRecord")
    if not isinstance(consumption, OAuthFlowConsumption):
        raise TypeError("consumption must be OAuthFlowConsumption")
    expected_consume_command = _consume_command_for_flow(flow)
    if (
        consumption.consumption_id != flow.flow_id
        or consumption.flow_id != flow.flow_id
        or consumption.connection_id != flow.connection_id
        or consumption.connection_incarnation_id != flow.connection_incarnation_id
        or consumption.expected_base_revision != flow.expected_base_revision
        or consumption.current_flow_nonce_sha256 != flow.current_flow_nonce_sha256
        or consumption.consume_binding_sha256 != expected_consume_command.binding_sha256
        or consumption.flow_binding_sha256 != flow.binding_sha256
        or consumption.consumed_at < flow.created_at
        or consumption.consumed_at >= flow.expires_at
    ):
        raise OAuthContractError("OAUTH_CONSUMPTION_BINDING_MISMATCH")
    deadline = min(flow.expires_at, consumption.consumed_at + _MAX_EXCHANGE_TTL)
    if deadline <= consumption.consumed_at:
        raise OAuthContractError("OAUTH_EXCHANGE_DEADLINE_EXPIRED")
    return OAuthExchangeCommand(
        exchange_id=consumption.consumption_id,
        consumption_id=consumption.consumption_id,
        flow_id=flow.flow_id,
        nonce_id=flow.nonce_id,
        owner_id=flow.owner_id,
        connection_id=flow.connection_id,
        connection_incarnation_id=flow.connection_incarnation_id,
        expected_base_revision=flow.expected_base_revision,
        current_flow_nonce_sha256=flow.current_flow_nonce_sha256,
        session_binding_sha256=flow.session_binding_sha256,
        provider=flow.provider,
        resource=flow.resource,
        account_kind=flow.account_kind,
        redirect_uri=flow.redirect_uri,
        actions_sha256=flow.actions_sha256,
        requested_scopes_sha256=flow.requested_scopes_sha256,
        flow_binding_sha256=flow.binding_sha256,
        consume_binding_sha256=consumption.consume_binding_sha256,
        pkce_challenge=flow.pkce_challenge,
        issued_at=consumption.consumed_at,
        deadline_at=deadline,
    )


def _validate_exchange_permit(
    command: OAuthExchangeCommand,
    permit: OAuthExchangePermit,
) -> None:
    if not isinstance(permit, OAuthExchangePermit) or (
        permit.permit_id != command.exchange_id
        or permit.exchange_binding_sha256 != command.binding_sha256
    ):
        raise OAuthContractError("OAUTH_EXCHANGE_PERMIT_BINDING_MISMATCH")


async def _obtain_exchange_permit(
    *,
    repository: OAuthFlowRepository,
    command: OAuthExchangeCommand,
) -> OAuthExchangePermit:
    async def read_permit() -> OAuthExchangePermit | None:
        try:
            return await repository.read_exchange_permit(command)
        except Exception:
            raise _external_failure("OAUTH_EXCHANGE_PERMIT_READ_FAILED") from None

    async def issue_permit() -> OAuthExchangePermit | None:
        try:
            return await repository.issue_exchange_permit_once(command)
        except OAuthExchangePermitResponseLost:
            return None
        except Exception:
            raise _external_failure("OAUTH_EXCHANGE_PERMIT_WRITE_FAILED") from None

    permit = await read_permit()
    if permit is None:
        permit = await issue_permit()
        if permit is None:
            permit = await read_permit()
            if permit is None:
                permit = await issue_permit()
                if permit is None:
                    permit = await read_permit()
                    if permit is None:
                        raise OAuthContractError("OAUTH_EXCHANGE_PERMIT_UNCONFIRMED") from None
    _validate_exchange_permit(command, permit)
    return permit


@dataclass(frozen=True, slots=True, repr=False)
class OAuthBrokerGrant:
    exchange_id: str
    exchange_binding_sha256: str = field(repr=False)
    consumption_id: str
    flow_id: str
    nonce_id: str
    owner_id: str
    connection_id: str
    connection_incarnation_id: str
    expected_base_revision: int
    current_flow_nonce_sha256: str = field(repr=False)
    session_binding_sha256: str = field(repr=False)
    provider: ConnectorProvider
    resource: ConnectorResource
    account_kind: ConnectorAccountKind
    redirect_uri: str
    flow_binding_sha256: str = field(repr=False)
    consume_binding_sha256: str = field(repr=False)
    actions_sha256: str = field(repr=False)
    requested_scopes_sha256: str = field(repr=False)
    credential: CredentialHandleRef = field(repr=False)
    external_account_id_hash: str = field(repr=False)
    actual_scopes: frozenset[str] = field(repr=False)
    actual_scopes_sha256: str = field(repr=False)
    issued_at: datetime
    expires_at: datetime
    verifier_erased_after_terminal: bool = True

    def __post_init__(self) -> None:
        for name in (
            "exchange_id",
            "consumption_id",
            "flow_id",
            "nonce_id",
            "owner_id",
            "connection_id",
            "connection_incarnation_id",
        ):
            object.__setattr__(self, name, _uuid(getattr(self, name), name))
        object.__setattr__(
            self,
            "expected_base_revision",
            _revision(self.expected_base_revision),
        )
        for name in (
            "exchange_binding_sha256",
            "current_flow_nonce_sha256",
            "session_binding_sha256",
            "flow_binding_sha256",
            "consume_binding_sha256",
            "actions_sha256",
            "requested_scopes_sha256",
            "external_account_id_hash",
        ):
            object.__setattr__(self, name, _sha256(getattr(self, name), name))
        if not isinstance(self.provider, ConnectorProvider):
            raise TypeError("provider must be a ConnectorProvider")
        if not isinstance(self.resource, ConnectorResource):
            raise TypeError("resource must be a ConnectorResource")
        if not isinstance(self.account_kind, ConnectorAccountKind):
            raise TypeError("account_kind must be a ConnectorAccountKind")
        object.__setattr__(self, "redirect_uri", _redirect_uri(self.redirect_uri))
        if not isinstance(self.credential, CredentialHandleRef):
            raise TypeError("credential must be opaque CredentialHandleRef")
        normalized_scopes = _scopes(self.actual_scopes)
        object.__setattr__(self, "actual_scopes", normalized_scopes)
        object.__setattr__(
            self,
            "actual_scopes_sha256",
            _sha256(self.actual_scopes_sha256, "actual_scopes_sha256"),
        )
        if self.actual_scopes_sha256 != _scope_hash(normalized_scopes):
            raise ValueError("actual_scopes_sha256 does not match the exact scope set")
        issued = _aware(self.issued_at, "issued_at")
        expires = _aware(self.expires_at, "expires_at")
        object.__setattr__(self, "issued_at", issued)
        object.__setattr__(self, "expires_at", expires)
        if expires <= issued:
            raise ValueError("broker authorization expiry must follow issuance")
        if self.verifier_erased_after_terminal is not True:
            raise ValueError("broker grant must attest post-terminal verifier erasure")

    @classmethod
    def build_for_exchange(
        cls,
        command: OAuthExchangeCommand,
        *,
        credential: CredentialHandleRef,
        external_account_id_hash: str,
        actual_scopes: frozenset[str],
        issued_at: datetime,
        expires_at: datetime,
    ) -> OAuthBrokerGrant:
        if not isinstance(command, OAuthExchangeCommand):
            raise TypeError("command must be OAuthExchangeCommand")
        normalized = _scopes(actual_scopes)
        return cls(
            exchange_id=command.exchange_id,
            exchange_binding_sha256=command.binding_sha256,
            consumption_id=command.consumption_id,
            flow_id=command.flow_id,
            nonce_id=command.nonce_id,
            owner_id=command.owner_id,
            connection_id=command.connection_id,
            connection_incarnation_id=command.connection_incarnation_id,
            expected_base_revision=command.expected_base_revision,
            current_flow_nonce_sha256=command.current_flow_nonce_sha256,
            session_binding_sha256=command.session_binding_sha256,
            provider=command.provider,
            resource=command.resource,
            account_kind=command.account_kind,
            redirect_uri=command.redirect_uri,
            flow_binding_sha256=command.flow_binding_sha256,
            consume_binding_sha256=command.consume_binding_sha256,
            actions_sha256=command.actions_sha256,
            requested_scopes_sha256=command.requested_scopes_sha256,
            credential=credential,
            external_account_id_hash=external_account_id_hash,
            actual_scopes=normalized,
            actual_scopes_sha256=_scope_hash(normalized),
            issued_at=issued_at,
            expires_at=expires_at,
            verifier_erased_after_terminal=True,
        )

    def __repr__(self) -> str:
        return (
            "OAuthBrokerGrant("
            f"exchange_id={self.exchange_id!r}, provider={self.provider.value!r}, "
            f"scope_count={len(self.actual_scopes)}, bindings='<redacted>', "
            "credential='<redacted>')"
        )


@dataclass(frozen=True, slots=True, repr=False)
class OAuthExchangeAmbiguous:
    exchange_id: str
    exchange_binding_sha256: str = field(repr=False)
    observed_at: datetime
    code: str = "response_lost_after_possible_exchange"

    def __post_init__(self) -> None:
        object.__setattr__(self, "exchange_id", _uuid(self.exchange_id, "exchange_id"))
        object.__setattr__(
            self,
            "exchange_binding_sha256",
            _sha256(self.exchange_binding_sha256, "exchange_binding_sha256"),
        )
        object.__setattr__(self, "observed_at", _aware(self.observed_at, "observed_at"))
        if self.code != "response_lost_after_possible_exchange":
            raise ValueError("ambiguous exchange code is invalid")

    def __repr__(self) -> str:
        return (
            "OAuthExchangeAmbiguous("
            f"exchange_id={self.exchange_id!r}, code={self.code!r}, binding='<redacted>')"
        )


@dataclass(frozen=True, slots=True, repr=False)
class OAuthExchangeAttemptFence:
    """Durable broker fence that forbids provider redispatch."""

    exchange_id: str
    exchange_binding_sha256: str = field(repr=False)
    recorded_at: datetime
    reason: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "exchange_id", _uuid(self.exchange_id, "exchange_id"))
        object.__setattr__(
            self,
            "exchange_binding_sha256",
            _sha256(self.exchange_binding_sha256, "exchange_binding_sha256"),
        )
        object.__setattr__(self, "recorded_at", _aware(self.recorded_at, "recorded_at"))
        if self.reason not in {"deadline_expired", "recovery_required"}:
            raise ValueError("attempt fence reason is invalid")

    def __repr__(self) -> str:
        return (
            "OAuthExchangeAttemptFence("
            f"exchange_id={self.exchange_id!r}, reason={self.reason!r}, "
            "binding='<redacted>')"
        )


OAuthExchangeTerminal = OAuthBrokerGrant | OAuthExchangeAmbiguous | OAuthExchangeAttemptFence


def _validate_exchange_terminal(
    command: OAuthExchangeCommand,
    terminal: OAuthExchangeTerminal,
) -> None:
    if terminal.exchange_id != command.exchange_id:
        raise OAuthContractError("OAUTH_EXCHANGE_TERMINAL_BINDING_MISMATCH")
    if terminal.exchange_binding_sha256 != command.binding_sha256:
        raise OAuthContractError("OAUTH_EXCHANGE_TERMINAL_BINDING_MISMATCH")
    if isinstance(terminal, OAuthExchangeAmbiguous) and terminal.observed_at < command.issued_at:
        raise OAuthContractError("OAUTH_EXCHANGE_TERMINAL_BINDING_MISMATCH")
    if isinstance(terminal, OAuthExchangeAttemptFence) and (
        (
            terminal.reason == "deadline_expired"
            and terminal.recorded_at < command.deadline_at
        )
        or (
            terminal.reason == "recovery_required"
            and terminal.recorded_at < command.issued_at
        )
    ):
        raise OAuthContractError("OAUTH_EXCHANGE_TERMINAL_BINDING_MISMATCH")
    if isinstance(terminal, OAuthBrokerGrant) and (
        terminal.consumption_id != command.consumption_id
        or terminal.flow_id != command.flow_id
        or terminal.nonce_id != command.nonce_id
        or terminal.owner_id != command.owner_id
        or terminal.connection_id != command.connection_id
        or terminal.connection_incarnation_id != command.connection_incarnation_id
        or terminal.expected_base_revision != command.expected_base_revision
        or terminal.current_flow_nonce_sha256 != command.current_flow_nonce_sha256
        or terminal.session_binding_sha256 != command.session_binding_sha256
        or terminal.provider is not command.provider
        or terminal.resource is not command.resource
        or terminal.account_kind is not command.account_kind
        or terminal.redirect_uri != command.redirect_uri
        or terminal.flow_binding_sha256 != command.flow_binding_sha256
        or terminal.consume_binding_sha256 != command.consume_binding_sha256
        or terminal.actions_sha256 != command.actions_sha256
        or terminal.requested_scopes_sha256 != command.requested_scopes_sha256
        or terminal.credential.owner_id != command.owner_id
        or terminal.credential.connection_id != command.connection_id
        or terminal.credential.provider is not command.provider
        or terminal.issued_at < command.issued_at
        or terminal.issued_at >= command.deadline_at
        or terminal.verifier_erased_after_terminal is not True
    ):
        raise OAuthContractError("OAUTH_EXCHANGE_TERMINAL_BINDING_MISMATCH")
    if isinstance(terminal, OAuthBrokerGrant) and (
        terminal.actual_scopes_sha256 != command.requested_scopes_sha256
    ):
        raise OAuthContractError("OAUTH_SCOPE_SET_MISMATCH")


async def read_oauth_exchange_terminal(
    *,
    broker: OAuthCredentialBroker,
    command: OAuthExchangeCommand,
) -> OAuthExchangeTerminal | None:
    """Recover a durable broker terminal without needing the ephemeral code."""

    try:
        existing = await broker.read_exchange(command=command)
    except Exception:
        raise _external_failure("OAUTH_EXCHANGE_READ_FAILED") from None
    if existing is None:
        return None
    if not isinstance(
        existing,
        (OAuthBrokerGrant, OAuthExchangeAmbiguous, OAuthExchangeAttemptFence),
    ):
        raise OAuthContractError("OAUTH_EXCHANGE_TERMINAL_INVALID")
    _validate_exchange_terminal(command, existing)
    if isinstance(existing, OAuthExchangeAttemptFence):
        code = (
            "OAUTH_EXCHANGE_DEADLINE_EXPIRED"
            if existing.reason == "deadline_expired"
            else "OAUTH_EXCHANGE_RECOVERY_REQUIRED"
        )
        raise OAuthContractError(code)
    return existing


async def exchange_oauth_code_once(
    *,
    broker: OAuthCredentialBroker,
    repository: OAuthFlowRepository,
    command: OAuthExchangeCommand,
    authorization_code: OAuthAuthorizationCodeSecret,
    now: datetime,
) -> OAuthExchangeTerminal:
    """Read before exchange so a process replay never blindly exchanges again."""

    reference = _aware(now, "now")
    existing = await read_oauth_exchange_terminal(broker=broker, command=command)
    if existing is not None:
        return existing
    if not isinstance(authorization_code, OAuthAuthorizationCodeSecret):
        raise TypeError("authorization_code must be OAuthAuthorizationCodeSecret")
    if reference < command.issued_at or reference >= command.deadline_at:
        raise OAuthContractError("OAUTH_EXCHANGE_DEADLINE_EXPIRED")
    # This is deliberately the final application-side operation before broker
    # dispatch.  The application can obtain the repository-issued opaque
    # capability, but cannot choose the authority that authenticates it.  The
    # broker uses only the trusted authority captured by its composition and
    # revalidates live connection authority under that authority's lock.
    permit = await _obtain_exchange_permit(repository=repository, command=command)
    try:
        terminal = await broker.exchange_once(
            command=command,
            permit=permit,
            authorization_code=authorization_code,
        )
    except OAuthExchangeResponseLost:
        terminal = await read_oauth_exchange_terminal(broker=broker, command=command)
        if terminal is None:
            raise OAuthContractError("OAUTH_EXCHANGE_RECOVERY_REQUIRED") from None
    except Exception:
        raise _external_failure("OAUTH_EXCHANGE_DISPATCH_FAILED") from None
    if not isinstance(
        terminal,
        (OAuthBrokerGrant, OAuthExchangeAmbiguous, OAuthExchangeAttemptFence),
    ):
        raise OAuthContractError("OAUTH_EXCHANGE_TERMINAL_INVALID")
    _validate_exchange_terminal(command, terminal)
    if isinstance(terminal, OAuthExchangeAttemptFence):
        code = (
            "OAUTH_EXCHANGE_DEADLINE_EXPIRED"
            if terminal.reason == "deadline_expired"
            else "OAUTH_EXCHANGE_RECOVERY_REQUIRED"
        )
        raise OAuthContractError(code)
    if isinstance(terminal, OAuthExchangeAmbiguous):
        durable = await read_oauth_exchange_terminal(broker=broker, command=command)
        if not isinstance(durable, OAuthExchangeAmbiguous):
            raise OAuthContractError("OAUTH_EXCHANGE_RECOVERY_REQUIRED") from None
        return durable
    return terminal


@dataclass(frozen=True, slots=True, repr=False)
class OAuthCompletionCommand:
    completion_id: str
    consumption_id: str
    exchange_id: str
    owner_id: str
    connection_id: str
    connection_incarnation_id: str
    expected_base_revision: int
    current_flow_nonce_sha256: str = field(repr=False)
    provider: ConnectorProvider
    resource: ConnectorResource
    account_kind: ConnectorAccountKind
    redirect_uri: str
    flow_binding_sha256: str = field(repr=False)
    exchange_binding_sha256: str = field(repr=False)
    credential: CredentialHandleRef = field(repr=False)
    external_account_id_hash: str = field(repr=False)
    granted_actions: frozenset[ConnectorActionKind] = field(repr=False)
    granted_actions_sha256: str = field(repr=False)
    granted_scopes: frozenset[str] = field(repr=False)
    granted_scopes_sha256: str = field(repr=False)
    issued_at: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        for name in (
            "completion_id",
            "consumption_id",
            "exchange_id",
            "owner_id",
            "connection_id",
            "connection_incarnation_id",
        ):
            object.__setattr__(self, name, _uuid(getattr(self, name), name))
        object.__setattr__(
            self,
            "expected_base_revision",
            _revision(self.expected_base_revision),
        )
        if not isinstance(self.provider, ConnectorProvider):
            raise TypeError("provider must be a ConnectorProvider")
        if not isinstance(self.resource, ConnectorResource):
            raise TypeError("resource must be a ConnectorResource")
        if not isinstance(self.account_kind, ConnectorAccountKind):
            raise TypeError("account_kind must be a ConnectorAccountKind")
        object.__setattr__(self, "redirect_uri", _redirect_uri(self.redirect_uri))
        for name in (
            "current_flow_nonce_sha256",
            "flow_binding_sha256",
            "exchange_binding_sha256",
            "external_account_id_hash",
            "granted_actions_sha256",
            "granted_scopes_sha256",
        ):
            object.__setattr__(self, name, _sha256(getattr(self, name), name))
        if not isinstance(self.credential, CredentialHandleRef):
            raise TypeError("credential must be an opaque CredentialHandleRef")
        normalized_actions = _actions(self.granted_actions)
        object.__setattr__(self, "granted_actions", normalized_actions)
        if self.granted_actions_sha256 != _action_hash(normalized_actions):
            raise ValueError("granted_actions_sha256 does not match the exact action set")
        normalized = _scopes(self.granted_scopes)
        object.__setattr__(self, "granted_scopes", normalized)
        if self.granted_scopes_sha256 != _scope_hash(normalized):
            raise ValueError("granted_scopes_sha256 does not match the exact scope set")
        issued = _aware(self.issued_at, "issued_at")
        expires = _aware(self.expires_at, "expires_at")
        object.__setattr__(self, "issued_at", issued)
        object.__setattr__(self, "expires_at", expires)
        if expires <= issued:
            raise ValueError("authorization expiry must follow issuance")

    @property
    def binding_sha256(self) -> str:
        return _canonical_hash(
            {
                "version": _COMPLETION_BINDING_VERSION,
                "completion_id": self.completion_id,
                "consumption_id": self.consumption_id,
                "exchange_id": self.exchange_id,
                "owner_id": self.owner_id,
                "connection_id": self.connection_id,
                "connection_incarnation_id": self.connection_incarnation_id,
                "expected_base_revision": self.expected_base_revision,
                "current_flow_nonce_sha256": self.current_flow_nonce_sha256,
                "provider": self.provider.value,
                "resource": self.resource.value,
                "account_kind": self.account_kind.value,
                "redirect_uri": self.redirect_uri,
                "flow_binding_sha256": self.flow_binding_sha256,
                "exchange_binding_sha256": self.exchange_binding_sha256,
                "credential_handle_id_sha256": _digest(self.credential.handle_id),
                "external_account_id_hash": self.external_account_id_hash,
                "granted_actions_sha256": self.granted_actions_sha256,
                "granted_scopes_sha256": self.granted_scopes_sha256,
                "issued_at": self.issued_at.isoformat(),
                "expires_at": self.expires_at.isoformat(),
            }
        )

    def __repr__(self) -> str:
        return (
            "OAuthCompletionCommand("
            f"completion_id={self.completion_id!r}, provider={self.provider.value!r}, "
            "credential='<redacted>', bindings='<redacted>')"
        )


@dataclass(frozen=True, slots=True, repr=False)
class OAuthCompletion:
    consumption_id: str
    exchange_id: str
    connection_incarnation_id: str
    expected_base_revision: int
    current_flow_nonce_sha256: str = field(repr=False)
    completion_binding_sha256: str = field(repr=False)
    credential: CredentialHandleRef = field(repr=False)
    external_account_id_hash: str = field(repr=False)
    authorization: ConnectedAuthorizationSnapshot

    def __post_init__(self) -> None:
        for name in ("consumption_id", "exchange_id", "connection_incarnation_id"):
            object.__setattr__(self, name, _uuid(getattr(self, name), name))
        object.__setattr__(
            self,
            "expected_base_revision",
            _revision(self.expected_base_revision),
        )
        object.__setattr__(
            self,
            "current_flow_nonce_sha256",
            _sha256(self.current_flow_nonce_sha256, "current_flow_nonce_sha256"),
        )
        object.__setattr__(
            self,
            "completion_binding_sha256",
            _sha256(self.completion_binding_sha256, "completion_binding_sha256"),
        )
        if not isinstance(self.credential, CredentialHandleRef):
            raise TypeError("credential must be opaque CredentialHandleRef")
        object.__setattr__(
            self,
            "external_account_id_hash",
            _sha256(self.external_account_id_hash, "external_account_id_hash"),
        )
        if not isinstance(self.authorization, ConnectedAuthorizationSnapshot):
            raise TypeError("authorization must be ConnectedAuthorizationSnapshot")
        if (
            self.credential.owner_id != self.authorization.owner_id
            or self.credential.connection_id != self.authorization.connection_id
            or self.credential.provider is not self.authorization.provider
        ):
            raise ValueError("credential must bind the exact authorization snapshot")

    def __repr__(self) -> str:
        return (
            "OAuthCompletion("
            f"consumption_id={self.consumption_id!r}, exchange_id={self.exchange_id!r}, "
            f"authorization_revision={self.authorization.revision}, "
            "credential='<redacted>', binding='<redacted>')"
        )


@dataclass(frozen=True, slots=True, repr=False)
class OAuthCompletionInactive:
    """Content-free terminal proving an exact completion is no longer live."""

    completion_id: str
    completion_binding_sha256: str = field(repr=False)
    connection_id: str
    observed_at: datetime
    reason: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "completion_id", _uuid(self.completion_id, "completion_id"))
        object.__setattr__(self, "connection_id", _uuid(self.connection_id, "connection_id"))
        object.__setattr__(
            self,
            "completion_binding_sha256",
            _sha256(self.completion_binding_sha256, "completion_binding_sha256"),
        )
        object.__setattr__(self, "observed_at", _aware(self.observed_at, "observed_at"))
        if self.reason not in {
            "revoked",
            "replaced",
            "revision_changed",
            "incarnation_changed",
            "newer_flow",
            "account_changed",
        }:
            raise ValueError("inactive completion reason is invalid")

    def __repr__(self) -> str:
        return (
            "OAuthCompletionInactive("
            f"completion_id={self.completion_id!r}, reason={self.reason!r}, "
            "binding='<redacted>')"
        )


@dataclass(frozen=True, slots=True, repr=False)
class OAuthCredentialCleanupCommand:
    """Durable revocation/cleanup outbox command for an unusable broker grant."""

    cleanup_id: str
    completion_id: str
    exchange_id: str
    owner_id: str
    connection_id: str
    connection_incarnation_id: str
    provider: ConnectorProvider
    credential: CredentialHandleRef = field(repr=False)
    exchange_binding_sha256: str = field(repr=False)
    completion_binding_sha256: str = field(repr=False)
    reason: str = "stale_connection"

    def __post_init__(self) -> None:
        for name in (
            "cleanup_id",
            "completion_id",
            "exchange_id",
            "owner_id",
            "connection_id",
            "connection_incarnation_id",
        ):
            object.__setattr__(self, name, _uuid(getattr(self, name), name))
        if not isinstance(self.provider, ConnectorProvider):
            raise TypeError("provider must be a ConnectorProvider")
        if not isinstance(self.credential, CredentialHandleRef):
            raise TypeError("credential must be an opaque CredentialHandleRef")
        if (
            self.credential.owner_id != self.owner_id
            or self.credential.connection_id != self.connection_id
            or self.credential.provider is not self.provider
        ):
            raise ValueError("cleanup credential must bind the exact connection")
        for name in ("exchange_binding_sha256", "completion_binding_sha256"):
            object.__setattr__(self, name, _sha256(getattr(self, name), name))
        if self.reason != "stale_connection":
            raise ValueError("cleanup reason is invalid")

    @property
    def binding_sha256(self) -> str:
        return _canonical_hash(
            {
                "version": _CREDENTIAL_CLEANUP_BINDING_VERSION,
                "cleanup_id": self.cleanup_id,
                "completion_id": self.completion_id,
                "exchange_id": self.exchange_id,
                "owner_id": self.owner_id,
                "connection_id": self.connection_id,
                "connection_incarnation_id": self.connection_incarnation_id,
                "provider": self.provider.value,
                "credential_handle_id_sha256": _digest(self.credential.handle_id),
                "exchange_binding_sha256": self.exchange_binding_sha256,
                "completion_binding_sha256": self.completion_binding_sha256,
                "reason": self.reason,
            }
        )

    def __repr__(self) -> str:
        return (
            "OAuthCredentialCleanupCommand("
            f"cleanup_id={self.cleanup_id!r}, provider={self.provider.value!r}, "
            "credential='<redacted>', bindings='<redacted>')"
        )


@dataclass(frozen=True, slots=True, repr=False)
class OAuthCredentialCleanupReceipt:
    cleanup_id: str
    cleanup_binding_sha256: str = field(repr=False)
    recorded_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "cleanup_id", _uuid(self.cleanup_id, "cleanup_id"))
        object.__setattr__(
            self,
            "cleanup_binding_sha256",
            _sha256(self.cleanup_binding_sha256, "cleanup_binding_sha256"),
        )
        object.__setattr__(self, "recorded_at", _aware(self.recorded_at, "recorded_at"))

    def __repr__(self) -> str:
        return (
            "OAuthCredentialCleanupReceipt("
            f"cleanup_id={self.cleanup_id!r}, binding='<redacted>')"
        )


class OAuthCompletionRepository(Protocol):
    """Atomic credential-link and authorization-snapshot writer.

    Under the exact connection lock, ``complete_once`` reads the current
    authorization revision/incarnation/current-flow nonce, refuses revoked or
    replaced connections and every drift from the expected base, and requires
    the broker account hash to equal an existing connection identity for every
    reconnect or scope expansion.  A replacement account requires a fresh
    connection ID and invalidates old grants.  It then allocates
    ``current_revision + 1`` and atomically stores the opaque credential link,
    account identity, and snapshot. The consumption/exchange ID plus full
    command binding is the idempotency key.

    Both ``read_completion`` and ``complete_once`` transactionally revalidate
    the current live connection. An exact replay returns a usable completion
    only while the same revision, incarnation, current-flow nonce, account
    identity, and ACTIVE state remain current. After revocation, replacement,
    or a newer flow they return ``OAuthCompletionInactive`` rather than an old
    credential-bearing ACTIVE snapshot. ``record_cleanup_once`` atomically
    enqueues broker credential revocation/cleanup for every provisional grant
    rejected by that live-state check; its exact replay is idempotent.
    """

    async def read_completion(
        self,
        command: OAuthCompletionCommand,
    ) -> OAuthCompletion | OAuthCompletionInactive | None: ...

    async def complete_once(
        self,
        command: OAuthCompletionCommand,
    ) -> OAuthCompletion | OAuthCompletionInactive: ...

    async def read_cleanup(
        self,
        command: OAuthCredentialCleanupCommand,
    ) -> OAuthCredentialCleanupReceipt | None: ...

    async def record_cleanup_once(
        self,
        command: OAuthCredentialCleanupCommand,
    ) -> OAuthCredentialCleanupReceipt: ...


def _completion_command(
    flow: OAuthFlowRecord,
    consumption: OAuthFlowConsumption,
    command: OAuthExchangeCommand,
    grant: OAuthBrokerGrant,
) -> OAuthCompletionCommand:
    _validate_exchange_terminal(command, grant)
    if (
        consumption.consumption_id != command.consumption_id
        or consumption.flow_id != flow.flow_id
        or consumption.connection_id != flow.connection_id
        or consumption.connection_incarnation_id != flow.connection_incarnation_id
        or consumption.expected_base_revision != flow.expected_base_revision
        or consumption.current_flow_nonce_sha256 != flow.current_flow_nonce_sha256
        or consumption.flow_binding_sha256 != flow.binding_sha256
        or consumption.consume_binding_sha256 != command.consume_binding_sha256
        or command.flow_binding_sha256 != flow.binding_sha256
        or command.connection_incarnation_id != flow.connection_incarnation_id
        or command.expected_base_revision != flow.expected_base_revision
        or command.current_flow_nonce_sha256 != flow.current_flow_nonce_sha256
        or command.redirect_uri != flow.redirect_uri
        or grant.redirect_uri != flow.redirect_uri
        or grant.credential.owner_id != flow.owner_id
        or grant.credential.connection_id != flow.connection_id
        or grant.credential.provider is not flow.provider
    ):
        raise OAuthContractError("OAUTH_COMPLETION_BINDING_MISMATCH")
    if (
        grant.actual_scopes != flow.requested_scopes
        or grant.actual_scopes_sha256 != flow.requested_scopes_sha256
        or command.requested_scopes_sha256 != flow.requested_scopes_sha256
        or command.actions_sha256 != flow.actions_sha256
    ):
        raise OAuthContractError("OAUTH_SCOPE_SET_MISMATCH")
    return OAuthCompletionCommand(
        completion_id=consumption.consumption_id,
        consumption_id=consumption.consumption_id,
        exchange_id=command.exchange_id,
        owner_id=flow.owner_id,
        connection_id=flow.connection_id,
        connection_incarnation_id=flow.connection_incarnation_id,
        expected_base_revision=flow.expected_base_revision,
        current_flow_nonce_sha256=flow.current_flow_nonce_sha256,
        provider=flow.provider,
        resource=flow.resource,
        account_kind=flow.account_kind,
        redirect_uri=flow.redirect_uri,
        flow_binding_sha256=flow.binding_sha256,
        exchange_binding_sha256=command.binding_sha256,
        credential=grant.credential,
        external_account_id_hash=grant.external_account_id_hash,
        granted_actions=flow.actions,
        granted_actions_sha256=flow.actions_sha256,
        granted_scopes=grant.actual_scopes,
        granted_scopes_sha256=grant.actual_scopes_sha256,
        issued_at=grant.issued_at,
        expires_at=grant.expires_at,
    )


def _validate_completion(
    command: OAuthCompletionCommand,
    completion: OAuthCompletion,
) -> None:
    if not isinstance(completion, OAuthCompletion):
        raise OAuthContractError("OAUTH_COMPLETION_INVALID")
    authorization = completion.authorization
    if (
        completion.consumption_id != command.consumption_id
        or completion.exchange_id != command.exchange_id
        or completion.connection_incarnation_id != command.connection_incarnation_id
        or completion.expected_base_revision != command.expected_base_revision
        or completion.current_flow_nonce_sha256 != command.current_flow_nonce_sha256
        or completion.completion_binding_sha256 != command.binding_sha256
        or completion.credential != command.credential
        or completion.external_account_id_hash != command.external_account_id_hash
        or authorization.owner_id != command.owner_id
        or authorization.connection_id != command.connection_id
        or authorization.provider is not command.provider
        or authorization.resource is not command.resource
        or authorization.account_kind is not command.account_kind
        or authorization.revision != command.expected_base_revision + 1
        or authorization.granted_actions != command.granted_actions
        or authorization.granted_actions_sha256 != command.granted_actions_sha256
        or authorization.granted_scopes != command.granted_scopes
        or authorization.granted_scopes_sha256 != command.granted_scopes_sha256
        or authorization.state is not ConnectionAuthorizationState.ACTIVE
        or authorization.issued_at != command.issued_at
        or authorization.expires_at != command.expires_at
        or authorization.revoked_at is not None
    ):
        raise OAuthContractError("OAUTH_COMPLETION_BINDING_MISMATCH")


def _validate_inactive_completion(
    command: OAuthCompletionCommand,
    inactive: OAuthCompletionInactive,
) -> None:
    if not isinstance(inactive, OAuthCompletionInactive) or (
        inactive.completion_id != command.completion_id
        or inactive.completion_binding_sha256 != command.binding_sha256
        or inactive.connection_id != command.connection_id
        or inactive.observed_at < command.issued_at
    ):
        raise OAuthContractError("OAUTH_COMPLETION_INACTIVE_BINDING_MISMATCH")


def _cleanup_command_for_completion(
    command: OAuthCompletionCommand,
) -> OAuthCredentialCleanupCommand:
    return OAuthCredentialCleanupCommand(
        cleanup_id=command.exchange_id,
        completion_id=command.completion_id,
        exchange_id=command.exchange_id,
        owner_id=command.owner_id,
        connection_id=command.connection_id,
        connection_incarnation_id=command.connection_incarnation_id,
        provider=command.provider,
        credential=command.credential,
        exchange_binding_sha256=command.exchange_binding_sha256,
        completion_binding_sha256=command.binding_sha256,
    )


def _validate_cleanup_receipt(
    command: OAuthCredentialCleanupCommand,
    receipt: OAuthCredentialCleanupReceipt,
) -> None:
    if not isinstance(receipt, OAuthCredentialCleanupReceipt) or (
        receipt.cleanup_id != command.cleanup_id
        or receipt.cleanup_binding_sha256 != command.binding_sha256
    ):
        raise OAuthContractError("OAUTH_CREDENTIAL_CLEANUP_BINDING_MISMATCH")


async def _record_credential_cleanup(
    *,
    repository: OAuthCompletionRepository,
    command: OAuthCompletionCommand,
) -> OAuthCredentialCleanupReceipt:
    cleanup = _cleanup_command_for_completion(command)

    async def read_cleanup() -> OAuthCredentialCleanupReceipt | None:
        try:
            return await repository.read_cleanup(cleanup)
        except Exception:
            raise _external_failure("OAUTH_CREDENTIAL_CLEANUP_READ_FAILED") from None

    async def record_cleanup() -> OAuthCredentialCleanupReceipt | None:
        try:
            return await repository.record_cleanup_once(cleanup)
        except OAuthCredentialCleanupResponseLost:
            return None
        except Exception:
            raise _external_failure("OAUTH_CREDENTIAL_CLEANUP_WRITE_FAILED") from None

    receipt = await read_cleanup()
    if receipt is None:
        receipt = await record_cleanup()
        if receipt is None:
            receipt = await read_cleanup()
            if receipt is None:
                receipt = await record_cleanup()
                if receipt is None:
                    receipt = await read_cleanup()
                    if receipt is None:
                        raise OAuthContractError("OAUTH_CREDENTIAL_CLEANUP_UNCONFIRMED") from None
    _validate_cleanup_receipt(cleanup, receipt)
    return receipt


async def finalize_oauth_completion(
    flow: OAuthFlowRecord,
    consumption: OAuthFlowConsumption,
    exchange_command: OAuthExchangeCommand,
    grant: OAuthBrokerGrant,
    *,
    repository: OAuthCompletionRepository,
) -> OAuthCompletion:
    """Atomically allocate revision and persist an idempotent connection completion."""

    command = _completion_command(flow, consumption, exchange_command, grant)

    async def read_completion() -> OAuthCompletion | OAuthCompletionInactive | None:
        try:
            return await repository.read_completion(command)
        except Exception:
            raise _external_failure("OAUTH_COMPLETION_READ_FAILED") from None

    async def complete_once() -> OAuthCompletion | OAuthCompletionInactive | None:
        try:
            return await repository.complete_once(command)
        except OAuthCompletionResponseLost:
            return None
        except Exception:
            raise _external_failure("OAUTH_COMPLETION_WRITE_FAILED") from None

    existing = await read_completion()
    if existing is not None:
        if isinstance(existing, OAuthCompletionInactive):
            _validate_inactive_completion(command, existing)
            await _record_credential_cleanup(repository=repository, command=command)
            raise OAuthContractError("OAUTH_COMPLETION_STALE_CONNECTION") from None
        _validate_completion(command, existing)
        return existing
    completion = await complete_once()
    if completion is None:
        completion = await read_completion()
        if completion is None:
            # A completion replay is safe because the repository owns the
            # connection lock, monotonic revision, and exact idempotency key.
            completion = await complete_once()
            if completion is None:
                completion = await read_completion()
                if completion is None:
                    raise OAuthContractError("OAUTH_COMPLETION_UNCONFIRMED") from None
    if isinstance(completion, OAuthCompletionInactive):
        _validate_inactive_completion(command, completion)
        await _record_credential_cleanup(repository=repository, command=command)
        raise OAuthContractError("OAUTH_COMPLETION_STALE_CONNECTION") from None
    _validate_completion(command, completion)
    return completion
