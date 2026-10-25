"""Static release contract for the disposable guest/Free PostgreSQL gate."""
from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = (
    ROOT / ".github" / "workflows" / "postgres-migration-gate.yml"
).read_text(encoding="utf-8")
BASELINE = (ROOT / "tests" / "postgres" / "guest_sync_admission_baseline.sql").read_text(
    encoding="utf-8"
)
GUEST_CONTROL = (
    ROOT / "migrations" / "20261021040000_guest_mode_control.sql"
).read_text(encoding="utf-8")
GUEST_BASE = (
    ROOT / "migrations" / "20261021003000_guest_mode.sql"
).read_text(encoding="utf-8")
FREE_RECEIPTS = (
    ROOT / "migrations" / "20261021020000_guest_message_receipts.sql"
).read_text(encoding="utf-8")
GUEST_NETWORK_BUDGET = (
    ROOT / "migrations" / "20261025010000_guest_network_message_budget.sql"
).read_text(encoding="utf-8")
GUEST_SYNC = (
    ROOT / "migrations" / "20261021030000_guest_sync_admission.sql"
).read_text(encoding="utf-8")
GUEST_MIGRATIONS = [
    ROOT / "migrations" / "20261021003000_guest_mode.sql",
    ROOT / "migrations" / "20261021020000_guest_message_receipts.sql",
    ROOT / "migrations" / "20261021030000_guest_sync_admission.sql",
    ROOT / "migrations" / "20261021040000_guest_mode_control.sql",
    ROOT / "migrations" / "20261025010000_guest_network_message_budget.sql",
]


def _strip_dollar_quoted_bodies(sql: str) -> str:
    """Remove PL/pgSQL bodies so their BEGIN/END blocks are not SQL transactions."""
    result: list[str] = []
    cursor = 0
    opening_tag = re.compile(r"\$[A-Za-z_][A-Za-z0-9_]*\$|\$\$")

    while match := opening_tag.search(sql, cursor):
        result.append(sql[cursor : match.start()])
        tag = match.group(0)
        closing = sql.find(tag, match.end())
        assert closing >= 0, f"unterminated dollar quote {tag}"
        cursor = closing + len(tag)

    result.append(sql[cursor:])
    return "".join(result)


def test_guest_free_postgres_gate_runs_real_migrations_and_fixtures_in_order():
    assert "guest-free-access-contract:" in WORKFLOW

    job = WORKFLOW.split("guest-free-access-contract:", 1)[1].split(
        "\n  project-artifact-continuity:", 1
    )[0]
    assert "image: postgres:17" in job

    ordered_paths = [
        "tests/postgres/guest_sync_admission_baseline.sql",
        "migrations/002_server_authoritative_chat_sync.sql",
        "migrations/20261021003000_guest_mode.sql",
        "migrations/20261021020000_guest_message_receipts.sql",
        "migrations/20261021030000_guest_sync_admission.sql",
        "tests/postgres/test_free_message_reservation_migration.sql",
        "tests/postgres/test_guest_sync_admission_migration.sql",
        "migrations/20261021040000_guest_mode_control.sql",
        "tests/postgres/guest_network_cron_stub.sql",
        "migrations/20261025010000_guest_network_message_budget.sql",
        "tests/postgres/test_guest_network_message_budget_migration.sql",
        "tests/postgres/test_guest_mode_control_migration.sql",
    ]
    positions = [job.index(path) for path in ordered_paths]
    assert positions == sorted(positions)
    assert job.count("--set=ON_ERROR_STOP=1") == len(ordered_paths) + 8
    assert job.count("--single-transaction") == 15


def test_guest_schema_is_created_by_the_real_migration_not_the_baseline():
    assert "is_guest" not in BASELINE
    assert "is_verified boolean not null default false" in BASELINE
    assert "create table public.sessions" in BASELINE


