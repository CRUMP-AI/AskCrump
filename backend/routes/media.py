"""Cost-guarded asynchronous media generation endpoints."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..auth_service import authenticate_request
from ..db import eq
from ..feature_service import FeatureAccessError
from ..project_service import ProjectNotFoundError
from ..runtime import db, features, projects, settings, video
from ..usage_service import has_internal_access
from ..video_service import VideoServiceError

router = APIRouter(prefix="/api/media", tags=["media"])
logger = logging.getLogger("askcrump.media")


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


def _video_error(exc: VideoServiceError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": exc.message,
            "code": exc.code,
            "shouldRetry": exc.retryable,
        },
    )


def _idempotency_key(request: Request, payload: dict) -> str | None:
    return " ".join(
        str(request.headers.get("X-Idempotency-Key") or payload.get("idempotencyKey") or "").split()
    ).strip()[:160] or None


async def _existing_job(user_id: str, key: str | None):
    if not key:
        return None
    return await db.select_one(
        "media_jobs",
        filters={"user_id": eq(user_id), "idempotency_key": eq(key)},
    )


async def _attach_ready_video_to_project(*, user_id: str, row: dict) -> dict | None:
    if row.get("status") != "ready" or not row.get("project_id") or not row.get("file_id"):
        return None

    project_id = str(row["project_id"])
    receipt = {
        "projectId": project_id,
        "role": "generated_video",
        "shouldRetry": False,
    }
    try:
        await projects.attach_file(
            user_id=user_id,
            project_id=project_id,
            file_id=str(row["file_id"]),
            role="generated_video",
        )
        return {**receipt, "status": "attached"}
    except ProjectNotFoundError:
        logger.info("Generated video Project attachment skipped because the Project is unavailable.")
        return {
            **receipt,
            "status": "missing",
            "message": "The video is safe in Files, but its original Project is no longer available.",
        }
    except Exception:
        logger.warning("Generated video Project attachment needs a retry.")
        return {
            **receipt,
            "status": "failed",
            "shouldRetry": True,
            "message": "The video is safe in Files, but its Project link needs a retry.",
        }


@router.post("/video")
async def create_video(request: Request):
    auth = await authenticate_request(request, db, settings)
    payload = await request.json()
    if not isinstance(payload, dict):
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": "Invalid video request.", "code": "INVALID_VIDEO_REQUEST"},
        )

    try:
        engine, resolution, duration = video.normalize_request(
            engine=payload.get("engine") or "quick",
            resolution=payload.get("resolution") or "720p",
            duration_seconds=payload.get("durationSeconds") or 0,
        )
        feature_code = video.feature_code(engine=engine, resolution=resolution, duration_seconds=duration)
    except VideoServiceError as exc:
        return _video_error(exc)

    idempotency_key = _idempotency_key(request, payload)
    existing = await _existing_job(auth.user["id"], idempotency_key)
    if existing:
        return {
            "success": True,
            "job": await video.public_job(user_id=auth.user["id"], row=existing),
            "idempotentReplay": True,
        }

    estimated_cost = video.provider_cost_cents(
        engine=engine,
        resolution=resolution,
        duration_seconds=duration,
    )
    try:
        await video.guard_provider_budget(
            user_id=auth.user["id"],
            provider=video.provider_for_engine(engine),
            estimated_cost_cents=estimated_cost,
            bypass_user_limit=has_internal_access(auth.user),
        )
    except VideoServiceError as exc:
        return _video_error(exc)

    try:
        receipt = await features.consume(
            auth.user,
            feature_code,
            {
                "route": "media_video",
                "engine": engine,
                "resolution": resolution,
                "durationSeconds": duration,
            },
        )
    except FeatureAccessError as exc:
        return _feature_error(exc)

    project_id = str(payload.get("projectId") or "").strip() or None
    if project_id:
        try:
            await projects.get(auth.user["id"], project_id)
        except ProjectNotFoundError:
            await features.refund(auth.user["id"], receipt)
            return JSONResponse(
                status_code=404,
                content={"success": False, "error": "Project not found.", "code": "PROJECT_NOT_FOUND"},
            )

    try:
        row = await video.start(
            user_id=auth.user["id"],
            prompt=str(payload.get("prompt") or ""),
            engine=engine,
            aspect_ratio=str(payload.get("aspectRatio") or "16:9"),
            resolution=resolution,
            duration_seconds=duration,
            project_id=project_id,
            idempotency_key=idempotency_key,
            charge_receipt=receipt,
        )
        return {"success": True, "job": await video.public_job(user_id=auth.user["id"], row=row)}
    except VideoServiceError as exc:
        if exc.refund_eligible:
            await features.refund(auth.user["id"], receipt)
        return _video_error(exc)


@router.post("/video/{job_id}/continue")
async def continue_video(job_id: str, request: Request):
    auth = await authenticate_request(request, db, settings)
    payload = await request.json()
    if not isinstance(payload, dict):
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": "Invalid continuation request.", "code": "INVALID_VIDEO_REQUEST"},
        )
    idempotency_key = _idempotency_key(request, payload)
    existing = await _existing_job(auth.user["id"], idempotency_key)
    if existing:
        return {
            "success": True,
            "job": await video.public_job(user_id=auth.user["id"], row=existing),
            "idempotentReplay": True,
        }

    try:
        await video.validate_continuation_parent(user_id=auth.user["id"], job_id=job_id)
    except VideoServiceError as exc:
        return _video_error(exc)

    estimated_cost = video.provider_cost_cents(
        engine=video.EXTENDABLE,
        resolution="720p",
        duration_seconds=8,
        operation_type="extend",
    )
    try:
        await video.guard_provider_budget(
            user_id=auth.user["id"],
            provider="gemini",
            estimated_cost_cents=estimated_cost,
            bypass_user_limit=has_internal_access(auth.user),
        )
    except VideoServiceError as exc:
        return _video_error(exc)

    try:
        receipt = await features.consume(
            auth.user,
            "video_continue",
            {"route": "media_video_continue", "parentJobId": job_id},
        )
    except FeatureAccessError as exc:
        return _feature_error(exc)

    try:
        row = await video.continue_video(
            user_id=auth.user["id"],
            parent_job_id=job_id,
            prompt=str(payload.get("prompt") or ""),
            idempotency_key=idempotency_key,
            charge_receipt=receipt,
        )
        return {"success": True, "job": await video.public_job(user_id=auth.user["id"], row=row)}
    except VideoServiceError as exc:
        if exc.refund_eligible:
            await features.refund(auth.user["id"], receipt)
        return _video_error(exc)


@router.get("/video/{job_id}")
async def video_status(job_id: str, request: Request):
    auth = await authenticate_request(request, db, settings)
    try:
        row = await video.poll(user_id=auth.user["id"], job_id=job_id)
        if (
            row.get("status") == "failed"
            and not row.get("billing_refunded")
            and video.refund_eligible(row)
        ):
            await features.refund(auth.user["id"], row.get("billing_receipt") or {})
            updated = await db.update(
                "media_jobs",
                {"billing_refunded": True},
                filters={"id": eq(row["id"]), "user_id": eq(auth.user["id"])},
            )
            if updated:
                row = updated[0]
        project_attachment = await _attach_ready_video_to_project(user_id=auth.user["id"], row=row)
        public_job = await video.public_job(user_id=auth.user["id"], row=row)
        if project_attachment:
            public_job["projectAttachment"] = project_attachment
        return {"success": True, "job": public_job}
    except VideoServiceError as exc:
        return _video_error(exc)
