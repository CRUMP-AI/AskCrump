from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "migrations" / "20261107190000_connected_app_control_plane.sql"
SQL = MIGRATION.read_text(encoding="utf-8")
LOWER_SQL = SQL.lower()
OAUTH_SOURCE = (ROOT / "backend" / "connected_app_oauth.py").read_text(encoding="utf-8")

EXPECTED_TABLES = {
    "action_preparations",
    "action_authority",
    "action_ledger",
    "approval_reviews",
    "approvals",
    "connections",
    "credential_cleanup_outbox",
    "credential_ref_tombstones",
    "oauth_exchange_permits",
    "oauth_flows",
    "operator_commands",
    "schedules",
    "task_grants",
}

EXPECTED_RPCS = {
    "connected_app_begin_access_v1",
    "connected_app_begin_effect_v1",
    "connected_app_begin_postobserve_v1",
    "connected_app_claim_action_v1",
    "connected_app_claim_cleanup_v1",
    "connected_app_claim_schedule_v1",
    "connected_app_consume_approval_v1",
    "connected_app_consume_credential_lease_v1",
    "connected_app_create_approval_v1",
    "connected_app_create_connection_v1",
    "connected_app_create_task_grant_v1",
    "connected_app_finish_cleanup_v1",
    "connected_app_finish_schedule_v1",
    "connected_app_get_binding_v1",
    "connected_app_oauth_consume_pending_v1",
    "connected_app_oauth_consume_permit_v1",
    "connected_app_oauth_create_pending_v1",
    "connected_app_oauth_finalize_v1",
    "connected_app_oauth_issue_permit_v1",
    "connected_app_operator_create_schedule_v1",
    "connected_app_operator_decide_approval_v1",
    "connected_app_operator_disconnect_v1",
    "connected_app_operator_get_action_v1",
    "connected_app_operator_get_approval_v1",
    "connected_app_operator_get_connection_authority_v1",
    "connected_app_operator_get_schedule_v1",
    "connected_app_operator_list_actions_v1",
    "connected_app_operator_list_approvals_v1",
    "connected_app_operator_list_connections_v1",
    "connected_app_operator_list_schedules_v1",
    "connected_app_operator_put_approval_review_v1",
    "connected_app_operator_prepare_action_v1",
    "connected_app_operator_read_action_preparation_v1",
    "connected_app_operator_read_approval_decision_v1",
    "connected_app_operator_read_disconnect_v1",
    "connected_app_operator_read_schedule_create_v1",
    "connected_app_operator_read_schedule_transition_v1",
    "connected_app_operator_transition_schedule_v1",
    "connected_app_purge_cleanup_v1",
    "connected_app_put_schedule_v1",
    "connected_app_read_action_v1",
    "connected_app_record_credential_cleanup_v1",
    "connected_app_recover_access_v1",
    "connected_app_recover_cleanup_v1",
    "connected_app_revoke_connection_v1",
    "connected_app_revoke_task_grant_v1",
    "connected_app_settle_action_v1",
}


def _table_body(name: str) -> str:
    match = re.search(
        rf"create table if not exists connected_app_private\.{re.escape(name)} \((.*?)\n\);",
        SQL,
        flags=re.DOTALL | re.IGNORECASE,
    )
    assert match, f"missing table {name}"
    return match.group(1)


def _function_body(name: str, *, schema: str = "public") -> str:
    match = re.search(
        rf"create or replace function {re.escape(schema)}\.{re.escape(name)}\(.*?\)\s*"
        r"returns .*?\n"
        r"language (?:plpgsql|sql)\n"
        r"(?:stable\n)?"
        r"security definer\n"
        r"set search_path = ''\n"
        r"as \$fn\$(.*?)\$fn\$;",
        SQL,
        flags=re.DOTALL | re.IGNORECASE,
    )
    assert match, f"missing hardened function {schema}.{name}"
    return match.group(1)


def _public_rpc_names() -> set[str]:
    return set(
        re.findall(
            r"create or replace function public\.(connected_app_[a-z0-9_]+)\(",
            LOWER_SQL,
        )
    )


def _signature_types(parameters: str) -> list[str]:
    if not parameters.strip():
        return []
    result: list[str] = []
    for parameter in parameters.split(","):
        pieces = parameter.strip().split()
        assert len(pieces) >= 2, parameter
        result.append(" ".join(pieces[1:]).lower())
    return result


def test_migration_is_local_exact_reapply_attested_and_transactional() -> None:
    assert SQL.startswith("-- ASK_CRUMP_CONNECTED_APP_CONTROL_PLANE_V1")
    assert "begin;" in LOWER_SQL
    assert re.search(r"\ncommit;\s*\n", LOWER_SQL)
    assert "using errcode = '55000'" in LOWER_SQL
    assert "fresh first apply and a bounded owner-operator behavior gate" in LOWER_SQL
    assert "3700cbb8e9d67dab331d090b26a70510" in LOWER_SQL
    assert "observed_target_fingerprint" in LOWER_SQL
    assert "partial or drifted connected-app target; refusing repair" in LOWER_SQL
    assert "create or replace function" in LOWER_SQL
    assert "create schema if not exists" in LOWER_SQL
    assert "create table if not exists" in LOWER_SQL


def test_private_table_manifest_is_exact() -> None:
    tables = set(
        re.findall(
            r"create table if not exists connected_app_private\.([a-z0-9_]+) \(",
            LOWER_SQL,
        )
    )
    assert tables == EXPECTED_TABLES
    assert (
        "create sequence if not exists connected_app_private.action_fencing_token_seq" in LOWER_SQL
    )


