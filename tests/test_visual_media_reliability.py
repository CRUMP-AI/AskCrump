import base64
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest
import httpx
from PIL import Image

from backend.ai_service import AIServiceError
from backend import media_service as media_module
from backend.media_service import (
    EDIT_IMAGE_MAX_EDGE,
    EDIT_IMAGE_MAX_PIXELS,
    IMAGE_EDIT_PROVIDER_MAX_BYTES,
    MediaService,
)
from backend.routes import files as file_routes
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
        assert image.width * image.height <= EDIT_IMAGE_MAX_PIXELS
    assert len(prepared) < IMAGE_EDIT_PROVIDER_MAX_BYTES


def test_edit_source_caps_total_pixels_before_provider_spend(monkeypatch) -> None:
    monkeypatch.setattr(media_module, "EDIT_IMAGE_MAX_EDGE", 64)
    monkeypatch.setattr(media_module, "EDIT_IMAGE_MAX_PIXELS", 1024)
    original = Image.new("RGB", (64, 64), color=(20, 40, 60))
    raw = BytesIO()
    original.save(raw, format="PNG")

    prepared, _, _ = MediaService._prepare_edit_image(raw.getvalue())

    with Image.open(BytesIO(prepared)) as image:
        assert image.size == (32, 32)


def test_edit_source_rejects_an_encoded_provider_input_at_the_byte_limit(monkeypatch) -> None:
    original = Image.new("RGB", (16, 16), color=(20, 40, 60))
    raw = BytesIO()
    original.save(raw, format="PNG")
    monkeypatch.setattr(media_module, "IMAGE_EDIT_PROVIDER_MAX_BYTES", 10)

    with pytest.raises(AIServiceError) as caught:
        MediaService._prepare_edit_image(raw.getvalue())

    assert caught.value.status_code == 413
    assert caught.value.code == "IMAGE_EDIT_SOURCE_TOO_LARGE"
    assert caught.value.retryable is False


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


def test_local_image_adjustments_change_only_the_manual_selection() -> None:
    source = Image.new("RGBA", (120, 100), color=(100, 110, 120, 255))
    source_bytes = BytesIO()
    source.save(source_bytes, format="PNG")
    mask = Image.new("RGBA", source.size, color=(209, 191, 150, 0))
    mask.paste((209, 191, 150, 255), (40, 30, 80, 70))

    result_bytes, values, size = MediaService._apply_local_image_adjustments(
        source_bytes.getvalue(),
        _png_data_url(mask),
        {"warmth": 30, "exposure": 10, "saturation": 15},
    )

    assert values == {"warmth": 30.0, "exposure": 10.0, "saturation": 15.0}
    assert size == "120x100"
    with Image.open(BytesIO(result_bytes)) as result:
        pixels = result.convert("RGBA")
        assert pixels.getpixel((10, 10)) == source.getpixel((10, 10))
        assert pixels.getpixel((39, 50)) == source.getpixel((39, 50))
        assert pixels.getpixel((80, 50)) == source.getpixel((80, 50))
        adjusted = pixels.getpixel((60, 50))
        assert adjusted != source.getpixel((60, 50))
        assert adjusted[0] > adjusted[2]


def test_local_image_adjustments_support_a_whole_image_mask() -> None:
    source = Image.new("RGBA", (120, 100), color=(100, 110, 120, 255))
    source_bytes = BytesIO()
    source.save(source_bytes, format="PNG")
    full_mask = Image.new("RGBA", source.size, color=(255, 255, 255, 255))

    result_bytes, values, size = MediaService._apply_local_image_adjustments(
        source_bytes.getvalue(),
        _png_data_url(full_mask),
        {"warmth": 18, "exposure": 16, "saturation": -14},
    )

    assert values == {"warmth": 18.0, "exposure": 16.0, "saturation": -14.0}
    assert size == "120x100"
    with Image.open(BytesIO(result_bytes)) as result:
        pixels = result.convert("RGBA")
        for point in ((0, 0), (60, 50), (119, 99)):
            assert pixels.getpixel(point) != source.getpixel(point)


