"""Cost-guarded asynchronous media generation endpoints."""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
from uuid import uuid4

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..auth_service import authenticate_request
from ..db import eq
from ..feature_service import FeatureAccessError
from ..project_service import ProjectNotFoundError
from ..runtime import db, features, projects, settings, video
from ..security import normalize_chat_id
from ..usage_service import has_internal_access
from ..video_service import VideoService, VideoServiceError

router = APIRouter(prefix="/api/media", tags=["media"])
cron_router = APIRouter(tags=["cron"])
logger = logging.getLogger("askcrump.media")
VIDEO_IDEMPOTENCY_KEY_MAX_LENGTH = VideoService.IDEMPOTENCY_KEY_MAX_LENGTH


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
        },
    )


def _idempotency_key(request: Request, payload: dict) -> str | None:
    raw_value = request.headers.get("X-Idempotency-Key")
    if not isinstance(raw_value, str) or not raw_value.strip():
        raw_value = payload.get("idempotencyKey")
    if not isinstance(raw_value, str):
        return None
    value = " ".join(raw_value.split()).strip()
    if not value or len(value) > VIDEO_IDEMPOTENCY_KEY_MAX_LENGTH:
        return None
    return value


def _idempotency_required_error() -> JSONResponse:
    return _video_error(
        VideoServiceError(
            "Provide a nonblank video idempotency key of at most 120 characters.",
            "VIDEO_IDEMPOTENCY_REQUIRED",
            400,
        ),
        stage="request",
    )


def _billing_reservation_pending(row: dict | None) -> bool:
    return (
        (row or {}).get("status") == "queued"
        and str((row or {}).get("provider_job_id") or "").startswith("pending:")
        and (row or {}).get("video_phase") == "reserved_unbilled"
    )


def _reservation_in_progress_error() -> JSONResponse:
    return _video_error(
        VideoServiceError(
            "This same video request is already being authorized. Retry it with the same request key.",
            "VIDEO_REQUEST_IN_PROGRESS",
            409,
            True,
            False,
        ),
        stage="request",
    )


def _request_fingerprint(payload: dict) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _idempotency_conflict_error() -> JSONResponse:
    return _video_error(
        VideoServiceError(
            "That video request key is already bound to different settings. "
            "Start this changed request again.",
            "VIDEO_IDEMPOTENCY_CONFLICT",
            409,
        ),
        stage="request",
    )


def _same_request(row: dict, fingerprint: str) -> bool:
    stored = str(row.get("request_fingerprint") or "")
    return bool(stored and stored == fingerprint)


def _pre_atomic_compatibility_row(row: dict | None) -> bool:
    metadata = (row or {}).get("metadata") or {}
    return metadata.get("compatibilityOrigin") == "pre-atomic"


def _billing_state_unavailable_error() -> JSONResponse:
    return _video_error(
        VideoServiceError(
            "Ask Crump could not confirm this video charge safely. Retry with "
            "the same request key.",
            "VIDEO_BILLING_STATE_UNAVAILABLE",
            503,
            True,
            False,
        ),
        stage="request",
    )


def _normalized_creation_identity(
    payload: dict,
    *,
    engine: str,
    resolution: str,
    duration: int,
) -> tuple[str, str, str | None, list[dict[str, str]], str]:
    prompt = video.validate_prompt(
        payload.get("prompt"),
        max_chars=1000 if engine == VideoService.CINEMATIC else 4000,
    )
    aspect_ratio = video.validate_aspect_ratio(payload.get("aspectRatio") or "16:9")
    raw_project_id = str(payload.get("projectId") or "").strip()
    project_id = normalize_chat_id(raw_project_id) if raw_project_id else None
    reference_plan = video.normalize_reference_plan(
        file_ids=payload.get("referenceFileIds"),
        reference_plan=payload.get("referencePlan"),
        engine=engine,
        reference_confirmation=payload.get("referencePlanConfirmation"),
    )
    fingerprint = _request_fingerprint(
        {
            "operation": "generate",
            "prompt": prompt,
            "engine": engine,
            "aspectRatio": aspect_ratio,
            "resolution": resolution,
            "durationSeconds": duration,
            "projectId": project_id,
            "referencePlan": reference_plan,
        }
    )
    return prompt, aspect_ratio, project_id, reference_plan, fingerprint


