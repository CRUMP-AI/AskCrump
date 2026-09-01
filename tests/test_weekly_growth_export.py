from __future__ import annotations

import pytest

from scripts.export_weekly_growth import build_report


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
    report = build_report(
        ROWS,
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
    with pytest.raises(ValueError, match="cannot be negative"):
        build_report(
            ROWS,
            since="2026-08-24T00:00:00Z",
            until="2026-08-31T00:00:00Z",
            environment="production",
            recognized_revenue_cents=-1,
        )
