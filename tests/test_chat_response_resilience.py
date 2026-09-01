from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

import app as app_module
from backend.db import eq
from backend.routes import chat as chat_routes


ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"
CLIENT = TestClient(app_module.app)
MESSAGE_ID = "b2f94abc-56b5-4df2-9dc8-1cb0937ed6c6"


class ChatJobDB:
    def __init__(self, row, conversation=None):
        self.row = row
        self.conversation = conversation
        self.selects = []

    async def select_one(self, table, *, columns="*", filters=None):
        self.selects.append((table, columns, filters))
        return self.conversation if table == "user_chats" else self.row


def install_job(monkeypatch, row, conversation=None):
    fake_db = ChatJobDB(row, conversation)

    async def authenticate(*_args, **_kwargs):
        return SimpleNamespace(user={"id": "owner-1"}, session={"id": "session-1"}, token="token")

    monkeypatch.setattr(chat_routes, "db", fake_db)
    monkeypatch.setattr(chat_routes, "authenticate_request", authenticate)
    return fake_db


def test_reply_status_requires_authentication():
    response = CLIENT.get(f"/api/chat/status/{MESSAGE_ID}")

    assert response.status_code == 401


def test_completed_reply_status_is_owner_scoped_and_returns_cached_response(monkeypatch):
    fake_db = install_job(
        monkeypatch,
        {
            "status": "completed",
            "response_data": {
                "response": "Recovered answer",
                "assistantMessage": {"id": "reply-1", "role": "assistant", "content": "Recovered answer"},
            },
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
    )

    response = CLIENT.get(f"/api/chat/status/{MESSAGE_ID}")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["status"] == "completed"
    assert response.json()["cached"] is True
    assert response.json()["assistantMessage"]["id"] == "reply-1"
    table, columns, filters = fake_db.selects[0]
    assert table == "chat_jobs"
    assert columns == "chat_id,message_id,status,response_data,error_code,updated_at"
    assert filters == {"user_id": eq("owner-1"), "message_id": eq(MESSAGE_ID)}


def test_active_reply_status_is_retryable_without_restarting_generation(monkeypatch):
    install_job(
        monkeypatch,
        {
            "status": "processing",
            "response_data": None,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
    )

    response = CLIENT.get(f"/api/chat/status/{MESSAGE_ID}")

    assert response.status_code == 202
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {"success": True, "status": "processing", "retryAfter": 3}


def test_status_recovers_authoritative_document_after_response_and_job_cache_are_lost(monkeypatch):
    chat_id = "6bd623ee-93fe-4b50-957a-01f79d289d88"
    assistant = {
        "id": "reply-durable-1",
        "role": "assistant",
        "content": "Your durable document is ready.",
        "inReplyTo": MESSAGE_ID,
        "artifact": {
            "id": "8f946445-f51d-4f77-8214-8de75ab42a4e",
            "name": "durable-document.docx",
            "format": "docx",
            "kind": "generated_document",
            "status": "ready",
        },
    }
    fake_db = install_job(
        monkeypatch,
        {
            "chat_id": chat_id,
            "status": "processing",
            "response_data": None,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
        {
            "chat_id": chat_id,
            "messages": [
                {"id": MESSAGE_ID, "role": "user", "content": "Make the document."},
                assistant,
            ],
            "revision": 11,
            "updated_at": "2026-08-31T13:15:00Z",
        },
    )

    response = CLIENT.get(f"/api/chat/status/{MESSAGE_ID}")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "response": "Your durable document is ready.",
        "assistantMessage": assistant,
        "artifact": assistant["artifact"],
        "conversationRevision": 11,
        "conversationUpdatedAt": "2026-08-31T13:15:00Z",
        "success": True,
        "status": "completed",
        "cached": True,
        "reconciled": True,
    }
    table, columns, filters = fake_db.selects[1]
    assert table == "user_chats"
    assert columns == "chat_id,messages,revision,updated_at"
    assert filters == {
        "user_id": eq("owner-1"),
        "chat_id": eq(chat_id),
        "deleted_at": "is.null",
    }


def test_stale_or_failed_reply_status_allows_the_existing_idempotent_job_to_retry(monkeypatch):
    install_job(
        monkeypatch,
        {
            "status": "processing",
            "response_data": None,
            "error_code": None,
            "updated_at": (datetime.now(timezone.utc) - timedelta(minutes=3)).isoformat(),
        },
    )

    response = CLIENT.get(f"/api/chat/status/{MESSAGE_ID}")

    assert response.status_code == 409
    assert response.json()["status"] == "retryable"
    assert response.json()["shouldRetry"] is True


def test_primary_and_fallback_chat_runtimes_use_bounded_server_job_recovery():
    transport = (PUBLIC / "chat-resilience.js").read_text(encoding="utf-8")
    primary = (PUBLIC / "crump-5.0.js").read_text(encoding="utf-8")
    fallback = (PUBLIC / "app.js").read_text(encoding="utf-8")

    assert "REPLY_TIMEOUT_MS = 105_000" in transport
    assert "STATUS_MAX_POLLS = 10" in transport
    assert "new AbortController()" in transport
    assert "`/api/chat/status/${encodeURIComponent(messageId)}`" in transport
    assert "const recovered = await recover(requestBody.messageId)" in transport
    assert "Crump is still working on this message. Tap it to check again." in transport
    assert "window.CrumpChatTransport.acknowledge" in primary
    assert "window.CrumpChatTransport.send" in primary
    assert "window.CrumpChatTransport?.recover?.(id)" in primary
    assert "const transport = window.CrumpChatTransport" in fallback
    assert "const recovered = await window.CrumpChatTransport?.recover?.(id)" in fallback


def test_completed_reply_sync_is_best_effort_and_cannot_relabel_durable_success():
    primary = (PUBLIC / "crump-5.0.js").read_text(encoding="utf-8")
    fallback = (PUBLIC / "app.js").read_text(encoding="utf-8")
    primary_completion = primary.split("async function completeReply", 1)[1].split(
        "async function studioSendMessage", 1
    )[0]
    fallback_completion = fallback.split("function completeUserMessage", 1)[1].split(
        "async function recordFirstSuccessfulResponse", 1
    )[0]

    assert "function syncCompletedReplyInBackground()" in primary
    assert "void Promise.resolve(window.syncChatsFromServer?.()).catch(() =>" in primary
    assert "syncCompletedReplyInBackground();" in primary_completion
    assert "await window.syncChatsFromServer?.()" not in primary_completion
    assert "function syncCompletedReplyInBackground()" in fallback
    assert "void Promise.resolve(window.syncChatsToServer?.()).catch(() =>" in fallback
    assert "syncCompletedReplyInBackground();" in fallback_completion
    assert "window.syncChatsToServer?.();" not in fallback_completion
    for source in (primary, fallback):
        assert "Completed reply sync deferred; background sync will retry." in source


def test_completed_reply_creation_handoff_cannot_relabel_durable_success():
    primary = (PUBLIC / "crump-5.0.js").read_text(encoding="utf-8")
    fallback = (PUBLIC / "app.js").read_text(encoding="utf-8")
    primary_completion = primary.split("async function completeReply", 1)[1].split(
        "async function studioSendMessage", 1
    )[0]
    fallback_completion = fallback.split("function completeUserMessage", 1)[1].split(
        "async function recordFirstSuccessfulResponse", 1
    )[0]

    for source, completion in (
        (primary, primary_completion),
        (fallback, fallback_completion),
    ):
        assert "function runCompletedCreationHandoffInBackground(data)" in source
        assert "void Promise.resolve(pending).catch(() =>" in source
        assert "runCompletedCreationHandoffInBackground(data);" in completion
        assert "handleCreationHandoff?.(" not in completion
        assert "Completed creation handoff deferred; the saved reply remains available." in source


def test_completed_reply_presentation_failure_cannot_relabel_durable_success():
    primary = (PUBLIC / "crump-5.0.js").read_text(encoding="utf-8")
    fallback = (PUBLIC / "app.js").read_text(encoding="utf-8")
    primary_send = primary.split("async function studioSendMessage", 1)[1].split(
        "async function retryMessage", 1
    )[0]
    primary_retry = primary.split("async function retryMessage", 1)[1].split(
        "function replaceLegacyControls", 1
    )[0]
    fallback_send = fallback.split("async function processUserMessage", 1)[1].split(
        "async function sendMessage", 1
    )[0]
    fallback_retry = fallback.split("async function retryMessage", 1)[1].split(
        "window.retryMessage", 1
    )[0]

    assert "async function applyCompletedReplySafely(chat, userMessage, data)" in primary
    assert primary_send.count("await applyCompletedReplySafely(") == 1
    assert primary_retry.count("await applyCompletedReplySafely(") == 2
    assert "await completeReply(" not in primary_send
    assert "await completeReply(" not in primary_retry

    assert "function applyCompletedReplySafely(chat, userMessage, data)" in fallback
    assert "applyCompletedReplySafely(chat, userMessage, data);" in fallback_send
    assert "applyCompletedReplySafely(chat, message, recovered);" in fallback_retry
    assert "completeUserMessage(chat, userMessage, data);" not in fallback_send
    assert "completeUserMessage(chat, message, recovered);" not in fallback_retry

    for source in (primary, fallback):
        assert "Your reply was saved, but this screen could not finish updating." in source
        assert "Refresh this conversation to load the saved reply." in source


def test_changed_primary_runtime_and_transport_are_release_versioned_and_network_first():
    shell = (PUBLIC / "app.html").read_text(encoding="utf-8")
    runtime = (PUBLIC / "runtime-body-v1.js").read_text(encoding="utf-8")
    worker = (PUBLIC / "sw.js").read_text(encoding="utf-8")

    assert '/chat-resilience.js?v=5.9.76-contextual-plan-recovery-1' not in shell
    assert "['/chat-resilience.js?v=5.9.76-image-safety-recovery-1', 'workspacechatresilience']" in runtime
    assert "['/crump-5.0.js?v=5.9.76-file-delivery-1', 'crump50']" in runtime
    assert "'/chat-resilience.js?v=5.9.76-image-safety-recovery-1'" in worker
    assert "'/crump-5.0.js?v=5.9.76-file-delivery-1'" in worker
    assert "url.pathname === '/chat-resilience.js'" in worker
    assert "url.pathname === '/crump-5.0.js'" in worker


def test_browser_fixture_exercises_primary_runtime_without_credentials_or_production_writes():
    fixture = (ROOT / "tests" / "fixtures" / "chat-response-stall.html").read_text(encoding="utf-8")

    assert '<script src="/public/chat-resilience.js?v=chat-response-fixture-2"></script>' in fixture
    assert '<script src="/public/crump-5.0.js?v=chat-response-fixture-2"></script>' in fixture
    assert "Reply request is stalled. Chat requests:" in fixture
    assert "Message acknowledgement is stalled." in fixture
    assert "url.pathname.startsWith('/api/chat/status/')" in fixture
    assert "Here is a focused launch plan for the neighborhood bakery." in fixture
    assert "password" not in fixture.lower()
    assert "askcrump.com" not in fixture
