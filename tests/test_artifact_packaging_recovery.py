import asyncio
import hashlib
import json
from pathlib import Path

import pytest

import backend.crump52_patches as crump52_patches
import backend.file_service as file_service_module
import backend.sync_service as sync_module
from backend.artifact_service import ArtifactService
from backend.file_service import FileService, FileServiceError
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


def recovery_file_row(
    file_id,
    *,
    logical_file_id=None,
    message_id=MESSAGE_ID,
    format_name="docx",
    kind="generated_document",
):
    metadata = {
        "format": format_name,
        "title": "Resume",
        "profile": "professional",
        "_artifactFingerprint": "a" * 64,
        "_contentSha256": "b" * 64,
    }
    if logical_file_id:
        metadata["_logicalArtifactId"] = logical_file_id
    return {
        "id": file_id,
        "user_id": USER_ID,
        "chat_id": CHAT_ID,
        "message_id": message_id,
        "file_name": "resume.docx",
        "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "size_bytes": 512,
        "kind": kind,
        "status": "ready",
        "metadata": metadata,
        "deleted_at": None,
    }


class RecoveryFiles:
    def __init__(self, rows=None, *, failure=None):
        self.rows = dict(rows or {})
        self.failure = failure
        self.lookups = []

    async def get_owned(self, *, user_id, file_id, **_kwargs):
        self.lookups.append((user_id, file_id))
        if self.failure:
            raise self.failure
        row = self.rows.get(file_id)
        if not row:
            raise FileServiceError("File not found.", 404, "FILE_NOT_FOUND")
        return row

    public_file = staticmethod(FileService.public_file)


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
    logical_file_id = chat_routes._artifact_file_id(
        user_id=USER_ID, message_id=MESSAGE_ID, format_name="docx"
    )
    recovery_files = RecoveryFiles({
        logical_file_id: recovery_file_row(logical_file_id),
    })
    events = []

    async def record_event(_database, **kwargs):
        events.append((kwargs["event_name"], kwargs.get("artifact_type")))
        return True

    monkeypatch.setattr(chat_routes, "authenticate_request", authenticate)
    monkeypatch.setattr(chat_routes, "db", database)
    monkeypatch.setattr(chat_routes, "artifacts", artifacts)
    monkeypatch.setattr(chat_routes, "files", recovery_files)
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
async def test_packaging_retry_reuses_only_a_live_matching_version(monkeypatch):
    database = RecoveryDB()
    artifacts = RecoveryArtifacts()
    logical_file_id = chat_routes._artifact_file_id(
        user_id=USER_ID, message_id=MESSAGE_ID, format_name="docx"
    )
    version_file_id = "00000000-0000-0000-0000-000000000099"
    stored = recovery_file_row(version_file_id, logical_file_id=logical_file_id)
    public_artifact = FileService.public_file(stored)
    database.assistant["artifact"] = public_artifact
    database.job["response_data"]["artifact"] = public_artifact
    database.job["response_data"]["assistantMessage"] = dict(database.assistant)
    database.conversation["messages"] = [dict(database.user), dict(database.assistant)]

    monkeypatch.setattr(chat_routes, "authenticate_request", authenticate)
    monkeypatch.setattr(chat_routes, "db", database)
    monkeypatch.setattr(chat_routes, "artifacts", artifacts)
    monkeypatch.setattr(chat_routes, "files", RecoveryFiles({version_file_id: stored}))
    monkeypatch.setattr(chat_routes, "projects", NoProject())
    monkeypatch.setattr(chat_routes, "record_product_event", lambda *_args, **_kwargs: asyncio.sleep(0, result=True))

    payload = await chat_routes.retry_chat_artifact(MESSAGE_ID, object())

    assert payload["success"] is True
    assert payload["artifact"]["id"] == version_file_id
    assert payload["artifact"]["format"] == "docx"
    assert "_logicalArtifactId" not in payload["artifact"]["metadata"]
    assert artifacts.calls == []


