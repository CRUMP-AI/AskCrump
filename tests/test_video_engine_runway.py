from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from backend.video_providers import GeminiVeoProvider, ProviderError, RunwayProvider
from backend.video_service import VideoService, VideoServiceError


ROOT = Path(__file__).resolve().parents[1]
USER_ID = "00000000-0000-0000-0000-000000000001"
REQUEST_FINGERPRINT = "a" * 64


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def settings(**overrides):
    values = {
        "gemini_api_key": "gemini-test",
        "gemini_video_model": "veo-3.1-lite-generate-preview",
        "gemini_video_extend_model": "veo-3.1-fast-generate-preview",
        "runway_api_secret": "runway-test",
        "runway_video_model": "gen4.5",
        "runway_api_version": "2024-11-06",
        "video_generation_enabled": True,
        "max_active_video_jobs_per_user": 1,
        "max_generated_video_bytes": 90 * 1024 * 1024,
        "video_daily_provider_budget_cents": 10_000,
        "video_user_daily_provider_budget_cents": 2_000,
        "runway_monthly_provider_budget_cents": 50_000,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_video_engines_keep_quick_compatible_and_make_extension_explicit():
    assert VideoService.normalize_request(engine="quick", resolution="1080p", duration_seconds=5) == (
        "quick", "1080p", 8,
    )
    assert VideoService.normalize_request(engine="extendable", resolution="1080p", duration_seconds=5) == (
        "extendable", "720p", 8,
    )
    assert VideoService.normalize_request(engine="cinematic", resolution="1080p", duration_seconds=10) == (
        "cinematic", "720p", 10,
    )
    assert VideoService.feature_code(engine="cinematic", resolution="720p", duration_seconds=10) == "video_cinematic_10"
    assert VideoService.provider_cost_cents(
        engine="cinematic", resolution="720p", duration_seconds=10,
    ) == 120
    assert VideoService.provider_cost_cents(
        engine="extendable", resolution="720p", duration_seconds=8, operation_type="extend",
    ) == 80


def test_video_feature_paywalls_and_provider_keys_are_explicit():
    policy = read("backend/feature_service.py")
    assert '"video_extendable"' in policy and '"professional"' in policy and "80" in policy
    assert '"video_continue"' in policy
    assert '"video_cinematic_5"' in policy and '"RUNWAYML_API_SECRET"' in policy
    assert '"video_cinematic_10"' in policy and '"enterprise"' in policy and "120" in policy


class SpendDB:
    def __init__(self, rows):
        self.rows = rows

    async def select(self, _table, **_kwargs):
        return list(self.rows)


@pytest.mark.asyncio
async def test_provider_budget_guard_blocks_runaway_spend_but_can_bypass_founder_user_cap():
    service = VideoService(
        settings(video_user_daily_provider_budget_cents=100, video_daily_provider_budget_cents=10_000),
        SpendDB([{"estimated_provider_cost_cents": 80}]),
        SimpleNamespace(),
    )
    with pytest.raises(VideoServiceError) as exc:
        await service.guard_provider_budget(
            user_id=USER_ID,
            provider="gemini",
            estimated_cost_cents=80,
            bypass_user_limit=False,
        )
    assert exc.value.code == "VIDEO_USER_PROVIDER_BUDGET_LIMIT"

    # Founder/internal access bypasses the per-user guard but not the global guard.
    await service.guard_provider_budget(
        user_id=USER_ID,
        provider="gemini",
        estimated_cost_cents=80,
        bypass_user_limit=True,
    )


def test_continuation_stops_before_combined_file_is_likely_to_break_storage_guard():
    service = VideoService(settings(max_generated_video_bytes=90 * 1024 * 1024), SimpleNamespace(), SimpleNamespace())
    base = {
        "id": USER_ID,
        "status": "ready",
        "engine": "extendable",
        "provider": "gemini",
        "resolution": "720p",
        "provider_asset_reference": "https://generativelanguage.googleapis.com/v1beta/files/example:download?alt=media",
        "provider_asset_expires_at": "2999-01-01T00:00:00+00:00",
        "sequence_index": 3,
        "duration_seconds": 29,
        "metadata": {"storedBytes": 20 * 1024 * 1024},
    }
    assert service._continuation_available(base) is True
    too_large = {**base, "metadata": {"storedBytes": 88 * 1024 * 1024}}
    assert service._continuation_available(too_large) is False


class FakeAsyncClient:
    last_post = None
    poll_body = None

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, *, headers, json):
        type(self).last_post = (url, headers, json)
        body = {"name": "operations/gemini-123"} if "googleapis.com" in url else {"id": "task-123"}
        return httpx.Response(200, request=httpx.Request("POST", url), json=body)

    async def get(self, url, *, headers):
        return httpx.Response(200, request=httpx.Request("GET", url), json=type(self).poll_body or {})


