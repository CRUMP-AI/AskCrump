from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib
from typing import Any, Callable

import pytest

from backend.connected_app_contracts import (
    ConnectedAuthorizationSnapshot,
    ConnectionAuthorizationState,
    ConnectorAccountKind,
    CredentialHandleRef,
)
from backend.connected_app_durable_oauth import ConnectedOAuthMasterKey
from backend.connected_app_credential_vault import (
    ConnectedCredentialMasterKey,
    ConnectedCredentialVault,
    EncryptedConnectedCredential,
)
from backend.connected_app_oauth import (
    OAuthCompletion,
    OAuthCompletionCommand,
    OAuthCompletionInactive,
    OAuthContractError,
    OAuthExchangeCommand,
)
from backend.connected_app_oauth_supabase import (
    ConnectedOAuthRepositoryError,
    SupabaseConnectedAccountRegistry,
    SupabaseOAuthFlowRepository,
    SupabaseOAuthRepositoryCoordinator,
)
from backend.connected_app_policy import (
    ConnectorActionKind,
    ConnectorProvider,
    ConnectorResource,
    action_set_sha256,
)
from backend.connected_app_scopes import delegated_scope_plan
from backend.connected_app_provider_oauth import (
    ProviderOAuthRefreshToken,
    ProviderOAuthTokenBinding,
)


OWNER_ID = "00000000-0000-4000-8000-000000000001"
CONNECTION_ID = "00000000-0000-4000-8000-000000000002"
INCARNATION_ID = "00000000-0000-4000-8000-000000000003"
FLOW_ID = "00000000-0000-4000-8000-000000000004"
NONCE_ID = "00000000-0000-4000-8000-000000000005"
EXCHANGE_ID = "00000000-0000-4000-8000-000000000006"
CREDENTIAL_ID = "00000000-0000-4000-8000-000000000007"
NOW = datetime(2026, 11, 8, 3, 0, tzinfo=UTC)
REDIRECT = "https://askcrump.com/api/connected-apps/oauth/callback/google"
HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64
HASH_D = "d" * 64


class ScriptedRPC:
    def __init__(self) -> None:
        self.handlers: dict[str, Callable[[dict[str, object]], object]] = {}
        self.calls: list[tuple[str, dict[str, object], bool]] = []

    async def rpc(
        self,
        function_name: str,
        payload: dict[str, Any],
        *,
        retry_transient: bool = False,
    ) -> object:
        self.calls.append((function_name, dict(payload), retry_transient))
        return self.handlers[function_name](payload)


class CredentialStore:
    def __init__(self) -> None:
        self.rows: dict[str, EncryptedConnectedCredential] = {}

    async def create_once(
        self, record: EncryptedConnectedCredential
    ) -> EncryptedConnectedCredential:
        existing = self.rows.get(record.metadata.credential.handle_id)
        if existing is not None and existing.record_binding_sha256 != record.record_binding_sha256:
            raise RuntimeError("credential replay drift")
        self.rows[record.metadata.credential.handle_id] = record
        return record

    async def read(self, credential: CredentialHandleRef) -> EncryptedConnectedCredential | None:
        return self.rows.get(credential.handle_id)

    async def replace_once(
        self,
        *,
        expected_record_binding_sha256: str,
        record: EncryptedConnectedCredential,
    ) -> EncryptedConnectedCredential:
        existing = self.rows.get(record.metadata.credential.handle_id)
        if existing is None or existing.record_binding_sha256 != expected_record_binding_sha256:
            raise RuntimeError("credential CAS drift")
        self.rows[record.metadata.credential.handle_id] = record
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
            raise RuntimeError("credential delete drift")
        del self.rows[credential.handle_id]
        return True


def scopes() -> frozenset[str]:
    return frozenset(
        delegated_scope_plan(
            ConnectorProvider.GOOGLE,
            {ConnectorActionKind.MAIL_GET},
            account_kind=ConnectorAccountKind.PERSONAL,
        ).delegated_scopes
    )


