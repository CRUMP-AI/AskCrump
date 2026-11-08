from __future__ import annotations

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = (
    ROOT / "migrations" / "20261108066000_connected_schedule_occurrence_approval.sql"
)


def _sql() -> str:
    return MIGRATION.read_text(encoding="utf-8")


def test_occurrence_approval_migration_pins_exact_predecessors_and_target():
    sql = _sql()

    assert "04209d99c31c8d1d01943c424ea4da74" in sql
    assert "52629ef0c6f07fe7ac8eb4292bfc59aa" in sql
    target = re.findall(
        r"existing_target_fingerprint<>'([0-9a-f]{32})'", sql
    )
    assert len(target) == 1
    assert sql.count(target[0]) == 2
    assert "connected schedule approval predecessor drifted" in sql
    assert "connected schedule approval existing target drifted" in sql
    assert "connected schedule approval postflight drifted" in sql


def test_occurrence_ledger_is_private_content_free_and_owner_scoped():
    sql = _sql()
    compact = "".join(sql.split())

    assert "create table if not exists connected_schedule_private.occurrences" in sql
    assert "enable row level security" in sql
    assert "force row level security" in sql
    assert "ASK_CRUMP_CONNECTED_SCHEDULE_OCCURRENCES_V1_CONTENT_FREE_FRESH_APPROVAL" in sql
    assert "ASK_CRUMP_KEYED_HMAC_PAYLOAD_COMMITMENT_NOT_PLAINTEXT" in sql
    assert (
        "createorreplacefunctionpublic.connected_app_read_schedule_approval_v1("
        "p_owner_iduuid,p_occurrence_iduuid)"
    ) in compact
    assert "whereoccurrence.owner_id=p_owner_id" in compact
    assert "connected_app_operator_list_approvals_v1" in sql
    assert "connected_app_operator_get_approval_v1" in sql
    for forbidden_column in (
        "email_body",
        "body_text",
        "subject_text",
        "recipient_address",
        "attendee_address",
        "event_description",
        "access_token",
        "refresh_token",
    ):
        assert forbidden_column not in sql.casefold()


def test_every_write_occurrence_is_exactly_bound_and_fails_closed():
    sql = _sql()

    for binding in (
        "occurrence_row.owner_id<>p_owner_id",
        "occurrence_row.schedule_id<>p_schedule_id",
        "occurrence_row.current_claim_id<>p_claim_id",
        "occurrence_row.action_id<>p_action_id",
        "occurrence_row.approval_id<>p_approval_id",
        "occurrence_row.parameters_sha256<>p_parameters_sha256",
        "occurrence_row.authorization_snapshot_sha256<>",
        "connection_row.authorization_state<>'active'",
        "connection_row.authorization_expires_at<=p_expires_at",
        "schedule_row.status<>'active'",
        "occurrence_row.terminal_at is not null",
    ):
        assert binding in sql
    assert "p_expires_at>p_created_at+interval '15 minutes'" in sql
    assert "schedule approval occurrence is no longer current" in sql
    assert "connected_schedule_one_open_occurrence_idx" in sql
    assert "action_id uuid not null unique" in sql
    assert "approval_id uuid not null unique" in sql


def test_schedule_approval_functions_are_service_role_only_and_unpublished():
    sql = _sql()
    compact = "".join(sql.split())

    assert "puballtables" in sql
    assert "pg_publication_namespace" in sql
    assert "pg_publication_rel" in sql
    assert "grant execute on function %s to service_role" in sql
    assert (
        "revokeallonfunction%sfrompublic,anon,authenticated,service_role"
        in compact
    )
    assert "iffunction_row.schema_name='public'then" in compact
    assert "security definer set search_path=''" in sql
