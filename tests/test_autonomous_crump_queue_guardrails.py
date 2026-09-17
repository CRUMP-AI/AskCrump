from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from threading import Barrier, Lock
from types import SimpleNamespace
from uuid import UUID

import pytest

from backend.code_service import (
    CodeTaskConflictError,
    CodeTaskGuardrailError,
    CodeTaskService,
    code_guardrail_error,
)
from backend.routes import code as code_routes
from backend.routes import manuscripts as manuscript_routes


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "migrations" / "20260917001500_autonomous_crump_queue_guardrails.sql"
USER_ID = "00000000-0000-4000-8000-0000000000a1"
PROJECT_ID = "00000000-0000-4000-8000-0000000000a2"
TASK_ID = "00000000-0000-4000-8000-0000000000a3"
CLAIM_ID = "00000000-0000-4000-8000-0000000000a4"


def migration() -> str:
    return MIGRATION.read_text(encoding="utf-8").lower()


def test_guardrail_migration_is_private_bounded_and_content_free() -> None:
    sql = migration()
    assert sql.startswith("-- autonomous crump queue, budget, concurrency, and fairness guardrails")
    assert sql.rstrip().endswith("commit;")
    for table in (
        "code_guardrail_limits",
        "code_guardrail_receipts",
        "code_guardrail_global_daily_facts",
    ):
        assert f"alter table public.{table} enable row level security" in sql
        normalized_sql = " ".join(sql.split())
        assert (
            f"revoke all on table public.{table} from public, anon, authenticated, service_role"
            in normalized_sql
        )
    assert "grant select on table public.code_guardrail_limits to service_role" in sql
    assert "grant select, insert on table public.code_guardrail_receipts to service_role" in sql
    assert (
        "grant select, insert, update on table public.code_guardrail_global_daily_facts"
        in sql
    )
    assert "grant update on table public.code_guardrail_limits" not in sql
    assert "grant delete on table public.code_guardrail_receipts" not in sql
    assert "values (1, 3, 100, 2, 3, 30, 4, 24, 720, 4320)" in sql
    for bounded_check in (
        "user_queue_limit between 1 and 5",
        "global_queue_limit between 10 and 500",
        "global_active_lease_limit between 1 and 4",
        "user_daily_accept_limit between 1 and 10",
        "global_daily_model_start_limit between 2 and 100",
        "user_daily_sandbox_seconds between 30 and 2880",
        "global_daily_sandbox_seconds between 60 and 24000",
    ):
        assert bounded_check in sql

    receipt_ddl = sql[
        sql.index("create table if not exists public.code_guardrail_receipts") :
        sql.index("create index if not exists code_guardrail_receipts_global_day_idx")
    ]
    for private_content in (
        "objective",
        "source_repo_url",
        "source_ref",
        "result_summary",
        "result_patch",
        "sandbox_name",
        "lease_token",
        "dispatch_token",
        "provider",
        "prompt",
        "output",
    ):
        assert private_content not in receipt_ddl

    facts_ddl = sql[
        sql.index("create table if not exists public.code_guardrail_global_daily_facts") :
        sql.index("create unique index if not exists code_tasks_one_accepted_active_per_user_idx")
    ]
    assert "budget_day date primary key" in facts_ddl
    assert "accepted_count integer" in facts_ddl
    assert "model_start_count integer" in facts_ddl
    assert "declared_sandbox_seconds bigint" in facts_ddl
    for customer_identifier in ("user_id", "task_id", "project_id", "email"):
        assert customer_identifier not in facts_ddl


def test_both_autonomous_release_gates_remain_closed() -> None:
    config = (ROOT / "backend" / "config.py").read_text(encoding="utf-8")
    assert "CODE_WORKSPACE_PUBLIC_RELEASED = False" in config
    assert "CODE_WORKSPACE_PUBLIC_RELEASED\n            and _bool(" in config
    assert "os.getenv('CRUMP_ENABLE_CODE_WORKSPACE'), False" in config


