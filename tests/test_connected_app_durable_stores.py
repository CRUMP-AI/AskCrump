from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
import hashlib
from pathlib import Path
from uuid import UUID

import pytest

from backend.connected_app_contracts import (
    ConnectedAccountRef,
    ConnectedAuthorizationSnapshot,
    ConnectionAuthorizationState,
    ConnectorAccountKind,
    CredentialHandleRef,
)
from backend.connected_app_credential_vault import (
    ConnectedAccessTokenBroker,
    ConnectedCredentialMasterKey,
    ConnectedCredentialVault,
    EncryptedConnectedCredential,
)
from backend.connected_app_durable_stores import (
    ConnectedDurableStoreError,
    SupabaseConnectedCredentialRefreshCoordinator,
    SupabaseConnectedCredentialSecretStore,
    SupabaseConnectedPayloadStore,
)
from backend.connected_app_payload_vault import (
    ConnectedPayloadCommitmentKey,
    ConnectedPayloadMasterKey,
    ConnectedPayloadVault,
    EncryptedConnectedPayload,
)
from backend.connected_app_policy import (
    ConnectorActionKind,
    ConnectorProvider,
    ConnectorResource,
)
from backend.connected_app_provider_oauth import (
    ProviderOAuthAccessToken,
    ProviderOAuthRefreshToken,
    ProviderOAuthTokenBinding,
    ProviderOAuthTokenSet,
)


NOW = datetime(2026, 11, 7, 20, 0, tzinfo=UTC)
OWNER = "00000000-0000-4000-8000-000000001001"
CONNECTION = "00000000-0000-4000-8000-000000001002"
ACTION = "00000000-0000-4000-8000-000000001003"
PAYLOAD = "00000000-0000-4000-8000-000000001004"
INCARNATION = "00000000-0000-4000-8000-000000001005"
ACCOUNT_HASH = "a" * 64
CLIENT_HASH = "b" * 64


class RandomBytes:
    def __init__(self) -> None:
        self.value = 1

    def __call__(self, length: int) -> bytes:
        result = bytes([self.value]) * length
        self.value += 1
        return result


class PayloadCapture:
    def __init__(self) -> None:
        self.record: EncryptedConnectedPayload | None = None

    async def put_once(self, record):
        self.record = self.record or record
        return self.record

    async def read(self, _reference):
        return self.record

    async def delete_once(self, _reference):
        existed = self.record is not None
        self.record = None
        return existed


class CredentialCapture:
    def __init__(self) -> None:
        self.record: EncryptedConnectedCredential | None = None

    async def create_once(self, record):
        self.record = self.record or record
        return self.record

    async def read(self, _credential):
        return self.record

    async def replace_once(self, *, expected_record_binding_sha256, record):
        assert self.record is not None
        assert self.record.record_binding_sha256 == expected_record_binding_sha256
        self.record = record
        return record

    async def delete_once(self, *, credential, expected_record_binding_sha256):
        del credential
        assert self.record is not None
        assert self.record.record_binding_sha256 == expected_record_binding_sha256
        self.record = None
        return True


async def payload_record() -> EncryptedConnectedPayload:
    capture = PayloadCapture()
    subject = ConnectedPayloadVault(
        keys={"payload-key": ConnectedPayloadMasterKey("payload-key", b"p" * 32)},
        active_key_id="payload-key",
        commitment_keys={
            "commitment-key": ConnectedPayloadCommitmentKey("commitment-key", b"c" * 32)
        },
        active_commitment_key_id="commitment-key",
        store=capture,
        now=lambda: NOW,
        random_bytes=RandomBytes(),
    )
    await subject.seal_json(
        payload_id=PAYLOAD,
        owner_id=OWNER,
        connection_id=CONNECTION,
        action_id=ACTION,
        provider=ConnectorProvider.GOOGLE,
        action=ConnectorActionKind.MAIL_SEND,
        value={"to": ["owner@example.test"], "body": "private"},
        created_at=NOW,
        expires_at=NOW + timedelta(hours=1),
    )
    assert capture.record is not None
    return capture.record


def authorization() -> ConnectedAuthorizationSnapshot:
    return ConnectedAuthorizationSnapshot.build(
        owner_id=OWNER,
        connection_id=CONNECTION,
        provider=ConnectorProvider.GOOGLE,
        resource=ConnectorResource.MAIL,
        account_kind=ConnectorAccountKind.PERSONAL,
        revision=1,
        granted_actions=frozenset({ConnectorActionKind.MAIL_SEARCH}),
        granted_scopes=frozenset(
            {"openid", "email", "https://www.googleapis.com/auth/gmail.readonly"}
        ),
        state=ConnectionAuthorizationState.ACTIVE,
        issued_at=NOW,
        expires_at=NOW + timedelta(days=30),
    )


