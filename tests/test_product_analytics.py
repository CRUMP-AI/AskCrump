import ast
from pathlib import Path

import pytest
from fastapi import HTTPException, Request

from backend.routes import analytics as analytics_routes
from backend.routes import files as files_routes
from backend.product_analytics import (
    CLIENT_EVENT_NAMES,
    EVENT_NAMES,
    OUTCOME_FEEDBACK_SOURCES,
    RECENT_WORK_SOURCES,
    RESPONSE_SHARE_SOURCES,
    artifact_type_for_file,
    artifact_type_for_format,
    artifact_type_for_result,
    environment_for_request,
    normalize_event_key,
    record_product_event,
)
from backend.schemas import ProductEventRequest


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
    assert artifact_type_for_format("PPTX") == "presentation"
    assert artifact_type_for_format(".pdf") == "pdf"
    assert artifact_type_for_format("unknown-private-extension") == "file"
    assert artifact_type_for_file({
        "kind": "generated_document",
        "metadata": {"format": "xlsx", "title": "Private title"},
        "file_name": "private-customer-name.xlsx",
    }) == "spreadsheet"
    assert artifact_type_for_file({
        "kind": "manuscript_export",
        "file_name": "private-book-title.epub",
    }) == "manuscript"
    assert artifact_type_for_result({"imageFile": {"name": "private.png"}}) == "image"
    assert artifact_type_for_result({"artifact": {"format": "xlsx", "title": "Private"}}) == "spreadsheet"
    assert artifact_type_for_result({"manuscriptWorkspace": {"title": "Private"}}) == "manuscript"
    assert artifact_type_for_result({"creationHandoff": {"kind": "video"}}) is None
    assert artifact_type_for_result({"response": "private response only"}) is None


def test_artifact_journey_events_are_server_allowlisted_only():
    artifact_events = {
        "ArtifactRequested",
        "ArtifactPackaged",
        "ArtifactPackagingFailed",
        "ArtifactDownloaded",
    }
    assert artifact_events.issubset(EVENT_NAMES)
    assert artifact_events.isdisjoint(CLIENT_EVENT_NAMES)


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


@pytest.mark.asyncio
async def test_generated_document_download_records_only_content_free_artifact_stage(monkeypatch):
    calls = []
    user_id = "00000000-0000-0000-0000-000000000001"
    file_id = "00000000-0000-0000-0000-000000000002"
    message_id = "00000000-0000-0000-0000-000000000003"

    async def authenticate(_request, _database, _settings):
        return type("Auth", (), {"user": {
            "id": user_id,
            "subscription_tier": "professional",
            "subscription_status": "active",
        }})()

    class FakeFiles:
        async def get_owned(self, *, user_id, file_id):
            assert user_id == "00000000-0000-0000-0000-000000000001"
            assert file_id == "00000000-0000-0000-0000-000000000002"
            return {
                "id": file_id,
                "message_id": message_id,
                "kind": "generated_document",
                "file_name": "private-client-strategy.pptx",
                "mime_type": (
                    "application/vnd.openxmlformats-officedocument."
                    "presentationml.presentation"
                ),
                "metadata": {"format": "pptx", "title": "Private client strategy"},
            }

        async def signed_url(self, *, row, expires_in, download):
            assert row["id"] == file_id
            assert expires_in == 600
            assert download is True
            return "https://storage.example.test/signed"

    async def recorder(_database, **kwargs):
        calls.append(kwargs)
        return True

    monkeypatch.setattr(files_routes, "authenticate_request", authenticate)
    monkeypatch.setattr(files_routes, "files", FakeFiles())
    monkeypatch.setattr(files_routes, "record_product_event", recorder)

    response = await files_routes.content(
        file_id,
        request_for("www.askcrump.com"),
        download=1,
    )

    assert response.status_code == 302
    assert response.headers["location"] == "https://storage.example.test/signed"
    assert len(calls) == 1
    assert calls[0]["event_name"] == "ArtifactDownloaded"
    assert calls[0]["event_key"] == f"artifact-downloaded:{message_id}"
    assert calls[0]["artifact_type"] == "presentation"
    assert calls[0]["plan"] == "professional"
    assert set(calls[0]) == {
        "user_id",
        "event_name",
        "event_key",
        "request",
        "plan",
        "artifact_type",
    }
    assert "private" not in str(calls[0]).lower()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("download", "kind"),
    [(0, "generated_document"), (1, "upload")],
)
async def test_inline_opens_and_ordinary_uploads_do_not_record_artifact_downloads(
    monkeypatch,
    download,
    kind,
):
    calls = []
    file_id = "00000000-0000-0000-0000-000000000002"

    async def authenticate(_request, _database, _settings):
        return type("Auth", (), {"user": {"id": "user-1"}})()

    class FakeFiles:
        async def get_owned(self, **_kwargs):
            return {"id": file_id, "kind": kind, "file_name": "private.docx"}

        async def signed_url(self, **_kwargs):
            return "https://storage.example.test/signed"

    async def recorder(_database, **kwargs):
        calls.append(kwargs)
        return True

    monkeypatch.setattr(files_routes, "authenticate_request", authenticate)
    monkeypatch.setattr(files_routes, "files", FakeFiles())
    monkeypatch.setattr(files_routes, "record_product_event", recorder)

    response = await files_routes.content(
        file_id,
        request_for("www.askcrump.com"),
        download=download,
    )

    assert response.status_code == 302
    assert calls == []


