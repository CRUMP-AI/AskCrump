"""Loopback-only FastAPI fixture for the conversational document browser gate.

The process uses the real chat/files routers and document formatter with in-memory
auth, database, AI, and storage substitutes. It must never contact an external
provider or production service.
"""

from __future__ import annotations

import asyncio
import ipaddress
import os
import socket
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("APP_URL", "http://127.0.0.1")
os.environ.setdefault("COOKIE_SECURE", "false")
os.environ.setdefault("SUPABASE_URL", "http://127.0.0.1:9")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fixture-service-key")

_socket_connect = socket.socket.connect
_socket_connect_ex = socket.socket.connect_ex
_socket_getaddrinfo = socket.getaddrinfo
_asyncio_create_connection = asyncio.BaseEventLoop.create_connection


def _require_loopback_host(raw_host) -> None:
    host = str(raw_host or "").strip("[]")
    try:
        is_loopback = ipaddress.ip_address(host).is_loopback
    except ValueError:
        is_loopback = host.lower() == "localhost"
    if not is_loopback:
        raise RuntimeError(f"The document-delivery fixture blocked an external connection to {host}.")


def _loopback_only_connect(sock: socket.socket, address) -> None:
    if not isinstance(address, tuple) or not address:
        raise RuntimeError("The document-delivery fixture blocks non-IP socket connections.")
    _require_loopback_host(address[0])
    _socket_connect(sock, address)


def _loopback_only_connect_ex(sock: socket.socket, address) -> int:
    if not isinstance(address, tuple) or not address:
        raise RuntimeError("The document-delivery fixture blocks non-IP socket connections.")
    _require_loopback_host(address[0])
    return _socket_connect_ex(sock, address)


def _loopback_only_getaddrinfo(host, *args, **kwargs):
    if host is not None:
        _require_loopback_host(host)
    return _socket_getaddrinfo(host, *args, **kwargs)


async def _loopback_only_asyncio_connection(self, protocol_factory, host=None, port=None, *args, **kwargs):
    if host is not None:
        _require_loopback_host(host)
    return await _asyncio_create_connection(self, protocol_factory, host, port, *args, **kwargs)


socket.socket.connect = _loopback_only_connect
socket.socket.connect_ex = _loopback_only_connect_ex
socket.getaddrinfo = _loopback_only_getaddrinfo
asyncio.BaseEventLoop.create_connection = _loopback_only_asyncio_connection

import uvicorn  # noqa: E402
from fastapi import FastAPI, HTTPException, Request, Response  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

from backend.artifact_service import ArtifactService  # noqa: E402
from backend.file_service import FileService  # noqa: E402
from backend.intelligence_service import PreparedRequest  # noqa: E402
from backend.routes import chat as chat_routes  # noqa: E402
from backend.routes import files as file_routes  # noqa: E402
from backend.security import normalize_chat_id  # noqa: E402


OWNER = "fixture-owner"
OTHER_OWNER = "fixture-other-owner"
READY_PREFIX = "ASKCRUMP_DOCUMENT_FIXTURE_READY="


def _filter_value(value):
    if isinstance(value, str) and value.startswith("eq."):
        return value[3:]
    return value


def _matches(row: dict, filters: dict | None) -> bool:
    for key, condition in (filters or {}).items():
        if condition == "is.null":
            if row.get(key) is not None:
                return False
        elif row.get(key) != _filter_value(condition):
            return False
    return True


