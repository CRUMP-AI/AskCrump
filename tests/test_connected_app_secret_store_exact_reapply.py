from __future__ import annotations

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
STORE = ROOT / "migrations" / "20261107230000_connected_app_secret_payload_stores.sql"
OAUTH = ROOT / "migrations" / "20261107231500_connected_app_oauth_secret_custody.sql"
VERIFIER = (
    ROOT / "scripts" / "verify-connected-app-secret-store-exact-reapply-pg17.ps1"
)


def _assert_attested_idempotent_migration(
    sql: str, *, fingerprint: str, first_table: str
) -> None:
    assert fingerprint in sql
    assert "observed_target_fingerprint" in sql
    assert "refusing repair" in sql
    assert "using errcode = '55000'" in sql
    assert "set_config('search_path', 'pg_catalog,public', true)" in sql
    assert "set_config('quote_all_identifiers', 'off', true)" in sql
    assert sql.index("observed_target_fingerprint <>") < sql.index(first_table)

    assert not re.search(r"(?m)^create table connected_app_private\.", sql)
    assert not re.search(
        r"(?m)^create function (?:public|connected_app_private)\.", sql
    )
    assert not re.search(r"(?m)^create (?:unique )?index (?!if not exists )", sql)
    assert not re.search(r"(?m)^create trigger connected_", sql)
    assert "create table if not exists connected_app_private." in sql
    assert "create or replace function " in sql
    assert "create or replace trigger connected_" in sql


def test_encrypted_store_reapply_is_exactly_attested_before_idempotent_ddl() -> None:
    sql = STORE.read_text(encoding="utf-8")
    _assert_attested_idempotent_migration(
        sql,
        fingerprint="f250e5f3e93732daabde65b3e3942f71",
        first_table="create table if not exists connected_app_private.payload_envelopes",
    )
    assert len(
        re.findall(r"(?m)^create table if not exists connected_app_private\.", sql)
    ) == 6
    assert len(re.findall(r"(?m)^create or replace function ", sql)) == 14
    assert len(re.findall(r"(?m)^create or replace trigger connected_", sql)) == 3


def test_oauth_secret_reapply_is_exactly_attested_before_idempotent_ddl() -> None:
    sql = OAUTH.read_text(encoding="utf-8")
    _assert_attested_idempotent_migration(
        sql,
        fingerprint="15a55a3a38c8fe732729e6d38c79c880",
        first_table="create table if not exists connected_app_private.oauth_secret_custody",
    )
    assert len(
        re.findall(r"(?m)^create table if not exists connected_app_private\.", sql)
    ) == 4
    assert len(re.findall(r"(?m)^create or replace function ", sql)) == 13
    assert len(re.findall(r"(?m)^create or replace trigger connected_", sql)) == 2


def test_both_target_manifests_cover_catalog_authority_and_hidden_surfaces() -> None:
    required_fragments = (
        "'schema'",
        "'relation'",
        "'column'",
        "'constraint'",
        "'index'",
        "'sequence'",
        "'type'",
        "'function'",
        "'trigger'",
        "'rule'",
        "'policy'",
        "'default_acl'",
        "'publication_all_tables'",
        "'publication_private'",
        "'effective_schema'",
        "'effective_table'",
        "'effective_column'",
        "'effective_function'",
        "pg_get_function_identity_arguments",
        "pg_get_function_result",
        "pg_get_functiondef",
        "pg_get_constraintdef",
        "pg_get_indexdef",
        "pg_get_triggerdef",
        "pg_get_ruledef",
        "has_schema_privilege",
        "has_table_privilege",
        "has_column_privilege",
        "has_function_privilege",
        "pg_has_role",
    )
    for migration in (STORE, OAUTH):
        sql = migration.read_text(encoding="utf-8")
        for fragment in required_fragments:
            assert fragment in sql

    assert "'allowlist'" in STORE.read_text(encoding="utf-8")


def test_postgres_gate_requires_hostile_exact_noop_and_representative_no_repair() -> None:
    verifier = VERIFIER.read_text(encoding="utf-8")
    assert "PASS encrypted-store fresh apply + hostile exact reapply" in verifier
    assert "PASS OAuth-secret fresh apply + hostile exact reapply" in verifier
    assert "quote_all_identifiers=on" in verifier
    assert "55000" in verifier
    assert "refusing repair" in verifier
    assert "$before -ne $after" in verifier
    for drift in (
        "s_col",
        "s_constraint",
        "s_index",
        "s_func_src",
        "s_func_cfg",
        "s_table_acl",
        "s_column_acl",
        "s_schema_acl",
        "s_comment",
        "s_trigger",
        "s_hidden_trg",
        "s_rule",
        "s_policy",
        "s_pub",
        "s_overload",
        "s_owner",
        "s_rls",
        "s_default_acl",
        "o_col",
        "o_constraint",
        "o_index",
        "o_func_src",
        "o_func_cfg",
        "o_table_acl",
        "o_column_acl",
        "o_comment",
        "o_trigger",
        "o_hidden_trg",
        "o_rule",
        "o_policy",
        "o_pub",
        "o_overload",
        "o_owner",
        "o_rls",
    ):
        assert f'Name = "{drift}"' in verifier