def test_owned_postgres_gate_refuses_shared_or_nonempty_databases() -> None:
    source = (
        ROOT / "scripts" / "run_autonomous_crump_guardrails_postgres.py"
    ).read_text(encoding="utf-8")
    assert 'DB_PREFIX = "askcrump_guardrails_"' in source
    assert 'OWNERSHIP_VALUE = "I_OWN_THIS_EMPTY_DISPOSABLE_DATABASE"' in source
    assert '{"localhost", "127.0.0.1", "::1"}' in source
    assert "The disposable guardrail database is not empty" in source
    assert "information_schema.tables" in source
    assert "drop database" not in source.lower()
    assert "drop schema" not in source.lower()
    assert "SUPABASE_URL" not in source
    assert "SUPABASE_SERVICE_KEY" not in source
    assert "service_role_created = _scalar(" in source
    assert (
        "'implement','https://github.com/openai/codex.git','main','syntax_only',180)"
        in source
    )
    assert "service_role guarded creation did not produce exactly one task.created event" in source
    for runtime_proof in (
        "service_role direct code_tasks INSERT was not rejected",
        "serviceRoleGuardedCreateSucceeded",
        "create replay inserted more than one task",
        "globalFactsSurviveUserDeletion",
        "deletionInvariantCapDeferredWithReadyTask",
        "expiredCrossProjectTaskReconciled",
        "retryLimitFiveTerminalizedBeforeCompute",
        "smallFittingTaskBypassedOversizedTask",
        "noFittingTaskDeferredUntilUtcReset",
        "exhaustedCapacityDistinguished",
        "emptyQueueAtActiveLeaseCapIsNoWork",
        "emptyQueueAtModelStartCapIsNoWork",
    ):
        assert runtime_proof in source
    for migration_name in (
        "20260827145025_crump_code_foundation.sql",
        "20260830093000_crump_code_durable_worker.sql",
        "20260916231500_autonomous_crump_atomic_dispatch.sql",
        "20260916233000_autonomous_crump_verification_policy.sql",
        "20260917001500_autonomous_crump_queue_guardrails.sql",
    ):
        assert migration_name in source

    workflow = (
        ROOT
        / ".github"
        / "workflows"
        / "autonomous-crump-guardrails-postgres.yml"
    ).read_text(encoding="utf-8")
    assert "workflow_dispatch:" in workflow
    assert "pull_request:" not in workflow
    assert "push:" not in workflow
    assert "postgres: ['15', '17']" in workflow
    assert 'python -m pip install "psycopg[binary]==3.3.5"' in workflow
    assert "I_OWN_THIS_EMPTY_DISPOSABLE_DATABASE" in workflow
    assert "python scripts/run_autonomous_crump_guardrails_postgres.py" in workflow

    evidence = (
        ROOT / "docs" / "AUTONOMOUS_CRUMP_QUEUE_GUARDRAILS_CANDIDATE_2026-09-16.md"
    ).read_text(encoding="utf-8")
    assert "1abd86f4a11c152881f84b69fc7a13d06edd1629" in evidence
    assert "3cbb714bae797a366b5e495937100a3462bd0c60" in evidence
    assert "GitHub Actions run 35170038398" in evidence
    assert "exact executable source identity and its CI-only mirror" in evidence
    assert "PostgreSQL 15 and PostgreSQL 17 jobs" in evidence
    assert "deliberately **not Supabase**" in evidence
    assert "no real PostgreSQL runtime or concurrency pass is claimed" not in evidence


def test_guardrail_functions_use_consistent_lock_order_and_private_execution() -> None:
    sql = migration()
    for name, signature in (
        (
            "create_code_task_guarded",
            "public.create_code_task_guarded(\n  uuid, uuid, uuid, text, text, text, text, text, integer\n)",
        ),
        (
            "accept_code_task_run",
            "public.accept_code_task_run(\n  uuid, uuid, uuid, text, integer, integer, text, integer\n)",
        ),
        ("claim_code_task_guarded", "public.claim_code_task_guarded(integer, uuid)"),
    ):
        function = sql[sql.index(f"create or replace function public.{name}") :]
        end = function.index("$$;", function.index("as $$"))
        body = function[:end]
        if name == "create_code_task_guarded":
            assert "security definer" in body
        else:
            assert "security invoker" in body
        assert "set search_path = ''" in body
        global_lock = body.index("pg_catalog.pg_advisory_xact_lock(8274, 0)")
        if name != "claim_code_task_guarded":
            user_lock = body.index("pg_catalog.hashtext(p_user_id::text)")
            row_lock = body.index("for update") if name == "accept_code_task_run" else len(body)
            assert global_lock < user_lock < row_lock
        else:
            user_lock = body.index("pg_catalog.hashtext(candidate_user_id::text)")
            row_lock = body.index("for update", user_lock)
            assert global_lock < user_lock < row_lock
        assert f"revoke all on function {signature}" in sql
        assert f"grant execute on function {signature}" in sql
    assert "revoke all on function public.claim_code_task(integer, uuid) from service_role" in sql
    assert "revoke insert on table public.code_tasks from service_role" in sql


