"""Ask Crump 5.7 private book-library endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..auth_service import authenticate_request
from ..library_service import LibraryError, LibraryService
from ..runtime import db, features, files, manuscripts, projects, settings

router = APIRouter(prefix="/api/library", tags=["library"])
library = LibraryService(db, files, manuscripts, projects)


def failure(exc: LibraryError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"success": False, "error": exc.message, "code": exc.code},
    )


@router.get("/books")
async def list_books(request: Request):
    auth = await authenticate_request(request, db, settings)
    items = await library.list_books(user_id=auth.user["id"])
    return {"success": True, "books": items}


@router.post("/books/import")
async def import_book(request: Request):
    auth = await authenticate_request(request, db, settings)
    payload = await request.json()
    if not isinstance(payload, dict):
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": "Invalid import request.", "code": "INVALID_REQUEST"},
        )
    try:
        requested_project_id = str(payload.get("projectId") or "").strip()
        if not requested_project_id:
            count = await projects.count(auth.user["id"])
            limit = features.project_limit(auth.user)
            if limit >= 0 and count >= limit:
                raise LibraryError(
                    f"Your current plan supports up to {limit} active projects. Choose an existing Project for this book or archive one first.",
                    "PROJECT_LIMIT_REACHED",
                    403,
                )

        item = await library.import_book(
            user_id=auth.user["id"],
            source_file_id=str(payload.get("sourceFileId") or ""),
            title=str(payload.get("title") or ""),
            subtitle=str(payload.get("subtitle") or ""),
            author_name=str(payload.get("authorName") or auth.user.get("full_name") or ""),
            project_id=requested_project_id or None,
            front_cover_file_id=str(payload.get("frontCoverFileId") or "") or None,
            back_cover_file_id=str(payload.get("backCoverFileId") or "") or None,
        )
        return {"success": True, "book": item}
    except LibraryError as exc:
        return failure(exc)


@router.patch("/books/{manuscript_id}")
async def update_book(manuscript_id: str, request: Request):
    auth = await authenticate_request(request, db, settings)
    payload = await request.json()
    if not isinstance(payload, dict):
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": "Invalid update request.", "code": "INVALID_REQUEST"},
        )
    try:
        item = await library.update_book(
            user_id=auth.user["id"],
            manuscript_id=manuscript_id,
            changes=payload,
        )
        return {"success": True, "book": item}
    except LibraryError as exc:
        return failure(exc)

@router.get("/books/deleted")
async def list_deleted_books(request: Request):
    auth = await authenticate_request(request, db, settings)
    items = await library.list_books(user_id=auth.user["id"], deleted=True)
    return {"success": True, "books": items}


@router.post("/books/{manuscript_id}/trash")
async def trash_book(manuscript_id: str, request: Request):
    auth = await authenticate_request(request, db, settings)
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    try:
        item = await library.trash_book(
            user_id=auth.user["id"],
            manuscript_id=manuscript_id,
            delete_source=payload.get("deleteSource") is True,
        )
        return {"success": True, "book": item, "sourceFileKept": bool(item.get("sourceFileKept"))}
    except LibraryError as exc:
        return failure(exc)


@router.post("/books/{manuscript_id}/restore")
async def restore_book(manuscript_id: str, request: Request):
    auth = await authenticate_request(request, db, settings)
    try:
        item = await library.restore_book(user_id=auth.user["id"], manuscript_id=manuscript_id)
        return {"success": True, "book": item}
    except LibraryError as exc:
        return failure(exc)


@router.delete("/books/{manuscript_id}")
async def delete_book_permanently(manuscript_id: str, request: Request):
    auth = await authenticate_request(request, db, settings)
    try:
        result = await library.delete_book_permanently(
            user_id=auth.user["id"],
            manuscript_id=manuscript_id,
        )
        return {"success": True, **result}
    except LibraryError as exc:
        return failure(exc)