def authorization() -> ConnectedAuthorizationSnapshot:
    return ConnectedAuthorizationSnapshot.build(
        owner_id=OWNER_ID,
        connection_id=CONNECTION_ID,
        provider=ConnectorProvider.GOOGLE,
        resource=ConnectorResource.MAIL,
        account_kind=ConnectorAccountKind.PERSONAL,
        revision=1,
        granted_actions=frozenset({ConnectorActionKind.MAIL_GET}),
        granted_scopes=scopes(),
        state=ConnectionAuthorizationState.ACTIVE,
        issued_at=NOW,
        expires_at=NOW + timedelta(hours=1),
    )


def binding_row(snapshot: ConnectedAuthorizationSnapshot) -> dict[str, object]:
    return {
        "owner_id": OWNER_ID,
        "connection_id": CONNECTION_ID,
        "provider": "google",
        "resource": "mail",
        "account_kind": "personal",
        "connection_incarnation_id": INCARNATION_ID,
        "authorization_revision": snapshot.revision,
        "authorization_state": "active",
        "authorization_snapshot_sha256": snapshot.snapshot_sha256,
        "authorization_issued_at": snapshot.issued_at.isoformat(),
        "granted_actions": ["mail.get"],
        "granted_actions_sha256": snapshot.granted_actions_sha256,
        "granted_scopes_sha256": snapshot.granted_scopes_sha256,
        "external_account_id_sha256": HASH_A,
        "broker_credential_ref": CREDENTIAL_ID,
        "credential_ref_sha256": hashlib.sha256(CREDENTIAL_ID.encode()).hexdigest(),
        "current_flow_nonce_sha256": hashlib.sha256(NONCE_ID.encode()).hexdigest(),
        "authorization_expires_at": snapshot.expires_at.isoformat(),
        "revoked_at": None,
    }


@pytest.mark.asyncio
async def test_restart_registry_reconstructs_and_hash_checks_exact_snapshot():
    rpc = ScriptedRPC()
    snapshot = authorization()
    rpc.handlers["connected_app_get_binding_v2"] = lambda _payload: binding_row(snapshot)

    binding = await SupabaseConnectedAccountRegistry(rpc).get_binding(
        owner_id=OWNER_ID, connection_id=CONNECTION_ID
    )

    assert binding is not None
    assert binding.authorization == snapshot
    assert binding.authorization.snapshot_sha256 == snapshot.snapshot_sha256
    assert binding.account.external_account_id_hash == HASH_A
    assert rpc.calls == [
        (
            "connected_app_get_binding_v2",
            {"p_owner_id": OWNER_ID, "p_connection_id": CONNECTION_ID},
            True,
        )
    ]


@pytest.mark.asyncio
async def test_restart_registry_rejects_snapshot_hash_drift():
    rpc = ScriptedRPC()
    row = binding_row(authorization())
    row["authorization_snapshot_sha256"] = HASH_D
    rpc.handlers["connected_app_get_binding_v2"] = lambda _payload: row

    with pytest.raises(ConnectedOAuthRepositoryError, match="OAUTH_REPOSITORY_BINDING_MISMATCH"):
        await SupabaseConnectedAccountRegistry(rpc).get_binding(
            owner_id=OWNER_ID, connection_id=CONNECTION_ID
        )


@pytest.mark.asyncio
async def test_coordinator_reuses_durable_secret_custody_for_denial_cleanup():
    rpc = ScriptedRPC()

    def abort(payload: dict[str, object]) -> dict[str, object]:
        assert payload == {
            "p_flow_id": FLOW_ID,
            "p_flow_binding_sha256": HASH_B,
            "p_reason": "denied",
        }
        return {"status": "erased"}

    rpc.handlers["connected_app_oauth_secret_abort_v1"] = abort
    coordinator = SupabaseOAuthRepositoryCoordinator.build(
        database=rpc,
        redirect_uris={ConnectorProvider.GOOGLE: REDIRECT},
        permit_keys={"oauth-k1": ConnectedOAuthMasterKey("oauth-k1", b"x" * 32)},
        active_permit_key_id="oauth-k1",
        now=lambda: NOW,
    )

    await coordinator.secrets.abort_flow_once(
        flow_id=FLOW_ID,
        flow_binding_sha256=HASH_B,
        reason="denied",
    )