def test_status_domains_and_idempotency_indexes_are_pinned() -> None:
    for exact_domain in (
        "authorization_state in ('pending', 'active', 'revoked')",
        "status in ('pending', 'consumed', 'exchanged', 'completed', 'invalidated')",
        "status in ('issued', 'attempt_fenced', 'terminal', 'expired')",
        "status in ('queued', 'leased', 'completed', 'failed_permanent')",
        "status in ('claimed', 'access_granted', 'effect_possible', 'terminal')",
        "status in ('active', 'paused', 'cancelled')",
    ):
        assert exact_domain in LOWER_SQL
    for required_index in (
        "connected_app_connections_active_identity_idx",
        "connected_app_connections_active_broker_ref_idx",
        "connected_app_oauth_exchange_once_idx",
        "connected_app_oauth_permit_capability_idx",
        "connected_app_cleanup_binding_idx",
        "connected_app_cleanup_lease_id_idx",
        "connected_app_cleanup_terminal_lease_id_idx",
        "connected_app_cleanup_recovery_id_idx",
        "connected_app_approval_binding_idx",
        "connected_app_action_idempotency_idx",
        "connected_app_action_claim_idx",
        "connected_app_schedule_claim_id_idx",
        "connected_app_oauth_permit_flow_fk_idx",
        "connected_app_oauth_permit_connection_fk_idx",
        "connected_app_schedules_owner_fk_idx",
        "connected_app_schedules_connection_fk_idx",
        "connected_app_approval_reviews_owner_idx",
        "connected_app_approval_reviews_connection_idx",
        "connected_app_operator_commands_owner_idx",
        "connected_app_approval_reviews_owner_idx",
        "connected_app_approval_reviews_connection_idx",
        "connected_app_operator_commands_owner_idx",
    ):
        assert required_index in LOWER_SQL


def test_every_private_table_is_force_rls_and_has_no_direct_api_grant() -> None:
    assert "alter table connected_app_private.%i enable row level security" in LOWER_SQL
    assert "alter table connected_app_private.%i force row level security" in LOWER_SQL
    assert (
        "revoke all on table connected_app_private.%i "
        "from public, anon, authenticated, service_role"
    ) in LOWER_SQL
    assert "create policy" not in LOWER_SQL
    assert "do $private_acl$" in LOWER_SQL
    assert "where role_row.rolname <> 'postgres'" in LOWER_SQL
    assert "pg_catalog.aclexplode(" in LOWER_SQL
    assert "acl_row.grantee <> table_row.relowner" in LOWER_SQL
    assert "acl_row.grantee <> namespace_row.nspowner" in LOWER_SQL
    assert "connected-app private default privileges drifted" in LOWER_SQL


def test_storage_columns_exclude_raw_secrets_and_customer_content() -> None:
    forbidden_columns = {
        "access_token",
        "refresh_token",
        "authorization_code",
        "pkce_verifier",
        "oauth_state",
        "email",
        "email_address",
        "subject",
        "body",
        "recipient",
        "event_text",
        "message",
        "prompt",
        "content",
    }
    declared_columns: set[str] = set()
    for table in EXPECTED_TABLES:
        for line in _table_body(table).splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith(("constraint ", "--")):
                continue
            candidate = stripped.split()[0].rstrip(",").lower()
            if candidate not in {"primary", "unique", "check", "foreign"}:
                declared_columns.add(candidate)
    assert declared_columns.isdisjoint(forbidden_columns)
    assert "broker_credential_ref uuid" in LOWER_SQL
    assert "capability_sha256 text" in LOWER_SQL
    assert "state_sha256 text" in LOWER_SQL
    assert "pkce_challenge text" in LOWER_SQL
    for forbidden_parameter in (
        "p_access_token",
        "p_refresh_token",
        "p_authorization_code",
        "p_pkce_verifier",
        "p_oauth_state",
        "p_email",
        "p_subject",
        "p_body",
        "p_recipient",
        "p_content",
    ):
        assert forbidden_parameter not in LOWER_SQL


def test_cleanup_outbox_is_unlinked_bounded_and_response_loss_safe() -> None:
    body = _table_body("credential_cleanup_outbox").lower()
    for identity_column in (
        "owner_id",
        "user_id",
        "connection_id",
        "task_id",
        "turn_id",
        "action_id",
    ):
        assert not re.search(rf"^\s*{identity_column}\s", body, re.MULTILINE)
    assert "references public.users" not in body
    assert "delete_after" in body
    assert "interval '30 days'" in body
    assert "terminal_lease_id" in body
    assert "recovery_id" in body
    assert "recovery_count" in body
    assert "connected_app_cleanup_lease_id_idx" in LOWER_SQL
    assert "connected_app_cleanup_terminal_lease_id_idx" in LOWER_SQL
    assert "connected_app_purge_cleanup_v1" in EXPECTED_RPCS
    assert "connected_app_recover_cleanup_v1" in EXPECTED_RPCS
    assert "for update skip locked" in _function_body("connected_app_purge_cleanup_v1").lower()


def test_account_kind_matches_application_contract() -> None:
    for table in ("connections", "oauth_flows"):
        body = _table_body(table).lower()
        assert "account_kind in ('personal', 'work_school')" in body
        assert "'consumer'" not in body


def test_cleanup_binding_is_distinct_from_credential_digest_and_exactly_replayed() -> None:
    record = _function_body("connected_app_record_credential_cleanup_v1").lower()
    finalize = _function_body("connected_app_oauth_finalize_v1").lower()
    assert "p_cleanup_binding_sha256 !~ '^[0-9a-f]{64}$'" in record
    assert "p_cleanup_binding_sha256 is distinct from p_credential_ref_sha256" not in record
    assert "p_cleanup_binding_sha256 is distinct from p_credential_ref_sha256" not in finalize
    assert "'stale_connection'" in record
    assert 'self.reason != "stale_connection"' in OAUTH_SOURCE
    assert "cleanup.cleanup_id = p_cleanup_id" in record
    assert "cleanup.cleanup_binding_sha256 = p_cleanup_binding_sha256" in record
    assert "cleanup_row.cleanup_id <> p_cleanup_id" in record
    assert '"version": _CREDENTIAL_CLEANUP_BINDING_VERSION' in OAUTH_SOURCE
    assert "receipt.cleanup_binding_sha256 != command.binding_sha256" in OAUTH_SOURCE