class StartServerErrorClient:
    post_count = 0

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, *, headers, json):
        type(self).post_count += 1
        body = (
            {"error": {"status": "INTERNAL", "message": "provider failure"}}
            if "googleapis.com" in url
            else {"error": "provider failure"}
        )
        return httpx.Response(
            503,
            request=httpx.Request("POST", url),
            json=body,
        )


@pytest.mark.asyncio
async def test_runway_adapter_keeps_secret_server_side_and_uses_versioned_gen45_api(monkeypatch):
    import backend.video_providers as providers

    monkeypatch.setattr(providers.httpx, "AsyncClient", FakeAsyncClient)
    runway = RunwayProvider(settings())
    task_id = await runway.start(
        model="gen4.5",
        prompt="A cinematic tracking shot through a rain-soaked city.",
        aspect_ratio="16:9",
        duration_seconds=5,
    )
    assert task_id == "task-123"
    url, headers, body = FakeAsyncClient.last_post
    assert url.endswith("/v1/text_to_video")
    assert headers["Authorization"] == "Bearer runway-test"
    assert headers["X-Runway-Version"] == "2024-11-06"
    assert body == {
        "model": "gen4.5",
        "promptText": "A cinematic tracking shot through a rain-soaked city.",
        "ratio": "1280:720",
        "duration": 5,
    }


@pytest.mark.asyncio
async def test_runway_reference_uses_private_data_uri_and_image_to_video_endpoint(monkeypatch):
    import backend.video_providers as providers

    monkeypatch.setattr(providers.httpx, "AsyncClient", FakeAsyncClient)
    task_id = await RunwayProvider(settings()).start(
        model="gen4.5",
        prompt="Animate the supplied vehicle while preserving its appearance.",
        aspect_ratio="9:16",
        duration_seconds=5,
        prompt_image="data:image/png;base64,cHJpdmF0ZS1pbWFnZQ==",
    )

    assert task_id == "task-123"
    url, _, body = FakeAsyncClient.last_post
    assert url.endswith("/v1/image_to_video")
    assert body["promptImage"] == "data:image/png;base64,cHJpdmF0ZS1pbWFnZQ=="
    assert body["ratio"] == "720:1280"


@pytest.mark.asyncio
async def test_gemini_reference_payloads_match_engine_capabilities(monkeypatch):
    import backend.video_providers as providers

    monkeypatch.setattr(providers.httpx, "AsyncClient", FakeAsyncClient)
    provider = GeminiVeoProvider(settings())
    reference = {"mimeType": "image/png", "data": "cmVmZXJlbmNl"}

    await provider.start(
        model="veo-3.1-fast-generate-preview",
        prompt="Preserve this product.",
        aspect_ratio="16:9",
        resolution="720p",
        reference_images=[reference, reference],
    )
    _, _, body = FakeAsyncClient.last_post
    instance = body["instances"][0]
    assert len(instance["referenceImages"]) == 2
    assert instance["referenceImages"][0] == {
        "image": {"inlineData": {"mimeType": "image/png", "data": "cmVmZXJlbmNl"}},
        "referenceType": "asset",
    }
    assert "image" not in instance

    await provider.start(
        model="veo-3.1-lite-generate-preview",
        prompt="Animate this opening frame.",
        aspect_ratio="16:9",
        resolution="720p",
        initial_image=reference,
    )
    _, _, body = FakeAsyncClient.last_post
    instance = body["instances"][0]
    assert instance["image"] == {"inlineData": reference}
    assert "referenceImages" not in instance


@pytest.mark.asyncio
async def test_runway_input_safety_failure_is_not_turned_into_free_retry(monkeypatch):
    import backend.video_providers as providers

    monkeypatch.setattr(providers.httpx, "AsyncClient", FakeAsyncClient)
    FakeAsyncClient.poll_body = {
        "status": "FAILED",
        "failureCode": "SAFETY.INPUT.TEXT",
        "failure": "diagnostic provider text",
    }
    result = await RunwayProvider(settings()).poll("task-123")
    assert result["status"] == "failed"
    assert result["refundEligible"] is False


