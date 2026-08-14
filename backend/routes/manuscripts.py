"""Project manuscript editing, AI drafting, and KDP export endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..auth_service import authenticate_request
from ..feature_service import FeatureAccessError
from ..manuscript_service import ManuscriptError
from ..project_service import ProjectNotFoundError
from ..runtime import db, features, files, manuscripts, projects, settings

router = APIRouter(tags=["manuscripts"])


def _feature_error(exc: FeatureAccessError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": exc.message,
            "code": exc.code,
            "upgradeRequired": exc.code == "SUBSCRIPTION_REQUIRED",
            "requiredTier": exc.required_tier,
            "creditsRequired": exc.credit_cost,
            "creditBalance": exc.credit_balance,
        },
    )


def _manuscript_error(exc: ManuscriptError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"success": False, "error": exc.message, "code": exc.code},
    )


@router.get("/api/projects/{project_id}/manuscripts")
async def list_manuscripts(project_id: str, request: Request):
    auth = await authenticate_request(request, db, settings)
    try:
        items = await manuscripts.list(user_id=auth.user["id"], project_id=project_id)
        return {"success": True, "manuscripts": items}
    except ProjectNotFoundError:
        return JSONResponse(
            status_code=404,
            content={"success": False, "error": "Project not found.", "code": "PROJECT_NOT_FOUND"},
        )


@router.post("/api/projects/{project_id}/manuscripts")
async def create_manuscript(project_id: str, request: Request):
    auth = await authenticate_request(request, db, settings)
    payload = await request.json()
    if not isinstance(payload, dict):
        return JSONResponse(status_code=400, content={"success": False, "error": "Invalid request."})
    try:
        item = await manuscripts.create(
            user_id=auth.user["id"],
            project_id=project_id,
            title=str(payload.get("title") or ""),
            subtitle=str(payload.get("subtitle") or ""),
            author_name=str(payload.get("authorName") or auth.user.get("full_name") or ""),
            trim_code=str(payload.get("trimCode") or "6x9"),
            bleed=bool(payload.get("bleed")),
        )
        return {"success": True, "manuscript": item}
    except ManuscriptError as exc:
        return _manuscript_error(exc)
    except ProjectNotFoundError:
        return JSONResponse(
            status_code=404,
            content={"success": False, "error": "Project not found.", "code": "PROJECT_NOT_FOUND"},
        )


@router.get("/api/manuscripts/{manuscript_id}")
async def get_manuscript(manuscript_id: str, request: Request):
    auth = await authenticate_request(request, db, settings)
    try:
        item = await manuscripts.get(user_id=auth.user["id"], manuscript_id=manuscript_id)
        sections = await manuscripts.list_sections(user_id=auth.user["id"], manuscript_id=manuscript_id)
        return {"success": True, "manuscript": item, "sections": sections}
    except ManuscriptError as exc:
        return _manuscript_error(exc)


@router.post("/api/manuscripts/{manuscript_id}/sections")
async def add_section(manuscript_id: str, request: Request):
    auth = await authenticate_request(request, db, settings)
    payload = await request.json()
    if not isinstance(payload, dict):
        return JSONResponse(status_code=400, content={"success": False, "error": "Invalid request."})
    try:
        item = await manuscripts.add_section(
            user_id=auth.user["id"],
            manuscript_id=manuscript_id,
            title=str(payload.get("title") or ""),
            section_type=str(payload.get("sectionType") or "chapter"),
            content=str(payload.get("content") or ""),
        )
        return {"success": True, "section": item}
    except ManuscriptError as exc:
        return _manuscript_error(exc)


@router.patch("/api/manuscripts/{manuscript_id}/sections/{section_id}")
async def update_section(manuscript_id: str, section_id: str, request: Request):
    auth = await authenticate_request(request, db, settings)
    payload = await request.json()
    try:
        item = await manuscripts.update_section(
            user_id=auth.user["id"],
            manuscript_id=manuscript_id,
            section_id=section_id,
            changes=payload if isinstance(payload, dict) else {},
        )
        return {"success": True, "section": item}
    except ManuscriptError as exc:
        return _manuscript_error(exc)


@router.post("/api/manuscripts/{manuscript_id}/sections/{section_id}/draft")
async def draft_section(manuscript_id: str, section_id: str, request: Request):
    auth = await authenticate_request(request, db, settings)
    if not settings.manuscript_generation_enabled or not settings.anthropic_api_key:
        return JSONResponse(
            status_code=503,
            content={
                "success": False,
                "error": "Manuscript drafting is not configured yet.",
                "code": "MANUSCRIPT_NOT_CONFIGURED",
            },
        )
    payload = await request.json()
    try:
        receipt = await features.consume(
            auth.user,
            "manuscript_draft",
            {"manuscriptId": manuscript_id, "sectionId": section_id},
        )
    except FeatureAccessError as exc:
        return _feature_error(exc)
    try:
        item = await manuscripts.draft_section(
            user=auth.user,
            manuscript_id=manuscript_id,
            section_id=section_id,
            instruction=str(payload.get("instruction") or "") if isinstance(payload, dict) else "",
        )
        return {"success": True, "section": item, "featureUsage": receipt}
    except ManuscriptError as exc:
        await features.refund(auth.user["id"], receipt)
        return _manuscript_error(exc)
    except Exception:
        await features.refund(auth.user["id"], receipt)
        return JSONResponse(
            status_code=502,
            content={"success": False, "error": "Crump could not draft that section.", "code": "DRAFT_FAILED"},
        )


@router.post("/api/manuscripts/{manuscript_id}/export")
async def export_manuscript(manuscript_id: str, request: Request):
    auth = await authenticate_request(request, db, settings)
    if not settings.manuscript_generation_enabled:
        return JSONResponse(
            status_code=503,
            content={
                "success": False,
                "error": "Manuscript exports are temporarily disabled.",
                "code": "MANUSCRIPT_NOT_CONFIGURED",
            },
        )
    payload = await request.json()
    try:
        receipt = await features.consume(auth.user, "kdp_export", {"manuscriptId": manuscript_id})
    except FeatureAccessError as exc:
        return _feature_error(exc)
    try:
        data, filename, mime, metadata = await manuscripts.export(
            user_id=auth.user["id"],
            manuscript_id=manuscript_id,
            export_format=str(payload.get("format") or "docx") if isinstance(payload, dict) else "docx",
        )
        manuscript = await manuscripts.get(user_id=auth.user["id"], manuscript_id=manuscript_id)
        row = await files.store_bytes(
            user_id=auth.user["id"],
            data=data,
            filename=filename,
            mime_type=mime,
            kind="manuscript_export",
            metadata=metadata,
        )
        await projects.attach_file(
            user_id=auth.user["id"],
            project_id=str(manuscript["project_id"]),
            file_id=str(row["id"]),
            role="manuscript_export",
        )
        return {
            "success": True,
            "file": files.public_file(row),
            "kdp": metadata,
            "featureUsage": receipt,
        }
    except ManuscriptError as exc:
        await features.refund(auth.user["id"], receipt)
        return _manuscript_error(exc)
    except Exception:
        await features.refund(auth.user["id"], receipt)
        return JSONResponse(
            status_code=503,
            content={"success": False, "error": "The manuscript export could not be created.", "code": "EXPORT_FAILED"},
        )
