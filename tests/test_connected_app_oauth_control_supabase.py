from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib
from pathlib import Path

import pytest

from backend.connected_app_contracts import ConnectorAccountKind
from backend.connected_app_oauth import (
    OAuthBrokerFlowCommand,
    OAuthConsumeCommand,
    OAuthFlowConsumption,
    OAuthFlowRecord,
)
from backend.connected_app_oauth_control import oauth_start_command_binding_sha256
from backend.connected_app_oauth_control_supabase import (
    ConnectedOAuthOperatorStoreError,
    SupabaseConnectedOAuthOperatorStore,
)
from backend.connected_app_policy import (
    ConnectorActionKind,
    ConnectorProvider,
    ConnectorResource,
    action_set_sha256,
)
from backend.connected_app_service import OAuthStartCommand
from backend.connected_app_scopes import delegated_scope_plan


ROOT = Path(__file__).resolve().parents[1]
OWNER = "10000000-0000-4000-8000-000000000001"
REQUEST = "20000000-0000-4000-8000-000000000002"
FLOW = "30000000-0000-4000-8000-000000000003"
NONCE = "40000000-0000-4000-8000-000000000004"
CONNECTION = "50000000-0000-4000-8000-000000000005"
INCARNATION = "60000000-0000-4000-8000-000000000006"
NOW = datetime(2026, 11, 8, 1, 0, tzinfo=UTC)
REDIRECT = "https://www.askcrump.com/api/connected-apps/oauth/callback/google"
ACTIONS = frozenset({ConnectorActionKind.MAIL_GET, ConnectorActionKind.MAIL_SEND})


def command() -> OAuthStartCommand:
    return OAuthStartCommand(
        request_id=REQUEST,
        owner_id=OWNER,
        session_binding_sha256="1" * 64,
        provider=ConnectorProvider.GOOGLE,
        resource=ConnectorResource.MAIL,
        account_kind=ConnectorAccountKind.PERSONAL,
        actions=ACTIONS,
        redirect_uri=REDIRECT,
        connection_id=None,
        requested_at=NOW,
    )


def start_row(**changes):
    cmd = command()
    row = {
        "request_id": REQUEST,
        "owner_id": OWNER,
        "session_binding_sha256": cmd.session_binding_sha256,
        "command_binding_sha256": oauth_start_command_binding_sha256(cmd),
        "requested_connection_id": None,
        "flow_id": FLOW,
        "nonce_id": NONCE,
        "connection_id": CONNECTION,
        "connection_incarnation_id": INCARNATION,
        "expected_base_revision": 0,
        "current_flow_nonce_sha256": hashlib.sha256(NONCE.encode()).hexdigest(),
        "provider": "google",
        "resource": "mail",
        "account_kind": "personal",
        "actions": sorted(action.value for action in ACTIONS),
        "actions_sha256": action_set_sha256(ACTIONS),
        "redirect_uri_sha256": hashlib.sha256(REDIRECT.encode()).hexdigest(),
        "requested_at": NOW.isoformat(),
        "expires_at": (NOW + timedelta(minutes=10)).isoformat(),
    }
    row.update(changes)
    return row


def decoded_flow() -> OAuthFlowRecord:
    scopes = frozenset(
        delegated_scope_plan(
            ConnectorProvider.GOOGLE,
            ACTIONS,
            account_kind=ConnectorAccountKind.PERSONAL,
        ).delegated_scopes
    )
    broker = OAuthBrokerFlowCommand(
        flow_id=FLOW,
        nonce_id=NONCE,
        owner_id=OWNER,
        connection_id=CONNECTION,
        connection_incarnation_id=INCARNATION,
        expected_base_revision=0,
        current_flow_nonce_sha256=hashlib.sha256(NONCE.encode()).hexdigest(),
        session_binding_sha256="1" * 64,
        provider=ConnectorProvider.GOOGLE,
        resource=ConnectorResource.MAIL,
        account_kind=ConnectorAccountKind.PERSONAL,
        actions=ACTIONS,
        actions_sha256=action_set_sha256(ACTIONS),
        requested_scopes=scopes,
        requested_scopes_sha256=hashlib.sha256(
            ("[" + ",".join(f'\"{value}\"' for value in sorted(scopes)) + "]").encode()
        ).hexdigest(),
        state_sha256="2" * 64,
        pkce_challenge="P" * 43,
        redirect_uri=REDIRECT,
        created_at=NOW,
        expires_at=NOW + timedelta(minutes=10),
    )
    return OAuthFlowRecord.from_broker_command(broker)