@pytest.mark.asyncio
async def test_runway_output_safety_failure_is_not_refunded(monkeypatch):
    cfg = settings(runway_api_secret="runway-secret")
    provider = RunwayProvider(cfg)

    class FakeResponse:
        status_code = 200
        headers = {}
        text = ""

        @staticmethod
        def json():
            return {
                "status": "FAILED",
                "failureCode": "SAFETY.OUTPUT.VIDEO",
                "failure": "provider diagnostic",
            }

    class FakeClient:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return False
        async def get(self, *args, **kwargs): return FakeResponse()

    monkeypatch.setattr(httpx, "AsyncClient", lambda *args, **kwargs: FakeClient())
    result = await provider.poll("task-123")
    assert result["status"] == "failed"
    assert result["refundEligible"] is False
    assert result["failureMessage"] == "Runway could not generate that request under its safety rules."


def test_poll_http_5xx_remains_status_retry_not_launch_acceptance_unknown():
    gemini_response = httpx.Response(
        503,
        request=httpx.Request("GET", "https://generativelanguage.googleapis.com/v1beta/operations/test"),
        json={"error": {"status": "INTERNAL", "message": "temporary"}},
    )
    runway_response = httpx.Response(
        503,
        request=httpx.Request("GET", "https://api.dev.runwayml.com/v1/tasks/test"),
        json={"error": "temporary"},
    )

    for error in (
        GeminiVeoProvider._exception(gemini_response, checking=True),
        RunwayProvider._exception(runway_response, checking=True),
    ):
        assert error.code == "VIDEO_STATUS_UNAVAILABLE"
        assert error.retryable is True
        assert error.acceptance_unknown is False


def test_video_continuation_schema_is_private_lineage_not_a_second_storage_system():
    migration = read("migrations/015_video_engine_continuations.sql")
    for column in (
        "engine text",
        "operation_type text",
        "parent_job_id uuid",
        "root_job_id uuid",
        "sequence_index integer",
        "duration_seconds integer",
        "provider_asset_reference text",
        "provider_asset_expires_at timestamptz",
        "estimated_provider_cost_cents integer",
    ):
        assert column in migration
    assert "references public.media_jobs(id)" in migration
    assert "create table" not in migration.lower()


def test_video_ui_surfaces_engines_continue_flow_and_runway_attribution():
    ui = read("public/crump-product-5.3.js")
    css = read("public/crump-product-5.3.css")
    assert "Quick · Veo Lite" in ui
    assert "Extendable · Veo Fast + Continue" in ui
    assert "Cinematic · Runway Gen-4.5" in ui
    assert "Continue scene" in ui
    assert "/continue`" in ui
    assert "Powered by Runway" in ui
    assert "https://runwayml.com" in ui
    assert ".crump53-video-continuation" in css
    assert "Optional appearance guidance · up to 3" in ui
    assert "best-effort appearance guidance, not as a pixel-locked frame or layout" in ui
    assert "referenceFileIds" in ui
    assert "window.CrumpFileTools.upload(file)" in ui
    assert ".crump53-video-reference-card" in css


def test_windows_javascript_validation_uses_file_url_to_path():
    checker = read("scripts/check-javascript.mjs")
    assert "fileURLToPath" in checker
    assert "['--check', fileURLToPath(path)]" in checker
    assert "path.pathname" not in checker

