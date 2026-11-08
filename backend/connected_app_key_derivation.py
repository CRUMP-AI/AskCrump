"""Domain-separated connected-operator key material.

Production composition receives one short-lived root data key only from a
separately attested cloud KMS boundary.  This module never loads credentials,
reads environment variables, or calls a network.  It derives a distinct
32-byte key for every connected-operator cryptographic purpose and binds every
derivation to the exact reviewed composition manifest.

The root and derived values are intentionally non-serializable and redacted
from representations.  A caller must re-attest the source and expiry before
using the bundle; this type is key separation, not a substitute for KMS.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
import re
from types import MappingProxyType
from typing import Callable, Mapping

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


_KEY_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_INFO_PREFIX = b"askcrump.connected-operator.key/v1/"


class ConnectedKeyDerivationError(RuntimeError):
    """Content-free key-custody failure."""

    _CODES = frozenset(
        {
            "CONNECTED_KEY_CUSTODY_INVALID",
            "CONNECTED_KEY_CUSTODY_EXPIRED",
        }
    )

    def __init__(self, code: str) -> None:
        self.code = code if code in self._CODES else "CONNECTED_KEY_CUSTODY_INVALID"
        super().__init__(self.code)


class ConnectedKeyCustodyKind(StrEnum):
    """Approved external roots; environment plaintext is deliberately absent."""

    GOOGLE_CLOUD_KMS = "google_cloud_kms"
    AWS_KMS = "aws_kms"
    AZURE_KEY_VAULT = "azure_key_vault"


class ConnectedKeyPurpose(StrEnum):
    HOST_CONFIGURATION = "host_configuration"
    READINESS_ATTESTATION = "readiness_attestation"
    OAUTH_ENVELOPE = "oauth_envelope"
    OAUTH_PERMIT = "oauth_permit"
    OAUTH_CODE_ENVELOPE = "oauth_code_envelope"
    CREDENTIAL_ENVELOPE = "credential_envelope"
    PAYLOAD_ENVELOPE = "payload_envelope"
    PAYLOAD_COMMITMENT = "payload_commitment"
    PLAN_ENVELOPE = "plan_envelope"
    PLAN_COMMITMENT = "plan_commitment"
    PLAN_BINDING = "plan_binding"
    SCHEDULE_ENVELOPE = "schedule_envelope"
    SCHEDULE_COMMITMENT = "schedule_commitment"
    CHAT_BINDING = "chat_binding"
    CHAT_COMPLETION = "chat_completion"
    LOOP_ENVELOPE = "loop_envelope"
    LOOP_COMMITMENT = "loop_commitment"


def _aware(value: object) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ConnectedKeyDerivationError("CONNECTED_KEY_CUSTODY_INVALID")
    return value.astimezone(UTC)


@dataclass(frozen=True, slots=True, repr=False)
class ConnectedRootKeyMaterial:
    """One KMS-unwrapped root data key with a bounded in-process lifetime."""

    key_id: str
    custody: ConnectedKeyCustodyKind
    attestation_sha256: str
    loaded_at: datetime
    expires_at: datetime
    secret: bytes = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if (
            not isinstance(self.key_id, str)
            or len(self.key_id) > 31
            or not _KEY_ID.fullmatch(self.key_id)
        ):
            raise ConnectedKeyDerivationError("CONNECTED_KEY_CUSTODY_INVALID")
        if not isinstance(self.custody, ConnectedKeyCustodyKind):
            raise ConnectedKeyDerivationError("CONNECTED_KEY_CUSTODY_INVALID")
        if (
            not isinstance(self.attestation_sha256, str)
            or not _SHA256.fullmatch(self.attestation_sha256)
        ):
            raise ConnectedKeyDerivationError("CONNECTED_KEY_CUSTODY_INVALID")
        loaded = _aware(self.loaded_at)
        expires = _aware(self.expires_at)
        if expires <= loaded:
            raise ConnectedKeyDerivationError("CONNECTED_KEY_CUSTODY_INVALID")
        if type(self.secret) is not bytes or len(self.secret) != 32:
            raise ConnectedKeyDerivationError("CONNECTED_KEY_CUSTODY_INVALID")
        object.__setattr__(self, "loaded_at", loaded)
        object.__setattr__(self, "expires_at", expires)

    def require_current(self, *, now: datetime) -> None:
        reference = _aware(now)
        if reference < self.loaded_at or reference >= self.expires_at:
            raise ConnectedKeyDerivationError("CONNECTED_KEY_CUSTODY_EXPIRED")

    def __repr__(self) -> str:
        return (
            "ConnectedRootKeyMaterial("
            f"key_id={self.key_id!r}, custody={self.custody.value!r}, secret='<redacted>')"
        )

    def __getstate__(self) -> object:
        raise TypeError("connected root key material cannot be serialized")

    def __reduce__(self) -> object:
        raise TypeError("connected root key material cannot be serialized")


class ConnectedDerivedKeyset:
    """Exact, manifest-bound domain keys derived from one current KMS root."""

    __slots__ = (
        "_keys",
        "_root",
        "composition_manifest_sha256",
    )

    def __init__(
        self,
        *,
        root: ConnectedRootKeyMaterial,
        composition_manifest_sha256: str,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if type(root) is not ConnectedRootKeyMaterial or not callable(now):
            raise ConnectedKeyDerivationError("CONNECTED_KEY_CUSTODY_INVALID")
        if (
            not isinstance(composition_manifest_sha256, str)
            or not _SHA256.fullmatch(composition_manifest_sha256)
        ):
            raise ConnectedKeyDerivationError("CONNECTED_KEY_CUSTODY_INVALID")
        root.require_current(now=now())
        salt = bytes.fromhex(composition_manifest_sha256)
        keys: dict[ConnectedKeyPurpose, bytes] = {}
        for purpose in ConnectedKeyPurpose:
            keys[purpose] = HKDF(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                info=_INFO_PREFIX + purpose.value.encode("ascii"),
            ).derive(root.secret)
        if (
            len(set(keys.values())) != len(ConnectedKeyPurpose)
            or root.secret in keys.values()
        ):
            raise ConnectedKeyDerivationError("CONNECTED_KEY_CUSTODY_INVALID")
        self._root = root
        self._keys: Mapping[ConnectedKeyPurpose, bytes] = MappingProxyType(keys)
        self.composition_manifest_sha256 = composition_manifest_sha256

    @property
    def custody(self) -> ConnectedKeyCustodyKind:
        return self._root.custody

    @property
    def root_key_id(self) -> str:
        return self._root.key_id

    @property
    def attestation_sha256(self) -> str:
        return self._root.attestation_sha256

    @property
    def expires_at(self) -> datetime:
        return self._root.expires_at

    def require_current(self, *, now: datetime) -> None:
        self._root.require_current(now=now)

    def key(self, purpose: ConnectedKeyPurpose) -> bytes:
        if not isinstance(purpose, ConnectedKeyPurpose):
            raise ConnectedKeyDerivationError("CONNECTED_KEY_CUSTODY_INVALID")
        return self._keys[purpose]

    def key_id(self, purpose: ConnectedKeyPurpose) -> str:
        if not isinstance(purpose, ConnectedKeyPurpose):
            raise ConnectedKeyDerivationError("CONNECTED_KEY_CUSTODY_INVALID")
        digest = self.composition_manifest_sha256[:10]
        # Purpose values are short enough to retain a human-auditable domain
        # while meeting every existing connected-vault 64-character key limit.
        value = f"{self.root_key_id}.{purpose.value}.{digest}"
        if len(value) > 64 or not _KEY_ID.fullmatch(value):
            raise ConnectedKeyDerivationError("CONNECTED_KEY_CUSTODY_INVALID")
        return value

    def __repr__(self) -> str:
        return (
            "ConnectedDerivedKeyset("
            f"custody={self.custody.value!r}, key_count={len(self._keys)}, keys='<redacted>')"
        )

    def __getstate__(self) -> object:
        raise TypeError("connected derived keyset cannot be serialized")

    def __reduce__(self) -> object:
        raise TypeError("connected derived keyset cannot be serialized")


__all__ = [
    "ConnectedDerivedKeyset",
    "ConnectedKeyCustodyKind",
    "ConnectedKeyDerivationError",
    "ConnectedKeyPurpose",
    "ConnectedRootKeyMaterial",
]