@pytest.mark.asyncio
async def test_packaging_retry_rebuilds_a_missing_or_mismatched_saved_artifact(monkeypatch):
    for stored_row in (
        None,
        recovery_file_row(
            "00000000-0000-0000-0000-000000000098",
            logical_file_id="00000000-0000-0000-0000-000000000097",
            message_id="00000000-0000-0000-0000-000000000096",
            format_name="pdf",
        ),
    ):
        database = RecoveryDB()
        artifacts = RecoveryArtifacts()
        stale_id = (
            stored_row["id"] if stored_row else "00000000-0000-0000-0000-000000000095"
        )
        stale_artifact = {"id": stale_id, "format": "docx", "status": "ready"}
        database.assistant["artifact"] = stale_artifact
        database.job["response_data"]["artifact"] = stale_artifact
        database.job["response_data"]["assistantMessage"] = dict(database.assistant)
        database.conversation["messages"] = [dict(database.user), dict(database.assistant)]
        rows = {stored_row["id"]: stored_row} if stored_row else {}

        monkeypatch.setattr(chat_routes, "authenticate_request", authenticate)
        monkeypatch.setattr(chat_routes, "db", database)
        monkeypatch.setattr(chat_routes, "artifacts", artifacts)
        monkeypatch.setattr(chat_routes, "files", RecoveryFiles(rows))
        monkeypatch.setattr(chat_routes, "projects", NoProject())
        monkeypatch.setattr(chat_routes, "record_product_event", lambda *_args, **_kwargs: asyncio.sleep(0, result=True))

        payload = await chat_routes.retry_chat_artifact(MESSAGE_ID, object())

        assert payload["success"] is True
        assert len(artifacts.calls) == 1
        assert payload["artifact"]["id"] == artifacts.calls[0]["file_id"]


@pytest.mark.asyncio
async def test_packaging_retry_does_not_clear_recovery_when_file_lookup_is_ambiguous(monkeypatch):
    database = RecoveryDB()
    artifacts = RecoveryArtifacts()
    database.assistant["artifact"] = {"id": "00000000-0000-0000-0000-000000000094"}
    database.job["response_data"]["artifact"] = dict(database.assistant["artifact"])
    database.job["response_data"]["assistantMessage"] = dict(database.assistant)
    database.conversation["messages"] = [dict(database.user), dict(database.assistant)]

    monkeypatch.setattr(chat_routes, "authenticate_request", authenticate)
    monkeypatch.setattr(chat_routes, "db", database)
    monkeypatch.setattr(chat_routes, "artifacts", artifacts)
    monkeypatch.setattr(chat_routes, "files", RecoveryFiles(failure=RuntimeError("private database detail")))

    response = await chat_routes.retry_chat_artifact(MESSAGE_ID, object())
    payload = response_payload(response)

    assert response.status_code == 503
    assert payload["code"] == "ARTIFACT_RECOVERY_LOOKUP_UNAVAILABLE"
    assert payload["shouldRetry"] is True
    assert artifacts.calls == []
    assert "artifactRecovery" in database.job["response_data"]
    assert "private database detail" not in str(payload)


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
            self.inserts = []
            self.updates = []

        async def select_one(self, _table, **_kwargs):
            return self.row

        async def insert(self, table, payload):
            self.inserts.append((table, dict(payload)))
            self.row = dict(payload)
            return [self.row]

        async def update(self, table, payload, *, filters):
            self.updates.append((table, dict(payload), dict(filters)))
            self.row = {**self.row, **dict(payload)}
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
        metadata={"title": "Saved answer"},
        idempotency_fingerprint="a" * 64,
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
        metadata={"title": "Saved answer"},
        idempotency_fingerprint="a" * 64,
    )

    assert first["id"] == stable_id == second["id"]
    assert len(uploads) == 1
    assert uploads[0][1]["headers"]["x-upsert"] == "false"
    assert f"/{stable_id}/versions/" in uploads[0][0]
    assert uploads[0][1]["data"] == {"cacheControl": "0"}
    assert len(database.inserts) == 1
    assert database.updates == []
    assert "_artifactFingerprint" not in files.public_file(second)["metadata"]
    assert "_contentSha256" not in files.public_file(second)["metadata"]
    assert files.public_file(second)["metadata"]["title"] == "Saved answer"


