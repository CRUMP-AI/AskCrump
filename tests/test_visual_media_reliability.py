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


def _png_data_url(image: Image.Image) -> str:
    output = BytesIO()
    image.save(output, format="PNG")
    return "data:image/png;base64," + base64.b64encode(output.getvalue()).decode("ascii")


def test_precision_edit_prepares_matching_flexible_canvas_and_inverted_provider_mask() -> None:
    source = Image.new("RGB", (800, 600), color=(18, 24, 30))
    source_bytes = BytesIO()
    source.save(source_bytes, format="PNG")
    mask = Image.new("RGBA", source.size, color=(209, 191, 150, 0))
    for x in range(250, 350):
        for y in range(200, 300):
            mask.putpixel((x, y), (209, 191, 150, 255))

    prepared, provider_mask, normalized_source, selection, size = MediaService._prepare_precision_edit(
        source_bytes.getvalue(),
        _png_data_url(mask),
    )

    width, height = (int(value) for value in size.split("x"))
    assert width % 16 == 0
    assert height % 16 == 0
    assert 655_360 <= width * height <= 8_294_400
    assert max(width, height) <= 3840
    assert normalized_source.size == selection.size == (width, height)
    with Image.open(BytesIO(prepared)) as prepared_image:
        assert prepared_image.size == (width, height)
    with Image.open(BytesIO(provider_mask)) as mask_image:
        provider_alpha = mask_image.getchannel("A")
        assert provider_alpha.getpixel((0, 0)) == 255
        selected_point = (round(300 * width / 800), round(250 * height / 600))
        assert provider_alpha.getpixel(selected_point) < 10


def test_precision_edit_restores_every_fully_protected_pixel_after_provider_output() -> None:
    source = Image.new("RGBA", (1024, 1024), color=(210, 40, 30, 255))
    generated = Image.new("RGBA", source.size, color=(20, 80, 230, 255))
    selection = Image.new("L", source.size, color=0)
    for x in range(400, 624):
        for y in range(400, 624):
            selection.putpixel((x, y), 255)
    generated_bytes = BytesIO()
    generated.save(generated_bytes, format="PNG")

    result_bytes = MediaService._composite_precision_edit(
        generated_bytes.getvalue(),
        source,
        selection,
    )

    with Image.open(BytesIO(result_bytes)) as result:
        assert result.convert("RGBA").getpixel((100, 100)) == source.getpixel((100, 100))
        assert result.convert("RGBA").getpixel((500, 500)) == generated.getpixel((500, 500))
        for point in ((0, 0), (1023, 1023), (399, 500), (624, 500)):
            assert result.convert("RGBA").getpixel(point) == source.getpixel(point)


def test_precision_edit_rejects_empty_broad_and_mismatched_masks_before_provider_spend() -> None:
    source = Image.new("RGB", (1024, 1024), color=(18, 24, 30))
    source_bytes = BytesIO()
    source.save(source_bytes, format="PNG")

    empty = Image.new("RGBA", source.size, color=(0, 0, 0, 0))
    with pytest.raises(AIServiceError) as empty_error:
        MediaService._prepare_precision_edit(source_bytes.getvalue(), _png_data_url(empty))
    assert empty_error.value.code == "EMPTY_IMAGE_EDIT_MASK"

    broad = Image.new("RGBA", source.size, color=(0, 0, 0, 255))
    with pytest.raises(AIServiceError) as broad_error:
        MediaService._prepare_precision_edit(source_bytes.getvalue(), _png_data_url(broad))
    assert broad_error.value.code == "IMAGE_EDIT_MASK_TOO_BROAD"

    mismatched = Image.new("RGBA", (512, 512), color=(0, 0, 0, 0))
    mismatched.putpixel((10, 10), (209, 191, 150, 255))
    with pytest.raises(AIServiceError) as mismatch_error:
        MediaService._prepare_precision_edit(source_bytes.getvalue(), _png_data_url(mismatched))
    assert mismatch_error.value.code == "IMAGE_EDIT_MASK_SIZE_MISMATCH"


def test_precision_edit_contract_never_infers_or_labels_race() -> None:
    prompt = MediaService._precision_edit_prompt("Make the selected area warmer")

    assert "modify only the transparent selected area" in prompt
    assert "Do not infer or label race or ethnicity" in prompt
    assert "explicitly requested visual change" in prompt


def test_precision_mask_is_transient_and_not_synchronized_or_traced() -> None:
    route = read("backend/routes/chat.py")
    extraction = "image_edit_mask = request_payload.pop('imageEditMask', None)"

    assert extraction in route
    assert route.index(extraction) < route.index("prepared = await intelligence.prepare")
    request_meta = route[route.index("request_meta = {") : route.index("assistant_message = {")]
    assert "imageEditMask" not in request_meta


class PrecisionImageFiles:
    def __init__(self, source: bytes) -> None:
        self.source = source
        self.stored: dict | None = None

    async def download_bytes(self, *, row, max_bytes: int):
        assert row["id"] == "source-image"
        assert max_bytes == 25 * 1024 * 1024
        return self.source

    async def store_bytes(self, **kwargs):
        self.stored = kwargs
        return {
            "id": "result-image",
            "file_name": kwargs["filename"],
            "mime_type": kwargs["mime_type"],
            "size_bytes": len(kwargs["data"]),
            "kind": kwargs["kind"],
            "status": "ready",
        }

    @staticmethod
    def public_file(row):
        return {
            "id": row["id"],
            "name": row["file_name"],
            "type": row["mime_type"],
            "size": row["size_bytes"],
            "url": f"/api/files/{row['id']}/content",
        }


