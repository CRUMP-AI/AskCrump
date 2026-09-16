"""Verify Autonomous Crump atomic dispatch on an owned disposable PostgreSQL 15.

The harness refuses directly addressed non-loopback servers and requires an exact
operator attestation because a loopback address could still front a proxy or tunnel.
It creates and drops a uniquely named database, applies the repository migration
ledger through the atomic-dispatch target, and exercises privileges, idempotency,
concurrency, receipts, worker visibility, and rollback with real transactions.
"""

from __future__ import annotations

import ipaddress
import os
import sys
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg
from psycopg import ClientCursor, sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.types.json import Jsonb


ROOT = Path(__file__).resolve().parents[1]
MIGRATION_TARGET = "20260916231500_autonomous_crump_atomic_dispatch.sql"
ADMIN_URL_ENV = "ASKCRUMP_POSTGRES_ADMIN_URL"
ATTESTATION_ENV = "ASKCRUMP_DISPOSABLE_POSTGRES_ACK"
ATTESTATION_VALUE = "I_OWN_THIS_DISPOSABLE_LOCAL_CLUSTER"
DATABASE_PREFIX = "askcrump_autonomous_atomic_"
REVISION = "a" * 40
OTHER_REVISION = "b" * 40
INCLUDED_LIMIT = 3
CREDIT_COST = 12
ROLE_OPTIONS = {
    "anon": sql.SQL("NOLOGIN NOINHERIT"),
    "authenticated": sql.SQL("NOLOGIN NOINHERIT"),
    "service_role": sql.SQL("NOLOGIN NOINHERIT BYPASSRLS"),
}


@dataclass
class DisposableDatabaseState:
    database_name: str
    database_created: bool = False
    created_roles: list[str] = field(default_factory=list)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def is_loopback_host(raw_host: str | None) -> bool:
    if not raw_host or "," in raw_host:
        return False
    host = raw_host.strip().strip("[]").lower()
    if host == "localhost":
        return True
    try:
        if "/" not in host:
            return ipaddress.ip_address(host).is_loopback
        interface = ipaddress.ip_interface(host)
        return interface.ip.is_loopback and interface.network.prefixlen == interface.max_prefixlen
    except ValueError:
        return False


def validate_disposable_attestation() -> None:
    if os.environ.get(ATTESTATION_ENV) != ATTESTATION_VALUE:
        raise RuntimeError(
            f"Set {ATTESTATION_ENV}={ATTESTATION_VALUE} only after confirming the endpoint is "
            "an owned disposable local cluster and not a loopback proxy or tunnel."
        )


def validate_admin_connection(admin_url: str) -> None:
    params = conninfo_to_dict(admin_url)
    raw_host = params.get("hostaddr") or params.get("host")
    if not is_loopback_host(raw_host):
        raise RuntimeError(
            f"{ADMIN_URL_ENV} must name exactly one explicit loopback host "
            "(localhost, 127.0.0.1, or ::1); directly addressed remote endpoints are refused."
        )

    with psycopg.connect(admin_url, autocommit=True) as connection:
        server_address, current_user, version_number = connection.execute(
            "select inet_server_addr()::text, current_user, "
            "current_setting('server_version_num')::integer"
        ).fetchone()
        require(
            server_address is not None and is_loopback_host(str(server_address)),
            f"PostgreSQL reported non-loopback server address {server_address!r}; refusing to run.",
        )
        require(
            current_user == "postgres",
            "The harness requires the local postgres superuser to own and clean up its database.",
        )
        require(
            150000 <= version_number < 160000,
            f"This gate requires PostgreSQL 15 exactly; server_version_num={version_number}.",
        )


def create_disposable_database(admin_url: str, state: DisposableDatabaseState) -> str:
    with psycopg.connect(admin_url, autocommit=True) as admin:
        for role_name, options in ROLE_OPTIONS.items():
            existing = admin.execute(
                "select rolbypassrls from pg_roles where rolname = %s", (role_name,)
            ).fetchone()
            if existing is None:
                admin.execute(
                    sql.SQL("create role {} {}").format(sql.Identifier(role_name), options)
                )
                state.created_roles.append(role_name)
            elif role_name == "service_role":
                require(
                    existing[0] is True,
                    "Existing local service_role lacks BYPASSRLS; refusing to mutate a shared role.",
                )

        admin.execute(
            sql.SQL("create database {} template template0").format(
                sql.Identifier(state.database_name)
            )
        )
        state.database_created = True
    return make_conninfo(admin_url, dbname=state.database_name)


