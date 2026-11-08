from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from backend.connected_app_contracts import (
    ConnectedAuthorizationSnapshot,
    ConnectionAuthorizationState,
    ConnectorAccountKind,
)
from backend.connected_app_credential_vault import (
    ConnectedCredentialMasterKey,
    ConnectedCredentialVault,
    EncryptedConnectedCredential,
)
from backend.connected_app_durable_oauth import (
    ConnectedOAuthBrokerError,
    ConnectedOAuthMasterKey,
    DurableOAuthCredentialBroker,
    OAuthDurableGrantRecord,
    OAuthProvisionalCredentialRecord,
    OAuthSecretExchangeFence,
    OAuthSecretFlowRecord,
    SupabaseOAuthSecretStore,
)
from backend.connected_app_grant_cleanup import (
    ConnectedGrantCleanupError,
    SupabaseConnectedGrantCleanupStore,
)
from backend.connected_app_oauth import (
    OAuthAuthorizationCodeSecret,
    OAuthBrokerBeginResponseLost,
    OAuthBrokerFlowCommand,
    OAuthBrokerFlowLookup,
    OAuthBrokerGrant,
    OAuthCompletion,
    OAuthExchangeAmbiguous,
    OAuthExchangeCommand,
    OAuthExchangePermitClaim,
    OAuthExchangeResponseLost,
    OAuthPkceVerifierSecret,
    OAuthStateSecret,
    _issue_exchange_permit,
    pkce_s256_challenge,
)
from backend.connected_app_policy import (
    ConnectorActionKind,
    ConnectorProvider,
    ConnectorResource,
)
from backend.connected_app_provider_oauth import (
    ProviderExternalAccount,
    ProviderOAuthAccessToken,
    ProviderOAuthEffectUnknown,
    ProviderOAuthQuarantineRequired,
    ProviderOAuthQuarantineTokenSet,
    ProviderOAuthRefreshToken,
    ProviderOAuthTokenBinding,
    ProviderOAuthTokenSet,
)


NOW = datetime(2026, 11, 7, 20, 0, tzinfo=UTC)
FLOW_ID = "10000000-0000-4000-8000-000000000001"
NONCE_ID = "10000000-0000-4000-8000-000000000002"
OWNER_ID = "10000000-0000-4000-8000-000000000003"
CONNECTION_ID = "10000000-0000-4000-8000-000000000004"
INCARNATION_ID = "10000000-0000-4000-8000-000000000005"
STATE = "state-state-state-state-state-state-state-state"
VERIFIER = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
CODE = "authorization-code-value-12345"
REDIRECT = "https://askcrump.com/api/connected-apps/oauth/callback/google"
ACCOUNT_HASH = "a" * 64
CLIENT_HASH = "c" * 64
SESSION_HASH = "1" * 64
CONSUME_HASH = "2" * 64
SCOPES = frozenset(
    {
        "openid",
        "email",
        "https://www.googleapis.com/auth/gmail.readonly",
    }
)
ACTIONS = frozenset({ConnectorActionKind.MAIL_SEARCH})


def _hash_array(values: list[str]) -> str:
    return hashlib.sha256(
        json.dumps(values, ensure_ascii=True, separators=(",", ":")).encode("ascii")
    ).hexdigest()


def flow_command() -> OAuthBrokerFlowCommand:
    return OAuthBrokerFlowCommand(
        flow_id=FLOW_ID,
        nonce_id=NONCE_ID,
        owner_id=OWNER_ID,
        connection_id=CONNECTION_ID,
        connection_incarnation_id=INCARNATION_ID,
        expected_base_revision=3,
        current_flow_nonce_sha256=hashlib.sha256(NONCE_ID.encode()).hexdigest(),
        session_binding_sha256=SESSION_HASH,
        provider=ConnectorProvider.GOOGLE,
        resource=ConnectorResource.MAIL,
        account_kind=ConnectorAccountKind.PERSONAL,
        actions=ACTIONS,
        actions_sha256=_hash_array(sorted(action.value for action in ACTIONS)),
        requested_scopes=SCOPES,
        requested_scopes_sha256=_hash_array(sorted(SCOPES)),
        state_sha256=hashlib.sha256(STATE.encode()).hexdigest(),
        pkce_challenge=pkce_s256_challenge(VERIFIER),
        redirect_uri=REDIRECT,
        created_at=NOW,
        expires_at=NOW + timedelta(minutes=10),
    )


