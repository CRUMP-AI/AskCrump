from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
import pickle

import pytest

from backend.connected_app_chat_turn import (
    ConnectedChatBindingKey,
    ConnectedChatRequestMaterial,
    ConnectedChatTurnError,
    ConnectedChatTurnState,
    SupabaseConnectedChatTurnStore,
)


OWNER = "00000000-0000-4000-8000-000000000001"
SESSION = "00000000-0000-4000-8000-000000000002"
CHAT = "00000000-0000-4000-8000-000000000003"
MESSAGE = "00000000-0000-4000-8000-000000000004"
ATTACHMENT = "00000000-0000-4000-8000-000000000005"
TURN = "00000000-0000-4000-8000-000000000006"
CLAIM = "00000000-0000-4000-8000-000000000007"
NOW = datetime(2026, 11, 7, 20, 0, tzinfo=UTC)


def key() -> ConnectedChatBindingKey:
    return ConnectedChatBindingKey("chat-binding-2026-11", b"k" * 32)


def material() -> ConnectedChatRequestMaterial:
    return ConnectedChatRequestMaterial(
        owner_id=OWNER,
        session_id=SESSION,
        chat_id=CHAT,
        message_id=MESSAGE,
        message="Check my inbox for the latest client response.",
        attachment_ids=(ATTACHMENT,),
        time_zone="America/New_York",
    )


def test_request_binding_is_stable_keyed_and_binds_every_required_input() -> None:
    value = material()
    expected = value.request_binding_sha256(key())
    assert expected == value.request_binding_sha256(key())
    assert expected != value.session_binding_sha256(key())
    variants = (
        replace(value, chat_id="00000000-0000-4000-8000-000000000008"),
        replace(value, message_id="00000000-0000-4000-8000-000000000009"),
        replace(value, message=value.message + " Now."),
        replace(value, attachment_ids=()),
        replace(value, time_zone="UTC"),
    )
    assert all(item.request_binding_sha256(key()) != expected for item in variants)


def test_origin_session_binding_changes_without_entering_request_commitment() -> None:
    value = material()
    sibling = replace(value, session_id="00000000-0000-4000-8000-00000000000a")
    assert value.request_binding_sha256(key()) == sibling.request_binding_sha256(key())
    assert value.session_binding_sha256(key()) != sibling.session_binding_sha256(key())


def test_secret_and_message_are_redacted_and_not_serializable() -> None:
    value = material()
    assert value.message not in repr(value)
    assert "6b6b6b" not in repr(key()).casefold()
    with pytest.raises(TypeError, match="cannot be serialized"):
        pickle.dumps(key())


@pytest.mark.parametrize(
    "changes",
    [
        {"attachment_ids": (ATTACHMENT, ATTACHMENT)},
        {"attachment_ids": tuple(str(index) for index in range(11))},
        {"time_zone": "Not/AZone"},
        {"message": "\ud800"},
    ],
)
def test_invalid_request_material_fails_closed(changes: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        replace(material(), **changes)


class RPC:
    def __init__(self, result: object) -> None:
        self.result = result
        self.calls: list[tuple[str, dict[str, object]]] = []

    async def rpc(self, name: str, payload: dict[str, object]) -> object:
        self.calls.append((name, payload))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def row(**changes: object) -> dict[str, object]:
    value: dict[str, object] = {
        "job_state": "claimed",
        "turn_id": TURN,
        "stage": "claimed",
        "claim_token": CLAIM,
        "response_data": None,
        "updated_at": NOW.isoformat(),
    }
    value.update(changes)
    return value


@pytest.mark.asyncio
async def test_store_claims_only_with_content_free_bindings() -> None:
    rpc = RPC([row()])
    command = material().command(key())
    result = await SupabaseConnectedChatTurnStore(rpc).claim(command)
    assert result.state is ConnectedChatTurnState.CLAIMED
    assert result.claim_token == CLAIM
    assert rpc.calls == [
        (
            "connected_chat_claim_turn_v1",
            {
                "p_owner_id": OWNER,
                "p_chat_id": CHAT,
                "p_message_id": MESSAGE,
                "p_origin_session_binding_sha256": command.origin_session_binding_sha256,
                "p_request_binding_sha256": command.request_binding_sha256,
            },
        )
    ]
    serialized = repr(rpc.calls)
    assert material().message not in serialized
    assert SESSION not in serialized


@pytest.mark.asyncio
async def test_completed_replay_requires_one_exact_response() -> None:
    response = {"message": {"id": "assistant-stable"}}
    rpc = RPC(
        row(
            job_state="completed",
            stage="terminal",
            claim_token=None,
            response_data=response,
        )
    )
    result = await SupabaseConnectedChatTurnStore(rpc).claim(material().command(key()))
    assert result.state is ConnectedChatTurnState.COMPLETED
    assert result.response_data == response


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "result",
    [
        [],
        [row(), row()],
        {**row(), "extra": True},
        row(job_state="busy", claim_token=CLAIM),
        row(job_state="completed", claim_token=None, response_data=None),
        RuntimeError("provider content must not escape"),
    ],
)
async def test_malformed_or_failed_rpc_is_quarantined(result: object) -> None:
    with pytest.raises(ConnectedChatTurnError) as captured:
        await SupabaseConnectedChatTurnStore(RPC(result)).claim(material().command(key()))
    assert "provider content" not in str(captured.value).casefold()
