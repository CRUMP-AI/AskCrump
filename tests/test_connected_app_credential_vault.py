from __future__ import annotations

import asyncio
import pickle
from datetime import UTC, datetime, timedelta
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
    ConnectedCredentialVaultError,
    EncryptedConnectedCredential,
)
from backend.connected_app_policy import (
    ConnectorActionKind,
    ConnectorProvider,
    ConnectorResource,
)
from backend.connected_app_provider_oauth import (
    ProviderOAuthAccessToken,
    ProviderOAuthEffectUnknown,
    ProviderOAuthRefreshToken,
    ProviderOAuthTokenBinding,
    ProviderOAuthTokenSet,
)


NOW = datetime(2026, 11, 7, 20, 0, tzinfo=UTC)
OWNER_ID = "00000000-0000-4000-8000-000000000301"
CONNECTION_ID = "00000000-0000-4000-8000-000000000302"
INCARNATION_ID = "00000000-0000-4000-8000-000000000303"
ACCOUNT_HASH = "a" * 64
OAUTH_CLIENT_HASH = "c" * 64
SCOPES = frozenset(
    {
        "email",
        "openid",
        "https://www.googleapis.com/auth/gmail.readonly",
    }
)


class Store:
    def __init__(self) -> None:
        self.rows: dict[str, EncryptedConnectedCredential] = {}
        self.lose_create_response = False
        self.lose_replace_response = False
        self.lose_delete_response = False
        self.refuse_delete = False

    async def create_once(
        self,
        record: EncryptedConnectedCredential,
    ) -> EncryptedConnectedCredential:
        key = record.metadata.credential.handle_id
        existing = self.rows.get(key)
        if existing is not None and existing.record_binding_sha256 != record.record_binding_sha256:
            raise RuntimeError("binding drift with secret provider detail")
        self.rows[key] = record
        if self.lose_create_response:
            self.lose_create_response = False
            raise RuntimeError("response lost after commit with secret provider detail")
        return record

    async def read(
        self,
        credential: CredentialHandleRef,
    ) -> EncryptedConnectedCredential | None:
        return self.rows.get(credential.handle_id)

    async def replace_once(
        self,
        *,
        expected_record_binding_sha256: str,
        record: EncryptedConnectedCredential,
    ) -> EncryptedConnectedCredential:
        key = record.metadata.credential.handle_id
        existing = self.rows.get(key)
        if existing is None or existing.record_binding_sha256 != expected_record_binding_sha256:
            raise RuntimeError("stale CAS with secret provider detail")
        self.rows[key] = record
        if self.lose_replace_response:
            self.lose_replace_response = False
            raise RuntimeError("response lost after CAS with secret provider detail")
        return record

    async def delete_once(
        self,
        *,
        credential: CredentialHandleRef,
        expected_record_binding_sha256: str,
    ) -> bool:
        existing = self.rows.get(credential.handle_id)
        if existing is None:
            return False
        if existing.record_binding_sha256 != expected_record_binding_sha256:
            raise RuntimeError("stale delete with secret provider detail")
        if not self.refuse_delete:
            del self.rows[credential.handle_id]
        if self.lose_delete_response:
            self.lose_delete_response = False
            raise RuntimeError("response lost after delete with secret provider detail")
        return True


class RandomBytes:
    def __init__(self) -> None:
        self.counter = 1

    def __call__(self, length: int) -> bytes:
        value = bytes([self.counter]) * length
        self.counter += 1
        return value


class OAuthClient:
    def __init__(
        self,
        provider: ConnectorProvider,
        *,
        rotated_refresh: str | None = None,
        returned_scopes: frozenset[str] | None = None,
    ) -> None:
        self.provider = provider
        self.rotated_refresh = rotated_refresh
        self.returned_scopes = returned_scopes
        self.calls = 0

    async def refresh(self, *, refresh_token, expected_scopes, binding):
        self.calls += 1
        await asyncio.sleep(0)
        return ProviderOAuthTokenSet(
            provider=self.provider,
            access_token=ProviderOAuthAccessToken("access-" + "x" * 64, binding),
            refresh_token=(
                ProviderOAuthRefreshToken(self.rotated_refresh, binding)
                if self.rotated_refresh
                else refresh_token
            ),
            granted_scopes=self.returned_scopes or expected_scopes,
            issued_at=NOW,
            expires_at=NOW + timedelta(hours=1),
        )


