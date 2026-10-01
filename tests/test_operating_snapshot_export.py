from __future__ import annotations

import copy
from io import BytesIO
import json
from pathlib import Path
import subprocess
import sys
from urllib import error

import pytest

import scripts.export_operating_snapshot as operating_snapshot
from scripts.export_operating_snapshot import (
    EXPECTED_SUPABASE_HOST,
    NAVIGATION_DESTINATIONS,
    PROJECT_CONTINUITY_COUNT_FIELDS,
    build_operating_snapshot,
    collect_rpc_rows,
    fetch_rpc_rows,
    rpc_payloads,
)


SINCE = "2026-09-01T00:00:00Z"
UNTIL = "2026-09-15T00:00:00Z"
ROOT = Path(__file__).resolve().parents[1]


def project_continuity_row(**overrides) -> dict:
    row = {
        "cohort_since": SINCE,
        "cohort_until": UNTIL,
        "offer_measurement_since": "2026-09-14T18:34:14Z",
        "acquisition": "clevercrump",
        "placement": None,
        "campaign": None,
        "creative": None,
        "intent": None,
        "accounts_created": 1,
        "activation_reached": 0,
        "project_save_offer_shown": 0,
        "project_save_offer_to_intent": 0,
        "project_save_offer_without_later_intent": 0,
        "project_save_intent_without_prior_offer": 0,
        "project_save_intent_reached": 0,
        "project_save_completed": 0,
        "project_save_paired_completion": 0,
        "project_save_intent_without_completion": 0,
        "project_save_completion_without_intent": 0,
        "project_resumed_after_save": 0,
        "offer_to_intent_rate_pct": None,
        "intent_to_completion_rate_pct": None,
        "completion_to_resume_rate_pct": None,
    }
    row.update(overrides)
    return row


def fixture_sections() -> dict[str, list[dict]]:
    sections = {
        name: []
        for name in rpc_payloads(
            since=SINCE,
            until=UNTIL,
            environment="production",
            include_internal=False,
        )
    }
    sections["product_weekly_attribution_export"] = [{
        "cohort_since": SINCE,
        "cohort_until": UNTIL,
        "acquisition": "clevercrump",
        "placement": None,
        "campaign": None,
        "creative": None,
        "intent": None,
        "accounts_created": 1,
        "account_event_recorded": 1,
        "verified_now": 1,
        "workspace_opened": 1,
        "activation_eligible_24h": 1,
        "activation_reached_24h": 1,
        "useful_feedback_reached_24h": 0,
        "durable_value_eligible_24h": 1,
        "durable_value_reached_24h": 0,
        "decision_grade_value_reached_24h": 0,
        "project_created_reached_24h": 0,
        "project_file_reached_24h": 0,
        "ready_file_reached_24h": 0,
        "d1_eligible": 1,
        "d1_returned": 0,
        "d7_eligible": 0,
        "d7_returned": 0,
        "plan_intent_reached": 0,
        "subscription_checkout_opened": 0,
        "subscription_checkout_completed": 0,
        "credit_checkout_opened": 0,
        "credit_checkout_completed": 0,
        "distinct_payers": 0,
        "paid_conversion_eligible": 0,
        "active_paid_now": 0,
        "refund_accounts": None,
        "recognized_revenue_cents": None,
        "variable_cost_cents": None,
    }]
    sections["demo_recording_proof_snapshot"] = [{
        "configured": False,
        "protected_identity": False,
        "complete_exchange": False,
        "project_saved": False,
        "project_reopened": False,
        "editable_artifact_ready": False,
        "proof_ready": False,
    }]
    sections["product_project_continuity_snapshot"] = [
        project_continuity_row(
            accounts_created=2,
            activation_reached=2,
            project_save_offer_shown=2,
            project_save_offer_to_intent=1,
            project_save_offer_without_later_intent=1,
            project_save_intent_reached=1,
            project_save_completed=1,
            project_save_paired_completion=1,
            offer_to_intent_rate_pct=50.0,
            intent_to_completion_rate_pct=100.0,
            completion_to_resume_rate_pct=0.0,
        ),
        project_continuity_row(
            acquisition="organic",
            activation_reached=1,
            project_save_completed=1,
            project_save_completion_without_intent=1,
            completion_to_resume_rate_pct=0.0,
        ),
        project_continuity_row(
            acquisition="facebook",
            placement="organic-social",
            campaign="real-product-continuity",
            creative="continuity-feed",
            intent="projects",
            activation_reached=1,
            project_save_offer_shown=1,
            project_save_offer_to_intent=1,
            project_save_intent_reached=1,
            project_save_completed=1,
            project_save_paired_completion=1,
            project_resumed_after_save=1,
            offer_to_intent_rate_pct=100.0,
            intent_to_completion_rate_pct=100.0,
            completion_to_resume_rate_pct=100.0,
        ),
    ]
    sections["product_navigation_discovery_snapshot"] = [
        {
            "measurement_since": "2026-09-14T20:57:00+00:00",
            "window_since": "2026-09-14T20:57:00+00:00",
            "window_until": UNTIL,
            "destination": destination,
            "active_workspace_accounts": 0,
            "selected_accounts": 0,
            "selected_account_days": 0,
            "selected_account_rate_pct": None,
        }
        for destination in NAVIGATION_DESTINATIONS
    ]
    return sections


