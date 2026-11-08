from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib
import pickle

import pytest

from backend.connected_app_key_derivation import (
    ConnectedDerivedKeyset,
    ConnectedKeyCustodyKind,
    ConnectedKeyDerivationError,
    ConnectedKeyPurpose,
    ConnectedRootKeyMaterial,
)


NOW = datetime(2026, 11, 8, 10, 0, tzinfo=UTC)
MANIFEST = hashlib.sha256(b"connected-production-graph").hexdigest()
ATTESTATION = hashlib.sha256(b"google-kms-attestation").hexdigest()


def root(**changes) -> ConnectedRootKeyMaterial:
    values = {
        "key_id": "kms1",
        "custody": ConnectedKeyCustodyKind.GOOGLE_CLOUD_KMS,
        "attestation_sha256": ATTESTATION,
        "loaded_at": NOW - timedelta(minutes=1),
        "expires_at": NOW + timedelta(minutes=14),
        "secret": bytes(range(32)),
    }
    values.update(changes)
    return ConnectedRootKeyMaterial(**values)


def test_every_domain_is_distinct_manifest_bound_and_current() -> None:
    first = ConnectedDerivedKeyset(
        root=root(),
        composition_manifest_sha256=MANIFEST,
        now=lambda: NOW,
    )
    keys = {purpose: first.key(purpose) for purpose in ConnectedKeyPurpose}
    assert len(keys) == 17
    assert len(set(keys.values())) == 17
    assert all(type(value) is bytes and len(value) == 32 for value in keys.values())
    assert bytes(range(32)) not in keys.values()
    assert all(len(first.key_id(purpose)) <= 64 for purpose in ConnectedKeyPurpose)
    first.require_current(now=NOW + timedelta(minutes=13))

    other_manifest = hashlib.sha256(b"other-production-graph").hexdigest()
    second = ConnectedDerivedKeyset(
        root=root(),
        composition_manifest_sha256=other_manifest,
        now=lambda: NOW,
    )
    assert all(second.key(purpose) != keys[purpose] for purpose in ConnectedKeyPurpose)

    longest = ConnectedDerivedKeyset(
        root=root(key_id="k" * 31),
        composition_manifest_sha256=MANIFEST,
        now=lambda: NOW,
    )
    assert len(longest.key_id(ConnectedKeyPurpose.READINESS_ATTESTATION)) == 64


def test_root_and_bundle_are_redacted_and_nonserializable() -> None:
    value = root()
    bundle = ConnectedDerivedKeyset(
        root=value,
        composition_manifest_sha256=MANIFEST,
        now=lambda: NOW,
    )
    assert "secret='<redacted>'" in repr(value)
    assert bytes(range(32)).hex() not in repr(value)
    assert "keys='<redacted>'" in repr(bundle)
    assert MANIFEST not in repr(bundle)
    for candidate in (value, bundle):
        with pytest.raises(TypeError):
            pickle.dumps(candidate)


@pytest.mark.parametrize(
    "changes",
    (
        {"key_id": "bad key"},
        {"key_id": "k" * 32},
        {"attestation_sha256": "0" * 63},
        {"secret": b"short"},
        {"loaded_at": NOW + timedelta(minutes=20)},
        {"expires_at": NOW - timedelta(minutes=2)},
    ),
)
def test_invalid_root_material_fails_closed(changes) -> None:
    with pytest.raises(
        ConnectedKeyDerivationError,
        match="CONNECTED_KEY_CUSTODY_INVALID",
    ):
        root(**changes)


def test_expired_or_future_root_cannot_derive_or_continue() -> None:
    expired = root(
        loaded_at=NOW - timedelta(minutes=2),
        expires_at=NOW - timedelta(seconds=1),
    )
    with pytest.raises(
        ConnectedKeyDerivationError,
        match="CONNECTED_KEY_CUSTODY_EXPIRED",
    ):
        ConnectedDerivedKeyset(
            root=expired,
            composition_manifest_sha256=MANIFEST,
            now=lambda: NOW,
        )

    future = root(
        loaded_at=NOW + timedelta(seconds=1),
        expires_at=NOW + timedelta(minutes=10),
    )
    with pytest.raises(
        ConnectedKeyDerivationError,
        match="CONNECTED_KEY_CUSTODY_EXPIRED",
    ):
        ConnectedDerivedKeyset(
            root=future,
            composition_manifest_sha256=MANIFEST,
            now=lambda: NOW,
        )

    current = ConnectedDerivedKeyset(
        root=root(),
        composition_manifest_sha256=MANIFEST,
        now=lambda: NOW,
    )
    with pytest.raises(
        ConnectedKeyDerivationError,
        match="CONNECTED_KEY_CUSTODY_EXPIRED",
    ):
        current.require_current(now=NOW + timedelta(minutes=14))


def test_unknown_purpose_and_invalid_manifest_fail_closed() -> None:
    value = ConnectedDerivedKeyset(
        root=root(),
        composition_manifest_sha256=MANIFEST,
        now=lambda: NOW,
    )
    with pytest.raises(ConnectedKeyDerivationError):
        value.key("payload_envelope")  # type: ignore[arg-type]
    with pytest.raises(ConnectedKeyDerivationError):
        value.key_id("payload_envelope")  # type: ignore[arg-type]
    with pytest.raises(ConnectedKeyDerivationError):
        ConnectedDerivedKeyset(
            root=root(),
            composition_manifest_sha256="not-a-manifest",
            now=lambda: NOW,
        )
