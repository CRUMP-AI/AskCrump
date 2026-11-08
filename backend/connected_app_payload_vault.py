"""Encrypted, owner-bound custody for connected-app action payloads.

The control plane stores only opaque references and content-free hashes.  This
module is the sole boundary that turns an approved mail/calendar payload into
encrypted bytes and later releases it to the exact authorized action.  Key
material is supplied by trusted composition and never crosses public routes.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Callable, Mapping, Protocol
from uuid import UUID

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from backend.connected_app_policy import ConnectorActionKind, ConnectorProvider


_KEY_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_MAX_PLAINTEXT_BYTES = 256 * 1024
_MAX_TTL = timedelta(days=7)
_NONCE_BYTES = 12
_DATA_KEY_BYTES = 32
_VAULT_BINDING_VERSION = "connected-payload-v1"
_COMMITMENT_VERSION = b"connected-payload-commitment-v1\x00"


def _uuid(value: str, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be text")
    try:
        parsed = UUID(value)
    except (ValueError, AttributeError, TypeError):
        raise ValueError(f"{name} must be a canonical UUID") from None
    canonical = str(parsed)
    if value != canonical:
        raise ValueError(f"{name} must be a canonical UUID")
    return canonical


def _aware(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(UTC)


def _sha256(value: str, name: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ValueError(f"{name} must be a lowercase SHA-256 digest")
    return value


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_hash(value: Mapping[str, object]) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return _digest(encoded)


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _unb64(value: str, name: str, *, minimum: int, maximum: int) -> bytes:
    if not isinstance(value, str) or not value or len(value) > maximum * 2:
        raise ValueError(f"{name} is invalid")
    try:
        decoded = base64.b64decode(
            value + "=" * (-len(value) % 4),
            altchars=b"-_",
            validate=True,
        )
    except (ValueError, TypeError):
        raise ValueError(f"{name} is invalid") from None
    if not minimum <= len(decoded) <= maximum or _b64(decoded) != value:
        raise ValueError(f"{name} is invalid")
    return decoded


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _canonical_payload(value: object) -> bytes:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError):
        raise ConnectedPayloadVaultError("PAYLOAD_INVALID") from None
    if not encoded or len(encoded) > _MAX_PLAINTEXT_BYTES:
        raise ConnectedPayloadVaultError("PAYLOAD_TOO_LARGE")
    return encoded


class ConnectedPayloadVaultError(RuntimeError):
    """Content-free payload-vault failure."""

    _ALLOWED = {
        "PAYLOAD_BINDING_MISMATCH",
        "PAYLOAD_CORRUPT",
        "PAYLOAD_ERASED",
        "PAYLOAD_EXPIRED",
        "PAYLOAD_INVALID",
        "PAYLOAD_KEY_UNAVAILABLE",
        "PAYLOAD_NOT_FOUND",
        "PAYLOAD_STORE_FAILED",
        "PAYLOAD_TOO_LARGE",
    }

    def __init__(self, code: str) -> None:
        if code not in self._ALLOWED:
            raise ValueError("invalid payload-vault error code")
        self.code = code
        super().__init__(code)


class ConnectedPayloadMasterKey:
    """Redacted, non-serializable AES-256 wrapping key."""

    __slots__ = ("_key", "key_id")

    def __init__(self, key_id: str, raw_key: bytes) -> None:
        if not isinstance(key_id, str) or not _KEY_ID.fullmatch(key_id):
            raise ValueError("payload master key ID is invalid")
        if type(raw_key) is not bytes or len(raw_key) != 32:
            raise ValueError("payload master key must contain exactly 32 bytes")
        self.key_id = key_id
        self._key = raw_key

    @classmethod
    def from_base64url(cls, key_id: str, encoded: str) -> ConnectedPayloadMasterKey:
        return cls(key_id, _unb64(encoded, "payload master key", minimum=32, maximum=32))

    def __repr__(self) -> str:
        return f"ConnectedPayloadMasterKey(key_id={self.key_id!r}, key='<redacted>')"

    def __getstate__(self) -> None:
        raise TypeError("payload master key cannot be serialized")

    def __reduce_ex__(self, _protocol: int) -> None:
        raise TypeError("payload master key cannot be serialized")


class ConnectedPayloadCommitmentKey:
    """Redacted key for equality-safe payload commitments.

    This key is separate from wrapping keys so a database/reference reader
    cannot run an offline dictionary against predictable recipients, subjects,
    dates, or short message bodies.
    """

    __slots__ = ("_key", "key_id")

    def __init__(self, key_id: str, raw_key: bytes) -> None:
        if not isinstance(key_id, str) or not _KEY_ID.fullmatch(key_id):
            raise ValueError("payload commitment key ID is invalid")
        if type(raw_key) is not bytes or len(raw_key) != 32:
            raise ValueError("payload commitment key must contain exactly 32 bytes")
        self.key_id = key_id
        self._key = raw_key

    @classmethod
    def from_base64url(cls, key_id: str, encoded: str) -> ConnectedPayloadCommitmentKey:
        return cls(key_id, _unb64(encoded, "payload commitment key", minimum=32, maximum=32))

    def __repr__(self) -> str:
        return f"ConnectedPayloadCommitmentKey(key_id={self.key_id!r}, key='<redacted>')"

    def __getstate__(self) -> None:
        raise TypeError("payload commitment key cannot be serialized")

    def __reduce_ex__(self, _protocol: int) -> None:
        raise TypeError("payload commitment key cannot be serialized")


@dataclass(frozen=True, slots=True, repr=False)
class ConnectedPayloadRef:
    payload_id: str
    owner_id: str
    connection_id: str
    action_id: str
    provider: ConnectorProvider
    action: ConnectorActionKind
    commitment_key_id: str
    payload_sha256: str = field(repr=False)
    created_at: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        for name in ("payload_id", "owner_id", "connection_id", "action_id"):
            object.__setattr__(self, name, _uuid(getattr(self, name), name))
        if not isinstance(self.provider, ConnectorProvider):
            raise TypeError("provider must be a ConnectorProvider")
        if not isinstance(self.action, ConnectorActionKind):
            raise TypeError("action must be a ConnectorActionKind")
        if not isinstance(self.commitment_key_id, str) or not _KEY_ID.fullmatch(
            self.commitment_key_id
        ):
            raise ValueError("payload commitment key ID is invalid")
        object.__setattr__(
            self,
            "payload_sha256",
            _sha256(self.payload_sha256, "payload_sha256"),
        )
        created = _aware(self.created_at, "created_at")
        expires = _aware(self.expires_at, "expires_at")
        object.__setattr__(self, "created_at", created)
        object.__setattr__(self, "expires_at", expires)
        if expires <= created or expires - created > _MAX_TTL:
            raise ValueError("payload lifetime must be positive and at most seven days")

    @property
    def identity_sha256(self) -> str:
        """Content-free immutable storage identity, independent of key rotation."""

        return _canonical_hash(
            {
                "version": "connected-payload-identity-v1",
                "payload_id": self.payload_id,
                "owner_id": self.owner_id,
                "connection_id": self.connection_id,
                "action_id": self.action_id,
                "provider": self.provider.value,
                "action": self.action.value,
                "created_at": self.created_at.isoformat(),
                "expires_at": self.expires_at.isoformat(),
            }
        )

    @property
    def binding_sha256(self) -> str:
        return _canonical_hash(
            {
                "version": _VAULT_BINDING_VERSION,
                "payload_id": self.payload_id,
                "owner_id": self.owner_id,
                "connection_id": self.connection_id,
                "action_id": self.action_id,
                "provider": self.provider.value,
                "action": self.action.value,
                "commitment_key_id": self.commitment_key_id,
                "payload_sha256": self.payload_sha256,
                "created_at": self.created_at.isoformat(),
                "expires_at": self.expires_at.isoformat(),
            }
        )

    def __repr__(self) -> str:
        return (
            "ConnectedPayloadRef("
            f"payload_id={self.payload_id!r}, provider={self.provider.value!r}, "
            f"action={self.action.value!r}, content='<redacted>')"
        )


@dataclass(frozen=True, slots=True, repr=False)
class EncryptedConnectedPayload:
    reference: ConnectedPayloadRef
    key_id: str
    wrapped_key_nonce: str = field(repr=False)
    wrapped_key_ciphertext: str = field(repr=False)
    payload_nonce: str = field(repr=False)
    payload_ciphertext: str = field(repr=False)
    record_binding_sha256: str = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.reference, ConnectedPayloadRef):
            raise TypeError("reference must be ConnectedPayloadRef")
        if not isinstance(self.key_id, str) or not _KEY_ID.fullmatch(self.key_id):
            raise ValueError("payload record key ID is invalid")
        _unb64(self.wrapped_key_nonce, "wrapped key nonce", minimum=12, maximum=12)
        _unb64(
            self.wrapped_key_ciphertext,
            "wrapped key ciphertext",
            minimum=48,
            maximum=48,
        )
        _unb64(self.payload_nonce, "payload nonce", minimum=12, maximum=12)
        _unb64(
            self.payload_ciphertext,
            "payload ciphertext",
            minimum=17,
            maximum=_MAX_PLAINTEXT_BYTES + 16,
        )
        object.__setattr__(
            self,
            "record_binding_sha256",
            _sha256(self.record_binding_sha256, "record_binding_sha256"),
        )
        if not hmac.compare_digest(self.record_binding_sha256, self.expected_binding_sha256):
            raise ValueError("payload record binding does not match ciphertext metadata")

    @property
    def expected_binding_sha256(self) -> str:
        return _canonical_hash(
            {
                "version": _VAULT_BINDING_VERSION,
                "reference_binding_sha256": self.reference.binding_sha256,
                "key_id": self.key_id,
                "wrapped_key_nonce_sha256": _digest(
                    _unb64(self.wrapped_key_nonce, "wrapped key nonce", minimum=12, maximum=12)
                ),
                "wrapped_key_ciphertext_sha256": _digest(
                    _unb64(
                        self.wrapped_key_ciphertext,
                        "wrapped key ciphertext",
                        minimum=48,
                        maximum=48,
                    )
                ),
                "payload_nonce_sha256": _digest(
                    _unb64(self.payload_nonce, "payload nonce", minimum=12, maximum=12)
                ),
                "payload_ciphertext_sha256": _digest(
                    _unb64(
                        self.payload_ciphertext,
                        "payload ciphertext",
                        minimum=17,
                        maximum=_MAX_PLAINTEXT_BYTES + 16,
                    )
                ),
            }
        )

    def __repr__(self) -> str:
        return (
            "EncryptedConnectedPayload("
            f"payload_id={self.reference.payload_id!r}, key_id={self.key_id!r}, "
            "ciphertext='<redacted>')"
        )


class ConnectedPayloadStore(Protocol):
    """Durable exact-binding encrypted-record store.

    ``put_once`` and ``delete_once`` share one atomic payload-ID domain and
    compare ``reference.identity_sha256`` before returning or mutating a row.
    A different owner/action/time identity under the same payload ID must fail;
    it may never read, overwrite, erase, or tombstone the existing identity.
    ``delete_once`` installs a durable tombstone even when no record exists;
    that tombstone permanently wins over every later ``put_once`` for the same
    payload identity. ``put_once`` returns ``None`` only when such a tombstone
    already won. A same-identity concurrent/replayed put returns the existing
    encrypted record, not the caller's freshly randomized ciphertext. This
    permits safe replay across commitment-key rotation; the vault decrypts and
    compares the existing semantic payload before accepting that winner.

    This contract is deliberately stronger than a delete/read pair: an erase
    that returns may never be followed by a delayed concurrent seal becoming
    visible.
    """

    async def put_once(
        self, record: EncryptedConnectedPayload
    ) -> EncryptedConnectedPayload | None: ...

    async def read(self, reference: ConnectedPayloadRef) -> EncryptedConnectedPayload | None: ...

    async def delete_once(self, reference: ConnectedPayloadRef) -> bool: ...


class ConnectedPayloadVault:
    """Envelope-encrypted JSON vault with exact owner/action binding."""

    def __init__(
        self,
        *,
        keys: Mapping[str, ConnectedPayloadMasterKey],
        active_key_id: str,
        commitment_keys: Mapping[str, ConnectedPayloadCommitmentKey],
        active_commitment_key_id: str,
        store: ConnectedPayloadStore,
        now: Callable[[], datetime] | None = None,
        random_bytes: Callable[[int], bytes] = secrets.token_bytes,
    ) -> None:
        if not isinstance(keys, Mapping) or not keys:
            raise ValueError("payload vault requires at least one wrapping key")
        copied: dict[str, ConnectedPayloadMasterKey] = {}
        for key_id, key in keys.items():
            if not isinstance(key, ConnectedPayloadMasterKey) or key.key_id != key_id:
                raise ValueError("payload vault key ring is invalid")
            copied[key_id] = key
        if active_key_id not in copied:
            raise ValueError("active payload wrapping key is unavailable")
        if not isinstance(commitment_keys, Mapping) or not commitment_keys:
            raise ValueError("payload vault requires at least one commitment key")
        copied_commitments: dict[str, ConnectedPayloadCommitmentKey] = {}
        for key_id, key in commitment_keys.items():
            if not isinstance(key, ConnectedPayloadCommitmentKey) or key.key_id != key_id:
                raise ValueError("payload commitment key ring is invalid")
            copied_commitments[key_id] = key
        if active_commitment_key_id not in copied_commitments:
            raise ValueError("active payload commitment key is unavailable")
        # Validate the exact operational surface without making the protocol
        # runtime-checkable (which would admit structurally incomplete mocks).
        for method in ("put_once", "read", "delete_once"):
            if not callable(getattr(store, method, None)):
                raise TypeError("payload store is invalid")
        if not callable(random_bytes):
            raise TypeError("random_bytes must be callable")
        self._keys = copied
        self._active_key_id = active_key_id
        self._commitment_keys = copied_commitments
        self._active_commitment_key_id = active_commitment_key_id
        self._store = store
        self._now = now or (lambda: datetime.now(UTC))
        self._random_bytes = random_bytes

    @staticmethod
    def _same_reference(actual: ConnectedPayloadRef, expected: ConnectedPayloadRef) -> bool:
        return hmac.compare_digest(actual.binding_sha256, expected.binding_sha256)

    @staticmethod
    def _record_for(
        *,
        reference: ConnectedPayloadRef,
        key: ConnectedPayloadMasterKey,
        plaintext: bytes,
        random_bytes: Callable[[int], bytes],
    ) -> EncryptedConnectedPayload:
        data_key = random_bytes(_DATA_KEY_BYTES)
        wrap_nonce = random_bytes(_NONCE_BYTES)
        payload_nonce = random_bytes(_NONCE_BYTES)
        if (
            type(data_key) is not bytes
            or type(wrap_nonce) is not bytes
            or type(payload_nonce) is not bytes
            or len(data_key) != _DATA_KEY_BYTES
            or len(wrap_nonce) != _NONCE_BYTES
            or len(payload_nonce) != _NONCE_BYTES
        ):
            raise ConnectedPayloadVaultError("PAYLOAD_STORE_FAILED")
        aad = reference.binding_sha256.encode("ascii")
        payload_ciphertext = AESGCM(data_key).encrypt(payload_nonce, plaintext, aad)
        wrap_aad = b"connected-payload-key-v1\x00" + key.key_id.encode("ascii") + b"\x00" + aad
        wrapped_key = AESGCM(key._key).encrypt(wrap_nonce, data_key, wrap_aad)
        partial = EncryptedConnectedPayload.__new__(EncryptedConnectedPayload)
        object.__setattr__(partial, "reference", reference)
        object.__setattr__(partial, "key_id", key.key_id)
        object.__setattr__(partial, "wrapped_key_nonce", _b64(wrap_nonce))
        object.__setattr__(partial, "wrapped_key_ciphertext", _b64(wrapped_key))
        object.__setattr__(partial, "payload_nonce", _b64(payload_nonce))
        object.__setattr__(partial, "payload_ciphertext", _b64(payload_ciphertext))
        object.__setattr__(partial, "record_binding_sha256", "0" * 64)
        return EncryptedConnectedPayload(
            reference=reference,
            key_id=key.key_id,
            wrapped_key_nonce=partial.wrapped_key_nonce,
            wrapped_key_ciphertext=partial.wrapped_key_ciphertext,
            payload_nonce=partial.payload_nonce,
            payload_ciphertext=partial.payload_ciphertext,
            record_binding_sha256=partial.expected_binding_sha256,
        )

    def _payload_commitment(
        self,
        *,
        owner_id: str,
        connection_id: str,
        action_id: str,
        provider: ConnectorProvider,
        action: ConnectorActionKind,
        commitment_key_id: str,
        plaintext: bytes,
    ) -> str:
        commitment_key = self._commitment_keys.get(commitment_key_id)
        if commitment_key is None:
            raise ConnectedPayloadVaultError("PAYLOAD_KEY_UNAVAILABLE")
        identity = "\x00".join(
            (
                _uuid(owner_id, "owner_id"),
                _uuid(connection_id, "connection_id"),
                _uuid(action_id, "action_id"),
                provider.value,
                action.value,
            )
        ).encode("utf-8")
        return hmac.new(
            commitment_key._key,
            _COMMITMENT_VERSION + identity + b"\x00" + plaintext,
            hashlib.sha256,
        ).hexdigest()

    async def seal_json(
        self,
        *,
        payload_id: str,
        owner_id: str,
        connection_id: str,
        action_id: str,
        provider: ConnectorProvider,
        action: ConnectorActionKind,
        value: object,
        created_at: datetime,
        expires_at: datetime,
    ) -> ConnectedPayloadRef:
        plaintext = _canonical_payload(value)
        reference = ConnectedPayloadRef(
            payload_id=payload_id,
            owner_id=owner_id,
            connection_id=connection_id,
            action_id=action_id,
            provider=provider,
            action=action,
            commitment_key_id=self._active_commitment_key_id,
            payload_sha256=self._payload_commitment(
                owner_id=owner_id,
                connection_id=connection_id,
                action_id=action_id,
                provider=provider,
                action=action,
                commitment_key_id=self._active_commitment_key_id,
                plaintext=plaintext,
            ),
            created_at=created_at,
            expires_at=expires_at,
        )
        reference_now = _aware(self._now(), "now")
        if (
            reference.created_at > reference_now
            or reference.expires_at <= reference_now
            or reference.expires_at - reference_now > _MAX_TTL
        ):
            raise ConnectedPayloadVaultError("PAYLOAD_INVALID")
        record = self._record_for(
            reference=reference,
            key=self._keys[self._active_key_id],
            plaintext=plaintext,
            random_bytes=self._random_bytes,
        )
        try:
            stored = await self._store.put_once(record)
        except Exception:
            try:
                stored = await self._store.read(reference)
            except Exception:
                stored = None
            if stored is None:
                raise ConnectedPayloadVaultError("PAYLOAD_STORE_FAILED") from None
        if stored is None:
            raise ConnectedPayloadVaultError("PAYLOAD_ERASED")
        if not isinstance(stored, EncryptedConnectedPayload):
            raise ConnectedPayloadVaultError("PAYLOAD_CORRUPT")
        if not hmac.compare_digest(stored.reference.identity_sha256, reference.identity_sha256):
            raise ConnectedPayloadVaultError("PAYLOAD_BINDING_MISMATCH")
        self._require_record(stored, stored.reference)
        if not self._same_reference(stored.reference, reference):
            try:
                existing_plaintext = _canonical_payload(await self.open_json(stored.reference))
            except ConnectedPayloadVaultError:
                raise
            if not hmac.compare_digest(existing_plaintext, plaintext):
                raise ConnectedPayloadVaultError("PAYLOAD_BINDING_MISMATCH")
        return stored.reference

    @staticmethod
    def _require_record(
        record: EncryptedConnectedPayload,
        reference: ConnectedPayloadRef,
    ) -> None:
        if not isinstance(record, EncryptedConnectedPayload):
            raise ConnectedPayloadVaultError("PAYLOAD_CORRUPT")
        if not ConnectedPayloadVault._same_reference(record.reference, reference):
            raise ConnectedPayloadVaultError("PAYLOAD_BINDING_MISMATCH")
        try:
            expected = record.expected_binding_sha256
        except (TypeError, ValueError):
            raise ConnectedPayloadVaultError("PAYLOAD_CORRUPT") from None
        if not hmac.compare_digest(record.record_binding_sha256, expected):
            raise ConnectedPayloadVaultError("PAYLOAD_CORRUPT")

    async def open_json(self, reference: ConnectedPayloadRef) -> object:
        if not isinstance(reference, ConnectedPayloadRef):
            raise TypeError("reference must be ConnectedPayloadRef")
        now = _aware(self._now(), "now")
        if now < reference.created_at or now >= reference.expires_at:
            raise ConnectedPayloadVaultError("PAYLOAD_EXPIRED")
        try:
            record = await self._store.read(reference)
        except Exception:
            raise ConnectedPayloadVaultError("PAYLOAD_STORE_FAILED") from None
        if record is None:
            raise ConnectedPayloadVaultError("PAYLOAD_NOT_FOUND")
        self._require_record(record, reference)
        key = self._keys.get(record.key_id)
        if key is None:
            raise ConnectedPayloadVaultError("PAYLOAD_KEY_UNAVAILABLE")
        try:
            aad = reference.binding_sha256.encode("ascii")
            wrap_aad = b"connected-payload-key-v1\x00" + key.key_id.encode("ascii") + b"\x00" + aad
            data_key = AESGCM(key._key).decrypt(
                _unb64(record.wrapped_key_nonce, "wrapped key nonce", minimum=12, maximum=12),
                _unb64(
                    record.wrapped_key_ciphertext,
                    "wrapped key ciphertext",
                    minimum=48,
                    maximum=48,
                ),
                wrap_aad,
            )
            plaintext = AESGCM(data_key).decrypt(
                _unb64(record.payload_nonce, "payload nonce", minimum=12, maximum=12),
                _unb64(
                    record.payload_ciphertext,
                    "payload ciphertext",
                    minimum=17,
                    maximum=_MAX_PLAINTEXT_BYTES + 16,
                ),
                aad,
            )
        except (InvalidTag, TypeError, ValueError):
            raise ConnectedPayloadVaultError("PAYLOAD_CORRUPT") from None
        expected_commitment = self._payload_commitment(
            owner_id=reference.owner_id,
            connection_id=reference.connection_id,
            action_id=reference.action_id,
            provider=reference.provider,
            action=reference.action,
            commitment_key_id=reference.commitment_key_id,
            plaintext=plaintext,
        )
        if len(plaintext) > _MAX_PLAINTEXT_BYTES or not hmac.compare_digest(
            expected_commitment, reference.payload_sha256
        ):
            raise ConnectedPayloadVaultError("PAYLOAD_CORRUPT")
        try:
            return json.loads(
                plaintext.decode("utf-8"),
                object_pairs_hook=_unique_object,
                parse_constant=lambda _value: (_ for _ in ()).throw(ValueError()),
            )
        except (UnicodeError, json.JSONDecodeError, ValueError, RecursionError):
            raise ConnectedPayloadVaultError("PAYLOAD_CORRUPT") from None

    async def erase(self, reference: ConnectedPayloadRef) -> None:
        if not isinstance(reference, ConnectedPayloadRef):
            raise TypeError("reference must be ConnectedPayloadRef")
        try:
            await self._store.delete_once(reference)
            remaining = await self._store.read(reference)
        except Exception:
            raise ConnectedPayloadVaultError("PAYLOAD_STORE_FAILED") from None
        if remaining is not None:
            raise ConnectedPayloadVaultError("PAYLOAD_STORE_FAILED")
