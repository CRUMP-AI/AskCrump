"""Static guardrails for the disposable real-PostgreSQL deletion-fence harness."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/video-provider-deletion-fence-postgres.yml"
RUNNER = ROOT / "scripts/verify-video-provider-deletion-fence-postgres.sh"
BOOTSTRAP = ROOT / "tests/postgres/video_provider_deletion_fence_bootstrap.sql"
VERIFY = ROOT / "tests/postgres/video_provider_deletion_fence_verify.sql"


def test_postgres_harness_is_disposable_path_scoped_and_secret_free():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    pull_request = workflow.split("  pull_request:", 1)[1].split("  push:", 1)[0]
    required_paths = {
        ".github/workflows/video-provider-deletion-fence-postgres.yml",
        "staging/video_provider_deletion_fence.sql",
        "scripts/verify-video-provider-deletion-fence-postgres.sh",
        "tests/postgres/video_provider_deletion_fence_bootstrap.sql",
        "tests/postgres/video_provider_deletion_fence_verify.sql",
        "tests/test_video_deletion_fence_postgres_harness.py",
    }

    assert "image: postgres:17-bookworm" in workflow
    assert "services:" in workflow
    assert "workflow_dispatch:" in workflow
    assert "paths:" in pull_request
    assert all(f"- {path}" in pull_request for path in required_paths)
    assert "secrets." not in workflow.lower()
    assert "supabase.co" not in workflow.lower()
    assert "PGDATABASE: askcrump_video_fence_test" in workflow


def test_runner_refuses_production_and_exercises_real_connection_races():
    runner = RUNNER.read_text(encoding="utf-8")

    assert 'ASKCRUMP_DISPOSABLE_POSTGRES:-' in runner
    assert '[[ "$PGDATABASE" == "askcrump_video_fence_test" ]]' in runner
    assert "127.0.0.1|localhost)" in runner
    assert "refusing non-local PostgreSQL host" in runner
    assert "pg_blocking_pids" in runner
    assert "reservation_holder" in runner and "deletion_holder" in runner
    assert "establish_holder" in runner and "recovery_after_establish" in runner
    assert "recovery_holder" in runner and "establish_after_recovery" in runner
    assert "begin_after_establish" in runner
    assert "acceptance_holder" in runner and "acceptance_waiter" in runner
    assert "reconciliation_row_holder" in runner
    assert "set statement_timeout = '3 seconds'" in runner
    # Twice in the valid database (idempotent reapply), once in the isolated
    # invalid-legacy database (explicit preflight rollback).
    assert runner.count("--file staging/video_provider_deletion_fence.sql") == 3
    assert "deletion_fence_rls_probe" in runner
    assert "expired reconciliation lease reclaim" in runner
    assert "askcrump_video_fence_invalid_preflight" in runner
    assert "video deletion-fence preflight failed" in runner
    assert "secrets." not in runner.lower()
    assert "supabase.co" not in runner.lower()


def test_database_contract_covers_rls_acl_trigger_replay_and_leases():
    bootstrap = BOOTSTRAP.read_text(encoding="utf-8").lower()
    verify = VERIFY.read_text(encoding="utf-8").lower()

    assert "create role service_role nologin bypassrls" in bootstrap
    assert "on delete cascade" in bootstrap
    assert "enable row level security" in bootstrap

    for contract in (
        "has_table_privilege",
        "has_function_privilege",
        "not p.prosecdef",
        "before delete row trigger",
        "deletion without a fence",
        "expired reservation",
        "reservation replay",
        "dispatch replay",
        "acceptance replay",
        "same-token deletion replay",
        "database clock did not preserve a recent jobless fence",
        "recent same-token job did not remain fenced",
        "job without a video fence did not remain fail-closed",
        "established same-token begin replay",
        "non-active user accepted a different begin token",
        "legacy release did not preserve an established users fence",
        "changed-argument reservation replay",
        "whitespace-only accepted provider id",
        "deletion-recovery timeout",
        "legacy pending work",
        "backfill must classify pending work as unknown",
        "deletion_fence_rls_probe",
        "race_gates",
    ):
        assert contract in verify