def test_exact_local_overlay_preserves_every_pixel_outside_supplied_artwork() -> None:
    source = Image.new("RGBA", (120, 100), color=(30, 40, 50, 255))
    source_bytes = BytesIO()
    source.save(source_bytes, format="PNG")
    overlay = Image.new("RGBA", source.size, color=(0, 0, 0, 0))
    overlay.paste((220, 30, 40, 255), (42, 34, 78, 66))

    result_bytes, values, size, has_overlay = MediaService._apply_local_image_composition(
        source_bytes.getvalue(),
        "",
        {"warmth": 0, "exposure": 0, "saturation": 0},
        _png_data_url(overlay),
    )

    assert values == {"warmth": 0.0, "exposure": 0.0, "saturation": 0.0}
    assert size == "120x100"
    assert has_overlay is True
    with Image.open(BytesIO(result_bytes)) as result:
        pixels = result.convert("RGBA")
        assert pixels.getpixel((60, 50)) == (220, 30, 40, 255)
        for point in ((0, 0), (41, 50), (78, 50), (119, 99)):
            assert pixels.getpixel(point) == source.getpixel(point)


@pytest.mark.parametrize(
    ("overlay", "code"),
    [
        (Image.new("RGBA", (120, 100), color=(0, 0, 0, 0)), "EMPTY_LOCAL_IMAGE_OVERLAY"),
        (Image.new("RGBA", (60, 50), color=(220, 30, 40, 255)), "LOCAL_IMAGE_OVERLAY_SIZE_MISMATCH"),
    ],
)
def test_exact_local_overlay_rejects_empty_or_mismatched_pixels(overlay, code) -> None:
    source = Image.new("RGBA", (120, 100), color=(30, 40, 50, 255))
    source_bytes = BytesIO()
    source.save(source_bytes, format="PNG")

    with pytest.raises(AIServiceError) as caught:
        MediaService._apply_local_image_composition(
            source_bytes.getvalue(),
            "",
            {"warmth": 0, "exposure": 0, "saturation": 0},
            _png_data_url(overlay),
        )

    assert caught.value.code == code


@pytest.mark.parametrize(
    ("adjustments", "code"),
    [
        ({"warmth": 0, "exposure": 0, "saturation": 0}, "EMPTY_LOCAL_IMAGE_ADJUSTMENT"),
        ({"warmth": 31, "exposure": 0, "saturation": 0}, "INVALID_LOCAL_IMAGE_ADJUSTMENT"),
        ({"warmth": "private prompt text", "exposure": 0, "saturation": 0}, "INVALID_LOCAL_IMAGE_ADJUSTMENT"),
    ],
)
def test_local_image_adjustments_reject_empty_or_unbounded_values(adjustments, code) -> None:
    source = Image.new("RGB", (100, 100), color=(100, 110, 120))
    source_bytes = BytesIO()
    source.save(source_bytes, format="PNG")
    mask = Image.new("RGBA", source.size, color=(209, 191, 150, 0))
    mask.paste((209, 191, 150, 255), (40, 40, 60, 60))

    with pytest.raises(AIServiceError) as caught:
        MediaService._apply_local_image_adjustments(
            source_bytes.getvalue(),
            _png_data_url(mask),
            adjustments,
        )

    assert caught.value.code == code


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

    async def get_owned(self, *, user_id: str, file_id: str):
        assert user_id == "user-one"
        assert file_id == "source-image"
        return {"id": file_id, "mime_type": "image/png"}

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


@pytest.mark.asyncio
async def test_local_image_adjustment_save_is_provider_free_private_and_retry_stable() -> None:
    source = Image.new("RGBA", (120, 100), color=(100, 110, 120, 255))
    source_bytes = BytesIO()
    source.save(source_bytes, format="PNG")
    mask = Image.new("RGBA", source.size, color=(209, 191, 150, 0))
    mask.paste((209, 191, 150, 255), (40, 30, 80, 70))
    files = PrecisionImageFiles(source_bytes.getvalue())
    service = MediaService(SimpleNamespace(), files)

    first = await service.save_local_image_adjustment(
        user_id="user-one",
        source_file_id="source-image",
        mask_data_url=_png_data_url(mask),
        adjustments={"warmth": 12, "exposure": 0, "saturation": 0},
        chat_id=None,
    )
    first_file_id = files.stored["file_id"]
    second = await service.save_local_image_adjustment(
        user_id="user-one",
        source_file_id="source-image",
        mask_data_url=_png_data_url(mask),
        adjustments={"warmth": 12, "exposure": 0, "saturation": 0},
        chat_id=None,
    )

    assert first["name"] == second["name"] == "Crump_Local_Edit.png"
    assert files.stored is not None
    assert files.stored["file_id"] == first_file_id
    assert files.stored["kind"] == "generated_image"
    assert files.stored["metadata"] == {
        "edited": True,
        "precisionEdit": True,
        "localAdjustment": True,
        "deterministicOverlay": False,
        "sourceFileId": "source-image",
        "size": "120x100",
        "warmth": 12.0,
        "exposure": 0.0,
        "saturation": 0.0,
    }
    assert "mask" not in files.stored["metadata"]