def exchange_command(command: OAuthBrokerFlowCommand) -> OAuthExchangeCommand:
    return OAuthExchangeCommand(
        exchange_id=command.flow_id,
        consumption_id=command.flow_id,
        flow_id=command.flow_id,
        nonce_id=command.nonce_id,
        owner_id=command.owner_id,
        connection_id=command.connection_id,
        connection_incarnation_id=command.connection_incarnation_id,
        expected_base_revision=command.expected_base_revision,
        current_flow_nonce_sha256=command.current_flow_nonce_sha256,
        session_binding_sha256=command.session_binding_sha256,
        provider=command.provider,
        resource=command.resource,
        account_kind=command.account_kind,
        redirect_uri=command.redirect_uri,
        actions_sha256=command.actions_sha256,
        requested_scopes_sha256=command.requested_scopes_sha256,
        flow_binding_sha256=command.binding_sha256,
        consume_binding_sha256=CONSUME_HASH,
        pkce_challenge=command.pkce_challenge,
        issued_at=NOW + timedelta(minutes=1),
        deadline_at=NOW + timedelta(minutes=3),
    )


class RandomBytes:
    def __init__(self) -> None:
        self.counter = 1

    def __call__(self, length: int) -> bytes:
        value = bytes([self.counter]) * length
        self.counter += 1
        return value


class OAuthStore:
    def __init__(self) -> None:
        self.flow: OAuthSecretFlowRecord | None = None
        self.fence: OAuthSecretExchangeFence | None = None
        self.terminal: OAuthDurableGrantRecord | OAuthExchangeAmbiguous | None = None
        self.provisional: dict[str, OAuthProvisionalCredentialRecord] = {}
        self.erased: set[str] = set()
        self.lose_begin_after_store = False
        self.lose_grant_after_store = False

    async def begin_once(self, record: OAuthSecretFlowRecord) -> OAuthSecretFlowRecord:
        if self.flow is None:
            self.flow = record
        elif self.flow.command.binding_sha256 != record.command.binding_sha256:
            raise RuntimeError("binding drift")
        if self.lose_begin_after_store:
            self.lose_begin_after_store = False
            raise RuntimeError("response lost after state custody")
        return self.flow

    async def read_flow(self, lookup: OAuthBrokerFlowLookup) -> OAuthSecretFlowRecord | None:
        if self.flow is None or self.flow.command.flow_id != lookup.flow_id:
            return None
        return self.flow

    async def fence_exchange(
        self, *, command: OAuthExchangeCommand, attempt_id: str
    ) -> OAuthSecretExchangeFence:
        if self.fence is None:
            self.fence = OAuthSecretExchangeFence(
                flow_id=command.flow_id,
                exchange_id=command.exchange_id,
                exchange_binding_sha256=command.binding_sha256,
                attempt_id=attempt_id,
                recorded_at=NOW + timedelta(minutes=1, seconds=1),
                fresh=True,
                deadline_expired=False,
            )
            return self.fence
        return OAuthSecretExchangeFence(
            flow_id=self.fence.flow_id,
            exchange_id=self.fence.exchange_id,
            exchange_binding_sha256=self.fence.exchange_binding_sha256,
            attempt_id=self.fence.attempt_id,
            recorded_at=self.fence.recorded_at,
            fresh=self.fence.attempt_id == attempt_id,
            deadline_expired=False,
        )

    async def put_grant_once(
        self, record: OAuthDurableGrantRecord, *, attempt_id: str
    ) -> OAuthDurableGrantRecord:
        if self.terminal is None:
            self.terminal = record
            assert record.provisional is not None
            self.provisional[record.credential_handle_sha256] = record.provisional
        if not isinstance(self.terminal, OAuthDurableGrantRecord):
            raise RuntimeError("terminal mismatch")
        if self.lose_grant_after_store:
            self.lose_grant_after_store = False
            raise RuntimeError("response lost after commit with raw provider body")
        return self.terminal

    async def mark_ambiguous_once(
        self,
        *,
        command: OAuthExchangeCommand,
        attempt_id: str,
        observed_at: datetime,
        quarantine: OAuthProvisionalCredentialRecord | None = None,
    ) -> OAuthExchangeAmbiguous:
        if self.terminal is None:
            self.terminal = OAuthExchangeAmbiguous(
                exchange_id=command.exchange_id,
                exchange_binding_sha256=command.binding_sha256,
                observed_at=observed_at,
            )
            if quarantine is not None:
                self.provisional[quarantine.credential_handle_sha256] = quarantine
        assert isinstance(self.terminal, OAuthExchangeAmbiguous)
        return self.terminal

    async def read_exchange(self, command: OAuthExchangeCommand):
        return self.terminal

    async def read_provisional(
        self, *, credential_handle_sha256: str
    ) -> OAuthProvisionalCredentialRecord | None:
        if credential_handle_sha256 in self.erased:
            return None
        return self.provisional.get(credential_handle_sha256)

    async def erase_provisional_once(
        self,
        *,
        credential_handle_sha256: str,
        expected_record_binding_sha256: str,
    ) -> bool:
        existing = self.provisional.get(credential_handle_sha256)
        if existing is not None and (
            existing.envelope.record_binding_sha256 != expected_record_binding_sha256
        ):
            raise RuntimeError("stale provisional CAS")
        self.erased.add(credential_handle_sha256)
        return self.provisional.pop(credential_handle_sha256, None) is not None

    async def abort_flow_once(self, *, flow_id: str, flow_binding_sha256: str, reason: str) -> None:
        self.provisional.clear()
        self.flow = None