def test_credential_tombstone_and_lock_prevent_cleanup_of_reused_live_authority() -> None:
    tombstone = _table_body("credential_ref_tombstones").lower()
    assert "credential_ref_sha256 text primary key" in tombstone
    assert "provider text not null" in tombstone
    assert "references" not in tombstone
    record = _function_body("connected_app_record_credential_cleanup_v1").lower()
    finalize = _function_body("connected_app_oauth_finalize_v1").lower()
    claim = _function_body("connected_app_claim_cleanup_v1").lower()
    lock_seed = "81424519024640287::bigint"
    assert lock_seed in record
    assert lock_seed in finalize
    assert lock_seed in claim
    assert "insert into connected_app_private.credential_ref_tombstones" in record
    assert "credential_retired" in finalize
    assert "duplicate_active_identity" in finalize
    assert finalize.index("duplicate_active_identity") < finalize.index(
        "update connected_app_private.connections as connection"
    )
    assert "live_connection.authorization_state = 'active'" in claim
    assert "cleanup credential tombstone is missing" in claim
    assert "set status = 'failed_permanent'" in claim


def test_duplicate_identity_is_cleaned_before_partial_unique_index_can_raise() -> None:
    finalize = _function_body("connected_app_oauth_finalize_v1").lower()
    duplicate = finalize.split("refuse a fresh connection", 1)[1].split("next_revision :=", 1)[0]
    assert "live_connection.external_account_id_sha256 = p_external_account_id_sha256" in duplicate
    assert "live_connection.id <> p_connection_id" in duplicate
    assert "connected_app_record_credential_cleanup_v1" in duplicate
    assert "return pg_catalog.jsonb_build_object" in duplicate


def test_cleanup_eighth_crash_terminalizes_without_attempt_overflow() -> None:
    claim = _function_body("connected_app_claim_cleanup_v1").lower()
    terminalize = claim.split("a worker may crash", 1)[1].split(
        "select cleanup.* into cleanup_row", 2
    )[1]
    assert "cleanup.attempts >= 8" in terminalize
    assert claim.count("set status = 'failed_permanent'") >= 2
    assert "if cleanup_row.attempts >= 8 then" in claim
    assert "set status = 'failed_permanent'" in claim
    assert "terminal_lease_id = cleanup.lease_id" in claim
    assert "cleanup.attempts < 8" in claim
    assert "attempts = cleanup.attempts + 1" in claim
    recovery = _function_body("connected_app_recover_cleanup_v1").lower()
    assert "cleanup_row.status <> 'failed_permanent'" in recovery
    assert "('queued', 'leased', 'completed', 'failed_permanent')" in recovery
    assert "set status = 'queued', attempts = 0" in recovery
    assert "recovery_count = cleanup.recovery_count + 1" in recovery
    assert "cleanup_row.delete_after <= now_at" in recovery
    assert recovery.index("cleanup_row.recovery_id = p_recovery_id") < recovery.index(
        "p_next_attempt_at < now_at"
    )


def test_expired_cleanup_lease_reclaims_the_same_row_before_scanning() -> None:
    claim = _function_body("connected_app_claim_cleanup_v1").lower()
    exact_retry = claim.split("where cleanup.lease_id = p_lease_id", 1)[1].split(
        "a worker may crash", 1
    )[0]
    assert "if found then" in exact_retry
    assert "cleanup.terminal_lease_id = p_lease_id" in exact_retry
    assert "cleanup_row.status in ('completed', 'failed_permanent')" in exact_retry
    assert "where cleanup.cleanup_id = cleanup_row.cleanup_id" in exact_retry
    assert "lease_id = p_lease_id" in exact_retry
    assert "attempts = cleanup.attempts + 1" in exact_retry
    assert "return pg_catalog.to_jsonb(cleanup_row)" in exact_retry
    assert claim.index("where cleanup.lease_id = p_lease_id") < claim.index(
        "order by cleanup.next_attempt_at"
    )


def test_oauth_expiry_transition_is_commit_safe_and_returns_terminal_row() -> None:
    consume = _function_body("connected_app_oauth_consume_permit_v1").lower()
    expired = consume.split("if now_at >= permit_row.deadline_at then", 1)[1].split("end if;", 1)[0]
    assert "set status = 'expired'" in expired
    assert "dispatch_fence_id = p_dispatch_fence_id" in expired
    assert "return pg_catalog.to_jsonb(permit_row)" in expired
    assert "raise exception" not in expired
    replay = consume.split("if permit_row.status <> 'issued' then", 1)[1].split("end if;", 1)[0]
    assert "permit_row.dispatch_fence_id = p_dispatch_fence_id" in replay
    permit = _table_body("oauth_exchange_permits").lower()
    assert "status = 'expired' and dispatch_fence_id is not null" in permit


