from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
import json

import pytest

from backend import config
from backend.connected_app_key_derivation import (
    ConnectedKeyCustodyKind,
    ConnectedRootKeyMaterial,
)
from backend.connected_app_kms import ConnectedVercelOIDCAssertion
from backend.connected_app_release_runtime_identity import (
    ConnectedReleaseRuntimeIdentityError,
    ConnectedVercelProductionRuntimeIdentity,
)


NOW = datetime(2026, 11, 8, tzinfo=UTC)


def token(**changes: object) -> ConnectedVercelOIDCAssertion:
    claims: dict[str, object] = {
        "owner_id": "team_12345678",
        "project_id": "prj_12345678",
        "environment": "production",
    }
    claims.update(changes)
    payload = base64.urlsafe_b64encode(
        json.dumps(claims, separators=(",", ":")).encode()
    ).decode("ascii").rstrip("=")
    return ConnectedVercelOIDCAssertion(
        "a" * 80 + "." + payload + "." + "c" * 80
    )


def root() -> ConnectedRootKeyMaterial:
    return ConnectedRootKeyMaterial(
        key_id="gkms1",
        custody=ConnectedKeyCustodyKind.GOOGLE_CLOUD_KMS,
        attestation_sha256="a" * 64,
        loaded_at=NOW,
        expires_at=NOW + timedelta(minutes=10),
        secret=b"k" * 32,
    )


@pytest.fixture(autouse=True)
def identity(monkeypatch):
    monkeypatch.setattr(
        config,
        "CONNECTED_APPS_VERCEL_TEAM_ID",
        "team_12345678",
    )
    monkeypatch.setattr(
        config,
        "CONNECTED_APPS_VERCEL_PROJECT_ID",
        "prj_12345678",
    )
    monkeypatch.setattr(
        config,
        "CONNECTED_APPS_VERCEL_ENVIRONMENT",
        "production",
    )
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("VERCEL_ENV", "production")
    monkeypatch.setenv("VERCEL_PROJECT_ID", "prj_12345678")
    monkeypatch.setenv("VERCEL_DEPLOYMENT_ID", "dpl_12345678abcd")
    monkeypatch.setenv("VERCEL_GIT_COMMIT_SHA", "a" * 40)


def test_attests_platform_tuple_only_after_kms_custody() -> None:
    value = ConnectedVercelProductionRuntimeIdentity().attest(
        assertion=token(),
        kms_root=root(),
    )
    assert value.deployment_id == "dpl_12345678abcd"
    assert value.commit_sha == "a" * 40
    assert value.project_id == "prj_12345678"
    assert value.team_id == "team_12345678"
    assert value.environment == "production"


@pytest.mark.parametrize(
    ("environment_name", "environment_value", "claim_changes"),
    (
        ("VERCEL", "0", {}),
        ("VERCEL_ENV", "preview", {}),
        ("VERCEL_PROJECT_ID", "prj_attacker1", {}),
        ("VERCEL_DEPLOYMENT_ID", "preview", {}),
        ("VERCEL_GIT_COMMIT_SHA", "A" * 40, {}),
        ("VERCEL_ENV", "production", {"environment": "preview"}),
        ("VERCEL_ENV", "production", {"project_id": "prj_attacker1"}),
        ("VERCEL_ENV", "production", {"owner_id": "team_attacker"}),
    ),
)
def test_claim_or_platform_drift_fails_content_free(
    monkeypatch,
    environment_name: str,
    environment_value: str,
    claim_changes: dict[str, object],
) -> None:
    monkeypatch.setenv(environment_name, environment_value)
    with pytest.raises(
        ConnectedReleaseRuntimeIdentityError,
        match="CONNECTED_RELEASE_RUNTIME_IDENTITY_FAILED",
    ):
        ConnectedVercelProductionRuntimeIdentity().attest(
            assertion=token(**claim_changes),
            kms_root=root(),
        )


def test_non_kms_root_is_refused_before_claim_use() -> None:
    invalid = ConnectedRootKeyMaterial(
        key_id="local1",
        custody=ConnectedKeyCustodyKind.AWS_KMS,
        attestation_sha256="a" * 64,
        loaded_at=NOW,
        expires_at=NOW + timedelta(minutes=10),
        secret=b"k" * 32,
    )
    with pytest.raises(ConnectedReleaseRuntimeIdentityError):
        ConnectedVercelProductionRuntimeIdentity().attest(
            assertion=token(),
            kms_root=invalid,
        )
