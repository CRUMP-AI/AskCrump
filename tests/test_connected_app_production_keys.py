from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib
import pickle

import pytest

from backend.connected_app_key_derivation import (
    ConnectedDerivedKeyset,
    ConnectedKeyCustodyKind,
    ConnectedKeyDerivationError,
    ConnectedRootKeyMaterial,
)
from backend.connected_app_production_keys import ConnectedProductionKeys


NOW = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)
MANIFEST = hashlib.sha256(b"connected-production-keys").hexdigest()
ATTESTATION = hashlib.sha256(b"kms-version-and-policy").hexdigest()


def keyset(*, expires_at: datetime | None = None) -> ConnectedDerivedKeyset:
    root = ConnectedRootKeyMaterial(
        key_id="gkms1",
        custody=ConnectedKeyCustodyKind.GOOGLE_CLOUD_KMS,
        attestation_sha256=ATTESTATION,
        loaded_at=NOW - timedelta(minutes=1),
        expires_at=expires_at or NOW + timedelta(minutes=14),
        secret=hashlib.sha256(b"test-only-root-material").digest(),
    )
    return ConnectedDerivedKeyset(
        root=root,
        composition_manifest_sha256=MANIFEST,
        now=lambda: NOW,
    )


def test_builds_exact_distinct_typed_keys() -> None:
    value = ConnectedProductionKeys.build(keyset(), now=lambda: NOW)
    keys = (
        value.host_configuration,
        value.readiness_attestation,
        value.oauth_envelope,
        value.oauth_permit,
        value.credential_envelope,
        value.payload_envelope,
        value.payload_commitment,
        value.plan_envelope,
        value.plan_commitment,
        value.plan_binding,
        value.schedule_envelope,
        value.schedule_commitment,
        value.chat_binding,
        value.chat_completion,
        value.loop_envelope,
        value.loop_commitment,
    )
    assert len({item.key_id for item in keys}) == len(keys)
    assert value.composition_manifest_sha256 == MANIFEST
    assert value.root_key_id == "gkms1"
    assert value.custody_attestation_sha256 == ATTESTATION
    assert value.expires_at == NOW + timedelta(minutes=14)
    assert repr(value) == "ConnectedProductionKeys(custody='attested', keys='<redacted>')"
    with pytest.raises(TypeError):
        pickle.dumps(value)


def test_expired_keyset_cannot_be_promoted_to_production_keys() -> None:
    value = keyset(expires_at=NOW + timedelta(seconds=1))
    with pytest.raises(
        ConnectedKeyDerivationError,
        match="CONNECTED_KEY_CUSTODY_EXPIRED",
    ):
        ConnectedProductionKeys.build(
            value,
            now=lambda: NOW + timedelta(seconds=1),
        )
