from pathlib import Path


SQL = Path("migrations/20261108023000_connected_plan_once.sql").read_text(encoding="utf-8")
NORMALIZED = " ".join(SQL.casefold().split())


def test_plan_once_uses_separate_catalog_and_never_expands_chat_manifest():
    assert "create schema if not exists connected_plan_private authorization postgres" in NORMALIZED
    assert "set_config('quote_all_identifiers', 'off', false)" in NORMALIZED
    assert "create table if not exists connected_plan_private.operations" in NORMALIZED
    assert "create table if not exists connected_plan_private.envelopes" in NORMALIZED
    assert "create table if not exists connected_chat_private" not in NORMALIZED
    assert "create or replace function public.connected_chat_" not in NORMALIZED


def test_plan_store_contains_only_ciphertext_and_opaque_bindings():
    assert "payload_ciphertext text" in NORMALIZED
    assert "wrapped_key_ciphertext text" in NORMALIZED
    assert "planning_binding_sha256 text not null" in NORMALIZED
    assert "request_binding_sha256 text not null" in NORMALIZED
    assert "session_id uuid not null" in NORMALIZED
    assert "claim_token uuid not null" in NORMALIZED
    assert "message_body" not in NORMALIZED
    assert "subject text" not in NORMALIZED
    assert "recipient" not in NORMALIZED
    assert "event_title" not in NORMALIZED
    assert "prompt text" not in NORMALIZED
    assert "model_output text" not in NORMALIZED


def test_plan_invocation_is_one_winner_and_ambiguity_fails_closed():
    assert "state = 'invoked', invocation_id = p_invocation_id" in NORMALIZED
    assert "'invoke_permitted', permitted" in NORMALIZED
    assert "operation_row.invocation_expires_at > now_at" in NORMALIZED
    assert "connected plan encrypted result requires settlement" in NORMALIZED
    assert "state = 'effect_unknown', error_code = 'model_effect_unknown'" in NORMALIZED
    assert "turn.stage = 'effect_unknown'" not in NORMALIZED
    assert "set stage = 'effect_unknown'" in NORMALIZED


def test_every_operation_mutation_revalidates_session_and_current_chat_claim():
    assert "perform connected_app_private.owner_lock_v1(p_owner_id)" in NORMALIZED
    assert "from public.sessions as session" in NORMALIZED
    assert "session_row.revoked_at is not null" in NORMALIZED
    assert "session_row.expires_at <= now_at" in NORMALIZED
    assert "job_row.claim_token <> p_claim_token" in NORMALIZED
    assert "operation_row.session_id <> p_session_id" in NORMALIZED
    assert "operation_row.claim_token <> p_claim_token" in NORMALIZED
    assert "turn_row.request_binding_sha256 <> p_request_binding_sha256" in NORMALIZED


def test_encrypted_envelope_deletion_is_a_permanent_tombstone():
    assert "record_state text not null check (record_state in ('live','deleted'))" in NORMALIZED
    assert "if envelope_row.record_state = 'deleted' then return null" in NORMALIZED
    assert "set record_state = 'deleted', commitment_key_id = null" in NORMALIZED
    assert "'ask_crump_connected_plan_envelope_delete_v1_permanent_tombstone'" in NORMALIZED


def test_service_role_only_forced_rls_and_exact_reapply_guard():
    assert NORMALIZED.count("enable row level security") >= 2
    assert NORMALIZED.count("force row level security") >= 2
    assert "to service_role" in NORMALIZED
    assert "from public, anon, authenticated" in NORMALIZED
    assert "set search_path = ''" in NORMALIZED
    assert "ef903d32f3d06fc616dea62d477cddd5" in NORMALIZED
    assert "connected plan-once target drifted; refusing repair" in NORMALIZED
    assert "using errcode = '55000'" in NORMALIZED


def test_postflight_attests_no_policies_user_triggers_rules_or_publication():
    assert "pg_catalog.pg_policy" in NORMALIZED
    assert "not trigger_row.tgisinternal" in NORMALIZED
    assert "rule_row.rulename <> '_return'" in NORMALIZED
    assert "pg_catalog.pg_publication_tables" in NORMALIZED
    assert "connected plan-once function authority drifted" in NORMALIZED
