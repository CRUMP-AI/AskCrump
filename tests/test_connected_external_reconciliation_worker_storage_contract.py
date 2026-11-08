from __future__ import annotations

import hashlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PREDECESSOR = ROOT / "migrations" / "20261108064000_connected_oauth_operator_bridge.sql"
MIGRATION = (
    ROOT / "migrations" / "20261108065000_connected_external_reconciliation_worker.sql"
)


def test_reconciliation_migration_pins_exact_reviewed_operator_predecessor():
    sql = MIGRATION.read_text(encoding="utf-8")

    assert hashlib.sha256(PREDECESSOR.read_bytes()).hexdigest().upper() == (
        "92F0FB26CEC7D25525DDD6F694A65DD8F42EE7DC2F1E0E6571D8F0FA689E7D9F"
    )
    assert "1bce6135686a0d64ec522a9217c9ea0c" in sql
    assert "95612aca01e069376fb82aca32e286e9" in sql
    assert "52629ef0c6f07fe7ac8eb4292bfc59aa" in sql
    assert "connected external reconciliation predecessor drifted" in sql
    assert "connected external reconciliation target drifted" in sql


def test_reconciliation_rpc_is_content_free_bounded_and_service_role_only():
    sql = MIGRATION.read_text(encoding="utf-8")

    assert "p_limit < 1 or p_limit > 100" in sql
    assert "pg_try_advisory_xact_lock" in sql
    assert "for update skip locked" in sql
    assert "'expired_flows', expired_flow_count" in sql
    assert "'expired_provisionals', expired_provisional_count" in sql
    assert "from public, anon, authenticated" in sql
    assert "to service_role" in sql
    assert "security definer" in sql
    assert "set search_path = ''" in sql
    assert "puballtables" in sql
    assert "pg_publication_namespace" in sql
    assert "where namespace_row.nspname = 'connected_app_private'" in sql
    assert "grant execute on function public.connected_app_oauth_reconcile_expired_v1(integer)\n  to anon" not in sql
    assert "grant execute on function public.connected_app_oauth_reconcile_expired_v1(integer)\n  to authenticated" not in sql