def test_guest_network_budget_is_private_fixed_and_lock_ordered():
    normalized = GUEST_NETWORK_BUDGET.lower()
    reservation = normalized.split(
        "create or replace function public.reserve_free_message_v2(", 1
    )[1].split("revoke all on function", 1)[0]

    assert "v_account_limit constant integer := 5" in reservation
    assert "v_network_limit constant integer := 25" in reservation
    assert "interval '24 hours'" in reservation
    assert "on delete set null" in normalized
    assert "receipt_id uuid primary key default pg_catalog.gen_random_uuid()" in normalized
    assert "usage_event_id uuid unique" in normalized
    assert "check (network_key_hash ~ '^[0-9a-f]{64}$')" in normalized
    assert "alter table public.guest_network_message_events enable row level security" in normalized
    assert "from public, anon, authenticated, service_role" in normalized
    assert "to service_role" in normalized
    assert "interval '25 hours'" in normalized
    assert "askcrump_guest_network_retention_v1" in normalized
    assert "*/15 * * * *" in normalized
    assert "select * from public.purge_guest_network_message_events_v1();" in normalized
    assert "nodename <> 'localhost'" in normalized
    assert "nodeport <> pg_catalog.inet_server_port()" in normalized
    assert "nodename = 'localhost'" in normalized
    assert "nodeport = pg_catalog.inet_server_port()" in normalized
    assert "unexpected guest network message-budget index definition" in normalized
    assert "index_row.indisvalid" in normalized
    assert "index_row.indisready" in normalized
    assert "pg_catalog.pg_get_indexdef" in normalized
    assert "unexpected guest network message-budget table security contract" in normalized
    assert "unexpected guest network message-budget function security contract" in normalized
    assert "relation_row.relpersistence = 'p'" in normalized
    assert "expected_constraints constant text[]" in normalized
    assert "constraint_row.conname || ':' || constraint_row.contype::text" in normalized
    assert "constraint_row.confkey = array[usage_event_target_attribute]" in normalized
    assert "constraint_row.confdelsetcols is null" in normalized
    assert "pg_catalog.pg_get_constraintdef(constraint_row.oid, false)" in normalized
    assert "'check ((network_key_hash ~ ''^[0-9a-f]{64}$''::text))'" in normalized
    assert "not index_row.indnullsnotdistinct" in normalized
    assert "index_row.indkey[0] = receipt_attribute" in normalized
    assert "index_row.indkey[0] = usage_event_attribute" in normalized
    assert "constraint_row.conkey = array[network_key_hash_attribute]" in normalized
    assert "operator_class.opcname = 'uuid_ops'" in normalized
    assert "constraint_row.convalidated" in normalized
    assert "guest_network_message_events_usage_event_id_fkey" in normalized
    assert "pg_catalog.count(*) <> 4" in normalized
    assert "pg_catalog.count(*) <> 2" in normalized
    assert "attribute_row.attacl is not null" in normalized
    assert "policy_row.polrelid = relation_oid" in normalized
    assert "not trigger_row.tgisinternal" in normalized
    assert "rewrite_row.ev_class = relation_oid" in normalized
    assert "alter function public.reserve_free_message_v2(uuid, uuid, text, text)" in normalized
    assert "alter function public.refund_usage_event_v2(uuid, uuid)" in normalized
    assert "delete from public.usage_events as usage_event" in normalized
    assert "where network_event.receipt_id = v_network_receipt_id" in normalized
    assert "return query select v_deleted = 1" in normalized
    assert "owner to postgres" in normalized

    account_lock = reservation.index("'usage:' || p_user_id::text || ':messages'")
    network_lock = reservation.index("'usage:guest-network:' || p_network_key_hash")
    clock = reservation.index("v_now := pg_catalog.clock_timestamp();")
    replay = reservation.index("and event.idempotency_key = v_key")
    account_denial = reservation.index("if v_used >= v_account_limit then", replay)
    network_denial = reservation.index(
        "if v_is_guest and v_network_used >= v_network_limit then", replay
    )
    assert account_lock < network_lock < clock < replay
    assert replay < account_denial < network_denial


def test_guest_control_is_fail_closed_service_only_and_deadlock_aware():
    assert "enabled boolean not null default false" in GUEST_CONTROL
    assert "for share nowait" in GUEST_CONTROL
    assert "before insert or update on public.sessions" in GUEST_CONTROL
    assert "account.is_guest is true" in GUEST_CONTROL
    assert "session.revoked_at is null" in GUEST_CONTROL
    assert "grant execute on function public.get_guest_mode_control_v1()" in GUEST_CONTROL
    assert (
        "grant execute on function public.set_guest_mode_enabled_v1(boolean)"
        in GUEST_CONTROL
    )
    assert "to service_role" in GUEST_CONTROL


def test_guest_verification_conversion_is_one_locked_database_transaction():
    signature = "public.verify_guest_and_create_session_v1("
    function = GUEST_CONTROL.split(
        f"create or replace function {signature}", 1
    )[1].split("comment on function", 1)[0]

    user_lock = "from public.users as account"
    conversion = "set is_verified = true,"
    session_drain = "update public.sessions as session"
    replacement = "insert into public.sessions as persisted"
    assert "for update;" in function
    assert function.index(user_lock) < function.index(conversion)
    assert function.index(conversion) < function.index(session_drain)
    assert function.index(session_drain) < function.index(replacement)
    assert "session.revoked_at is null" in function
    assert "on conflict (device_id) do update" in function
    assert "'guestVerificationRevokedAt', v_now" in function
    assert (
        "grant execute on function public.verify_guest_and_create_session_v1("
        in GUEST_CONTROL
    )
    assert "from public, anon, authenticated, service_role" in GUEST_CONTROL


