"""Exercise the atomic auth migration against an owned disposable PostgreSQL cluster.

The harness rejects directly addressed non-loopback servers and requires the operator to
attest that loopback is not a proxy or tunnel to somebody else's database. It creates and
later drops a uniquely named database, applies the repository migration ledger through the
atomic-auth target, and runs real multi-connection lock-ordering probes.
"""

from __future__ import annotations

import ipaddress
import os
import sys
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg
from psycopg import ClientCursor, sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.types.json import Jsonb


ROOT = Path(__file__).resolve().parents[1]
MIGRATION_TARGET = "20260916214309_atomic_auth_generation.sql"
ADMIN_URL_ENV = "ASKCRUMP_POSTGRES_ADMIN_URL"
ATTESTATION_ENV = "ASKCRUMP_DISPOSABLE_POSTGRES_ACK"
ATTESTATION_VALUE = "I_OWN_THIS_DISPOSABLE_LOCAL_CLUSTER"
DATABASE_PREFIX = "askcrump_atomic_auth_"
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
        return (
            interface.ip.is_loopback
            and interface.network.prefixlen == interface.max_prefixlen
        )
    except ValueError:
        return False


def validate_disposable_attestation() -> None:
    if os.environ.get(ATTESTATION_ENV) != ATTESTATION_VALUE:
        raise RuntimeError(
            f"Set {ATTESTATION_ENV}={ATTESTATION_VALUE} only after confirming the endpoint is an "
            "owned, disposable local cluster and not a loopback proxy or tunnel."
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
            "The disposable harness requires the local postgres superuser so it can create and "
            "drop a fresh database and Supabase-compatible test roles.",
        )
        require(
            version_number >= 150000,
            f"PostgreSQL 15 or newer is required; server_version_num={version_number}.",
        )


def create_disposable_database(
    admin_url: str,
    state: DisposableDatabaseState,
) -> str:
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

    test_url = make_conninfo(admin_url, dbname=state.database_name)
    return test_url


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
    target_index = names.index(MIGRATION_TARGET)
    return files[: target_index + 1]


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


