from __future__ import annotations

import asyncio
from dataclasses import replace
import json
import pickle
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from backend.connected_app_payload_vault import (
    ConnectedPayloadCommitmentKey,
    ConnectedPayloadMasterKey,
    ConnectedPayloadRef,
    ConnectedPayloadVault,
    ConnectedPayloadVaultError,
    EncryptedConnectedPayload,
)
from backend.connected_app_policy import ConnectorActionKind, ConnectorProvider


NOW = datetime(2026, 11, 7, 20, 0, tzinfo=UTC)
PAYLOAD_ID = "00000000-0000-4000-8000-000000000101"
OWNER_ID = "00000000-0000-4000-8000-000000000102"
CONNECTION_ID = "00000000-0000-4000-8000-000000000103"
ACTION_ID = "00000000-0000-4000-8000-000000000104"


class Store:
    def __init__(self) -> None:
        self.rows: dict[str, EncryptedConnectedPayload] = {}
        self.tombstones: dict[str, str] = {}
        self.lock = asyncio.Lock()
        self.lose_put_response = False
        self.malicious_read: EncryptedConnectedPayload | None = None

    async def put_once(self, record: EncryptedConnectedPayload) -> EncryptedConnectedPayload | None:
        key = record.reference.payload_id
        async with self.lock:
            tombstone = self.tombstones.get(key)
            if tombstone is not None:
                if tombstone != record.reference.identity_sha256:
                    raise RuntimeError("payload identity mismatch")
                return None
            existing = self.rows.get(key)
            if (
                existing is not None
                and existing.reference.identity_sha256 != record.reference.identity_sha256
            ):
                raise RuntimeError("binding mismatch with sensitive internal detail")
            stored = existing or record
            self.rows[key] = stored
        if self.lose_put_response:
            self.lose_put_response = False
            raise RuntimeError("response lost after commit with sensitive internal detail")
        return stored

    async def read(self, reference: ConnectedPayloadRef) -> EncryptedConnectedPayload | None:
        if self.malicious_read is not None:
            return self.malicious_read
        return self.rows.get(reference.payload_id)

    async def delete_once(self, reference: ConnectedPayloadRef) -> bool:
        async with self.lock:
            existing = self.rows.get(reference.payload_id)
            tombstone = self.tombstones.get(reference.payload_id)
            if (
                existing is not None
                and existing.reference.identity_sha256 != reference.identity_sha256
            ) or (tombstone is not None and tombstone != reference.identity_sha256):
                raise RuntimeError("payload identity mismatch")
            existed = self.rows.pop(reference.payload_id, None) is not None
            self.tombstones[reference.payload_id] = reference.identity_sha256
            return existed


class RandomBytes:
    def __init__(self) -> None:
        self.counter = 1

    def __call__(self, length: int) -> bytes:
        value = bytes([self.counter]) * length
        self.counter += 1
        return value


def key(name: str = "payload-key-2026-11") -> ConnectedPayloadMasterKey:
    return ConnectedPayloadMasterKey(name, bytes(range(32)))


def commitment_key() -> ConnectedPayloadCommitmentKey:
    return ConnectedPayloadCommitmentKey("payload-commitment-2026-11", b"c" * 32)


def vault(
    store: Store,
    *,
    master: ConnectedPayloadMasterKey | None = None,
    commitment_ring: dict[str, ConnectedPayloadCommitmentKey] | None = None,
    active_commitment_key_id: str | None = None,
    now: datetime = NOW,
) -> ConnectedPayloadVault:
    selected = master or key()
    default_commitment = commitment_key()
    commitments = commitment_ring or {default_commitment.key_id: default_commitment}
    active_commitment = active_commitment_key_id or default_commitment.key_id
    return ConnectedPayloadVault(
        keys={selected.key_id: selected},
        active_key_id=selected.key_id,
        commitment_keys=commitments,
        active_commitment_key_id=active_commitment,
        store=store,
        now=lambda: now,
        random_bytes=RandomBytes(),
    )


async def seal(subject: ConnectedPayloadVault) -> ConnectedPayloadRef:
    return await subject.seal_json(
        payload_id=PAYLOAD_ID,
        owner_id=OWNER_ID,
        connection_id=CONNECTION_ID,
        action_id=ACTION_ID,
        provider=ConnectorProvider.GOOGLE,
        action=ConnectorActionKind.MAIL_SEND,
        value={
            "to": ["person@example.com"],
            "subject": "Approved subject",
            "body": "Sensitive approved body",
        },
        created_at=NOW,
        expires_at=NOW + timedelta(hours=1),
    )


@pytest.mark.asyncio
async def test_seals_and_opens_only_encrypted_owner_bound_payload():
    store = Store()
    subject = vault(store)

    reference = await seal(subject)
    record = store.rows[PAYLOAD_ID]
    opened = await subject.open_json(reference)

    assert opened == {
        "body": "Sensitive approved body",
        "subject": "Approved subject",
        "to": ["person@example.com"],
    }
    assert "Sensitive approved body" not in repr(record)
    assert "person@example.com" not in repr(record)
    assert "Sensitive approved body" not in record.payload_ciphertext
    assert reference.payload_sha256 not in repr(reference)
    with pytest.raises(TypeError):
        pickle.dumps(key())
    with pytest.raises(TypeError):
        json.dumps(key())
    with pytest.raises(TypeError):
        pickle.dumps(commitment_key())


