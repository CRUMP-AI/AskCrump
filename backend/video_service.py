"""Provider-agnostic asynchronous video generation for Ask Crump."""
from __future__ import annotations

import base64
import warnings
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


def _parse_timestamp(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


_ISO_BMFF_MAX_BOXES = 16_384


def _iso_bmff_boxes(
    data: bytes,
    *,
    start: int = 0,
    end: int | None = None,
    budget: list[int] | None = None,
    allow_terminal_mdat: bool = False,
) -> list[tuple[bytes, int, int]] | None:
    """Parse one ISO-BMFF box level under a shared, copy-free work budget."""
    boundary = len(data) if end is None else end
    if start < 0 or boundary < start or boundary > len(data):
        return None
    remaining_budget = budget if budget is not None else [_ISO_BMFF_MAX_BOXES]

    boxes: list[tuple[bytes, int, int]] = []
    offset = start
    while offset < boundary:
        if remaining_budget[0] <= 0 or boundary - offset < 8:
            return None
        remaining_budget[0] -= 1
        short_size = int.from_bytes(data[offset : offset + 4], "big")
        box_type = data[offset + 4 : offset + 8]
        header_size = 8
        if short_size == 1:
            if boundary - offset < 16:
                return None
            box_size = int.from_bytes(data[offset + 8 : offset + 16], "big")
            header_size = 16
        elif short_size == 0:
            if not allow_terminal_mdat or box_type != b"mdat":
                return None
            box_size = boundary - offset
        else:
            box_size = short_size

        if box_type == b"uuid":
            header_size += 16

        if box_size < header_size or box_size > boundary - offset:
            return None
        box_end = offset + box_size
        boxes.append((box_type, offset + header_size, box_end))
        offset = box_end

    return boxes if offset == boundary else None


def _valid_video_movie_structure(
    data: bytes,
    *,
    moov_start: int,
    moov_end: int,
    budget: list[int],
) -> bool:
    """Require a canonical movie header and at least one declared video track."""
    movie_children = _iso_bmff_boxes(
        data,
        start=moov_start,
        end=moov_end,
        budget=budget,
    )
    if not movie_children:
        return False

    movie_headers = [box for box in movie_children if box[0] == b"mvhd"]
    tracks = [box for box in movie_children if box[0] == b"trak"]
    if len(movie_headers) != 1 or not tracks:
        return False

    _, header_start, header_end = movie_headers[0]
    if header_end <= header_start:
        return False
    version = data[header_start]
    minimum_header_size = 100 if version == 0 else 112 if version == 1 else 0
    if not minimum_header_size or header_end - header_start < minimum_header_size:
        return False
    timescale_start = header_start + (12 if version == 0 else 20)
    if int.from_bytes(data[timescale_start : timescale_start + 4], "big") == 0:
        return False

    has_video_track = False
    for _, track_start, track_end in tracks:
        track_children = _iso_bmff_boxes(
            data,
            start=track_start,
            end=track_end,
            budget=budget,
        )
        if not track_children:
            return False
        media_boxes = [box for box in track_children if box[0] == b"mdia"]
        if not media_boxes:
            return False
        for _, media_start, media_end in media_boxes:
            media_children = _iso_bmff_boxes(
                data,
                start=media_start,
                end=media_end,
                budget=budget,
            )
            if not media_children:
                return False
            for box_type, payload_start, payload_end in media_children:
                if (
                    box_type == b"hdlr"
                    and payload_end - payload_start >= 24
                    and data[payload_start + 8 : payload_start + 12] == b"vide"
                ):
                    has_video_track = True
    return has_video_track


@dataclass(slots=True)
class VideoServiceError(RuntimeError):
    message: str
    code: str = "VIDEO_ERROR"
    status_code: int = 400
    retryable: bool = False
    refund_eligible: bool = True
    failed_job_id: str | None = None

    def __post_init__(self) -> None:
        RuntimeError.__init__(self, self.message)


class VideoService:
    QUICK = "quick"
    EXTENDABLE = "extendable"
    CINEMATIC = "cinematic"
    ENGINES = {QUICK, EXTENDABLE, CINEMATIC}
    IDEMPOTENCY_KEY_MAX_LENGTH = 120
    HISTORICAL_IDEMPOTENCY_KEY_MAX_LENGTH = 160
    RESERVATION_LEASE_SECONDS = 5 * 60
    PROVIDER_READY_LEASE_SECONDS = 10 * 60
    PROVIDER_LAUNCH_LEASE_SECONDS = 2 * 60
    FINALIZATION_LEASE_SECONDS = 10 * 60
    FINALIZATION_MAX_AGE_SECONDS = 60 * 60
    PROCESSING_MAX_AGE_SECONDS = 24 * 60 * 60
    RECONCILIATION_BACKOFF_SECONDS = 10 * 60
    REFERENCE_IMAGE_MAX_BYTES = 20 * 1024 * 1024
    REFERENCE_IMAGE_MAX_EDGE = 2048
    REFERENCE_IMAGE_MAX_SOURCE_EDGE = 8192
    REFERENCE_IMAGE_MAX_PIXELS = 16_777_216
    REFERENCE_PLAN_VERSION = "video-reference-plan-v1"
    REFERENCE_ROLES = {
        "subject": "Subject / product",
        "mascot": "Mascot / character",
        "logo": "Logo / wordmark",
        "style": "Style / palette",
    }

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

    @classmethod
    def provider_prompt(
        cls,
        prompt: str,
        *,
        max_chars: int,
        reference_plan: list[dict[str, Any]] | None = None,
        reference_mode: str | None = None,
        has_visual_reference: bool = False,
    ) -> str:
        """Add bounded continuity/brand constraints without changing saved copy."""
        plan = list(reference_plan or [])
        role_lines: list[str] = []
        for index, item in enumerate(plan, start=1):
            role = str(item.get("role") or "").strip().lower() if isinstance(item, dict) else ""
            if role not in cls.REFERENCE_ROLES:
                raise VideoServiceError(
                    "Choose a valid role for every video reference.",
                    "INVALID_VIDEO_REFERENCE_PLAN",
                )
            role_lines.append(f"Input image {index}: {cls.REFERENCE_ROLES[role]} ({role}).")

        if role_lines:
            if reference_mode == "initial-frame":
                reference_guard = (
                    "The provider uses Input image 1 as the single starting frame, not as a loose mood board. "
                    f"{role_lines[0]} Preserve its composition and assigned visual identity as closely as the model allows."
                )
            else:
                reference_guard = (
                    "The provider uses these inputs as best-effort appearance guidance, not pixel-locked frames or layout "
                    f"templates. {' '.join(role_lines)} Apply each input only to its assigned role; do not merge or "
                    "substitute identities."
                )
            brand_guard = (
                f"{reference_guard} For a logo or wordmark, do not invent letters, redraw it in another style, or replace "
                "it with a similar symbol. Exact pixels and readable text are not guaranteed by video generation; leave "
                "the area clean for an approved overlay when exact branding is required."
            )
        elif has_visual_reference:
            # Compatibility for already-running callers while every new request
            # carries an indexed reference plan.
            brand_guard = (
                "Use the supplied visual reference to preserve the subject, product, colors, proportions, and visible "
                "mark as closely as the model allows; do not restyle the mark, add letters, or substitute symbols."
            )
        else:
            brand_guard = (
                "Never invent or approximate a logo, wordmark, label, or branded text. If an exact mark is not supplied "
                "as visual input, keep branding absent or out of frame."
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
    def reference_capability(cls, engine: Any) -> dict[str, str]:
        """Describe the provider semantics the user must review before spend."""
        normalized_engine = cls.validate_engine(engine)
        if normalized_engine == cls.EXTENDABLE:
            return {
                "provider": "gemini",
                "mode": "appearance-guidance",
                "fidelity": "best-effort-not-pixel-locked",
            }
        return {
            "provider": "runway" if normalized_engine == cls.CINEMATIC else "gemini",
            "mode": "initial-frame",
            "fidelity": "starting-frame-not-pixel-locked",
        }

    @classmethod
    def _normalize_reference_plan(
        cls,
        *,
        file_ids: Any,
        reference_plan: Any,
        engine: str,
    ) -> list[dict[str, str]]:
        """Validate reference identities, roles, count, and exact client order."""
        has_file_ids = file_ids is not None and file_ids != ""
        has_plan = reference_plan is not None
        if not has_file_ids and not has_plan:
            return []
        if has_file_ids and not isinstance(file_ids, list):
            raise VideoServiceError(
                "Video references must be selected from your private Files.",
                "INVALID_VIDEO_REFERENCE",
            )

        normalized_ids: list[str] = []
        for value in file_ids if isinstance(file_ids, list) else []:
            raw_file_id = str(value or "").strip()
            if not raw_file_id:
                raise VideoServiceError(
                    "One video reference is invalid. Remove it and upload the image again.",
                    "INVALID_VIDEO_REFERENCE",
                )
            try:
                file_id = normalize_chat_id(raw_file_id)
            except Exception as exc:
                raise VideoServiceError(
                    "One video reference is invalid. Remove it and upload the image again.",
                    "INVALID_VIDEO_REFERENCE",
                ) from exc
            if file_id in normalized_ids:
                raise VideoServiceError(
                    "Each video reference can appear only once.",
                    "INVALID_VIDEO_REFERENCE_PLAN",
                )
            normalized_ids.append(file_id)

        if has_plan:
            if not isinstance(reference_plan, list):
                raise VideoServiceError(
                    "Confirm one role for every selected video reference.",
                    "INVALID_VIDEO_REFERENCE_PLAN",
                )
            entries: list[dict[str, str]] = []
            plan_ids: list[str] = []
            for item in reference_plan:
                if not isinstance(item, dict):
                    raise VideoServiceError(
                        "Confirm one role for every selected video reference.",
                        "INVALID_VIDEO_REFERENCE_PLAN",
                    )
                raw_file_id = str(item.get("fileId") or "").strip()
                if not raw_file_id:
                    raise VideoServiceError(
                        "The video reference plan contains an invalid file.",
                        "INVALID_VIDEO_REFERENCE_PLAN",
                    )
                try:
                    file_id = normalize_chat_id(raw_file_id)
                except Exception as exc:
                    raise VideoServiceError(
                        "The video reference plan contains an invalid file.",
                        "INVALID_VIDEO_REFERENCE_PLAN",
                    ) from exc
                role = str(item.get("role") or "").strip().lower()
                if role not in cls.REFERENCE_ROLES or file_id in plan_ids:
                    raise VideoServiceError(
                        "Choose one valid, non-duplicate role assignment for every video reference.",
                        "INVALID_VIDEO_REFERENCE_PLAN",
                    )
                plan_ids.append(file_id)
                entries.append({"fileId": file_id, "role": role})
            if has_file_ids and plan_ids != normalized_ids:
                raise VideoServiceError(
                    "The video reference plan no longer matches the selected images or their order. Review it again.",
                    "INVALID_VIDEO_REFERENCE_PLAN",
                )
        else:
            # Legacy clients selected images without assigning roles. Keep them
            # working while treating each input as subject/product guidance.
            entries = [{"fileId": file_id, "role": "subject"} for file_id in normalized_ids]

        normalized_engine = cls.validate_engine(engine)
        limit = cls.reference_limit(normalized_engine)
        if len(entries) > limit:
            label = "Extendable" if normalized_engine == cls.EXTENDABLE else normalized_engine.title()
            raise VideoServiceError(
                f"{label} accepts up to {limit} reference image{'s' if limit != 1 else ''}.",
                "TOO_MANY_VIDEO_REFERENCES",
            )
        return entries

    @classmethod
    def normalize_reference_plan(
        cls,
        *,
        file_ids: Any,
        reference_plan: Any,
        engine: str,
        reference_confirmation: Any = None,
    ) -> list[dict[str, str]]:
        """Normalize references and enforce the reviewed request contract.

        Internal provider preparation uses ``_normalize_reference_plan`` after
        this public request-boundary check. That keeps already-normalized jobs
        resumable while preventing stale or direct creation callers from
        reserving or spending against an unreviewed reference plan.
        """
        no_charge_suffix = " Reopen Video Studio and confirm it again. No credits were used."
        try:
            entries = cls._normalize_reference_plan(
                file_ids=file_ids,
                reference_plan=reference_plan,
                engine=engine,
            )
        except VideoServiceError as exc:
            if exc.code == "INVALID_VIDEO_REFERENCE_PLAN":
                raise VideoServiceError(
                    "The video reference order or role assignments no longer match the reviewed plan."
                    + no_charge_suffix,
                    "VIDEO_REFERENCE_CONFIRMATION_STALE",
                    409,
                    False,
                    False,
                ) from exc
            raise
        if not entries:
            return []

        if not isinstance(reference_plan, list) or not isinstance(reference_confirmation, dict):
            raise VideoServiceError(
                "Review the ordered video reference plan before creating." + no_charge_suffix,
                "VIDEO_REFERENCE_CONFIRMATION_REQUIRED",
                409,
                False,
                False,
            )
        if reference_confirmation.get("confirmed") is not True:
            raise VideoServiceError(
                "The video reference plan has not been confirmed." + no_charge_suffix,
                "VIDEO_REFERENCE_CONFIRMATION_REQUIRED",
                409,
                False,
                False,
            )

        normalized_engine = cls.validate_engine(engine)
        expected_capability = cls.reference_capability(normalized_engine)
        expected_ids = [item["fileId"] for item in entries]
        expected_confirmation = {
            "version": cls.REFERENCE_PLAN_VERSION,
            "confirmed": True,
            "engine": normalized_engine,
            "capability": expected_capability,
            "fileIds": expected_ids,
            "referencePlan": entries,
        }
        if reference_confirmation != expected_confirmation:
            raise VideoServiceError(
                "The confirmed video reference plan is stale or no longer matches the selected order, roles, engine, provider, or reference mode."
                + no_charge_suffix,
                "VIDEO_REFERENCE_CONFIRMATION_STALE",
                409,
                False,
                False,
            )
        return entries

    @staticmethod
    def normalize_request_fingerprint(value: Any) -> str:
        fingerprint = str(value or "").strip().lower()
        if len(fingerprint) != 64 or any(
            character not in "0123456789abcdef" for character in fingerprint
        ):
            raise VideoServiceError(
                "This video request could not be identified safely. Start it again.",
                "VIDEO_REQUEST_FINGERPRINT_REQUIRED",
                400,
            )
        return fingerprint

    @classmethod
    def normalize_rpc_idempotency_key(cls, value: Any) -> str:
        """Preserve a validated historical key when addressing an existing row."""
        key = str(value or "").strip()
        if not key or len(key) > cls.HISTORICAL_IDEMPOTENCY_KEY_MAX_LENGTH:
            raise VideoServiceError(
                "This saved video request could not be identified safely.",
                "VIDEO_REQUEST_IDENTITY_INVALID",
                409,
                False,
                False,
            )
        return key

    @classmethod
    def reference_receipt(cls, references: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
        """Return the bounded, byte-free role receipt safe to persist and expose."""
        receipt: list[dict[str, Any]] = []
        seen: set[str] = set()
        for index, reference in enumerate(references or [], start=1):
            if not isinstance(reference, dict):
                raise VideoServiceError(
                    "The video reference plan is invalid.",
                    "INVALID_VIDEO_REFERENCE_PLAN",
                )
            raw_file_id = str(reference.get("fileId") or "").strip()
            if not raw_file_id:
                raise VideoServiceError(
                    "The video reference plan contains an invalid file.",
                    "INVALID_VIDEO_REFERENCE_PLAN",
                )
            try:
                file_id = normalize_chat_id(raw_file_id)
            except Exception as exc:
                raise VideoServiceError(
                    "The video reference plan contains an invalid file.",
                    "INVALID_VIDEO_REFERENCE_PLAN",
                ) from exc
            role = str(reference.get("role") or "subject").strip().lower()
            if role not in cls.REFERENCE_ROLES or file_id in seen:
                raise VideoServiceError(
                    "The video reference plan is invalid.",
                    "INVALID_VIDEO_REFERENCE_PLAN",
                )
            seen.add(file_id)
            receipt.append({"input": index, "fileId": file_id, "role": role})
        return receipt

    @classmethod
    def prepare_provider_prompt(
        cls,
        *,
        prompt: Any,
        engine: Any,
        references: list[dict[str, Any]] | None,
    ) -> tuple[str, str, list[dict[str, Any]], str | None]:
        """Validate the final reference-expanded prompt before any credit or provider spend."""
        normalized_engine = cls.validate_engine(engine)
        prepared_references = list(references or [])
        limit = cls.reference_limit(normalized_engine)
        if len(prepared_references) > limit:
            raise VideoServiceError(
                f"This video engine accepts up to {limit} reference image{'s' if limit != 1 else ''}.",
                "TOO_MANY_VIDEO_REFERENCES",
            )
        provider_prompt_limit = 1000 if normalized_engine == cls.CINEMATIC else 4000
        validated_prompt = cls.validate_prompt(prompt, max_chars=provider_prompt_limit)
        reference_receipt = cls.reference_receipt(prepared_references)
        reference_mode = (
            "appearance-guidance"
            if prepared_references and normalized_engine == cls.EXTENDABLE
            else "initial-frame" if prepared_references
            else None
        )
        guarded_prompt = cls.provider_prompt(
            validated_prompt,
            max_chars=provider_prompt_limit,
            reference_plan=reference_receipt,
            reference_mode=reference_mode,
        )
        return validated_prompt, guarded_prompt, reference_receipt, reference_mode

    @classmethod
    def _prepare_reference_image(cls, data: bytes) -> tuple[str, str]:
        """Decode one private upload into a bounded provider-safe PNG payload."""
        try:
            # Pillow emits DecompressionBombWarning from Image.open before a
            # caller can inspect dimensions. Promote it to an exception inside
            # this narrow decoder scope, then perform our stricter app-owned
            # edge/pixel/frame preflight before transpose or pixel loading.
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(BytesIO(data)) as source:
                    width, height = source.size
                    frame_count = int(getattr(source, "n_frames", 1) or 1)
                    if (
                        width <= 0
                        or height <= 0
                        or frame_count != 1
                        or max(width, height) > cls.REFERENCE_IMAGE_MAX_SOURCE_EDGE
                        or width * height > cls.REFERENCE_IMAGE_MAX_PIXELS
                    ):
                        raise VideoServiceError(
                            "That reference image is too large or complex to decode "
                            "safely. Use one still image under 16 megapixels.",
                            "VIDEO_REFERENCE_IMAGE_TOO_LARGE",
                            413,
                        )
                    source.seek(0)
                    image = ImageOps.exif_transpose(source)
                    image.load()
                    image = image.copy()
        except VideoServiceError:
            raise
        except (Image.DecompressionBombWarning, Image.DecompressionBombError) as exc:
            raise VideoServiceError(
                "That reference image is too large or complex to decode "
                "safely. Use one still image under 16 megapixels.",
                "VIDEO_REFERENCE_IMAGE_TOO_LARGE",
                413,
            ) from exc
        except (UnidentifiedImageError, OSError, ValueError) as exc:
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
        reference_plan: Any = None,
        engine: str,
    ) -> list[dict[str, str]]:
        """Resolve owner-scoped Files before credits or provider spend."""
        entries = self._normalize_reference_plan(
            file_ids=file_ids,
            reference_plan=reference_plan,
            engine=engine,
        )
        owned: list[tuple[dict[str, str], dict[str, Any]]] = []
        for entry in entries:
            file_id = entry["fileId"]
            try:
                row = await self.files.get_owned(user_id=user_id, file_id=file_id)
            except FileServiceError as exc:
                raise VideoServiceError(
                    "A selected video reference is unavailable. Remove it and upload the image again.",
                    "VIDEO_REFERENCE_UNAVAILABLE",
                    exc.status_code,
                    exc.status_code >= 500,
                ) from exc
            if str(row.get("id") or "") != file_id:
                raise VideoServiceError(
                    "A selected video reference is unavailable. Remove it and upload the image again.",
                    "VIDEO_REFERENCE_UNAVAILABLE",
                    404,
                )
            if not str(row.get("mime_type") or "").lower().startswith("image/"):
                raise VideoServiceError(
                    "Video references must be JPG, PNG, or WebP images.",
                    "INVALID_VIDEO_REFERENCE_IMAGE",
                )
            owned.append((entry, row))

        prepared: list[dict[str, str]] = []
        for entry, row in owned:
            try:
                raw = await self.files.download_bytes(row=row, max_bytes=self.REFERENCE_IMAGE_MAX_BYTES)
            except FileServiceError as exc:
                raise VideoServiceError(
                    "A selected video reference is unavailable. Remove it and upload the image again.",
                    "VIDEO_REFERENCE_UNAVAILABLE",
                    exc.status_code,
                    exc.status_code >= 500,
                ) from exc
            mime_type, encoded = self._prepare_reference_image(raw)
            prepared.append({
                "fileId": entry["fileId"],
                "role": entry["role"],
                "mimeType": mime_type,
                "data": encoded,
            })
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

    async def authorize_reservation_capacity(
        self,
        *,
        user_id: str,
        row: dict[str, Any],
        reservation_token: str,
        bypass_user_budget: bool = False,
    ) -> dict[str, Any]:
        """Settle prior owner billing, then serialize capacity before billing.

        The earlier read-only checks remain useful for fast feedback, but this
        RPC is decisive: all concurrent requests share one transaction lock.
        An owner-scoped settlement first removes expired included usage or
        returns credits from interrupted older jobs so the next billing choice
        cannot charge against stale allowance state. A denial deletes only
        this exact, still-unbilled reservation.
        """
        job_id = str(row.get("id") or "")

        async def release_after_failed_settlement() -> None:
            try:
                await self.release_unbilled_reservation(
                    user_id=user_id,
                    job_id=job_id,
                    idempotency_key=str(row.get("idempotency_key") or ""),
                    request_fingerprint=str(row.get("request_fingerprint") or ""),
                    reservation_token=reservation_token,
                )
            except Exception:
                # The reservation lease remains a bounded database recovery
                # fence even if this best-effort cleanup response is lost.
                pass

        try:
            settlement = await self.sweep_expired_leases(
                limit=500,
                user_id=user_id,
            )
        except Exception as exc:
            await release_after_failed_settlement()
            raise VideoServiceError(
                "Ask Crump is still settling an earlier video safely. Retry "
                "this request shortly.",
                "VIDEO_PREBILLING_SETTLEMENT_PENDING",
                503,
                True,
                False,
                job_id or None,
            ) from exc

        if (
            settlement.get("outcome") != "completed"
            or int(settlement.get("errors") or 0) > 0
            or int(settlement.get("scanned") or 0) >= 500
        ):
            await release_after_failed_settlement()
            raise VideoServiceError(
                "Ask Crump is still settling an earlier video safely. Retry "
                "this request shortly.",
                "VIDEO_PREBILLING_SETTLEMENT_PENDING",
                503,
                True,
                False,
                job_id or None,
            )

        try:
            result = await self.db.rpc(
                "authorize_video_reservation_capacity",
                {
                    "p_user_id": user_id,
                    "p_job_id": job_id,
                    "p_idempotency_key": self.normalize_rpc_idempotency_key(
                        row.get("idempotency_key")
                    ),
                    "p_request_fingerprint": self.normalize_request_fingerprint(
                        row.get("request_fingerprint")
                    ),
                    "p_reservation_token": str(reservation_token or "")[:128],
                    "p_max_active_jobs": int(
                        self.settings.max_active_video_jobs_per_user
                    ),
                    "p_global_daily_budget_cents": int(
                        self.settings.video_daily_provider_budget_cents or 0
                    ),
                    "p_user_daily_budget_cents": int(
                        self.settings.video_user_daily_provider_budget_cents or 0
                    ),
                    "p_runway_monthly_budget_cents": int(
                        self.settings.runway_monthly_provider_budget_cents or 0
                    ),
                    "p_bypass_user_budget": bool(bypass_user_budget),
                },
                retry_transient=True,
            )
        except VideoServiceError:
            raise
        except Exception as exc:
            raise VideoServiceError(
                "Ask Crump could not confirm video capacity safely. Retry with "
                "the same request key.",
                "VIDEO_CAPACITY_STATE_UNAVAILABLE",
                503,
                True,
                False,
                job_id or None,
            ) from exc

        outcome, current = self._rpc_job(result)
        if outcome in {"authorized", "existing"} and current:
            return current
        if outcome == "concurrency_limit":
            raise VideoServiceError(
                "Wait for the current video job to finish before starting another.",
                "VIDEO_CONCURRENCY_LIMIT",
                429,
                True,
                False,
                job_id or None,
            )
        if outcome == "global_budget":
            raise VideoServiceError(
                "Ask Crump's video provider budget is temporarily paused for today.",
                "VIDEO_PROVIDER_BUDGET_PAUSED",
                503,
                False,
                False,
                job_id or None,
            )
        if outcome == "user_budget":
            raise VideoServiceError(
                "You've reached today's video generation safety limit. Try again tomorrow.",
                "VIDEO_USER_PROVIDER_BUDGET_LIMIT",
                429,
                False,
                False,
                job_id or None,
            )
        if outcome == "runway_budget":
            raise VideoServiceError(
                "Cinematic video is temporarily paused while the provider budget resets.",
                "RUNWAY_PROVIDER_BUDGET_PAUSED",
                503,
                False,
                False,
                job_id or None,
            )
        raise VideoServiceError(
            "This video reservation could not be matched to its protected "
            "capacity decision. Retry with the same request key.",
            (
                "VIDEO_CAPACITY_RESERVATION_CONFLICT"
                if outcome in {
                    "reservation_missing",
                    "request_conflict",
                    "reservation_conflict",
                }
                else "VIDEO_CAPACITY_STATE_UNAVAILABLE"
            ),
            409 if outcome in {
                "reservation_missing",
                "request_conflict",
                "reservation_conflict",
            } else 503,
            outcome not in {
                "reservation_missing",
                "request_conflict",
                "reservation_conflict",
            },
            False,
            job_id or None,
        )

    @staticmethod
    def _public_base(row: dict[str, Any]) -> dict[str, Any]:
        metadata = row.get("metadata") or {}
        safe_reference_plan = []
        for index, item in enumerate(metadata.get("referencePlan") or [], start=1):
            if not isinstance(item, dict):
                continue
            role = str(item.get("role") or "").strip().lower()
            file_id = str(item.get("fileId") or "").strip()
            if role in VideoService.REFERENCE_ROLES and file_id:
                safe_reference_plan.append({
                    "input": index,
                    "fileId": file_id[:64],
                    "role": role,
                })
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
            "referenceMode": metadata.get("referenceMode"),
            "referencePlan": safe_reference_plan,
            "referenceVerification": "not-performed" if safe_reference_plan else None,
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
            columns=(
                "id,status,provider_job_id,idempotency_key,request_fingerprint,"
                "video_phase,lease_token,lease_expires_at,provider_started_at,"
                "finalization_started_at,metadata"
            ),
            filters={"user_id": eq(user_id), "kind": eq("video")},
            order="created_at.desc",
            limit=20,
        )
        reconciled: list[dict[str, Any]] = []
        for row in rows:
            if (
                row.get("status") == "queued"
                and str(row.get("provider_job_id") or "").startswith("pending:")
            ):
                try:
                    _, row, _ = await self._claim_provider_launch(
                        user_id=user_id,
                        row=row,
                        claim_ready=False,
                    )
                except Exception:
                    # A transient reconciliation failure must not weaken the
                    # concurrency guard. Keep counting the unresolved row.
                    pass
            reconciled.append(row)
        now = _now_dt()
        active: list[dict[str, Any]] = []
        for row in reconciled:
            if row.get("status") not in {"queued", "processing"}:
                continue
            if self._past_absolute_horizon(row, now=now):
                continue
            active.append(row)
        return len(active)

    def _past_absolute_horizon(
        self,
        row: dict[str, Any],
        *,
        now: datetime | None = None,
    ) -> bool:
        phase = str(row.get("video_phase") or "")
        current = now or _now_dt()
        if phase == "processing":
            started = _parse_timestamp(row.get("provider_started_at"))
            return bool(
                started
                and started
                <= current - timedelta(seconds=self.PROCESSING_MAX_AGE_SECONDS)
            )
        if phase == "finalizing":
            started = _parse_timestamp(row.get("finalization_started_at"))
            return bool(
                started
                and started
                <= current - timedelta(seconds=self.FINALIZATION_MAX_AGE_SECONDS)
            )
        return False

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

    async def _reserve_job_row(
        self,
        *,
        user_id: str,
        key: str | None,
        row: dict[str, Any],
    ) -> tuple[dict[str, Any], bool]:
        """Insert before provider work and resolve same-key insert races safely."""
        try:
            inserted = await self.db.insert("media_jobs", row)
        except Exception as exc:
            try:
                existing = await self._idempotent(user_id=user_id, key=key)
            except Exception:
                existing = None
            if existing:
                return existing, True
            raise VideoServiceError(
                "The video request could not reserve its tracking record yet. Retry with the same request.",
                "VIDEO_JOB_RESERVATION_FAILED",
                503,
                True,
                False,
            ) from exc
        return (inserted or [row])[0], False

    async def release_unbilled_reservation(
        self,
        *,
        user_id: str,
        job_id: str,
        idempotency_key: str,
        request_fingerprint: str,
        reservation_token: str,
    ) -> bool:
        """Atomically terminalize only the caller's unbilled reservation."""
        result = await self.db.rpc(
            "release_video_reservation",
            {
                "p_user_id": user_id,
                "p_job_id": job_id,
                "p_idempotency_key": self.normalize_rpc_idempotency_key(
                    idempotency_key
                ),
                "p_request_fingerprint": self.normalize_request_fingerprint(
                    request_fingerprint
                ),
                "p_reservation_token": str(reservation_token or "")[:128],
                "p_message": (
                    "This video request stopped before any allowance or credits "
                    "were used."
                ),
            },
            retry_transient=True,
        )
        item = result[0] if isinstance(result, list) and result else (result or {})
        return str(item.get("outcome") or "") in {"released", "missing"}

    @staticmethod
    def _rpc_job(result: Any) -> tuple[str, dict[str, Any]]:
        item = (
            result[0]
            if isinstance(result, list) and result
            else (result or {})
        )
        row = item.get("job") if isinstance(item, dict) else None
        return str(item.get("outcome") or ""), row if isinstance(row, dict) else {}

    async def _claim_provider_launch(
        self,
        *,
        user_id: str,
        row: dict[str, Any],
        claim_ready: bool,
    ) -> tuple[str, dict[str, Any], str | None]:
        launch_token = str(uuid4()) if claim_ready else ""
        try:
            result = await self.db.rpc(
                "claim_video_provider_launch",
                {
                    "p_user_id": user_id,
                    "p_job_id": str(row.get("id") or ""),
                    "p_idempotency_key": self.normalize_rpc_idempotency_key(
                        row.get("idempotency_key")
                    ),
                    "p_request_fingerprint": self.normalize_request_fingerprint(
                        row.get("request_fingerprint")
                    ),
                    "p_launch_token": launch_token,
                    "p_lease_seconds": self.PROVIDER_LAUNCH_LEASE_SECONDS,
                    "p_claim_ready": bool(claim_ready),
                },
                retry_transient=True,
            )
        except VideoServiceError:
            raise
        except Exception as exc:
            raise VideoServiceError(
                "Ask Crump could not confirm this video's launch state safely. "
                "Retry with the same request key.",
                "VIDEO_JOB_STATE_UNAVAILABLE",
                503,
                True,
                False,
                str(row.get("id") or "") or None,
            ) from exc
        outcome, current = self._rpc_job(result)
        return outcome, current or row, launch_token if outcome == "claimed" else None

    async def _complete_provider_launch(
        self,
        *,
        user_id: str,
        row: dict[str, Any],
        launch_token: str,
        provider_job_id: str,
    ) -> dict[str, Any]:
        job_id = str(row.get("id") or "")
        try:
            result = await self.db.rpc(
                "complete_video_provider_launch",
                {
                    "p_user_id": user_id,
                    "p_job_id": job_id,
                    "p_idempotency_key": self.normalize_rpc_idempotency_key(
                        row.get("idempotency_key")
                    ),
                    "p_request_fingerprint": self.normalize_request_fingerprint(
                        row.get("request_fingerprint")
                    ),
                    "p_launch_token": launch_token,
                    "p_provider_job_id": provider_job_id,
                },
                retry_transient=True,
            )
        except Exception as exc:
            raise VideoServiceError(
                "The provider accepted the video, but Ask Crump could not bind "
                "its tracking identifier safely. The launch will be reconciled "
                "without starting a duplicate.",
                "VIDEO_JOB_TRACKING_FAILED",
                503,
                True,
                False,
                job_id,
            ) from exc
        outcome, row = self._rpc_job(result)
        if outcome not in {"completed", "existing"} or not row:
            raise VideoServiceError(
                "The provider accepted the video, but Ask Crump could not bind "
                "its tracking identifier safely. The launch will be reconciled "
                "without starting a duplicate.",
                "VIDEO_JOB_TRACKING_FAILED",
                503,
                True,
                False,
                job_id,
            )
        return row

    async def _fail_provider_launch(
        self,
        *,
        user_id: str,
        row: dict[str, Any],
        launch_token: str,
        exc: ProviderError | VideoServiceError,
        acceptance: str,
    ) -> dict[str, Any]:
        result = await self.db.rpc(
            "fail_video_provider_launch",
            {
                "p_user_id": user_id,
                "p_job_id": str(row.get("id") or ""),
                "p_idempotency_key": self.normalize_rpc_idempotency_key(
                    row.get("idempotency_key")
                ),
                "p_request_fingerprint": self.normalize_request_fingerprint(
                    row.get("request_fingerprint")
                ),
                "p_launch_token": launch_token,
                "p_message": str(exc.message or "Video generation failed.")[:500],
                "p_failure_code": str(
                    getattr(exc, "failure_code", None) or exc.code or ""
                )[:120],
                "p_refund_eligible": bool(exc.refund_eligible),
                "p_provider_acceptance": acceptance,
            },
            retry_transient=True,
        )
        outcome, current = self._rpc_job(result)
        if outcome in {"failed", "existing"} and current:
            return current
        raise VideoServiceError(
            "Ask Crump is still reconciling this video launch safely. Check "
            "its status again shortly.",
            "VIDEO_JOB_STATE_UNAVAILABLE",
            503,
            True,
            False,
            str(row.get("id") or "") or None,
        )

    async def _claim_finalization(
        self,
        *,
        user_id: str,
        row: dict[str, Any],
        terminal_outcome: str,
        refund_eligible: bool = True,
    ) -> tuple[str, dict[str, Any], str | None]:
        token = str(uuid4())
        try:
            result = await self.db.rpc(
                "claim_video_finalization",
                {
                    "p_user_id": user_id,
                    "p_job_id": str(row.get("id") or ""),
                    "p_idempotency_key": self.normalize_rpc_idempotency_key(
                        row.get("idempotency_key")
                    ),
                    "p_request_fingerprint": self.normalize_request_fingerprint(
                        row.get("request_fingerprint")
                    ),
                    "p_finalization_token": token,
                    "p_lease_seconds": self.FINALIZATION_LEASE_SECONDS,
                    "p_terminal_outcome": terminal_outcome,
                    "p_refund_eligible": bool(refund_eligible),
                },
                retry_transient=True,
            )
        except Exception as exc:
            raise VideoServiceError(
                "Ask Crump could not claim this completed video safely yet. "
                "The provider job remains tracked; try the status again.",
                "VIDEO_FINALIZATION_STATE_UNAVAILABLE",
                503,
                True,
                False,
                str(row.get("id") or "") or None,
            ) from exc
        outcome, current = self._rpc_job(result)
        return outcome, current or row, token if outcome == "claimed" else None

    async def _complete_finalization(
        self,
        *,
        user_id: str,
        row: dict[str, Any],
        finalization_token: str,
        file_id: str,
        provider_asset_reference: str | None,
        provider_asset_expires_at: str | None,
        stored_bytes: int,
        file_metadata: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            result = await self.db.rpc(
                "complete_video_finalization",
                {
                    "p_user_id": user_id,
                    "p_job_id": str(row.get("id") or ""),
                    "p_idempotency_key": self.normalize_rpc_idempotency_key(
                        row.get("idempotency_key")
                    ),
                    "p_request_fingerprint": self.normalize_request_fingerprint(
                        row.get("request_fingerprint")
                    ),
                    "p_finalization_token": finalization_token,
                    "p_file_id": file_id,
                    "p_provider_asset_reference": provider_asset_reference,
                    "p_provider_asset_expires_at": provider_asset_expires_at,
                    "p_stored_bytes": max(0, int(stored_bytes or 0)),
                    "p_file_metadata": file_metadata,
                },
                retry_transient=True,
            )
        except Exception as exc:
            raise VideoServiceError(
                "The completed video is stored, but its final receipt is still "
                "being reconciled. Check its status again shortly.",
                "VIDEO_FINALIZATION_STATE_UNAVAILABLE",
                503,
                True,
                False,
                str(row.get("id") or "") or None,
            ) from exc
        outcome, current = self._rpc_job(result)
        if outcome in {"completed", "existing"} and current:
            return current
        raise VideoServiceError(
            "The completed video is stored, but its final receipt is still "
            "being reconciled. Check its status again shortly.",
            "VIDEO_FINALIZATION_STATE_UNAVAILABLE",
            503,
            True,
            False,
            str(row.get("id") or "") or None,
        )

    async def _fail_finalization(
        self,
        *,
        user_id: str,
        row: dict[str, Any],
        finalization_token: str,
        message: str,
        failure_code: str | None,
        refund_eligible: bool = True,
    ) -> dict[str, Any]:
        try:
            result = await self.db.rpc(
                "fail_video_finalization",
                {
                    "p_user_id": user_id,
                    "p_job_id": str(row.get("id") or ""),
                    "p_idempotency_key": self.normalize_rpc_idempotency_key(
                        row.get("idempotency_key")
                    ),
                    "p_request_fingerprint": self.normalize_request_fingerprint(
                        row.get("request_fingerprint")
                    ),
                    "p_finalization_token": finalization_token,
                    "p_message": str(message or "Video delivery failed.")[:500],
                    "p_failure_code": str(failure_code or "")[:120],
                    "p_refund_eligible": bool(refund_eligible),
                },
                retry_transient=True,
            )
        except Exception as exc:
            raise VideoServiceError(
                "Ask Crump is still reconciling this failed video safely. "
                "Check its status again shortly.",
                "VIDEO_FINALIZATION_STATE_UNAVAILABLE",
                503,
                True,
                False,
                str(row.get("id") or "") or None,
            ) from exc
        outcome, current = self._rpc_job(result)
        if outcome in {"failed", "existing"} and current:
            return current
        raise VideoServiceError(
            "Ask Crump is still reconciling this failed video safely. Check "
            "its status again shortly.",
            "VIDEO_FINALIZATION_STATE_UNAVAILABLE",
            503,
            True,
            False,
            str(row.get("id") or "") or None,
        )

    async def sweep_expired_leases(
        self,
        *,
        limit: int = 100,
        user_id: str | None = None,
        job_id: str | None = None,
    ) -> dict[str, Any]:
        """Settle expired video leases without launching a provider task."""
        bounded_limit = max(1, min(500, int(limit or 100)))
        payload: dict[str, Any] = {"p_limit": bounded_limit}
        if user_id is not None or job_id is not None:
            if not user_id or (job_id is not None and not job_id):
                raise VideoServiceError(
                    "Video recovery requires an owner; an exact recovery also "
                    "requires a job identity.",
                    "VIDEO_LEASE_SWEEP_IDENTITY_INVALID",
                    400,
                )
            payload["p_user_id"] = user_id
            if job_id is not None:
                payload["p_job_id"] = job_id
        try:
            result = await self.db.rpc(
                "sweep_expired_video_leases",
                payload,
                retry_transient=True,
            )
        except Exception as exc:
            raise VideoServiceError(
                "Expired video work could not be reconciled yet.",
                "VIDEO_LEASE_SWEEP_UNAVAILABLE",
                503,
                True,
                False,
            ) from exc
        item = result[0] if isinstance(result, list) and result else (result or {})
        return {
            "outcome": str(item.get("outcome") or "completed"),
            "scanned": max(0, int(item.get("scanned") or 0)),
            "released": max(0, int(item.get("released") or 0)),
            "completed": max(0, int(item.get("completed") or 0)),
            "failed": max(0, int(item.get("failed") or 0)),
            "refunded": max(0, int(item.get("refunded") or 0)),
            "errors": max(0, int(item.get("errors") or 0)),
        }

    async def reconcile_stale_processing(
        self,
        *,
        limit: int = 10,
        stale_seconds: int = 120,
    ) -> dict[str, int]:
        """Advance a bounded set of provider jobs after the browser goes away.

        Only job and owner identifiers cross this scheduler boundary. Each job
        is isolated so a provider outage or malformed historical row cannot
        prevent the rest of the batch from being checked. Existing token-fenced
        finalization keeps browser and scheduler polls safe when they overlap.
        """
        bounded_limit = max(1, min(25, int(limit or 10)))
        bounded_stale_seconds = max(60, min(3600, int(stale_seconds or 120)))
        try:
            result = await self.db.rpc(
                "claim_video_reconciliation_batch",
                {
                    "p_limit": bounded_limit,
                    "p_stale_seconds": bounded_stale_seconds,
                    "p_backoff_seconds": self.RECONCILIATION_BACKOFF_SECONDS,
                },
                retry_transient=True,
            )
            rows = result if isinstance(result, list) else []
        except Exception as exc:
            raise VideoServiceError(
                "Processing video jobs could not be reconciled yet.",
                "VIDEO_PROCESSING_RECONCILIATION_UNAVAILABLE",
                503,
                True,
                False,
            ) from exc

        summary = {
            "scanned": len(rows),
            "processing": 0,
            "ready": 0,
            "failed": 0,
            "retryable": 0,
            "errors": 0,
        }
        for item in rows:
            job_id = str(item.get("id") or "").strip()
            owner_id = str(item.get("user_id") or "").strip()
            if not job_id or not owner_id:
                summary["errors"] += 1
                continue
            try:
                row = await self.poll(user_id=owner_id, job_id=job_id)
            except VideoServiceError as exc:
                summary["errors"] += 1
                if exc.retryable:
                    summary["retryable"] += 1
                continue
            except Exception:
                summary["errors"] += 1
                continue
            status = str(row.get("status") or "processing")
            if status == "ready":
                summary["ready"] += 1
            elif status == "failed":
                summary["failed"] += 1
            else:
                summary["processing"] += 1
        return summary

    async def list_recent(self, *, user_id: str, limit: int = 12) -> list[dict[str, Any]]:
        """Return only this owner's newest video rows for resume/history UI."""
        bounded_limit = max(1, min(20, int(limit or 12)))
        return await self.db.select(
            "media_jobs",
            filters={"user_id": eq(user_id), "kind": eq("video")},
            order="created_at.desc",
            limit=bounded_limit,
        )

    async def _launch_reserved_job(
        self,
        *,
        user_id: str,
        row: dict[str, Any],
        references: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Claim exactly one provider launch, then bind or terminally reconcile it."""
        outcome, claimed, launch_token = await self._claim_provider_launch(
            user_id=user_id,
            row=row,
            claim_ready=True,
        )
        if outcome != "claimed" or not launch_token:
            return claimed

        job_id = str(claimed.get("id") or row.get("id") or "")
        operation_type = str(claimed.get("operation_type") or "generate")
        engine = str(claimed.get("engine") or self.QUICK)
        provider = str(claimed.get("provider") or "gemini")
        model = str(claimed.get("model") or "")
        aspect_ratio = str(claimed.get("aspect_ratio") or "16:9")
        resolution = str(claimed.get("resolution") or "720p")
        duration_seconds = int(claimed.get("duration_seconds") or 8)
        metadata = claimed.get("metadata") or {}

        try:
            if operation_type == "extend":
                parent = await self.validate_continuation_parent(
                    user_id=user_id,
                    job_id=str(claimed.get("parent_job_id") or ""),
                )
                guarded_prompt = self.provider_prompt(
                    self.validate_prompt(claimed.get("prompt"), max_chars=4000),
                    max_chars=4000,
                )
                provider_job_id = await self.gemini.start(
                    model=model,
                    prompt=guarded_prompt,
                    aspect_ratio=aspect_ratio,
                    resolution="720p",
                    duration_seconds=8,
                    video_reference=str(
                        parent.get("provider_asset_reference") or ""
                    ),
                )
            else:
                prepared_references = list(references or [])
                if references is None:
                    reference_plan = metadata.get("referencePlan") or []
                    prepared_references = await self.prepare_reference_images(
                        user_id=user_id,
                        file_ids=[
                            item.get("fileId")
                            for item in reference_plan
                            if isinstance(item, dict)
                        ],
                        reference_plan=reference_plan,
                        engine=engine,
                    )
                _, guarded_prompt, receipt, _ = self.prepare_provider_prompt(
                    prompt=claimed.get("prompt"),
                    engine=engine,
                    references=prepared_references,
                )
                if receipt != (metadata.get("referencePlan") or []):
                    raise VideoServiceError(
                        "The saved reference plan no longer matches this video "
                        "request. The generation charge was returned.",
                        "VIDEO_RESERVATION_MISMATCH",
                        409,
                        False,
                        True,
                    )
                if provider == "runway":
                    provider_job_id = await self.runway.start(
                        model=model,
                        prompt=guarded_prompt,
                        aspect_ratio=aspect_ratio,
                        duration_seconds=duration_seconds,
                        prompt_image=(
                            "data:"
                            f"{prepared_references[0]['mimeType']};base64,"
                            f"{prepared_references[0]['data']}"
                            if prepared_references
                            else None
                        ),
                    )
                else:
                    provider_job_id = await self.gemini.start(
                        model=model,
                        prompt=guarded_prompt,
                        aspect_ratio=aspect_ratio,
                        resolution=resolution,
                        duration_seconds=duration_seconds,
                        initial_image=(
                            prepared_references[0]
                            if prepared_references and engine == self.QUICK
                            else None
                        ),
                        reference_images=(
                            prepared_references
                            if engine == self.EXTENDABLE
                            else None
                        ),
                    )
        except ProviderError as exc:
            acceptance = "unknown" if exc.acceptance_unknown else "rejected"
            try:
                await self._fail_provider_launch(
                    user_id=user_id,
                    row=claimed,
                    launch_token=launch_token,
                    exc=exc,
                    acceptance=acceptance,
                )
            except Exception:
                # The launch lease remains durable. A later owner-scoped status
                # check terminally fails and refunds it without relaunching.
                pass
            mapped = self._map_provider_error(exc)
            mapped.retryable = False
            mapped.refund_eligible = False
            mapped.failed_job_id = job_id
            raise mapped from exc
        except VideoServiceError as exc:
            try:
                await self._fail_provider_launch(
                    user_id=user_id,
                    row=claimed,
                    launch_token=launch_token,
                    exc=exc,
                    acceptance="rejected",
                )
            except Exception:
                pass
            exc.retryable = False
            exc.refund_eligible = False
            exc.failed_job_id = job_id
            raise

        return await self._complete_provider_launch(
            user_id=user_id,
            row=claimed,
            launch_token=launch_token,
            provider_job_id=provider_job_id,
        )

    async def reconcile_pending(
        self,
        *,
        user_id: str,
        row: dict[str, Any],
        launch_ready: bool = True,
    ) -> dict[str, Any]:
        """Resume a safely unlaunched job or expire an ambiguous one without replay."""
        if (
            row.get("status") != "queued"
            or not str(row.get("provider_job_id") or "").startswith("pending:")
        ):
            return row
        if launch_ready:
            return await self._launch_reserved_job(user_id=user_id, row=row)
        _, current, _ = await self._claim_provider_launch(
            user_id=user_id,
            row=row,
            claim_ready=False,
        )
        return current

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
        reserve_only: bool = False,
        reservation_token: str | None = None,
        reserved_job_id: str | None = None,
        request_fingerprint: str | None = None,
    ) -> dict[str, Any]:
        engine, resolution, duration_seconds = self.normalize_request(
            engine=engine,
            resolution=resolution,
            duration_seconds=duration_seconds,
        )
        references: list[dict[str, Any]] = []
        for reference in reference_images or []:
            if not isinstance(reference, dict):
                raise VideoServiceError(
                    "The video reference plan is invalid.",
                    "INVALID_VIDEO_REFERENCE_PLAN",
                )
            references.append(dict(reference))
        prompt, guarded_prompt, reference_receipt, reference_mode = self.prepare_provider_prompt(
            prompt=prompt,
            engine=engine,
            references=references,
        )
        aspect_ratio = self.validate_aspect_ratio(aspect_ratio)
        project = normalize_chat_id(project_id) if project_id else None
        key = (
            " ".join(str(idempotency_key or "").split()).strip()
            [: self.IDEMPOTENCY_KEY_MAX_LENGTH]
            or None
        )
        fingerprint = self.normalize_request_fingerprint(request_fingerprint)

        if engine == self.CINEMATIC:
            provider = "runway"
            model = self.settings.runway_video_model
        else:
            provider = "gemini"
            model = self.settings.gemini_video_extend_model if engine == self.EXTENDABLE else self.settings.gemini_video_model

        if reserved_job_id:
            row = await self.get(user_id=user_id, job_id=reserved_job_id)
            metadata = row.get("metadata") or {}
            expected = {
                "idempotency_key": key,
                "prompt": prompt,
                "engine": engine,
                "provider": provider,
                "model": model,
                "aspect_ratio": aspect_ratio,
                "resolution": resolution,
                "duration_seconds": duration_seconds,
                "project_id": project,
            }
            if (
                any(row.get(field) != value for field, value in expected.items())
                or row.get("operation_type") != "generate"
                or row.get("status") != "queued"
                or not str(row.get("provider_job_id") or "").startswith("pending:")
                or row.get("video_phase") != "ready_to_launch"
                or row.get("request_fingerprint") != fingerprint
                or row.get("lease_token") is not None
                or not isinstance(row.get("billing_receipt"), dict)
                or not row.get("billing_receipt")
                or metadata.get("referencePlan") != reference_receipt
            ):
                raise VideoServiceError(
                    "This video reservation no longer matches the confirmed request. Start it again.",
                    "VIDEO_RESERVATION_MISMATCH",
                    409,
                )
        else:
            existing = await self._idempotent(user_id=user_id, key=key)
            if existing:
                return existing
            await self._guard_concurrency(user_id=user_id)
            token = str(reservation_token or "").strip()[:128]
            job_id = str(uuid4())
            row = {
                "id": job_id,
                "user_id": user_id,
                "project_id": project,
                "kind": "video",
                "provider": provider,
                # Reserve the job before billing or provider spend. media_jobs
                # predates provider abstraction and requires a provider_job_id.
                "provider_job_id": f"pending:{job_id}",
                "idempotency_key": key,
                "request_fingerprint": fingerprint,
                "status": "queued",
                "video_phase": (
                    "reserved_unbilled" if reserve_only else "ready_to_launch"
                ),
                "lease_token": token if reserve_only else None,
                "lease_expires_at": (
                    _now_dt()
                    + timedelta(
                        seconds=(
                            self.RESERVATION_LEASE_SECONDS
                            if reserve_only
                            else self.PROVIDER_READY_LEASE_SECONDS
                        )
                    )
                ).isoformat(),
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
                    "billingPending": bool(reserve_only),
                    "videoPhase": (
                        "reserved_unbilled" if reserve_only else "ready_to_launch"
                    ),
                    "reservationToken": token if reserve_only else None,
                    "reservationExpiresAt": (
                        (
                            _now_dt()
                            + timedelta(seconds=self.RESERVATION_LEASE_SECONDS)
                        ).isoformat()
                        if reserve_only
                        else None
                    ),
                    "requestFingerprint": fingerprint,
                    "referenceFileIds": [item["fileId"] for item in reference_receipt],
                    "referenceMode": reference_mode,
                    "referencePlan": reference_receipt,
                    "referenceVerification": "not-performed" if reference_receipt else None,
                },
                "updated_at": _now(),
            }
            row, idempotent_replay = await self._reserve_job_row(
                user_id=user_id,
                key=key,
                row=row,
            )
            if idempotent_replay:
                return row
            if reserve_only:
                return row
        return await self._launch_reserved_job(
            user_id=user_id,
            row=row,
            references=references,
        )

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
        reserve_only: bool = False,
        reservation_token: str | None = None,
        reserved_job_id: str | None = None,
        request_fingerprint: str | None = None,
    ) -> dict[str, Any]:
        key = (
            " ".join(str(idempotency_key or "").split()).strip()
            [: self.IDEMPOTENCY_KEY_MAX_LENGTH]
            or None
        )
        fingerprint = self.normalize_request_fingerprint(request_fingerprint)
        try:
            normalized_parent_job_id = normalize_chat_id(parent_job_id)
        except Exception as exc:
            raise VideoServiceError(
                "This video can no longer be continued safely.",
                "VIDEO_CONTINUATION_UNAVAILABLE",
                409,
            ) from exc
        reserved_row: dict[str, Any] | None = None
        if reserved_job_id:
            reserved_row = await self.get(
                user_id=user_id,
                job_id=reserved_job_id,
            )
            if str(reserved_row.get("parent_job_id") or "") != normalized_parent_job_id:
                raise VideoServiceError(
                    "This video continuation reservation no longer matches "
                    "the confirmed parent.",
                    "VIDEO_RESERVATION_MISMATCH",
                    409,
                )
            parent = await self.get(
                user_id=user_id,
                job_id=normalized_parent_job_id,
            )
        else:
            parent = await self.validate_continuation_parent(
                user_id=user_id,
                job_id=normalized_parent_job_id,
            )
        prompt = self.validate_prompt(prompt)

        model = self.settings.gemini_video_extend_model
        parent_duration = int(parent.get("duration_seconds") or 8)
        parent_sequence = int(parent.get("sequence_index") or 0)
        root_job_id = str(parent.get("root_job_id") or parent.get("id"))
        expected_duration = min(148, parent_duration + 7)
        expected_aspect_ratio = parent.get("aspect_ratio") or "16:9"
        if reserved_job_id:
            row = reserved_row or await self.get(
                user_id=user_id,
                job_id=reserved_job_id,
            )
            expected = {
                "idempotency_key": key,
                "prompt": prompt,
                "engine": self.EXTENDABLE,
                "provider": "gemini",
                "model": model,
                "aspect_ratio": expected_aspect_ratio,
                "resolution": "720p",
                "duration_seconds": expected_duration,
                "parent_job_id": parent.get("id"),
                "root_job_id": root_job_id,
                "sequence_index": parent_sequence + 1,
                "project_id": parent.get("project_id"),
            }
            if (
                any(row.get(field) != value for field, value in expected.items())
                or row.get("operation_type") != "extend"
                or row.get("status") != "queued"
                or not str(row.get("provider_job_id") or "").startswith("pending:")
                or row.get("video_phase") != "ready_to_launch"
                or row.get("request_fingerprint") != fingerprint
                or row.get("lease_token") is not None
                or not isinstance(row.get("billing_receipt"), dict)
                or not row.get("billing_receipt")
            ):
                raise VideoServiceError(
                    "This video continuation reservation no longer matches the confirmed request. Start it again.",
                    "VIDEO_RESERVATION_MISMATCH",
                    409,
                )
        else:
            existing = await self._idempotent(user_id=user_id, key=key)
            if existing:
                return existing
            await self._guard_concurrency(user_id=user_id)
            token = str(reservation_token or "").strip()[:128]
            job_id = str(uuid4())
            row = {
                "id": job_id,
                "user_id": user_id,
                "project_id": parent.get("project_id"),
                "kind": "video",
                "provider": "gemini",
                "provider_job_id": f"pending:{job_id}",
                "idempotency_key": key,
                "request_fingerprint": fingerprint,
                "status": "queued",
                "video_phase": (
                    "reserved_unbilled" if reserve_only else "ready_to_launch"
                ),
                "lease_token": token if reserve_only else None,
                "lease_expires_at": (
                    _now_dt()
                    + timedelta(
                        seconds=(
                            self.RESERVATION_LEASE_SECONDS
                            if reserve_only
                            else self.PROVIDER_READY_LEASE_SECONDS
                        )
                    )
                ).isoformat(),
                "prompt": prompt,
                "model": model,
                "aspect_ratio": expected_aspect_ratio,
                "resolution": "720p",
                "engine": self.EXTENDABLE,
                "operation_type": "extend",
                "parent_job_id": parent.get("id"),
                "root_job_id": root_job_id,
                "sequence_index": parent_sequence + 1,
                "duration_seconds": expected_duration,
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
                "metadata": {
                    "refundEligible": True,
                    "providerAccepted": False,
                    "billingPending": bool(reserve_only),
                    "videoPhase": (
                        "reserved_unbilled" if reserve_only else "ready_to_launch"
                    ),
                    "reservationToken": token if reserve_only else None,
                    "reservationExpiresAt": (
                        (
                            _now_dt()
                            + timedelta(seconds=self.RESERVATION_LEASE_SECONDS)
                        ).isoformat()
                        if reserve_only
                        else None
                    ),
                    "requestFingerprint": fingerprint,
                },
                "updated_at": _now(),
            }
            row, idempotent_replay = await self._reserve_job_row(
                user_id=user_id,
                key=key,
                row=row,
            )
            if idempotent_replay:
                return row
            if reserve_only:
                return row
        return await self._launch_reserved_job(user_id=user_id, row=row)

    async def _update_processing_status(
        self,
        *,
        user_id: str,
        row: dict[str, Any],
        provider_status: str,
    ) -> dict[str, Any]:
        """Persist non-terminal provider progress only while still processing."""
        metadata = {
            **(row.get("metadata") or {}),
            "providerStatus": str(provider_status)[:160],
        }
        updated = await self.db.update(
            "media_jobs",
            {
                "metadata": metadata,
                "updated_at": _now(),
            },
            filters={
                "id": eq(row["id"]),
                "user_id": eq(user_id),
                "idempotency_key": eq(str(row.get("idempotency_key") or "")),
                "request_fingerprint": eq(
                    self.normalize_request_fingerprint(row.get("request_fingerprint"))
                ),
                "provider_job_id": eq(str(row.get("provider_job_id") or "")),
                "status": eq("processing"),
                "video_phase": eq("processing"),
            },
        )
        if updated:
            return updated[0]
        return await self.get(user_id=user_id, job_id=str(row.get("id") or ""))

    @staticmethod
    def refund_eligible(row: dict[str, Any]) -> bool:
        metadata = row.get("metadata")
        if not isinstance(metadata, dict):
            return False
        if "refundEligible" not in metadata:
            return True
        return metadata.get("refundEligible") is True

    @staticmethod
    def _valid_generated_video(data: bytes) -> bool:
        """Require a bounded MP4-family movie and declared-video-track envelope."""
        if not isinstance(data, bytes) or len(data) < 40:
            return False
        box_budget = [_ISO_BMFF_MAX_BOXES]
        boxes = _iso_bmff_boxes(
            data,
            budget=box_budget,
            allow_terminal_mdat=True,
        )
        if not boxes:
            return False

        if boxes[0][0] != b"ftyp":
            return False

        ftyp_boxes = [box for box in boxes if box[0] == b"ftyp"]
        moov_boxes = [box for box in boxes if box[0] == b"moov"]
        mdat_boxes = [box for box in boxes if box[0] == b"mdat"]
        if len(ftyp_boxes) != 1 or len(moov_boxes) != 1 or not mdat_boxes:
            return False

        _, ftyp_start, ftyp_end = ftyp_boxes[0]
        ftyp_payload_size = ftyp_end - ftyp_start
        if ftyp_payload_size < 8 or (ftyp_payload_size - 8) % 4:
            return False
        if not any(box_end > payload_start for _, payload_start, box_end in mdat_boxes):
            return False
        _, moov_start, moov_end = moov_boxes[0]
        return _valid_video_movie_structure(
            data,
            moov_start=moov_start,
            moov_end=moov_end,
            budget=box_budget,
        )

    async def poll(self, *, user_id: str, job_id: str) -> dict[str, Any]:
        row = await self.get(user_id=user_id, job_id=job_id)
        metadata = row.get("metadata")
        if (
            row.get("status") == "failed"
            and not row.get("billing_refunded")
            and isinstance(row.get("billing_receipt"), dict)
            and bool(row.get("billing_receipt"))
            and isinstance(metadata, dict)
            and metadata.get("compatibilityOrigin") == "pre-atomic"
            and (
                "refundEligible" not in metadata
                or metadata.get("refundEligible") is not False
            )
        ):
            # An old instance could crash between its non-atomic failed-row
            # write and customer refund. Repair that exact compatibility row
            # before returning its terminal receipt; the DB path is idempotent.
            settlement = await self.sweep_expired_leases(
                limit=1,
                user_id=user_id,
                job_id=str(row.get("id") or ""),
            )
            row = await self.get(user_id=user_id, job_id=job_id)
            current_metadata = row.get("metadata")
            still_unsettled = (
                row.get("status") == "failed"
                and not row.get("billing_refunded")
                and isinstance(current_metadata, dict)
                and current_metadata.get("compatibilityOrigin") == "pre-atomic"
                and (
                    "refundEligible" not in current_metadata
                    or current_metadata.get("refundEligible") is not False
                )
            )
            if (
                settlement.get("outcome") != "completed"
                or int(settlement.get("errors") or 0) > 0
                or still_unsettled
            ):
                raise VideoServiceError(
                    "Ask Crump is still settling this video's charge safely. "
                    "Check its status again shortly.",
                    "VIDEO_SETTLEMENT_PENDING",
                    503,
                    True,
                    False,
                    job_id,
                )
        if row.get("status") in {"ready", "failed"}:
            return row
        # A pending provider ID is local state, never a remote task ID. Safely
        # launch only the explicit ready_to_launch phase; an expired launching
        # lease is terminally failed and refunded instead of being replayed.
        if str(row.get("provider_job_id") or "").startswith("pending:"):
            return await self.reconcile_pending(
                user_id=user_id,
                row=row,
                launch_ready=True,
            )

        # The absolute provider/finalization horizon is enforced before any
        # customer-triggered provider poll. The exact database sweep locks,
        # refunds, and terminalizes atomically; malformed settlement rows are
        # quarantined without extending the horizon or calling the provider.
        if self._past_absolute_horizon(row):
            settlement = await self.sweep_expired_leases(
                limit=1,
                user_id=user_id,
                job_id=str(row.get("id") or ""),
            )
            current = await self.get(
                user_id=user_id,
                job_id=str(row.get("id") or ""),
            )
            if (
                settlement.get("outcome") != "completed"
                or int(settlement.get("errors") or 0) > 0
                or self._past_absolute_horizon(current)
            ):
                raise VideoServiceError(
                    "Ask Crump is still settling this completed video safely. "
                    "Check its status again shortly.",
                    "VIDEO_SETTLEMENT_PENDING",
                    503,
                    True,
                    False,
                    str(row.get("id") or "") or None,
                )
            return current

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
            if row.get("video_phase") == "processing":
                return await self._update_processing_status(
                    user_id=user_id,
                    row=row,
                    provider_status=str(provider_status or "processing"),
                )
            return row

        terminal_outcome = (
            "failed" if result.get("status") == "failed" else "ready"
        )
        claim_outcome, claimed, finalization_token = await self._claim_finalization(
            user_id=user_id,
            row=row,
            terminal_outcome=terminal_outcome,
            refund_eligible=(
                bool(result.get("refundEligible", True))
                if terminal_outcome == "failed"
                else True
            ),
        )
        if claim_outcome != "claimed" or not finalization_token:
            return claimed
        row = claimed

        if terminal_outcome == "failed":
            return await self._fail_finalization(
                user_id=user_id,
                row=row,
                finalization_token=finalization_token,
                message=str(result.get("failureMessage") or "Video generation failed."),
                failure_code=str(result.get("failureCode") or "") or None,
                refund_eligible=bool(result.get("refundEligible", True)),
            )

        output_url = str(result.get("outputUrl") or "")
        if not output_url:
            return await self._fail_finalization(
                user_id=user_id,
                row=row,
                finalization_token=finalization_token,
                message="The provider completed without a video file.",
                failure_code="VIDEO_PROVIDER_OUTPUT_MISSING",
                refund_eligible=True,
            )

        try:
            data = await provider.download(output_url, max_bytes=self.settings.max_generated_video_bytes)
        except ProviderError as exc:
            if exc.retryable:
                mapped = self._map_provider_error(exc)
                mapped.refund_eligible = False
                mapped.failed_job_id = str(row.get("id") or "") or None
                raise mapped from exc
            return await self._fail_finalization(
                user_id=user_id,
                row=row,
                finalization_token=finalization_token,
                message=exc.message,
                failure_code=exc.failure_code or exc.code,
                refund_eligible=bool(exc.refund_eligible),
            )

        if not self._valid_generated_video(data):
            return await self._fail_finalization(
                user_id=user_id,
                row=row,
                finalization_token=finalization_token,
                message="The provider returned an invalid video file.",
                failure_code="VIDEO_PROVIDER_OUTPUT_INVALID",
                refund_eligible=True,
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
                    "providerAssetReference": provider_asset_reference,
                    "providerAssetExpiresAt": provider_asset_expires_at,
                    "attribution": "Powered by Runway" if provider_name == "runway" else None,
                },
                file_id=str(row["id"]),
                persist_metadata=False,
            )
        except Exception as exc:
            # Storage writes and metadata upserts can succeed even when their
            # response is lost. Keep the renewable finalization lease so a
            # retry uses the same job-derived file id instead of orphaning or
            # duplicating an object.
            raise VideoServiceError(
                "The provider finished the video, and Ask Crump is still "
                "confirming its private file. Check the status again shortly.",
                "VIDEO_FILE_FINALIZATION_PENDING",
                503,
                True,
                False,
                str(row.get("id") or "") or None,
            ) from exc

        try:
            return await self._complete_finalization(
                user_id=user_id,
                row=row,
                finalization_token=finalization_token,
                file_id=str(file_row["id"]),
                provider_asset_reference=provider_asset_reference,
                provider_asset_expires_at=provider_asset_expires_at,
                stored_bytes=len(data),
                file_metadata=dict(file_row.get("metadata") or {}),
            )
        except VideoServiceError:
            # Resolve response loss and the absolute-deadline race before
            # deciding whether the deterministic object is deliverable. The
            # DB transaction either bound both rows or neither one.
            try:
                await self.sweep_expired_leases(
                    limit=1,
                    user_id=user_id,
                    job_id=str(row.get("id") or ""),
                )
            except VideoServiceError:
                pass
            current = await self.get(
                user_id=user_id,
                job_id=str(row.get("id") or ""),
            )
            if (
                current.get("status") == "ready"
                and str(current.get("file_id") or "") == str(file_row["id"])
            ):
                return current
            if current.get("status") == "failed":
                try:
                    await self.files.discard_generated_file(
                        user_id=user_id,
                        file_id=str(file_row["id"]),
                        filename=f"crump-video-{row['id']}.mp4",
                    )
                except Exception:
                    # The object has no ready database row and is therefore
                    # not customer-visible; a later storage cleanup can retry.
                    pass
                return current
            raise

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
