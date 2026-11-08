"""Encrypted refresh-token custody and lease-bound access-token issuance.

Only refresh tokens are persisted. Provider access tokens remain ephemeral and
are exposed solely as owner/connection/credential-bound ``ConnectedAccessToken``
objects to the fixed-host provider transport.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import re
import secrets
from collections import OrderedDict
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from typing import Callable, Mapping, Protocol
from uuid import UUID

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from backend.connected_app_contracts import (
    ConnectedAccountRef,
    ConnectedAuthorizationSnapshot,
    ConnectorAccountKind,
    CredentialHandleRef,
)
from backend.connected_app_https import ConnectedAccessToken, ConnectedAccessTokenSource
from backend.connected_app_policy import ConnectorProvider
from backend.connected_app_provider_oauth import (
    ProviderOAuthEffectUnknown,
    ProviderOAuthAccessToken,
    ProviderOAuthHTTPSClient,
    ProviderOAuthRefreshToken,
    ProviderOAuthTokenBinding,
    ProviderOAuthTokenSet,
)


_KEY_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_NONCE_BYTES = 12
_DATA_KEY_BYTES = 32
_MAX_SECRET_BYTES = 32 * 1024
_CACHE_MIN_REMAINING = timedelta(minutes=2)
_BINDING_VERSION = "connected-credential-envelope-v1"


def _uuid(value: str, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be text")
    try:
        canonical = str(UUID(value))
    except (TypeError, ValueError, AttributeError):
        raise ValueError(f"{name} must be a canonical UUID") from None
    if value != canonical:
        raise ValueError(f"{name} must be a canonical UUID")
    return canonical


def _aware(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(UTC)


def _sha(value: str, name: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ValueError(f"{name} must be a lowercase SHA-256 digest")
    return value


def _digest(value: str | bytes) -> str:
    if isinstance(value, str):
        value = value.encode("utf-8")
    return hashlib.sha256(value).hexdigest()


def _canonical_hash(value: Mapping[str, object]) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")
    return _digest(encoded)


def _scope_hash(scopes: frozenset[str]) -> str:
    if (
        not isinstance(scopes, frozenset)
        or not scopes
        or any(
            not isinstance(scope, str)
            or not 1 <= len(scope) <= 512
            or scope != scope.strip()
            or any(
                character.isspace() or ord(character) < 33 or ord(character) == 127
                for character in scope
            )
            for scope in scopes
        )
    ):
        raise ValueError("granted scopes are invalid")
    encoded = json.dumps(
        sorted(scopes),
        ensure_ascii=True,
        separators=(",", ":"),
    ).encode("ascii")
    return _digest(encoded)


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _unb64(value: str, name: str, *, size: int | None = None, maximum: int) -> bytes:
    if not isinstance(value, str) or not value or len(value) > maximum * 2:
        raise ValueError(f"{name} is invalid")
    try:
        decoded = base64.b64decode(
            value + "=" * (-len(value) % 4),
            altchars=b"-_",
            validate=True,
        )
    except (TypeError, ValueError):
        raise ValueError(f"{name} is invalid") from None
    if (size is not None and len(decoded) != size) or not 1 <= len(decoded) <= maximum:
        raise ValueError(f"{name} is invalid")
    if _b64(decoded) != value:
        raise ValueError(f"{name} is invalid")
    return decoded


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


class ConnectedCredentialVaultError(RuntimeError):
    """Content-free credential custody failure."""

    _ALLOWED = {
        "CREDENTIAL_AUTHORITY_MISMATCH",
        "CREDENTIAL_CORRUPT",
        "CREDENTIAL_EXPIRED",
        "CREDENTIAL_KEY_UNAVAILABLE",
        "CREDENTIAL_NOT_FOUND",
        "CREDENTIAL_QUARANTINED",
        "CREDENTIAL_REFRESH_FAILED",
        "CREDENTIAL_STORE_FAILED",
    }

    def __init__(self, code: str) -> None:
        if code not in self._ALLOWED:
            raise ValueError("invalid credential-vault error code")
        self.code = code
        super().__init__(code)


class ConnectedCredentialMasterKey:
    """Redacted, non-serializable AES-256 wrapping key."""

    __slots__ = ("_key", "key_id")

    def __init__(self, key_id: str, raw_key: bytes) -> None:
        if not isinstance(key_id, str) or not _KEY_ID.fullmatch(key_id):
            raise ValueError("credential master key ID is invalid")
        if type(raw_key) is not bytes or len(raw_key) != 32:
            raise ValueError("credential master key must contain exactly 32 bytes")
        object.__setattr__(self, "key_id", key_id)
        object.__setattr__(self, "_key", raw_key)

    def __setattr__(self, _name: str, _value: object) -> None:
        raise AttributeError("credential master key is immutable")

    @classmethod
    def from_base64url(cls, key_id: str, encoded: str) -> ConnectedCredentialMasterKey:
        return cls(
            key_id,
            _unb64(encoded, "credential master key", size=32, maximum=32),
        )

    def __repr__(self) -> str:
        return f"ConnectedCredentialMasterKey(key_id={self.key_id!r}, key='<redacted>')"

    def __getstate__(self) -> None:
        raise TypeError("credential master key cannot be serialized")

    def __reduce_ex__(self, _protocol: int) -> None:
        raise TypeError("credential master key cannot be serialized")


@dataclass(frozen=True, slots=True, repr=False)
class ConnectedCredentialMetadata:
    credential: CredentialHandleRef = field(repr=False, compare=False)
    connection_incarnation_id: str
    oauth_client_id_sha256: str
    account_kind: ConnectorAccountKind
    authorization_revision: int
    authorization_snapshot_sha256: str
    granted_actions_sha256: str
    granted_scopes_sha256: str
    external_account_id_hash: str
    authorization_expires_at: datetime
    secret_revision: int
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.credential, CredentialHandleRef):
            raise TypeError("credential must be CredentialHandleRef")
        object.__setattr__(
            self,
            "connection_incarnation_id",
            _uuid(self.connection_incarnation_id, "connection_incarnation_id"),
        )
        if not isinstance(self.account_kind, ConnectorAccountKind):
            raise TypeError("account_kind must be ConnectorAccountKind")
        if type(self.authorization_revision) is not int or self.authorization_revision < 1:
            raise ValueError("authorization_revision is invalid")
        if type(self.secret_revision) is not int or self.secret_revision < 1:
            raise ValueError("secret_revision is invalid")
        for name in (
            "authorization_snapshot_sha256",
            "granted_actions_sha256",
            "granted_scopes_sha256",
            "external_account_id_hash",
            "oauth_client_id_sha256",
        ):
            object.__setattr__(self, name, _sha(getattr(self, name), name))
        created = _aware(self.created_at, "created_at")
        updated = _aware(self.updated_at, "updated_at")
        expires = _aware(self.authorization_expires_at, "authorization_expires_at")
        object.__setattr__(self, "created_at", created)
        object.__setattr__(self, "updated_at", updated)
        object.__setattr__(self, "authorization_expires_at", expires)
        if updated < created or expires <= created:
            raise ValueError("credential metadata timestamps are invalid")

    @property
    def authority_binding_sha256(self) -> str:
        return _canonical_hash(
            {
                "version": _BINDING_VERSION,
                "owner_id": self.credential.owner_id,
                "connection_id": self.credential.connection_id,
                "provider": self.credential.provider.value,
                "credential_handle_sha256": _digest(self.credential.handle_id),
                "connection_incarnation_id": self.connection_incarnation_id,
                "oauth_client_id_sha256": self.oauth_client_id_sha256,
                "account_kind": self.account_kind.value,
                "authorization_revision": self.authorization_revision,
                "authorization_snapshot_sha256": self.authorization_snapshot_sha256,
                "granted_actions_sha256": self.granted_actions_sha256,
                "granted_scopes_sha256": self.granted_scopes_sha256,
                "external_account_id_hash": self.external_account_id_hash,
                "authorization_expires_at": self.authorization_expires_at.isoformat(),
            }
        )

    @property
    def binding_sha256(self) -> str:
        return _canonical_hash(
            {
                "version": _BINDING_VERSION,
                "authority_binding_sha256": self.authority_binding_sha256,
                "secret_revision": self.secret_revision,
                "created_at": self.created_at.isoformat(),
                "updated_at": self.updated_at.isoformat(),
            }
        )

    def __repr__(self) -> str:
        return (
            "ConnectedCredentialMetadata("
            f"provider={self.credential.provider.value!r}, "
            f"authorization_revision={self.authorization_revision}, "
            f"secret_revision={self.secret_revision}, credential='<redacted>')"
        )


@dataclass(frozen=True, slots=True, repr=False)
class EncryptedConnectedCredential:
    metadata: ConnectedCredentialMetadata
    key_id: str
    wrapped_key_nonce: str = field(repr=False)
    wrapped_key_ciphertext: str = field(repr=False)
    secret_nonce: str = field(repr=False)
    secret_ciphertext: str = field(repr=False)
    record_binding_sha256: str = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.metadata, ConnectedCredentialMetadata):
            raise TypeError("metadata must be ConnectedCredentialMetadata")
        if not isinstance(self.key_id, str) or not _KEY_ID.fullmatch(self.key_id):
            raise ValueError("credential key ID is invalid")
        _unb64(self.wrapped_key_nonce, "wrapped key nonce", size=12, maximum=12)
        _unb64(self.wrapped_key_ciphertext, "wrapped key ciphertext", size=48, maximum=48)
        _unb64(self.secret_nonce, "secret nonce", size=12, maximum=12)
        _unb64(self.secret_ciphertext, "secret ciphertext", maximum=_MAX_SECRET_BYTES + 16)
        object.__setattr__(
            self,
            "record_binding_sha256",
            _sha(self.record_binding_sha256, "record_binding_sha256"),
        )
        if not hmac.compare_digest(self.record_binding_sha256, self.expected_binding_sha256):
            raise ValueError("credential record binding is invalid")

    @property
    def expected_binding_sha256(self) -> str:
        return _canonical_hash(
            {
                "version": _BINDING_VERSION,
                "metadata_binding_sha256": self.metadata.binding_sha256,
                "key_id": self.key_id,
                "wrapped_key_nonce_sha256": _digest(
                    _unb64(self.wrapped_key_nonce, "wrapped key nonce", size=12, maximum=12)
                ),
                "wrapped_key_ciphertext_sha256": _digest(
                    _unb64(
                        self.wrapped_key_ciphertext,
                        "wrapped key ciphertext",
                        size=48,
                        maximum=48,
                    )
                ),
                "secret_nonce_sha256": _digest(
                    _unb64(self.secret_nonce, "secret nonce", size=12, maximum=12)
                ),
                "secret_ciphertext_sha256": _digest(
                    _unb64(
                        self.secret_ciphertext,
                        "secret ciphertext",
                        maximum=_MAX_SECRET_BYTES + 16,
                    )
                ),
            }
        )

    def __repr__(self) -> str:
        return (
            "EncryptedConnectedCredential("
            f"provider={self.metadata.credential.provider.value!r}, "
            f"secret_revision={self.metadata.secret_revision}, "
            "credential='<redacted>', ciphertext='<redacted>')"
        )


class ConnectedCredentialSecretStore(Protocol):
    """CAS store for encrypted credential records."""

    async def create_once(
        self, record: EncryptedConnectedCredential
    ) -> EncryptedConnectedCredential: ...

    async def read(
        self, credential: CredentialHandleRef
    ) -> EncryptedConnectedCredential | None: ...

    async def replace_once(
        self,
        *,
        expected_record_binding_sha256: str,
        record: EncryptedConnectedCredential,
    ) -> EncryptedConnectedCredential: ...

    async def delete_once(
        self,
        *,
        credential: CredentialHandleRef,
        expected_record_binding_sha256: str,
    ) -> bool: ...


class ConnectedCredentialRefreshCoordinator(Protocol):
    """Optional cross-host refresh serialization boundary.

    The in-process broker lock is insufficient when several application hosts
    can rotate the same provider refresh token.  A production composition must
    inject a durable coordinator and re-open the credential after claiming.
    """

    async def claim(
        self,
        *,
        credential: CredentialHandleRef,
        expected_record_binding_sha256: str,
        lease_for: timedelta = timedelta(seconds=15),
    ) -> object: ...

    async def finish(self, lease: object) -> None: ...

    async def quarantine(self, lease: object) -> None:
        """Permanently fence a possibly consumed rotating refresh token."""
        ...

    async def commit_rotation(
        self,
        *,
        lease: object,
        record: EncryptedConnectedCredential,
    ) -> EncryptedConnectedCredential:
        """Commit ciphertext and retire the exact live lease atomically."""
        ...


@dataclass(frozen=True, slots=True, repr=False)
class ConnectedRefreshCredential:
    record: EncryptedConnectedCredential
    refresh_token: ProviderOAuthRefreshToken = field(repr=False, compare=False)
    granted_scopes: frozenset[str] = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.record, EncryptedConnectedCredential):
            raise TypeError("record must be EncryptedConnectedCredential")
        if not isinstance(self.refresh_token, ProviderOAuthRefreshToken):
            raise TypeError("refresh_token must be ProviderOAuthRefreshToken")
        if not isinstance(self.granted_scopes, frozenset) or not self.granted_scopes:
            raise ValueError("granted_scopes must be a nonempty frozen set")
        if _scope_hash(self.granted_scopes) != self.record.metadata.granted_scopes_sha256:
            raise ValueError("credential scopes do not match metadata")

    def __repr__(self) -> str:
        return (
            "ConnectedRefreshCredential("
            f"provider={self.record.metadata.credential.provider.value!r}, "
            f"scope_count={len(self.granted_scopes)}, refresh_token='<redacted>')"
        )


class ConnectedCredentialVault:
    """Envelope-encrypted refresh-token store with exact authority binding."""

    def __init__(
        self,
        *,
        keys: Mapping[str, ConnectedCredentialMasterKey],
        active_key_id: str,
        store: ConnectedCredentialSecretStore,
        now: Callable[[], datetime] | None = None,
        random_bytes: Callable[[int], bytes] = secrets.token_bytes,
    ) -> None:
        if not isinstance(keys, Mapping) or not keys:
            raise ValueError("credential vault requires a key ring")
        copied: dict[str, ConnectedCredentialMasterKey] = {}
        for key_id, key in keys.items():
            if not isinstance(key, ConnectedCredentialMasterKey) or key.key_id != key_id:
                raise ValueError("credential key ring is invalid")
            copied[key_id] = key
        if active_key_id not in copied:
            raise ValueError("active credential key is unavailable")
        for method in ("create_once", "read", "replace_once", "delete_once"):
            if not callable(getattr(store, method, None)):
                raise TypeError("credential secret store is invalid")
        if not callable(random_bytes):
            raise TypeError("random_bytes must be callable")
        self._keys = copied
        self._active_key_id = active_key_id
        self._store = store
        self._now = now or (lambda: datetime.now(UTC))
        self._random_bytes = random_bytes

    @staticmethod
    def _metadata(
        *,
        credential: CredentialHandleRef,
        connection_incarnation_id: str,
        authorization: ConnectedAuthorizationSnapshot,
        external_account_id_hash: str,
        oauth_client_id_sha256: str,
        account_kind: ConnectorAccountKind,
        secret_revision: int,
        created_at: datetime,
        updated_at: datetime,
    ) -> ConnectedCredentialMetadata:
        return ConnectedCredentialMetadata(
            credential=credential,
            connection_incarnation_id=connection_incarnation_id,
            oauth_client_id_sha256=oauth_client_id_sha256,
            account_kind=account_kind,
            authorization_revision=authorization.revision,
            authorization_snapshot_sha256=authorization.snapshot_sha256,
            granted_actions_sha256=authorization.granted_actions_sha256,
            granted_scopes_sha256=authorization.granted_scopes_sha256,
            external_account_id_hash=external_account_id_hash,
            authorization_expires_at=authorization.expires_at,
            secret_revision=secret_revision,
            created_at=created_at,
            updated_at=updated_at,
        )

    @staticmethod
    def _token_binding(metadata: ConnectedCredentialMetadata) -> ProviderOAuthTokenBinding:
        return ProviderOAuthTokenBinding(
            provider=metadata.credential.provider,
            oauth_client_id_sha256=metadata.oauth_client_id_sha256,
            owner_id=metadata.credential.owner_id,
            connection_id=metadata.credential.connection_id,
            connection_incarnation_id=metadata.connection_incarnation_id,
            account_kind=metadata.account_kind,
            credential_handle_sha256=_digest(metadata.credential.handle_id),
            external_account_id_hash=metadata.external_account_id_hash,
        )

    def _encrypt(
        self,
        *,
        metadata: ConnectedCredentialMetadata,
        refresh_token: ProviderOAuthRefreshToken,
        granted_scopes: frozenset[str],
    ) -> EncryptedConnectedCredential:
        if not isinstance(refresh_token, ProviderOAuthRefreshToken):
            raise TypeError("refresh_token must be ProviderOAuthRefreshToken")
        if _scope_hash(granted_scopes) != metadata.granted_scopes_sha256:
            raise ConnectedCredentialVaultError("CREDENTIAL_AUTHORITY_MISMATCH")
        expected_binding = self._token_binding(metadata)
        if refresh_token.binding != expected_binding:
            raise ConnectedCredentialVaultError("CREDENTIAL_AUTHORITY_MISMATCH")
        try:
            refresh_value = refresh_token.require_binding(expected_binding)
            plaintext = json.dumps(
                {
                    "refresh_token": refresh_value,
                },
                ensure_ascii=True,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("ascii")
        except (TypeError, ValueError, UnicodeError):
            raise ConnectedCredentialVaultError("CREDENTIAL_CORRUPT") from None
        if len(plaintext) > _MAX_SECRET_BYTES:
            raise ConnectedCredentialVaultError("CREDENTIAL_CORRUPT")
        data_key = self._random_bytes(_DATA_KEY_BYTES)
        key_nonce = self._random_bytes(_NONCE_BYTES)
        secret_nonce = self._random_bytes(_NONCE_BYTES)
        if (
            type(data_key) is not bytes
            or len(data_key) != _DATA_KEY_BYTES
            or type(key_nonce) is not bytes
            or len(key_nonce) != _NONCE_BYTES
            or type(secret_nonce) is not bytes
            or len(secret_nonce) != _NONCE_BYTES
        ):
            raise ConnectedCredentialVaultError("CREDENTIAL_STORE_FAILED")
        key = self._keys[self._active_key_id]
        aad = metadata.binding_sha256.encode("ascii")
        wrap_aad = b"connected-credential-key-v1\x00" + key.key_id.encode() + b"\x00" + aad
        wrapped_key = AESGCM(key._key).encrypt(key_nonce, data_key, wrap_aad)
        ciphertext = AESGCM(data_key).encrypt(secret_nonce, plaintext, aad)
        partial = object.__new__(EncryptedConnectedCredential)
        object.__setattr__(partial, "metadata", metadata)
        object.__setattr__(partial, "key_id", key.key_id)
        object.__setattr__(partial, "wrapped_key_nonce", _b64(key_nonce))
        object.__setattr__(partial, "wrapped_key_ciphertext", _b64(wrapped_key))
        object.__setattr__(partial, "secret_nonce", _b64(secret_nonce))
        object.__setattr__(partial, "secret_ciphertext", _b64(ciphertext))
        object.__setattr__(partial, "record_binding_sha256", "0" * 64)
        return EncryptedConnectedCredential(
            metadata=metadata,
            key_id=key.key_id,
            wrapped_key_nonce=partial.wrapped_key_nonce,
            wrapped_key_ciphertext=partial.wrapped_key_ciphertext,
            secret_nonce=partial.secret_nonce,
            secret_ciphertext=partial.secret_ciphertext,
            record_binding_sha256=partial.expected_binding_sha256,
        )

    @staticmethod
    def _exact(
        value: object,
        credential: CredentialHandleRef,
    ) -> EncryptedConnectedCredential:
        if not isinstance(value, EncryptedConnectedCredential):
            raise ConnectedCredentialVaultError("CREDENTIAL_CORRUPT")
        bound = value.metadata.credential
        if (
            bound.owner_id != credential.owner_id
            or bound.connection_id != credential.connection_id
            or bound.provider is not credential.provider
            or not hmac.compare_digest(bound.handle_id, credential.handle_id)
        ):
            raise ConnectedCredentialVaultError("CREDENTIAL_AUTHORITY_MISMATCH")
        try:
            expected = value.expected_binding_sha256
        except (TypeError, ValueError):
            raise ConnectedCredentialVaultError("CREDENTIAL_CORRUPT") from None
        if not hmac.compare_digest(value.record_binding_sha256, expected):
            raise ConnectedCredentialVaultError("CREDENTIAL_CORRUPT")
        return value

    @staticmethod
    def _authority_matches(
        *,
        account: ConnectedAccountRef,
        credential: CredentialHandleRef,
        authorization: ConnectedAuthorizationSnapshot,
    ) -> bool:
        return (
            authorization.binds(account)
            and credential.owner_id == account.owner_id
            and credential.connection_id == account.connection_id
            and credential.provider is account.provider
        )

    async def create(
        self,
        *,
        credential: CredentialHandleRef,
        connection_incarnation_id: str,
        authorization: ConnectedAuthorizationSnapshot,
        external_account_id_hash: str,
        oauth_client_id_sha256: str,
        refresh_token: ProviderOAuthRefreshToken,
    ) -> EncryptedConnectedCredential:
        now = _aware(self._now(), "now")
        expected_incarnation = _uuid(
            connection_incarnation_id,
            "connection_incarnation_id",
        )
        expected_oauth_client = _sha(
            oauth_client_id_sha256,
            "oauth_client_id_sha256",
        )
        expected_external_account = _sha(
            external_account_id_hash,
            "external_account_id_hash",
        )
        if not isinstance(refresh_token, ProviderOAuthRefreshToken):
            raise TypeError("refresh_token must be ProviderOAuthRefreshToken")
        token_binding = refresh_token.binding
        expected_handle_sha256 = _digest(credential.handle_id)
        if (
            credential.owner_id != authorization.owner_id
            or credential.connection_id != authorization.connection_id
            or credential.provider is not authorization.provider
            or not authorization.active_at(now)
            or token_binding.provider is not credential.provider
            or token_binding.owner_id != credential.owner_id
            or token_binding.connection_id != credential.connection_id
            or token_binding.connection_incarnation_id != expected_incarnation
            or token_binding.account_kind is not authorization.account_kind
            or token_binding.oauth_client_id_sha256 != expected_oauth_client
            or (
                token_binding.persisted
                and (
                    token_binding.credential_handle_sha256 != expected_handle_sha256
                    or token_binding.external_account_id_hash != expected_external_account
                )
            )
        ):
            raise ConnectedCredentialVaultError("CREDENTIAL_AUTHORITY_MISMATCH")
        metadata = self._metadata(
            credential=credential,
            connection_incarnation_id=expected_incarnation,
            authorization=authorization,
            external_account_id_hash=expected_external_account,
            oauth_client_id_sha256=expected_oauth_client,
            account_kind=token_binding.account_kind,
            secret_revision=1,
            created_at=now,
            updated_at=now,
        )
        persisted_refresh_token = ProviderOAuthRefreshToken(
            refresh_token._reveal(),
            self._token_binding(metadata),
        )
        try:
            existing = await self._store.read(credential)
        except Exception:
            raise ConnectedCredentialVaultError("CREDENTIAL_STORE_FAILED") from None
        if existing is not None:
            stored = self._exact(existing, credential)
            if not hmac.compare_digest(
                stored.metadata.authority_binding_sha256,
                metadata.authority_binding_sha256,
            ):
                raise ConnectedCredentialVaultError("CREDENTIAL_AUTHORITY_MISMATCH")
            return stored
        record = self._encrypt(
            metadata=metadata,
            refresh_token=persisted_refresh_token,
            granted_scopes=authorization.granted_scopes,
        )
        try:
            stored = await self._store.create_once(record)
        except Exception:
            try:
                stored = await self._store.read(credential)
            except Exception:
                stored = None
            if stored is None:
                raise ConnectedCredentialVaultError("CREDENTIAL_STORE_FAILED") from None
        stored = self._exact(stored, credential)
        if not hmac.compare_digest(
            stored.record_binding_sha256,
            record.record_binding_sha256,
        ):
            raise ConnectedCredentialVaultError("CREDENTIAL_STORE_FAILED")
        return stored

    async def open(
        self,
        *,
        account: ConnectedAccountRef,
        credential: CredentialHandleRef,
        connection_incarnation_id: str,
        authorization: ConnectedAuthorizationSnapshot,
    ) -> ConnectedRefreshCredential:
        now = _aware(self._now(), "now")
        expected_incarnation = _uuid(
            connection_incarnation_id,
            "connection_incarnation_id",
        )
        if not self._authority_matches(
            account=account,
            credential=credential,
            authorization=authorization,
        ) or not authorization.active_at(now):
            raise ConnectedCredentialVaultError("CREDENTIAL_AUTHORITY_MISMATCH")
        try:
            stored = await self._store.read(credential)
        except Exception:
            raise ConnectedCredentialVaultError("CREDENTIAL_STORE_FAILED") from None
        if stored is None:
            raise ConnectedCredentialVaultError("CREDENTIAL_NOT_FOUND")
        record = self._exact(stored, credential)
        metadata = record.metadata
        if now >= metadata.authorization_expires_at:
            raise ConnectedCredentialVaultError("CREDENTIAL_EXPIRED")
        if (
            metadata.connection_incarnation_id != expected_incarnation
            or metadata.account_kind is not account.account_kind
            or metadata.authorization_revision != authorization.revision
            or metadata.authorization_snapshot_sha256 != authorization.snapshot_sha256
            or metadata.granted_actions_sha256 != authorization.granted_actions_sha256
            or metadata.granted_scopes_sha256 != authorization.granted_scopes_sha256
            or metadata.external_account_id_hash != account.external_account_id_hash
        ):
            raise ConnectedCredentialVaultError("CREDENTIAL_AUTHORITY_MISMATCH")
        key = self._keys.get(record.key_id)
        if key is None:
            raise ConnectedCredentialVaultError("CREDENTIAL_KEY_UNAVAILABLE")
        try:
            aad = metadata.binding_sha256.encode("ascii")
            wrap_aad = b"connected-credential-key-v1\x00" + key.key_id.encode() + b"\x00" + aad
            data_key = AESGCM(key._key).decrypt(
                _unb64(record.wrapped_key_nonce, "wrapped key nonce", size=12, maximum=12),
                _unb64(
                    record.wrapped_key_ciphertext,
                    "wrapped key ciphertext",
                    size=48,
                    maximum=48,
                ),
                wrap_aad,
            )
            plaintext = AESGCM(data_key).decrypt(
                _unb64(record.secret_nonce, "secret nonce", size=12, maximum=12),
                _unb64(
                    record.secret_ciphertext,
                    "secret ciphertext",
                    maximum=_MAX_SECRET_BYTES + 16,
                ),
                aad,
            )
            decoded = json.loads(
                plaintext.decode("ascii"),
                object_pairs_hook=_unique_object,
                parse_constant=lambda _value: (_ for _ in ()).throw(ValueError()),
            )
            if type(decoded) is not dict or set(decoded) != {"refresh_token"}:
                raise ValueError
            scopes = authorization.granted_scopes
            refresh_token = ProviderOAuthRefreshToken(
                decoded["refresh_token"],
                self._token_binding(metadata),
            )
            if _scope_hash(scopes) != metadata.granted_scopes_sha256:
                raise ValueError
        except (InvalidTag, TypeError, ValueError, UnicodeError, json.JSONDecodeError):
            raise ConnectedCredentialVaultError("CREDENTIAL_CORRUPT") from None
        return ConnectedRefreshCredential(
            record=record,
            refresh_token=refresh_token,
            granted_scopes=scopes,
        )

    async def rotate(
        self,
        current: ConnectedRefreshCredential,
        replacement_token: ProviderOAuthRefreshToken,
        *,
        refresh_coordinator: ConnectedCredentialRefreshCoordinator | None = None,
        refresh_lease: object | None = None,
    ) -> EncryptedConnectedCredential:
        if not isinstance(current, ConnectedRefreshCredential):
            raise TypeError("current must be ConnectedRefreshCredential")
        now = _aware(self._now(), "now")
        if now >= current.record.metadata.authorization_expires_at:
            raise ConnectedCredentialVaultError("CREDENTIAL_EXPIRED")
        metadata = replace(
            current.record.metadata,
            secret_revision=current.record.metadata.secret_revision + 1,
            updated_at=now,
        )
        replacement = self._encrypt(
            metadata=metadata,
            refresh_token=replacement_token,
            granted_scopes=current.granted_scopes,
        )
        if (refresh_coordinator is None) is not (refresh_lease is None):
            raise ConnectedCredentialVaultError("CREDENTIAL_REFRESH_FAILED")
        try:
            if refresh_coordinator is not None:
                stored = await refresh_coordinator.commit_rotation(
                    lease=refresh_lease,
                    record=replacement,
                )
            else:
                stored = await self._store.replace_once(
                    expected_record_binding_sha256=current.record.record_binding_sha256,
                    record=replacement,
                )
        except Exception:
            try:
                stored = await self._store.read(current.record.metadata.credential)
            except Exception:
                stored = None
            if stored is None:
                raise ConnectedCredentialVaultError("CREDENTIAL_STORE_FAILED") from None
        stored = self._exact(stored, current.record.metadata.credential)
        if not hmac.compare_digest(
            stored.record_binding_sha256,
            replacement.record_binding_sha256,
        ):
            raise ConnectedCredentialVaultError("CREDENTIAL_STORE_FAILED")
        return stored

    async def erase(
        self,
        *,
        account: ConnectedAccountRef,
        credential: CredentialHandleRef,
        connection_incarnation_id: str,
    ) -> None:
        expected_incarnation = _uuid(
            connection_incarnation_id,
            "connection_incarnation_id",
        )
        if (
            credential.owner_id != account.owner_id
            or credential.connection_id != account.connection_id
            or credential.provider is not account.provider
        ):
            raise ConnectedCredentialVaultError("CREDENTIAL_AUTHORITY_MISMATCH")
        try:
            stored = await self._store.read(credential)
        except Exception:
            raise ConnectedCredentialVaultError("CREDENTIAL_STORE_FAILED") from None
        if stored is None:
            return
        record = self._exact(stored, credential)
        if (
            record.metadata.connection_incarnation_id != expected_incarnation
            or record.metadata.account_kind is not account.account_kind
            or record.metadata.external_account_id_hash != account.external_account_id_hash
        ):
            raise ConnectedCredentialVaultError("CREDENTIAL_AUTHORITY_MISMATCH")
        try:
            await self._store.delete_once(
                credential=credential,
                expected_record_binding_sha256=record.record_binding_sha256,
            )
        except Exception:
            try:
                remaining = await self._store.read(credential)
            except Exception:
                raise ConnectedCredentialVaultError("CREDENTIAL_STORE_FAILED") from None
            if remaining is None:
                return
            raise ConnectedCredentialVaultError("CREDENTIAL_STORE_FAILED") from None
        try:
            remaining = await self._store.read(credential)
        except Exception:
            raise ConnectedCredentialVaultError("CREDENTIAL_STORE_FAILED") from None
        if remaining is not None:
            raise ConnectedCredentialVaultError("CREDENTIAL_STORE_FAILED")


@dataclass(slots=True)
class _CachedToken:
    provider: ConnectorProvider
    access_token: ProviderOAuthAccessToken = field(repr=False)
    granted_scopes: frozenset[str]
    expires_at: datetime
    record_binding_sha256: str


@dataclass(slots=True)
class _CredentialLock:
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    users: int = 0


class ConnectedAccessTokenBroker:
    """Refresh coordinator with bounded cache and one-use bound facades."""

    def __init__(
        self,
        *,
        vault: ConnectedCredentialVault,
        clients: Mapping[ConnectorProvider, ProviderOAuthHTTPSClient],
        refresh_coordinator: ConnectedCredentialRefreshCoordinator | None = None,
        now: Callable[[], datetime] | None = None,
        max_cache_entries: int = 1024,
    ) -> None:
        if not isinstance(vault, ConnectedCredentialVault):
            raise TypeError("vault must be ConnectedCredentialVault")
        if set(clients) != {ConnectorProvider.GOOGLE, ConnectorProvider.MICROSOFT}:
            raise ValueError("both provider OAuth clients are required")
        if any(not callable(getattr(client, "refresh", None)) for client in clients.values()):
            raise TypeError("provider OAuth client is invalid")
        if refresh_coordinator is not None and (
            not callable(getattr(refresh_coordinator, "claim", None))
            or not callable(getattr(refresh_coordinator, "finish", None))
            or not callable(getattr(refresh_coordinator, "quarantine", None))
            or not callable(getattr(refresh_coordinator, "commit_rotation", None))
        ):
            raise TypeError("credential refresh coordinator is invalid")
        if not 1 <= max_cache_entries <= 4096:
            raise ValueError("max_cache_entries is invalid")
        self._vault = vault
        self._clients = dict(clients)
        self._refresh_coordinator = refresh_coordinator
        self._now = now or (lambda: datetime.now(UTC))
        self._max_cache_entries = max_cache_entries
        self._cache: OrderedDict[str, _CachedToken] = OrderedDict()
        # A local fence is still useful for non-production/test compositions.
        # Production composes the durable coordinator below so this decision
        # survives host loss.
        self._quarantined: set[str] = set()
        self._locks: dict[str, _CredentialLock] = {}
        self._guard = asyncio.Lock()

    def bind(
        self,
        *,
        account: ConnectedAccountRef,
        credential: CredentialHandleRef,
        presented_credential: CredentialHandleRef | None = None,
        connection_incarnation_id: str,
        authorization: ConnectedAuthorizationSnapshot,
        hard_expires_at: datetime,
    ) -> ConnectedAccessTokenSource:
        if not self._vault._authority_matches(
            account=account,
            credential=credential,
            authorization=authorization,
        ):
            raise ConnectedCredentialVaultError("CREDENTIAL_AUTHORITY_MISMATCH")
        return _BoundAccessTokenSource(
            broker=self,
            account=account,
            credential=credential,
            presented_credential=presented_credential or credential,
            connection_incarnation_id=connection_incarnation_id,
            authorization=authorization,
            hard_expires_at=hard_expires_at,
        )

    async def _lock_for(self, key: str) -> _CredentialLock:
        async with self._guard:
            entry = self._locks.get(key)
            if entry is None:
                if len(self._locks) >= self._max_cache_entries:
                    raise ConnectedCredentialVaultError("CREDENTIAL_REFRESH_FAILED")
                entry = _CredentialLock()
                self._locks[key] = entry
            entry.users += 1
            return entry

    async def _release_lock(self, key: str, entry: _CredentialLock) -> None:
        async with self._guard:
            current = self._locks.get(key)
            if current is not entry or entry.users < 1:
                raise ConnectedCredentialVaultError("CREDENTIAL_REFRESH_FAILED")
            entry.users -= 1
            if entry.users == 0:
                self._locks.pop(key, None)

    async def _issue(
        self,
        *,
        account: ConnectedAccountRef,
        credential: CredentialHandleRef,
        presented_credential: CredentialHandleRef | None = None,
        connection_incarnation_id: str,
        authorization: ConnectedAuthorizationSnapshot,
        hard_expires_at: datetime,
    ) -> ConnectedAccessToken:
        # Prove the handle is durable before allocating lock/cache state.
        await self._vault.open(
            account=account,
            credential=credential,
            connection_incarnation_id=connection_incarnation_id,
            authorization=authorization,
        )
        handle_sha256 = _digest(credential.handle_id)
        key = _canonical_hash(
            {
                "owner_id": credential.owner_id,
                "connection_id": credential.connection_id,
                "provider": credential.provider.value,
                "credential_handle_sha256": handle_sha256,
            }
        )
        if key in self._quarantined:
            raise ConnectedCredentialVaultError("CREDENTIAL_QUARANTINED")
        entry = await self._lock_for(key)
        try:
            async with entry.lock:
                now = _aware(self._now(), "now")
                hard_expiry = min(
                    _aware(hard_expires_at, "hard_expires_at"),
                    _aware(authorization.expires_at, "authorization.expires_at"),
                )
                if hard_expiry <= now + timedelta(seconds=15):
                    raise ConnectedCredentialVaultError("CREDENTIAL_EXPIRED")
                current = await self._vault.open(
                    account=account,
                    credential=credential,
                    connection_incarnation_id=connection_incarnation_id,
                    authorization=authorization,
                )
                cached = self._cache.get(key)
                if (
                    cached is not None
                    and cached.provider is credential.provider
                    and cached.access_token.binding == current.refresh_token.binding
                    and cached.record_binding_sha256 == current.record.record_binding_sha256
                    and cached.expires_at > now + _CACHE_MIN_REMAINING
                    and cached.granted_scopes == current.granted_scopes
                ):
                    access_token = cached.access_token
                    token_expires_at = cached.expires_at
                    self._cache.move_to_end(key)
                else:
                    refresh_lease: object | None = None
                    cache_written = False
                    try:
                        if self._refresh_coordinator is not None:
                            refresh_lease = await self._refresh_coordinator.claim(
                                credential=credential,
                                expected_record_binding_sha256=(
                                    current.record.record_binding_sha256
                                ),
                                lease_for=timedelta(seconds=30),
                            )
                            # Another host may have rotated the secret before
                            # this lease was acquired. Always refresh from the
                            # newest exact record under the durable lease.
                            current = await self._vault.open(
                                account=account,
                                credential=credential,
                                connection_incarnation_id=connection_incarnation_id,
                                authorization=authorization,
                            )
                        token_set = await self._clients[credential.provider].refresh(
                            refresh_token=current.refresh_token,
                            expected_scopes=current.granted_scopes,
                            binding=current.refresh_token.binding,
                        )
                        if (
                            not isinstance(token_set, ProviderOAuthTokenSet)
                            or token_set.provider is not credential.provider
                            or token_set.granted_scopes != current.granted_scopes
                            or token_set.refresh_token is None
                            or token_set.access_token.binding != current.refresh_token.binding
                            or token_set.refresh_token.binding != current.refresh_token.binding
                            or token_set.issued_at > now + timedelta(minutes=1)
                            or token_set.expires_at <= now + timedelta(seconds=15)
                        ):
                            raise ConnectedCredentialVaultError("CREDENTIAL_REFRESH_FAILED")
                        if (
                            not hmac.compare_digest(
                                token_set.refresh_token._reveal(),
                                current.refresh_token._reveal(),
                            )
                            or current.record.key_id != self._vault._active_key_id
                        ):
                            rotated = await self._vault.rotate(
                                current,
                                token_set.refresh_token,
                                refresh_coordinator=self._refresh_coordinator,
                                refresh_lease=refresh_lease,
                            )
                            if self._refresh_coordinator is not None:
                                # commit_rotation atomically retired this exact
                                # lease; finally must never issue a second
                                # finish against the permanent replay fence.
                                refresh_lease = None
                            record_binding = rotated.record_binding_sha256
                        else:
                            record_binding = current.record.record_binding_sha256
                        access_token = token_set.access_token
                        token_expires_at = token_set.expires_at
                        self._cache[key] = _CachedToken(
                            provider=token_set.provider,
                            access_token=access_token,
                            granted_scopes=token_set.granted_scopes,
                            expires_at=token_expires_at,
                            record_binding_sha256=record_binding,
                        )
                        cache_written = True
                        self._cache.move_to_end(key)
                        while len(self._cache) > self._max_cache_entries:
                            self._cache.popitem(last=False)
                    except ProviderOAuthEffectUnknown:
                        # A rotating provider may have consumed the old token
                        # even though no usable response arrived. Never release
                        # the lease back into the refresh pool. The quarantine
                        # call is itself exact/idempotent and the local fence is
                        # installed before attempting the durable write.
                        self._cache.pop(key, None)
                        self._quarantined.add(key)
                        if refresh_lease is not None:
                            lease_to_quarantine = refresh_lease
                            refresh_lease = None
                            try:
                                assert self._refresh_coordinator is not None
                                await self._refresh_coordinator.quarantine(lease_to_quarantine)
                            except Exception:
                                raise ConnectedCredentialVaultError(
                                    "CREDENTIAL_REFRESH_FAILED"
                                ) from None
                        raise ConnectedCredentialVaultError("CREDENTIAL_QUARANTINED") from None
                    except ConnectedCredentialVaultError:
                        raise
                    except Exception:
                        raise ConnectedCredentialVaultError("CREDENTIAL_REFRESH_FAILED") from None
                    finally:
                        if refresh_lease is not None:
                            try:
                                assert self._refresh_coordinator is not None
                                await self._refresh_coordinator.finish(refresh_lease)
                            except Exception:
                                if cache_written:
                                    self._cache.pop(key, None)
                                raise ConnectedCredentialVaultError(
                                    "CREDENTIAL_REFRESH_FAILED"
                                ) from None
                    if cache_written is not True:
                        # This is unreachable for a successful refresh, but
                        # makes a future refactor fail closed.
                        if refresh_lease is not None:
                            self._cache.pop(key, None)
                        raise ConnectedCredentialVaultError("CREDENTIAL_REFRESH_FAILED")
                access_expiry = min(
                    token_expires_at,
                    hard_expiry,
                    now + timedelta(hours=2) - timedelta(seconds=1),
                )
                try:
                    presented = presented_credential or credential
                    if (
                        presented.owner_id != credential.owner_id
                        or presented.connection_id != credential.connection_id
                        or presented.provider is not credential.provider
                    ):
                        raise ConnectedCredentialVaultError("CREDENTIAL_AUTHORITY_MISMATCH")
                    return ConnectedAccessToken(
                        owner_id=account.owner_id,
                        connection_id=account.connection_id,
                        provider=account.provider,
                        credential_handle_sha256=_digest(presented.handle_id),
                        expires_at=access_expiry,
                        token=access_token.require_binding(current.refresh_token.binding),
                    )
                except Exception:
                    raise ConnectedCredentialVaultError("CREDENTIAL_REFRESH_FAILED") from None
        finally:
            await self._release_lock(key, entry)


class _BoundAccessTokenSource:
    __slots__ = (
        "_account",
        "_authorization",
        "_broker",
        "_credential",
        "_presented_credential",
        "_connection_incarnation_id",
        "_hard_expires_at",
        "_lock",
        "_used",
    )

    def __init__(
        self,
        *,
        broker: ConnectedAccessTokenBroker,
        account: ConnectedAccountRef,
        credential: CredentialHandleRef,
        presented_credential: CredentialHandleRef,
        connection_incarnation_id: str,
        authorization: ConnectedAuthorizationSnapshot,
        hard_expires_at: datetime,
    ) -> None:
        self._broker = broker
        self._account = account
        self._credential = credential
        if (
            presented_credential.owner_id != credential.owner_id
            or presented_credential.connection_id != credential.connection_id
            or presented_credential.provider is not credential.provider
        ):
            raise ConnectedCredentialVaultError("CREDENTIAL_AUTHORITY_MISMATCH")
        self._presented_credential = presented_credential
        self._connection_incarnation_id = _uuid(
            connection_incarnation_id,
            "connection_incarnation_id",
        )
        self._authorization = authorization
        self._hard_expires_at = _aware(hard_expires_at, "hard_expires_at")
        self._lock = asyncio.Lock()
        self._used = False

    async def issue_access_token(
        self,
        *,
        account: ConnectedAccountRef,
        credential: CredentialHandleRef,
    ) -> ConnectedAccessToken:
        async with self._lock:
            if (
                self._used
                or account != self._account
                or credential != self._presented_credential
            ):
                raise ConnectedCredentialVaultError("CREDENTIAL_AUTHORITY_MISMATCH")
            self._used = True
            return await self._broker._issue(
                account=account,
                credential=self._credential,
                presented_credential=self._presented_credential,
                connection_incarnation_id=self._connection_incarnation_id,
                authorization=self._authorization,
                hard_expires_at=self._hard_expires_at,
            )