@pytest.mark.asyncio
async def test_response_loss_recovers_exact_record_and_replay_is_idempotent():
    store = Store()
    store.lose_put_response = True
    subject = vault(store)

    first = await seal(subject)
    first_binding = store.rows[PAYLOAD_ID].record_binding_sha256
    second = await seal(subject)

    assert first.binding_sha256 == second.binding_sha256
    assert store.rows[PAYLOAD_ID].record_binding_sha256 == first_binding


@pytest.mark.asyncio
async def test_concurrent_identical_seals_return_the_same_durable_record():
    store = Store()
    subject = vault(store)

    first, second = await asyncio.gather(seal(subject), seal(subject))

    assert first.binding_sha256 == second.binding_sha256
    assert tuple(store.rows) == (PAYLOAD_ID,)


class PausedPutStore(Store):
    def __init__(self) -> None:
        super().__init__()
        self.put_entered = asyncio.Event()
        self.allow_put = asyncio.Event()
        self.pending_reference: ConnectedPayloadRef | None = None

    async def put_once(self, record: EncryptedConnectedPayload) -> EncryptedConnectedPayload | None:
        self.pending_reference = record.reference
        self.put_entered.set()
        await self.allow_put.wait()
        return await super().put_once(record)


@pytest.mark.asyncio
async def test_erase_winner_tombstone_prevents_delayed_seal_resurrection():
    store = PausedPutStore()
    subject = vault(store)
    seal_task = asyncio.create_task(seal(subject))
    await store.put_entered.wait()
    reference = store.pending_reference
    assert reference is not None

    await subject.erase(reference)
    store.allow_put.set()
    with pytest.raises(ConnectedPayloadVaultError) as raised:
        await seal_task

    assert raised.value.code == "PAYLOAD_ERASED"
    assert PAYLOAD_ID not in store.rows
    assert PAYLOAD_ID in store.tombstones


@pytest.mark.asyncio
async def test_seal_winner_is_removed_and_tombstoned_by_later_erase():
    store = Store()
    subject = vault(store)
    reference = await seal(subject)

    await subject.erase(reference)

    assert PAYLOAD_ID not in store.rows
    assert PAYLOAD_ID in store.tombstones
    with pytest.raises(ConnectedPayloadVaultError) as raised:
        await seal(subject)
    assert raised.value.code == "PAYLOAD_ERASED"


@pytest.mark.asyncio
async def test_cross_owner_erase_cannot_delete_or_tombstone_existing_payload():
    store = Store()
    subject = vault(store)
    reference = await seal(subject)
    other = replace(
        reference,
        owner_id="00000000-0000-4000-8000-000000000199",
    )

    with pytest.raises(ConnectedPayloadVaultError) as raised:
        await subject.erase(other)

    assert raised.value.code == "PAYLOAD_STORE_FAILED"
    assert store.rows[PAYLOAD_ID].reference == reference
    assert PAYLOAD_ID not in store.tombstones


@pytest.mark.asyncio
async def test_cross_owner_record_substitution_fails_closed():
    store = Store()
    subject = vault(store)
    reference = await seal(subject)
    original = store.rows[PAYLOAD_ID]
    other = ConnectedPayloadRef(
        payload_id=reference.payload_id,
        owner_id=str(UUID(int=999)),
        connection_id=reference.connection_id,
        action_id=reference.action_id,
        provider=reference.provider,
        action=reference.action,
        commitment_key_id=reference.commitment_key_id,
        payload_sha256=reference.payload_sha256,
        created_at=reference.created_at,
        expires_at=reference.expires_at,
    )
    store.malicious_read = original

    with pytest.raises(ConnectedPayloadVaultError) as raised:
        await subject.open_json(other)
    assert raised.value.code == "PAYLOAD_BINDING_MISMATCH"


@pytest.mark.asyncio
async def test_ciphertext_tamper_fails_without_sensitive_error_detail():
    store = Store()
    subject = vault(store)
    reference = await seal(subject)
    record = store.rows[PAYLOAD_ID]
    object.__setattr__(record, "payload_ciphertext", "A" + record.payload_ciphertext[1:])

    with pytest.raises(ConnectedPayloadVaultError) as raised:
        await subject.open_json(reference)
    assert raised.value.code == "PAYLOAD_CORRUPT"
    assert str(raised.value) == "PAYLOAD_CORRUPT"


@pytest.mark.asyncio
async def test_missing_rotated_key_fails_closed():
    store = Store()
    original = vault(store, master=key("old-key"))
    reference = await seal(original)
    replacement = vault(store, master=ConnectedPayloadMasterKey("new-key", b"n" * 32))

    with pytest.raises(ConnectedPayloadVaultError) as raised:
        await replacement.open_json(reference)
    assert raised.value.code == "PAYLOAD_KEY_UNAVAILABLE"


