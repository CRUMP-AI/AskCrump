from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import json

import pytest

from backend.project_limit_plan_experiment import (
    CONTROL_DETAIL,
    EVENT_KEY,
    EVENT_NAME,
    TREATMENT_DETAIL,
    claim_project_limit_plan_message,
    record_project_limit_plan_message_shown,
    session_hash,
)
from backend.schemas import ProjectLimitPlanShownRequest
from backend.routes import projects as project_routes


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "migrations" / "20260908163226_add_project_limit_plan_experiment_dormant.sql"


class Database:
    def __init__(self, result=None):
        self.result = result
        self.calls: list[tuple[str, dict]] = []

    async def rpc(self, name: str, payload: dict):
        self.calls.append((name, payload))
        return self.result


def request(hostname: str = "www.askcrump.com", platform: str = "web"):
    return SimpleNamespace(
        url=SimpleNamespace(hostname=hostname),
        headers={"x-crump-platform": platform},
    )


class ProjectRequest:
    def __init__(self, payload: dict):
        self.payload = payload
        self.url = SimpleNamespace(hostname="www.askcrump.com")
        self.headers = {}

    async def json(self):
        return self.payload


class ProjectsAtLimit:
    async def count(self, _user_id: str):
        return 2


class FeaturesAtFreeLimit:
    def project_limit(self, _user: dict):
        return 2


async def authenticated(*_args):
    return SimpleNamespace(
        user={"id": "external-user", "subscription_tier": "free"},
        session={"id": "session-one"},
    )


@pytest.mark.asyncio
async def test_server_gate_defaults_off_without_database_read_or_mutation():
    database = Database({"eligible": True, "variant": "value-specific", "decisionId": "ignored"})
    result = await claim_project_limit_plan_message(
        database,
        user_id="external-user",
        auth_session_id="session-one",
        request=request(),
        enabled=False,
    )
    assert result is None
    assert database.calls == []


@pytest.mark.asyncio
async def test_project_limit_response_is_exact_control_when_candidate_is_off(monkeypatch):
    database = Database({"eligible": True, "variant": "value-specific", "decisionId": "ignored"})
    monkeypatch.setattr(project_routes, "authenticate_request", authenticated)
    monkeypatch.setattr(project_routes, "db", database)
    monkeypatch.setattr(project_routes, "projects", ProjectsAtLimit())
    monkeypatch.setattr(project_routes, "features", FeaturesAtFreeLimit())
    monkeypatch.setattr(
        project_routes,
        "settings",
        SimpleNamespace(project_limit_plan_experiment_enabled=False),
    )
    response = await project_routes.create_project(ProjectRequest({"name": "Third Project"}))
    payload = json.loads(response.body)
    assert response.status_code == 403
    assert payload == {
        "success": False,
        "error": "Your current plan supports up to 2 active projects.",
        "code": "PROJECT_LIMIT_REACHED",
    }
    assert database.calls == []


@pytest.mark.asyncio
async def test_enabled_isolated_route_returns_only_server_claimed_treatment(monkeypatch):
    database = Database({
        "eligible": True,
        "variant": "value-specific",
        "decisionId": "3c36e8bf-c631-46d6-b82d-af4eb08f06d4",
    })
    monkeypatch.setattr(project_routes, "authenticate_request", authenticated)
    monkeypatch.setattr(project_routes, "db", database)
    monkeypatch.setattr(project_routes, "projects", ProjectsAtLimit())
    monkeypatch.setattr(project_routes, "features", FeaturesAtFreeLimit())
    monkeypatch.setattr(
        project_routes,
        "settings",
        SimpleNamespace(project_limit_plan_experiment_enabled=True),
    )
    response = await project_routes.create_project(ProjectRequest({"name": "Third Project"}))
    payload = json.loads(response.body)
    assert response.status_code == 403
    assert payload["code"] == "PROJECT_LIMIT_REACHED"
    assert payload["projectLimitPlan"]["variant"] == "value-specific"
    assert payload["projectLimitPlan"]["experiment"] == "project-limit-plan-copy"
    assert payload["projectLimitPlan"]["decisionId"] == "3c36e8bf-c631-46d6-b82d-af4eb08f06d4"
    assert "detail" not in payload["projectLimitPlan"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("variant", "detail"),
    [("control", CONTROL_DETAIL), ("value-specific", TREATMENT_DETAIL)],
)
async def test_only_fixed_server_variants_return_fixed_content_free_copy(variant: str, detail: str):
    database = Database({
        "eligible": True,
        "variant": variant,
        "decisionId": "3c36e8bf-c631-46d6-b82d-af4eb08f06d4",
    })
    result = await claim_project_limit_plan_message(
        database,
        user_id="external-user",
        auth_session_id="session-one",
        request=request(),
        enabled=True,
    )
    assert result == {
        "eligible": True,
        "experiment": "project-limit-plan-copy",
        "decisionId": "3c36e8bf-c631-46d6-b82d-af4eb08f06d4",
        "variant": variant,
    }
    name, payload = database.calls[0]
    assert name == "claim_project_limit_plan_message"
    assert payload == {
        "p_user_id": "external-user",
        "p_environment": "production",
        "p_client_platform": "web",
        "p_session_hash": session_hash("session-one"),
        "p_project_limit_code": "PROJECT_LIMIT_REACHED",
        "p_feature_enabled": True,
    }
    assert "email" not in str(payload).lower()
    assert "prompt" not in str(payload).lower()

    shown_database = Database({"recorded": True, "variant": variant})
    exposure = await record_project_limit_plan_message_shown(
        shown_database,
        user_id="external-user",
        auth_session_id="session-one",
        decision_id="3c36e8bf-c631-46d6-b82d-af4eb08f06d4",
        request=request(),
        enabled=True,
    )
    assert exposure == {
        "eligible": True,
        "experiment": "project-limit-plan-copy",
        "eventName": EVENT_NAME,
        "eventKey": EVENT_KEY,
        "decisionId": "3c36e8bf-c631-46d6-b82d-af4eb08f06d4",
        "variant": variant,
        "detail": detail,
        "source": "recovery_project",
        "plan": "professional",
    }
    assert shown_database.calls == [("record_project_limit_plan_message_shown", {
        "p_user_id": "external-user",
        "p_decision_id": "3c36e8bf-c631-46d6-b82d-af4eb08f06d4",
        "p_environment": "production",
        "p_client_platform": "web",
        "p_session_hash": session_hash("session-one"),
        "p_feature_enabled": True,
    })]