def test_one_collection_requires_every_protected_aggregate_with_exact_arguments() -> None:
    calls: list[tuple[str, dict]] = []

    def fetcher(name: str, payload: dict) -> list[dict]:
        calls.append((name, payload))
        return fixture_sections()[name]

    sections = collect_rpc_rows(
        fetcher,
        since=SINCE,
        until=UNTIL,
        environment="production",
        include_internal=False,
    )

    assert list(sections) == [
        "product_growth_funnel_snapshot",
        "product_weekly_attribution_export",
        "product_artifact_journey_snapshot",
        "product_project_continuity_snapshot",
        "product_plan_conversion_snapshot",
        "product_outcome_issue_snapshot",
        "product_navigation_discovery_snapshot",
        "product_weekly_lifecycle_export",
        "product_project_limit_plan_snapshot",
        "demo_recording_proof_snapshot",
    ]
    assert calls[-1] == ("demo_recording_proof_snapshot", {})
    assert calls[-2][0] == "product_project_limit_plan_snapshot"
    assert "p_include_internal" not in calls[-2][1]
    for name, payload in calls[:7]:
        assert name.startswith("product_")
        assert payload["p_environment"] == "production"
        assert payload["p_include_internal"] is False


def test_snapshot_exposes_exact_retention_denominators_without_content_or_identity() -> None:
    report = build_operating_snapshot(
        fixture_sections(),
        since=SINCE,
        until=UNTIL,
        environment="production",
        include_internal=False,
    )

    assert report["schema"] == "ask-crump.operating-snapshot.v1"
    assert report["privacy"] == {
        "aggregate_only": True,
        "contains_customer_content": False,
        "contains_account_identifiers": False,
        "service_role_required": True,
        "internal_accounts_included": False,
    }
    assert report["retention_readiness"] == {
        "d1": {
            "status": "eligible",
            "eligible_accounts": 1,
            "returned_accounts": 0,
            "rate_pct": 0.0,
        },
        "d7": {
            "status": "not_yet_eligible",
            "eligible_accounts": 0,
            "returned_accounts": 0,
            "rate_pct": None,
        },
    }
    assert report["boundaries"]["all_sections_required"] is True
    assert report["boundaries"]["no_database_writes"] is True
    assert report["navigation_discovery"] == {
        "status": "awaiting_traffic",
        "measurement_since": "2026-09-14T20:57:00+00:00",
        "window_since": "2026-09-14T20:57:00+00:00",
        "window_until": UNTIL,
        "active_workspace_accounts": 0,
        "selected_accounts_by_destination": {
            destination: 0 for destination in NAVIGATION_DESTINATIONS
        },
        "selected_account_days_by_destination": {
            destination: 0 for destination in NAVIGATION_DESTINATIONS
        },
        "proves_destination_selection_only": True,
        "does_not_prove_task_completion": True,
    }