@pytest.mark.asyncio
async def test_commitment_key_rotation_retains_only_explicit_old_key_access():
    store = Store()
    old = ConnectedPayloadCommitmentKey("commitment-old", b"o" * 32)
    new = ConnectedPayloadCommitmentKey("commitment-new", b"n" * 32)
    original = vault(
        store,
        commitment_ring={old.key_id: old},
        active_commitment_key_id=old.key_id,
    )
    reference = await seal(original)

    rotated = vault(
        store,
        commitment_ring={old.key_id: old, new.key_id: new},
        active_commitment_key_id=new.key_id,
    )
    assert (await rotated.open_json(reference))["subject"] == "Approved subject"
    replay = await seal(rotated)
    assert replay == reference

    retired = vault(
        store,
        commitment_ring={new.key_id: new},
        active_commitment_key_id=new.key_id,
    )
    with pytest.raises(ConnectedPayloadVaultError) as raised:
        await retired.open_json(reference)
    assert raised.value.code == "PAYLOAD_KEY_UNAVAILABLE"


@pytest.mark.asyncio
async def test_expiry_is_exclusive_and_erasure_is_idempotent():
    store = Store()
    reference = await seal(vault(store))
    expired = vault(store, now=reference.expires_at)

    with pytest.raises(ConnectedPayloadVaultError) as raised:
        await expired.open_json(reference)
    assert raised.value.code == "PAYLOAD_EXPIRED"

    active = vault(store)
    await active.erase(reference)
    await active.erase(reference)
    with pytest.raises(ConnectedPayloadVaultError) as missing:
        await active.open_json(reference)
    assert missing.value.code == "PAYLOAD_NOT_FOUND"


@pytest.mark.asyncio
async def test_non_json_and_oversized_payloads_never_reach_store():
    store = Store()
    subject = vault(store)
    common = {
        "payload_id": PAYLOAD_ID,
        "owner_id": OWNER_ID,
        "connection_id": CONNECTION_ID,
        "action_id": ACTION_ID,
        "provider": ConnectorProvider.GOOGLE,
        "action": ConnectorActionKind.MAIL_SEND,
        "created_at": NOW,
        "expires_at": NOW + timedelta(hours=1),
    }

    with pytest.raises(ConnectedPayloadVaultError) as invalid:
        await subject.seal_json(value={"bad": object()}, **common)
    assert invalid.value.code == "PAYLOAD_INVALID"

    with pytest.raises(ConnectedPayloadVaultError) as too_large:
        await subject.seal_json(value={"body": "x" * (256 * 1024)}, **common)
    assert too_large.value.code == "PAYLOAD_TOO_LARGE"
    assert store.rows == {}


@pytest.mark.asyncio
async def test_future_dated_reference_cannot_extend_retention_window():
    store = Store()
    subject = vault(store)

    with pytest.raises(ConnectedPayloadVaultError) as raised:
        await subject.seal_json(
            payload_id=PAYLOAD_ID,
            owner_id=OWNER_ID,
            connection_id=CONNECTION_ID,
            action_id=ACTION_ID,
            provider=ConnectorProvider.GOOGLE,
            action=ConnectorActionKind.MAIL_SEND,
            value={"body": "sensitive"},
            created_at=NOW + timedelta(days=30),
            expires_at=NOW + timedelta(days=31),
        )

    assert raised.value.code == "PAYLOAD_INVALID"
    assert store.rows == {}


@pytest.mark.asyncio
async def test_commitment_hides_low_entropy_payload_and_cross_owner_equality():
    first_store = Store()
    second_store = Store()
    first = vault(first_store)
    second = vault(second_store)
    payload = {"answer": "yes"}

    first_ref = await first.seal_json(
        payload_id=PAYLOAD_ID,
        owner_id=OWNER_ID,
        connection_id=CONNECTION_ID,
        action_id=ACTION_ID,
        provider=ConnectorProvider.GOOGLE,
        action=ConnectorActionKind.MAIL_SEND,
        value=payload,
        created_at=NOW,
        expires_at=NOW + timedelta(hours=1),
    )
    second_ref = await second.seal_json(
        payload_id="00000000-0000-4000-8000-000000000111",
        owner_id="00000000-0000-4000-8000-000000000112",
        connection_id="00000000-0000-4000-8000-000000000113",
        action_id="00000000-0000-4000-8000-000000000114",
        provider=ConnectorProvider.GOOGLE,
        action=ConnectorActionKind.MAIL_SEND,
        value=payload,
        created_at=NOW,
        expires_at=NOW + timedelta(hours=1),
    )
    raw_digest = (
        __import__("hashlib")
        .sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"))
        .hexdigest()
    )

    assert first_ref.payload_sha256 != raw_digest
    assert first_ref.payload_sha256 != second_ref.payload_sha256