def test_queue_creation_has_stable_replay_identity_and_one_creation_event() -> None:
    sql = migration()
    body = sql[
        sql.index("create or replace function public.create_code_task_guarded") :
        sql.index("create or replace function public.accept_code_task_run")
    ]
    assert "code_tasks_creation_token_idx" in sql
    assert "p_creation_token uuid" in body
    replay_lookup = body.index("where creation_token = p_creation_token")
    capacity_lookup = body.index("from public.code_guardrail_limits")
    task_insert = body.index("insert into public.code_tasks")
    event_insert = body.index("insert into public.code_task_events")
    assert replay_lookup < capacity_lookup < task_insert < event_insert
    assert "'replayed', true" in body
    assert "event.event_type = 'task.created'" in body
    assert "created.verification_policy <> p_verification_policy" in body
    assert "'reason', 'creation_token_conflict'" in body


def test_global_daily_facts_survive_customer_deletion_and_are_atomic() -> None:
    sql = migration()
    facts_ddl = sql[
        sql.index("create table if not exists public.code_guardrail_global_daily_facts") :
        sql.index("create unique index if not exists code_tasks_one_accepted_active_per_user_idx")
    ]
    assert "references public.users" not in facts_ddl
    assert "references public.code_tasks" not in facts_ddl
    assert "on delete cascade" not in facts_ddl

    accept = sql[
        sql.index("create or replace function public.accept_code_task_run") :
        sql.index("create or replace function public.claim_code_task_guarded")
    ]
    assert "select fact.accepted_count" in accept
    assert "accepted_count = daily.accepted_count + 1" in accept
    assert accept.index("insert into public.code_guardrail_receipts") < accept.index(
        "insert into public.code_guardrail_global_daily_facts"
    )

    claim = sql[sql.index("create or replace function public.claim_code_task_guarded") :]
    assert "select fact.model_start_count" in claim
    assert "select fact.declared_sandbox_seconds::integer" in claim
    assert "model_start_count = daily.model_start_count + 1" in claim


def test_acceptance_reconciles_expired_tasks_across_projects_before_active_check() -> None:
    sql = migration()
    body = sql[
        sql.index("create or replace function public.accept_code_task_run") :
        sql.index("create or replace function public.claim_code_task_guarded")
    ]
    cleanup = body.index("with expired as")
    active_check = body.index("select min(active.expires_at)")
    charge = body.index("from public.consume_usage_event(")
    assert cleanup < active_check < charge
    assert "stale.user_id = p_user_id" in body
    assert "stale.expires_at <= now()" in body
    assert "failure_code = 'code_task_expired'" in body
    assert "payment_source = 'refund_pending'" in body
    assert "'task.cancelled'" in body


def test_final_attempt_is_terminalized_before_any_compute_reservation() -> None:
    sql = migration()
    body = sql[sql.index("create or replace function public.claim_code_task_guarded") :]
    terminal = body.index("task.attempt_count >= task.max_attempts")
    global_budget = body.index("select fact.model_start_count")
    model_receipt = body.index("insert into public.code_guardrail_receipts")
    assert terminal < global_budget < model_receipt
    terminal_block = body[terminal:global_budget]
    assert "failure_code = 'code_retry_limit'" in terminal_block
    assert "payment_source = 'refund_pending'" in terminal_block
    assert "'task.failed'" in terminal_block
    assert "'terminalized', true" in terminal_block
    assert "insert into public.code_guardrail_receipts" not in terminal_block


