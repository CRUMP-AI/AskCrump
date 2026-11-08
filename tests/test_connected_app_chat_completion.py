from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
import pickle

import pytest

from backend.connected_app_chat_completion import (
    ConnectedChatCompletionCommand,
    ConnectedChatCompletionError,
    ConnectedChatCompletionKey,
    ConnectedChatCompletionKind,
    SupabaseConnectedChatCompletionStore,
)


OWNER = "00000000-0000-4000-8000-000000000001"
SESSION = "00000000-0000-4000-8000-000000000002"
TURN = "00000000-0000-4000-8000-000000000003"
CHAT = "00000000-0000-4000-8000-000000000004"
MESSAGE = "00000000-0000-4000-8000-000000000005"
ASSISTANT = "00000000-0000-4000-8000-000000000006"
CLAIM = "00000000-0000-4000-8000-000000000007"
ORIGIN = "a" * 64
REQUEST = "b" * 64
NOW = datetime(2026, 11, 8, 3, 0, tzinfo=UTC)


def key() -> ConnectedChatCompletionKey:
    return ConnectedChatCompletionKey("chat-completion-2026-11", b"k" * 32)


def user_message() -> dict[str, object]:
    return {
        "id": MESSAGE,
        "role": "user",
        "content": "Check my inbox for the newest client reply.",
    }


def assistant_message() -> dict[str, object]:
    return {
        "id": ASSISTANT,
        "role": "assistant",
        "inReplyTo": MESSAGE,
        "content": "I found one recent reply.",
        "connectedApp": {"resultHandle": "opaque-result"},
    }


def response_data() -> dict[str, object]:
    return {
        "response": "I found one recent reply.",
        "assistantMessage": assistant_message(),
        "connectedApp": {"state": "done", "resultHandle": "opaque-result"},
    }


def command() -> ConnectedChatCompletionCommand:
    return ConnectedChatCompletionCommand.build(
        key=key(),
        owner_id=OWNER,
        session_id=SESSION,
        turn_id=TURN,
        chat_id=CHAT,
        message_id=MESSAGE,
        assistant_message_id=ASSISTANT,
        claim_token=CLAIM,
        origin_session_binding_sha256=ORIGIN,
        request_binding_sha256=REQUEST,
        kind=ConnectedChatCompletionKind.ACTION_TERMINAL,
        title="Client inbox check",
        user_message=user_message(),
        assistant_message=assistant_message(),
        response_data=response_data(),
    )


def row(value: ConnectedChatCompletionCommand | None = None) -> dict[str, object]:
    value = value or command()
    return {
        "completion_id": value.completion_id,
        "kind": value.kind.value,
        "response_binding_sha256": value.response_binding_sha256,
        "resulting_revision": 2,
        "resulting_updated_at": NOW.isoformat(),
        "completed_at": NOW.isoformat(),
        "response_data": value.response_data,
    }


def test_completion_binding_is_keyed_stable_and_binds_customer_content() -> None:
    value = command()
    assert value == command()
    changed = ConnectedChatCompletionCommand.build(
        key=key(),
        owner_id=OWNER,
        session_id=SESSION,
        turn_id=TURN,
        chat_id=CHAT,
        message_id=MESSAGE,
        assistant_message_id=ASSISTANT,
        claim_token=CLAIM,
        origin_session_binding_sha256=ORIGIN,
        request_binding_sha256=REQUEST,
        kind=ConnectedChatCompletionKind.ACTION_TERMINAL,
        title="Client inbox check",
        user_message=user_message(),
        assistant_message={**assistant_message(), "content": "Different."},
        response_data=response_data(),
    )
    assert changed.completion_id == value.completion_id
    assert changed.response_binding_sha256 != value.response_binding_sha256


def test_repr_and_serialization_do_not_disclose_content_or_secret() -> None:
    value = command()
    assert "Check my inbox" not in repr(value)
    assert "I found one" not in repr(value)
    assert "6b6b6b" not in repr(key()).casefold()
    with pytest.raises(TypeError, match="cannot be serialized"):
        pickle.dumps(key())


@pytest.mark.parametrize(
    "change",
    [
        {"completion_id": "00000000-0000-4000-8000-000000000099"},
        {"assistant_message": {**assistant_message(), "inReplyTo": CHAT}},
        {"response_data": {"response": "missing exact assistant"}},
        {"title": ""},
    ],
)
def test_command_fails_closed_on_identity_or_shape_drift(
    change: dict[str, object],
) -> None:
    with pytest.raises(ValueError):
        replace(command(), **change)


class RPC:
    def __init__(self, *results: object) -> None:
        self.results = list(results)
        self.calls: list[tuple[str, dict[str, object]]] = []

    async def rpc(self, name: str, payload: dict[str, object]) -> object:
        self.calls.append((name, payload))
        if not self.results:
            raise AssertionError("unexpected RPC")
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


@pytest.mark.asyncio
async def test_completion_rpc_carries_live_session_but_no_secret_key() -> None:
    value = command()
    rpc = RPC([row(value)])
    result = await SupabaseConnectedChatCompletionStore(rpc).complete(value)
    assert result.response_data == value.response_data
    assert rpc.calls[0][0] == "connected_operator_complete_chat_v1"
    payload = rpc.calls[0][1]
    assert payload["p_session_id"] == SESSION
    assert payload["p_claim_token"] == CLAIM
    assert payload["p_response_binding_sha256"] == value.response_binding_sha256
    assert "secret" not in repr(payload).casefold()


@pytest.mark.asyncio
async def test_response_loss_recovers_exact_committed_completion_once() -> None:
    value = command()
    rpc = RPC(TimeoutError("lost response"), row(value))
    result = await SupabaseConnectedChatCompletionStore(rpc).complete(value)
    assert result.completion_id == value.completion_id
    assert [name for name, _ in rpc.calls] == [
        "connected_operator_complete_chat_v1",
        "connected_operator_read_chat_completion_v1",
    ]
    assert "p_title" not in rpc.calls[1][1]
    assert "p_user_message" not in rpc.calls[1][1]


@pytest.mark.asyncio
async def test_ambiguous_failure_without_exact_receipt_fails_closed() -> None:
    rpc = RPC(TimeoutError("provider content"), None)
    with pytest.raises(ConnectedChatCompletionError) as captured:
        await SupabaseConnectedChatCompletionStore(rpc).complete(command())
    assert captured.value.code == "CONNECTED_CHAT_COMPLETION_FAILED"
    assert "provider content" not in str(captured.value).casefold()


@pytest.mark.asyncio
async def test_malformed_or_mismatched_receipt_is_never_accepted() -> None:
    value = command()
    mismatched = {**row(value), "response_binding_sha256": "f" * 64}
    rpc = RPC(mismatched, None)
    with pytest.raises(ConnectedChatCompletionError):
        await SupabaseConnectedChatCompletionStore(rpc).complete(value)


@pytest.mark.asyncio
async def test_read_returns_none_only_for_absent_exact_completion() -> None:
    assert await SupabaseConnectedChatCompletionStore(RPC(None)).read(command()) is None
