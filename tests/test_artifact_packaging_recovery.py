import json
from pathlib import Path

import pytest

import backend.crump52_patches as crump52_patches
import backend.file_service as file_service_module
import backend.sync_service as sync_module
from backend.file_service import FileService
from backend.routes import chat as chat_routes


ROOT = Path(__file__).resolve().parents[1]
USER_ID = "00000000-0000-0000-0000-000000000001"
CHAT_ID = "00000000-0000-0000-0000-000000000002"
MESSAGE_ID = "00000000-0000-0000-0000-000000000003"
ASSISTANT_ID = "00000000-0000-0000-0000-000000000004"


async def authenticate(*_args, **_kwargs):
    return type("Auth", (), {"user": {"id": USER_ID, "subscription_tier": "free"}})()


class RecoveryDB:
    def __init__(self, *, persistence_fails=False):
        recovery = {
            "status": "failed",
            "format": "docx",
            "purpose": "resume",
            "shouldRetry": True,
            "message": "fixed",
        }
        self.assistant = {
            "id": ASSISTANT_ID,
            "role": "assistant",
            "content": "# Resume\n\n## Experience\n\nBuilt durable systems.",
            "inReplyTo": MESSAGE_ID,
            "artifactRecovery": recovery,
        }
        self.user = {
            "id": MESSAGE_ID,
            "role": "user",
            "content": "Create a polished resume from my saved experience.",
        }
        self.job = {
            "chat_id": CHAT_ID,
            "message_id": MESSAGE_ID,
            "status": "completed",
            "response_data": {
                "response": self.assistant["content"],
                "assistantMessage": dict(self.assistant),
                "artifactRecovery": dict(recovery),
            },
        }
        self.conversation = {"chat_id": CHAT_ID, "messages": [dict(self.user), dict(self.assistant)]}
        self.persistence_fails = persistence_fails
        self.rpc_calls = []
        self.update_calls = []

    async def select_one(self, table, **_kwargs):
        if table == "chat_jobs":
            return self.job
        if table == "user_chats":
            return self.conversation
        return None

    async def rpc(self, name, payload):
        self.rpc_calls.append((name, payload))
        if name == "persist_chat_reply" and self.persistence_fails:
            raise RuntimeError("private persistence detail")
        if name == "persist_chat_reply":
            self.assistant = dict(payload["p_assistant_message"])
            self.conversation["messages"] = [dict(self.user), dict(self.assistant)]
            return [{"resulting_revision": 7, "resulting_updated_at": "2026-08-30T20:00:00Z"}]
        return True

    async def update(self, table, payload, **_kwargs):
        self.update_calls.append((table, payload))
        if table == "chat_jobs":
            self.job.update(payload)
        return [payload]


class RecoveryArtifacts:
    def __init__(self, *, failure=None):
        self.calls = []
        self.failure = failure

    @staticmethod
    def normalize_format(value):
        candidate = str(value or "").strip().lower().lstrip(".")
        return candidate if candidate in {"docx", "pdf", "pptx", "xlsx", "md", "txt"} else None

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.failure:
            raise self.failure
        return {
            "id": kwargs["file_id"],
            "name": "resume.docx",
            "format": "docx",
            "kind": "generated_document",
            "status": "ready",
            "url": f"/api/files/{kwargs['file_id']}/content",
        }


class NoProject:
    @staticmethod
    async def find_for_chat(**_kwargs):
        return None


def response_payload(response):
    return json.loads(response.body.decode("utf-8")) if hasattr(response, "body") else response