@pytest.mark.asyncio
async def test_exact_overlay_only_save_is_private_provider_free_and_retry_stable() -> None:
    source = Image.new("RGBA", (120, 100), color=(30, 40, 50, 255))
    source_bytes = BytesIO()
    source.save(source_bytes, format="PNG")
    overlay = Image.new("RGBA", source.size, color=(0, 0, 0, 0))
    overlay.paste((220, 30, 40, 255), (42, 34, 78, 66))
    files = PrecisionImageFiles(source_bytes.getvalue())
    service = MediaService(SimpleNamespace(), files)

    first = await service.save_local_image_adjustment(
        user_id="user-one",
        source_file_id="source-image",
        mask_data_url="",
        adjustments={"warmth": 0, "exposure": 0, "saturation": 0},
        overlay_data_url=_png_data_url(overlay),
        chat_id=None,
    )
    first_file_id = files.stored["file_id"]
    second = await service.save_local_image_adjustment(
        user_id="user-one",
        source_file_id="source-image",
        mask_data_url="",
        adjustments={"warmth": 0, "exposure": 0, "saturation": 0},
        overlay_data_url=_png_data_url(overlay),
        chat_id=None,
    )

    assert first["id"] == second["id"]
    assert files.stored["file_id"] == first_file_id
    assert files.stored["metadata"]["localAdjustment"] is False
    assert files.stored["metadata"]["deterministicOverlay"] is True
    assert "overlay" not in files.stored["metadata"]


@pytest.mark.asyncio
async def test_local_image_adjustment_route_uses_authenticated_owner_and_zero_provider_credits(monkeypatch) -> None:
    captured: dict = {}

    class LocalRequest:
        async def json(self):
            return {
                "maskDataUrl": "data:image/png;base64,fixture",
                "adjustments": {"warmth": 8, "exposure": 0, "saturation": 0},
                "overlayDataUrl": "data:image/png;base64,overlay",
                "chatId": "22222222-2222-4222-8222-222222222222",
            }

    async def authenticate(_request, _db, _settings):
        return SimpleNamespace(user={"id": "user-one"})

    async def save(**kwargs):
        captured.update(kwargs)
        return {
            "id": "33333333-3333-4333-8333-333333333333",
            "name": "Crump_Local_Edit.png",
            "type": "image/png",
        }

    monkeypatch.setattr(file_routes, "authenticate_request", authenticate)
    monkeypatch.setattr(file_routes.media, "save_local_image_adjustment", save)
    result = await file_routes.image_adjust(
        "11111111-1111-4111-8111-111111111111",
        LocalRequest(),
    )

    assert result["providerUsed"] is False
    assert result["creditsUsed"] == 0
    assert captured == {
        "user_id": "user-one",
        "source_file_id": "11111111-1111-4111-8111-111111111111",
        "mask_data_url": "data:image/png;base64,fixture",
        "adjustments": {"warmth": 8, "exposure": 0, "saturation": 0},
        "overlay_data_url": "data:image/png;base64,overlay",
        "chat_id": "22222222-2222-4222-8222-222222222222",
    }