def credential_handle() -> CredentialHandleRef:
    return CredentialHandleRef(
        owner_id=OWNER,
        connection_id=CONNECTION,
        provider=ConnectorProvider.GOOGLE,
        handle_id="opaque-credential-handle-00000000000001",
    )


async def credential_record() -> EncryptedConnectedCredential:
    auth = authorization()
    handle = credential_handle()
    capture = CredentialCapture()
    vault = ConnectedCredentialVault(
        keys={"credential-key": ConnectedCredentialMasterKey("credential-key", b"k" * 32)},
        active_key_id="credential-key",
        store=capture,
        now=lambda: NOW,
        random_bytes=RandomBytes(),
    )
    binding = ProviderOAuthTokenBinding(
        provider=ConnectorProvider.GOOGLE,
        oauth_client_id_sha256=CLIENT_HASH,
        owner_id=OWNER,
        connection_id=CONNECTION,
        connection_incarnation_id=INCARNATION,
        account_kind=ConnectorAccountKind.PERSONAL,
    )
    await vault.create(
        credential=handle,
        connection_incarnation_id=INCARNATION,
        authorization=auth,
        external_account_id_hash=ACCOUNT_HASH,
        oauth_client_id_sha256=CLIENT_HASH,
        refresh_token=ProviderOAuthRefreshToken("refresh-" + "x" * 80, binding),
    )
    assert capture.record is not None
    return capture.record


def payload_row(record: EncryptedConnectedPayload) -> dict[str, object]:
    ref = record.reference
    return {
        "payload_id": ref.payload_id,
        "owner_id": ref.owner_id,
        "connection_id": ref.connection_id,
        "action_id": ref.action_id,
        "provider": ref.provider.value,
        "action": ref.action.value,
        "commitment_key_id": ref.commitment_key_id,
        "payload_sha256": ref.payload_sha256,
        "created_at": ref.created_at.isoformat(),
        "expires_at": ref.expires_at.isoformat(),
        "identity_sha256": ref.identity_sha256,
        "reference_binding_sha256": ref.binding_sha256,
        "key_id": record.key_id,
        "wrapped_key_nonce": record.wrapped_key_nonce,
        "wrapped_key_ciphertext": record.wrapped_key_ciphertext,
        "payload_nonce": record.payload_nonce,
        "payload_ciphertext": record.payload_ciphertext,
        "record_binding_sha256": record.record_binding_sha256,
    }


def credential_row(record: EncryptedConnectedCredential) -> dict[str, object]:
    metadata = record.metadata
    handle = metadata.credential

    return {
        "owner_id": handle.owner_id,
        "connection_id": handle.connection_id,
        "provider": handle.provider.value,
        "credential_handle_sha256": hashlib.sha256(handle.handle_id.encode()).hexdigest(),
        "connection_incarnation_id": metadata.connection_incarnation_id,
        "oauth_client_id_sha256": metadata.oauth_client_id_sha256,
        "account_kind": metadata.account_kind.value,
        "authorization_revision": metadata.authorization_revision,
        "authorization_snapshot_sha256": metadata.authorization_snapshot_sha256,
        "granted_actions_sha256": metadata.granted_actions_sha256,
        "granted_scopes_sha256": metadata.granted_scopes_sha256,
        "external_account_id_hash": metadata.external_account_id_hash,
        "authorization_expires_at": metadata.authorization_expires_at.isoformat(),
        "secret_revision": metadata.secret_revision,
        "created_at": metadata.created_at.isoformat(),
        "updated_at": metadata.updated_at.isoformat(),
        "authority_binding_sha256": metadata.authority_binding_sha256,
        "metadata_binding_sha256": metadata.binding_sha256,
        "key_id": record.key_id,
        "wrapped_key_nonce": record.wrapped_key_nonce,
        "wrapped_key_ciphertext": record.wrapped_key_ciphertext,
        "secret_nonce": record.secret_nonce,
        "secret_ciphertext": record.secret_ciphertext,
        "record_binding_sha256": record.record_binding_sha256,
    }