def test_acceptance_rejects_guardrails_before_any_allowance_or_credit_charge() -> None:
    sql = migration()
    body = sql[
        sql.index("create or replace function public.accept_code_task_run") :
        sql.index("create or replace function public.claim_code_task_guarded")
    ]
    last_precharge_guardrail = body.index("global_daily_accept_limit")
    allowance = body.index("from public.consume_usage_event(")
    credits = body.index("from public.spend_credits_confirmed(")
    task_update = body.index("update public.code_tasks\n  set status = 'provisioning'")
    receipt = body.index("insert into public.code_guardrail_receipts")
    assert last_precharge_guardrail < allowance < credits < task_update < receipt
    assert "code_tasks_one_accepted_active_per_user_idx" in sql
    assert "active.id <> candidate.id" in body
    assert "'reason', 'user_active_task'" in body


def test_claim_is_fair_skip_locked_equivalent_and_budgeted_before_compute() -> None:
    sql = migration()
    body = sql[sql.index("create or replace function public.claim_code_task_guarded") :]
    assert "global_active >= guardrails.global_active_lease_limit" in body
    assert "user_daily_model_start_limit" in body
    assert "global_daily_model_start_limit" in body
    assert "user_daily_sandbox_seconds" in body
    assert "global_daily_sandbox_seconds" in body
    assert "code_guardrail_global_daily_facts" in body
    assert "task.max_duration_seconds <= remaining_global_seconds" in body
    assert "'no_fitting_task'" in body
    assert "'exhausted'" in body
    assert "task.attempt_count < task.max_attempts" in body
    assert "'reason', 'retry_limit_exhausted'" in body
    assert "select max(served.created_at)" in body
    assert "asc nulls first" in body
    assert "for update skip locked" in body
    assert body.index("insert into public.code_guardrail_receipts") < body.index(
        "return jsonb_build_object(\n    'claimed', true"
    )
    assert "'kind', 'model_start'" in body
    assert "'declaredsandboxseconds', declared_seconds" in body


def test_claim_proves_ready_work_before_global_capacity_deferrals() -> None:
    body = migration()[
        migration().index("create or replace function public.claim_code_task_guarded") :
    ]
    ready_probe = body.index("from public.code_tasks as ready")
    empty_result = body.index("'reason', 'no_work'", ready_probe)
    active_cap = body.index("global_active >= guardrails.global_active_lease_limit")
    model_start_cap = body.index(
        "global_starts >= guardrails.global_daily_model_start_limit"
    )
    fair_selection = body.index("from public.code_tasks as task", model_start_cap)
    assert ready_probe < empty_result < active_cap < model_start_cap < fair_selection
    ready_block = body[ready_probe:empty_result]
    assert "ready.usage_receipt is not null" in ready_block
    assert "ready.attempt_count < ready.max_attempts" in ready_block
    assert "ready.next_attempt_at <= now()" in ready_block
    assert "ready.expires_at > now()" in ready_block
    assert "ready.lease_expires_at < now()" in ready_block


class GuardedRPCDB:
    def __init__(self, responses: dict[str, object]):
        self.responses = responses
        self.calls: list[tuple[str, dict, bool]] = []

    async def rpc(self, name, payload, *, retry_transient=False):
        self.calls.append((name, dict(payload), retry_transient))
        return self.responses[name]


@pytest.mark.asyncio
async def test_service_creates_only_through_guarded_replay_safe_rpc(monkeypatch) -> None:
    task = {"id": TASK_ID, "user_id": USER_ID, "project_id": PROJECT_ID, "status": "queued"}
    database = GuardedRPCDB(
        {"create_code_task_guarded": {"created": True, "task": task}}
    )

    async def get_project(_user_id, _project_id):
        return {"id": PROJECT_ID}

    service = CodeTaskService(database, SimpleNamespace(get=get_project))
    monkeypatch.setattr("backend.code_service.uuid4", lambda: UUID(CLAIM_ID))
    created = await service.create(
        user_id=USER_ID,
        project_id=PROJECT_ID,
        objective="Fix the bounded bug",
        mode="implement",
        repo_url="https://github.com/openai/codex",
        revision="main",
        max_duration_seconds=999,
    )
    assert created == task
    name, payload, retry = database.calls[0]
    assert name == "create_code_task_guarded"
    assert payload == {
        "p_user_id": USER_ID,
        "p_project_id": PROJECT_ID,
        "p_creation_token": CLAIM_ID,
        "p_objective": "Fix the bounded bug",
        "p_mode": "implement",
        "p_source_repo_url": "https://github.com/openai/codex.git",
        "p_source_ref": "main",
        "p_verification_policy": "syntax_only",
        "p_max_duration_seconds": 240,
    }
    assert retry is True


