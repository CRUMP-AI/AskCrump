from __future__ import annotations

import copy
from io import BytesIO
import json

import pytest

import scripts.export_weekly_growth as weekly_growth
from scripts.export_weekly_growth import (
    EXPECTED_SUPABASE_HOST,
    build_report,
    fetch_rows,
)


ROWS = [
    {
        "cohort_since": "2026-08-24T00:00:00+00:00",
        "cohort_until": "2026-08-31T00:00:00+00:00",
        "acquisition": "instagram",
        "placement": "profile-link",
        "campaign": "presentation-proof-current",
        "creative": "ig-feed",
        "intent": "presentation",
        "accounts_created": 10,
        "account_event_recorded": 10,
        "verified_now": 8,
        "workspace_opened": 8,
        "activation_eligible_24h": 10,
        "activation_reached_24h": 5,
        "useful_feedback_reached_24h": 3,
        "durable_value_eligible_24h": 10,
        "durable_value_reached_24h": 4,
        "decision_grade_value_reached_24h": 4,
        "project_created_reached_24h": 2,
        "project_file_reached_24h": 1,
        "ready_file_reached_24h": 2,
        "d1_eligible": 8,
        "d1_returned": 3,
        "d7_eligible": 4,
        "d7_returned": 1,
        "plan_intent_reached": 2,
        "subscription_checkout_opened": 2,
        "subscription_checkout_completed": 1,
        "credit_checkout_opened": 1,
        "credit_checkout_completed": 0,
        "distinct_payers": 1,
        "paid_conversion_eligible": 5,
        "active_paid_now": 1,
        "refund_accounts": None,
        "recognized_revenue_cents": None,
        "variable_cost_cents": None,
    },
]


class FakeResponse:
    def __init__(self, payload: object) -> None:
        self.body = BytesIO(json.dumps(payload).encode("utf-8"))

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def read(self) -> bytes:
        return self.body.read()


def test_weekly_fetch_uses_exact_project_origin_before_attaching_service_key(monkeypatch):
    observed = []

    def urlopen(call, timeout):
        observed.append((call, timeout))
        return FakeResponse([])

    monkeypatch.setattr(weekly_growth.request, "urlopen", urlopen)

    assert fetch_rows(
        supabase_url=f"https://{EXPECTED_SUPABASE_HOST}/",
        service_key="server-secret",
        since="2026-08-24T00:00:00Z",
        until="2026-08-31T00:00:00Z",
        environment="production",
        include_internal=False,
    ) == []

    call, timeout = observed[0]
    assert call.full_url == (
        f"https://{EXPECTED_SUPABASE_HOST}/rest/v1/rpc/product_weekly_attribution_export"
    )
    assert call.headers["Apikey"] == "server-secret"
    assert call.headers["Authorization"] == "Bearer server-secret"
    assert json.loads(call.data) == {
        "p_since": "2026-08-24T00:00:00Z",
        "p_until": "2026-08-31T00:00:00Z",
        "p_environment": "production",
        "p_include_internal": False,
    }
    assert timeout == 30


@pytest.mark.parametrize(
    "supabase_url",
    [
        "http://xncftwjfpjskgtwgbgci.supabase.co",
        "https://attacker.example",
        "https://xncftwjfpjskgtwgbgci.supabase.co.attacker.example",
        "https://user@xncftwjfpjskgtwgbgci.supabase.co",
        "https://xncftwjfpjskgtwgbgci.supabase.co:443",
        "https://xncftwjfpjskgtwgbgci.supabase.co/redirect",
        "https://xncftwjfpjskgtwgbgci.supabase.co?redirect=attacker.example",
        "https://xncftwjfpjskgtwgbgci.supabase.co#attacker.example",
    ],
)
def test_weekly_fetch_rejects_non_project_origin_before_transmitting_key(
    monkeypatch,
    supabase_url,
):
    calls = 0

    def urlopen(_call, timeout):
        nonlocal calls
        assert timeout == 30
        calls += 1
        return FakeResponse([])

    monkeypatch.setattr(weekly_growth.request, "urlopen", urlopen)

    with pytest.raises(ValueError, match="exact HTTPS Supabase project origin"):
        fetch_rows(
            supabase_url=supabase_url,
            service_key="server-secret",
            since="2026-08-24T00:00:00Z",
            until="2026-08-31T00:00:00Z",
            environment="production",
            include_internal=False,
        )
    assert calls == 0