@pytest.mark.asyncio
async def test_stable_generated_file_overwrites_changed_or_legacy_content(monkeypatch):
    stable_id = "00000000-0000-0000-0000-000000000099"

    class Database:
        def __init__(self):
            self.row = None
            self.inserts = []
            self.updates = []

        async def select_one(self, _table, **_kwargs):
            return self.row

        async def insert(self, table, payload):
            self.inserts.append((table, dict(payload)))
            self.row = dict(payload)
            return [self.row]

        async def update(self, table, payload, *, filters):
            self.updates.append((table, dict(payload), dict(filters)))
            if filters.get("storage_path") != f"eq.{self.row.get('storage_path')}":
                return []
            self.row = {**self.row, **dict(payload)}
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
        data=b"answer A",
        filename="answer.docx",
        mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        kind="generated_document",
        file_id=stable_id,
        metadata={"title": "Answer A"},
        idempotency_fingerprint="a" * 64,
    )
    second = await files.store_bytes(
        user_id=USER_ID,
        data=b"answer B",
        filename="answer.docx",
        mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        kind="generated_document",
        file_id=stable_id,
        metadata={"title": "Answer B"},
        idempotency_fingerprint="b" * 64,
    )

    assert first["id"] == stable_id == second["id"]
    assert len(uploads) == 2
    assert uploads[-1][1]["headers"]["x-upsert"] == "false"
    assert uploads[0][0] != uploads[1][0]
    assert uploads[-1][1]["files"]["file"][1] == b"answer B"
    assert database.row["metadata"]["title"] == "Answer B"
    assert database.row["metadata"]["_artifactFingerprint"] == "b" * 64
    assert len(database.row["metadata"]["_contentSha256"]) == 64
    assert "_artifactFingerprint" not in files.public_file(database.row)["metadata"]

    database.row = {
        **database.row,
        "metadata": {"title": "Legacy answer"},
    }
    await files.store_bytes(
        user_id=USER_ID,
        data=b"answer C",
        filename="answer.docx",
        mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        kind="generated_document",
        file_id=stable_id,
        metadata={"title": "Answer C"},
        idempotency_fingerprint="c" * 64,
    )

    assert len(uploads) == 3
    assert uploads[-1][1]["files"]["file"][1] == b"answer C"
    assert database.row["metadata"]["title"] == "Answer C"


@pytest.mark.asyncio
@pytest.mark.parametrize("format_name", ["docx", "pdf", "pptx", "xlsx"])
async def test_real_artifact_renderer_reuses_one_semantic_publication(monkeypatch, format_name):
    class Database:
        def __init__(self):
            self.row = None
            self.inserts = []

        async def select_one(self, _table, **_kwargs):
            return dict(self.row) if self.row else None

        async def insert(self, table, payload):
            self.inserts.append((table, dict(payload)))
            self.row = dict(payload)
            return [dict(self.row)]

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

    settings = type("Settings", (), {
        "storage_bucket": "crump-files",
        "supabase_url": "https://example.supabase.co",
        "supabase_service_key": "service-test",
        "max_upload_bytes": 50 * 1024 * 1024,
        "max_generated_video_bytes": 90 * 1024 * 1024,
    })()
    database = Database()
    files = FileService(settings, database)
    artifacts = ArtifactService(files)
    monkeypatch.setattr(file_service_module.httpx, "AsyncClient", Client)
    kwargs = {
        "user_id": USER_ID,
        "markdown": "# Fixture decision\n\nKeep the durable answer.",
        "format_name": format_name,
        "chat_id": CHAT_ID,
        "message_id": MESSAGE_ID,
        "title": "Fixture decision",
        "file_id": "00000000-0000-0000-0000-000000000099",
    }

    first = await artifacts.create(**kwargs)
    second = await artifacts.create(**kwargs)

    assert first["id"] == second["id"]
    assert len(uploads) == 1
    assert len(database.inserts) == 1
    assert database.row["metadata"]["_artifactFingerprint"]
    assert database.row["metadata"]["_contentSha256"]