@pytest.mark.asyncio
async def test_delivery_endpoint_returns_treatment_only_after_server_records_shown(monkeypatch):
    database = Database({"recorded": True, "variant": "value-specific"})
    monkeypatch.setattr(project_routes, "authenticate_request", authenticated)
    monkeypatch.setattr(project_routes, "db", database)
    monkeypatch.setattr(
        project_routes,
        "settings",
        SimpleNamespace(project_limit_plan_experiment_enabled=True),
    )
    result = await project_routes.project_limit_plan_message_shown(
        ProjectLimitPlanShownRequest(decisionId="3c36e8bf-c631-46d6-b82d-af4eb08f06d4"),
        ProjectRequest({}),
    )
    assert result["recorded"] is True
    assert result["variant"] == "value-specific"
    assert result["detail"] == TREATMENT_DETAIL
    assert result["eventName"] == EVENT_NAME
    assert result["eventKey"] == EVENT_KEY


@pytest.mark.asyncio
async def test_delivery_gate_defaults_off_without_database_mutation():
    database = Database({"recorded": True, "variant": "value-specific"})
    assert await record_project_limit_plan_message_shown(
        database,
        user_id="external-user",
        auth_session_id="session-one",
        decision_id="3c36e8bf-c631-46d6-b82d-af4eb08f06d4",
        request=request(),
        enabled=False,
    ) is None
    assert database.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("result", [None, {}, {"eligible": False}, {"eligible": True, "variant": "other", "decisionId": "id"}])
async def test_rpc_failure_or_unregistered_assignment_fails_closed(result):
    database = Database(result)
    assert await claim_project_limit_plan_message(
        database,
        user_id="external-user",
        auth_session_id="session-one",
        request=request(),
        enabled=True,
    ) is None


def test_session_assignment_key_is_stable_per_session_and_distinct_across_devices():
    assert session_hash("session-one") == session_hash("session-one")
    assert session_hash("session-one") != session_hash("session-two")
    assert len(session_hash("session-one")) == 64


def test_migration_encodes_every_account_and_project_eligibility_boundary():
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    required = [
        "coalesce(p_project_limit_code, '') <> 'project_limit_reached'",
        "coalesce(p_environment, '') <> 'production'",
        "not coalesce(v_user.is_verified, false)",
        "v_user.deleted_at is not null",
        "coalesce(v_user.registration_environment, '') <> 'production'",
        "coalesce(v_user.internal_tier, '') <> ''",
        "coalesce(v_user.subscription_tier, 'free') <> 'free'",
        "coalesce(v_user.subscription_status, 'inactive') <> 'inactive'",
        "v_user.stripe_customer_id is not null",
        "v_user.stripe_subscription_id is not null",
        "v_user.store_product_id is not null",
        "v_user.subscription_provider is not null",
        "if v_project_count <> 2",
        "message ->> 'role' = 'assistant'",
        "f.status = 'ready'",
        "f.size_bytes > 0",
        "'bare-projects'",
    ]
    for clause in required:
        assert clause in sql


def test_durable_random_assignment_is_account_level_and_not_identity_derived():
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    assignment = sql[sql.index("insert into public.project_limit_plan_state"):sql.index("select * into v_state")]
    assert "random() < 0.5" in assignment
    assert "on conflict (user_id) do nothing" in assignment
    assert "email" not in assignment
    assert "location" not in assignment
    assert "device" not in assignment
    assert "content" not in assignment
    assert "prompt" not in assignment


