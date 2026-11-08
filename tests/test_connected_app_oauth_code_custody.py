from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib

import pytest

from backend.connected_app_durable_oauth import ConnectedOAuthMasterKey
from backend.connected_app_oauth import (
    OAuthAuthorizationCodeSecret,
    OAuthConsumeCommand,
    OAuthExchangeCommand,
)
from backend.connected_app_oauth_code_custody import (
    ConnectedOAuthAuthorizationCodeVault,
    ConnectedOAuthCodeCustodyError,
    SupabaseOAuthAuthorizationCodeCustodyStore,
)
from backend.connected_app_policy import (
    ConnectorProvider,
    ConnectorResource,
)
from backend.connected_app_contracts import ConnectorAccountKind


NOW = datetime(2026, 11, 8, 8, 0, tzinfo=UTC)
OWNER = "10000000-0000-4000-8000-000000000001"
FLOW = "20000000-0000-4000-8000-000000000002"
CONNECTION = "30000000-0000-4000-8000-000000000003"
INCARNATION = "40000000-0000-4000-8000-000000000004"
NONCE = "50000000-0000-4000-8000-000000000005"
SESSION_HASH = "1" * 64
STATE_HASH = hashlib.sha256(("s" * 43).encode()).hexdigest()
CALLBACK_HASH = "2" * 64
FLOW_HASH = "3" * 64
NONCE_HASH = "4" * 64
CODE = "provider-code-opaque-0123456789"


def commands() -> tuple[OAuthConsumeCommand, OAuthExchangeCommand]:
    consume = OAuthConsumeCommand(
        consumption_id=FLOW,
        flow_id=FLOW,
        owner_id=OWNER,
        connection_id=CONNECTION,
        connection_incarnation_id=INCARNATION,
        expected_base_revision=0,
        current_flow_nonce_sha256=NONCE_HASH,
        session_binding_sha256=SESSION_HASH,
        provider=ConnectorProvider.GOOGLE,
        resource=ConnectorResource.MAIL,
        account_kind=ConnectorAccountKind.PERSONAL,
        redirect_uri="https://www.askcrump.com/api/connected-apps/oauth/callback/google",
        state_sha256=STATE_HASH,
        flow_binding_sha256=FLOW_HASH,
        flow_created_at=NOW - timedelta(minutes=1),
        flow_expires_at=NOW + timedelta(minutes=8),
    )
    exchange = OAuthExchangeCommand(
        exchange_id=FLOW,
        consumption_id=FLOW,
        flow_id=FLOW,
        nonce_id=NONCE,
        owner_id=OWNER,
        connection_id=CONNECTION,
        connection_incarnation_id=INCARNATION,
        expected_base_revision=0,
        current_flow_nonce_sha256=NONCE_HASH,
        session_binding_sha256=SESSION_HASH,
        provider=ConnectorProvider.GOOGLE,
        resource=ConnectorResource.MAIL,
        account_kind=ConnectorAccountKind.PERSONAL,
        redirect_uri=consume.redirect_uri,
        actions_sha256="5" * 64,
        requested_scopes_sha256="6" * 64,
        flow_binding_sha256=FLOW_HASH,
        consume_binding_sha256=consume.binding_sha256,
        pkce_challenge="p" * 43,
        issued_at=NOW,
        deadline_at=NOW + timedelta(minutes=2),
    )
    return consume, exchange