def verify_schema_and_privileges(test_url: str) -> None:
    with psycopg.connect(test_url, autocommit=True) as connection:
        columns = {
            (table_name, column_name): (data_type, is_nullable, column_default)
            for table_name, column_name, data_type, is_nullable, column_default in connection.execute(
                """
                select table_name, column_name, data_type, is_nullable, column_default
                from information_schema.columns
                where table_schema = 'public'
                  and table_name in ('users', 'sessions')
                  and column_name = 'auth_generation'
                """
            ).fetchall()
        }
        require(len(columns) == 2, "users/sessions auth_generation columns were not both created.")
        for table_name in ("users", "sessions"):
            data_type, nullable, default = columns[(table_name, "auth_generation")]
            require(data_type == "bigint", f"{table_name}.auth_generation is not bigint.")
            require(nullable == "NO", f"{table_name}.auth_generation is nullable.")
            require(default is not None and default.startswith("0"), (
                f"{table_name}.auth_generation does not default to zero: {default!r}."
            ))

        constraints = {
            name: definition.lower()
            for name, definition in connection.execute(
                """
                select conname, pg_get_constraintdef(oid)
                from pg_constraint
                where connamespace = 'public'::regnamespace
                  and conname in (
                    'users_auth_generation_nonnegative',
                    'sessions_auth_generation_nonnegative'
                  )
                """
            ).fetchall()
        }
        require(len(constraints) == 2, "Both nonnegative auth-generation constraints are required.")
        require(
            all("auth_generation >= 0" in definition for definition in constraints.values()),
            "An auth-generation constraint has the wrong predicate.",
        )

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
            where p.pronamespace = 'public'::regnamespace
              and p.proname in ('persist_auth_session', 'consume_password_reset')
            order by p.proname
            """
        ).fetchall()
        require(len(functions) == 2, "Both atomic-auth functions must exist exactly once.")
        for (
            function_name,
            security_definer,
            configuration,
            result_type,
            service_can_execute,
            anon_can_execute,
            authenticated_can_execute,
            execute_grantees,
            public_can_execute,
        ) in functions:
            require(not security_definer, f"{function_name} must remain SECURITY INVOKER.")
            require(result_type == "jsonb", f"{function_name} must return jsonb.")
            require(
                configuration is not None and 'search_path=""' in configuration,
                f"{function_name} must pin an empty search_path.",
            )
            require(service_can_execute, f"service_role cannot execute {function_name}.")
            require(not anon_can_execute, f"anon can execute {function_name}.")
            require(not authenticated_can_execute, f"authenticated can execute {function_name}.")
            require(
                execute_grantees == ["postgres", "service_role"],
                f"{function_name} has unexpected execute grantees: {execute_grantees!r}.",
            )
            require(not public_can_execute, f"PUBLIC can execute {function_name}.")


def service_connection(test_url: str) -> psycopg.Connection:
    connection = psycopg.connect(test_url, autocommit=True)
    connection.execute("set statement_timeout = '15s'")
    connection.execute("set role service_role")
    connection.autocommit = False
    return connection


def seed_user(
    admin: psycopg.Connection,
    label: str,
    *,
    generation: int = 0,
) -> tuple[uuid.UUID, str]:
    user_id = uuid.uuid4()
    reset_token = f"reset-{label}-{uuid.uuid4().hex}"
    admin.execute(
        """
        insert into public.users (
          id, email, password_hash, is_verified, auth_generation,
          password_reset_token_hash, password_reset_expires
        ) values (%s, %s, 'old-password-hash', true, %s, %s, %s)
        """,
        (
            user_id,
            f"{label}-{uuid.uuid4().hex}@example.test",
            generation,
            reset_token,
            datetime.now(timezone.utc) + timedelta(hours=1),
        ),
    )
    return user_id, reset_token


def seed_session(
    admin: psycopg.Connection,
    user_id: uuid.UUID,
    *,
    generation: int = 0,
) -> uuid.UUID:
    session_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    admin.execute(
        """
        insert into public.sessions (
          id, user_id, token_hash, auth_generation, device_id,
          created_at, last_activity, expires_at
        ) values (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            session_id,
            user_id,
            f"token-{uuid.uuid4().hex}",
            generation,
            f"device-{uuid.uuid4().hex}",
            now,
            now,
            now + timedelta(hours=1),
        ),
    )
    return session_id


def persist_session(
    connection: psycopg.Connection,
    user_id: uuid.UUID,
    expected_generation: int,
    *,
    session_id: uuid.UUID | None = None,
) -> dict | None:
    now = datetime.now(timezone.utc)
    session_id = session_id or uuid.uuid4()
    return connection.execute(
        """
        select public.persist_auth_session(
          %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
        )
        """,
        (
            user_id,
            expected_generation,
            session_id,
            f"token-{uuid.uuid4().hex}",
            f"device-{uuid.uuid4().hex}",
            "Atomic probe",
            "test",
            Jsonb({"probe": True}),
            "127.0.0.1",
            "atomic-auth-postgres-probe",
            now,
            now + timedelta(hours=1),
        ),
    ).fetchone()[0]


def consume_reset(
    connection: psycopg.Connection,
    reset_token: str,
    new_password_hash: str,
) -> dict | None:
    return connection.execute(
        "select public.consume_password_reset(%s, %s, %s)",
        (reset_token, new_password_hash, datetime.now(timezone.utc)),
    ).fetchone()[0]


def wait_for_lock(
    admin: psycopg.Connection,
    backend_pid: int,
    future: Future,
    label: str,
) -> None:
    deadline = time.monotonic() + 5
    last_state: tuple[str | None, str | None, str | None] | None = None
    while time.monotonic() < deadline:
        if future.done():
            try:
                result = future.result()
            except Exception as exc:
                raise AssertionError(f"{label} failed before reaching the row lock.") from exc
            raise AssertionError(f"{label} completed before the blocking transaction: {result!r}")
        last_state = admin.execute(
            """
            select wait_event_type, wait_event, state
            from pg_stat_activity
            where pid = %s
            """,
            (backend_pid,),
        ).fetchone()
        if last_state and last_state[0] == "Lock":
            return
        time.sleep(0.05)
    raise AssertionError(f"{label} did not report a PostgreSQL lock wait; last_state={last_state!r}")


