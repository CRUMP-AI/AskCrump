import base64
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from backend.video_service import VideoService, VideoServiceError


ROOT = Path(__file__).resolve().parents[1]
USER_ID = "00000000-0000-0000-0000-000000000001"
REQUEST_FINGERPRINT = "b" * 64
REFERENCE_IDS = [
    "00000000-0000-0000-0000-000000000011",
    "00000000-0000-0000-0000-000000000012",
    "00000000-0000-0000-0000-000000000013",
]


def confirmed_reference_plan(
    engine: str,
    plan: list[dict[str, str]],
) -> dict:
    return {
        "version": VideoService.REFERENCE_PLAN_VERSION,
        "confirmed": True,
        "engine": engine,
        "capability": VideoService.reference_capability(engine),
        "fileIds": [item["fileId"] for item in plan],
        "referencePlan": plan,
    }


def settings():
    return SimpleNamespace(
        gemini_api_key="gemini-test",
        gemini_video_model="veo-lite-test",
        gemini_video_extend_model="veo-fast-test",
        runway_api_secret="runway-test",
        runway_video_model="gen4.5-test",
        runway_api_version="2024-11-06",
        video_generation_enabled=True,
        max_active_video_jobs_per_user=1,
        max_generated_video_bytes=90 * 1024 * 1024,
        video_daily_provider_budget_cents=10_000,
        video_user_daily_provider_budget_cents=2_000,
        runway_monthly_provider_budget_cents=50_000,
    )


def png_bytes() -> bytes:
    output = BytesIO()
    Image.new("RGB", (16, 16), "navy").save(output, format="PNG")
    return output.getvalue()


class ReferenceFiles:
    def __init__(self) -> None:
        self.lookups: list[tuple[str, str]] = []
        self.downloads: list[str] = []
        self.raw = png_bytes()

    async def get_owned(self, *, user_id: str, file_id: str):
        self.lookups.append((user_id, file_id))
        return {
            "id": file_id,
            "mime_type": "image/png",
            "storage_path": f"private/{file_id}.png",
        }

    async def download_bytes(self, *, row, max_bytes: int):
        assert max_bytes == VideoService.REFERENCE_IMAGE_MAX_BYTES
        self.downloads.append(row["id"])
        return self.raw


@pytest.mark.asyncio
async def test_video_reference_plan_preserves_owner_scoped_order_and_roles() -> None:
    files = ReferenceFiles()
    service = VideoService(settings(), SimpleNamespace(), files)
    plan = [
        {"fileId": REFERENCE_IDS[0], "role": "logo"},
        {"fileId": REFERENCE_IDS[1], "role": "mascot"},
        {"fileId": REFERENCE_IDS[2], "role": "style"},
    ]

    references = await service.prepare_reference_images(
        user_id=USER_ID,
        file_ids=REFERENCE_IDS,
        reference_plan=plan,
        engine="extendable",
    )

    assert files.lookups == [(USER_ID, file_id) for file_id in REFERENCE_IDS]
    assert files.downloads == REFERENCE_IDS
    assert [(item["fileId"], item["role"]) for item in references] == [
        (item["fileId"], item["role"]) for item in plan
    ]
    assert all(item["mimeType"] == "image/png" for item in references)
    assert all(base64.b64decode(item["data"]).startswith(b"\x89PNG") for item in references)


@pytest.mark.asyncio
async def test_video_reference_plan_rejects_order_role_and_blank_id_before_owner_lookup() -> None:
    files = ReferenceFiles()
    service = VideoService(settings(), SimpleNamespace(), files)

    invalid_plans = [
        [
            {"fileId": REFERENCE_IDS[1], "role": "subject"},
            {"fileId": REFERENCE_IDS[0], "role": "logo"},
        ],
        [
            {"fileId": REFERENCE_IDS[0], "role": "subject"},
            {"fileId": REFERENCE_IDS[1], "role": "inspiration"},
        ],
        [
            {"fileId": REFERENCE_IDS[0], "role": "subject"},
            {"fileId": "", "role": "logo"},
        ],
    ]
    for plan in invalid_plans:
        with pytest.raises(VideoServiceError) as caught:
            await service.prepare_reference_images(
                user_id=USER_ID,
                file_ids=REFERENCE_IDS[:2],
                reference_plan=plan,
                engine="extendable",
            )
        assert caught.value.code == "INVALID_VIDEO_REFERENCE_PLAN"

    assert files.lookups == []