class FixtureDB:
    def __init__(self) -> None:
        self.files: dict[str, dict] = {}
        self.messages: list[dict] = []
        self.conversations: dict[tuple[str, str], dict] = {}
        self.events: list[tuple[str, str | None]] = []
        self.auth_attempts: list[tuple[str, str | None]] = []
        self.jobs: dict[tuple[str, str], dict] = {}
        self.receipts: dict[tuple[str, str], dict] = {}

    async def select_one(self, table: str, *, filters=None, **_kwargs):
        if table == "user_settings":
            return {"assistant_name": "Crump", "work_mode": True}
        if table == "user_files":
            return next((dict(row) for row in self.files.values() if _matches(row, filters)), None)
        if table == "user_chats":
            user_id = str(_filter_value((filters or {}).get("user_id")) or "")
            chat_id = str(_filter_value((filters or {}).get("chat_id")) or "")
            value = self.conversations.get((user_id, chat_id))
            return dict(value) if value and _matches(value, filters) else None
        if table == "chat_jobs":
            user_id = str(_filter_value((filters or {}).get("user_id")) or "")
            message_id = str(_filter_value((filters or {}).get("message_id")) or "")
            value = self.jobs.get((user_id, message_id))
            return dict(value) if value and _matches(value, filters) else None
        return None

    async def select(self, table: str, *, filters=None, **_kwargs):
        if table != "user_files":
            return []
        return [dict(row) for row in self.files.values() if _matches(row, filters)]

    async def upsert(self, table: str, payload: dict, **_kwargs):
        if table != "message_receipts":
            raise AssertionError(f"Unexpected local upsert: {table}")
        key = (str(payload.get("user_id") or ""), str(payload.get("message_id") or ""))
        self.receipts[key] = dict(payload)
        return [dict(payload)]

    async def rpc(self, name: str, payload: dict, **_kwargs):
        if name == "claim_chat_job_v2":
            key = (str(payload["p_user_id"]), str(payload["p_message_id"]))
            existing = self.jobs.get(key)
            if existing and existing.get("status") == "completed":
                return [{"job_state": "completed", "response_data": existing.get("response_data")}]
            token = "00000000-0000-4000-8000-000000000779"
            self.jobs[key] = {
                "user_id": key[0],
                "message_id": key[1],
                "chat_id": str(payload["p_chat_id"]),
                "status": "processing",
                "claim_token": token,
                "response_data": None,
            }
            return [{"job_state": "claimed", "claim_token": token}]
        if name == "persist_chat_reply":
            user_id = str(payload["p_user_id"])
            chat_id = str(payload["p_chat_id"])
            self.messages = [payload["p_user_message"], payload["p_assistant_message"]]
            self.conversations[(user_id, chat_id)] = {
                "user_id": user_id,
                "chat_id": chat_id,
                "messages": list(self.messages),
                "revision": 1,
                "updated_at": "2026-10-01T00:00:00Z",
            }
            return [{"resulting_revision": 1, "resulting_updated_at": "2026-10-01T00:00:00Z"}]
        if name == "record_product_event":
            self.events.append((payload["p_event_name"], payload.get("p_artifact_type")))
            return True
        if name == "retire_generated_document_versions":
            keep_file_id = str(payload.get("p_keep_file_id") or "")
            logical_file_id = str(payload.get("p_logical_file_id") or "")
            retired = 0
            for row in self.files.values():
                metadata = row.get("metadata") or {}
                if (
                    row.get("user_id") == payload.get("p_user_id")
                    and metadata.get("_logicalArtifactId") == logical_file_id
                    and row.get("id") != keep_file_id
                    and row.get("deleted_at") is None
                ):
                    row["deleted_at"] = "2026-10-01T00:00:00Z"
                    retired += 1
            return retired
        if name == "release_chat_job_claim":
            key = (str(payload["p_user_id"]), str(payload["p_message_id"]))
            job = self.jobs.get(key)
            if job and job.get("claim_token") == payload.get("p_claim_token"):
                job.update({"status": "failed", "claim_token": None, "error_code": payload.get("p_error_code")})
                return True
            return False
        raise AssertionError(f"Unexpected local RPC: {name}")

    async def update(self, table: str, payload: dict, *, filters: dict, **_kwargs):
        if table == "chat_jobs":
            user_id = str(_filter_value(filters.get("user_id")) or OWNER)
            message_id = str(_filter_value(filters.get("message_id")) or "")
            key = (user_id, message_id)
            stored = self.jobs.get(key)
            if not stored or not _matches(stored, filters):
                return []
            current = dict(stored)
            current.update(payload)
            current.setdefault("user_id", user_id)
            current.setdefault("message_id", message_id)
            self.jobs[key] = current
            return [dict(current)]
        if table == "user_files":
            updated = []
            for file_id, row in self.files.items():
                if _matches(row, filters):
                    row.update(payload)
                    self.files[file_id] = row
                    updated.append(dict(row))
            return updated
        raise AssertionError(f"Unexpected local update: {table}")