def release_blocker_and_get_result(
    admin: psycopg.Connection,
    blocker: psycopg.Connection,
    waiter_pid: int,
    future: Future,
    label: str,
):
    try:
        wait_for_lock(admin, waiter_pid, future, label)
    finally:
        blocker.commit()
    return future.result(timeout=10)


def probe_login_before_reset(admin: psycopg.Connection, test_url: str) -> None:
    user_id, reset_token = seed_user(admin, "login-first")
    login = service_connection(test_url)
    reset = service_connection(test_url)
    try:
        persisted = persist_session(login, user_id, 0)
        require(persisted is not None, "Login-first session was not persisted.")
        reset_pid = reset.execute("select pg_backend_pid()").fetchone()[0]
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(consume_reset, reset, reset_token, "login-first-password")
            reset_result = release_blocker_and_get_result(
                admin, login, reset_pid, future, "login-before-reset"
            )
        reset.commit()
        require(reset_result is not None, "Reset lost after the login transaction committed.")
    finally:
        login.rollback()
        reset.rollback()
        login.close()
        reset.close()

    generation, active_count, session_generations = admin.execute(
        """
        select u.auth_generation,
               count(*) filter (where s.id is not null and s.revoked_at is null),
               coalesce(array_agg(s.auth_generation) filter (where s.id is not null), '{}')
        from public.users u
        left join public.sessions s on s.user_id = u.id
        where u.id = %s
        group by u.auth_generation
        """,
        (user_id,),
    ).fetchone()
    require(generation == 1, "Login-first reset did not advance the generation.")
    require(active_count == 0, "Login-first reset left an active session.")
    require(session_generations == [0], "The pre-reset session has the wrong generation.")


def probe_reset_before_login(admin: psycopg.Connection, test_url: str) -> None:
    user_id, reset_token = seed_user(admin, "reset-first")
    reset = service_connection(test_url)
    login = service_connection(test_url)
    try:
        reset_result = consume_reset(reset, reset_token, "reset-first-password")
        require(reset_result is not None, "Reset-first transaction did not consume its token.")
        login_pid = login.execute("select pg_backend_pid()").fetchone()[0]
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(persist_session, login, user_id, 0)
            persist_result = release_blocker_and_get_result(
                admin, reset, login_pid, future, "reset-before-login"
            )
        login.commit()
        require(persist_result is None, "A stale post-reset login persisted a session.")
    finally:
        reset.rollback()
        login.rollback()
        reset.close()
        login.close()

    generation, session_count = admin.execute(
        """
        select u.auth_generation, count(s.id)
        from public.users u
        left join public.sessions s on s.user_id = u.id
        where u.id = %s
        group by u.auth_generation
        """,
        (user_id,),
    ).fetchone()
    require(generation == 1, "Reset-first transaction did not persist generation one.")
    require(session_count == 0, "Reset-first ordering created a stale session.")


def probe_two_resets(admin: psycopg.Connection, test_url: str) -> None:
    user_id, reset_token = seed_user(admin, "two-resets")
    seed_session(admin, user_id)
    first = service_connection(test_url)
    second = service_connection(test_url)
    try:
        first_result = consume_reset(first, reset_token, "first-reset-wins")
        require(first_result is not None, "First reset did not consume the token.")
        second_pid = second.execute("select pg_backend_pid()").fetchone()[0]
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(consume_reset, second, reset_token, "second-reset-loses")
            second_result = release_blocker_and_get_result(
                admin, first, second_pid, future, "two-resets"
            )
        second.commit()
        require(second_result is None, "The same reset token succeeded twice.")
    finally:
        first.rollback()
        second.rollback()
        first.close()
        second.close()

    password_hash, generation, active_count = admin.execute(
        """
        select u.password_hash, u.auth_generation,
               count(*) filter (where s.id is not null and s.revoked_at is null)
        from public.users u
        left join public.sessions s on s.user_id = u.id
        where u.id = %s
        group by u.password_hash, u.auth_generation
        """,
        (user_id,),
    ).fetchone()
    require(password_hash == "first-reset-wins", "The losing reset changed the password.")
    require(generation == 1, "Two reset attempts advanced the generation more than once.")
    require(active_count == 0, "The winning reset did not revoke the active session.")