class MemoryRPC:
    def __init__(self) -> None:
        self.payload: dict[str, object] | None = None
        self.payload_identity: str | None = None
        self.payload_tombstone: tuple[str, bool] | None = None
        self.credential: dict[str, object] | None = None
        self.credential_tombstone: bool | None = None
        self.refresh_lease: dict[str, object] | None = None
        self.refresh_history: dict[str, tuple[str, str, str]] = {}
        self.fail_after: set[str] = set()
        self.calls: list[tuple[str, dict[str, object], bool]] = []
        self.lock = asyncio.Lock()

    async def rpc(self, name, payload, *, retry_transient=False):
        self.calls.append((name, dict(payload), retry_transient))
        async with self.lock:
            result = self._apply(name, payload)
        if name in self.fail_after:
            self.fail_after.remove(name)
            raise RuntimeError("lost response containing sensitive provider detail")
        return result

    def _apply(self, name, payload):
        if name == "connected_app_payload_put_v1":
            identity = payload["p_identity_sha256"]
            if self.payload_tombstone is not None:
                assert self.payload_tombstone[0] == identity
                return {"status": "erased", "record": None}
            if self.payload is None:
                self.payload = {key[2:]: value for key, value in payload.items()}
                self.payload_identity = identity
            assert self.payload_identity == identity
            return {"status": "present", "record": self.payload}
        if name == "connected_app_payload_read_v1":
            assert self.payload_identity in {None, payload["p_identity_sha256"]}
            if self.payload_tombstone is not None:
                return {"status": "erased", "record": None}
            if self.payload is None:
                return {"status": "absent", "record": None}
            return {"status": "present", "record": self.payload}
        if name == "connected_app_payload_reference_get_v1":
            if self.payload_tombstone is not None:
                return {"status": "erased", "reference": None}
            if self.payload is None:
                return {"status": "absent", "reference": None}
            expected = {
                "owner_id": payload["p_owner_id"],
                "payload_id": payload["p_payload_id"],
                "connection_id": payload["p_connection_id"],
                "action_id": payload["p_action_id"],
                "provider": payload["p_provider"],
                "action": payload["p_action"],
            }
            if any(self.payload[key] != value for key, value in expected.items()):
                raise RuntimeError("payload reference lookup binding mismatch")
            reference_keys = {
                "payload_id",
                "owner_id",
                "connection_id",
                "action_id",
                "provider",
                "action",
                "commitment_key_id",
                "payload_sha256",
                "created_at",
                "expires_at",
                "identity_sha256",
                "reference_binding_sha256",
            }
            return {
                "status": "present",
                "reference": {key: self.payload[key] for key in reference_keys},
            }
        if name == "connected_app_payload_delete_v1":
            existed = self.payload is not None
            identity = payload["p_identity_sha256"]
            assert self.payload_identity in {None, identity}
            if self.payload_tombstone is None:
                self.payload_tombstone = (identity, existed)
            self.payload = None
            self.payload_identity = identity
            return {
                "status": "erased",
                "record_existed": self.payload_tombstone[1],
            }
        if name == "connected_app_credential_create_v1":
            if self.credential_tombstone is not None:
                raise RuntimeError("retired")
            row = {key[2:]: value for key, value in payload.items()}
            self.credential = self.credential or row
            return {"status": "present", "record": self.credential}
        if name == "connected_app_credential_read_v1":
            if self.credential_tombstone is not None:
                return {"status": "erased", "record": None}
            if self.credential is None:
                return {"status": "absent", "record": None}
            return {"status": "present", "record": self.credential}
        if name == "connected_app_credential_replace_v1":
            assert self.credential is not None
            assert (
                self.credential["record_binding_sha256"]
                == payload["p_expected_record_binding_sha256"]
            )
            self.credential = {
                key[2:]: value
                for key, value in payload.items()
                if key != "p_expected_record_binding_sha256"
            }
            return {"status": "present", "record": self.credential}
        if name == "connected_app_credential_delete_v1":
            existed = self.credential is not None
            if existed:
                assert (
                    self.credential["record_binding_sha256"]
                    == payload["p_expected_record_binding_sha256"]
                )
            if self.credential_tombstone is None:
                self.credential_tombstone = existed
            self.credential = None
            return {
                "status": "erased",
                "record_existed": self.credential_tombstone,
            }
        if name == "connected_app_credential_claim_refresh_v2":
            retired = self.refresh_history.get(payload["p_lease_id"])
            if retired is not None:
                return {
                    "status": "stale",
                    "credential_handle_sha256": retired[0],
                    "lease_id": payload["p_lease_id"],
                    "expected_record_binding_sha256": retired[1],
                    "issued_at": NOW.isoformat(),
                    "expires_at": NOW.isoformat(),
                }
            if self.refresh_lease is not None:
                if self.refresh_lease["lease_id"] == payload["p_lease_id"]:
                    return self.refresh_lease
                return dict(self.refresh_lease) | {"status": "busy"}
            self.refresh_lease = {
                "status": "claimed",
                "credential_handle_sha256": payload["p_credential_handle_sha256"],
                "lease_id": payload["p_lease_id"],
                "expected_record_binding_sha256": payload["p_expected_record_binding_sha256"],
                "issued_at": NOW.isoformat(),
                "expires_at": (NOW + timedelta(seconds=payload["p_lease_seconds"])).isoformat(),
            }
            return self.refresh_lease
        if name == "connected_app_credential_finish_refresh_v2":
            if self.refresh_lease is not None:
                assert self.refresh_lease["lease_id"] == payload["p_lease_id"]
                self.refresh_history[payload["p_lease_id"]] = (
                    self.refresh_lease["credential_handle_sha256"],
                    self.refresh_lease["expected_record_binding_sha256"],
                    "finished",
                )
                self.refresh_lease = None
            elif payload["p_lease_id"] not in self.refresh_history:
                return {"status": "stale", "lease_id": payload["p_lease_id"]}
            return {"status": "finished", "lease_id": payload["p_lease_id"]}
        if name == "connected_app_credential_commit_refresh_v2":
            lease_id = payload["p_lease_id"]
            target_binding = payload["p_record_binding_sha256"]
            retired = self.refresh_history.get(lease_id)
            if retired is not None:
                if (
                    retired[2] == "committed"
                    and self.credential is not None
                    and self.credential["record_binding_sha256"] == target_binding
                ):
                    return {"status": "present", "record": self.credential}
                return {"status": "stale", "record": None}
            if self.refresh_lease is None or self.refresh_lease["lease_id"] != lease_id:
                return {"status": "stale", "record": None}
            assert (
                self.refresh_lease["expected_record_binding_sha256"]
                == payload["p_expected_record_binding_sha256"]
            )
            assert self.credential is not None
            assert (
                self.credential["record_binding_sha256"]
                == payload["p_expected_record_binding_sha256"]
            )
            self.credential = {
                key[2:]: value
                for key, value in payload.items()
                if key not in {"p_expected_record_binding_sha256", "p_lease_id"}
            }
            self.refresh_history[lease_id] = (
                self.refresh_lease["credential_handle_sha256"],
                self.refresh_lease["expected_record_binding_sha256"],
                "committed",
            )
            self.refresh_lease = None
            return {"status": "present", "record": self.credential}
        if name == "connected_app_credential_quarantine_refresh_v2":
            lease_id = payload["p_lease_id"]
            if self.refresh_lease is not None:
                assert self.refresh_lease["lease_id"] == lease_id
                self.refresh_history[lease_id] = (
                    self.refresh_lease["credential_handle_sha256"],
                    self.refresh_lease["expected_record_binding_sha256"],
                    "quarantined",
                )
                self.refresh_lease = None
            retired = self.refresh_history[lease_id]
            return {
                "status": "quarantined",
                "credential_handle_sha256": retired[0],
                "lease_id": lease_id,
                "expected_record_binding_sha256": retired[1],
                "quarantined_at": NOW.isoformat(),
            }
        raise AssertionError(name)