@pytest.mark.asyncio
async def test_changed_artifact_markdown_stays_active_until_new_version_is_durable(monkeypatch):
    logical_id = "00000000-0000-0000-0000-000000000099"

    class Database:
        def __init__(self):
            self.rows = {}
            self.rpc_calls = []

        @staticmethod
        def value(raw):
            return str(raw or "").removeprefix("eq.")

        async def select_one(self, table, **kwargs):
            assert table == "user_files"
            filters = kwargs.get("filters") or {}
            row = self.rows.get(self.value(filters.get("id")))
            if not row or row.get("user_id") != self.value(filters.get("user_id")):
                return None
            if filters.get("deleted_at") == "is.null" and row.get("deleted_at") is not None:
                return None
            return dict(row)

        async def insert(self, table, payload):
            assert table == "user_files"
            assert payload["id"] not in self.rows
            self.rows[payload["id"]] = dict(payload)
            return [dict(payload)]

        async def rpc(self, name, payload):
            assert name == "retire_generated_document_versions"
            self.rpc_calls.append((name, dict(payload)))
            keep = self.rows[payload["p_keep_file_id"]]
            assert keep["user_id"] == payload["p_user_id"]
            assert keep["kind"] == "generated_document"
            assert keep["metadata"]["_logicalArtifactId"] == payload["p_logical_file_id"]
            retired = 0
            for file_id, row in self.rows.items():
                if (
                    file_id != payload["p_keep_file_id"]
                    and row["user_id"] == payload["p_user_id"]
                    and row["kind"] == "generated_document"
                    and row.get("deleted_at") is None
                    and (
                        file_id == payload["p_logical_file_id"]
                        or row["metadata"].get("_logicalArtifactId") == payload["p_logical_file_id"]
                    )
                ):
                    row["deleted_at"] = "2026-09-24T12:00:00Z"
                    retired += 1
            keep["deleted_at"] = None
            return retired

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

    settings = type("Settings", (), {
        "storage_bucket": "crump-files",
        "supabase_url": "https://example.supabase.co",
        "supabase_service_key": "service-test",
        "max_upload_bytes": 50 * 1024 * 1024,
        "max_generated_video_bytes": 90 * 1024 * 1024,
    })()
    database = Database()
    files = FileService(settings, database)
    artifacts = ArtifactService(files)
    monkeypatch.setattr(file_service_module.httpx, "AsyncClient", Client)
    common = {
        "user_id": USER_ID,
        "format_name": "docx",
        "chat_id": CHAT_ID,
        "message_id": MESSAGE_ID,
        "title": "Versioned answer",
        "file_id": logical_id,
    }

    old_version = await artifacts.create(
        **common,
        markdown="# Versioned answer\n\nKeep the original decision.",
    )
    new_version = await artifacts.create(
        **common,
        markdown="# Versioned answer\n\nUse the revised decision.",
    )

    assert old_version["id"] != new_version["id"]
    assert old_version["id"] != logical_id
    assert new_version["id"] != logical_id
    assert len(database.rows) == 2
    assert len(uploads) == 2
    assert database.rows[old_version["id"]]["deleted_at"] is None
    assert database.rows[new_version["id"]]["deleted_at"] is None
    assert {
        row["metadata"]["_logicalArtifactId"]
        for row in database.rows.values()
    } == {logical_id}

    await files.retire_artifact_versions(
        user_id=USER_ID,
        logical_file_id=logical_id,
        keep_file_id=new_version["id"],
    )

    assert database.rpc_calls == [(
        "retire_generated_document_versions",
        {
            "p_user_id": USER_ID,
            "p_logical_file_id": logical_id,
            "p_keep_file_id": new_version["id"],
        },
    )]
    assert database.rows[old_version["id"]]["deleted_at"] is not None
    assert database.rows[new_version["id"]]["deleted_at"] is None
    with pytest.raises(FileServiceError, match="File not found"):
        await files.get_owned(user_id=USER_ID, file_id=old_version["id"])
    assert (
        await files.get_owned(user_id=USER_ID, file_id=new_version["id"])
    )["id"] == new_version["id"]


@pytest.mark.asyncio
async def test_storage_db_failure_keeps_old_pointer_and_removes_unpublished_candidate(monkeypatch):
    old_path = f"{USER_ID}/stable.docx"
    old_bytes = b"answer A"

    class Database:
        def __init__(self):
            self.row = {
                "id": "00000000-0000-0000-0000-000000000099",
                "user_id": USER_ID,
                "storage_path": old_path,
                "deleted_at": None,
                "metadata": {
                    "_artifactFingerprint": "a" * 64,
                    "_contentSha256": hashlib.sha256(old_bytes).hexdigest(),
                },
            }

        async def select_one(self, _table, **_kwargs):
            return dict(self.row)

        async def update(self, *_args, **_kwargs):
            raise RuntimeError("database write failed")

    uploads = []

    class Response:
        status_code = 200

    class Client:
        def __init__(self, *_args, **_kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *_args): return False
        async def post(self, url, **kwargs):
            uploads.append(url)
            return Response()

    settings = type("Settings", (), {
        "storage_bucket": "crump-files", "supabase_url": "https://example.supabase.co",
        "supabase_service_key": "service-test", "max_upload_bytes": 50 * 1024 * 1024,
        "max_generated_video_bytes": 90 * 1024 * 1024,
    })()
    database = Database()
    files = FileService(settings, database)
    deleted = []

    async def delete_candidate(_method, _path, *, payload=None, **_kwargs):
        deleted.extend(payload["prefixes"])
        return {}

    files._storage_json = delete_candidate
    monkeypatch.setattr(file_service_module.httpx, "AsyncClient", Client)

    with pytest.raises(RuntimeError, match="database write failed"):
        await files.store_bytes(
            user_id=USER_ID, data=b"answer B", filename="answer.docx",
            mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            kind="generated_document", file_id=database.row["id"],
            idempotency_fingerprint="b" * 64,
        )

    assert database.row["storage_path"] == old_path
    assert len(uploads) == 1
    assert len(deleted) == 1
    assert deleted[0] != old_path


