#!/usr/bin/env python3
"""Run Autonomous Crump guardrail races against an owned disposable PostgreSQL DB.

This gate deliberately refuses remote hosts, ordinary database names, databases
with existing public tables, or missing ownership attestation. It never connects
to Supabase and never drops or rewrites an existing schema. Run it only against a
fresh local database whose lifetime is controlled by the caller.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import sys
from urllib.parse import urlsplit
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = (
    ROOT / "migrations" / "20260827145025_crump_code_foundation.sql",
    ROOT / "migrations" / "20260830093000_crump_code_durable_worker.sql",
    ROOT / "migrations" / "20260916231500_autonomous_crump_atomic_dispatch.sql",
    ROOT / "migrations" / "20260917001500_autonomous_crump_queue_guardrails.sql",
)
DSN_ENV = "AUTONOMOUS_CRUMP_GUARDRAIL_TEST_DSN"
OWNERSHIP_ENV = "AUTONOMOUS_CRUMP_GUARDRAIL_TEST_OWNERSHIP"
OWNERSHIP_VALUE = "I_OWN_THIS_EMPTY_DISPOSABLE_DATABASE"
DB_PREFIX = "askcrump_guardrails_"


def _dependency():
    try:
        import psycopg  # type: ignore
    except ImportError as exc:  # pragma: no cover - operator environment boundary
        raise SystemExit(
            "psycopg is required only for this disposable PostgreSQL gate; "
            "install psycopg[binary] in the temporary validation environment."
        ) from exc
    return psycopg


def _validated_dsn() -> str:
    dsn = str(os.getenv(DSN_ENV) or "").strip()
    if not dsn:
        raise SystemExit(f"{DSN_ENV} is required.")
    if os.getenv(OWNERSHIP_ENV) != OWNERSHIP_VALUE:
        raise SystemExit(f"{OWNERSHIP_ENV} must equal {OWNERSHIP_VALUE}.")
    parsed = urlsplit(dsn)
    if parsed.scheme not in {"postgres", "postgresql"}:
        raise SystemExit("The disposable gate requires a postgres:// or postgresql:// DSN.")
    if (parsed.hostname or "").casefold() not in {"localhost", "127.0.0.1", "::1"}:
        raise SystemExit("The disposable gate refuses non-loopback PostgreSQL hosts.")
    database = parsed.path.lstrip("/").split("?", 1)[0]
    if not database.startswith(DB_PREFIX) or len(database) <= len(DB_PREFIX):
        raise SystemExit(f"The database name must start with {DB_PREFIX} and include a suffix.")
    return dsn


BOOTSTRAP = r"""
do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'anon') then
    create role anon nologin;
  end if;
  if not exists (select 1 from pg_roles where rolname = 'authenticated') then
    create role authenticated nologin;
  end if;
  if not exists (select 1 from pg_roles where rolname = 'service_role') then
    create role service_role nologin bypassrls;
  end if;
end
$$;

create table public.users (
  id uuid primary key,
  email text not null,
  password_hash text not null,
  internal_tier text,
  deleted_at timestamptz
);

create table public.projects (
  id uuid primary key,
  user_id uuid not null references public.users(id) on delete cascade,
  name text not null
);

create table public.credit_accounts (
  user_id uuid primary key references public.users(id) on delete cascade,
  balance bigint not null default 0
);

create or replace function public.consume_usage_event(
  p_user_id uuid,
  p_event_type text,
  p_limit integer,
  p_metadata jsonb default '{}'::jsonb
)
returns table(event_id uuid, used integer, allowed boolean)
language sql
security invoker
set search_path = ''
as $$
  select gen_random_uuid(), 1, true
$$;

create or replace function public.spend_credits_confirmed(
  p_user_id uuid,
  p_amount integer,
  p_reason text,
  p_action_key text,
  p_component text,
  p_confirmed_max integer,
  p_metadata jsonb default '{}'::jsonb
)
returns table(
  ledger_id uuid,
  balance bigint,
  allowed boolean,
  duplicate boolean,
  limit_exceeded boolean
)
language sql
security invoker
set search_path = ''
as $$
  select gen_random_uuid(), 1000::bigint, true, false, false
