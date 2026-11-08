from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import pickle

import pytest

from backend.connected_app_readiness_attestation import (
    ConnectedProviderSmokeAttestor,
    ConnectedProviderSmokeChallenge,
    ConnectedProviderSmokeDeployment,
    ConnectedReadinessAttestationError,
    ConnectedReadinessAttestationKey,
)


NOW = datetime(2026, 11, 8, 20, 30, 45, 123456, tzinfo=UTC)
MANIFEST = hashlib.sha256(b"manifest").hexdigest()
DATABASE = hashlib.sha256(b"database").hexdigest()
PROVIDER = hashlib.sha256(b"provider").hexdigest()
HOST = hashlib.sha256(b"encrypted-host-envelope").hexdigest()
TARGET = "1" * 32
RELEASE = hashlib.sha256(b"release-preview").hexdigest()
DESCRIPTORS = hashlib.sha256(b"descriptor-matrix").hexdigest()
OPERATOR = hashlib.sha256(b"operator-attestation").hexdigest()
EFFECTS = hashlib.sha256(b"effect-manifest").hexdigest()
INVOCATION = "22222222-2222-4222-8222-222222222222"


def deployment(**changes: object) -> ConnectedProviderSmokeDeployment:
    values: dict[str, object] = {
        "composition_manifest_sha256": MANIFEST,
        "database_contract_sha256": DATABASE,
        "database_target_fingerprint": TARGET,
        "provider_contract_sha256": PROVIDER,
        "deployment_id": "dpl_12345678abcd",
        "commit_sha": "a" * 40,
        "host_configuration_ciphertext_sha256": HOST,
        "root_key_id": "gkms1",
        "release_preview_contract_sha256": RELEASE,
        "release_preview_descriptor_matrix_sha256": DESCRIPTORS,
        "release_preview_dedicated_account_attestation_sha256": OPERATOR,
        "release_preview_invocation_id": INVOCATION,
        "release_preview_effect_manifest_sha256": EFFECTS,
    }
    values.update(changes)
    return ConnectedProviderSmokeDeployment(**values)  # type: ignore[arg-type]


def challenge(**deployment_changes: object) -> ConnectedProviderSmokeChallenge:
    return ConnectedProviderSmokeChallenge(
        deployment=deployment(**deployment_changes),
        challenge_id="11111111-1111-4111-8111-111111111111",
        issued_at=NOW,
    )


def test_receipt_is_deterministic_domain_separated_and_rotation_bound() -> None:
    key = ConnectedReadinessAttestationKey(
        f"gkms1.readiness_attestation.{MANIFEST[:10]}",
        b"k" * 32,
    )
    attestor = ConnectedProviderSmokeAttestor(key)
    value = attestor.sign(challenge())
    assert len(value) == 64
    assert attestor.verify(challenge(), value)
    assert not ConnectedProviderSmokeAttestor(
        ConnectedReadinessAttestationKey(
            f"gkms2.readiness_attestation.{MANIFEST[:10]}",
            b"z" * 32,
        )
    ).verify(challenge(), value)
    assert not attestor.verify(challenge(commit_sha="b" * 40), value)
    assert not attestor.verify(challenge(root_key_id="gkms2"), value)
    assert not attestor.verify(
        challenge(host_configuration_ciphertext_sha256="0" * 64),
        value,
    )


def test_canonical_receipt_contains_only_exact_content_free_tuple() -> None:
    value = challenge().canonical_bytes()
    assert value.startswith(b"askcrump.connected-provider-smoke/v1\0{")
    for expected in (
        MANIFEST,
        DATABASE,
        TARGET,
        PROVIDER,
        HOST,
        RELEASE,
        DESCRIPTORS,
        OPERATOR,
        EFFECTS,
        INVOCATION,
        '"providers":["google","microsoft"]',
        '"planning_gateway":{"authentication":"current_vercel_request_oidc",'
        '"model":"openai/gpt-oss-20b","provider":"groq",'
        '"retention":"zero_data_retention_and_no_prompt_training"}',
        '"resources":["mail","calendar"]',
    ):
        assert str(expected).encode() in value
    for forbidden in (b"access_token", b"email_address", b"event_id", b"subject"):
        assert forbidden not in value


def test_key_and_attestor_are_redacted_and_nonserializable() -> None:
    key = ConnectedReadinessAttestationKey(
        f"gkms1.readiness_attestation.{MANIFEST[:10]}",
        b"s" * 32,
    )
    attestor = ConnectedProviderSmokeAttestor(key)
    assert "<redacted>" in repr(key)
    assert "<redacted>" in repr(attestor)
    assert (b"s" * 32).hex() not in repr(key)
    for value in (key, attestor):
        with pytest.raises(TypeError):
            pickle.dumps(value)


@pytest.mark.parametrize(
    "changes",
    (
        {"database_target_fingerprint": "0" * 31},
        {"deployment_id": "preview"},
        {"commit_sha": "A" * 40},
        {"host_configuration_ciphertext_sha256": "0" * 63},
        {"root_key_id": "bad key"},
        {"root_key_id": "k" * 32},
        {"release_preview_contract_sha256": "0" * 63},
        {"release_preview_descriptor_matrix_sha256": "0" * 63},
        {
            "release_preview_dedicated_account_attestation_sha256": "0" * 63
        },
        {"release_preview_invocation_id": "not-a-uuid"},
        {"release_preview_effect_manifest_sha256": "0" * 63},
    ),
)
def test_invalid_deployment_tuple_fails_content_free(changes: dict[str, object]) -> None:
    with pytest.raises(
        ConnectedReadinessAttestationError,
        match="CONNECTED_READINESS_ATTESTATION_INVALID",
    ):
        deployment(**changes)