class PausingOAuthClient(OAuthClient):
    def __init__(self, provider: ConnectorProvider) -> None:
        super().__init__(
            provider,
            rotated_refresh="race-rotated-" + "v" * 64,
        )
        self.started = asyncio.Event()
        self.proceed = asyncio.Event()

    async def refresh(self, *, refresh_token, expected_scopes, binding):
        self.started.set()
        await self.proceed.wait()
        return await super().refresh(
            refresh_token=refresh_token,
            expected_scopes=expected_scopes,
            binding=binding,
        )


class PausingDeleteStore(Store):
    def __init__(self) -> None:
        super().__init__()
        self.delete_started = asyncio.Event()
        self.proceed_delete = asyncio.Event()

    async def delete_once(
        self,
        *,
        credential: CredentialHandleRef,
        expected_record_binding_sha256: str,
    ) -> bool:
        self.delete_started.set()
        await self.proceed_delete.wait()
        return await super().delete_once(
            credential=credential,
            expected_record_binding_sha256=expected_record_binding_sha256,
        )


class EffectUnknownOAuthClient(OAuthClient):
    async def refresh(self, *, refresh_token, expected_scopes, binding):
        self.calls += 1
        raise ProviderOAuthEffectUnknown()


class RefreshCoordinator:
    def __init__(self) -> None:
        self.claims: list[tuple[CredentialHandleRef, str, timedelta]] = []
        self.finished: list[object] = []
        self.quarantined: list[object] = []
        self.committed: list[tuple[object, EncryptedConnectedCredential]] = []

    async def claim(
        self,
        *,
        credential: CredentialHandleRef,
        expected_record_binding_sha256: str,
        lease_for: timedelta,
    ) -> object:
        lease = object()
        self.claims.append((credential, expected_record_binding_sha256, lease_for))
        return lease

    async def finish(self, lease: object) -> None:
        self.finished.append(lease)

    async def quarantine(self, lease: object) -> None:
        self.quarantined.append(lease)

    async def commit_rotation(
        self,
        *,
        lease: object,
        record: EncryptedConnectedCredential,
    ) -> EncryptedConnectedCredential:
        self.committed.append((lease, record))
        return record


def authorization() -> ConnectedAuthorizationSnapshot:
    return ConnectedAuthorizationSnapshot.build(
        owner_id=OWNER_ID,
        connection_id=CONNECTION_ID,
        provider=ConnectorProvider.GOOGLE,
        resource=ConnectorResource.MAIL,
        account_kind=ConnectorAccountKind.PERSONAL,
        revision=3,
        granted_actions=frozenset({ConnectorActionKind.MAIL_SEARCH}),
        granted_scopes=SCOPES,
        state=ConnectionAuthorizationState.ACTIVE,
        issued_at=NOW - timedelta(minutes=5),
        expires_at=NOW + timedelta(days=30),
    )


def account(*, external_hash: str = ACCOUNT_HASH) -> ConnectedAccountRef:
    return ConnectedAccountRef(
        owner_id=OWNER_ID,
        connection_id=CONNECTION_ID,
        provider=ConnectorProvider.GOOGLE,
        resource=ConnectorResource.MAIL,
        account_kind=ConnectorAccountKind.PERSONAL,
        external_account_id_hash=external_hash,
    )


def credential(
    *,
    owner_id: str = OWNER_ID,
    handle_id: str = "opaque-broker-handle-0000000000000001",
) -> CredentialHandleRef:
    return CredentialHandleRef(
        owner_id=owner_id,
        connection_id=CONNECTION_ID,
        provider=ConnectorProvider.GOOGLE,
        handle_id=handle_id,
    )