class ReservationDB:
    def __init__(self):
        self.rows = {}
        self.events = []

    async def select(self, table, **kwargs):
        if table == "media_jobs":
            return []
        return []

    async def select_one(self, table, *, filters=None, **kwargs):
        if table != "media_jobs":
            return None
        filters = filters or {}
        wanted_id = str(filters.get("id") or "").removeprefix("eq.")
        if wanted_id:
            row = self.rows.get(wanted_id)
            return dict(row) if row else None
        wanted_key = str(filters.get("idempotency_key") or "").removeprefix("eq.")
        for row in self.rows.values():
            if wanted_key and row.get("idempotency_key") == wanted_key:
                return dict(row)
        return None

    async def insert(self, table, payload):
        assert table == "media_jobs"
        self.events.append(("insert", payload["status"], payload["provider_job_id"]))
        self.rows[payload["id"]] = dict(payload)
        return [dict(payload)]

    async def update(self, table, payload, *, filters):
        assert table == "media_jobs"
        self.events.append(("update", payload.get("status"), payload.get("provider_job_id")))
        row = next(iter(self.rows.values()))
        row.update(payload)
        return [dict(row)]

    async def rpc(self, function_name, payload, *, retry_transient=False):
        assert retry_transient is True
        row = self.rows.get(payload.get("p_job_id"))
        if not row:
            return [{"outcome": "missing", "job": {}}]
        assert row["user_id"] == payload["p_user_id"]
        assert row["idempotency_key"] == payload["p_idempotency_key"]
        assert row["request_fingerprint"] == payload["p_request_fingerprint"]

        if function_name == "claim_video_provider_launch":
            if row["video_phase"] == "ready_to_launch":
                if not payload["p_claim_ready"]:
                    return [{"outcome": "ready", "job": dict(row)}]
                row["video_phase"] = "launching"
                row["lease_token"] = payload["p_launch_token"]
                row["metadata"] = {
                    **(row.get("metadata") or {}),
                    "videoPhase": "launching",
                }
                return [{"outcome": "claimed", "job": dict(row)}]
            if row["video_phase"] == "launching":
                return [{"outcome": "launch_in_progress", "job": dict(row)}]
            return [{"outcome": "current", "job": dict(row)}]

        if function_name == "complete_video_provider_launch":
            assert row["video_phase"] == "launching"
            assert row["lease_token"] == payload["p_launch_token"]
            row.update(
                {
                    "status": "processing",
                    "provider_job_id": payload["p_provider_job_id"],
                    "video_phase": "processing",
                    "lease_token": None,
                    "lease_expires_at": None,
                    "metadata": {
                        **(row.get("metadata") or {}),
                        "providerAccepted": True,
                        "videoPhase": "processing",
                    },
                }
            )
            return [{"outcome": "completed", "job": dict(row)}]

        if function_name == "fail_video_provider_launch":
            assert row["video_phase"] == "launching"
            assert row["lease_token"] == payload["p_launch_token"]
            acceptance = payload["p_provider_acceptance"]
            row.update(
                {
                    "status": "failed",
                    "video_phase": "failed",
                    "lease_token": None,
                    "lease_expires_at": None,
                    "billing_refunded": True,
                    "error_message": payload["p_message"],
                    "estimated_provider_cost_cents": (
                        0
                        if acceptance == "rejected"
                        else row["estimated_provider_cost_cents"]
                    ),
                    "metadata": {
                        **(row.get("metadata") or {}),
                        "providerAccepted": False,
                        "providerAcceptance": acceptance,
                        "providerFailureCode": payload["p_failure_code"],
                        "refundEligible": False,
                        "videoPhase": "failed",
                    },
                }
            )
            return [{"outcome": "failed", "job": dict(row)}]

        raise AssertionError(f"Unexpected RPC: {function_name}")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("engine", "resolution", "duration", "key", "expected_cost"),
    [
        ("quick", "720p", 8, "gemini-start-5xx", 40),
        ("cinematic", "720p", 5, "runway-start-5xx", 60),
    ],
)
async def test_start_http_5xx_is_unknown_refunded_and_never_relaunched(
    monkeypatch,
    engine,
    resolution,
    duration,
    key,
    expected_cost,
):
    import backend.video_providers as providers

    StartServerErrorClient.post_count = 0
    monkeypatch.setattr(providers.httpx, "AsyncClient", StartServerErrorClient)
    db = ReservationDB()
    service = VideoService(settings(), db, SimpleNamespace())

    with pytest.raises(VideoServiceError) as caught:
        await service.start(
            user_id=USER_ID,
            prompt="A production promo scene whose start response is ambiguous.",
            engine=engine,
            aspect_ratio="16:9",
            resolution=resolution,
            duration_seconds=duration,
            idempotency_key=key,
            request_fingerprint=REQUEST_FINGERPRINT,
            charge_receipt={
                "eventId": "credit:00000000-0000-0000-0000-000000000099",
                "paymentSource": "credits",
            },
        )

    assert caught.value.code == "VIDEO_PROVIDER_UNAVAILABLE"
    assert caught.value.retryable is False
    assert caught.value.refund_eligible is False
    failed = next(iter(db.rows.values()))
    assert failed["status"] == "failed"
    assert failed["billing_refunded"] is True
    assert failed["metadata"]["providerAcceptance"] == "unknown"
    assert failed["estimated_provider_cost_cents"] == expected_cost

    replay = await service.poll(user_id=USER_ID, job_id=failed["id"])
    assert replay["status"] == "failed"
    assert StartServerErrorClient.post_count == 1


