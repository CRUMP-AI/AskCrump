from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib
import inspect
from types import SimpleNamespace

import pytest

from backend.connected_app_contracts import (
    ConnectedAccountRef,
    ConnectedAuthorizationSnapshot,
    ConnectionAuthorizationState,
    ConnectorAccountKind,
)
from backend.connected_app_dispatch import ConnectedDispatchError
from backend.connected_app_policy import (
    ConnectorActionKind,
    ConnectorProvider,
    ConnectorResource,
)
from backend.connected_app_runtime import (
    ConnectedActionAccessRecoveryRequest,
    ConnectedActionAuthorityRecord,
    ConnectedActionClaim,
    ConnectedActionClaimRequest,
    ConnectedActionClaimStatus,
    ConnectedActionLookupRecord,
    ConnectedCredentialPhase,
    ConnectedReadTerminalRecord,
    _record_hash,
)
from backend.connected_app_runtime_adapters import (
    SupabaseConnectedActionLedger,
    SupabaseConnectedCredentialGateway,
)


NOW = datetime(2026, 11, 8, 5, 30, tzinfo=UTC)
OWNER = "11111111-1111-4111-8111-111111111111"
TASK = "22222222-2222-4222-8222-222222222222"
TURN = "33333333-3333-4333-8333-333333333333"
CONNECTION = "44444444-4444-4444-8444-444444444444"
OPERATION = "55555555-5555-4555-8555-555555555555"
GRANT = "66666666-6666-4666-8666-666666666666"
REQUEST = "77777777-7777-4777-8777-777777777777"
CLAIM = "88888888-8888-4888-8888-888888888888"
EXPIRED_CLAIM = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"
USE = "99999999-9999-4999-8999-999999999999"
HANDLE = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
INCARNATION = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
ALIAS = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
SHA = hashlib.sha256(b"exact-binding").hexdigest()


class FakeRPC:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object], bool]] = []
        self.responses: dict[str, object] = {}
        self.failures: dict[str, Exception] = {}

    async def rpc(self, function_name, payload, *, retry_transient=False):
        self.calls.append((function_name, payload, retry_transient))
        failure = self.failures.get(function_name)
        if failure is not None:
            raise failure
        return self.responses.get(function_name)


def lookup() -> ConnectedActionLookupRecord:
    return ConnectedActionLookupRecord(
        operation_id=OPERATION,
        owner_id=OWNER,
        task_id=TASK,
        turn_id=TURN,
        connection_id=CONNECTION,
        provider=ConnectorProvider.GOOGLE,
        resource=ConnectorResource.MAIL,
        action=ConnectorActionKind.MAIL_GET,
        parameters_sha256=SHA,
        resource_version_sha256=None,
        binding_sha256=SHA,
        idempotency_key_hash=SHA,
    )


def authority() -> ConnectedActionAuthorityRecord:
    return ConnectedActionAuthorityRecord(
        grant_id=GRANT,
        grant_sha256=SHA,
        grant_expires_at=NOW + timedelta(minutes=10),
        approval_id=None,
        approval_sha256=None,
        approval_expires_at=None,
        authorization_revision=1,
        authorization_snapshot_sha256=SHA,
        granted_actions_sha256=SHA,
        granted_scopes_sha256=SHA,
        task_state_revision=1,
        policy_version="connected-action-policy-v1",
        decided_at=NOW,
    )


def claim_request() -> ConnectedActionClaimRequest:
    return ConnectedActionClaimRequest(
        lookup=lookup(),
        claim_request_id=REQUEST,
        authority_sha256=authority().authority_sha256,
        granted_actions_sha256=SHA,
        mutates_external_state=False,
        requested_at=NOW,
        execution_deadline=NOW + timedelta(minutes=5),
    )