def test_oauth_finalize_requires_exact_permit_flow_connection_and_exchange() -> None:
    finalize = _function_body("connected_app_oauth_finalize_v1").lower()
    for exact in (
        "permit_row.flow_id <> p_flow_id",
        "permit_row.connection_id <> p_connection_id",
        "permit_row.exchange_id <> p_exchange_id",
        "permit_row.exchange_binding_sha256 <> p_exchange_binding_sha256",
        "permit_row.dispatch_fence_id <> p_dispatch_fence_id",
        "permit_row.status <> 'attempt_fenced'",
    ):
        assert exact in finalize
    permit = _table_body("oauth_exchange_permits").lower()
    for terminal_binding in (
        "terminal_completion_id uuid",
        "terminal_flow_id uuid",
        "terminal_connection_id uuid",
        "terminal_broker_credential_ref uuid",
        "terminal_credential_ref_sha256 text",
        "terminal_authorization_revision bigint",
    ):
        assert terminal_binding in permit


def test_database_action_allowlist_derives_mutation_and_approval_class() -> None:
    authority = _table_body("action_authority").lower()
    assert "mutates_external_state boolean not null" in authority
    assert "approval_class text not null" in authority
    for exact_row in (
        "('mail.search', 'mail', false, 'none')",
        "('mail.send', 'mail', true, 'external_communication')",
        "('calendar.free_busy', 'calendar', false, 'none')",
        "('calendar.create', 'calendar', true, 'calendar_write')",
    ):
        assert exact_row in LOWER_SQL
    declaration = re.search(
        r"create or replace function public\.connected_app_claim_action_v1\((.*?)\)\s*returns",
        LOWER_SQL,
        flags=re.DOTALL,
    )
    assert declaration
    assert "p_mutates_external_state" not in declaration.group(1)
    claim = _function_body("connected_app_claim_action_v1").lower()
    assert "from connected_app_private.action_authority" in claim
    assert "authority_row.mutates_external_state" in claim
    assert "authority_row.approval_class" in claim
    create_approval = _function_body("connected_app_create_approval_v1").lower()
    assert "authority_row.approval_class <> p_approval_class" in create_approval
    for rpc in ("connected_app_consume_approval_v1", "connected_app_begin_effect_v1"):
        body = _function_body(rpc).lower()
        assert "authority_row.approval_class <> action_row.approval_class" in body
        assert "approval_row.approval_class <> action_row.approval_class" in body


def test_begin_effect_rechecks_exact_live_grant_and_task_revision() -> None:
    effect = _function_body("connected_app_begin_effect_v1").lower()
    assert "from connected_app_private.task_grants" in effect
    for exact in (
        "grant_row.owner_id <> action_row.owner_id",
        "grant_row.task_id <> action_row.task_id",
        "grant_row.turn_id <> action_row.turn_id",
        "grant_row.connection_id <> action_row.connection_id",
        "grant_row.authorization_revision <> action_row.authorization_revision",
        "grant_row.authorization_snapshot_sha256 <> action_row.authorization_snapshot_sha256",
        "grant_row.task_state_revision <> action_row.task_state_revision",
        "grant_row.revoked_at is not null",
        "grant_row.expires_at <= now_at",
        "not (action_row.action = any(grant_row.actions))",
    ):
        assert exact in effect


def test_read_access_and_recovery_recheck_connection_expiry() -> None:
    begin = _function_body("connected_app_begin_access_v1").lower()
    recover = _function_body("connected_app_recover_access_v1").lower()
    expiry_refusal = (
        "connection_row.authorization_expires_at is not null\n"
        "         and connection_row.authorization_expires_at <= now_at"
    )
    assert expiry_refusal in begin
    assert recover.count("connection_row.authorization_expires_at") >= 4
    replay = recover.split("if action_row.status = 'access_granted'", 1)[1].split(
        "return pg_catalog.to_jsonb(action_row)", 1
    )[0]
    assert "connection_row.authorization_expires_at is null" in replay
    assert "connection_row.authorization_expires_at > now_at" in replay
    recovery = recover.split("if action_row.status <> 'access_granted'", 1)[1].split(
        "raise exception 'action access is not recoverable'", 1
    )[0]
    assert "connection_row.authorization_expires_at <= now_at" in recovery


def test_all_account_cascade_foreign_keys_have_full_indexes() -> None:
    for required_index in (
        "connected_app_connections_owner_id_idx",
        "connected_app_oauth_flow_owner_fk_idx",
        "connected_app_oauth_flow_nonce_idx",
        "connected_app_oauth_permit_flow_fk_idx",
        "connected_app_oauth_permit_connection_fk_idx",
        "connected_app_task_grants_owner_fk_idx",
        "connected_app_task_grants_connection_fk_idx",
        "connected_app_approvals_owner_fk_idx",
        "connected_app_approvals_connection_fk_idx",
        "connected_app_action_idempotency_idx",
        "connected_app_action_connection_fk_idx",
        "connected_app_action_grant_idx",
        "connected_app_action_preparations_owner_idx",
        "connected_app_action_preparations_connection_idx",
        "connected_app_action_preparations_expiry_idx",
        "connected_app_schedules_owner_fk_idx",
        "connected_app_schedules_connection_fk_idx",
    ):
        assert required_index in LOWER_SQL


def test_public_rpc_manifest_and_hardening_are_exact() -> None:
    assert _public_rpc_names() == EXPECTED_RPCS
    assert LOWER_SQL.count("create or replace function public.connected_app_") == len(EXPECTED_RPCS)
    manifest = re.search(
        r"expected_functions constant text\[\] := array\[(.*?)\];",
        LOWER_SQL,
        flags=re.DOTALL,
    )
    assert manifest
    postflight_names = re.findall(r"'(connected_app_[a-z0-9_]+)'", manifest.group(1))
    assert postflight_names == sorted(EXPECTED_RPCS)
    for rpc in EXPECTED_RPCS:
        _function_body(rpc)
    assert "grant execute on function ' || signature || ' to service_role'" in LOWER_SQL
    rpc_acl = LOWER_SQL.split("do $rpc_acl$", 1)[1].split("$rpc_acl$;", 1)[0]
    assert "where role_row.rolname <> 'postgres'" in rpc_acl
    assert "pg_catalog.quote_ident(role_name)" in rpc_acl
    assert "function_row.proconfig is distinct from array['search_path=\"\"']::text[]" in LOWER_SQL
    assert "acl_row.grantee <> function_row.proowner" in LOWER_SQL
    assert "where role_row.rolname = 'service_role'" in LOWER_SQL


