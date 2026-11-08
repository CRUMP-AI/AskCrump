from pathlib import Path
import re


MIGRATION = Path(
    "migrations/20261107233000_connected_app_encrypted_read_results.sql"
).read_text(encoding="utf-8")
LOWER = MIGRATION.lower()


def _function_body(name: str) -> str:
    match = re.search(
        rf"create or replace function public\.{re.escape(name)}\((.*?)\)\s*"
        rf"returns jsonb.*?as \$fn\$(.*?)\$fn\$;",
        MIGRATION,
        re.IGNORECASE | re.DOTALL,
    )
    assert match is not None
    return match.group(2).lower()


def test_migration_is_forward_only_with_exact_predecessor_and_target_guards() -> None:
    assert "9c752ba79dc1b9b695d89f57fc17078d" in MIGRATION
    assert "98e077727ddee102f6effd4e78e11b78" in MIGRATION
    assert "target_relations = 0 and target_functions = 0" in LOWER
    assert "target_relations = 1 and target_functions = 2" in LOWER
    assert "partial or mixed" in LOWER
    assert "errcode = '55000'" in LOWER
    assert "drop table" not in LOWER
    assert "drop function" not in LOWER


def test_private_result_table_stores_only_opaque_reference_and_content_free_bindings() -> None:
    table = re.search(
        r"create table if not exists connected_app_private\.read_results \((.*?)\n\);",
        MIGRATION,
        re.IGNORECASE | re.DOTALL,
    )
    assert table is not None
    body = table.group(1).lower()
    for required in (
        "completion_id",
        "operation_id",
        "owner_id",
        "connection_id",
        "result_payload_id",
        "result_payload_sha256",
        "result_reference_binding_sha256",
        "authority_sha256",
        "idempotency_key_sha256",
        "claim_id",
        "fencing_token",
        "read_use_nonce",
    ):
        assert required in body
    for forbidden in (
        "subject",
        "body_text",
        "description",
        "location",
        "recipient",
        "attendee",
        "payload_ciphertext",
        "provider_resource_id",
    ):
        assert forbidden not in body
    assert "references public.users(id) on delete cascade" in body
    assert "references connected_app_private.payload_envelopes(payload_id) on delete cascade" in body


def test_settlement_is_one_fenced_transaction_after_one_use_read_consumption() -> None:
    body = _function_body("connected_app_settle_read_result_v1")
    assert "perform connected_app_private.owner_lock_v1(p_owner_id)" in body
    assert "for update" in body
    assert "action_row.status <> 'access_granted'" in body
    assert "action_row.access_phase <> 'read'" in body
    assert "action_row.read_consumed_at is null" in body
    assert "action_row.claim_id <> p_claim_id" in body
    assert "action_row.fencing_token <> p_fencing_token" in body
    assert "action_row.read_use_nonce is distinct from p_read_use_nonce" in body
    assert "insert into connected_app_private.read_results" in body
    assert "update connected_app_private.action_ledger" in body
    assert "set status = 'terminal', terminal_outcome = 'read'" in body
    assert body.index("insert into connected_app_private.read_results") < body.index(
        "update connected_app_private.action_ledger"
    )


def test_response_loss_readback_is_exact_and_effect_unknown_is_visible() -> None:
    body = _function_body("connected_app_read_read_result_v1")
    assert "p_owner_id" in body
    assert "p_operation_id" in body
    assert "p_completion_id" in body
    assert "p_idempotency_key_sha256" in body
    assert "'status', 'terminal'" in body
    assert "'status', 'not_consumed'" in body
    assert "then 'not_consumed' else 'consumed_unknown'" in body
    assert "payload_ciphertext" not in body
    assert "wrapped_key" not in body


def test_private_relation_and_rpcs_are_service_role_only_and_unpublished() -> None:
    assert "enable row level security" in LOWER
    assert "force row level security" in LOWER
    assert "revoke all on table connected_app_private.read_results from service_role" in LOWER
    for name in (
        "connected_app_settle_read_result_v1",
        "connected_app_read_read_result_v1",
    ):
        assert f"grant execute on function public.{name}" in LOWER
    assert "from anon" in LOWER
    assert "from authenticated" in LOWER
    assert "pg_publication" in LOWER
    assert "pg_publication_rel" in LOWER
    assert "pg_policy" in LOWER
    assert "pg_trigger" in LOWER
    assert "pg_rewrite" in LOWER


def test_only_five_read_actions_are_accepted() -> None:
    for action in (
        "mail.search",
        "mail.get",
        "calendar.list",
        "calendar.get",
        "calendar.free_busy",
    ):
        assert action in MIGRATION
    settlement = _function_body("connected_app_settle_read_result_v1")
    for write in (
        "mail.send",
        "mail.reply",
        "mail.create_draft",
        "calendar.create",
        "calendar.update",
        "calendar.cancel",
    ):
        assert write not in settlement
