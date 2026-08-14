"""Cost-guarded asynchronous media generation endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..auth_service import authenticate_request
from ..db import eq
from ..feature_service import FeatureAccessError
from ..project_service import ProjectNotFoundError
from ..runtime import db, features, projects, settings, video
from ..video_service import VideoServiceError

router = APIRouter(prefix="/api/media", tags=["media"])


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


@router.post("/video")
async def create_video(request: Request):
    auth = await authenticate_request(request, db, settings)
    payload = await request.json()
    if not isinstance(payload, dict):
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": "Invalid video request.", "code": "INVALID_VIDEO_REQUEST"},
        )
    resolution = str(payload.get("resolution") or "720p").lower()
    feature_code = "video_hd" if resolution == "1080p" else "video"
    idempotency_key = " ".join(
        str(request.headers.get("X-Idempotency-Key") or payload.get("idempotencyKey") or "").split()
    ).strip()[:160] or None

    # Retry safety comes before billing. A browser retry with the same key must
    # return the original job without consuming another included use or credit.
    if idempotency_key:
        existing = await db.select_one(
            "media_jobs",
            filters={
                "user_id": eq(auth.user["id"]),
                "idempotency_key": eq(idempotency_key),
            },
        )
        if existing:
            return {
                "success": True,
                "job": await video.public_job(user_id=auth.user["id"], row=existing),
                "idempotentReplay": True,
            }

    try:
        receipt = await features.consume(
            auth.user,
            feature_code,
            {"route": "media_video", "resolution": resolution},
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
            aspect_ratio=str(payload.get("aspectRatio") or "16:9"),
            resolution=resolution,
            project_id=project_id,
            idempotency_key=idempotency_key,
            charge_receipt=receipt,
        )
        return {"success": True, "job": await video.public_job(user_id=auth.user["id"], row=row)}
    except VideoServiceError as exc:
        await features.refund(auth.user["id"], receipt)
        return _video_error(exc)


@router.get("/video/{job_id}")
async def video_status(job_id: str, request: Request):
    auth = await authenticate_request(request, db, settings)
    try:
        row = await video.poll(user_id=auth.user["id"], job_id=job_id)
        if row.get("status") == "failed" and not row.get("billing_refunded"):
            await features.refund(auth.user["id"], row.get("billing_receipt") or {})
            updated = await db.update(
                "media_jobs",
                {"billing_refunded": True},
                filters={"id": eq(row["id"]), "user_id": eq(auth.user["id"])},
            )
            if updated:
                row = updated[0]
        if row.get("status") == "ready" and row.get("project_id") and row.get("file_id"):
            try:
                await projects.attach_file(
                    user_id=auth.user["id"],
                    project_id=str(row["project_id"]),
                    file_id=str(row["file_id"]),
                    role="generated_video",
                )
            except Exception:
                pass
        return {"success": True, "job": await video.public_job(user_id=auth.user["id"], row=row)}
    except VideoServiceError as exc:
        return _video_error(exc)
