from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "migrations" / "20261024043331_email_verification_measurement.sql"
POSTGRES_TEST = (
    ROOT / "tests" / "postgres" / "test_email_verification_measurement_migration.sql"
)
WORKFLOW = ROOT / ".github" / "workflows" / "postgres-migration-gate.yml"


def normalized(path: Path) -> str:
    return " ".join(path.read_text(encoding="utf-8").lower().split())


def test_migration_records_an_immutable_database_verification_boundary():
    sql = normalized(MIGRATION)

    assert "add column if not exists email_verified_at timestamptz" in sql
    assert "new.email_verified_at := pg_catalog.statement_timestamp()" in sql
    assert "old.is_verified is false and new.is_verified is true" in sql
    assert "new.email_verified_at := old.email_verified_at" in sql
    assert "legacy timing unavailable" in sql
    assert "security invoker" in sql
    assert "set search_path = ''" in sql
    assert "from public, anon, authenticated, service_role" in sql


def test_growth_reports_fail_closed_without_known_verification_timing():
    sql = normalized(MIGRATION)

    assert "e.event_name = 'accountcreated'" in sql
    assert "e.created_at >= c.email_verified_at" in sql
    assert "j.created_at >= f.email_verified_at" in sql
    assert "j.updated_at >= f.email_verified_at" in sql
    assert "signals.email_verified_at is not null" in sql
    assert "email_verified_at < p_until" in sql
    assert "f.email_verified_at" in sql
    assert "email_verified_at < p_until" in sql
    assert "legacy unknown timing is excluded" in sql
    assert "unexpected preexisting verification timing" in sql
    assert "using errcode = '55000'" in sql


def test_real_postgres_gate_exercises_ordering_window_and_acl_contracts():
    workflow = normalized(WORKFLOW)
    test_sql = normalized(POSTGRES_TEST)

    assert "20261024043331_email_verification_measurement.sql" in workflow
    assert "test_email_verification_measurement_migration.sql" in workflow
    assert workflow.index("20261023191029_registration_submission_cohorts.sql") < workflow.index(
        "20261024043331_email_verification_measurement.sql"
    )
    assert "pre-verification completed answer activated after verification" in test_sql
    assert "verification window rewrote history" in test_sql
    assert "legacy unknown verification timing was fabricated" in test_sql
    assert "project_save_completed" in test_sql
    assert "d1_returned" in test_sql
    assert "d7_returned" in test_sql
    assert "has_function_privilege('anon'" in test_sql
    assert "has_function_privilege('service_role'" in test_sql
