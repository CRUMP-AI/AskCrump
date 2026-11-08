from __future__ import annotations

import hashlib
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = (
    ROOT
    / "migrations"
    / "20261108068500_connected_multi_step_continuation_queue.sql"
)


def _sql() -> str:
    return MIGRATION.read_text(encoding="utf-8")


def test_continuation_migration_is_exactly_pinned_and_immutable() -> None:
    sql = _sql()

    assert "755dbb418bb4cef4d102f1587ee1c99a" in sql
    assert sql.count("1fac1595981f5cd703aaabbc3d13c571") == 2
    assert "continuation predecessor drifted" in sql
    assert "continuation target drifted" in sql
    assert "continuation postflight drifted" in sql
    assert hashlib.sha256(MIGRATION.read_bytes()).hexdigest().upper() == (
        "2C9B0C082E0121EE430824CFC50E1A1AA6EAD50B7579CD37A35D3247E39079D3"
    )


def test_continuation_queue_is_private_content_free_forced_rls() -> None:
    sql = _sql()
    compact = "".join(sql.split()).casefold()

    for table in ("jobs", "claims"):
        assert f"create table if not exists connected_loop_continuation_private.{table}" in sql
        assert (
            f"altertableconnected_loop_continuation_private.{table}"
            "enablerowlevelsecurity"
        ) in compact
        assert (
            f"altertableconnected_loop_continuation_private.{table}"
            "forcerowlevelsecurity"
        ) in compact
    for forbidden in (
        "email_body",
        "body_text",
        "subject_text",
        "recipient_address",
        "attendee_address",
        "access_token",
        "refresh_token",
        "provider_payload",
    ):
        assert forbidden not in sql.casefold()
    assert "on delete cascade" in sql
    assert "publication exposure refused" in sql


def test_continuation_claims_are_revision_deadline_and_owner_fenced() -> None:
    sql = _sql()

    assert "perform connected_app_private.owner_lock_v1(p_owner_id)" in sql
    assert "loop_row.task_state_revision<>p_expected_revision" in sql
    assert "claim_row.claim_expires_at<=now_at" in sql
    assert "current_claim_request_id<>p_claim_request_id" in sql
    assert "status='superseded'" in sql
    assert "unique(loop_id,generation)" in sql
    assert "claim identity collision" in sql
    assert "settlement replay drifted" in sql


def test_only_database_proven_consumed_successful_write_is_runnable() -> None:
    sql = _sql()

    for proof in (
        "review_row.status='approved'",
        "approval_row.consumed_at is not null",
        "approval_row.consumed_by_operation_id=step_row.action_id",
        "ledger_row.status='terminal'",
        "ledger_row.terminal_outcome='succeeded'",
        "ledger_row.terminal_binding_sha256 is not null",
    ):
        assert proof in sql
    assert "loop_row.status='waiting_approval'" in sql
    assert "'kind',case when loop_row.status='active' then 'active'" in sql


def test_public_continuation_rpcs_are_service_role_only() -> None:
    sql = _sql()
    compact = "".join(sql.split()).casefold()
    public_functions = re.findall(
        r"create or replace function public\."
        r"(connected_multi_step_continuation_[a-z0-9_]+)",
        sql,
    )

    assert len(public_functions) == 8
    assert len(set(public_functions)) == 8
    assert "security definer set search_path=''" in sql
    assert compact.count("toservice_role") >= 8
    assert compact.count("frompublic,anon,authenticated") >= 8
    assert "connected_multi_step_continuation_instruction_v1" in public_functions
    assert "connected_multi_step_continuation_fail_v1" in public_functions