class UnavailableRPC:
    async def rpc(self, _name, _payload, *, retry_transient=False):
        assert retry_transient is True
        raise TimeoutError("provider or database detail must not escape")


class MalformedRPC:
    async def rpc(self, _name, _payload, *, retry_transient=False):
        assert retry_transient is True
        return {"status": "present", "record": None, "unexpected": True}


class DoubleLostDeleteRPC(MemoryRPC):
    def __init__(self) -> None:
        super().__init__()
        self.losses = 2

    async def rpc(self, name, payload, *, retry_transient=False):
        if name != "connected_app_payload_delete_v1" or self.losses == 0:
            return await super().rpc(name, payload, retry_transient=retry_transient)
        self.calls.append((name, dict(payload), retry_transient))
        async with self.lock:
            self._apply(name, payload)
        self.losses -= 1
        raise TimeoutError("lost erase response")


@pytest.mark.asyncio
async def test_payload_store_round_trip_tombstone_and_response_loss_readback():
    record = await payload_record()
    rpc = MemoryRPC()
    rpc.fail_after.add("connected_app_payload_put_v1")
    store = SupabaseConnectedPayloadStore(rpc)

    stored = await store.put_once(record)
    assert stored == record
    assert await store.read(record.reference) == record
    rpc.fail_after.add("connected_app_payload_delete_v1")
    assert await store.delete_once(record.reference) is True
    assert await store.read(record.reference) is None
    assert await store.put_once(record) is None
    assert all(call[2] is True for call in rpc.calls)
    rpc_surface = repr(rpc.calls)
    assert "owner@example.test" not in rpc_surface
    assert '"body": "private"' not in rpc_surface


