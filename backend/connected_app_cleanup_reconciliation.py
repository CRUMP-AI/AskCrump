"""Explicit durable reconciliation for connected-app OAuth cleanup.

This module is intentionally request/cron driven.  It does not create an
in-process loop, which lets a short-lived serverless worker invoke the same
bounded lane safely.  Encrypted cleanup rows are opened only long enough to
construct the redacted, non-serializable provider revocation secret.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import hmac
import json
import re
from collections.abc import Mapping
from typing import Any, Protocol
from uuid import UUID

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .connected_app_credential_vault import ConnectedCredentialMasterKey
from .connected_app_durable_oauth import ConnectedOAuthMasterKey
from .connected_app_grant_cleanup import (
    ConnectedGrantCleanupClaim,
    ConnectedGrantCleanupWorker,
    ProviderGrantRevocationSecret,
)


_KEY_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MAX_SECRET_BYTES = 64 * 1024
_PROVISIONAL_VERSION = "connected-oauth-provisional-credential-v1"


class ConnectedExternalReconciliationError(RuntimeError):
    """Content-free reconciliation failure."""

    _CODES = frozenset(
        {
            "CONNECTED_RECONCILIATION_INVALID",
            "CONNECTED_RECONCILIATION_KEY_UNAVAILABLE",
            "CONNECTED_RECONCILIATION_SECRET_CORRUPT",
            "CONNECTED_RECONCILIATION_STORE_UNAVAILABLE",
        }
    )

    def __init__(self, code: str) -> None:
        if code not in self._CODES:
            raise ValueError("invalid reconciliation error")
        self.code = code
        super().__init__(code)


def _sha(value: object) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ConnectedExternalReconciliationError(
            "CONNECTED_RECONCILIATION_SECRET_CORRUPT"
        )
    return value


def _key_id(value: object) -> str:
    if not isinstance(value, str) or _KEY_ID.fullmatch(value) is None:
        raise ConnectedExternalReconciliationError(
            "CONNECTED_RECONCILIATION_SECRET_CORRUPT"
        )
    return value


def _decode(value: object, *, size: int | None = None, maximum: int) -> bytes:
    if not isinstance(value, str) or not value or len(value) > maximum * 2:
        raise ConnectedExternalReconciliationError(
            "CONNECTED_RECONCILIATION_SECRET_CORRUPT"
        )
    try:
        decoded = base64.b64decode(
            value + "=" * (-len(value) % 4),
            altchars=b"-_",
            validate=True,
        )
    except (TypeError, ValueError):
        raise ConnectedExternalReconciliationError(
            "CONNECTED_RECONCILIATION_SECRET_CORRUPT"
        ) from None
    canonical = base64.urlsafe_b64encode(decoded).decode("ascii").rstrip("=")
    if (
        canonical != value
        or not 1 <= len(decoded) <= maximum
        or (size is not None and len(decoded) != size)
    ):
        raise ConnectedExternalReconciliationError(
            "CONNECTED_RECONCILIATION_SECRET_CORRUPT"
        )
    return decoded


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_hash(value: Mapping[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
    ).hexdigest()


def _uuid(value: object) -> str:
    if not isinstance(value, str):
        raise ConnectedExternalReconciliationError(
            "CONNECTED_RECONCILIATION_SECRET_CORRUPT"
        )
    try:
        canonical = str(UUID(value))
    except (TypeError, ValueError, AttributeError):
        raise ConnectedExternalReconciliationError(
            "CONNECTED_RECONCILIATION_SECRET_CORRUPT"
        ) from None
    if canonical != value:
        raise ConnectedExternalReconciliationError(
            "CONNECTED_RECONCILIATION_SECRET_CORRUPT"
        )
    return value


def _time(value: object) -> str:
    if not isinstance(value, str) or not value or len(value) > 64:
        raise ConnectedExternalReconciliationError(
            "CONNECTED_RECONCILIATION_SECRET_CORRUPT"
        )
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ConnectedExternalReconciliationError(
            "CONNECTED_RECONCILIATION_SECRET_CORRUPT"
        ) from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ConnectedExternalReconciliationError(
            "CONNECTED_RECONCILIATION_SECRET_CORRUPT"
        )
    return parsed.astimezone(UTC).isoformat()


def _positive(value: object) -> int:
    if type(value) is not int or value < 1:
        raise ConnectedExternalReconciliationError(
            "CONNECTED_RECONCILIATION_SECRET_CORRUPT"
        )
    return value


def _account_kind(value: object) -> str:
    if not isinstance(value, str) or value not in {"personal", "work_school"}:
        raise ConnectedExternalReconciliationError(
            "CONNECTED_RECONCILIATION_SECRET_CORRUPT"
        )
    return value


def _decoded_json(value: bytes, keys: frozenset[str]) -> dict[str, object]:
    return _decoded_json_one_of(value, (keys,))


def _decoded_json_one_of(
    value: bytes,
    key_sets: tuple[frozenset[str], ...],
) -> dict[str, object]:
    def unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, item in pairs:
            if key in result:
                raise ValueError
            result[key] = item
        return result

    try:
        decoded = json.loads(
            value.decode("ascii"),
            object_pairs_hook=unique,
            parse_constant=lambda _value: (_ for _ in ()).throw(ValueError()),
        )
    except (TypeError, ValueError, UnicodeError, json.JSONDecodeError, RecursionError):
        raise ConnectedExternalReconciliationError(
            "CONNECTED_RECONCILIATION_SECRET_CORRUPT"
        ) from None
    if type(decoded) is not dict or not any(set(decoded) == keys for keys in key_sets):
        raise ConnectedExternalReconciliationError(
            "CONNECTED_RECONCILIATION_SECRET_CORRUPT"
        )
    return decoded


_CREDENTIAL_KEYS = frozenset(
    {
        "credential_handle_sha256",
        "owner_id",
        "connection_id",
        "provider",
        "connection_incarnation_id",
        "oauth_client_id_sha256",
        "account_kind",
        "authorization_revision",
        "authorization_snapshot_sha256",
        "granted_actions_sha256",
        "granted_scopes_sha256",
        "external_account_id_hash",
        "authorization_expires_at",
        "secret_revision",
        "created_at",
        "updated_at",
        "authority_binding_sha256",
        "metadata_binding_sha256",
        "key_id",
        "wrapped_key_nonce",
        "wrapped_key_ciphertext",
        "secret_nonce",
        "secret_ciphertext",
        "record_binding_sha256",
    }
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
        "authority_binding_sha256",
        "key_id",
        "wrapped_key_nonce",
        "wrapped_key_ciphertext",
        "secret_nonce",
        "secret_ciphertext",
        "record_binding_sha256",
    }
)


class EncryptedProviderGrantSecretResolver:
    """Open exact credential/provisional cleanup snapshots under key custody."""

    def __init__(
        self,
        *,
        credential_keys: Mapping[str, ConnectedCredentialMasterKey],
        oauth_keys: Mapping[str, ConnectedOAuthMasterKey],
    ) -> None:
        self._credential_keys = self._copy_keys(
            credential_keys, ConnectedCredentialMasterKey
        )
        self._oauth_keys = self._copy_keys(oauth_keys, ConnectedOAuthMasterKey)

    @staticmethod
    def _copy_keys(value: Mapping[str, object], expected: type) -> dict[str, object]:
        if not isinstance(value, Mapping) or not value:
            raise ConnectedExternalReconciliationError(
                "CONNECTED_RECONCILIATION_INVALID"
            )
        copied: dict[str, object] = {}
        for key_id, key in value.items():
            if not isinstance(key_id, str) or not isinstance(key, expected):
                raise ConnectedExternalReconciliationError(
                    "CONNECTED_RECONCILIATION_INVALID"
                )
            if key.key_id != key_id:  # type: ignore[attr-defined]
                raise ConnectedExternalReconciliationError(
                    "CONNECTED_RECONCILIATION_INVALID"
                )
            copied[key_id] = key
        return copied

    @staticmethod
    def _decrypt(
        *,
        key: object,
        wrapped_nonce: bytes,
        wrapped_ciphertext: bytes,
        secret_nonce: bytes,
        secret_ciphertext: bytes,
        wrap_aad: bytes,
        aad: bytes,
    ) -> bytes:
        try:
            data_key = AESGCM(key._key).decrypt(  # type: ignore[attr-defined]
                wrapped_nonce,
                wrapped_ciphertext,
                wrap_aad,
            )
            return AESGCM(data_key).decrypt(secret_nonce, secret_ciphertext, aad)
        except (InvalidTag, TypeError, ValueError):
            raise ConnectedExternalReconciliationError(
                "CONNECTED_RECONCILIATION_SECRET_CORRUPT"
            ) from None

    def _credential_token(self, claim: ConnectedGrantCleanupClaim) -> str:
        row = claim.encrypted_record
        if set(row) != _CREDENTIAL_KEYS or row.get("provider") != claim.provider.value:
            raise ConnectedExternalReconciliationError(
                "CONNECTED_RECONCILIATION_SECRET_CORRUPT"
            )
        key_id = _key_id(row["key_id"])
        key = self._credential_keys.get(key_id)
        if key is None:
            raise ConnectedExternalReconciliationError(
                "CONNECTED_RECONCILIATION_KEY_UNAVAILABLE"
            )
        authority_binding = _canonical_hash(
            {
                "version": "connected-credential-envelope-v1",
                "owner_id": _uuid(row["owner_id"]),
                "connection_id": _uuid(row["connection_id"]),
                "provider": claim.provider.value,
                "credential_handle_sha256": _sha(
                    row["credential_handle_sha256"]
                ),
                "connection_incarnation_id": _uuid(
                    row["connection_incarnation_id"]
                ),
                "oauth_client_id_sha256": _sha(row["oauth_client_id_sha256"]),
                "account_kind": _account_kind(row["account_kind"]),
                "authorization_revision": _positive(
                    row["authorization_revision"]
                ),
                "authorization_snapshot_sha256": _sha(
                    row["authorization_snapshot_sha256"]
                ),
                "granted_actions_sha256": _sha(row["granted_actions_sha256"]),
                "granted_scopes_sha256": _sha(row["granted_scopes_sha256"]),
                "external_account_id_hash": _sha(row["external_account_id_hash"]),
                "authorization_expires_at": _time(
                    row["authorization_expires_at"]
                ),
            }
        )
        if not hmac.compare_digest(
            authority_binding, _sha(row["authority_binding_sha256"])
        ):
            raise ConnectedExternalReconciliationError(
                "CONNECTED_RECONCILIATION_SECRET_CORRUPT"
            )
        metadata_binding = _canonical_hash(
            {
                "version": "connected-credential-envelope-v1",
                "authority_binding_sha256": authority_binding,
                "secret_revision": _positive(row["secret_revision"]),
                "created_at": _time(row["created_at"]),
                "updated_at": _time(row["updated_at"]),
            }
        )
        if not hmac.compare_digest(
            metadata_binding, _sha(row["metadata_binding_sha256"])
        ):
            raise ConnectedExternalReconciliationError(
                "CONNECTED_RECONCILIATION_SECRET_CORRUPT"
            )
        wrapped_nonce = _decode(row["wrapped_key_nonce"], size=12, maximum=12)
        wrapped_ciphertext = _decode(
            row["wrapped_key_ciphertext"], size=48, maximum=48
        )
        secret_nonce = _decode(row["secret_nonce"], size=12, maximum=12)
        secret_ciphertext = _decode(
            row["secret_ciphertext"], maximum=32 * 1024 + 16
        )
        expected_record = _canonical_hash(
            {
                "version": "connected-credential-envelope-v1",
                "metadata_binding_sha256": metadata_binding,
                "key_id": key_id,
                "wrapped_key_nonce_sha256": _digest(wrapped_nonce),
                "wrapped_key_ciphertext_sha256": _digest(wrapped_ciphertext),
                "secret_nonce_sha256": _digest(secret_nonce),
                "secret_ciphertext_sha256": _digest(secret_ciphertext),
            }
        )
        record_binding = _sha(row["record_binding_sha256"])
        if not hmac.compare_digest(record_binding, expected_record) or not hmac.compare_digest(
            record_binding, claim.source_binding_sha256
        ):
            raise ConnectedExternalReconciliationError(
                "CONNECTED_RECONCILIATION_SECRET_CORRUPT"
            )
        aad = metadata_binding.encode("ascii")
        plaintext = self._decrypt(
            key=key,
            wrapped_nonce=wrapped_nonce,
            wrapped_ciphertext=wrapped_ciphertext,
            secret_nonce=secret_nonce,
            secret_ciphertext=secret_ciphertext,
            wrap_aad=(
                b"connected-credential-key-v1\x00"
                + key_id.encode("ascii")
                + b"\x00"
                + aad
            ),
            aad=aad,
        )
        decoded = _decoded_json(plaintext, frozenset({"refresh_token"}))
        if not isinstance(decoded["refresh_token"], str):
            raise ConnectedExternalReconciliationError(
                "CONNECTED_RECONCILIATION_SECRET_CORRUPT"
            )
        return decoded["refresh_token"]

    def _provisional_token(self, claim: ConnectedGrantCleanupClaim) -> str:
        row = claim.encrypted_record
        if (
            set(row) != _PROVISIONAL_KEYS
            or row.get("provider") != claim.provider.value
            or row.get("status") not in {"provisional", "quarantined"}
        ):
            raise ConnectedExternalReconciliationError(
                "CONNECTED_RECONCILIATION_SECRET_CORRUPT"
            )
        key_id = _key_id(row["key_id"])
        key = self._oauth_keys.get(key_id)
        if key is None:
            raise ConnectedExternalReconciliationError(
                "CONNECTED_RECONCILIATION_KEY_UNAVAILABLE"
            )
        scopes = row["granted_scopes"]
        if (
            type(scopes) is not list
            or not scopes
            or len(scopes) > 64
            or any(
                not isinstance(scope, str)
                or not scope
                or len(scope) > 512
                or any(character.isspace() for character in scope)
                for scope in scopes
            )
            or len(set(scopes)) != len(scopes)
        ):
            raise ConnectedExternalReconciliationError(
                "CONNECTED_RECONCILIATION_SECRET_CORRUPT"
            )
        scopes_binding = _digest(
            json.dumps(sorted(scopes), separators=(",", ":")).encode("ascii")
        )
        if not hmac.compare_digest(
            scopes_binding, _sha(row["granted_scopes_sha256"])
        ):
            raise ConnectedExternalReconciliationError(
                "CONNECTED_RECONCILIATION_SECRET_CORRUPT"
            )
        authority_binding = _canonical_hash(
            {
                "version": _PROVISIONAL_VERSION,
                "provisional_id": _uuid(row["provisional_id"]),
                "owner_id": _uuid(row["owner_id"]),
                "connection_id": _uuid(row["connection_id"]),
                "connection_incarnation_id": _uuid(
                    row["connection_incarnation_id"]
                ),
                "flow_id": _uuid(row["flow_id"]),
                "exchange_id": _uuid(row["exchange_id"]),
                "provider": claim.provider.value,
                "account_kind": _account_kind(row["account_kind"]),
                "credential_handle_sha256": _sha(
                    row["credential_handle_sha256"]
                ),
                "oauth_client_id_sha256": _sha(row["oauth_client_id_sha256"]),
                "external_account_id_hash": _sha(row["external_account_id_hash"]),
                "granted_scopes_sha256": scopes_binding,
                "exchange_binding_sha256": _sha(
                    row["exchange_binding_sha256"]
                ),
                "issued_at": _time(row["issued_at"]),
                "expires_at": _time(row["expires_at"]),
            }
        )
        if not hmac.compare_digest(
            authority_binding, _sha(row["authority_binding_sha256"])
        ):
            raise ConnectedExternalReconciliationError(
                "CONNECTED_RECONCILIATION_SECRET_CORRUPT"
            )
        envelope_kind = "provisional" if row["status"] == "provisional" else "quarantine"
        wrapped_nonce = _decode(row["wrapped_key_nonce"], size=12, maximum=12)
        wrapped_ciphertext = _decode(
            row["wrapped_key_ciphertext"], size=48, maximum=48
        )
        secret_nonce = _decode(row["secret_nonce"], size=12, maximum=12)
        secret_ciphertext = _decode(
            row["secret_ciphertext"], maximum=_MAX_SECRET_BYTES + 16
        )
        expected_record = _canonical_hash(
            {
                "version": "connected-oauth-envelope-v1",
                "envelope_kind": envelope_kind,
                "authority_binding_sha256": authority_binding,
                "key_id": key_id,
                "wrapped_key_nonce_sha256": _digest(wrapped_nonce),
                "wrapped_key_ciphertext_sha256": _digest(wrapped_ciphertext),
                "secret_nonce_sha256": _digest(secret_nonce),
                "secret_ciphertext_sha256": _digest(secret_ciphertext),
            }
        )
        record_binding = _sha(row["record_binding_sha256"])
        if not hmac.compare_digest(record_binding, expected_record) or not hmac.compare_digest(
            record_binding, claim.source_binding_sha256
        ):
            raise ConnectedExternalReconciliationError(
                "CONNECTED_RECONCILIATION_SECRET_CORRUPT"
            )
        aad = f"{envelope_kind}\x00{authority_binding}".encode("ascii")
        plaintext = self._decrypt(
            key=key,
            wrapped_nonce=wrapped_nonce,
            wrapped_ciphertext=wrapped_ciphertext,
            secret_nonce=secret_nonce,
            secret_ciphertext=secret_ciphertext,
            wrap_aad=(
                b"connected-oauth-key-v1\x00"
                + key_id.encode("ascii")
                + b"\x00"
                + aad
            ),
            aad=aad,
        )
        legacy_keys = frozenset(
            {
                "version",
                "provisional_binding_sha256",
                "credential_handle",
                "refresh_token",
                "flow_binding_sha256",
            }
        )
        quarantine_keys = frozenset(
            {
                "version",
                "provisional_binding_sha256",
                "credential_handle",
                "access_token",
                "refresh_token",
                "revocation_token_kind",
                "flow_binding_sha256",
            }
        )
        decoded = _decoded_json_one_of(
            plaintext,
            (legacy_keys, quarantine_keys) if envelope_kind == "quarantine" else (legacy_keys,),
        )
        if (
            decoded["version"] != _PROVISIONAL_VERSION
            or decoded["provisional_binding_sha256"] != authority_binding
            or not isinstance(decoded["credential_handle"], str)
            or _digest(decoded["credential_handle"].encode("utf-8"))
            != row["credential_handle_sha256"]
            or _sha(decoded["flow_binding_sha256"])
            != decoded["flow_binding_sha256"]
        ):
            raise ConnectedExternalReconciliationError(
                "CONNECTED_RECONCILIATION_SECRET_CORRUPT"
            )
        if set(decoded) == legacy_keys:
            token = decoded["refresh_token"]
            if not isinstance(token, str):
                raise ConnectedExternalReconciliationError(
                    "CONNECTED_RECONCILIATION_SECRET_CORRUPT"
                )
            return token
        access_token = decoded["access_token"]
        refresh_token = decoded["refresh_token"]
        token_kind = decoded["revocation_token_kind"]
        if (
            (access_token is not None and not isinstance(access_token, str))
            or (refresh_token is not None and not isinstance(refresh_token, str))
            or token_kind not in {"access", "refresh"}
            or (token_kind == "access" and not isinstance(access_token, str))
            or (token_kind == "refresh" and not isinstance(refresh_token, str))
        ):
            raise ConnectedExternalReconciliationError(
                "CONNECTED_RECONCILIATION_SECRET_CORRUPT"
            )
        return refresh_token if token_kind == "refresh" else access_token

    async def resolve(
        self,
        claim: ConnectedGrantCleanupClaim,
    ) -> ProviderGrantRevocationSecret:
        if not isinstance(claim, ConnectedGrantCleanupClaim):
            raise ConnectedExternalReconciliationError(
                "CONNECTED_RECONCILIATION_INVALID"
            )
        token = (
            self._provisional_token(claim)
            if claim.source_kind == "provisional"
            else self._credential_token(claim)
        )
        try:
            return ProviderGrantRevocationSecret(token)
        except (TypeError, ValueError):
            raise ConnectedExternalReconciliationError(
                "CONNECTED_RECONCILIATION_SECRET_CORRUPT"
            ) from None

    def __repr__(self) -> str:
        return "EncryptedProviderGrantSecretResolver(keys='<redacted>')"


class ConnectedOAuthExpiryRPC(Protocol):
    async def rpc(
        self,
        function_name: str,
        payload: dict[str, Any],
        *,
        retry_transient: bool = False,
    ) -> Any: ...


class SupabaseConnectedOAuthExpiryReconciler:
    """Bounded adapter for the atomic expiry/provisional cleanup RPC."""

    def __init__(self, rpc: ConnectedOAuthExpiryRPC) -> None:
        if not callable(getattr(rpc, "rpc", None)):
            raise TypeError("OAuth expiry RPC boundary is invalid")
        self._rpc = rpc

    async def run_bounded(self, *, maximum: int) -> tuple[int, int]:
        if type(maximum) is not int or not 1 <= maximum <= 100:
            raise ConnectedExternalReconciliationError(
                "CONNECTED_RECONCILIATION_INVALID"
            )
        try:
            value = await self._rpc.rpc(
                "connected_app_oauth_reconcile_expired_v1",
                {"p_limit": maximum},
                retry_transient=False,
            )
        except Exception:
            raise ConnectedExternalReconciliationError(
                "CONNECTED_RECONCILIATION_STORE_UNAVAILABLE"
            ) from None
        if isinstance(value, list) and len(value) == 1:
            value = value[0]
        if type(value) is not dict or set(value) != {
            "expired_flows",
            "expired_provisionals",
        }:
            raise ConnectedExternalReconciliationError(
                "CONNECTED_RECONCILIATION_SECRET_CORRUPT"
            )
        flows = value["expired_flows"]
        provisionals = value["expired_provisionals"]
        if (
            type(flows) is not int
            or type(provisionals) is not int
            or not 0 <= flows <= maximum
            or not 0 <= provisionals <= maximum
        ):
            raise ConnectedExternalReconciliationError(
                "CONNECTED_RECONCILIATION_SECRET_CORRUPT"
            )
        return flows, provisionals


@dataclass(frozen=True, slots=True)
class ConnectedExternalReconciliationResult:
    cleanup_attempts: int
    cleanup_terminal: int
    expired_flows: int
    expired_provisionals: int
    cleanup_failed: bool
    expiry_failed: bool
    observed_at: datetime

    def __post_init__(self) -> None:
        for name in (
            "cleanup_attempts",
            "cleanup_terminal",
            "expired_flows",
            "expired_provisionals",
        ):
            if type(getattr(self, name)) is not int or getattr(self, name) < 0:
                raise ConnectedExternalReconciliationError(
                    "CONNECTED_RECONCILIATION_INVALID"
                )
        if type(self.cleanup_failed) is not bool or type(self.expiry_failed) is not bool:
            raise ConnectedExternalReconciliationError(
                "CONNECTED_RECONCILIATION_INVALID"
            )
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ConnectedExternalReconciliationError(
                "CONNECTED_RECONCILIATION_INVALID"
            )


class ConnectedExternalReconciliationCoordinator:
    """One authenticated external wake over cleanup and OAuth expiry lanes."""

    def __init__(
        self,
        *,
        cleanup: ConnectedGrantCleanupWorker,
        oauth_expiry: SupabaseConnectedOAuthExpiryReconciler,
        now=lambda: datetime.now(UTC),
    ) -> None:
        if not isinstance(cleanup, ConnectedGrantCleanupWorker):
            raise TypeError("cleanup worker is invalid")
        if not isinstance(oauth_expiry, SupabaseConnectedOAuthExpiryReconciler):
            raise TypeError("OAuth expiry reconciler is invalid")
        if not callable(now):
            raise TypeError("reconciliation clock is invalid")
        self._cleanup = cleanup
        self._oauth_expiry = oauth_expiry
        self._now = now

    async def run_bounded(
        self,
        *,
        cleanup_maximum: int = 16,
        expiry_maximum: int = 32,
    ) -> ConnectedExternalReconciliationResult:
        if (
            type(cleanup_maximum) is not int
            or not 1 <= cleanup_maximum <= 100
            or type(expiry_maximum) is not int
            or not 1 <= expiry_maximum <= 100
        ):
            raise ConnectedExternalReconciliationError(
                "CONNECTED_RECONCILIATION_INVALID"
            )
        cleanup_attempts = 0
        cleanup_terminal = 0
        cleanup_failed = False
        for _ in range(cleanup_maximum):
            try:
                outcome = await self._cleanup.run_once()
            except Exception:
                cleanup_failed = True
                break
            if outcome == "empty":
                break
            cleanup_attempts += 1
            cleanup_terminal += int(outcome in {"succeeded", "user_action_required"})
        expired_flows = 0
        expired_provisionals = 0
        expiry_failed = False
        try:
            expired_flows, expired_provisionals = await self._oauth_expiry.run_bounded(
                maximum=expiry_maximum
            )
        except Exception:
            expiry_failed = True
        observed = self._now()
        if not isinstance(observed, datetime) or observed.tzinfo is None:
            raise ConnectedExternalReconciliationError(
                "CONNECTED_RECONCILIATION_INVALID"
            )
        return ConnectedExternalReconciliationResult(
            cleanup_attempts=cleanup_attempts,
            cleanup_terminal=cleanup_terminal,
            expired_flows=expired_flows,
            expired_provisionals=expired_provisionals,
            cleanup_failed=cleanup_failed,
            expiry_failed=expiry_failed,
            observed_at=observed.astimezone(UTC),
        )

    def __repr__(self) -> str:
        return "ConnectedExternalReconciliationCoordinator(content='<none>')"


__all__ = [
    "ConnectedExternalReconciliationCoordinator",
    "ConnectedExternalReconciliationError",
    "ConnectedExternalReconciliationResult",
    "EncryptedProviderGrantSecretResolver",
    "SupabaseConnectedOAuthExpiryReconciler",
]
