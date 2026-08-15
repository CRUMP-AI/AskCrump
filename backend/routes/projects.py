"""Authenticated Project workspace endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..auth_service import authenticate_request
from ..db import eq
from ..project_service import ProjectNotFoundError
from ..runtime import db, features, files, projects, settings

router = APIRouter(prefix="/api/projects", tags=["projects"])


def _error(message: str, code: str, status: int) -> JSONResponse:
    return JSONResponse(status_code=status, content={"success": False, "error": message, "code": code})


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
    count = await projects.count(auth.user["id"])
    limit = features.project_limit(auth.user)
    if limit >= 0 and count >= limit:
        return _error(
            f"Your current plan supports up to {limit} active projects.",
            "PROJECT_LIMIT_REACHED",
            403,
        )
    try:
        item = await projects.create(
            user_id=auth.user["id"],
            name=str(payload.get("name") or ""),
            description=str(payload.get("description") or ""),
            instructions=str(payload.get("instructions") or ""),
        )
        return {"success": True, "project": item, "limit": limit}
    except ValueError as exc:
        return _error(str(exc), "INVALID_PROJECT", 400)


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
    except ProjectNotFoundError as exc:
        return _error(str(exc), "PROJECT_NOT_FOUND", 404)
    mappings = await db.select(
        "project_files",
        filters={"project_id": eq(project["id"]), "user_id": eq(auth.user["id"])},
        order="created_at.desc",
        limit=200,
    )
    output = []
    for mapping in mappings:
        try:
            row = await files.get_owned(user_id=auth.user["id"], file_id=str(mapping["file_id"]))
            public = files.public_file(row)
            public["projectRole"] = mapping.get("role")
            output.append(public)
        except Exception:
            continue
    return {"success": True, "files": output}
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
    except Exception:
        return _error("Could not attach that file to the Project.", "PROJECT_FILE_FAILED", 400)