def row(*, status: str = "claimed") -> dict[str, object]:
    values: dict[str, object] = {
        "operation_id": OPERATION,
        "action_id": OPERATION,
        "owner_id": OWNER,
        "task_id": TASK,
        "turn_id": TURN,
        "connection_id": CONNECTION,
        "grant_id": GRANT,
        "provider": "google",
        "resource": "mail",
        "action": "mail.get",
        "authorization_revision": 1,
        "authorization_snapshot_sha256": SHA,
        "granted_actions_sha256": SHA,
        "granted_scopes_sha256": SHA,
        "parameters_sha256": SHA,
        "resource_version_sha256": None,
        "authority_sha256": authority().authority_sha256,
        "idempotency_key_sha256": SHA,
        "invocation_binding_sha256": SHA,
        "task_state_revision": 1,
        "status": status,
        "mutates_external_state": False,
        "approval_class": "none",
        "claim_request_id": REQUEST,
        "claim_id": CLAIM,
        "fencing_token": 9,
        "lease_expires_at": (NOW + timedelta(seconds=45)).isoformat(),
        "execution_deadline": (NOW + timedelta(minutes=5)).isoformat(),
        "access_phase": None,
        "read_use_nonce": None,
        "read_credential_expires_at": None,
        "read_consumed_at": None,
        "preobserve_use_nonce": None,
        "preobserve_credential_expires_at": None,
        "preobserve_consumed_at": None,
        "access_started_at": None,
        "effect_use_nonce": None,
        "effect_credential_expires_at": None,
        "effect_consumed_at": None,
        "effect_started_at": None,
        "postobserve_use_nonce": None,
        "postobserve_started_at": None,
        "postobserve_expires_at": None,
        "postobserve_consumed_at": None,
        "postobserve_impossible": False,
        "terminal_outcome": None,
        "terminal_binding_sha256": None,
        "terminal_resource_version_sha256": None,
        "provider_request_id_sha256": None,
        "provider_resource_id_sha256": None,
        "observed_at": None,
        "terminal_at": None,
        "created_at": NOW.isoformat(),
        "updated_at": NOW.isoformat(),
    }
    return values


@pytest.mark.asyncio
async def test_claim_and_response_loss_readback_use_v2_only() -> None:
    rpc = FakeRPC()
    rpc.responses["connected_app_claim_action_v2"] = row()
    rpc.responses["connected_app_read_action_v2"] = row()
    ledger = SupabaseConnectedActionLedger(rpc, new_uuid=lambda: CLAIM)
    request = claim_request()

    claimed = await ledger.claim(request, authority())
    unrelated = await ledger.readback(request.lookup)
    recovered = await ledger.readback(request)

    assert claimed.status is ConnectedActionClaimStatus.CLAIMED
    assert claimed.fencing_token == 9
    assert unrelated is not None
    assert unrelated.status is ConnectedActionClaimStatus.BUSY
    assert unrelated.fencing_token is None
    assert recovered is not None
    assert recovered.status is ConnectedActionClaimStatus.CLAIMED
    assert recovered.fencing_token == 9
    assert [call[0] for call in rpc.calls] == [
        "connected_app_claim_action_v2",
        "connected_app_read_action_v2",
        "connected_app_read_action_v2",
    ]
    assert rpc.calls[0][2] is False
    assert rpc.calls[1][2] is True
    assert all("_v1" not in call[0] for call in rpc.calls)


