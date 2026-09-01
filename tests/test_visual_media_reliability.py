import base64
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest
import httpx
from PIL import Image

from backend.ai_service import AIServiceError
from backend.media_service import EDIT_IMAGE_MAX_EDGE, MediaService
from backend.video_service import VideoService, VideoServiceError


ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_edit_source_is_orientation_safe_provider_png() -> None:
    original = Image.new("CMYK", (5000, 2500), color=(0, 120, 120, 0))
    raw = BytesIO()
    original.save(raw, format="JPEG")

    prepared, filename, mime = MediaService._prepare_edit_image(raw.getvalue())

    assert filename == "Crump_Edit_Source.png"
    assert mime == "image/png"
    with Image.open(BytesIO(prepared)) as image:
        assert image.format == "PNG"
        assert image.mode in {"RGB", "RGBA"}
        assert max(image.size) == EDIT_IMAGE_MAX_EDGE


def test_invalid_edit_source_is_rejected_before_provider_spend() -> None:
    with pytest.raises(AIServiceError) as caught:
        MediaService._prepare_edit_image(b"not an image")

    assert caught.value.status_code == 400
    assert caught.value.code == "INVALID_IMAGE_EDIT_SOURCE"
    assert caught.value.retryable is False


def test_provider_invalid_image_rejection_is_specific_and_actionable() -> None:
    response = httpx.Response(
        400,
        request=httpx.Request("POST", "https://api.openai.com/v1/images/edits"),
        json={"error": {"code": "invalid_image_file", "type": "image_generation_user_error"}},
    )

    error = MediaService._image_provider_exception(response)

    assert error.code == "INVALID_IMAGE_EDIT_SOURCE"
    assert error.status_code == 400
    assert "JPG, PNG, or WebP" in error.message


def test_moderation_block_uses_stable_code_and_content_free_diagnostics(caplog) -> None:
    sensitive_provider_message = "Blocked prompt: private family photo description"
    response = httpx.Response(
        400,
        request=httpx.Request("POST", "https://api.openai.com/v1/images/edits"),
        headers={"x-request-id": "image-request-123"},
        json={
            "error": {
                "code": "moderation_blocked",
                "type": "image_generation_user_error",
                "message": sensitive_provider_message,
                "moderation_details": {
                    "moderation_stage": "input",
                    "categories": {"violence": True, "private prompt content": True},
                    "safety_violations": ["graphic", "not safe for logs"],
                },
            },
        },
    )

    with caplog.at_level("WARNING", logger="askcrump.media"):
        error = MediaService._image_provider_exception(response)

    assert error.code == "IMAGE_SAFETY_REJECTED"
    assert error.status_code == 400
    assert error.retryable is False
    assert "Adjust the prompt or reference image" in error.message
    log_text = caplog.text
    assert "moderation_stage=input" in log_text
    assert "categories=violence,graphic" in log_text
    assert "image-request-123" in log_text
    assert sensitive_provider_message not in log_text
    assert "private prompt content" not in log_text
    assert "not safe for logs" not in log_text


def test_themed_edits_preserve_people_and_do_not_invent_brand_marks() -> None:
    prompt = MediaService._edit_fidelity_prompt("Make this Snow White themed")

    for requirement in (
        "Preserve identity",
        "skin tone",
        "ethnicity",
        "infant or child",
        "not as a different person or race",
        "do not invent or approximate branded text",
    ):
        assert requirement in prompt


def test_generated_images_get_geometry_and_brand_fidelity_contract() -> None:
    prompt = MediaService._generation_fidelity_prompt("Create a blue school bus")

    assert "object counts" in prompt
    assert "geometry" in prompt
    assert "Do not invent or approximate real logos" in prompt


def test_video_provider_prompt_adds_continuity_and_logo_constraints() -> None:
    prompt = VideoService.provider_prompt("A blue school bus drives through town.", max_chars=1000)

    assert "avoid morphing, duplicates, substitutions" in prompt
    assert "Never invent or approximate a logo" in prompt
    assert len(prompt) <= 1000


