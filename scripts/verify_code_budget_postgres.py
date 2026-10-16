"""Exercise the real Code migrations with contending PostgreSQL sessions.

Only an empty, loopback database named askcrump_code_test_* is accepted. The
GitHub Actions job creates that disposable database; this script never reads a
project URL, provisions a service, or connects to a linked customer database.
Requires psql on PATH. No provider requests or customer credits are involved.
"""

from __future__ import annotations

import concurrent.futures
import json
import os
from pathlib import Path
import re
import subprocess
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
POLICY = dict(model="exact-approved-fixture-model", input_rate=1_000_000,
              output_rate=1_000_000, max_input_bytes=100_000,
              max_output_tokens=6000, call_limit=20_000, run_limit=40_000,
              account_daily_limit=120_000, global_daily_limit=240_000)


def fixture_environment(source: dict[str, str]) -> dict[str, str]:
    """Reject remote destinations and neutralize libpq connection overrides."""
    if source.get("PGHOST") not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("PGHOST must explicitly name loopback")
    if not re.fullmatch(r"askcrump_code_test_[a-z0-9_]{1,43}", source.get("PGDATABASE", "")):
        raise ValueError("PGDATABASE must name an isolated askcrump_code_test_* fixture")
    port = source.get("PGPORT", "5432")
    if not port.isascii() or not port.isdecimal() or not 1 <= int(port) <= 65535:
        raise ValueError("PGPORT must be a valid numeric port")
    # Whitelist libpq settings rather than inheriting services, hostaddr, SSL
    # routing options, or credentials from a developer's unrelated project.
    env = {key: value for key, value in source.items() if not key.upper().startswith("PG")}
    for key in ("PGHOST", "PGDATABASE", "PGUSER", "PGPASSWORD"):
        if key in source:
            env[key] = source[key]
    env.update(PGPORT=port, PGCONNECT_TIMEOUT="5", PGSSLMODE="disable",
               PGOPTIONS="-c statement_timeout=12000 -c lock_timeout=10000")
    return env


def literal(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, dict):
        return "'" + json.dumps(value, separators=(",", ":")).replace("'", "''") + "'::jsonb"
    return "'" + str(value).replace("'", "''") + "'"


def invocation(name: str, *args: object) -> str:
    if not re.fullmatch(r"[a-z_]+", name):
        raise ValueError("invalid fixture function")
    return f"public.{name}({','.join(map(literal, args))})"