@pytest.mark.asyncio
async def test_video_reference_count_matches_engine_semantics_before_owner_lookup() -> None:
    files = ReferenceFiles()
    service = VideoService(settings(), SimpleNamespace(), files)
    plan = [
        {"fileId": REFERENCE_IDS[0], "role": "subject"},
        {"fileId": REFERENCE_IDS[1], "role": "style"},
    ]

    with pytest.raises(VideoServiceError) as caught:
        await service.prepare_reference_images(
            user_id=USER_ID,
            file_ids=REFERENCE_IDS[:2],
            reference_plan=plan,
            engine="quick",
        )

    assert caught.value.code == "TOO_MANY_VIDEO_REFERENCES"
    assert files.lookups == []
    assert VideoService.reference_limit("quick") == 1
    assert VideoService.reference_limit("cinematic") == 1
    assert VideoService.reference_limit("extendable") == 3


def test_video_reference_confirmation_accepts_only_the_exact_versioned_plan() -> None:
    plan = [
        {"fileId": REFERENCE_IDS[0], "role": "subject"},
        {"fileId": REFERENCE_IDS[1], "role": "logo"},
    ]

    normalized = VideoService.normalize_reference_plan(
        file_ids=REFERENCE_IDS[:2],
        reference_plan=plan,
        engine="extendable",
        reference_confirmation=confirmed_reference_plan("extendable", plan),
    )

    assert normalized == plan
    assert VideoService.normalize_reference_plan(
        file_ids=None,
        reference_plan=None,
        engine="quick",
        reference_confirmation=None,
    ) == []


@pytest.mark.parametrize(
    ("mutate", "expected_code"),
    [
        (lambda _confirmation: None, "VIDEO_REFERENCE_CONFIRMATION_REQUIRED"),
        (
            lambda confirmation: {**confirmation, "confirmed": False},
            "VIDEO_REFERENCE_CONFIRMATION_REQUIRED",
        ),
        (
            lambda confirmation: {**confirmation, "version": "video-reference-plan-v0"},
            "VIDEO_REFERENCE_CONFIRMATION_STALE",
        ),
        (
            lambda confirmation: {
                **confirmation,
                "fileIds": list(reversed(confirmation["fileIds"])),
            },
            "VIDEO_REFERENCE_CONFIRMATION_STALE",
        ),
        (
            lambda confirmation: {
                **confirmation,
                "referencePlan": [
                    confirmation["referencePlan"][1],
                    confirmation["referencePlan"][0],
                ],
            },
            "VIDEO_REFERENCE_CONFIRMATION_STALE",
        ),
        (
            lambda confirmation: {**confirmation, "engine": "quick"},
            "VIDEO_REFERENCE_CONFIRMATION_STALE",
        ),
        (
            lambda confirmation: {
                **confirmation,
                "capability": {
                    **confirmation["capability"],
                    "provider": "runway",
                },
            },
            "VIDEO_REFERENCE_CONFIRMATION_STALE",
        ),
        (
            lambda confirmation: {
                **confirmation,
                "capability": {
                    **confirmation["capability"],
                    "mode": "initial-frame",
                },
            },
            "VIDEO_REFERENCE_CONFIRMATION_STALE",
        ),
    ],
    ids=[
        "unconfirmed",
        "confirmed-false",
        "stale-version",
        "reordered-ids",
        "reordered-roles",
        "changed-engine",
        "changed-provider",
        "changed-mode",
    ],
)
def test_video_reference_confirmation_rejects_stale_or_changed_contracts(
    mutate,
    expected_code: str,
) -> None:
    plan = [
        {"fileId": REFERENCE_IDS[0], "role": "subject"},
        {"fileId": REFERENCE_IDS[1], "role": "logo"},
    ]
    confirmation = mutate(confirmed_reference_plan("extendable", plan))

    with pytest.raises(VideoServiceError) as caught:
        VideoService.normalize_reference_plan(
            file_ids=REFERENCE_IDS[:2],
            reference_plan=plan,
            engine="extendable",
            reference_confirmation=confirmation,
        )

    assert caught.value.code == expected_code
    assert caught.value.status_code == 409
    assert caught.value.refund_eligible is False
    assert "No credits were used" in caught.value.message