@pytest.mark.asyncio
async def test_payload_reference_is_recovered_after_restart_and_tombstone_wins():
    record = await payload_record()
    rpc = MemoryRPC()
    writer = SupabaseConnectedPayloadStore(rpc)
    assert await writer.put_once(record) == record

    restarted_reader = SupabaseConnectedPayloadStore(rpc)
    recovered = await restarted_reader.resolve_reference(
        owner_id=record.reference.owner_id,
        payload_id=record.reference.payload_id,
        connection_id=record.reference.connection_id,
        action_id=record.reference.action_id,
        provider=record.reference.provider,
        action=record.reference.action,
    )
    assert recovered == record.reference
    assert await restarted_reader.read(recovered) == record

    with pytest.raises(ConnectedDurableStoreError) as mismatch:
        await restarted_reader.resolve_reference(
            owner_id="00000000-0000-4000-8000-000000009999",
            payload_id=record.reference.payload_id,
            connection_id=record.reference.connection_id,
            action_id=record.reference.action_id,
            provider=record.reference.provider,
            action=record.reference.action,
        )
    assert mismatch.value.code == "CONNECTED_STORE_UNAVAILABLE"

    assert await writer.delete_once(record.reference) is True
    with pytest.raises(ConnectedDurableStoreError) as retired:
        await restarted_reader.resolve_reference(
            owner_id=record.reference.owner_id,
            payload_id=record.reference.payload_id,
            connection_id=record.reference.connection_id,
            action_id=record.reference.action_id,
            provider=record.reference.provider,
            action=record.reference.action,
        )
    assert retired.value.code == "CONNECTED_STORE_TOMBSTONED"


@pytest.mark.asyncio
async def test_stores_fail_closed_on_unavailable_or_malformed_postgrest_results():
    record = await payload_record()

    with pytest.raises(ConnectedDurableStoreError) as unavailable:
        await SupabaseConnectedPayloadStore(UnavailableRPC()).read(record.reference)
    assert unavailable.value.code == "CONNECTED_STORE_UNAVAILABLE"

    with pytest.raises(ConnectedDurableStoreError) as malformed:
        await SupabaseConnectedPayloadStore(MalformedRPC()).read(record.reference)
    assert malformed.value.code == "CONNECTED_STORE_INVALID"


@pytest.mark.asyncio
async def test_double_lost_erase_response_is_ambiguous_and_never_reports_success():
    record = await payload_record()
    rpc = DoubleLostDeleteRPC()
    rpc.payload = payload_row(record)
    rpc.payload_identity = record.reference.identity_sha256
    store = SupabaseConnectedPayloadStore(rpc)

    with pytest.raises(ConnectedDurableStoreError) as ambiguous:
        await store.delete_once(record.reference)
    assert ambiguous.value.code == "CONNECTED_STORE_AMBIGUOUS"
    assert rpc.payload is None
    assert rpc.payload_tombstone == (record.reference.identity_sha256, True)


@pytest.mark.asyncio
async def test_payload_store_rejects_malformed_or_substituted_database_rows():
    record = await payload_record()
    rpc = MemoryRPC()
    rpc.payload = payload_row(record)
    rpc.payload_identity = record.reference.identity_sha256
    rpc.payload["owner_id"] = "00000000-0000-4000-8000-000000009999"
    store = SupabaseConnectedPayloadStore(rpc)

    with pytest.raises(ConnectedDurableStoreError) as raised:
        await store.read(record.reference)
    assert raised.value.code == "CONNECTED_STORE_BINDING_MISMATCH"

    rpc.payload = payload_row(record) | {"unexpected": "field"}
    with pytest.raises(ConnectedDurableStoreError) as malformed:
        await store.read(record.reference)
    assert malformed.value.code == "CONNECTED_STORE_INVALID"