def test_legacy_direct_claim_method_is_absent() -> None:
    assert not hasattr(CodeTaskService, "claim")


@pytest.mark.asyncio
async def test_generic_transition_cannot_bypass_guarded_provisioning() -> None:
    service = CodeTaskService(GuardedRPCDB({}), SimpleNamespace())
    with pytest.raises(CodeTaskConflictError, match="cannot move from queued to provisioning"):
        await service.transition(
            {
                "id": TASK_ID,
                "user_id": USER_ID,
                "project_id": PROJECT_ID,
                "status": "queued",
            },
            "provisioning",
        )
    assert service.db.calls == []


@pytest.mark.asyncio
async def test_service_surfaces_truthful_queue_deferral() -> None:
    database = GuardedRPCDB(
        {
            "create_code_task_guarded": {
                "created": False,
                "deferred": True,
                "reason": "user_queue_limit",
                "retryAfterSeconds": 30,
            }
        }
    )

    async def get_project(_user_id, _project_id):
        return {"id": PROJECT_ID}

    service = CodeTaskService(database, SimpleNamespace(get=get_project))
    with pytest.raises(CodeTaskGuardrailError) as exc:
        await service.create(
            user_id=USER_ID,
            project_id=PROJECT_ID,
            objective="Another task",
            mode="plan",
            repo_url="https://github.com/openai/codex",
        )
    assert exc.value.code == "CODE_USER_QUEUE_LIMIT"
    assert exc.value.status_code == 429
    assert exc.value.retry_after_seconds == 30
    assert exc.value.reason == "user_queue_limit"


@pytest.mark.asyncio
async def test_service_uses_guarded_claim_receipt_and_fails_closed_if_incomplete() -> None:
    task = {"id": TASK_ID, "user_id": USER_ID, "status": "provisioning"}
    database = GuardedRPCDB(
        {"claim_code_task_guarded": {"claimed": True, "task": task}}
    )
    service = CodeTaskService(database, SimpleNamespace())
    result = await service.claim_next(lease_seconds=999, claim_token=CLAIM_ID)
    assert result == {"claimed": True, "task": task}
    assert database.calls == [
        (
            "claim_code_task_guarded",
            {"p_lease_seconds": 300, "p_claim_token": CLAIM_ID},
            True,
        )
    ]

    broken = CodeTaskService(
        GuardedRPCDB({"claim_code_task_guarded": {"claimed": True}}),
        SimpleNamespace(),
    )
    with pytest.raises(CodeTaskConflictError, match="incomplete worker claim receipt"):
        await broken.claim_next(lease_seconds=60, claim_token=CLAIM_ID)


def test_guardrail_error_mapping_never_claims_a_charge() -> None:
    active = code_guardrail_error("user_active_task", 30)
    daily = code_guardrail_error("global_daily_accept_limit", 42_000)
    unavailable = code_guardrail_error("guardrail_unavailable", 60)
    malformed = code_guardrail_error("private database detail", "not-a-number")
    assert (active.code, active.status_code) == ("CODE_ACTIVE_TASK_EXISTS", 409)
    assert (daily.code, daily.status_code, daily.retry_after_seconds) == (
        "CODE_DAILY_CAPACITY",
        503,
        42_000,
    )
    assert unavailable.code == "CODE_GUARDRAIL_UNAVAILABLE"
    assert "No task was accepted or charged" in str(unavailable)
    assert malformed.code == "CODE_GUARDRAIL_UNAVAILABLE"
    assert malformed.reason == "guardrail_unavailable"
    assert malformed.retry_after_seconds == 30

    response = code_routes._task_error(daily)
    assert response.status_code == 503
    assert response.headers["retry-after"] == "42000"
    assert json.loads(response.body) == {
        "success": False,
        "error": str(daily),
        "code": "CODE_DAILY_CAPACITY",
        "deferred": True,
        "reason": "global_daily_accept_limit",
        "retryAfterSeconds": 42_000,
    }