def test_every_function_comment_signature_matches_its_declaration() -> None:
    declarations = {
        (schema.lower(), name.lower()): _signature_types(parameters)
        for schema, name, parameters in re.findall(
            r"create or replace function ([a-z0-9_]+)\.([a-z0-9_]+)\((.*?)\)\s*returns",
            SQL,
            flags=re.DOTALL | re.IGNORECASE,
        )
    }
    comments = {
        (schema.lower(), name.lower()): [
            item.strip().lower() for item in parameters.split(",") if item.strip()
        ]
        for schema, name, parameters in re.findall(
            r"comment on function ([a-z0-9_]+)\.([a-z0-9_]+)\((.*?)\)\s+is",
            SQL,
            flags=re.DOTALL | re.IGNORECASE,
        )
    }
    assert comments.keys() == declarations.keys()
    assert comments == declarations


def test_internal_functions_are_not_callable_by_api_roles() -> None:
    _function_body("owner_lock_v1", schema="connected_app_private")
    _function_body("enqueue_owner_cleanup_before_delete_v1", schema="connected_app_private")
    for helper in (
        "connection_view_v1",
        "schedule_view_v1",
        "action_view_v1",
        "action_preparation_view_v1",
        "approval_view_v1",
    ):
        _function_body(helper, schema="connected_app_private")
    assert (
        "revoke all on function connected_app_private.owner_lock_v1(uuid)\n"
        "  from public, anon, authenticated, service_role"
    ) in LOWER_SQL
    assert "connected-app private function authority drifted" in LOWER_SQL


def test_operator_surface_is_owner_scoped_content_free_and_exactly_replayable() -> None:
    reviews = _table_body("approval_reviews").lower()
    commands = _table_body("operator_commands").lower()
    assert "review_payload_ref uuid not null" in reviews
    assert "decision_session_binding_sha256" in reviews
    assert "subject_id uuid not null" in commands
    assert "command_binding_sha256 text not null" in commands
    for rpc in (
        "connected_app_operator_disconnect_v1",
        "connected_app_operator_create_schedule_v1",
        "connected_app_operator_transition_schedule_v1",
        "connected_app_operator_decide_approval_v1",
    ):
        body = _function_body(rpc).lower()
        assert "owner_lock_v1(p_owner_id)" in body
    disconnect = _function_body("connected_app_operator_disconnect_v1").lower()
    assert "connected_app_revoke_connection_v1" in disconnect
    assert "connection_row.credential_ref_sha256,\n    p_command_binding_sha256" in disconnect
    assert "set revoked_at = now_at" in disconnect
    assert "set status = 'cancelled', next_run_at = null" in disconnect
    decision = _function_body("connected_app_operator_decide_approval_v1").lower()
    assert "connected_app_create_approval_v1" in decision
    assert "review_row.status <> 'pending'" in decision
    assert "review_row.expires_at <= now_at" in decision


def test_action_preparation_is_atomic_content_free_and_never_executes() -> None:
    preparations = _table_body("action_preparations").lower()
    for required in (
        "request_id uuid primary key",
        "grant_id uuid not null unique",
        "action_id uuid not null unique",
        "payload_id uuid not null",
        "payload_reference_binding_sha256 text not null",
        "parameters_sha256 text not null",
        "grant_actions_sha256 text not null",
        "status text not null",
        "preview_payload_id uuid",
        "preview_sha256 text",
    ):
        assert required in preparations
    for forbidden in (
        "target_binding",
        "request_target",
        "subject text",
        "body text",
        "recipient",
        "calendar_title",
        "session_id uuid",
    ):
        assert forbidden not in preparations

    prepare = _function_body("connected_app_operator_prepare_action_v1").lower()
    for required in (
        "owner_lock_v1(p_owner_id)",
        "from public.sessions as session",
        "session.id = p_session_id and session.user_id = p_owner_id",
        "session_row.revoked_at is not null",
        "session_row.expires_at <= now_at",
        "authorization_state <> 'active'",
        "connection_row.authorization_revision <> p_authorization_revision",
        "connection_row.authorization_snapshot_sha256\n        <> p_authorization_snapshot_sha256",
        "connection_row.granted_actions_sha256 <> p_granted_actions_sha256",
        "connection_row.granted_scopes_sha256 <> p_granted_scopes_sha256",
        "not (p_action = any(connection_row.granted_actions))",
        "insert into connected_app_private.task_grants",
        "insert into connected_app_private.action_preparations",
        "insert into connected_app_private.approval_reviews",
        "action_preparation_view_v1(\n    p_owner_id, p_request_id",
    ):
        assert required in prepare
    for forbidden in (
        "insert into connected_app_private.action_ledger",
        "connected_app_claim_action_v1",
        "connected_app_begin_effect_v1",
        "target_binding_sha256",
    ):
        assert forbidden not in prepare
    assert (
        prepare.index("owner_lock_v1(p_owner_id)")
        < prepare.index("from public.sessions as session")
        < prepare.index("from connected_app_private.connections as connection")
    )

    readback = _function_body("connected_app_operator_read_action_preparation_v1").lower()
    assert "action_preparation_view_v1(\n    p_owner_id, p_request_id" in readback
    assert "owner_lock_v1" not in readback