$$;
"""


def _scalar(connection, sql: str, params: tuple = ()):
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        row = cursor.fetchone()
        return row[0] if row else None


def _create_identity(connection, label: str) -> tuple[str, str]:
    user_id = str(uuid4())
    project_id = str(uuid4())
    with connection.cursor() as cursor:
        cursor.execute(
            "insert into public.users (id, email, password_hash, internal_tier) "
            "values (%s, %s, 'fixture', 'professional')",
            (user_id, f"{label}-{user_id}@example.invalid"),
        )
        cursor.execute(
            "insert into public.projects (id, user_id, name) values (%s, %s, %s)",
            (project_id, user_id, label),
        )
        cursor.execute(
            "insert into public.credit_accounts (user_id, balance) values (%s, 1000)",
            (user_id,),
        )
    return user_id, project_id


def _create_task(
    connection,
    user_id: str,
    project_id: str,
    label: str,
    *,
    creation_token: str | None = None,
    max_duration_seconds: int = 180,
) -> dict:
    token = creation_token or str(uuid4())
    return _scalar(
        connection,
        "select public.create_code_task_guarded(%s,%s,%s,%s,'implement',"
        "'https://github.com/openai/codex.git','main',%s)",
        (user_id, project_id, token, label, max_duration_seconds),
    )


def _accept(dsn: str, user_id: str, task_id: str, token: str) -> dict:
    psycopg = _dependency()
    with psycopg.connect(dsn, autocommit=True) as connection:
        return _scalar(
            connection,
            "select public.accept_code_task_run(%s,%s,%s,%s,3,12,'fixture',12)",
            (task_id, user_id, token, "a" * 40),
        )


def _concurrent_create(dsn: str, user_id: str, project_id: str, index: int) -> dict:
    psycopg = _dependency()
    with psycopg.connect(dsn, autocommit=True) as connection:
        return _create_task(connection, user_id, project_id, f"queued-{index}")


def _replay_create(
    dsn: str,
    user_id: str,
    project_id: str,
    creation_token: str,
) -> dict:
    psycopg = _dependency()
    with psycopg.connect(dsn, autocommit=True) as connection:
        return _create_task(
            connection,
            user_id,
            project_id,
            "replay-safe-create",
            creation_token=creation_token,
        )


def main() -> int:
    psycopg = _dependency()
    dsn = _validated_dsn()
    with psycopg.connect(dsn, autocommit=True) as connection:
        existing = _scalar(
            connection,
            "select count(*) from information_schema.tables "
            "where table_schema = 'public' and table_type = 'BASE TABLE'",
        )
        if int(existing or 0) != 0:
            raise SystemExit(
                "The disposable guardrail database is not empty; refusing to modify it."
            )
        connection.execute(BOOTSTRAP)
        for path in MIGRATIONS:
            connection.execute(path.read_text(encoding="utf-8"))

        owner_user, owner_project = _create_identity(connection, "ownership-a")
        other_user, other_project = _create_identity(connection, "ownership-b")
        connection.execute("set role service_role")
        direct_insert_rejected = False
        try:
            connection.execute(
                "insert into public.code_tasks "
                "(user_id,project_id,creation_token,objective,mode,source_repo_url,"
                "source_ref,max_duration_seconds) values (%s,%s,%s,'forged','implement',"
                "'https://github.com/openai/codex.git','main',180)",
                (owner_user, owner_project, str(uuid4())),
            )
        except psycopg.errors.InsufficientPrivilege:
            direct_insert_rejected = True
        finally:
            connection.execute("reset role")
        if not direct_insert_rejected:
            raise AssertionError("service_role direct code_tasks INSERT was not rejected")

        connection.execute("set role service_role")
        cross_owner = _scalar(
            connection,
            "select public.create_code_task_guarded(%s,%s,%s,'cross-owner','implement',"
            "'https://github.com/openai/codex.git','main',180)",
            (owner_user, other_project, str(uuid4())),
        )
        connection.execute("reset role")
        if cross_owner.get("reason") != "project_not_found":
            raise AssertionError((cross_owner, owner_user, other_user, other_project))

        replay_user, replay_project = _create_identity(connection, "create-replay")

        queue_user, queue_project = _create_identity(connection, "queue-race")

    replay_token = str(uuid4())
    with ThreadPoolExecutor(max_workers=2) as pool:
        replay_results = list(
            pool.map(
                lambda _index: _replay_create(
                    dsn,
                    replay_user,
                    replay_project,
                    replay_token,
                ),
                range(2),
            )
        )
    if not all(result.get("created") is True for result in replay_results):
        raise AssertionError(replay_results)
    if sorted(bool(result.get("replayed")) for result in replay_results) != [False, True]:
        raise AssertionError(replay_results)
    replay_task_ids = {result["task"]["id"] for result in replay_results}
    if len(replay_task_ids) != 1:
        raise AssertionError(replay_results)
    with psycopg.connect(dsn, autocommit=True) as connection:
        replay_task_id = next(iter(replay_task_ids))
        if _scalar(
            connection,
            "select count(*) from public.code_tasks where creation_token=%s",
            (replay_token,),
        ) != 1:
            raise AssertionError("create replay inserted more than one task")
        if _scalar(
            connection,
            "select count(*) from public.code_task_events "
            "where task_id=%s and event_type='task.created'",
            (replay_task_id,),
        ) != 1:
            raise AssertionError("create replay inserted more than one creation event")
        connection.execute(
            "update public.code_tasks set status='cancelled', completed_at=now() where id=%s",
            (replay_task_id,),
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        queue_results = list(
            pool.map(
                lambda index: _concurrent_create(
                    dsn, queue_user, queue_project, index
                ),
                range(8),
            )
        )
    created_count = sum(result.get("created") is True for result in queue_results)
    deferred_count = sum(result.get("reason") == "user_queue_limit" for result in queue_results)
    if (created_count, deferred_count) != (3, 5):
        raise AssertionError((created_count, deferred_count, queue_results))

    with psycopg.connect(dsn, autocommit=True) as connection:
        connection.execute(
            "update public.code_guardrail_limits set global_queue_limit=10 where id=1"
        )
        global_identities = [
            _create_identity(connection, f"global-queue-{index}") for index in range(10)
        ]
    with ThreadPoolExecutor(max_workers=10) as pool:
        global_queue_results = list(
            pool.map(
                lambda item: _concurrent_create(dsn, item[0], item[1], item[2]),
                (
                    (user_id, project_id, index)
                    for index, (user_id, project_id) in enumerate(global_identities)
                ),
            )
        )
    global_created = sum(result.get("created") is True for result in global_queue_results)
    global_deferred = sum(
        result.get("reason") == "global_queue_limit" for result in global_queue_results
    )
    if (global_created, global_deferred) != (7, 3):
        raise AssertionError((global_created, global_deferred, global_queue_results))

    with psycopg.connect(dsn, autocommit=True) as connection:
        connection.execute(
            "update public.code_tasks set status='cancelled', completed_at=now() "
            "where status='queued' and dispatch_token is null and usage_receipt is null"
        )
        connection.execute(
            "update public.code_guardrail_limits set global_queue_limit=100 where id=1"
        )
        race_user, race_project = _create_identity(connection, "accept-race")
        first = _create_task(connection, race_user, race_project, "first")
        second = _create_task(connection, race_user, race_project, "second")
        task_ids = [first["task"]["id"], second["task"]["id"]]
        connection.execute(
            "update public.code_tasks set source_ref=%s, base_revision=%s "
            "where id = any(%s::uuid[])",
            ("a" * 40, "a" * 40, task_ids),
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        accept_results = list(
            pool.map(
                lambda pair: _accept(dsn, race_user, pair[0], pair[1]),
                zip(task_ids, (str(uuid4()), str(uuid4())), strict=True),
            )
        )
    if sum(result.get("accepted") is True for result in accept_results) != 1:
        raise AssertionError(accept_results)
    if sum(result.get("reason") == "user_active_task" for result in accept_results) != 1:
        raise AssertionError(accept_results)
    accepted_task_id = next(
        result["task"]["id"] for result in accept_results if result.get("accepted") is True
    )

    with psycopg.connect(dsn, autocommit=True) as connection:
        receipts = _scalar(
            connection,
            "select count(*) from public.code_guardrail_receipts "
            "where user_id=%s and receipt_kind='accepted'",
            (race_user,),
        )
        if receipts != 1:
            raise AssertionError(f"expected one acceptance receipt, got {receipts}")
        connection.execute(
            "update public.code_tasks set status='completed', completed_at=now() where id=%s",
            (accepted_task_id,),
        )

        fair_users: list[tuple[str, str, str]] = []
        for label in ("served", "never-served"):
            user_id, project_id = _create_identity(connection, label)
            task = _create_task(connection, user_id, project_id, label)["task"]
            connection.execute(
                "update public.code_tasks set source_ref=%s, base_revision=%s where id=%s",
                ("a" * 40, "a" * 40, task["id"]),
            )
            accepted = _accept(dsn, user_id, task["id"], str(uuid4()))
            if accepted.get("accepted") is not True:
                raise AssertionError(accepted)
            fair_users.append((user_id, project_id, task["id"]))

        connection.execute(
            "insert into public.code_guardrail_receipts "
            "(task_id,user_id,budget_day,receipt_kind,attempt_number,declared_sandbox_seconds) "
            "values (%s,%s,(current_timestamp at time zone 'UTC')::date,'model_start',1,30)",
            (fair_users[0][2], fair_users[0][0]),
        )
        connection.execute(
            "insert into public.code_guardrail_global_daily_facts as daily "
            "(budget_day,accepted_count,model_start_count,declared_sandbox_seconds) "
            "values ((current_timestamp at time zone 'UTC')::date,0,1,30) "
            "on conflict (budget_day) do update set "
            "model_start_count=daily.model_start_count+1, "
            "declared_sandbox_seconds="
            "daily.declared_sandbox_seconds+30, "
            "updated_at=now()"
        )
        connection.execute(
            "update public.code_tasks set attempt_count=1 where id=%s",
            (fair_users[0][2],),
        )
        claim = _scalar(
            connection,
            "select public.claim_code_task_guarded(225,%s)",
            (str(uuid4()),),
        )
        if claim.get("claimed") is not True:
            raise AssertionError(claim)
        if claim["task"]["user_id"] != fair_users[1][0]:
            raise AssertionError((claim, fair_users))

        connection.execute(
            "update public.code_guardrail_limits set global_active_lease_limit=1 where id=1"
        )
        active_deferred = _scalar(
            connection,
            "select public.claim_code_task_guarded(225,%s)",
            (str(uuid4()),),
        )
        if active_deferred.get("reason") != "global_active_lease_limit":
            raise AssertionError(active_deferred)

        connection.execute(
            "update public.code_tasks set status='completed', completed_at=now(), "
            "lease_token=null, lease_expires_at=null where id=%s",
            (claim["task"]["id"],),
        )
        connection.execute(
            "update public.code_guardrail_limits set "
            "global_active_lease_limit=2, user_daily_sandbox_seconds=30 where id=1"
        )
        user_budget_deferred = _scalar(
            connection,
            "select public.claim_code_task_guarded(225,%s)",
            (str(uuid4()),),
        )
        if user_budget_deferred.get("reason") != "user_daily_compute_limit":
            raise AssertionError(user_budget_deferred)

        connection.execute(
            "update public.code_guardrail_limits set "
            "user_daily_sandbox_seconds=720, global_daily_sandbox_seconds=60 where id=1"
        )
        global_budget_deferred = _scalar(
            connection,
            "select public.claim_code_task_guarded(225,%s)",
            (str(uuid4()),),
        )
        if global_budget_deferred.get("reason") != "global_daily_sandbox_seconds":
            raise AssertionError(global_budget_deferred)

        connection.execute(
            "update public.code_guardrail_limits set "
            "global_daily_sandbox_seconds=4320, global_daily_model_start_limit=2 where id=1"
        )
        global_start_deferred = _scalar(
            connection,
            "select public.claim_code_task_guarded(225,%s)",
            (str(uuid4()),),
        )
        if global_start_deferred.get("reason") != "global_daily_model_start_limit":
            raise AssertionError(global_start_deferred)

        global_model_fact_before = _scalar(
            connection,
            "select model_start_count from public.code_guardrail_global_daily_facts "
            "where budget_day=(current_timestamp at time zone 'UTC')::date",
        )
        linked_model_receipts_before = _scalar(
            connection,
            "select count(*) from public.code_guardrail_receipts "
            "where budget_day=(current_timestamp at time zone 'UTC')::date "
            "and receipt_kind='model_start'",
        )
        connection.execute("delete from public.users where id=%s", (fair_users[0][0],))
        linked_model_receipts_after = _scalar(
            connection,
            "select count(*) from public.code_guardrail_receipts "
            "where budget_day=(current_timestamp at time zone 'UTC')::date "
            "and receipt_kind='model_start'",
        )
        global_model_fact_after = _scalar(
            connection,
            "select model_start_count from public.code_guardrail_global_daily_facts "
            "where budget_day=(current_timestamp at time zone 'UTC')::date",
        )
        if linked_model_receipts_after != linked_model_receipts_before - 1:
            raise AssertionError(
                (linked_model_receipts_before, linked_model_receipts_after)
            )
        if global_model_fact_after != global_model_fact_before:
            raise AssertionError((global_model_fact_before, global_model_fact_after))
        deletion_invariant_model_deferred = _scalar(
            connection,
            "select public.claim_code_task_guarded(225,%s)",
            (str(uuid4()),),
        )
        if deletion_invariant_model_deferred.get("reason") != "global_daily_model_start_limit":
            raise AssertionError(deletion_invariant_model_deferred)

        daily_user, daily_project = _create_identity(connection, "daily-accept")
        for index in range(3):
            daily_task = _create_task(
                connection, daily_user, daily_project, f"daily-accept-{index}"
            )["task"]
            connection.execute(
                "update public.code_tasks set source_ref=%s, base_revision=%s where id=%s",
                ("a" * 40, "a" * 40, daily_task["id"]),
            )
            daily_result = _accept(dsn, daily_user, daily_task["id"], str(uuid4()))
            if daily_result.get("accepted") is not True:
                raise AssertionError(daily_result)
            connection.execute(
                "update public.code_tasks set status='completed', completed_at=now() where id=%s",
                (daily_task["id"],),
            )
        fourth_daily = _create_task(
            connection, daily_user, daily_project, "daily-accept-blocked"
        )["task"]
        connection.execute(
            "update public.code_tasks set source_ref=%s, base_revision=%s where id=%s",
            ("a" * 40, "a" * 40, fourth_daily["id"]),
        )
        user_accept_deferred = _accept(
            dsn, daily_user, fourth_daily["id"], str(uuid4())
        )
        if user_accept_deferred.get("reason") != "user_daily_accept_limit":
            raise AssertionError(user_accept_deferred)

        connection.execute(
            "update public.code_guardrail_limits set global_daily_accept_limit=10 where id=1"
        )
        global_accept_users: list[str] = []
        for index in range(4):
            global_user, global_project = _create_identity(
                connection, f"global-accept-{index}"
            )
            global_accept_users.append(global_user)
            global_task = _create_task(
                connection, global_user, global_project, f"global-accept-{index}"
            )["task"]
            connection.execute(
                "update public.code_tasks set source_ref=%s, base_revision=%s where id=%s",
                ("a" * 40, "a" * 40, global_task["id"]),
            )
            global_result = _accept(
                dsn, global_user, global_task["id"], str(uuid4())
            )
            if global_result.get("accepted") is not True:
                raise AssertionError(global_result)
            connection.execute(
                "update public.code_tasks set status='completed', completed_at=now() where id=%s",
                (global_task["id"],),
            )
        blocked_user, blocked_project = _create_identity(connection, "global-accept-blocked")
        blocked_task = _create_task(
            connection, blocked_user, blocked_project, "global-accept-blocked"
        )["task"]
        connection.execute(
            "update public.code_tasks set source_ref=%s, base_revision=%s where id=%s",
            ("a" * 40, "a" * 40, blocked_task["id"]),
        )
        global_accept_deferred = _accept(
            dsn, blocked_user, blocked_task["id"], str(uuid4())
        )
        if global_accept_deferred.get("reason") != "global_daily_accept_limit":
            raise AssertionError(global_accept_deferred)

        accepted_fact_before = _scalar(
            connection,
            "select accepted_count from public.code_guardrail_global_daily_facts "
            "where budget_day=(current_timestamp at time zone 'UTC')::date",
        )
        linked_accepted_before = _scalar(
            connection,
            "select count(*) from public.code_guardrail_receipts "
            "where budget_day=(current_timestamp at time zone 'UTC')::date "
            "and receipt_kind='accepted'",
        )
        connection.execute("delete from public.users where id=%s", (global_accept_users[0],))
        linked_accepted_after = _scalar(
            connection,
            "select count(*) from public.code_guardrail_receipts "
            "where budget_day=(current_timestamp at time zone 'UTC')::date "
            "and receipt_kind='accepted'",
        )
        accepted_fact_after = _scalar(
            connection,
            "select accepted_count from public.code_guardrail_global_daily_facts "
            "where budget_day=(current_timestamp at time zone 'UTC')::date",
        )
        if linked_accepted_after != linked_accepted_before - 1:
            raise AssertionError((linked_accepted_before, linked_accepted_after))
        if accepted_fact_after != accepted_fact_before:
            raise AssertionError((accepted_fact_before, accepted_fact_after))
        deletion_invariant_accept_deferred = _accept(
            dsn, blocked_user, blocked_task["id"], str(uuid4())
        )
        if deletion_invariant_accept_deferred.get("reason") != "global_daily_accept_limit":
            raise AssertionError(deletion_invariant_accept_deferred)

        # Start isolated proof phases in the same disposable database. Resetting
        # only private fixture counters here lets each semantic edge be asserted
        # without weakening the production functions under test.
        connection.execute(
            "update public.code_tasks set status='completed', completed_at=now(), "
            "lease_token=null, lease_expires_at=null "
            "where usage_receipt is not null and status in "
            "('queued','provisioning','running','awaiting_approval','verifying')"
        )
        connection.execute(
            "update public.code_guardrail_global_daily_facts set "
            "accepted_count=0, model_start_count=0, declared_sandbox_seconds=0, "
            "updated_at=now() where budget_day=(current_timestamp at time zone 'UTC')::date"
        )
        connection.execute(
            "update public.code_guardrail_limits set global_daily_accept_limit=30, "
            "global_daily_model_start_limit=24, global_daily_sandbox_seconds=4320, "
            "user_daily_sandbox_seconds=720, global_active_lease_limit=2 where id=1"
        )

        stale_user, stale_project_a = _create_identity(connection, "stale-cross-project")
        stale_project_b = str(uuid4())
        connection.execute(
            "insert into public.projects (id,user_id,name) values (%s,%s,'second-project')",
            (stale_project_b, stale_user),
        )
        stale_task = _create_task(
            connection, stale_user, stale_project_a, "stale-project-a"
        )["task"]
        connection.execute(
            "update public.code_tasks set source_ref=%s, base_revision=%s where id=%s",
            ("a" * 40, "a" * 40, stale_task["id"]),
        )
        stale_accepted = _accept(dsn, stale_user, stale_task["id"], str(uuid4()))
        if stale_accepted.get("accepted") is not True:
            raise AssertionError(stale_accepted)
        connection.execute(
            "update public.code_tasks set expires_at=now()-interval '1 second' where id=%s",
            (stale_task["id"],),
        )
        replacement_task = _create_task(
            connection, stale_user, stale_project_b, "replacement-project-b"
        )["task"]
        connection.execute(
            "update public.code_tasks set source_ref=%s, base_revision=%s where id=%s",
            ("a" * 40, "a" * 40, replacement_task["id"]),
        )
        replacement_accepted = _accept(
            dsn, stale_user, replacement_task["id"], str(uuid4())
        )
        if replacement_accepted.get("accepted") is not True:
            raise AssertionError(replacement_accepted)
        stale_state = _scalar(
            connection,
            "select jsonb_build_object('status',status,'failure',failure_code,"
            "'payment',payment_source) from public.code_tasks where id=%s",
            (stale_task["id"],),
        )
        if stale_state != {
            "status": "cancelled",
            "failure": "CODE_TASK_EXPIRED",
            "payment": "refund_pending",
        }:
            raise AssertionError(stale_state)
        if _scalar(
            connection,
            "select count(*) from public.code_task_events where task_id=%s "
            "and event_type='task.cancelled' and payload->>'failureCode'='CODE_TASK_EXPIRED'",
            (stale_task["id"],),
        ) != 1:
            raise AssertionError("expired cross-Project task was not reconciled exactly once")
        connection.execute(
            "update public.code_tasks set status='completed', completed_at=now() where id=%s",
            (replacement_task["id"],),
        )

        retry_user, retry_project = _create_identity(connection, "retry-limit-five")
        retry_task = _create_task(
            connection, retry_user, retry_project, "retry-limit-five", max_duration_seconds=30
        )["task"]
        connection.execute(
            "update public.code_tasks set source_ref=%s, base_revision=%s where id=%s",
            ("a" * 40, "a" * 40, retry_task["id"]),
        )
        retry_accepted = _accept(dsn, retry_user, retry_task["id"], str(uuid4()))
        if retry_accepted.get("accepted") is not True:
            raise AssertionError(retry_accepted)
        connection.execute(
            "update public.code_tasks set attempt_count=5,max_attempts=5,status='provisioning',"
            "lease_token=%s,lease_expires_at=now()-interval '1 second' where id=%s",
            (str(uuid4()), retry_task["id"]),
        )
        connection.execute(
            "insert into public.code_guardrail_receipts "
            "(task_id,user_id,budget_day,receipt_kind,attempt_number,declared_sandbox_seconds) "
            "select %s,%s,(current_timestamp at time zone 'UTC')::date,'model_start',"
            "attempt,30 from generate_series(1,5) as attempts(attempt)",
            (retry_task["id"], retry_user),
        )
        connection.execute(
            "update public.code_guardrail_global_daily_facts set model_start_count=5,"
            "declared_sandbox_seconds=150,updated_at=now() "
            "where budget_day=(current_timestamp at time zone 'UTC')::date"
        )
        retry_facts_before = _scalar(
            connection,
            "select jsonb_build_array(model_start_count,declared_sandbox_seconds) "
            "from public.code_guardrail_global_daily_facts "
            "where budget_day=(current_timestamp at time zone 'UTC')::date",
        )
        retry_terminalized = _scalar(
            connection,
            "select public.claim_code_task_guarded(225,%s)",
            (str(uuid4()),),
        )
        if not (
            retry_terminalized.get("handled") is True
            and retry_terminalized.get("terminalized") is True
            and retry_terminalized.get("claimed") is False
            and retry_terminalized.get("reason") == "retry_limit_exhausted"
        ):
            raise AssertionError(retry_terminalized)
        if retry_terminalized["task"]["attempt_count"] != 5:
            raise AssertionError(retry_terminalized)
        retry_facts_after = _scalar(
            connection,
            "select jsonb_build_array(model_start_count,declared_sandbox_seconds) "
            "from public.code_guardrail_global_daily_facts "
            "where budget_day=(current_timestamp at time zone 'UTC')::date",
        )
        if retry_facts_after != retry_facts_before:
            raise AssertionError((retry_facts_before, retry_facts_after))
        if _scalar(
            connection,
            "select count(*) from public.code_guardrail_receipts where task_id=%s "
            "and receipt_kind='model_start'",
            (retry_task["id"],),
        ) != 5:
            raise AssertionError("retry exhaustion reserved an extra compute attempt")
        retry_state = _scalar(
            connection,
            "select jsonb_build_object('status',status,'failure',failure_code,"
            "'payment',payment_source) from public.code_tasks where id=%s",
            (retry_task["id"],),
        )
        if retry_state != {
            "status": "failed",
            "failure": "CODE_RETRY_LIMIT",
            "payment": "refund_pending",
        }:
            raise AssertionError(retry_state)

        connection.execute(
            "update public.code_guardrail_global_daily_facts set model_start_count=0,"
            "declared_sandbox_seconds=240,updated_at=now() "
            "where budget_day=(current_timestamp at time zone 'UTC')::date"
        )
        connection.execute(
            "update public.code_guardrail_limits set global_daily_model_start_limit=24,"
            "global_daily_sandbox_seconds=300,user_daily_sandbox_seconds=720 where id=1"
        )
        large_user, large_project = _create_identity(connection, "large-first")
        small_user, small_project = _create_identity(connection, "small-fitting")
        large_task = _create_task(
            connection,
            large_user,
            large_project,
            "large-first",
            max_duration_seconds=240,
        )["task"]
        small_task = _create_task(
            connection,
            small_user,
            small_project,
            "small-fitting",
            max_duration_seconds=30,
        )["task"]
        for task_row, user_id in ((large_task, large_user), (small_task, small_user)):
            connection.execute(
                "update public.code_tasks set source_ref=%s, base_revision=%s where id=%s",
                ("a" * 40, "a" * 40, task_row["id"]),
            )
            accepted = _accept(dsn, user_id, task_row["id"], str(uuid4()))
            if accepted.get("accepted") is not True:
                raise AssertionError(accepted)
        fitting_claim = _scalar(
            connection,
            "select public.claim_code_task_guarded(225,%s)",
            (str(uuid4()),),
        )
        if fitting_claim.get("claimed") is not True:
            raise AssertionError(fitting_claim)
        if fitting_claim["task"]["id"] != small_task["id"]:
            raise AssertionError((fitting_claim, large_task, small_task))
        connection.execute(
            "update public.code_tasks set status='completed',completed_at=now(),"
            "lease_token=null,lease_expires_at=null where id=%s",
            (small_task["id"],),
        )
        no_fitting_claim = _scalar(
            connection,
            "select public.claim_code_task_guarded(225,%s)",
            (str(uuid4()),),
        )
        if no_fitting_claim.get("reason") != "global_daily_sandbox_seconds":
            raise AssertionError(no_fitting_claim)
        if no_fitting_claim.get("capacityState") != "no_fitting_task":
            raise AssertionError(no_fitting_claim)
        if int(no_fitting_claim.get("retryAfterSeconds") or 0) <= 0:
            raise AssertionError(no_fitting_claim)
        connection.execute(
            "update public.code_guardrail_global_daily_facts set "
            "declared_sandbox_seconds=300,updated_at=now() "
            "where budget_day=(current_timestamp at time zone 'UTC')::date"
        )
        exhausted_claim = _scalar(
            connection,
            "select public.claim_code_task_guarded(225,%s)",
            (str(uuid4()),),
        )
        if not (
            exhausted_claim.get("reason") == "global_daily_sandbox_seconds"
            and exhausted_claim.get("capacityState") == "exhausted"
        ):
            raise AssertionError(exhausted_claim)

    print(
        json.dumps(
            {
                "status": "passed",
                "queueRaceCreated": created_count,
                "queueRaceDeferred": deferred_count,
                "globalQueueRaceCreated": global_created,
                "globalQueueRaceDeferred": global_deferred,
                "acceptRaceAccepted": 1,
                "acceptRaceDeferred": 1,
                "fairClaimSelectedNeverServed": True,
                "activeLeaseDeferred": True,
                "userSandboxBudgetDeferred": True,
                "globalSandboxBudgetDeferred": True,
                "globalModelStartBudgetDeferred": True,
                "userDailyAcceptDeferred": True,
                "globalDailyAcceptDeferred": True,
                "createReplaySingular": True,
                "directInsertRejected": direct_insert_rejected,
                "crossOwnerProjectRejected": True,
                "globalFactsSurviveUserDeletion": True,
                "expiredCrossProjectTaskReconciled": True,
                "retryLimitFiveTerminalizedBeforeCompute": True,
                "smallFittingTaskBypassedOversizedTask": True,
                "noFittingTaskDeferredUntilUtcReset": True,
                "exhaustedCapacityDistinguished": True,
                "database": "owned-loopback-disposable",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