class CredentialStore:
    def __init__(self) -> None:
        self.rows: dict[str, EncryptedConnectedCredential] = {}

    async def create_once(self, record: EncryptedConnectedCredential):
        key = record.metadata.credential.handle_id
        existing = self.rows.get(key)
        if existing is not None:
            return existing
        self.rows[key] = record
        return record

    async def read(self, credential):
        return self.rows.get(credential.handle_id)

    async def replace_once(self, *, expected_record_binding_sha256: str, record):
        existing = self.rows.get(record.metadata.credential.handle_id)
        if existing is None or (existing.record_binding_sha256 != expected_record_binding_sha256):
            raise RuntimeError("stale credential CAS")
        self.rows[record.metadata.credential.handle_id] = record
        return record

    async def delete_once(self, *, credential, expected_record_binding_sha256: str):
        existing = self.rows.get(credential.handle_id)
        if existing is None:
            return False
        if existing.record_binding_sha256 != expected_record_binding_sha256:
            raise RuntimeError("stale credential delete")
        del self.rows[credential.handle_id]
        return True


class PermitAuthority:
    def __init__(self) -> None:
        self.calls = 0

    async def consume_exchange_permit_for_dispatch(self, command, permit):
        self.calls += 1
        return OAuthExchangePermitClaim(
            permit_id=permit.permit_id,
            exchange_binding_sha256=permit.exchange_binding_sha256,
            permit_binding_sha256=permit.permit_binding_sha256,
            consumed_at=command.issued_at + timedelta(seconds=1),
        )