@pytest.mark.asyncio
async def test_outcome_feedback_route_accepts_only_binary_content_free_signal(monkeypatch):
    calls = []

    async def authenticate(_request, _database, _settings):
        return type("Auth", (), {"user": {"id": "00000000-0000-0000-0000-000000000001"}})()

    async def rate_limit(*_args, **_kwargs):
        return None

    async def recorder(_database, **kwargs):
        calls.append(kwargs)
        return True

    monkeypatch.setattr(analytics_routes, "authenticate_request", authenticate)
    monkeypatch.setattr(analytics_routes, "enforce_user_rate_limit", rate_limit)
    monkeypatch.setattr(analytics_routes, "record_product_event", recorder)

    result = await analytics_routes.create_product_event(
        ProductEventRequest(
            eventName="OutcomeFeedbackSubmitted",
            eventKey="outcome-feedback:response-123",
            source="useful",
        ),
        request_for("www.askcrump.com"),
    )

    assert result == {"success": True, "recorded": True}
    assert calls[0]["event_name"] == "OutcomeFeedbackSubmitted"
    assert calls[0]["event_key"] == "outcome-feedback:response-123"
    assert calls[0]["source"] == "useful"
    assert set(calls[0]) == {"user_id", "event_name", "event_key", "request", "source", "plan"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("event_key", "source"),
    [
        ("outcome-feedback:response-123", "maybe"),
        ("other-event:response-123", "needs_work"),
    ],
)
async def test_outcome_feedback_route_rejects_non_contract_values(event_key, source):
    with pytest.raises(HTTPException) as error:
        await analytics_routes.create_product_event(
            ProductEventRequest(
                eventName="OutcomeFeedbackSubmitted",
                eventKey=event_key,
                source=source,
            ),
            request_for("www.askcrump.com"),
        )

    assert error.value.status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("event_key", "source"),
    [
        ("response-share:response-123", "made_up"),
        ("other-event:response-123", "native_share"),
    ],
)
async def test_response_share_route_rejects_non_contract_values(event_key, source):
    with pytest.raises(HTTPException) as error:
        await analytics_routes.create_product_event(
            ProductEventRequest(
                eventName="ResponseShared",
                eventKey=event_key,
                source=source,
            ),
            request_for("www.askcrump.com"),
        )

    assert error.value.status_code == 422


def test_response_share_sources_are_narrow_and_content_free():
    assert RESPONSE_SHARE_SOURCES == frozenset({
        "native_share",
        "clipboard",
        "useful_prompt_native",
        "useful_prompt_clipboard",
    })


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("event_key", "source"),
    [
        ("recent-work-resumed", "other"),
        ("other-event:2026-08-24", "launchpad"),
        ("recent-work-resumed:2026-08-24", "launchpad"),
    ],
)
async def test_recent_work_route_rejects_non_contract_values(event_key, source):
    with pytest.raises(HTTPException) as error:
        await analytics_routes.create_product_event(
            ProductEventRequest(
                eventName="RecentWorkResumed",
                eventKey=event_key,
                source=source,
            ),
            request_for("www.askcrump.com"),
        )

    assert error.value.status_code == 422


def test_recent_work_source_is_narrow_and_content_free():
    assert RECENT_WORK_SOURCES == frozenset({"launchpad"})


