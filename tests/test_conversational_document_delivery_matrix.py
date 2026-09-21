"""Local-only chat-to-private-file matrix using the production route and formatter."""

from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock
from zipfile import is_zipfile

import pytest
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.testclient import TestClient
from pypdf import PdfReader

from backend.ai_consent import CURRENT_AI_DATA_SHARING_CONSENT_VERSION
from backend.artifact_service import ArtifactService, MIME
from backend.file_service import FileService
from backend.intelligence_service import PreparedRequest
from backend.routes import chat as chat_routes
from backend.routes import files as file_routes
from backend.security import normalize_chat_id


OWNER = "fixture-owner"
OTHER_OWNER = "fixture-other-owner"
CHAT_ID = "00000000-0000-4000-8000-000000000010"
MESSAGE_ID = "00000000-0000-4000-8000-000000000011"
ANSWER = "# Fixture decision\n\nA useful, completed answer for the fixture owner."


def matches(row: dict, filters: dict | None) -> bool:
    for key, condition in (filters or {}).items():
        if condition == "is.null":
            if row.get(key) is not None:
                return False
        elif isinstance(condition, str) and condition.startswith("eq."):
            if str(row.get(key)) != condition[3:]:
                return False
        elif row.get(key) != condition:
            return False
    return True


class FixtureDB:
    def __init__(self) -> None:
        self.files: dict[str, dict] = {}
        self.messages: list[dict] = []
        self.events: list[tuple[str, str | None]] = []
        self.jobs: dict[str, dict] = {}
        self.fail_persistence = False
        self.persistence_receipt = [
            {"resulting_revision": 1, "resulting_updated_at": "2026-09-20T00:00:00Z"}
        ]

    async def select_one(self, table: str, *, filters=None, **_kwargs):
        if table == "user_settings":
            return {"assistant_name": "Crump", "work_mode": True}
        if table == "user_files":
            return next((dict(row) for row in self.files.values() if matches(row, filters)), None)
        return None

    async def select(self, table: str, *, filters=None, **_kwargs):
        assert table == "user_files"
        return [dict(row) for row in self.files.values() if matches(row, filters)]

    async def rpc(self, name: str, payload: dict, **_kwargs):
        if name == "claim_chat_job":
            return [{"job_state": "claimed"}]
        if name == "persist_chat_reply":
            if self.fail_persistence:
                raise RuntimeError("private fixture persistence failure")
            assert payload["p_user_id"] == OWNER
            receipt = self.persistence_receipt
            if (
                isinstance(receipt, list)
                and receipt
                and isinstance(receipt[0], dict)
                and receipt[0].get("resulting_revision") is not None
                and str(receipt[0].get("resulting_updated_at") or "").strip()
            ):
                self.messages = [payload["p_user_message"], payload["p_assistant_message"]]
            return receipt
        if name == "record_product_event":
            self.events.append((payload["p_event_name"], payload.get("p_artifact_type")))
            return True
        raise AssertionError(f"Unexpected local RPC: {name}")

    async def update(self, table: str, payload: dict, *, filters: dict, **_kwargs):
        assert table == "chat_jobs"
        self.jobs[filters["message_id"]] = dict(payload)
        return [dict(payload)]


class FixtureFiles(FileService):
    def __init__(self, database: FixtureDB) -> None:
        super().__init__(chat_routes.settings, database)
        self.bytes_by_id: dict[str, bytes] = {}

    async def store_bytes(self, *, user_id, data, filename, mime_type, kind,
                          chat_id=None, message_id=None, metadata=None, file_id=None):
        file_id = normalize_chat_id(file_id)
        row = {
            "id": file_id,
            "user_id": user_id,
            "chat_id": chat_id,
            "message_id": message_id,
            "file_name": self.clean_filename(filename),
            "mime_type": mime_type,
            "size_bytes": len(data),
            "kind": kind,
            "status": "ready",
            "deleted_at": None,
            "metadata": metadata or {},
        }
        self.db.files[file_id] = row
        self.bytes_by_id[file_id] = data
        return dict(row)

    async def download_bytes(self, *, row, max_bytes=None):
        return self.bytes_by_id[row["id"]]

    async def signed_url(self, *, row, expires_in=600, download=False):
        assert expires_in == 600
        assert download is False
        return f"/fixture-storage/{row['id']}"


class FixtureAI:
    def needs_external_lookup(self, _message):
        return False

    async def chat(self, _payload):
        return {"response": ANSWER, "model": "fixture-model", "usage": {}}