def consume_command(flow: OAuthFlowRecord) -> OAuthConsumeCommand:
    return OAuthConsumeCommand(
        consumption_id=flow.flow_id,
        flow_id=flow.flow_id,
        owner_id=flow.owner_id,
        connection_id=flow.connection_id,
        connection_incarnation_id=flow.connection_incarnation_id,
        expected_base_revision=flow.expected_base_revision,
        current_flow_nonce_sha256=flow.current_flow_nonce_sha256,
        session_binding_sha256=flow.session_binding_sha256,
        provider=flow.provider,
        resource=flow.resource,
        account_kind=flow.account_kind,
        redirect_uri=flow.redirect_uri,
        state_sha256=flow.state_sha256,
        flow_binding_sha256=flow.binding_sha256,
        flow_created_at=flow.created_at,
        flow_expires_at=flow.expires_at,
    )


class RPC:
    def __init__(self, values):
        self.values = list(values)
        self.calls = []

    async def rpc(self, name, payload, *, retry_transient=False):
        self.calls.append((name, payload, retry_transient))
        value = self.values.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


class Decoder:
    def __init__(self, flow=None):
        self.values = []
        self.flow = flow or decoded_flow()

    def decode_flow(self, value):
        self.values.append(value)
        return self.flow


def store(rpc, decoder=None):
    return SupabaseConnectedOAuthOperatorStore(
        database=rpc,
        flow_decoder=decoder or Decoder(),
        redirect_uris={
            ConnectorProvider.GOOGLE: REDIRECT,
            ConnectorProvider.MICROSOFT: (
                "https://www.askcrump.com/api/connected-apps/oauth/callback/microsoft"
            ),
        },
    )


@pytest.mark.asyncio
async def test_prepare_start_sends_only_content_free_exact_authority_and_parses_replay():
    rpc = RPC([start_row()])
    result = await store(rpc).prepare_start(
        command(),
        proposed_flow_id=FLOW,
        proposed_nonce_id=NONCE,
        proposed_connection_id=CONNECTION,
        proposed_connection_incarnation_id=INCARNATION,
    )
    assert result.command == command()
    assert result.flow_id == FLOW
    name, payload, retry = rpc.calls[0]
    assert name == "connected_app_operator_prepare_oauth_start_v2"
    assert retry is False
    assert payload["p_command_binding_sha256"] == oauth_start_command_binding_sha256(command())
    assert payload["p_current_flow_nonce_sha256"] == hashlib.sha256(NONCE.encode()).hexdigest()
    rendered = repr(payload).casefold()
    for forbidden in ("authorization_code", "refresh_token", "access_token", "verifier"):
        assert forbidden not in rendered


@pytest.mark.asyncio
async def test_start_readback_rejects_redirect_or_command_binding_drift():
    rpc = RPC([start_row(redirect_uri_sha256="f" * 64)])
    with pytest.raises(ConnectedOAuthOperatorStoreError) as caught:
        await store(rpc).read_start(owner_id=OWNER, request_id=REQUEST)
    assert str(caught.value) == "OAUTH_OPERATOR_STORE_BINDING_MISMATCH"


@pytest.mark.asyncio
async def test_callback_store_receives_hashes_only_and_uses_shared_flow_decoder():
    flow_row = {"opaque": "content-free-flow-row"}
    rpc = RPC([{"flow": flow_row, "callback_received_at": NOW.isoformat()}])
    decoder = Decoder()
    result = await store(rpc, decoder).bind_callback(
        owner_id=OWNER,
        session_binding_sha256="1" * 64,
        provider=ConnectorProvider.GOOGLE,
        state_sha256="2" * 64,
        callback_binding_sha256="3" * 64,
        received_at=NOW,
    )
    assert result is not None
    assert decoder.values == [flow_row]
    name, payload, retry = rpc.calls[0]
    assert result.accepted_at == NOW
    assert name == "connected_app_operator_prepare_oauth_callback_v2"
    assert retry is False
    assert payload == {
        "p_owner_id": OWNER,
        "p_session_binding_sha256": "1" * 64,
        "p_provider": "google",
        "p_state_sha256": "2" * 64,
        "p_callback_binding_sha256": "3" * 64,
        "p_received_at": NOW.isoformat(),
    }


@pytest.mark.asyncio
async def test_callback_denial_is_one_state_bound_content_free_retirement_rpc():
    rpc = RPC(
        [
            {
                "denied": True,
                "flow_id": FLOW,
                "connection_id": CONNECTION,
                "observed_at": NOW.isoformat(),
            }
        ]
    )
    result = await store(rpc).deny_callback(
        owner_id=OWNER,
        session_binding_sha256="1" * 64,
        provider=ConnectorProvider.GOOGLE,
        state_sha256="2" * 64,
        denial_binding_sha256="3" * 64,
        received_at=NOW,
    )

    assert result.owner_id == OWNER
    assert result.flow_id == FLOW
    assert result.connection_id == CONNECTION
    assert rpc.calls == [
        (
            "connected_app_operator_deny_oauth_callback_v1",
            {
                "p_owner_id": OWNER,
                "p_session_binding_sha256": "1" * 64,
                "p_provider": "google",
                "p_state_sha256": "2" * 64,
                "p_error": "access_denied",
                "p_denial_binding_sha256": "3" * 64,
                "p_received_at": NOW.isoformat(),
            },
            False,
        )
    ]