def test_payload_and_preview_hashes_are_keyed_opaque_commitments() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    assert (
        sql.count(
            "ASK_CRUMP_CONNECTED_APP_KEYED_HMAC_PAYLOAD_COMMITMENT_V1_NOT_PLAINTEXT_REQUEST_DIGEST"
        )
        == 5
    )
    assert (
        "ASK_CRUMP_CONNECTED_APP_KEYED_HMAC_PREVIEW_COMMITMENT_V1_NOT_PREDICTABLE_CONTENT_DIGEST"
        in sql
    )
    action_view = _function_body("action_view_v1", schema="connected_app_private").lower()
    assert "order by ledger.updated_at desc, ledger.operation_id desc" in action_view
    assert "public action projection binding drifted" in action_view


def test_owner_lock_and_database_owned_revision_and_fence_are_present() -> None:
    assert "pg_advisory_xact_lock" in LOWER_SQL
    assert "hashtextextended(p_owner_id::text" in LOWER_SQL
    finalize = _function_body("connected_app_oauth_finalize_v1").lower()
    assert "next_revision := connection_row.authorization_revision + 1" in finalize
    assert "set authorization_revision = next_revision" in finalize
    assert "set authorization_revision = p_" not in finalize
    claim = _function_body("connected_app_claim_action_v1").lower()
    assert "action_fencing_token_seq" in claim
    assert "fencing_token = pg_catalog.nextval" in claim


def test_oauth_flow_is_prehashed_fenced_and_terminal_replay_readable() -> None:
    flow = _table_body("oauth_flows").lower()
    permit = _table_body("oauth_exchange_permits").lower()
    assert "state_sha256" in flow
    assert "current_flow_nonce_sha256" in flow
    assert "session_binding_sha256" in flow
    assert "flow_binding_sha256" in flow
    assert "pkce_challenge" in flow
    assert "capability_sha256" in permit
    assert "dispatch_fence_id" in permit
    consume = _function_body("connected_app_oauth_consume_permit_v1").lower()
    assert "status = 'attempt_fenced'" in consume
    assert "status = 'exchanged'" in consume
    assert "permit_row.dispatch_fence_id = p_dispatch_fence_id" in consume
    finalize = _function_body("connected_app_oauth_finalize_v1").lower()
    assert "flow_row.status = 'completed'" in finalize
    assert "permit_row.status = 'terminal'" in finalize
    assert "completion_id" in finalize
    assert "completion_broker_credential_ref" in finalize
    assert "completion_credential_ref_sha256" in finalize
    assert "completion_authorization_revision" in finalize
    assert "terminal_flow_id = p_flow_id" in finalize
    assert "terminal_connection_id = p_connection_id" in finalize
    assert "terminal_broker_credential_ref = p_broker_credential_ref" in finalize
    assert "current_live_credential" in finalize
    assert finalize.index("current_live_credential") < finalize.index(
        "connected_app_record_credential_cleanup_v1"
    )
    assert (
        "connection_row.current_flow_nonce_sha256 = p_current_flow_nonce_sha256"
        not in (
            finalize.split("-- terminal replay", 1)[-1].split("if connection_row.id is null", 1)[0]
        )
    )
    assert "snapshot_sha256 := p_completion_binding_sha256" in finalize
    assert "digest(" not in LOWER_SQL
    assert "public.digest" not in LOWER_SQL


def test_task_grant_and_approval_are_exact_live_one_use_authority() -> None:
    grants = _table_body("task_grants").lower()
    approvals = _table_body("approvals").lower()
    assert "authorization_revision" in grants
    assert "authorization_snapshot_sha256" in grants
    assert "task_state_revision" in grants
    assert "revoked_at" in grants
    assert "consumed_at" in approvals
    assert "consumed_by_operation_id" in approvals
    consume = _function_body("connected_app_consume_approval_v1").lower()
    for exact_field in (
        "action_id",
        "task_id",
        "turn_id",
        "connection_id",
        "parameters_sha256",
        "resource_version_sha256",
        "authorization_revision",
        "authorization_snapshot_sha256",
    ):
        assert exact_field in consume
    assert "approval already consumed by another operation" in consume
    assert "connected_app_revoke_task_grant_v1" in EXPECTED_RPCS
    revoke = _function_body("connected_app_revoke_task_grant_v1").lower()
    assert "p_task_state_revision <= grant_row.task_state_revision" in revoke
    assert "set revoked_at = now_at, task_state_revision = p_task_state_revision" in revoke
    assert "set status = 'paused'" in revoke


def test_exact_action_set_is_durable_across_oauth_grant_and_execution_fences() -> None:
    connections = _table_body("connections").lower()
    flows = _table_body("oauth_flows").lower()
    grants = _table_body("task_grants").lower()
    ledger = _table_body("action_ledger").lower()
    for required in ("granted_actions text[]", "granted_actions_sha256 text"):
        assert required in connections
    for required in (
        "actions text[]",
        "actions_sha256 text",
        "completion_granted_actions text[]",
        "completion_granted_actions_sha256 text",
    ):
        assert required in flows
    assert "actions_sha256 text not null" in grants
    assert "granted_actions_sha256 text not null" in ledger

    pending = _function_body("connected_app_oauth_create_pending_v1").lower()
    assert "existing_row.actions is distinct from p_actions" in pending
    assert "existing_row.actions_sha256 <> p_actions_sha256" in pending
    finalize = _function_body("connected_app_oauth_finalize_v1").lower()
    assert "granted_actions = flow_row.actions" in finalize
    assert "granted_actions_sha256 = flow_row.actions_sha256" in finalize
    assert "completion_granted_actions = flow_row.actions" in finalize
    assert "completion_granted_actions_sha256 = flow_row.actions_sha256" in finalize

    create_grant = _function_body("connected_app_create_task_grant_v1").lower()
    assert "grant_row.actions is distinct from p_actions" in create_grant
    assert "grant_row.actions_sha256 <> p_actions_sha256" in create_grant
    assert "requested.action_name = any(connection_row.granted_actions)" in create_grant

    for rpc in (
        "connected_app_claim_action_v1",
        "connected_app_begin_access_v1",
        "connected_app_recover_access_v1",
        "connected_app_begin_effect_v1",
        "connected_app_begin_postobserve_v1",
    ):
        body = _function_body(rpc).lower()
        assert "granted_actions_sha256" in body
        assert "any(connection_row.granted_actions)" in body