def test_project_continuity_preserves_valid_conversation_artifact_and_resume_evidence() -> None:
    report = build_operating_snapshot(
        fixture_sections(),
        since=SINCE,
        until=UNTIL,
        environment="production",
        include_internal=False,
    )

    rows = report["sections"]["product_project_continuity_snapshot"]
    assert len(rows) == 3
    assert rows[0]["project_save_paired_completion"] == 1
    assert rows[1]["project_save_completion_without_intent"] == 1
    assert rows[2]["project_resumed_after_save"] == 1


def test_project_continuity_accepts_an_empty_aggregate() -> None:
    sections = fixture_sections()
    sections["product_project_continuity_snapshot"] = []

    report = build_operating_snapshot(
        sections,
        since=SINCE,
        until=UNTIL,
        environment="production",
        include_internal=False,
    )

    assert report["sections"]["product_project_continuity_snapshot"] == []


def test_project_continuity_rejects_an_impossible_zero_account_row() -> None:
    sections = fixture_sections()
    sections["product_project_continuity_snapshot"] = [
        project_continuity_row(accounts_created=0)
    ]

    with pytest.raises(ValueError, match="must contain at least one account"):
        build_operating_snapshot(
            sections,
            since=SINCE,
            until=UNTIL,
            environment="production",
            include_internal=False,
        )


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda row: row.pop("project_save_completed"),
            "schema drifted",
        ),
        (
            lambda row: row.update(invented_metric=1),
            "schema drifted",
        ),
        (
            lambda row: row.update(acquisition=[]),
            "invalid attribution tuple",
        ),
    ],
)
def test_project_continuity_rejects_schema_or_dimension_drift(mutate, message: str) -> None:
    sections = fixture_sections()
    mutate(sections["product_project_continuity_snapshot"][0])

    with pytest.raises(ValueError, match=message):
        build_operating_snapshot(
            sections,
            since=SINCE,
            until=UNTIL,
            environment="production",
            include_internal=False,
        )


@pytest.mark.parametrize("value", [True, "1", 1.0, -1])
def test_project_continuity_rejects_invalid_count_types_or_values(value) -> None:
    sections = fixture_sections()
    sections["product_project_continuity_snapshot"][0]["activation_reached"] = value

    with pytest.raises(ValueError, match="invalid nonnegative integer count"):
        build_operating_snapshot(
            sections,
            since=SINCE,
            until=UNTIL,
            environment="production",
            include_internal=False,
        )


@pytest.mark.parametrize(
    "field",
    [field for field in PROJECT_CONTINUITY_COUNT_FIELDS if field != "accounts_created"],
)
def test_project_continuity_rejects_counts_above_the_account_cohort(field: str) -> None:
    sections = fixture_sections()
    sections["product_project_continuity_snapshot"][0][field] = 3

    with pytest.raises(ValueError, match=rf"{field} above accounts_created"):
        build_operating_snapshot(
            sections,
            since=SINCE,
            until=UNTIL,
            environment="production",
            include_internal=False,
        )


def test_project_continuity_rejects_inconsistent_or_duplicate_cohorts() -> None:
    inconsistent = fixture_sections()
    inconsistent["product_project_continuity_snapshot"][1]["cohort_until"] = (
        "2026-09-14T00:00:00Z"
    )
    with pytest.raises(ValueError, match="inconsistent reporting boundaries"):
        build_operating_snapshot(
            inconsistent,
            since=SINCE,
            until=UNTIL,
            environment="production",
            include_internal=False,
        )

    duplicate = fixture_sections()
    duplicate["product_project_continuity_snapshot"].append(
        copy.deepcopy(duplicate["product_project_continuity_snapshot"][0])
    )
    with pytest.raises(ValueError, match="duplicate attribution tuple"):
        build_operating_snapshot(
            duplicate,
            since=SINCE,
            until=UNTIL,
            environment="production",
            include_internal=False,
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("cohort_since", "2026-09-02T00:00:00Z", "cohort start does not match"),
        ("cohort_until", "2026-09-16T00:00:00Z", "cohort end does not match"),
        (
            "offer_measurement_since",
            "2026-09-14T18:34:15Z",
            "offer measurement boundary is not authoritative",
        ),
    ],
)
def test_project_continuity_rejects_non_authoritative_boundaries(
    field: str,
    value: str,
    message: str,
) -> None:
    sections = fixture_sections()
    for row in sections["product_project_continuity_snapshot"]:
        row[field] = value

    with pytest.raises(ValueError, match=message):
        build_operating_snapshot(
            sections,
            since=SINCE,
            until=UNTIL,
            environment="production",
            include_internal=False,
        )