class FixtureFiles(FileService):
    def __init__(self, database: FixtureDB) -> None:
        super().__init__(chat_routes.settings, database)
        self.bytes_by_id: dict[str, bytes] = {}

    async def store_bytes(
        self,
        *,
        user_id,
        data,
        filename,
        mime_type,
        kind,
        chat_id=None,
        message_id=None,
        metadata=None,
        file_id=None,
        idempotency_fingerprint=None,
        logical_artifact_id=None,
        **_kwargs,
    ):
        file_id = normalize_chat_id(file_id)
        existing = self.db.files.get(file_id)
        existing_metadata = (existing or {}).get("metadata") or {}
        if (
            existing
            and existing.get("user_id") == user_id
            and existing.get("deleted_at") is None
            and existing_metadata.get("_artifactFingerprint") == idempotency_fingerprint
        ):
            return dict(existing)
        row = {
            "id": file_id,
            "user_id": user_id,
            "chat_id": chat_id,
            "message_id": message_id,
            "storage_path": f"fixture/{user_id}/{file_id}/{self.clean_filename(filename)}",
            "file_name": self.clean_filename(filename),
            "mime_type": mime_type,
            "size_bytes": len(data),
            "kind": kind,
            "status": "ready",
            "deleted_at": None,
            "created_at": "2026-10-01T00:00:00Z",
            "updated_at": "2026-10-01T00:00:00Z",
            "metadata": {
                **dict(metadata or {}),
                **({"_artifactFingerprint": idempotency_fingerprint} if idempotency_fingerprint else {}),
                **({"_logicalArtifactId": logical_artifact_id} if logical_artifact_id else {}),
                "_contentSha256": "0" * 64,
            },
        }
        self.db.files[file_id] = row
        self.bytes_by_id[file_id] = data
        return dict(row)

    async def download_bytes(self, *, row, max_bytes=None):
        data = self.bytes_by_id[row["id"]]
        if max_bytes is not None and len(data) > max_bytes:
            raise AssertionError("Fixture download exceeded the requested bound")
        return data

    async def signed_url(self, *, row, expires_in=600, download=False):
        return f"/fixture-storage/{row['id']}"


class FixtureAI:
    def needs_external_lookup(self, _message):
        return False

    def activity_for(self, _message, _file_types):
        return "creating"

    async def chat(self, _payload):
        return {
            "response": "# Fixture decision\n\nA useful, completed answer for the fixture owner.",
            "model": "fixture-model",
            "usage": {},
        }


class FixtureFeatures:
    def entitled(self, *_args):
        return False

    async def authorize(self, _user, components, *_args, **_kwargs):
        return SimpleNamespace(action_key="fixture", max_by_code={key: 0 for key in components})

    async def consume_message(self, *_args, **_kwargs):
        return {"eventId": "fixture-usage", "used": 1, "limit": 100, "remaining": 99, "creditsSpent": 0}

    async def refund(self, *_args, **_kwargs):
        return None


class ForbiddenFixtureService:
    def __init__(self, label: str) -> None:
        self.label = label

    def __getattr__(self, name: str):
        raise AssertionError(f"Unexpected {self.label}.{name} access in the document-delivery fixture")


async def forbid_generated_output_attachment(**_kwargs):
    raise AssertionError("Unexpected Project attachment in the document-delivery fixture")


