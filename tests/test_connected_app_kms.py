from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
import hashlib
import json
import pickle
from urllib.parse import parse_qs

import httpx
import pytest

from backend.connected_app_key_derivation import ConnectedKeyCustodyKind
from backend.connected_app_kms import (
    ConnectedGoogleKMSConfiguration,
    ConnectedGoogleKMSRootLoader,
    ConnectedKMSRootLoaderError,
    ConnectedVercelOIDCAssertion,
    _crc32c,
)


NOW = datetime(2026, 11, 8, 15, 0, tzinfo=UTC)
MANIFEST = hashlib.sha256(b"production-composition").hexdigest()
ATTESTATION = hashlib.sha256(b"reviewed-wif-iam-kms-policy").hexdigest()
ROOT = hashlib.sha256(b"test-only-connected-root").digest()
CIPHERTEXT = b"kms-ciphertext-not-a-secret"
ASSERTION_TEXT = "a" * 80 + "." + "b" * 80 + "." + "c" * 80


def configuration(**overrides) -> ConnectedGoogleKMSConfiguration:
    values = {
        "project_number": "123456789012",
        "workload_identity_pool_id": "vercel-prod",
        "workload_identity_provider_id": "askcrump-prod",
        "service_account_email": "askcrump-kms@askcrump-prod.iam.gserviceaccount.com",
        "crypto_key_resource": (
            "projects/askcrump-prod/locations/us-east1/keyRings/connected-operator/"
            "cryptoKeys/root-envelope"
        ),
        "encrypted_root_b64": base64.b64encode(CIPHERTEXT).decode("ascii"),
        "root_key_id": "gkms-primary",
        "composition_manifest_sha256": MANIFEST,
        "custody_attestation_sha256": ATTESTATION,
        "expected_protection_level": "HSM",
        "root_ttl_seconds": 600,
    }
    values.update(overrides)
    return ConnectedGoogleKMSConfiguration(**values)


def response(value: dict[str, object], status: int = 200) -> httpx.Response:
    return httpx.Response(
        status,
        headers={"content-type": "application/json"},
        content=json.dumps(value, separators=(",", ":")).encode(),
    )


@pytest.mark.anyio
async def test_request_scoped_oidc_unwraps_manifest_bound_short_lived_root() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.host == "sts.googleapis.com":
            return response(
                {
                    "access_token": "s" * 64,
                    "issued_token_type": "urn:ietf:params:oauth:token-type:access_token",
                    "token_type": "Bearer",
                    "expires_in": 900,
                }
            )
        if request.url.host == "iamcredentials.googleapis.com":
            return response(
                {
                    "accessToken": "i" * 64,
                    "expireTime": (NOW + timedelta(minutes=15)).isoformat().replace("+00:00", "Z"),
                }
            )
        assert request.url.host == "cloudkms.googleapis.com"
        return response(
            {
                "plaintext": base64.b64encode(ROOT).decode("ascii"),
                "plaintextCrc32c": str(_crc32c(ROOT)),
                "usedPrimary": True,
                "protectionLevel": "HSM",
            }
        )

    assertion = ConnectedVercelOIDCAssertion(ASSERTION_TEXT)
    loader = ConnectedGoogleKMSRootLoader(
        configuration(), transport=httpx.MockTransport(handler), now=lambda: NOW
    )
    root = await loader.load(assertion=assertion)

    assert root.key_id == "gkms-primary"
    assert root.custody is ConnectedKeyCustodyKind.GOOGLE_CLOUD_KMS
    assert root.attestation_sha256 == ATTESTATION
    assert root.loaded_at == NOW
    assert root.expires_at == NOW + timedelta(minutes=10)
    assert root.secret == ROOT
    assert repr(assertion) == "ConnectedVercelOIDCAssertion(token='<redacted>')"
    assert repr(loader) == "ConnectedGoogleKMSRootLoader(identity='vercel-oidc', root='<redacted>')"
    with pytest.raises(TypeError):
        pickle.dumps(assertion)

    assert [item.url.host for item in requests] == [
        "sts.googleapis.com",
        "iamcredentials.googleapis.com",
        "cloudkms.googleapis.com",
    ]
    sts = parse_qs(requests[0].content.decode("ascii"), strict_parsing=True)
    assert sts["subject_token"] == [ASSERTION_TEXT]
    assert sts["audience"] == [configuration().audience]
    assert "authorization" not in requests[0].headers
    assert requests[1].headers["authorization"] == "Bearer " + "s" * 64
    assert requests[2].headers["authorization"] == "Bearer " + "i" * 64
    kms = json.loads(requests[2].content)
    assert base64.b64decode(kms["additionalAuthenticatedData"]) == bytes.fromhex(MANIFEST)
    assert int(kms["ciphertextCrc32c"]) == _crc32c(CIPHERTEXT)
    assert int(kms["additionalAuthenticatedDataCrc32c"]) == _crc32c(
        bytes.fromhex(MANIFEST)
    )


@pytest.mark.anyio
@pytest.mark.parametrize(
    "drift",
    ["checksum", "primary", "protection", "length"],
)
async def test_kms_integrity_drift_never_returns_root(drift: str) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "sts.googleapis.com":
            return response(
                {
                    "access_token": "s" * 64,
                    "issued_token_type": "urn:ietf:params:oauth:token-type:access_token",
                    "token_type": "Bearer",
                    "expires_in": 900,
                }
            )
        if request.url.host == "iamcredentials.googleapis.com":
            return response(
                {
                    "accessToken": "i" * 64,
                    "expireTime": (NOW + timedelta(minutes=15)).isoformat().replace("+00:00", "Z"),
                }
            )
        plaintext = ROOT if drift != "length" else ROOT[:-1]
        return response(
            {
                "plaintext": base64.b64encode(plaintext).decode("ascii"),
                "plaintextCrc32c": str(_crc32c(plaintext) + (1 if drift == "checksum" else 0)),
                "usedPrimary": drift != "primary",
                "protectionLevel": "SOFTWARE" if drift == "protection" else "HSM",
            }
        )

    loader = ConnectedGoogleKMSRootLoader(
        configuration(), transport=httpx.MockTransport(handler), now=lambda: NOW
    )
    with pytest.raises(
        ConnectedKMSRootLoaderError,
        match="CONNECTED_KMS_INTEGRITY_FAILED",
    ):
        await loader.load(assertion=ConnectedVercelOIDCAssertion(ASSERTION_TEXT))


@pytest.mark.parametrize(
    "kwargs",
    [
        {"project_number": "project"},
        {"encrypted_root_b64": "not-base64"},
        {"root_ttl_seconds": 901},
        {"expected_protection_level": "UNKNOWN"},
    ],
)
def test_configuration_rejects_unattested_shapes(kwargs: dict[str, object]) -> None:
    with pytest.raises(
        ConnectedKMSRootLoaderError,
        match="CONNECTED_KMS_CONFIGURATION_INVALID",
    ):
        configuration(**kwargs)


def test_crc32c_matches_standard_vector() -> None:
    assert _crc32c(b"123456789") == 0xE3069283