def test_provider_invalid_image_rejection_is_specific_actionable_and_categorical(caplog) -> None:
    sensitive_provider_message = "Invalid private-family-photo.png supplied for prompt details"
    response = httpx.Response(
        400,
        request=httpx.Request("POST", "https://api.openai.com/v1/images/edits"),
        headers={"x-request-id": "unique-invalid-image-request"},
        json={
            "error": {
                "code": "invalid_image_file",
                "type": "image_generation_user_error",
                "message": sensitive_provider_message,
            }
        },
    )

    with caplog.at_level("WARNING", logger="askcrump.media"):
        error = MediaService._image_provider_exception(response)

    assert error.code == "INVALID_IMAGE_EDIT_SOURCE"
    assert error.status_code == 400
    assert "JPG, PNG, or WebP" in error.message
    assert [record.getMessage() for record in caplog.records] == [
        "Image provider rejected request category=invalid_reference status=400 "
        "code=invalid_image_file type=image_generation_user_error"
    ]
    assert "unique-invalid-image-request" not in caplog.text
    assert sensitive_provider_message not in caplog.text


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

    with caplog.at_level("INFO", logger="askcrump.media"):
        error = MediaService._image_provider_exception(response)

    assert error.code == "IMAGE_SAFETY_REJECTED"
    assert error.status_code == 400
    assert error.retryable is False
    assert "Adjust the prompt or reference image" in error.message
    log_messages = [record.getMessage() for record in caplog.records]
    assert log_messages == [
        "Image provider rejected request category=safety status=400 "
        "code=moderation_blocked type=image_generation_user_error",
        "Image provider safety classification stage=input categories=violence,graphic",
    ]
    log_text = caplog.text
    assert "image-request-123" not in log_text
    assert sensitive_provider_message not in log_text
    assert "private prompt content" not in log_text
    assert "not safe for logs" not in log_text


def test_repeated_provider_rejections_share_one_operational_signature(caplog) -> None:
    responses = [
        httpx.Response(
            400,
            request=httpx.Request("POST", "https://api.openai.com/v1/images/edits"),
            headers={"x-request-id": f"unique-request-{index}"},
            json={
                "error": {
                    "code": "invalid_image_file",
                    "type": "image_generation_user_error",
                    "message": f"private provider detail {index}",
                }
            },
        )
        for index in range(2)
    ]

    with caplog.at_level("WARNING", logger="askcrump.media"):
        for response in responses:
            MediaService._image_provider_exception(response)

    messages = [record.getMessage() for record in caplog.records]
    assert len(messages) == 2
    assert len(set(messages)) == 1
    assert messages[0] == (
        "Image provider rejected request category=invalid_reference status=400 "
        "code=invalid_image_file type=image_generation_user_error"
    )
    assert "unique-request" not in caplog.text
    assert "private provider detail" not in caplog.text


def test_upstream_provider_failure_is_error_categorical_and_content_free(caplog) -> None:
    sensitive_provider_message = "Private upstream diagnostic with request content"
    response = httpx.Response(
        503,
        request=httpx.Request("POST", "https://api.openai.com/v1/images/generations"),
        headers={"x-request-id": "unique-upstream-request"},
        json={
            "error": {
                "code": "server_error",
                "type": "upstream_failure",
                "message": sensitive_provider_message,
            }
        },
    )

    with caplog.at_level("ERROR", logger="askcrump.media"):
        error = MediaService._image_provider_exception(response)

    assert error.code == "IMAGE_UPSTREAM_ERROR"
    assert error.retryable is True
    assert [record.getMessage() for record in caplog.records] == [
        "Image provider rejected request category=upstream status=503 "
        "code=server_error type=upstream_failure"
    ]
    assert "unique-upstream-request" not in caplog.text
    assert sensitive_provider_message not in caplog.text


