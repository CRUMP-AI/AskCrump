"""Project manuscript editing, AI drafting, and KDP export endpoints."""
from __future__ import annotations

import hmac

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


async def _public_run(user_id: str, row: dict | None) -> dict | None:
    payload = manuscripts.public_run(row)
    if not payload or not row or not row.get("output_file_id"):
        return payload
    try:
        file_row = await files.get_owned(user_id=user_id, file_id=str(row["output_file_id"]))
        payload["outputFile"] = files.public_file(file_row)
    except Exception:
        pass
    return payload


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
            metadata={
                "premise": str(payload.get("premise") or "").strip()[:1200],
                "targetWords": payload.get("targetWords") or 80000,
            },
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
        run = await manuscripts.latest_run(user_id=auth.user["id"], manuscript_id=manuscript_id)
        return {
            "success": True,
            "manuscript": item,
            "sections": sections,
            "progress": manuscripts.progress(item, sections),
            "run": await _public_run(auth.user["id"], run),
        }
    except ManuscriptError as exc:
        return _manuscript_error(exc)


@router.post("/api/manuscripts/{manuscript_id}/runs")
async def start_manuscript_run(manuscript_id: str, request: Request):
    auth = await authenticate_request(request, db, settings)
    if not settings.manuscript_generation_enabled or not settings.anthropic_api_key:
        return JSONResponse(
            status_code=503,
            content={
                "success": False,
                "error": "Full-manuscript generation is not configured yet.",
                "code": "MANUSCRIPT_NOT_CONFIGURED",
            },
        )
    payload = await request.json()
    payload = payload if isinstance(payload, dict) else {}
    try:
        existing = await manuscripts.latest_run(user_id=auth.user["id"], manuscript_id=manuscript_id)
        if existing and existing.get("status") in {"queued", "running", "paused", "awaiting_credits"}:
            return {
                "success": True,
                "run": await _public_run(auth.user["id"], existing),
                "idempotentReplay": True,
            }
        sections = await manuscripts.list_sections(user_id=auth.user["id"], manuscript_id=manuscript_id)
        receipt = None
        if not sections:
            receipt = await features.consume(
                auth.user,
                "manuscript_blueprint",
                {"manuscriptId": manuscript_id, "mode": "durable_run"},
            )
        run = await manuscripts.queue_run(
            user=auth.user,
            manuscript_id=manuscript_id,
            brief=str(payload.get("brief") or ""),
            target_words=payload.get("targetWords"),
            chapter_count=payload.get("chapterCount"),
            preferred_format=str(payload.get("format") or "docx"),
            mode=str(payload.get("mode") or "autopilot"),
            blueprint_receipt=receipt,
        )
        return {"success": True, "run": await _public_run(auth.user["id"], run)}
    except FeatureAccessError as exc:
        return _feature_error(exc)
    except ManuscriptError as exc:
        if "receipt" in locals() and receipt:
            await features.refund(auth.user["id"], receipt)
        return _manuscript_error(exc)
    except Exception:
        if "receipt" in locals() and receipt:
            await features.refund(auth.user["id"], receipt)
        return JSONResponse(
            status_code=503,
            content={
                "success": False,
                "error": "Crump could not queue the full manuscript yet.",
                "code": "MANUSCRIPT_RUN_QUEUE_FAILED",
            },
        )


@router.get("/api/manuscripts/{manuscript_id}/run")
async def manuscript_run_status(manuscript_id: str, request: Request):
    auth = await authenticate_request(request, db, settings)
    try:
        row = await manuscripts.latest_run(user_id=auth.user["id"], manuscript_id=manuscript_id)
        return {"success": True, "run": await _public_run(auth.user["id"], row)}
    except ManuscriptError as exc:
        return _manuscript_error(exc)


@router.post("/api/manuscript-runs/{run_id}/pause")
async def pause_manuscript_run(run_id: str, request: Request):
    auth = await authenticate_request(request, db, settings)
    try:
        row = await manuscripts.pause_run(user_id=auth.user["id"], run_id=run_id)
        return {"success": True, "run": await _public_run(auth.user["id"], row)}
    except ManuscriptError as exc:
        return _manuscript_error(exc)


@router.post("/api/manuscript-runs/{run_id}/resume")
async def resume_manuscript_run(run_id: str, request: Request):
    auth = await authenticate_request(request, db, settings)
    try:
        row = await manuscripts.resume_run(user_id=auth.user["id"], run_id=run_id)
        return {"success": True, "run": await _public_run(auth.user["id"], row)}
    except ManuscriptError as exc:
        return _manuscript_error(exc)