def flow_binding() -> ProviderOAuthTokenBinding:
    return ProviderOAuthTokenBinding(
        provider=ConnectorProvider.GOOGLE,
        oauth_client_id_sha256=OAUTH_CLIENT_HASH,
        owner_id=OWNER_ID,
        connection_id=CONNECTION_ID,
        connection_incarnation_id=INCARNATION_ID,
        account_kind=ConnectorAccountKind.PERSONAL,
    )


def master(key_id: str = "credential-key-2026-11") -> ConnectedCredentialMasterKey:
    return ConnectedCredentialMasterKey(key_id, bytes(range(32)))


def vault(
    store: Store,
    *,
    selected: ConnectedCredentialMasterKey | None = None,
    now: datetime = NOW,
) -> ConnectedCredentialVault:
    key = selected or master()
    return ConnectedCredentialVault(
        keys={key.key_id: key},
        active_key_id=key.key_id,
        store=store,
        now=lambda: now,
        random_bytes=RandomBytes(),
    )


async def create(subject: ConnectedCredentialVault):
    return await subject.create(
        credential=credential(),
        connection_incarnation_id=INCARNATION_ID,
        authorization=authorization(),
        external_account_id_hash=ACCOUNT_HASH,
        oauth_client_id_sha256=OAUTH_CLIENT_HASH,
        refresh_token=ProviderOAuthRefreshToken(
            "refresh-" + "r" * 64,
            flow_binding(),
        ),
    )


@pytest.mark.asyncio
async def test_refresh_token_is_encrypted_redacted_and_exactly_bound():
    store = Store()
    subject = vault(store)

    record = await create(subject)
    opened = await subject.open(
        account=account(),
        credential=credential(),
        connection_incarnation_id=INCARNATION_ID,
        authorization=authorization(),
    )

    assert "refresh-" not in record.secret_ciphertext
    assert "refresh-" not in repr(record)
    assert "refresh-" not in repr(opened)
    assert opened.refresh_token._reveal() == "refresh-" + "r" * 64
    assert opened.granted_scopes == SCOPES
    assert record.metadata.authorization_snapshot_sha256 == authorization().snapshot_sha256
    assert record.metadata.granted_actions_sha256 == authorization().granted_actions_sha256
    assert record.metadata.oauth_client_id_sha256 == OAUTH_CLIENT_HASH
    assert record.metadata.account_kind is ConnectorAccountKind.PERSONAL
    assert opened.refresh_token.binding.persisted
    assert opened.refresh_token.binding.credential_handle_sha256 is not None
    assert opened.refresh_token.binding.external_account_id_hash == ACCOUNT_HASH
    with pytest.raises(TypeError):
        pickle.dumps(master())
    with pytest.raises(AttributeError):
        master()._key = b"x" * 32


@pytest.mark.asyncio
async def test_create_response_loss_recovers_exact_ciphertext_and_replay_does_not_replace():
    store = Store()
    store.lose_create_response = True
    subject = vault(store)

    first = await create(subject)
    first_binding = first.record_binding_sha256
    second = await create(vault(store, now=NOW + timedelta(minutes=5)))

    assert second.record_binding_sha256 == first_binding
    assert store.rows[credential().handle_id].record_binding_sha256 == first_binding


