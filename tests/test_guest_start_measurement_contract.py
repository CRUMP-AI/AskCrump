from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "migrations" / "20261027184134_guest_start_measurement.sql"
POSTGRES_TEST = ROOT / "tests" / "postgres" / "test_guest_start_measurement_migration.sql"
SECURITY_BASELINE = (
    ROOT / "tests" / "postgres" / "guest_start_measurement_security_baseline.sql"
)
CONCURRENCY_TEST = (
    ROOT / "tests" / "postgres" / "test_guest_start_measurement_concurrency.sh"
)
DRIFT_TEST = ROOT / "tests" / "postgres" / "test_guest_start_measurement_drift.sh"
WORKFLOW = ROOT / ".github" / "workflows" / "postgres-migration-gate.yml"


def test_forward_only_columns_and_successful_session_boundary() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")

    assert "add column if not exists guest_start_tracking_version smallint" in sql
    assert "alter column guest_start_tracking_version set default 1" in sql
    assert "add column if not exists guest_started_at timestamptz" in sql
    assert "add column if not exists guest_start_environment text" in sql
    assert "guest_start_tracking_version is null" in sql
    assert "account.guest_start_tracking_version = 1" in sql
    assert "after insert or update of user_id" in sql
    assert "before insert\non public.sessions" in sql
    assert "a_guest_start_owner_lock_v1" in sql
    assert "for update;" in sql
    assert "for update nowait" in sql
    assert "new.user_id is not distinct from old.user_id" in sql
    assert "update public.users as account" in sql
    assert "registration_environment" in sql
    assert "guest_start_environment = v_environment" in sql
    assert "v_stamp_at := pg_catalog.clock_timestamp()" in sql
    assert "set guest_started_at = v_stamp_at" in sql
    assert "set guest_started_at = pg_catalog.statement_timestamp()" not in sql
    assert "guest_started_at >= created_at" not in sql
    assert "guest_started_at <= registration_submitted_at" not in sql


def test_private_trigger_and_service_only_aggregate_contract() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")

    for signature in (
        "public.enforce_guest_start_immutability_v1()",
        "public.lock_guest_start_owner_before_session_v1()",
        "public.stamp_guest_start_from_session_v1()",
    ):
        assert f"revoke all on function {signature}" in sql

    signature = (
        "public.product_guest_start_funnel_snapshot(\n"
        "  timestamptz, timestamptz, text, boolean\n"
        ")"
    )
    assert "returns table(\n  stage_order smallint" in sql
    assert "security invoker" in sql
    assert "set search_path = ''" in sql
    assert f"revoke all on function {signature}" in sql
    assert f"grant execute on function {signature} to service_role" in sql
    assert "account.guest_start_environment = p_environment" in sql
    assert "and account.deleted_at is null" in sql
    assert "pg_catalog.md5(function_row.prosrc)" in sql
    assert "trigger_row.tgqual is null" in sql
    assert "index_row.indnkeyatts = 3" in sql
    assert "array['anon', 'authenticated']::text[]" in sql
    assert "array['public.users', 'public.sessions']::text[]" in sql
    assert "has_any_column_privilege(" in sql
    assert "language_row.lanname = 'plpgsql'" in sql
    assert "function_row.prokind = 'f'" in sql
    assert "function_row.proisstrict is false" in sql
    assert "function_row.proleakproof is false" in sql
    assert "function_row.proparallel = 'u'" in sql
    assert "if p_environment is null" in sql
    aggregate_sql = sql.split(
        "create or replace function public.product_guest_start_funnel_snapshot", 1
    )[1]
    assert "registration_environment = p_environment" not in aggregate_sql
    assert "event.environment = p_environment" not in aggregate_sql
    assert "on any later surface" in aggregate_sql
    assert "account.email," not in aggregate_sql
    assert "event.payload" not in aggregate_sql
    assert "job.output" not in aggregate_sql


def test_postgres_gate_covers_required_behavior_and_concurrency() -> None:
    postgres_test = POSTGRES_TEST.read_text(encoding="utf-8")
    concurrency_test = CONCURRENCY_TEST.read_text(encoding="utf-8")
    drift_test = DRIFT_TEST.read_text(encoding="utf-8")
    workflow = WORKFLOW.read_text(encoding="utf-8")
    security_baseline = SECURITY_BASELINE.read_text(encoding="utf-8")

    for contract in (
        "direct registration was counted as a guest start",
        "guest creation without a session was counted as a start",
        "successful guest session did not stamp exact environment and time",
        "device-session reassignment did not stamp the new guest",
        "verification or conversion rewrote the immutable guest-start boundary",
        "aggregate exposes identifiers or content-bearing fields",
        "post-cutover session fabricated legacy guest timing",
        "failed session persistence stamped a guest start",
        "conflict DO NOTHING was counted as a successful guest session",
        "soft-deleted guest session was counted as a guest start",
        "future app created_at rejected or rewrote the database guest-start stamp",
        "null environment unexpectedly succeeded",
        "soft deletion rewrote immutable facts needed to prove aggregate exclusion",
        "unexpected deletion-adjusted forward guest funnel",
    ):
        assert contract in postgres_test

    assert "on conflict (device_id) do update" in concurrency_test
    assert "v_stamped <> 2" in concurrency_test
    assert "near-expiry-owner-wait" in concurrency_test
    assert 'wait_for_ready "same-owner same-device"' in concurrency_test
    assert 'wait_for_ready "near-expiry owner-lock"' in concurrency_test
    assert "sleep 0.2" not in concurrency_test
    assert "same-marker function source" in drift_test
    assert "function STRICT/parallel attributes" in drift_test
    assert "user trigger columns/WHEN" in drift_test
    assert "index parent/key/include/opclass" in drift_test
    assert "users table ACL" in drift_test
    assert "users column ACL" in drift_test
    assert "users RLS" in drift_test
    assert "20261027184134_guest_start_measurement.sql" in workflow
    assert "test_guest_start_measurement_migration.sql" in workflow
    assert "test_guest_start_measurement_concurrency.sh" in workflow
    assert "test_guest_start_measurement_drift.sh" in workflow
    assert "guest_start_measurement_security_baseline.sql" in workflow
    assert "alter table public.users enable row level security" in security_baseline
    assert "alter table public.sessions enable row level security" in security_baseline