def probe_generation_mismatch(admin: psycopg.Connection, test_url: str) -> None:
    user_id, _ = seed_user(admin, "generation-mismatch", generation=1)
    stale_session_id = seed_session(admin, user_id, generation=0)
    connection = service_connection(test_url)
    try:
        result = persist_session(connection, user_id, 0)
        connection.commit()
        require(result is None, "A stale expected generation persisted a new session.")
    finally:
        connection.rollback()
        connection.close()

    matching_active, session_count = admin.execute(
        """
        select count(*) filter (
                 where s.auth_generation = u.auth_generation and s.revoked_at is null
               ),
               count(*)
        from public.sessions s
        join public.users u on u.id = s.user_id
        where s.id = %s
        """,
        (stale_session_id,),
    ).fetchone()
    require(matching_active == 0, "A generation-mismatched session matched current credentials.")
    require(session_count == 1, "A stale generation unexpectedly created another session.")


def probe_rollbacks(admin: psycopg.Connection, test_url: str) -> None:
    user_id, reset_token = seed_user(admin, "rollback-reset")
    session_id = seed_session(admin, user_id)
    reset = service_connection(test_url)
    try:
        reset_result = consume_reset(reset, reset_token, "rolled-back-password")
        require(reset_result is not None, "Rollback probe reset did not execute.")
        inside_generation, inside_revoked = reset.execute(
            """
            select u.auth_generation, s.revoked_at is not null
            from public.users u join public.sessions s on s.user_id = u.id
            where u.id = %s and s.id = %s
            """,
            (user_id, session_id),
        ).fetchone()
        require(inside_generation == 1 and inside_revoked, "Reset was not atomic inside its tx.")
        reset.rollback()
    finally:
        reset.rollback()
        reset.close()

    password_hash, generation, saved_token, revoked_at = admin.execute(
        """
        select u.password_hash, u.auth_generation, u.password_reset_token_hash, s.revoked_at
        from public.users u join public.sessions s on s.user_id = u.id
        where u.id = %s and s.id = %s
        """,
        (user_id, session_id),
    ).fetchone()
    require(password_hash == "old-password-hash", "Rollback retained the new password.")
    require(generation == 0, "Rollback retained the advanced generation.")
    require(saved_token == reset_token, "Rollback consumed the reset token.")
    require(revoked_at is None, "Rollback retained the session revocation.")

    persist_user_id, _ = seed_user(admin, "rollback-persist")
    rolled_back_session = uuid.uuid4()
    persist = service_connection(test_url)
    try:
        result = persist_session(persist, persist_user_id, 0, session_id=rolled_back_session)
        require(result is not None, "Persist rollback probe did not create its session.")
        persist.rollback()
    finally:
        persist.rollback()
        persist.close()
    session_count = admin.execute(
        "select count(*) from public.sessions where id = %s", (rolled_back_session,)
    ).fetchone()[0]
    require(session_count == 0, "Rollback retained a newly persisted session.")


def run_probes(test_url: str) -> None:
    verify_schema_and_privileges(test_url)
    print("[pass] schema and service-role-only function privileges")
    with psycopg.connect(test_url, autocommit=True) as admin:
        probe_login_before_reset(admin, test_url)
        print("[pass] login-before-reset lock ordering")
        probe_reset_before_login(admin, test_url)
        print("[pass] reset-before-login lock ordering")
        probe_two_resets(admin, test_url)
        print("[pass] two-reset single-use ordering")
        probe_generation_mismatch(admin, test_url)
        print("[pass] stale session generation mismatch")
        probe_rollbacks(admin, test_url)
        print("[pass] reset and session-persist transaction rollback")


def cleanup(
    admin_url: str,
    state: DisposableDatabaseState,
) -> list[str]:
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
            f"Set {ADMIN_URL_ENV} to a disposable loopback PostgreSQL 15+ admin URL.",
            file=sys.stderr,
        )
        return 2

    validate_disposable_attestation()
    validate_admin_connection(admin_url)
    state = DisposableDatabaseState(
        database_name=f"{DATABASE_PREFIX}{uuid.uuid4().hex[:12]}"
    )
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
    print("Atomic auth PostgreSQL verification passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