def completion_command() -> OAuthCompletionCommand:
    granted_actions = frozenset({ConnectorActionKind.MAIL_GET})
    granted_scopes = scopes()
    return OAuthCompletionCommand(
        completion_id=FLOW_ID,
        consumption_id=FLOW_ID,
        exchange_id=EXCHANGE_ID,
        owner_id=OWNER_ID,
        connection_id=CONNECTION_ID,
        connection_incarnation_id=INCARNATION_ID,
        expected_base_revision=0,
        current_flow_nonce_sha256=hashlib.sha256(NONCE_ID.encode()).hexdigest(),
        provider=ConnectorProvider.GOOGLE,
        resource=ConnectorResource.MAIL,
        account_kind=ConnectorAccountKind.PERSONAL,
        redirect_uri=REDIRECT,
        flow_binding_sha256=HASH_B,
        exchange_binding_sha256=HASH_C,
        credential=CredentialHandleRef(
            owner_id=OWNER_ID,
            connection_id=CONNECTION_ID,
            provider=ConnectorProvider.GOOGLE,
            handle_id=CREDENTIAL_ID,
        ),
        external_account_id_hash=HASH_A,
        granted_actions=granted_actions,
        granted_actions_sha256=action_set_sha256(granted_actions),
        granted_scopes=granted_scopes,
        granted_scopes_sha256=authorization().granted_scopes_sha256,
        issued_at=NOW,
        expires_at=NOW + timedelta(hours=1),
    )


@pytest.mark.asyncio
async def test_finalize_keeps_replay_binding_separate_then_reconstructs_after_restart():
    rpc = ScriptedRPC()
    command = completion_command()
    snapshot = authorization()

    def finalize(payload: dict[str, object]) -> dict[str, object]:
        assert payload["p_completion_binding_sha256"] == command.binding_sha256
        assert payload["p_authorization_snapshot_sha256"] == snapshot.snapshot_sha256
        assert command.binding_sha256 != snapshot.snapshot_sha256
        return {
            "completed": True,
            "active": True,
            "owner_id": OWNER_ID,
            "connection_id": CONNECTION_ID,
            "connection_incarnation_id": INCARNATION_ID,
            "consumption_id": FLOW_ID,
            "exchange_id": EXCHANGE_ID,
            "completion_id": FLOW_ID,
            "completion_binding_sha256": command.binding_sha256,
            "authorization_revision": 1,
            "authorization_snapshot_sha256": snapshot.snapshot_sha256,
            "authorization_issued_at": NOW.isoformat(),
            "granted_actions": ["mail.get"],
            "granted_actions_sha256": snapshot.granted_actions_sha256,
            "granted_scopes_sha256": snapshot.granted_scopes_sha256,
            "external_account_id_sha256": HASH_A,
            "broker_credential_ref": CREDENTIAL_ID,
            "credential_ref_sha256": hashlib.sha256(CREDENTIAL_ID.encode()).hexdigest(),
            "authorization_expires_at": (NOW + timedelta(hours=1)).isoformat(),
        }

    rpc.handlers["connected_app_oauth_finalize_v2"] = finalize
    rpc.handlers["connected_app_get_binding_v2"] = lambda _payload: binding_row(snapshot)
    coordinator = SupabaseOAuthRepositoryCoordinator.build(
        database=rpc,
        redirect_uris={ConnectorProvider.GOOGLE: REDIRECT},
        permit_keys={"oauth-k1": ConnectedOAuthMasterKey("oauth-k1", b"x" * 32)},
        active_permit_key_id="oauth-k1",
        now=lambda: NOW,
    )

    completion, restarted = await coordinator.complete_and_reconstruct(command)

    assert isinstance(completion, OAuthCompletion)
    assert restarted is not None
    assert completion.authorization == snapshot
    assert restarted.authorization == snapshot
    assert completion.completion_binding_sha256 == command.binding_sha256