def test_thirty_day_multi_device_concurrency_and_prompt_priority_are_server_owned():
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    assert "pg_advisory_xact_lock" in sql
    assert "active_session_hash is distinct from p_session_hash" in sql
    assert "active_decision_expires_at = now() + interval '10 minutes'" in sql
    assert "now() - interval '30 days'" in sql
    assert "lifecycle_prompt_state" in sql
    assert "chat_jobs" in sql and "j.status = 'processing'" in sql
    assert "media_jobs" in sql and "('queued', 'processing')" in sql
    assert "manuscript_runs" in sql
    assert "code_tasks" in sql
    assert "event_name = 'plancenterviewed'" in sql
    assert "event_name = 'subscriptioncheckoutopened'" in sql
    assert "'prompt-priority'" in sql


def test_control_and_treatment_change_only_the_detail_sentence():
    assert CONTROL_DETAIL == (
        "Compare monthly plans below before creating another Project. "
        "Nothing changes until you choose and confirm."
    )
    assert TREATMENT_DETAIL == (
        "Your two Free Projects stay available. Professional raises the active Project limit "
        "to 25 for $20/month. You can keep using Free or review the plan before deciding."
    )
    for asset in ("crump-billing-5.1.js", "crump-5.2.js"):
        source = (ROOT / "public" / asset).read_text(encoding="utf-8")
        assert CONTROL_DETAIL in source
        assert TREATMENT_DETAIL in source
        assert "title: 'Your active Project limit has been reached.'" in source
        assert "treatment ? PROJECT_LIMIT_TREATMENT_DETAIL : PROJECT_LIMIT_CONTROL_DETAIL" in source


def test_flag_and_database_control_both_default_off():
    config = (ROOT / "backend" / "config.py").read_text(encoding="utf-8")
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    assert "os.getenv('crump_enable_project_limit_plan_experiment')" in config.lower()
    assert "CRUMP_ENABLE_PROJECT_LIMIT_PLAN_EXPERIMENT=false" in (ROOT / ".env.example").read_text(encoding="utf-8")
    assert "project_limit_plan_experiment_enabled=_bool(" in config
    assert "false" in sql[sql.index("create table if not exists public.project_limit_plan_controls"):sql.index("create table if not exists public.project_limit_plan_state")]
    assert "values ('project-limit-plan-copy', false)" in sql
    assert "if not coalesce(p_feature_enabled, false)" in sql


def test_measurement_is_fixed_field_aggregate_only_and_missing_finance_is_unavailable():
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    event_table = sql[sql.index("create table if not exists public.project_limit_plan_events"):sql.index("create index if not exists project_limit_plan_events_window_idx")]
    for fixed in (
        "projectlimitplanmessageshown",
        "project-limit-plan-message-shown",
        "recovery_project",
        "professional",
        "control",
        "value-specific",
    ):
        assert fixed in event_table
    for forbidden in ("email", "prompt", "response", "file_name", "project_name", "payment_method", "stripe_customer"):
        assert forbidden not in event_table
    report = sql[sql.index("create or replace function public.product_project_limit_plan_snapshot"):]
    for separated in (
        "eligible_exposure_accounts",
        "plan_center_view_accounts",
        "professional_checkout_open_accounts",
        "verified_completion_accounts",
        "reconciled_entitlement_accounts",
        "failure_accounts",
        "cancellation_accounts",
        "refund_accounts",
        "dispute_accounts",
        "chargeback_accounts",
        "recognized_revenue_cents",
    ):
        assert separated in report
    assert report.count("'unavailable'::text") == 6
    return_shape = report[report.index("returns table ("):report.index(")\nlanguage plpgsql")]
    assert "user_id" not in return_shape
    assert "email" not in return_shape


def test_rls_and_function_grants_deny_browser_roles_and_allow_service_role_only():
    sql = " ".join(MIGRATION.read_text(encoding="utf-8").lower().split())
    for table in (
        "project_limit_plan_controls",
        "project_limit_plan_state",
        "project_limit_plan_events",
    ):
        assert f"alter table public.{table} enable row level security" in sql
        assert f"revoke all on table public.{table} from public, anon, authenticated" in sql
        assert "to service_role" in sql
    for function in (
        "claim_project_limit_plan_message",
        "record_project_limit_plan_message_shown",
        "product_project_limit_plan_snapshot",
    ):
        assert f"revoke all on function public.{function}" in sql
    assert sql.count("from public, anon, authenticated") >= 6
    assert sql.count("to service_role") >= 6


def test_recovery_does_not_create_checkout_or_mutate_commerce_configuration():
    route = (ROOT / "backend" / "routes" / "projects.py").read_text(encoding="utf-8")
    migration = MIGRATION.read_text(encoding="utf-8").lower()
    recovery = route[route.index("if not existing:"):route.index("try:", route.index("if not existing:"))]
    assert "claim_project_limit_plan_message" in recovery
    assert "checkout" not in recovery.lower()
    for forbidden in (
        "stripe_post(", "checkout/sessions", "stripe_price", "promotion_code",
        "automatic_tax", "update public.users", "update public.product_events",
    ):
        assert forbidden not in migration