@pytest.mark.parametrize(
    ("since", "until", "environment", "message"),
    [
        (
            "2026-08-31T00:00:00Z",
            "2026-08-24T00:00:00Z",
            "production",
            "valid half-open reporting window",
        ),
        (
            "2026-08-24T00:00:00Z",
            "2026-08-24T00:00:00Z",
            "production",
            "valid half-open reporting window",
        ),
        (
            "2026-08-24T00:00:00Z",
            "2026-08-31T00:00:00Z",
            "staging",
            "Invalid reporting environment",
        ),
    ],
)
def test_weekly_fetch_rejects_invalid_boundary_before_network(
    monkeypatch,
    since,
    until,
    environment,
    message,
):
    calls = 0

    def urlopen(_call, timeout):
        nonlocal calls
        assert timeout == 30
        calls += 1
        return FakeResponse([])

    monkeypatch.setattr(weekly_growth.request, "urlopen", urlopen)

    with pytest.raises(ValueError, match=message):
        fetch_rows(
            supabase_url=f"https://{EXPECTED_SUPABASE_HOST}",
            service_key="server-secret",
            since=since,
            until=until,
            environment=environment,
            include_internal=False,
        )
    assert calls == 0


def test_missing_provider_evidence_remains_not_provided_instead_of_zero():
    report = build_report(
        ROWS,
        since="2026-08-24T00:00:00Z",
        until="2026-08-31T00:00:00Z",
        environment="production",
    )

    totals = report["authoritative_period_totals"]
    for field in (
        "landing_visitors",
        "refund_accounts",
        "recognized_revenue_cents",
        "refund_adjustments_cents",
        "variable_cost_cents",
        "ad_spend_cents",
        "net_recognized_revenue_cents",
    ):
        assert totals[field] == {"status": "not_provided", "value": None}
    assert report["derived_rates"]["landing_to_signup_pct"] is None
    assert report["derived_rates"]["cost_per_activated_user_cents"] is None


def test_report_calculates_only_rates_with_explicit_denominators():
    rows = copy.deepcopy(ROWS)
    rows[0]["cohort_since"] = "2026-08-24T04:00:00Z"
    rows[0]["cohort_until"] = "2026-08-31T04:00:00Z"
    report = build_report(
        rows,
        since="2026-08-24T00:00:00-04:00",
        until="2026-08-31T00:00:00-04:00",
        environment="production",
        landing_visitors=100,
        refund_accounts=1,
        recognized_revenue_cents=20_000,
        refund_adjustments_cents=2_000,
        variable_cost_cents=3_000,
        ad_spend_cents=5_000,
    )

    assert report["window"]["since"] == "2026-08-24T04:00:00Z"
    assert report["window"]["until"] == "2026-08-31T04:00:00Z"
    assert report["derived_rates"] == {
        "landing_to_signup_pct": 10.0,
        "signup_to_activation_24h_pct": 50.0,
        "signup_to_useful_feedback_24h_pct": 30.0,
        "signup_to_durable_value_24h_pct": 40.0,
        "signup_to_decision_grade_value_24h_pct": 40.0,
        "signup_to_project_24h_pct": 20.0,
        "signup_to_project_file_24h_pct": 10.0,
        "signup_to_ready_file_24h_pct": 20.0,
        "d1_retention_pct": 37.5,
        "d7_retention_pct": 25.0,
        "paid_conversion_pct": 20.0,
        "cost_per_activated_user_cents": 1000,
        "cost_per_decision_grade_user_cents": 1250,
        "cost_per_d7_retained_user_cents": 5000,
    }
    assert report["authoritative_period_totals"]["net_recognized_revenue_cents"] == {
        "status": "measured",
        "value": 18_000,
    }