def bootstrap_supabase_compatibility(test_url: str) -> None:
    statements = """
    grant usage on schema public to anon, authenticated, service_role;
    alter default privileges for role postgres in schema public
      grant all on tables to service_role;
    alter default privileges for role postgres in schema public
      grant all on sequences to service_role;
    alter default privileges for role postgres in schema public
      grant execute on functions to service_role;

    create schema storage;
    create table storage.buckets (
      id text primary key,
      name text not null,
      public boolean not null default false,
      file_size_limit bigint,
      allowed_mime_types text[]
    );
    """
    with psycopg.connect(test_url, autocommit=True) as connection:
        with ClientCursor(connection) as cursor:
            cursor.execute(statements)
            for _ in cursor.results():
                pass


def migration_files_through_target() -> list[Path]:
    files = sorted((ROOT / "migrations").glob("*.sql"), key=lambda path: path.name)
    names = [path.name for path in files]
    require(MIGRATION_TARGET in names, f"Missing migration target {MIGRATION_TARGET}.")
    return files[: names.index(MIGRATION_TARGET) + 1]


def apply_migrations(test_url: str) -> list[Path]:
    migration_files = migration_files_through_target()
    with psycopg.connect(test_url, autocommit=True) as connection:
        for migration in migration_files:
            try:
                with ClientCursor(connection) as cursor:
                    cursor.execute(migration.read_text(encoding="utf-8"))
                    for _ in cursor.results():
                        pass
            except Exception as exc:
                raise RuntimeError(f"Migration failed: {migration.name}") from exc
    return migration_files


def role_connection(test_url: str, role: str) -> psycopg.Connection:
    connection = psycopg.connect(test_url, autocommit=True)
    connection.execute("set statement_timeout = '15s'")
    connection.execute(sql.SQL("set role {}").format(sql.Identifier(role)))
    return connection