@pytest.mark.asyncio
async def test_packaging_retry_reuses_saved_answer_and_is_idempotent(monkeypatch):
    database = RecoveryDB()
    artifacts = RecoveryArtifacts()
    events = []

    async def record_event(_database, **kwargs):
        events.append((kwargs["event_name"], kwargs.get("artifact_type")))
        return True

    monkeypatch.setattr(chat_routes, "authenticate_request", authenticate)
    monkeypatch.setattr(chat_routes, "db", database)
    monkeypatch.setattr(chat_routes, "artifacts", artifacts)
    monkeypatch.setattr(chat_routes, "projects", NoProject())
    monkeypatch.setattr(chat_routes, "record_product_event", record_event)

    first = await chat_routes.retry_chat_artifact(MESSAGE_ID, object())
    second = await chat_routes.retry_chat_artifact(MESSAGE_ID, object())

    assert first["success"] is True and second["success"] is True
    assert first["conversationSaved"] is True
    assert first["artifact"]["id"] == second["artifact"]["id"]
    assert len(artifacts.calls) == 1
    call = artifacts.calls[0]
    assert call["markdown"] == "# Resume\n\n## Experience\n\nBuilt durable systems."
    assert call["brief"] == database.user["content"]
    assert call["purpose"] == "resume"
    assert call["file_id"] == chat_routes._artifact_file_id(
        user_id=USER_ID, message_id=MESSAGE_ID, format_name="docx"
    )
    assert "artifactRecovery" not in database.assistant
    assert database.assistant["artifact"]["id"] == first["artifact"]["id"]
    assert ("ArtifactPackaged", "document") in events
    assert ("AhaReached", "document") in events


@pytest.mark.asyncio
async def test_packaging_retry_returns_fixed_error_without_leaking_exception(monkeypatch):
    database = RecoveryDB()
    artifacts = RecoveryArtifacts(failure=RuntimeError("SECRET storage diagnostic"))

    monkeypatch.setattr(chat_routes, "authenticate_request", authenticate)
    monkeypatch.setattr(chat_routes, "db", database)
    monkeypatch.setattr(chat_routes, "artifacts", artifacts)
    monkeypatch.setattr(chat_routes, "projects", NoProject())

    response = await chat_routes.retry_chat_artifact(MESSAGE_ID, object())
    payload = response_payload(response)

    assert response.status_code == 503
    assert payload == {
        "success": False,
        "error": "The saved answer is safe, but its file still could not be packaged.",
        "code": "ARTIFACT_RECOVERY_FAILED",
        "shouldRetry": True,
    }
    assert "SECRET" not in str(payload)


@pytest.mark.asyncio
async def test_packaging_retry_lookup_failure_is_retryable_and_content_free(monkeypatch):
    class UnavailableDB:
        async def select_one(self, *_args, **_kwargs):
            raise RuntimeError("SECRET database topology")

    monkeypatch.setattr(chat_routes, "authenticate_request", authenticate)
    monkeypatch.setattr(chat_routes, "db", UnavailableDB())

    response = await chat_routes.retry_chat_artifact(MESSAGE_ID, object())
    payload = response_payload(response)

    assert response.status_code == 503
    assert payload == {
        "success": False,
        "error": "The saved answer is safe, but file recovery is temporarily unavailable.",
        "code": "ARTIFACT_RECOVERY_LOOKUP_UNAVAILABLE",
        "shouldRetry": True,
    }
    assert "SECRET" not in str(payload)


@pytest.mark.asyncio
async def test_packaged_file_remains_available_when_conversation_link_retry_fails(monkeypatch):
    database = RecoveryDB(persistence_fails=True)
    artifacts = RecoveryArtifacts()

    async def record_event(*_args, **_kwargs):
        return True

    monkeypatch.setattr(chat_routes, "authenticate_request", authenticate)
    monkeypatch.setattr(chat_routes, "db", database)
    monkeypatch.setattr(chat_routes, "artifacts", artifacts)
    monkeypatch.setattr(chat_routes, "projects", NoProject())
    monkeypatch.setattr(chat_routes, "record_product_event", record_event)

    payload = await chat_routes.retry_chat_artifact(MESSAGE_ID, object())

    assert payload["success"] is True
    assert payload["conversationSaved"] is False
    assert payload["artifact"]["id"] == artifacts.calls[0]["file_id"]
    assert payload["artifactRecovery"] == {
        "status": "packaged",
        "format": "docx",
        "purpose": "resume",
        "shouldRetry": True,
        "message": "The file is safe in Files, but its conversation link needs a retry.",
    }
    assert "private persistence detail" not in str(payload)


