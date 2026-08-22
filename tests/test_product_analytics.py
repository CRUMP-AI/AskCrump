from pathlib import Path

import pytest
from fastapi import Request

from backend.product_analytics import (
    artifact_type_for_result,
    environment_for_request,
    normalize_event_key,
    record_product_event,
)


ROOT = Path(__file__).resolve().parents[1]


def request_for(host: str, platform: str = "web") -> Request:
    return Request({
        "type": "http",
        "method": "POST",
        "scheme": "https",
        "server": (host, 443),
        "path": "/api/analytics/events",
        "query_string": b"",
        "headers": [(b"x-crump-platform", platform.encode("ascii"))],
    })


class FakeDB:
    def __init__(self, result=True, error: Exception | None = None):
        self.result = result
        self.error = error
        self.calls = []

    async def rpc(self, function_name, payload):
        self.calls.append((function_name, payload))
        if self.error:
            raise self.error
        return self.result


def test_environment_is_server_derived_and_preview_is_separate():
    assert environment_for_request(request_for("www.askcrump.com")) == "production"
    assert environment_for_request(request_for("askcrump-git-release.vercel.app")) == "preview"
    assert environment_for_request(request_for("localhost")) == "development"


def test_event_keys_are_stable_and_unsafe_values_are_hashed():
    assert normalize_event_key("workspace-open:2026-08-22") == "workspace-open:2026-08-22"
    hashed = normalize_event_key("prompt text must never become a key")
    assert hashed.startswith("sha256:")
    assert "prompt text" not in hashed


def test_artifact_classification_never_copies_names_or_content():
    assert artifact_type_for_result({"imageFile": {"name": "private.png"}}) == "image"
    assert artifact_type_for_result({"artifact": {"format": "xlsx", "title": "Private"}}) == "spreadsheet"
    assert artifact_type_for_result({"manuscriptWorkspace": {"title": "Private"}}) == "manuscript"
    assert artifact_type_for_result({"creationHandoff": {"kind": "video"}}) is None
    assert artifact_type_for_result({"response": "private response only"}) is None


@pytest.mark.asyncio
async def test_recorder_sends_only_the_allowlisted_database_contract():
    database = FakeDB()
    recorded = await record_product_event(
        database,
        user_id="00000000-0000-0000-0000-000000000001",
        event_name="PlanIntentReached",
        event_key="plan-intent:professional:1",
        request=request_for("www.askcrump.com", "ios"),
        source="Campaign_One",
        plan="professional",
    )

    assert recorded is True
    function_name, payload = database.calls[0]
    assert function_name == "record_product_event"
    assert payload == {
        "p_user_id": "00000000-0000-0000-0000-000000000001",
        "p_event_name": "PlanIntentReached",
        "p_event_key": "plan-intent:professional:1",
        "p_environment": "production",
        "p_client_platform": "ios",
        "p_source": "campaign_one",
        "p_plan": "professional",
        "p_artifact_type": None,
    }


@pytest.mark.asyncio
async def test_analytics_failure_is_fail_open():
    database = FakeDB(error=RuntimeError("database unavailable"))
    recorded = await record_product_event(
        database,
        user_id="00000000-0000-0000-0000-000000000001",
        event_name="ActivationReached",
        event_key="first-successful-response",
        request=request_for("www.askcrump.com"),
    )
    assert recorded is False


def test_migration_is_private_idempotent_and_has_no_arbitrary_metadata():
    migration = (ROOT / "migrations" / "017_product_events.sql").read_text(encoding="utf-8")
    assert "enable row level security" in migration
    assert "revoke all on table public.product_events from public, anon, authenticated" in migration
    assert "grant all on table public.product_events to service_role" in migration
    assert "on conflict (user_id, event_name, event_key, environment) do nothing" in migration
    assert "on delete cascade" in migration
    assert "metadata jsonb" not in migration


def test_frontend_intake_is_narrow_and_wired_before_authentication_bootstrap():
    app = (ROOT / "public" / "app.html").read_text(encoding="utf-8")
    client = (ROOT / "public" / "product-analytics.js").read_text(encoding="utf-8")
    worker = (ROOT / "public" / "sw.js").read_text(encoding="utf-8")
    application = (ROOT / "backend" / "application.py").read_text(encoding="utf-8")

    assert app.index('/product-analytics.js') < app.index('/auth-controller.js')
    assert "new Set(['WorkspaceOpened', 'PlanIntentReached'])" in client
    assert "prompt" not in client.lower()
    assert "filename" not in client.lower()
    assert "/product-analytics.js" in worker
    assert "application.include_router(analytics.router)" in application