def create_fixture_app() -> tuple[FastAPI, FixtureDB, FixtureFiles]:
    database = FixtureDB()
    files = FixtureFiles(database)
    artifacts = ArtifactService(files)

    async def authenticate(request: Request, *_args, **_kwargs):
        owner = request.cookies.get("fixture_owner")
        database.auth_attempts.append((request.url.path, owner))
        if owner not in {OWNER, OTHER_OWNER}:
            raise HTTPException(status_code=401, detail="Fixture authentication required")
        return SimpleNamespace(
            user={"id": owner, "email": f"{owner}@example.test", "full_name": "Fixture", "subscription_tier": "free"},
            session={"id": "fixture-session"},
            token="fixture-token",
        )

    async def prepare(_user_id, payload, **_kwargs):
        return PreparedRequest(
            payload=dict(payload),
            requested_mode="auto",
            effective_mode="balanced",
            verification_level="off",
            route="chat",
            creation_intent=None,
            user_tier="free",
        )

    async def verify_answer(*, result, **_kwargs):
        return result, False

    async def record_event(_database, **kwargs):
        database.events.append((kwargs["event_name"], kwargs.get("artifact_type")))
        return True

    for route in (chat_routes, file_routes):
        route.db = database
        route.files = files
        route.authenticate_request = authenticate
        route.record_product_event = record_event
    chat_routes.artifacts = artifacts
    chat_routes.ai = FixtureAI()
    chat_routes.features = FixtureFeatures()
    chat_routes.intelligence = SimpleNamespace(
        prepare=prepare,
        verify_answer=verify_answer,
        learn_explicit=AsyncMock(return_value=0),
        record_trace=AsyncMock(return_value=None),
    )
    chat_routes.media = SimpleNamespace(
        needs_prior_files=lambda _message: False,
        is_image_request=lambda *_args: False,
        is_edit_request=lambda *_args: False,
    )
    chat_routes.projects = ForbiddenFixtureService("projects")
    chat_routes.manuscripts = ForbiddenFixtureService("manuscripts")
    chat_routes.attach_generated_outputs = forbid_generated_output_attachment
    file_routes.media = ForbiddenFixtureService("file_media")
    chat_routes.apply_project_context = AsyncMock(return_value=None)
    chat_routes.mark_check_in_responded = AsyncMock(return_value=None)
    chat_routes.feature_for_request = lambda **_kwargs: (None, {})

    app = FastAPI()
    app.include_router(chat_routes.router)
    app.include_router(file_routes.router)

    @app.get("/api/usage/check")
    async def usage_check(request: Request):
        await authenticate(request)
        return {"success": True, "limits": {"messages": -1}, "usage": {"messages": 0}}

    @app.get("/fixture-state")
    async def fixture_state(request: Request):
        auth = await authenticate(request)
        owner_jobs = [
            row for key, row in database.jobs.items()
            if key[0] == auth.user["id"]
        ]
        owner_files = [
            files.public_file(row)
            for row in database.files.values()
            if row.get("user_id") == auth.user["id"] and row.get("deleted_at") is None
        ]
        return {
            "success": True,
            "files": owner_files,
            "events": list(database.events),
            "jobs": len(owner_jobs),
            "jobStatuses": sorted(str(row.get("status") or "") for row in owner_jobs),
            "activeClaims": sum(1 for row in owner_jobs if row.get("claim_token")),
            "authAttempts": list(database.auth_attempts),
        }

    @app.get("/fixture-storage/{file_id}")
    async def fixture_storage(file_id: str, request: Request):
        auth = await authenticate(request)
        row = await files.get_owned(user_id=auth.user["id"], file_id=normalize_chat_id(file_id))
        return Response(files.bytes_by_id[row["id"]], media_type=row["mime_type"])

    @app.get("/fixture")
    async def fixture_page():
        return FileResponse(ROOT / "tests" / "fixtures" / "conversational-document-delivery.html")

    app.mount("/public", StaticFiles(directory=ROOT / "public"), name="public")
    return app, database, files


async def main() -> None:
    app, _database, _files = create_fixture_app()
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(2048)
    port = listener.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level="warning", access_log=False, lifespan="off"))
    task = asyncio.create_task(server.serve(sockets=[listener]))
    while not server.started and not task.done():
        await asyncio.sleep(0.01)
    if task.done():
        await task
        raise RuntimeError("Fixture server stopped before readiness")
    print(f"{READY_PREFIX}http://127.0.0.1:{port}", flush=True)
    await task


if __name__ == "__main__":
    asyncio.run(main())