def test_phase_credentials_are_exact_one_use_before_provider_boundary() -> None:
    ledger = _table_body("action_ledger").lower()
    for required in (
        "read_credential_expires_at timestamptz",
        "read_consumed_at timestamptz",
        "preobserve_credential_expires_at timestamptz",
        "preobserve_consumed_at timestamptz",
        "effect_credential_expires_at timestamptz",
        "effect_consumed_at timestamptz",
        "postobserve_consumed_at timestamptz",
    ):
        assert required in ledger

    consume = _function_body("connected_app_consume_credential_lease_v1").lower()
    for exact_binding in (
        "action_row.connection_id <> p_connection_id",
        "action_row.action_id <> p_action_id",
        "action_row.action <> p_action",
        "action_row.claim_id <> p_claim_id",
        "action_row.fencing_token <> p_fencing_token",
        "action_row.authorization_snapshot_sha256 <> p_authorization_snapshot_sha256",
        "action_row.granted_actions_sha256 <> p_granted_actions_sha256",
        "action_row.granted_scopes_sha256 <> p_granted_scopes_sha256",
        "action_row.authority_sha256 <> p_authority_sha256",
        "action_row.task_state_revision <> p_task_state_revision",
        "expected_nonce is distinct from p_use_nonce",
        "expected_expires_at is distinct from p_credential_expires_at",
    ):
        assert exact_binding in consume
    assert "credential lease already consumed" in consume
    assert "read_consumed_at = now_at" in consume
    assert "preobserve_consumed_at = now_at" in consume
    assert "effect_consumed_at = now_at" in consume
    assert "postobserve_consumed_at = now_at" in consume
    assert "not (p_action = any(connection_row.granted_actions))" in consume

    effect = _function_body("connected_app_begin_effect_v1").lower()
    postobserve = _function_body("connected_app_begin_postobserve_v1").lower()
    settle = _function_body("connected_app_settle_action_v1").lower()
    assert "action_row.preobserve_consumed_at is null" in effect
    assert "action_row.effect_consumed_at is null" in postobserve
    assert "action_row.read_consumed_at is null" in settle
    assert "action_row.preobserve_consumed_at is null" in settle
    assert "action_row.effect_consumed_at is null" in settle
    assert "action_row.postobserve_consumed_at is not null" in settle


def test_action_ledger_has_distinct_phases_and_no_effect_retry_path() -> None:
    ledger = _table_body("action_ledger").lower()
    for required in (
        "status text",
        "fencing_token bigint",
        "access_phase text",
        "read_use_nonce uuid",
        "preobserve_use_nonce uuid",
        "effect_use_nonce uuid",
        "postobserve_use_nonce uuid",
        "terminal_binding_sha256 text",
        "idempotency_key_sha256 text",
    ):
        assert required in ledger
    assert "'claimed', 'access_granted', 'effect_possible', 'terminal'" in ledger
    assert "'read', 'preobserve'" in ledger
    recover = _function_body("connected_app_recover_access_v1").lower()
    assert "action_row.effect_use_nonce is not null" in recover
    assert "never_after_effect" in LOWER_SQL
    effect = _function_body("connected_app_begin_effect_v1").lower()
    assert "effect already began with another nonce" in effect
    assert "never_autoretry" in LOWER_SQL
    postobserve = _function_body("connected_app_begin_postobserve_v1").lower()
    assert "execution_deadline + interval '24 hours'" in postobserve
    assert "postobserve_expires_at > now_at" in postobserve
    assert "another live nonce" in postobserve
    settle = _function_body("connected_app_settle_action_v1").lower()
    assert "action phase receipt mismatch" in settle
    assert "read_use_nonce is distinct from p_access_use_nonce" in settle
    assert "preobserve_use_nonce is distinct from p_access_use_nonce" in settle
    assert "p_postobserve_impossible" in settle
    assert "p_terminal_outcome <> 'ambiguous'" in settle
    assert "action_row.postobserve_use_nonce is null" in settle
    assert "p_postobserve_use_nonce is null" in settle
    assert "action_row.postobserve_use_nonce = p_postobserve_use_nonce" in settle
    assert "postobserve_impossible = p_postobserve_impossible" in settle
    assert "'mail.create_draft', 'mail.send', 'mail.reply', 'calendar.create'" in settle
    assert "p_provider_request_id_sha256 is not null" in settle
    assert "p_provider_resource_id_sha256 is not null" in settle


def test_action_readback_and_claim_recovery_are_idempotency_bound() -> None:
    claim = _function_body("connected_app_claim_action_v1").lower()
    assert "idempotency_key_sha256 = p_idempotency_key_sha256" in claim
    assert "action idempotency replay drifted" in claim
    assert "action_row.status = 'claimed'" in claim
    assert "action_row.lease_expires_at <= now_at" in claim
    readback = _function_body("connected_app_read_action_v1").lower()
    assert "ledger.operation_id = p_operation_id" in readback
    assert "ledger.idempotency_key_sha256 = p_idempotency_key_sha256" in readback
    exact_lookup = readback.split("select ledger.* into action_row", 1)[1].split("if not found", 1)[
        0
    ]
    assert (
        "ledger.operation_id = p_operation_id\n    and ledger.idempotency_key_sha256"
        in exact_lookup
    )
    assert "action readback keys refer to different rows" in readback