def test_project_continuity_enforces_the_instrumentation_floor_for_early_windows() -> None:
    early_since = "2026-08-01T00:00:00Z"
    sections = fixture_sections()
    for row in sections["product_project_continuity_snapshot"]:
        row["cohort_since"] = "2026-08-23T09:10:55.602863Z"

    build_operating_snapshot(
        sections,
        since=early_since,
        until=UNTIL,
        environment="production",
        include_internal=False,
    )

    for row in sections["product_project_continuity_snapshot"]:
        row["cohort_since"] = early_since
    with pytest.raises(ValueError, match="cohort start does not match"):
        build_operating_snapshot(
            sections,
            since=early_since,
            until=UNTIL,
            environment="production",
            include_internal=False,
        )


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda row: row.update(project_save_offer_without_later_intent=0),
            "invalid offer partition",
        ),
        (
            lambda row: row.update(project_save_intent_without_completion=1),
            "invalid intent partition",
        ),
        (
            lambda row: row.update(project_save_completion_without_intent=1),
            "invalid completion partition",
        ),
        (
            lambda row: row.update(project_save_intent_without_prior_offer=1),
            "more comparable intent than total intent",
        ),
        (
            lambda row: row.update(accounts_created=2, project_resumed_after_save=2),
            "resumed Projects above completions",
        ),
    ],
)
def test_project_continuity_rejects_broken_partitions(mutate, message: str) -> None:
    sections = fixture_sections()
    mutate(sections["product_project_continuity_snapshot"][0])

    with pytest.raises(ValueError, match=message):
        build_operating_snapshot(
            sections,
            since=SINCE,
            until=UNTIL,
            environment="production",
            include_internal=False,
        )


@pytest.mark.parametrize(
    ("row_index", "field", "value", "message"),
    [
        (1, "offer_to_intent_rate_pct", 0.0, "zero denominator"),
        (0, "offer_to_intent_rate_pct", None, "invalid numeric rate"),
        (0, "offer_to_intent_rate_pct", 50.01, "exact denominator"),
        (0, "offer_to_intent_rate_pct", True, "invalid numeric rate"),
        (0, "offer_to_intent_rate_pct", float("nan"), "invalid numeric rate"),
        (0, "offer_to_intent_rate_pct", float("inf"), "invalid numeric rate"),
    ],
)
def test_project_continuity_rejects_invalid_or_inconsistent_rates(
    row_index: int,
    field: str,
    value,
    message: str,
) -> None:
    sections = fixture_sections()
    sections["product_project_continuity_snapshot"][row_index][field] = value

    with pytest.raises(ValueError, match=message):
        build_operating_snapshot(
            sections,
            since=SINCE,
            until=UNTIL,
            environment="production",
            include_internal=False,
        )


def test_project_continuity_matches_postgres_two_decimal_rounding() -> None:
    sections = fixture_sections()
    row = sections["product_project_continuity_snapshot"][0]
    row.update(
        accounts_created=3,
        activation_reached=3,
        project_save_intent_reached=3,
        project_save_completed=2,
        project_save_paired_completion=2,
        project_save_intent_without_completion=1,
        intent_to_completion_rate_pct=66.67,
    )

    build_operating_snapshot(
        sections,
        since=SINCE,
        until=UNTIL,
        environment="production",
        include_internal=False,
    )

    row["intent_to_completion_rate_pct"] = 66.66
    with pytest.raises(ValueError, match="exact denominator"):
        build_operating_snapshot(
            sections,
            since=SINCE,
            until=UNTIL,
            environment="production",
            include_internal=False,
        )