def test_artifact_recovery_sanitizer_is_allowlisted_and_uses_fixed_copy():
    crump52_patches.apply_crump52_patches()
    safe = sync_module.sanitize_message({
        "id": ASSISTANT_ID,
        "role": "assistant",
        "content": "Saved answer.",
        "artifactRecovery": {
            "status": "FAILED",
            "format": ".DOCX",
            "purpose": "RESUME",
            "shouldRetry": True,
            "message": "attacker-controlled copy",
            "secret": "not allowed",
        },
    })
    invalid = sync_module.sanitize_message({
        "id": ASSISTANT_ID,
        "role": "assistant",
        "content": "Saved answer.",
        "artifactRecovery": {"status": "failed", "format": "exe", "shouldRetry": True},
    })

    assert safe["artifactRecovery"] == {
        "status": "failed",
        "format": "docx",
        "purpose": "resume",
        "shouldRetry": True,
        "message": "Crump wrote the content, but the downloadable file still needs packaging.",
    }
    assert "artifactRecovery" not in invalid


@pytest.mark.asyncio
async def test_stable_generated_file_identity_reuses_existing_row_and_upserts_storage_once(monkeypatch):
    stable_id = "00000000-0000-0000-0000-000000000099"

    class Database:
        def __init__(self):
            self.row = None
            self.upserts = []

        async def select_one(self, _table, **_kwargs):
            return self.row

        async def upsert(self, table, payload, *, on_conflict):
            self.upserts.append((table, payload, on_conflict))
            self.row = dict(payload)
            return [self.row]

    uploads = []

    class Response:
        status_code = 200

    class Client:
        def __init__(self, *_args, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def post(self, url, **kwargs):
            uploads.append((url, kwargs))
            return Response()

    database = Database()
    settings = type("Settings", (), {
        "storage_bucket": "crump-files",
        "supabase_url": "https://example.supabase.co",
        "supabase_service_key": "service-test",
        "max_upload_bytes": 50 * 1024 * 1024,
        "max_generated_video_bytes": 90 * 1024 * 1024,
    })()
    files = FileService(settings, database)
    monkeypatch.setattr(file_service_module.httpx, "AsyncClient", Client)

    first = await files.store_bytes(
        user_id=USER_ID,
        data=b"saved answer",
        filename="answer.docx",
        mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        kind="generated_document",
        chat_id=CHAT_ID,
        message_id=MESSAGE_ID,
        file_id=stable_id,
    )
    second = await files.store_bytes(
        user_id=USER_ID,
        data=b"saved answer",
        filename="answer.docx",
        mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        kind="generated_document",
        chat_id=CHAT_ID,
        message_id=MESSAGE_ID,
        file_id=stable_id,
    )

    assert first["id"] == stable_id == second["id"]
    assert len(uploads) == 1
    assert uploads[0][1]["headers"]["x-upsert"] == "true"
    assert len(database.upserts) == 1
    assert database.upserts[0][2] == "id"


def test_client_retry_is_packaging_only_and_never_resends_the_ai_request():
    client = (ROOT / "public" / "crump-5.0.js").read_text(encoding="utf-8")
    legacy = (ROOT / "public" / "app.js").read_text(encoding="utf-8")
    route = (ROOT / "backend" / "routes" / "chat.py").read_text(encoding="utf-8")
    client_segment = client.split("const artifactRecovery = message.artifactRecovery", 1)[1].split(
        "if (message.imageFile", 1
    )[0]
    route_segment = route.split("async def retry_chat_artifact", 1)[1].split(
        "def _file_ids", 1
    )[0]

    assert "Retry file packaging" in client_segment
    assert "/api/chat/artifacts/${encodeURIComponent(message.inReplyTo)}/retry" in client_segment
    assert "method: 'POST', body: '{}'" in client_segment
    assert "creditConfirmation" not in client_segment
    assert "featureUsage" not in client_segment
    assert "consume" not in client_segment
    assert "buildRequestBody" not in client_segment
    assert "sendMessage" not in client_segment
    assert "artifactRecovery" in legacy
    assert "result['artifactRecovery'] = {" in route
    assert "assistant_message['artifactRecovery'] = result['artifactRecovery']" in route
    assert "artifacts.create(" in route_segment
    assert "ai." not in route_segment
    assert "features." not in route_segment
    assert "consume" not in route_segment
    assert "refund" not in route_segment
