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
            "creditQuote": exc.quote,
        },
    )


_VIDEO_ERROR_STAGES = frozenset({
    "request",
    "references",
    "budget",
    "generation",
    "continuation_parent",
    "continuation_budget",
    "continuation_generation",
    "status",
})


def _video_error(exc: VideoServiceError, *, stage: str) -> JSONResponse:
    safe_stage = stage if stage in _VIDEO_ERROR_STAGES else "unknown"
    safe_code = (
        exc.code
        if 1 <= len(exc.code) <= 64 and exc.code.isascii() and exc.code.replace("_", "").isalnum()
        else "VIDEO_ERROR"
    )
    log_level = logging.ERROR if exc.status_code >= 500 else logging.WARNING
    reconciliation_pending = exc.code in {
        "VIDEO_START_OUTCOME_UNKNOWN",
        "VIDEO_JOB_TRACKING_FAILED",
        "VIDEO_START_RECONCILIATION_PENDING",
    }
    logger.log(
        log_level,
        "Video request rejected stage=%s status=%s code=%s retryable=%s",
        safe_stage,
        exc.status_code,
        safe_code,
        exc.retryable,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": exc.message,
            "code": exc.code,
            "shouldRetry": exc.retryable,
            "jobId": exc.failed_job_id if reconciliation_pending else None,
            "reconciliationPending": reconciliation_pending,
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


async def _refund_failed_video_charge(
    *,
    user_id: str,
    receipt: dict | None,
    job_id: str | None,
) -> None:
    """Return a failed pre-acceptance charge and reconcile its private job row."""
    await features.refund(user_id, receipt)
    if not job_id:
        return
    try:
        await db.update(
            "media_jobs",
            {"billing_refunded": True},
            filters={"id": eq(job_id), "user_id": eq(user_id)},
        )
    except Exception:
        # The credit refund is idempotent. Leaving the flag false lets the
        # existing status route safely reconcile it again if storage recovers.
        logger.warning("Video refund state update needs a retry.")


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
        return _video_error(
            VideoServiceError("Invalid video request.", "INVALID_VIDEO_REQUEST"),
            stage="request",
        )

    try:
        engine, resolution, duration = video.normalize_request(
            engine=payload.get("engine") or "quick",
            resolution=payload.get("resolution") or "720p",
            duration_seconds=payload.get("durationSeconds") or 0,
        )
        feature_code = video.feature_code(engine=engine, resolution=resolution, duration_seconds=duration)
    except VideoServiceError as exc:
        return _video_error(exc, stage="request")

    idempotency_key = _idempotency_key(request, payload)
    existing = await _existing_job(auth.user["id"], idempotency_key)
    if existing:
        return {
            "success": True,
            "job": await video.public_job(user_id=auth.user["id"], row=existing),
            "idempotentReplay": True,
        }

    try:
        reference_images = await video.prepare_reference_images(
            user_id=auth.user["id"],
            file_ids=payload.get("referenceFileIds"),
            engine=engine,
        )
    except VideoServiceError as exc:
        return _video_error(exc, stage="references")

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
        return _video_error(exc, stage="budget")

    project_id = str(payload.get("projectId") or "").strip() or None
    if project_id:
        try:
            await projects.get(auth.user["id"], project_id)
        except ProjectNotFoundError:
            return JSONResponse(
                status_code=404,
                content={"success": False, "error": "Project not found.", "code": "PROJECT_NOT_FOUND"},
            )

    charge_scope = {
        "route": "media_video",
        "payload": {
            key: value for key, value in payload.items()
            if key != "creditConfirmation"
        },
    }
    charge_metadata = {
        "route": "media_video",
        "engine": engine,
        "resolution": resolution,
        "durationSeconds": duration,
        "referenceImageCount": len(reference_images),
    }
    try:
        authorization = await features.authorize(
            auth.user, {feature_code: 1},
            payload.get("creditConfirmation"), scope=charge_scope,
        )
    except FeatureAccessError as exc:
        return _feature_error(exc)

    # This short database claim precedes the charge. A deletion fence can now
    # reject the request without debiting credits or contacting the provider.
    try:
        claimed_job_id = await video.reserve_provider_claim(
            user_id=auth.user["id"],
            provider=video.provider_for_engine(engine),
            operation_type="generate",
        )
    except VideoServiceError as exc:
        return _video_error(exc, stage="reservation")
    try:
        receipt = await features.consume(
            auth.user,
            feature_code,
            charge_metadata,
            authorization=authorization,
            instance_key=idempotency_key,
            scope=charge_scope,
        )
    except FeatureAccessError as exc:
        try:
            await video.finish_provider_claim(
                user_id=auth.user["id"], job_id=claimed_job_id, outcome="rejected",
            )
        except Exception:
            logger.warning("Uncharged video claim needs expiry cleanup.")
        return _feature_error(exc)

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
            reference_images=reference_images,
            claimed_job_id=claimed_job_id,
        )
        return {"success": True, "job": await video.public_job(user_id=auth.user["id"], row=row)}
    except VideoServiceError as exc:
        if exc.refund_eligible:
            try:
                await video.finish_provider_claim(
                    user_id=auth.user["id"], job_id=claimed_job_id, outcome="rejected",
                )
            except Exception:
                logger.warning("Refundable video claim needs expiry cleanup.")
            await _refund_failed_video_charge(
                user_id=auth.user["id"],
                receipt=receipt,
                job_id=exc.failed_job_id,
            )
        return _video_error(exc, stage="generation")