class GrantCleanupRPC:
    def __init__(self) -> None:
        self.cleanup_id: str | None = None
        self.exchange_binding_sha256: str | None = None
        self.source_binding_sha256: str | None = None
        self.encrypted_record: dict[str, object] | None = None
        self.status: str | None = None
        self.calls: list[str] = []
        self.release_failures_remaining = 0

    async def rpc(self, function_name, payload, *, retry_transient=False):
        del retry_transient
        self.calls.append(function_name)
        timestamp = (NOW + timedelta(minutes=1, seconds=3)).isoformat()
        if function_name == "connected_app_provider_cleanup_begin_v1":
            self.cleanup_id = payload["p_cleanup_id"]
            self.exchange_binding_sha256 = payload["p_exchange_binding_sha256"]
            self.status = "exchange_pending"
            return {
                "status": self.status,
                "cleanup_id": self.cleanup_id,
                "source_binding_sha256": self.exchange_binding_sha256,
                "created_at": timestamp,
                "updated_at": timestamp,
            }
        if function_name == "connected_app_provider_cleanup_attach_v1":
            assert payload["p_cleanup_id"] == self.cleanup_id
            assert payload["p_exchange_binding_sha256"] == self.exchange_binding_sha256
            self.source_binding_sha256 = payload["p_source_binding_sha256"]
            self.encrypted_record = payload["p_encrypted_record"]
            self.status = "retained"
            return {
                "status": self.status,
                "cleanup_id": self.cleanup_id,
                "source_binding_sha256": self.source_binding_sha256,
                "created_at": timestamp,
                "updated_at": timestamp,
            }
        if function_name == "connected_app_provider_cleanup_release_v1":
            assert payload["p_cleanup_id"] == self.cleanup_id
            assert payload["p_source_binding_sha256"] == self.source_binding_sha256
            if self.release_failures_remaining:
                self.release_failures_remaining -= 1
                raise RuntimeError("cleanup release unavailable")
            self.status = "released"
            self.encrypted_record = None
            return {"status": self.status, "cleanup_id": self.cleanup_id}
        if function_name == "connected_app_provider_cleanup_release_recover_v1":
            assert payload["p_cleanup_id"] == self.cleanup_id
            if self.status != "released":
                assert self.encrypted_record is not None
                assert (
                    payload["p_credential_handle_sha256"]
                    == self.encrypted_record["credential_handle_sha256"]
                )
            self.status = "released"
            self.encrypted_record = None
            return {"status": self.status, "cleanup_id": self.cleanup_id}
        raise AssertionError(function_name)


class Provider:
    def __init__(self, provider: ConnectorProvider) -> None:
        self.provider = provider
        self.exchange_calls = 0
        self.identify_calls = 0
        self.exchange_error: Exception | None = None
        self.identify_error: Exception | None = None

    async def exchange_code(self, *, command, authorization_code, verifier):
        self.exchange_calls += 1
        if self.exchange_error is not None:
            raise self.exchange_error
        binding = ProviderOAuthTokenBinding(
            provider=self.provider,
            oauth_client_id_sha256=CLIENT_HASH,
            owner_id=command.owner_id,
            connection_id=command.connection_id,
            connection_incarnation_id=command.connection_incarnation_id,
            account_kind=command.account_kind,
        )
        return ProviderOAuthTokenSet(
            provider=self.provider,
            access_token=ProviderOAuthAccessToken("access-" + "x" * 64, binding),
            refresh_token=ProviderOAuthRefreshToken("refresh-" + "r" * 64, binding),
            granted_scopes=command.requested_scopes,
            issued_at=NOW + timedelta(minutes=1, seconds=2),
            expires_at=NOW + timedelta(hours=1),
        )

    async def identify(self, access_token, *, binding):
        self.identify_calls += 1
        if self.identify_error is not None:
            raise self.identify_error
        return ProviderExternalAccount(
            provider=self.provider,
            account_kind=ConnectorAccountKind.PERSONAL,
            external_account_id_hash=ACCOUNT_HASH,
        )


def broker(
    *,
    oauth_store: OAuthStore | None = None,
    provider: Provider | None = None,
    credential_store: CredentialStore | None = None,
):
    oauth_store = oauth_store or OAuthStore()
    provider = provider or Provider(ConnectorProvider.GOOGLE)
    credential_store = credential_store or CredentialStore()
    credential_key = ConnectedCredentialMasterKey("credential-key", bytes(range(32)))
    vault = ConnectedCredentialVault(
        keys={credential_key.key_id: credential_key},
        active_key_id=credential_key.key_id,
        store=credential_store,
        now=lambda: NOW + timedelta(minutes=2),
        random_bytes=RandomBytes(),
    )
    oauth_key = ConnectedOAuthMasterKey("oauth-key", bytes(reversed(range(32))))
    authority = PermitAuthority()
    cleanup_rpc = GrantCleanupRPC()
    subject = DurableOAuthCredentialBroker(
        keys={oauth_key.key_id: oauth_key},
        active_key_id=oauth_key.key_id,
        store=oauth_store,
        permit_authority=authority,
        clients={
            ConnectorProvider.GOOGLE: provider,
            ConnectorProvider.MICROSOFT: Provider(ConnectorProvider.MICROSOFT),
        },
        credential_vault=vault,
        grant_cleanup_store=SupabaseConnectedGrantCleanupStore(cleanup_rpc),
        now=lambda: NOW + timedelta(minutes=1, seconds=3),
        random_bytes=RandomBytes(),
    )
    subject.cleanup_rpc = cleanup_rpc
    return subject, oauth_store, provider, authority, credential_store