@pytest.mark.asyncio
async def test_recent_work_route_derives_one_server_utc_day_key(monkeypatch):
    calls = []

    async def authenticate(_request, _database, _settings):
        return type("Auth", (), {"user": {"id": "00000000-0000-0000-0000-000000000001"}})()

    async def rate_limit(*_args, **_kwargs):
        return None

    async def recorder(_database, **kwargs):
        calls.append(kwargs)
        return True

    monkeypatch.setattr(analytics_routes, "authenticate_request", authenticate)
    monkeypatch.setattr(analytics_routes, "enforce_user_rate_limit", rate_limit)
    monkeypatch.setattr(analytics_routes, "record_product_event", recorder)

    result = await analytics_routes.create_product_event(
        ProductEventRequest(
            eventName="RecentWorkResumed",
            eventKey="recent-work-resumed",
            source="launchpad",
        ),
        request_for("www.askcrump.com"),
    )

    assert result == {"success": True, "recorded": True}
    assert calls[0]["event_name"] == "RecentWorkResumed"
    assert calls[0]["event_key"].startswith("recent-work-resumed:")
    assert len(calls[0]["event_key"]) == len("recent-work-resumed:2026-08-24")
    assert calls[0]["source"] == "launchpad"
    assert set(calls[0]) == {"user_id", "event_name", "event_key", "request", "source", "plan"}


def test_migration_is_private_idempotent_and_has_no_arbitrary_metadata():
    migration = (ROOT / "migrations" / "017_product_events.sql").read_text(encoding="utf-8")
    assert "enable row level security" in migration
    assert "revoke all on table public.product_events from public, anon, authenticated" in migration
    assert "grant all on table public.product_events to service_role" in migration
    assert "on conflict (user_id, event_name, event_key, environment) do nothing" in migration
    assert "on delete cascade" in migration
    assert "metadata jsonb" not in migration


def test_response_share_event_extends_only_the_allowlisted_milestones():
    migration = (ROOT / "migrations" / "018_response_shared_event.sql").read_text(
        encoding="utf-8"
    )
    assert "'ResponseShared'" in migration
    assert "product_events_event_name_check" in migration
    assert "metadata jsonb" not in migration


def test_outcome_feedback_contract_is_binary_and_content_free():
    migration = (
        ROOT / "migrations" / "20260824151926_outcome_feedback.sql"
    ).read_text(encoding="utf-8")
    normalized = " ".join(migration.lower().split())

    assert OUTCOME_FEEDBACK_SOURCES == frozenset({"useful", "needs_work"})
    assert "'outcomefeedbacksubmitted'" in normalized
    assert "'useful'" in normalized
    assert "'needs_work'" in normalized
    assert "metadata jsonb" not in normalized
    assert "freeform" not in normalized
    assert "p_prompt" not in normalized
    assert "p_response" not in normalized
    assert "p_filename" not in normalized
    assert "from public, anon, authenticated" in normalized
    assert "to service_role" in normalized


def test_starter_intent_event_extends_only_the_private_allowlist():
    migration = (ROOT / "migrations" / "019_starter_intent_event.sql").read_text(
        encoding="utf-8"
    )
    assert "'StarterIntentReached'" in migration
    assert "product_events_event_name_check" in migration
    assert "metadata jsonb" not in migration
    assert "p_prompt" not in migration.lower()


def test_growth_funnel_snapshot_is_aggregate_private_and_retention_aware():
    migration = (
        ROOT / "migrations" / "20260824131311_product_growth_funnel_snapshot.sql"
    ).read_text(encoding="utf-8")
    normalized = " ".join(migration.lower().split())
    return_contract = normalized[
        normalized.index("returns table") : normalized.index("language plpgsql")
    ]

    assert "security invoker" in normalized
    assert "security definer" not in normalized
    assert "set search_path = ''" in normalized
    assert "users_growth_cohort_idx" in normalized
    assert "product_events_growth_journey_idx" in normalized
    assert "from public, anon, authenticated" in normalized
    assert "to service_role" in normalized
    assert "p_include_internal boolean default false" in normalized
    assert "coalesce(u.internal_tier, '') = ''" in normalized
    assert "user_id" not in return_contract
    assert "email" not in normalized
    assert "prompt" not in normalized
    assert "filename" not in normalized

    for metric in (
        "account_event_recorded",
        "starter_intent_reached",
        "activation_reached",
        "durable_value_reached",
        "response_shared",
        "plan_intent_reached",
        "checkout_completed",
        "active_paid_now",
        "d1_returned",
        "d7_returned",
    ):
        assert f"'{metric}'" in normalized

    assert "d1_eligible_accounts" in normalized
    assert "d7_eligible_accounts" in normalized
    assert "retention_anchor_at" in normalized