@pytest.mark.asyncio
async def test_finalize_refuses_external_account_binding_drift():
    rpc = ScriptedRPC()
    command = completion_command()
    snapshot = authorization()
    rpc.handlers["connected_app_oauth_finalize_v2"] = lambda _payload: {
        "completed": True,
        "active": True,
        "owner_id": OWNER_ID,
        "connection_id": CONNECTION_ID,
        "connection_incarnation_id": INCARNATION_ID,
        "consumption_id": FLOW_ID,
        "exchange_id": EXCHANGE_ID,
        "completion_id": FLOW_ID,
        "completion_binding_sha256": command.binding_sha256,
        "authorization_revision": 1,
        "authorization_snapshot_sha256": snapshot.snapshot_sha256,
        "authorization_issued_at": NOW.isoformat(),
        "granted_actions": ["mail.get"],
        "granted_actions_sha256": snapshot.granted_actions_sha256,
        "granted_scopes_sha256": snapshot.granted_scopes_sha256,
        "external_account_id_sha256": HASH_D,
        "broker_credential_ref": CREDENTIAL_ID,
        "credential_ref_sha256": hashlib.sha256(CREDENTIAL_ID.encode()).hexdigest(),
        "authorization_expires_at": (NOW + timedelta(hours=1)).isoformat(),
    }
    coordinator = SupabaseOAuthRepositoryCoordinator.build(
        database=rpc,
        redirect_uris={ConnectorProvider.GOOGLE: REDIRECT},
        permit_keys={"oauth-k1": ConnectedOAuthMasterKey("oauth-k1", b"x" * 32)},
        active_permit_key_id="oauth-k1",
        now=lambda: NOW,
    )

    with pytest.raises(ConnectedOAuthRepositoryError, match="OAUTH_REPOSITORY_BINDING_MISMATCH"):
        await coordinator.completions.complete_once(command)


@pytest.mark.asyncio
async def test_duplicate_inactive_completion_recovers_exactly_after_finalize_response_loss():
    rpc = ScriptedRPC()
    command = completion_command()

    def lost_after_commit(_payload: dict[str, object]) -> object:
        raise RuntimeError("simulated response loss")

    rpc.handlers["connected_app_oauth_finalize_v2"] = lost_after_commit
    rpc.handlers["connected_app_oauth_read_completion_v3"] = lambda _payload: {
        "completed": False,
        "active": False,
        "completion_id": command.completion_id,
        "completion_binding_sha256": command.binding_sha256,
        "connection_id": command.connection_id,
        "observed_at": NOW.isoformat(),
        "reason": "replaced",
    }
    coordinator = SupabaseOAuthRepositoryCoordinator.build(
        database=rpc,
        redirect_uris={ConnectorProvider.GOOGLE: REDIRECT},
        permit_keys={"oauth-k1": ConnectedOAuthMasterKey("oauth-k1", b"x" * 32)},
        active_permit_key_id="oauth-k1",
        now=lambda: NOW,
    )

    result = await coordinator.completions.complete_once(command)

    assert isinstance(result, OAuthCompletionInactive)
    assert result.completion_id == command.completion_id
    assert result.completion_binding_sha256 == command.binding_sha256
    assert result.connection_id == command.connection_id
    assert result.reason == "replaced"
    assert [call[0] for call in rpc.calls] == [
        "connected_app_oauth_finalize_v2",
        "connected_app_oauth_read_completion_v3",
    ]
    assert rpc.calls[1][2] is True


@pytest.mark.parametrize("via_readback", [False, True])
@pytest.mark.asyncio
async def test_contradictory_active_false_completed_true_is_never_an_inactive_receipt(
    via_readback: bool,
):
    rpc = ScriptedRPC()
    command = completion_command()
    contradictory = {
        "completed": True,
        "active": False,
        "completion_id": command.completion_id,
        "completion_binding_sha256": command.binding_sha256,
        "connection_id": command.connection_id,
        "observed_at": NOW.isoformat(),
        "reason": "replaced",
    }
    rpc.handlers["connected_app_oauth_finalize_v2"] = lambda _payload: contradictory
    rpc.handlers["connected_app_oauth_read_completion_v3"] = lambda _payload: contradictory
    coordinator = SupabaseOAuthRepositoryCoordinator.build(
        database=rpc,
        redirect_uris={ConnectorProvider.GOOGLE: REDIRECT},
        permit_keys={"oauth-k1": ConnectedOAuthMasterKey("oauth-k1", b"x" * 32)},
        active_permit_key_id="oauth-k1",
        now=lambda: NOW,
    )

    with pytest.raises(
        ConnectedOAuthRepositoryError, match="OAUTH_REPOSITORY_BINDING_MISMATCH"
    ):
        if via_readback:
            await coordinator.completions.read_completion(command)
        else:
            await coordinator.completions.complete_once(command)

    assert [call[0] for call in rpc.calls] == [
        (
            "connected_app_oauth_read_completion_v3"
            if via_readback
            else "connected_app_oauth_finalize_v2"
        )
    ]