async def begin_and_exchange(subject: DurableOAuthCredentialBroker):
    flow = flow_command()
    await subject.begin_flow(
        command=flow,
        authorization_state=OAuthStateSecret(STATE),
        verifier=OAuthPkceVerifierSecret(VERIFIER),
    )
    exchange = exchange_command(flow)
    _record, permit = _issue_exchange_permit(
        exchange,
        issued_at=exchange.issued_at,
    )
    terminal = await subject.exchange_once(
        command=exchange,
        permit=permit,
        authorization_code=OAuthAuthorizationCodeSecret(CODE),
    )
    return flow, exchange, permit, terminal


@pytest.mark.asyncio
async def test_flow_and_refresh_token_are_encrypted_redacted_and_exchange_is_one_use():
    subject, store, provider, authority, _credentials = broker()
    flow, exchange, permit, terminal = await begin_and_exchange(subject)

    assert isinstance(terminal, OAuthBrokerGrant)
    assert provider.exchange_calls == 1
    assert authority.calls == 1
    assert subject.cleanup_rpc.status == "retained"
    assert subject.cleanup_rpc.calls[:2] == [
        "connected_app_provider_cleanup_begin_v1",
        "connected_app_provider_cleanup_attach_v1",
    ]
    assert subject.cleanup_rpc.encrypted_record is not None
    assert "refresh-" not in repr(subject.cleanup_rpc.encrypted_record)
    assert store.flow is not None
    assert STATE not in store.flow.envelope.secret_ciphertext
    assert VERIFIER not in store.flow.envelope.secret_ciphertext
    provisional = next(iter(store.provisional.values()))
    assert "refresh-" not in provisional.envelope.secret_ciphertext
    assert "access-" not in repr(store.flow)
    assert "refresh-" not in repr(provisional)

    replay = await subject.exchange_once(
        command=exchange,
        permit=permit,
        authorization_code=OAuthAuthorizationCodeSecret(CODE),
    )
    assert isinstance(replay, OAuthBrokerGrant)
    assert replay.credential == terminal.credential
    assert provider.exchange_calls == 1
    assert authority.calls == 1
    assert flow.binding_sha256 == store.flow.command.binding_sha256


@pytest.mark.asyncio
async def test_begin_response_loss_recovers_exact_encrypted_state_without_regeneration():
    store = OAuthStore()
    store.lose_begin_after_store = True
    subject, _store, _provider, _authority, _credentials = broker(oauth_store=store)
    command = flow_command()
    with pytest.raises(OAuthBrokerBeginResponseLost):
        await subject.begin_flow(
            command=command,
            authorization_state=OAuthStateSecret(STATE),
            verifier=OAuthPkceVerifierSecret(VERIFIER),
        )
    recovered = await subject.read_flow(
        lookup=OAuthBrokerFlowLookup(
            flow_id=FLOW_ID,
            owner_id=OWNER_ID,
            connection_id=CONNECTION_ID,
            connection_incarnation_id=INCARNATION_ID,
            expected_base_revision=3,
            current_flow_nonce_sha256=command.current_flow_nonce_sha256,
        )
    )
    assert recovered is not None
    assert recovered.authorization_state.value == STATE
    assert recovered.command.binding_sha256 == command.binding_sha256
    assert store.flow is not None
    assert STATE not in store.flow.envelope.secret_ciphertext
    assert VERIFIER not in store.flow.envelope.secret_ciphertext