@pytest.mark.asyncio
async def test_storage_reconciles_database_commit_after_transport_error(monkeypatch):
    old_path = f"{USER_ID}/stable.docx"

    class Database:
        def __init__(self):
            self.row = {
                "id": "00000000-0000-0000-0000-000000000099", "user_id": USER_ID,
                "storage_path": old_path, "deleted_at": None, "metadata": {},
            }

        async def select_one(self, _table, **_kwargs):
            return dict(self.row)

        async def update(self, _table, payload, **_kwargs):
            self.row = {**self.row, **dict(payload)}
            raise RuntimeError("response lost after commit")

    class Response:
        status_code = 200

    class Client:
        def __init__(self, *_args, **_kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *_args): return False
        async def post(self, _url, **_kwargs): return Response()

    settings = type("Settings", (), {
        "storage_bucket": "crump-files", "supabase_url": "https://example.supabase.co",
        "supabase_service_key": "service-test", "max_upload_bytes": 50 * 1024 * 1024,
        "max_generated_video_bytes": 90 * 1024 * 1024,
    })()
    database = Database()
    files = FileService(settings, database)
    deleted = []

    async def delete_path(_method, _path, *, payload=None, **_kwargs):
        deleted.extend(payload["prefixes"])
        return {}

    files._storage_json = delete_path
    monkeypatch.setattr(file_service_module.httpx, "AsyncClient", Client)

    stored = await files.store_bytes(
        user_id=USER_ID, data=b"answer B", filename="answer.docx",
        mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        kind="generated_document", file_id=database.row["id"],
        idempotency_fingerprint="b" * 64,
    )

    assert stored["storage_path"] == database.row["storage_path"]
    assert stored["metadata"]["_artifactFingerprint"] == "b" * 64
    assert deleted == [old_path]


@pytest.mark.asyncio
async def test_concurrent_changed_versions_publish_one_matching_row(monkeypatch):
    stable_id = "00000000-0000-0000-0000-000000000099"
    old_path = f"{USER_ID}/stable.docx"

    class Database:
        def __init__(self):
            self.row = {
                "id": stable_id, "user_id": USER_ID, "storage_path": old_path,
                "deleted_at": None, "metadata": {},
            }
            self.initial_reads = 0
            self.both_read = asyncio.Event()

        async def select_one(self, _table, **_kwargs):
            if self.initial_reads < 2:
                snapshot = dict(self.row)
                self.initial_reads += 1
                if self.initial_reads == 2:
                    self.both_read.set()
                await self.both_read.wait()
                return snapshot
            return dict(self.row)

        async def update(self, _table, payload, *, filters):
            if filters["storage_path"] != f"eq.{self.row['storage_path']}":
                return []
            self.row = {**self.row, **dict(payload)}
            return [dict(self.row)]

    class Response:
        status_code = 200

    class Client:
        def __init__(self, *_args, **_kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *_args): return False
        async def post(self, _url, **_kwargs): return Response()

    settings = type("Settings", (), {
        "storage_bucket": "crump-files", "supabase_url": "https://example.supabase.co",
        "supabase_service_key": "service-test", "max_upload_bytes": 50 * 1024 * 1024,
        "max_generated_video_bytes": 90 * 1024 * 1024,
    })()
    database = Database()
    files = FileService(settings, database)
    deleted = []

    async def delete_path(_method, _path, *, payload=None, **_kwargs):
        deleted.extend(payload["prefixes"])
        return {}

    files._storage_json = delete_path
    monkeypatch.setattr(file_service_module.httpx, "AsyncClient", Client)

    async def publish(label):
        return await files.store_bytes(
            user_id=USER_ID, data=f"answer {label}".encode(), filename="answer.docx",
            mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            kind="generated_document", file_id=stable_id,
            idempotency_fingerprint=label.lower() * 64,
        )

    results = await asyncio.gather(publish("b"), publish("c"), return_exceptions=True)
    successes = [item for item in results if isinstance(item, dict)]
    failures = [item for item in results if isinstance(item, Exception)]

    assert len(successes) == 1
    assert len(failures) == 1
    assert getattr(failures[0], "code", None) == "FILE_VERSION_CONFLICT"
    assert successes[0]["storage_path"] == database.row["storage_path"]
    assert database.row["metadata"]["_contentSha256"] == hashlib.sha256(
        f"answer {database.row['metadata']['_artifactFingerprint'][0]}".encode()
    ).hexdigest()
    assert old_path in deleted


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
