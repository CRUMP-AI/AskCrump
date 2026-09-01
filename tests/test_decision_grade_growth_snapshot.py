from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = (
    ROOT
    / "migrations"
    / "20260901012708_decision_grade_growth_snapshot.sql"
)


def normalized_sql() -> str:
    return " ".join(MIGRATION.read_text(encoding="utf-8").lower().split())


def test_weekly_snapshot_exposes_decision_grade_and_durable_adoption_counts_only():
    sql = normalized_sql()
    return_contract = sql[
        sql.index("returns table"):
        sql.index("language plpgsql")
    ]

    for field in (
        "activation_reached_24h bigint",
        "useful_feedback_reached_24h bigint",
        "durable_value_reached_24h bigint",
        "decision_grade_value_reached_24h bigint",
        "project_created_reached_24h bigint",
        "project_file_reached_24h bigint",
        "ready_file_reached_24h bigint",
        "paid_conversion_eligible bigint",
    ):
        assert field in return_contract

    for forbidden in (
        "user_id",
        "email",
        "prompt",
        "response",
        "filename",
        "project_id",
        "file_id",
        "payment_method",
        "payment_object",
        "referrer",
        "url",
        "metadata",
    ):
        assert forbidden not in return_contract


def test_decision_grade_requires_technical_activation_plus_independent_value():
    sql = normalized_sql()
    journey_block = sql[
        sql.index("journey_signals as"):
        sql.index("select greatest", sql.index("journey_signals as"))
    ]

    assert "e.event_name = 'outcomefeedbacksubmitted' and e.source = 'useful'" in sql
    assert "signals.activation_24h" in journey_block
    assert "signals.useful_feedback_24h or signals.durable_value_24h" in journey_block
    assert "as decision_grade_value_24h" in journey_block
    assert "where j.eligible_24h and j.decision_grade_value_24h" in sql
    assert "coalesce(f.activation_at, f.cohort_at)" not in sql


def test_project_and_file_signals_use_owned_ready_rows_inside_the_24h_window():
    sql = normalized_sql()

    assert "from public.projects as project_row" in sql
    assert "project_row.user_id = f.user_id" in sql
    assert "project_row.archived_at is null" in sql
    assert "from public.project_files as project_file" in sql
    assert "project_file.user_id = f.user_id" in sql
    assert "file_row.user_id = project_file.user_id" in sql
    assert "file_row.deleted_at is null" in sql
    assert "file_row.status = 'ready'" in sql
    assert "f.cohort_at + interval '24 hours'" in sql


def test_payers_are_provider_backed_and_checkout_events_remain_diagnostic():
    sql = normalized_sql()
    payer_definition = sql[
        sql.index("as credit_payer") - 700:
        sql.index("as active_subscription_payer") + 40
    ]
    payer_output = sql[
        sql.index("where j.active_subscription_payer or j.credit_payer") - 50:
        sql.index("where j.active_subscription_payer or j.credit_payer") + 120
    ]

    assert "purchase.reason = 'credit_purchase'" in payer_definition
    assert "purchase.provider in ('stripe', 'revenuecat')" in payer_definition
    assert "signals.subscription_status = 'active'" in payer_definition
    assert "signals.subscription_provider in ('stripe', 'revenuecat')" in payer_definition
    assert "subscription_checkout_completed_at" not in payer_output
    assert "credit_checkout_completed_at" not in payer_output


def test_snapshot_is_service_role_only_and_finance_fields_stay_unavailable():
    sql = normalized_sql()

    assert "security invoker" in sql
    assert "from public, anon, authenticated" in sql
    assert "to service_role" in sql
    assert sql.count("null::bigint") >= 3
    assert "finance fields remain null" in sql
    assert "checkout diagnostics" in sql


def test_snapshot_does_not_add_reporting_only_index_debt():
    assert "create index" not in normalized_sql()