@pytest.mark.asyncio
async def test_grant_response_loss_recovers_without_provider_redispatch():
    store = OAuthStore()
    store.lose_grant_after_store = True
    subject, _store, provider, authority, _credentials = broker(oauth_store=store)
    flow = flow_command()
    await subject.begin_flow(
        command=flow,
        authorization_state=OAuthStateSecret(STATE),
        verifier=OAuthPkceVerifierSecret(VERIFIER),
    )
    exchange = exchange_command(flow)
    _record, permit = _issue_exchange_permit(exchange, issued_at=exchange.issued_at)
    with pytest.raises(OAuthExchangeResponseLost):
        await subject.exchange_once(
            command=exchange,
            permit=permit,
            authorization_code=OAuthAuthorizationCodeSecret(CODE),
        )
    recovered = await subject.exchange_once(
        command=exchange,
        permit=permit,
        authorization_code=OAuthAuthorizationCodeSecret(CODE),
    )
    assert isinstance(recovered, OAuthBrokerGrant)
    assert provider.exchange_calls == 1
    assert authority.calls == 1


@pytest.mark.asyncio
async def test_unknown_provider_effect_is_terminal_ambiguous_and_not_retried():
    provider = Provider(ConnectorProvider.GOOGLE)
    provider.exchange_error = ProviderOAuthEffectUnknown()
    subject, _store, _provider, authority, _credentials = broker(provider=provider)
    _flow, exchange, permit, terminal = await begin_and_exchange(subject)
    assert isinstance(terminal, OAuthExchangeAmbiguous)
    replay = await subject.exchange_once(
        command=exchange,
        permit=permit,
        authorization_code=OAuthAuthorizationCodeSecret(CODE),
    )
    assert isinstance(replay, OAuthExchangeAmbiguous)
    assert provider.exchange_calls == 1
    assert authority.calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("include_refresh", (True, False))
async def test_semantically_invalid_200_tokens_enter_encrypted_cleanup_quarantine(
    include_refresh,
):
    provider = Provider(ConnectorProvider.GOOGLE)
    command = flow_command()
    binding = ProviderOAuthTokenBinding(
        provider=ConnectorProvider.GOOGLE,
        oauth_client_id_sha256=CLIENT_HASH,
        owner_id=command.owner_id,
        connection_id=command.connection_id,
        connection_incarnation_id=command.connection_incarnation_id,
        account_kind=command.account_kind,
    )
    token_set = ProviderOAuthQuarantineTokenSet(
        provider=ConnectorProvider.GOOGLE,
        access_token=ProviderOAuthAccessToken("access-" + "x" * 64, binding),
        refresh_token=(
            ProviderOAuthRefreshToken("refresh-" + "r" * 64, binding)
            if include_refresh
            else None
        ),
        requested_scopes=command.requested_scopes,
        issued_at=NOW + timedelta(minutes=1, seconds=2),
        expires_at=NOW + timedelta(hours=1),
    )
    provider.exchange_error = ProviderOAuthQuarantineRequired(token_set)
    subject, store, _provider, authority, _credentials = broker(provider=provider)

    _flow, exchange, permit, terminal = await begin_and_exchange(subject)

    assert isinstance(terminal, OAuthExchangeAmbiguous)
    assert provider.exchange_calls == 1
    assert authority.calls == 1
    assert subject.cleanup_rpc.status == "retained"
    assert subject.cleanup_rpc.encrypted_record is not None
    quarantine = next(iter(store.provisional.values()))
    assert quarantine.status == "quarantined"
    assert subject.cleanup_rpc.source_binding_sha256 == (
        quarantine.envelope.record_binding_sha256
    )
    assert "access-" not in quarantine.envelope.secret_ciphertext
    assert "refresh-" not in quarantine.envelope.secret_ciphertext
    assert "access-" not in repr(subject.cleanup_rpc.encrypted_record)
    replay = await subject.exchange_once(
        command=exchange,
        permit=permit,
        authorization_code=OAuthAuthorizationCodeSecret(CODE),
    )
    assert isinstance(replay, OAuthExchangeAmbiguous)
    assert provider.exchange_calls == 1