@pytest.mark.asyncio
async def test_owner_account_or_authorization_substitution_fails_closed():
    store = Store()
    subject = vault(store)
    await create(subject)

    with pytest.raises(ConnectedCredentialVaultError) as account_mismatch:
        await subject.open(
            account=account(external_hash="b" * 64),
            credential=credential(),
            connection_incarnation_id=INCARNATION_ID,
            authorization=authorization(),
        )
    assert account_mismatch.value.code == "CREDENTIAL_AUTHORITY_MISMATCH"

    with pytest.raises(ConnectedCredentialVaultError) as owner_mismatch:
        await subject.open(
            account=account(),
            credential=credential(owner_id=str(UUID(int=999))),
            connection_incarnation_id=INCARNATION_ID,
            authorization=authorization(),
        )
    assert owner_mismatch.value.code == "CREDENTIAL_AUTHORITY_MISMATCH"

    expanded = ConnectedAuthorizationSnapshot.build(
        owner_id=OWNER_ID,
        connection_id=CONNECTION_ID,
        provider=ConnectorProvider.GOOGLE,
        resource=ConnectorResource.MAIL,
        account_kind=ConnectorAccountKind.PERSONAL,
        revision=4,
        granted_actions=frozenset(
            {ConnectorActionKind.MAIL_SEARCH, ConnectorActionKind.MAIL_REPLY}
        ),
        granted_scopes=SCOPES,
        state=ConnectionAuthorizationState.ACTIVE,
        issued_at=NOW - timedelta(minutes=1),
        expires_at=NOW + timedelta(days=30),
    )
    with pytest.raises(ConnectedCredentialVaultError) as revision_mismatch:
        await subject.open(
            account=account(),
            credential=credential(),
            connection_incarnation_id=INCARNATION_ID,
            authorization=expanded,
        )
    assert revision_mismatch.value.code == "CREDENTIAL_AUTHORITY_MISMATCH"

    with pytest.raises(ConnectedCredentialVaultError) as incarnation_mismatch:
        await subject.open(
            account=account(),
            credential=credential(),
            connection_incarnation_id=str(UUID(int=998)),
            authorization=authorization(),
        )
    assert incarnation_mismatch.value.code == "CREDENTIAL_AUTHORITY_MISMATCH"


@pytest.mark.parametrize(
    ("provider", "client_hash", "account_kind"),
    [
        (ConnectorProvider.MICROSOFT, OAUTH_CLIENT_HASH, ConnectorAccountKind.PERSONAL),
        (ConnectorProvider.GOOGLE, "d" * 64, ConnectorAccountKind.PERSONAL),
        (ConnectorProvider.GOOGLE, OAUTH_CLIENT_HASH, ConnectorAccountKind.WORK_SCHOOL),
    ],
    ids=("provider", "client", "account-kind"),
)
@pytest.mark.asyncio
async def test_create_rejects_cross_provenance_token_substitution(
    provider: ConnectorProvider,
    client_hash: str,
    account_kind: ConnectorAccountKind,
):
    store = Store()
    subject = vault(store)
    bad_binding = ProviderOAuthTokenBinding(
        provider=provider,
        oauth_client_id_sha256=client_hash,
        owner_id=OWNER_ID,
        connection_id=CONNECTION_ID,
        connection_incarnation_id=INCARNATION_ID,
        account_kind=account_kind,
    )

    with pytest.raises(ConnectedCredentialVaultError) as mismatch:
        await subject.create(
            credential=credential(),
            connection_incarnation_id=INCARNATION_ID,
            authorization=authorization(),
            external_account_id_hash=ACCOUNT_HASH,
            oauth_client_id_sha256=OAUTH_CLIENT_HASH,
            refresh_token=ProviderOAuthRefreshToken(
                "refresh-" + "r" * 64,
                bad_binding,
            ),
        )
    assert mismatch.value.code == "CREDENTIAL_AUTHORITY_MISMATCH"
    assert store.rows == {}