def test_recent_work_migration_is_private_content_free_and_reported_once():
    migration = (
        ROOT / "migrations" / "20260824234612_recent_work_resumed.sql"
    ).read_text(encoding="utf-8")
    normalized = " ".join(migration.lower().split())
    return_contract = normalized[
        normalized.index("returns table") : normalized.index("language plpgsql")
    ]

    assert "'recentworkresumed'" in normalized
    assert "'recent_work_resumed'" in normalized
    assert "(18::smallint, 'd7_returned'" in normalized
    assert "security invoker" in normalized
    assert "security definer" not in normalized
    assert "set search_path = ''" in normalized
    assert "from public, anon, authenticated" in normalized
    assert "to service_role" in normalized
    assert "user_id" not in return_contract
    assert "metadata jsonb" not in normalized
    assert "p_prompt" not in normalized
    assert "p_response" not in normalized
    assert "p_filename" not in normalized


def test_growth_snapshot_excludes_pre_instrumentation_accounts_from_comparable_cohorts():
    migration = (
        ROOT / "migrations" / "20260827180833_product_growth_measurement_boundary.sql"
    ).read_text(encoding="utf-8")
    normalized = " ".join(migration.lower().split())
    return_contract = normalized[
        normalized.index("returns table") : normalized.index("language plpgsql")
    ]

    assert "greatest( p_since, timestamptz '2026-08-23 09:10:55.602863+00' )" in normalized
    assert "first observed production event boundary" in normalized
    assert "security invoker" in normalized
    assert "security definer" not in normalized
    assert "set search_path = ''" in normalized
    assert "from public, anon, authenticated" in normalized
    assert "to service_role" in normalized
    assert "user_id" not in return_contract
    assert "email" not in return_contract
    assert "prompt" not in return_contract
    assert "filename" not in return_contract


def test_artifact_journey_migration_is_private_aggregate_and_content_free():
    migration = (
        ROOT / "migrations" / "20260827050550_artifact_journey.sql"
    ).read_text(encoding="utf-8")
    normalized = " ".join(migration.lower().split())
    return_contract = normalized[
        normalized.index("returns table") : normalized.index("language plpgsql")
    ]

    for event_name in (
        "artifactrequested",
        "artifactpackaged",
        "artifactpackagingfailed",
        "artifactdownloaded",
    ):
        assert f"'{event_name}'" in normalized

    assert "product_events_artifact_journey_idx" in normalized
    assert "product_artifact_journey_snapshot" in normalized
    assert "security invoker" in normalized
    assert "security definer" not in normalized
    assert "set search_path = ''" in normalized
    assert "from public, anon, authenticated" in normalized
    assert "to service_role" in normalized
    assert "user_id" not in return_contract
    assert "email" not in return_contract
    assert "prompt" not in return_contract
    assert "filename" not in return_contract
    assert "p_prompt" not in normalized
    assert "p_response" not in normalized
    assert "p_filename" not in normalized
    assert "p_error" not in normalized
    assert "metadata jsonb" not in normalized


def test_chat_records_artifact_events_after_entitlement_and_around_packaging():
    source = (ROOT / "backend" / "routes" / "chat.py").read_text(encoding="utf-8")
    request_index = source.index("event_name='ArtifactRequested'")
    generation_index = source.index("result = None", request_index)
    packaging_index = source.index("result['artifact'] = await artifacts.create")
    packaged_index = source.index("event_name='ArtifactPackaged'", packaging_index)
    packaging_failed_index = source.index("event_name='ArtifactPackagingFailed'", packaged_index)

    assert source.index("except FeatureAccessError as exc:") < request_index < generation_index
    assert packaging_index < packaged_index < packaging_failed_index
    event_calls = {}
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            continue
        if node.func.id != "record_product_event":
            continue
        keywords = {item.arg: item.value for item in node.keywords if item.arg}
        event_node = keywords.get("event_name")
        if isinstance(event_node, ast.Constant) and str(event_node.value).startswith("Artifact"):
            event_calls[str(event_node.value)] = set(keywords)

    assert event_calls == {
        "ArtifactRequested": {
            "user_id", "event_name", "event_key", "request", "plan", "artifact_type",
        },
        "ArtifactPackaged": {
            "user_id", "event_name", "event_key", "request", "plan", "artifact_type",
        },
        "ArtifactPackagingFailed": {
            "user_id", "event_name", "event_key", "request", "plan", "artifact_type",
        },
    }