@pytest.mark.asyncio
async def test_identity_failure_keeps_encrypted_quarantine_and_never_grants():
    provider = Provider(ConnectorProvider.GOOGLE)
    provider.identify_error = RuntimeError("provider body access-token-value")
    subject, store, _provider, _authority, _credentials = broker(provider=provider)
    _flow, _exchange, _permit, terminal = await begin_and_exchange(subject)
    assert isinstance(terminal, OAuthExchangeAmbiguous)
    quarantine = next(iter(store.provisional.values()))
    assert quarantine.status == "quarantined"
    assert subject.cleanup_rpc.status == "retained"
    assert subject.cleanup_rpc.source_binding_sha256 == (
        quarantine.envelope.record_binding_sha256
    )
    assert "refresh-" not in quarantine.envelope.secret_ciphertext
    assert "access-token-value" not in repr(terminal)


@pytest.mark.asyncio
async def test_active_completion_promotes_provisional_by_cas_then_tombstones_and_replays():
    subject, store, _provider, _authority, credentials = broker()
    _flow, exchange, _permit, terminal = await begin_and_exchange(subject)
    assert isinstance(terminal, OAuthBrokerGrant)
    authorization = ConnectedAuthorizationSnapshot.build(
        owner_id=OWNER_ID,
        connection_id=CONNECTION_ID,
        provider=ConnectorProvider.GOOGLE,
        resource=ConnectorResource.MAIL,
        account_kind=ConnectorAccountKind.PERSONAL,
        revision=4,
        granted_actions=ACTIONS,
        granted_scopes=SCOPES,
        state=ConnectionAuthorizationState.ACTIVE,
        issued_at=NOW + timedelta(minutes=1, seconds=2),
        expires_at=NOW + timedelta(hours=1),
    )
    completion = OAuthCompletion(
        consumption_id=exchange.consumption_id,
        exchange_id=exchange.exchange_id,
        connection_incarnation_id=INCARNATION_ID,
        expected_base_revision=3,
        current_flow_nonce_sha256=exchange.current_flow_nonce_sha256,
        completion_binding_sha256="d" * 64,
        credential=terminal.credential,
        external_account_id_hash=ACCOUNT_HASH,
        authorization=authorization,
    )

    created = await subject.activate_completion(completion)
    digest = hashlib.sha256(terminal.credential.handle_id.encode()).hexdigest()
    assert created.metadata.credential == terminal.credential
    assert digest in store.erased
    assert store.provisional == {}
    assert credentials.rows[terminal.credential.handle_id] is created
    assert "refresh-" not in created.secret_ciphertext
    assert subject.cleanup_rpc.status == "released"
    assert subject.cleanup_rpc.encrypted_record is None

    replay = await subject.activate_completion(completion)
    assert replay.record_binding_sha256 == created.record_binding_sha256
    assert len(credentials.rows) == 1
    assert subject.cleanup_rpc.calls[-1] == (
        "connected_app_provider_cleanup_release_recover_v1"
    )


@pytest.mark.asyncio
async def test_activation_replay_releases_retained_cleanup_after_source_erasure():
    subject, store, _provider, _authority, credentials = broker()
    _flow, exchange, _permit, terminal = await begin_and_exchange(subject)
    assert isinstance(terminal, OAuthBrokerGrant)
    authorization = ConnectedAuthorizationSnapshot.build(
        owner_id=OWNER_ID,
        connection_id=CONNECTION_ID,
        provider=ConnectorProvider.GOOGLE,
        resource=ConnectorResource.MAIL,
        account_kind=ConnectorAccountKind.PERSONAL,
        revision=4,
        granted_actions=ACTIONS,
        granted_scopes=SCOPES,
        state=ConnectionAuthorizationState.ACTIVE,
        issued_at=NOW + timedelta(minutes=1, seconds=2),
        expires_at=NOW + timedelta(hours=1),
    )
    completion = OAuthCompletion(
        consumption_id=exchange.consumption_id,
        exchange_id=exchange.exchange_id,
        connection_incarnation_id=INCARNATION_ID,
        expected_base_revision=3,
        current_flow_nonce_sha256=exchange.current_flow_nonce_sha256,
        completion_binding_sha256="d" * 64,
        credential=terminal.credential,
        external_account_id_hash=ACCOUNT_HASH,
        authorization=authorization,
    )
    subject.cleanup_rpc.release_failures_remaining = 2

    with pytest.raises(ConnectedGrantCleanupError):
        await subject.activate_completion(completion)

    digest = hashlib.sha256(terminal.credential.handle_id.encode()).hexdigest()
    assert digest in store.erased
    assert store.provisional == {}
    assert credentials.rows[terminal.credential.handle_id]
    assert subject.cleanup_rpc.status == "retained"
    assert subject.cleanup_rpc.encrypted_record is not None

    recovered = await subject.activate_completion(completion)
    assert recovered is credentials.rows[terminal.credential.handle_id]
    assert subject.cleanup_rpc.status == "released"
    assert subject.cleanup_rpc.encrypted_record is None
    assert subject.cleanup_rpc.calls[-1] == (
        "connected_app_provider_cleanup_release_recover_v1"
    )


