from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "migrations" / "20261108043000_connected_dispatch_execution_outbox.sql"


def _sql() -> str:
    return MIGRATION.read_text(encoding="utf-8")


def test_dispatch_is_separate_content_free_private_schema() -> None:
    sql = _sql()
    assert "create schema if not exists connected_dispatch_private" in sql
    assert "create table if not exists connected_dispatch_private.execution_outbox" in sql
    assert "content text" not in sql
    assert "subject text" not in sql
    assert "body text" not in sql
    assert "recipient" not in sql
    assert "ASK_CRUMP_CONNECTED_DISPATCH_OUTBOX_V1_CONTENT_FREE_RUNTIME_LEDGER_FINAL" in sql


def test_source_rows_are_discovered_not_assumed_atomically_enqueued() -> None:
    sql = _sql()
    assert "connected_app_private.action_preparations" in sql
    assert "connected_app_private.approval_reviews" in sql
    assert "connected_app_private.approvals" in sql
    assert "connected_dispatch_private.ensure_one_v1" in sql
    assert "not exists (" in sql
    assert "connected_dispatch_reconcile_owner_v1" in sql


def test_every_mutating_boundary_takes_owner_lock_before_row_locks() -> None:
    sql = _sql()
    for function in (
        "ensure_one_v1",
        "settle_from_ledger_v1",
        "reconcile_one_v1",
        "connected_dispatch_reconcile_owner_v1",
        "connected_dispatch_claim_v1",
        "connected_dispatch_mark_invoked_v1",
        "connected_dispatch_preflight_failure_v1",
        "connected_dispatch_settle_v1",
        "connected_dispatch_report_runtime_exit_v1",
    ):
        start = sql.index(f"function {'public.' if function.startswith('connected_') else 'connected_dispatch_private.'}{function}")
        end = sql.index("$fn$;", start)
        body = sql[start:end]
        assert "owner_lock_v1" in body
        if "for update" in body or "for share" in body:
            assert body.index("owner_lock_v1") < min(
                position for token in ("for update", "for share")
                if (position := body.find(token)) >= 0
            )


def test_runtime_ledger_and_encrypted_read_result_are_terminal_authority() -> None:
    sql = _sql()
    assert "connected_app_private.action_ledger" in sql
    assert "connected_app_private.read_results" in sql
    assert "read_result_ref = read_row.result_payload_id" in sql
    assert "provider_request_id_sha256 = ledger_row.provider_request_id_sha256" in sql
    assert "provider_resource_id_sha256 = ledger_row.provider_resource_id_sha256" in sql
    assert "status = 'effect_unknown'" in sql
    assert "status = 'queued'" in sql


def test_private_storage_and_public_rpc_family_are_service_only() -> None:
    sql = _sql()
    assert "force row level security" in sql
    assert "revoke all on all tables in schema connected_dispatch_private" in sql
    assert "grant execute on function %s to service_role" in sql
    assert "connected-dispatch catalog exposure drifted" in sql
    assert "target_fingerprint <> 'f57cba04c9b7d590d97e1ea62f960f30'" in sql