def test_video_reference_confirmation_rejects_reordered_request_before_spend() -> None:
    ordered = [
        {"fileId": REFERENCE_IDS[0], "role": "subject"},
        {"fileId": REFERENCE_IDS[1], "role": "logo"},
    ]
    reordered = [ordered[1], ordered[0]]

    with pytest.raises(VideoServiceError) as caught:
        VideoService.normalize_reference_plan(
            file_ids=REFERENCE_IDS[:2],
            reference_plan=reordered,
            engine="extendable",
            reference_confirmation=confirmed_reference_plan("extendable", reordered),
        )

    assert caught.value.code == "VIDEO_REFERENCE_CONFIRMATION_STALE"
    assert caught.value.status_code == 409
    assert caught.value.refund_eligible is False
    assert "No credits were used" in caught.value.message


def test_video_provider_prompt_enumerates_roles_and_states_provider_semantics_honestly() -> None:
    plan = [
        {"fileId": REFERENCE_IDS[0], "role": "subject"},
        {"fileId": REFERENCE_IDS[1], "role": "logo"},
    ]

    appearance = VideoService.provider_prompt(
        "Keep the product centered while the camera moves slowly around it.",
        max_chars=2000,
        reference_plan=plan,
        reference_mode="appearance-guidance",
    )
    assert "Input image 1: Subject / product (subject)." in appearance
    assert "Input image 2: Logo / wordmark (logo)." in appearance
    assert "best-effort appearance guidance" in appearance
    assert "not pixel-locked frames" in appearance
    assert "Exact pixels and readable text are not guaranteed" in appearance

    starting_frame = VideoService.provider_prompt(
        "Animate this opening frame with a slow camera push.",
        max_chars=1600,
        reference_plan=[plan[0]],
        reference_mode="initial-frame",
    )
    assert "single starting frame" in starting_frame
    assert "Input image 1: Subject / product (subject)." in starting_frame
    assert "Input image 2" not in starting_frame


def test_reference_expanded_video_prompt_is_validated_as_one_bounded_request() -> None:
    references = [{
        "fileId": REFERENCE_IDS[0],
        "role": "logo",
        "mimeType": "image/png",
        "data": "cHJpdmF0ZQ==",
    }]

    with pytest.raises(VideoServiceError) as caught:
        VideoService.prepare_provider_prompt(
            prompt="x" * 3800,
            engine="extendable",
            references=references,
        )

    assert caught.value.code == "PROMPT_TOO_LONG"


class CaptureDB:
    def __init__(self) -> None:
        self.rows: dict[str, dict] = {}

    async def select(self, _table, **_kwargs):
        return []

    async def select_one(self, _table, **_kwargs):
        return None

    async def insert(self, table, payload):
        assert table == "media_jobs"
        self.rows[payload["id"]] = dict(payload)
        return [dict(payload)]

    async def update(self, table, payload, *, filters, **_kwargs):
        assert table == "media_jobs"
        job_id = str(filters["id"]).removeprefix("eq.")
        self.rows[job_id].update(payload)
        return [dict(self.rows[job_id])]

    async def rpc(self, function_name, payload, *, retry_transient=False):
        assert retry_transient is True
        row = self.rows[payload["p_job_id"]]
        assert row["idempotency_key"] == payload["p_idempotency_key"]
        assert row["request_fingerprint"] == payload["p_request_fingerprint"]
        if function_name == "claim_video_provider_launch":
            row["video_phase"] = "launching"
            row["lease_token"] = payload["p_launch_token"]
            return [{"outcome": "claimed", "job": dict(row)}]
        if function_name == "complete_video_provider_launch":
            row.update(
                {
                    "status": "processing",
                    "video_phase": "processing",
                    "lease_token": None,
                    "lease_expires_at": None,
                    "provider_job_id": payload["p_provider_job_id"],
                    "metadata": {
                        **(row.get("metadata") or {}),
                        "providerAccepted": True,
                    },
                }
            )
            return [{"outcome": "completed", "job": dict(row)}]
        raise AssertionError(f"Unexpected RPC: {function_name}")