@pytest.mark.asyncio
async def test_terminal_replay_and_settlement_are_exact_and_no_legacy_fallback() -> None:
    rpc = FakeRPC()
    terminal = ConnectedReadTerminalRecord(
        operation_id=OPERATION,
        provider=ConnectorProvider.GOOGLE,
        resource=ConnectorResource.MAIL,
        action=ConnectorActionKind.MAIL_GET,
        binding_sha256=SHA,
        authority_sha256=authority().authority_sha256,
        idempotency_key_hash=SHA,
        observed_at=NOW + timedelta(seconds=2),
        resource_version_sha256=SHA,
    )
    terminal_row = row(status="terminal")
    terminal_row.update(
        {
            "access_phase": "read",
            "read_use_nonce": USE,
            "read_credential_expires_at": (NOW + timedelta(seconds=45)).isoformat(),
            "read_consumed_at": (NOW + timedelta(seconds=1)).isoformat(),
            "access_started_at": NOW.isoformat(),
            "terminal_outcome": "read",
            "terminal_binding_sha256": _record_hash(terminal),
            "terminal_resource_version_sha256": SHA,
            "observed_at": terminal.observed_at.isoformat(),
            "terminal_at": (NOW + timedelta(seconds=3)).isoformat(),
        }
    )
    rpc.responses["connected_app_read_action_v2"] = terminal_row
    rpc.responses["connected_app_settle_action_v2"] = terminal_row
    ledger = SupabaseConnectedActionLedger(rpc)
    active = ConnectedActionClaim(
        claim_id=CLAIM,
        status=ConnectedActionClaimStatus.ACCESS_GRANTED,
        binding_sha256=SHA,
        authority_sha256=authority().authority_sha256,
        granted_actions_sha256=SHA,
        fencing_token=9,
        lease_expires_at=NOW + timedelta(seconds=45),
        execution_deadline=NOW + timedelta(minutes=5),
        access_started_at=NOW,
        access_phase=ConnectedCredentialPhase.READ,
        access_use_nonce=USE,
    )

    settled = await ledger.settle(active, terminal)
    replayed = await ledger.readback(lookup())

    assert settled.terminal == terminal
    assert replayed is not None and replayed.terminal == terminal
    assert rpc.calls[0][0] == "connected_app_settle_action_v2"
    assert rpc.calls[0][2] is False
    assert rpc.calls[0][1]["p_claim_id"] == CLAIM
    assert rpc.calls[0][1]["p_fencing_token"] == 9
    assert rpc.calls[0][1]["p_terminal_resource_version_sha256"] == SHA
    assert "p_owner_id" not in rpc.calls[0][1]


@pytest.mark.asyncio
async def test_access_recovery_uses_v2_fresh_authority_and_exact_invocation() -> None:
    rpc = FakeRPC()
    recovered_row = row(status="access_granted")
    recovered_row.update(
        {
            "access_phase": "read",
            "read_use_nonce": USE,
            "read_credential_expires_at": (NOW + timedelta(seconds=45)).isoformat(),
            "access_started_at": NOW.isoformat(),
        }
    )
    rpc.responses["connected_app_recover_access_v2"] = recovered_row
    ledger = SupabaseConnectedActionLedger(rpc, new_uuid=lambda: CLAIM)
    record = ConnectedActionAccessRecoveryRequest(
        lookup=lookup(),
        expired_claim_id=EXPIRED_CLAIM,
        claim_request_id=REQUEST,
        authority_sha256=authority().authority_sha256,
        task_state_revision=1,
        authorization_revision=1,
        authorization_snapshot_sha256=SHA,
        granted_actions_sha256=SHA,
        granted_scopes_sha256=SHA,
        phase=ConnectedCredentialPhase.READ,
        credential_use_nonce=USE,
        credential_expires_at=NOW + timedelta(seconds=45),
        requested_at=NOW,
        execution_deadline=NOW + timedelta(minutes=5),
    )

    recovered = await ledger.recover_access(record, authority())

    assert recovered.status is ConnectedActionClaimStatus.ACCESS_GRANTED
    assert recovered.claim_id == CLAIM
    assert recovered.fencing_token == 9
    assert recovered.access_use_nonce == USE
    assert [call[0] for call in rpc.calls] == ["connected_app_recover_access_v2"]
    assert rpc.calls[0][2] is False
    payload = rpc.calls[0][1]
    assert payload["p_expired_claim_id"] == EXPIRED_CLAIM
    assert payload["p_invocation_binding_sha256"] == SHA
    assert payload["p_authority_sha256"] == authority().authority_sha256


class FakeTokenSource:
    def __init__(self, token: object) -> None:
        self.token = token
        self.calls = 0

    async def issue_access_token(self, *, account, credential):
        self.calls += 1
        return self.token


