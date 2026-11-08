"""Request-scoped Vercel OIDC to Google Cloud KMS root-key custody.

Vercel Functions expose their rotating OIDC assertion on the incoming request,
not as a stable process secret.  This boundary exchanges that assertion through
Google Workload Identity Federation, impersonates one narrowly scoped service
account, and decrypts one manifest-bound 32-byte data key with Cloud KMS.

No service-account key, KMS plaintext, or bearer token is read from an
environment variable.  All network destinations are fixed, redirects and
ambient proxies are disabled, response bodies are bounded, KMS CRC32C is
verified, and the resulting root is short lived and non-serializable.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import json
import re
from typing import Callable
from urllib.parse import quote, urlencode

import certifi
import httpx

from .connected_app_key_derivation import (
    ConnectedKeyCustodyKind,
    ConnectedRootKeyMaterial,
)


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_KEY_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,31}$")
_PROJECT_NUMBER = re.compile(r"^[1-9][0-9]{5,19}$")
_WIF_ID = re.compile(r"^[a-z][a-z0-9-]{3,31}$")
_SERVICE_ACCOUNT = re.compile(
    r"^[a-z][a-z0-9-]{4,28}[a-z0-9]@[a-z][a-z0-9.-]{4,61}\.iam\.gserviceaccount\.com$"
)
_KMS_RESOURCE = re.compile(
    r"^projects/[a-z][a-z0-9-]{4,62}/locations/[a-z0-9-]{1,63}/"
    r"keyRings/[A-Za-z0-9_-]{1,63}/cryptoKeys/[A-Za-z0-9_-]{1,63}$"
)
_PROTECTION_LEVELS = frozenset({"SOFTWARE", "HSM", "EXTERNAL", "EXTERNAL_VPC"})
_CLOUD_PLATFORM_SCOPE = "https://www.googleapis.com/auth/cloud-platform"
_CLOUD_KMS_SCOPE = "https://www.googleapis.com/auth/cloudkms"
_GRANT_TYPE = "urn:ietf:params:oauth:grant-type:token-exchange"
_ACCESS_TOKEN_TYPE = "urn:ietf:params:oauth:token-type:access_token"
_JWT_TOKEN_TYPE = "urn:ietf:params:oauth:token-type:jwt"
_MAX_RESPONSE_BYTES = 64 * 1024
_MAX_CIPHERTEXT_BYTES = 64 * 1024
_MIN_TOKEN_REMAINING = timedelta(seconds=30)


class ConnectedKMSRootLoaderError(RuntimeError):
    """Content-free request-scoped custody failure."""

    _CODES = frozenset(
        {
            "CONNECTED_KMS_CONFIGURATION_INVALID",
            "CONNECTED_KMS_IDENTITY_INVALID",
            "CONNECTED_KMS_UNAVAILABLE",
            "CONNECTED_KMS_INTEGRITY_FAILED",
        }
    )

    def __init__(self, code: str) -> None:
        self.code = code if code in self._CODES else "CONNECTED_KMS_UNAVAILABLE"
        super().__init__(self.code)


def _aware(value: object) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ConnectedKMSRootLoaderError("CONNECTED_KMS_CONFIGURATION_INVALID")
    return value.astimezone(UTC)


def _json_no_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON key")
        value[key] = item
    return value


def _crc32c(value: bytes) -> int:
    """Return the Castagnoli CRC used by Cloud KMS (not zlib CRC32)."""

    crc = 0xFFFFFFFF
    for byte in value:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ (0x82F63B78 if crc & 1 else 0)
    return crc ^ 0xFFFFFFFF


def _b64decode(value: object, *, maximum: int) -> bytes:
    if not isinstance(value, str) or not value or len(value) > ((maximum + 2) // 3) * 4 + 4:
        raise ConnectedKMSRootLoaderError("CONNECTED_KMS_CONFIGURATION_INVALID")
    try:
        decoded = base64.b64decode(value, validate=True)
    except (ValueError, TypeError):
        raise ConnectedKMSRootLoaderError("CONNECTED_KMS_CONFIGURATION_INVALID") from None
    if not decoded or len(decoded) > maximum:
        raise ConnectedKMSRootLoaderError("CONNECTED_KMS_CONFIGURATION_INVALID")
    return decoded


class ConnectedVercelOIDCAssertion:
    """One request's rotating assertion; representation and serialization are refused."""

    __slots__ = ("__token",)

    def __init__(self, token: str) -> None:
        if (
            not isinstance(token, str)
            or not 100 <= len(token) <= 16_384
            or token.count(".") != 2
            or any(ord(character) <= 32 or ord(character) == 127 for character in token)
        ):
            raise ConnectedKMSRootLoaderError("CONNECTED_KMS_IDENTITY_INVALID")
        self.__token = token

    def reveal_for_exchange(self) -> str:
        return self.__token

    def __repr__(self) -> str:
        return "ConnectedVercelOIDCAssertion(token='<redacted>')"

    def __str__(self) -> str:
        return "<vercel-oidc-assertion:redacted>"

    def __getstate__(self) -> object:
        raise TypeError("Vercel OIDC assertions cannot be serialized")

    def __reduce__(self) -> object:
        raise TypeError("Vercel OIDC assertions cannot be serialized")