@pytest.mark.asyncio
async def test_credential_store_round_trip_cas_delete_and_response_loss_readback():
    record = await credential_record()
    rpc = MemoryRPC()
    rpc.fail_after.add("connected_app_credential_create_v1")
    store = SupabaseConnectedCredentialSecretStore(rpc)

    stored = await store.create_once(record)
    assert stored == record
    assert await store.read(record.metadata.credential) == record

    rotated_metadata = record.metadata.__class__(
        credential=record.metadata.credential,
        connection_incarnation_id=record.metadata.connection_incarnation_id,
        oauth_client_id_sha256=record.metadata.oauth_client_id_sha256,
        account_kind=record.metadata.account_kind,
        authorization_revision=record.metadata.authorization_revision,
        authorization_snapshot_sha256=record.metadata.authorization_snapshot_sha256,
        granted_actions_sha256=record.metadata.granted_actions_sha256,
        granted_scopes_sha256=record.metadata.granted_scopes_sha256,
        external_account_id_hash=record.metadata.external_account_id_hash,
        authorization_expires_at=record.metadata.authorization_expires_at,
        secret_revision=2,
        created_at=record.metadata.created_at,
        updated_at=record.metadata.updated_at + timedelta(seconds=1),
    )
    partial = object.__new__(EncryptedConnectedCredential)
    object.__setattr__(partial, "metadata", rotated_metadata)
    object.__setattr__(partial, "key_id", record.key_id)
    object.__setattr__(partial, "wrapped_key_nonce", record.wrapped_key_nonce)
    object.__setattr__(partial, "wrapped_key_ciphertext", record.wrapped_key_ciphertext)
    object.__setattr__(partial, "secret_nonce", record.secret_nonce)
    object.__setattr__(partial, "secret_ciphertext", record.secret_ciphertext)
    object.__setattr__(partial, "record_binding_sha256", "0" * 64)
    rotated = EncryptedConnectedCredential(
        metadata=rotated_metadata,
        key_id=record.key_id,
        wrapped_key_nonce=record.wrapped_key_nonce,
        wrapped_key_ciphertext=record.wrapped_key_ciphertext,
        secret_nonce=record.secret_nonce,
        secret_ciphertext=record.secret_ciphertext,
        record_binding_sha256=partial.expected_binding_sha256,
    )
    rpc.fail_after.add("connected_app_credential_replace_v1")
    replaced = await store.replace_once(
        expected_record_binding_sha256=record.record_binding_sha256,
        record=rotated,
    )
    assert replaced == rotated

    rpc.fail_after.add("connected_app_credential_delete_v1")
    assert (
        await store.delete_once(
            credential=rotated.metadata.credential,
            expected_record_binding_sha256=rotated.record_binding_sha256,
        )
        is True
    )
    assert await store.read(rotated.metadata.credential) is None
    with pytest.raises(ConnectedDurableStoreError) as retired:
        await store.create_once(rotated)
    assert retired.value.code == "CONNECTED_STORE_TOMBSTONED"
    rpc_surface = repr(rpc.calls)
    assert "refresh-" not in rpc_surface
    assert "access-" not in rpc_surface


@pytest.mark.asyncio
async def test_credential_store_rejects_cross_owner_and_binding_drift():
    record = await credential_record()
    rpc = MemoryRPC()
    rpc.credential = credential_row(record)
    rpc.credential["owner_id"] = "00000000-0000-4000-8000-000000009999"
    store = SupabaseConnectedCredentialSecretStore(rpc)

    with pytest.raises(ConnectedDurableStoreError) as raised:
        await store.read(record.metadata.credential)
    assert raised.value.code == "CONNECTED_STORE_BINDING_MISMATCH"


@pytest.mark.asyncio
async def test_cross_host_refresh_lease_is_bound_busy_and_idempotently_finished():
    record = await credential_record()
    rpc = MemoryRPC()
    rpc.credential = credential_row(record)
    coordinator = SupabaseConnectedCredentialRefreshCoordinator(rpc, now=lambda: NOW)

    lease = await coordinator.claim(
        credential=record.metadata.credential,
        expected_record_binding_sha256=record.record_binding_sha256,
    )
    with pytest.raises(ConnectedDurableStoreError) as busy:
        await coordinator.claim(
            credential=record.metadata.credential,
            expected_record_binding_sha256=record.record_binding_sha256,
        )
    assert busy.value.code == "CONNECTED_STORE_BUSY"

    rpc.fail_after.add("connected_app_credential_finish_refresh_v2")
    await coordinator.finish(lease)
    assert rpc.refresh_lease is None


@pytest.mark.asyncio
async def test_refresh_claim_recovers_exact_lease_after_response_loss():
    record = await credential_record()
    rpc = MemoryRPC()
    rpc.credential = credential_row(record)
    rpc.fail_after.add("connected_app_credential_claim_refresh_v2")
    coordinator = SupabaseConnectedCredentialRefreshCoordinator(rpc, now=lambda: NOW)

    lease = await coordinator.claim(
        credential=record.metadata.credential,
        expected_record_binding_sha256=record.record_binding_sha256,
    )

    claims = [call for call in rpc.calls if call[0] == "connected_app_credential_claim_refresh_v2"]
    assert len(claims) == 2
    assert claims[0][1] == claims[1][1]
    assert lease.lease_id == claims[0][1]["p_lease_id"]
    await coordinator.finish(lease)


