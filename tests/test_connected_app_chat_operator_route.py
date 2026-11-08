from __future__ import annotations

import json
import inspect
from types import SimpleNamespace

import pytest

from backend.connected_app_chat_operator import (
    ConnectedOperatorChatError,
    ConnectedOperatorChatResponse,
)
from backend.routes import chat


OWNER = "00000000-0000-4000-8000-000000000001"
SESSION = "00000000-0000-4000-8000-000000000002"
CHAT = "00000000-0000-4000-8000-000000000003"
MESSAGE = "00000000-0000-4000-8000-000000000004"


class Operator:
    def __init__(self) -> None:
        self.calls = []

    async def handle(self, command):
        self.calls.append(command)
        return ConnectedOperatorChatResponse(
            200,
            {
                "success": True,
                "response": "I found one event.",
                "assistantMessage": {"id": MESSAGE, "inReplyTo": MESSAGE},
            },
        )


def auth(*, guest: bool = False):
    return SimpleNamespace(
        user={"id": OWNER, "is_guest": guest},
        session={"id": SESSION},
    )


def request():
    return SimpleNamespace(headers={})


@pytest.mark.asyncio
async def test_release_off_and_guest_requests_stay_on_legacy_path(monkeypatch) -> None:
    operator = Operator()
    monkeypatch.setattr(chat, "connected_operator_chat_service", operator)
    monkeypatch.setattr(chat, "settings", SimpleNamespace(connected_apps_enabled=False))
    result = await chat._connected_operator_response(
        request=request(),
        auth=auth(),
        request_payload={},
        original_message="Check my email.",
        chat_id=CHAT,
        message_id=MESSAGE,
    )
    assert result is None
    monkeypatch.setattr(chat, "settings", SimpleNamespace(connected_apps_enabled=True))
    result = await chat._connected_operator_response(
        request=request(),
        auth=auth(guest=True),
        request_payload={},
        original_message="Check my email.",
        chat_id=CHAT,
        message_id=MESSAGE,
    )
    assert result is None
    assert operator.calls == []


@pytest.mark.asyncio
async def test_non_candidate_stays_on_legacy_path_when_released(monkeypatch) -> None:
    operator = Operator()
    monkeypatch.setattr(chat, "connected_operator_chat_service", operator)
    monkeypatch.setattr(chat, "settings", SimpleNamespace(connected_apps_enabled=True))

    async def forbidden_activation(_source):
        raise AssertionError("ordinary chat must not activate the connected graph")

    monkeypatch.setattr(chat, "acquire_connected_request_activation", forbidden_activation)
    result = await chat._connected_operator_response(
        request=request(),
        auth=auth(),
        request_payload={},
        original_message="Help me improve this paragraph.",
        chat_id=CHAT,
        message_id=MESSAGE,
    )
    assert result is None
    assert operator.calls == []


@pytest.mark.asyncio
async def test_authenticated_candidate_holds_request_activation_lease(monkeypatch) -> None:
    operator = Operator()
    released = 0

    class Lease:
        async def release(self):
            nonlocal released
            released += 1

    async def acquire(source):
        assert source() == "request-oidc"
        return Lease()

    monkeypatch.setattr(chat, "connected_operator_chat_service", operator)
    monkeypatch.setattr(chat, "settings", SimpleNamespace(connected_apps_enabled=True))
    monkeypatch.setattr(chat, "acquire_connected_request_activation", acquire)
    response = await chat._connected_operator_response(
        request=SimpleNamespace(headers={"x-vercel-oidc-token": "request-oidc"}),
        auth=auth(),
        request_payload={},
        original_message="Check my inbox.",
        chat_id=CHAT,
        message_id=MESSAGE,
    )
    assert response is not None and response.status_code == 200
    assert len(operator.calls) == 1
    assert released == 1