@dataclass(frozen=True, slots=True, repr=False)
class ConnectedGoogleKMSConfiguration:
    project_number: str
    workload_identity_pool_id: str
    workload_identity_provider_id: str
    service_account_email: str
    crypto_key_resource: str
    encrypted_root_b64: str
    root_key_id: str
    composition_manifest_sha256: str
    custody_attestation_sha256: str
    expected_protection_level: str = "HSM"
    root_ttl_seconds: int = 600

    def __post_init__(self) -> None:
        if (
            not _PROJECT_NUMBER.fullmatch(self.project_number)
            or not _WIF_ID.fullmatch(self.workload_identity_pool_id)
            or not _WIF_ID.fullmatch(self.workload_identity_provider_id)
            or not _SERVICE_ACCOUNT.fullmatch(self.service_account_email)
            or not _KMS_RESOURCE.fullmatch(self.crypto_key_resource)
            or not _KEY_ID.fullmatch(self.root_key_id)
            or not _SHA256.fullmatch(self.composition_manifest_sha256)
            or not _SHA256.fullmatch(self.custody_attestation_sha256)
            or self.expected_protection_level not in _PROTECTION_LEVELS
            or type(self.root_ttl_seconds) is not int
            or not 60 <= self.root_ttl_seconds <= 900
        ):
            raise ConnectedKMSRootLoaderError("CONNECTED_KMS_CONFIGURATION_INVALID")
        _b64decode(self.encrypted_root_b64, maximum=_MAX_CIPHERTEXT_BYTES)

    @property
    def audience(self) -> str:
        return (
            f"//iam.googleapis.com/projects/{self.project_number}/locations/global/"
            f"workloadIdentityPools/{self.workload_identity_pool_id}/providers/"
            f"{self.workload_identity_provider_id}"
        )

    def __repr__(self) -> str:
        return (
            "ConnectedGoogleKMSConfiguration("
            f"crypto_key_resource={self.crypto_key_resource!r}, ciphertext='<redacted>')"
        )


