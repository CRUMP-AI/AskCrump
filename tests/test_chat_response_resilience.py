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
    def __init__(self, row):
        self.row = row
        self.selects = []

    async def select_one(self, table, *, columns="*", filters=None):
        self.selects.append((table, columns, filters))
        return self.row


def install_job(monkeypatch, row):
    fake_db = ChatJobDB(row)

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
    assert columns == "message_id,status,response_data,error_code,updated_at"
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


def test_changed_primary_runtime_and_transport_are_release_versioned_and_network_first():
    shell = (PUBLIC / "app.html").read_text(encoding="utf-8")
    runtime = (PUBLIC / "runtime-body-v1.js").read_text(encoding="utf-8")
    worker = (PUBLIC / "sw.js").read_text(encoding="utf-8")

    assert '<script defer src="/chat-resilience.js?v=5.9.61"></script>' in shell
    assert "['/crump-5.0.js?v=5.9.61', 'crump50']" in runtime
    assert "'/chat-resilience.js?v=5.9.61'" in worker
    assert "'/crump-5.0.js?v=5.9.61'" in worker
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