@pytest.mark.asyncio
async def test_precision_edit_full_path_sends_provider_mask_and_stores_protected_composite(monkeypatch) -> None:
    source = Image.new("RGBA", (1024, 1024), color=(210, 40, 30, 255))
    source_bytes = BytesIO()
    source.save(source_bytes, format="PNG")
    mask = Image.new("RGBA", source.size, color=(209, 191, 150, 0))
    mask.paste((209, 191, 150, 255), (400, 400, 624, 624))
    generated = Image.new("RGBA", source.size, color=(20, 80, 230, 255))
    generated_bytes = BytesIO()
    generated.save(generated_bytes, format="PNG")
    provider_payload = base64.b64encode(generated_bytes.getvalue()).decode("ascii")
    files = PrecisionImageFiles(source_bytes.getvalue())
    service = MediaService(
        SimpleNamespace(
            openai_api_key="test-only",
            image_generation_enabled=True,
            openai_image_model="gpt-image-2",
        ),
        files,
    )
    provider_request: dict = {}

    async def fake_post(client, endpoint, **kwargs):
        provider_request.update({"endpoint": endpoint, **kwargs})
        return httpx.Response(
            200,
            request=httpx.Request("POST", endpoint),
            json={"data": [{"b64_json": provider_payload}]},
        )

    monkeypatch.setattr(MediaService, "_post_image_request", staticmethod(fake_post))
    result = await service.generate_or_edit_image(
        user_id="user-one",
        payload={
            "message": "Make the selected area blue",
            "creativeTool": "image",
            "imageUseReference": True,
            "imageQuality": "medium",
        },
        file_rows=[{"id": "source-image", "mime_type": "image/png"}],
        chat_id=None,
        message_id=None,
        image_edit_mask=_png_data_url(mask),
    )

    assert provider_request["endpoint"].endswith("/v1/images/edits")
    assert set(provider_request["files"]) == {"image[]", "mask"}
    assert provider_request["data"]["size"] == "1024x1024"
    assert "Do not infer or label race or ethnicity" in provider_request["data"]["prompt"]
    assert "input_fidelity" not in provider_request["data"]
    assert result["response"] == "I edited only the area you selected."
    assert files.stored is not None
    assert files.stored["metadata"]["precisionEdit"] is True
    assert "mask" not in files.stored["metadata"]
    with Image.open(BytesIO(files.stored["data"])) as stored:
        pixels = stored.convert("RGBA")
        assert pixels.getpixel((100, 100)) == source.getpixel((100, 100))
        assert pixels.getpixel((500, 500)) == generated.getpixel((500, 500))


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
        "Select the pixels yourself",
        "does not infer race or ethnicity",
        "placed as overlays for exact fidelity",
        "Select a specific area",
        "aria-label', 'Image Studio",
        "aria-label', 'Close Image Studio",
        "aria-modal', 'true",
        "wireMenuKeyboard(sheet, dismiss)",
        "mountMenu(sheet, close)",
        "restoreMenuFocus(returnFocus)",
    ):
        assert contract in studio
    assert "reference.innerHTML" not in studio
    assert "referenceDescription.textContent = currentReference" in studio
    assert "crump50-reference-action" in styles
    assert "crump50-precision-entry" in styles


def test_precision_editor_is_manual_private_and_pixel_protected() -> None:
    editor = read("public/crump-precision-image-edit.js")
    styles = read("public/crump-precision-image-edit.css")
    composer = read("public/crump-5.0.js")
    runtime = read("public/runtime-body-v1.js")
    worker = read("public/sw.js")

    for contract in (
        "Choose exactly what may change",
        "Paint the area yourself",
        "Brush",
        "Erase",
        "Undo",
        "Clear",
        "Outside-selection lock",
        "restores protected pixels",
        "Skin tone is not a race label",
        "selectionHasVisiblePixels",
        "maskDataUrl",
        "applyPrecisionSelection",
        "aria-modal",
    ):
        assert contract in editor
    assert "face-api" not in editor
    assert "race classification" not in editor.lower()
    assert "localStorage" not in editor
    assert "sessionStorage" not in editor
    assert "imageEditMask = precision.maskDataUrl" in composer
    assert "state.precisionImageEdit = null" in composer
    assert "imageEditMask" not in composer[composer.index("requestMeta: {") : composer.index("state.imageRecovery = null;")]
    assert "crump-precision-open" in styles
    exact_script = "/crump-precision-image-edit.js?v=5.9.76-precision-edit-studio-1"
    exact_style = "/crump-precision-image-edit.css?v=5.9.76-precision-edit-studio-1"
    for asset in (exact_script, exact_style):
        assert asset in runtime
        assert asset in worker


def test_image_studio_close_restores_a_visible_opener_or_the_composer() -> None:
    script = read("public/crump-5.0.js")
    studio = script[script.index("function restoreMenuFocus") : script.index("function showDocumentOptions()")]
    verifier = read("scripts/verify-visual-media-browser.cjs")
    fixture = read("tests/fixtures/image-upload-preview-stability.html")

    assert "target.closest('[hidden], [inert], [aria-hidden=\"true\"]')" in studio
    assert "target.getClientRects().length" in studio
    assert "usableFocusReturnTarget(returnFocus) || $('#userInput')" in studio
    assert "requestAnimationFrame" in studio
    assert 'id="openImageStudioTransient"' in fixture
    assert "directCloseFocus.activeId !== 'openImageStudio'" in verifier
    assert "transientCloseFocus.activeId !== 'userInput'" in verifier
    assert "initialStudio.workspaceInert !== ''" in verifier
    assert "reverseWrapFocus !== 'Create without reference'" in verifier
    assert "forwardWrapFocus !== 'Close Image Studio'" in verifier


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