class FakeRPC:
    def __init__(self, *, lose_accept_response: bool = False) -> None:
        self.lose_accept_response = lose_accept_response
        self.accept_payload: dict[str, object] | None = None
        self.calls: list[str] = []

    async def rpc(self, name, payload, *, retry_transient=False):
        assert retry_transient is False
        self.calls.append(name)
        if name == "connected_app_operator_accept_oauth_callback_v2":
            self.accept_payload = dict(payload)
            if self.lose_accept_response:
                self.lose_accept_response = False
                raise RuntimeError("response lost after commit")
            return self._consumption()
        if name == "connected_app_oauth_code_read_v1":
            assert self.accept_payload is not None
            return self._row(lookup=False)
        if name == "connected_app_oauth_code_claim_v1":
            assert self.accept_payload is not None
            return self._row(lookup=True, claimed_at=NOW + timedelta(seconds=1))
        if name == "connected_app_oauth_code_retire_v1":
            return {"retired": True, "retired_at": NOW + timedelta(seconds=2)}
        raise AssertionError(name)

    def _consumption(self):
        assert self.accept_payload is not None
        return {
            "consumption_id": FLOW,
            "flow_id": FLOW,
            "connection_id": CONNECTION,
            "connection_incarnation_id": INCARNATION,
            "expected_base_revision": 0,
            "current_flow_nonce_sha256": NONCE_HASH,
            "consume_binding_sha256": self.accept_payload[
                "p_consume_binding_sha256"
            ],
            "flow_binding_sha256": FLOW_HASH,
            "consumed_at": NOW,
        }

    def _row(self, *, lookup: bool, claimed_at=None):
        assert self.accept_payload is not None
        value = {
            "status": "available",
            "code_authority_binding_sha256": self.accept_payload[
                "p_code_authority_binding_sha256"
            ],
            "code_key_id": self.accept_payload["p_code_key_id"],
            "code_nonce": self.accept_payload["p_code_nonce"],
            "code_ciphertext": self.accept_payload["p_code_ciphertext"],
            "code_record_binding_sha256": self.accept_payload[
                "p_code_record_binding_sha256"
            ],
            "claimed_at": claimed_at,
            "retired_at": None,
        }
        if lookup:
            value.update(
                {
                    "callback_binding_sha256": CALLBACK_HASH,
                    "authorization_code_sha256": self.accept_payload[
                        "p_authorization_code_sha256"
                    ],
                }
            )
        return value


def vault(rpc: FakeRPC, *, key: bytes = b"k" * 32):
    return ConnectedOAuthAuthorizationCodeVault(
        key=ConnectedOAuthMasterKey("root.oauth_code_envelope.test", key),
        store=SupabaseOAuthAuthorizationCodeCustodyStore(rpc),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("lose_response", [False, True])
async def test_atomic_accept_encrypts_before_sql_and_recovers_response_loss(
    lose_response,
) -> None:
    consume, exchange = commands()
    rpc = FakeRPC(lose_accept_response=lose_response)
    subject = vault(rpc)
    consumption, command = await subject.accept_callback_once(
        consume=consume,
        exchange=exchange,
        callback_binding_sha256=CALLBACK_HASH,
        authorization_code=OAuthAuthorizationCodeSecret(CODE),
        received_at=NOW,
    )

    assert consumption.flow_id == FLOW
    assert command.exchange_binding_sha256 == exchange.binding_sha256
    assert rpc.accept_payload is not None
    encoded = repr(rpc.accept_payload)
    assert CODE not in encoded
    assert "authorization_code" not in rpc.accept_payload
    assert rpc.accept_payload["p_authorization_code_sha256"] == hashlib.sha256(
        CODE.encode()
    ).hexdigest()
    assert rpc.accept_payload["p_code_ciphertext"] != CODE
    if lose_response:
        assert rpc.calls == [
            "connected_app_operator_accept_oauth_callback_v2",
            "connected_app_oauth_code_read_v1",
        ]


@pytest.mark.asyncio
async def test_recovery_opens_only_exact_exchange_bound_envelope_then_retires() -> None:
    consume, exchange = commands()
    rpc = FakeRPC()
    subject = vault(rpc)
    await subject.accept_callback_once(
        consume=consume,
        exchange=exchange,
        callback_binding_sha256=CALLBACK_HASH,
        authorization_code=OAuthAuthorizationCodeSecret(CODE),
        received_at=NOW,
    )

    code, command = await subject.recover_code_for_exchange(
        exchange,
        state_sha256=STATE_HASH,
        now=NOW + timedelta(seconds=1),
    )
    assert code.value == CODE
    assert command.callback_binding_sha256 == CALLBACK_HASH
    assert CODE not in repr(command)

    await subject.retire_for_exchange(
        exchange,
        state_sha256=STATE_HASH,
        reason="terminal",
    )
    assert rpc.calls[-1] == "connected_app_oauth_code_retire_v1"


@pytest.mark.asyncio
async def test_wrong_key_cannot_open_and_secrets_are_not_serializable() -> None:
    consume, exchange = commands()
    rpc = FakeRPC()
    await vault(rpc).accept_callback_once(
        consume=consume,
        exchange=exchange,
        callback_binding_sha256=CALLBACK_HASH,
        authorization_code=OAuthAuthorizationCodeSecret(CODE),
        received_at=NOW,
    )
    with pytest.raises(ConnectedOAuthCodeCustodyError) as caught:
        await vault(rpc, key=b"z" * 32).recover_code_for_exchange(
            exchange,
            state_sha256=STATE_HASH,
            now=NOW + timedelta(seconds=1),
        )
    assert caught.value.code == "OAUTH_CODE_CUSTODY_CORRUPT"
