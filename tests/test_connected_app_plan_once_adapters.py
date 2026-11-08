from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from backend.connected_app_plan_once import (
    ConnectedPlanBindingKey,
    ConnectedPlanOnceCommand,
    ConnectedPlanOperationState,
    SupabaseConnectedPlanControlPlane,
    SupabaseConnectedPlanEnvelopeStore,
)
from backend.connected_app_plan_vault import (
    ConnectedPlanCommitmentKey,
    ConnectedPlanEnvelopeVault,
    ConnectedPlanMasterKey,
)


NOW = datetime(2026, 11, 7, 20, 0, tzinfo=timezone.utc)
OWNER = "40000000-0000-4000-8000-000000000001"
SESSION = "40000000-0000-4000-8000-000000000002"
CHAT = "40000000-0000-4000-8000-000000000003"
MESSAGE = "40000000-0000-4000-8000-000000000004"
TURN = "40000000-0000-4000-8000-000000000005"
CLAIM = "40000000-0000-4000-8000-000000000006"


def command():
    return ConnectedPlanOnceCommand.build(
        binding_key=ConnectedPlanBindingKey("bind-1", b"b" * 32),
        owner_id=OWNER,
        session_id=SESSION,
        chat_id=CHAT,
        message_id=MESSAGE,
        turn_id=TURN,
        claim_token=CLAIM,
        origin_session_binding_sha256="a" * 64,
        request_binding_sha256="c" * 64,
        requested_at=NOW,
        expires_at=NOW + timedelta(minutes=15),
    )


def record(command_value, *, state="reserved"):
    invoked = state != "reserved"
    return {
        "state": state,
        "planning_id": command_value.planning_id,
        "owner_id": command_value.owner_id,
        "turn_id": command_value.turn_id,
        "planning_binding_key_id": command_value.planning_binding_key_id,
        "planning_binding_sha256": command_value.planning_binding_sha256,
        "payload_id": command_value.payload_id,
        "invocation_id": command_value.invocation_id if invoked else None,
        "invocation_expires_at": ((NOW + timedelta(seconds=45)).isoformat() if invoked else None),
        "disposition": None,
        "connection_id": None,
        "provider": None,
        "resource": None,
        "action": None,
        "payload_commitment_key_id": None,
        "payload_sha256": None,
        "payload_reference_binding_sha256": None,
        "error_code": None,
        "requested_at": command_value.requested_at.isoformat(),
        "expires_at": command_value.expires_at.isoformat(),
        "updated_at": NOW.isoformat(),
    }


class RPC:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def rpc(self, name, payload, *, retry_transient=False):
        self.calls.append((name, payload, retry_transient))
        value = self.responses.pop(0)
        if isinstance(value, BaseException):
            raise value
        return value


@pytest.mark.asyncio
async def test_control_plane_never_transient_retries_mutations_and_keeps_session_ephemeral():
    cmd = command()
    rpc = RPC([record(cmd), {"record": record(cmd, state="invoked"), "invoke_permitted": True}])
    store = SupabaseConnectedPlanControlPlane(rpc)
    begun = await store.begin(cmd)
    invoked = await store.mark_invoked(cmd)
    assert begun.state is ConnectedPlanOperationState.RESERVED
    assert invoked.invoke_permitted is True
    assert [call[2] for call in rpc.calls] == [False, False]
    assert rpc.calls[0][1]["p_session_id"] == SESSION
    assert SESSION not in repr(cmd)


@pytest.mark.asyncio
async def test_control_plane_rejects_extra_or_missing_response_keys():
    cmd = command()
    invalid = record(cmd)
    invalid["unexpected"] = "field"
    with pytest.raises(Exception):
        await SupabaseConnectedPlanControlPlane(RPC([invalid])).begin(cmd)


@pytest.mark.asyncio
async def test_envelope_put_response_loss_uses_readback_without_repeating_put():
    cmd = command()
    rpc = RPC([])
    durable_store = SupabaseConnectedPlanEnvelopeStore(rpc)
    encrypted_vault = ConnectedPlanEnvelopeVault(
        store=durable_store,
        master_keys={"kek-1": ConnectedPlanMasterKey("kek-1", b"k" * 32)},
        active_master_key_id="kek-1",
        commitment_keys={"hmac-1": ConnectedPlanCommitmentKey("hmac-1", b"h" * 32)},
        active_commitment_key_id="hmac-1",
    )

    # Build one valid encrypted row through the same vault with a memory capture.
    class Capture:
        def __init__(self):
            self.value = None

        async def put_once(self, value):
            self.value = value
            return value

        async def read_exact(self, **_kwargs):
            return self.value

        async def delete_once(self, **_kwargs):
            return True

    capture = Capture()
    source = ConnectedPlanEnvelopeVault(
        store=capture,
        master_keys={"kek-1": ConnectedPlanMasterKey("kek-1", b"k" * 32)},
        active_master_key_id="kek-1",
        commitment_keys={"hmac-1": ConnectedPlanCommitmentKey("hmac-1", b"h" * 32)},
        active_commitment_key_id="hmac-1",
    )
    await source.seal_json(
        payload_id=cmd.payload_id,
        owner_id=cmd.owner_id,
        turn_id=cmd.turn_id,
        planning_id=cmd.planning_id,
        planning_binding_sha256=cmd.planning_binding_sha256,
        value={"version": "connected-plan-output-v1", "raw": "opaque"},
        created_at=cmd.requested_at,
        expires_at=cmd.expires_at,
    )
    row = capture.value
    ref = row.reference
    encoded = {
        "payload_id": ref.payload_id,
        "owner_id": ref.owner_id,
        "turn_id": ref.turn_id,
        "planning_id": ref.planning_id,
        "planning_binding_sha256": ref.planning_binding_sha256,
        "commitment_key_id": ref.commitment_key_id,
        "payload_sha256": ref.payload_sha256,
        "created_at": ref.created_at.isoformat(),
        "expires_at": ref.expires_at.isoformat(),
        "key_id": row.key_id,
        "wrapped_key_nonce": row.wrapped_key_nonce,
        "wrapped_key_ciphertext": row.wrapped_key_ciphertext,
        "payload_nonce": row.payload_nonce,
        "payload_ciphertext": row.payload_ciphertext,
        "record_binding_sha256": row.record_binding_sha256,
    }
    rpc.responses.extend([RuntimeError("lost response"), encoded])
    stored = await durable_store.put_once(row)
    assert stored.reference == row.reference
    assert [call[0] for call in rpc.calls] == [
        "connected_plan_envelope_put_v1",
        "connected_plan_envelope_read_v1",
    ]
    assert all(call[2] is False for call in rpc.calls)
    # Keep the constructed vault live so type validation covers composition.
    assert "redacted" in repr(encrypted_vault)