@pytest.mark.asyncio
async def test_ciphertext_tamper_and_missing_rotation_key_fail_content_free():
    store = Store()
    subject = vault(store)
    record = await create(subject)
    object.__setattr__(record, "secret_ciphertext", "A" + record.secret_ciphertext[1:])

    with pytest.raises(ConnectedCredentialVaultError) as corrupt:
        await subject.open(
            account=account(),
            credential=credential(),
            connection_incarnation_id=INCARNATION_ID,
            authorization=authorization(),
        )
    assert corrupt.value.code == "CREDENTIAL_CORRUPT"
    assert str(corrupt.value) == "CREDENTIAL_CORRUPT"

    # Restore a clean record and prove an old key must remain available during rotation.
    store = Store()
    old = vault(store, selected=master("old-key"))
    await create(old)
    replacement = vault(
        store,
        selected=ConnectedCredentialMasterKey("new-key", b"n" * 32),
    )
    with pytest.raises(ConnectedCredentialVaultError) as missing_key:
        await replacement.open(
            account=account(),
            credential=credential(),
            connection_incarnation_id=INCARNATION_ID,
            authorization=authorization(),
        )
    assert missing_key.value.code == "CREDENTIAL_KEY_UNAVAILABLE"


@pytest.mark.asyncio
async def test_old_master_key_is_readable_and_rewrapped_under_active_key_on_refresh():
    store = Store()
    old_key = master("old-key")
    new_key = ConnectedCredentialMasterKey("new-key", b"n" * 32)
    old = vault(store, selected=old_key)
    await create(old)
    rotating = ConnectedCredentialVault(
        keys={old_key.key_id: old_key, new_key.key_id: new_key},
        active_key_id=new_key.key_id,
        store=store,
        now=lambda: NOW,
        random_bytes=RandomBytes(),
    )
    opened = await rotating.open(
        account=account(),
        credential=credential(),
        connection_incarnation_id=INCARNATION_ID,
        authorization=authorization(),
    )
    assert opened.record.key_id == old_key.key_id
    google = OAuthClient(ConnectorProvider.GOOGLE)
    broker = ConnectedAccessTokenBroker(
        vault=rotating,
        clients=clients(google),
        now=lambda: NOW,
    )
    source = broker.bind(
        account=account(),
        credential=credential(),
        connection_incarnation_id=INCARNATION_ID,
        authorization=authorization(),
        hard_expires_at=NOW + timedelta(minutes=10),
    )

    await source.issue_access_token(account=account(), credential=credential())

    assert store.rows[credential().handle_id].key_id == new_key.key_id
    assert store.rows[credential().handle_id].metadata.secret_revision == 2


@pytest.mark.asyncio
async def test_rotated_refresh_token_uses_cas_and_response_loss_readback():
    store = Store()
    subject = vault(store)
    await create(subject)
    current = await subject.open(
        account=account(),
        credential=credential(),
        connection_incarnation_id=INCARNATION_ID,
        authorization=authorization(),
    )
    store.lose_replace_response = True

    rotated = await subject.rotate(
        current,
        ProviderOAuthRefreshToken(
            "rotated-" + "z" * 64,
            current.refresh_token.binding,
        ),
    )
    opened = await subject.open(
        account=account(),
        credential=credential(),
        connection_incarnation_id=INCARNATION_ID,
        authorization=authorization(),
    )

    assert rotated.metadata.secret_revision == 2
    assert opened.refresh_token._reveal() == "rotated-" + "z" * 64


@pytest.mark.asyncio
async def test_erase_is_idempotent_and_confirms_secret_is_gone():
    store = Store()
    subject = vault(store)
    await create(subject)

    with pytest.raises(ConnectedCredentialVaultError) as wrong_account:
        await subject.erase(
            account=account(external_hash="b" * 64),
            credential=credential(),
            connection_incarnation_id=INCARNATION_ID,
        )
    assert wrong_account.value.code == "CREDENTIAL_AUTHORITY_MISMATCH"
    assert credential().handle_id in store.rows

    await subject.erase(
        account=account(),
        credential=credential(),
        connection_incarnation_id=INCARNATION_ID,
    )
    await subject.erase(
        account=account(),
        credential=credential(),
        connection_incarnation_id=INCARNATION_ID,
    )
    with pytest.raises(ConnectedCredentialVaultError) as missing:
        await subject.open(
            account=account(),
            credential=credential(),
            connection_incarnation_id=INCARNATION_ID,
            authorization=authorization(),
        )
    assert missing.value.code == "CREDENTIAL_NOT_FOUND"

    await create(subject)
    store.lose_delete_response = True
    await subject.erase(
        account=account(),
        credential=credential(),
        connection_incarnation_id=INCARNATION_ID,
    )
    assert store.rows == {}

    await create(subject)
    store.refuse_delete = True
    with pytest.raises(ConnectedCredentialVaultError) as refused:
        await subject.erase(
            account=account(),
            credential=credential(),
            connection_incarnation_id=INCARNATION_ID,
        )
    assert refused.value.code == "CREDENTIAL_STORE_FAILED"


