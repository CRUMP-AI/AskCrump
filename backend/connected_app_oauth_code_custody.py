"""Short-lived encrypted authorization-code custody for OAuth callbacks.

The provider authorization code is encrypted in the application before the
callback receipt and flow consumption are committed.  SQL receives only the
purpose-specific AES-GCM envelope and content-free bindings.  Recovery may
open that envelope only while the durable OAuth broker has no exchange fence
or terminal; the broker remains the only exactly-once provider-effect
authority.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
import hashlib
import hmac
import json
import re
import secrets
from typing import Any, Protocol
from uuid import UUID

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .connected_app_durable_oauth import ConnectedOAuthMasterKey
from .connected_app_oauth import (
    OAuthAuthorizationCodeSecret,
    OAuthConsumeCommand,
    OAuthExchangeCommand,
    OAuthFlowConsumption,
)
from .connected_app_policy import ConnectorProvider


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_KEY_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
_B64URL = re.compile(r"^[A-Za-z0-9_-]{1,8192}$")
_NONCE_BYTES = 12
_VERSION = "connected-oauth-authorization-code-custody-v1"
_RECORD_VERSION = "connected-oauth-authorization-code-envelope-v1"


class ConnectedOAuthCodeCustodyError(RuntimeError):
    """Content-free code-custody failure."""

    _ALLOWED = frozenset(
        {
            "OAUTH_CODE_CUSTODY_BINDING_MISMATCH",
            "OAUTH_CODE_CUSTODY_CORRUPT",
            "OAUTH_CODE_CUSTODY_EXPIRED",
            "OAUTH_CODE_CUSTODY_INVALID",
            "OAUTH_CODE_CUSTODY_NOT_FOUND",
            "OAUTH_CODE_CUSTODY_RETIRED",
            "OAUTH_CODE_CUSTODY_STORE_FAILED",
            "OAUTH_CODE_CUSTODY_UNAVAILABLE_AFTER_DISPATCH",
        }
    )

    def __init__(self, code: str) -> None:
        if code not in self._ALLOWED:
            code = "OAUTH_CODE_CUSTODY_INVALID"
        self.code = code
        super().__init__(code)


def _fail(code: str = "OAUTH_CODE_CUSTODY_INVALID") -> None:
    raise ConnectedOAuthCodeCustodyError(code)


def _uuid(value: object) -> str:
    if not isinstance(value, str):
        _fail()
    try:
        parsed = UUID(value)
    except (TypeError, ValueError, AttributeError):
        _fail()
    if str(parsed) != value:
        _fail()
    return value


def _sha(value: object) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        _fail()
    return value


def _aware(value: object) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        _fail()
    return value.astimezone(UTC)


def _time(value: object) -> datetime:
    if isinstance(value, datetime):
        return _aware(value)
    if not isinstance(value, str) or not value or len(value) > 64:
        _fail()
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        _fail()
    return _aware(parsed)


def _digest(value: bytes | str) -> str:
    raw = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.sha256(raw).hexdigest()


def _canonical_hash(value: dict[str, object]) -> str:
    return _digest(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _unb64(value: object, *, minimum: int, maximum: int) -> bytes:
    if not isinstance(value, str) or _B64URL.fullmatch(value) is None:
        _fail("OAUTH_CODE_CUSTODY_CORRUPT")
    try:
        decoded = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (ValueError, TypeError):
        _fail("OAUTH_CODE_CUSTODY_CORRUPT")
    if not minimum <= len(decoded) <= maximum:
        _fail("OAUTH_CODE_CUSTODY_CORRUPT")
    return decoded


@dataclass(frozen=True, slots=True, repr=False)
class OAuthAuthorizationCodeCustodyCommand:
    """Exact nonsecret authority bound into the code envelope."""

    owner_id: str
    session_binding_sha256: str = field(repr=False)
    provider: ConnectorProvider
    flow_id: str
    consumption_id: str
    exchange_id: str
    connection_id: str
    connection_incarnation_id: str
    current_flow_nonce_sha256: str = field(repr=False)
    state_sha256: str = field(repr=False)
    callback_binding_sha256: str = field(repr=False)
    flow_binding_sha256: str = field(repr=False)
    consume_binding_sha256: str = field(repr=False)
    exchange_binding_sha256: str = field(repr=False)
    pkce_challenge_sha256: str = field(repr=False)
    redirect_uri_sha256: str = field(repr=False)
    authorization_code_sha256: str = field(repr=False)
    received_at: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        for name in (
            "owner_id",
            "flow_id",
            "consumption_id",
            "exchange_id",
            "connection_id",
            "connection_incarnation_id",
        ):
            object.__setattr__(self, name, _uuid(getattr(self, name)))
        for name in (
            "session_binding_sha256",
            "current_flow_nonce_sha256",
            "state_sha256",
            "callback_binding_sha256",
            "flow_binding_sha256",
            "consume_binding_sha256",
            "exchange_binding_sha256",
            "pkce_challenge_sha256",
            "redirect_uri_sha256",
            "authorization_code_sha256",
        ):
            object.__setattr__(self, name, _sha(getattr(self, name)))
        if not isinstance(self.provider, ConnectorProvider):
            _fail()
        received = _aware(self.received_at)
        expires = _aware(self.expires_at)
        if expires <= received or expires - received > timedelta(minutes=2):
            _fail()
        object.__setattr__(self, "received_at", received)
        object.__setattr__(self, "expires_at", expires)

    @classmethod
    def build(
        cls,
        *,
        consume: OAuthConsumeCommand,
        exchange: OAuthExchangeCommand,
        callback_binding_sha256: str,
        authorization_code: OAuthAuthorizationCodeSecret,
        received_at: datetime,
    ) -> "OAuthAuthorizationCodeCustodyCommand":
        if (
            not isinstance(consume, OAuthConsumeCommand)
            or not isinstance(exchange, OAuthExchangeCommand)
            or not isinstance(authorization_code, OAuthAuthorizationCodeSecret)
            or consume.consumption_id != exchange.consumption_id
            or consume.flow_id != exchange.flow_id
            or consume.owner_id != exchange.owner_id
            or consume.connection_id != exchange.connection_id
            or consume.connection_incarnation_id != exchange.connection_incarnation_id
            or consume.provider is not exchange.provider
            or consume.flow_binding_sha256 != exchange.flow_binding_sha256
            or consume.binding_sha256 != exchange.consume_binding_sha256
        ):
            _fail("OAUTH_CODE_CUSTODY_BINDING_MISMATCH")
        return cls(
            owner_id=exchange.owner_id,
            session_binding_sha256=exchange.session_binding_sha256,
            provider=exchange.provider,
            flow_id=exchange.flow_id,
            consumption_id=exchange.consumption_id,
            exchange_id=exchange.exchange_id,
            connection_id=exchange.connection_id,
            connection_incarnation_id=exchange.connection_incarnation_id,
            current_flow_nonce_sha256=exchange.current_flow_nonce_sha256,
            state_sha256=consume.state_sha256,
            callback_binding_sha256=_sha(callback_binding_sha256),
            flow_binding_sha256=exchange.flow_binding_sha256,
            consume_binding_sha256=exchange.consume_binding_sha256,
            exchange_binding_sha256=exchange.binding_sha256,
            pkce_challenge_sha256=_digest(exchange.pkce_challenge),
            redirect_uri_sha256=_digest(exchange.redirect_uri),
            authorization_code_sha256=_digest(authorization_code.value),
            received_at=received_at,
            expires_at=exchange.deadline_at,
        )

    @classmethod
    def from_exchange(
        cls,
        *,
        exchange: OAuthExchangeCommand,
        state_sha256: str,
        callback_binding_sha256: str,
        authorization_code_sha256: str,
    ) -> "OAuthAuthorizationCodeCustodyCommand":
        """Reconstruct exact envelope authority without callback plaintext."""

        if not isinstance(exchange, OAuthExchangeCommand):
            _fail()
        return cls(
            owner_id=exchange.owner_id,
            session_binding_sha256=exchange.session_binding_sha256,
            provider=exchange.provider,
            flow_id=exchange.flow_id,
            consumption_id=exchange.consumption_id,
            exchange_id=exchange.exchange_id,
            connection_id=exchange.connection_id,
            connection_incarnation_id=exchange.connection_incarnation_id,
            current_flow_nonce_sha256=exchange.current_flow_nonce_sha256,
            state_sha256=_sha(state_sha256),
            callback_binding_sha256=_sha(callback_binding_sha256),
            flow_binding_sha256=exchange.flow_binding_sha256,
            consume_binding_sha256=exchange.consume_binding_sha256,
            exchange_binding_sha256=exchange.binding_sha256,
            pkce_challenge_sha256=_digest(exchange.pkce_challenge),
            redirect_uri_sha256=_digest(exchange.redirect_uri),
            authorization_code_sha256=_sha(authorization_code_sha256),
            received_at=exchange.issued_at,
            expires_at=exchange.deadline_at,
        )

    @property
    def authority_binding_sha256(self) -> str:
        return _canonical_hash(
            {
                "version": _VERSION,
                "owner_id": self.owner_id,
                "session_binding_sha256": self.session_binding_sha256,
                "provider": self.provider.value,
                "flow_id": self.flow_id,
                "consumption_id": self.consumption_id,
                "exchange_id": self.exchange_id,
                "connection_id": self.connection_id,
                "connection_incarnation_id": self.connection_incarnation_id,
                "current_flow_nonce_sha256": self.current_flow_nonce_sha256,
                "state_sha256": self.state_sha256,
                "callback_binding_sha256": self.callback_binding_sha256,
                "flow_binding_sha256": self.flow_binding_sha256,
                "consume_binding_sha256": self.consume_binding_sha256,
                "exchange_binding_sha256": self.exchange_binding_sha256,
                "pkce_challenge_sha256": self.pkce_challenge_sha256,
                "redirect_uri_sha256": self.redirect_uri_sha256,
                "authorization_code_sha256": self.authorization_code_sha256,
                "received_at": self.received_at.isoformat(),
                "expires_at": self.expires_at.isoformat(),
            }
        )

    def __repr__(self) -> str:
        return (
            "OAuthAuthorizationCodeCustodyCommand("
            f"flow_id={self.flow_id!r}, provider={self.provider.value!r}, "
            "bindings='<redacted>')"
        )


@dataclass(frozen=True, slots=True, repr=False)
class EncryptedOAuthAuthorizationCode:
    authority_binding_sha256: str = field(repr=False)
    key_id: str
    nonce: str = field(repr=False)
    ciphertext: str = field(repr=False)
    record_binding_sha256: str = field(repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "authority_binding_sha256", _sha(self.authority_binding_sha256))
        if not isinstance(self.key_id, str) or _KEY_ID.fullmatch(self.key_id) is None:
            _fail()
        _unb64(self.nonce, minimum=12, maximum=12)
        _unb64(self.ciphertext, minimum=17, maximum=8192)
        object.__setattr__(self, "record_binding_sha256", _sha(self.record_binding_sha256))
        if not hmac.compare_digest(
            self.record_binding_sha256,
            _canonical_hash(
                {
                    "version": _RECORD_VERSION,
                    "authority_binding_sha256": self.authority_binding_sha256,
                    "key_id": self.key_id,
                    "nonce_sha256": _digest(_unb64(self.nonce, minimum=12, maximum=12)),
                    "ciphertext_sha256": _digest(
                        _unb64(self.ciphertext, minimum=17, maximum=8192)
                    ),
                }
            ),
        ):
            _fail("OAUTH_CODE_CUSTODY_BINDING_MISMATCH")

    def __repr__(self) -> str:
        return (
            "EncryptedOAuthAuthorizationCode("
            f"key_id={self.key_id!r}, ciphertext='<redacted>')"
        )


@dataclass(frozen=True, slots=True, repr=False)
class OAuthAuthorizationCodeCustodyRecord:
    command: OAuthAuthorizationCodeCustodyCommand
    envelope: EncryptedOAuthAuthorizationCode | None = field(repr=False)
    status: str
    claimed_at: datetime | None
    retired_at: datetime | None

    def __post_init__(self) -> None:
        if not isinstance(self.command, OAuthAuthorizationCodeCustodyCommand):
            _fail()
        if self.status not in {"available", "retired"}:
            _fail()
        if self.claimed_at is not None:
            object.__setattr__(self, "claimed_at", _aware(self.claimed_at))
        if self.retired_at is not None:
            object.__setattr__(self, "retired_at", _aware(self.retired_at))
        if self.status == "available":
            if not isinstance(self.envelope, EncryptedOAuthAuthorizationCode) or self.retired_at is not None:
                _fail()
        elif self.envelope is not None or self.retired_at is None:
            _fail()

    def __repr__(self) -> str:
        return (
            "OAuthAuthorizationCodeCustodyRecord("
            f"flow_id={self.command.flow_id!r}, status={self.status!r}, "
            "ciphertext='<redacted>')"
        )


class OAuthAuthorizationCodeCustodyRPC(Protocol):
    async def rpc(
        self,
        function_name: str,
        payload: dict[str, Any],
        *,
        retry_transient: bool = False,
    ) -> Any: ...


class SupabaseOAuthAuthorizationCodeCustodyStore:
    """Strict RPC adapter; it never accepts or returns plaintext code values."""

    __slots__ = ("_rpc",)

    def __init__(self, rpc: OAuthAuthorizationCodeCustodyRPC) -> None:
        if not callable(getattr(rpc, "rpc", None)):
            raise TypeError("code custody RPC is invalid")
        self._rpc = rpc

    @staticmethod
    def _row(value: object) -> dict[str, object]:
        if not isinstance(value, dict):
            _fail("OAUTH_CODE_CUSTODY_STORE_FAILED")
        return value

    @staticmethod
    def _payload(command: OAuthAuthorizationCodeCustodyCommand) -> dict[str, object]:
        return {
            "p_owner_id": command.owner_id,
            "p_session_binding_sha256": command.session_binding_sha256,
            "p_provider": command.provider.value,
            "p_flow_id": command.flow_id,
            "p_consumption_id": command.consumption_id,
            "p_exchange_id": command.exchange_id,
            "p_connection_id": command.connection_id,
            "p_connection_incarnation_id": command.connection_incarnation_id,
            "p_current_flow_nonce_sha256": command.current_flow_nonce_sha256,
            "p_state_sha256": command.state_sha256,
            "p_callback_binding_sha256": command.callback_binding_sha256,
            "p_flow_binding_sha256": command.flow_binding_sha256,
            "p_consume_binding_sha256": command.consume_binding_sha256,
            "p_exchange_binding_sha256": command.exchange_binding_sha256,
            "p_pkce_challenge_sha256": command.pkce_challenge_sha256,
            "p_redirect_uri_sha256": command.redirect_uri_sha256,
            "p_authorization_code_sha256": command.authorization_code_sha256,
            "p_code_authority_binding_sha256": command.authority_binding_sha256,
            "p_received_at": command.received_at.isoformat(),
            "p_code_expires_at": command.expires_at.isoformat(),
        }

    async def accept_once(
        self,
        *,
        command: OAuthAuthorizationCodeCustodyCommand,
        consume: OAuthConsumeCommand,
        envelope: EncryptedOAuthAuthorizationCode,
    ) -> OAuthFlowConsumption:
        if (
            not isinstance(command, OAuthAuthorizationCodeCustodyCommand)
            or not isinstance(consume, OAuthConsumeCommand)
            or not isinstance(envelope, EncryptedOAuthAuthorizationCode)
            or envelope.authority_binding_sha256 != command.authority_binding_sha256
        ):
            _fail("OAUTH_CODE_CUSTODY_BINDING_MISMATCH")
        payload = self._payload(command)
        payload.update(
            {
                "p_expected_base_revision": consume.expected_base_revision,
                "p_code_key_id": envelope.key_id,
                "p_code_nonce": envelope.nonce,
                "p_code_ciphertext": envelope.ciphertext,
                "p_code_record_binding_sha256": envelope.record_binding_sha256,
            }
        )
        try:
            value = await self._rpc.rpc(
                "connected_app_operator_accept_oauth_callback_v2",
                payload,
                retry_transient=False,
            )
            row = self._row(value)
            if set(row) != {
                "consumption_id",
                "flow_id",
                "connection_id",
                "connection_incarnation_id",
                "expected_base_revision",
                "current_flow_nonce_sha256",
                "consume_binding_sha256",
                "flow_binding_sha256",
                "consumed_at",
            }:
                _fail("OAUTH_CODE_CUSTODY_STORE_FAILED")
            result = OAuthFlowConsumption(
                consumption_id=_uuid(row["consumption_id"]),
                flow_id=_uuid(row["flow_id"]),
                connection_id=_uuid(row["connection_id"]),
                connection_incarnation_id=_uuid(row["connection_incarnation_id"]),
                expected_base_revision=int(row["expected_base_revision"]),
                current_flow_nonce_sha256=_sha(row["current_flow_nonce_sha256"]),
                consume_binding_sha256=_sha(row["consume_binding_sha256"]),
                flow_binding_sha256=_sha(row["flow_binding_sha256"]),
                consumed_at=_time(row["consumed_at"]),
            )
        except ConnectedOAuthCodeCustodyError:
            raise
        except Exception:
            # Never repeat the mutation after an ambiguous response.  Exact
            # readback determines whether callback consumption committed.
            record = await self.read(command)
            if record is None:
                _fail("OAUTH_CODE_CUSTODY_STORE_FAILED")
            result = OAuthFlowConsumption.build_for_command(
                consume,
                consumed_at=command.received_at,
            )
        if (
            result.consumption_id != consume.consumption_id
            or result.flow_id != consume.flow_id
            or result.connection_id != consume.connection_id
            or result.connection_incarnation_id != consume.connection_incarnation_id
            or result.expected_base_revision != consume.expected_base_revision
            or result.current_flow_nonce_sha256 != consume.current_flow_nonce_sha256
            or result.consume_binding_sha256 != consume.binding_sha256
            or result.flow_binding_sha256 != consume.flow_binding_sha256
            or result.consumed_at != command.received_at
        ):
            _fail("OAUTH_CODE_CUSTODY_BINDING_MISMATCH")
        return result

    async def read(
        self,
        command: OAuthAuthorizationCodeCustodyCommand,
    ) -> OAuthAuthorizationCodeCustodyRecord | None:
        if not isinstance(command, OAuthAuthorizationCodeCustodyCommand):
            _fail()
        try:
            value = await self._rpc.rpc(
                "connected_app_oauth_code_read_v1",
                self._payload(command),
                retry_transient=False,
            )
        except Exception:
            _fail("OAUTH_CODE_CUSTODY_STORE_FAILED")
        if value is None:
            return None
        return self._decode(command, value)

    @staticmethod
    def _exchange_payload(
        exchange: OAuthExchangeCommand,
        *,
        state_sha256: str,
    ) -> dict[str, object]:
        if not isinstance(exchange, OAuthExchangeCommand):
            _fail()
        return {
            "p_owner_id": exchange.owner_id,
            "p_session_binding_sha256": exchange.session_binding_sha256,
            "p_provider": exchange.provider.value,
            "p_flow_id": exchange.flow_id,
            "p_consumption_id": exchange.consumption_id,
            "p_exchange_id": exchange.exchange_id,
            "p_exchange_binding_sha256": exchange.binding_sha256,
            "p_state_sha256": _sha(state_sha256),
        }

    async def claim_for_exchange(
        self,
        exchange: OAuthExchangeCommand,
        *,
        state_sha256: str,
    ) -> OAuthAuthorizationCodeCustodyRecord:
        """Recover an envelope after process loss without knowing its code hash."""

        payload = self._exchange_payload(exchange, state_sha256=state_sha256)
        try:
            value = await self._rpc.rpc(
                "connected_app_oauth_code_claim_v1",
                payload,
                retry_transient=False,
            )
        except Exception:
            _fail("OAUTH_CODE_CUSTODY_UNAVAILABLE_AFTER_DISPATCH")
        row = self._row(value)
        if set(row) != {
            "status",
            "callback_binding_sha256",
            "authorization_code_sha256",
            "code_authority_binding_sha256",
            "code_key_id",
            "code_nonce",
            "code_ciphertext",
            "code_record_binding_sha256",
            "claimed_at",
            "retired_at",
        }:
            _fail("OAUTH_CODE_CUSTODY_STORE_FAILED")
        command = OAuthAuthorizationCodeCustodyCommand.from_exchange(
            exchange=exchange,
            state_sha256=state_sha256,
            callback_binding_sha256=row["callback_binding_sha256"],
            authorization_code_sha256=row["authorization_code_sha256"],
        )
        record = self._decode(command, row, allow_lookup_fields=True)
        if record.status != "available" or record.claimed_at is None:
            _fail("OAUTH_CODE_CUSTODY_UNAVAILABLE_AFTER_DISPATCH")
        return record

    async def retire(
        self,
        command: OAuthAuthorizationCodeCustodyCommand,
        *,
        reason: str,
    ) -> None:
        if reason not in {"terminal", "ambiguous", "deadline", "safe_restart"}:
            _fail()
        payload = self._payload(command)
        payload["p_reason"] = reason
        try:
            value = await self._rpc.rpc(
                "connected_app_oauth_code_retire_v1",
                payload,
                retry_transient=False,
            )
            row = self._row(value)
            if set(row) != {"retired", "retired_at"} or row["retired"] is not True:
                _fail("OAUTH_CODE_CUSTODY_STORE_FAILED")
            _time(row["retired_at"])
        except ConnectedOAuthCodeCustodyError:
            raise
        except Exception:
            record = await self.read(command)
            if record is None or record.status != "retired":
                _fail("OAUTH_CODE_CUSTODY_STORE_FAILED")

    async def retire_for_exchange(
        self,
        exchange: OAuthExchangeCommand,
        *,
        state_sha256: str,
        reason: str,
    ) -> None:
        if reason not in {"terminal", "ambiguous", "deadline", "safe_restart"}:
            _fail()
        payload = self._exchange_payload(exchange, state_sha256=state_sha256)
        payload["p_reason"] = reason
        try:
            value = await self._rpc.rpc(
                "connected_app_oauth_code_retire_v1",
                payload,
                retry_transient=False,
            )
            row = self._row(value)
            if set(row) != {"retired", "retired_at"} or row["retired"] is not True:
                _fail("OAUTH_CODE_CUSTODY_STORE_FAILED")
            _time(row["retired_at"])
        except ConnectedOAuthCodeCustodyError:
            raise
        except Exception:
            _fail("OAUTH_CODE_CUSTODY_STORE_FAILED")

    @staticmethod
    def _decode(
        command: OAuthAuthorizationCodeCustodyCommand,
        value: object,
        *,
        allow_lookup_fields: bool = False,
    ) -> OAuthAuthorizationCodeCustodyRecord:
        row = SupabaseOAuthAuthorizationCodeCustodyStore._row(value)
        expected = {
            "status",
            "code_authority_binding_sha256",
            "code_key_id",
            "code_nonce",
            "code_ciphertext",
            "code_record_binding_sha256",
            "claimed_at",
            "retired_at",
        }
        if allow_lookup_fields:
            expected |= {
                "callback_binding_sha256",
                "authorization_code_sha256",
            }
        if set(row) != expected or row["code_authority_binding_sha256"] != command.authority_binding_sha256:
            _fail("OAUTH_CODE_CUSTODY_BINDING_MISMATCH")
        if allow_lookup_fields and (
            row["callback_binding_sha256"] != command.callback_binding_sha256
            or row["authorization_code_sha256"]
            != command.authorization_code_sha256
        ):
            _fail("OAUTH_CODE_CUSTODY_BINDING_MISMATCH")
        status = row["status"]
        envelope: EncryptedOAuthAuthorizationCode | None = None
        if status == "available":
            envelope = EncryptedOAuthAuthorizationCode(
                authority_binding_sha256=_sha(row["code_authority_binding_sha256"]),
                key_id=row["code_key_id"],
                nonce=row["code_nonce"],
                ciphertext=row["code_ciphertext"],
                record_binding_sha256=row["code_record_binding_sha256"],
            )
        elif status != "retired" or any(
            row[key] is not None
            for key in ("code_key_id", "code_nonce", "code_ciphertext", "code_record_binding_sha256")
        ):
            _fail("OAUTH_CODE_CUSTODY_CORRUPT")
        return OAuthAuthorizationCodeCustodyRecord(
            command=command,
            envelope=envelope,
            status=status,
            claimed_at=(None if row["claimed_at"] is None else _time(row["claimed_at"])),
            retired_at=(None if row["retired_at"] is None else _time(row["retired_at"])),
        )


class ConnectedOAuthAuthorizationCodeVault:
    """Purpose-separated AES-GCM authority for the short-lived code packet."""

    __slots__ = ("_key", "_store")

    def __init__(
        self,
        *,
        key: ConnectedOAuthMasterKey,
        store: SupabaseOAuthAuthorizationCodeCustodyStore,
    ) -> None:
        if (
            not isinstance(key, ConnectedOAuthMasterKey)
            or not isinstance(store, SupabaseOAuthAuthorizationCodeCustodyStore)
        ):
            raise TypeError("authorization-code vault composition is invalid")
        self._key = key
        self._store = store

    def _seal(
        self,
        command: OAuthAuthorizationCodeCustodyCommand,
        code: OAuthAuthorizationCodeSecret,
    ) -> EncryptedOAuthAuthorizationCode:
        if not isinstance(command, OAuthAuthorizationCodeCustodyCommand) or not isinstance(
            code, OAuthAuthorizationCodeSecret
        ):
            _fail()
        if not hmac.compare_digest(command.authorization_code_sha256, _digest(code.value)):
            _fail("OAUTH_CODE_CUSTODY_BINDING_MISMATCH")
        nonce = secrets.token_bytes(_NONCE_BYTES)
        aad = command.authority_binding_sha256.encode("ascii")
        ciphertext = AESGCM(self._key._key).encrypt(
            nonce,
            code.value.encode("utf-8"),
            aad,
        )
        partial = {
            "version": _RECORD_VERSION,
            "authority_binding_sha256": command.authority_binding_sha256,
            "key_id": self._key.key_id,
            "nonce_sha256": _digest(nonce),
            "ciphertext_sha256": _digest(ciphertext),
        }
        return EncryptedOAuthAuthorizationCode(
            authority_binding_sha256=command.authority_binding_sha256,
            key_id=self._key.key_id,
            nonce=_b64(nonce),
            ciphertext=_b64(ciphertext),
            record_binding_sha256=_canonical_hash(partial),
        )

    def _open(
        self,
        record: OAuthAuthorizationCodeCustodyRecord,
        *,
        now: datetime,
    ) -> OAuthAuthorizationCodeSecret:
        if not isinstance(record, OAuthAuthorizationCodeCustodyRecord):
            _fail()
        reference = _aware(now)
        if reference < record.command.received_at or reference >= record.command.expires_at:
            _fail("OAUTH_CODE_CUSTODY_EXPIRED")
        envelope = record.envelope
        if record.status != "available" or envelope is None:
            _fail("OAUTH_CODE_CUSTODY_RETIRED")
        if envelope.key_id != self._key.key_id:
            _fail("OAUTH_CODE_CUSTODY_BINDING_MISMATCH")
        try:
            plaintext = AESGCM(self._key._key).decrypt(
                _unb64(envelope.nonce, minimum=12, maximum=12),
                _unb64(envelope.ciphertext, minimum=17, maximum=8192),
                record.command.authority_binding_sha256.encode("ascii"),
            )
            code = OAuthAuthorizationCodeSecret(plaintext.decode("utf-8"))
        except (InvalidTag, UnicodeError, ValueError):
            _fail("OAUTH_CODE_CUSTODY_CORRUPT")
        if not hmac.compare_digest(
            record.command.authorization_code_sha256,
            _digest(code.value),
        ):
            _fail("OAUTH_CODE_CUSTODY_CORRUPT")
        return code

    async def accept_callback_once(
        self,
        *,
        consume: OAuthConsumeCommand,
        exchange: OAuthExchangeCommand,
        callback_binding_sha256: str,
        authorization_code: OAuthAuthorizationCodeSecret,
        received_at: datetime,
    ) -> tuple[OAuthFlowConsumption, OAuthAuthorizationCodeCustodyCommand]:
        command = OAuthAuthorizationCodeCustodyCommand.build(
            consume=consume,
            exchange=exchange,
            callback_binding_sha256=callback_binding_sha256,
            authorization_code=authorization_code,
            received_at=received_at,
        )
        envelope = self._seal(command, authorization_code)
        consumption = await self._store.accept_once(
            command=command,
            consume=consume,
            envelope=envelope,
        )
        return consumption, command

    async def recover_code_for_exchange(
        self,
        exchange: OAuthExchangeCommand,
        *,
        state_sha256: str,
        now: datetime,
    ) -> tuple[OAuthAuthorizationCodeSecret, OAuthAuthorizationCodeCustodyCommand]:
        record = await self._store.claim_for_exchange(
            exchange,
            state_sha256=state_sha256,
        )
        return self._open(record, now=now), record.command

    async def retire(
        self,
        command: OAuthAuthorizationCodeCustodyCommand,
        *,
        reason: str,
    ) -> None:
        await self._store.retire(command, reason=reason)

    async def retire_for_exchange(
        self,
        exchange: OAuthExchangeCommand,
        *,
        state_sha256: str,
        reason: str,
    ) -> None:
        await self._store.retire_for_exchange(
            exchange,
            state_sha256=state_sha256,
            reason=reason,
        )

    def __repr__(self) -> str:
        return "ConnectedOAuthAuthorizationCodeVault(key='<redacted>')"

    def __getstate__(self) -> object:
        raise TypeError("authorization-code vault cannot be serialized")

    def __reduce_ex__(self, _protocol: int) -> object:
        raise TypeError("authorization-code vault cannot be serialized")


__all__ = [
    "ConnectedOAuthAuthorizationCodeVault",
    "ConnectedOAuthCodeCustodyError",
    "EncryptedOAuthAuthorizationCode",
    "OAuthAuthorizationCodeCustodyCommand",
    "OAuthAuthorizationCodeCustodyRecord",
    "SupabaseOAuthAuthorizationCodeCustodyStore",
]
