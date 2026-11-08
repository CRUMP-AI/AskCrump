from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "migrations" / "20261107190000_connected_app_control_plane.sql"
VERIFIER = ROOT / "scripts" / "verify-connected-app-control-plane-exact-reapply-pg17.ps1"


def test_base_control_plane_reapply_is_attested_before_idempotent_ddl() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")

    assert "3700cbb8e9d67dab331d090b26a70510" in sql
    assert "observed_target_fingerprint" in sql
    assert "partial or drifted connected-app target; refusing repair" in sql
    assert "using errcode = '55000'" in sql
    assert sql.index("observed_target_fingerprint <>") < sql.index(
        "create schema if not exists connected_app_private"
    )
    assert "on conflict (action) do nothing" in sql
    assert "set_config('quote_all_identifiers', 'off', false)" in sql

    assert not re.search(r"(?m)^create table connected_app_private\.", sql)
    assert not re.search(r"(?m)^create function (?:public|connected_app_private)\.", sql)
    assert not re.search(r"(?m)^create (?:unique )?index (?!if not exists )", sql)
    assert not re.search(r"(?m)^create sequence connected_app_private\.", sql)
    assert not re.search(r"(?m)^create trigger connected_app_", sql)

    assert len(re.findall(r"(?m)^create table if not exists connected_app_private\.", sql)) == 13
    assert len(re.findall(r"(?m)^create or replace function ", sql)) == 54
    assert "create or replace trigger connected_app_owner_delete_cleanup_v1" in sql


def test_exact_target_manifest_covers_security_and_catalog_boundaries() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    required_fragments = (
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
        "'allowlist'",
        "'publication_all_tables'",
        "'publication_private'",
        "'effective'",
        "pg_get_function_identity_arguments",
        "pg_get_function_result",
        "md5(proc_row.prosrc)",
        "pg_get_constraintdef",
        "pg_get_indexdef",
        "pg_get_triggerdef",
        "has_schema_privilege",
        "has_table_privilege",
        "has_function_privilege",
        "pg_has_role",
    )
    for fragment in required_fragments:
        assert fragment in sql


def test_postgres_gate_plants_representative_drift_and_requires_no_repair() -> None:
    verifier = VERIFIER.read_text(encoding="utf-8")
    assert "PASS fresh apply + hostile exact reapply" in verifier
    assert "quote_all_identifiers=on" in verifier
    assert "55000" in verifier
    assert "refusing repair" in verifier
    assert "before -ne $after" in verifier
    for drift in (
        "column_default",
        "constraint",
        "index",
        "function_source",
        "function_config",
        "table_acl",
        "column_acl",
        "comment",
        "trigger",
        "rule",
        "publication",
        "sequence",
        "overload",
        "owner",
        "extra_table",
        "extra_type",
        "policy",
        "rls",
        "default_acl",
    ):
        assert f'Name = "{drift}"' in verifier