@pytest.mark.asyncio
async def test_finalize_credential_activation_and_restart_authority_compose_exactly():
    rpc = ScriptedRPC()
    command = completion_command()
    snapshot = authorization()

    rpc.handlers["connected_app_oauth_finalize_v2"] = lambda _payload: {
        "completed": True,
        "active": True,
        "owner_id": OWNER_ID,
        "connection_id": CONNECTION_ID,
        "connection_incarnation_id": INCARNATION_ID,
        "consumption_id": FLOW_ID,
        "exchange_id": EXCHANGE_ID,
        "completion_id": FLOW_ID,
        "completion_binding_sha256": command.binding_sha256,
        "authorization_revision": 1,
        "authorization_snapshot_sha256": snapshot.snapshot_sha256,
        "authorization_issued_at": NOW.isoformat(),
        "granted_actions": ["mail.get"],
        "granted_actions_sha256": snapshot.granted_actions_sha256,
        "granted_scopes_sha256": snapshot.granted_scopes_sha256,
        "external_account_id_sha256": HASH_A,
        "broker_credential_ref": CREDENTIAL_ID,
        "credential_ref_sha256": hashlib.sha256(CREDENTIAL_ID.encode()).hexdigest(),
        "authorization_expires_at": (NOW + timedelta(hours=1)).isoformat(),
    }
    rpc.handlers["connected_app_get_binding_v2"] = lambda _payload: binding_row(snapshot)
    coordinator = SupabaseOAuthRepositoryCoordinator.build(
        database=rpc,
        redirect_uris={ConnectorProvider.GOOGLE: REDIRECT},
        permit_keys={"oauth-k1": ConnectedOAuthMasterKey("oauth-k1", b"x" * 32)},
        active_permit_key_id="oauth-k1",
        now=lambda: NOW,
    )
    completion, restarted = await coordinator.complete_and_reconstruct(command)
    assert isinstance(completion, OAuthCompletion)
    assert restarted is not None

    store = CredentialStore()
    vault = ConnectedCredentialVault(
        keys={"credential-k1": ConnectedCredentialMasterKey("credential-k1", b"z" * 32)},
        active_key_id="credential-k1",
        store=store,
        now=lambda: NOW + timedelta(seconds=1),
    )
    oauth_client_id_sha256 = hashlib.sha256(b"google-client-id").hexdigest()
    refresh = ProviderOAuthRefreshToken(
        "refresh-token-value-abcdefghijklmnopqrstuvwxyz",
        ProviderOAuthTokenBinding(
            provider=ConnectorProvider.GOOGLE,
            oauth_client_id_sha256=oauth_client_id_sha256,
            owner_id=OWNER_ID,
            connection_id=CONNECTION_ID,
            connection_incarnation_id=INCARNATION_ID,
            account_kind=ConnectorAccountKind.PERSONAL,
        ),
    )
    created = await vault.create(
        credential=completion.credential,
        connection_incarnation_id=INCARNATION_ID,
        authorization=completion.authorization,
        external_account_id_hash=HASH_A,
        oauth_client_id_sha256=oauth_client_id_sha256,
        refresh_token=refresh,
    )
    opened = await vault.open(
        account=restarted.account,
        credential=completion.credential,
        connection_incarnation_id=INCARNATION_ID,
        authorization=restarted.authorization,
    )

    assert created.metadata.authorization_snapshot_sha256 == snapshot.snapshot_sha256
    assert opened.record.metadata.authorization_snapshot_sha256 == snapshot.snapshot_sha256
    assert "refresh-token-value" not in created.secret_ciphertext


