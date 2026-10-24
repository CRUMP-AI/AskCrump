from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "migrations" / "20261024001624_harden_legacy_delete_own_account.sql"
WORKFLOW = ROOT / ".github" / "workflows" / "postgres-migration-gate.yml"


def test_legacy_self_delete_hardening_is_conditional_and_non_replacing():
    sql = MIGRATION.read_text(encoding="utf-8").lower()

    assert (
        "target_oid oid := "
        "pg_catalog.to_regprocedure('public.delete_own_account()')"
    ) in sql
    assert "if target_oid is null" in sql
    assert "e8e18f430f5911f16824ff7b2ec36068" in sql
    assert "22f067b67e8e0209a3ef29bc3c28e37d" in sql
    assert "using errcode = '55000'" in sql
    assert "alter function public.delete_own_account() set search_path" in sql
    assert "revoke execute on function public.delete_own_account() from public, anon" in sql
    assert (
        "grant execute on function public.delete_own_account() "
        "to authenticated, service_role"
    ) in sql
    assert "create function public.delete_own_account" not in sql
    assert "create or replace function public.delete_own_account" not in sql
    assert "drop function" not in sql


def test_postgres_gate_exercises_absent_and_present_legacy_function_paths():
    workflow = WORKFLOW.read_text(encoding="utf-8")

    migration = "migrations/20261024001624_harden_legacy_delete_own_account.sql"
    baseline = "tests/postgres/legacy_delete_own_account_baseline.sql"
    absent_test = "tests/postgres/test_legacy_delete_own_account_absent.sql"
    present_test = "tests/postgres/test_legacy_delete_own_account_migration.sql"
    drift_fixture = "tests/postgres/legacy_delete_own_account_drift_fixture.sql"
    drift_test = "tests/postgres/test_legacy_delete_own_account_drift_refusal.sql"
    acl_drift_fixture = "tests/postgres/legacy_delete_own_account_acl_drift_fixture.sql"
    acl_drift_test = "tests/postgres/test_legacy_delete_own_account_acl_drift_refusal.sql"

    assert "legacy-account-deletion-security:" in workflow
    assert workflow.count(migration) == 5
    migration_positions = []
    cursor = 0
    while (position := workflow.find(migration, cursor)) != -1:
        migration_positions.append(position)
        cursor = position + len(migration)
    assert migration_positions[0] < workflow.index(absent_test)
    assert workflow.index(absent_test) < workflow.index(baseline)
    assert workflow.index(baseline) < migration_positions[1]
    assert migration_positions[1] < migration_positions[2]
    assert migration_positions[2] < workflow.index(present_test)
    assert workflow.index(present_test) < workflow.index(drift_fixture)
    assert workflow.index(drift_fixture) < migration_positions[3]
    assert migration_positions[3] < workflow.index(drift_test)
    assert workflow.index(drift_test) < workflow.index(acl_drift_fixture)
    assert workflow.index(acl_drift_fixture) < migration_positions[4]
    assert migration_positions[4] < workflow.index(acl_drift_test)
    assert "Unexpected public.delete_own_account() definition" in workflow
    assert "Unexpected public.delete_own_account() ACL" in workflow