@pytest.mark.asyncio
async def test_video_job_persists_only_safe_role_receipt_and_sends_extendable_guidance() -> None:
    db = CaptureDB()
    service = VideoService(settings(), db, SimpleNamespace())
    provider_call = {}

    async def fake_start(**kwargs):
        provider_call.update(kwargs)
        return "provider-video-1"

    service.gemini.start = fake_start
    references = [
        {
            "fileId": REFERENCE_IDS[0],
            "role": "mascot",
            "mimeType": "image/png",
            "data": "cHJpdmF0ZS1pbWFnZS0x",
        },
        {
            "fileId": REFERENCE_IDS[1],
            "role": "style",
            "mimeType": "image/png",
            "data": "cHJpdmF0ZS1pbWFnZS0y",
        },
    ]

    row = await service.start(
        user_id=USER_ID,
        prompt="Keep the mascot recognizable while it walks through the branded scene.",
        engine="extendable",
        aspect_ratio="16:9",
        resolution="720p",
        duration_seconds=8,
        idempotency_key="reference-role-receipt",
        request_fingerprint=REQUEST_FINGERPRINT,
        reference_images=references,
        charge_receipt={"eventId": "credit:test"},
    )

    expected_receipt = [
        {"input": 1, "fileId": REFERENCE_IDS[0], "role": "mascot"},
        {"input": 2, "fileId": REFERENCE_IDS[1], "role": "style"},
    ]
    assert provider_call["reference_images"] == references
    assert provider_call["initial_image"] is None
    assert row["metadata"]["referenceMode"] == "appearance-guidance"
    assert row["metadata"]["referencePlan"] == expected_receipt
    assert row["metadata"]["referenceVerification"] == "not-performed"
    assert "data" not in row["metadata"]
    ready_row = {**row, "status": "ready"}
    public = await service.public_job(user_id=USER_ID, row=ready_row)
    assert public["status"] == "ready"
    assert public["referenceMode"] == "appearance-guidance"
    assert public["referencePlan"] == expected_receipt
    assert public["referenceVerification"] == "not-performed"
    assert "referenceVerified" not in public


def test_video_route_validates_reference_plan_before_budget_charge_and_provider() -> None:
    source = (ROOT / "backend/routes/media.py").read_text(encoding="utf-8")
    prepare = source.index("reference_images = await video.prepare_reference_images")
    plan = source.index("reference_plan=normalized_reference_plan", prepare)
    prompt = source.index("video.prepare_provider_prompt", plan)
    budget = source.index("await video.guard_provider_budget", prompt)
    charge = source.index("receipt = await features.consume_video_reservation", budget)
    provider = source.index("row = await video.start", charge)

    assert prepare < plan < prompt < budget < charge < provider
    assert '"referencePlan": reference_receipt' in source


def test_completed_video_ui_exposes_an_honest_ordered_reference_receipt_without_spend() -> None:
    loader = (ROOT / "public" / "crump-product-loader.js").read_text(encoding="utf-8")
    product = (ROOT / "public" / "crump-product-5.3.js").read_text(encoding="utf-8")
    styles = (ROOT / "public" / "crump-product-5.3.css").read_text(encoding="utf-8")
    verifier = (ROOT / "scripts" / "verify-video-reference-browser.cjs").read_text(encoding="utf-8")
    receipt_renderer = loader.split("function renderVideoReferenceReceipt", 1)[1].split(
        "window.CrumpVideoReferenceReceipt", 1
    )[0]

    assert "window.CrumpVideoReferenceReceipt?.render(result, job);" in product
    assert "job?.status !== 'ready'" in receipt_renderer
    assert "references.forEach((reference, index)" in receipt_renderer
    assert "Input image ${index + 1}" in receipt_renderer
    assert "VIDEO_REFERENCE_ROLE_LABELS[reference.role]" in receipt_renderer
    assert "sent as the starting frame" in loader
    assert "best-effort appearance guidance" in loader
    assert "not as pixel-locked frames or layouts" in loader
    assert "Exact logos, readable text, and subject identity were not automatically verified" in receipt_renderer
    assert "compare them side by side with each source image" in receipt_renderer
    assert "deterministic overlay" in receipt_renderer
    assert "Open Files to compare" in receipt_renderer
    assert "video-reference-plan-v1" in product
    assert "confirmedVideoReferencePlan" in product
    assert "referencePlanConfirmation" in product
    assert "starting-frame-not-pixel-locked" in product
    assert "best-effort-not-pixel-locked" in product
    assert "fetch(" not in receipt_renderer
    assert "api(" not in receipt_renderer
    assert ".crump53-video-reference-receipt" in styles
    assert "providerStarts !== 1" in verifier
    assert "startingFrameReceipt" in verifier