def test_video_provider_prompt_uses_supplied_reference_without_claiming_perfection() -> None:
    prompt = VideoService.provider_prompt(
        "A blue school bus drives through town.",
        max_chars=1000,
        has_visual_reference=True,
    )

    assert "Use the supplied visual reference" in prompt
    assert "do not restyle the mark" in prompt
    assert "exact" not in prompt.lower()


def test_video_provider_prompt_reserves_room_for_fidelity_contract() -> None:
    with pytest.raises(VideoServiceError) as caught:
        VideoService.provider_prompt("x" * 900, max_chars=1000)

    assert caught.value.code == "PROMPT_TOO_LONG"
    assert "visual-fidelity instructions" in caught.value.message


def test_upload_preview_reconciles_cards_without_recreating_images() -> None:
    script = read("public/crump-5.0.js")
    block = script[script.index("function renderAttachmentTray()") : script.index("function activeToolLabel()")]

    assert "tray.replaceChildren()" not in block
    assert "data-crump50-attachment-id" in block
    assert "if (!card)" in block
    assert "tray.insertBefore(card" in block


def test_image_studio_exposes_an_optional_reference_and_honest_fidelity_guidance() -> None:
    script = read("public/crump-5.0.js")
    styles = read("public/crump-5.0.css")
    studio = script[script.index("function showImageOptions()") : script.index("function showDocumentOptions()")]

    for contract in (
        "Add an image to edit",
        "Reference image ready",
        "Create without reference",
        "Continue with reference",
        "Describe what to keep and what to change",
        "preserve identity and appearance",
        "Logos and readable text can still vary",
        "aria-label', 'Image Studio",
        "aria-label', 'Close Image Studio",
        "aria-modal', 'true",
        "close.focus({preventScroll: true})",
        "if (returnFocus?.isConnected) returnFocus.focus({preventScroll: true})",
        "event.key !== 'Escape'",
    ):
        assert contract in studio
    assert "reference.innerHTML" not in studio
    assert "referenceDescription.textContent = currentReference" in studio
    assert "crump50-reference-action" in styles


def test_image_reference_picker_is_single_image_private_state_and_replaces_only_images() -> None:
    script = read("public/crump-5.0.js")
    picker = script[script.index("function isImageAttachment") : script.index("function showImageOptions()")]

    assert "selected.slice(0, 1)" in picker
    assert "const issue = validateFile(selected[0]);" in picker
    assert "!isSupportedImageFile(selected[0])" in picker
    assert "if (!replace && state.attachments.length >= MAX_FILES)" in picker
    assert picker.index("const issue = validateFile(selected[0]);") < picker.index("if (replace) clearImageAttachments();")
    assert "if (replace) clearImageAttachments();" in picker
    assert "state.attachments.filter(item => !isImageAttachment(item))" in picker
    assert "localStorage" not in picker
    assert "sessionStorage" not in picker
    assert "fetch(" not in picker
    assert "input.accept = 'image/jpeg,image/png,image/webp,image/heic,image/heif,.heic,.heif'" in picker


def test_blocked_image_request_has_revision_instead_of_exact_retry_contract() -> None:
    transport = read("public/chat-resilience.js")
    composer = read("public/crump-5.0.js")
    renderer = read("public/ui-functions.js")
    route = read("backend/routes/chat.py")
    ai_error_handler = route.split("except AIServiceError as exc:", 1)[1].split("except Exception:", 1)[0]

    assert "safeImageRecovery(data?.recovery)" in transport
    assert "message.replyErrorCode === 'IMAGE_SAFETY_REJECTED'" in composer
    assert "reviseImageMessage(id);" in composer
    assert "unchangedRecoveredImageRequest(text, ready)" in composer
    assert "Change the wording or reference image before sending this request again." in composer
    assert "window.reviseImageMessage = reviseImageMessage" in composer
    assert "Image request needs changes — Tap to revise" in renderer
    assert "window.reviseImageMessage?.(message.id)" in renderer
    assert "index === lastUserIndex || message?.replyStatus === 'failed'" in renderer
    assert "'action': 'revise_image_request'" in route
    assert ai_error_handler.index("await refund_usage") < ai_error_handler.index("recovery = _ai_error_recovery(exc.code)")
    assert ai_error_handler.index("await features.refund") < ai_error_handler.index("recovery = _ai_error_recovery(exc.code)")
    for source in (read("backend/media_service.py"), route, transport, composer):
        assert "moderation: low" not in source