class Fixture:
    def __init__(self, env: dict[str, str]):
        self.env = fixture_environment(env)
        self.marker = str(uuid.uuid4())
        self.scenarios = 0

    def sql(self, sql: str, app: str = "crump-code-fixture") -> list[str]:
        result = subprocess.run(
            ["psql", "-X", "-w", "-qAt", "--set=ON_ERROR_STOP=1"], input=sql,
            text=True, capture_output=True, env={**self.env, "PGAPPNAME": app}, timeout=25,
            check=False,
        )
        if result.returncode:
            # SQL contains synthetic identifiers only. Never print env/passwords.
            raise RuntimeError(f"PostgreSQL fixture failed: {result.stderr[-3000:]}")
        return [line for line in result.stdout.splitlines() if line]

    def scalar(self, sql: str) -> str:
        rows = self.sql(sql)
        assert len(rows) == 1, rows
        return rows[0]

    def rpc(self, name: str, *args: object) -> dict:
        return json.loads(self.scalar(f"select {invocation(name, *args)}"))

    def bootstrap(self) -> None:
        assert self.scalar("select count(*) from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname='public'") == "0", "Fixture database public schema must be empty"
        self.sql("""do $$ begin
          if not exists(select from pg_roles where rolname='anon') then create role anon; end if;
          if not exists(select from pg_roles where rolname='authenticated') then create role authenticated; end if;
          if not exists(select from pg_roles where rolname='service_role') then create role service_role bypassrls; end if;
          end $$;
          create table public.fixture_marker(id uuid primary key);
          create table public.users(id uuid primary key,deleted_at timestamptz);
          create table public.projects(id uuid primary key,user_id uuid references public.users on delete cascade);
          create table public.usage_events(id uuid primary key default gen_random_uuid(),user_id uuid not null references public.users,
            event_type text not null,metadata jsonb not null default '{}',created_at timestamptz not null default now());
        """ + f"insert into public.fixture_marker values({literal(self.marker)});")
        self.migration("005_credit_wallet.sql")
        self.sql("alter table public.usage_events add column idempotency_key text; create unique index fixture_usage_key on public.usage_events(user_id,event_type,idempotency_key) where idempotency_key is not null;")
        text = (ROOT / "migrations/20260924213808_align_chat_job_lease_with_ai_timeout.sql").read_text(encoding="utf-8")
        start = text.index("create or replace function public.consume_usage_event_v2(")
        end = text.index("create or replace function public.claim_chat_job(", start)
        self.sql(text[start:end])
        self.migration("20260827145025_crump_code_foundation.sql")
        self.migration("20260830093000_crump_code_durable_worker.sql")
        self.sql("create table public.user_chats(user_id uuid references public.users); create table public.user_settings(user_id uuid references public.users); create table public.sessions(user_id uuid references public.users);")
        self.migration("20260924210000_durable_account_storage_deletion.sql")
        self.migration("20261015230059_atomic_code_dispatch_provider_budget.sql")

    def migration(self, name: str) -> None:
        self.sql((ROOT / "migrations" / name).read_text(encoding="utf-8"))

    def reset(self) -> None:
        assert self.scalar("select id from public.fixture_marker") == self.marker
        # Enumerate only fixture-created tables, never DROP SCHEMA or a linked DB.
        self.sql("""truncate table public.code_provider_call_reservations,public.code_provider_global_daily,
          public.code_provider_account_daily,public.code_task_approvals,public.code_task_events,
          public.code_tasks,public.usage_events,public.credit_ledger,public.credit_accounts,
          public.user_chats,public.user_settings,public.sessions,public.projects,public.users,
          public.account_storage_deletion_jobs;""")

    def owner(self) -> tuple[str, str]:
        owner, project = str(uuid.uuid4()), str(uuid.uuid4())
        self.sql(f"insert into public.users(id) values({literal(owner)}); insert into public.projects(id,user_id) values({literal(project)},{literal(owner)}); insert into public.credit_accounts(user_id,balance) values({literal(owner)},1000);")
        return owner, project

    def task(self, owner: tuple[str, str], *, policy: dict | None = None, dispatch: bool = True) -> dict:
        task = dict(id=str(uuid.uuid4()), user=owner[0], lease=str(uuid.uuid4()), policy=policy or POLICY)
        self.sql(f"insert into public.code_tasks(id,user_id,project_id,objective,source_repo_url) values({literal(task['id'])},{literal(owner[0])},{literal(owner[1])},'Disposable concurrency fixture','https://github.com/example/fixture');")
        if dispatch:
            receipt = self.rpc("reserve_and_dispatch_code_task", task["id"], task["user"], str(uuid.uuid4()), 0, 12, 12, str(uuid.uuid4()), None, task["policy"])
            assert receipt["outcome"] == "dispatched", receipt.get("code", "fixture dispatch refused")
            self.sql(f"update public.code_tasks set status='running',lease_token={literal(task['lease'])},lease_expires_at=clock_timestamp()+interval '5 minutes' where id={literal(task['id'])}")
        return task

    @staticmethod
    def dispatch(t: dict, included: int = 0, confirmed: int = 12) -> str:
        return invocation("reserve_and_dispatch_code_task", t["id"], t["user"], str(uuid.uuid4()), included, 12, confirmed, str(uuid.uuid4()), None, t["policy"])

    @staticmethod
    def reserve(t: dict) -> str:
        return invocation("reserve_code_provider_call", t["id"], t["user"], t["lease"], "turn:0", "a" * 64, 6000, 5000, 1000, t["policy"])

    def reservation(self, t: dict) -> dict:
        return json.loads(self.scalar("select " + self.reserve(t)))["reservation"]

    @staticmethod
    def begin(t: dict, r: dict) -> str:
        return invocation("begin_code_provider_call", t["id"], t["user"], t["lease"], r["id"])

    @staticmethod
    def refund(t: dict) -> str:
        return invocation("refund_code_task_if_unstarted", t["id"], t["user"])

    @staticmethod
    def cancel(t: dict) -> str:
        return f"update public.code_tasks set status='cancelled',cancel_requested_at=clock_timestamp(),payment_source='refund_pending',lease_token=null where id={literal(t['id'])};"

    def race(self, expressions: list[str], *, lock: str, prefixes: list[str] | None = None) -> list[dict]:
        """Each actor is a separate backend, observed blocked behind a real lock."""
        prefix = "crump-race-" + uuid.uuid4().hex[:10]
        gate_app = prefix + "-gate"
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(expressions) + 1) as pool:
            gate = pool.submit(self.sql, f"begin; {lock}; select pg_sleep(4); commit;", gate_app)
            deadline = time.monotonic() + 6
            while self.scalar(f"select count(*) from pg_stat_activity where application_name={literal(gate_app)} and wait_event='PgSleep'") != "1":
                if gate.done():
                    gate.result()
                    raise AssertionError("contention gate did not acquire its lock")
                assert time.monotonic() < deadline, "gate timeout"
                time.sleep(0.03)
            actors = [pool.submit(self.sql, (prefixes or [""] * len(expressions))[i] +
                       f"select json_build_object('pid',pg_backend_pid(),'result',{expr});", f"{prefix}-actor-{i}")
                      for i, expr in enumerate(expressions)]
            observed = 0
            while time.monotonic() < deadline:
                observed = int(self.scalar(f"select count(*) from pg_stat_activity where application_name like {literal(prefix + '-actor-%')} and cardinality(pg_blocking_pids(pid))>0"))
                if observed >= min(2, len(expressions)):
                    break
                time.sleep(0.03)
            gate.result()
            rows = [json.loads(future.result()[-1]) for future in actors]
        assert observed >= min(2, len(expressions)), "race did not demonstrate overlapping blocked sessions"
        assert len({row["pid"] for row in rows}) == len(rows), "actors must use independent backend sessions"
        return [row["result"] for row in rows]

    def passed(self, name: str) -> None:
        self.scenarios += 1
        print(f"PASS {name}", flush=True)

    def held(self) -> int:
        return int(self.scalar("select coalesce(sum(held_micros),0) from public.code_provider_global_daily"))

    def run(self) -> None:
        self.bootstrap()
        deadlocks = int(self.scalar("select deadlocks from pg_stat_database where datname=current_database()"))
        global_lock = "select pg_advisory_xact_lock(hashtextextended('code-provider-global:v1',0))"
        self.reset()
        owner = self.owner()
        t = self.task(owner, dispatch=False)
        task_lock = f"select id from public.code_tasks where id={literal(t['id'])} for update"
        results = self.race([self.dispatch(t) for _ in range(16)], lock=task_lock)
        assert sum(r["outcome"] == "dispatched" for r in results) == 1
        assert sum(r["outcome"] == "replay" for r in results) == 15
        assert len({json.dumps(r["task"]["usage_receipt"], sort_keys=True) for r in results}) == 1
        assert self.scalar("select count(*) from public.credit_ledger") == "1"
        assert self.scalar("select balance from public.credit_accounts") == "988"
        assert self.scalar("select count(*) from public.code_task_events where event_type='task.claimed'") == "1"
        self.passed("16-way same-task dispatch has one canonical receipt and debit")

        # Ignore the first committed response, then retry with fresh request IDs.
        self.reset()
        t = self.task(self.owner(), dispatch=False)
        self.sql("select " + self.dispatch(t))
        results = self.race([self.dispatch(t) for _ in range(8)], lock=f"select id from public.code_tasks where id={literal(t['id'])} for update")
        assert all(r["outcome"] == "replay" for r in results)
        assert self.scalar("select balance from public.credit_accounts") == "988"
        self.passed("lost committed dispatch response replays without a second charge")

        self.reset()
        owner = self.owner()
        tasks = [self.task(owner, dispatch=False) for _ in range(16)]
        results = self.race([self.dispatch(t, 3, 0) for t in tasks], lock=f"select id from public.users where id={literal(owner[0])} for update")
        assert sum(r["outcome"] == "dispatched" for r in results) == 3
        assert sum(r.get("code") == "CREDIT_CONFIRMATION_REQUIRED" for r in results) == 13
        assert self.scalar("select count(*) from public.credit_ledger") == "0"
        self.passed("shared included allowance never silently spends credits")

        for name, owners, policy, expected in [
            ("account", 1, {**POLICY, "call_limit": 6000, "run_limit": 6000, "account_daily_limit": 18_000}, 3),
            ("global", 4, {**POLICY, "call_limit": 6000, "run_limit": 6000, "account_daily_limit": 24_000, "global_daily_limit": 24_000}, 4),
        ]:
            self.reset()
            accounts = [self.owner() for _ in range(owners)]
            tasks = [self.task(accounts[i % owners], policy=policy) for i in range(16)]
            results = self.race([self.reserve(t) for t in tasks], lock=global_lock)
            assert sum(r["outcome"] == "reserved" for r in results) == expected
            assert self.held() == expected * 6000
            self.passed(f"16-way {name} provider budget race cannot overspend")

        self.reset()
        t = self.task(self.owner())
        results = self.race([self.reserve(t) for _ in range(16)], lock=global_lock)
        assert sum(r["outcome"] == "reserved" for r in results) == 1
        assert sum(r["outcome"] == "reserved_replay" for r in results) == 15
        assert self.held() == 6000
        r = results[0]["reservation"]
        self.passed("same-call reservations hold budget exactly once")
        results = self.race([self.begin(t, r) for _ in range(16)], lock=global_lock)
        assert sum(r["outcome"] == "started" for r in results) == 1
        assert sum(r["outcome"] == "already_started" for r in results) == 15
        self.passed("exactly one provider-begin owner among 16 sessions")

        self.reset()
        t = self.task(self.owner())
        r = self.reservation(t)
        self.race([self.begin(t, r), self.refund(t)], lock=f"select id from public.code_tasks where id={literal(t['id'])} for update", prefixes=["", self.cancel(t)])
        started = self.scalar(f"select (provider_started_at is not null)::int from public.code_tasks where id={literal(t['id'])}") == "1"
        assert self.scalar("select status from public.code_tasks") == "cancelled"
        assert self.scalar("select balance from public.credit_accounts") == ("988" if started else "1000")
        assert self.held() == (6000 if started else 0)
        self.passed("provider begin vs cancel/refund preserves accepted-request charges")

        for settled in (False, True):
            self.reset()
            t = self.task(self.owner())
            r = self.reservation(t)
            if settled:
                assert json.loads(self.scalar("select " + self.begin(t, r)))["outcome"] == "started"
                competing = invocation("settle_code_provider_call", t["id"], t["user"], t["lease"], r["id"], 1000, False)
                prefixes = None
            else:
                self.sql(self.cancel(t))
                competing = self.refund(t)
                prefixes = None
            self.race([invocation("delete_user_account", t["user"], "fixture-bucket"), competing],
                      lock=f"select id from public.users where id={literal(t['user'])} for update", prefixes=prefixes)
            assert self.scalar("select count(*) from public.users") == "0"
            assert self.scalar("select count(*) from public.account_storage_deletion_jobs") == "1"
            assert self.scalar("select count(*) from public.code_provider_account_daily") == "0"
            assert self.held() in ({1000, 6000} if settled else {0, 6000})
            assert self.scalar("select strictest_cap_micros from public.code_provider_global_daily") == str(POLICY["global_daily_limit"])
            self.passed(f"account deletion vs {'settlement' if settled else 'refund'} retains global cost/cap and storage obligation")

        assert int(self.scalar("select deadlocks from pg_stat_database where datname=current_database()")) == deadlocks
        print(f"PASS {self.scenarios} real PostgreSQL concurrency scenarios; no deadlocks", flush=True)


if __name__ == "__main__":
    Fixture(dict(os.environ)).run()
