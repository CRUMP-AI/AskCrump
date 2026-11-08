from __future__ import annotations

import pytest

from backend.connected_app_chat_operator import ConnectedOperatorChatRequest
from backend.connected_app_delegated_responder import (
    ConnectedOperatorDelegatedResponderError,
    ConnectedOperatorDelegatedTextResponder,
)


OWNER = "00000000-0000-4000-8000-000000000001"


class Gateway:
    def __init__(self, result: object) -> None:
        self.result = result
        self.calls: list[dict[str, object]] = []

    async def gateway_text(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self.result, BaseException):
            raise self.result
        return self.result


def request(*, attachments: tuple[str, ...] = ()) -> ConnectedOperatorChatRequest:
    return ConnectedOperatorChatRequest(
        owner_id=OWNER,
        session_id="00000000-0000-4000-8000-000000000002",
        chat_id="00000000-0000-4000-8000-000000000003",
        message_id="00000000-0000-4000-8000-000000000004",
        message="What does the word email mean?",
        attachment_ids=attachments,
        time_zone="America/New_York",
    )


@pytest.mark.asyncio
async def test_delegated_response_is_owner_attributed_and_tool_free() -> None:
    gateway = Gateway("Email is a way to exchange digital messages.")
    responder = ConnectedOperatorDelegatedTextResponder(gateway)

    result = await responder.respond(request=request())

    assert result == "Email is a way to exchange digital messages."
    assert gateway.calls[0]["user_id"] == OWNER
    assert gateway.calls[0]["purpose"] == "connected_app_delegated_response"
    assert gateway.calls[0]["prompt"] == request().message
    assert "external action" in str(gateway.calls[0]["system"])
    assert OWNER not in repr(responder)


@pytest.mark.asyncio
@pytest.mark.parametrize("result", (RuntimeError("secret"), "", object()))
async def test_delegated_dependency_failure_is_content_free(result: object) -> None:
    responder = ConnectedOperatorDelegatedTextResponder(Gateway(result))
    with pytest.raises(ConnectedOperatorDelegatedResponderError) as error:
        await responder.respond(request=request())
    assert str(error.value) == "CONNECTED_OPERATOR_DELEGATED_RESPONSE_FAILED"
    assert "secret" not in str(error.value)


@pytest.mark.asyncio
async def test_delegated_responder_never_accepts_attachments() -> None:
    gateway = Gateway("must not run")
    responder = ConnectedOperatorDelegatedTextResponder(gateway)
    with pytest.raises(ConnectedOperatorDelegatedResponderError):
        await responder.respond(
            request=request(
                attachments=("00000000-0000-4000-8000-000000000005",)
            )
        )
    assert gateway.calls == []