def test_shared_cron_has_deterministic_fair_turns_and_separate_check_ins() -> None:
    utc = timezone.utc
    assert manuscript_routes.shared_worker_order(datetime(2026, 9, 17, 0, 0, tzinfo=utc)) == (
        "manuscripts",
        "code",
    )
    assert manuscript_routes.shared_worker_order(datetime(2026, 9, 17, 0, 1, tzinfo=utc)) == (
        "code",
        "manuscripts",
    )
    assert manuscript_routes.shared_worker_order(datetime(2026, 9, 17, 0, 2, tzinfo=utc)) == (
        "code",
        "manuscripts",
    )
    assert manuscript_routes.shared_worker_order(datetime(2026, 9, 17, 0, 3, tzinfo=utc)) == (
        "manuscripts",
        "code",
    )
    config = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))
    assert {item["path"]: item["schedule"] for item in config["crons"]} == {
        "/api/cron/check-ins": "0 * * * *",
        "/api/cron/manuscripts": "* * * * *",
    }


@pytest.mark.asyncio
async def test_deferred_code_yields_the_same_cron_invocation_to_manuscripts(monkeypatch) -> None:
    calls: list[str] = []

    class DeferredCode:
        async def process_next(self, *, oidc_token):
            calls.append(f"code:{oidc_token}")
            return {
                "handled": False,
                "claimed": False,
                "deferred": True,
                "reason": "global_active_lease_limit",
                "retryAfterSeconds": 30,
            }

    class ClaimedManuscript:
        async def process_next_run(self):
            calls.append("manuscripts")
            return {"claimed": True, "status": "queued"}

    class Request:
        headers = {"authorization": "Bearer secret", "x-vercel-oidc-token": "oidc"}

    monkeypatch.setattr(
        manuscript_routes,
        "settings",
        SimpleNamespace(cron_secret="secret", vercel_oidc_token=None),
    )
    monkeypatch.setattr(manuscript_routes, "code_worker", DeferredCode())
    monkeypatch.setattr(manuscript_routes, "manuscripts", ClaimedManuscript())
    monkeypatch.setattr(
        manuscript_routes,
        "shared_worker_order",
        lambda at=None: ("code", "manuscripts"),
    )

    result = await manuscript_routes.manuscript_cron(Request())
    assert result == {
        "success": True,
        "worker": "manuscripts",
        "claimed": True,
        "status": "queued",
    }
    assert calls == ["code:oidc", "manuscripts"]


@pytest.mark.asyncio
async def test_reserved_manuscript_turn_does_not_touch_code(monkeypatch) -> None:
    calls: list[str] = []

    class Code:
        async def process_next(self, *, oidc_token):
            calls.append(f"code:{oidc_token}")
            return {"handled": True, "claimed": True}

    class Manuscript:
        async def process_next_run(self):
            calls.append("manuscripts")
            return {"claimed": True, "status": "queued"}

    class Request:
        headers = {"authorization": "Bearer secret", "x-vercel-oidc-token": "oidc"}

    monkeypatch.setattr(
        manuscript_routes,
        "settings",
        SimpleNamespace(cron_secret="secret", vercel_oidc_token=None),
    )
    monkeypatch.setattr(manuscript_routes, "code_worker", Code())
    monkeypatch.setattr(manuscript_routes, "manuscripts", Manuscript())
    monkeypatch.setattr(
        manuscript_routes,
        "shared_worker_order",
        lambda at=None: ("manuscripts", "code"),
    )

    result = await manuscript_routes.manuscript_cron(Request())
    assert result["worker"] == "manuscripts"
    assert calls == ["manuscripts"]


def test_deterministic_concurrency_oracle_allows_one_active_task_per_user() -> None:
    """Executable race oracle; real PostgreSQL proof remains a separate gate."""

    barrier = Barrier(2)
    transaction_lock = Lock()
    active_by_user: set[str] = set()

    def accept(task_id: str) -> tuple[str, bool]:
        barrier.wait()
        with transaction_lock:
            if USER_ID in active_by_user:
                return (task_id, False)
            active_by_user.add(USER_ID)
            return (task_id, True)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(accept, ("task-a", "task-b")))
    assert sorted(accepted for _task, accepted in results) == [False, True]
    assert active_by_user == {USER_ID}
