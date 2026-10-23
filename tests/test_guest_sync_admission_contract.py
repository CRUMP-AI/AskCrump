from __future__ import annotations

from pathlib import Path
import re


ROOT = Path(__file__).parents[1]
MIGRATION = (
    ROOT / "migrations" / "20261021030000_guest_sync_admission.sql"
).read_text(encoding="utf-8")
SYNC_SERVICE = (ROOT / "backend" / "sync_service.py").read_text(encoding="utf-8")


def executable_sql(source: str) -> str:
    return "\n".join(
        line.split("--", 1)[0]
        for line in source.splitlines()
    ).lower()


SQL = executable_sql(MIGRATION)


def test_guest_sync_rpc_is_one_server_authoritative_post_merge_operation():
    assert "create or replace function public.apply_guest_chat_sync_v2(" in SQL
    function = SQL.split(
        "create or replace function public.apply_guest_chat_sync_v2(", 1
    )[1].split("comment on function public.apply_guest_chat_sync_v2", 1)[0]

    assert "security definer" in function
    assert "set search_path = ''" in function
    assert "from public.users as candidate" in function
    assert "for update;" in function
    assert function.index("from public.users as candidate") < function.index(
        "from public.apply_chat_sync("
    )
    assert "pg_catalog.octet_length(candidate.messages::text)" in function
    assert "v_after_count <= 50" in function
    assert "v_after_chat_bytes <= 200000" in function
    assert "v_after_total <= 2000000" in function

    # No caller-controlled storage limits or pre-apply size estimates survive.
    assert "p_sizes" not in function
    assert "p_max_chats" not in function
    assert "p_max_bytes" not in function
    assert "length(candidate.messages::text)" not in function.replace(
        "octet_length(candidate.messages::text)", ""
    )


def test_quota_rejection_rolls_back_only_the_inner_apply_and_keeps_cleanup_paths():
    function = SQL.split(
        "create or replace function public.apply_guest_chat_sync_v2(", 1
    )[1].split("comment on function public.apply_guest_chat_sync_v2", 1)[0]

    apply_at = function.index("from public.apply_chat_sync(")
    quota_raise_at = function.index("errcode = 'gx001'")
    handler_at = function.index("when sqlstate 'gx001'")
    assert apply_at < quota_raise_at < handler_at
    assert "'quota_exceeded'::text" in function[handler_at:]
    assert "v_safe_reduction := v_existed" in function
    assert "p_deleted_at is not null" in function
    assert "'unknown_tombstone'::text" in function
    assert function.index("'unknown_tombstone'::text") < apply_at


def test_normal_guest_reply_persistence_uses_the_same_serialized_storage_boundary():
    assert "create or replace function public.persist_guest_chat_reply_v1(" in SQL
    function = SQL.split(
        "create or replace function public.persist_guest_chat_reply_v1(", 1
    )[1].split("comment on function public.persist_guest_chat_reply_v1", 1)[0]
    assert "from public.users as candidate" in function
    assert "for update;" in function
    assert "from public.persist_chat_reply(" in function
    assert "v_after_count <= 50" in function
    assert "v_after_chat_bytes <= 200000" in function
    assert "v_after_total <= 2000000" in function
    assert "when sqlstate 'gx001'" in function
    assert "'quota_exceeded'::text" in function
    assert "set search_path = ''" in function

    chat = (ROOT / "backend" / "routes" / "chat.py").read_text(encoding="utf-8").lower()
    assert "'persist_guest_chat_reply_v1'" in chat
    assert "if is_guest_user(auth.user)" in chat
    assert "'status': 'queued_locally'" in chat


def test_guest_sync_migration_is_runner_transaction_safe_and_private():
    assert not re.search(r"^\s*(begin|commit)\s*;\s*$", SQL, flags=re.MULTILINE)
    signature = (
        "public.apply_guest_chat_sync_v2(\n"
        "    uuid, uuid, text, jsonb, timestamptz, timestamptz, timestamptz, bigint\n"
        ")"
    )
    assert f"revoke all on function {signature}" in SQL
    assert ") from public, anon, authenticated, service_role;" in SQL
    assert f"grant execute on function {signature}" in SQL
    assert ") to service_role;" in SQL
    assert (
        "revoke all on function public.persist_guest_chat_reply_v1(uuid, uuid, text, jsonb, jsonb)"
        in SQL
    )
    assert (
        "grant execute on function public.persist_guest_chat_reply_v1(uuid, uuid, text, jsonb, jsonb)"
        in SQL
    )

    # Retire the legacy capability without dropping its function or any data.
    retire = SQL.split("do $retire_guest_admission$", 1)[1]
    assert "revoke all on function public.admit_guest_sync_chats" in retire
    assert "from public, anon, authenticated, service_role" in retire
    assert "drop function" not in retire
    assert "delete from" not in retire
    assert "truncate" not in retire


def test_python_guest_path_uses_only_the_atomic_rpc_and_registered_path_is_unchanged():
    assert "'admit_guest_sync_chats'" not in SYNC_SERVICE
    assert "'p_sizes'" not in SYNC_SERVICE
    assert "'p_max_chats'" not in SYNC_SERVICE
    assert "'p_max_bytes'" not in SYNC_SERVICE
    assert (
        "sync_rpc = 'apply_guest_chat_sync_v2' if is_guest else 'apply_chat_sync'"
        in SYNC_SERVICE
    )
    assert "result = await db.rpc(\n            sync_rpc," in SYNC_SERVICE