@pytest.mark.asyncio
async def test_provider_id_completion_existing_outcome_never_restarts_provider():
    class CompleteExistingDB(ReservationDB):
        async def rpc(self, function_name, payload, *, retry_transient=False):
            if function_name != "complete_video_provider_launch":
                return await super().rpc(
                    function_name,
                    payload,
                    retry_transient=retry_transient,
                )
            row = self.rows[payload["p_job_id"]]
            row.update(
                {
                    "status": "processing",
                    "provider_job_id": payload["p_provider_job_id"],
                    "video_phase": "processing",
                    "lease_token": None,
                    "lease_expires_at": None,
                }
            )
            return [{"outcome": "existing", "job": dict(row)}]

    db = CompleteExistingDB()
    service = VideoService(settings(), db, SimpleNamespace())
    starts = 0

    async def fake_start(**_kwargs):
        nonlocal starts
        starts += 1
        return "runway-task-existing"

    service.runway.start = fake_start
    row = await service.start(
        user_id=USER_ID,
        prompt="A provider ID settlement response-loss fixture.",
        engine="cinematic",
        aspect_ratio="16:9",
        resolution="720p",
        duration_seconds=5,
        idempotency_key="complete-existing",
        request_fingerprint=REQUEST_FINGERPRINT,
        charge_receipt={"eventId": "included-fixture"},
    )

    assert row["status"] == "processing"
    assert row["provider_job_id"] == "runway-task-existing"
    assert starts == 1


@pytest.mark.asyncio
async def test_provider_job_is_reserved_before_runway_spend():
    db = ReservationDB()
    service = VideoService(settings(), db, SimpleNamespace())

    async def fake_start(**kwargs):
        assert db.events and db.events[0][0] == "insert"
        assert db.events[0][1] == "queued"
        assert str(db.events[0][2]).startswith("pending:")
        return "runway-task-1"

    service.runway.start = fake_start
    row = await service.start(
        user_id=USER_ID,
        prompt="A carefully composed cinematic crane shot over a futuristic coastal city.",
        engine="cinematic",
        aspect_ratio="16:9",
        resolution="720p",
        duration_seconds=5,
        idempotency_key="runway-reservation",
        request_fingerprint=REQUEST_FINGERPRINT,
        charge_receipt={"eventId": "credit:test"},
    )
    assert row["status"] == "processing"
    assert row["provider_job_id"] == "runway-task-1"
    assert row["metadata"]["providerAccepted"] is True


@pytest.mark.asyncio
async def test_same_key_insert_race_returns_existing_job_without_second_provider_start():
    existing = {
        "id": "00000000-0000-0000-0000-000000000090",
        "user_id": USER_ID,
        "idempotency_key": "same-key-race",
        "request_fingerprint": REQUEST_FINGERPRINT,
        "status": "queued",
        "provider_job_id": "pending:existing",
    }

    class SameKeyRaceDB(ReservationDB):
        def __init__(self):
            super().__init__()
            self.idempotency_lookups = 0

        async def select_one(self, table, *, filters=None, **kwargs):
            if table == "media_jobs" and "idempotency_key" in (filters or {}):
                self.idempotency_lookups += 1
                return existing if self.idempotency_lookups > 1 else None
            return None

        async def insert(self, table, payload):
            assert table == "media_jobs"
            raise RuntimeError("duplicate media_jobs_user_idempotency_idx")

    db = SameKeyRaceDB()
    service = VideoService(settings(), db, SimpleNamespace())
    provider_starts = 0

    async def fail_if_started(**_kwargs):
        nonlocal provider_starts
        provider_starts += 1
        raise AssertionError("an idempotent replay must not start a second provider job")

    service.runway.start = fail_if_started
    row = await service.start(
        user_id=USER_ID,
        prompt="A careful same-key video reservation race.",
        engine="cinematic",
        aspect_ratio="16:9",
        resolution="720p",
        duration_seconds=5,
        idempotency_key="same-key-race",
        request_fingerprint=REQUEST_FINGERPRINT,
        charge_receipt={"eventId": "credit:same-key-race"},
    )

    assert row == existing
    assert db.idempotency_lookups == 2
    assert provider_starts == 0