@router.post("/video/{job_id}/continue")
async def continue_video(job_id: str, request: Request):
    auth = await authenticate_request(request, db, settings)
    payload = await request.json()
    if not isinstance(payload, dict):
        return _video_error(
            VideoServiceError("Invalid continuation request.", "INVALID_VIDEO_REQUEST"),
            stage="request",
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
        return _video_error(exc, stage="continuation_parent")

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
        return _video_error(exc, stage="continuation_budget")

    charge_scope = {
        "route": "media_video_continue",
        "parentJobId": job_id,
        "payload": {
            key: value for key, value in payload.items()
            if key != "creditConfirmation"
        },
    }
    try:
        authorization = await features.authorize(
            auth.user, {"video_continue": 1},
            payload.get("creditConfirmation"), scope=charge_scope,
        )
    except FeatureAccessError as exc:
        return _feature_error(exc)
    try:
        claimed_job_id = await video.reserve_provider_claim(
            user_id=auth.user["id"], provider="gemini", operation_type="extend",
        )
    except VideoServiceError as exc:
        return _video_error(exc, stage="continuation_reservation")
    try:
        receipt = await features.consume(
            auth.user,
            "video_continue",
            {"route": "media_video_continue", "parentJobId": job_id},
            authorization=authorization,
            instance_key=idempotency_key,
            scope=charge_scope,
        )
    except FeatureAccessError as exc:
        try:
            await video.finish_provider_claim(
                user_id=auth.user["id"], job_id=claimed_job_id, outcome="rejected",
            )
        except Exception:
            logger.warning("Uncharged continuation claim needs expiry cleanup.")
        return _feature_error(exc)

    try:
        row = await video.continue_video(
            user_id=auth.user["id"],
            parent_job_id=job_id,
            prompt=str(payload.get("prompt") or ""),
            idempotency_key=idempotency_key,
            charge_receipt=receipt,
            claimed_job_id=claimed_job_id,
        )
        return {"success": True, "job": await video.public_job(user_id=auth.user["id"], row=row)}
    except VideoServiceError as exc:
        if exc.refund_eligible:
            try:
                await video.finish_provider_claim(
                    user_id=auth.user["id"], job_id=claimed_job_id, outcome="rejected",
                )
            except Exception:
                logger.warning("Refundable continuation claim needs expiry cleanup.")
            await _refund_failed_video_charge(
                user_id=auth.user["id"],
                receipt=receipt,
                job_id=exc.failed_job_id,
            )
        return _video_error(exc, stage="continuation_generation")


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
        return _video_error(exc, stage="status")
