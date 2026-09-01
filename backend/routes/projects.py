"""Authenticated Project workspace endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..auth_service import authenticate_request
from ..db import DatabaseError, eq
from ..file_service import FileServiceError
from ..product_analytics import record_product_event
from ..project_service import ProjectChatNotFoundError, ProjectNotFoundError
from ..runtime import db, features, files, projects, settings
from ..usage_service import tier_name

router = APIRouter(prefix="/api/projects", tags=["projects"])


def _error(message: str, code: str, status: int) -> JSONResponse:
    return JSONResponse(status_code=status, content={"success": False, "error": message, "code": code})


def _projects_unavailable() -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={
            "success": False,
            "error": "Projects are temporarily unavailable. Try again.",
            "code": "PROJECTS_UNAVAILABLE",
            "shouldRetry": True,
        },
    )


@router.get("")
async def list_projects(request: Request):
    auth = await authenticate_request(request, db, settings)
    items = await projects.list(auth.user["id"])
    return {
        "success": True,
        "projects": items,
        "limit": features.project_limit(auth.user),
    }


@router.post("")
async def create_project(request: Request):
    auth = await authenticate_request(request, db, settings)
    payload = await request.json()
    if not isinstance(payload, dict):
        return _error("Invalid project request.", "INVALID_PROJECT_REQUEST", 400)
    chat_id = str(payload.get("chatId") or "").strip()
    existing = None
    count = await projects.count(auth.user["id"])
    limit = features.project_limit(auth.user)
    if limit >= 0 and count >= limit:
        if chat_id:
            try:
                existing = await projects.find_for_chat(
                    user_id=auth.user["id"],
                    chat_id=chat_id,
                )
            except ProjectChatNotFoundError:
                existing = None
        if not existing:
            return _error(
                f"Your current plan supports up to {limit} active projects.",
                "PROJECT_LIMIT_REACHED",
                403,
            )
    try:
        common = {
            "user_id": auth.user["id"],
            "name": str(payload.get("name") or ""),
            "description": str(payload.get("description") or ""),
            "instructions": str(payload.get("instructions") or ""),
        }
        if chat_id:
            item = existing or await projects.create_from_chat(chat_id=chat_id, **common)
            await record_product_event(
                db,
                user_id=auth.user["id"],
                event_name="AhaReached",
                event_key="first-durable-project",
                request=request,
                plan=tier_name(auth.user),
                artifact_type="project",
            )
        else:
            item = await projects.create(**common)
        return {
            "success": True,
            "project": item,
            "limit": limit,
            "conversationSaved": bool(chat_id),
        }
    except ProjectChatNotFoundError as exc:
        return _error(str(exc), "PROJECT_CHAT_NOT_READY", 409)
    except ValueError as exc:
        return _error(str(exc), "INVALID_PROJECT", 400)


@router.post("/{project_id}/chats")
async def attach_project_chat(project_id: str, request: Request):
    auth = await authenticate_request(request, db, settings)
    payload = await request.json()
    if not isinstance(payload, dict):
        return _error("Invalid conversation request.", "INVALID_PROJECT_CHAT", 400)
    chat_id = str(payload.get("chatId") or "").strip()
    if not chat_id:
        return _error("Choose a conversation first.", "INVALID_PROJECT_CHAT", 400)
    try:
        item = await projects.attach_owned_chat(
            user_id=auth.user["id"],
            project_id=project_id,
            chat_id=chat_id,
        )
        await record_product_event(
            db,
            user_id=auth.user["id"],
            event_name="AhaReached",
            event_key="first-durable-project",
            request=request,
            plan=tier_name(auth.user),
            artifact_type="project",
        )
        return {"success": True, "project": item, "conversationSaved": True}
    except ProjectNotFoundError as exc:
        return _error(str(exc), "PROJECT_NOT_FOUND", 404)
    except ProjectChatNotFoundError as exc:
        return _error(str(exc), "PROJECT_CHAT_NOT_READY", 409)


@router.get("/for-chat/{chat_id}")
async def project_for_chat(chat_id: str, request: Request):
    auth = await authenticate_request(request, db, settings)
    try:
        item = await projects.find_for_chat(
            user_id=auth.user["id"],
            chat_id=chat_id,
        )
    except ProjectChatNotFoundError:
        item = None
    project = None
    if item:
        project = {
            "id": str(item.get("id") or ""),
            "name": str(item.get("name") or "Project"),
        }
    return {"success": True, "project": project}


@router.get("/target/{project_id}")
async def project_target(project_id: str, request: Request):
    auth = await authenticate_request(request, db, settings)
    try:
        item = await projects.get(auth.user["id"], project_id)
        project = {
            "id": str(item.get("id") or ""),
            "name": str(item.get("name") or "Project"),
        }
        return {"success": True, "project": project}
    except ProjectNotFoundError as exc:
        return _error(str(exc), "PROJECT_NOT_FOUND", 404)


@router.get("/{project_id}/chats")
async def list_project_chats(project_id: str, request: Request):
    auth = await authenticate_request(request, db, settings)
    try:
        conversations = await projects.list_chats(
            user_id=auth.user["id"],
            project_id=project_id,
        )
        return {"success": True, "conversations": conversations}
    except ProjectNotFoundError as exc:
        return _error(str(exc), "PROJECT_NOT_FOUND", 404)


@router.get("/{project_id}")
async def get_project(project_id: str, request: Request):
    auth = await authenticate_request(request, db, settings)
    try:
        item = await projects.get(auth.user["id"], project_id)
        context = await projects.hydrate_context(auth.user["id"], project_id)
        return {"success": True, "project": item, "context": context}
    except ProjectNotFoundError as exc:
        return _error(str(exc), "PROJECT_NOT_FOUND", 404)


@router.patch("/{project_id}")
async def update_project(project_id: str, request: Request):
    auth = await authenticate_request(request, db, settings)
    payload = await request.json()
    try:
        item = await projects.update(
            user_id=auth.user["id"],
            project_id=project_id,
            changes=payload if isinstance(payload, dict) else {},
        )
        return {"success": True, "project": item}
    except ProjectNotFoundError as exc:
        return _error(str(exc), "PROJECT_NOT_FOUND", 404)
    except ValueError as exc:
        return _error(str(exc), "INVALID_PROJECT", 400)


@router.delete("/{project_id}")
async def archive_project(project_id: str, request: Request):
    auth = await authenticate_request(request, db, settings)
    try:
        await projects.archive(auth.user["id"], project_id)
        return {"success": True}
    except ProjectNotFoundError as exc:
        return _error(str(exc), "PROJECT_NOT_FOUND", 404)


@router.post("/{project_id}/context")
async def add_context(project_id: str, request: Request):
    auth = await authenticate_request(request, db, settings)
    payload = await request.json()
    if not isinstance(payload, dict):
        return _error("Invalid context request.", "INVALID_CONTEXT", 400)
    try:
        item = await projects.add_context(
            user_id=auth.user["id"],
            project_id=project_id,
            kind=str(payload.get("kind") or "note"),
            label=str(payload.get("label") or ""),
            content=str(payload.get("content") or ""),
        )
        return {"success": True, "context": item}
    except ProjectNotFoundError as exc:
        return _error(str(exc), "PROJECT_NOT_FOUND", 404)
    except ValueError as exc:
        return _error(str(exc), "INVALID_CONTEXT", 400)


@router.get("/{project_id}/files")
async def project_files(project_id: str, request: Request):
    auth = await authenticate_request(request, db, settings)
    try:
        project = await projects.get(auth.user["id"], project_id)
        mappings = await db.select(
            "project_files",
            filters={"project_id": eq(project["id"]), "user_id": eq(auth.user["id"])},
            order="created_at.desc",
            limit=200,
        )
        output = []
        for mapping in mappings:
            try:
                row = await files.get_owned(
                    user_id=auth.user["id"],
                    file_id=str(mapping["file_id"]),
                )
            except FileServiceError as exc:
                if exc.status_code == 404:
                    # A stale mapping to a deleted/private file is absent. A
                    # database outage must never be converted into this case.
                    continue
                return _error(exc.message, exc.code, exc.status_code)
            public = files.public_file(row)
            public["projectRole"] = mapping.get("role")
            output.append(public)
        return {"success": True, "files": output}
    except ProjectNotFoundError as exc:
        return _error(str(exc), "PROJECT_NOT_FOUND", 404)
    except DatabaseError:
        return _projects_unavailable()


@router.post("/{project_id}/files")
async def attach_project_file(project_id: str, request: Request):
    auth = await authenticate_request(request, db, settings)
    payload = await request.json()
    if not isinstance(payload, dict):
        return _error("Invalid file request.", "INVALID_PROJECT_FILE", 400)
    file_id = str(payload.get("fileId") or "").strip()
    role = str(payload.get("role") or "reference").strip().lower()
    allowed_roles = {
        "reference", "source", "canon", "inspiration", "asset",
        "conversation_asset", "generated_image", "generated_document",
        "generated_video", "manuscript_export",
    }
    if role not in allowed_roles:
        role = "reference"
    if not file_id:
        return _error("Choose a file first.", "INVALID_PROJECT_FILE", 400)
    try:
        await projects.get(auth.user["id"], project_id)
        row = await files.get_owned(user_id=auth.user["id"], file_id=file_id)
        await projects.attach_file(
            user_id=auth.user["id"],
            project_id=project_id,
            file_id=str(row["id"]),
            role=role,
        )
        public = files.public_file(row)
        public["projectRole"] = role
        return {"success": True, "file": public}
    except ProjectNotFoundError as exc:
        return _error(str(exc), "PROJECT_NOT_FOUND", 404)
    except FileServiceError as exc:
        return _error(exc.message, exc.code, exc.status_code)
    except DatabaseError:
        return _projects_unavailable()
    except Exception:
        return _error("Could not attach that file to the Project.", "PROJECT_FILE_FAILED", 500)