class FixtureFeatures:
    def entitled(self, *_args):
        return False

    async def authorize(self, _user, components, *_args, **_kwargs):
        return SimpleNamespace(action_key="fixture", max_by_code={key: 0 for key in components})

    async def consume_message(self, *_args, **_kwargs):
        return {"eventId": "fixture-usage", "used": 1, "limit": 100, "remaining": 99, "creditsSpent": 0}

    async def refund(self, *_args, **_kwargs):
        return None


@pytest.fixture
def delivery(monkeypatch):
    database = FixtureDB()
    files = FixtureFiles(database)
    artifacts = ArtifactService(files)

    async def authenticate(request: Request, *_args, **_kwargs):
        owner = request.headers.get("x-fixture-owner")
        if owner not in {OWNER, OTHER_OWNER}:
            raise HTTPException(status_code=401, detail="Fixture authentication required")
        return SimpleNamespace(
            user={
                "id": owner,
                "email": f"{owner}@example.test",
                "full_name": "Fixture",
                "ai_data_sharing_consent_at": "2026-09-20T00:00:00Z",
                "ai_data_sharing_consent_version": CURRENT_AI_DATA_SHARING_CONSENT_VERSION,
                "ai_data_sharing_consent_revoked_at": None,
            },
            session={"id": "fixture-session"},
            token="fixture-token",
        )

    async def prepare(_user_id, payload, **_kwargs):
        creation_intent = None
        if payload.get("artifactFormat") == "xlsx":
            creation_intent = {
                "kind": "video",
                "stage": "execute",
                "confidence": 0.9,
                "brief": str(payload.get("message") or ""),
                "question": "",
                "title": "",
                "format": "",
            }
        return PreparedRequest(
            payload=dict(payload), requested_mode="auto", effective_mode="balanced",
            verification_level="off", route="chat", creation_intent=creation_intent, user_tier="free",
        )

    async def verify_answer(*, result, **_kwargs):
        return result, False

    async def record_event(_database, **kwargs):
        database.events.append((kwargs["event_name"], kwargs.get("artifact_type")))
        return True

    for route in (chat_routes, file_routes):
        monkeypatch.setattr(route, "db", database)
        monkeypatch.setattr(route, "files", files)
        monkeypatch.setattr(route, "authenticate_request", authenticate)
        monkeypatch.setattr(route, "record_product_event", record_event)
    monkeypatch.setattr(chat_routes, "artifacts", artifacts)
    monkeypatch.setattr(chat_routes, "ai", FixtureAI())
    monkeypatch.setattr(chat_routes, "features", FixtureFeatures())
    monkeypatch.setattr(chat_routes, "intelligence", SimpleNamespace(
        prepare=prepare,
        verify_answer=verify_answer,
        learn_explicit=AsyncMock(return_value=0),
        record_trace=AsyncMock(return_value=None),
    ))
    monkeypatch.setattr(chat_routes, "media", SimpleNamespace(
        needs_prior_files=lambda _message: False,
        is_image_request=lambda *_args: False,
        is_edit_request=lambda *_args: False,
    ))
    monkeypatch.setattr(chat_routes, "apply_project_context", AsyncMock(return_value=None))
    monkeypatch.setattr(chat_routes, "mark_check_in_responded", AsyncMock(return_value=None))
    monkeypatch.setattr(chat_routes, "feature_for_request", lambda **_kwargs: (None, {}))

    app = FastAPI()
    app.include_router(chat_routes.router)
    app.include_router(file_routes.router)

    @app.get("/fixture-storage/{file_id}")
    async def fixture_storage(file_id: str):
        return Response(files.bytes_by_id[file_id], media_type="application/pdf")

    return TestClient(app), database, files


