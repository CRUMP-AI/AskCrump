from __future__ import annotations

import hashlib
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "migrations" / "20261108067000_connected_multi_step_operator_loop.sql"


def _sql() -> str:
    return MIGRATION.read_text(encoding="utf-8")


def test_multi_step_migration_is_exactly_pinned_and_immutable():
    sql = _sql()

    assert "fd7caa733d4112ade452de4755f39a45" in sql
    assert sql.count("a63bd463531f048bac9024b17d5823c1") == 4
    assert "connected multi-step predecessor drifted" in sql
    assert "connected multi-step existing target drifted" in sql
    assert "connected multi-step target drifted" in sql
    assert hashlib.sha256(MIGRATION.read_bytes()).hexdigest().upper() == (
        "F52DCE5AB7EFAA3DBBD3727F4A394FF8BBD88745B99024B32287CC4CD0D5BB1D"
    )


def test_multi_step_private_state_is_forced_rls_content_free_and_cascades():
    sql = _sql()
    compact = "".join(sql.split()).casefold()

    for table in ("loops", "steps", "envelopes"):
        assert f"create table if not exists connected_loop_private.{table}" in sql
        assert f"altertableconnected_loop_private.{table}enablerowlevelsecurity" in compact
        assert f"altertableconnected_loop_private.{table}forcerowlevelsecurity" in compact
    assert sql.count("owner_id uuid not null references public.users(id) on delete cascade") == 2
    assert "loop_id uuid not null references connected_loop_private.loops(loop_id) on delete cascade" in sql
    assert "references connected_loop_private.steps(loop_id,step_id) on delete cascade" in sql
    assert "references connected_loop_private.steps(owner_id,step_id) on delete cascade" in sql
    for forbidden in (
        "email_body",
        "body_text",
        "subject_text",
        "recipient_address",
        "attendee_address",
        "event_description",
        "access_token",
        "refresh_token",
        "attachment_content",
    ):
        assert forbidden not in sql.casefold()


def test_loop_is_bounded_and_every_mutation_is_owner_revision_fenced():
    sql = _sql()

    assert "max_steps integer not null default 8 check(max_steps=8)" in sql
    assert "step_index integer not null check(step_index between 0 and 7)" in sql
    assert "p_max_steps<>8" in sql
    assert "task_state_revision<>p_expected_revision" in sql
    assert "perform connected_app_private.owner_lock_v1(p_owner_id)" in sql
    assert "unique(loop_id,step_index)" in sql
    assert "unique(loop_id,claim_request_id)" in sql
    assert "connected multi-step claim replay drifted" in sql
    assert "connected multi-step approval resume fence changed" in sql


def test_every_mutating_step_requires_a_fresh_consumed_normal_approval():
    sql = _sql()

    for proof in (
        "review_row.status<>'approved'",
        "approval_row.consumed_at is null",
        "approval_row.consumed_by_operation_id<>p_action_id",
        "ledger_row.status<>'terminal'",
        "ledger_row.terminal_outcome<>'succeeded'",
        "step_row.approval_id<>p_approval_id",
    ):
        assert proof in sql
    assert "connected multi-step fresh approval execution is not proven" in sql
    assert "ASK_CRUMP_CONNECTED_MULTI_STEP_WRITE_RESULT_V1_DATABASE_AUTHORED_CONTENT_FREE" in sql


def test_public_control_plane_is_service_role_only_and_exactly_scoped():
    sql = _sql()
    compact = "".join(sql.split()).casefold()
    public_functions = re.findall(
        r"create or replace function public\.(connected_multi_step_[a-z0-9_]+)", sql
    )

    assert len(public_functions) == 18
    assert len(set(public_functions)) == 18
    assert "connected_multi_step_list_v1" in public_functions
    assert "connected_multi_step_owner_status_v1" in public_functions
    assert "connected_multi_step_cancel_owner_v1" in public_functions
    assert "where loop_row.owner_id=p_owner_id" in sql
    assert "ASK_CRUMP_CONNECTED_MULTI_STEP_LIST_V1_OWNER_SCOPED_CONTENT_FREE" in sql
    assert "security definer set search_path=''" in sql
    assert "grant execute on function " in sql
    assert " to service_role" in sql
    assert "revokeallonfunction" in compact
    assert "frompublic" in compact
    assert "fromanon" in compact
    assert "fromauthenticated" in compact
    assert "loop_row.task_state_revision not in" in sql
    assert "connected multi-step owner cancel revision changed" in sql
