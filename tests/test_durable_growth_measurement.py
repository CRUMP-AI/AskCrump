from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "migrations" / "20260908134343_durable_growth_measurement.sql"


def normalized_sql() -> str:
    return " ".join(MIGRATION.read_text(encoding="utf-8").lower().split())


def function_block(sql: str, name: str, next_marker: str) -> str:
    start = sql.index(f"create or replace function public.{name}")
    return sql[start:sql.index(next_marker, start)]


def test_growth_reports_use_completed_jobs_as_durable_activation():
    sql = normalized_sql()
    overall = function_block(
        sql,
        "product_growth_funnel_snapshot",
        "create or replace function public.product_weekly_attribution_export",
    )
    weekly = function_block(
        sql,
        "product_weekly_attribution_export",
        "comment on function public.product_growth_funnel_snapshot",
    )

    for block in (overall, weekly):
        assert "from public.chat_jobs as j" in block
        assert "j.status = 'completed'" in block
        assert "j.updated_at >= f.cohort_at" in block
        assert "j.updated_at < p_until" in block
        assert "as activation_at" in block

    assert "f.activation_at <= f.cohort_at + interval '24 hours'" in weekly
    assert "f.activation_at is not null" in weekly
    assert "coalesce(f.activation_at, f.cohort_at)" not in sql


def test_durable_value_requires_project_continuity_or_nonempty_generated_file():
    sql = normalized_sql()

    for relation in (
        "from public.project_chats as pc",
        "from public.project_files as pf",
        "from public.user_files as file_row",
    ):
        assert sql.count(relation) >= 2

    assert sql.count("project_row.archived_at is null") >= 4
    assert sql.count("file_row.deleted_at is null") >= 4
    assert sql.count("file_row.status = 'ready'") >= 4
    assert sql.count("file_row.size_bytes > 0") >= 2
    assert sql.count("'generated_document'") >= 2


def test_both_cohorts_enforce_the_exact_environment_and_internal_boundary():
    sql = normalized_sql()

    assert sql.count("u.registration_environment = p_environment") == 2
    assert sql.count(
        "p_environment = 'production' and u.registration_environment is null"
    ) == 2
    assert sql.count("coalesce(u.internal_tier, '') = ''") == 2
    assert sql.count("u.deleted_at is null") == 2


def test_exports_remain_content_free_private_and_finance_safe():
    sql = normalized_sql()
    weekly_start = sql.index(
        "create or replace function public.product_weekly_attribution_export"
    )
    return_contract = sql[
        sql.index("returns table", weekly_start):
        sql.index("language plpgsql", weekly_start)
    ]

    for forbidden in (
        "user_id",
        "email",
        "prompt",
        "response",
        "filename",
        "project_id",
        "file_id",
        "referrer",
        "url",
        "metadata",
    ):
        assert forbidden not in return_contract

    assert sql.count("security invoker") == 2
    assert sql.count("set search_path = ''") == 2
    assert sql.count("from public, anon, authenticated") == 2
    assert sql.count("to service_role") == 2
    assert sql.count("null::bigint") >= 3
    assert "finance fields remain null" in sql


def test_retention_denominators_are_anchored_to_effective_activation():
    sql = normalized_sql()

    assert sql.count("d.activation_at is not null") >= 2
    assert sql.count("f.activation_at is not null") >= 2
    assert sql.count("= (d.activation_at at time zone 'utc')::date + 1") == 1
    assert sql.count("= (d.activation_at at time zone 'utc')::date + 7") == 1
    assert sql.count("= (f.activation_at at time zone 'utc')::date + 1") == 1
    assert sql.count("= (f.activation_at at time zone 'utc')::date + 7") == 1