def test_guest_write_barrier_precedes_every_guest_database_write():
    assert "create or replace function public.lock_guest_mode_control_v1()" in GUEST_BASE
    assert "for share;" in GUEST_BASE
    assert (
        "revoke all on function public.lock_guest_mode_control_v1()"
        in GUEST_BASE
    )

    reservation = FREE_RECEIPTS.split(
        "create or replace function public.reserve_free_message_v1(", 1
    )[1].split("revoke all on function", 1)[0]
    control_lock = "v_guest_mode_enabled := public.lock_guest_mode_control_v1();"
    account_lock = "from public.users as account"
    usage_lock = "pg_catalog.pg_advisory_xact_lock("
    receipt_insert = "insert into public.usage_events"
    assert reservation.index(control_lock) < reservation.index(account_lock)
    assert reservation.index(account_lock) < reservation.index(usage_lock)
    assert reservation.index(usage_lock) < reservation.index(receipt_insert)
    assert "'guest_mode_disabled'::text" in reservation

    for signature, persistence in (
        ("public.apply_guest_chat_sync_v2(", "from public.apply_chat_sync("),
        ("public.persist_guest_chat_reply_v1(", "from public.persist_chat_reply("),
    ):
        function = GUEST_SYNC.split(f"create or replace function {signature}", 1)[1]
        function = function.split("comment on function", 1)[0]
        assert function.index(control_lock) < function.index("from public.users as candidate")
        assert function.index("from public.users as candidate") < function.index(persistence)
        assert "'guest_mode_disabled'::text" in function


def test_registered_session_updates_bypass_guest_control_and_drain_is_attributed():
    trigger = GUEST_CONTROL.split(
        "create or replace function public.enforce_guest_mode_on_session_v1()", 1
    )[1].split("-- Install the user invariant", 1)[0]
    identity_read = "from public.users as account"
    registered_return = "if not coalesce(v_is_guest, false) then"
    control_read = "from public.guest_mode_control as control"
    assert trigger.index(identity_read) < trigger.index(registered_return)
    assert trigger.index(registered_return) < trigger.index(control_read)
    assert "for share nowait" in trigger
    assert "'guestControlRevokedAt', v_updated_at" in GUEST_CONTROL


def test_guest_settings_writes_share_the_fail_closed_control_boundary():
    trigger = GUEST_CONTROL.split(
        "create or replace function public.enforce_guest_mode_on_user_settings_v1()",
        1,
    )[1].split("-- Install the user invariant", 1)[0]

    identity_lock = "from public.users as account"
    registered_return = "if not v_is_guest then"
    control_lock = "public.lock_guest_mode_control_v1()"
    assert trigger.index(identity_lock) < trigger.index("for share;")
    assert trigger.index("for share;") < trigger.index(registered_return)
    assert trigger.index(registered_return) < trigger.index(control_lock)
    assert "errcode = 'GX003'" in trigger
    assert "before insert or update on public.user_settings" in GUEST_CONTROL
    assert (
        "revoke all on function public.enforce_guest_mode_on_user_settings_v1()"
        in GUEST_CONTROL
    )

    rpc_signature = "public.apply_guest_user_settings_v1("
    rpc = GUEST_CONTROL.split(
        f"create or replace function {rpc_signature}", 1
    )[1].split("comment on function", 1)[0]
    rpc_control_lock = "v_guest_mode_enabled := public.lock_guest_mode_control_v1();"
    rpc_user_lock = "from public.users as account"
    rpc_upsert = "insert into public.user_settings as current_settings"
    assert rpc.index(rpc_control_lock) < rpc.index(rpc_user_lock)
    assert rpc.index(rpc_user_lock) < rpc.index("for share;")
    assert rpc.index("for share;") < rpc.index(rpc_upsert)
    assert "'not_guest'::text" in rpc
    assert "'guest_mode_disabled'::text" in rpc
    assert "on conflict (user_id) do update" in rpc
    assert (
        "revoke all on function public.apply_guest_user_settings_v1("
        in GUEST_CONTROL
    )
    assert (
        "grant execute on function public.apply_guest_user_settings_v1("
        in GUEST_CONTROL
    )


def test_guest_migrations_leave_transaction_control_to_the_production_runner():
    """Embedded transaction control can split schema state from migration history."""
    transaction_control = re.compile(
        r"^\s*(?:begin|start\s+transaction|commit|rollback|savepoint|"
        r"release\s+savepoint)\b",
        flags=re.IGNORECASE | re.MULTILINE,
    )

    for path in GUEST_MIGRATIONS:
        sql = path.read_text(encoding="utf-8")
        outside_bodies = _strip_dollar_quoted_bodies(sql)
        outside_comments = re.sub(r"/\*.*?\*/", "", outside_bodies, flags=re.DOTALL)
        outside_comments = re.sub(r"--[^\n]*", "", outside_comments)

        assert "migration runner owns" in sql.lower(), path.name
        assert transaction_control.search(outside_comments) is None, path.name