def exchange_command() -> OAuthExchangeCommand:
    return OAuthExchangeCommand(
        exchange_id=EXCHANGE_ID,
        consumption_id=FLOW_ID,
        flow_id=FLOW_ID,
        nonce_id=NONCE_ID,
        owner_id=OWNER_ID,
        connection_id=CONNECTION_ID,
        connection_incarnation_id=INCARNATION_ID,
        expected_base_revision=0,
        current_flow_nonce_sha256=hashlib.sha256(NONCE_ID.encode()).hexdigest(),
        session_binding_sha256=HASH_A,
        provider=ConnectorProvider.GOOGLE,
        resource=ConnectorResource.MAIL,
        account_kind=ConnectorAccountKind.PERSONAL,
        redirect_uri=REDIRECT,
        actions_sha256=action_set_sha256({ConnectorActionKind.MAIL_GET}),
        requested_scopes_sha256=authorization().granted_scopes_sha256,
        flow_binding_sha256=HASH_B,
        consume_binding_sha256=HASH_C,
        pkce_challenge="A" * 43,
        issued_at=NOW,
        deadline_at=NOW + timedelta(minutes=1),
    )


@pytest.mark.asyncio
async def test_encrypted_permit_survives_restart_and_only_fresh_winner_gets_claim():
    rpc = ScriptedRPC()
    custody: dict[str, object] | None = None
    consumed = False

    def put(payload: dict[str, object]) -> dict[str, object]:
        nonlocal custody
        custody = {
            "permit_id": payload["p_permit_id"],
            "exchange_binding_sha256": payload["p_exchange_binding_sha256"],
            "permit_binding_sha256": payload["p_permit_binding_sha256"],
            "capability_sha256": payload["p_capability_sha256"],
            "key_id": payload["p_key_id"],
            "wrapped_key_nonce": payload["p_wrapped_key_nonce"],
            "wrapped_key_ciphertext": payload["p_wrapped_key_ciphertext"],
            "secret_nonce": payload["p_secret_nonce"],
            "secret_ciphertext": payload["p_secret_ciphertext"],
            "record_binding_sha256": payload["p_record_binding_sha256"],
            "created_at": payload["p_issued_at"],
            "expires_at": payload["p_deadline_at"],
        }
        assert "capability_secret" not in repr(payload)
        return {"permit": {}, "custody": custody}

    def read(_payload: dict[str, object]) -> object:
        return None if consumed else custody

    def consume(payload: dict[str, object]) -> dict[str, object]:
        nonlocal consumed
        if consumed:
            return {
                "claimed": False,
                "status": "attempt_fenced",
                "permit_id": EXCHANGE_ID,
                "exchange_binding_sha256": payload["p_exchange_binding_sha256"],
                "permit_binding_sha256": payload["p_permit_binding_sha256"],
                "consumed_at": (NOW + timedelta(seconds=2)).isoformat(),
            }
        consumed = True
        return {
            "claimed": True,
            "status": "attempt_fenced",
            "permit_id": EXCHANGE_ID,
            "exchange_binding_sha256": payload["p_exchange_binding_sha256"],
            "permit_binding_sha256": payload["p_permit_binding_sha256"],
            "consumed_at": (NOW + timedelta(seconds=2)).isoformat(),
        }

    rpc.handlers["connected_app_oauth_put_permit_capability_v2"] = put
    rpc.handlers["connected_app_oauth_read_permit_capability_v2"] = read
    rpc.handlers["connected_app_oauth_consume_permit_v2"] = consume
    key = ConnectedOAuthMasterKey("oauth-k1", b"y" * 32)
    command = exchange_command()
    first = SupabaseOAuthFlowRepository(
        database=rpc,
        redirect_uris={ConnectorProvider.GOOGLE: REDIRECT},
        permit_keys={key.key_id: key},
        active_permit_key_id=key.key_id,
        now=lambda: NOW + timedelta(seconds=1),
    )

    issued = await first.issue_exchange_permit_once(command)
    restarted = SupabaseOAuthFlowRepository(
        database=rpc,
        redirect_uris={ConnectorProvider.GOOGLE: REDIRECT},
        permit_keys={key.key_id: key},
        active_permit_key_id=key.key_id,
        now=lambda: NOW + timedelta(seconds=1),
    )
    recovered = await restarted.read_exchange_permit(command)
    assert recovered is not None
    assert recovered.permit_binding_sha256 == issued.permit_binding_sha256
    assert "redacted" in repr(recovered)
    claim = await restarted.consume_exchange_permit_for_dispatch(command, recovered)
    assert claim.permit_id == EXCHANGE_ID

    with pytest.raises(OAuthContractError, match="OAUTH_EXCHANGE_RECOVERY_REQUIRED"):
        await restarted.consume_exchange_permit_for_dispatch(command, recovered)