def clients(google: OAuthClient) -> dict[ConnectorProvider, OAuthClient]:
    return {
        ConnectorProvider.GOOGLE: google,
        ConnectorProvider.MICROSOFT: OAuthClient(ConnectorProvider.MICROSOFT),
    }


@pytest.mark.asyncio
async def test_bound_source_is_one_use_and_cache_prevents_duplicate_refresh():
    store = Store()
    subject = vault(store)
    await create(subject)
    google = OAuthClient(ConnectorProvider.GOOGLE)
    broker = ConnectedAccessTokenBroker(
        vault=subject,
        clients=clients(google),
        now=lambda: NOW,
    )

    first_source = broker.bind(
        account=account(),
        credential=credential(),
        connection_incarnation_id=INCARNATION_ID,
        authorization=authorization(),
        hard_expires_at=NOW + timedelta(minutes=10),
    )
    first = await first_source.issue_access_token(
        account=account(),
        credential=credential(),
    )
    assert first.expires_at == NOW + timedelta(minutes=10)
    assert (
        first.reveal_for_transport(
            account=account(),
            credential=credential(),
            now=NOW,
        )
        == "access-" + "x" * 64
    )
    persisted = pickle.dumps(store.rows[credential().handle_id])
    assert b"access-" not in persisted
    assert b"refresh-" not in persisted
    with pytest.raises(ConnectedCredentialVaultError) as reused:
        await first_source.issue_access_token(account=account(), credential=credential())
    assert reused.value.code == "CREDENTIAL_AUTHORITY_MISMATCH"

    second_source = broker.bind(
        account=account(),
        credential=credential(),
        connection_incarnation_id=INCARNATION_ID,
        authorization=authorization(),
        hard_expires_at=NOW + timedelta(minutes=10),
    )
    await second_source.issue_access_token(account=account(), credential=credential())
    assert google.calls == 1


@pytest.mark.asyncio
async def test_concurrent_sources_share_one_refresh_and_persist_rotation():
    store = Store()
    subject = vault(store)
    await create(subject)
    google = OAuthClient(
        ConnectorProvider.GOOGLE,
        rotated_refresh="rotated-by-provider-" + "q" * 64,
    )
    broker = ConnectedAccessTokenBroker(
        vault=subject,
        clients=clients(google),
        now=lambda: NOW,
    )
    sources = [
        broker.bind(
            account=account(),
            credential=credential(),
            connection_incarnation_id=INCARNATION_ID,
            authorization=authorization(),
            hard_expires_at=NOW + timedelta(minutes=10),
        )
        for _ in range(2)
    ]

    await asyncio.gather(
        *[
            source.issue_access_token(account=account(), credential=credential())
            for source in sources
        ]
    )
    opened = await subject.open(
        account=account(),
        credential=credential(),
        connection_incarnation_id=INCARNATION_ID,
        authorization=authorization(),
    )
    assert google.calls == 1
    assert opened.record.metadata.secret_revision == 2
    assert opened.refresh_token._reveal() == "rotated-by-provider-" + "q" * 64