def accept_run(
    test_url: str,
    *,
    task_id: uuid.UUID,
    user_id: uuid.UUID,
    dispatch_token: uuid.UUID,
    revision: str = REVISION,
    action_key: str = "",
    confirmed_max: int = 0,
) -> dict:
    with role_connection(test_url, "service_role") as connection:
        return connection.execute(
            """
            select public.accept_code_task_run(%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                task_id,
                user_id,
                dispatch_token,
                revision,
                INCLUDED_LIMIT,
                CREDIT_COST,
                action_key,
                confirmed_max,
            ),
        ).fetchone()[0]


def claim_run(test_url: str, claim_token: uuid.UUID) -> dict | None:
    with role_connection(test_url, "service_role") as connection:
        row = connection.execute(
            """
            select to_jsonb(claimed)
            from public.claim_code_task(%s, %s) as claimed
            """,
            (120, claim_token),
        ).fetchone()
        return None if row is None else row[0]


def assert_permission_denied(
    test_url: str,
    role: str,
    statement: str,
    parameters: tuple,
    label: str,
) -> None:
    with role_connection(test_url, role) as connection:
        try:
            connection.execute(statement, parameters).fetchone()
        except psycopg.errors.InsufficientPrivilege:
            return
    raise AssertionError(f"{label} unexpectedly executed as {role}.")


def verify_schema_and_privileges(test_url: str) -> None:
    with psycopg.connect(test_url, autocommit=True) as connection:
        functions = connection.execute(
            """
            select
              p.proname,
              p.prosecdef,
              p.proconfig,
              pg_get_function_result(p.oid),
              has_function_privilege('service_role', p.oid, 'EXECUTE'),
              has_function_privilege('anon', p.oid, 'EXECUTE'),
              has_function_privilege('authenticated', p.oid, 'EXECUTE'),
              array(
                select case
                  when acl.grantee = 0 then 'PUBLIC'
                  else pg_get_userbyid(acl.grantee)
                end
                from aclexplode(coalesce(p.proacl, acldefault('f', p.proowner))) acl
                where acl.privilege_type = 'EXECUTE'
                order by 1
              ) as execute_grantees,
              exists (
                select 1
                from aclexplode(coalesce(p.proacl, acldefault('f', p.proowner))) acl
                where acl.grantee = 0 and acl.privilege_type = 'EXECUTE'
              ) as public_can_execute
            from pg_proc p
            where p.oid = 'public.accept_code_task_run(uuid,uuid,uuid,text,integer,integer,text,integer)'::regprocedure
            """
        ).fetchall()
        require(len(functions) == 1, "Atomic acceptance function must exist exactly once.")
        (
            function_name,
            security_definer,
            configuration,
            result_type,
            service_can_execute,
            anon_can_execute,
            authenticated_can_execute,
            execute_grantees,
            public_can_execute,
        ) = functions[0]
        require(function_name == "accept_code_task_run", "Unexpected atomic function identity.")
        require(not security_definer, "Atomic acceptance must remain SECURITY INVOKER.")
        require(result_type == "jsonb", "Atomic acceptance must return jsonb.")
        require(
            configuration is not None and 'search_path=""' in configuration,
            "Atomic acceptance must pin an empty search_path.",
        )
        require(service_can_execute, "service_role cannot execute atomic acceptance.")
        require(not anon_can_execute, "anon can execute atomic acceptance.")
        require(not authenticated_can_execute, "authenticated can execute atomic acceptance.")
        require(
            execute_grantees == ["postgres", "service_role"],
            f"Unexpected atomic execute grantees: {execute_grantees!r}.",
        )
        require(not public_can_execute, "PUBLIC can execute atomic acceptance.")

        legacy = connection.execute(
            """
            select
              has_function_privilege('service_role', p.oid, 'EXECUTE'),
              has_function_privilege('anon', p.oid, 'EXECUTE'),
              has_function_privilege('authenticated', p.oid, 'EXECUTE'),
              exists (
                select 1
                from aclexplode(coalesce(p.proacl, acldefault('f', p.proowner))) acl
                where acl.grantee = 0 and acl.privilege_type = 'EXECUTE'
              )
            from pg_proc p
            where p.oid = 'public.dispatch_code_task(uuid,uuid,uuid,jsonb,text,integer)'::regprocedure
            """
        ).fetchone()
        require(
            legacy == (False, False, False, False), f"Legacy dispatch remains callable: {legacy!r}."
        )

    function_sql = "select public.accept_code_task_run(%s, %s, %s, %s, %s, %s, %s, %s)"
    arguments = (
        uuid.uuid4(),
        uuid.uuid4(),
        uuid.uuid4(),
        REVISION,
        INCLUDED_LIMIT,
        CREDIT_COST,
        "denied-probe",
        CREDIT_COST,
    )
    for role in ("anon", "authenticated"):
        assert_permission_denied(test_url, role, function_sql, arguments, "atomic acceptance")
    assert_permission_denied(
        test_url,
        "service_role",
        "select * from public.dispatch_code_task(%s, %s, %s, %s, %s, %s)",
        (uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), Jsonb({}), "included", 0),
        "legacy dispatch",
    )


def seed_account(
    admin: psycopg.Connection,
    label: str,
    *,
    balance: int = 0,
    internal_tier: str | None = None,
) -> tuple[uuid.UUID, uuid.UUID]:
    user_id = uuid.uuid4()
    project_id = uuid.uuid4()
    admin.execute(
        """
        insert into public.users (
          id, email, password_hash, is_verified, internal_tier
        ) values (%s, %s, 'atomic-probe-password', true, %s)
        """,
        (user_id, f"{label}-{uuid.uuid4().hex}@example.test", internal_tier),
    )
    admin.execute(
        """
        insert into public.credit_accounts (
          user_id, balance, lifetime_granted, lifetime_spent
        ) values (%s, %s, %s, 0)
        on conflict (user_id) do update
        set balance = excluded.balance,
            lifetime_granted = excluded.lifetime_granted,
            lifetime_spent = 0
        """,
        (user_id, balance, balance),
    )
    admin.execute(
        "insert into public.projects (id, user_id, name) values (%s, %s, %s)",
        (project_id, user_id, f"Atomic probe {label}"),
    )
    return user_id, project_id


def seed_task(
    admin: psycopg.Connection,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    label: str,
    *,
    status: str = "queued",
    expires_at: datetime | None = None,
) -> uuid.UUID:
    task_id = uuid.uuid4()
    admin.execute(
        """
        insert into public.code_tasks (
          id, user_id, project_id, objective, mode, source_repo_url,
          source_ref, base_revision, status, expires_at
        ) values (%s, %s, %s, %s, 'implement', %s, %s, %s, %s, %s)
        """,
        (
            task_id,
            user_id,
            project_id,
            f"Atomic dispatch probe {label}",
            "https://github.com/example/atomic-probe",
            REVISION,
            REVISION,
            status,
            expires_at or datetime.now(timezone.utc) + timedelta(hours=1),
        ),
    )
    return task_id


def seed_usage(admin: psycopg.Connection, user_id: uuid.UUID, count: int) -> None:
    for position in range(count):
        admin.execute(
            """
            insert into public.usage_events (user_id, event_type, metadata)
            values (%s, 'feature:code_workspace', %s)
            """,
            (user_id, Jsonb({"probeSeed": position + 1})),
        )


def counts(
    admin: psycopg.Connection,
    user_id: uuid.UUID,
) -> tuple[int, int, int]:
    usage = admin.execute(
        """
        select count(*) from public.usage_events
        where user_id = %s and event_type = 'feature:code_workspace'
        """,
        (user_id,),
    ).fetchone()[0]
    spends = admin.execute(
        """
        select count(*) from public.credit_ledger
        where user_id = %s and provider = 'feature-spend' and delta < 0
        """,
        (user_id,),
    ).fetchone()[0]
    claims = admin.execute(
        """
        select count(*) from public.code_task_events
        where user_id = %s and event_type = 'task.claimed'
        """,
        (user_id,),
    ).fetchone()[0]
    return usage, spends, claims


def task_state(admin: psycopg.Connection, task_id: uuid.UUID) -> tuple:
    return admin.execute(
        """
        select status, dispatch_token, usage_receipt, payment_source, credits_spent
        from public.code_tasks where id = %s
        """,
        (task_id,),
    ).fetchone()


def probe_not_ready_paths(admin: psycopg.Connection, test_url: str) -> None:
    user_id, project_id = seed_account(admin, "not-ready", balance=48)
    mismatch = seed_task(admin, user_id, project_id, "sha-mismatch")
    expired = seed_task(
        admin,
        user_id,
        project_id,
        "expired",
        expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
    )
    completed = seed_task(admin, user_id, project_id, "completed", status="completed")

    cases = (
        (mismatch, OTHER_REVISION),
        (expired, REVISION),
        (completed, REVISION),
    )
    for task_id, revision in cases:
        result = accept_run(
            test_url,
            task_id=task_id,
            user_id=user_id,
            dispatch_token=uuid.uuid4(),
            revision=revision,
        )
        require(
            result == {"accepted": False, "reason": "task_not_ready"},
            (f"Not-ready probe returned an unexpected result: {result!r}."),
        )
    missing = accept_run(
        test_url,
        task_id=uuid.uuid4(),
        user_id=user_id,
        dispatch_token=uuid.uuid4(),
    )
    require(
        missing == {"accepted": False, "reason": "task_not_ready"},
        (f"Missing-task probe returned an unexpected result: {missing!r}."),
    )
    require(counts(admin, user_id) == (0, 0, 0), "A not-ready path created billing/audit facts.")
    for task_id, expected_status in (
        (mismatch, "queued"),
        (expired, "queued"),
        (completed, "completed"),
    ):
        state = task_state(admin, task_id)
        require(
            state == (expected_status, None, None, None, 0),
            (f"Not-ready task {task_id} changed state: {state!r}."),
        )


def probe_receipt_replay_and_worker(admin: psycopg.Connection, test_url: str) -> None:
    user_id, project_id = seed_account(admin, "receipt-worker", balance=24)
    task_id = seed_task(admin, user_id, project_id, "receipt-worker")
    require(claim_run(test_url, uuid.uuid4()) is None, "Queued unpaid work was worker-claimable.")

    dispatch_token = uuid.uuid4()
    first = accept_run(
        test_url,
        task_id=task_id,
        user_id=user_id,
        dispatch_token=dispatch_token,
    )
    replay = accept_run(
        test_url,
        task_id=task_id,
        user_id=user_id,
        dispatch_token=dispatch_token,
    )
    require(first["accepted"] is True and first["replayed"] is False, "Initial acceptance failed.")
    require(replay["accepted"] is True and replay["replayed"] is True, "Token replay failed.")
    require(first["task"]["id"] == replay["task"]["id"] == str(task_id), "Replay task drifted.")
    require(
        first["task"]["dispatch_token"] == replay["task"]["dispatch_token"] == str(dispatch_token),
        ("The exact private dispatch owner token was not retained."),
    )
    receipt = first["task"]["usage_receipt"]
    require(receipt == replay["task"]["usage_receipt"], "Replay returned a different receipt.")
    require(receipt["feature"] == "code_workspace", "Receipt feature identity drifted.")
    require(receipt["paymentSource"] == "included", "Included receipt source drifted.")
    require(receipt["creditsSpent"] == 0 and receipt["used"] == 1, "Included receipt is incorrect.")
    require(
        receipt["limit"] == INCLUDED_LIMIT and receipt["eventId"], "Included receipt lacks proof."
    )
    require(counts(admin, user_id) == (1, 0, 1), "Replay duplicated usage, spend, or claim.")

    persisted = task_state(admin, task_id)
    require(persisted[0] == "provisioning", "Accepted task is not provisioning.")
    require(persisted[1] == dispatch_token, "Persisted owner token differs from the caller token.")
    require(persisted[2] == receipt, "Persisted receipt differs from the returned receipt.")

    claim_token = uuid.uuid4()
    claimed = claim_run(test_url, claim_token)
    replayed_claim = claim_run(test_url, claim_token)
    require(claimed is not None and replayed_claim is not None, "Accepted work was not claimable.")
    require(claimed["id"] == replayed_claim["id"] == str(task_id), "Worker claim replay drifted.")
    require(
        claimed["dispatch_token"] == str(dispatch_token), "Worker lost the dispatch owner token."
    )
    require(
        claimed["lease_token"] == replayed_claim["lease_token"] == str(claim_token),
        ("Worker lease token was not replay-safe."),
    )
    require(
        claimed["attempt_count"] == replayed_claim["attempt_count"] == 1,
        ("Worker replay incremented the attempt count."),
    )
    admin.execute("update public.code_tasks set status = 'completed' where id = %s", (task_id,))


def concurrent_accepts(test_url: str, calls: list[dict]) -> tuple[list[dict], list[int]]:
    barrier = threading.Barrier(len(calls) + 1)

    def invoke(call: dict) -> tuple[dict, int]:
        with role_connection(test_url, "service_role") as connection:
            backend_pid = connection.execute("select pg_backend_pid()").fetchone()[0]
            barrier.wait(timeout=10)
            result = connection.execute(
                "select public.accept_code_task_run(%s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    call["task_id"],
                    call["user_id"],
                    call["dispatch_token"],
                    call.get("revision", REVISION),
                    INCLUDED_LIMIT,
                    CREDIT_COST,
                    call.get("action_key", ""),
                    call.get("confirmed_max", 0),
                ),
            ).fetchone()[0]
            return result, backend_pid

    with ThreadPoolExecutor(max_workers=len(calls)) as executor:
        futures = [executor.submit(invoke, call) for call in calls]
        barrier.wait(timeout=10)
        completed = [future.result(timeout=20) for future in futures]
    results = [item[0] for item in completed]
    backend_pids = [item[1] for item in completed]
    require(len(set(backend_pids)) == len(calls), "Concurrency probe reused a database session.")
    return results, backend_pids


def probe_same_task_concurrency(admin: psycopg.Connection, test_url: str) -> None:
    user_id, project_id = seed_account(admin, "same-task-race")
    task_id = seed_task(admin, user_id, project_id, "same-task-race")
    results, _ = concurrent_accepts(
        test_url,
        [
            {"task_id": task_id, "user_id": user_id, "dispatch_token": uuid.uuid4()},
            {"task_id": task_id, "user_id": user_id, "dispatch_token": uuid.uuid4()},
        ],
    )
    accepted = [result for result in results if result.get("accepted") is True]
    rejected = [result for result in results if result.get("accepted") is False]
    require(len(accepted) == 1, f"Same-task race accepted {len(accepted)} calls.")
    require(
        rejected == [{"accepted": False, "reason": "task_not_ready"}],
        (f"Same-task loser did not fail closed: {rejected!r}."),
    )
    require(counts(admin, user_id) == (1, 0, 1), "Same-task race duplicated accounting.")
    admin.execute("update public.code_tasks set status = 'completed' where id = %s", (task_id,))


def probe_last_included_slot_concurrency(admin: psycopg.Connection, test_url: str) -> None:
    user_id, project_id = seed_account(admin, "last-slot")
    seed_usage(admin, user_id, INCLUDED_LIMIT - 1)
    task_ids = [
        seed_task(admin, user_id, project_id, "last-slot-a"),
        seed_task(admin, user_id, project_id, "last-slot-b"),
    ]
    results, _ = concurrent_accepts(
        test_url,
        [
            {"task_id": task_ids[0], "user_id": user_id, "dispatch_token": uuid.uuid4()},
            {"task_id": task_ids[1], "user_id": user_id, "dispatch_token": uuid.uuid4()},
        ],
    )
    accepted = [result for result in results if result.get("accepted") is True]
    rejected = [result for result in results if result.get("accepted") is False]
    require(len(accepted) == 1, f"Last included slot accepted {len(accepted)} tasks.")
    require(
        len(rejected) == 1 and rejected[0]["reason"] == "credit_confirmation_required",
        (f"Last-slot loser did not require confirmation: {rejected!r}."),
    )
    require(
        counts(admin, user_id) == (INCLUDED_LIMIT, 0, 1),
        ("Last-slot concurrency duplicated allowance or claim facts."),
    )
    statuses = admin.execute(
        "select status, count(*) from public.code_tasks where id = any(%s) group by status",
        (task_ids,),
    ).fetchall()
    require(
        sorted(statuses) == [("provisioning", 1), ("queued", 1)],
        (f"Last-slot task states are incorrect: {statuses!r}."),
    )
    admin.execute(
        "update public.code_tasks set status = 'completed' where id = any(%s) and status <> 'queued'",
        (task_ids,),
    )


def probe_credit_replay(admin: psycopg.Connection, test_url: str) -> None:
    user_id, project_id = seed_account(admin, "credit-replay", balance=24)
    seed_usage(admin, user_id, INCLUDED_LIMIT)
    task_id = seed_task(admin, user_id, project_id, "credit-replay")
    dispatch_token = uuid.uuid4()
    action_key = f"credit-replay-{uuid.uuid4()}"
    first = accept_run(
        test_url,
        task_id=task_id,
        user_id=user_id,
        dispatch_token=dispatch_token,
        action_key=action_key,
        confirmed_max=CREDIT_COST,
    )
    replay = accept_run(
        test_url,
        task_id=task_id,
        user_id=user_id,
        dispatch_token=dispatch_token,
        action_key=action_key,
        confirmed_max=CREDIT_COST,
    )
    require(first["accepted"] is True and first["replayed"] is False, "Credit acceptance failed.")
    require(replay["accepted"] is True and replay["replayed"] is True, "Credit replay failed.")
    receipt = first["task"]["usage_receipt"]
    require(receipt == replay["task"]["usage_receipt"], "Credit replay changed its receipt.")
    require(receipt["paymentSource"] == "credits", "Credit receipt source drifted.")
    require(receipt["creditsSpent"] == CREDIT_COST, "Credit receipt amount drifted.")
    require(str(receipt["eventId"]).startswith("credit:"), "Credit receipt lacks ledger identity.")
    require(counts(admin, user_id) == (INCLUDED_LIMIT, 1, 1), "Credit replay duplicated facts.")
    balance, lifetime_spent = admin.execute(
        "select balance, lifetime_spent from public.credit_accounts where user_id = %s",
        (user_id,),
    ).fetchone()
    require((balance, lifetime_spent) == (12, 12), "Credit replay deducted more than once.")
    admin.execute("update public.code_tasks set status = 'completed' where id = %s", (task_id,))


def probe_credit_denials(admin: psycopg.Connection, test_url: str) -> None:
    cases = (
        ("confirmation", 24, 0, "credit_confirmation_required"),
        ("balance", 5, 12, "credits_required"),
    )
    for label, balance, confirmed_max, expected_reason in cases:
        user_id, project_id = seed_account(admin, f"credit-denial-{label}", balance=balance)
        seed_usage(admin, user_id, INCLUDED_LIMIT)
        task_id = seed_task(admin, user_id, project_id, f"credit-denial-{label}")
        result = accept_run(
            test_url,
            task_id=task_id,
            user_id=user_id,
            dispatch_token=uuid.uuid4(),
            action_key=f"credit-denial-{label}-{uuid.uuid4()}",
            confirmed_max=confirmed_max,
        )
        require(
            result["accepted"] is False and result["reason"] == expected_reason,
            (f"{label} denial returned {result!r}."),
        )
        require(
            counts(admin, user_id) == (INCLUDED_LIMIT, 0, 0),
            (f"{label} denial created a spend or claim."),
        )
        require(
            task_state(admin, task_id) == ("queued", None, None, None, 0),
            (f"{label} denial transitioned the task."),
        )
        saved_balance = admin.execute(
            "select balance from public.credit_accounts where user_id = %s", (user_id,)
        ).fetchone()[0]
        require(saved_balance == balance, f"{label} denial changed the balance.")


def install_post_charge_failure(admin: psycopg.Connection) -> None:
    admin.execute(
        """
        create or replace function public.autonomous_atomic_probe_reject_update()
        returns trigger language plpgsql set search_path = '' as $$
        begin
          if old.status = 'queued' and new.status = 'provisioning' then
            raise exception 'injected post-charge task update failure';
          end if;
          return new;
        end;
        $$
        """
    )
    admin.execute(
        "drop trigger if exists autonomous_atomic_probe_reject_update on public.code_tasks"
    )
    admin.execute(
        """
        create trigger autonomous_atomic_probe_reject_update
        before update on public.code_tasks
        for each row execute function public.autonomous_atomic_probe_reject_update()
        """
    )


def remove_post_charge_failure(admin: psycopg.Connection) -> None:
    admin.execute(
        "drop trigger if exists autonomous_atomic_probe_reject_update on public.code_tasks"
    )
    admin.execute("drop function if exists public.autonomous_atomic_probe_reject_update()")


def expect_injected_failure(**accept_kwargs) -> None:
    try:
        accept_run(**accept_kwargs)
    except psycopg.errors.RaiseException as exc:
        require(
            "injected post-charge task update failure" in str(exc),
            (f"Unexpected injected failure: {exc}."),
        )
        return
    raise AssertionError("Injected post-charge task update failure did not abort acceptance.")


def probe_post_charge_rollbacks(admin: psycopg.Connection, test_url: str) -> None:
    allowance_user, allowance_project = seed_account(admin, "rollback-allowance")
    allowance_task = seed_task(admin, allowance_user, allowance_project, "rollback-allowance")
    install_post_charge_failure(admin)
    try:
        expect_injected_failure(
            test_url=test_url,
            task_id=allowance_task,
            user_id=allowance_user,
            dispatch_token=uuid.uuid4(),
        )
    finally:
        remove_post_charge_failure(admin)
    require(counts(admin, allowance_user) == (0, 0, 0), "Failed update retained allowance facts.")
    require(
        task_state(admin, allowance_task) == ("queued", None, None, None, 0),
        ("Failed update retained an allowance task transition."),
    )

    credit_user, credit_project = seed_account(admin, "rollback-credit", balance=24)
    seed_usage(admin, credit_user, INCLUDED_LIMIT)
    credit_task = seed_task(admin, credit_user, credit_project, "rollback-credit")
    install_post_charge_failure(admin)
    try:
        expect_injected_failure(
            test_url=test_url,
            task_id=credit_task,
            user_id=credit_user,
            dispatch_token=uuid.uuid4(),
            action_key=f"rollback-credit-{uuid.uuid4()}",
            confirmed_max=CREDIT_COST,
        )
    finally:
        remove_post_charge_failure(admin)
    require(
        counts(admin, credit_user) == (INCLUDED_LIMIT, 0, 0),
        ("Failed update retained a credit ledger or claim fact."),
    )
    balance, lifetime_spent = admin.execute(
        "select balance, lifetime_spent from public.credit_accounts where user_id = %s",
        (credit_user,),
    ).fetchone()
    require((balance, lifetime_spent) == (24, 0), "Failed update retained the credit deduction.")
    require(
        task_state(admin, credit_task) == ("queued", None, None, None, 0),
        ("Failed update retained a credit task transition."),
    )


def probe_internal_tier(admin: psycopg.Connection, test_url: str) -> None:
    user_id, project_id = seed_account(
        admin, "internal-tier", balance=24, internal_tier="professional"
    )
    task_id = seed_task(admin, user_id, project_id, "internal-tier")
    result = accept_run(
        test_url,
        task_id=task_id,
        user_id=user_id,
        dispatch_token=uuid.uuid4(),
    )
    require(result["accepted"] is True, "Internal-tier task was not accepted.")
    receipt = result["task"]["usage_receipt"]
    require(receipt["paymentSource"] == "internal", "Internal receipt source drifted.")
    require(
        receipt["creditsSpent"] == 0 and receipt["internalAccess"] is True,
        ("Internal receipt recorded a paid or non-internal path."),
    )
    require(receipt["eventId"] is None, "Internal receipt unexpectedly references usage.")
    require(counts(admin, user_id) == (0, 0, 1), "Internal tier created usage or credit facts.")
    balance, lifetime_spent = admin.execute(
        "select balance, lifetime_spent from public.credit_accounts where user_id = %s",
        (user_id,),
    ).fetchone()
    require((balance, lifetime_spent) == (24, 0), "Internal tier changed credits.")
    admin.execute("update public.code_tasks set status = 'completed' where id = %s", (task_id,))


def run_probes(test_url: str) -> None:
    verify_schema_and_privileges(test_url)
    print("[pass] service-role-only atomic privilege and revoked legacy dispatch")
    with psycopg.connect(test_url, autocommit=True) as admin:
        probe_not_ready_paths(admin, test_url)
        print("[pass] pinned SHA, expiry, and task-readiness fail closed")
        probe_receipt_replay_and_worker(admin, test_url)
        print("[pass] exact receipt/owner token, replay, and worker visibility")
        probe_same_task_concurrency(admin, test_url)
        print("[pass] same-task concurrent tokens produce one acceptance")
        probe_last_included_slot_concurrency(admin, test_url)
        print("[pass] final included slot is serialized across tasks")
        probe_credit_replay(admin, test_url)
        print("[pass] exhausted allowance charges once and replays without duplication")
        probe_credit_denials(admin, test_url)
        print("[pass] confirmation and balance denials leave tasks and ledger untouched")
        probe_post_charge_rollbacks(admin, test_url)
        print("[pass] post-charge task-update failures roll back allowance and credits")
        probe_internal_tier(admin, test_url)
        print("[pass] internal-tier acceptance creates no usage or credit deduction")


def cleanup(admin_url: str, state: DisposableDatabaseState) -> list[str]:
    cleanup_errors: list[str] = []
    try:
        with psycopg.connect(admin_url, autocommit=True) as admin:
            if state.database_created:
                try:
                    admin.execute(
                        sql.SQL("drop database {} with (force)").format(
                            sql.Identifier(state.database_name)
                        )
                    )
                    state.database_created = False
                except Exception as exc:
                    cleanup_errors.append(f"database cleanup failed: {exc}")
            for role_name in reversed(state.created_roles):
                try:
                    admin.execute(
                        sql.SQL("drop role if exists {}").format(sql.Identifier(role_name))
                    )
                except Exception as exc:
                    cleanup_errors.append(f"role {role_name} cleanup failed: {exc}")
    except Exception as exc:
        cleanup_errors.append(f"cleanup connection failed: {exc}")
    return cleanup_errors


def main() -> int:
    admin_url = os.environ.get(ADMIN_URL_ENV, "").strip()
    if not admin_url:
        print(
            f"Set {ADMIN_URL_ENV} to an owned disposable loopback PostgreSQL 15 URL.",
            file=sys.stderr,
        )
        return 2

    validate_disposable_attestation()
    validate_admin_connection(admin_url)
    state = DisposableDatabaseState(database_name=f"{DATABASE_PREFIX}{uuid.uuid4().hex[:16]}")
    failure: BaseException | None = None
    try:
        test_url = create_disposable_database(admin_url, state)
        bootstrap_supabase_compatibility(test_url)
        migration_files = apply_migrations(test_url)
        print(
            f"[pass] applied {len(migration_files)} migrations through "
            f"{MIGRATION_TARGET} to {state.database_name}"
        )
        run_probes(test_url)
    except BaseException as exc:
        failure = exc
    finally:
        cleanup_errors = cleanup(admin_url, state)
        if cleanup_errors:
            for message in cleanup_errors:
                print(f"[cleanup-error] {message}", file=sys.stderr)
        else:
            print("[pass] disposable database and harness-created roles cleaned up")

    if failure is not None:
        raise failure.with_traceback(failure.__traceback__)
    if cleanup_errors:
        raise RuntimeError("; ".join(cleanup_errors))
    print("Autonomous Crump atomic dispatch PostgreSQL verification passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