def test_account_delete_enqueues_cleanup_before_cascade() -> None:
    trigger = _function_body(
        "enqueue_owner_cleanup_before_delete_v1", schema="connected_app_private"
    ).lower()
    assert "where connection.owner_id = old.id" in trigger
    assert "connection.broker_credential_ref is not null" in trigger
    assert "'owner_deleted'" in trigger
    assert "return old" in trigger
    assert "before delete on public.users" in LOWER_SQL
    assert "connected_app_owner_delete_cleanup_v1_explicit_attested_trigger" in LOWER_SQL
    assert "cleanup_binding" in trigger
    assert "old.id::text" not in trigger
    assert trigger.index("owner_lock_v1(old.id)") < trigger.index("for connection_row in")
    assert "order by connection.id\n    for update" in trigger


def test_account_linked_rows_have_cascade_paths_but_cleanup_does_not() -> None:
    assert (
        _table_body("connections").lower().count("references public.users(id) on delete cascade")
        == 1
    )
    for table in ("oauth_flows", "task_grants", "approvals", "action_ledger", "schedules"):
        assert "references public.users(id) on delete cascade" in _table_body(table).lower()
    assert "on delete cascade" in _table_body("oauth_exchange_permits").lower()
    assert "references" not in _table_body("credential_cleanup_outbox").lower()


def test_scheduler_is_content_free_bounded_and_response_loss_readable() -> None:
    schedules = _table_body("schedules").lower()
    assert "action_template_ref uuid" in schedules
    assert "parameters_sha256 text" in schedules
    assert "quiet_start_minute" in schedules
    assert "quiet_end_minute" in schedules
    assert "requires_approval_every_run boolean not null" in schedules
    assert "claim_id uuid" in schedules
    assert "completed_claim_id uuid" in schedules
    claim = _function_body("connected_app_claim_schedule_v1").lower()
    assert "where schedule.claim_id = p_claim_id" in claim
    assert "p_lease_seconds not between 30 and 300" in claim
    assert "pg_catalog.timezone(schedule_row.time_zone, now_at)" in claim
    assert "limit 32" in claim
    assert "for update skip locked" in claim
    bounded_scan = claim.split("for candidate in", 1)[1]
    assert "pg_catalog.pg_try_advisory_xact_lock" in bounded_scan
    assert "connected_app_private.owner_lock_v1(candidate.owner_id)" not in bounded_scan
    assert bounded_scan.index("pg_catalog.pg_try_advisory_xact_lock") < bounded_scan.index(
        "for update skip locked"
    )
    assert "set status = 'paused'" in claim
    assert "schedule_row.requires_approval_every_run" in claim
    assert "schedule.next_run_at" in claim
    assert "continue;" in claim
    finish = _function_body("connected_app_finish_schedule_v1").lower()
    assert "schedule_row.completed_claim_id = p_claim_id" in finish
    put = _function_body("connected_app_put_schedule_v1").lower()
    assert "p_requires_approval_every_run is null" in put
    assert "and not p_requires_approval_every_run" in put
    assert "schedule_row.requires_approval_every_run <> p_requires_approval_every_run" in put
    assert "requires_approval_every_run, status, next_run_at" in put


def test_postflight_refuses_catalog_publication_and_hidden_object_drift() -> None:
    assert "connected-app table manifest drifted at postflight" in LOWER_SQL
    assert "connected-app public rpc manifest drifted at postflight" in LOWER_SQL
    assert "connected-app hidden policy/trigger/rule drifted" in LOWER_SQL
    assert "pg_catalog.pg_policy" in LOWER_SQL
    assert "pg_catalog.pg_trigger" in LOWER_SQL
    assert "pg_catalog.pg_rewrite" in LOWER_SQL
    assert "pg_catalog.pg_publication" in LOWER_SQL
    assert "pg_catalog.pg_publication_rel" in LOWER_SQL
    assert "connected-app private state is publication-exposed" in LOWER_SQL
    assert "connected-app action authority allowlist drifted" in LOWER_SQL


def test_acl_hardening_rejects_every_unexpected_direct_grantee() -> None:
    private_acl = LOWER_SQL.split("do $private_acl$", 1)[1].split("$private_acl$;", 1)[0]
    rpc_acl = LOWER_SQL.split("do $rpc_acl$", 1)[1].split("$rpc_acl$;", 1)[0]
    postflight = LOWER_SQL.split("do $postflight$", 1)[1].split("$postflight$;", 1)[0]
    for block in (private_acl, rpc_acl):
        assert "from pg_catalog.pg_roles as role_row" in block
        assert "where role_row.rolname <> 'postgres'" in block
        assert "pg_catalog.quote_ident(role_name)" in block
    assert postflight.count("pg_catalog.aclexplode(") >= 5
    assert "acl_row.grantee <> table_row.relowner" in postflight
    assert "acl_row.grantee <> function_row.proowner" in postflight
    assert "acl_row.grantee <> default_acl.defaclrole" in postflight
    assert "connected-app rpc authority drifted" in postflight


def test_sql_envelopes_are_balanced_for_static_review() -> None:
    assert LOWER_SQL.count("create or replace function ") == LOWER_SQL.count("\n$fn$;")
    for tag in ("preflight", "rls", "private_acl", "rpc_acl", "postflight"):
        assert LOWER_SQL.count(f"${tag}$") == 2
    assert LOWER_SQL.count("begin;") >= 1
    assert LOWER_SQL.count("commit;") == 1
    assert not re.search(r"\b(apply_migration|supabase db push)\b", LOWER_SQL)
