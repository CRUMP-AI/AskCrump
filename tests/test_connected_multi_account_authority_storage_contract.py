from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "migrations" / "20261108068900_connected_multi_account_authority.sql"
SQL = MIGRATION.read_text(encoding="utf-8")
COMPACT = re.sub(r"\s+", "", SQL.lower())
RACES = (ROOT / "tests" / "postgres" / "test_connected_multi_account_authority_races.sql").read_text(
    encoding="utf-8"
)
GATE = (ROOT / "scripts" / "verify-connected-multi-account-authority-pg17.ps1").read_text(
    encoding="utf-8"
)
OAUTH_BRIDGE = (
    ROOT / "migrations" / "20261108064000_connected_oauth_operator_bridge.sql"
).read_text(encoding="utf-8")


def _function_body(name: str) -> str:
    match = re.search(
        rf"create or replace function public\.{re.escape(name)}\(.*?\n\$fn\$;",
        SQL,
        flags=re.DOTALL | re.IGNORECASE,
    )
    assert match is not None
    return match.group(0).lower()


def test_active_authority_is_unique_per_account_kind_and_resource() -> None:
    assert (
        "dropindexifexistsconnected_app_private."
        "connected_app_connections_one_active_resource_idx"
    ) in COMPACT
    assert "connected_app_connections_one_active_account_kind_resource_idx" in SQL
    assert (
        "onconnected_app_private.connections(owner_id,provider,account_kind,resource)"
        "whereauthorization_state='active'"
    ) in COMPACT
    assert "ASK_CRUMP_ONE_ACTIVE_CONNECTION_PER_OWNER_PROVIDER_ACCOUNT_KIND_RESOURCE_V1" in SQL


def test_start_and_finalize_conflicts_are_scoped_to_the_exact_account_kind() -> None:
    prepare = _function_body("connected_app_operator_prepare_oauth_start_v2")
    finalize = _function_body("connected_app_oauth_finalize_v2")
    for body in (prepare, finalize):
        assert "connection.provider=p_provider" in body or "live_connection.provider=p_provider" in body
        assert "account_kind=p_account_kind" in body
        assert "resource=p_resource" in body
    assert "connected_app_operator_prepare_oauth_start_v1" in prepare
    assert "connected_app_oauth_finalize_v1" in finalize
    assert "live_connection.account_kind=p_account_kind" in finalize


def test_migration_is_exact_predecessor_and_exact_target_guarded() -> None:
    assert "oauth_code_custody_target_fingerprint_v1()" in SQL
    assert "multi_account_target_fingerprint_v1()" in SQL
    assert "target is partial" in SQL
    assert "publication exposure refused" in SQL
    assert "using errcode='55000'" in SQL
    assert "00000000000000000000000000000000" not in SQL


def test_fresh_stack_oauth_bridge_predecessor_pin_is_reproducible() -> None:
    assert "19213a47c265e0d80bc06a4dfbdd18f8" in OAUTH_BRIDGE
    assert "59771080b2eddba748998c7ba3ba30fc" not in OAUTH_BRIDGE


def test_target_attests_acl_rls_search_path_owner_and_hidden_objects() -> None:
    assert "class_row.relrowsecurity" in SQL
    assert "class_row.relforcerowsecurity" in SQL
    assert "pg_catalog.pg_get_userbyid(class_row.relowner)" in SQL
    assert "attribute_row.attacl" in SQL
    assert "from pg_catalog.pg_policy as policy_row" in SQL
    assert "coalesce(procedure.proconfig::text,'')" in SQL
    assert "coalesce(procedure.proacl::text,'')" in SQL
    assert "pg_catalog.pg_get_triggerdef" in SQL
    assert "pg_catalog.pg_get_ruledef" in SQL
    assert "pg_catalog.pg_publication" in SQL
    assert "from public,anon,authenticated" in SQL
    assert "to service_role" in SQL
    assert "has_schema_privilege" in SQL


def test_postgres_gate_covers_both_winner_orders_and_no_repair_drifts() -> None:
    assert "different-a-first" in RACES
    assert "different-b-first" in RACES
    assert "same-a-first" in RACES
    assert "same-b-first" in RACES
    assert "account_kind_count<>2" in RACES
    assert "pg_catalog.count(*)<>1" in RACES
    for name in (
        '"missing"',
        '"partial"',
        '"predecessor"',
        '"search_path"',
        '"acl"',
        '"owner"',
        '"rls"',
        '"column_acl"',
        '"hidden_policy"',
        '"publication"',
        '"carried_publication_namespace"',
        '"hidden_trigger"',
        '"hidden_rule"',
        '"carried_attestation"',
    ):
        assert name in GATE
    assert "drift was mutated before refusal" in GATE
    assert "55000" in GATE


def test_migration_remains_local_and_transactional() -> None:
    assert SQL.startswith("\\set ON_ERROR_STOP on\n\nbegin;")
    assert SQL.rstrip().endswith("commit;")
    assert "apply_migration" not in SQL
    assert "supabase_migrations.schema_migrations" not in SQL
