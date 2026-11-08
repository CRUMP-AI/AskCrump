from __future__ import annotations

import asyncio
import base64
from datetime import UTC, datetime, timedelta
import hashlib
import inspect
from pathlib import Path
import pickle

import httpx
import pytest

from backend import config
from backend.connected_app_host_configuration import (
    ConnectedEncryptedHostConfiguration,
)
from backend.connected_app_kms import (
    ConnectedGoogleKMSConfiguration,
    ConnectedGoogleKMSRootLoader,
    ConnectedVercelOIDCAssertion,
)
from backend.connected_app_release_preview import (
    CONNECTED_RELEASE_PREVIEW_CONTRACT_SHA256,
    ConnectedAIGatewayReleaseProbe,
    ConnectedGatewayReleasePreviewReceipt,
    ConnectedReleasePreviewError,
    ConnectedReleasePreviewHarness,
    ConnectedReleasePreviewPermit,
)
from backend.connected_app_release_runtime_identity import (
    ConnectedVercelProductionRuntimeIdentity,
)
from backend.connected_app_release_database import (
    ConnectedReleasePreviewProductionDatabase,
)
from backend.connected_app_request_ai_gateway import (
    ConnectedRequestScopedAIGatewayFactory,
)


NOW = datetime(2026, 11, 8, 8, 0, tzinfo=UTC)
MANIFEST = hashlib.sha256(b"connected-release-preview-manifest").hexdigest()
ATTESTATION = hashlib.sha256(b"connected-preview-kms-policy").hexdigest()
DATABASE_TARGET = "1" * 32
DEPLOYMENT_ID = "dpl_12345678preview"
COMMIT_SHA = "a" * 40
INVOCATION_ID = "11111111-1111-4111-8111-111111111111"
TOKEN = "a" * 80 + "." + "b" * 80 + "." + "c" * 80
CONFIRMATION = "RUN_CONNECTED_RELEASE_PREVIEW_WITH_DEDICATED_NON_CUSTOMER_ACCOUNTS"
ENCRYPTED_ROOT_B64 = base64.b64encode(b"x" * 48).decode("ascii")


class FakeRootLoader:
    async def load(self, *, assertion):
        raise AssertionError((assertion, "fake KMS must remain unreachable"))


class FakeGatewayProbe:
    async def preview(self, **_kwargs):
        return ConnectedGatewayReleasePreviewReceipt(
            invocation_id=INVOCATION_ID,
            contract_sha256=CONNECTED_RELEASE_PREVIEW_CONTRACT_SHA256,
            checked_at=NOW,
            request_oidc_attested=True,
            pinned_model_provider_attested=True,
            zero_retention_attested=True,
            cost_receipt_attested=True,
        )


def _kms_loader(
    *, transport: httpx.AsyncBaseTransport | None = None
) -> ConnectedGoogleKMSRootLoader:
    configuration = ConnectedGoogleKMSConfiguration(
        project_number="123456789012",
        workload_identity_pool_id="askcrump-pool",
        workload_identity_provider_id="vercel-provider",
        service_account_email="askcrump-kms@askcrump-prod.iam.gserviceaccount.com",
        crypto_key_resource=(
            "projects/askcrump-prod/locations/us-east1/"
            "keyRings/connected/cryptoKeys/root"
        ),
        encrypted_root_b64=ENCRYPTED_ROOT_B64,
        root_key_id="gkms1",
        composition_manifest_sha256=MANIFEST,
        custody_attestation_sha256=ATTESTATION,
    )
    return ConnectedGoogleKMSRootLoader(
        configuration,
        transport=transport,
        now=lambda: NOW,
    )


def _ciphertext() -> ConnectedEncryptedHostConfiguration:
    nonce = base64.urlsafe_b64encode(b"n" * 12).decode("ascii").rstrip("=")
    ciphertext = (
        base64.urlsafe_b64encode(b"c" * 17).decode("ascii").rstrip("=")
    )
    return ConnectedEncryptedHostConfiguration(f"v1:host-key:{nonce}:{ciphertext}")


def _database() -> ConnectedReleasePreviewProductionDatabase:
    return ConnectedReleasePreviewProductionDatabase()


def _gateway_factory(
    database: ConnectedReleasePreviewProductionDatabase,
) -> ConnectedRequestScopedAIGatewayFactory:
    return ConnectedRequestScopedAIGatewayFactory(
        database=database,
        model="openai/gpt-oss-20b",
        provider="groq",
        deployment_id=DEPLOYMENT_ID,
        commit_sha=COMMIT_SHA,
    )