@router.post("/api/manuscript-runs/{run_id}/cancel")
async def cancel_manuscript_run(run_id: str, request: Request):
    auth = await authenticate_request(request, db, settings)
    try:
        row = await manuscripts.cancel_run(user_id=auth.user["id"], run_id=run_id)
        return {"success": True, "run": await _public_run(auth.user["id"], row)}
    except ManuscriptError as exc:
        return _manuscript_error(exc)


@router.get("/api/cron/manuscripts")
async def manuscript_cron(request: Request):
    expected = settings.cron_secret
    authorization = request.headers.get("authorization", "")
    if not expected or not hmac.compare_digest(authorization, f"Bearer {expected}"):
        return JSONResponse(status_code=401, content={"success": False, "error": "Unauthorized."})
    summary = await manuscripts.process_next_run()
    return {"success": True, **summary}


@router.post("/api/manuscripts/{manuscript_id}/blueprint")
async def blueprint_manuscript(manuscript_id: str, request: Request):
    auth = await authenticate_request(request, db, settings)
    if not settings.manuscript_generation_enabled or not settings.anthropic_api_key:
        return JSONResponse(
            status_code=503,
            content={
                "success": False,
                "error": "Manuscript planning is not configured yet.",
                "code": "MANUSCRIPT_NOT_CONFIGURED",
            },
        )
    payload = await request.json()
    payload = payload if isinstance(payload, dict) else {}
    try:
        receipt = await features.consume(
            auth.user,
            "manuscript_blueprint",
            {"manuscriptId": manuscript_id},
        )
    except FeatureAccessError as exc:
        return _feature_error(exc)
    try:
        result = await manuscripts.apply_blueprint(
            user=auth.user,
            manuscript_id=manuscript_id,
            brief=str(payload.get("brief") or payload.get("premise") or ""),
            target_words=payload.get("targetWords"),
            chapter_count=payload.get("chapterCount"),
            replace_outlines=bool(payload.get("replaceOutlines")),
        )
        item = await manuscripts.get(user_id=auth.user["id"], manuscript_id=manuscript_id)
        return {
            "success": True,
            **result,
            "manuscript": item,
            "progress": manuscripts.progress(item, result["sections"]),
            "featureUsage": receipt,
        }
    except ManuscriptError as exc:
        await features.refund(auth.user["id"], receipt)
        return _manuscript_error(exc)
    except Exception:
        await features.refund(auth.user["id"], receipt)
        return JSONResponse(
            status_code=502,
            content={
                "success": False,
                "error": "Crump could not build that manuscript plan.",
                "code": "BLUEPRINT_FAILED",
            },
        )


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
        manuscript = await manuscripts.get(user_id=auth.user["id"], manuscript_id=manuscript_id)
        sections = await manuscripts.list_sections(user_id=auth.user["id"], manuscript_id=manuscript_id)
        return {
            "success": True,
            "section": item,
            "progress": manuscripts.progress(manuscript, sections),
            "featureUsage": receipt,
        }
    except ManuscriptError as exc:
        await features.refund(auth.user["id"], receipt)
        return _manuscript_error(exc)
    except Exception:
        await features.refund(auth.user["id"], receipt)
        return JSONResponse(
            status_code=502,
            content={"success": False, "error": "Crump could not draft that section.", "code": "DRAFT_FAILED"},
        )


@router.post("/api/manuscripts/{manuscript_id}/draft-next")
async def draft_next_section(manuscript_id: str, request: Request):
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
    payload = payload if isinstance(payload, dict) else {}
    try:
        receipt = await features.consume(
            auth.user,
            "manuscript_draft",
            {"manuscriptId": manuscript_id, "mode": "next"},
        )
    except FeatureAccessError as exc:
        return _feature_error(exc)
    try:
        item = await manuscripts.draft_next(
            user=auth.user,
            manuscript_id=manuscript_id,
            instruction=str(payload.get("instruction") or ""),
        )
        manuscript = await manuscripts.get(user_id=auth.user["id"], manuscript_id=manuscript_id)
        sections = await manuscripts.list_sections(user_id=auth.user["id"], manuscript_id=manuscript_id)
        return {
            "success": True,
            "section": item,
            "progress": manuscripts.progress(manuscript, sections),
            "featureUsage": receipt,
        }
    except ManuscriptError as exc:
        await features.refund(auth.user["id"], receipt)
        return _manuscript_error(exc)
    except Exception:
        await features.refund(auth.user["id"], receipt)
        return JSONResponse(
            status_code=502,
            content={
                "success": False,
                "error": "Crump could not draft the next section.",
                "code": "DRAFT_FAILED",
            },
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