def test_snapshot_refuses_impossible_retention_evidence() -> None:
    sections = fixture_sections()
    sections["product_weekly_attribution_export"][0]["d1_returned"] = 2

    with pytest.raises(ValueError, match="d1_returned above d1_eligible"):
        build_operating_snapshot(
            sections,
            since=SINCE,
            until=UNTIL,
            environment="production",
            include_internal=False,
        )


def test_snapshot_fails_closed_for_missing_extra_or_sensitive_sections() -> None:
    missing = fixture_sections()
    missing.pop("product_plan_conversion_snapshot")
    with pytest.raises(ValueError, match="sections are incomplete"):
        build_operating_snapshot(
            missing,
            since=SINCE,
            until=UNTIL,
            environment="production",
            include_internal=False,
        )

    unexpected = fixture_sections()
    unexpected["invented_snapshot"] = []
    with pytest.raises(ValueError, match="unexpected"):
        build_operating_snapshot(
            unexpected,
            since=SINCE,
            until=UNTIL,
            environment="production",
            include_internal=False,
        )

    sensitive = copy.deepcopy(fixture_sections())
    sensitive["product_artifact_journey_snapshot"] = [{"email": "private@example.com"}]
    with pytest.raises(ValueError, match="sensitive fields"):
        build_operating_snapshot(
            sensitive,
            since=SINCE,
            until=UNTIL,
            environment="production",
            include_internal=False,
        )


def test_nonproduction_snapshot_omits_production_only_experiment_rpc() -> None:
    payloads = rpc_payloads(
        since=SINCE,
        until=UNTIL,
        environment="preview",
        include_internal=True,
    )

    assert "product_project_limit_plan_snapshot" not in payloads
    assert payloads["product_weekly_attribution_export"]["p_include_internal"] is True


def test_navigation_discovery_exposes_an_exact_observed_denominator() -> None:
    sections = fixture_sections()
    for row in sections["product_navigation_discovery_snapshot"]:
        row["active_workspace_accounts"] = 2
        if row["destination"] == "projects":
            row["selected_accounts"] = 1
            row["selected_account_days"] = 2
            row["selected_account_rate_pct"] = 50.0
        else:
            row["selected_account_rate_pct"] = 0.0

    discovery = build_operating_snapshot(
        sections,
        since=SINCE,
        until=UNTIL,
        environment="production",
        include_internal=False,
    )["navigation_discovery"]

    assert discovery["status"] == "observed"
    assert discovery["active_workspace_accounts"] == 2
    assert discovery["selected_accounts_by_destination"]["projects"] == 1
    assert discovery["selected_account_days_by_destination"]["projects"] == 2


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda rows: rows.pop(),
            "nine fixed destinations",
        ),
        (
            lambda rows: rows[1].update(active_workspace_accounts=1),
            "inconsistent active-account denominators",
        ),
        (
            lambda rows: rows[0].update(selected_accounts=1),
            "exceed its denominator",
        ),
        (
            lambda rows: rows[0].update(selected_account_rate_pct=0.0),
            "rate must be unavailable",
        ),
    ],
)
def test_navigation_discovery_fails_closed_on_invalid_evidence(mutate, message: str) -> None:
    sections = fixture_sections()
    mutate(sections["product_navigation_discovery_snapshot"])

    with pytest.raises(ValueError, match=message):
        build_operating_snapshot(
            sections,
            since=SINCE,
            until=UNTIL,
            environment="production",
            include_internal=False,
        )


@pytest.mark.parametrize(
    ("since", "until", "environment", "message"),
    [
        (UNTIL, SINCE, "production", "valid half-open reporting window"),
        (SINCE, SINCE, "production", "valid half-open reporting window"),
        (SINCE, UNTIL, "staging", "Invalid reporting environment"),
    ],
)
def test_invalid_collection_arguments_fail_before_any_rpc_call(
    since: str,
    until: str,
    environment: str,
    message: str,
) -> None:
    calls = 0

    def fetcher(_name: str, _payload: dict) -> list[dict]:
        nonlocal calls
        calls += 1
        return []

    with pytest.raises(ValueError, match=message):
        collect_rpc_rows(
            fetcher,
            since=since,
            until=until,
            environment=environment,
            include_internal=False,
        )

    assert calls == 0