@pytest.mark.asyncio
async def test_cross_host_refresh_claim_race_has_exactly_one_winner():
    record = await credential_record()
    rpc = MemoryRPC()
    rpc.credential = credential_row(record)
    host_a = SupabaseConnectedCredentialRefreshCoordinator(rpc, now=lambda: NOW)
    host_b = SupabaseConnectedCredentialRefreshCoordinator(rpc, now=lambda: NOW)

    results = await asyncio.gather(
        host_a.claim(
            credential=record.metadata.credential,
            expected_record_binding_sha256=record.record_binding_sha256,
        ),
        host_b.claim(
            credential=record.metadata.credential,
            expected_record_binding_sha256=record.record_binding_sha256,
        ),
        return_exceptions=True,
    )

    leases = [item for item in results if not isinstance(item, BaseException)]
    failures = [item for item in results if isinstance(item, BaseException)]
    assert len(leases) == 1
    assert len(failures) == 1
    assert isinstance(failures[0], ConnectedDurableStoreError)
    assert failures[0].code == "CONNECTED_STORE_BUSY"
    await host_a.finish(leases[0])
    assert rpc.refresh_lease is None


@pytest.mark.asyncio
async def test_payload_put_delete_race_is_permanently_tombstoned():
    record = await payload_record()
    rpc = MemoryRPC()
    store_a = SupabaseConnectedPayloadStore(rpc)
    store_b = SupabaseConnectedPayloadStore(rpc)

    results = await asyncio.gather(
        store_a.put_once(record),
        store_b.delete_once(record.reference),
    )

    assert results[0] in {None, record}
    assert results[1] in {False, True}
    assert await store_a.read(record.reference) is None
    assert await store_b.put_once(record) is None
    assert rpc.payload_tombstone is not None


@pytest.mark.asyncio
async def test_credential_create_delete_race_cannot_resurrect_handle():
    record = await credential_record()
    rpc = MemoryRPC()
    store_a = SupabaseConnectedCredentialSecretStore(rpc)
    store_b = SupabaseConnectedCredentialSecretStore(rpc)

    results = await asyncio.gather(
        store_a.create_once(record),
        store_b.delete_once(
            credential=record.metadata.credential,
            expected_record_binding_sha256=record.record_binding_sha256,
        ),
        return_exceptions=True,
    )

    assert sum(isinstance(item, EncryptedConnectedCredential) for item in results) <= 1
    assert rpc.credential is None
    assert rpc.credential_tombstone is not None
    with pytest.raises(ConnectedDurableStoreError) as retired:
        await store_a.create_once(record)
    assert retired.value.code == "CONNECTED_STORE_TOMBSTONED"


@pytest.mark.asyncio
async def test_access_token_broker_holds_durable_refresh_lease_during_provider_rotation():
    record = await credential_record()
    rpc = MemoryRPC()
    rpc.credential = credential_row(record)
    store = SupabaseConnectedCredentialSecretStore(rpc)
    vault = ConnectedCredentialVault(
        keys={"credential-key": ConnectedCredentialMasterKey("credential-key", b"k" * 32)},
        active_key_id="credential-key",
        store=store,
        now=lambda: NOW,
        random_bytes=RandomBytes(),
    )
    coordinator = SupabaseConnectedCredentialRefreshCoordinator(rpc, now=lambda: NOW)
    rpc.fail_after.add("connected_app_credential_commit_refresh_v2")

    class Client:
        def __init__(self, provider):
            self.provider = provider

        async def refresh(self, *, refresh_token, expected_scopes, binding):
            assert rpc.refresh_lease is not None
            return ProviderOAuthTokenSet(
                provider=self.provider,
                access_token=ProviderOAuthAccessToken("access-" + "z" * 64, binding),
                refresh_token=ProviderOAuthRefreshToken("refresh-" + "n" * 80, binding),
                granted_scopes=expected_scopes,
                issued_at=NOW,
                expires_at=NOW + timedelta(hours=1),
            )

    broker = ConnectedAccessTokenBroker(
        vault=vault,
        clients={
            ConnectorProvider.GOOGLE: Client(ConnectorProvider.GOOGLE),
            ConnectorProvider.MICROSOFT: Client(ConnectorProvider.MICROSOFT),
        },
        refresh_coordinator=coordinator,
        now=lambda: NOW,
    )
    account = ConnectedAccountRef(
        owner_id=OWNER,
        connection_id=CONNECTION,
        provider=ConnectorProvider.GOOGLE,
        resource=ConnectorResource.MAIL,
        account_kind=ConnectorAccountKind.PERSONAL,
        external_account_id_hash=ACCOUNT_HASH,
    )
    source = broker.bind(
        account=account,
        credential=record.metadata.credential,
        connection_incarnation_id=INCARNATION,
        authorization=authorization(),
        hard_expires_at=NOW + timedelta(minutes=10),
    )

    token = await source.issue_access_token(
        account=account,
        credential=record.metadata.credential,
    )

    assert token.expires_at == NOW + timedelta(minutes=10)
    assert rpc.refresh_lease is None
    names = [call[0] for call in rpc.calls]
    assert "connected_app_credential_claim_refresh_v2" in names
    assert "connected_app_credential_commit_refresh_v2" in names
    assert "connected_app_credential_finish_refresh_v2" not in names
    commits = [call for call in rpc.calls if call[0] == "connected_app_credential_commit_refresh_v2"]
    assert len(commits) == 2
    assert commits[0][1] == commits[1][1]
    assert len(rpc.refresh_history) == 1