@pytest.mark.asyncio
async def test_local_pending_reservation_is_never_polled_as_a_provider_job():
    placeholder = {
        "id": "00000000-0000-0000-0000-000000000093",
        "user_id": USER_ID,
        "status": "queued",
        "provider": "runway",
        "provider_job_id": "pending:00000000-0000-0000-0000-000000000093",
        "idempotency_key": "pending-launch",
        "request_fingerprint": REQUEST_FINGERPRINT,
        "video_phase": "launching",
        "lease_token": "00000000-0000-0000-0000-000000000094",
        "lease_expires_at": "2999-01-01T00:00:00+00:00",
        "metadata": {"billingPending": False, "providerAccepted": False},
    }

    class PendingReservationDB(ReservationDB):
        async def select_one(self, table, *, filters=None, **kwargs):
            if table == "media_jobs":
                return dict(placeholder)
            return None

    pending_db = PendingReservationDB()
    pending_db.rows[placeholder["id"]] = dict(placeholder)
    service = VideoService(settings(), pending_db, SimpleNamespace())
    provider_polls = 0

    async def fail_if_polled(_job_id):
        nonlocal provider_polls
        provider_polls += 1
        raise AssertionError("a local pending reservation must never reach a provider poll")

    service.runway.poll = fail_if_polled
    row = await service.poll(user_id=USER_ID, job_id=placeholder["id"])

    assert row == placeholder
    assert provider_polls == 0


@pytest.mark.asyncio
async def test_provider_acceptance_tracking_failure_is_not_auto_refundable():
    class TrackingFailureDB(ReservationDB):
        async def rpc(self, function_name, payload, *, retry_transient=False):
            if function_name == "complete_video_provider_launch":
                raise RuntimeError("database unavailable after provider accepted task")
            return await super().rpc(
                function_name,
                payload,
                retry_transient=retry_transient,
            )

    db = TrackingFailureDB()
    service = VideoService(settings(), db, SimpleNamespace())

    async def fake_start(**kwargs):
        return "runway-task-1"

    service.runway.start = fake_start
    with pytest.raises(VideoServiceError) as exc:
        await service.start(
            user_id=USER_ID,
            prompt="A carefully composed cinematic crane shot over a futuristic coastal city.",
            engine="cinematic",
            aspect_ratio="16:9",
            resolution="720p",
            duration_seconds=5,
            idempotency_key="tracking-failure",
            request_fingerprint=REQUEST_FINGERPRINT,
            charge_receipt={"eventId": "credit:test"},
        )
    assert exc.value.code == "VIDEO_JOB_TRACKING_FAILED"
    assert exc.value.refund_eligible is False
    row = next(iter(db.rows.values()))
    assert row["video_phase"] == "launching"
    recovered = await service.poll(user_id=USER_ID, job_id=row["id"])
    assert recovered["video_phase"] == "launching"


@pytest.mark.asyncio
async def test_pre_acceptance_rejection_identifies_the_reserved_job_for_refund_reconciliation():
    db = ReservationDB()
    service = VideoService(settings(), db, SimpleNamespace())

    async def reject_before_acceptance(**_kwargs):
        raise ProviderError(
            "The video provider rejected the generation request.",
            "VIDEO_PROVIDER_REJECTED",
            502,
            False,
            "INVALID_ARGUMENT",
            True,
        )

    service.runway.start = reject_before_acceptance
    with pytest.raises(VideoServiceError) as exc:
        await service.start(
            user_id=USER_ID,
            prompt="A carefully composed cinematic crane shot over a futuristic coastal city.",
            engine="cinematic",
            aspect_ratio="16:9",
            resolution="720p",
            duration_seconds=5,
            idempotency_key="provider-rejection",
            request_fingerprint=REQUEST_FINGERPRINT,
            charge_receipt={"eventId": "credit:test"},
        )

    assert exc.value.code == "VIDEO_PROVIDER_REJECTED"
    assert exc.value.failed_job_id in db.rows
    failed = db.rows[exc.value.failed_job_id]
    assert failed["status"] == "failed"
    assert failed["estimated_provider_cost_cents"] == 0
    assert failed["metadata"]["providerAccepted"] is False
    assert failed["metadata"]["providerFailureCode"] == "INVALID_ARGUMENT"