@pytest.mark.asyncio
async def test_cache_invalidates_on_credential_rotation_and_erase():
    store = Store()
    subject = vault(store)
    await create(subject)
    google = OAuthClient(ConnectorProvider.GOOGLE)
    broker = ConnectedAccessTokenBroker(
        vault=subject,
        clients=clients(google),
        now=lambda: NOW,
    )

    async def issue_once():
        source = broker.bind(
            account=account(),
            credential=credential(),
            connection_incarnation_id=INCARNATION_ID,
            authorization=authorization(),
            hard_expires_at=NOW + timedelta(minutes=10),
        )
        return await source.issue_access_token(
            account=account(),
            credential=credential(),
        )

    await issue_once()
    current = await subject.open(
        account=account(),
        credential=credential(),
        connection_incarnation_id=INCARNATION_ID,
        authorization=authorization(),
    )
    await subject.rotate(
        current,
        ProviderOAuthRefreshToken(
            "out-of-band-rotated-" + "o" * 64,
            current.refresh_token.binding,
        ),
    )
    await issue_once()
    assert google.calls == 2

    await subject.erase(
        account=account(),
        credential=credential(),
        connection_incarnation_id=INCARNATION_ID,
    )
    with pytest.raises(ConnectedCredentialVaultError) as erased:
        await issue_once()
    assert erased.value.code == "CREDENTIAL_NOT_FOUND"
    assert google.calls == 2


@pytest.mark.asyncio
async def test_erase_wins_refresh_race_without_credential_resurrection():
    store = Store()
    subject = vault(store)
    await create(subject)
    google = PausingOAuthClient(ConnectorProvider.GOOGLE)
    broker = ConnectedAccessTokenBroker(
        vault=subject,
        clients=clients(google),
        now=lambda: NOW,
    )
    source = broker.bind(
        account=account(),
        credential=credential(),
        connection_incarnation_id=INCARNATION_ID,
        authorization=authorization(),
        hard_expires_at=NOW + timedelta(minutes=10),
    )
    issue = asyncio.create_task(
        source.issue_access_token(account=account(), credential=credential())
    )
    await google.started.wait()

    await subject.erase(
        account=account(),
        credential=credential(),
        connection_incarnation_id=INCARNATION_ID,
    )
    google.proceed.set()

    with pytest.raises(ConnectedCredentialVaultError) as lost_race:
        await issue
    assert lost_race.value.code == "CREDENTIAL_STORE_FAILED"
    assert store.rows == {}


@pytest.mark.asyncio
async def test_refresh_wins_erase_race_and_stale_delete_fails_closed():
    store = PausingDeleteStore()
    subject = vault(store)
    await create(subject)
    google = OAuthClient(
        ConnectorProvider.GOOGLE,
        rotated_refresh="refresh-winner-" + "w" * 64,
    )
    broker = ConnectedAccessTokenBroker(
        vault=subject,
        clients=clients(google),
        now=lambda: NOW,
    )
    erase = asyncio.create_task(
        subject.erase(
            account=account(),
            credential=credential(),
            connection_incarnation_id=INCARNATION_ID,
        )
    )
    await store.delete_started.wait()
    source = broker.bind(
        account=account(),
        credential=credential(),
        connection_incarnation_id=INCARNATION_ID,
        authorization=authorization(),
        hard_expires_at=NOW + timedelta(minutes=10),
    )

    await source.issue_access_token(account=account(), credential=credential())
    store.proceed_delete.set()

    with pytest.raises(ConnectedCredentialVaultError) as stale_delete:
        await erase
    assert stale_delete.value.code == "CREDENTIAL_STORE_FAILED"
    assert store.rows[credential().handle_id].metadata.secret_revision == 2

    await subject.erase(
        account=account(),
        credential=credential(),
        connection_incarnation_id=INCARNATION_ID,
    )
    assert store.rows == {}