def _normalized_continuation_identity(
    payload: dict,
    *,
    parent_job_id: str,
) -> tuple[str, str, str]:
    prompt = video.validate_prompt(payload.get("prompt"), max_chars=4000)
    normalized_parent = normalize_chat_id(parent_job_id)
    fingerprint = _request_fingerprint(
        {
            "operation": "extend",
            "parentJobId": normalized_parent,
            "prompt": prompt,
            "engine": VideoService.EXTENDABLE,
            "resolution": "720p",
            "durationSeconds": 8,
        }
    )
    return prompt, normalized_parent, fingerprint


async def _release_unbilled_reservation(
    *,
    user_id: str,
    row: dict,
    reservation_token: str,
) -> None:
    try:
        await video.release_unbilled_reservation(
            user_id=user_id,
            job_id=str(row.get("id") or ""),
            idempotency_key=str(row.get("idempotency_key") or ""),
            request_fingerprint=str(row.get("request_fingerprint") or ""),
            reservation_token=reservation_token,
        )
    except Exception:
        logger.warning("Unbilled video reservation cleanup needs a retry.")


async def _existing_job(user_id: str, key: str | None):
    if not key:
        return None
    return await db.select_one(
        "media_jobs",
        filters={"user_id": eq(user_id), "idempotency_key": eq(key)},
    )