def test_subsecond_half_open_window_compares_instants_not_strings():
    report = build_report(
        [],
        since="2026-08-24T00:00:00Z",
        until="2026-08-24T00:00:00.500000Z",
        environment="production",
    )

    assert report["window"]["since"] == "2026-08-24T00:00:00Z"
    assert report["window"]["until"] == "2026-08-24T00:00:00.500000Z"


@pytest.mark.parametrize(
    "rows",
    [
        [{"user_id": "private", "accounts_created": 1}],
        [{"email": "private@example.com", "accounts_created": 1}],
        [{"prompt": "private content", "accounts_created": 1}],
        [{"artifact_url": "private", "accounts_created": 1}],
        [{"project_id": "private", "accounts_created": 1}],
        [{"file_id": "private", "accounts_created": 1}],
        [{"payment_intent": "private", "accounts_created": 1}],
        [{"metadata": {"private": True}, "accounts_created": 1}],
    ],
)
def test_export_rejects_any_unexpected_sensitive_field(rows):
    with pytest.raises(ValueError, match="sensitive fields"):
        build_report(
            rows,
            since="2026-08-24T00:00:00Z",
            until="2026-08-31T00:00:00Z",
            environment="production",
        )


def test_negative_operator_totals_are_rejected():
    with pytest.raises(ValueError, match="nonnegative integers"):
        build_report(
            ROWS,
            since="2026-08-24T00:00:00Z",
            until="2026-08-31T00:00:00Z",
            environment="production",
            recognized_revenue_cents=-1,
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("d1_returned", 9, "d1_returned above d1_eligible"),
        ("d7_eligible", 9, "d7_eligible above d1_eligible"),
        ("activation_reached_24h", 11, "activation_reached_24h above activation_eligible_24h"),
        ("accounts_created", -1, "invalid nonnegative integer count accounts_created"),
        ("accounts_created", "10", "invalid nonnegative integer count accounts_created"),
        ("accounts_created", True, "invalid nonnegative integer count accounts_created"),
    ],
)
def test_impossible_or_untyped_cohort_counts_fail_closed(field, value, message):
    rows = copy.deepcopy(ROWS)
    rows[0][field] = value

    with pytest.raises(ValueError, match=message):
        build_report(
            rows,
            since="2026-08-24T00:00:00Z",
            until="2026-08-31T00:00:00Z",
            environment="production",
        )


def test_missing_retention_denominator_fails_closed_instead_of_becoming_zero():
    rows = copy.deepcopy(ROWS)
    rows[0].pop("d1_eligible")

    with pytest.raises(ValueError, match="missing required count d1_eligible"):
        build_report(
            rows,
            since="2026-08-24T00:00:00Z",
            until="2026-08-31T00:00:00Z",
            environment="production",
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("cohort_since", "2026-08-23T23:59:59Z", "start falls outside"),
        ("cohort_until", "2026-08-30T23:59:59Z", "end does not match"),
        ("cohort_until", "not-a-timestamp", "invalid cohort boundary"),
    ],
)
def test_cohort_boundaries_must_match_the_requested_window(field, value, message):
    rows = copy.deepcopy(ROWS)
    rows[0][field] = value

    with pytest.raises(ValueError, match=message):
        build_report(
            rows,
            since="2026-08-24T00:00:00Z",
            until="2026-08-31T00:00:00Z",
            environment="production",
        )


def test_multiple_cohorts_must_share_one_authoritative_boundary():
    rows = copy.deepcopy(ROWS) * 2
    rows[1] = copy.deepcopy(rows[1])
    rows[1]["cohort_since"] = "2026-08-25T00:00:00Z"

    with pytest.raises(ValueError, match="inconsistent cohort boundaries"):
        build_report(
            rows,
            since="2026-08-24T00:00:00Z",
            until="2026-08-31T00:00:00Z",
            environment="production",
        )
