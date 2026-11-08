"""KMS-bound, content-free provider-smoke readiness receipts.

The database issues a one-use challenge for one immutable deployment tuple.
Only a process that has unwrapped the reviewed KMS root can derive this
separate key and attest the tuple after the bounded Google and Microsoft smoke
ceremony.  The database never receives the key.  Later hosts can verify the
durable HMAC receipt while issuing only a short-lived runtime readiness lease;
ordinary graph renewal therefore never needs to touch a user's providers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
import hashlib
import hmac
import json
import re
from uuid import UUID


_KEY_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
_ROOT_KEY_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,30}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_FINGERPRINT = re.compile(r"^[0-9a-f]{32}$")
_DEPLOYMENT = re.compile(r"^dpl_[A-Za-z0-9]{8,}$")
_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_VERSION = "askcrump-connected-provider-smoke-v1"
_HMAC_PREFIX = b"askcrump.connected-provider-smoke/v1\0"


class ConnectedReadinessAttestationError(RuntimeError):
    """Content-free attestation failure safe for request quarantine."""

    def __init__(self) -> None:
        self.code = "CONNECTED_READINESS_ATTESTATION_INVALID"
        super().__init__(self.code)


def _aware(value: object) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ConnectedReadinessAttestationError()
    return value.astimezone(UTC)


def _uuid(value: object) -> str:
    if not isinstance(value, str):
        raise ConnectedReadinessAttestationError()
    try:
        canonical = str(UUID(value))
    except (TypeError, ValueError, AttributeError):
        raise ConnectedReadinessAttestationError() from None
    if canonical != value:
        raise ConnectedReadinessAttestationError()
    return canonical


@dataclass(frozen=True, slots=True, repr=False)
class ConnectedReadinessAttestationKey:
    """One manifest-bound key used only for provider-smoke receipts."""

    key_id: str
    secret: bytes = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if (
            not isinstance(self.key_id, str)
            or not _KEY_ID.fullmatch(self.key_id)
            or type(self.secret) is not bytes
            or len(self.secret) != 32
        ):
            raise ConnectedReadinessAttestationError()

    def __repr__(self) -> str:
        return (
            "ConnectedReadinessAttestationKey("
            f"key_id={self.key_id!r}, secret='<redacted>')"
        )

    def __getstate__(self) -> object:
        raise TypeError("connected readiness-attestation keys cannot be serialized")

    def __reduce__(self) -> object:
        raise TypeError("connected readiness-attestation keys cannot be serialized")


@dataclass(frozen=True, slots=True)
class ConnectedProviderSmokeDeployment:
    """Exact nonsecret tuple that requires a fresh two-provider smoke."""

    composition_manifest_sha256: str
    database_contract_sha256: str
    database_target_fingerprint: str
    provider_contract_sha256: str
    deployment_id: str
    commit_sha: str
    host_configuration_ciphertext_sha256: str
    root_key_id: str
    release_preview_contract_sha256: str
    release_preview_descriptor_matrix_sha256: str
    release_preview_dedicated_account_attestation_sha256: str
    release_preview_invocation_id: str
    release_preview_effect_manifest_sha256: str

    def __post_init__(self) -> None:
        if (
            not _SHA256.fullmatch(str(self.composition_manifest_sha256 or ""))
            or not _SHA256.fullmatch(str(self.database_contract_sha256 or ""))
            or not _FINGERPRINT.fullmatch(str(self.database_target_fingerprint or ""))
            or not _SHA256.fullmatch(str(self.provider_contract_sha256 or ""))
            or not _DEPLOYMENT.fullmatch(str(self.deployment_id or ""))
            or not _COMMIT.fullmatch(str(self.commit_sha or ""))
            or not _SHA256.fullmatch(
                str(self.host_configuration_ciphertext_sha256 or "")
            )
            or not _ROOT_KEY_ID.fullmatch(str(self.root_key_id or ""))
            or not _SHA256.fullmatch(
                str(self.release_preview_contract_sha256 or "")
            )
            or not _SHA256.fullmatch(
                str(self.release_preview_descriptor_matrix_sha256 or "")
            )
            or not _SHA256.fullmatch(
                str(
                    self.release_preview_dedicated_account_attestation_sha256
                    or ""
                )
            )
            or _uuid(self.release_preview_invocation_id)
            != self.release_preview_invocation_id
            or not _SHA256.fullmatch(
                str(self.release_preview_effect_manifest_sha256 or "")
            )
        ):
            raise ConnectedReadinessAttestationError()


@dataclass(frozen=True, slots=True)
class ConnectedProviderSmokeChallenge:
    """One DB-issued, one-use challenge for the exact deployment tuple."""

    deployment: ConnectedProviderSmokeDeployment
    challenge_id: str
    issued_at: datetime

    def __post_init__(self) -> None:
        if type(self.deployment) is not ConnectedProviderSmokeDeployment:
            raise ConnectedReadinessAttestationError()
        object.__setattr__(self, "challenge_id", _uuid(self.challenge_id))
        object.__setattr__(self, "issued_at", _aware(self.issued_at))

    def canonical_bytes(self) -> bytes:
        deployment = self.deployment
        value = {
            "challenge_id": self.challenge_id,
            "challenge_issued_at": self.issued_at.isoformat().replace("+00:00", "Z"),
            "commit_sha": deployment.commit_sha,
            "composition_manifest_sha256": deployment.composition_manifest_sha256,
            "database_contract_sha256": deployment.database_contract_sha256,
            "database_target_fingerprint": deployment.database_target_fingerprint,
            "deployment_id": deployment.deployment_id,
            "host_configuration_ciphertext_sha256": (
                deployment.host_configuration_ciphertext_sha256
            ),
            "provider_contract_sha256": deployment.provider_contract_sha256,
            "release_preview_contract_sha256": (
                deployment.release_preview_contract_sha256
            ),
            "release_preview_dedicated_account_attestation_sha256": (
                deployment.release_preview_dedicated_account_attestation_sha256
            ),
            "release_preview_descriptor_matrix_sha256": (
                deployment.release_preview_descriptor_matrix_sha256
            ),
            "release_preview_effect_manifest_sha256": (
                deployment.release_preview_effect_manifest_sha256
            ),
            "release_preview_invocation_id": (
                deployment.release_preview_invocation_id
            ),
            "providers": ["google", "microsoft"],
            "planning_gateway": {
                "authentication": "current_vercel_request_oidc",
                "model": "openai/gpt-oss-20b",
                "provider": "groq",
                "retention": "zero_data_retention_and_no_prompt_training",
            },
            "resources": ["mail", "calendar"],
            "root_key_id": deployment.root_key_id,
            "version": _VERSION,
        }
        return _HMAC_PREFIX + json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")


class ConnectedProviderSmokeAttestor:
    """Create or verify a receipt without exposing the derived HMAC key."""

    __slots__ = ("_key",)

    def __init__(self, key: ConnectedReadinessAttestationKey) -> None:
        if type(key) is not ConnectedReadinessAttestationKey:
            raise ConnectedReadinessAttestationError()
        self._key = key

    def _matches_deployment(self, challenge: ConnectedProviderSmokeChallenge) -> bool:
        deployment = challenge.deployment
        return self._key.key_id == (
            f"{deployment.root_key_id}.readiness_attestation."
            f"{deployment.composition_manifest_sha256[:10]}"
        )

    def sign(self, challenge: ConnectedProviderSmokeChallenge) -> str:
        if (
            type(challenge) is not ConnectedProviderSmokeChallenge
            or not self._matches_deployment(challenge)
        ):
            raise ConnectedReadinessAttestationError()
        return hmac.new(
            self._key.secret,
            challenge.canonical_bytes(),
            hashlib.sha256,
        ).hexdigest()

    def verify(
        self,
        challenge: ConnectedProviderSmokeChallenge,
        receipt_sha256: str,
    ) -> bool:
        if (
            type(challenge) is not ConnectedProviderSmokeChallenge
            or not isinstance(receipt_sha256, str)
            or not _SHA256.fullmatch(receipt_sha256)
            or not self._matches_deployment(challenge)
        ):
            return False
        return hmac.compare_digest(self.sign(challenge), receipt_sha256)

    def __repr__(self) -> str:
        return "ConnectedProviderSmokeAttestor(key='<redacted>')"

    def __getstate__(self) -> object:
        raise TypeError("connected provider-smoke attestors cannot be serialized")

    def __reduce__(self) -> object:
        raise TypeError("connected provider-smoke attestors cannot be serialized")


__all__ = [
    "ConnectedProviderSmokeAttestor",
    "ConnectedProviderSmokeChallenge",
    "ConnectedProviderSmokeDeployment",
    "ConnectedReadinessAttestationError",
    "ConnectedReadinessAttestationKey",
]