class FakeTokenBroker:
    def __init__(self) -> None:
        self.source = FakeTokenSource(object())
        self.calls: list[dict[str, object]] = []

    def bind(self, **values):
        self.calls.append(values)
        return self.source


def authorization() -> ConnectedAuthorizationSnapshot:
    return ConnectedAuthorizationSnapshot.build(
        owner_id=OWNER,
        connection_id=CONNECTION,
        provider=ConnectorProvider.GOOGLE,
        resource=ConnectorResource.MAIL,
        account_kind=ConnectorAccountKind.PERSONAL,
        revision=1,
        granted_actions=frozenset({ConnectorActionKind.MAIL_GET}),
        granted_scopes=frozenset({"https://www.googleapis.com/auth/gmail.readonly"}),
        state=ConnectionAuthorizationState.ACTIVE,
        issued_at=NOW - timedelta(hours=1),
        expires_at=NOW + timedelta(hours=1),
    )


def account() -> ConnectedAccountRef:
    return ConnectedAccountRef(
        owner_id=OWNER,
        connection_id=CONNECTION,
        provider=ConnectorProvider.GOOGLE,
        resource=ConnectorResource.MAIL,
        account_kind=ConnectorAccountKind.PERSONAL,
        external_account_id_hash=SHA,
    )


def binding_row(auth: ConnectedAuthorizationSnapshot) -> dict[str, object]:
    return {
        "owner_id": OWNER,
        "connection_id": CONNECTION,
        "provider": "google",
        "resource": "mail",
        "account_kind": "personal",
        "connection_incarnation_id": INCARNATION,
        "authorization_revision": 1,
        "authorization_state": "active",
        "authorization_snapshot_sha256": auth.snapshot_sha256,
        "authorization_issued_at": auth.issued_at.isoformat(),
        "granted_actions": ["mail.get"],
        "granted_actions_sha256": auth.granted_actions_sha256,
        "granted_scopes_sha256": auth.granted_scopes_sha256,
        "external_account_id_sha256": SHA,
        "broker_credential_ref": HANDLE,
        "credential_ref_sha256": hashlib.sha256(HANDLE.encode()).hexdigest(),
        "current_flow_nonce_sha256": SHA,
        "authorization_expires_at": auth.expires_at.isoformat(),
        "revoked_at": None,
    }


@pytest.mark.asyncio
async def test_credential_gateway_consumes_database_nonce_before_one_use_token() -> None:
    auth = authorization()
    rpc = FakeRPC()
    rpc.responses["connected_app_get_binding_v2"] = binding_row(auth)
    rpc.responses["connected_app_consume_credential_lease_v1"] = {
        "operation_id": OPERATION,
        "action_id": OPERATION,
        "phase": "read",
        "consumed": True,
        "consumed_at": (NOW + timedelta(seconds=1)).isoformat(),
    }
    tokens = FakeTokenBroker()
    gateway = SupabaseConnectedCredentialGateway(
        database=rpc,
        tokens=tokens,  # type: ignore[arg-type]
        now=lambda: NOW,
        new_uuid=lambda: ALIAS,
    )
    auth_record = authority()
    active = ConnectedActionClaim(
        claim_id=CLAIM,
        status=ConnectedActionClaimStatus.ACCESS_GRANTED,
        binding_sha256=SHA,
        authority_sha256=auth_record.authority_sha256,
        granted_actions_sha256=auth.granted_actions_sha256,
        fencing_token=9,
        lease_expires_at=NOW + timedelta(minutes=1),
        execution_deadline=NOW + timedelta(minutes=5),
        access_started_at=NOW,
        access_phase=ConnectedCredentialPhase.READ,
        access_use_nonce=USE,
    )
    intent = SimpleNamespace(
        owner_id=OWNER,
        connection_id=CONNECTION,
        provider=ConnectorProvider.GOOGLE,
        resource=ConnectorResource.MAIL,
    )
    lease = await gateway.issue_child_lease(
        account=account(),
        authorization=auth,
        intent=intent,
        claim=active,
        authority=auth_record,
        phase=ConnectedCredentialPhase.READ,
        use_nonce=USE,
        hard_expires_at=NOW + timedelta(seconds=45),
    )

    assert lease.credential.handle_id == ALIAS
    assert tokens.calls[0]["credential"].handle_id == HANDLE
    assert tokens.calls[0]["presented_credential"] == lease.credential
    receipt = await gateway.consume_once(
        lease=lease,
        operation_id=OPERATION,
        action=ConnectorActionKind.MAIL_GET,
    )
    token = await gateway.issue_access_token(account=account(), credential=lease.credential)

    assert receipt.use_nonce == USE
    assert token is tokens.source.token
    assert tokens.source.calls == 1
    consume_call = next(
        call for call in rpc.calls if call[0] == "connected_app_consume_credential_lease_v1"
    )
    assert consume_call[2] is False
    assert consume_call[1]["p_authority_sha256"] == auth_record.authority_sha256
    with pytest.raises(ConnectedDispatchError):
        await gateway.issue_access_token(account=account(), credential=lease.credential)