def _exact_inputs() -> dict[str, object]:
    database = _database()
    return {
        "root_loader": _kms_loader(),
        "ciphertext": _ciphertext(),
        "database": database,
        "ai_gateway_factory": _gateway_factory(database),
        "gateway_probe": ConnectedAIGatewayReleaseProbe(now=lambda: NOW),
        "runtime_identity": ConnectedVercelProductionRuntimeIdentity(),
        "database_target_fingerprint": DATABASE_TARGET,
        "now": lambda: NOW,
    }


@pytest.fixture(autouse=True)
def preview_source(monkeypatch):
    monkeypatch.setattr(config, "CONNECTED_APPS_RELEASE_PREVIEW_SOURCE_RELEASED", False)
    monkeypatch.setattr(config, "CONNECTED_APPS_PUBLIC_RELEASED", False)
    monkeypatch.setattr(config, "CONNECTED_MULTI_STEP_SOURCE_RELEASED", False)
    monkeypatch.setattr(config, "CONNECTED_APPS_COMPOSITION_MANIFEST_SHA256", MANIFEST)
    monkeypatch.setattr(
        config,
        "CONNECTED_APPS_DATABASE_TARGET_FINGERPRINT",
        DATABASE_TARGET,
    )
    monkeypatch.setattr(config, "CONNECTED_APPS_KMS_PROJECT_NUMBER", "123456789012")
    monkeypatch.setattr(config, "CONNECTED_APPS_KMS_WIF_POOL_ID", "askcrump-pool")
    monkeypatch.setattr(
        config,
        "CONNECTED_APPS_KMS_WIF_PROVIDER_ID",
        "vercel-provider",
    )
    monkeypatch.setattr(
        config,
        "CONNECTED_APPS_KMS_SERVICE_ACCOUNT_EMAIL",
        "askcrump-kms@askcrump-prod.iam.gserviceaccount.com",
    )
    monkeypatch.setattr(
        config,
        "CONNECTED_APPS_KMS_CRYPTO_KEY_RESOURCE",
        "projects/askcrump-prod/locations/us-east1/keyRings/connected/cryptoKeys/root",
    )
    monkeypatch.setattr(config, "CONNECTED_APPS_KMS_ROOT_KEY_ID", "gkms1")
    monkeypatch.setattr(
        config,
        "CONNECTED_APPS_KMS_CUSTODY_ATTESTATION_SHA256",
        ATTESTATION,
    )
    monkeypatch.setattr(
        config,
        "CONNECTED_APPS_KMS_ENCRYPTED_ROOT_SHA256",
        hashlib.sha256(ENCRYPTED_ROOT_B64.encode("ascii")).hexdigest(),
    )


def _permit() -> ConnectedReleasePreviewPermit:
    return ConnectedReleasePreviewPermit(
        invocation_id=INVOCATION_ID,
        issued_at=NOW - timedelta(seconds=1),
        expires_at=NOW + timedelta(minutes=5),
        confirmation=CONFIRMATION,
    )


def _release_candidate(monkeypatch) -> None:
    monkeypatch.setattr(
        config,
        "CONNECTED_APPS_RELEASE_PREVIEW_SOURCE_RELEASED",
        True,
    )
    monkeypatch.setattr(config, "CONNECTED_APPS_PUBLIC_RELEASED", True)
    monkeypatch.setattr(config, "CONNECTED_MULTI_STEP_SOURCE_RELEASED", True)


@pytest.mark.asyncio
async def test_source_lock_false_prevents_permit_and_every_external_read(
    monkeypatch,
) -> None:
    inputs = _exact_inputs()
    harness = ConnectedReleasePreviewHarness(**inputs)
    database = inputs["database"]
    assert type(database) is ConnectedReleasePreviewProductionDatabase
    with pytest.raises(ConnectedReleasePreviewError):
        _permit()

    _release_candidate(monkeypatch)
    permit = _permit()
    monkeypatch.setattr(config, "CONNECTED_APPS_RELEASE_PREVIEW_SOURCE_RELEASED", False)
    monkeypatch.setattr(
        config.os,
        "getenv",
        lambda *_args: (_ for _ in ()).throw(
            AssertionError("lock-false release preview read the environment")
        ),
    )
    with pytest.raises(ConnectedReleasePreviewError):
        await harness.run(
            permit=permit,
            assertion=ConnectedVercelOIDCAssertion(TOKEN),
            expected_manifest_sha256=MANIFEST,
        )