def test_image_rejection_browser_fixture_is_private_and_credential_free() -> None:
    fixture = read("tests/fixtures/image-safety-recovery.html")
    verifier = read("scripts/verify-image-safety-recovery-browser.cjs")

    assert '<script src="/public/ui-functions.js?v=image-safety-recovery-fixture-1"></script>' in fixture
    assert '<script src="/public/crump-5.0.js?v=image-safety-recovery-fixture-1"></script>' in fixture
    assert "IMAGE_SAFETY_REJECTED" in fixture
    assert "revise_image_request" in fixture
    assert "sendCalls" in verifier
    assert "ensureUsageCalls" in verifier
    assert "askcrump.com" not in fixture
    assert "password" not in fixture.lower()


def test_video_job_survives_navigation_and_duplicate_submission() -> None:
    script = read("public/crump-product-5.3.js")

    for contract in (
        "VIDEO_REQUEST_STORAGE_KEY",
        "videoRequestFingerprint",
        "if (state.videoStarting) return",
        "Your current video is still generating",
        "resumePendingVideoJob",
        "document.addEventListener('visibilitychange'",
        "window.addEventListener('online', resumePendingVideoJob)",
        "event.key === VIDEO_JOB_STORAGE_KEY",
    ):
        assert contract in script

    assert "Exact logos and readable brand marks can distort" in script


class ReferenceFiles:
    def __init__(self, raw: bytes) -> None:
        self.raw = raw
        self.lookups: list[tuple[str, str]] = []

    async def get_owned(self, *, user_id: str, file_id: str):
        self.lookups.append((user_id, file_id))
        return {"id": file_id, "mime_type": "image/jpeg", "storage_path": "private/reference.jpg"}

    async def download_bytes(self, *, row, max_bytes: int):
        assert row["storage_path"] == "private/reference.jpg"
        assert max_bytes == VideoService.REFERENCE_IMAGE_MAX_BYTES
        return self.raw


@pytest.mark.asyncio
async def test_video_references_are_owner_scoped_and_normalized_before_provider_use() -> None:
    source = Image.new("CMYK", (3000, 1500), color=(10, 20, 30, 0))
    raw = BytesIO()
    source.save(raw, format="JPEG")
    files = ReferenceFiles(raw.getvalue())
    service = VideoService(SimpleNamespace(), SimpleNamespace(), files)
    file_id = "00000000-0000-0000-0000-000000000002"

    references = await service.prepare_reference_images(
        user_id="00000000-0000-0000-0000-000000000001",
        file_ids=[file_id],
        engine="extendable",
    )

    assert files.lookups == [("00000000-0000-0000-0000-000000000001", file_id)]
    assert references[0]["fileId"] == file_id
    assert references[0]["mimeType"] == "image/png"
    decoded = base64.b64decode(references[0]["data"])
    with Image.open(BytesIO(decoded)) as prepared:
        assert prepared.mode in {"RGB", "RGBA"}
        assert max(prepared.size) == VideoService.REFERENCE_IMAGE_MAX_EDGE


@pytest.mark.asyncio
async def test_video_reference_limits_match_real_provider_modes() -> None:
    service = VideoService(SimpleNamespace(), SimpleNamespace(), ReferenceFiles(b"unused"))
    ids = [f"00000000-0000-0000-0000-{index:012d}" for index in range(1, 4)]

    with pytest.raises(VideoServiceError) as caught:
        await service.prepare_reference_images(user_id=ids[0], file_ids=ids[:2], engine="quick")

    assert caught.value.code == "TOO_MANY_VIDEO_REFERENCES"
    assert VideoService.reference_limit("extendable") == 3
