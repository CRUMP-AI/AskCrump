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


def _create_task(connection, user_id: str, project_id: str, label: str) -> dict:
    return _scalar(
        connection,
        "select public.create_code_task_guarded(%s,%s,%s,'implement',"
        "'https://github.com/openai/codex.git','main',180)",
        (user_id, project_id, label),
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

        queue_user, queue_project = _create_identity(connection, "queue-race")

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
        for index in range(4):
            global_user, global_project = _create_identity(
                connection, f"global-accept-{index}"
            )
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
                "database": "owned-loopback-disposable",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