class ConnectedGoogleKMSRootLoader:
    """Exchange one request assertion and unwrap a short-lived manifest-bound root."""

    def __init__(
        self,
        configuration: ConnectedGoogleKMSConfiguration,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if type(configuration) is not ConnectedGoogleKMSConfiguration or not callable(now):
            raise ConnectedKMSRootLoaderError("CONNECTED_KMS_CONFIGURATION_INVALID")
        self._configuration = configuration
        self._transport = transport
        self._now = now

    @staticmethod
    def _bearer(value: object) -> str:
        if (
            not isinstance(value, str)
            or not 32 <= len(value) <= 12_288
            or any(ord(character) <= 32 or ord(character) == 127 for character in value)
        ):
            raise ConnectedKMSRootLoaderError("CONNECTED_KMS_IDENTITY_INVALID")
        return value

    @staticmethod
    def _parse_expiry(value: object) -> datetime:
        if not isinstance(value, str) or not 20 <= len(value) <= 40:
            raise ConnectedKMSRootLoaderError("CONNECTED_KMS_IDENTITY_INVALID")
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            raise ConnectedKMSRootLoaderError("CONNECTED_KMS_IDENTITY_INVALID") from None
        return _aware(parsed)

    @staticmethod
    async def _read_json(response: httpx.Response) -> dict[str, object]:
        if response.status_code != 200:
            raise ConnectedKMSRootLoaderError("CONNECTED_KMS_UNAVAILABLE")
        content_type = response.headers.get("content-type", "").split(";", 1)[0].casefold()
        if content_type != "application/json":
            raise ConnectedKMSRootLoaderError("CONNECTED_KMS_UNAVAILABLE")
        declared = response.headers.get("content-length")
        if declared is not None:
            try:
                if not 0 <= int(declared) <= _MAX_RESPONSE_BYTES:
                    raise ValueError
            except ValueError:
                raise ConnectedKMSRootLoaderError("CONNECTED_KMS_UNAVAILABLE") from None
        collected = bytearray()
        async for chunk in response.aiter_bytes():
            if len(collected) + len(chunk) > _MAX_RESPONSE_BYTES:
                raise ConnectedKMSRootLoaderError("CONNECTED_KMS_UNAVAILABLE")
            collected.extend(chunk)
        body = bytes(collected)
        if not body:
            raise ConnectedKMSRootLoaderError("CONNECTED_KMS_UNAVAILABLE")
        try:
            value = json.loads(
                body.decode("utf-8"),
                object_pairs_hook=_json_no_duplicates,
                parse_constant=lambda _item: (_ for _ in ()).throw(ValueError()),
            )
        except (UnicodeError, ValueError, json.JSONDecodeError, RecursionError):
            raise ConnectedKMSRootLoaderError("CONNECTED_KMS_UNAVAILABLE") from None
        if not isinstance(value, dict):
            raise ConnectedKMSRootLoaderError("CONNECTED_KMS_UNAVAILABLE")
        return value

    async def load(
        self,
        *,
        assertion: ConnectedVercelOIDCAssertion,
    ) -> ConnectedRootKeyMaterial:
        if type(assertion) is not ConnectedVercelOIDCAssertion:
            raise ConnectedKMSRootLoaderError("CONNECTED_KMS_IDENTITY_INVALID")
        reference = _aware(self._now())
        configuration = self._configuration
        timeout = httpx.Timeout(15.0, connect=5.0, write=10.0, read=15.0, pool=5.0)
        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "identity",
            "User-Agent": "AskCrump-ConnectedKMS/1",
        }
        try:
            async with httpx.AsyncClient(
                http2=True,
                verify=certifi.where(),
                follow_redirects=False,
                trust_env=False,
                timeout=timeout,
                transport=self._transport,
            ) as client:
                sts_body = urlencode(
                    {
                        "grant_type": _GRANT_TYPE,
                        "audience": configuration.audience,
                        "scope": _CLOUD_PLATFORM_SCOPE,
                        "requested_token_type": _ACCESS_TOKEN_TYPE,
                        "subject_token": assertion.reveal_for_exchange(),
                        "subject_token_type": _JWT_TOKEN_TYPE,
                    }
                ).encode("ascii")
                sts_response = await client.post(
                    "https://sts.googleapis.com/v1/token",
                    headers={**headers, "Content-Type": "application/x-www-form-urlencoded"},
                    content=sts_body,
                )
                sts = await self._read_json(sts_response)
                if (
                    sts.get("token_type") != "Bearer"
                    or sts.get("issued_token_type") != _ACCESS_TOKEN_TYPE
                    or type(sts.get("expires_in")) is not int
                    or not 60 <= int(sts["expires_in"]) <= 3600
                ):
                    raise ConnectedKMSRootLoaderError("CONNECTED_KMS_IDENTITY_INVALID")
                federated_token = self._bearer(sts.get("access_token"))

                service_account = quote(configuration.service_account_email, safe="@.")
                impersonation_response = await client.post(
                    "https://iamcredentials.googleapis.com/v1/projects/-/serviceAccounts/"
                    f"{service_account}:generateAccessToken",
                    headers={
                        **headers,
                        "Authorization": f"Bearer {federated_token}",
                        "Content-Type": "application/json; charset=utf-8",
                    },
                    json={"scope": [_CLOUD_KMS_SCOPE], "lifetime": "900s"},
                )
                impersonated = await self._read_json(impersonation_response)
                kms_token = self._bearer(impersonated.get("accessToken"))
                token_expiry = self._parse_expiry(impersonated.get("expireTime"))
                if not reference + _MIN_TOKEN_REMAINING < token_expiry <= reference + timedelta(
                    seconds=901
                ):
                    raise ConnectedKMSRootLoaderError("CONNECTED_KMS_IDENTITY_INVALID")

                ciphertext = _b64decode(
                    configuration.encrypted_root_b64,
                    maximum=_MAX_CIPHERTEXT_BYTES,
                )
                associated_data = bytes.fromhex(configuration.composition_manifest_sha256)
                kms_response = await client.post(
                    f"https://cloudkms.googleapis.com/v1/{configuration.crypto_key_resource}:decrypt",
                    headers={
                        **headers,
                        "Authorization": f"Bearer {kms_token}",
                        "Content-Type": "application/json; charset=utf-8",
                    },
                    json={
                        "ciphertext": configuration.encrypted_root_b64,
                        "additionalAuthenticatedData": base64.b64encode(associated_data).decode(
                            "ascii"
                        ),
                        "ciphertextCrc32c": str(_crc32c(ciphertext)),
                        "additionalAuthenticatedDataCrc32c": str(_crc32c(associated_data)),
                    },
                )
                decrypted = await self._read_json(kms_response)
        except ConnectedKMSRootLoaderError:
            raise
        except (httpx.HTTPError, UnicodeError, ValueError, TypeError, OverflowError):
            raise ConnectedKMSRootLoaderError("CONNECTED_KMS_UNAVAILABLE") from None

        if (
            decrypted.get("usedPrimary") is not True
            or decrypted.get("protectionLevel") != configuration.expected_protection_level
        ):
            raise ConnectedKMSRootLoaderError("CONNECTED_KMS_INTEGRITY_FAILED")
        plaintext_value = decrypted.get("plaintext")
        if not isinstance(plaintext_value, str):
            raise ConnectedKMSRootLoaderError("CONNECTED_KMS_INTEGRITY_FAILED")
        try:
            plaintext = base64.b64decode(plaintext_value, validate=True)
            returned_crc = int(decrypted.get("plaintextCrc32c"))
        except (ValueError, TypeError, OverflowError):
            raise ConnectedKMSRootLoaderError("CONNECTED_KMS_INTEGRITY_FAILED") from None
        if len(plaintext) != 32 or not 0 <= returned_crc <= 0xFFFFFFFF:
            raise ConnectedKMSRootLoaderError("CONNECTED_KMS_INTEGRITY_FAILED")
        if _crc32c(plaintext) != returned_crc:
            raise ConnectedKMSRootLoaderError("CONNECTED_KMS_INTEGRITY_FAILED")

        expires_at = min(
            reference + timedelta(seconds=configuration.root_ttl_seconds),
            token_expiry - timedelta(seconds=15),
        )
        if expires_at <= reference:
            raise ConnectedKMSRootLoaderError("CONNECTED_KMS_IDENTITY_INVALID")
        return ConnectedRootKeyMaterial(
            key_id=configuration.root_key_id,
            custody=ConnectedKeyCustodyKind.GOOGLE_CLOUD_KMS,
            attestation_sha256=configuration.custody_attestation_sha256,
            loaded_at=reference,
            expires_at=expires_at,
            secret=plaintext,
        )

    def __repr__(self) -> str:
        return "ConnectedGoogleKMSRootLoader(identity='vercel-oidc', root='<redacted>')"


__all__ = [
    "ConnectedGoogleKMSConfiguration",
    "ConnectedGoogleKMSRootLoader",
    "ConnectedKMSRootLoaderError",
    "ConnectedVercelOIDCAssertion",
]