@pytest.mark.asyncio
async def test_source_lock_still_prevents_preview_on_public_release(monkeypatch) -> None:
    inputs = _exact_inputs()
    harness = ConnectedReleasePreviewHarness(**inputs)
    database = inputs["database"]
    assert type(database) is ConnectedReleasePreviewProductionDatabase
    _release_candidate(monkeypatch)
    permit = _permit()
    monkeypatch.setattr(config, "CONNECTED_APPS_RELEASE_PREVIEW_SOURCE_RELEASED", False)
    with pytest.raises(ConnectedReleasePreviewError):
        await harness.run(
            permit=permit,
            assertion=ConnectedVercelOIDCAssertion(TOKEN),
            expected_manifest_sha256=MANIFEST,
        )


@pytest.mark.parametrize("replacement", (FakeRootLoader(), object()))
def test_fake_or_duck_typed_kms_loader_is_rejected_without_io(replacement) -> None:
    inputs = _exact_inputs()
    database = inputs["database"]
    inputs["root_loader"] = replacement
    with pytest.raises(ConnectedReleasePreviewError):
        ConnectedReleasePreviewHarness(**inputs)
    assert type(database) is ConnectedReleasePreviewProductionDatabase


def test_test_transport_kms_loader_cannot_mint_production_readiness() -> None:
    inputs = _exact_inputs()
    inputs["root_loader"] = _kms_loader(
        transport=httpx.MockTransport(
            lambda _request: pytest.fail("test transport must remain unreachable")
        )
    )
    with pytest.raises(ConnectedReleasePreviewError):
        ConnectedReleasePreviewHarness(**inputs)


def test_fake_all_true_provider_probe_cannot_enter_production_harness() -> None:
    inputs = _exact_inputs()
    inputs["provider_probes"] = {"google": object(), "microsoft": object()}
    database = inputs["database"]
    with pytest.raises(TypeError):
        ConnectedReleasePreviewHarness(**inputs)
    assert type(database) is ConnectedReleasePreviewProductionDatabase
    assert "provider_probes" not in inspect.signature(
        ConnectedReleasePreviewHarness
    ).parameters


def test_fake_gateway_probe_or_factory_cannot_enter_production_harness() -> None:
    for field, replacement in (
        ("gateway_probe", FakeGatewayProbe()),
        ("ai_gateway_factory", object()),
    ):
        inputs = _exact_inputs()
        inputs[field] = replacement
        database = inputs["database"]
        with pytest.raises(ConnectedReleasePreviewError):
            ConnectedReleasePreviewHarness(**inputs)
        assert type(database) is ConnectedReleasePreviewProductionDatabase


@pytest.mark.asyncio
async def test_permit_is_exact_one_use_under_concurrency(monkeypatch) -> None:
    _release_candidate(monkeypatch)
    permit = _permit()
    results = await asyncio.gather(
        permit.claim(now=NOW),
        permit.claim(now=NOW),
        return_exceptions=True,
    )
    assert sum(value is None for value in results) == 1
    assert sum(type(value) is ConnectedReleasePreviewError for value in results) == 1
    with pytest.raises(TypeError):
        pickle.dumps(permit)


def test_harness_has_no_route_ambient_auth_or_self_attested_probe_path() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "backend"
        / "connected_app_release_preview.py"
    ).read_text(encoding="utf-8")
    assert "os.environ" not in source
    assert "os.getenv" not in source
    assert "VERCEL_OIDC_TOKEN" not in source
    assert "@router" not in source
    assert "FastAPI" not in source
    assert "type(root_loader) is not ConnectedGoogleKMSRootLoader" in source
    assert "type(gateway_probe) is not ConnectedAIGatewayReleaseProbe" in source
    assert "ConnectedGoogleReleasePreviewProbe" in source
    assert "ConnectedMicrosoftReleasePreviewProbe" in source
    assert "connected_apps_release_candidate_source_released() is not True" in source
    config_source = (
        Path(__file__).resolve().parents[1] / "backend" / "config.py"
    ).read_text(encoding="utf-8")
    assert "CONNECTED_APPS_RELEASE_PREVIEW_SOURCE_RELEASED = False" in config_source