@pytest.mark.asyncio
async def test_credential_consumption_response_loss_fails_closed_without_retry() -> None:
    auth = authorization()
    rpc = FakeRPC()
    rpc.responses["connected_app_get_binding_v2"] = binding_row(auth)
    rpc.failures["connected_app_consume_credential_lease_v1"] = TimeoutError("lost")
    tokens = FakeTokenBroker()
    gateway = SupabaseConnectedCredentialGateway(
        database=rpc,
        tokens=tokens,  # type: ignore[arg-type]
        now=lambda: NOW,
        new_uuid=lambda: ALIAS,
    )
    auth_record = authority()
    active = ConnectedActionClaim(
        claim_id=CLAIM,
        status=ConnectedActionClaimStatus.ACCESS_GRANTED,
        binding_sha256=SHA,
        authority_sha256=auth_record.authority_sha256,
        granted_actions_sha256=auth.granted_actions_sha256,
        fencing_token=9,
        lease_expires_at=NOW + timedelta(minutes=1),
        execution_deadline=NOW + timedelta(minutes=5),
        access_started_at=NOW,
        access_phase=ConnectedCredentialPhase.READ,
        access_use_nonce=USE,
    )
    lease = await gateway.issue_child_lease(
        account=account(),
        authorization=auth,
        intent=SimpleNamespace(
            owner_id=OWNER,
            connection_id=CONNECTION,
            provider=ConnectorProvider.GOOGLE,
            resource=ConnectorResource.MAIL,
        ),
        claim=active,
        authority=auth_record,
        phase=ConnectedCredentialPhase.READ,
        use_nonce=USE,
        hard_expires_at=NOW + timedelta(seconds=45),
    )

    with pytest.raises(ConnectedDispatchError) as caught:
        await gateway.consume_once(
            lease=lease,
            operation_id=OPERATION,
            action=ConnectorActionKind.MAIL_GET,
        )
    assert caught.value.code == "CONNECTED_DISPATCH_LEASE_UNCERTAIN"
    assert sum(
        call[0] == "connected_app_consume_credential_lease_v1" for call in rpc.calls
    ) == 1
    with pytest.raises(ConnectedDispatchError):
        await gateway.issue_access_token(account=account(), credential=lease.credential)


def test_adapter_source_has_no_legacy_ledger_fallback() -> None:
    source = inspect.getsource(SupabaseConnectedActionLedger)
    assert "connected_app_claim_action_v1" not in source
    assert "connected_app_read_action_v1" not in source
    assert "connected_app_recover_access_v1" not in source
    assert "connected_app_settle_action_v1" not in source
    gateway = inspect.getsource(SupabaseConnectedCredentialGateway)
    assert "connected_app_get_binding_v2" in gateway
    assert "connected_app_get_binding_v1" not in gateway