@pytest.mark.parametrize(
    ("format_name", "message", "history", "category", "explicit_format"),
    [
        ("docx", "Write a decision memo and deliver it as a Word document.", [], "document", None),
        ("pdf", "Write a decision memo and deliver it as a PDF.", [], "pdf", None),
        ("pptx", "Can you export it?", [
            {"role": "user", "content": "Build a presentation for the product launch."},
            {"role": "assistant", "content": "Here is the completed slide narrative."},
        ], "presentation", None),
        (
            "xlsx",
            "Create a production budget for this video campaign.",
            [],
            "spreadsheet",
            "xlsx",
        ),
    ],
)
def test_chat_persists_owned_artifact_and_delivers_private_download(
    delivery, format_name, message, history, category, explicit_format,
):
    client, database, files = delivery
    payload = {"chatId": CHAT_ID, "messageId": MESSAGE_ID, "message": message, "history": history}
    if explicit_format:
        payload["artifactFormat"] = explicit_format
    response = client.post(
        "/api/chat",
        headers={"x-fixture-owner": OWNER},
        json=payload,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["success"] is True
    artifact = body["artifact"]
    assert artifact["format"] == format_name
    assert artifact["type"] == MIME[format_name]
    assert artifact["url"] == f"/api/files/{artifact['id']}/content"
    assert body["assistantMessage"]["artifact"] == artifact
    assert database.messages[1]["artifact"] == artifact
    assert database.messages[1]["inReplyTo"] == MESSAGE_ID
    assert database.jobs[f"eq.{MESSAGE_ID}"]["response_data"]["artifact"] == artifact
    assert database.files[artifact["id"]]["user_id"] == OWNER
    assert database.files[artifact["id"]]["kind"] == "generated_document"
    assert ("ArtifactRequested", category) in database.events
    assert ("ArtifactPackaged", category) in database.events
    assert ("ActivationReached", None) in database.events

    stored_bytes = files.bytes_by_id[artifact["id"]]
    if format_name == "pdf":
        assert stored_bytes.startswith(b"%PDF")
        assert "Fixture decision" in (PdfReader(BytesIO(stored_bytes)).pages[0].extract_text() or "")
    else:
        assert is_zipfile(BytesIO(stored_bytes))

    content_url = artifact["url"]
    assert client.get(content_url, headers={"x-fixture-owner": OTHER_OWNER}).status_code == 404
    assert client.get(content_url).status_code == 401
    download = client.get(f"{content_url}?download=1", headers={"x-fixture-owner": OWNER})
    assert download.status_code == 200
    assert download.content == stored_bytes
    assert download.headers["content-type"].startswith(MIME[format_name])
    assert download.headers["content-disposition"].startswith("attachment; filename=")
    assert ("ArtifactDownloaded", category) in database.events

    listing = client.get("/api/files", headers={"x-fixture-owner": OWNER})
    assert listing.status_code == 200
    assert listing.json()["files"][0]["id"] == artifact["id"]
    assert client.get("/api/files", headers={"x-fixture-owner": OTHER_OWNER}).json()["files"] == []

    if format_name == "pdf":
        inline = client.get(content_url, headers={"x-fixture-owner": OWNER}, follow_redirects=False)
        assert inline.status_code == 302
        assert inline.headers["location"] == f"/fixture-storage/{artifact['id']}"
        preview = client.get(inline.headers["location"])
        assert preview.status_code == 200
        assert preview.headers["content-type"].startswith("application/pdf")
        assert preview.content == stored_bytes


def test_chat_persistence_failure_never_records_activation(delivery, monkeypatch):
    client, database, _files = delivery
    database.fail_persistence = True
    refund_usage = AsyncMock(return_value=None)
    monkeypatch.setattr(chat_routes, "refund_usage", refund_usage)

    response = client.post(
        "/api/chat",
        headers={"x-fixture-owner": OWNER},
        json={
            "chatId": CHAT_ID,
            "messageId": MESSAGE_ID,
            "message": "Give me one useful answer.",
        },
    )

    assert response.status_code == 503
    assert response.json()["code"] == "CHAT_PERSISTENCE"
    assert ("ActivationReached", None) not in database.events
    assert database.messages == []
    assert database.jobs[f"eq.{MESSAGE_ID}"]["status"] == "failed"
    assert database.jobs[f"eq.{MESSAGE_ID}"]["error_code"] == "CHAT_PERSISTENCE"
    refund_usage.assert_awaited_once_with(database, OWNER, "fixture-usage")


@pytest.mark.parametrize(
    "receipt",
    [None, [], {}, [None], [{}], [{"resulting_revision": 1}], [{"resulting_updated_at": "2026-09-20T00:00:00Z"}]],
    ids=["none", "empty-list", "mapping", "null-row", "empty-row", "missing-updated-at", "missing-revision"],
)
def test_chat_malformed_persistence_receipt_never_records_activation(delivery, monkeypatch, receipt):
    client, database, _files = delivery
    database.persistence_receipt = receipt
    refund_usage = AsyncMock(return_value=None)
    monkeypatch.setattr(chat_routes, "refund_usage", refund_usage)

    response = client.post(
        "/api/chat",
        headers={"x-fixture-owner": OWNER},
        json={
            "chatId": CHAT_ID,
            "messageId": MESSAGE_ID,
            "message": "Give me one useful answer.",
        },
    )

    assert response.status_code == 503
    assert response.json()["code"] == "CHAT_PERSISTENCE"
    assert ("ActivationReached", None) not in database.events
    assert database.messages == []
    assert database.jobs[f"eq.{MESSAGE_ID}"]["status"] == "failed"
    assert database.jobs[f"eq.{MESSAGE_ID}"]["error_code"] == "CHAT_PERSISTENCE"
    refund_usage.assert_awaited_once_with(database, OWNER, "fixture-usage")