@pytest.mark.asyncio
async def test_candidate_uses_connected_service_before_legacy_claim(monkeypatch) -> None:
    operator = Operator()
    monkeypatch.setattr(chat, "connected_operator_chat_service", operator)
    monkeypatch.setattr(chat, "settings", SimpleNamespace(connected_apps_enabled=True))
    response = await chat._connected_operator_response(
        request=request(),
        auth=auth(),
        request_payload={"currentDateTime": {"timezone": "America/New_York"}},
        original_message="Check my calendar for tomorrow.",
        chat_id=CHAT,
        message_id=MESSAGE,
    )
    assert response is not None
    assert response.status_code == 200
    assert json.loads(response.body)["response"] == "I found one event."
    assert len(operator.calls) == 1
    assert operator.calls[0].time_zone == "America/New_York"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "message",
    (
        "Schedule lunch with Jane Tuesday at noon.",
        "What’s on my agenda tomorrow?",
        "Find the note from Jane about the budget.",
        "Draft a reply to the vendor.",
        "Send a note to the team.",
        "Cancel the appointment tomorrow.",
        "Move the meeting to 3 PM.",
        "Change the event location to Room 2.",
        "Delete the calendar event next Friday.",
        "Do I have any emails from Sarah?",
        "Any new emails?",
        "When am I free tomorrow?",
        "Set a meeting with Sarah tomorrow.",
        "Make an appointment with Sarah tomorrow.",
        "Add an event tomorrow at 2 PM.",
    ),
)
async def test_natural_connected_idioms_never_fall_through_to_legacy(
    monkeypatch, message
) -> None:
    operator = Operator()
    monkeypatch.setattr(chat, "connected_operator_chat_service", operator)
    monkeypatch.setattr(chat, "settings", SimpleNamespace(connected_apps_enabled=True))
    response = await chat._connected_operator_response(
        request=request(),
        auth=auth(),
        request_payload={},
        original_message=message,
        chat_id=CHAT,
        message_id=MESSAGE,
    )
    assert response is not None and response.status_code == 200
    assert len(operator.calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "message",
    (
        "Explain how cron scheduling works.",
        "Draft a project proposal.",
        "Send me a summary of this paragraph.",
        "Reply with JSON only.",
        "Cancel the database migration.",
        "Move the paragraph to the end.",
        "Change the event loop implementation.",
        "Delete this email.",
        "Do I have any email addresses in this spreadsheet?",
        "Any new email protocol changes?",
        "Set the meeting variable in this code tomorrow.",
        "Add an event loop example tomorrow.",
        "Make an appointment class in Python tomorrow.",
    ),
)
async def test_unrelated_action_idioms_remain_on_legacy_path(monkeypatch, message) -> None:
    operator = Operator()
    monkeypatch.setattr(chat, "connected_operator_chat_service", operator)
    monkeypatch.setattr(chat, "settings", SimpleNamespace(connected_apps_enabled=True))
    response = await chat._connected_operator_response(
        request=request(),
        auth=auth(),
        request_payload={},
        original_message=message,
        chat_id=CHAT,
        message_id=MESSAGE,
    )
    assert response is None
    assert operator.calls == []


@pytest.mark.asyncio
async def test_released_candidate_fails_closed_when_uncomposed(monkeypatch) -> None:
    monkeypatch.setattr(chat, "connected_operator_chat_service", None)
    monkeypatch.setattr(chat, "settings", SimpleNamespace(connected_apps_enabled=True))
    response = await chat._connected_operator_response(
        request=request(),
        auth=auth(),
        request_payload={},
        original_message="Check my inbox.",
        chat_id=CHAT,
        message_id=MESSAGE,
    )
    assert response is not None
    body = json.loads(response.body)
    assert response.status_code == 503
    assert body["code"] == "CONNECTED_OPERATOR_CHAT_NOT_READY"
    assert body["shouldRetry"] is False


@pytest.mark.asyncio
async def test_attachment_unsupported_error_has_truthful_safe_copy(monkeypatch) -> None:
    class RejectAttachments:
        async def handle(self, command):
            raise ConnectedOperatorChatError(
                "CONNECTED_OPERATOR_ATTACHMENT_UNSUPPORTED",
                status_code=400,
            )

    monkeypatch.setattr(chat, "connected_operator_chat_service", RejectAttachments())
    monkeypatch.setattr(chat, "settings", SimpleNamespace(connected_apps_enabled=True))
    response = await chat._connected_operator_response(
        request=request(),
        auth=auth(),
        request_payload={"files": [{"id": "00000000-0000-4000-8000-000000000005"}]},
        original_message="Email the attached file.",
        chat_id=CHAT,
        message_id=MESSAGE,
    )
    assert response is not None
    body = json.loads(response.body)
    assert response.status_code == 400
    assert body["code"] == "CONNECTED_OPERATOR_ATTACHMENT_UNSUPPORTED"
    assert body["message"] == (
        "Connected mail and calendar requests cannot use attachments yet. "
        "Send this request again without an attachment."
    )


def test_connected_candidate_dispatch_precedes_legacy_job_claim() -> None:
    source = inspect.getsource(chat._chat_impl)
    assert source.index("_connected_operator_response(") < source.index("'claim_chat_job_v2'")
