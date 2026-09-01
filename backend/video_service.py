"""Provider-agnostic asynchronous video generation for Ask Crump."""
from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from io import BytesIO
from typing import Any
from uuid import uuid4

from PIL import Image, ImageOps, UnidentifiedImageError

from .config import Settings
from .db import SupabaseDB, eq, gte
from .file_service import FileService, FileServiceError
from .security import normalize_chat_id
from .video_providers import GeminiVeoProvider, ProviderError, RunwayProvider


def _now_dt() -> datetime:
    return datetime.now(timezone.utc)


def _now() -> str:
    return _now_dt().isoformat()


def _future(hours: int) -> str:
    return (_now_dt() + timedelta(hours=hours)).isoformat()


@dataclass(slots=True)
class VideoServiceError(RuntimeError):
    message: str
    code: str = "VIDEO_ERROR"
    status_code: int = 400
    retryable: bool = False
    refund_eligible: bool = True

    def __post_init__(self) -> None:
        RuntimeError.__init__(self, self.message)


class VideoService:
    QUICK = "quick"
    EXTENDABLE = "extendable"
    CINEMATIC = "cinematic"
    ENGINES = {QUICK, EXTENDABLE, CINEMATIC}
    REFERENCE_IMAGE_MAX_BYTES = 20 * 1024 * 1024
    REFERENCE_IMAGE_MAX_EDGE = 2048

    def __init__(self, settings: Settings, db: SupabaseDB, files: FileService) -> None:
        self.settings = settings
        self.db = db
        self.files = files
        self.gemini = GeminiVeoProvider(settings)
        self.runway = RunwayProvider(settings)

    @property
    def enabled(self) -> bool:
        return self.gemini.enabled or self.runway.enabled

    @property
    def engine_status(self) -> dict[str, dict[str, Any]]:
        return {
            self.QUICK: {
                "configured": self.gemini.enabled,
                "provider": "gemini",
                "model": self.settings.gemini_video_model,
                "durations": [8],
                "resolutions": ["720p", "1080p"],
                "continuable": False,
                "attribution": None,
            },
            self.EXTENDABLE: {
                "configured": self.gemini.enabled,
                "provider": "gemini",
                "model": self.settings.gemini_video_extend_model,
                "durations": [8],
                "resolutions": ["720p"],
                "continuable": True,
                "attribution": None,
            },
            self.CINEMATIC: {
                "configured": self.runway.enabled,
                "provider": "runway",
                "model": self.settings.runway_video_model,
                "durations": [5, 10],
                "resolutions": ["720p"],
                "continuable": False,
                "attribution": "Powered by Runway",
            },
        }

    @staticmethod
    def _map_provider_error(exc: ProviderError) -> VideoServiceError:
        return VideoServiceError(exc.message, exc.code, exc.status_code, exc.retryable, exc.refund_eligible)

    @classmethod
    def _provider_exception(cls, response, *, checking: bool = False) -> VideoServiceError:
        """Compatibility bridge for the existing Gemini error contract/tests."""
        return cls._map_provider_error(GeminiVeoProvider._exception(response, checking=checking))

    @staticmethod
    def validate_prompt(value: Any, *, max_chars: int = 4000) -> str:
        prompt = " ".join(str(value or "").split()).strip()
        if len(prompt) < 8:
            raise VideoServiceError("Describe the video in a little more detail.", "PROMPT_TOO_SHORT")
        if len(prompt) > max_chars:
            raise VideoServiceError(f"Video prompts for this engine must be {max_chars:,} characters or fewer.", "PROMPT_TOO_LONG")
        return prompt

    @staticmethod
    def provider_prompt(prompt: str, *, max_chars: int, has_visual_reference: bool = False) -> str:
        """Add bounded continuity/brand constraints without changing saved copy."""
        brand_guard = (
            'Use the supplied visual reference to preserve the subject, product, colors, proportions, and visible mark; '
            'do not restyle the mark, add letters, or substitute symbols.'
            if has_visual_reference
            else 'Never invent or approximate a logo, wordmark, label, or branded text. If an exact mark is not supplied '
                 'as visual input, keep branding absent or out of frame.'
        )
        guard = (
            'Continuity requirements: keep subject identity, colors, geometry, object counts, anatomy, and spatial '
            'relationships stable across every frame; avoid morphing, duplicates, substitutions, and unreadable details. '
            f'{brand_guard}'
        )
        combined = f'{prompt}\n\n{guard}'
        if len(combined) > max_chars:
            user_limit = max(8, max_chars - len(guard) - 2)
            raise VideoServiceError(
                f'Keep this video prompt to {user_limit:,} characters or fewer so Crump can include its visual-fidelity instructions.',
                'PROMPT_TOO_LONG',
            )
        return combined

    @staticmethod
    def reference_limit(engine: str) -> int:
        return 3 if engine == VideoService.EXTENDABLE else 1

    @classmethod
    def _prepare_reference_image(cls, data: bytes) -> tuple[str, str]:
        """Decode one private upload into a bounded provider-safe PNG payload."""
        try:
            with Image.open(BytesIO(data)) as source:
                source.seek(0)
                image = ImageOps.exif_transpose(source)
                image.load()
                image = image.copy()
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
            raise VideoServiceError(
                "That reference could not be read as an image. Use a JPG, PNG, or WebP file.",
                "INVALID_VIDEO_REFERENCE_IMAGE",
            ) from exc

        longest_edge = max(image.size or (0, 0))
        if longest_edge <= 0:
            raise VideoServiceError(
                "That reference image has invalid dimensions.",
                "INVALID_VIDEO_REFERENCE_IMAGE",
            )
        if longest_edge > cls.REFERENCE_IMAGE_MAX_EDGE:
            scale = cls.REFERENCE_IMAGE_MAX_EDGE / longest_edge
            image = image.resize(
                (max(1, round(image.width * scale)), max(1, round(image.height * scale))),
                Image.Resampling.LANCZOS,
            )
        if image.mode not in {"RGB", "RGBA"}:
            image = image.convert("RGBA" if "A" in image.getbands() or "transparency" in image.info else "RGB")

        prepared = BytesIO()
        image.save(prepared, format="PNG", optimize=True)
        normalized = prepared.getvalue()
        if not normalized or len(normalized) > cls.REFERENCE_IMAGE_MAX_BYTES:
            raise VideoServiceError(
                "That reference image is too complex to prepare safely. Use a smaller JPG, PNG, or WebP file.",
                "VIDEO_REFERENCE_IMAGE_TOO_LARGE",
                413,
            )
        return "image/png", base64.b64encode(normalized).decode("ascii")

    async def prepare_reference_images(
        self,
        *,
        user_id: str,
        file_ids: Any,
        engine: str,
    ) -> list[dict[str, str]]:
        """Resolve owner-scoped Files before credits or provider spend."""
        if file_ids is None or file_ids == "":
            return []
        if not isinstance(file_ids, list):
            raise VideoServiceError(
                "Video references must be selected from your private Files.",
                "INVALID_VIDEO_REFERENCE",
            )

        normalized_engine = self.validate_engine(engine)
        normalized_ids: list[str] = []
        for value in file_ids:
            try:
                file_id = normalize_chat_id(str(value))
            except Exception as exc:
                raise VideoServiceError(
                    "One video reference is invalid. Remove it and upload the image again.",
                    "INVALID_VIDEO_REFERENCE",
                ) from exc
            if file_id not in normalized_ids:
                normalized_ids.append(file_id)

        limit = self.reference_limit(normalized_engine)
        if len(normalized_ids) > limit:
            label = "Extendable" if normalized_engine == self.EXTENDABLE else normalized_engine.title()
            raise VideoServiceError(
                f"{label} accepts up to {limit} reference image{'s' if limit != 1 else ''}.",
                "TOO_MANY_VIDEO_REFERENCES",
            )

        prepared: list[dict[str, str]] = []
        for file_id in normalized_ids:
            try:
                row = await self.files.get_owned(user_id=user_id, file_id=file_id)
                if not str(row.get("mime_type") or "").lower().startswith("image/"):
                    raise VideoServiceError(
                        "Video references must be JPG, PNG, or WebP images.",
                        "INVALID_VIDEO_REFERENCE_IMAGE",
                    )
                raw = await self.files.download_bytes(row=row, max_bytes=self.REFERENCE_IMAGE_MAX_BYTES)
            except FileServiceError as exc:
                raise VideoServiceError(
                    "A selected video reference is unavailable. Remove it and upload the image again.",
                    "VIDEO_REFERENCE_UNAVAILABLE",
                    exc.status_code,
                    exc.status_code >= 500,
                ) from exc
            mime_type, encoded = self._prepare_reference_image(raw)
            prepared.append({"fileId": file_id, "mimeType": mime_type, "data": encoded})
        return prepared

    @staticmethod
    def validate_aspect_ratio(value: Any) -> str:
        aspect = str(value or "16:9").strip()
        if aspect not in {"16:9", "9:16"}:
            raise VideoServiceError("Video aspect ratio must be 16:9 or 9:16.", "INVALID_ASPECT")
        return aspect

    @classmethod
    def validate_engine(cls, value: Any) -> str:
        engine = str(value or cls.QUICK).strip().lower()
        if engine not in cls.ENGINES:
            raise VideoServiceError("That video engine is not available.", "INVALID_VIDEO_ENGINE")
        return engine

    @staticmethod
    def validate_resolution(value: Any) -> str:
        resolution = str(value or "720p").strip().lower()
        if resolution not in {"720p", "1080p"}:
            raise VideoServiceError("Ask Crump currently supports 720p or 1080p video.", "INVALID_RESOLUTION")
        return resolution

    @classmethod
    def normalize_request(cls, *, engine: Any, resolution: Any, duration_seconds: Any) -> tuple[str, str, int]:
        normalized_engine = cls.validate_engine(engine)
        normalized_resolution = cls.validate_resolution(resolution)
        try:
            duration = int(duration_seconds or 0)
        except (TypeError, ValueError) as exc:
            raise VideoServiceError("Invalid video duration.", "INVALID_VIDEO_DURATION") from exc

        if normalized_engine == cls.QUICK:
            duration = 8
        elif normalized_engine == cls.EXTENDABLE:
            normalized_resolution = "720p"
            duration = 8
        else:
            normalized_resolution = "720p"
            duration = duration or 5
            if duration not in {5, 10}:
                raise VideoServiceError("Cinematic video supports 5 or 10 seconds.", "INVALID_VIDEO_DURATION")
        return normalized_engine, normalized_resolution, duration

    @classmethod
    def feature_code(cls, *, engine: Any, resolution: Any, duration_seconds: Any) -> str:
        normalized_engine, normalized_resolution, duration = cls.normalize_request(
            engine=engine,
            resolution=resolution,
            duration_seconds=duration_seconds,
        )
        if normalized_engine == cls.QUICK:
            return "video_hd" if normalized_resolution == "1080p" else "video"
        if normalized_engine == cls.EXTENDABLE:
            return "video_extendable"
        return "video_cinematic_10" if duration == 10 else "video_cinematic_5"

    @staticmethod
    def provider_cost_cents(*, engine: str, resolution: str, duration_seconds: int, operation_type: str = "generate") -> int:
        if operation_type == "extend":
            return 80  # conservative envelope around a Veo Fast continuation
        if engine == VideoService.QUICK:
            return 64 if resolution == "1080p" else 40
        if engine == VideoService.EXTENDABLE:
            return 80
        if engine == VideoService.CINEMATIC:
            return 12 * int(duration_seconds)  # Runway Gen-4.5 = 12 provider credits/sec = $0.12/sec
        return 0

    @classmethod
    def provider_for_engine(cls, engine: str) -> str:
        return "runway" if engine == cls.CINEMATIC else "gemini"

    async def _estimated_spend_since(
        self,
        *,
        since: datetime,
        user_id: str | None = None,
        provider: str | None = None,
    ) -> int:
        filters: dict[str, Any] = {
            "kind": eq("video"),
            "created_at": gte(since.isoformat()),
        }
        if user_id:
            filters["user_id"] = eq(user_id)
        if provider:
            filters["provider"] = eq(provider)
        rows = await self.db.select(
            "media_jobs",
            columns="estimated_provider_cost_cents",
            filters=filters,
            order="created_at.desc",
            limit=2000,
        )
        return sum(max(0, int(row.get("estimated_provider_cost_cents") or 0)) for row in rows)

    async def guard_provider_budget(
        self,
        *,
        user_id: str,
        provider: str,
        estimated_cost_cents: int,
        bypass_user_limit: bool = False,
    ) -> None:
        """Conservative provider-cost circuit breakers for early production.

        These guards count reserved/attempted work, not only successful invoices,
        on purpose. They are an emergency ceiling against loops, leaked sessions,
        or provider-side billing surprises. Operators can raise or disable each
        limit deliberately through environment variables.
        """
        estimate = max(0, int(estimated_cost_cents or 0))
        now = _now_dt()
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        month_start = day_start.replace(day=1)

        global_limit = int(self.settings.video_daily_provider_budget_cents or 0)
        if global_limit > 0:
            spent = await self._estimated_spend_since(since=day_start)
            if spent + estimate > global_limit:
                raise VideoServiceError(
                    "Ask Crump's video provider budget is temporarily paused for today.",
                    "VIDEO_PROVIDER_BUDGET_PAUSED",
                    503,
                    False,
                )

        user_limit = int(self.settings.video_user_daily_provider_budget_cents or 0)
        if user_limit > 0 and not bypass_user_limit:
            spent = await self._estimated_spend_since(since=day_start, user_id=user_id)
            if spent + estimate > user_limit:
                raise VideoServiceError(
                    "You've reached today's video generation safety limit. Try again tomorrow.",
                    "VIDEO_USER_PROVIDER_BUDGET_LIMIT",
                    429,
                    False,
                )

        runway_limit = int(self.settings.runway_monthly_provider_budget_cents or 0)
        if provider == "runway" and runway_limit > 0:
            spent = await self._estimated_spend_since(since=month_start, provider="runway")
            if spent + estimate > runway_limit:
                raise VideoServiceError(
                    "Cinematic video is temporarily paused while the provider budget resets.",
                    "RUNWAY_PROVIDER_BUDGET_PAUSED",
                    503,
                    False,
                )

    @staticmethod
    def _public_base(row: dict[str, Any]) -> dict[str, Any]:
        metadata = row.get("metadata") or {}
        return {
            "id": row.get("id"),
            "status": row.get("status"),
            "prompt": row.get("prompt"),
            "aspectRatio": row.get("aspect_ratio"),
            "resolution": row.get("resolution"),
            "model": row.get("model"),
            "provider": row.get("provider"),
            "engine": row.get("engine") or VideoService.QUICK,
            "operationType": row.get("operation_type") or "generate",
            "durationSeconds": int(row.get("duration_seconds") or 8),
            "sequenceIndex": int(row.get("sequence_index") or 0),
            "parentJobId": row.get("parent_job_id"),
            "rootJobId": row.get("root_job_id") or row.get("id"),
            "projectId": row.get("project_id"),
            "fileId": row.get("file_id"),
            "error": row.get("error_message"),
            "chargeReturned": bool(row.get("billing_refunded")),
            "providerStatus": metadata.get("providerStatus"),
            "createdAt": row.get("created_at"),
            "updatedAt": row.get("updated_at"),
        }

    async def get(self, *, user_id: str, job_id: str) -> dict[str, Any]:
        try:
            normalized = normalize_chat_id(job_id)
        except Exception as exc:
            raise VideoServiceError("Video job not found.", "VIDEO_JOB_NOT_FOUND", 404) from exc
        row = await self.db.select_one("media_jobs", filters={"id": eq(normalized), "user_id": eq(user_id)})
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

    async def _idempotent(self, *, user_id: str, key: str | None) -> dict[str, Any] | None:
        if not key:
            return None
        return await self.db.select_one("media_jobs", filters={"user_id": eq(user_id), "idempotency_key": eq(key)})

    async def _guard_concurrency(self, *, user_id: str) -> None:
        if await self.active_count(user_id=user_id) >= self.settings.max_active_video_jobs_per_user:
            raise VideoServiceError(
                "Wait for the current video job to finish before starting another.",
                "VIDEO_CONCURRENCY_LIMIT",
                429,
                True,
            )

    async def start(
        self,
        *,
        user_id: str,
        prompt: str,
        engine: str = QUICK,
        aspect_ratio: str = "16:9",
        resolution: str = "720p",
        duration_seconds: int = 8,
        project_id: str | None = None,
        idempotency_key: str | None = None,
        charge_receipt: dict[str, Any] | None = None,
        reference_images: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        engine, resolution, duration_seconds = self.normalize_request(
            engine=engine,
            resolution=resolution,
            duration_seconds=duration_seconds,
        )
        provider_prompt_limit = 1000 if engine == self.CINEMATIC else 4000
        prompt = self.validate_prompt(prompt, max_chars=provider_prompt_limit)
        references = list(reference_images or [])
        limit = self.reference_limit(engine)
        if len(references) > limit:
            raise VideoServiceError(
                f"This video engine accepts up to {limit} reference image{'s' if limit != 1 else ''}.",
                "TOO_MANY_VIDEO_REFERENCES",
            )
        guarded_prompt = self.provider_prompt(
            prompt,
            max_chars=provider_prompt_limit,
            has_visual_reference=bool(references),
        )
        aspect_ratio = self.validate_aspect_ratio(aspect_ratio)
        project = normalize_chat_id(project_id) if project_id else None
        key = " ".join(str(idempotency_key or "").split()).strip()[:160] or None

        existing = await self._idempotent(user_id=user_id, key=key)
        if existing:
            return existing
        await self._guard_concurrency(user_id=user_id)

        if engine == self.CINEMATIC:
            provider = "runway"
            model = self.settings.runway_video_model
        else:
            provider = "gemini"
            model = self.settings.gemini_video_extend_model if engine == self.EXTENDABLE else self.settings.gemini_video_model

        job_id = str(uuid4())
        row = {
            "id": job_id,
            "user_id": user_id,
            "project_id": project,
            "kind": "video",
            "provider": provider,
            # Reserve the job before provider spend. media_jobs predates provider
            # abstraction and requires a non-null provider_job_id.
            "provider_job_id": f"pending:{job_id}",
            "idempotency_key": key,
            "status": "queued",
            "prompt": prompt,
            "model": model,
            "aspect_ratio": aspect_ratio,
            "resolution": resolution,
            "engine": engine,
            "operation_type": "generate",
            "parent_job_id": None,
            "root_job_id": None,
            "sequence_index": 0,
            "duration_seconds": duration_seconds,
            "provider_asset_reference": None,
            "provider_asset_expires_at": None,
            "estimated_provider_cost_cents": self.provider_cost_cents(
                engine=engine,
                resolution=resolution,
                duration_seconds=duration_seconds,
            ),
            "file_id": None,
            "error_message": None,
            "billing_receipt": charge_receipt or {},
            "metadata": {
                "refundEligible": True,
                "providerAccepted": False,
                "referenceFileIds": [str(reference.get("fileId") or "") for reference in references],
                "referenceMode": (
                    "asset" if references and engine == self.EXTENDABLE
                    else "initial-frame" if references
                    else None
                ),
            },
            "updated_at": _now(),
        }
        inserted = await self.db.insert("media_jobs", row)
        row = (inserted or [row])[0]

        try:
            if engine == self.CINEMATIC:
                provider_job_id = await self.runway.start(
                    model=model,
                    prompt=guarded_prompt,
                    aspect_ratio=aspect_ratio,
                    duration_seconds=duration_seconds,
                    prompt_image=(
                        f"data:{references[0]['mimeType']};base64,{references[0]['data']}"
                        if references else None
                    ),
                )
            else:
                provider_job_id = await self.gemini.start(
                    model=model,
                    prompt=guarded_prompt,
                    aspect_ratio=aspect_ratio,
                    resolution=resolution,
                    duration_seconds=duration_seconds,
                    initial_image=references[0] if references and engine == self.QUICK else None,
                    reference_images=references if engine == self.EXTENDABLE else None,
                )
        except ProviderError as exc:
            # No provider task was accepted. Preserve a diagnostic job row but
            # remove the reserved provider cost so circuit breakers reflect spend.
            try:
                await self.db.update(
                    "media_jobs",
                    {
                        "status": "failed",
                        "error_message": exc.message[:500],
                        "estimated_provider_cost_cents": 0,
                        "metadata": {
                            **(row.get("metadata") or {}),
                            "providerAccepted": False,
                            "providerFailureCode": exc.failure_code or exc.code,
                            "refundEligible": bool(exc.refund_eligible),
                        },
                        "updated_at": _now(),
                    },
                    filters={"id": eq(job_id), "user_id": eq(user_id)},
                )
            except Exception:
                pass
            raise self._map_provider_error(exc) from exc

        try:
            updated = await self.db.update(
                "media_jobs",
                {
                    "provider_job_id": provider_job_id,
                    "status": "processing",
                    "metadata": {**(row.get("metadata") or {}), "providerAccepted": True},
                    "updated_at": _now(),
                },
                filters={"id": eq(job_id), "user_id": eq(user_id)},
            )
        except Exception as exc:
            # The provider accepted work and may bill it. Do not automatically
            # refund Ask Crump credits if persistence fails after that boundary.
            raise VideoServiceError(
                "The video provider accepted the job, but Ask Crump could not persist its tracking state.",
                "VIDEO_JOB_TRACKING_FAILED",
                503,
                True,
                False,
            ) from exc
        if not updated:
            raise VideoServiceError(
                "The video provider accepted the job, but Ask Crump could not persist its tracking state.",
                "VIDEO_JOB_TRACKING_FAILED",
                503,
                True,
                False,
            )
        return updated[0]

    def _continuation_storage_safe(self, row: dict[str, Any]) -> bool:
        metadata = row.get("metadata") or {}
        current_bytes = max(0, int(metadata.get("storedBytes") or 0))
        current_duration = max(1, int(row.get("duration_seconds") or 8))
        if current_bytes <= 0:
            return True
        next_duration = min(148, current_duration + 7)
        # Veo returns one combined file. Reserve 25% headroom because bitrate can
        # change between generations. The configured byte ceiling is deliberately
        # kept below the active storage tier's effective object limit.
        projected = int(current_bytes * (next_duration / current_duration) * 1.25)
        return projected <= int(self.settings.max_generated_video_bytes)

    def _continuation_available(self, row: dict[str, Any]) -> bool:
        if row.get("status") != "ready":
            return False
        if (row.get("engine") or self.QUICK) != self.EXTENDABLE or row.get("provider") != "gemini":
            return False
        if row.get("resolution") != "720p" or not row.get("provider_asset_reference"):
            return False
        if not self._continuation_storage_safe(row):
            return False
        if int(row.get("sequence_index") or 0) >= 20 or int(row.get("duration_seconds") or 8) > 141:
            return False
        expires = row.get("provider_asset_expires_at")
        if not expires:
            return False
        try:
            parsed = datetime.fromisoformat(str(expires).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed > _now_dt()
        except ValueError:
            return False

    async def validate_continuation_parent(self, *, user_id: str, job_id: str) -> dict[str, Any]:
        row = await self.get(user_id=user_id, job_id=job_id)
        if not self._continuation_available(row):
            raise VideoServiceError(
                "This video can no longer be continued safely. Extendable clips use a short-lived provider reference and Ask Crump also stops before the next combined file is likely to exceed its private storage limit.",
                "VIDEO_CONTINUATION_UNAVAILABLE",
                409,
            )
        return row

    async def continue_video(
        self,
        *,
        user_id: str,
        parent_job_id: str,
        prompt: str,
        idempotency_key: str | None = None,
        charge_receipt: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        key = " ".join(str(idempotency_key or "").split()).strip()[:160] or None
        existing = await self._idempotent(user_id=user_id, key=key)
        if existing:
            return existing

        parent = await self.validate_continuation_parent(user_id=user_id, job_id=parent_job_id)
        await self._guard_concurrency(user_id=user_id)
        prompt = self.validate_prompt(prompt)
        guarded_prompt = self.provider_prompt(prompt, max_chars=4000)

        model = self.settings.gemini_video_extend_model
        parent_duration = int(parent.get("duration_seconds") or 8)
        parent_sequence = int(parent.get("sequence_index") or 0)
        root_job_id = str(parent.get("root_job_id") or parent.get("id"))
        job_id = str(uuid4())
        row = {
            "id": job_id,
            "user_id": user_id,
            "project_id": parent.get("project_id"),
            "kind": "video",
            "provider": "gemini",
            "provider_job_id": f"pending:{job_id}",
            "idempotency_key": key,
            "status": "queued",
            "prompt": prompt,
            "model": model,
            "aspect_ratio": parent.get("aspect_ratio") or "16:9",
            "resolution": "720p",
            "engine": self.EXTENDABLE,
            "operation_type": "extend",
            "parent_job_id": parent.get("id"),
            "root_job_id": root_job_id,
            "sequence_index": parent_sequence + 1,
            "duration_seconds": min(148, parent_duration + 7),
            "provider_asset_reference": None,
            "provider_asset_expires_at": None,
            "estimated_provider_cost_cents": self.provider_cost_cents(
                engine=self.EXTENDABLE,
                resolution="720p",
                duration_seconds=8,
                operation_type="extend",
            ),
            "file_id": None,
            "error_message": None,
            "billing_receipt": charge_receipt or {},
            "metadata": {"refundEligible": True, "providerAccepted": False},
            "updated_at": _now(),
        }
        inserted = await self.db.insert("media_jobs", row)
        row = (inserted or [row])[0]

        try:
            provider_job_id = await self.gemini.start(
                model=model,
                prompt=guarded_prompt,
                aspect_ratio=str(parent.get("aspect_ratio") or "16:9"),
                resolution="720p",
                duration_seconds=8,
                video_reference=str(parent.get("provider_asset_reference") or ""),
            )
        except ProviderError as exc:
            try:
                await self.db.update(
                    "media_jobs",
                    {
                        "status": "failed",
                        "error_message": exc.message[:500],
                        "estimated_provider_cost_cents": 0,
                        "metadata": {
                            **(row.get("metadata") or {}),
                            "providerAccepted": False,
                            "providerFailureCode": exc.failure_code or exc.code,
                            "refundEligible": bool(exc.refund_eligible),
                        },
                        "updated_at": _now(),
                    },
                    filters={"id": eq(job_id), "user_id": eq(user_id)},
                )
            except Exception:
                pass
            raise self._map_provider_error(exc) from exc

        try:
            updated = await self.db.update(
                "media_jobs",
                {
                    "provider_job_id": provider_job_id,
                    "status": "processing",
                    "metadata": {**(row.get("metadata") or {}), "providerAccepted": True},
                    "updated_at": _now(),
                },
                filters={"id": eq(job_id), "user_id": eq(user_id)},
            )
        except Exception as exc:
            raise VideoServiceError(
                "The video provider accepted the continuation, but Ask Crump could not persist its tracking state.",
                "VIDEO_JOB_TRACKING_FAILED",
                503,
                True,
                False,
            ) from exc
        if not updated:
            raise VideoServiceError(
                "The video provider accepted the continuation, but Ask Crump could not persist its tracking state.",
                "VIDEO_JOB_TRACKING_FAILED",
                503,
                True,
                False,
            )
        return updated[0]

    async def _mark_failed(
        self,
        *,
        user_id: str,
        row: dict[str, Any],
        message: str,
        failure_code: str | None = None,
        refund_eligible: bool = True,
    ) -> dict[str, Any]:
        metadata = {
            **(row.get("metadata") or {}),
            "providerFailureCode": failure_code,
            "refundEligible": bool(refund_eligible),
        }
        updated = await self.db.update(
            "media_jobs",
            {
                "status": "failed",
                "error_message": str(message or "Video delivery failed.")[:500],
                "metadata": metadata,
                "updated_at": _now(),
            },
            filters={"id": eq(row["id"]), "user_id": eq(user_id)},
        )
        return (updated or [{**row, "status": "failed", "error_message": message, "metadata": metadata}])[0]

    @staticmethod
    def refund_eligible(row: dict[str, Any]) -> bool:
        return bool((row.get("metadata") or {}).get("refundEligible", True))

    async def poll(self, *, user_id: str, job_id: str) -> dict[str, Any]:
        row = await self.get(user_id=user_id, job_id=job_id)
        if row.get("status") in {"ready", "failed"}:
            return row

        provider_name = str(row.get("provider") or "gemini").lower()
        provider = self.runway if provider_name == "runway" else self.gemini
        if not provider.enabled:
            raise VideoServiceError("Video generation is not configured.", "VIDEO_NOT_CONFIGURED", 503)

        try:
            result = await provider.poll(str(row.get("provider_job_id") or ""))
        except ProviderError as exc:
            raise self._map_provider_error(exc) from exc

        if result.get("status") == "processing":
            provider_status = result.get("providerStatus")
            if provider_status:
                metadata = {**(row.get("metadata") or {}), "providerStatus": provider_status}
                updated = await self.db.update(
                    "media_jobs",
                    {"metadata": metadata, "updated_at": _now()},
                    filters={"id": eq(row["id"]), "user_id": eq(user_id)},
                )
                return (updated or [row])[0]
            return row

        if result.get("status") == "failed":
            return await self._mark_failed(
                user_id=user_id,
                row=row,
                message=str(result.get("failureMessage") or "Video generation failed."),
                failure_code=str(result.get("failureCode") or "") or None,
                refund_eligible=bool(result.get("refundEligible", True)),
            )

        output_url = str(result.get("outputUrl") or "")
        if not output_url:
            return await self._mark_failed(
                user_id=user_id,
                row=row,
                message="The provider completed without a video file.",
            )

        try:
            data = await provider.download(output_url, max_bytes=self.settings.max_generated_video_bytes)
        except ProviderError as exc:
            return await self._mark_failed(
                user_id=user_id,
                row=row,
                message=exc.message,
                failure_code=exc.failure_code or exc.code,
                refund_eligible=exc.refund_eligible,
            )

        root_job_id = str(row.get("root_job_id") or row.get("id") or "")
        engine = str(row.get("engine") or self.QUICK)
        sequence_index = int(row.get("sequence_index") or 0)
        duration_seconds = int(row.get("duration_seconds") or 8)
        provider_asset_reference = str(result.get("providerAssetReference") or "") or None
        provider_asset_expires_at = _future(48) if provider_asset_reference and engine == self.EXTENDABLE else None

        try:
            file_row = await self.files.store_bytes(
                user_id=user_id,
                data=data,
                filename=f"crump-video-{row['id']}.mp4",
                mime_type="video/mp4",
                kind="generated_video",
                metadata={
                    "prompt": row.get("prompt"),
                    "provider": provider_name,
                    "model": row.get("model"),
                    "engine": engine,
                    "operationType": row.get("operation_type") or "generate",
                    "aspectRatio": row.get("aspect_ratio"),
                    "resolution": row.get("resolution"),
                    "durationSeconds": duration_seconds,
                    "mediaJobId": row.get("id"),
                    "rootJobId": root_job_id,
                    "sequenceIndex": sequence_index,
                    "continuable": engine == self.EXTENDABLE,
                    "attribution": "Powered by Runway" if provider_name == "runway" else None,
                },
            )
        except Exception:
            return await self._mark_failed(
                user_id=user_id,
                row=row,
                message="The video finished but Ask Crump could not save the file.",
            )

        metadata = {
            **(row.get("metadata") or {}),
            "providerCompleted": True,
            "refundEligible": False,
            "storedBytes": len(data),
        }
        updated = await self.db.update(
            "media_jobs",
            {
                "status": "ready",
                "file_id": file_row["id"],
                "provider_asset_reference": provider_asset_reference,
                "provider_asset_expires_at": provider_asset_expires_at,
                "metadata": metadata,
                "updated_at": _now(),
            },
            filters={"id": eq(row["id"]), "user_id": eq(user_id)},
        )
        return (updated or [{**row, "status": "ready", "file_id": file_row["id"]}])[0]

    async def public_job(self, *, user_id: str, row: dict[str, Any]) -> dict[str, Any]:
        payload = self._public_base(row)
        payload["canContinue"] = self._continuation_available(row)
        payload["continuationWindowHours"] = 48 if payload["canContinue"] else None
        payload["attribution"] = "Powered by Runway" if row.get("provider") == "runway" else None
        payload["attributionUrl"] = "https://runwayml.com" if row.get("provider") == "runway" else None
        file_id = row.get("file_id")
        if file_id:
            try:
                file_row = await self.files.get_owned(user_id=user_id, file_id=str(file_id))
                payload["file"] = self.files.public_file(file_row)
            except Exception:
                payload["file"] = None
        return payload