def test_provider_log_tokens_fail_closed_on_unstructured_values(caplog) -> None:
    response = httpx.Response(
        502,
        request=httpx.Request("POST", "https://api.openai.com/v1/images/generations"),
        json={
            "error": {
                "code": "private filename and prompt detail",
                "type": "unstructured upstream detail",
                "message": "another private provider diagnostic",
            }
        },
    )

    with caplog.at_level("ERROR", logger="askcrump.media"):
        MediaService._image_provider_exception(response)

    assert [record.getMessage() for record in caplog.records] == [
        "Image provider rejected request category=upstream status=502 code=unknown type=unknown"
    ]
    for private_value in (
        "private filename and prompt detail",
        "unstructured upstream detail",
        "another private provider diagnostic",
    ):
        assert private_value not in caplog.text


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
        "Edit one exact area",
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
        "Brush or outline the area yourself",
        "Brush",
        "Erase",
        "Lasso",
        "Move",
        "Invert",
        "Zoom in",
        "Fit image to screen",
        "Undo",
        "Redo",
        "Clear",
        "Outside-selection lock",
        "restores protected pixels",
        "Skin tone is not a race label",
        "Natural retouch",
        "Slightly deeper",
        "Slightly lighter",
        "No person is identified or classified",
        "LOCAL ADJUSTMENTS · NO AI OR CREDITS",
        "EXACT OVERLAY · NO AI OR CREDITS",
        "Place",
        "Add logo or image",
        "Exact overlay image",
        "Exact overlay text",
        "Exact text color",
        "Selected overlay size",
        "Selected overlay opacity",
        "Remove selected",
        "model to redraw it",
        "['warmth', 'Warmth']",
        "['exposure', 'Exposure']",
        "['saturation', 'Saturation']",
        "`${label} adjustment`",
        "Apply changes",
        "Show original",
        "Continue with AI edit",
        "image-adjust",
        "selectionHasVisiblePixels",
        "localAdjustmentMaskDataUrl",
        "maskDataUrl",
        "overlayDataUrl",
        "overlayCanvas.toBlob",
        "MAX_OVERLAY_ITEMS = 12",
        "MAX_OVERLAY_SOURCE_PIXELS = 16_777_216",
        "MAX_LASSO_POINTS = 4096",
        "MIN_LASSO_AREA = 0.0001",
        "function polygonArea",
        "function selectionCoverage",
        "function invertSelection",
        "crump-precision-lasso-guide",
        "applyPrecisionSelection",
        "aria-modal",
    ):
        assert contract in editor
    assert "face-api" not in editor
    assert "race detection" not in editor.lower()
    assert "race selector" not in editor.lower()
    assert "race classification" not in editor.lower()
    assert "localStorage" not in editor
    assert "sessionStorage" not in editor
    assert "request_id" not in editor
    assert "Crump Credits were used" in editor
    assert "rgba(226, 196, 126, 1)" in editor
    assert "image_adjust" in read("backend/routes/files.py")
    assert "payload.get('overlayDataUrl')" in read("backend/routes/files.py")
    assert "providerUsed': False" in read("backend/routes/files.py")
    assert "creditsUsed': 0" in read("backend/routes/files.py")
    backend = read("backend/media_service.py")
    assert "_decode_local_overlay" in backend
    assert "Image.alpha_composite" in backend
    assert "'deterministicOverlay': has_overlay" in backend
    assert "'sourceFileId': source_file_id" in backend
    assert "imageEditMask = precision.maskDataUrl" in composer
    assert "state.precisionImageEdit = null" in composer
    assert "imageEditMask" not in composer[composer.index("requestMeta: {") : composer.index("state.imageRecovery = null;")]
    assert "crump-precision-open" in styles
    assert "instruction: String(state.instruction?.value || '').trim()" in editor
    assert "guidedInstruction" in composer
    assert "input.dispatchEvent(new Event('input', {bubbles: true}))" in composer
    assert "Edit area" in composer
    assert "Precision Edit area" in composer
    assert "reflectAppliedImage" in composer
    assert "onApplied: ({file: savedFile})" in composer
    assert "base.width = image.naturalWidth" in editor
    assert "base.height = image.naturalHeight" in editor
    assert "stage.clientWidth" in editor
    assert "stage.clientHeight" in editor
    assert "state.fitWidth = Math.max(1" in editor
    assert "state.fitHeight = Math.max(1" in editor
    exact_script = "/crump-precision-image-edit.js?v=5.9.76-live-image-preview-1"
    exact_style = "/crump-precision-image-edit.css?v=5.9.76-precision-visible-1"
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
    assert "const IMAGE_REVISION_CODES = new Set([" in composer
    assert "'IMAGE_SAFETY_REJECTED'" in composer
    assert "'INVALID_IMAGE_EDIT_SOURCE'" in composer
    assert "'IMAGE_EDIT_SOURCE_TOO_LARGE'" in composer
    assert "IMAGE_REVISION_CODES.has(message.replyErrorCode)" in composer
    assert "reviseImageMessage(id);" in composer
    assert "unchangedRecoveredImageRequest(text, ready)" in composer
    assert "Change the wording or reference image before sending this request again." in composer
    assert "window.reviseImageMessage = reviseImageMessage" in composer
    assert "Image request needs changes — Tap to revise" in renderer
    assert "Reference image needs replacement — Tap to replace" in renderer
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
    assert "scenario') === 'invalid-reference'" in fixture
    assert "sendCalls" in verifier
    assert "ensureUsageCalls" in verifier
    assert "replacementRestored.attachmentCount === 0" in verifier
    assert "replacementRestored.fileInputClicks === 1" in verifier
    assert "replacementBlocked.ensureUsageCalls === 0" in verifier
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
