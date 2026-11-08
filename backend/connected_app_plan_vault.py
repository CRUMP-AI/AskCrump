"""Encrypted, turn-bound custody for one connected-operator proposal.

Planner output can contain recipients, subjects, event details, and other
customer content.  The durable control plane receives only opaque references
and keyed commitments; the exact model response is envelope-encrypted here.
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
from typing import Mapping, Protocol
from uuid import UUID

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


_KEY_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MAX_PLAINTEXT_BYTES = 64 * 1024
_MAX_TTL = timedelta(minutes=30)
_COMMITMENT_VERSION = b"connected-plan-output-commitment-v1\x00"


class ConnectedPlanVaultError(RuntimeError):
    """Content-free encrypted-plan failure."""

    _ALLOWED = frozenset(
        {
            "CONNECTED_PLAN_VAULT_BINDING_MISMATCH",
            "CONNECTED_PLAN_VAULT_CORRUPT",
            "CONNECTED_PLAN_VAULT_ERASED",
            "CONNECTED_PLAN_VAULT_EXPIRED",
            "CONNECTED_PLAN_VAULT_INVALID",
            "CONNECTED_PLAN_VAULT_KEY_UNAVAILABLE",
            "CONNECTED_PLAN_VAULT_NOT_FOUND",
            "CONNECTED_PLAN_VAULT_STORE_FAILED",
            "CONNECTED_PLAN_VAULT_TOO_LARGE",
        }
    )

    def __init__(self, code: str) -> None:
        if code not in self._ALLOWED:
            raise ValueError("invalid connected plan-vault error")
        self.code = code
        super().__init__(code)


def _uuid(value: object) -> str:
    if not isinstance(value, str):
        raise ConnectedPlanVaultError("CONNECTED_PLAN_VAULT_INVALID")
    try:
        canonical = str(UUID(value))
    except (TypeError, ValueError, AttributeError):
        raise ConnectedPlanVaultError("CONNECTED_PLAN_VAULT_INVALID") from None
    if canonical != value:
        raise ConnectedPlanVaultError("CONNECTED_PLAN_VAULT_INVALID")
    return value


def _sha(value: object) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ConnectedPlanVaultError("CONNECTED_PLAN_VAULT_INVALID")
    return value


def _key_id(value: object) -> str:
    if not isinstance(value, str) or not _KEY_ID.fullmatch(value):
        raise ConnectedPlanVaultError("CONNECTED_PLAN_VAULT_INVALID")
    return value


def _aware(value: object) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ConnectedPlanVaultError("CONNECTED_PLAN_VAULT_INVALID")
    return value.astimezone(UTC)


def _canonical(value: object) -> bytes:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError):
        raise ConnectedPlanVaultError("CONNECTED_PLAN_VAULT_INVALID") from None
    if not encoded:
        raise ConnectedPlanVaultError("CONNECTED_PLAN_VAULT_INVALID")
    if len(encoded) > _MAX_PLAINTEXT_BYTES:
        raise ConnectedPlanVaultError("CONNECTED_PLAN_VAULT_TOO_LARGE")
    return encoded


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _unb64(value: object, *, minimum: int, maximum: int) -> bytes:
    if not isinstance(value, str) or not value or len(value) > maximum * 2:
        raise ConnectedPlanVaultError("CONNECTED_PLAN_VAULT_CORRUPT")
    try:
        decoded = base64.b64decode(
            value + "=" * (-len(value) % 4),
            altchars=b"-_",
            validate=True,
        )
    except (TypeError, ValueError):
        raise ConnectedPlanVaultError("CONNECTED_PLAN_VAULT_CORRUPT") from None
    if not minimum <= len(decoded) <= maximum or _b64(decoded) != value:
        raise ConnectedPlanVaultError("CONNECTED_PLAN_VAULT_CORRUPT")
    return decoded


class ConnectedPlanMasterKey:
    """Dedicated AES-256 wrapping key; never serialized or logged."""

    __slots__ = ("_key", "key_id")

    def __init__(self, key_id: str, raw_key: bytes) -> None:
        self.key_id = _key_id(key_id)
        if type(raw_key) is not bytes or len(raw_key) != 32:
            raise ConnectedPlanVaultError("CONNECTED_PLAN_VAULT_INVALID")
        self._key = raw_key

    def __repr__(self) -> str:
        return f"ConnectedPlanMasterKey(key_id={self.key_id!r}, key='<redacted>')"

    def __reduce_ex__(self, _protocol: int):
        raise TypeError("connected plan key cannot be serialized")


class ConnectedPlanCommitmentKey:
    """Separate HMAC key preventing offline guesses of proposal content."""

    __slots__ = ("_key", "key_id")

    def __init__(self, key_id: str, raw_key: bytes) -> None:
        self.key_id = _key_id(key_id)
        if type(raw_key) is not bytes or len(raw_key) != 32:
            raise ConnectedPlanVaultError("CONNECTED_PLAN_VAULT_INVALID")
        self._key = raw_key

    def __repr__(self) -> str:
        return f"ConnectedPlanCommitmentKey(key_id={self.key_id!r}, key='<redacted>')"

    def __reduce_ex__(self, _protocol: int):
        raise TypeError("connected plan commitment key cannot be serialized")


@dataclass(frozen=True, slots=True, repr=False)
class ConnectedPlanEnvelopeRef:
    payload_id: str
    owner_id: str
    turn_id: str
    planning_id: str
    planning_binding_sha256: str = field(repr=False)
    commitment_key_id: str
    payload_sha256: str = field(repr=False)
    created_at: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        for name in ("payload_id", "owner_id", "turn_id", "planning_id"):
            object.__setattr__(self, name, _uuid(getattr(self, name)))
        object.__setattr__(self, "planning_binding_sha256", _sha(self.planning_binding_sha256))
        object.__setattr__(self, "commitment_key_id", _key_id(self.commitment_key_id))
        object.__setattr__(self, "payload_sha256", _sha(self.payload_sha256))
        created_at = _aware(self.created_at)
        expires_at = _aware(self.expires_at)
        if expires_at <= created_at or expires_at - created_at > _MAX_TTL:
            raise ConnectedPlanVaultError("CONNECTED_PLAN_VAULT_INVALID")
        object.__setattr__(self, "created_at", created_at)
        object.__setattr__(self, "expires_at", expires_at)

    @property
    def binding_sha256(self) -> str:
        return hashlib.sha256(
            _canonical(
                {
                    "version": "connected-plan-reference-v1",
                    "payloadId": self.payload_id,
                    "ownerId": self.owner_id,
                    "turnId": self.turn_id,
                    "planningId": self.planning_id,
                    "planningBindingSha256": self.planning_binding_sha256,
                    "commitmentKeyId": self.commitment_key_id,
                    "payloadSha256": self.payload_sha256,
                    "createdAt": self.created_at.isoformat(),
                    "expiresAt": self.expires_at.isoformat(),
                }
            )
        ).hexdigest()

    def __repr__(self) -> str:
        return (
            "ConnectedPlanEnvelopeRef("
            f"payload_id={self.payload_id!r}, planning_id={self.planning_id!r}, "
            "content='<encrypted>')"
        )


@dataclass(frozen=True, slots=True, repr=False)
class EncryptedConnectedPlanEnvelope:
    reference: ConnectedPlanEnvelopeRef
    key_id: str
    wrapped_key_nonce: str = field(repr=False)
    wrapped_key_ciphertext: str = field(repr=False)
    payload_nonce: str = field(repr=False)
    payload_ciphertext: str = field(repr=False)
    record_binding_sha256: str = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.reference, ConnectedPlanEnvelopeRef):
            raise ConnectedPlanVaultError("CONNECTED_PLAN_VAULT_INVALID")
        object.__setattr__(self, "key_id", _key_id(self.key_id))
        _unb64(self.wrapped_key_nonce, minimum=12, maximum=12)
        _unb64(self.wrapped_key_ciphertext, minimum=48, maximum=80)
        _unb64(self.payload_nonce, minimum=12, maximum=12)
        _unb64(self.payload_ciphertext, minimum=17, maximum=_MAX_PLAINTEXT_BYTES + 16)
        object.__setattr__(self, "record_binding_sha256", _sha(self.record_binding_sha256))
        if not hmac.compare_digest(self.record_binding_sha256, self.expected_binding_sha256):
            raise ConnectedPlanVaultError("CONNECTED_PLAN_VAULT_BINDING_MISMATCH")

    @property
    def expected_binding_sha256(self) -> str:
        return hashlib.sha256(
            _canonical(
                {
                    "version": "connected-plan-record-v1",
                    "referenceBindingSha256": self.reference.binding_sha256,
                    "keyId": self.key_id,
                    "wrappedKeyNonce": self.wrapped_key_nonce,
                    "wrappedKeyCiphertext": self.wrapped_key_ciphertext,
                    "payloadNonce": self.payload_nonce,
                    "payloadCiphertext": self.payload_ciphertext,
                }
            )
        ).hexdigest()

    def __repr__(self) -> str:
        return (
            "EncryptedConnectedPlanEnvelope("
            f"payload_id={self.reference.payload_id!r}, content='<encrypted>')"
        )


class ConnectedPlanEnvelopeStore(Protocol):
    async def put_once(
        self, record: EncryptedConnectedPlanEnvelope
    ) -> EncryptedConnectedPlanEnvelope | None: ...

    async def read_exact(
        self,
        *,
        owner_id: str,
        turn_id: str,
        planning_id: str,
        planning_binding_sha256: str,
        payload_id: str,
    ) -> EncryptedConnectedPlanEnvelope | None: ...

    async def delete_once(
        self,
        *,
        owner_id: str,
        turn_id: str,
        planning_id: str,
        planning_binding_sha256: str,
        payload_id: str,
    ) -> bool: ...


class ConnectedPlanEnvelopeVault:
    """Envelope encryption with deterministic identity and permanent erasure."""

    def __init__(
        self,
        *,
        store: ConnectedPlanEnvelopeStore,
        master_keys: Mapping[str, ConnectedPlanMasterKey],
        active_master_key_id: str,
        commitment_keys: Mapping[str, ConnectedPlanCommitmentKey],
        active_commitment_key_id: str,
    ) -> None:
        if any(
            not callable(getattr(store, method, None))
            for method in ("put_once", "read_exact", "delete_once")
        ):
            raise TypeError("connected plan store is invalid")
        self._store = store
        self._master_keys = dict(master_keys)
        self._commitment_keys = dict(commitment_keys)
        self._active_master_key_id = _key_id(active_master_key_id)
        self._active_commitment_key_id = _key_id(active_commitment_key_id)
        if self._active_master_key_id not in self._master_keys:
            raise ConnectedPlanVaultError("CONNECTED_PLAN_VAULT_KEY_UNAVAILABLE")
        if self._active_commitment_key_id not in self._commitment_keys:
            raise ConnectedPlanVaultError("CONNECTED_PLAN_VAULT_KEY_UNAVAILABLE")
        if any(item != key.key_id for item, key in self._master_keys.items()):
            raise ConnectedPlanVaultError("CONNECTED_PLAN_VAULT_INVALID")
        if any(item != key.key_id for item, key in self._commitment_keys.items()):
            raise ConnectedPlanVaultError("CONNECTED_PLAN_VAULT_INVALID")

    @staticmethod
    def _payload_aad(reference: ConnectedPlanEnvelopeRef) -> bytes:
        return _canonical(
            {
                "version": "connected-plan-payload-aad-v1",
                "referenceBindingSha256": reference.binding_sha256,
            }
        )

    @staticmethod
    def _wrap_aad(reference: ConnectedPlanEnvelopeRef, key_id: str) -> bytes:
        return _canonical(
            {
                "version": "connected-plan-wrap-aad-v1",
                "referenceBindingSha256": reference.binding_sha256,
                "keyId": key_id,
            }
        )

    @staticmethod
    def _commitment(
        key: ConnectedPlanCommitmentKey,
        *,
        payload_id: str,
        owner_id: str,
        turn_id: str,
        planning_id: str,
        planning_binding_sha256: str,
        plaintext: bytes,
    ) -> str:
        return hmac.new(
            key._key,
            _COMMITMENT_VERSION
            + _canonical(
                {
                    "payloadId": payload_id,
                    "ownerId": owner_id,
                    "turnId": turn_id,
                    "planningId": planning_id,
                    "planningBindingSha256": planning_binding_sha256,
                }
            )
            + b"\x00"
            + plaintext,
            hashlib.sha256,
        ).hexdigest()

    def _encrypt(
        self,
        reference: ConnectedPlanEnvelopeRef,
        plaintext: bytes,
    ) -> EncryptedConnectedPlanEnvelope:
        key = self._master_keys[self._active_master_key_id]
        data_key = secrets.token_bytes(32)
        payload_nonce = secrets.token_bytes(12)
        wrap_nonce = secrets.token_bytes(12)
        payload_ciphertext = AESGCM(data_key).encrypt(
            payload_nonce,
            plaintext,
            self._payload_aad(reference),
        )
        wrapped_key = AESGCM(key._key).encrypt(
            wrap_nonce,
            data_key,
            self._wrap_aad(reference, key.key_id),
        )
        values = {
            "reference": reference,
            "key_id": key.key_id,
            "wrapped_key_nonce": _b64(wrap_nonce),
            "wrapped_key_ciphertext": _b64(wrapped_key),
            "payload_nonce": _b64(payload_nonce),
            "payload_ciphertext": _b64(payload_ciphertext),
        }
        binding = hashlib.sha256(
            _canonical(
                {
                    "version": "connected-plan-record-v1",
                    "referenceBindingSha256": reference.binding_sha256,
                    "keyId": values["key_id"],
                    "wrappedKeyNonce": values["wrapped_key_nonce"],
                    "wrappedKeyCiphertext": values["wrapped_key_ciphertext"],
                    "payloadNonce": values["payload_nonce"],
                    "payloadCiphertext": values["payload_ciphertext"],
                }
            )
        ).hexdigest()
        return EncryptedConnectedPlanEnvelope(
            **values,
            record_binding_sha256=binding,
        )

    def _decrypt(self, record: EncryptedConnectedPlanEnvelope) -> bytes:
        master_key = self._master_keys.get(record.key_id)
        commitment_key = self._commitment_keys.get(record.reference.commitment_key_id)
        if master_key is None or commitment_key is None:
            raise ConnectedPlanVaultError("CONNECTED_PLAN_VAULT_KEY_UNAVAILABLE")
        try:
            data_key = AESGCM(master_key._key).decrypt(
                _unb64(record.wrapped_key_nonce, minimum=12, maximum=12),
                _unb64(record.wrapped_key_ciphertext, minimum=48, maximum=80),
                self._wrap_aad(record.reference, record.key_id),
            )
            plaintext = AESGCM(data_key).decrypt(
                _unb64(record.payload_nonce, minimum=12, maximum=12),
                _unb64(
                    record.payload_ciphertext,
                    minimum=17,
                    maximum=_MAX_PLAINTEXT_BYTES + 16,
                ),
                self._payload_aad(record.reference),
            )
        except (InvalidTag, ValueError):
            raise ConnectedPlanVaultError("CONNECTED_PLAN_VAULT_CORRUPT") from None
        expected = self._commitment(
            commitment_key,
            payload_id=record.reference.payload_id,
            owner_id=record.reference.owner_id,
            turn_id=record.reference.turn_id,
            planning_id=record.reference.planning_id,
            planning_binding_sha256=record.reference.planning_binding_sha256,
            plaintext=plaintext,
        )
        if not hmac.compare_digest(expected, record.reference.payload_sha256):
            raise ConnectedPlanVaultError("CONNECTED_PLAN_VAULT_CORRUPT")
        return plaintext

    async def seal_json(
        self,
        *,
        payload_id: str,
        owner_id: str,
        turn_id: str,
        planning_id: str,
        planning_binding_sha256: str,
        value: object,
        created_at: datetime,
        expires_at: datetime,
    ) -> ConnectedPlanEnvelopeRef:
        plaintext = _canonical(value)
        commitment_key = self._commitment_keys[self._active_commitment_key_id]
        reference = ConnectedPlanEnvelopeRef(
            payload_id=_uuid(payload_id),
            owner_id=_uuid(owner_id),
            turn_id=_uuid(turn_id),
            planning_id=_uuid(planning_id),
            planning_binding_sha256=_sha(planning_binding_sha256),
            commitment_key_id=commitment_key.key_id,
            payload_sha256=self._commitment(
                commitment_key,
                payload_id=payload_id,
                owner_id=owner_id,
                turn_id=turn_id,
                planning_id=planning_id,
                planning_binding_sha256=planning_binding_sha256,
                plaintext=plaintext,
            ),
            created_at=_aware(created_at),
            expires_at=_aware(expires_at),
        )
        candidate = self._encrypt(reference, plaintext)
        try:
            stored = await self._store.put_once(candidate)
        except Exception:
            raise ConnectedPlanVaultError("CONNECTED_PLAN_VAULT_STORE_FAILED") from None
        if stored is None:
            raise ConnectedPlanVaultError("CONNECTED_PLAN_VAULT_ERASED")
        opened = self._decrypt(stored)
        if (
            stored.reference.payload_id != reference.payload_id
            or stored.reference.owner_id != reference.owner_id
            or stored.reference.turn_id != reference.turn_id
            or stored.reference.planning_id != reference.planning_id
            or not hmac.compare_digest(
                stored.reference.planning_binding_sha256,
                reference.planning_binding_sha256,
            )
            or opened != plaintext
        ):
            raise ConnectedPlanVaultError("CONNECTED_PLAN_VAULT_BINDING_MISMATCH")
        return stored.reference

    async def open_json(
        self,
        *,
        owner_id: str,
        turn_id: str,
        planning_id: str,
        planning_binding_sha256: str,
        payload_id: str,
        now: datetime,
    ) -> tuple[ConnectedPlanEnvelopeRef, object]:
        try:
            record = await self._store.read_exact(
                owner_id=_uuid(owner_id),
                turn_id=_uuid(turn_id),
                planning_id=_uuid(planning_id),
                planning_binding_sha256=_sha(planning_binding_sha256),
                payload_id=_uuid(payload_id),
            )
        except ConnectedPlanVaultError:
            raise
        except Exception:
            raise ConnectedPlanVaultError("CONNECTED_PLAN_VAULT_STORE_FAILED") from None
        if record is None:
            raise ConnectedPlanVaultError("CONNECTED_PLAN_VAULT_NOT_FOUND")
        reference = record.reference
        if (
            reference.owner_id != owner_id
            or reference.turn_id != turn_id
            or reference.planning_id != planning_id
            or reference.payload_id != payload_id
            or not hmac.compare_digest(
                reference.planning_binding_sha256,
                planning_binding_sha256,
            )
        ):
            raise ConnectedPlanVaultError("CONNECTED_PLAN_VAULT_BINDING_MISMATCH")
        if reference.expires_at <= _aware(now):
            raise ConnectedPlanVaultError("CONNECTED_PLAN_VAULT_EXPIRED")
        plaintext = self._decrypt(record)
        try:
            return reference, json.loads(plaintext.decode("utf-8"))
        except (UnicodeError, ValueError, json.JSONDecodeError, RecursionError):
            raise ConnectedPlanVaultError("CONNECTED_PLAN_VAULT_CORRUPT") from None

    async def erase(
        self,
        *,
        owner_id: str,
        turn_id: str,
        planning_id: str,
        planning_binding_sha256: str,
        payload_id: str,
    ) -> bool:
        try:
            return bool(
                await self._store.delete_once(
                    owner_id=_uuid(owner_id),
                    turn_id=_uuid(turn_id),
                    planning_id=_uuid(planning_id),
                    planning_binding_sha256=_sha(planning_binding_sha256),
                    payload_id=_uuid(payload_id),
                )
            )
        except Exception:
            raise ConnectedPlanVaultError("CONNECTED_PLAN_VAULT_STORE_FAILED") from None

    def __repr__(self) -> str:
        return "ConnectedPlanEnvelopeVault(keys='<redacted>')"
