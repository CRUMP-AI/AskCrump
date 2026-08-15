"""Server-side asynchronous video generation through the Gemini/Veo REST API."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import logging
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

import httpx

from .config import Settings
from .db import SupabaseDB, eq
from .file_service import FileService
from .security import normalize_chat_id


GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
ALLOWED_VIDEO_HOST_SUFFIXES = (".googleapis.com", ".googleusercontent.com")
logger = logging.getLogger("askcrump.video")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class VideoServiceError(RuntimeError):
    message: str
    code: str = "VIDEO_ERROR"
    status_code: int = 400
    retryable: bool = False

    def __post_init__(self) -> None:
        RuntimeError.__init__(self, self.message)


class VideoService:
    def __init__(self, settings: Settings, db: SupabaseDB, files: FileService) -> None:
        self.settings = settings
        self.db = db
        self.files = files

    @property
    def enabled(self) -> bool:
        return bool(self.settings.gemini_api_key and self.settings.video_generation_enabled)

    @staticmethod
    def _provider_error(response: httpx.Response) -> tuple[str, str]:
        code = ""
        message = ""
        try:
            body = response.json()
            error = body.get("error") if isinstance(body, dict) else None
            if isinstance(error, dict):
                code = str(error.get("status") or error.get("code") or "")[:120]
                message = " ".join(str(error.get("message") or "").split())[:500]
        except (TypeError, ValueError):
            message = " ".join(response.text.split())[:500]
        return code, message

    @classmethod
    def _provider_exception(cls, response: httpx.Response, *, checking: bool = False) -> VideoServiceError:
        provider_code, provider_message = cls._provider_error(response)
        request_id = str(
            response.headers.get("x-request-id")
            or response.headers.get("x-goog-request-id")
            or ""
        )[:160]
        logger.error(
            "Gemini video request rejected phase=%s status=%s code=%s request_id=%s message=%s",
            "poll" if checking else "start",
            response.status_code,
            provider_code or "-",
            request_id or "-",
            provider_message or "-",
        )
        diagnostic = f"{provider_code} {provider_message}".lower()
        if response.status_code in {401, 403} or "permission_denied" in diagnostic:
            return VideoServiceError(
                "Gemini video access is not enabled for this API key or project.",
                "VIDEO_PROVIDER_PERMISSION_REQUIRED",
                503,
                False,
            )
        if "quota" in diagnostic or "billing" in diagnostic or "resource_exhausted" in diagnostic:
            return VideoServiceError(
                "The Gemini video provider project has no available quota or billing budget.",
                "VIDEO_PROVIDER_QUOTA_REQUIRED",
                503,
                False,
            )
        if response.status_code == 429:
            return VideoServiceError(
                "The video provider is rate limited. Try again shortly.",
                "VIDEO_RATE_LIMIT",
                429,
                True,
            )
        return VideoServiceError(
            "The video provider could not return job status."
            if checking
            else "The video provider rejected the generation request.",
            "VIDEO_STATUS_UNAVAILABLE" if checking else "VIDEO_PROVIDER_REJECTED",
            502,
            response.status_code >= 500,
        )

    @staticmethod
    def validate_prompt(value: Any) -> str:
        prompt = " ".join(str(value or "").split()).strip()
        if len(prompt) < 8:
            raise VideoServiceError("Describe the video in a little more detail.", "PROMPT_TOO_SHORT")
        if len(prompt) > 4000:
            raise VideoServiceError("Video prompts must be 4,000 characters or fewer.", "PROMPT_TOO_LONG")
        return prompt

    @staticmethod
    def validate_aspect_ratio(value: Any) -> str:
        aspect = str(value or "16:9").strip()
        if aspect not in {"16:9", "9:16"}:
            raise VideoServiceError("Video aspect ratio must be 16:9 or 9:16.", "INVALID_ASPECT")
        return aspect

    @staticmethod
    def validate_resolution(value: Any) -> str:
        resolution = str(value or "720p").strip().lower()
        if resolution not in {"720p", "1080p"}:
            raise VideoServiceError("Ask Crump currently supports 720p or 1080p video.", "INVALID_RESOLUTION")
        return resolution

    @staticmethod
    def _public(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": row.get("id"),
            "status": row.get("status"),
            "prompt": row.get("prompt"),
            "aspectRatio": row.get("aspect_ratio"),
            "resolution": row.get("resolution"),
            "model": row.get("model"),
            "projectId": row.get("project_id"),
            "fileId": row.get("file_id"),
            "error": row.get("error_message"),
            "createdAt": row.get("created_at"),
            "updatedAt": row.get("updated_at"),
        }

    async def get(self, *, user_id: str, job_id: str) -> dict[str, Any]:
        try:
            normalized = normalize_chat_id(job_id)
        except Exception as exc:
            raise VideoServiceError("Video job not found.", "VIDEO_JOB_NOT_FOUND", 404) from exc
        row = await self.db.select_one(
            "media_jobs",
            filters={"id": eq(normalized), "user_id": eq(user_id)},
        )
        if not row:
            raise VideoServiceError("Video job not found.", "VIDEO_JOB_NOT_FOUND", 404)
        return row

    async def active_count(self, *, user_id: str) -> int:
        rows = await self.db.select(
            "media_jobs",
            columns="id,status",
            filters={"user_id": eq(user_id), "kind": eq("video")},
            order="created_at.desc",
            limit=20,
        )
        return sum(1 for row in rows if row.get("status") in {"queued", "processing"})

    async def start(
        self,
        *,
        user_id: str,
        prompt: str,
        aspect_ratio: str = "16:9",
        resolution: str = "720p",
        project_id: str | None = None,
        idempotency_key: str | None = None,
        charge_receipt: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self.enabled:
            raise VideoServiceError(
                "Video generation is not configured yet.",
                "VIDEO_NOT_CONFIGURED",
                503,
            )
        prompt = self.validate_prompt(prompt)
        aspect_ratio = self.validate_aspect_ratio(aspect_ratio)
        resolution = self.validate_resolution(resolution)
        project = normalize_chat_id(project_id) if project_id else None
        key = " ".join(str(idempotency_key or "").split()).strip()[:160] or None

        if key:
            existing = await self.db.select_one(
                "media_jobs",
                filters={"user_id": eq(user_id), "idempotency_key": eq(key)},
            )
            if existing:
                return existing

        if await self.active_count(user_id=user_id) >= self.settings.max_active_video_jobs_per_user:
            raise VideoServiceError(
                "Wait for the current video job to finish before starting another.",
                "VIDEO_CONCURRENCY_LIMIT",
                429,
                True,
            )

        model = self.settings.gemini_video_model
        payload = {
            "instances": [{"prompt": prompt}],
            "parameters": {
                "aspectRatio": aspect_ratio,
                "resolution": resolution,
                "numberOfVideos": 1,
                "durationSeconds": 8,
            },
        }
        headers = {
            "x-goog-api-key": str(self.settings.gemini_api_key),
            "Content-Type": "application/json",
        }
        url = f"{GEMINI_BASE_URL}/models/{model}:predictLongRunning"
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(45.0, connect=15.0)) as client:
                response = await client.post(url, headers=headers, json=payload)
        except httpx.HTTPError as exc:
            raise VideoServiceError(
                "Could not start the video generation job.",
                "VIDEO_PROVIDER_UNAVAILABLE",
                503,
                True,
            ) from exc
        if response.status_code >= 400:
            raise self._provider_exception(response)
        try:
            body = response.json()
        except ValueError as exc:
            raise VideoServiceError(
                "The video provider returned an invalid response.",
                "VIDEO_PROVIDER_INVALID_RESPONSE",
                502,
                True,
            ) from exc
        operation_name = str(body.get("name") or "").strip()
        if not operation_name:
            raise VideoServiceError(
                "The video provider did not return a job identifier.",
                "VIDEO_PROVIDER_INVALID_RESPONSE",
                502,
                True,
            )

        row = {
            "id": str(uuid4()),
            "user_id": user_id,
            "project_id": project,
            "kind": "video",
            "provider": "gemini",
            "provider_job_id": operation_name[:500],
            "idempotency_key": key,
            "status": "processing",
            "prompt": prompt,
            "model": model,
            "aspect_ratio": aspect_ratio,
            "resolution": resolution,
            "file_id": None,
            "error_message": None,
            "billing_receipt": charge_receipt or {},
            "metadata": {},
            "updated_at": _now(),
        }
        result = await self.db.insert("media_jobs", row)
        return (result or [row])[0]

    @staticmethod
    def _safe_video_uri(uri: str) -> str:
        parsed = urlparse(uri)
        host = (parsed.hostname or "").lower()
        if parsed.scheme != "https" or not host:
            raise VideoServiceError("Unsafe video download location.", "UNSAFE_VIDEO_URI", 502)
        if host == "generativelanguage.googleapis.com" or any(
            host.endswith(suffix) for suffix in ALLOWED_VIDEO_HOST_SUFFIXES
        ):
            return uri
        raise VideoServiceError("Unexpected video download host.", "UNSAFE_VIDEO_URI", 502)

    async def _mark_failed(
        self,
        *,
        user_id: str,
        row: dict[str, Any],
        message: str,
    ) -> dict[str, Any]:
        updated = await self.db.update(
            "media_jobs",
            {"status": "failed", "error_message": str(message or "Video delivery failed.")[:500], "updated_at": _now()},
            filters={"id": eq(row["id"]), "user_id": eq(user_id)},
        )
        return (updated or [{**row, "status": "failed", "error_message": message}])[0]

    async def poll(self, *, user_id: str, job_id: str) -> dict[str, Any]:
        row = await self.get(user_id=user_id, job_id=job_id)
        if row.get("status") in {"ready", "failed"}:
            return row
        if not self.settings.gemini_api_key:
            raise VideoServiceError("Video generation is not configured.", "VIDEO_NOT_CONFIGURED", 503)

        operation_name = str(row.get("provider_job_id") or "").lstrip("/")
        if not operation_name:
            raise VideoServiceError("Video job is missing provider state.", "VIDEO_JOB_CORRUPT", 500)
        headers = {"x-goog-api-key": str(self.settings.gemini_api_key)}
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=15.0)) as client:
                response = await client.get(f"{GEMINI_BASE_URL}/{operation_name}", headers=headers)
        except httpx.HTTPError as exc:
            raise VideoServiceError(
                "Could not check video generation status.",
                "VIDEO_STATUS_UNAVAILABLE",
                503,
                True,
            ) from exc
        if response.status_code >= 400:
            raise self._provider_exception(response, checking=True)
        try:
            body = response.json()
        except ValueError as exc:
            raise VideoServiceError(
                "The video provider returned an invalid status response.",
                "VIDEO_PROVIDER_INVALID_RESPONSE",
                502,
                True,
            ) from exc

        if not body.get("done"):
            return row
        if body.get("error"):
            provider_error = body.get("error") or {}
            error_text = str(provider_error.get("message") or "Video generation failed.")[:500]
            provider_code = str(provider_error.get("status") or provider_error.get("code") or "")[:120]
            logger.error(
                "Gemini video job failed job=%s code=%s message=%s",
                str(row.get("id") or "")[:80],
                provider_code or "-",
                " ".join(error_text.split()),
            )
            updated = await self.db.update(
                "media_jobs",
                {
                    "status": "failed",
                    "error_message": error_text,
                    "metadata": {**(row.get("metadata") or {}), "providerErrorCode": provider_code},
                    "updated_at": _now(),
                },
                filters={"id": eq(row["id"]), "user_id": eq(user_id)},
            )
            return (updated or [row])[0]

        samples = (((body.get("response") or {}).get("generateVideoResponse") or {}).get("generatedSamples") or [])
        sample = samples[0] if samples and isinstance(samples[0], dict) else {}
        uri = str((sample.get("video") or {}).get("uri") or "").strip()
        if not uri:
            updated = await self.db.update(
                "media_jobs",
                {
                    "status": "failed",
                    "error_message": "The provider completed without a video file.",
                    "updated_at": _now(),
                },
                filters={"id": eq(row["id"]), "user_id": eq(user_id)},
            )
            return (updated or [row])[0]

        try:
            safe_uri = self._safe_video_uri(uri)
        except VideoServiceError as exc:
            return await self._mark_failed(user_id=user_id, row=row, message=exc.message)
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(120.0, connect=20.0),
                follow_redirects=True,
            ) as client:
                download = await client.get(safe_uri, headers=headers)
        except httpx.HTTPError:
            return await self._mark_failed(
                user_id=user_id,
                row=row,
                message="The video finished but Ask Crump could not retrieve the file.",
            )
        if download.status_code >= 400:
            return await self._mark_failed(
                user_id=user_id,
                row=row,
                message="The video finished but Ask Crump could not retrieve the file.",
            )
        data = download.content
        if not data or len(data) > self.settings.max_generated_video_bytes:
            return await self._mark_failed(
                user_id=user_id,
                row=row,
                message="The generated video exceeded Ask Crump's storage safety limit.",
            )

        try:
            file_row = await self.files.store_bytes(
                user_id=user_id,
                data=data,
                filename=f"crump-video-{row['id']}.mp4",
                mime_type="video/mp4",
                kind="generated_video",
                metadata={
                    "prompt": row.get("prompt"),
                    "provider": "gemini",
                    "model": row.get("model"),
                    "aspectRatio": row.get("aspect_ratio"),
                    "resolution": row.get("resolution"),
                },
            )
        except Exception:
            return await self._mark_failed(
                user_id=user_id,
                row=row,
                message="The video finished but Ask Crump could not save the file.",
            )
        updated = await self.db.update(
            "media_jobs",
            {
                "status": "ready",
                "file_id": file_row["id"],
                "metadata": {"providerCompleted": True},
                "updated_at": _now(),
            },
            filters={"id": eq(row["id"]), "user_id": eq(user_id)},
        )
        return (updated or [{**row, "status": "ready", "file_id": file_row["id"]}])[0]

    async def public_job(self, *, user_id: str, row: dict[str, Any]) -> dict[str, Any]:
        payload = self._public(row)
        file_id = row.get("file_id")
        if file_id:
            try:
                file_row = await self.files.get_owned(user_id=user_id, file_id=str(file_id))
                payload["file"] = self.files.public_file(file_row)
            except Exception:
                payload["file"] = None
        return payload