class RPC:
    def __init__(self, result=None, error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.calls = 0

    async def rpc(self, function_name, payload, *, retry_transient=False):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.result


@pytest.mark.asyncio
async def test_supabase_adapter_fails_closed_on_malformed_rows_and_rpc_failure():
    lookup = OAuthBrokerFlowLookup(
        flow_id=FLOW_ID,
        owner_id=OWNER_ID,
        connection_id=CONNECTION_ID,
        connection_incarnation_id=INCARNATION_ID,
        expected_base_revision=3,
        current_flow_nonce_sha256=hashlib.sha256(NONCE_ID.encode()).hexdigest(),
    )
    malformed = SupabaseOAuthSecretStore(RPC({"status": "absent", "record": None, "extra": True}))
    with pytest.raises(ConnectedOAuthBrokerError) as invalid:
        await malformed.read_flow(lookup)
    assert invalid.value.code == "OAUTH_SECRET_INVALID"

    failed = SupabaseOAuthSecretStore(RPC(error=TimeoutError("provider detail")))
    with pytest.raises(ConnectedOAuthBrokerError) as unavailable:
        await failed.read_flow(lookup)
    assert unavailable.value.code == "OAUTH_SECRET_STORE_FAILED"
    assert "provider detail" not in repr(unavailable.value)


def test_forward_migration_is_private_exact_and_never_accepts_plain_oauth_secrets():
    sql = Path("migrations/20261107231500_connected_app_oauth_secret_custody.sql").read_text(
        encoding="utf-8"
    )
    normalized = " ".join(sql.casefold().split())
    for table in (
        "oauth_secret_custody",
        "oauth_secret_tombstones",
        "oauth_provisional_credentials",
        "oauth_provisional_tombstones",
    ):
        assert f"create table if not exists connected_app_private.{table}" in normalized
        assert f"alter table connected_app_private.{table} enable row level security" in normalized
        assert f"alter table connected_app_private.{table} force row level security" in normalized
    for function in (
        "connected_app_oauth_secret_begin_v1",
        "connected_app_oauth_secret_read_flow_v1",
        "connected_app_oauth_secret_fence_v1",
        "connected_app_oauth_secret_grant_v1",
        "connected_app_oauth_secret_ambiguous_v1",
        "connected_app_oauth_secret_read_exchange_v1",
        "connected_app_oauth_provisional_read_v1",
        "connected_app_oauth_provisional_erase_v1",
        "connected_app_oauth_secret_abort_v1",
    ):
        assert f"create or replace function public.{function}" in normalized
    assert "security definer set search_path = ''" in normalized
    assert "grant execute on function" in normalized
    assert "to service_role" in normalized
    assert "03b28d375bdb0f819bb70fbc2dff1819" in normalized
    assert "refresh_token" not in normalized
    assert "access_token" not in normalized
    assert "pkce_verifier" not in normalized
    assert "authorization_code" not in normalized
    assert "15a55a3a38c8fe732729e6d38c79c880" in normalized
    assert "partial or drifted connected-app oauth secret target; refusing repair" in normalized
    assert "using errcode = '55000'" in normalized

    race_sql = Path("scripts/verify-connected-app-oauth-secret-custody-races-pg17.sql").read_text(
        encoding="utf-8"
    )
    assert "losing host" in race_sql
    assert "grant wins" in race_sql.casefold()
    assert "abort wins" in race_sql.casefold()