@pytest.mark.asyncio
async def test_callback_accept_is_one_atomic_hash_only_consumption_rpc():
    flow = decoded_flow()
    command = consume_command(flow)
    expected = OAuthFlowConsumption.build_for_command(command, consumed_at=NOW)
    rpc = RPC(
        [
            {
                "consumption_id": expected.consumption_id,
                "flow_id": expected.flow_id,
                "connection_id": expected.connection_id,
                "connection_incarnation_id": expected.connection_incarnation_id,
                "expected_base_revision": expected.expected_base_revision,
                "current_flow_nonce_sha256": expected.current_flow_nonce_sha256,
                "consume_binding_sha256": expected.consume_binding_sha256,
                "flow_binding_sha256": expected.flow_binding_sha256,
                "consumed_at": expected.consumed_at.isoformat(),
            }
        ]
    )
    result = await store(rpc).accept_callback(
        provider=ConnectorProvider.GOOGLE,
        state_sha256=flow.state_sha256,
        callback_binding_sha256="3" * 64,
        received_at=NOW,
        command=command,
    )
    assert result == expected
    name, payload, retry = rpc.calls[0]
    assert name == "connected_app_operator_accept_oauth_callback_v1"
    assert retry is False
    assert payload == {
        "p_provider": "google",
        "p_state_sha256": "2" * 64,
        "p_callback_binding_sha256": "3" * 64,
        "p_received_at": NOW.isoformat(),
        "p_consumption_id": FLOW,
        "p_owner_id": OWNER,
        "p_connection_id": CONNECTION,
        "p_connection_incarnation_id": INCARNATION,
        "p_expected_base_revision": 0,
        "p_current_flow_nonce_sha256": flow.current_flow_nonce_sha256,
        "p_session_binding_sha256": flow.session_binding_sha256,
        "p_flow_binding_sha256": flow.binding_sha256,
        "p_consume_binding_sha256": command.binding_sha256,
    }


@pytest.mark.asyncio
async def test_callback_readback_returns_exact_active_public_connection():
    rpc = RPC(
        [
            {
                "connection_id": CONNECTION,
                "provider": "google",
                "resource": "mail",
                "account_kind": "personal",
                "granted_actions": sorted(action.value for action in ACTIONS),
                "authorization_state": "active",
                "authorization_revision": 1,
                "authorization_snapshot_sha256": "4" * 64,
                "authorization_expires_at": (NOW + timedelta(hours=1)).isoformat(),
                "updated_at": NOW.isoformat(),
            }
        ]
    )
    result = await store(rpc).read_callback(
        provider=ConnectorProvider.GOOGLE,
        callback_binding_sha256="3" * 64,
    )
    assert result is not None
    assert result.connection_id == CONNECTION
    assert result.authorization_revision == 1
    assert rpc.calls[0][2] is True


def test_operator_bridge_migration_is_private_hash_only_and_service_role_scoped():
    sql = (
        ROOT / "migrations" / "20261108064000_connected_oauth_operator_bridge.sql"
    ).read_text(encoding="utf-8")
    folded = sql.casefold()
    for marker in (
        "oauth_operator_starts",
        "oauth_callback_requests",
        "connected_app_operator_prepare_oauth_start_v1",
        "connected_app_operator_prepare_oauth_callback_v1",
        "connected_app_operator_accept_oauth_callback_v1",
        "connected_app_operator_read_oauth_callback_v1",
        "oauth_operator_target_fingerprint_v1",
        "effective_received_at := callback_row.received_at",
        "pg_publication_namespace",
        "puballtables",
        "relpersistence",
        "attacl",
        "indisvalid",
        'collate pg_catalog."c"',
        "from pg_catalog.unnest(policy_row.polroles)",
        "pg_catalog.pg_am",
        "pg_catalog.pg_tablespace",
        "pg_catalog.pg_opclass",
        "force row level security",
        "to service_role",
        "set search_path = ''",
    ):
        assert marker in folded
    assert "authorization_code" not in folded
    assert "refresh_token" not in folded
    assert "access_token" not in folded
    assert "pkce_verifier" not in folded
    assert "policy_row.polroles," not in folded
    assert "index_link.indcollation::text" not in folded
    assert "index_link.indclass::text" not in folded