@pytest.mark.asyncio
async def test_retired_refresh_lease_id_cannot_be_reclaimed_after_response_loss(monkeypatch):
    record = await credential_record()
    rpc = MemoryRPC()
    rpc.credential = credential_row(record)
    retired_id = "10000000-0000-4000-8000-000000000099"
    handle_hash = hashlib.sha256(record.metadata.credential.handle_id.encode()).hexdigest()
    rpc.refresh_history[retired_id] = (
        handle_hash,
        record.record_binding_sha256,
        "expired",
    )
    monkeypatch.setattr(
        "backend.connected_app_durable_stores.uuid4",
        lambda: UUID(retired_id),
    )
    coordinator = SupabaseConnectedCredentialRefreshCoordinator(rpc, now=lambda: NOW)

    with pytest.raises(ConnectedDurableStoreError) as stale:
        await coordinator.claim(
            credential=record.metadata.credential,
            expected_record_binding_sha256=record.record_binding_sha256,
        )

    assert stale.value.code == "CONNECTED_STORE_TOMBSTONED"
    assert rpc.refresh_lease is None


def test_forward_migration_has_private_encrypted_stores_and_exact_rpc_boundary():
    sql = Path("migrations/20261107230000_connected_app_secret_payload_stores.sql").read_text(
        encoding="utf-8"
    )
    normalized = " ".join(sql.casefold().split())

    for table in (
        "payload_envelopes",
        "payload_tombstones",
        "credential_envelopes",
        "credential_refresh_quarantines",
        "credential_secret_tombstones",
        "credential_refresh_leases",
    ):
        assert f"create table if not exists connected_app_private.{table}" in normalized
        assert f"alter table connected_app_private.{table} enable row level security" in normalized
        assert f"alter table connected_app_private.{table} force row level security" in normalized
    for function in (
        "connected_app_payload_put_v1",
        "connected_app_payload_read_v1",
        "connected_app_payload_delete_v1",
        "connected_app_payload_reference_get_v1",
        "connected_app_credential_create_v1",
        "connected_app_credential_read_v1",
        "connected_app_credential_replace_v1",
        "connected_app_credential_delete_v1",
        "connected_app_credential_claim_refresh_v1",
        "connected_app_credential_quarantine_refresh_v1",
        "connected_app_credential_finish_refresh_v1",
    ):
        assert f"create or replace function public.{function}" in normalized
    assert "security definer set search_path = ''" in normalized
    assert "grant execute on function" in normalized
    assert "to service_role" in normalized
    assert "permanent_content_free" in normalized
    assert "permanent_unlinked" in normalized
    assert "access_token" not in normalized
    assert "refresh_token" not in normalized
    assert "oauth_state" not in normalized
    assert "pkce_verifier" not in normalized
    assert "target_binding_sha256" not in normalized
    assert "preview_sha256" not in normalized
    assert "e7ca1fb4ad5cd5be19109ceae76a1b19535bd3b05d2d7750e49be8b86ee48678" in normalized
    assert "8052016e79f8049ccdab9785409c7820" in normalized
    assert "credential_retire_after_connection_update_v1" in normalized
    assert "create index if not exists connected_payload_action_fk_idx" in normalized
    assert "f250e5f3e93732daabde65b3e3942f71" in normalized
    assert "partial or drifted connected-app encrypted-store target; refusing repair" in normalized


def test_durable_store_contract_pins_keyed_commitments_and_release_blockers():
    contract = Path("docs/CONNECTED_APP_DURABLE_SECRET_STORES_2026-11-07.md").read_text(
        encoding="utf-8"
    )
    normalized = " ".join(contract.casefold().split())

    assert "only request-parameter commitment permitted in sql" in normalized
    assert "requesttargetbindingsha256" in normalized
    assert "all three fields are inside aes-gcm ciphertext" in normalized
    assert "keyed preview commitment" in normalized
    assert "after process restart" in normalized
    assert "host clocks do not decide" in normalized
    assert "oauth state, pkce, and provisional credential custody" in normalized
    assert "writes its refresh token directly into provisional encrypted custody" in normalized
    assert "provider revocation" in normalized
    assert "permanently quarantines the exact credential generation" in normalized
    assert "provider-result reconciliation" in normalized
