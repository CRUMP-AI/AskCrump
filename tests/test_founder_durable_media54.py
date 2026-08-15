from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from backend.feature_service import FeatureService
from backend.manuscript_service import ManuscriptService
from backend.media_service import MediaService
from backend.usage_service import consume_usage
from backend.video_service import VideoService


ROOT = Path(__file__).resolve().parents[1]
USER_ID = "00000000-0000-0000-0000-000000000001"
PROJECT_ID = "00000000-0000-0000-0000-000000000002"
MANUSCRIPT_ID = "00000000-0000-0000-0000-000000000003"
CHAT_ID = "00000000-0000-0000-0000-000000000004"


class EntitlementDB:
    def __init__(self):
        self.rpc_calls = []

    async def select_one(self, table, **_kwargs):
        if table == "credit_accounts":
            return {"balance": 17, "lifetime_granted": 20, "lifetime_spent": 3}
        return None

    async def rpc(self, name, payload):
        self.rpc_calls.append((name, payload))
        raise AssertionError("Internal access must not consume an allowance or app credit")


@pytest.mark.asyncio
async def test_founder_internal_access_bypasses_app_metering_without_faking_billing():
    db = EntitlementDB()
    user = {
        "id": USER_ID,
        "internal_tier": "enterprise",
        "subscription_tier": "free",
        "subscription_status": "inactive",
    }
    features = FeatureService(db)
    status = await features.status(user)
    image = await features.consume(user, "image")
    message = await consume_usage(
        db,
        user,
        SimpleNamespace(
            free_daily_messages=25,
            professional_daily_messages=500,
            enterprise_daily_messages=5000,
        ),
    )

    assert status["internalAccess"] is True
    assert status["accessSource"] == "internal"
    assert status["projectLimit"] == -1
    assert status["features"]["video"]["overflowCredits"] == 0
    assert image["paymentSource"] == "internal" and image["creditsSpent"] == 0
    assert message["paymentSource"] == "internal" and message["limit"] == -1
    assert db.rpc_calls == []


class RunDB:
    def __init__(self):
        self.rows = []

    async def insert(self, table, payload):
        row = dict(payload)
        if table == "manuscripts":
            row["id"] = MANUSCRIPT_ID
        if table == "manuscript_runs":
            row.setdefault("current_receipt", {})
            row.setdefault("provider_usage", {})
            row.setdefault("attempt_count", 0)
            row.setdefault("consecutive_failures", 0)
        self.rows.append((table, row))
        return [row]


class RunProjects:
    def __init__(self):
        self.project = {
            "id": PROJECT_ID,
            "name": "Untitled Manuscript",
            "description": "",
        }

    async def count(self, _user_id):
        return 0

    async def create(self, **_kwargs):
        return self.project

    async def get(self, _user_id, _project_id):
        return self.project

    async def attach_chat(self, **_kwargs):
        return None


class NoCallAI:
    def __init__(self):
        self.settings = SimpleNamespace(anthropic_model="test-model")
        self.calls = 0

    async def chat(self, *_args, **_kwargs):
        self.calls += 1
        raise AssertionError("Workspace creation must not wait on a provider call")


@pytest.mark.asyncio
async def test_long_form_request_persists_a_resumable_run_before_calling_ai():
    db = RunDB()
    ai = NoCallAI()
    service = ManuscriptService(db, ai, RunProjects())
    result = await service.begin_long_form(
        user={"id": USER_ID, "full_name": "Founder"},
        brief="Write a 70,000 word novel called The Glass Orchard in 24 chapters.",
        chat_id=CHAT_ID,
        preferred_format="docx",
        project_limit=-1,
        blueprint_receipt={"paymentSource": "internal", "eventId": None},
    )

    assert ai.calls == 0
    assert result["stopReason"] == "queued"
    assert result["manuscriptWorkspace"]["runStatus"] == "queued"
    run = next(row for table, row in db.rows if table == "manuscript_runs")
    assert run["mode"] == "autopilot"
    assert run["target_words"] == 70_000
    assert run["chapter_count"] == 24
    assert run["blueprint_receipt"]["paymentSource"] == "internal"


def test_media_provider_errors_are_actionable_and_sanitized():
    request = httpx.Request("POST", "https://api.openai.com/v1/images/generations")
    response = httpx.Response(
        403,
        request=request,
        headers={"x-request-id": "req_test"},
        json={
            "error": {
                "code": "organization_verification_required",
                "type": "image_generation_user_error",
                "message": "Organization verification is required.",
            }
        },
    )
    error = MediaService._image_provider_exception(response)
    assert error.code == "IMAGE_ORGANIZATION_VERIFICATION_REQUIRED"
    assert error.retryable is False

    video_response = httpx.Response(
        403,
        request=httpx.Request("POST", "https://generativelanguage.googleapis.com/v1beta/models/test"),
        json={"error": {"status": "PERMISSION_DENIED", "message": "API not enabled"}},
    )
    video_error = VideoService._provider_exception(video_response)
    assert video_error.code == "VIDEO_PROVIDER_PERMISSION_REQUIRED"
    assert video_error.retryable is False


def test_durable_run_schema_is_private_leased_and_scheduled():
    migration = (ROOT / "migrations" / "013_durable_manuscript_runs.sql").read_text()
    vercel = (ROOT / "vercel.json").read_text()
    routes = (ROOT / "backend" / "routes" / "manuscripts.py").read_text()
    assert "create table if not exists public.manuscript_runs" in migration
    assert "for update skip locked" in migration.lower()
    assert "enable row level security" in migration
    assert "revoke all on table public.manuscript_runs from anon, authenticated" in migration
    assert '"path": "/api/cron/manuscripts"' in vercel
    assert "hmac.compare_digest" in routes
    assert "/api/manuscript-runs/{run_id}/pause" in routes
    assert "/api/manuscript-runs/{run_id}/resume" in routes
    assert "/api/manuscript-runs/{run_id}/cancel" in routes