async def _read_bound_video_receipt(
    *,
    user_id: str,
    idempotency_key: str,
    request_fingerprint: str,
) -> tuple[dict | None, dict | None]:
    """Resolve a transport-ambiguous billing call without mutating state."""
    current = await _existing_job(user_id, idempotency_key)
    if not current or not _same_request(current, request_fingerprint):
        return current, None
    receipt = current.get("billing_receipt")
    if (
        isinstance(receipt, dict)
        and receipt
        and current.get("video_phase")
        in {
            "ready_to_launch",
            "launching",
            "processing",
            "finalizing",
            "ready",
            "failed",
        }
    ):
        return current, receipt
    return current, None


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

    idempotency_key = _idempotency_key(request, payload)
    if not idempotency_key:
        return _idempotency_required_error()

    try:
        engine, resolution, duration = video.normalize_request(
            engine=payload.get("engine") or "quick",
            resolution=payload.get("resolution") or "720p",
            duration_seconds=payload.get("durationSeconds") or 0,
        )
        feature_code = video.feature_code(
            engine=engine,
            resolution=resolution,
            duration_seconds=duration,
        )
        (
            prompt,
            aspect_ratio,
            project_id,
            normalized_reference_plan,
            request_fingerprint,
        ) = _normalized_creation_identity(
            payload,
            engine=engine,
            resolution=resolution,
            duration=duration,
        )
    except VideoServiceError as exc:
        return _video_error(exc, stage="request")

    existing = await _existing_job(auth.user["id"], idempotency_key)
    if existing:
        if (
            not _same_request(existing, request_fingerprint)
            and not _pre_atomic_compatibility_row(existing)
        ):
            return _idempotency_conflict_error()
        try:
            existing = await video.reconcile_pending(
                user_id=auth.user["id"],
                row=existing,
                launch_ready=True,
            )
        except VideoServiceError as exc:
            return _video_error(exc, stage="generation")
        if _billing_reservation_pending(existing):
            return _reservation_in_progress_error()
        return {
            "success": True,
            "job": await video.public_job(user_id=auth.user["id"], row=existing),
            "idempotentReplay": True,
        }

    if project_id:
        try:
            await projects.get(auth.user["id"], project_id)
        except ProjectNotFoundError:
            return JSONResponse(
                status_code=404,
                content={"success": False, "error": "Project not found.", "code": "PROJECT_NOT_FOUND"},
            )

    try:
        reference_images = await video.prepare_reference_images(
            user_id=auth.user["id"],
            file_ids=[item["fileId"] for item in normalized_reference_plan],
            reference_plan=normalized_reference_plan,
            engine=engine,
        )
        _, _, reference_receipt, reference_mode = video.prepare_provider_prompt(
            prompt=prompt,
            engine=engine,
            references=reference_images,
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

    reservation_token = str(uuid4())
    try:
        reservation = await video.start(
            user_id=auth.user["id"],
            prompt=prompt,
            engine=engine,
            aspect_ratio=aspect_ratio,
            resolution=resolution,
            duration_seconds=duration,
            project_id=project_id,
            idempotency_key=idempotency_key,
            reference_images=reference_images,
            reserve_only=True,
            reservation_token=reservation_token,
            request_fingerprint=request_fingerprint,
        )
    except VideoServiceError as exc:
        return _video_error(exc, stage="generation")

    if not _same_request(reservation, request_fingerprint):
        return _idempotency_conflict_error()
    if str(reservation.get("lease_token") or "") != reservation_token:
        if _billing_reservation_pending(reservation):
            return _reservation_in_progress_error()
        try:
            reservation = await video.reconcile_pending(
                user_id=auth.user["id"],
                row=reservation,
                launch_ready=True,
            )
        except VideoServiceError as exc:
            return _video_error(exc, stage="generation")
        return {
            "success": True,
            "job": await video.public_job(user_id=auth.user["id"], row=reservation),
            "idempotentReplay": True,
        }

    try:
        reservation = await video.authorize_reservation_capacity(
            user_id=auth.user["id"],
            row=reservation,
            reservation_token=reservation_token,
            bypass_user_budget=has_internal_access(auth.user),
        )
    except VideoServiceError as exc:
        return _video_error(exc, stage="budget")

    try:
        receipt = await features.consume_video_reservation(
            auth.user,
            feature_code,
            media_job_id=str(reservation.get("id") or ""),
            idempotency_key=idempotency_key,
            request_fingerprint=request_fingerprint,
            reservation_token=reservation_token,
            metadata={
                "route": "media_video",
                "engine": engine,
                "resolution": resolution,
                "durationSeconds": duration,
                "referenceImageCount": len(reference_images),
                "referencePlan": reference_receipt,
                "referenceMode": reference_mode,
            },
            confirmation=payload.get("creditConfirmation"),
            instance_key=idempotency_key,
            scope={
                "route": "media_video",
                "payload": {
                    key: value
                    for key, value in payload.items()
                    if key != "creditConfirmation"
                },
            },
        )
    except FeatureAccessError as exc:
        if exc.code != "VIDEO_BILLING_STATE_UNAVAILABLE":
            await _release_unbilled_reservation(
                user_id=auth.user["id"],
                row=reservation,
                reservation_token=reservation_token,
            )
            return _feature_error(exc)
        try:
            _, recovered = await _read_bound_video_receipt(
                user_id=auth.user["id"],
                idempotency_key=idempotency_key,
                request_fingerprint=request_fingerprint,
            )
        except Exception:
            recovered = None
        if not recovered:
            return _billing_state_unavailable_error()
        receipt = recovered
    except Exception:
        logger.warning(
            "Video billing response was ambiguous; resolving from its protected job row."
        )
        try:
            _, recovered = await _read_bound_video_receipt(
                user_id=auth.user["id"],
                idempotency_key=idempotency_key,
                request_fingerprint=request_fingerprint,
            )
        except Exception:
            recovered = None
        if not recovered:
            return _billing_state_unavailable_error()
        receipt = recovered

    try:
        row = await video.start(
            user_id=auth.user["id"],
            prompt=prompt,
            engine=engine,
            aspect_ratio=aspect_ratio,
            resolution=resolution,
            duration_seconds=duration,
            project_id=project_id,
            idempotency_key=idempotency_key,
            charge_receipt=receipt,
            reference_images=reference_images,
            reservation_token=reservation_token,
            reserved_job_id=str(reservation.get("id") or ""),
            request_fingerprint=request_fingerprint,
        )
        return {"success": True, "job": await video.public_job(user_id=auth.user["id"], row=row)}
    except VideoServiceError as exc:
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
    if not idempotency_key:
        return _idempotency_required_error()

    try:
        prompt, normalized_parent_id, request_fingerprint = (
            _normalized_continuation_identity(payload, parent_job_id=job_id)
        )
    except VideoServiceError as exc:
        return _video_error(exc, stage="request")

    existing = await _existing_job(auth.user["id"], idempotency_key)
    if existing:
        if (
            not _same_request(existing, request_fingerprint)
            and not _pre_atomic_compatibility_row(existing)
        ):
            return _idempotency_conflict_error()
        try:
            existing = await video.reconcile_pending(
                user_id=auth.user["id"],
                row=existing,
                launch_ready=True,
            )
        except VideoServiceError as exc:
            return _video_error(exc, stage="continuation_generation")
        if _billing_reservation_pending(existing):
            return _reservation_in_progress_error()
        return {
            "success": True,
            "job": await video.public_job(user_id=auth.user["id"], row=existing),
            "idempotentReplay": True,
        }

    try:
        await video.validate_continuation_parent(
            user_id=auth.user["id"],
            job_id=normalized_parent_id,
        )
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

    reservation_token = str(uuid4())
    try:
        reservation = await video.continue_video(
            user_id=auth.user["id"],
            parent_job_id=normalized_parent_id,
            prompt=prompt,
            idempotency_key=idempotency_key,
            reserve_only=True,
            reservation_token=reservation_token,
            request_fingerprint=request_fingerprint,
        )
    except VideoServiceError as exc:
        return _video_error(exc, stage="continuation_generation")

    if not _same_request(reservation, request_fingerprint):
        return _idempotency_conflict_error()
    if str(reservation.get("lease_token") or "") != reservation_token:
        if _billing_reservation_pending(reservation):
            return _reservation_in_progress_error()
        try:
            reservation = await video.reconcile_pending(
                user_id=auth.user["id"],
                row=reservation,
                launch_ready=True,
            )
        except VideoServiceError as exc:
            return _video_error(exc, stage="continuation_generation")
        return {
            "success": True,
            "job": await video.public_job(user_id=auth.user["id"], row=reservation),
            "idempotentReplay": True,
        }

    try:
        reservation = await video.authorize_reservation_capacity(
            user_id=auth.user["id"],
            row=reservation,
            reservation_token=reservation_token,
            bypass_user_budget=has_internal_access(auth.user),
        )
    except VideoServiceError as exc:
        return _video_error(exc, stage="continuation_budget")

    try:
        receipt = await features.consume_video_reservation(
            auth.user,
            "video_continue",
            media_job_id=str(reservation.get("id") or ""),
            idempotency_key=idempotency_key,
            request_fingerprint=request_fingerprint,
            reservation_token=reservation_token,
            metadata={
                "route": "media_video_continue",
                "parentJobId": normalized_parent_id,
            },
            confirmation=payload.get("creditConfirmation"),
            instance_key=idempotency_key,
            scope={
                "route": "media_video_continue",
                "parentJobId": normalized_parent_id,
                "payload": {
                    key: value
                    for key, value in payload.items()
                    if key != "creditConfirmation"
                },
            },
        )
    except FeatureAccessError as exc:
        if exc.code != "VIDEO_BILLING_STATE_UNAVAILABLE":
            await _release_unbilled_reservation(
                user_id=auth.user["id"],
                row=reservation,
                reservation_token=reservation_token,
            )
            return _feature_error(exc)
        try:
            _, recovered = await _read_bound_video_receipt(
                user_id=auth.user["id"],
                idempotency_key=idempotency_key,
                request_fingerprint=request_fingerprint,
            )
        except Exception:
            recovered = None
        if not recovered:
            return _billing_state_unavailable_error()
        receipt = recovered
    except Exception:
        logger.warning(
            "Video continuation billing response was ambiguous; resolving "
            "from its protected job row."
        )
        try:
            _, recovered = await _read_bound_video_receipt(
                user_id=auth.user["id"],
                idempotency_key=idempotency_key,
                request_fingerprint=request_fingerprint,
            )
        except Exception:
            recovered = None
        if not recovered:
            return _billing_state_unavailable_error()
        receipt = recovered

    try:
        row = await video.continue_video(
            user_id=auth.user["id"],
            parent_job_id=normalized_parent_id,
            prompt=prompt,
            idempotency_key=idempotency_key,
            charge_receipt=receipt,
            reservation_token=reservation_token,
            reserved_job_id=str(reservation.get("id") or ""),
            request_fingerprint=request_fingerprint,
        )
        return {"success": True, "job": await video.public_job(user_id=auth.user["id"], row=row)}
    except VideoServiceError as exc:
        return _video_error(exc, stage="continuation_generation")


@router.get("/video")
async def recent_videos(request: Request):
    auth = await authenticate_request(request, db, settings)
    rows = await video.list_recent(user_id=auth.user["id"], limit=12)
    jobs = [
        await video.public_job(user_id=auth.user["id"], row=row)
        for row in rows
    ]
    return {"success": True, "jobs": jobs}


@router.get("/video/request-status")
async def video_request_status(request: Request):
    auth = await authenticate_request(request, db, settings)
    idempotency_key = _idempotency_key(request, {})
    if not idempotency_key:
        return _idempotency_required_error()
    row = await _existing_job(auth.user["id"], idempotency_key)
    if not row:
        return JSONResponse(
            status_code=404,
            content={
                "success": False,
                "error": "No video job exists for this request yet.",
                "code": "VIDEO_JOB_NOT_FOUND",
            },
        )
    try:
        row = await video.reconcile_pending(
            user_id=auth.user["id"],
            row=row,
            launch_ready=True,
        )
    except VideoServiceError as exc:
        return _video_error(exc, stage="status")
    if _billing_reservation_pending(row):
        return _reservation_in_progress_error()
    return {
        "success": True,
        "job": await video.public_job(user_id=auth.user["id"], row=row),
        "idempotentReplay": True,
    }


@router.get("/video/{job_id}")
async def video_status(job_id: str, request: Request):
    auth = await authenticate_request(request, db, settings)
    try:
        row = await video.poll(user_id=auth.user["id"], job_id=job_id)
        project_attachment = await _attach_ready_video_to_project(user_id=auth.user["id"], row=row)
        public_job = await video.public_job(user_id=auth.user["id"], row=row)
        if project_attachment:
            public_job["projectAttachment"] = project_attachment
        return {"success": True, "job": public_job}
    except VideoServiceError as exc:
        return _video_error(exc, stage="status")


@cron_router.get("/api/cron/videos")
async def video_lease_cron(request: Request):
    expected = settings.cron_secret
    authorization = request.headers.get("authorization", "")
    if not expected or not hmac.compare_digest(
        authorization,
        f"Bearer {expected}",
    ):
        return JSONResponse(
            status_code=401,
            content={"success": False, "error": "Unauthorized."},
        )
    try:
        summary = await video.sweep_expired_leases(limit=100)
        if summary.get("errors"):
            logger.error(
                "Expired video lease sweep quarantined rows count=%s scanned=%s",
                summary["errors"],
                summary.get("scanned", 0),
            )
        provider_summary = await video.reconcile_stale_processing(
            limit=10,
            stale_seconds=120,
        )
        if provider_summary.get("errors"):
            logger.warning(
                "Processing video reconciliation deferred rows count=%s retryable=%s scanned=%s",
                provider_summary["errors"],
                provider_summary.get("retryable", 0),
                provider_summary.get("scanned", 0),
            )
        return {
            "success": True,
            **summary,
            "providerReconciliation": provider_summary,
        }
    except VideoServiceError:
        logger.warning("Video background reconciliation needs a retry.")
        return JSONResponse(
            status_code=503,
            content={
                "success": False,
                "error": "Video background reconciliation is temporarily unavailable.",
                "code": "VIDEO_BACKGROUND_RECONCILIATION_UNAVAILABLE",
            },
        )
