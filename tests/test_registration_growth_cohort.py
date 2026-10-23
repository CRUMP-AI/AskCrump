from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = (
    ROOT
    / "migrations"
    / "20261023191029_registration_submission_cohorts.sql"
)
WORKFLOW = ROOT / ".github" / "workflows" / "postgres-migration-gate.yml"


def normalized_sql() -> str:
    return " ".join(MIGRATION.read_text(encoding="utf-8").lower().split())


def test_registration_boundary_is_nullable_durable_and_conservatively_backfilled():
    sql = normalized_sql()

    assert "add column if not exists registration_submitted_at timestamptz" in sql
    assert "registration_submitted_at timestamptz default" not in sql
    assert "select distinct on (event.user_id)" in sql
    assert "order by event.user_id, event.created_at, event.id" in sql
    assert "event.created_at >= account.created_at" in sql
    assert "first_event.created_at >= account.created_at" in sql
    assert "event.environment in ('production', 'preview', 'development')" in sql
    assert "set registration_submitted_at = account.updated_at" not in sql
    assert "ambiguous post-guest-launch account(s)" in sql
    assert "'guest-' || account.id::text || '@guest.askcrump.local'" in sql


def test_postgres_gate_exercises_the_fail_closed_refusal_and_rollback_path():
    workflow = " ".join(WORKFLOW.read_text(encoding="utf-8").lower().split())

    assert "registration_growth_cohort_ambiguous_fixture.sql" in workflow
    assert "--set=verbosity=verbose" in workflow
    assert 'grep -f "55000"' in workflow
    assert "registration_growth_cohort_refusal_rollback.sql" in workflow


def test_registration_boundary_is_immutable_and_trigger_is_not_an_rpc():
    sql = normalized_sql()

    assert "users_registration_submission_boundary_check" in sql
    assert "registration_submitted_at is not null and registration_environment" in sql
    assert "registration_submitted_at >= created_at" in sql
    assert "created_at < timestamptz '2026-10-23 18:01:51.842574+00'" in sql
    assert "security invoker set search_path = ''" in sql
    assert "new.registration_submitted_at := old.registration_submitted_at" in sql
    assert "new.registration_environment := old.registration_environment" in sql
    assert "if tg_op = 'insert'" in sql
    assert (
        "if new.registration_submitted_at is null and new.is_guest is false then"
        in sql
    )
    assert "before insert on public.users" in sql
    assert "coalesce(new.registration_submitted_at, pg_catalog.statement_timestamp())" in sql
    assert "'guest-' || old.id::text || '@guest.askcrump.local'" in sql
    assert (
        "before update of registration_submitted_at, registration_environment, email"
        in sql
    )
    assert (
        "revoke all on function "
        "public.enforce_registration_submission_immutability_v1() "
        "from public, anon, authenticated, service_role"
        in sql
    )


def test_all_registered_account_reports_use_the_reviewed_cohort_rewrite():
    sql = normalized_sql()

    for signature in (
        "public.product_growth_funnel_snapshot(timestamptz,timestamptz,text,boolean)",
        "public.product_weekly_attribution_export(timestamptz,timestamptz,text,boolean)",
        "public.product_project_continuity_snapshot(timestamptz,timestamptz,text,boolean)",
    ):
        assert signature in sql

    assert "when u.registration_submitted_at is not null" in sql
    assert "when u.is_guest is false" in sql
    assert "users_registration_submission_cohort_idx" in sql
    assert "where deleted_at is null;" in sql
    assert (
        "where deleted_at is null and (registration_submitted_at is not null"
        not in sql
    )
    assert "v_anchor_count <> 3" in sql
    assert "refusing rewrite" in sql
    assert "preview-only guests are excluded" in sql


def test_report_privacy_and_finance_contracts_remain_explicit():
    sql = normalized_sql()

    assert sql.count("from public, anon, authenticated;") == 3
    assert sql.count("to service_role") == 3
    assert "content-free" in sql
    assert "finance fields remain null" in sql
    assert "optional profile-name completion" in sql