@pytest.mark.asyncio
async def test_lock_and_cache_bounds_allow_sequential_credential_churn():
    store = Store()
    subject = vault(store)
    await create(subject)
    second_credential = credential(handle_id="opaque-broker-handle-0000000000000002")
    await subject.create(
        credential=second_credential,
        connection_incarnation_id=INCARNATION_ID,
        authorization=authorization(),
        external_account_id_hash=ACCOUNT_HASH,
        oauth_client_id_sha256=OAUTH_CLIENT_HASH,
        refresh_token=ProviderOAuthRefreshToken(
            "refresh-second-" + "s" * 64,
            flow_binding(),
        ),
    )
    google = OAuthClient(ConnectorProvider.GOOGLE)
    broker = ConnectedAccessTokenBroker(
        vault=subject,
        clients=clients(google),
        now=lambda: NOW,
        max_cache_entries=1,
    )

    for bound_credential in (credential(), second_credential):
        source = broker.bind(
            account=account(),
            credential=bound_credential,
            connection_incarnation_id=INCARNATION_ID,
            authorization=authorization(),
            hard_expires_at=NOW + timedelta(minutes=10),
        )
        await source.issue_access_token(
            account=account(),
            credential=bound_credential,
        )

    assert google.calls == 2
    assert len(broker._cache) == 1
    assert broker._locks == {}


@pytest.mark.asyncio
async def test_scope_drift_and_too_short_hard_expiry_fail_closed():
    store = Store()
    subject = vault(store)
    await create(subject)
    google = OAuthClient(
        ConnectorProvider.GOOGLE,
        returned_scopes=frozenset({"unexpected.scope"}),
    )
    broker = ConnectedAccessTokenBroker(
        vault=subject,
        clients=clients(google),
        now=lambda: NOW,
    )
    source = broker.bind(
        account=account(),
        credential=credential(),
        connection_incarnation_id=INCARNATION_ID,
        authorization=authorization(),
        hard_expires_at=NOW + timedelta(minutes=10),
    )
    with pytest.raises(ConnectedCredentialVaultError) as drift:
        await source.issue_access_token(account=account(), credential=credential())
    assert drift.value.code == "CREDENTIAL_REFRESH_FAILED"

    healthy = ConnectedAccessTokenBroker(
        vault=subject,
        clients=clients(OAuthClient(ConnectorProvider.GOOGLE)),
        now=lambda: NOW,
    )
    short = healthy.bind(
        account=account(),
        credential=credential(),
        connection_incarnation_id=INCARNATION_ID,
        authorization=authorization(),
        hard_expires_at=NOW + timedelta(seconds=15),
    )
    with pytest.raises(ConnectedCredentialVaultError) as expired:
        await short.issue_access_token(account=account(), credential=credential())
    assert expired.value.code == "CREDENTIAL_EXPIRED"


@pytest.mark.asyncio
async def test_unknown_rotating_refresh_effect_is_durably_quarantined_and_never_retried():
    store = Store()
    subject = vault(store)
    await create(subject)
    google = EffectUnknownOAuthClient(ConnectorProvider.GOOGLE)
    coordinator = RefreshCoordinator()
    broker = ConnectedAccessTokenBroker(
        vault=subject,
        clients=clients(google),
        refresh_coordinator=coordinator,
        now=lambda: NOW,
    )

    async def issue_once() -> None:
        source = broker.bind(
            account=account(),
            credential=credential(),
            connection_incarnation_id=INCARNATION_ID,
            authorization=authorization(),
            hard_expires_at=NOW + timedelta(minutes=10),
        )
        await source.issue_access_token(account=account(), credential=credential())

    with pytest.raises(ConnectedCredentialVaultError) as first:
        await issue_once()
    assert first.value.code == "CREDENTIAL_QUARANTINED"
    assert google.calls == 1
    assert len(coordinator.claims) == 1
    assert len(coordinator.quarantined) == 1
    assert coordinator.finished == []

    with pytest.raises(ConnectedCredentialVaultError) as replay:
        await issue_once()
    assert replay.value.code == "CREDENTIAL_QUARANTINED"
    assert google.calls == 1
    assert len(coordinator.claims) == 1
    assert len(coordinator.quarantined) == 1
    assert coordinator.finished == []