def test_frontend_intake_is_narrow_and_wired_before_authentication_bootstrap():
    app = (ROOT / "public" / "app.html").read_text(encoding="utf-8")
    client = (ROOT / "public" / "product-analytics.js").read_text(encoding="utf-8")
    worker = (ROOT / "public" / "sw.js").read_text(encoding="utf-8")
    application = (ROOT / "backend" / "application.py").read_text(encoding="utf-8")

    assert app.index('/product-analytics.js') < app.index('/auth-controller.js')
    assert (
        "new Set(['WorkspaceOpened', 'StarterIntentReached', 'ActivationReached', "
        "'OutcomeFeedbackSubmitted', 'RecentWorkResumed', 'PlanIntentReached', "
        "'ResponseShared'])"
    ) in client
    assert "prompt" not in client.lower()
    assert "filename" not in client.lower()
    assert "ResponseShared" in client
    assert "RecentWorkResumed" in client
    assert "StarterIntentReached" in client
    assert "/product-analytics.js" in worker
    assert "application.include_router(analytics.router)" in application


def test_first_successful_response_records_activation_without_message_content():
    app_js = (ROOT / "public" / "app.js").read_text(encoding="utf-8")

    tracker = app_js[
        app_js.index("async function recordFirstSuccessfulResponse"):
        app_js.index("async function processUserMessage")
    ]
    assert "'ActivationReached'" in tracker
    assert "eventKey: 'first-successful-response'" in tracker
    assert "ACTIVATION_RECORDED" in tracker
    assert "message" not in tracker.lower()
    assert "content" not in tracker.lower()
    assert "void recordFirstSuccessfulResponse();" in app_js


def test_launchpad_records_only_an_allowlisted_first_task_category():
    body = (ROOT / "public" / "crump-v1-body.js").read_text(encoding="utf-8")
    tracker = body[
        body.index("const STARTER_INTENTS"):
        body.index("function command(command)")
    ]
    assert "'focus', 'research', 'file', 'image', 'projects', 'video'" in tracker
    assert "'StarterIntentReached'" in tracker
    assert "eventKey: 'first-starter-intent'" in tracker
    assert "source: command" in tracker
    assert "prompt" not in tracker.lower()
    assert "button.closest('#v1Launchpad')" in body


def test_latest_result_offers_binary_outcome_feedback_without_content_capture():
    ui = (ROOT / "public" / "ui-functions.js").read_text(encoding="utf-8")
    tracker = ui[
        ui.index("const OUTCOME_FEEDBACK_STORAGE_PREFIX"):
        ui.index("function openImage")
    ]

    assert "Did this move your work forward?" in tracker
    assert "[['Yes', 'useful'], ['Not yet', 'needs_work']]" in tracker
    assert "'OutcomeFeedbackSubmitted'" in tracker
    assert "eventKey" in tracker
    assert "source: value" in tracker
    assert "message?.id" in tracker
    assert "message?.content" not in tracker
    assert "filename" not in tracker.lower()
    assert "lastAssistantIndex" in ui


def test_useful_outcome_offers_an_optional_content_free_referral():
    ui = (ROOT / "public" / "ui-functions.js").read_text(encoding="utf-8")
    referral = ui[
        ui.index("async function shareAskCrump"):
        ui.index("const OUTCOME_FEEDBACK_STORAGE_PREFIX")
    ]
    feedback = ui[
        ui.index("function createOutcomeFeedback"):
        ui.index("function openImage")
    ]

    assert "Ask Crump helped me move work forward. Try it free." in referral
    assert "ASK_CRUMP_SHARE_URL" in referral
    assert "useful_prompt_native" in referral
    assert "useful_prompt_clipboard" in referral
    assert "message?.content" not in referral
    assert "if (value !== 'useful') return" in feedback
    assert "Keep in a Project" in feedback
    assert "Or help someone else:" in feedback
    assert feedback.index("Keep in a Project") < feedback.index("Or help someone else:")
    assert "Share Ask Crump" in feedback
    assert "shareAskCrump(message, index)" in feedback
