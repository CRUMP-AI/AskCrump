from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from backend.video_providers import RunwayProvider
from backend.video_service import VideoService, VideoServiceError


ROOT = Path(__file__).resolve().parents[1]
USER_ID = "00000000-0000-0000-0000-000000000001"


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
        return httpx.Response(200, request=httpx.Request("POST", url), json={"id": "task-123"})

    async def get(self, url, *, headers):
        return httpx.Response(200, request=httpx.Request("GET", url), json=type(self).poll_body or {})


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
    assert "Extendable · Continue enabled" in ui
    assert "Cinematic · Runway Gen-4.5" in ui
    assert "Continue scene" in ui
    assert "/continue`" in ui
    assert "Powered by Runway" in ui
    assert "https://runwayml.com" in ui
    assert ".crump53-video-continuation" in css


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
        charge_receipt={"eventId": "credit:test"},
    )
    assert row["status"] == "processing"
    assert row["provider_job_id"] == "runway-task-1"
    assert row["metadata"]["providerAccepted"] is True


@pytest.mark.asyncio
async def test_provider_acceptance_tracking_failure_is_not_auto_refundable():
    class TrackingFailureDB(ReservationDB):
        async def update(self, table, payload, *, filters):
            if payload.get("provider_job_id") == "runway-task-1":
                raise RuntimeError("database unavailable after provider accepted task")
            return await super().update(table, payload, filters=filters)

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
            charge_receipt={"eventId": "credit:test"},
        )
    assert exc.value.code == "VIDEO_JOB_TRACKING_FAILED"
    assert exc.value.refund_eligible is False


def test_media_routes_respect_nonrefundable_provider_boundary():
    source = read("backend/routes/media.py")
    assert source.count("if exc.refund_eligible:") >= 2
    assert "await features.refund" in source
