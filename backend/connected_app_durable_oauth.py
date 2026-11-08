"""Durable encrypted OAuth broker custody for connected apps.

The ordinary OAuth control plane intentionally stores only hashes and opaque
references.  This module is the complementary secret boundary: state and the
PKCE verifier are envelope encrypted before a flow becomes durable; a provider
refresh token is first written to provisional encrypted custody; and it is
promoted into the normal credential vault only after the control plane returns
the exact ACTIVE completion.  Provider access tokens are never promoted; a
newly issued access token may be retained only inside encrypted cleanup
quarantine when a 200 response fails semantic validation.

Every database mutation is keyed by an immutable binding and supports exact
readback after a lost PostgREST response.  A durable exchange fence is written
before the repository permit is consumed, so a process crash can only strand a
flow for operator recovery; it can never cause a second provider exchange.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Callable, Mapping, Protocol
from uuid import UUID, uuid4

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from backend.connected_app_contracts import (
    ConnectedAccountRef,
    CredentialHandleRef,
    ConnectorAccountKind,
    ConnectorResource,
)
from backend.connected_app_credential_vault import (
    ConnectedCredentialVault,
    EncryptedConnectedCredential,
)
from backend.connected_app_grant_cleanup import SupabaseConnectedGrantCleanupStore
from backend.connected_app_oauth import (
    OAuthAuthorizationCodeSecret,
    OAuthBrokerBeginResponseLost,
    OAuthBrokerFlowCommand,
    OAuthBrokerFlowLookup,
    OAuthBrokerFlowReceipt,
    OAuthBrokerGrant,
    OAuthBrokerStartRecovery,
    OAuthCompletion,
    OAuthContractError,
    OAuthCredentialBroker,
    OAuthExchangeAmbiguous,
    OAuthExchangeAttemptFence,
    OAuthExchangeCommand,
    OAuthExchangePermit,
    OAuthExchangePermitClaim,
    OAuthExchangeResponseLost,
    OAuthExchangeTerminal,
    OAuthFlowRepository,
    OAuthPkceVerifierSecret,
    OAuthStateSecret,
    _validate_exchange_permit,
    pkce_s256_challenge,
)
from backend.connected_app_policy import ConnectorActionKind, ConnectorProvider
from backend.connected_app_provider_oauth import (
    ProviderOAuthEffectUnknown,
    ProviderOAuthHTTPSClient,
    ProviderOAuthNotDispatched,
    ProviderOAuthQuarantineRequired,
    ProviderOAuthQuarantineTokenSet,
    ProviderOAuthRefreshToken,
    ProviderOAuthRejected,
    ProviderOAuthTokenBinding,
    ProviderOAuthTokenSet,
)


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_KEY_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
_B64URL = re.compile(r"^[A-Za-z0-9_-]{1,131072}$")
_MAX_SECRET_BYTES = 64 * 1024
_NONCE_BYTES = 12
_DATA_KEY_BYTES = 32
_FLOW_ENVELOPE_VERSION = "connected-oauth-flow-secret-v1"
_TERMINAL_ENVELOPE_VERSION = "connected-oauth-terminal-secret-v1"
_PROVISIONAL_ENVELOPE_VERSION = "connected-oauth-provisional-credential-v1"


def _uuid(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise ConnectedOAuthBrokerError("OAUTH_SECRET_INVALID")
    try:
        parsed = UUID(value)
    except (TypeError, ValueError, AttributeError):
        raise ConnectedOAuthBrokerError("OAUTH_SECRET_INVALID") from None
    if str(parsed) != value:
        raise ConnectedOAuthBrokerError("OAUTH_SECRET_INVALID")
    return value


def _sha(value: object, name: str = "digest") -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ConnectedOAuthBrokerError("OAUTH_SECRET_INVALID")
    return value


def _aware(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ConnectedOAuthBrokerError("OAUTH_SECRET_INVALID")
    return value.astimezone(UTC)


def _time(value: object) -> datetime:
    if not isinstance(value, str) or not value or len(value) > 64:
        raise ConnectedOAuthBrokerError("OAUTH_SECRET_INVALID")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ConnectedOAuthBrokerError("OAUTH_SECRET_INVALID") from None
    return _aware(parsed, "timestamp")


def _iso(value: datetime) -> str:
    return _aware(value, "timestamp").isoformat()


def _digest(value: str | bytes) -> str:
    if isinstance(value, str):
        value = value.encode("utf-8")
    return hashlib.sha256(value).hexdigest()


def _canonical_hash(value: Mapping[str, object]) -> str:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
    except (TypeError, ValueError, UnicodeError, RecursionError):
        raise ConnectedOAuthBrokerError("OAUTH_SECRET_INVALID") from None
    return _digest(encoded)


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _unb64(value: object, name: str, *, minimum: int, maximum: int) -> bytes:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > maximum * 2
        or not _B64URL.fullmatch(value)
    ):
        raise ConnectedOAuthBrokerError("OAUTH_SECRET_INVALID")
    try:
        decoded = base64.b64decode(
            value + "=" * (-len(value) % 4),
            altchars=b"-_",
            validate=True,
        )
    except (TypeError, ValueError):
        raise ConnectedOAuthBrokerError("OAUTH_SECRET_INVALID") from None
    if not minimum <= len(decoded) <= maximum or _b64(decoded) != value:
        raise ConnectedOAuthBrokerError("OAUTH_SECRET_INVALID")
    return decoded


def _object(value: object, keys: frozenset[str]) -> dict[str, object]:
    if type(value) is not dict or set(value) != keys:
        raise ConnectedOAuthBrokerError("OAUTH_SECRET_INVALID")
    return value


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _enum(enum_type: type[Any], value: object) -> Any:
    if not isinstance(value, str):
        raise ConnectedOAuthBrokerError("OAUTH_SECRET_INVALID")
    try:
        return enum_type(value)
    except ValueError:
        raise ConnectedOAuthBrokerError("OAUTH_SECRET_INVALID") from None


class ConnectedOAuthBrokerError(RuntimeError):
    """Content-free durable OAuth custody failure."""

    _ALLOWED = frozenset(
        {
            "OAUTH_SECRET_AMBIGUOUS",
            "OAUTH_SECRET_BINDING_MISMATCH",
            "OAUTH_SECRET_BUSY",
            "OAUTH_SECRET_CORRUPT",
            "OAUTH_SECRET_ERASED",
            "OAUTH_SECRET_EXPIRED",
            "OAUTH_SECRET_INVALID",
            "OAUTH_SECRET_KEY_UNAVAILABLE",
            "OAUTH_SECRET_NOT_FOUND",
            "OAUTH_SECRET_STORE_FAILED",
        }
    )

    def __init__(self, code: str) -> None:
        if code not in self._ALLOWED:
            raise ValueError("invalid durable OAuth broker error code")
        self.code = code
        super().__init__(code)


class ConnectedOAuthMasterKey:
    """Redacted, non-serializable AES-256 wrapping key."""

    __slots__ = ("_key", "key_id")

    def __init__(self, key_id: str, raw_key: bytes) -> None:
        if not isinstance(key_id, str) or not _KEY_ID.fullmatch(key_id):
            raise ValueError("OAuth master key ID is invalid")
        if type(raw_key) is not bytes or len(raw_key) != 32:
            raise ValueError("OAuth master key must contain exactly 32 bytes")
        object.__setattr__(self, "key_id", key_id)
        object.__setattr__(self, "_key", raw_key)

    def __setattr__(self, _name: str, _value: object) -> None:
        raise AttributeError("OAuth master key is immutable")

    @classmethod
    def from_base64url(cls, key_id: str, encoded: str) -> ConnectedOAuthMasterKey:
        return cls(key_id, _unb64(encoded, "OAuth master key", minimum=32, maximum=32))

    def __repr__(self) -> str:
        return f"ConnectedOAuthMasterKey(key_id={self.key_id!r}, key='<redacted>')"

    def __getstate__(self) -> None:
        raise TypeError("OAuth master key cannot be serialized")

    def __reduce_ex__(self, _protocol: int) -> None:
        raise TypeError("OAuth master key cannot be serialized")


@dataclass(frozen=True, slots=True, repr=False)
class EncryptedOAuthEnvelope:
    envelope_kind: str
    authority_binding_sha256: str = field(repr=False)
    key_id: str
    wrapped_key_nonce: str = field(repr=False)
    wrapped_key_ciphertext: str = field(repr=False)
    secret_nonce: str = field(repr=False)
    secret_ciphertext: str = field(repr=False)
    record_binding_sha256: str = field(repr=False)

    def __post_init__(self) -> None:
        if self.envelope_kind not in {"flow", "terminal", "provisional", "quarantine"}:
            raise ValueError("OAuth envelope kind is invalid")
        object.__setattr__(
            self,
            "authority_binding_sha256",
            _sha(self.authority_binding_sha256, "authority_binding_sha256"),
        )
        if not isinstance(self.key_id, str) or not _KEY_ID.fullmatch(self.key_id):
            raise ValueError("OAuth envelope key ID is invalid")
        _unb64(self.wrapped_key_nonce, "wrapped key nonce", minimum=12, maximum=12)
        _unb64(
            self.wrapped_key_ciphertext,
            "wrapped key ciphertext",
            minimum=48,
            maximum=48,
        )
        _unb64(self.secret_nonce, "secret nonce", minimum=12, maximum=12)
        _unb64(
            self.secret_ciphertext,
            "secret ciphertext",
            minimum=17,
            maximum=_MAX_SECRET_BYTES + 16,
        )
        object.__setattr__(
            self,
            "record_binding_sha256",
            _sha(self.record_binding_sha256, "record_binding_sha256"),
        )
        if not hmac.compare_digest(self.record_binding_sha256, self.expected_binding_sha256):
            raise ValueError("OAuth envelope record binding is invalid")

    @property
    def expected_binding_sha256(self) -> str:
        return _canonical_hash(
            {
                "version": "connected-oauth-envelope-v1",
                "envelope_kind": self.envelope_kind,
                "authority_binding_sha256": self.authority_binding_sha256,
                "key_id": self.key_id,
                "wrapped_key_nonce_sha256": _digest(
                    _unb64(
                        self.wrapped_key_nonce,
                        "wrapped key nonce",
                        minimum=12,
                        maximum=12,
                    )
                ),
                "wrapped_key_ciphertext_sha256": _digest(
                    _unb64(
                        self.wrapped_key_ciphertext,
                        "wrapped key ciphertext",
                        minimum=48,
                        maximum=48,
                    )
                ),
                "secret_nonce_sha256": _digest(
                    _unb64(self.secret_nonce, "secret nonce", minimum=12, maximum=12)
                ),
                "secret_ciphertext_sha256": _digest(
                    _unb64(
                        self.secret_ciphertext,
                        "secret ciphertext",
                        minimum=17,
                        maximum=_MAX_SECRET_BYTES + 16,
                    )
                ),
            }
        )

    def __repr__(self) -> str:
        return (
            "EncryptedOAuthEnvelope("
            f"envelope_kind={self.envelope_kind!r}, key_id={self.key_id!r}, "
            "ciphertext='<redacted>')"
        )


@dataclass(frozen=True, slots=True, repr=False)
class OAuthSecretFlowRecord:
    command: OAuthBrokerFlowCommand
    receipt: OAuthBrokerFlowReceipt
    envelope: EncryptedOAuthEnvelope
    status: str = "pending"
    exchange_id: str | None = None
    exchange_binding_sha256: str | None = field(default=None, repr=False)
    attempt_id: str | None = None
    terminal_at: datetime | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.command, OAuthBrokerFlowCommand):
            raise TypeError("command must be OAuthBrokerFlowCommand")
        if not isinstance(self.receipt, OAuthBrokerFlowReceipt):
            raise TypeError("receipt must be OAuthBrokerFlowReceipt")
        if not isinstance(self.envelope, EncryptedOAuthEnvelope):
            raise TypeError("envelope must be EncryptedOAuthEnvelope")
        if self.status not in {
            "pending",
            "attempt_fenced",
            "granted",
            "ambiguous",
            "deadline_expired",
            "erased",
        }:
            raise ValueError("OAuth secret status is invalid")
        if self.receipt.flow_id != self.command.flow_id:
            raise ValueError("OAuth secret receipt binding is invalid")
        terminal = self.status not in {"pending", "erased"}
        if terminal:
            object.__setattr__(self, "exchange_id", _uuid(self.exchange_id, "exchange_id"))
            object.__setattr__(
                self,
                "exchange_binding_sha256",
                _sha(self.exchange_binding_sha256, "exchange_binding_sha256"),
            )
            object.__setattr__(self, "attempt_id", _uuid(self.attempt_id, "attempt_id"))
            if self.terminal_at is None:
                raise ValueError("terminal OAuth secret requires terminal_at")
            object.__setattr__(self, "terminal_at", _aware(self.terminal_at, "terminal_at"))
        elif any(
            value is not None
            for value in (
                self.exchange_id,
                self.exchange_binding_sha256,
                self.attempt_id,
                self.terminal_at,
            )
        ):
            raise ValueError("pending OAuth secret cannot carry exchange state")
        expected_envelope_binding = (
            self.exchange_binding_sha256
            if self.status == "granted"
            else self.command.binding_sha256
        )
        if self.envelope.authority_binding_sha256 != expected_envelope_binding:
            raise ValueError("OAuth secret envelope binding is invalid")

    def __repr__(self) -> str:
        return (
            "OAuthSecretFlowRecord("
            f"flow_id={self.command.flow_id!r}, status={self.status!r}, "
            "secret='<redacted>')"
        )


@dataclass(frozen=True, slots=True, repr=False)
class OAuthProvisionalCredentialRecord:
    provisional_id: str
    owner_id: str
    connection_id: str
    connection_incarnation_id: str
    flow_id: str
    exchange_id: str
    provider: ConnectorProvider
    account_kind: ConnectorAccountKind
    credential_handle_sha256: str = field(repr=False)
    oauth_client_id_sha256: str = field(repr=False)
    external_account_id_hash: str = field(repr=False)
    granted_scopes: frozenset[str] = field(repr=False)
    granted_scopes_sha256: str = field(repr=False)
    exchange_binding_sha256: str = field(repr=False)
    issued_at: datetime
    expires_at: datetime
    status: str
    envelope: EncryptedOAuthEnvelope

    def __post_init__(self) -> None:
        for name in (
            "provisional_id",
            "owner_id",
            "connection_id",
            "connection_incarnation_id",
            "flow_id",
            "exchange_id",
        ):
            object.__setattr__(self, name, _uuid(getattr(self, name), name))
        if not isinstance(self.provider, ConnectorProvider):
            raise TypeError("provider must be ConnectorProvider")
        if not isinstance(self.account_kind, ConnectorAccountKind):
            raise TypeError("account_kind must be ConnectorAccountKind")
        for name in (
            "credential_handle_sha256",
            "oauth_client_id_sha256",
            "external_account_id_hash",
            "granted_scopes_sha256",
            "exchange_binding_sha256",
        ):
            object.__setattr__(self, name, _sha(getattr(self, name), name))
        if not isinstance(self.granted_scopes, frozenset) or not self.granted_scopes:
            raise ValueError("granted scopes must be nonempty")
        normalized = frozenset(self.granted_scopes)
        if any(
            not isinstance(scope, str)
            or not scope
            or len(scope) > 512
            or any(character.isspace() for character in scope)
            for scope in normalized
        ):
            raise ValueError("granted scopes are invalid")
        object.__setattr__(self, "granted_scopes", normalized)
        expected_scope_hash = _digest(
            json.dumps(sorted(normalized), separators=(",", ":")).encode("ascii")
        )
        if not hmac.compare_digest(expected_scope_hash, self.granted_scopes_sha256):
            raise ValueError("granted scope binding is invalid")
        object.__setattr__(self, "issued_at", _aware(self.issued_at, "issued_at"))
        object.__setattr__(self, "expires_at", _aware(self.expires_at, "expires_at"))
        if self.expires_at <= self.issued_at:
            raise ValueError("provisional credential expiry is invalid")
        if not isinstance(self.envelope, EncryptedOAuthEnvelope):
            raise TypeError("envelope must be EncryptedOAuthEnvelope")
        if self.status not in {"provisional", "quarantined"}:
            raise ValueError("provisional credential status is invalid")
        expected_kind = "provisional" if self.status == "provisional" else "quarantine"
        if self.envelope.envelope_kind != expected_kind:
            raise ValueError("provisional credential envelope kind is invalid")
        if self.envelope.authority_binding_sha256 != self.authority_binding_sha256:
            raise ValueError("provisional credential envelope is misbound")

    @property
    def authority_binding_sha256(self) -> str:
        return _canonical_hash(
            {
                "version": _PROVISIONAL_ENVELOPE_VERSION,
                "provisional_id": self.provisional_id,
                "owner_id": self.owner_id,
                "connection_id": self.connection_id,
                "connection_incarnation_id": self.connection_incarnation_id,
                "flow_id": self.flow_id,
                "exchange_id": self.exchange_id,
                "provider": self.provider.value,
                "account_kind": self.account_kind.value,
                "credential_handle_sha256": self.credential_handle_sha256,
                "oauth_client_id_sha256": self.oauth_client_id_sha256,
                "external_account_id_hash": self.external_account_id_hash,
                "granted_scopes_sha256": self.granted_scopes_sha256,
                "exchange_binding_sha256": self.exchange_binding_sha256,
                "issued_at": self.issued_at.isoformat(),
                "expires_at": self.expires_at.isoformat(),
            }
        )

    def __repr__(self) -> str:
        return (
            "OAuthProvisionalCredentialRecord("
            f"provisional_id={self.provisional_id!r}, provider={self.provider.value!r}, "
            "credential='<redacted>', ciphertext='<redacted>')"
        )


@dataclass(frozen=True, slots=True)
class OAuthSecretExchangeFence:
    flow_id: str
    exchange_id: str
    exchange_binding_sha256: str
    attempt_id: str
    recorded_at: datetime
    fresh: bool
    deadline_expired: bool

    def __post_init__(self) -> None:
        for name in ("flow_id", "exchange_id", "attempt_id"):
            object.__setattr__(self, name, _uuid(getattr(self, name), name))
        object.__setattr__(
            self,
            "exchange_binding_sha256",
            _sha(self.exchange_binding_sha256, "exchange_binding_sha256"),
        )
        object.__setattr__(self, "recorded_at", _aware(self.recorded_at, "recorded_at"))
        if type(self.fresh) is not bool or type(self.deadline_expired) is not bool:
            raise ValueError("OAuth exchange fence flags are invalid")


@dataclass(frozen=True, slots=True, repr=False)
class OAuthDurableGrantRecord:
    command: OAuthExchangeCommand
    credential_handle_sha256: str = field(repr=False)
    external_account_id_hash: str = field(repr=False)
    actual_scopes: frozenset[str] = field(repr=False)
    issued_at: datetime
    expires_at: datetime
    terminal_envelope: EncryptedOAuthEnvelope
    provisional: OAuthProvisionalCredentialRecord | None

    def __post_init__(self) -> None:
        if not isinstance(self.command, OAuthExchangeCommand):
            raise TypeError("command must be OAuthExchangeCommand")
        object.__setattr__(
            self,
            "credential_handle_sha256",
            _sha(self.credential_handle_sha256, "credential_handle_sha256"),
        )
        object.__setattr__(
            self,
            "external_account_id_hash",
            _sha(self.external_account_id_hash, "external_account_id_hash"),
        )
        if not isinstance(self.actual_scopes, frozenset) or not self.actual_scopes:
            raise ValueError("actual scopes must be nonempty")
        object.__setattr__(self, "issued_at", _aware(self.issued_at, "issued_at"))
        object.__setattr__(self, "expires_at", _aware(self.expires_at, "expires_at"))
        if self.expires_at <= self.issued_at:
            raise ValueError("OAuth grant expiry is invalid")
        if not isinstance(self.terminal_envelope, EncryptedOAuthEnvelope):
            raise TypeError("terminal_envelope must be EncryptedOAuthEnvelope")
        if self.terminal_envelope.authority_binding_sha256 != self.command.binding_sha256:
            raise ValueError("terminal envelope is misbound")
        if self.provisional is not None and not isinstance(
            self.provisional, OAuthProvisionalCredentialRecord
        ):
            raise TypeError("provisional must be OAuthProvisionalCredentialRecord or None")


class OAuthSecretStore(Protocol):
    async def begin_once(self, record: OAuthSecretFlowRecord) -> OAuthSecretFlowRecord: ...

    async def read_flow(self, lookup: OAuthBrokerFlowLookup) -> OAuthSecretFlowRecord | None: ...

    async def fence_exchange(
        self,
        *,
        command: OAuthExchangeCommand,
        attempt_id: str,
    ) -> OAuthSecretExchangeFence: ...

    async def put_grant_once(
        self,
        record: OAuthDurableGrantRecord,
        *,
        attempt_id: str,
    ) -> OAuthDurableGrantRecord: ...

    async def mark_ambiguous_once(
        self,
        *,
        command: OAuthExchangeCommand,
        attempt_id: str,
        observed_at: datetime,
        quarantine: OAuthProvisionalCredentialRecord | None = None,
    ) -> OAuthExchangeAmbiguous: ...

    async def read_exchange(
        self,
        command: OAuthExchangeCommand,
    ) -> OAuthDurableGrantRecord | OAuthExchangeAmbiguous | OAuthExchangeAttemptFence | None: ...

    async def read_provisional(
        self,
        *,
        credential_handle_sha256: str,
    ) -> OAuthProvisionalCredentialRecord | None: ...

    async def erase_provisional_once(
        self,
        *,
        credential_handle_sha256: str,
        expected_record_binding_sha256: str,
    ) -> bool: ...

    async def abort_flow_once(
        self,
        *,
        flow_id: str,
        flow_binding_sha256: str,
        reason: str,
    ) -> None: ...


class OAuthSecretStoreRPC(Protocol):
    async def rpc(
        self,
        function_name: str,
        payload: dict[str, Any],
        *,
        retry_transient: bool = False,
    ) -> Any: ...


async def _rpc(rpc: OAuthSecretStoreRPC, name: str, payload: dict[str, object]) -> object:
    try:
        return await rpc.rpc(name, payload, retry_transient=True)
    except ConnectedOAuthBrokerError:
        raise
    except Exception:
        raise ConnectedOAuthBrokerError("OAUTH_SECRET_STORE_FAILED") from None


def _command_parameters(command: OAuthBrokerFlowCommand) -> dict[str, object]:
    return {
        "p_flow_id": command.flow_id,
        "p_nonce_id": command.nonce_id,
        "p_owner_id": command.owner_id,
        "p_connection_id": command.connection_id,
        "p_connection_incarnation_id": command.connection_incarnation_id,
        "p_expected_base_revision": command.expected_base_revision,
        "p_current_flow_nonce_sha256": command.current_flow_nonce_sha256,
        "p_session_binding_sha256": command.session_binding_sha256,
        "p_provider": command.provider.value,
        "p_resource": command.resource.value,
        "p_account_kind": command.account_kind.value,
        "p_actions": sorted(action.value for action in command.actions),
        "p_actions_sha256": command.actions_sha256,
        "p_requested_scopes": sorted(command.requested_scopes),
        "p_requested_scopes_sha256": command.requested_scopes_sha256,
        "p_state_sha256": command.state_sha256,
        "p_pkce_challenge": command.pkce_challenge,
        "p_redirect_uri": command.redirect_uri,
        "p_created_at": _iso(command.created_at),
        "p_expires_at": _iso(command.expires_at),
        "p_flow_binding_sha256": command.binding_sha256,
    }


def _envelope_parameters(envelope: EncryptedOAuthEnvelope, *, prefix: str) -> dict[str, object]:
    return {
        f"p_{prefix}_key_id": envelope.key_id,
        f"p_{prefix}_wrapped_key_nonce": envelope.wrapped_key_nonce,
        f"p_{prefix}_wrapped_key_ciphertext": envelope.wrapped_key_ciphertext,
        f"p_{prefix}_secret_nonce": envelope.secret_nonce,
        f"p_{prefix}_secret_ciphertext": envelope.secret_ciphertext,
        f"p_{prefix}_record_binding_sha256": envelope.record_binding_sha256,
    }


_FLOW_ROW_KEYS = frozenset(
    {
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
        "status",
        "actions",
        "actions_sha256",
        "requested_scopes",
        "requested_scopes_sha256",
        "state_sha256",
        "pkce_challenge",
        "redirect_uri",
        "created_at",
        "expires_at",
        "flow_binding_sha256",
        "accepted_at",
        "status",
        "exchange_id",
        "exchange_binding_sha256",
        "attempt_id",
        "terminal_at",
        "secret_key_id",
        "secret_wrapped_key_nonce",
        "secret_wrapped_key_ciphertext",
        "secret_nonce",
        "secret_ciphertext",
        "secret_record_binding_sha256",
    }
)


def _string_array(value: object, *, maximum: int = 64) -> tuple[str, ...]:
    if (
        type(value) is not list
        or not value
        or len(value) > maximum
        or any(not isinstance(item, str) or not item or len(item) > 512 for item in value)
        or len(set(value)) != len(value)
    ):
        raise ConnectedOAuthBrokerError("OAUTH_SECRET_INVALID")
    return tuple(value)


def _flow_record(value: object) -> OAuthSecretFlowRecord:
    row = _object(value, _FLOW_ROW_KEYS)
    actions = frozenset(
        _enum(ConnectorActionKind, item) for item in _string_array(row["actions"], maximum=16)
    )
    scopes = frozenset(_string_array(row["requested_scopes"]))
    command = OAuthBrokerFlowCommand(
        flow_id=_uuid(row["flow_id"], "flow_id"),
        nonce_id=_uuid(row["nonce_id"], "nonce_id"),
        owner_id=_uuid(row["owner_id"], "owner_id"),
        connection_id=_uuid(row["connection_id"], "connection_id"),
        connection_incarnation_id=_uuid(
            row["connection_incarnation_id"], "connection_incarnation_id"
        ),
        expected_base_revision=row["expected_base_revision"],
        current_flow_nonce_sha256=_sha(row["current_flow_nonce_sha256"]),
        session_binding_sha256=_sha(row["session_binding_sha256"]),
        provider=_enum(ConnectorProvider, row["provider"]),
        resource=_enum(ConnectorResource, row["resource"]),
        account_kind=_enum(ConnectorAccountKind, row["account_kind"]),
        actions=actions,
        actions_sha256=_sha(row["actions_sha256"]),
        requested_scopes=scopes,
        requested_scopes_sha256=_sha(row["requested_scopes_sha256"]),
        state_sha256=_sha(row["state_sha256"]),
        pkce_challenge=row["pkce_challenge"],
        redirect_uri=row["redirect_uri"],
        created_at=_time(row["created_at"]),
        expires_at=_time(row["expires_at"]),
    )
    if not hmac.compare_digest(command.binding_sha256, _sha(row["flow_binding_sha256"])):
        raise ConnectedOAuthBrokerError("OAUTH_SECRET_BINDING_MISMATCH")
    receipt = OAuthBrokerFlowReceipt(
        flow_id=command.flow_id,
        connection_id=command.connection_id,
        connection_incarnation_id=command.connection_incarnation_id,
        expected_base_revision=command.expected_base_revision,
        current_flow_nonce_sha256=command.current_flow_nonce_sha256,
        flow_binding_sha256=command.binding_sha256,
        accepted_at=_time(row["accepted_at"]),
        expires_at=command.expires_at,
    )
    status = row["status"]
    if not isinstance(status, str):
        raise ConnectedOAuthBrokerError("OAUTH_SECRET_INVALID")
    envelope_kind = "terminal" if status == "granted" else "flow"
    envelope_authority = (
        _sha(row["exchange_binding_sha256"]) if status == "granted" else command.binding_sha256
    )
    envelope = EncryptedOAuthEnvelope(
        envelope_kind=envelope_kind,
        authority_binding_sha256=envelope_authority,
        key_id=row["secret_key_id"],
        wrapped_key_nonce=row["secret_wrapped_key_nonce"],
        wrapped_key_ciphertext=row["secret_wrapped_key_ciphertext"],
        secret_nonce=row["secret_nonce"],
        secret_ciphertext=row["secret_ciphertext"],
        record_binding_sha256=row["secret_record_binding_sha256"],
    )
    return OAuthSecretFlowRecord(
        command=command,
        receipt=receipt,
        envelope=envelope,
        status=status,
        exchange_id=row["exchange_id"],
        exchange_binding_sha256=row["exchange_binding_sha256"],
        attempt_id=row["attempt_id"],
        terminal_at=None if row["terminal_at"] is None else _time(row["terminal_at"]),
    )


_PROVISIONAL_KEYS = frozenset(
    {
        "provisional_id",
        "owner_id",
        "connection_id",
        "connection_incarnation_id",
        "flow_id",
        "exchange_id",
        "provider",
        "account_kind",
        "status",
        "credential_handle_sha256",
        "oauth_client_id_sha256",
        "external_account_id_hash",
        "granted_scopes",
        "granted_scopes_sha256",
        "exchange_binding_sha256",
        "issued_at",
        "expires_at",
        "key_id",
        "wrapped_key_nonce",
        "wrapped_key_ciphertext",
        "secret_nonce",
        "secret_ciphertext",
        "record_binding_sha256",
    }
)


def _provisional(value: object) -> OAuthProvisionalCredentialRecord:
    row = _object(value, _PROVISIONAL_KEYS)
    identity = {
        "provisional_id": _uuid(row["provisional_id"], "provisional_id"),
        "owner_id": _uuid(row["owner_id"], "owner_id"),
        "connection_id": _uuid(row["connection_id"], "connection_id"),
        "connection_incarnation_id": _uuid(
            row["connection_incarnation_id"], "connection_incarnation_id"
        ),
        "flow_id": _uuid(row["flow_id"], "flow_id"),
        "exchange_id": _uuid(row["exchange_id"], "exchange_id"),
        "provider": _enum(ConnectorProvider, row["provider"]),
        "account_kind": _enum(ConnectorAccountKind, row["account_kind"]),
        "credential_handle_sha256": _sha(row["credential_handle_sha256"]),
        "oauth_client_id_sha256": _sha(row["oauth_client_id_sha256"]),
        "external_account_id_hash": _sha(row["external_account_id_hash"]),
        "granted_scopes": frozenset(_string_array(row["granted_scopes"])),
        "granted_scopes_sha256": _sha(row["granted_scopes_sha256"]),
        "exchange_binding_sha256": _sha(row["exchange_binding_sha256"]),
        "issued_at": _time(row["issued_at"]),
        "expires_at": _time(row["expires_at"]),
        "status": row["status"],
    }
    partial = object.__new__(OAuthProvisionalCredentialRecord)
    for name, item in identity.items():
        object.__setattr__(partial, name, item)
    object.__setattr__(partial, "envelope", None)
    # Validate identity and derive the exact AAD before constructing envelope.
    authority_binding = OAuthProvisionalCredentialRecord.authority_binding_sha256.fget(partial)
    status = identity["status"]
    if status not in {"provisional", "quarantined"}:
        raise ConnectedOAuthBrokerError("OAUTH_SECRET_INVALID")
    envelope = EncryptedOAuthEnvelope(
        envelope_kind="provisional" if status == "provisional" else "quarantine",
        authority_binding_sha256=authority_binding,
        key_id=row["key_id"],
        wrapped_key_nonce=row["wrapped_key_nonce"],
        wrapped_key_ciphertext=row["wrapped_key_ciphertext"],
        secret_nonce=row["secret_nonce"],
        secret_ciphertext=row["secret_ciphertext"],
        record_binding_sha256=row["record_binding_sha256"],
    )
    return OAuthProvisionalCredentialRecord(**identity, envelope=envelope)


def _provisional_cleanup_record(
    provisional: OAuthProvisionalCredentialRecord,
) -> dict[str, object]:
    """Match the encrypted database row captured by the deletion trigger."""

    if not isinstance(provisional, OAuthProvisionalCredentialRecord):
        raise TypeError("provisional must be OAuthProvisionalCredentialRecord")
    envelope = provisional.envelope
    return {
        "provisional_id": provisional.provisional_id,
        "owner_id": provisional.owner_id,
        "connection_id": provisional.connection_id,
        "connection_incarnation_id": provisional.connection_incarnation_id,
        "flow_id": provisional.flow_id,
        "exchange_id": provisional.exchange_id,
        "provider": provisional.provider.value,
        "account_kind": provisional.account_kind.value,
        "status": provisional.status,
        "credential_handle_sha256": provisional.credential_handle_sha256,
        "oauth_client_id_sha256": provisional.oauth_client_id_sha256,
        "external_account_id_hash": provisional.external_account_id_hash,
        "granted_scopes": sorted(provisional.granted_scopes),
        "granted_scopes_sha256": provisional.granted_scopes_sha256,
        "exchange_binding_sha256": provisional.exchange_binding_sha256,
        "issued_at": _iso(provisional.issued_at),
        "expires_at": _iso(provisional.expires_at),
        "authority_binding_sha256": provisional.authority_binding_sha256,
        "key_id": envelope.key_id,
        "wrapped_key_nonce": envelope.wrapped_key_nonce,
        "wrapped_key_ciphertext": envelope.wrapped_key_ciphertext,
        "secret_nonce": envelope.secret_nonce,
        "secret_ciphertext": envelope.secret_ciphertext,
        "record_binding_sha256": envelope.record_binding_sha256,
    }


_GRANT_KEYS = frozenset(
    {
        "flow",
        "credential_handle_sha256",
        "external_account_id_hash",
        "actual_scopes",
        "issued_at",
        "expires_at",
        "provisional",
    }
)


class SupabaseOAuthSecretStore(OAuthSecretStore):
    """Strict PostgREST adapter for encrypted OAuth custody RPCs."""

    def __init__(self, rpc: OAuthSecretStoreRPC) -> None:
        if not callable(getattr(rpc, "rpc", None)):
            raise TypeError("OAuth secret RPC boundary is invalid")
        self._rpc = rpc

    async def begin_once(self, record: OAuthSecretFlowRecord) -> OAuthSecretFlowRecord:
        if not isinstance(record, OAuthSecretFlowRecord) or record.status != "pending":
            raise TypeError("record must be a pending OAuthSecretFlowRecord")
        payload = _command_parameters(record.command)
        payload.update(_envelope_parameters(record.envelope, prefix="secret"))
        try:
            result = await _rpc(self._rpc, "connected_app_oauth_secret_begin_v1", payload)
        except ConnectedOAuthBrokerError:
            recovered = await self.read_flow(
                OAuthBrokerFlowLookup(
                    flow_id=record.command.flow_id,
                    owner_id=record.command.owner_id,
                    connection_id=record.command.connection_id,
                    connection_incarnation_id=record.command.connection_incarnation_id,
                    expected_base_revision=record.command.expected_base_revision,
                    current_flow_nonce_sha256=record.command.current_flow_nonce_sha256,
                )
            )
            if recovered is None:
                raise ConnectedOAuthBrokerError("OAUTH_SECRET_AMBIGUOUS") from None
            result_record = recovered
        else:
            envelope = _object(result, frozenset({"status", "record"}))
            if envelope["status"] != "present" or envelope["record"] is None:
                raise ConnectedOAuthBrokerError("OAUTH_SECRET_INVALID")
            result_record = _flow_record(envelope["record"])
        if (
            result_record.command.binding_sha256 != record.command.binding_sha256
            or result_record.envelope.record_binding_sha256 != record.envelope.record_binding_sha256
        ):
            raise ConnectedOAuthBrokerError("OAUTH_SECRET_BINDING_MISMATCH")
        return result_record

    async def read_flow(self, lookup: OAuthBrokerFlowLookup) -> OAuthSecretFlowRecord | None:
        if not isinstance(lookup, OAuthBrokerFlowLookup):
            raise TypeError("lookup must be OAuthBrokerFlowLookup")
        result = await _rpc(
            self._rpc,
            "connected_app_oauth_secret_read_flow_v1",
            {
                "p_flow_id": lookup.flow_id,
                "p_owner_id": lookup.owner_id,
                "p_connection_id": lookup.connection_id,
                "p_connection_incarnation_id": lookup.connection_incarnation_id,
                "p_expected_base_revision": lookup.expected_base_revision,
                "p_current_flow_nonce_sha256": lookup.current_flow_nonce_sha256,
            },
        )
        envelope = _object(result, frozenset({"status", "record"}))
        if envelope["status"] == "absent" and envelope["record"] is None:
            return None
        if envelope["status"] == "erased" and envelope["record"] is None:
            raise ConnectedOAuthBrokerError("OAUTH_SECRET_ERASED")
        if envelope["status"] != "present" or envelope["record"] is None:
            raise ConnectedOAuthBrokerError("OAUTH_SECRET_INVALID")
        record = _flow_record(envelope["record"])
        command = record.command
        if (
            command.flow_id != lookup.flow_id
            or command.owner_id != lookup.owner_id
            or command.connection_id != lookup.connection_id
            or command.connection_incarnation_id != lookup.connection_incarnation_id
            or command.expected_base_revision != lookup.expected_base_revision
            or command.current_flow_nonce_sha256 != lookup.current_flow_nonce_sha256
        ):
            raise ConnectedOAuthBrokerError("OAUTH_SECRET_BINDING_MISMATCH")
        return record

    async def fence_exchange(
        self,
        *,
        command: OAuthExchangeCommand,
        attempt_id: str,
    ) -> OAuthSecretExchangeFence:
        if not isinstance(command, OAuthExchangeCommand):
            raise TypeError("command must be OAuthExchangeCommand")
        attempt = _uuid(attempt_id, "attempt_id")
        payload = {
            "p_flow_id": command.flow_id,
            "p_exchange_id": command.exchange_id,
            "p_exchange_binding_sha256": command.binding_sha256,
            "p_flow_binding_sha256": command.flow_binding_sha256,
            "p_attempt_id": attempt,
            "p_deadline_at": _iso(command.deadline_at),
        }
        try:
            result = await _rpc(self._rpc, "connected_app_oauth_secret_fence_v1", payload)
        except ConnectedOAuthBrokerError:
            # The attempt ID is an exact idempotency key. Repeating this
            # database-only operation recovers whether this attempt won.
            result = await _rpc(self._rpc, "connected_app_oauth_secret_fence_v1", payload)
        row = _object(
            result,
            frozenset(
                {
                    "status",
                    "flow_id",
                    "exchange_id",
                    "exchange_binding_sha256",
                    "attempt_id",
                    "recorded_at",
                    "fresh",
                }
            ),
        )
        if row["status"] not in {"claimed", "deadline_expired", "fenced"}:
            raise ConnectedOAuthBrokerError("OAUTH_SECRET_INVALID")
        fence = OAuthSecretExchangeFence(
            flow_id=row["flow_id"],
            exchange_id=row["exchange_id"],
            exchange_binding_sha256=row["exchange_binding_sha256"],
            attempt_id=row["attempt_id"],
            recorded_at=_time(row["recorded_at"]),
            fresh=row["fresh"],
            deadline_expired=row["status"] == "deadline_expired",
        )
        if (
            fence.flow_id != command.flow_id
            or fence.exchange_id != command.exchange_id
            or fence.exchange_binding_sha256 != command.binding_sha256
            or (fence.fresh and fence.attempt_id != attempt)
        ):
            raise ConnectedOAuthBrokerError("OAUTH_SECRET_BINDING_MISMATCH")
        return fence

    async def put_grant_once(
        self,
        record: OAuthDurableGrantRecord,
        *,
        attempt_id: str,
    ) -> OAuthDurableGrantRecord:
        if not isinstance(record, OAuthDurableGrantRecord):
            raise TypeError("record must be OAuthDurableGrantRecord")
        provisional = record.provisional
        if provisional is None or provisional.status != "provisional":
            raise ConnectedOAuthBrokerError("OAUTH_SECRET_INVALID")
        payload: dict[str, object] = {
            "p_flow_id": record.command.flow_id,
            "p_exchange_id": record.command.exchange_id,
            "p_exchange_binding_sha256": record.command.binding_sha256,
            "p_attempt_id": _uuid(attempt_id, "attempt_id"),
            "p_credential_handle_sha256": record.credential_handle_sha256,
            "p_external_account_id_hash": record.external_account_id_hash,
            "p_actual_scopes": sorted(record.actual_scopes),
            "p_actual_scopes_sha256": provisional.granted_scopes_sha256,
            "p_issued_at": _iso(record.issued_at),
            "p_expires_at": _iso(record.expires_at),
            "p_provisional_id": provisional.provisional_id,
            "p_oauth_client_id_sha256": provisional.oauth_client_id_sha256,
            "p_provisional_binding_sha256": provisional.authority_binding_sha256,
        }
        payload.update(_envelope_parameters(record.terminal_envelope, prefix="terminal"))
        payload.update(_envelope_parameters(provisional.envelope, prefix="provisional"))
        try:
            result = await _rpc(self._rpc, "connected_app_oauth_secret_grant_v1", payload)
        except ConnectedOAuthBrokerError:
            recovered = await self.read_exchange(record.command)
            if not isinstance(recovered, OAuthDurableGrantRecord):
                raise ConnectedOAuthBrokerError("OAUTH_SECRET_AMBIGUOUS") from None
            return recovered
        return self._grant_result(record.command, result)

    def _grant_result(
        self,
        command: OAuthExchangeCommand,
        value: object,
    ) -> OAuthDurableGrantRecord:
        envelope = _object(value, frozenset({"status", "record"}))
        if envelope["status"] != "granted" or envelope["record"] is None:
            raise ConnectedOAuthBrokerError("OAUTH_SECRET_INVALID")
        row = _object(envelope["record"], _GRANT_KEYS)
        flow = _flow_record(row["flow"])
        if (
            flow.command.flow_id != command.flow_id
            or flow.exchange_id != command.exchange_id
            or flow.exchange_binding_sha256 != command.binding_sha256
            or flow.status != "granted"
        ):
            raise ConnectedOAuthBrokerError("OAUTH_SECRET_BINDING_MISMATCH")
        provisional = None if row["provisional"] is None else _provisional(row["provisional"])
        return OAuthDurableGrantRecord(
            command=command,
            credential_handle_sha256=_sha(row["credential_handle_sha256"]),
            external_account_id_hash=_sha(row["external_account_id_hash"]),
            actual_scopes=frozenset(_string_array(row["actual_scopes"])),
            issued_at=_time(row["issued_at"]),
            expires_at=_time(row["expires_at"]),
            terminal_envelope=flow.envelope,
            provisional=provisional,
        )

    async def mark_ambiguous_once(
        self,
        *,
        command: OAuthExchangeCommand,
        attempt_id: str,
        observed_at: datetime,
        quarantine: OAuthProvisionalCredentialRecord | None = None,
    ) -> OAuthExchangeAmbiguous:
        payload: dict[str, object] = {
            "p_flow_id": command.flow_id,
            "p_exchange_id": command.exchange_id,
            "p_exchange_binding_sha256": command.binding_sha256,
            "p_attempt_id": _uuid(attempt_id, "attempt_id"),
            "p_observed_at": _iso(observed_at),
            "p_quarantine": quarantine is not None,
        }
        if quarantine is not None:
            payload.update(
                {
                    "p_provisional_id": quarantine.provisional_id,
                    "p_credential_handle_sha256": quarantine.credential_handle_sha256,
                    "p_oauth_client_id_sha256": quarantine.oauth_client_id_sha256,
                    "p_external_account_id_hash": quarantine.external_account_id_hash,
                    "p_actual_scopes": sorted(quarantine.granted_scopes),
                    "p_actual_scopes_sha256": quarantine.granted_scopes_sha256,
                    "p_issued_at": _iso(quarantine.issued_at),
                    "p_expires_at": _iso(quarantine.expires_at),
                    "p_provisional_binding_sha256": quarantine.authority_binding_sha256,
                }
            )
            payload.update(_envelope_parameters(quarantine.envelope, prefix="provisional"))
        try:
            result = await _rpc(
                self._rpc,
                "connected_app_oauth_secret_ambiguous_v1",
                payload,
            )
        except ConnectedOAuthBrokerError:
            recovered = await self.read_exchange(command)
            if isinstance(recovered, OAuthExchangeAmbiguous):
                return recovered
            # Same attempt/binding is idempotent and recovers a response that
            # was lost before the read path became observable.
            result = await _rpc(
                self._rpc,
                "connected_app_oauth_secret_ambiguous_v1",
                payload,
            )
        row = _object(
            result,
            frozenset({"status", "exchange_id", "exchange_binding_sha256", "observed_at"}),
        )
        if row["status"] != "ambiguous":
            raise ConnectedOAuthBrokerError("OAUTH_SECRET_INVALID")
        terminal = OAuthExchangeAmbiguous(
            exchange_id=row["exchange_id"],
            exchange_binding_sha256=row["exchange_binding_sha256"],
            observed_at=_time(row["observed_at"]),
        )
        if (
            terminal.exchange_id != command.exchange_id
            or terminal.exchange_binding_sha256 != command.binding_sha256
        ):
            raise ConnectedOAuthBrokerError("OAUTH_SECRET_BINDING_MISMATCH")
        return terminal

    async def read_exchange(
        self,
        command: OAuthExchangeCommand,
    ) -> OAuthDurableGrantRecord | OAuthExchangeAmbiguous | OAuthExchangeAttemptFence | None:
        if not isinstance(command, OAuthExchangeCommand):
            raise TypeError("command must be OAuthExchangeCommand")
        result = await _rpc(
            self._rpc,
            "connected_app_oauth_secret_read_exchange_v1",
            {
                "p_flow_id": command.flow_id,
                "p_exchange_id": command.exchange_id,
                "p_exchange_binding_sha256": command.binding_sha256,
            },
        )
        envelope = _object(result, frozenset({"status", "record"}))
        status = envelope["status"]
        if status == "absent" and envelope["record"] is None:
            return None
        if status == "granted":
            return self._grant_result(command, result)
        if status in {"ambiguous", "attempt_fenced", "deadline_expired"}:
            row = _object(
                envelope["record"],
                frozenset({"exchange_id", "exchange_binding_sha256", "recorded_at"}),
            )
            if status == "ambiguous":
                return OAuthExchangeAmbiguous(
                    exchange_id=row["exchange_id"],
                    exchange_binding_sha256=row["exchange_binding_sha256"],
                    observed_at=_time(row["recorded_at"]),
                )
            return OAuthExchangeAttemptFence(
                exchange_id=row["exchange_id"],
                exchange_binding_sha256=row["exchange_binding_sha256"],
                recorded_at=_time(row["recorded_at"]),
                reason=(
                    "deadline_expired" if status == "deadline_expired" else "recovery_required"
                ),
            )
        raise ConnectedOAuthBrokerError("OAUTH_SECRET_INVALID")

    async def read_provisional(
        self,
        *,
        credential_handle_sha256: str,
    ) -> OAuthProvisionalCredentialRecord | None:
        digest = _sha(credential_handle_sha256, "credential_handle_sha256")
        result = await _rpc(
            self._rpc,
            "connected_app_oauth_provisional_read_v1",
            {"p_credential_handle_sha256": digest},
        )
        envelope = _object(result, frozenset({"status", "record"}))
        if envelope["status"] == "absent" and envelope["record"] is None:
            return None
        if envelope["status"] == "erased" and envelope["record"] is None:
            return None
        if envelope["status"] not in {"provisional", "quarantined"} or envelope["record"] is None:
            raise ConnectedOAuthBrokerError("OAUTH_SECRET_INVALID")
        return _provisional(envelope["record"])

    async def erase_provisional_once(
        self,
        *,
        credential_handle_sha256: str,
        expected_record_binding_sha256: str,
    ) -> bool:
        payload = {
            "p_credential_handle_sha256": _sha(
                credential_handle_sha256, "credential_handle_sha256"
            ),
            "p_expected_record_binding_sha256": _sha(
                expected_record_binding_sha256, "expected_record_binding_sha256"
            ),
        }
        try:
            result = await _rpc(
                self._rpc,
                "connected_app_oauth_provisional_erase_v1",
                payload,
            )
        except ConnectedOAuthBrokerError:
            result = await _rpc(
                self._rpc,
                "connected_app_oauth_provisional_erase_v1",
                payload,
            )
        row = _object(result, frozenset({"status", "record_existed"}))
        if row["status"] != "erased" or type(row["record_existed"]) is not bool:
            raise ConnectedOAuthBrokerError("OAUTH_SECRET_INVALID")
        return row["record_existed"]

    async def abort_flow_once(
        self,
        *,
        flow_id: str,
        flow_binding_sha256: str,
        reason: str,
    ) -> None:
        if reason not in {"denied", "expired", "aborted", "stale"}:
            raise ConnectedOAuthBrokerError("OAUTH_SECRET_INVALID")
        payload = {
            "p_flow_id": _uuid(flow_id, "flow_id"),
            "p_flow_binding_sha256": _sha(flow_binding_sha256, "flow_binding_sha256"),
            "p_reason": reason,
        }
        try:
            result = await _rpc(self._rpc, "connected_app_oauth_secret_abort_v1", payload)
        except ConnectedOAuthBrokerError:
            result = await _rpc(self._rpc, "connected_app_oauth_secret_abort_v1", payload)
        row = _object(result, frozenset({"status"}))
        if row["status"] != "erased":
            raise ConnectedOAuthBrokerError("OAUTH_SECRET_INVALID")


class DurableOAuthCredentialBroker(OAuthCredentialBroker):
    """Concrete one-use OAuth broker with encrypted durable custody."""

    def __init__(
        self,
        *,
        keys: Mapping[str, ConnectedOAuthMasterKey],
        active_key_id: str,
        store: OAuthSecretStore,
        permit_authority: OAuthFlowRepository,
        clients: Mapping[ConnectorProvider, ProviderOAuthHTTPSClient],
        credential_vault: ConnectedCredentialVault,
        grant_cleanup_store: SupabaseConnectedGrantCleanupStore,
        now: Callable[[], datetime] | None = None,
        random_bytes: Callable[[int], bytes] = secrets.token_bytes,
    ) -> None:
        if not isinstance(keys, Mapping) or not keys:
            raise ValueError("OAuth broker requires a key ring")
        copied: dict[str, ConnectedOAuthMasterKey] = {}
        for key_id, key in keys.items():
            if not isinstance(key, ConnectedOAuthMasterKey) or key.key_id != key_id:
                raise ValueError("OAuth broker key ring is invalid")
            copied[key_id] = key
        if active_key_id not in copied:
            raise ValueError("active OAuth broker key is unavailable")
        for method in (
            "begin_once",
            "read_flow",
            "fence_exchange",
            "put_grant_once",
            "mark_ambiguous_once",
            "read_exchange",
            "read_provisional",
            "erase_provisional_once",
            "abort_flow_once",
        ):
            if not callable(getattr(store, method, None)):
                raise TypeError("OAuth secret store is invalid")
        if not callable(getattr(permit_authority, "consume_exchange_permit_for_dispatch", None)):
            raise TypeError("OAuth permit authority is invalid")
        if set(clients) != {ConnectorProvider.GOOGLE, ConnectorProvider.MICROSOFT}:
            raise ValueError("both provider OAuth clients are required")
        if not isinstance(credential_vault, ConnectedCredentialVault):
            raise TypeError("credential_vault must be ConnectedCredentialVault")
        if not isinstance(grant_cleanup_store, SupabaseConnectedGrantCleanupStore):
            raise TypeError("grant_cleanup_store must be SupabaseConnectedGrantCleanupStore")
        if not callable(random_bytes):
            raise TypeError("random_bytes must be callable")
        self._keys = copied
        self._active_key_id = active_key_id
        self._store = store
        self._permit_authority = permit_authority
        self._clients = dict(clients)
        self._credential_vault = credential_vault
        self._grant_cleanup_store = grant_cleanup_store
        self._now = now or (lambda: datetime.now(UTC))
        self._random_bytes = random_bytes

    def _seal(
        self,
        *,
        envelope_kind: str,
        authority_binding_sha256: str,
        payload: Mapping[str, object],
    ) -> EncryptedOAuthEnvelope:
        binding = _sha(authority_binding_sha256, "authority_binding_sha256")
        try:
            plaintext = json.dumps(
                payload,
                ensure_ascii=True,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("ascii")
        except (TypeError, ValueError, UnicodeError, RecursionError):
            raise ConnectedOAuthBrokerError("OAUTH_SECRET_INVALID") from None
        if not plaintext or len(plaintext) > _MAX_SECRET_BYTES:
            raise ConnectedOAuthBrokerError("OAUTH_SECRET_INVALID")
        data_key = self._random_bytes(_DATA_KEY_BYTES)
        wrap_nonce = self._random_bytes(_NONCE_BYTES)
        secret_nonce = self._random_bytes(_NONCE_BYTES)
        if (
            type(data_key) is not bytes
            or type(wrap_nonce) is not bytes
            or type(secret_nonce) is not bytes
            or len(data_key) != _DATA_KEY_BYTES
            or len(wrap_nonce) != _NONCE_BYTES
            or len(secret_nonce) != _NONCE_BYTES
        ):
            raise ConnectedOAuthBrokerError("OAUTH_SECRET_STORE_FAILED")
        key = self._keys[self._active_key_id]
        aad = f"{envelope_kind}\x00{binding}".encode("ascii")
        wrapped = AESGCM(key._key).encrypt(
            wrap_nonce,
            data_key,
            b"connected-oauth-key-v1\x00" + key.key_id.encode("ascii") + b"\x00" + aad,
        )
        ciphertext = AESGCM(data_key).encrypt(secret_nonce, plaintext, aad)
        partial = object.__new__(EncryptedOAuthEnvelope)
        object.__setattr__(partial, "envelope_kind", envelope_kind)
        object.__setattr__(partial, "authority_binding_sha256", binding)
        object.__setattr__(partial, "key_id", key.key_id)
        object.__setattr__(partial, "wrapped_key_nonce", _b64(wrap_nonce))
        object.__setattr__(partial, "wrapped_key_ciphertext", _b64(wrapped))
        object.__setattr__(partial, "secret_nonce", _b64(secret_nonce))
        object.__setattr__(partial, "secret_ciphertext", _b64(ciphertext))
        object.__setattr__(partial, "record_binding_sha256", "0" * 64)
        return EncryptedOAuthEnvelope(
            envelope_kind=envelope_kind,
            authority_binding_sha256=binding,
            key_id=key.key_id,
            wrapped_key_nonce=partial.wrapped_key_nonce,
            wrapped_key_ciphertext=partial.wrapped_key_ciphertext,
            secret_nonce=partial.secret_nonce,
            secret_ciphertext=partial.secret_ciphertext,
            record_binding_sha256=partial.expected_binding_sha256,
        )

    def _open(self, envelope: EncryptedOAuthEnvelope) -> dict[str, object]:
        if not isinstance(envelope, EncryptedOAuthEnvelope):
            raise ConnectedOAuthBrokerError("OAUTH_SECRET_CORRUPT")
        key = self._keys.get(envelope.key_id)
        if key is None:
            raise ConnectedOAuthBrokerError("OAUTH_SECRET_KEY_UNAVAILABLE")
        aad = (f"{envelope.envelope_kind}\x00{envelope.authority_binding_sha256}").encode("ascii")
        try:
            data_key = AESGCM(key._key).decrypt(
                _unb64(
                    envelope.wrapped_key_nonce,
                    "wrapped key nonce",
                    minimum=12,
                    maximum=12,
                ),
                _unb64(
                    envelope.wrapped_key_ciphertext,
                    "wrapped key ciphertext",
                    minimum=48,
                    maximum=48,
                ),
                b"connected-oauth-key-v1\x00" + key.key_id.encode("ascii") + b"\x00" + aad,
            )
            plaintext = AESGCM(data_key).decrypt(
                _unb64(envelope.secret_nonce, "secret nonce", minimum=12, maximum=12),
                _unb64(
                    envelope.secret_ciphertext,
                    "secret ciphertext",
                    minimum=17,
                    maximum=_MAX_SECRET_BYTES + 16,
                ),
                aad,
            )
            decoded = json.loads(
                plaintext.decode("ascii"),
                object_pairs_hook=_unique_object,
                parse_constant=lambda _value: (_ for _ in ()).throw(ValueError()),
            )
        except (InvalidTag, TypeError, ValueError, UnicodeError, json.JSONDecodeError):
            raise ConnectedOAuthBrokerError("OAUTH_SECRET_CORRUPT") from None
        if type(decoded) is not dict:
            raise ConnectedOAuthBrokerError("OAUTH_SECRET_CORRUPT")
        return decoded

    @staticmethod
    def _flow_payload(
        *,
        command: OAuthBrokerFlowCommand,
        state: OAuthStateSecret,
        verifier: OAuthPkceVerifierSecret,
    ) -> dict[str, object]:
        return {
            "version": _FLOW_ENVELOPE_VERSION,
            "flow_binding_sha256": command.binding_sha256,
            "state": state.value,
            "verifier": verifier.value,
        }

    def _flow_secrets(
        self,
        record: OAuthSecretFlowRecord,
    ) -> tuple[OAuthStateSecret, OAuthPkceVerifierSecret]:
        decoded = self._open(record.envelope)
        if set(decoded) != {"version", "flow_binding_sha256", "state", "verifier"} or (
            decoded["version"] != _FLOW_ENVELOPE_VERSION
            or decoded["flow_binding_sha256"] != record.command.binding_sha256
        ):
            raise ConnectedOAuthBrokerError("OAUTH_SECRET_CORRUPT")
        try:
            state = OAuthStateSecret(decoded["state"])
            verifier = OAuthPkceVerifierSecret(decoded["verifier"])
        except (TypeError, ValueError):
            raise ConnectedOAuthBrokerError("OAUTH_SECRET_CORRUPT") from None
        if (
            _digest(state.value) != record.command.state_sha256
            or pkce_s256_challenge(verifier.value) != record.command.pkce_challenge
        ):
            raise ConnectedOAuthBrokerError("OAUTH_SECRET_BINDING_MISMATCH")
        return state, verifier

    async def begin_flow(
        self,
        *,
        command: OAuthBrokerFlowCommand,
        authorization_state: OAuthStateSecret,
        verifier: OAuthPkceVerifierSecret,
    ) -> OAuthBrokerStartRecovery:
        if not isinstance(command, OAuthBrokerFlowCommand):
            raise TypeError("command must be OAuthBrokerFlowCommand")
        if not isinstance(authorization_state, OAuthStateSecret) or not isinstance(
            verifier, OAuthPkceVerifierSecret
        ):
            raise TypeError("OAuth flow secrets are invalid")
        if (
            _digest(authorization_state.value) != command.state_sha256
            or pkce_s256_challenge(verifier.value) != command.pkce_challenge
        ):
            raise OAuthContractError("OAUTH_BROKER_FLOW_BINDING_MISMATCH")
        envelope = self._seal(
            envelope_kind="flow",
            authority_binding_sha256=command.binding_sha256,
            payload=self._flow_payload(
                command=command,
                state=authorization_state,
                verifier=verifier,
            ),
        )
        provisional_receipt = OAuthBrokerFlowReceipt(
            flow_id=command.flow_id,
            connection_id=command.connection_id,
            connection_incarnation_id=command.connection_incarnation_id,
            expected_base_revision=command.expected_base_revision,
            current_flow_nonce_sha256=command.current_flow_nonce_sha256,
            flow_binding_sha256=command.binding_sha256,
            accepted_at=command.created_at,
            expires_at=command.expires_at,
        )
        try:
            stored = await self._store.begin_once(
                OAuthSecretFlowRecord(
                    command=command,
                    receipt=provisional_receipt,
                    envelope=envelope,
                )
            )
        except ConnectedOAuthBrokerError:
            raise
        except Exception:
            raise OAuthBrokerBeginResponseLost() from None
        state, stored_verifier = self._flow_secrets(stored)
        if not hmac.compare_digest(stored_verifier.value, verifier.value):
            raise OAuthContractError("OAUTH_BROKER_VERIFIER_REPLAY_MISMATCH")
        return OAuthBrokerStartRecovery(
            command=stored.command,
            receipt=stored.receipt,
            authorization_state=state,
        )

    async def read_flow(
        self,
        *,
        lookup: OAuthBrokerFlowLookup,
    ) -> OAuthBrokerStartRecovery | None:
        record = await self._store.read_flow(lookup)
        if record is None:
            return None
        if record.status != "pending":
            return None
        state, _verifier = self._flow_secrets(record)
        return OAuthBrokerStartRecovery(
            command=record.command,
            receipt=record.receipt,
            authorization_state=state,
        )

    @staticmethod
    def _require_claim(
        command: OAuthExchangeCommand,
        permit: OAuthExchangePermit,
        claim: OAuthExchangePermitClaim,
    ) -> None:
        if (
            not isinstance(claim, OAuthExchangePermitClaim)
            or claim.permit_id != permit.permit_id
            or claim.exchange_binding_sha256 != command.binding_sha256
            or claim.permit_binding_sha256 != permit.permit_binding_sha256
            or claim.consumed_at < command.issued_at
            or claim.consumed_at >= command.deadline_at
        ):
            raise OAuthContractError("OAUTH_BROKER_EXCHANGE_PERMIT_MISMATCH")

    def _grant_from_record(self, record: OAuthDurableGrantRecord) -> OAuthBrokerGrant:
        decoded = self._open(record.terminal_envelope)
        if set(decoded) != {
            "version",
            "exchange_binding_sha256",
            "credential_handle",
        } or (
            decoded["version"] != _TERMINAL_ENVELOPE_VERSION
            or decoded["exchange_binding_sha256"] != record.command.binding_sha256
            or _digest(decoded["credential_handle"]) != record.credential_handle_sha256
        ):
            raise ConnectedOAuthBrokerError("OAUTH_SECRET_CORRUPT")
        try:
            credential = CredentialHandleRef(
                owner_id=record.command.owner_id,
                connection_id=record.command.connection_id,
                provider=record.command.provider,
                handle_id=decoded["credential_handle"],
            )
        except (TypeError, ValueError):
            raise ConnectedOAuthBrokerError("OAUTH_SECRET_CORRUPT") from None
        return OAuthBrokerGrant.build_for_exchange(
            record.command,
            credential=credential,
            external_account_id_hash=record.external_account_id_hash,
            actual_scopes=record.actual_scopes,
            issued_at=record.issued_at,
            expires_at=record.expires_at,
        )

    async def read_exchange(
        self,
        *,
        command: OAuthExchangeCommand,
    ) -> OAuthExchangeTerminal | None:
        terminal = await self._store.read_exchange(command)
        if isinstance(terminal, OAuthDurableGrantRecord):
            return self._grant_from_record(terminal)
        return terminal

    async def exchange_once(
        self,
        *,
        command: OAuthExchangeCommand,
        permit: OAuthExchangePermit,
        authorization_code: OAuthAuthorizationCodeSecret,
    ) -> OAuthExchangeTerminal:
        if not isinstance(command, OAuthExchangeCommand):
            raise TypeError("command must be OAuthExchangeCommand")
        _validate_exchange_permit(command, permit)
        if not isinstance(authorization_code, OAuthAuthorizationCodeSecret):
            raise TypeError("authorization_code must be OAuthAuthorizationCodeSecret")
        existing = await self.read_exchange(command=command)
        if existing is not None:
            return existing
        lookup = OAuthBrokerFlowLookup(
            flow_id=command.flow_id,
            owner_id=command.owner_id,
            connection_id=command.connection_id,
            connection_incarnation_id=command.connection_incarnation_id,
            expected_base_revision=command.expected_base_revision,
            current_flow_nonce_sha256=command.current_flow_nonce_sha256,
        )
        flow_record = await self._store.read_flow(lookup)
        if flow_record is None or flow_record.command.binding_sha256 != command.flow_binding_sha256:
            raise OAuthContractError("OAUTH_BROKER_FLOW_BINDING_MISMATCH")
        _state, verifier = self._flow_secrets(flow_record)
        attempt_id = str(uuid4())
        fence = await self._store.fence_exchange(command=command, attempt_id=attempt_id)
        if fence.deadline_expired:
            return OAuthExchangeAttemptFence(
                exchange_id=command.exchange_id,
                exchange_binding_sha256=command.binding_sha256,
                recorded_at=fence.recorded_at,
                reason="deadline_expired",
            )
        if not fence.fresh:
            recovered = await self.read_exchange(command=command)
            if recovered is not None:
                return recovered
            return OAuthExchangeAttemptFence(
                exchange_id=command.exchange_id,
                exchange_binding_sha256=command.binding_sha256,
                recorded_at=fence.recorded_at,
                reason="recovery_required",
            )
        try:
            claim = await self._permit_authority.consume_exchange_permit_for_dispatch(
                command,
                permit,
            )
            self._require_claim(command, permit, claim)
        except Exception:
            return OAuthExchangeAttemptFence(
                exchange_id=command.exchange_id,
                exchange_binding_sha256=command.binding_sha256,
                recorded_at=fence.recorded_at,
                reason="recovery_required",
            )
        try:
            # This durable obligation exists before the provider token request.
            # If the host disappears after a provider response but before token
            # custody can be attached, it becomes an honest action-required
            # tombstone after the exchange deadline instead of false success.
            await self._grant_cleanup_store.begin(
                cleanup_id=command.exchange_id,
                owner_id=command.owner_id,
                connection_id=command.connection_id,
                exchange_id=command.exchange_id,
                provider=command.provider,
                exchange_binding_sha256=command.binding_sha256,
                deadline_at=command.deadline_at,
            )
        except Exception:
            return OAuthExchangeAttemptFence(
                exchange_id=command.exchange_id,
                exchange_binding_sha256=command.binding_sha256,
                recorded_at=fence.recorded_at,
                reason="recovery_required",
            )
        client = self._clients[command.provider]
        try:
            token_set = await client.exchange_code(
                command=flow_record.command,
                authorization_code=authorization_code,
                verifier=verifier,
            )
        except ProviderOAuthNotDispatched:
            return OAuthExchangeAttemptFence(
                exchange_id=command.exchange_id,
                exchange_binding_sha256=command.binding_sha256,
                recorded_at=fence.recorded_at,
                reason="recovery_required",
            )
        except ProviderOAuthQuarantineRequired as response:
            quarantine = self._provisional_record(
                command=command,
                flow_command=flow_record.command,
                token_set=response.token_set,
                credential_handle=str(uuid4()),
                external_account_id_hash="0" * 64,
                envelope_kind="quarantine",
            )
            try:
                await self._grant_cleanup_store.attach(
                    cleanup_id=command.exchange_id,
                    exchange_binding_sha256=command.binding_sha256,
                    source_kind="provisional",
                    source_binding_sha256=quarantine.envelope.record_binding_sha256,
                    encrypted_record=_provisional_cleanup_record(quarantine),
                )
                return await self._store.mark_ambiguous_once(
                    command=command,
                    attempt_id=attempt_id,
                    observed_at=_aware(self._now(), "now"),
                    quarantine=quarantine,
                )
            except Exception:
                # The provider may have issued authority.  The exchange fence
                # prevents redispatch and the pre-existing cleanup obligation
                # remains an honest operator-action tombstone.
                raise OAuthExchangeResponseLost() from None
        except (ProviderOAuthEffectUnknown, ProviderOAuthRejected):
            return await self._store.mark_ambiguous_once(
                command=command,
                attempt_id=attempt_id,
                observed_at=_aware(self._now(), "now"),
            )
        if (
            not isinstance(token_set, ProviderOAuthTokenSet)
            or token_set.provider is not command.provider
            or token_set.refresh_token is None
            or token_set.granted_scopes != flow_record.command.requested_scopes
        ):
            return await self._store.mark_ambiguous_once(
                command=command,
                attempt_id=attempt_id,
                observed_at=_aware(self._now(), "now"),
            )
        try:
            account = await client.identify(
                token_set.access_token,
                binding=token_set.access_token.binding,
            )
        except Exception:
            # The code exchange may have rotated/issued a refresh token. Keep
            # it encrypted and quarantined; never try the authorization code
            # again and never expose the token to the completion path.
            quarantine = self._provisional_record(
                command=command,
                flow_command=flow_record.command,
                token_set=token_set,
                credential_handle=str(uuid4()),
                external_account_id_hash="0" * 64,
                envelope_kind="quarantine",
            )
            await self._grant_cleanup_store.attach(
                cleanup_id=command.exchange_id,
                exchange_binding_sha256=command.binding_sha256,
                source_kind="provisional",
                source_binding_sha256=quarantine.envelope.record_binding_sha256,
                encrypted_record=_provisional_cleanup_record(quarantine),
            )
            return await self._store.mark_ambiguous_once(
                command=command,
                attempt_id=attempt_id,
                observed_at=_aware(self._now(), "now"),
                quarantine=quarantine,
            )
        if (
            account.provider is not command.provider
            or account.account_kind is not command.account_kind
        ):
            quarantine = self._provisional_record(
                command=command,
                flow_command=flow_record.command,
                token_set=token_set,
                credential_handle=str(uuid4()),
                external_account_id_hash="0" * 64,
                envelope_kind="quarantine",
            )
            await self._grant_cleanup_store.attach(
                cleanup_id=command.exchange_id,
                exchange_binding_sha256=command.binding_sha256,
                source_kind="provisional",
                source_binding_sha256=quarantine.envelope.record_binding_sha256,
                encrypted_record=_provisional_cleanup_record(quarantine),
            )
            return await self._store.mark_ambiguous_once(
                command=command,
                attempt_id=attempt_id,
                observed_at=_aware(self._now(), "now"),
                quarantine=quarantine,
            )
        credential_handle = str(uuid4())
        provisional = self._provisional_record(
            command=command,
            flow_command=flow_record.command,
            token_set=token_set,
            credential_handle=credential_handle,
            external_account_id_hash=account.external_account_id_hash,
            envelope_kind="provisional",
        )
        await self._grant_cleanup_store.attach(
            cleanup_id=command.exchange_id,
            exchange_binding_sha256=command.binding_sha256,
            source_kind="provisional",
            source_binding_sha256=provisional.envelope.record_binding_sha256,
            encrypted_record=_provisional_cleanup_record(provisional),
        )
        terminal_envelope = self._seal(
            envelope_kind="terminal",
            authority_binding_sha256=command.binding_sha256,
            payload={
                "version": _TERMINAL_ENVELOPE_VERSION,
                "exchange_binding_sha256": command.binding_sha256,
                "credential_handle": credential_handle,
            },
        )
        durable = OAuthDurableGrantRecord(
            command=command,
            credential_handle_sha256=_digest(credential_handle),
            external_account_id_hash=account.external_account_id_hash,
            actual_scopes=token_set.granted_scopes,
            issued_at=token_set.issued_at,
            expires_at=token_set.expires_at,
            terminal_envelope=terminal_envelope,
            provisional=provisional,
        )
        try:
            stored = await self._store.put_grant_once(durable, attempt_id=attempt_id)
        except Exception:
            # Provider exchange has occurred. Never retry it. A caller must use
            # read_exchange/operator recovery to determine the durable outcome.
            raise OAuthExchangeResponseLost() from None
        return self._grant_from_record(stored)

    def _provisional_record(
        self,
        *,
        command: OAuthExchangeCommand,
        flow_command: OAuthBrokerFlowCommand,
        token_set: ProviderOAuthTokenSet | ProviderOAuthQuarantineTokenSet,
        credential_handle: str,
        external_account_id_hash: str,
        envelope_kind: str,
    ) -> OAuthProvisionalCredentialRecord:
        if not isinstance(
            token_set, (ProviderOAuthTokenSet, ProviderOAuthQuarantineTokenSet)
        ):
            raise ConnectedOAuthBrokerError("OAUTH_SECRET_INVALID")
        if envelope_kind == "provisional" and (
            not isinstance(token_set, ProviderOAuthTokenSet)
            or token_set.refresh_token is None
        ):
            raise ConnectedOAuthBrokerError("OAUTH_SECRET_INVALID")
        access_token = token_set.access_token
        refresh_token = token_set.refresh_token
        binding = (
            token_set.binding
            if isinstance(token_set, ProviderOAuthQuarantineTokenSet)
            else access_token.binding
        )
        granted_scopes = (
            token_set.requested_scopes
            if isinstance(token_set, ProviderOAuthQuarantineTokenSet)
            else token_set.granted_scopes
        )
        provisional_id = str(uuid4())
        scopes_sha256 = _digest(
            json.dumps(sorted(granted_scopes), separators=(",", ":")).encode("ascii")
        )
        identity: dict[str, object] = {
            "provisional_id": provisional_id,
            "owner_id": command.owner_id,
            "connection_id": command.connection_id,
            "connection_incarnation_id": command.connection_incarnation_id,
            "flow_id": command.flow_id,
            "exchange_id": command.exchange_id,
            "provider": command.provider,
            "account_kind": command.account_kind,
            "credential_handle_sha256": _digest(credential_handle),
            "oauth_client_id_sha256": binding.oauth_client_id_sha256,
            "external_account_id_hash": external_account_id_hash,
            "granted_scopes": granted_scopes,
            "granted_scopes_sha256": scopes_sha256,
            "exchange_binding_sha256": command.binding_sha256,
            "issued_at": token_set.issued_at,
            "expires_at": token_set.expires_at,
            "status": ("quarantined" if envelope_kind == "quarantine" else "provisional"),
        }
        partial = object.__new__(OAuthProvisionalCredentialRecord)
        for name, value in identity.items():
            object.__setattr__(partial, name, value)
        object.__setattr__(partial, "envelope", None)
        binding = OAuthProvisionalCredentialRecord.authority_binding_sha256.fget(partial)
        secret_payload: dict[str, object] = {
            "version": _PROVISIONAL_ENVELOPE_VERSION,
            "provisional_binding_sha256": binding,
            "credential_handle": credential_handle,
            "flow_binding_sha256": flow_command.binding_sha256,
        }
        if envelope_kind == "quarantine":
            secret_payload.update(
                {
                    "access_token": (
                        None if access_token is None else access_token._reveal()
                    ),
                    "refresh_token": (
                        None if refresh_token is None else refresh_token._reveal()
                    ),
                    "revocation_token_kind": (
                        "refresh" if refresh_token is not None else "access"
                    ),
                }
            )
        else:
            assert refresh_token is not None
            secret_payload["refresh_token"] = refresh_token._reveal()
        envelope = self._seal(
            envelope_kind=envelope_kind,
            authority_binding_sha256=binding,
            payload=secret_payload,
        )
        return OAuthProvisionalCredentialRecord(**identity, envelope=envelope)

    async def activate_completion(
        self,
        completion: OAuthCompletion,
    ) -> EncryptedConnectedCredential:
        """Promote a provisional refresh token after exact ACTIVE completion.

        The final credential create is CAS/idempotent.  A crash after it commits
        but before provisional erasure is recovered by replay: vault.create
        returns the same exact record and the permanent provisional tombstone is
        then installed.  A missing/tombstoned provisional is accepted only when
        the exact final credential already exists and binds the completion.
        """

        if not isinstance(completion, OAuthCompletion):
            raise TypeError("completion must be OAuthCompletion")
        credential = completion.credential
        credential_hash = _digest(credential.handle_id)
        provisional = await self._store.read_provisional(credential_handle_sha256=credential_hash)
        account = ConnectedAccountRef(
            owner_id=completion.authorization.owner_id,
            connection_id=completion.authorization.connection_id,
            provider=completion.authorization.provider,
            resource=completion.authorization.resource,
            account_kind=completion.authorization.account_kind,
            external_account_id_hash=completion.external_account_id_hash,
        )
        if provisional is None:
            existing = await self._credential_vault._store.read(credential)
            if existing is None:
                raise ConnectedOAuthBrokerError("OAUTH_SECRET_NOT_FOUND")
            # Full binding is revalidated through open; no tombstone alone can
            # make a credential appear activated.
            await self._credential_vault.open(
                account=account,
                credential=credential,
                connection_incarnation_id=completion.connection_incarnation_id,
                authorization=completion.authorization,
            )
            await self._grant_cleanup_store.release_recover(
                cleanup_id=completion.exchange_id,
                credential_handle_sha256=credential_hash,
            )
            return existing
        if (
            provisional.status != "provisional"
            or provisional.owner_id != credential.owner_id
            or provisional.connection_id != credential.connection_id
            or provisional.connection_incarnation_id != completion.connection_incarnation_id
            or provisional.provider is not credential.provider
            or provisional.account_kind is not completion.authorization.account_kind
            or provisional.credential_handle_sha256 != credential_hash
            or provisional.external_account_id_hash != completion.external_account_id_hash
            or provisional.granted_scopes != completion.authorization.granted_scopes
            or provisional.expires_at != completion.authorization.expires_at
        ):
            raise ConnectedOAuthBrokerError("OAUTH_SECRET_BINDING_MISMATCH")
        decoded = self._open(provisional.envelope)
        if set(decoded) != {
            "version",
            "provisional_binding_sha256",
            "credential_handle",
            "refresh_token",
            "flow_binding_sha256",
        } or (
            decoded["version"] != _PROVISIONAL_ENVELOPE_VERSION
            or decoded["provisional_binding_sha256"] != provisional.authority_binding_sha256
            or decoded["credential_handle"] != credential.handle_id
        ):
            raise ConnectedOAuthBrokerError("OAUTH_SECRET_CORRUPT")
        token_binding = ProviderOAuthTokenBinding(
            provider=provisional.provider,
            oauth_client_id_sha256=provisional.oauth_client_id_sha256,
            owner_id=provisional.owner_id,
            connection_id=provisional.connection_id,
            connection_incarnation_id=provisional.connection_incarnation_id,
            account_kind=provisional.account_kind,
        )
        try:
            refresh = ProviderOAuthRefreshToken(decoded["refresh_token"], token_binding)
        except (TypeError, ValueError):
            raise ConnectedOAuthBrokerError("OAUTH_SECRET_CORRUPT") from None
        stored = await self._credential_vault.create(
            credential=credential,
            connection_incarnation_id=completion.connection_incarnation_id,
            authorization=completion.authorization,
            external_account_id_hash=completion.external_account_id_hash,
            oauth_client_id_sha256=provisional.oauth_client_id_sha256,
            refresh_token=refresh,
        )
        await self._store.erase_provisional_once(
            credential_handle_sha256=credential_hash,
            expected_record_binding_sha256=provisional.envelope.record_binding_sha256,
        )
        await self._grant_cleanup_store.release(
            cleanup_id=provisional.exchange_id,
            source_binding_sha256=provisional.envelope.record_binding_sha256,
        )
        # Re-open after erasure so success cannot be returned for a detached or
        # authority-drifted final record.
        await self._credential_vault.open(
            account=account,
            credential=credential,
            connection_incarnation_id=completion.connection_incarnation_id,
            authorization=completion.authorization,
        )
        return stored

    async def abort_flow(
        self,
        *,
        flow_id: str,
        flow_binding_sha256: str,
        reason: str,
    ) -> None:
        await self._store.abort_flow_once(
            flow_id=flow_id,
            flow_binding_sha256=flow_binding_sha256,
            reason=reason,
        )