class FakeResponse:
    def __init__(self, payload: object) -> None:
        self.body = BytesIO(json.dumps(payload).encode("utf-8"))

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def read(self) -> bytes:
        return self.body.read()


def test_rpc_fetch_uses_service_role_headers_and_exact_payload(monkeypatch) -> None:
    observed = []

    def urlopen(call, timeout):
        observed.append((call, timeout))
        return FakeResponse([{"metric": "accounts_created", "accounts": 1}])

    monkeypatch.setattr(operating_snapshot.request, "urlopen", urlopen)

    rows = fetch_rpc_rows(
        supabase_url=f"https://{EXPECTED_SUPABASE_HOST}/",
        service_key="server-secret",
        rpc_name="product_growth_funnel_snapshot",
        payload={"p_environment": "production"},
    )

    call, timeout = observed[0]
    assert rows == [{"metric": "accounts_created", "accounts": 1}]
    assert call.full_url == (
        f"https://{EXPECTED_SUPABASE_HOST}/rest/v1/rpc/product_growth_funnel_snapshot"
    )
    assert call.method == "POST"
    assert json.loads(call.data) == {"p_environment": "production"}
    assert call.headers["Apikey"] == "server-secret"
    assert call.headers["Authorization"] == "Bearer server-secret"
    assert timeout == 30


def test_rpc_fetch_retries_transient_failures_then_succeeds(monkeypatch) -> None:
    attempts = 0
    sleeps = []

    def urlopen(call, timeout):
        nonlocal attempts
        assert timeout == 30
        attempts += 1
        if attempts < 3:
            raise error.HTTPError(call.full_url, 503, "Unavailable", {}, None)
        return FakeResponse([])

    monkeypatch.setattr(operating_snapshot.request, "urlopen", urlopen)
    monkeypatch.setattr(operating_snapshot.time, "sleep", sleeps.append)

    assert fetch_rpc_rows(
        supabase_url=f"https://{EXPECTED_SUPABASE_HOST}",
        service_key="server-secret",
        rpc_name="product_weekly_attribution_export",
        payload={},
    ) == []
    assert attempts == 3
    assert sleeps == [0.25, 0.5]


def test_rpc_fetch_does_not_retry_permanent_http_failure(monkeypatch) -> None:
    attempts = 0

    def urlopen(call, timeout):
        nonlocal attempts
        assert timeout == 30
        attempts += 1
        raise error.HTTPError(call.full_url, 400, "Bad request", {}, None)

    monkeypatch.setattr(operating_snapshot.request, "urlopen", urlopen)

    with pytest.raises(RuntimeError, match="HTTP 400"):
        fetch_rpc_rows(
            supabase_url=f"https://{EXPECTED_SUPABASE_HOST}",
            service_key="server-secret",
            rpc_name="product_weekly_attribution_export",
            payload={},
        )
    assert attempts == 1


def test_rpc_fetch_rejects_non_project_origin_before_transmitting_key(monkeypatch) -> None:
    calls = 0

    def urlopen(_call, timeout):
        nonlocal calls
        assert timeout == 30
        calls += 1
        return FakeResponse([])

    monkeypatch.setattr(operating_snapshot.request, "urlopen", urlopen)

    with pytest.raises(ValueError, match="exact HTTPS Supabase project origin"):
        fetch_rpc_rows(
            supabase_url="https://attacker.example",
            service_key="server-secret",
            rpc_name="product_weekly_attribution_export",
            payload={},
        )
    assert calls == 0


def test_operator_command_is_directly_executable() -> None:
    completed = subprocess.run(
        [sys.executable, "scripts/export_operating_snapshot.py", "--help"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert "Export one privacy-safe Ask Crump operating snapshot" in completed.stdout
