from __future__ import annotations

from pathlib import Path
import re

from backend import config
from backend.connected_app_host_bootstrap import (
    CONNECTED_DATABASE_CONTRACT_SHA256,
    CONNECTED_PROVIDER_CONTRACT_SHA256,
)


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = (
    ROOT / "migrations" / "20261108069000_connected_runtime_readiness_attestation.sql"
)
SQL = MIGRATION.read_text(encoding="utf-8")
TRANSITION_SQL = (
    ROOT / "migrations" / "20261108069100_connected_approval_effect_transition.sql"
).read_text(encoding="utf-8")
BEHAVIOR_SQL = (
    ROOT / "tests" / "postgres" / "test_connected_runtime_readiness_attestation.sql"
).read_text(encoding="utf-8")


def test_readiness_migration_is_forward_exact_and_contract_bound() -> None:
    assert "__PREDECESSOR_FINGERPRINT__" not in SQL
    assert "__TARGET_FINGERPRINT__" not in SQL
    assert "connected_multi_account_private.multi_account_target_fingerprint_v1()" in SQL
    assert SQL.count(CONNECTED_DATABASE_CONTRACT_SHA256) == 3
    assert SQL.count(CONNECTED_PROVIDER_CONTRACT_SHA256) == 3
    assert BEHAVIOR_SQL.count(CONNECTED_DATABASE_CONTRACT_SHA256) >= 3
    assert BEHAVIOR_SQL.count(CONNECTED_PROVIDER_CONTRACT_SHA256) >= 8
    targets = re.findall(r"[0-9a-f]{32}", SQL)
    assert len(set(targets)) >= 2
    assert SQL.count("using errcode='55000'") >= 6
    assert SQL.startswith("\\set ON_ERROR_STOP on\n\nbegin;")
    assert SQL.rstrip().endswith("commit;")


def test_provider_smoke_is_content_free_private_bounded_and_forced_rls() -> None:
    compact = "".join(SQL.split()).casefold()
    assert "create schema if not exists connected_readiness_private" in SQL
    assert "create table if not exists connected_readiness_private.provider_smoke" in SQL
    assert "altertableconnected_readiness_private.provider_smokeenablerowlevelsecurity" in compact
    assert "altertableconnected_readiness_private.provider_smokeforcerowlevelsecurity" in compact
    assert "provider_smoke_challenge" in SQL
    assert "expires_at<=issued_at+interval'15minutes'" in compact
    assert "CONTENT_FREE_DURABLE_EXACT_DEPLOYMENT" in SQL
    assert "host_configuration_ciphertext_sha256" in SQL
    assert "database_target_fingerprint" in SQL
    assert "root_key_id" in SQL
    assert "publication exposure refused" in SQL
    smoke_tables = re.search(
        r"create table if not exists connected_readiness_private\.provider_smoke_challenge"
        r"(?P<body>.*?)"
        r"create or replace function public\.connected_app_claim_release_preview_ceremony_v1",
        SQL,
        flags=re.DOTALL,
    )
    assert smoke_tables is not None
    content_free_smoke_sql = smoke_tables.group("body").casefold()
    for forbidden in (
        "owner_id",
        "account_id",
        "connection_id",
        "message_id",
        "calendar_id",
        "event_id",
        "email_address",
        "subject_text",
        "access_token",
        "refresh_token",
    ):
        assert forbidden not in content_free_smoke_sql
    assert "owner_id uuid not null references public.users(id)" in SQL
    assert "dedicated_account_attestation_sha256" in SQL


def test_readiness_rpcs_are_service_role_only_empty_search_path_and_live() -> None:
    assert (
        "public.connected_app_issue_provider_smoke_challenge_v1(\n"
        "  p_composition_manifest_sha256 text"
    ) in SQL
    assert (
        "public.connected_app_record_provider_smoke_v1(\n"
        "  p_composition_manifest_sha256 text"
    ) in SQL
    assert (
        "public.connected_app_runtime_readiness_v1(\n"
        "  p_expected_manifest_sha256 text"
    ) in SQL
    assert SQL.count("security definer set search_path=''") == 14
    assert SQL.count("to service_role;") == 13
    assert "from public,anon,authenticated,service_role;" in SQL
    assert "runtime_readiness_target_fingerprint_v1()" in SQL
    assert "provider smoke is absent or mismatched" in SQL
    assert "reference+interval '15 minutes'" in SQL
    assert "challenge_id=p_challenge_id" in SQL
    assert "delete from connected_readiness_private.provider_smoke_challenge" in SQL


def test_full_stack_fingerprint_covers_authority_privacy_and_hidden_objects() -> None:
    assert "observed_target[[:space:]]*<>[[:space:]]*''[0-9a-f]{32}''" in SQL
    assert "'[0-9a-f]{32}','<TARGET_FINGERPRINT>'" not in SQL
    for item in (
        "pg_namespace",
        "pg_class",
        "pg_inherits",
        "pg_sequence",
        "pg_depend",
        "pg_attribute",
        "pg_constraint",
        "pg_index",
        "pg_trigger",
        "pg_rewrite",
        "pg_type",
        "pg_enum",
        "pg_policies",
        "pg_default_acl",
        "pg_proc",
        "pg_roles",
        "pg_auth_members",
        "pg_publication",
        "pg_publication_rel",
        "pg_publication_namespace",
        "relrowsecurity",
        "relforcerowsecurity",
        "relispopulated",
        "relispartition",
        "pg_get_viewdef",
        "attcollation",
        "attmissingval",
        "connoinherit",
        "tgconstraint",
        "indisexclusion",
        "indnullsnotdistinct",
        "tgenabled",
        "ev_enabled",
        "typcategory",
        "prosecdef",
        "prokind",
        "proconfig",
        "proacl",
        "pubviaroot",
        "prqual",
        "rolconnlimit",
        "rolconfig",
        "obj_description",
        "col_description",
        "apply_guest_chat_sync_v2",
        "persist_guest_chat_reply_v1",
        "consume_password_reset_v1",
        "delete_user_account",
        "claim_ai_gateway_cost_receipt",
        "settle_ai_gateway_cost_receipt",
    ):
        assert item in SQL


def test_final_readiness_target_is_the_atomic_691_catalog() -> None:
    assert "59714dce4c61f8140eddc1a2c8606b70" in TRANSITION_SQL
    assert config.CONNECTED_APPS_DATABASE_TARGET_FINGERPRINT in TRANSITION_SQL
    assert "runtime_readiness_catalog_fingerprint_v1()" in TRANSITION_SQL
    assert "runtime_readiness_target_fingerprint_v1()" in TRANSITION_SQL
    assert "connected_app_consume_approval_and_begin_effect_v1" in TRANSITION_SQL
    for primitive in (
        "connected_app_create_approval_v1",
        "connected_app_consume_approval_v1",
        "connected_app_begin_effect_v1",
    ):
        assert f"revoke all on function public.{primitive}" in TRANSITION_SQL
    assert "connected_app_operator_decide_approval_v1" in TRANSITION_SQL
    assert "publication exposure refused" in TRANSITION_SQL