@pytest.mark.asyncio
async def test_unknown_provider_acceptance_refunds_once_retains_cost_and_never_relaunches():
    db = ReservationDB()
    service = VideoService(settings(), db, SimpleNamespace())
    starts = 0

    async def lose_acceptance_response(**_kwargs):
        nonlocal starts
        starts += 1
        raise ProviderError(
            "The provider response was lost after submission.",
            "VIDEO_PROVIDER_UNAVAILABLE",
            503,
            True,
            "TRANSPORT_UNCONFIRMED",
            True,
            True,
        )

    service.runway.start = lose_acceptance_response
    with pytest.raises(VideoServiceError) as exc:
        await service.start(
            user_id=USER_ID,
            prompt="A cinematic brand scene with a transport ambiguity fixture.",
            engine="cinematic",
            aspect_ratio="16:9",
            resolution="720p",
            duration_seconds=5,
            idempotency_key="unknown-provider-acceptance",
            request_fingerprint=REQUEST_FINGERPRINT,
            charge_receipt={
                "eventId": "credit:00000000-0000-0000-0000-000000000099",
                "paymentSource": "credits",
            },
        )

    assert exc.value.retryable is False
    assert exc.value.refund_eligible is False
    failed = next(iter(db.rows.values()))
    assert failed["status"] == "failed"
    assert failed["video_phase"] == "failed"
    assert failed["billing_refunded"] is True
    assert failed["estimated_provider_cost_cents"] == 60
    assert failed["metadata"]["providerAcceptance"] == "unknown"

    replay = await service.poll(user_id=USER_ID, job_id=failed["id"])
    assert replay["status"] == "failed"
    assert starts == 1


@pytest.mark.asyncio
async def test_continuation_rejection_identifies_its_reserved_job_for_refund_reconciliation():
    parent_id = "00000000-0000-0000-0000-000000000002"

    class ContinuationDB(ReservationDB):
        async def select_one(self, table, *, filters=None, **kwargs):
            if table == "media_jobs" and (filters or {}).get("id") == f"eq.{parent_id}":
                return {
                    "id": parent_id,
                    "status": "ready",
                    "engine": "extendable",
                    "provider": "gemini",
                    "resolution": "720p",
                    "aspect_ratio": "16:9",
                    "provider_asset_reference": "https://generativelanguage.googleapis.com/v1beta/files/example",
                    "provider_asset_expires_at": "2999-01-01T00:00:00+00:00",
                    "sequence_index": 0,
                    "duration_seconds": 8,
                    "metadata": {"storedBytes": 1024},
                }
            return None

    db = ContinuationDB()
    service = VideoService(settings(), db, SimpleNamespace())

    async def reject_before_acceptance(**_kwargs):
        raise ProviderError(
            "The video provider rejected the continuation request.",
            "VIDEO_PROVIDER_REJECTED",
            502,
            False,
            "INVALID_ARGUMENT",
            True,
        )

    service.gemini.start = reject_before_acceptance
    with pytest.raises(VideoServiceError) as exc:
        await service.continue_video(
            user_id=USER_ID,
            parent_job_id=parent_id,
            prompt="Continue the same scene while preserving every visible detail.",
            idempotency_key="continue-fixture",
            request_fingerprint=REQUEST_FINGERPRINT,
            charge_receipt={"eventId": "credit:test"},
        )

    assert exc.value.failed_job_id in db.rows
    failed = db.rows[exc.value.failed_job_id]
    assert failed["operation_type"] == "extend"
    assert failed["status"] == "failed"
    assert failed["estimated_provider_cost_cents"] == 0
    assert failed["metadata"]["providerFailureCode"] == "INVALID_ARGUMENT"


def test_media_routes_respect_nonrefundable_provider_boundary():
    source = read("backend/routes/media.py")
    assert "_refund_failed_video_charge" not in source
    assert source.count("consume_video_reservation(") == 2
    assert source.count("_read_bound_video_receipt(") >= 4


def test_reference_files_are_owner_checked_before_credits_or_provider_spend():
    source = read("backend/routes/media.py")
    prepare = source.index("reference_images = await video.prepare_reference_images")
    charge = source.index("receipt = await features.consume_video_reservation", prepare)
    start = source.index("row = await video.start", charge)

    assert prepare < charge < start
    assert '"referenceImageCount": len(reference_images)' in source
